#!/usr/bin/env python3
"""Run compliance checks against repo definitions and policy baselines.

jolarca-control — marketplace (jolarca-dev) governance control plane.
Outputs a JSON compliance report usable as audit evidence (SOC 2 CC4.1,
ISO 27001 A.5.31 / A.8.8, PCI-DSS 12.10) for the DECLARED configuration.

Scope matters when citing this report: every check reads repos/*.yml and
policy/, never the GitHub API. `overall_status: pass` means the allow-list is
internally consistent — it is not a statement about the live organization.
Live verification is scripts/drift_detect.py. Both are needed for evidence;
neither substitutes for the other (D-30).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

BASE_DIR = Path(__file__).resolve().parent.parent
REPOS_DIR = BASE_DIR / "repos"
POLICY_DIR = BASE_DIR / "policy"

# Every marketplace repo is inside the PCI-DSS CDE-adjacent scope, so all four
# frameworks are mandatory at every tier — unlike jol-control, where pci-dss
# applies only to payment-related repos.
REQUIRED_FRAMEWORKS = {"soc2", "gdpr", "iso27001", "pci-dss"}
CLASSIFICATIONS_REQUIRING_PRIVATE = {"confidential", "restricted"}
FLEET_NAME_RE = re.compile(r"^jolarca(-[a-z0-9-]+)?$")


def load_yaml(filepath: Path) -> dict[str, Any]:
    with open(filepath, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data if isinstance(data, dict) else {}


def check_fleet_separation(repos: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """ADR-0004 R1/R3: no mission-platform repo may enter this allow-list."""
    violations = [n for n in repos if not FLEET_NAME_RE.match(n)]
    return {
        "check": "fleet_separation_adr0004",
        "status": "pass" if not violations else "fail",
        "compliant": len(repos) - len(violations),
        "total": len(repos),
        "violations": sorted(violations),
    }


def check_dependabot_coverage(repos: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Verify Dependabot vulnerability alerts are declared on every repo."""
    gaps = [
        n for n, d in repos.items() if not d.get("settings", {}).get("vulnerability_alerts", False)
    ]
    return {
        "check": "dependabot_alerts_coverage",
        "status": "pass" if not gaps else "fail",
        "covered": len(repos) - len(gaps),
        "total": len(repos),
        "gaps": sorted(gaps),
    }


def check_branch_protection(repos: dict[str, dict[str, Any]], want_signed: bool) -> dict[str, Any]:
    """Verify all repos declare branch protection with the required settings."""
    hard_failures = []
    deviations = []
    for name, defn in repos.items():
        bp = defn.get("branch_protection", {}).get("main", {})
        issues = []
        if want_signed and not bp.get("require_signed_commits"):
            issues.append("missing signed commits")
        if not bp.get("block_force_pushes"):
            issues.append("allows force push")
        if not bp.get("block_deletions"):
            issues.append("allows branch deletion")
        if not bp.get("enforce_admins"):
            issues.append("admins not enforced")
        if not bp.get("require_linear_history"):
            issues.append("linear history not required")
        if not (bp.get("required_status_checks") or {}).get("contexts"):
            issues.append("no required status checks — protection enforces nothing")
        reviews = bp.get("required_pull_request_reviews") or {}
        count = reviews.get("required_approving_review_count")
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            issues.append("invalid required_approving_review_count")
        elif count == 0:
            # Not a failure: tracked solo-era deviation D-04. Reported in its
            # own list so the audit trail shows it explicitly instead of either
            # hiding it or counting it as a defect.
            deviations.append(name)
        if issues:
            hard_failures.append({"repo": name, "issues": issues})
    return {
        "check": "branch_protection",
        "status": "pass" if not hard_failures else "fail",
        "compliant": len(repos) - len(hard_failures),
        "total": len(repos),
        "non_compliant": hard_failures,
        "solo_era_deviation_D04": sorted(deviations),
        "note": "solo_era_deviation_D04 lists repos relying on the documented "
        "zero-approving-review deviation. That is a tracked risk "
        "acceptance, not a control failure.",
    }


def check_data_classification(repos: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Verify classification is set and coherent with repo visibility."""
    valid = ("public", "internal", "confidential", "restricted")
    unclassified = []
    incoherent = []
    for name, defn in repos.items():
        dc = defn.get("compliance", {}).get("data_classification", "")
        if dc not in valid:
            unclassified.append(name)
            continue
        if dc in CLASSIFICATIONS_REQUIRING_PRIVATE and defn.get("visibility") == "public":
            incoherent.append({"repo": name, "data_classification": dc, "visibility": "public"})
    classified = len(repos) - len(unclassified)
    return {
        "check": "data_classification",
        "status": "pass" if not unclassified and not incoherent else "fail",
        "classified": classified,
        "total": len(repos),
        "unclassified": sorted(unclassified),
        "public_but_sensitive": incoherent,
    }


def check_compliance_frameworks(repos: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Verify every repo declares all four mandatory frameworks."""
    compliant = 0
    gaps = []
    for name, defn in repos.items():
        frameworks = set(defn.get("compliance", {}).get("frameworks", []))
        missing = REQUIRED_FRAMEWORKS - frameworks
        if missing:
            gaps.append({"repo": name, "missing": sorted(missing)})
        else:
            compliant += 1
    return {
        "check": "compliance_frameworks",
        "status": "pass" if not gaps else "fail",
        "compliant": compliant,
        "total": len(repos),
        "gaps": gaps,
    }


def check_wiki_disabled(repos: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Verify wiki is disabled on all repos."""
    violations = sorted(n for n, d in repos.items() if d.get("settings", {}).get("has_wiki", False))
    return {
        "check": "wiki_disabled",
        "status": "pass" if not violations else "fail",
        "compliant": len(repos) - len(violations),
        "total": len(repos),
        "violations": violations,
    }


def check_merge_policy(repos: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Squash-only + branch deletion keeps a linear, auditable history (CC8.1)."""
    violations = []
    for name, defn in repos.items():
        s = defn.get("settings", {})
        if s.get("allow_merge_commit", False) or not s.get("allow_squash_merge", True):
            violations.append(name)
    return {
        "check": "squash_only_merge_policy",
        "status": "pass" if not violations else "fail",
        "compliant": len(repos) - len(violations),
        "total": len(repos),
        "violations": sorted(violations),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run compliance checks on jolarca-control repo definitions"
    )
    parser.add_argument("--output", type=str, help="Output file path (default: stdout)")
    args = parser.parse_args()

    repos: dict[str, dict[str, Any]] = {}
    for yml_file in sorted(REPOS_DIR.glob("*.yml")):
        repos[yml_file.stem] = load_yaml(yml_file)

    defaults = load_yaml(POLICY_DIR / "repo-defaults.yml")
    want_signed = ((defaults.get("branch_protection") or {}).get("main") or {}).get(
        "require_signed_commits", True
    )

    checks = [
        check_fleet_separation(repos),
        check_dependabot_coverage(repos),
        check_branch_protection(repos, want_signed),
        check_data_classification(repos),
        check_compliance_frameworks(repos),
        check_wiki_disabled(repos),
        check_merge_policy(repos),
    ]

    overall_status = "pass" if all(c["status"] == "pass" for c in checks) else "fail"

    report = {
        "timestamp": datetime.now(UTC).isoformat(),
        "control_plane": "jolarca-control",
        "organization": "jolarca-dev",
        "framework": "SOC2/GDPR/ISO27001/PCI-DSS-4.0",
        # Without this caveat the report is actively misleading as evidence:
        # every check below reads repos/*.yml and policy/, never the GitHub API.
        # On 2026-09-25 this report returned overall_status=pass while four
        # repos classified `confidential` were publicly readable and exposing
        # the live RoPA (D-01). Declared-config consistency and organizational
        # compliance are different claims, and an auditor is entitled to know
        # which one they are holding (D-30).
        "scope": "DECLARED CONFIGURATION ONLY — repos/*.yml validated against "
        "policy/. This report does NOT read live GitHub state.",
        "scope_warning": "overall_status=pass means the allow-list is internally "
        "consistent. It does NOT mean the organization complies. For live "
        "verification see scripts/drift_detect.py.",
        "live_state_verified": False,
        "live_state_source": "scripts/drift_detect.py",
        "overall_status": overall_status,
        "total_repos": len(repos),
        "checks": checks,
    }

    output = json.dumps(report, indent=2)
    if args.output:
        Path(args.output).write_text(output)
        print(f"Report written to {args.output}")
    else:
        print(output)

    return 0 if overall_status == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
