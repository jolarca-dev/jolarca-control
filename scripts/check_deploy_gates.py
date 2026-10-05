#!/usr/bin/env python3
"""check_deploy_gates.py -- every job that names an `environment:` must face a human who cannot skip it.

GitHub creates a deployment environment *empty* the first time a workflow references it. An `environment:`
block is therefore a claim, not a control: what matters is whether that environment has a protection rule,
and whether administrators can bypass it. Measured 2026-10-05 across the organisation, all five existing
environments report `can_admins_bypass: true` and four of five have `protection_rules: []`. In this
repository `.github/workflows/apply.yml` opens with "Single-stage production apply with a manual approval
gate" and points at `production`, which has no rules at all -- so the only thing between a merge touching
`repos/**` and `terraform apply -auto-approve` against the whole org is one unset repository variable.
D-22 again: a control that no pipeline verifies is folklore.

Exit codes follow the fleet's three-valued contract: 0 clean, 1 findings, 2 could-not-verify. 2 is never
a pass (D-23) -- a missing token or an unreadable environment is reported as unverified, never as green.

Known limit, stated rather than hidden: the clean-path `required_reviewers` object shape in the tests is
inferred from the documented Create-or-update-an-environment body, because no environment in this
organisation currently has reviewers, so the green path has never been observed here. The red path is
observed, and verdicts use only fields the live API returns (`protection_rules`, `can_admins_bypass`).

Scope defaults to this repository. `DEPLOY_GATE_REPOS="owner/repo …"` widens it by reading other repos'
workflows over the API, as context-parity does. Widening is deliberately not wired into CI yet: three of
those environments belong to the mission-side workstream, and a control-plane job kept red by another
workstream's settings trains dismissal.
"""

from __future__ import annotations

import base64
import datetime as dt
import json
import os
import re
import subprocess
import sys
import urllib.parse
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
TARGET = re.compile(r"[\w.-]+/[\w.-]+:[\w][\w.-]*")
ORG = os.environ.get("FLEET_ORG", "jolarca-dev")


def repo_slug() -> str:
    """This repo's slug: Actions' own value first, then the checkout directory name locally."""
    from_env = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if from_env:
        return from_env
    return f"{ORG}/{ROOT.name}"


def gh_api(path: str) -> tuple[int, Any]:
    """GET via gh, keeping 404 distinct from every other failure.

    A 404 on an environment is a real answer (never created yet; GitHub will create it empty). Anything
    else -- 403, transport error, unparseable JSON -- is not an answer, so the caller must treat it as
    unverifiable. Collapsing the two is how a missing control comes to read as a passing one.
    """
    proc = subprocess.run(["gh", "api", path], capture_output=True, text=True)
    if proc.returncode == 0:
        try:
            return 200, json.loads(proc.stdout or "null")
        except json.JSONDecodeError as exc:
            return 0, f"unparseable JSON from {path}: {exc}"
    blob = (proc.stderr or "").strip()
    if "HTTP 404" in blob:
        return 404, blob[:200]
    return 0, blob[:200] or f"gh api {path} failed"


def _envs_in_workflow(name: str, text: str) -> list[tuple[str, str, Any]]:
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        return [(name, "<unparseable>", f"cannot parse ({exc})")]
    jobs = (doc or {}).get("jobs") if isinstance(doc, dict) else None
    if not isinstance(jobs, dict):
        return []
    return [
        (name, str(job_id), body.get("environment"))
        for job_id, body in jobs.items()
        if isinstance(body, dict) and "environment" in body
    ]


def local_environment_refs(workflows: Path) -> list[tuple[str, str, Any]]:
    """(workflow file, job key, `environment:` value) for every job in a directory that names one."""
    refs: list[tuple[str, str, Any]] = []
    for path in sorted(workflows.glob("*.yml")):
        refs.extend(_envs_in_workflow(path.name, path.read_text(encoding="utf-8")))
    return refs


def resolve_environment(value: Any) -> tuple[list[str], list[str], str | None]:
    """(findings, unverifiable, name) for a job's `environment:` value.

    Either a bare name or a mapping with `name:`; a `${{ … }}` expression cannot be resolved from YAML,
    which is a verification gap and never a pass.
    """
    if isinstance(value, dict):
        name = value.get("name")
        if isinstance(name, str) and name.strip():
            return resolve_environment(name)
        return [], [f"environment mapping with no resolvable name: {value!r}"], None
    if not isinstance(value, str) or not value.strip():
        return [], [f"environment value is not a name: {value!r}"], None
    text = value.strip()
    if "${{" in text:
        return [], [f"dynamic environment name cannot be resolved statically: {text}"], None
    return [], [], text


def assess(target: str, body: dict[str, Any]) -> list[str]:
    """Findings for one environment document returned by the API."""
    findings: list[str] = []
    rules = body.get("protection_rules")
    if not isinstance(rules, list) or not rules:
        findings.append(f"{target}: no protection rule of any kind (protection_rules is empty)")
    else:
        kinds = sorted({str(r.get("type")) for r in rules if isinstance(r, dict)})
        if "required_reviewers" not in kinds:
            findings.append(
                f"{target}: rules are {kinds}, with no required_reviewers, so no human approves the deploy"
            )
    if body.get("can_admins_bypass") is not False:
        findings.append(
            f"{target}: can_admins_bypass={body.get('can_admins_bypass')!r} -- the gate is skippable by "
            "the same role that merges the change"
        )
    return findings


def classify_missing(target: str, status: int) -> tuple[list[str], list[str]]:
    """404 means the environment does not exist yet; GitHub creates it empty on first run."""
    if status == 404:
        return [
            (
                f"{target}: not created yet (HTTP 404) -- GitHub will create it with no protection rules "
                "the first time the job runs"
            )
        ], []
    return [], [f"{target}: could not read the environment (status {status})"]


def _date_or_expired(raw: str) -> dt.date:
    try:
        return dt.date.fromisoformat(raw) if raw else dt.date(1970, 1, 1)
    except ValueError:
        return dt.date(1970, 1, 1)  # fails toward red, never toward green


def allowance_error(env: Mapping[str, str]) -> str | None:
    """An exemption without an expiry is how a known gap becomes permanent."""
    entries = [x for x in env.get("ALLOW_UNPROTECTED_ENVS", "").split() if x]
    if not entries:
        return None
    raw = env.get("ALLOW_UNPROTECTED_UNTIL", "").strip()
    if not raw:
        return "ERROR: ALLOW_UNPROTECTED_ENVS is set without ALLOW_UNPROTECTED_UNTIL"
    try:
        dt.date.fromisoformat(raw)
    except ValueError:
        return f"ERROR: {raw!r} is not an ISO date for ALLOW_UNPROTECTED_UNTIL"
    return None


def parse_allowance() -> dict[str, dt.date]:
    entries = [x for x in os.environ.get("ALLOW_UNPROTECTED_ENVS", "").split() if x]
    raw = os.environ.get("ALLOW_UNPROTECTED_UNTIL", "").strip()
    return {e: _date_or_expired(raw) for e in entries}


def apply_allowance(
    findings: list[str], allowed: dict[str, dt.date], today: dt.date | None = None
) -> tuple[list[str], list[str]]:
    """Keep findings nobody exempted; report exempted ones as dated notes. Expiry restores the failure."""
    today = today or dt.date.today()
    kept: list[str] = []
    notes: list[str] = []
    for finding in findings:
        target = next((key for key in allowed if finding.startswith(f"{key}:")), None)
        if target is None:
            kept.append(finding)
            continue
        until = allowed[target]
        if today <= until:
            notes.append(f"ALLOWED (expires {until.isoformat()}): {target}")
        else:
            notes.append(f"EXPIRED allowance ({until.isoformat()}): {target}")
            kept.append(finding)
    return kept, notes


def target_of(message: str) -> str:
    """The `owner/repo:environment` a finding or note is about.

    Findings are `o/r:env: text`; exemption notes are `ALLOWED (expires D): o/r:env`. Splitting on the
    first colon would key the note on the word ALLOWED and its date, which is how two exemptions for one
    environment were reported earlier today, so the owner/repo:env token is matched instead.
    """
    found = TARGET.search(message)
    return found.group(0) if found else message


def exit_code(findings: list[str], unverifiable: list[str]) -> int:
    if unverifiable:
        return 2
    return 1 if findings else 0


def summary(gated: int, findings: int, allowed: int, unverifiable: int) -> str:
    """Counts derived from this run, one per environment -- never per finding.

    An 'all clear' that examined nothing, or that ignored an exemption, is an overclaim; the sibling check
    printed exactly that bug before CI caught it. These arguments used to be finding-shaped, so one
    environment failing two rules was announced as two exempted environments. Rather than clamp the
    nonsense quietly, an inconsistent request now raises: a summary that cannot add up is a bug in the
    summary, and silence is how it would survive.
    """
    if findings + allowed > gated:
        raise ValueError(
            f"summary would over-report: {findings} finding(s) + {allowed} allowed > {gated} examined"
        )
    clean = gated - findings - allowed
    parts = [f"{gated} environment(s) examined", f"{clean} gated"]
    if findings:
        parts.append(f"{findings} finding(s)")
    if allowed:
        parts.append(f"{allowed} allowed until their expiry")
    if unverifiable:
        parts.append(f"{unverifiable} unverifiable")
    prefix = "NOT VERIFIED:" if unverifiable else ("FAIL:" if findings else "OK:")
    return f"{prefix} " + "; ".join(parts) + "."


def remote_environment_refs(slug: str) -> tuple[list[tuple[str, str, Any]], list[str]]:
    """Workflow `environment:` refs for another repository, read over the API."""
    status, listing = gh_api(f"repos/{slug}/contents/.github/workflows")
    if status != 200 or not isinstance(listing, list):
        return [], [f"{slug}: cannot list .github/workflows ({listing})"]
    refs: list[tuple[str, str, Any]] = []
    problems: list[str] = []
    for entry in listing:
        path = str(entry.get("path", "")) if isinstance(entry, dict) else ""
        if (
            not isinstance(entry, dict)
            or entry.get("type") != "file"
            or not path.endswith((".yml", ".yaml"))
        ):
            continue
        st, body = gh_api(f"repos/{slug}/contents/{path}")
        if st != 200 or not isinstance(body, dict):
            problems.append(f"{slug}/{path}: cannot read ({body})")
            continue
        try:
            text = base64.b64decode(str(body.get("content", ""))).decode("utf-8")
        except (ValueError, UnicodeDecodeError) as exc:
            problems.append(f"{slug}/{path}: undecodable content ({exc})")
            continue
        refs.extend(_envs_in_workflow(str(entry.get("name", path)), text))
    return refs, problems


def main(argv: list[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    as_json = "--json" in args

    if not (os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")):
        print(
            "ERROR: no GITHUB_TOKEN or GH_TOKEN in the environment; deployment gates are unverified, "
            "and unverified is not a pass",
            file=sys.stderr,
        )
        return 2

    err = allowance_error(os.environ)
    if err:
        print(err, file=sys.stderr)
        return 1

    allowed = parse_allowance()
    targets: list[tuple[str, Any]] = [
        (repo_slug(), ref) for ref in local_environment_refs(ROOT / ".github" / "workflows")
    ]
    unverifiable: list[str] = []
    for slug in os.environ.get("DEPLOY_GATE_REPOS", "").split():
        if not slug:
            continue
        refs, problems = remote_environment_refs(slug)
        unverifiable.extend(problems)
        targets.extend((slug, ref) for ref in refs)

    findings: list[str] = []
    checked: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for slug, (_workflow, _job, value) in targets:
        resolved_findings, resolved_gaps, name = resolve_environment(value)
        findings.extend(resolved_findings)
        unverifiable.extend(resolved_gaps)
        if name is None:
            continue
        key = (slug, name)
        if key in seen:
            continue
        seen.add(key)
        checked.append(key)
        target = f"{slug}:{name}"
        status, body = gh_api(f"repos/{slug}/environments/{urllib.parse.quote(name, safe='')}")
        if status == 200 and isinstance(body, dict):
            findings.extend(assess(target, body))
        else:
            more_findings, more_gaps = classify_missing(target, status)
            findings.extend(more_findings)
            unverifiable.extend(more_gaps)

    kept, notes = apply_allowance(findings, allowed)
    # Per environment, not per finding: one environment can fail both rules at once.
    failing = {target_of(f) for f in kept}
    exempt = {target_of(n) for n in notes if n.startswith("ALLOWED")} - failing
    line = summary(len(checked), len(failing), len(exempt), len(unverifiable))
    for finding in kept:
        print(f"ERROR: {finding}", file=sys.stderr)
    for note in notes:
        print(f"NOTE: {note}", file=sys.stderr)
    for gap in unverifiable:
        print(f"UNVERIFIABLE: {gap}", file=sys.stderr)
    if as_json:
        print(
            json.dumps(
                {
                    "checked": [f"{s}:{n}" for s, n in checked],
                    "findings": kept,
                    "notes": notes,
                    "unverifiable": unverifiable,
                    "summary": line,
                },
                indent=2,
            )
        )
    print(line, file=sys.stderr)
    return exit_code(kept, unverifiable)


if __name__ == "__main__":
    raise SystemExit(main())
