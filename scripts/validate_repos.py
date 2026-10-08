#!/usr/bin/env python3
"""Validate all repository YAML definitions against the allow-list and policy.

jolarca-control — marketplace (jolarca-dev) governance control plane.

Checks enforced here:
  * required fields present, name matches filename
  * ADR-0004 R1: every fleet entry is named `jolarca` or `jolarca-<suffix>`
  * visibility / tier / data_classification come from the permitted vocabularies
  * criticality / launch_status come from the permitted vocabularies declared in
    policy/repo-defaults.yml#asset_inventory, so the inventory rubric lives in
    one place and a change to it changes what this validator enforces
  * wiki disabled (policy)
  * branch protection on `main` with force-push blocked and admins enforced
  * signed-commit expectation read from policy/repo-defaults.yml, NOT hardcoded,
    so a documented deviation (D-05) does not silently fail validation
  * data-classification ↔ visibility coherence: confidential/restricted data
    must not sit in a public repository
  * data-classification ↔ criticality coherence: confidential/restricted data
    cannot be tier-3, whose definition is "holds no regulated data"
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

import yaml

BASE_DIR = Path(__file__).resolve().parent.parent
REPOS_DIR = BASE_DIR / "repos"
POLICY_FILE = BASE_DIR / "policy" / "repo-defaults.yml"

REQUIRED_FIELDS = [
    "name",
    "description",
    "visibility",
    "tier",
    "criticality",
    "launch_status",
    "settings",
    "branch_protection",
    "compliance",
]
VALID_VISIBILITIES = {"public", "private", "internal"}
VALID_TIERS = {"governance", "platform", "devops", "site", "template"}
VALID_CLASSIFICATIONS = {"public", "internal", "confidential", "restricted"}
CLASSIFICATIONS_REQUIRING_PRIVATE = {"confidential", "restricted"}
# tier-3 is defined as "holds no regulated data", so it contradicts a
# confidential/restricted classification by construction.
CRITICALITY_INCOMPATIBLE_WITH_SENSITIVE = {"tier-3"}

# ADR-0004 R1/R3 — mission/marketplace separation. Mirrors the Terraform
# precondition in repositories.tf and scripts/check_fleet_separation.sh.
FLEET_NAME_RE = re.compile(r"^jolarca(-[a-z0-9-]+)?$")


def load_policy() -> dict[str, Any]:
    with open(POLICY_FILE, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data if isinstance(data, dict) else {}


def policy_main_bp(policy: dict[str, Any]) -> dict[str, Any]:
    return (policy.get("branch_protection") or {}).get("main") or {}


def asset_vocabulary(policy: dict[str, Any], attribute: str) -> set[str]:
    """Closed vocabulary for an asset-inventory attribute, read from policy.

    The rubric lives in policy/repo-defaults.yml#asset_inventory so an auditor
    reads the definition and the enforcement from the same source.
    """
    inventory = policy.get("asset_inventory") or {}
    return set((inventory.get(attribute) or {}).keys())


def validate_repo(filepath: Path, policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    with open(filepath) as f:
        try:
            data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            return [f"{filepath.name}: Invalid YAML — {e}"]

    if not isinstance(data, dict):
        return [f"{filepath.name}: Root must be a YAML mapping"]

    # Required fields
    for field in REQUIRED_FIELDS:
        if field not in data:
            errors.append(f"{filepath.name}: Missing required field '{field}'")

    # Name consistency
    expected_name = filepath.stem
    if data.get("name") != expected_name:
        errors.append(
            f"{filepath.name}: name='{data.get('name')}' does not match filename '{expected_name}'"
        )

    # ADR-0004 R1 — fleet naming / mission separation
    name = data.get("name", "")
    if not FLEET_NAME_RE.match(name):
        errors.append(
            f"{filepath.name}: '{name}' is not named jolarca or jolarca-<suffix>. "
            "Mission-platform repos (jol-*) belong to jol-control, not this control "
            "plane (ADR-0004 R1/R3 mission/marketplace separation)."
        )

    # Visibility
    vis = data.get("visibility", "")
    if vis not in VALID_VISIBILITIES:
        errors.append(
            f"{filepath.name}: Invalid visibility '{vis}' — must be one of {sorted(VALID_VISIBILITIES)}"
        )

    # Tier
    tier = data.get("tier", "")
    if tier not in VALID_TIERS:
        errors.append(
            f"{filepath.name}: Invalid tier '{tier}' — must be one of {sorted(VALID_TIERS)}"
        )

    # Asset-inventory attributes (ISO 27001 A.5.9 / SOC 2 CC6.1). `tier` above
    # is the FUNCTIONAL tier that selects gates in compliance-gates.yml;
    # `criticality` is the business-impact tier used to prioritise incidents.
    # They are different axes and both are required.
    valid_criticality = asset_vocabulary(policy, "criticality")
    valid_launch_status = asset_vocabulary(policy, "launch_status")

    criticality = data.get("criticality", "")
    if criticality not in valid_criticality:
        errors.append(
            f"{filepath.name}: Invalid criticality '{criticality}' — must be one of "
            f"{sorted(valid_criticality)} (policy/repo-defaults.yml#asset_inventory)"
        )

    launch_status = data.get("launch_status", "")
    if launch_status not in valid_launch_status:
        errors.append(
            f"{filepath.name}: Invalid launch_status '{launch_status}' — must be one of "
            f"{sorted(valid_launch_status)} (policy/repo-defaults.yml#asset_inventory)"
        )

    # Settings validation
    settings = data.get("settings", {})
    if not isinstance(settings, dict):
        errors.append(f"{filepath.name}: 'settings' must be a mapping")
    else:
        # Wiki must be disabled (security best practice)
        if settings.get("has_wiki", False):
            errors.append(f"{filepath.name}: has_wiki should be false (security policy)")

    # Branch protection validation
    bp = data.get("branch_protection", {})
    if "main" not in bp:
        errors.append(f"{filepath.name}: Missing branch protection for 'main'")
    else:
        main_bp = bp["main"]
        if not main_bp.get("block_force_pushes", False):
            errors.append(f"{filepath.name}: main branch must block force pushes")
        if not main_bp.get("block_deletions", False):
            errors.append(f"{filepath.name}: main branch must block branch deletion")
        if not main_bp.get("enforce_admins", False):
            errors.append(f"{filepath.name}: main branch must enforce admins")
        if not main_bp.get("require_linear_history", False):
            errors.append(f"{filepath.name}: main branch must require linear history")

        # Signed commits: expectation comes from policy so a documented
        # deviation stays valid instead of being silently ignored.
        want_signed = policy_main_bp(policy).get("require_signed_commits", True)
        if want_signed and not main_bp.get("require_signed_commits", False):
            errors.append(
                f"{filepath.name}: main branch must require signed commits (policy/repo-defaults.yml)"
            )

        reviews = main_bp.get("required_pull_request_reviews") or {}
        if not isinstance(reviews, dict):
            errors.append(f"{filepath.name}: required_pull_request_reviews must be a mapping")
        else:
            count = reviews.get("required_approving_review_count")
            if not isinstance(count, int) or isinstance(count, bool) or count < 0:
                errors.append(
                    f"{filepath.name}: required_approving_review_count must be a non-negative integer"
                )

        checks = main_bp.get("required_status_checks") or {}
        if not isinstance(checks, dict):
            errors.append(f"{filepath.name}: required_status_checks must be a mapping")
        elif not checks.get("contexts"):
            # A protected branch with zero required contexts enforces nothing
            # beyond the review rule — that is how unreviewed code reached main
            # in the 2026-09 delivery-chain audit.
            errors.append(f"{filepath.name}: required_status_checks.contexts must not be empty")

    # Compliance validation
    compliance = data.get("compliance", {})
    if not isinstance(compliance, dict):
        errors.append(f"{filepath.name}: 'compliance' must be a mapping")
        return errors

    frameworks = compliance.get("frameworks") or []
    if not frameworks:
        errors.append(f"{filepath.name}: compliance.frameworks must not be empty")

    dc = compliance.get("data_classification", "")
    if dc not in VALID_CLASSIFICATIONS:
        errors.append(
            f"{filepath.name}: Invalid data_classification '{dc}' — must be one of {sorted(VALID_CLASSIFICATIONS)}"
        )

    # Data-classification ↔ visibility coherence (GDPR Art. 32, PCI-DSS 1.2)
    if dc in CLASSIFICATIONS_REQUIRING_PRIVATE and vis == "public":
        errors.append(
            f"{filepath.name}: data_classification '{dc}' cannot live in a public "
            "repository. Set visibility to private, or reclassify with a recorded "
            "decision in docs/drift-findings.md."
        )

    # Data-classification ↔ criticality coherence. tier-3 is DEFINED as holding
    # no regulated data, so pairing it with confidential/restricted means one of
    # the two entries is wrong and the inventory cannot be trusted for incident
    # triage.
    if dc in CLASSIFICATIONS_REQUIRING_PRIVATE and (
        criticality in CRITICALITY_INCOMPATIBLE_WITH_SENSITIVE
    ):
        errors.append(
            f"{filepath.name}: data_classification '{dc}' cannot be criticality "
            f"'{criticality}' — tier-3 is defined as holding no regulated data."
        )

    # PCI-DSS operational repos must not be public. A repo that is both
    # PCI-DSS-scoped and operational ("actively relied on for a live obligation")
    # sits in or adjacent to the CDE; public readability exposes the payment
    # estate's structure. Override only with `documented_risk_acceptance: true`
    # AND a matching entry in policy/compliance-gates.yml exceptions.active
    # (D-25 dated-acceptance pattern: approved_by, ISO-8601 expires, exit_trigger).
    launch = data.get("launch_status", "")
    frameworks = compliance.get("frameworks") or []
    if (
        "pci-dss" in frameworks
        and launch == "operational"
        and vis == "public"
        and not data.get("documented_risk_acceptance")
    ):
        errors.append(
            f"{filepath.name}: PCI-DSS-scoped operational repo cannot be public. "
            "Set visibility to private, or add documented_risk_acceptance: true "
            "with a matching dated entry in policy/compliance-gates.yml "
            "exceptions.active (approved_by, expires, exit_trigger)."
        )

    return errors


def main() -> int:
    if not REPOS_DIR.is_dir():
        print(f"ERROR: repos directory not found: {REPOS_DIR}", file=sys.stderr)
        return 1

    policy = load_policy()
    all_errors: list[str] = []
    repo_count = 0

    for yml_file in sorted(REPOS_DIR.glob("*.yml")):
        repo_count += 1
        all_errors.extend(validate_repo(yml_file, policy))

    if all_errors:
        print(f"FAILED — {len(all_errors)} error(s) in {repo_count} repo definitions:\n")
        for err in all_errors:
            print(f"  x {err}")
        return 1

    print(f"PASSED — {repo_count} repo definitions validated successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
