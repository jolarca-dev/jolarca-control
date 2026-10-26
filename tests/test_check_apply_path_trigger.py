"""Negative controls for scripts/check_apply_path_trigger.py (D-81).

AGENTS.md §7: a gate that runs and reports green has not been shown to detect anything.
This gate sits in a REQUIRED context, so its own failure modes are the dangerous ones —
a false positive would block every PR that touches Terraform (the A-01 / FA-control-03
deadlock class this repo keeps recording), and a false negative is exactly the defect it
exists to catch. Both directions are therefore pinned.

The glob cases are the regression that mattered most while writing it: `fnmatch`'s `*`
crosses `/`, so `*.tf` would match `modules/x.tf` and the gate would fire on a change that
cannot trigger anything. GitHub's `paths:` filter does not work that way (its own cheat sheet
says `'*.js'` "Matches all `.js` files at the root of the repository"), and a required check
that cries wolf is a gate people route around.

The permission case at the bottom is the defect this file caught *after* the gate was wired:
the D-81 step calls `gh api …/pulls/<n>/files` inside the `validate` job, and that job declares
its own `permissions:` — which replaces the workflow-level set, so `pull-requests` was `none`.
The call would have 403'd, the step would have failed, and a REQUIRED context would have gone
red on every PR in the repository. Offline, one assertion, before the push.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
GATE = ROOT / "scripts" / "check_apply_path_trigger.py"

APPLY_YML = """on:
  push:
    branches: [main]
    paths:
      - "repos/**"
      - "policy/**"
      - "*.tf"
      - "*.tfvars"
      - ".github/workflows/apply.yml"
  workflow_dispatch: {}
jobs:
  prod-apply:
    steps:
      - run: terraform apply -input=false -auto-approve tfplan
"""


def _load() -> Any:
    spec = importlib.util.spec_from_file_location("check_apply_path_trigger", GATE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _workflow(tmp_path: Path, text: str = APPLY_YML) -> Path:
    wf = tmp_path / "apply.yml"
    wf.write_text(text, encoding="utf-8")
    return wf


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(GATE), *args], capture_output=True, text=True)


# ── T2: glob semantics, the direction that would wedge ordinary work ──────────
def test_nested_tf_does_not_match_root_pattern(tmp_path: Path) -> None:
    """`*.tf` is a ROOT pattern; `modules/x.tf` cannot trigger apply.yml's push."""
    mod = _load()
    patterns = mod.read_trigger_paths(_workflow(tmp_path))
    assert mod.matching_paths(patterns, ["modules/x.tf"]) == []
    assert mod.matching_paths(patterns, ["main.tf"]) == ["main.tf"]
    code = _run(
        ["--workflow", str(_workflow(tmp_path)), "--changed", "modules/x.tf", "--actor-type", "Bot"]
    )
    assert code.returncode == 0, code.stdout + code.stderr
    assert "no apply armed" in code.stdout


def test_directory_patterns_match_at_depth(tmp_path: Path) -> None:
    mod = _load()
    patterns = mod.read_trigger_paths(_workflow(tmp_path))
    hits = mod.matching_paths(
        patterns, ["repos/jolarca.yml", "policy/repo-defaults.yml", "terraform.tfvars", "README.md"]
    )
    assert hits == ["repos/jolarca.yml", "policy/repo-defaults.yml", "terraform.tfvars"]


def test_dot_prefixed_path_is_not_mangled(tmp_path: Path) -> None:
    """THE regression for the first draft: `lstrip("./")` is a character-set strip.

    It turned `.github/workflows/apply.yml` into `github/workflows/apply.yml`, so the only
    path Dependabot edits in apply.yml's own trigger list silently stopped matching — an inert
    gate reporting clean. Asserted on both the dotted and the `./`-prefixed form.
    """
    mod = _load()
    patterns = mod.read_trigger_paths(_workflow(tmp_path))
    target = ".github/workflows/apply.yml"
    assert mod.matching_paths(patterns, [target]) == [target]
    assert mod.matching_paths(patterns, ["./" + target]) == ["./" + target]
    assert mod.matching_paths(patterns, ["github/workflows/apply.yml"]) == []


# ── the two verdicts the gate exists to separate ──────────────────────────────
def test_bot_touching_apply_yml_is_a_finding(tmp_path: Path) -> None:
    """Dependabot bumping a pinned action inside apply.yml == arming a production apply."""
    code = _run(
        [
            "--workflow",
            str(_workflow(tmp_path)),
            "--changed",
            ".github/workflows/apply.yml",
            "--actor-type",
            "Bot",
            "--actor",
            "dependabot[bot]",
        ]
    )
    assert code.returncode == 1, (code.stdout, code.stderr)
    assert "'dependabot[bot]' is a bot" in code.stdout
    assert "auto-approve" in code.stdout


def test_human_touching_apply_yml_passes_with_a_warning(tmp_path: Path) -> None:
    """Refusing human Terraform work would be a new deadlock; the gate announces instead."""
    code = _run(
        [
            "--workflow",
            str(_workflow(tmp_path)),
            "--changed",
            ".github/workflows/apply.yml",
            "--actor-type",
            "User",
            "--actor",
            "JourneyOfLife",
        ]
    )
    assert code.returncode == 0, (code.stdout, code.stderr)
    assert "NOTICE" in code.stdout and "production apply" in code.stdout


def test_bot_on_an_unrelated_file_passes(tmp_path: Path) -> None:
    code = _run(
        ["--workflow", str(_workflow(tmp_path)), "--changed", "README.md", "--actor-type", "Bot"]
    )
    assert code.returncode == 0, code.stdout


# ── T3/T4: never a silent pass ───────────────────────────────────────────────
def test_missing_diff_is_cannot_verify(tmp_path: Path) -> None:
    code = _run(["--workflow", str(_workflow(tmp_path)), "--actor-type", "Bot"])
    assert code.returncode == 2, (code.returncode, code.stdout, code.stderr)
    assert "CANNOT-VERIFY" in code.stderr


def test_empty_diff_is_cannot_verify_not_clean(tmp_path: Path) -> None:
    """An empty file list reads as 'nothing changed' and is the exact false-clean shape."""
    empty = tmp_path / "empty.txt"
    empty.write_text("\n\n", encoding="utf-8")
    code = _run(
        ["--workflow", str(_workflow(tmp_path)), "--files-from", str(empty), "--actor-type", "Bot"]
    )
    assert code.returncode == 2, (code.returncode, code.stdout, code.stderr)
    assert "lost input" in code.stderr or "empty" in code.stderr


def test_unreadable_diff_file_is_cannot_verify(tmp_path: Path) -> None:
    code = _run(
        [
            "--workflow",
            str(_workflow(tmp_path)),
            "--files-from",
            str(tmp_path / "nope.txt"),
            "--actor-type",
            "Bot",
        ]
    )
    assert code.returncode == 2, code.stdout + code.stderr


def test_unparseable_workflow_is_cannot_verify(tmp_path: Path) -> None:
    wf = tmp_path / "apply.yml"
    wf.write_text("on: [unclosed\n", encoding="utf-8")
    code = _run(["--workflow", str(wf), "--changed", "main.tf", "--actor-type", "Bot"])
    assert code.returncode == 2, (code.returncode, code.stdout, code.stderr)
    assert "cannot parse" in code.stderr


def test_workflow_without_paths_widens_instead_of_narrowing(tmp_path: Path) -> None:
    """No `paths:` means EVERY push triggers the apply — the widest case, not the empty one."""
    wf = _workflow(
        tmp_path,
        "on:\n  push:\n    branches: [main]\njobs:\n  a:\n    steps:\n"
        "      - run: terraform apply\n",
    )
    mod = _load()
    assert mod.read_trigger_paths(wf) == ["**"]
    code = _run(["--workflow", str(wf), "--changed", "docs/anything.md", "--actor-type", "App"])
    assert code.returncode == 1, (code.returncode, code.stdout, code.stderr)


def test_unknown_actor_on_a_match_is_cannot_verify(tmp_path: Path) -> None:
    """Judged only when a path matches, so ordinary PRs are untouched; then it is exit 2."""
    code = _run(["--workflow", str(_workflow(tmp_path)), "--changed", "main.tf"])
    assert code.returncode == 2, (code.returncode, code.stdout, code.stderr)
    assert "author kind is unknown" in code.stderr


# ── T5: a trigger set the gate cannot model is refused, not approximated ──────
def test_exclusion_pattern_in_paths_is_cannot_verify(tmp_path: Path) -> None:
    """`!repos/generated/**` makes last-match semantics decide — the gate will not guess.

    Treating a `!` entry as a positive pattern would refuse bot PRs that arm nothing; skipping
    it would pass a diff that arms everything. Both are verdicts the input does not support.
    """
    wf = _workflow(
        tmp_path,
        'on:\n  push:\n    branches: [main]\n    paths:\n      - "repos/**"\n'
        '      - "!repos/generated/**"\njobs:\n  a:\n    steps:\n      - run: terraform apply\n',
    )
    code = _run(["--workflow", str(wf), "--changed", "repos/jolarca.yml", "--actor-type", "Bot"])
    assert code.returncode == 2, (code.returncode, code.stdout, code.stderr)
    assert "exclusion pattern" in code.stderr


def test_paths_ignore_is_cannot_verify_not_widened(tmp_path: Path) -> None:
    """Widening `paths-ignore` to `**` would refuse every bot PR, including ones that arm nothing."""
    wf = _workflow(
        tmp_path,
        'on:\n  push:\n    branches: [main]\n    paths-ignore:\n      - "docs/**"\n'
        "jobs:\n  a:\n    steps:\n      - run: terraform apply\n",
    )
    code = _run(["--workflow", str(wf), "--changed", "main.tf", "--actor-type", "Bot"])
    assert code.returncode == 2, (code.returncode, code.stdout, code.stderr)
    assert "paths-ignore" in code.stderr


def test_actor_type_absent_from_the_gh_cli_projection_is_fail_closed(tmp_path: Path) -> None:
    """Why the CI wiring reads `github.event.pull_request.user.type`, not `gh pr view author.type`.

    Measured 2026-10-26: `gh pr view 87 --json author --jq .author.type` returns an EMPTY string,
    because the GraphQL `author` node has no `type` field — so passing it through would hand the
    gate an empty actor kind on exactly the apply-path PRs it must judge. The gate turns that into
    exit 2 rather than a pass; this case pins both halves of that behaviour.
    """
    mod = _load()
    patterns = mod.read_trigger_paths(_workflow(tmp_path))
    assert mod.matching_paths(patterns, [".github/workflows/apply.yml"])
    code = _run(
        [
            "--workflow",
            str(_workflow(tmp_path)),
            "--changed",
            ".github/workflows/apply.yml",
            "--actor-type",
            "",
            "--actor",
            "dependabot[bot]",
        ]
    )
    assert code.returncode == 2, (code.returncode, code.stdout, code.stderr)
    assert "author kind is unknown" in code.stderr


def test_report_only_never_fails(tmp_path: Path) -> None:
    """The live dry-run mode used against real PRs must not mutate any verdict path."""
    code = _run(
        [
            "--workflow",
            str(_workflow(tmp_path)),
            "--changed",
            "main.tf",
            "--actor-type",
            "Bot",
            "--report-only",
        ]
    )
    assert code.returncode == 0, (code.returncode, code.stdout, code.stderr)
    assert "APPLY-PATH CHANGE" in code.stdout


# ── the real repository ───────────────────────────────────────────────────────
def test_real_apply_yml_declares_the_documented_trigger_set() -> None:
    """Non-vacuity for T1: the paths are READ from apply.yml, and must still be 5."""
    mod = _load()
    patterns = mod.read_trigger_paths(ROOT / ".github" / "workflows" / "apply.yml")
    assert patterns == [
        "repos/**",
        "policy/**",
        "*.tf",
        "*.tfvars",
        ".github/workflows/apply.yml",
    ], patterns


def test_real_human_prs_do_not_trip_the_gate() -> None:
    """The three merges that shipped D-80 must all read as 'no apply armed'."""
    mod = _load()
    patterns = mod.read_trigger_paths(ROOT / ".github" / "workflows" / "apply.yml")
    for changed in (
        ["scripts/check_gate_parity.py", ".github/workflows/compliance-scan.yml", "Makefile"],
        ["docs/security/fleet-audit-2026-Q4/index.md", "CHANGELOG.md"],
        ["docs/drift-findings.md"],
    ):
        assert mod.matching_paths(patterns, changed) == [], changed


def test_real_dependabot_file_lists_would_be_refused() -> None:
    """PR #87 (setup-python) and #68 (upload-artifact) both edit apply.yml — the D-81 defect.

    Measured with `gh pr diff <n> --name-only` on 2026-10-26. If Dependabot ever stops
    including apply.yml, this case is the signal to re-read the PRs, not to delete the test.
    """
    mod = _load()
    patterns = mod.read_trigger_paths(ROOT / ".github" / "workflows" / "apply.yml")
    pr87 = [
        ".github/workflows/apply.yml",
        ".github/workflows/compliance-scan.yml",
        ".github/workflows/context-parity.yml",
        ".github/workflows/deploy-gates.yml",
        ".github/workflows/plan.yml",
        ".github/workflows/sast.yml",
    ]
    pr68 = [".github/workflows/apply.yml", ".github/workflows/evidence-integrity.yml"]
    assert mod.matching_paths(patterns, pr87) == [".github/workflows/apply.yml"]
    assert mod.matching_paths(patterns, pr68) == [".github/workflows/apply.yml"]


def test_gate_is_three_valued_on_the_real_tree() -> None:
    code = _run(["--changed", "README.md", "--actor-type", "User"])
    assert code.returncode == 0, code.stdout + code.stderr
    assert "no apply armed" in code.stdout


def test_permission_scope_for_the_d81_step_is_declared_at_job_level() -> None:
    """The step that gates merges must itself be able to run — checked statically, not in CI.

    GitHub's rule is explicit: "If you specify the access for any of these permissions, all of
    those that are not specified are set to `none`", and a job-level `permissions:` block is
    applied after the workflow-level one. The `validate` job declares `contents`/`actions`, so
    the workflow's `pull-requests: read` does not reach it — and `gh api …/pulls/<n>/files`
    returns 403 with `pull-requests: none`. Because this step sits in a REQUIRED context, that
    403 would have made every pull request in the repository unmergeable, not merely red.

    The assertion is paired with a check that the step is still in this job: if the step moves,
    this case fails and says to re-read where it went, rather than returning early and reporting
    green over nothing (AGENTS.md §7 — an early `return` once hid six filesystem checks).
    """
    doc = yaml.safe_load(
        (ROOT / ".github" / "workflows" / "compliance-scan.yml").read_text(encoding="utf-8")
    )
    job = next(j for j in doc["jobs"].values() if j.get("name") == "Validate Repo Allow-List")
    runs_gate = any(
        "check_apply_path_trigger.py" in str(step.get("run", "")) for step in job["steps"]
    )
    assert runs_gate, (
        "the D-81 step no longer runs in the required Validate Repo Allow-List job — "
        "find where it went and move this assertion with it"
    )
    perms = job.get("permissions") or {}
    assert perms.get("pull-requests") == "read", (
        f"the D-81 step calls the pulls REST API but this job's permissions are {perms} — "
        "an unspecified scope is `none`, the call 403s, and a required context fails on every PR"
    )
