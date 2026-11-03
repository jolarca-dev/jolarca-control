#!/usr/bin/env python3
"""gate_parity.py — every gate has a negative control, and every control is executed.

jolarca-control — marketplace (jolarca-dev) governance control plane.
SOC 2 CC4.1 / CC7.1 · ISO/IEC 27001 A.8.8, A.8.32 · PCI-DSS 6.3.3

WHY THIS EXISTS (measured, 2026-10-26, main `4e2adc6`)
---------------------------------------------------------------------------
AGENTS.md §7 requires every gate to carry a negative control, and §3 requires the
three-valued exit code. Neither requirement was itself enforced by anything, so both
rot in the same way:

  * `scripts/check_secret_inventory.sh` landed on 2026-10-20 (PR #86) with NO fixture and NO
    invocation: `git grep -n check_secret_inventory origin/main -- Makefile '.github/workflows'`
    → exit 1, and `git grep -l` finds its name only in prose. Its own register
    (`docs/security/key-custody.md:41`) says an `unknown` expiry means "the gate is red
    by design", and `:33` says that table is "the single `expires`-bearing block the gate
    parses". A gate designed to be red, wired to nothing, reports green forever: the
    deliberate fail-closed signal was swallowed not by `||` but by absence.
  * The same script's default input path `docs/SECRETS_INVENTORY.md` has never existed
    (`git log --all --diff-filter=A -- docs/SECRETS_INVENTORY.md` → 0 lines), so run as
    documented it exits 2 — the dead-pointer class PR #79 exists to forbid.
  * `tests/test_check_workspace_execution_mode.sh` (13 cases, self-reported) is invoked by the
    Makefile only. `pytest tests/` auto-collects `.py` and NEVER `.sh`, so a shell fixture can
    exist, look maintained, and never run.

test_ci_gates_are_real.py covers swallowed exits, `continue-on-error` and phantom
interpreters. Nothing covered parity, so this closes that gap rather than duplicating it.

RULES
---------------------------------------------------------------------------
R1  fixture parity   each scripts/<name>.{py,sh} has tests/test_<name>.{py,sh}
R1b fixture substance
                     that fixture's body must name the gate it controls. A placeholder file
                     with the right name satisfies R1 and can never fail on anything.
R2  execution parity each tests/test_*.sh is invoked by a run step in a workflow that CAN
                     TRIGGER ON `pull_request`. `.py` needs nothing — `pytest tests/` collects
                     it — but nothing collects `.sh`, and a fixture that only `make test` runs
                     is invisible to the merge gate. That is not hypothetical: tests/
                     test_check_workspace_execution_mode.sh (13 cases) was Makefile-only until
                     this gate found it. A push-only or schedule-only workflow is scored as NOT
                     merge-protecting: it runs after the merge, which is the opposite of a gate.
R3  liveness         each scripts/* appears in a Makefile recipe or a workflow run STEP.
                     Parsing, not grepping: a YAML comment or a Python docstring that names a
                     script is documentation, not an invocation — the first draft matched raw
                     text and passed the very defect it was written to find (`
                     check_secret_inventory.sh`, unwired since 2026-10-20, D-80). A gate nobody
                     calls cannot change a verdict. Comment lines are stripped from run bodies
                     too, because a `#` inside a `run: |` block is still prose. Liveness is
                     judged on ALL workflows, not only PR-triggerable ones: a script wired only
                     into apply.yml guards a real apply, even though it cannot block a merge.
R4  baseline hygiene entries may only SHRINK. A listed item that no longer violates its
                     rule is a stale hiding place and fails, and the list length is
                     capped so a new offender cannot be smuggled in as an exception.
                     A baseline entry excuses R1 ONLY. The first draft `continue`d past the
                     rest of the loop, so naming an unwired script in the baseline silenced R3
                     as well — proven by fixture, see tests/test_check_gate_parity.py.

EXIT CODES (AGENTS.md §3 — never a silent pass)
   0  parity holds
   1  findings — a rule above is violated
   2  could not verify — an input directory or file is unreadable, or the tree is empty
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent

# Paths are derived from the `root` argument everywhere, deliberately: module-level copies of
# the same paths would be a second definition of the input, and a fixture pointing the gate at
# a throwaway tree would then silently scan the real repository (see check()'s docstring).

# Pre-existing gaps, recorded with the reason each is tolerated. This list may only
# shrink: R4 fails on a stale entry and on any growth past MAX_UNFIXTURED. Adding a name
# here is a decision a reviewer has to see in the diff, which is the point.
NO_FIXTURE_BASELINE: dict[str, str] = {
    "check_fleet_separation.sh": (
        "ADR-0004 guard; 15-line grep over repos/*.yml. It IS invoked by "
        "fleet-separation-guard.yml, so R3 passes — only the negative control is missing."
    ),
    "org_delivery_audit.sh": (
        "live read-only org audit; AGENTS.md §2 already states it runs in no workflow, "
        "so its fixture needs a network stub and is scheduled separately."
    ),
}
MAX_UNFIXTURED = len(NO_FIXTURE_BASELINE)

SCRIPT_SUFFIXES = (".py", ".sh")


def _strip_comment_lines(text: str) -> str:
    """Drop lines whose first non-blank token is `#`.

    Used for both corpora. In a Makefile and inside a shell `run: |` block a `#` line is
    documentation, not a command, and both corpora are searched by substring — so leaving
    comments in lets prose manufacture liveness.
    """
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))


def _read(path: Path) -> str | None:
    """Return text, or None when unreadable — the caller must turn that into exit 2."""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _makefile_text(path: Path) -> str | None:
    """Makefile bodies with comment lines removed.

    A `#` line in a Makefile is documentation, not a recipe: counting it as an invocation
    is the same error that raw-text matching produced for workflows.
    """
    text = _read(path)
    if text is None:
        return None
    return _strip_comment_lines(text)


def _workflow_facts(path: Path) -> tuple[str, bool, str | None]:
    """Return (comment-stripped `- run:` bodies, can-trigger-pull_request, error).

    Parsing rather than substring matching is the point. The first draft of this gate grepped
    raw workflow text, so a YAML COMMENT naming a script satisfied R3 — and the fixture written
    to prove R3 caught the dead gate passed it instead, because the fixture's own comment named
    the file. A meta-gate fooled by prose is worse than none: its green reads as systemic
    assurance. Same reasoning as the D-22 inline-regex gate and the D-80 dead pointer.

    `on:` is read under both spellings because YAML 1.1 resolves the bare key `on` to `True`
    (measured: `safe_load` hands back `{True: …}`), and a workflow that declares no trigger at
    all is an error, not a silent exclusion — GitHub would refuse to run it, so nothing here
    may credit it with protecting anything.
    """
    text = _read(path)
    if text is None:
        return "", False, f"cannot read {path}"
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        return "", False, f"cannot parse {path}: {str(exc)[:120]}"
    if not isinstance(doc, dict):
        return "", False, f"{path} did not parse to a mapping"
    triggers = doc.get("on", doc.get(True))
    if triggers is None:
        return "", False, f"{path} declares no `on:` trigger — cannot tell what runs it"
    if isinstance(triggers, (list, tuple)):
        names = {str(t) for t in triggers}
    elif isinstance(triggers, dict):
        names = {str(k) for k in triggers}
    else:
        return "", False, f"{path} has an `on:` block that is not a mapping or a list"
    jobs = doc.get("jobs")
    if not isinstance(jobs, dict) or not jobs:
        return "", False, f"{path} declares no jobs — nothing executable to read"
    bodies: list[str] = []
    for job in jobs.values():
        if not isinstance(job, dict):
            continue
        for step in job.get("steps") or []:
            if isinstance(step, dict) and isinstance(step.get("run"), str):
                bodies.append(step["run"])
    return _strip_comment_lines("\n".join(bodies)), "pull_request" in names, None


def _gate_scripts(scripts_dir: Path) -> list[str]:
    """The single definition of 'a gate script', shared by check() and the success message.

    Two definitions in one file is how a count stops describing the thing that was checked.
    """
    if not scripts_dir.is_dir():
        return []
    return sorted(
        p.name for p in scripts_dir.iterdir() if p.suffix in SCRIPT_SUFFIXES and p.is_file()
    )


def _corpora(root: Path) -> tuple[str, str, str, list[str]]:
    """Three corpora, kept apart on purpose: (Makefile, all run steps, PR-triggerable run steps).

    Makefile-only invocation is NOT CI invocation, and CI that cannot fire on a pull request is
    not merge protection — that is what the third corpus is for, and why collapsing them would
    let a fixture wired into a nightly-only workflow look covered while running after the merge.

    An unreadable or unparseable input is a gap, never a pass — and never a silent skip: an
    early `return` on one bad file once hid six filesystem checks and a whole secret sweep
    while the job reported green.
    """
    gaps: list[str] = []
    makefile_text = _makefile_text(root / "Makefile")
    if makefile_text is None:
        gaps.append("Makefile unreadable")
        makefile_text = ""
    wdir = root / ".github" / "workflows"
    all_bodies: list[str] = []
    pr_bodies: list[str] = []
    if not wdir.is_dir():
        gaps.append(f"workflow directory missing: {wdir}")
    else:
        ymls = sorted(wdir.glob("*.yml"))
        if not ymls:
            gaps.append(f"no workflows found under {wdir}")
        for y in ymls:
            body, pr_triggers, err = _workflow_facts(y)
            if err:
                gaps.append(err)
                continue
            all_bodies.append(body)
            if pr_triggers:
                pr_bodies.append(body)
    return makefile_text, "\n".join(all_bodies), "\n".join(pr_bodies), gaps


def check(root: Path = ROOT) -> tuple[list[dict[str, str]], list[str]]:
    """Pure over `root` so a fixture can point the whole gate at a throwaway tree —
    a default evaluated at import time would keep scanning the real repository and make
    every tmp_path test meaningless (same reason check_findings_register takes ROOT)."""
    findings: list[dict[str, str]] = []
    gaps: list[str] = []

    scripts_dir, tests_dir = root / "scripts", root / "tests"
    if not scripts_dir.is_dir() or not tests_dir.is_dir():
        return [], [f"cannot enumerate gates: missing {scripts_dir} or {tests_dir}"]

    scripts = _gate_scripts(scripts_dir)
    test_files = sorted(
        p.name
        for p in tests_dir.iterdir()
        if p.name.startswith("test_") and p.suffix in SCRIPT_SUFFIXES and p.is_file()
    )
    if not scripts:
        return [], [f"non-vacuity: no scripts found under {scripts_dir}"]

    makefile_text, workflow_text, pr_workflow_text, io_gaps = _corpora(root)
    gaps.extend(io_gaps)
    invoked = f"{makefile_text}\n{workflow_text}"

    # Keyed by the SUBJECT each fixture is named after (`test_<subject>` -> `<subject>`), so
    # every rule below compares stems to stems. Deriving the set of prefixed names instead is
    # what made the first draft's R4a unable to fire.
    fixture_by_subject: dict[str, str] = {}
    for t in test_files:
        fixture_by_subject.setdefault(re.sub(r"^test_|\.(py|sh)$", "", t), t)

    for name in scripts:
        stem = re.sub(r"\.(py|sh)$", "", name)
        # R1 — fixture parity. A NO_FIXTURE_BASELINE entry excuses the missing fixture and
        # NOTHING ELSE. The first draft `continue`d here, so naming an unwired script in the
        # baseline silenced R3 too and the gate reported parity on a gate that runs nowhere
        # (measured before the fix: findings == [] for a baselined, unwired script). R3 below
        # is therefore unconditional — an exception has to be narrow to be an exception.
        if stem not in fixture_by_subject:
            if name not in NO_FIXTURE_BASELINE:
                findings.append(
                    {
                        "rule": "R1",
                        "where": f"scripts/{name}",
                        "what": f"no tests/test_{stem}.py or tests/test_{stem}.sh exists",
                        "fix": f"add a negative-control fixture that must FAIL on the defect {name} detects "
                        "(AGENTS.md §7); or justify it in NO_FIXTURE_BASELINE and lower MAX_UNFIXTURED "
                        "so the exception is visible in the diff",
                    }
                )
        else:
            # R1b — the fixture must at least name the gate it claims to control. A stub with
            # the right filename satisfies R1, runs green and can never fail on anything; that
            # is the difference between a fixture and a control (§7: verify the verifier).
            fixture = fixture_by_subject[stem]
            body = _read(tests_dir / fixture)
            if body is None:
                gaps.append(f"cannot read tests/{fixture}")
            elif stem not in body:
                findings.append(
                    {
                        "rule": "R1b",
                        "where": f"tests/{fixture}",
                        "what": f"fixture exists for scripts/{name} but its body never mentions "
                        f"`{stem}`: a placeholder, not a negative control",
                        "fix": f"make the fixture invoke scripts/{name} and assert the exit code it "
                        "must produce on the defect (0 / 1 / 2 are different verdicts; test all three)",
                    }
                )
        # R3 — liveness, judged only on executable surfaces (Makefile recipes + run steps).
        # Matched as `scripts/<name>`, not as a bare filename: the first draft used the bare
        # name, so `bash tests/test_thing_guard.sh` satisfied liveness for scripts/thing_guard.sh
        # — a fixture naming its subject proved the subject runs. Paths are how real commands
        # reference files, and this repo's workflows always spell them out.
        if f"scripts/{name}" not in invoked and f"scripts/{stem}" not in invoked:
            findings.append(
                {
                    "rule": "R3",
                    "where": f"scripts/{name}",
                    "what": "named by nothing executable: no Makefile recipe and no workflow "
                    f"run step invokes `scripts/{name}`",
                    "fix": "wire it into a job (required only once it can pass) or delete it; "
                    "an unrunnable gate manufactures assurance",
                }
            )

    # R2 — every shell fixture must run in CI that can block a merge. pytest never collects .sh.
    for t in test_files:
        if not t.endswith(".sh"):
            continue
        if f"tests/{t}" in pr_workflow_text:
            continue
        in_any_workflow = f"tests/{t}" in workflow_text
        local_only = f"tests/{t}" in makefile_text
        findings.append(
            {
                "rule": "R2",
                "where": f"tests/{t}",
                "what": (
                    "shell fixture is invoked only by workflows that cannot trigger on "
                    "pull_request — it runs after the merge, so it reports instead of preventing"
                    if in_any_workflow
                    else "shell fixture runs only via `make test` — no workflow step invokes it, so it "
                    "cannot protect a merge"
                    if local_only
                    else "shell fixture is invoked by nothing at all: neither a workflow step nor the "
                    "Makefile (pytest auto-collects .py and never .sh)"
                ),
                "fix": f"add `- name: {t.replace('.sh', '').replace('test_', '')} fixtures` / "
                f"`run: bash tests/{t}` to the Regression Tests job and the Makefile test target",
            }
        )

    # R4a — baseline entries that no longer describe a gap must be removed, so the list
    # cannot calcify into a permanent hiding place.
    for name in NO_FIXTURE_BASELINE:
        stem = re.sub(r"\.(py|sh)$", "", name)
        # The comparison is stem-to-stem through fixture_by_subject, which is keyed by subject.
        # Written against prefixed fixture names, R4a never fired: a resolved exception would
        # stay in the baseline forever, silently — the bug the stale-baseline case tests.
        if stem in fixture_by_subject:
            findings.append(
                {
                    "rule": "R4",
                    "where": f"NO_FIXTURE_BASELINE[{name!r}]",
                    "what": "stale baseline entry: a fixture now exists, so the exception is "
                    "hiding nothing",
                    "fix": f"delete {name} from NO_FIXTURE_BASELINE and lower MAX_UNFIXTURED",
                }
            )
    # R4b — the ratchet: the tolerated set may only shrink.
    if len(NO_FIXTURE_BASELINE) > MAX_UNFIXTURED:
        findings.append(
            {
                "rule": "R4",
                "where": "NO_FIXTURE_BASELINE",
                "what": f"baseline holds {len(NO_FIXTURE_BASELINE)} entries, ceiling is {MAX_UNFIXTURED}",
                "fix": "write the missing fixture; the ceiling is lowered deliberately, never raised",
            }
        )
    return findings, gaps


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    root = Path(args[0]) if args else ROOT
    findings, gaps = check(root)

    for f in findings:
        print(f"{f['rule']}  {f['where']}")
        print(f"      what: {f['what']}")
        print(f"      fix:  {f['fix']}")

    if gaps:
        print(
            f"\nRESULT: {len(findings)} parity finding(s) and {len(gaps)} unreadable input(s) "
            "across the gate tree",
            file=sys.stderr,
        )
        for g in gaps:
            print(f"  CANNOT-VERIFY: {g}", file=sys.stderr)
        # Findings outrank a gap in severity only in the sense that both are non-zero;
        # an unreadable input can never reduce the verdict to a pass (§3, D-23).
        return 1 if findings else 2

    if findings:
        rules: dict[str, int] = {}
        for f in findings:
            rules[f["rule"]] = rules.get(f["rule"], 0) + 1
        breakdown = ", ".join(f"{k}={v}" for k, v in sorted(rules.items()))
        print(f"\nRESULT: {sum(rules.values())} parity finding(s): {breakdown}")
        return 1

    scripts = _gate_scripts(root / "scripts")
    print(
        f"OK: {len(scripts)} gate scripts each have a fixture or a dated baseline entry; "
        "every shell fixture runs in a PR-triggerable workflow; no gate is unreferenced"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
