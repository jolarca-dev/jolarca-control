#!/usr/bin/env python3
"""Detect drift between jolarca-control definitions and live GitHub state.

Compares the repos/*.yml allow-list and the organization_baseline in
policy/repo-defaults.yml against the live jolarca-dev organization:

  1. fleet membership    — declared but absent / present but undeclared
                           (ADR-0004 R2: out-of-band creation is an incident)
  2. visibility          — declared vs live (this is how D-01 was found)
  3. wiki / archived     — policy forbids both by default
  4. branch protection   — protection MISSING entirely, or weakened below the
                           baseline (D-08: five of six rules were unmanaged)
  5. unexpected admins   — anyone holding admin who is not in allowed_admins
  6. organization settings — 2FA, member repo creation, default permission
                           (provider cannot manage these; D-18 / D-19)

Exit codes are deliberately three-valued, because "could not check" must never
be reported as "no drift":

  0  no drift detected
  1  drift detected
  2  live state could not be verified (auth failure, missing gh, API error)

The previous version returned 0 when the API call failed, so an expired
TF_GITHUB_TOKEN_READONLY made this control pass silently while checking
nothing (D-23). Pass --allow-unverifiable to downgrade per-repo scope errors
(403) to warnings; total failures still exit 2.

Structured JSON goes to stdout; the human summary to stderr, so the JSON stays
pipeable. --issue-body writes a Markdown report for the alerting workflow.

Auth: GITHUB_TOKEN or GH_TOKEN. Read-only — this script never writes to GitHub.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

BASE_DIR = Path(__file__).resolve().parent.parent
REPOS_DIR = BASE_DIR / "repos"
POLICY_FILE = BASE_DIR / "policy" / "repo-defaults.yml"

# This control plane governs jolarca-dev ONLY (ADR-0004). Override is provided
# for test runs against a scratch org, never for pointing at journeyoflife-org.
ORG = os.environ.get("JOLARCA_CONTROL_ORG", "jolarca-dev")

# The org community-health repo is declared in health-repo.tf, not in the
# allow-list, so it is excluded from fleet-membership comparison. It still gets
# a branch-protection check because it is a real repo with a real main branch.
HEALTH_REPO = ".github"

# gh writes "gh: Not Found (HTTP 404)" to stderr on API errors.
_HTTP_RE = re.compile(r"HTTP\s+(\d{3})")

# Org settings the provider cannot manage, compared against organization_baseline.
ORG_SETTINGS = (
    "two_factor_requirement_enabled",
    "members_can_create_repositories",
    "members_can_create_public_repositories",
    "members_can_create_private_repositories",
    "members_can_fork_private_repositories",
    "default_repository_permission",
    "web_commit_signoff_required",
)


class Unverifiable(Exception):
    """Raised when live state cannot be read at all."""


def _env() -> dict[str, str]:
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""
    env = dict(os.environ)
    if token:
        env["GITHUB_TOKEN"] = token
    return env


def gh_api(path: str) -> tuple[int, Any]:
    """Call the REST API via gh. Returns (http_status, parsed_body).

    status 0 means the call could not be classified (gh missing, transport
    error, unparseable body) — callers must treat that as unverifiable.
    """
    try:
        proc = subprocess.run(
            ["gh", "api", path],
            capture_output=True,
            text=True,
            env=_env(),
            check=False,
        )
    except FileNotFoundError:
        return 0, {"error": "gh CLI not found"}

    if proc.returncode == 0:
        try:
            return 200, json.loads(proc.stdout or "null")
        except json.JSONDecodeError as exc:
            return 0, {"error": f"unparseable JSON: {exc}"}

    match = _HTTP_RE.search(proc.stderr)
    status = int(match.group(1)) if match else 0
    return status, {"error": proc.stderr.strip()[:400]}


def must_get(path: str) -> Any:
    """gh_api, but any non-200 is fatal (exit 2)."""
    status, body = gh_api(path)
    if status != 200:
        raise Unverifiable(f"GET {path} -> HTTP {status}: {body.get('error', '')}")
    return body


def try_get(path: str) -> tuple[int, Any]:
    """gh_api for optional resources; caller decides what each status means."""
    return gh_api(path)


def load_yaml(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    return data if isinstance(data, dict) else {}


def get_defined_repos() -> dict[str, dict[str, Any]]:
    """Load declared repos from the YAML allow-list."""
    defined: dict[str, dict[str, Any]] = {}
    for yml_file in sorted(REPOS_DIR.glob("*.yml")):
        data = load_yaml(yml_file)
        name = data.get("name")
        if isinstance(name, str) and name:
            defined[name] = data
    return defined


def check_fleet(
    defined: dict[str, dict[str, Any]], live: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    """Membership, visibility, wiki and archive drift."""
    declared_only = sorted(set(defined) - set(live))
    live_only = sorted(set(live) - set(defined))
    matched = sorted(set(defined) & set(live))

    visibility_drift: list[dict[str, str]] = []
    wiki_drift: list[str] = []
    archived: list[str] = []

    for name in matched:
        want = defined[name]
        have = live[name]
        live_vis = "private" if have.get("isPrivate") else "public"
        want_vis = str(want.get("visibility", ""))
        if want_vis != live_vis:
            visibility_drift.append(
                {
                    "repo": name,
                    "declared": want_vis,
                    "live": live_vis,
                    # A repo declared private but live public is the dangerous
                    # direction: confidential content is world-readable now.
                    "exposure": "high" if want_vis == "private" and live_vis == "public" else "low",
                }
            )
        settings = want.get("settings") or {}
        if have.get("hasWikiEnabled") and not settings.get("has_wiki", False):
            wiki_drift.append(name)
        if have.get("isArchived") and not settings.get("archived", False):
            archived.append(name)

    return {
        "declared_but_missing_from_org": declared_only,
        "in_org_but_not_declared": live_only,
        "matched": matched,
        "visibility_drift": visibility_drift,
        "wiki_drift": wiki_drift,
        "unexpectedly_archived": archived,
    }


def check_branch_protection(
    repos: list[str], baseline: dict[str, Any]
) -> tuple[dict[str, Any], list[str]]:
    """Verify a protection rule exists and is not weaker than the baseline.

    Repos in branch_protection_baseline_exempt must still HAVE a rule; only the
    attribute comparison is skipped. That keeps the exemption from becoming a
    way to leave a repo unprotected.
    """
    required = baseline.get("required_branch_protection") or {}
    min_contexts = int(required.get("minimum_required_contexts", 1))
    exempt = {str(r) for r in (baseline.get("branch_protection_baseline_exempt") or [])}

    missing: list[str] = []
    weakened: list[dict[str, Any]] = []
    unverifiable: list[str] = []

    for repo in repos:
        branch = "main"
        status, prot = try_get(f"repos/{ORG}/{repo}/branches/{branch}/protection")

        if status == 404:
            # 404 here means "no protection rule", which is a real finding —
            # but only if the repo itself exists. Distinguish the two.
            repo_status, _ = try_get(f"repos/{ORG}/{repo}")
            if repo_status == 404:
                continue  # absent repo is already reported by the fleet check
            missing.append(repo)
            continue
        if status != 200:
            unverifiable.append(f"{repo}: protection HTTP {status}")
            continue
        if repo in exempt:
            continue

        issues: list[str] = []
        reviews = prot.get("required_pull_request_reviews") or {}
        checks = prot.get("required_status_checks") or {}
        contexts = list(checks.get("contexts") or [])
        contexts += [c.get("context") for c in (checks.get("checks") or []) if c.get("context")]

        if required.get("enforce_admins", True) and not (prot.get("enforce_admins") or {}).get(
            "enabled", False
        ):
            issues.append("enforce_admins disabled")
        if not required.get("allow_force_pushes", False) and (
            prot.get("allow_force_pushes") or {}
        ).get("enabled", False):
            issues.append("force pushes allowed")
        if not required.get("allow_deletions", False) and (prot.get("allow_deletions") or {}).get(
            "enabled", False
        ):
            issues.append("branch deletion allowed")
        if required.get("require_code_owner_reviews", True) and not reviews.get(
            "require_code_owner_reviews", False
        ):
            issues.append("CODEOWNERS review not required")
        if required.get("dismiss_stale_reviews", True) and not reviews.get(
            "dismiss_stale_reviews", False
        ):
            issues.append("stale reviews not dismissed")
        if len(contexts) < min_contexts:
            issues.append(f"only {len(contexts)} required status check(s), need >= {min_contexts}")

        if issues:
            weakened.append({"repo": repo, "issues": issues})

    return (
        {"missing": missing, "weakened": weakened, "required": required, "exempt": sorted(exempt)},
        unverifiable,
    )


def check_admins(repos: list[str], allowed: list[str]) -> tuple[list[dict[str, Any]], list[str]]:
    """Flag anyone holding admin who is not on the allow-list."""
    unexpected: list[dict[str, Any]] = []
    unverifiable: list[str] = []
    allowed_set = set(allowed)

    for repo in repos:
        status, body = try_get(f"repos/{ORG}/{repo}/collaborators?affiliation=all&permission=admin")
        if status == 404:
            continue  # absent repo reported elsewhere
        if status != 200:
            unverifiable.append(f"{repo}: collaborators HTTP {status}")
            continue
        if not isinstance(body, list):
            unverifiable.append(f"{repo}: unexpected collaborators payload")
            continue
        admins = sorted(str(c.get("login", "")) for c in body if isinstance(c, dict))
        extra = [a for a in admins if a not in allowed_set]
        if extra:
            unexpected.append({"repo": repo, "unexpected_admins": extra, "all_admins": admins})

    return unexpected, unverifiable


def check_codeowners(repos: list[str]) -> tuple[list[dict[str, Any]], list[str]]:
    """Check for cross-project CODEOWNERS references (ADR-0004 R4, D-20).

    Fetches .github/CODEOWNERS from each repo and checks for references to
    mission-platform orgs (journeyoflife-org, jol-infrastructure) that don't
    exist in jolarca-dev. Such references make require_code_owner_reviews inert.
    """
    import base64

    violations: list[dict[str, Any]] = []
    unverifiable: list[str] = []

    # Cross-project org references that must not appear in jolarca-dev CODEOWNERS
    forbidden_orgs = ["journeyoflife-org", "jol-infrastructure"]

    for repo in repos:
        status, body = try_get(f"repos/{ORG}/{repo}/contents/.github/CODEOWNERS")
        if status == 404:
            # No CODEOWNERS file — not a violation, just note it
            continue
        if status != 200:
            unverifiable.append(f"{repo}: CODEOWNERS HTTP {status}")
            continue

        # API returns base64-encoded content
        content_b64 = body.get("content", "")
        try:
            content = base64.b64decode(content_b64).decode("utf-8")
        except (ValueError, UnicodeDecodeError) as exc:
            unverifiable.append(f"{repo}: CODEOWNERS decode error: {exc}")
            continue

        # Check for forbidden org references
        found_forbidden: list[str] = []
        for line in content.splitlines():
            # Skip comments
            if line.strip().startswith("#"):
                continue
            # Check each forbidden org
            for org in forbidden_orgs:
                if f"@{org}/" in line:
                    # Extract the full reference
                    import re
                    matches = re.findall(rf"@{re.escape(org)}/\S+", line)
                    found_forbidden.extend(matches)

        if found_forbidden:
            violations.append({
                "repo": repo,
                "forbidden_refs": sorted(set(found_forbidden)),
            })

    return violations, unverifiable


def check_org_settings(baseline: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    """Compare live org owner settings against the declared baseline."""
    live = must_get(f"orgs/{ORG}")
    violations: list[dict[str, Any]] = []
    unverifiable: list[str] = []

    for setting in ORG_SETTINGS:
        if setting not in baseline:
            continue
        if setting not in live:
            unverifiable.append(f"org setting '{setting}' absent from API response")
            continue
        expected = baseline[setting]
        actual = live[setting]
        if actual != expected:
            violations.append(
                {"setting": setting, "expected": expected, "live": actual}
            )

    return violations, unverifiable


def render_issue_body(report: dict[str, Any]) -> str:
    """Markdown body for the drift alert issue."""
    source = (
        "**Source:** `scripts/drift_detect.py` (allow-list + "
        "`policy/repo-defaults.yml` `organization_baseline`)"
    )
    scope_note = (
        "This is automated detection, not remediation. Org-level settings require an "
        "org owner; repository settings require a PR to `repos/*.yml`."
    )
    lines = [
        "## Control-plane drift detected",
        "",
        f"**Organization:** `{report['organization']}`  ",
        f"**Detected:** {report['generated_at']}  ",
        source,
        "",
        scope_note,
        "",
    ]

    sections = [
        ("Repos declared but missing from the org", report["fleet"]["declared_but_missing_from_org"]),
        ("Repos in the org but not declared (ADR-0004 R2 incident)", report["fleet"]["in_org_but_not_declared"]),
        ("Wiki enabled contrary to policy", report["fleet"]["wiki_drift"]),
        ("Unexpectedly archived", report["fleet"]["unexpectedly_archived"]),
        ("Branch protection MISSING entirely", report["branch_protection"]["missing"]),
    ]
    for title, items in sections:
        if items:
            lines.append(f"### {title}")
            lines += [f"- `{i}`" for i in items]
            lines.append("")

    exposure = [d for d in report["fleet"]["visibility_drift"] if d.get("exposure") == "high"]
    other_vis = [d for d in report["fleet"]["visibility_drift"] if d.get("exposure") != "high"]
    if exposure:
        lines.append("### HIGH EXPOSURE — declared private, live PUBLIC")
        lines.append(
            "Confidential-classified content is world-readable. Assess under "
            "GDPR Art. 33 before treating this as routine drift."
        )
        lines += [f"- `{d['repo']}`: declared `{d['declared']}`, live `{d['live']}`" for d in exposure]
        lines.append("")
    if other_vis:
        lines.append("### Visibility mismatch")
        lines += [f"- `{d['repo']}`: declared `{d['declared']}`, live `{d['live']}`" for d in other_vis]
        lines.append("")

    if report["branch_protection"]["weakened"]:
        lines.append("### Branch protection weaker than baseline")
        for item in report["branch_protection"]["weakened"]:
            lines.append(f"- `{item['repo']}`: {'; '.join(item['issues'])}")
        lines.append("")

    if report["unexpected_admins"]:
        lines.append("### Unexpected administrators")
        lines.append(
            "Verify each is an authorised invitation. An unexplained admin on a "
            "governance repo is a compromise indicator, not drift."
        )
        for item in report["unexpected_admins"]:
            lines.append(f"- `{item['repo']}`: {', '.join(item['unexpected_admins'])}")
        lines.append("")

    if report["codeowners_violations"]:
        lines.append("### CODEOWNERS references mission-platform orgs (ADR-0004 R4)")
        lines.append(
            "These references point to teams that don't exist in jolarca-dev, "
            "making `require_code_owner_reviews` inert. Fix by removing cross-project "
            "references and setting jolarca-dev-only owners."
        )
        for item in report["codeowners_violations"]:
            lines.append(f"- `{item['repo']}`: {', '.join(item['forbidden_refs'])}")
        lines.append("")

    if report["organization_settings"]["violations"]:
        lines.append("### Organization settings below baseline")
        lines.append("| Setting | Expected | Live |")
        lines.append("|---|---|---|")
        for item in report["organization_settings"]["violations"]:
            lines.append(f"| `{item['setting']}` | `{item['expected']}` | `{item['live']}` |")
        lines.append("")

    if report["unverifiable"]:
        lines.append("### Could not be verified (token scope)")
        lines += [f"- {i}" for i in report["unverifiable"]]
        lines.append("")

    return "\n".join(lines)


def summarise(report: dict[str, Any]) -> list[str]:
    """Human-readable stderr lines."""
    out: list[str] = []
    fleet = report["fleet"]

    for name in fleet["declared_but_missing_from_org"]:
        out.append(f"DRIFT: '{name}' is in the allow-list but NOT in {ORG}")
    for name in fleet["in_org_but_not_declared"]:
        out.append(
            f"DRIFT: '{name}' is in {ORG} but NOT in the allow-list "
            "(out-of-band creation — import within 48h, ADR-0004 R2)"
        )
    for item in fleet["visibility_drift"]:
        tag = "HIGH EXPOSURE" if item.get("exposure") == "high" else "mismatch"
        out.append(
            f"DRIFT [{tag}]: {item['repo']} visibility declared "
            f"{item['declared']}, live {item['live']}"
        )
    if fleet["wiki_drift"]:
        out.append(f"DRIFT: wiki enabled contrary to policy: {', '.join(fleet['wiki_drift'])}")
    if fleet["unexpectedly_archived"]:
        out.append(f"DRIFT: unexpectedly archived: {', '.join(fleet['unexpectedly_archived'])}")

    bp = report["branch_protection"]
    for name in bp["missing"]:
        out.append(f"DRIFT: {name} has NO branch protection on main — repo is unguarded")
    for item in bp["weakened"]:
        out.append(f"DRIFT: {item['repo']} branch protection weakened: {'; '.join(item['issues'])}")

    for item in report["unexpected_admins"]:
        out.append(
            f"DRIFT: {item['repo']} has unexpected admin(s): "
            f"{', '.join(item['unexpected_admins'])}"
        )

    for item in report["codeowners_violations"]:
        out.append(
            f"DRIFT: {item['repo']} CODEOWNERS references mission-platform orgs "
            f"(ADR-0004 R4): {', '.join(item['forbidden_refs'])}"
        )

    for item in report["organization_settings"]["violations"]:
        out.append(
            f"DRIFT: org {item['setting']} = {item['live']!r}, baseline requires "
            f"{item['expected']!r}"
        )

    for item in report["unverifiable"]:
        out.append(f"UNVERIFIED: {item}")

    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--issue-body",
        type=Path,
        help="Write a Markdown drift report to this path for the alerting workflow.",
    )
    parser.add_argument(
        "--allow-unverifiable",
        action="store_true",
        help="Downgrade per-repo scope errors (HTTP 403) to warnings instead of exit 2.",
    )
    args = parser.parse_args()

    defined = get_defined_repos()
    policy = load_yaml(POLICY_FILE)
    baseline = policy.get("organization_baseline") or {}
    if not baseline:
        print(
            "ERROR: policy/repo-defaults.yml has no organization_baseline section",
            file=sys.stderr,
        )
        return 2

    # ── Fatal-if-unreadable: the fleet listing is the root of every check ────
    status, live_list = try_get(f"orgs/{ORG}/repos?per_page=100")
    if status != 200 or not isinstance(live_list, list):
        detail = live_list.get("error", "unexpected payload") if isinstance(live_list, dict) else "unexpected payload"
        print(
            f"ERROR: could not list {ORG} repositories (HTTP {status}): {detail}",
            file=sys.stderr,
        )
        print(
            "Refusing to report 'no drift': the live state could not be read. "
            "Check that GITHUB_TOKEN/GH_TOKEN is present and unexpired (D-23).",
            file=sys.stderr,
        )
        return 2
    if not live_list:
        print(
            f"ERROR: {ORG} returned an empty repository list — expected at least the "
            "six fleet repos. Treating as unverifiable rather than as a deleted fleet.",
            file=sys.stderr,
        )
        return 2

    live_names = {str(r["name"]) for r in live_list if isinstance(r, dict) and r.get("name")}
    live = {name: r for name, r in ((str(r["name"]), r) for r in live_list if isinstance(r, dict)
                                    and r.get("name")) if name != HEALTH_REPO}

    fleet = check_fleet(defined, live)

    # Protection and admin checks cover every repo that actually exists,
    # including the health repo, which carries a deliberately minimal rule.
    existing = sorted(set(fleet["matched"]) | ({HEALTH_REPO} & live_names))

    unverifiable: list[str] = []
    allowed_admins = [str(a) for a in (baseline.get("allowed_admins") or [])]

    try:
        org_violations, org_unverifiable = check_org_settings(baseline)
    except Unverifiable as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        print("Org settings could not be read; refusing to report 'no drift'.", file=sys.stderr)
        return 2
    unverifiable.extend(org_unverifiable)

    bp_report, bp_unverifiable = check_branch_protection(existing, baseline)
    unverifiable.extend(bp_unverifiable)

    admins_report, admin_unverifiable = check_admins(existing, allowed_admins)
    unverifiable.extend(admin_unverifiable)

    codeowners_report, codeowners_unverifiable = check_codeowners(existing)
    unverifiable.extend(codeowners_unverifiable)

    report: dict[str, Any] = {
        "organization": ORG,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "health_repo_excluded": HEALTH_REPO,
        "declared_count": len(defined),
        "live_count": len(live),
        "matched_count": len(fleet["matched"]),
        "fleet": fleet,
        "branch_protection": bp_report,
        "unexpected_admins": admins_report,
        "codeowners_violations": codeowners_report,
        "organization_settings": {
            "violations": org_violations,
            "baseline_source": "policy/repo-defaults.yml#organization_baseline",
        },
        "unverifiable": unverifiable,
    }
    report["drift_detected"] = bool(
        fleet["declared_but_missing_from_org"]
        or fleet["in_org_but_not_declared"]
        or fleet["visibility_drift"]
        or fleet["wiki_drift"]
        or fleet["unexpectedly_archived"]
        or bp_report["missing"]
        or bp_report["weakened"]
        or admins_report
        or codeowners_report
        or org_violations
    )

    print(json.dumps(report, indent=2, default=str))

    for line in summarise(report):
        print(line, file=sys.stderr)

    if args.issue_body:
        args.issue_body.write_text(render_issue_body(report), encoding="utf-8")
        print(f"issue body written to {args.issue_body}", file=sys.stderr)

    if unverifiable and not args.allow_unverifiable:
        print(
            f"ERROR: {len(unverifiable)} check(s) could not be verified. "
            "Pass --allow-unverifiable only if the token genuinely lacks scope.",
            file=sys.stderr,
        )
        return 2

    if not report["drift_detected"]:
        print(
            f"NO DRIFT — {len(fleet['matched'])} declared repos match {ORG}, "
            "branch protection and org baseline verified.",
            file=sys.stderr,
        )
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
