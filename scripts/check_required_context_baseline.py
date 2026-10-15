#!/usr/bin/env python3
"""check_required_context_baseline.py — the policy baseline for THIS repo's
required status checks has to agree with the declaration and with what CI can
actually report.

Why this exists (D-62, found 2026-10-15)
---------------------------------------------------------------------------
`policy/repo-defaults.yml` `required_checks.control_plane` is the document an
auditor reads to learn what gates `jolarca-control`. It listed
`Fleet Separation Guard`, which is not a job name anywhere in this repository
(the job is `Fleet Separation (ADR-0004)` and its workflow is path-filtered to
`repos/**` plus a weekly schedule), and it omitted `SAST (semgrep)`, which has
been a required context since A-08 on 2026-10-08. Nothing checked either fact,
so the baseline drifted twice in ten days while reading as authoritative.

That is the same defect class as D-44/D-47 (a required context no workflow can
report makes every PR unmergeable under `strict: true`) and the same
overstatement/understatement pair that `jolarca-security` records as F-08/F-09.
`scripts/check_declared_contexts.py` compares each *fleet repo's* declaration
against that repo's workflows; it never looked at this baseline, so the policy
file could rot in silence.

What is checked
---------------
1. the baseline is non-empty;
2. baseline set == `repos/jolarca-control.yml`
   `branch_protection.main.required_status_checks.contexts` (the declaration
   Terraform would apply);
3. every name is producible on a pull request: it is a job `name:` (or job key)
   in a workflow that triggers on `pull_request` with no path filter. Requiring
   an unproducible name is how `jolarca-identity` deadlocked (D-44).

Exit codes (AGENTS.md §3, three-valued — cannot-verify is never a pass)
----------------------------------------------------------------------
0  all three agree
1  findings: mismatch, empty baseline, or an unproducible name
2  could not verify: a required input is missing or unparseable
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
POLICY_PATH = REPO_ROOT / "policy" / "repo-defaults.yml"
REPO_PATH = REPO_ROOT / "repos" / "jolarca-control.yml"
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"


class CannotVerify(Exception):
    """Raised when an input is absent or unreadable — never reported as clean."""


_ABSENT = object()  # distinguishes "key missing" from "key present, value null"


def _rel(path: Path) -> str:
    """Repo-relative for readability, absolute when it is outside the repo.

    `Path.relative_to` raises ValueError for anything off the repo root, and this
    runs *inside* the error path: the first draft crashed with ValueError exactly
    where it was supposed to report "cannot verify" and exit 2. A reporter that
    throws is worse than no reporter, because the exit code is the contract
    (AGENTS.md §3).
    """
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _load_yaml(path: Path) -> Any:
    if not path.is_file():
        raise CannotVerify(f"missing file: {_rel(path)}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:  # a parse failure is not an empty result
        raise CannotVerify(f"{_rel(path)}: {exc}") from exc
    if not isinstance(data, dict):
        raise CannotVerify(f"{_rel(path)} did not parse to a mapping")
    return data


def baseline_contexts() -> list[str]:
    policy = _load_yaml(POLICY_PATH)
    block = policy.get("required_checks")
    if not isinstance(block, dict) or not isinstance(block.get("control_plane"), list):
        raise CannotVerify("policy/repo-defaults.yml has no required_checks.control_plane list")
    out: list[str] = []
    for entry in block["control_plane"]:
        if isinstance(entry, dict) and isinstance(entry.get("context"), str):
            out.append(entry["context"])
        else:
            raise CannotVerify(
                f"control_plane entry is not a mapping with a context key: {entry!r}"
            )
    return out


def declared_contexts() -> list[str]:
    repo = _load_yaml(REPO_PATH)
    try:
        contexts = repo["branch_protection"]["main"]["required_status_checks"]["contexts"]
    except (KeyError, TypeError) as exc:
        raise CannotVerify(
            "repos/jolarca-control.yml has no branch_protection.main.required_status_checks.contexts"
        ) from exc
    if not isinstance(contexts, list):
        raise CannotVerify("declared contexts must be a list")
    return [str(c) for c in contexts]


def pr_producible_names() -> tuple[set[str], list[str]]:
    """(names a pull_request can report, workflow files inspected)."""
    if not WORKFLOW_DIR.is_dir():
        raise CannotVerify(f"no workflows directory at {_rel(WORKFLOW_DIR)}")
    files = sorted(WORKFLOW_DIR.glob("*.yml"))
    if not files:
        raise CannotVerify("workflows directory contains no .yml files")
    producible: set[str] = set()
    for path in files:
        doc = _load_yaml(path)
        triggers = doc.get("on") or doc.get(True)  # YAML 1.1 reads bare `on:` as True
        if not isinstance(triggers, dict):
            if isinstance(triggers, (str, list)) or triggers is True:
                continue  # scalar/None triggers: nothing pull_request-shaped to learn
            continue
        pr = triggers.get("pull_request") if "pull_request" in triggers else _ABSENT
        if pr is _ABSENT:
            continue  # no pull_request trigger at all
        # `pull_request:` written with no value parses to None, and that means
        # "trigger with no options" — the common shape in this repo. Treating it
        # as absent made every real context look unproducible, which is how a
        # gate invents four findings out of thin air.
        if isinstance(pr, dict) and (pr.get("paths") or pr.get("paths-ignore")):
            continue  # path-filtered: cannot report on every PR, so cannot be required
        jobs = doc.get("jobs")
        if not isinstance(jobs, dict):
            continue
        for key, job in jobs.items():
            name = job.get("name") if isinstance(job, dict) else None
            producible.add(str(name) if name else str(key))
    return producible, [p.name for p in files]


def check() -> tuple[list[str], list[str]]:
    """(findings, unverifiable-messages) — never both, findings win."""
    problems: list[str] = []
    base = baseline_contexts()
    declared = declared_contexts()
    producible, _ = pr_producible_names()

    if not base:
        problems.append(
            "required_checks.control_plane is empty: a baseline that requires nothing enforces nothing"
        )
    if not declared:
        problems.append(
            "repos/jolarca-control.yml declares no required contexts (minimum_contexts: 1 in policy)"
        )

    missing = sorted(set(declared) - set(base))
    extra = sorted(set(base) - set(declared))
    if missing:
        problems.append(f"baseline omits required contexts the repository declares: {missing}")
    if extra:
        problems.append(f"baseline lists contexts the repository does not declare: {extra}")

    unproducible = sorted(set(base) | set(declared))
    unproducible = [c for c in unproducible if c not in producible]
    if unproducible:
        problems.append(
            "contexts no pull_request event can report (job name mismatch or a "
            f"path-filtered workflow): {unproducible}"
        )
    return problems, []


def main() -> int:
    try:
        problems, _ = check()
    except CannotVerify as exc:
        print(json.dumps({"status": "unverifiable", "reason": str(exc)}, indent=2))
        print(
            "CANNOT VERIFY: the required-context baseline could not be evaluated.", file=sys.stderr
        )
        print("  This is exit 2, not a pass (AGENTS.md §3).", file=sys.stderr)
        return 2

    report = {
        "status": "fail" if problems else "pass",
        "baseline": baseline_contexts(),
        "declared": declared_contexts(),
        "findings": problems,
    }
    print(json.dumps(report, indent=2))
    for problem in problems:
        print(f"::error::{problem}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
