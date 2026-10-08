"""CI gates must be capable of failing, and must run the command they name.

Fleet sibling: jolarca-hermes-agents/tests/test_ci_gates_are_real.py. Same name, same purpose, one
deliberate difference recorded below.

ADR-0004 R3 says a control without a failing CI job is folklore. The mirror-image failure is a job that
always reports success: it manufactures assurance while checking nothing, and because `Policy Compliance
Check` and friends are *required status checks*, an auditor or a branch-protection rule reads the green
as proof.

Measured on control main `ab0d28f` (2026-10-05), this repo had the mirror-image defect at
`.github/workflows/compliance-scan.yml:85`:

    - run: .venv/bin/python -m pytest tests/ -q || python -m pytest tests/ -q

No workflow in this repository creates a virtualenv (checked: no `python -m venv`, `virtualenv` or `tox`
in any of the six), and `.gitignore` excludes `.venv/`, so the primary command cannot exist on a runner.
CI's log for run 37243451777 confirms it: `line 1: .venv/bin/python: No such file or directory`, then
`209 passed in 2.49s` from the fallback. The verdict has always belonged to the second command.

WHY THE `||` RULE HERE IS BROADER THAN THE HERMES COPY
---------------------------------------------------------------------------
The sibling module matches an OR-true pattern (`||` followed by the literal word true), which catches a swallowed status whose
replacement is `true`. That regex does NOT match control's defect, whose right-hand side is a second real
invocation -- exactly the variant that can turn a genuine red suite green while still printing plausible
test output. So this module forbids any `||` inside a gate step's run block. The cost is that a
legitimate shell conditional containing `||` in a run step also fails and must be argued for here; that
trade-off is intentional, because ambiguity inside a gate step is where this class of bug lives.

The `continue-on-error` clause currently has nothing to catch: measured zero occurrences across control's
workflows. It is a ratchet, not a bug report, and it says so rather than pretending to be load-bearing.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"

EXIT_STATUS_SWALLOW = re.compile(r"\|\|")
VENV_INTERPRETER = re.compile(r"(?:^|[\s;/])\.venv/bin/")
VENV_CREATION = re.compile(r"python3? -m venv|virtualenv\b|uv venv")


def _workflows() -> list[tuple[str, dict[str, Any]]]:
    return [
        (p.name, yaml.safe_load(p.read_text(encoding="utf-8")))
        for p in sorted(WORKFLOWS_DIR.glob("*.yml"))
    ]


def _run_steps() -> list[tuple[str, str, str, str]]:
    """(workflow, job, step label, script) for every `- run:` step in the repository."""
    found: list[tuple[str, str, str, str]] = []
    for workflow, doc in _workflows():
        for job_name, job in (doc.get("jobs") or {}).items():
            for index, step in enumerate((job or {}).get("steps") or []):
                script = step.get("run")
                if isinstance(script, str):
                    label = str(step.get("name") or f"step{index}")
                    found.append((workflow, job_name, label, script))
    return found


def test_no_run_step_swallows_its_exit_status() -> None:
    """No gate step may hand its verdict to a fallback command."""
    offenders = [
        f"{workflow}:{job}:{label} -> {script.strip()[:80]}"
        for workflow, job, label, script in _run_steps()
        if EXIT_STATUS_SWALLOW.search(script)
    ]
    assert not offenders, f"run step(s) neutered by an exit-status swallow: {offenders}"


def test_no_step_or_job_declares_continue_on_error() -> None:
    """continue-on-error is the YAML spelling of the same defect, at job level as well as step level."""
    offenders: list[str] = []
    for workflow, doc in _workflows():
        for job_name, job in (doc.get("jobs") or {}).items():
            if (job or {}).get("continue-on-error"):
                offenders.append(f"{workflow}:{job_name} (job)")
            for step in (job or {}).get("steps") or []:
                if step.get("continue-on-error"):
                    offenders.append(f"{workflow}:{job_name}:{step.get('name', '?')}")
    assert not offenders, f"continue-on-error declared at: {offenders}"


def test_no_step_runs_an_interpreter_the_workflow_never_installs() -> None:
    """A `.venv/bin/...` command is dead code unless a step in the same workflow builds that venv.

    This is the control-specific half: a swallowed status is visible in the shell, a nonexistent
    interpreter is visible only in a log line nobody reads.
    """
    steps = _run_steps()
    offenders = [
        f"{workflow}:{job}:{label} names .venv/bin but no step in {workflow} creates a venv"
        for workflow, job, label, script in steps
        if VENV_INTERPRETER.search(script)
        and not any(VENV_CREATION.search(other) for wf2, _j, _l, other in steps if wf2 == workflow)
    ]
    assert not offenders, "steps that cannot run their own command: " + str(offenders)


def test_regression_job_actually_runs_the_suite() -> None:
    """The `Regression Tests` job must invoke pytest; an empty or renamed step would green-light anything."""
    scripts = [script for _wf, _job, label, script in _run_steps() if "pytest" in script]
    assert scripts, "no run step invokes pytest anywhere: the suite is not wired into CI"
    labels = [label for _wf, _job, label, script in _run_steps() if "pytest" in script]
    assert any("egression" in label for label in labels), (
        f"pytest step is unnamed, so logs cannot attribute it: {labels}"
    )


def test_comments_point_at_files_that_exist() -> None:
    """A comment naming a test module that does not exist is a pointer the next reader follows nowhere.

    Not hypothetical: this repository's regression step carried
    `# Guarded by tests/test_ci_steps_are_real.py` for a module that had already been renamed to
    tests/test_ci_gates_are_real.py before the commit was made. Nothing failed, because nothing read the
    sentence. A comment that cites a path is a claim, and a claim about a path is cheap to verify.
    """
    refs: list[tuple[str, int, str]] = []
    for path in sorted(WORKFLOWS_DIR.glob("*.yml")):
        for number, line in enumerate(path.read_text(encoding="utf-8").split("\n"), 1):
            for m in re.finditer(r"(?:tests|scripts)/[A-Za-z0-9_./-]+\.(?:py|sh)", line):
                refs.append((path.name, number, m.group(0)))
    missing = [f"{wf}:{n} -> {ref}" for wf, n, ref in refs if not (REPO_ROOT / ref).exists()]
    assert not missing, "workflow comments cite paths that do not exist:\n  " + "\n  ".join(missing)
    assert refs, "no path references found in any workflow comment -- the rule is scanning nothing"


def test_workflows_are_parsed_and_non_vacuous() -> None:
    """If the loader saw nothing, every rule above would pass for free."""
    names = [workflow for workflow, _doc in _workflows()]
    assert "compliance-scan.yml" in names, names
    steps = _run_steps()
    assert len(steps) >= 15, (
        f"parsed only {len(steps)} run steps -- workflow format may have changed"
    )
    assert any("pytest" in script for _wf, _job, _label, script in steps), steps
