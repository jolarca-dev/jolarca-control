#!/usr/bin/env python3
"""check_declared_contexts.py -- every required status check in repos/*.yml must be producible.

GitHub names a required status check after a workflow job's `name:` when it has one, falling back to the
job key. A declaration that names something no job reports is therefore unsatisfiable, and under
`strict: true` it makes every future PR in that repository unmergeable. jolarca-control declared
[ci, security, lint] for jolarca-identity while that repo published `shellcheck` and
`gitleaks (full history)` -- three unproducible contexts, discovered only because someone ran the
readiness audit by hand (D-44).

A detection that only exists in a terminal is folklore, not a control (D-22): this script is the narrow,
deterministic slice of that audit that CI can run to a pass/fail verdict. The full audit stays a manual
operator tool, because 15 of 16 repos currently report BLOCKED for reasons unrelated to this class and a
permanently red scheduled job trains people to dismiss red.

Exit codes: 0 clean, 1 findings, 2 could-not-verify. 2 is never a pass (D-23).
"""

from __future__ import annotations

import base64
import datetime as dt
import json
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
REPOS_DIR = ROOT / "repos"
ORG = os.environ.get("FLEET_ORG", "jolarca-dev")


def gh_api(path: str) -> tuple[int, Any]:
    """GET via gh. Status 0 means the call could not be classified -> unverifiable, never agreement."""
    proc = subprocess.run(["gh", "api", path], capture_output=True, text=True)
    if proc.returncode == 127:
        return 0, "gh CLI not found"
    if proc.returncode == 0:
        try:
            return 200, json.loads(proc.stdout or "null")
        except json.JSONDecodeError as exc:
            return 0, f"unparseable JSON from {path}: {exc}"
    return 0, (proc.stderr or f"gh api {path} failed").strip()[:200]


def contexts_from_yaml(text: str) -> set[str]:
    """Context names a workflow can report: job `name:` if present, else the job key."""
    doc = yaml.safe_load(text)
    if not isinstance(doc, dict):
        raise ValueError("workflow is not a mapping")
    jobs = doc.get("jobs")
    if not isinstance(jobs, dict):
        raise ValueError("workflow has no jobs mapping")
    out: set[str] = set()
    for job_id, body in jobs.items():
        name = body.get("name") if isinstance(body, dict) else None
        out.add(name if isinstance(name, str) and name.strip() else str(job_id))
    return out


def probe_workflow_bodies(repo: str) -> tuple[list[str], list[str], bool]:
    """Workflow file contents for one repo. Returns (bodies, errors, is_empty).

    ``is_empty`` is the 404 whose message says the repository has no commits yet -- a declared state for
    the planned/in-development entries, not a verification gap. Any other failure stays an error.
    """
    status, listing = gh_api(f"repos/{ORG}/{repo}/contents/.github/workflows")
    if status != 200 or not isinstance(listing, list):
        message = str(listing)
        if "This repository is empty" in message:
            return [], [], True
        return [], [f"{repo}: cannot list .github/workflows ({message})"], False
    bodies: list[str] = []
    errors: list[str] = []
    for entry in listing:
        if not isinstance(entry, dict) or entry.get("type") != "file":
            continue
        path = str(entry.get("path", ""))
        if not path.endswith((".yml", ".yaml")):
            continue
        st, body = gh_api(f"repos/{ORG}/{repo}/contents/{path}")
        if st != 200 or not isinstance(body, dict):
            errors.append(f"{repo}/{path}: cannot read ({body})")
            continue
        try:
            bodies.append(base64.b64decode(str(body.get("content", ""))).decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            errors.append(f"{repo}/{path}: undecodable content ({exc})")
    return bodies, errors, False


def produced_contexts(
    repo: str, probe: Callable[[str], tuple[list[str], list[str], bool]] = probe_workflow_bodies
) -> tuple[set[str], list[str], bool]:
    bodies, errors, is_empty = probe(repo)
    out: set[str] = set()
    for text in bodies:
        try:
            out |= contexts_from_yaml(text)
        except (yaml.YAMLError, ValueError) as exc:
            errors.append(f"{repo}: unparseable workflow ({exc})")
    return out, errors, is_empty


def declared_contexts(defn: dict[str, Any]) -> list[str]:
    bp = (defn.get("branch_protection") or {}).get("main") or {}
    checks = bp.get("required_status_checks") or {}
    contexts = checks.get("contexts")
    return [str(c) for c in contexts] if isinstance(contexts, list) else []


def compare(repo: str, declared: list[str], produced: set[str]) -> list[dict[str, Any]]:
    """Declared names that no job in that repo can report."""
    unproducible = [c for c in declared if c not in produced]
    if not unproducible:
        return []
    return [
        {
            "repo": repo,
            "unproducible": unproducible,
            "produced": sorted(produced),
            "note": "unsatisfiable under strict:true -- every PR there would block forever",
        }
    ]


def apply_allowance(
    findings: list[dict[str, Any]], allowed: set[str], until: dt.date, today: dt.date
) -> tuple[list[dict[str, Any]], list[str]]:
    """Time-boxed exception, mirroring ALLOW_MISSING/ALLOW_MISSING_UNTIL in fleet-separation-guard.yml.

    An expired allowance fails again rather than being quietly renewed: an exception without an expiry is
    how a known gap becomes permanent.
    """
    kept: list[dict[str, Any]] = []
    notes: list[str] = []
    for finding in findings:
        repo = str(finding.get("repo"))
        if repo in allowed:
            if today <= until:
                notes.append(
                    f"ALLOWED (expires {until.isoformat()}): {repo} unproducible "
                    f"{finding.get('unproducible')}"
                )
                continue
            notes.append(f"EXPIRED allowance ({until.isoformat()}): {repo}")
        kept.append(finding)
    return kept, notes


def parse_allowance() -> tuple[set[str], dt.date]:
    allowed = {x for x in os.environ.get("ALLOW_MISSING_REPOS", "").split() if x}
    raw = os.environ.get("ALLOW_MISSING_UNTIL", "").strip()
    try:
        until = dt.date.fromisoformat(raw) if raw else dt.date.today()
    except ValueError:
        print(f"ERROR: {raw!r} is not an ISO date for ALLOW_MISSING_UNTIL", file=sys.stderr)
        until = dt.date(1970, 1, 1)  # already expired -> fails open toward red, never toward green
    return allowed, until


def exit_code(findings: list[dict[str, Any]], unverifiable: list[str]) -> int:
    if unverifiable:
        return 2
    return 1 if findings else 0


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    only = (
        args[args.index("--repo") + 1]
        if "--repo" in args and len(args) > args.index("--repo") + 1
        else None
    )

    if not REPOS_DIR.is_dir():
        print(f"ERROR: allow-list directory not found: {REPOS_DIR}", file=sys.stderr)
        return 2

    allowed, until = parse_allowance()
    today = dt.date.today()
    findings: list[dict[str, Any]] = []
    unverifiable: list[str] = []
    skipped: list[str] = []
    checked = 0

    for path in sorted(REPOS_DIR.glob("*.yml")):
        repo = path.stem
        if only and repo != only:
            continue
        defn = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        declared = declared_contexts(defn if isinstance(defn, dict) else {})
        if not declared:
            continue
        checked += 1
        produced, errors, is_empty = produced_contexts(repo)
        if is_empty:
            skipped.append(repo)
            continue
        unverifiable.extend(errors)
        if errors:
            continue  # never guess a finding from a repo we could not read
        findings.extend(compare(repo, declared, produced))

    kept, notes = apply_allowance(findings, allowed, until, today)
    print(
        json.dumps(
            {
                "organization": ORG,
                "repos_with_declared_contexts": checked,
                "findings": kept,
                "allowed_exceptions": notes,
                "unverifiable": unverifiable,
                "skipped_empty_repos": skipped,
                "generated_at": today.isoformat(),
            },
            indent=2,
        )
    )
    for note in notes:
        print(f"NOTE: {note}", file=sys.stderr)
    for finding in kept:
        print(
            f"ERROR: {finding['repo']} declares {finding['unproducible']} but reports "
            f"{finding['produced']}",
            file=sys.stderr,
        )
    for repo in skipped:
        print(
            f"SKIPPED (no commits yet): {repo} -- re-checked automatically once it has content",
            file=sys.stderr,
        )
    for item in unverifiable:
        print(f"UNVERIFIABLE: {item}", file=sys.stderr)
    if unverifiable:
        print(
            "ERROR: some repositories could not be read; that is not a pass (D-23).",
            file=sys.stderr,
        )

    code = exit_code(kept, unverifiable)
    if code == 0:
        print(
            f"OK: {checked} repositories declare required contexts and all are producible.",
            file=sys.stderr,
        )
    return code


if __name__ == "__main__":
    sys.exit(main())
