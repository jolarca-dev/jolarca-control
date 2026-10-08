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

# A-08 (2026-10-08): when policy declares the `sast` gate mandatory for a tier,
# that tier's repos must have a job producing the primary SAST context as a
# required status check. `SAST (semgrep)` is the Semgrep OSS job name emitted
# by `.github/workflows/sast.yml` — the language-agnostic rule engine that
# runs on the Free plan without GHAS. Bandit and Trivy run alongside in the
# same workflow but are defense-in-depth contexts; only the primary one is
# required, so a temporary Trivy infra outage does not deadlock every PR.
SAST_PRIMARY_CONTEXT = "SAST (semgrep)"
# The scope of this control plane's self-check. Other repos in the fleet have
# the same policy requirement (all three tiers list `sast` in
# enforcement_matrix.required) but their own PRs must land their own
# `.github/workflows/sast.yml`; validating them from here would fire a red
# for 15 of 16 repos before any of them get the chance to close the gap.
SELF_REPO_NAME = "jolarca-control"


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


def check_sast_gate_wiring(
    repos: dict[str, dict[str, Any]],
    gates: dict[str, Any],
    enforcement_matrix: dict[str, Any],
) -> dict[str, Any]:
    """A-08: if policy declares `sast` mandatory for this repo's tier, the
    declared required-status-check contexts must include the SAST primary.

    Scope is `jolarca-control` (this repo). Other fleet members carry the same
    tier requirement but their own CI wiring is theirs to land; validating
    them from here would fire red for 15 of 16 repos before any of them gets
    the chance to close the gap — a D-23 class unverified-as-verified inversion
    in the other direction (a permanent fail is as dishonest as a permanent
    pass).

    Three invariants, all read from declared config:
    1. `gates.sast` exists AND declares `enforcement: mandatory` OR a
       `mandatory_for_tier:` list that includes this repo's declared tier.
    2. `enforcement_matrix[<tier>].required` includes `sast`.
    3. `repos/jolarca-control.yml` branch_protection.main.required_status_checks
       .contexts contains `SAST (semgrep)`.

    Missing gate or missing tier: unverifiable, exit-code semantics preserved
    by returning status=fail (this is a DECLARED-consistency script; live
    drift belongs to scripts/drift_detect.py per the module docstring).
    """
    self_repo = repos.get(SELF_REPO_NAME)
    if not isinstance(self_repo, dict):
        return {
            "check": "sast_gate_wiring",
            "status": "fail",
            "compliant": 0,
            "total": 1,
            "violations": [
                (
                    f"{SELF_REPO_NAME}.yml is missing or unreadable — cannot "
                    "verify the SAST gate is wired"
                ),
            ],
        }

    tier = self_repo.get("tier")
    if not tier:
        return {
            "check": "sast_gate_wiring",
            "status": "fail",
            "compliant": 0,
            "total": 1,
            "violations": [f"repos/{SELF_REPO_NAME}.yml does not declare a tier"],
        }

    tier_row = enforcement_matrix.get(tier) or {}
    required_in_tier = tier_row.get("required") or []
    sast_required = "sast" in required_in_tier

    sast_gate = gates.get("sast") or {}
    sast_enforcement = sast_gate.get("enforcement", "")
    # `mandatory_for_tier:governance,devops` is the other spelling used in this
    # file; parse the tier list so the check does not silently miss it.
    mandatory_tiers: list[str] = []
    if isinstance(sast_enforcement, str):
        if sast_enforcement == "mandatory":
            mandatory_tiers = [tier]  # applies to every tier
        elif sast_enforcement.startswith("mandatory_for_tier:"):
            mandatory_tiers = [t.strip() for t in sast_enforcement.split(":", 1)[1].split(",")]

    gate_declares_mandatory_here = tier in mandatory_tiers or sast_enforcement == "mandatory"

    violations: list[str] = []
    if not (sast_required or gate_declares_mandatory_here):
        # Neither policy path says SAST is required for this repo's tier.
        # That is a policy-integrity defect, not a wiring defect. Fail loud.
        violations.append(
            f"policy/compliance-gates.yml neither lists 'sast' in "
            f"enforcement_matrix['{tier}'].required nor declares gates.sast."
            f"enforcement covering tier '{tier}' (observed enforcement: "
            f"{sast_enforcement!r}). A 'mandatory' gate that is not required "
            "anywhere is folklore, not a control (AGENTS.md §7, D-22)."
        )
    else:
        bp = (self_repo.get("branch_protection") or {}).get("main") or {}
        contexts = (bp.get("required_status_checks") or {}).get("contexts") or []
        if not isinstance(contexts, list):
            violations.append(
                f"repos/{SELF_REPO_NAME}.yml branch_protection.main.required_status_checks"
                f".contexts must be a list, got {type(contexts).__name__}"
            )
        elif SAST_PRIMARY_CONTEXT not in contexts:
            violations.append(
                f"repos/{SELF_REPO_NAME}.yml declares tier '{tier}' which "
                f"requires the 'sast' gate (enforcement_matrix['{tier}']."
                f"required), but its required_status_checks.contexts list "
                f"{contexts!r} does not include {SAST_PRIMARY_CONTEXT!r}. "
                "Either wire the workflow (see .github/workflows/sast.yml) "
                "or amend the enforcement_matrix — do NOT silently remove "
                "'sast' from the tier's required list without an ADR (RB-04)."
            )

    return {
        "check": "sast_gate_wiring",
        "status": "pass" if not violations else "fail",
        "compliant": 1 - len(violations),
        "total": 1,
        "sast_required_for_tier": sast_required,
        "primary_context": SAST_PRIMARY_CONTEXT,
        "scope": f"self (repos/{SELF_REPO_NAME}.yml); siblings carry the same "
        "tier requirement and must land their own SAST workflow",
        "violations": violations,
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

    gates_doc = load_yaml(POLICY_DIR / "compliance-gates.yml")
    gates = gates_doc.get("gates", {})
    enforcement_matrix = gates_doc.get("enforcement_matrix", {})

    checks = [
        check_fleet_separation(repos),
        check_dependabot_coverage(repos),
        check_branch_protection(repos, want_signed),
        check_data_classification(repos),
        check_compliance_frameworks(repos),
        check_wiki_disabled(repos),
        check_merge_policy(repos),
        check_sast_gate_wiring(repos, gates, enforcement_matrix),
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
