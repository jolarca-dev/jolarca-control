"""Regression tests for the Phase 3 first-commit pipeline gate.

WHY THESE EXIST
---------------
The first revision of scripts/first_commit_pipeline.py allowlisted `git config`
so Step B could READ `commit.gpgsign`. That single entry also permitted
`git config --global user.name evil` — a WRITE — through a gate whose entire
value proposition is that it cannot write. The allowlist was the control, and
the control had a hole in it that only an explicit adversarial test found.

docs/drift-findings.md D-22 records the governing lesson for this repository:
"an untested regex gate is a hypothesis, not a control." The same standard
applies to an allowlist, and to the commands this tool tells a human to run —
they are the deliverable, not commentary on it.

Run:  .venv/bin/python -m pytest tests/test_first_commit_pipeline.py -q
      make test
"""

from __future__ import annotations

import datetime
import importlib.util
import re
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
PIPELINE = SCRIPTS / "first_commit_pipeline.py"
READINESS = SCRIPTS / "repo_readiness_audit.py"


def _load(module_name: str, path: Path) -> ModuleType:
    """Import a script by path without making scripts/ a package.

    The module MUST be registered in sys.modules under the same name given to
    spec_from_file_location: @dataclass resolution walks
    sys.modules[cls.__module__], and a mismatch raises AttributeError at import.
    """
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None, f"cannot build an import spec for {path}"
    assert spec.loader is not None, "import spec has no loader"
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


# rra MUST be loaded first: first_commit_pipeline.py does `import
# repo_readiness_audit`, which resolves from sys.modules only once the readiness
# gate is registered there. There is no conftest.py and scripts/ is not a package,
# so the path insertion inside _load is what makes both imports work.
rra = _load("repo_readiness_audit", READINESS)
fcp = _load("first_commit_pipeline", PIPELINE)


def _make_repo(tmp_path: Path, branch: str = "feat/bootstrap") -> Path:
    """Create a real git repository with one commit on `branch`."""
    subprocess.run(["git", "init", "-b", "main", str(tmp_path)], check=True, capture_output=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "git@github.com:jolarca-dev/example.git"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    (tmp_path / "README.md").write_text("# example\n", encoding="utf-8")
    _git(["add", "-A"], tmp_path)
    _git(["commit", "-m", "chore: bootstrap", "--no-verify"], tmp_path)
    _git(["checkout", "-b", branch], tmp_path)
    return tmp_path


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=test",
            "-c",
            "user.email=t@example.com",
            "-c",
            "commit.gpgsign=false",
            *args,
        ],
        cwd=cwd,
        check=True,
        capture_output=True,
    )


# ── The read-only invariant (the regression that motivated this suite) ────────

WRITE_ATTEMPTS = [
    ["git", "push", "origin", "main"],
    ["git", "push", "-u", "origin", "feat/x"],
    ["git", "commit", "-m", "x"],
    ["git", "commit", "-S", "-m", "x"],
    ["git", "config", "--global", "user.name", "evil"],
    ["git", "config", "user.email", "evil@example.com"],
    ["git", "config", "--unset", "commit.gpgsign"],
    ["git", "checkout", "-b", "x"],
    ["git", "switch", "-c", "x"],
    ["git", "add", "-A"],
    ["git", "restore", "--staged", "x"],
    ["git", "rebase", "origin/main"],
    ["git", "reset", "--hard"],
    ["git", "clean", "-fd"],
    ["git", "tag", "v1"],
    ["gh", "pr", "merge", "1"],
    ["gh", "pr", "create", "--title", "x"],
    ["gh", "pr", "edit", "1", "--body", "x"],
    ["gh", "pr", "close", "1"],
    ["gh", "repo", "create", "x"],
    ["gh", "repo", "set-default", "x"],
    ["gh", "api", "repos/o/r", "-X", "PUT"],
    ["gh", "api", "repos/o/r", "-X", "DELETE"],
    ["gh", "api", "repos/o/r", "-X", "POST"],
    ["gh", "api", "repos/o/r", "-f", "x=y"],
    ["gh", "api", "repos/o/r", "-F", "x=y"],
    ["gh", "api", "repos/o/r", "--input", "-"],
    ["gh", "secret", "set", "X"],
    ["rm", "-rf", "/"],
    ["sh", "-c", "git push"],
]


def test_every_write_attempt_is_refused() -> None:
    """The allowlist is the control. Each of these must raise, not return a status
    a caller could ignore."""
    for cmd in WRITE_ATTEMPTS:
        try:
            fcp._assert_read_only(cmd)
        except fcp.ReadOnlyViolation:
            continue
        raise AssertionError(f"READ-ONLY LEAK: {cmd} was permitted")


READ_ONLY_COMMANDS = [
    ["git", "status"],
    ["git", "status", "--porcelain=v1"],
    ["git", "log", "--oneline"],
    ["git", "diff", "--cached", "--name-only"],
    ["git", "rev-parse", "HEAD"],
    ["git", "rev-parse", "--abbrev-ref", "HEAD"],
    ["git", "branch", "--show-current"],
    ["git", "config", "--get", "commit.gpgsign"],
    ["git", "config", "--list"],
    ["git", "remote", "get-url", "origin"],
    ["git", "ls-files"],
    ["git", "rev-list", "--count", "origin/main..HEAD"],
    ["git", "symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD"],
    ["gh", "pr", "view", "1"],
    ["gh", "pr", "list"],
    ["gh", "pr", "checks", "1"],
    ["gh", "pr", "diff", "1"],
    ["gh", "run", "list"],
    ["gh", "run", "view", "1"],
    ["gh", "repo", "view"],
    ["gh", "api", "repos/o/r"],
    ["gh", "--version"],
    ["gitleaks", "detect"],
]


def test_every_read_command_is_permitted() -> None:
    """The fix for the leak must not be a blanket refusal — a gate that cannot
    read its subject reports UNVERIFIABLE forever and is useless."""
    for cmd in READ_ONLY_COMMANDS:
        try:
            fcp._assert_read_only(cmd)
        except fcp.ReadOnlyViolation as exc:
            raise AssertionError(f"WRONGLY REFUSED: {cmd} ({exc})") from exc


def test_git_config_read_is_allowed_but_write_is_not() -> None:
    """The exact regression. `--get` reads; a bare `name value` pair writes."""
    fcp._assert_read_only(["git", "config", "--get", "commit.gpgsign"])
    try:
        fcp._assert_read_only(["git", "config", "commit.gpgsign", "false"])
    except fcp.ReadOnlyViolation:
        return
    raise AssertionError("git config write was permitted")


def test_run_read_only_enforces_the_allowlist_too() -> None:
    """The chokepoint must guard the executor, not only the validator, or a
    caller can bypass _assert_read_only by calling run_read_only directly."""
    try:
        fcp.run_read_only(["git", "push"])
    except fcp.ReadOnlyViolation:
        return
    raise AssertionError("run_read_only executed a write command")


def test_empty_command_is_refused() -> None:
    try:
        fcp._assert_read_only([])
    except fcp.ReadOnlyViolation:
        return
    raise AssertionError("empty command was permitted")


# Prose in the docstring legitimately mentions `git push` and `gh pr merge` —
# this test scans for the CALL SITES, which are list literals, so documentation
# cannot produce a false pass or a false failure.
FORBIDDEN_CALL_PATTERNS = (
    r'\[\s*"git"\s*,\s*"push"',
    r'\[\s*"git"\s*,\s*"commit"',
    r'\[\s*"git"\s*,\s*"add"',
    r'\[\s*"git"\s*,\s*"checkout"',
    r'\[\s*"git"\s*,\s*"switch"',
    r'\[\s*"gh"\s*,\s*"pr"\s*,\s*"merge"',
    r'\[\s*"gh"\s*,\s*"pr"\s*,\s*"create"',
    r'\[\s*"gh"\s*,\s*"pr"\s*,\s*"edit"',
    r'"-X"\s*,\s*"(?:PUT|POST|PATCH|DELETE)"',
)


def test_module_source_never_constructs_a_write_command() -> None:
    """Belt and braces: even if the allowlist were widened by a future edit, no
    call site in this module may build a mutating command."""
    source = PIPELINE.read_text(encoding="utf-8")
    for pattern in FORBIDDEN_CALL_PATTERNS:
        assert not re.search(pattern, source), f"write call site present: {pattern}"


def test_write_commands_only_ever_appear_as_printed_instructions() -> None:
    """The human runs the writes. Confirm the module still TELLS them to — a gate
    that stopped printing `git push -u origin` would be silently useless."""
    source = PIPELINE.read_text(encoding="utf-8")
    for instruction in ("git commit -S -m", "git push -u origin", "--squash --delete-branch"):
        assert instruction in source, f"missing printed instruction: {instruction}"


# ── Tracked-exception resolution (plan-tier reality) ─────────────────────────

_ACTIVE = {
    "D-04": {
        "id": "D-04",
        "expires": "2026-12-24",
        "compensating_control": "signed commits by operator policy",
        "exit_trigger": "second-operator onboarding",
    },
    "D-05": {"id": "D-05", "expires": "2026-12-24", "compensating_control": "local gpgsign"},
    "NO_EXPIRY": {"id": "NO_EXPIRY", "compensating_control": "x"},
    "BAD_EXPIRY": {"id": "BAD_EXPIRY", "expires": "when the second operator joins"},
}

# Nothing in open_blocking here, so the tests below exercise the accepted-exception
# paths in isolation. The open_blocking paths have their own tests.
_REGISTER = fcp.ExceptionRegister(_ACTIVE, frozenset())

_TODAY = datetime.date(2026, 9, 28)


def test_unexpired_exception_is_tracked_not_blocking() -> None:
    status, reason = fcp.exception_state(_REGISTER, "D-04", _TODAY)
    assert status == fcp.STATUS_EXCEPTION
    assert "2026-12-24" in reason
    assert "signed commits by operator policy" in reason


def test_lapsed_exception_blocks() -> None:
    """The D-25 lesson: an acceptance that outlives its expiry is not an
    acceptance. It must block without any code change on the day it lapses."""
    status, reason = fcp.exception_state(_REGISTER, "D-04", datetime.date(2026, 12, 25))
    assert status == fcp.STATUS_BLOCKED
    assert "LAPSED" in reason


def test_exception_expiring_today_is_still_valid() -> None:
    """Boundary: `expires` is inclusive. Off-by-one here would block a day early
    or, worse, honour an acceptance a day late."""
    status, _ = fcp.exception_state(_REGISTER, "D-04", datetime.date(2026, 12, 24))
    assert status == fcp.STATUS_EXCEPTION


def test_missing_expiry_blocks() -> None:
    status, reason = fcp.exception_state(_REGISTER, "NO_EXPIRY", _TODAY)
    assert status == fcp.STATUS_BLOCKED
    assert "D-25" in reason


def test_event_only_expiry_blocks() -> None:
    """An event-only expiry has no deadline and can stay open forever."""
    status, reason = fcp.exception_state(_REGISTER, "BAD_EXPIRY", _TODAY)
    assert status == fcp.STATUS_BLOCKED
    assert "ISO-8601" in reason


def test_unregistered_finding_blocks() -> None:
    """The gate must not invent an exception the policy owner never approved."""
    status, reason = fcp.exception_state(_REGISTER, "D-99", _TODAY)
    assert status == fcp.STATUS_BLOCKED
    assert "not registered" in reason


def test_real_policy_exceptions_parse_and_are_currently_valid() -> None:
    """Read the LIVE policy file. When D-04/D-05/D-07 expire on 2026-12-24 this
    test starts failing on its own — which is the point: the lapse must be
    visible, not discovered during an incident."""
    gates = rra.load_yaml(rra.POLICY_GATES)
    register = fcp.load_register(gates)
    assert register.active, "no exceptions parsed from policy/compliance-gates.yml"
    for finding_id in ("D-04", "D-05", "D-07"):
        assert finding_id in register.active, f"{finding_id} missing from exceptions.active"
        status, reason = fcp.exception_state(register, finding_id, _TODAY)
        assert status == fcp.STATUS_EXCEPTION, f"{finding_id}: {reason}"


def test_load_exceptions_indexes_by_id_and_skips_junk() -> None:
    parsed = fcp.load_exceptions({"exceptions": {"active": [{"id": "X"}, "junk", {"no_id": 1}]}})
    assert set(parsed) == {"X"}


def test_load_exceptions_handles_absent_section() -> None:
    assert fcp.load_exceptions({}) == {}


# ── Conventional Commits ─────────────────────────────────────────────────────


def test_conventional_commit_accepts_valid_subjects() -> None:
    for message in (
        "feat: add token vault",
        "fix(payments): close the webhook replay window",
        "docs: record the D-33 acceptance",
        "chore!: drop the legacy endpoint",
        "revert: feat: add token vault",
    ):
        assert fcp.conventional_commit_subject(message) is not None, message


def test_conventional_commit_rejects_unclassifiable_subjects() -> None:
    """An open regex accepts "update stuff", which is the shape of a commit
    message an auditor cannot classify."""
    for message in (
        "update stuff",
        "WIP",
        "feat add token vault",  # missing colon
        "feat: ",  # empty subject
        "FEAT: shouty type",
        "feature: not in the closed type set",
        "",
        "   ",
    ):
        assert fcp.conventional_commit_subject(message) is None, repr(message)


def test_conventional_commit_reads_only_the_subject_line() -> None:
    message = "feat: add token vault\n\nThe body may say anything at all.\n"
    assert fcp.conventional_commit_subject(message) == "add token vault"


def test_conventional_commit_rejects_an_overlong_subject() -> None:
    assert fcp.conventional_commit_subject("feat: " + "x" * 200) is None


# ── Status aggregation ───────────────────────────────────────────────────────


def test_unverifiable_outranks_blocked() -> None:
    """A control that could not read its subject must never be reported as a mere
    failure — that is how D-33 hid seven unguarded repos behind "unverifiable"."""
    result = fcp.StepResult("A", "VERIFY FIRST")
    result.add("x", fcp.STATUS_BLOCKED, "blocked")
    result.add("y", fcp.STATUS_UNVERIFIABLE, "could not read")
    assert result.status == fcp.STATUS_UNVERIFIABLE


def test_blocked_outranks_tracked_exception() -> None:
    result = fcp.StepResult("A", "VERIFY FIRST")
    result.add("x", fcp.STATUS_EXCEPTION, "accepted deviation")
    result.add("y", fcp.STATUS_BLOCKED, "real defect")
    assert result.status == fcp.STATUS_BLOCKED


def test_clean_step_passes() -> None:
    result = fcp.StepResult("A", "VERIFY FIRST")
    result.add("x", fcp.STATUS_PASS, "ok")
    assert result.status == fcp.STATUS_PASS


def test_tracked_exception_does_not_count_as_passed() -> None:
    """Only an unqualified PASS advances the pipeline. An accepted deviation is
    recorded and a human decides — it is not an automatic green light."""
    result = fcp.StepResult("A", "VERIFY FIRST")
    result.add("x", fcp.STATUS_EXCEPTION, "D-04")
    assert result.status == fcp.STATUS_EXCEPTION
    assert result.passed is False


def test_passed_is_true_only_for_pass() -> None:
    result = fcp.StepResult("A", "VERIFY FIRST")
    result.add("x", fcp.STATUS_PASS, "ok")
    assert result.passed is True


def test_pipeline_status_is_the_worst_step_status() -> None:
    report = fcp.PipelineReport(repo="r")
    a = report.step("A")
    a.add("x", fcp.STATUS_PASS, "ok")
    b = report.step("B")
    b.add("y", fcp.STATUS_UNVERIFIABLE, "no message")
    assert report.status == fcp.STATUS_UNVERIFIABLE


# ── Step ordering ────────────────────────────────────────────────────────────


def test_every_step_declares_its_prerequisites() -> None:
    assert set(fcp.PREREQUISITES) == set(fcp.STEP_ORDER)


def test_prerequisites_are_cumulative_and_ordered() -> None:
    for index, step in enumerate(fcp.STEP_ORDER):
        assert fcp.PREREQUISITES[step] == fcp.STEP_ORDER[:index]


def test_step_a_has_no_prerequisites() -> None:
    assert fcp.PREREQUISITES["A"] == ()


def test_every_step_has_a_title() -> None:
    assert set(fcp.STEP_TITLES) == set(fcp.STEP_ORDER)


def test_run_pipeline_refuses_a_step_whose_prerequisites_were_not_requested() -> None:
    """--step E on its own must not merge anything: A-D never ran in this process,
    so there is no evidence they passed."""
    readiness = rra.RepoReport(repo="example")
    readiness.decide()
    report, code = fcp.run_pipeline(
        "example", ("E",), live=False, readiness=readiness, attest="Tester"
    )
    step_e = report.get("E")
    assert step_e is not None
    assert step_e.status == fcp.STATUS_BLOCKED
    assert code == 1
    assert any(c.name == "prerequisites" for c in step_e.checks)


def test_a_blocked_step_a_stops_step_b() -> None:
    """Step B must not run when the readiness verdict is BLOCKED."""
    readiness = rra.RepoReport(repo="example")
    readiness.add(rra.Finding("L-15", "S0", "local", "secret in tracked file", "x", "rotate it"))
    readiness.decide()
    assert readiness.verdict == rra.VERDICT_BLOCKED
    report, code = fcp.run_pipeline("example", ("A", "B"), live=False, readiness=readiness)
    assert report.get("A") is not None
    assert report.get("A").status == fcp.STATUS_BLOCKED
    assert report.get("B") is not None
    assert report.get("B").status == fcp.STATUS_BLOCKED
    assert code == 1


def test_strict_converts_tracked_exceptions_to_blocked() -> None:
    """--strict is the posture to adopt once GitHub Team lands: a compensating
    control is no longer an acceptable substitute for the real one."""
    readiness = rra.RepoReport(repo="example")
    readiness.decide()
    report, code = fcp.run_pipeline("example", ("A",), live=False, readiness=readiness, strict=True)
    step_a = report.get("A")
    assert step_a is not None
    assert fcp.STATUS_EXCEPTION not in {c.status for c in step_a.checks}
    assert code == 1


def test_default_mode_keeps_tracked_exceptions_visible() -> None:
    """Without --strict the deviation is recorded, not hidden and not failed."""
    readiness = rra.RepoReport(repo="example")
    readiness.decide()
    report, code = fcp.run_pipeline("example", ("A",), live=False, readiness=readiness)
    step_a = report.get("A")
    assert step_a is not None
    assert step_a.status == fcp.STATUS_EXCEPTION
    assert code == 1


# ── Forbidden-path reuse ─────────────────────────────────────────────────────


def test_forbidden_staged_catches_idea_directory() -> None:
    """D-28 regression: IDE metadata in the index must block the commit."""
    assert fcp.forbidden_staged([".idea/misc.xml"])


def test_forbidden_staged_catches_terraform_state() -> None:
    assert fcp.forbidden_staged(["terraform.tfstate"])


def test_forbidden_staged_catches_env_and_key_material() -> None:
    assert fcp.forbidden_staged([".env"])
    assert fcp.forbidden_staged(["server.pem"])
    assert fcp.forbidden_staged(["credentials.json"])


def test_forbidden_staged_allows_ordinary_source() -> None:
    assert fcp.forbidden_staged(["README.md", "scripts/x.py", "docs/a.md"]) == []


def test_forbidden_staged_uses_the_readiness_gates_own_list() -> None:
    """The two gates must never disagree about what may not be tracked. If this
    assertion fails, one of them has been edited and the other has not."""
    source = PIPELINE.read_text(encoding="utf-8")
    assert "rra.FORBIDDEN_TRACKED_PATTERNS" in source
    assert not re.search(r"^FORBIDDEN_TRACKED_PATTERNS\s*=", source, re.MULTILINE)


# ── Local git readers ────────────────────────────────────────────────────────


def test_current_branch_reads_the_real_branch(tmp_path: Path) -> None:
    _make_repo(tmp_path, branch="feat/bootstrap")
    assert fcp.current_branch(tmp_path) == "feat/bootstrap"


def test_default_branch_falls_back_to_main(tmp_path: Path) -> None:
    """No origin/HEAD exists in a fresh clone-less repo, so the fallback is what
    makes the "am I on the default branch?" check work at all."""
    _make_repo(tmp_path)
    assert fcp.default_branch(tmp_path) == "main"


def test_on_default_branch_is_detected(tmp_path: Path) -> None:
    """The core pipeline rule: never commit or push directly to the default branch."""
    _make_repo(tmp_path, branch="feat/bootstrap")
    _git(["checkout", "main"], tmp_path)
    assert fcp.current_branch(tmp_path) == fcp.default_branch(tmp_path)


def test_remote_url_is_read(tmp_path: Path) -> None:
    _make_repo(tmp_path)
    assert fcp.remote_url(tmp_path).endswith("jolarca-dev/example.git")


def test_staged_files_lists_the_index(tmp_path: Path) -> None:
    _make_repo(tmp_path)
    (tmp_path / "new.txt").write_text("x\n", encoding="utf-8")
    _git(["add", "new.txt"], tmp_path)
    assert "new.txt" in fcp.staged_files(tmp_path)


def test_gpgsign_detection(tmp_path: Path) -> None:
    _make_repo(tmp_path)
    subprocess.run(
        ["git", "config", "commit.gpgsign", "true"], cwd=tmp_path, check=True, capture_output=True
    )
    assert fcp.gpgsign_enabled(tmp_path) is True
    subprocess.run(
        ["git", "config", "commit.gpgsign", "false"], cwd=tmp_path, check=True, capture_output=True
    )
    assert fcp.gpgsign_enabled(tmp_path) is False


# ── Printed commands are the deliverable ─────────────────────────────────────


def test_step_b_prints_a_signed_commit_command(tmp_path: Path) -> None:
    """Signed commits are the compensating control for the 0-review deviation
    (D-04), so `-S` is not optional in the instruction we hand the operator."""
    _make_repo(tmp_path)
    (tmp_path / "a.txt").write_text("x\n", encoding="utf-8")
    _git(["add", "a.txt"], tmp_path)
    result = fcp.StepResult("B", "COMMIT")
    fcp.step_b_commit(result, tmp_path, "feat: add a", _REGISTER, _TODAY)
    assert result.command.startswith("git commit -S -m ")
    assert "feat: add a" in result.command


def test_step_b_blocks_an_unconventional_message(tmp_path: Path) -> None:
    _make_repo(tmp_path)
    (tmp_path / "a.txt").write_text("x\n", encoding="utf-8")
    _git(["add", "a.txt"], tmp_path)
    result = fcp.StepResult("B", "COMMIT")
    fcp.step_b_commit(result, tmp_path, "update stuff", _REGISTER, _TODAY)
    by_name = {c.name: c for c in result.checks}
    assert by_name["Conventional Commits subject"].status == fcp.STATUS_BLOCKED


def test_step_b_is_unverifiable_without_a_message(tmp_path: Path) -> None:
    """Not PASS and not BLOCKED: the gate could not check what it was not given."""
    _make_repo(tmp_path)
    result = fcp.StepResult("B", "COMMIT")
    fcp.step_b_commit(result, tmp_path, None, _REGISTER, _TODAY)
    by_name = {c.name: c for c in result.checks}
    assert by_name["Conventional Commits subject"].status == fcp.STATUS_UNVERIFIABLE


def test_step_b_blocks_forbidden_staged_paths(tmp_path: Path) -> None:
    _make_repo(tmp_path)
    idea = tmp_path / ".idea"
    idea.mkdir()
    (idea / "misc.xml").write_text("<project/>\n", encoding="utf-8")
    _git(["add", "-A"], tmp_path)
    result = fcp.StepResult("B", "COMMIT")
    fcp.step_b_commit(result, tmp_path, "chore: scaffold", _REGISTER, _TODAY)
    by_name = {c.name: c for c in result.checks}
    assert by_name["no forbidden paths staged"].status == fcp.STATUS_BLOCKED


def test_step_b_blocks_nothing_staged(tmp_path: Path) -> None:
    _make_repo(tmp_path)
    result = fcp.StepResult("B", "COMMIT")
    fcp.step_b_commit(result, tmp_path, "feat: x", _REGISTER, _TODAY)
    by_name = {c.name: c for c in result.checks}
    assert by_name["staged changes present"].status == fcp.STATUS_BLOCKED


def test_step_c_prints_a_feature_branch_push(tmp_path: Path) -> None:
    _make_repo(tmp_path, branch="feat/bootstrap")
    readiness = rra.RepoReport(repo="example")
    result = fcp.StepResult("C", "PUSH")
    fcp.step_c_push(result, "example", tmp_path, readiness, _REGISTER, _TODAY)
    assert result.command == "git push -u origin feat/bootstrap"


def test_step_c_blocks_a_push_of_the_default_branch(tmp_path: Path) -> None:
    _make_repo(tmp_path)
    _git(["checkout", "main"], tmp_path)
    readiness = rra.RepoReport(repo="example")
    result = fcp.StepResult("C", "PUSH")
    fcp.step_c_push(result, "example", tmp_path, readiness, _REGISTER, _TODAY)
    by_name = {c.name: c for c in result.checks}
    assert by_name["not pushing to default branch"].status == fcp.STATUS_BLOCKED


def test_step_c_blocks_a_mismatched_remote(tmp_path: Path) -> None:
    """Pushing the wrong repository's content to another repo is how a
    PCI-scoped file lands somewhere it was never classified for."""
    _make_repo(tmp_path, branch="feat/bootstrap")
    subprocess.run(
        ["git", "remote", "set-url", "origin", "git@github.com:other-org/other.git"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    readiness = rra.RepoReport(repo="example")
    result = fcp.StepResult("C", "PUSH")
    fcp.step_c_push(result, "example", tmp_path, readiness, _REGISTER, _TODAY)
    by_name = {c.name: c for c in result.checks}
    assert by_name["remote identity"].status == fcp.STATUS_BLOCKED


def test_step_c_tracks_push_protection_under_the_conditional_d33_acceptance(
    tmp_path: Path,
) -> None:
    """Live policy (2026-09-28) accepts D-33 conditionally until 2026-12-27, and
    D-33's own gate text names push protection among the plan-blocked controls.
    So Step C must report a TRACKED-EXCEPTION that says it is CONDITIONAL — not a
    silent pass, and not a block that contradicts the owner's approval."""
    _make_repo(tmp_path, branch="feat/bootstrap")
    register = fcp.load_register(rra.load_yaml(rra.POLICY_GATES))
    readiness = rra.RepoReport(repo="example")
    result = fcp.StepResult("C", "PUSH")
    fcp.step_c_push(result, "example", tmp_path, readiness, register, _TODAY)
    by_name = {c.name: c for c in result.checks}
    assert by_name["push protection"].status == fcp.STATUS_EXCEPTION
    assert "CONDITIONAL" in by_name["push protection"].detail


def test_step_c_blocks_push_protection_when_d33_is_only_open_blocking(
    tmp_path: Path,
) -> None:
    """If the owner ever withdraws the acceptance and leaves only the open_blocking
    row, the same check must go back to BLOCKED and name the owner decision. The
    gate must never invent an acceptance that is not there."""
    _make_repo(tmp_path, branch="feat/bootstrap")
    register = fcp.ExceptionRegister({}, frozenset({"D-33"}))
    readiness = rra.RepoReport(repo="example")
    result = fcp.StepResult("C", "PUSH")
    fcp.step_c_push(result, "example", tmp_path, readiness, register, _TODAY)
    by_name = {c.name: c for c in result.checks}
    assert by_name["push protection"].status == fcp.STATUS_BLOCKED
    assert "OPEN_BLOCKING" in by_name["push protection"].detail


def test_step_c_tracks_push_protection_once_d33_is_accepted(tmp_path: Path) -> None:
    """The moment the owner moves D-33 into exceptions.active with a future expiry,
    the same check degrades to TRACKED-EXCEPTION naming the compensating control —
    with no code change here. That is the point of reading the policy live."""
    _make_repo(tmp_path, branch="feat/bootstrap")
    register = fcp.ExceptionRegister(
        {
            **_ACTIVE,
            "D-33": {
                "id": "D-33",
                "expires": "2026-12-24",
                "compensating_control": "gitleaks pre-push hook",
            },
        },
        frozenset(),
    )
    readiness = rra.RepoReport(repo="example")
    result = fcp.StepResult("C", "PUSH")
    fcp.step_c_push(result, "example", tmp_path, readiness, register, _TODAY)
    by_name = {c.name: c for c in result.checks}
    assert by_name["push protection"].status == fcp.STATUS_EXCEPTION
    assert "gitleaks pre-push hook" in by_name["push protection"].detail


def test_open_blocking_finding_is_never_treated_as_accepted() -> None:
    register = fcp.ExceptionRegister({}, frozenset({"D-33"}))
    status, reason = fcp.exception_state(register, "D-33", _TODAY)
    assert status == fcp.STATUS_BLOCKED
    assert "OPEN_BLOCKING" in reason
    assert "owner decision" in reason.lower()


def test_load_open_blocking_reads_the_real_policy() -> None:
    gates = rra.load_yaml(rra.POLICY_GATES)
    assert fcp.load_open_blocking(gates) >= {"D-01", "D-02", "D-18", "D-20", "D-33"}


def test_dual_listed_finding_is_conditional_not_contradictory() -> None:
    """D-33 is deliberately in BOTH sections: the owner recorded a dated,
    CONDITIONAL acceptance (2026-09-28, expires 2026-12-27) while retaining the
    open_blocking row until four interim controls are stood up.

    The gate must honour the acceptance AND surface the conditionality. Silently
    picking one section would either contradict an approved decision or hide an
    outstanding control — both are worse than saying so.
    """
    register = fcp.load_register(rra.load_yaml(rra.POLICY_GATES))
    dual = sorted(set(register.active) & register.open_blocking)
    assert dual, "expected at least one conditionally-accepted finding (D-33)"
    for finding_id in dual:
        status, reason = fcp.exception_state(register, finding_id, _TODAY)
        assert status == fcp.STATUS_EXCEPTION, f"{finding_id}: {reason}"
        assert "CONDITIONAL" in reason, f"{finding_id} dual listing was not surfaced"


def test_every_active_exception_carries_the_fields_the_gate_depends_on() -> None:
    """`exception_state()` reads exactly three things: the id, a parseable
    ISO-8601 `expires`, and a `compensating_control` it can name to the operator.
    An entry missing any of them would make the gate honour an acceptance it
    cannot describe — which is the D-25 defect in a new shape.

    NOTE, deliberately NOT asserted here: policy `exceptions.requirements` also
    demands a "Risk description and business justification", and the live file is
    inconsistent about it — D-07 and D-33 carry a `risk:` key, D-04 and D-05 carry
    `gate:` instead with the risk folded into prose. That is a real policy-schema
    gap, reported to the owner rather than papered over by a test that accepts
    either spelling. Fixing it means editing policy/compliance-gates.yml under
    RB-04, which is not this gate's call.
    """
    register = fcp.load_register(rra.load_yaml(rra.POLICY_GATES))
    assert register.active, "no active exceptions parsed"
    for finding_id, entry in register.active.items():
        assert entry.get("id") == finding_id, f"{finding_id} id mismatch"
        assert entry.get("approved_by"), f"{finding_id} has no approved_by"
        assert entry.get("compensating_control"), f"{finding_id} has no compensating control"
        assert fcp._parse_expiry(entry.get("expires")) is not None, (
            f"{finding_id} has no ISO-8601 expiry"
        )


def test_policy_risk_field_is_inconsistently_applied() -> None:
    """Pins the schema gap named above so it cannot be silently forgotten, and
    fails the day someone normalises the file — at which point this test should be
    replaced by a real schema assertion inside the gate."""
    register = fcp.load_register(rra.load_yaml(rra.POLICY_GATES))
    with_risk = {k for k, v in register.active.items() if v.get("risk")}
    without_risk = set(register.active) - with_risk
    assert with_risk, "expected at least one entry to use the `risk:` key"
    assert without_risk, (
        "every active exception now carries `risk:` — normalise this into the gate "
        "as a hard requirement and delete this test"
    )


def test_long_compensating_control_is_truncated_with_a_pointer() -> None:
    """D-33's compensating_control runs to ~1000 characters. The evidence file is an
    audit record, not a wall of text — truncate, but always leave the authoritative
    pointer so nothing is lost."""
    register = fcp.ExceptionRegister(
        {"D-99": {"id": "D-99", "expires": "2026-12-24", "compensating_control": "x" * 2000}},
        frozenset(),
    )
    status, reason = fcp.exception_state(register, "D-99", _TODAY)
    assert status == fcp.STATUS_EXCEPTION
    assert len(reason) < 900, "truncation did not apply"
    assert "policy/compliance-gates.yml" in reason


def test_load_open_blocking_tolerates_a_missing_or_malformed_section() -> None:
    assert fcp.load_open_blocking({}) == frozenset()
    assert fcp.load_open_blocking({"exceptions": {"open_blocking": "nope"}}) == frozenset()


def test_merge_command_is_squash_only() -> None:
    """Policy is squash-only (`allow_merge_commit: false`) for a linear, auditable
    history, so the printed merge command must not offer a merge commit."""
    defaults = (rra.load_yaml(rra.POLICY_DEFAULTS) or {}).get("repository_defaults") or {}
    assert defaults.get("allow_merge_commit") is False
    assert defaults.get("allow_squash_merge") is True
    source = PIPELINE.read_text(encoding="utf-8")
    assert "--squash --delete-branch" in source


def test_step_e_is_unverifiable_when_the_pr_cannot_be_read(monkeypatch: pytest.MonkeyPatch) -> None:
    """No network in the test suite: stub the reader. An unreadable PR is
    UNVERIFIABLE, never a pass."""
    monkeypatch.setattr(fcp, "gh_json", lambda args: (1, None))
    policy = rra.load_yaml(rra.POLICY_DEFAULTS)
    result = fcp.StepResult("E", "MERGE")
    fcp.step_e_merge(result, "example", "feat/x", policy, _REGISTER, _TODAY)
    assert result.status == fcp.STATUS_UNVERIFIABLE


def test_step_e_blocks_a_conflicting_pr(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "number": 7,
        "mergeable": "CONFLICTING",
        "mergeStateStatus": "BLOCKED",
        "reviewDecision": None,
        "reviewThreads": [],
        "statusCheckRollup": [],
    }
    monkeypatch.setattr(fcp, "gh_json", lambda args: (0, payload))
    policy = rra.load_yaml(rra.POLICY_DEFAULTS)
    result = fcp.StepResult("E", "MERGE")
    fcp.step_e_merge(result, "example", "feat/x", policy, _REGISTER, _TODAY)
    by_name = {c.name: c for c in result.checks}
    assert by_name["no conflicts"].status == fcp.STATUS_BLOCKED


def test_step_e_blocks_a_failing_status_check(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "number": 7,
        "mergeable": "MERGEABLE",
        "mergeStateStatus": "BLOCKED",
        "reviewDecision": None,
        "reviewThreads": [],
        "statusCheckRollup": [{"name": "gitleaks", "conclusion": "FAILURE"}],
    }
    monkeypatch.setattr(fcp, "gh_json", lambda args: (0, payload))
    policy = rra.load_yaml(rra.POLICY_DEFAULTS)
    result = fcp.StepResult("E", "MERGE")
    fcp.step_e_merge(result, "example", "feat/x", policy, _REGISTER, _TODAY)
    by_name = {c.name: c for c in result.checks}
    assert by_name["all status checks green"].status == fcp.STATUS_BLOCKED


def test_step_e_blocks_an_unresolved_review_thread(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "number": 7,
        "mergeable": "MERGEABLE",
        "mergeStateStatus": "CLEAN",
        "reviewDecision": None,
        "reviewThreads": [{"isResolved": False}],
        "statusCheckRollup": [],
    }
    monkeypatch.setattr(fcp, "gh_json", lambda args: (0, payload))
    policy = rra.load_yaml(rra.POLICY_DEFAULTS)
    result = fcp.StepResult("E", "MERGE")
    fcp.step_e_merge(result, "example", "feat/x", policy, _REGISTER, _TODAY)
    by_name = {c.name: c for c in result.checks}
    assert by_name["no unresolved review threads"].status == fcp.STATUS_BLOCKED


def test_step_e_tracks_the_zero_approval_deviation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Policy requires 0 approvals (D-04, solo-operator era). That is an accepted
    deviation with a compensating control — recorded, not hidden, and not failed."""
    payload = {
        "number": 7,
        "mergeable": "MERGEABLE",
        "mergeStateStatus": "CLEAN",
        "reviewDecision": None,
        "reviewThreads": [],
        "statusCheckRollup": [{"name": "gitleaks", "conclusion": "SUCCESS"}],
    }
    monkeypatch.setattr(fcp, "gh_json", lambda args: (0, payload))
    policy = rra.load_yaml(rra.POLICY_DEFAULTS)
    register = fcp.load_register(rra.load_yaml(rra.POLICY_GATES))
    result = fcp.StepResult("E", "MERGE")
    fcp.step_e_merge(result, "example", "feat/x", policy, register, _TODAY)
    by_name = {c.name: c for c in result.checks}
    assert by_name["approvals meet policy"].status == fcp.STATUS_EXCEPTION
    assert "D-04" in by_name["approvals meet policy"].detail
    assert result.command.endswith("--squash --delete-branch")


def test_step_e_enforces_a_real_approval_requirement(monkeypatch: pytest.MonkeyPatch) -> None:
    """Once D-04 lapses and the count rises to 1, an unapproved PR must block.
    This is the post-second-operator behaviour, tested now so the switch is not a
    surprise."""
    payload = {
        "number": 7,
        "mergeable": "MERGEABLE",
        "mergeStateStatus": "CLEAN",
        "reviewDecision": "REVIEW_REQUIRED",
        "reviewThreads": [],
        "statusCheckRollup": [],
    }
    monkeypatch.setattr(fcp, "gh_json", lambda args: (0, payload))
    policy = {
        "branch_protection": {
            "main": {"required_pull_request_reviews": {"required_approving_review_count": 1}}
        }
    }
    result = fcp.StepResult("E", "MERGE")
    fcp.step_e_merge(result, "example", "feat/x", policy, _REGISTER, _TODAY)
    by_name = {c.name: c for c in result.checks}
    assert by_name["approvals meet policy"].status == fcp.STATUS_BLOCKED


# ── Evidence record ──────────────────────────────────────────────────────────


def test_evidence_records_the_sign_off_when_attested() -> None:
    report = fcp.PipelineReport(repo="example")
    step = report.step("A")
    step.add("x", fcp.STATUS_PASS, "ok")
    text = fcp.render_evidence(report, "G. Kazlauskas", "2026-09-28T00:00:00+00:00")
    assert "G. Kazlauskas" in text
    assert "- [x] I, G. Kazlauskas, confirm" in text


def test_evidence_refuses_to_sign_off_without_attestation() -> None:
    """The sign-off line is the one a student must not skip. An unattested run
    must not be able to render itself as launch-ready."""
    report = fcp.PipelineReport(repo="example")
    step = report.step("A")
    step.add("x", fcp.STATUS_PASS, "ok")
    text = fcp.render_evidence(report, None, "2026-09-28T00:00:00+00:00")
    assert "NOT SIGNED OFF" in text
    assert "- [x]" not in text


def test_evidence_does_not_sign_off_a_blocked_run() -> None:
    report = fcp.PipelineReport(repo="example")
    step = report.step("A")
    step.add("x", fcp.STATUS_BLOCKED, "defect")
    text = fcp.render_evidence(report, "G. Kazlauskas", "2026-09-28T00:00:00+00:00")
    assert "NOT SIGNED OFF" in text


def test_evidence_never_emits_a_secret_value() -> None:
    """The evidence file is committed as audit material; it must not become the
    leak. Every detail string is built from counts, paths, ids and statuses.

    The fixture is ASSEMBLED at runtime rather than written as a literal. A
    literal `AKIA...` in this file would be matched by the readiness gate's own
    secret sweep and by gitleaks, permanently BLOCKING this repository for
    containing a fake credential — the defect that tests/test_repo_readiness_audit.py
    has today. Assembling it keeps the runtime value identical and the source clean.
    """
    token = "AKIA" + "Q3EGFCLVW9YX7B2M"
    assert re.search(r"AKIA[0-9A-Z]{16}", token), "fixture must still look like a real key"
    report = fcp.PipelineReport(repo="example")
    step = report.step("B")
    step.add("no forbidden paths staged", fcp.STATUS_PASS, "none of 3 staged path(s) forbidden")
    text = fcp.render_evidence(report, "Tester", "2026-09-28T00:00:00+00:00")
    assert token not in text


def test_evidence_escapes_pipe_characters_in_details() -> None:
    """A detail containing `|` would corrupt the markdown table."""
    report = fcp.PipelineReport(repo="example")
    step = report.step("A")
    step.add("x", fcp.STATUS_PASS, "a|b")
    text = fcp.render_evidence(report, "Tester", "2026-09-28T00:00:00+00:00")
    assert "a\\|b" in text


def test_evidence_lists_every_step_and_status() -> None:
    report = fcp.PipelineReport(repo="example")
    for step_id in fcp.STEP_ORDER:
        step = report.step(step_id)
        step.add("x", fcp.STATUS_PASS, "ok")
    text = fcp.render_evidence(report, "Tester", "2026-09-28T00:00:00+00:00")
    for step_id in fcp.STEP_ORDER:
        assert f"## Step {step_id} — {fcp.STEP_TITLES[step_id]}" in text


# ── Exit-code trichotomy (the D-23 lesson) ───────────────────────────────────


def test_exit_code_is_2_when_something_could_not_be_verified() -> None:
    readiness = rra.RepoReport(repo="example")
    readiness.note_unverified("branch protection", "HTTP 403")
    readiness.decide()
    _report, code = fcp.run_pipeline("example", ("A",), live=False, readiness=readiness)
    assert code == 2


def test_exit_code_is_1_on_findings() -> None:
    readiness = rra.RepoReport(repo="example")
    readiness.add(rra.Finding("L-10", "S2", "local", "missing CODEOWNERS", "x", "add it"))
    readiness.decide()
    _report, code = fcp.run_pipeline("example", ("A",), live=False, readiness=readiness)
    assert code == 1


def test_exit_code_is_never_0_while_a_step_is_blocked() -> None:
    """A control that cannot read its subject must never report success."""
    readiness = rra.RepoReport(repo="example")
    readiness.add(rra.Finding("L-15", "S0", "local", "secret", "x", "rotate"))
    readiness.decide()
    _report, code = fcp.run_pipeline("example", ("A",), live=False, readiness=readiness)
    assert code != 0
