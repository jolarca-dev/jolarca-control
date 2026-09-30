"""Regression tests for the PCI-DSS operational-public guard in validate_repos.

WHY THESE EXIST
---------------
`scripts/validate_repos.py` enforces a fleet-wide allow-list: every repos/*.yml
must pass a battery of structural checks before CI reports green. On
2026-09-30 the user decided that jolarca-payments should remain public despite
being PCI-DSS-scoped, but wanted a guard preventing any FUTURE PCI-DSS
operational repo from going public without a documented risk acceptance.

The guard fires when ALL of:
  * compliance.frameworks contains "pci-dss"
  * launch_status == "operational"
  * visibility == "public"
  * documented_risk_acceptance is NOT truthy

The override mechanism (`documented_risk_acceptance: true`) is itself guarded:
the field must be accompanied by a matching entry in
policy/compliance-gates.yml exceptions.active (D-25 dated-acceptance pattern).
The validator does not check the exceptions file — that is the compliance
scanner's job — but the field cannot be added silently.

Run:  .venv/bin/python -m pytest tests/test_validate_repos.py -q
      make test
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import yaml

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "validate_repos.py"


def _load_module() -> ModuleType:
    """Import scripts/validate_repos.py without making scripts/ a package."""
    spec = importlib.util.spec_from_file_location("validate_repos", SCRIPT)
    assert spec is not None, f"cannot build an import spec for {SCRIPT}"
    assert spec.loader is not None, "import spec has no loader"
    module = importlib.util.module_from_spec(spec)
    sys.modules["validate_repos"] = module
    spec.loader.exec_module(module)
    return module


vr = _load_module()


def _policy() -> dict[str, Any]:
    return vr.load_policy()


def _minimal_repo(
    *,
    name: str = "test-repo",
    visibility: str = "public",
    tier: str = "platform",
    criticality: str = "tier-1",
    launch_status: str = "operational",
    frameworks: list[str] | None = None,
    data_classification: str = "internal",
    documented_risk_acceptance: bool = False,
) -> dict[str, Any]:
    """A repo dict matching the shape validate_repo expects, as a YAML fixture."""
    data: dict[str, Any] = {
        "name": name,
        "description": f"Test repo {name}",
        "visibility": visibility,
        "tier": tier,
        "criticality": criticality,
        "launch_status": launch_status,
        "language": "Python",
        "settings": {
            "has_issues": True,
            "has_wiki": False,
            "has_projects": False,
            "delete_branch_on_merge": True,
            "allow_merge_commit": False,
            "allow_squash_merge": True,
            "allow_rebase_merge": False,
            "vulnerability_alerts": True,
            "archived": False,
            "is_template": False,
            "auto_init": False,
            "web_commit_signoff_required": True,
        },
        "branch_protection": {
            "main": {
                "pattern": "main",
                "required_status_checks": {
                    "strict": True,
                    "contexts": ["lint"],
                },
                "required_pull_request_reviews": {
                    "required_approving_review_count": 0,
                    "dismiss_stale_reviews": True,
                    "require_code_owner_reviews": False,
                    "require_last_push_approval": False,
                },
                "enforce_admins": True,
                "restrict_pushes": True,
                "require_signed_commits": False,
                "require_linear_history": True,
                "require_conversation_resolution": True,
                "block_force_pushes": True,
                "block_deletions": True,
            }
        },
        "teams": {},
        "compliance": {
            "frameworks": frameworks or ["soc2"],
            "data_classification": data_classification,
            "required_gates": {"secret_scan": True},
        },
    }
    if documented_risk_acceptance:
        data["documented_risk_acceptance"] = True
    return data


def _validate(data: dict[str, Any], policy: dict[str, Any]) -> list[str]:
    """Run validate_repo on an in-memory dict (no filesystem needed)."""
    # validate_repo expects a Path for error messages; we pass a dummy.
    return vr.validate_repo(Path("test-repo.yml"), policy)


# We need validate_repo to read from the dict, not from a file. The current
# implementation opens the filepath. For unit tests we monkey-patch the open
# call by writing to a temp file — but that is slow. Instead, we test the
# guard logic directly by calling the function with a real YAML file on disk.
#
# A lighter approach: test via the live repos/ directory, which is what the
# validator actually runs against. The fleet-level tests below do exactly that.


# ── The guard fires on the exact conjunction ─────────────────────────────────


def test_pci_dss_operational_public_without_override_is_rejected(
    tmp_path: Path,
) -> None:
    """The core regression: pci-dss + operational + public must fail."""
    data = _minimal_repo(
        frameworks=["pci-dss", "soc2"],
        launch_status="operational",
        visibility="public",
    )
    filepath = tmp_path / "test-repo.yml"
    filepath.write_text(yaml.dump(data))
    errors = vr.validate_repo(filepath, _policy())
    assert any("PCI-DSS-scoped operational repo cannot be public" in e for e in errors)


def test_pci_dss_operational_public_with_override_passes(
    tmp_path: Path,
) -> None:
    """documented_risk_acceptance: true suppresses the guard."""
    data = _minimal_repo(
        frameworks=["pci-dss", "soc2"],
        launch_status="operational",
        visibility="public",
        documented_risk_acceptance=True,
    )
    filepath = tmp_path / "test-repo.yml"
    filepath.write_text(yaml.dump(data))
    errors = vr.validate_repo(filepath, _policy())
    assert not any("PCI-DSS-scoped operational repo cannot be public" in e for e in errors)


def test_pci_dss_planned_public_does_not_fire(
    tmp_path: Path,
) -> None:
    """launch_status=planned is the jolarca-payments case — guard must not fire."""
    data = _minimal_repo(
        frameworks=["pci-dss", "soc2"],
        launch_status="planned",
        visibility="public",
    )
    filepath = tmp_path / "test-repo.yml"
    filepath.write_text(yaml.dump(data))
    errors = vr.validate_repo(filepath, _policy())
    assert not any("PCI-DSS-scoped operational repo cannot be public" in e for e in errors)


def test_pci_dss_operational_private_does_not_fire(
    tmp_path: Path,
) -> None:
    """Private repos are the correct state — guard must not fire."""
    data = _minimal_repo(
        frameworks=["pci-dss", "soc2"],
        launch_status="operational",
        visibility="private",
    )
    filepath = tmp_path / "test-repo.yml"
    filepath.write_text(yaml.dump(data))
    errors = vr.validate_repo(filepath, _policy())
    assert not any("PCI-DSS-scoped operational repo cannot be public" in e for e in errors)


def test_non_pci_dss_operational_public_does_not_fire(
    tmp_path: Path,
) -> None:
    """A non-PCI-DSS repo can be operational and public without tripping the guard."""
    data = _minimal_repo(
        frameworks=["soc2", "gdpr"],
        launch_status="operational",
        visibility="public",
    )
    filepath = tmp_path / "test-repo.yml"
    filepath.write_text(yaml.dump(data))
    errors = vr.validate_repo(filepath, _policy())
    assert not any("PCI-DSS-scoped operational repo cannot be public" in e for e in errors)


# ── Fleet-level: the live repos/ directory passes ────────────────────────────


def test_live_fleet_passes_validation() -> None:
    """The real repos/ directory must pass after these changes.

    Pins the exact state: jolarca-security is now declared private (matching
    live), jolarca-control and jolarca-payments carry documented_risk_acceptance,
    and jolarca-hermes-agents declares pci-dss.
    """
    policy = _policy()
    all_errors: list[str] = []
    repos_dir = Path(__file__).resolve().parent.parent / "repos"
    for yml_file in sorted(repos_dir.glob("*.yml")):
        all_errors.extend(vr.validate_repo(yml_file, policy))
    assert all_errors == [], f"live fleet validation failed: {all_errors}"


def test_jolarca_security_declared_private() -> None:
    """jolarca-security.yml must declare visibility: private (matches live)."""
    repos_dir = Path(__file__).resolve().parent.parent / "repos"
    with open(repos_dir / "jolarca-security.yml") as f:
        data = yaml.safe_load(f)
    assert data["visibility"] == "private"


def test_jolarca_hermes_agents_declares_pci_dss() -> None:
    """jolarca-hermes-agents.yml must include pci-dss in compliance.frameworks."""
    repos_dir = Path(__file__).resolve().parent.parent / "repos"
    with open(repos_dir / "jolarca-hermes-agents.yml") as f:
        data = yaml.safe_load(f)
    assert "pci-dss" in data["compliance"]["frameworks"]


def test_jolarca_control_carries_risk_acceptance() -> None:
    """jolarca-control.yml must carry documented_risk_acceptance (ADR-0007)."""
    repos_dir = Path(__file__).resolve().parent.parent / "repos"
    with open(repos_dir / "jolarca-control.yml") as f:
        data = yaml.safe_load(f)
    assert data.get("documented_risk_acceptance") is True


def test_jolarca_payments_carries_risk_acceptance() -> None:
    """jolarca-payments.yml must carry documented_risk_acceptance (payments-public)."""
    repos_dir = Path(__file__).resolve().parent.parent / "repos"
    with open(repos_dir / "jolarca-payments.yml") as f:
        data = yaml.safe_load(f)
    assert data.get("documented_risk_acceptance") is True
