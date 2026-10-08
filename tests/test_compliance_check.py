"""Regression tests for scripts/compliance_check.py.

A-08 (2026-10-08): policy/compliance-gates.yml declares the `sast` gate as
mandatory for every tier, but until this session nothing verified that a
repo's branch protection actually required a SAST context. An untested
regex gate is a hypothesis (D-22); this file is the hypothesis becoming a
control.

Scope: `check_sast_gate_wiring` is the A-08 addition. The other
check_* functions have been live for months and are covered by their own
behavioural tests in scripts/ and by the fleet-wide `make compliance`
gate; the tests here specifically pin the wiring invariant the A-08 prompt
asked to enforce:

    if policy says the SAST gate is required for this repo's tier, then
    `SAST (semgrep)` MUST appear in this repo's required status checks.

A PR that removes `SAST (semgrep)` from `repos/jolarca-control.yml` without
also removing `sast` from the tier's required list must fail. A PR that
removes it from BOTH places must fail on the policy-integrity branch (a
mandatory gate that is not required anywhere is folklore, not a control).
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml

# Import the module under test by absolute path so pytest can find it from
# the tests/ directory without an installed package.
_ROOT = Path(__file__).resolve().parent.parent
import sys as _sys  # noqa: E402

_sys.path.insert(0, str(_ROOT / "scripts"))
import compliance_check as cc  # noqa: E402

REAL_GATES: dict[str, Any] = yaml.safe_load(
    (_ROOT / "policy" / "compliance-gates.yml").read_text(encoding="utf-8")
)
REAL_ENFORCEMENT_MATRIX: dict[str, Any] = REAL_GATES.get("enforcement_matrix", {})
REAL_REPO: dict[str, Any] = yaml.safe_load(
    (_ROOT / "repos" / "jolarca-control.yml").read_text(encoding="utf-8")
)


def _repos_with(self_repo: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {cc.SELF_REPO_NAME: self_repo}


def _contexts(self_repo: dict[str, Any]) -> list[str]:
    return (
        ((self_repo.get("branch_protection") or {}).get("main") or {})
        .get("required_status_checks", {})
        .get("contexts", [])
    )


# ── Positive: the real repo config, as it stands after A-08 ───────────────────


def test_real_repo_passes_sast_gate_wiring() -> None:
    """The current `repos/jolarca-control.yml` must satisfy the wiring rule."""
    result = cc.check_sast_gate_wiring(
        _repos_with(REAL_REPO),
        REAL_GATES.get("gates", {}),
        REAL_ENFORCEMENT_MATRIX,
    )
    assert result["status"] == "pass", result
    assert cc.SAST_PRIMARY_CONTEXT in _contexts(REAL_REPO)


def test_sast_required_for_governance_tier_in_matrix() -> None:
    """Policy integrity: the governance tier lists `sast` in required.

    If a future PR drops `sast` from the tier without also amending
    `gates.sast.enforcement`, the wiring check catches the mismatch; if both
    are dropped together the check catches the "mandatory gate is nowhere"
    folklore case below.
    """
    gov = REAL_ENFORCEMENT_MATRIX["governance"]["required"]
    assert "sast" in gov


def test_gate_id_is_semantic_and_not_name_of_the_engine() -> None:
    """gates.sast.id is `codeql-analysis` (historical naming); the enforcement
    is now Semgrep OSS + Bandit + Trivy. A reader must not conclude from the
    id string that CodeQL is running. Pinned here because the drift is
    invisible in the gate name."""
    gate = REAL_GATES["gates"]["sast"]
    assert gate["id"] == "codeql-analysis"
    assert gate["enforcement"] == "mandatory"
    # The engine actually wired is the Semgrep context, not a CodeQL one:
    assert cc.SAST_PRIMARY_CONTEXT in _contexts(REAL_REPO)
    assert "CodeQL" not in cc.SAST_PRIMARY_CONTEXT


# ── Negative controls: the class of drift the check exists to catch ────────────


def test_removing_sast_context_from_repo_is_a_finding() -> None:
    """The exact A-08 defect: policy requires sast, repo does not wire it."""
    drifted = copy.deepcopy(REAL_REPO)
    contexts = _contexts(drifted)
    contexts.remove(cc.SAST_PRIMARY_CONTEXT)
    drifted["branch_protection"]["main"]["required_status_checks"]["contexts"] = contexts

    result = cc.check_sast_gate_wiring(
        _repos_with(drifted),
        REAL_GATES.get("gates", {}),
        REAL_ENFORCEMENT_MATRIX,
    )
    assert result["status"] == "fail"
    assert any(
        cc.SAST_PRIMARY_CONTEXT in v and "does not include" in v for v in result["violations"]
    ), result["violations"]


def test_folklore_gate_declaration_covering_no_path_is_a_finding() -> None:
    """A PR that removes `sast` from BOTH the tier's required list AND the
    gate's own `enforcement` string leaves a `gates.sast` entry that is not
    required anywhere. That is the "control described but not enforced"
    folklore class (AGENTS.md §7, D-22) — the check MUST fire.

    Removing `sast` from the matrix alone is not enough to trigger this
    branch: `gates.sast.enforcement: mandatory` still covers the repo. Removing
    it from both is a separate policy decision that would need its own ADR
    per RB-04, and the check should loudly object."""
    matrix_no_sast = copy.deepcopy(REAL_ENFORCEMENT_MATRIX)
    required = list(matrix_no_sast["governance"]["required"])
    required.remove("sast")
    matrix_no_sast["governance"]["required"] = required

    gates_no_mandatory = copy.deepcopy(REAL_GATES.get("gates", {}))
    gates_no_mandatory["sast"] = {**gates_no_mandatory["sast"], "enforcement": "informational"}

    result = cc.check_sast_gate_wiring(
        _repos_with(REAL_REPO),
        gates_no_mandatory,
        matrix_no_sast,
    )
    assert result["status"] == "fail"
    assert any("folklore" in v for v in result["violations"]), result["violations"]


def test_missing_self_repo_is_a_finding_not_silent_pass() -> None:
    """Non-vacuity guard. If `repos/jolarca-control.yml` disappears from the
    load, the check must fail loudly, not return an empty pass."""
    result = cc.check_sast_gate_wiring({}, REAL_GATES.get("gates", {}), REAL_ENFORCEMENT_MATRIX)
    assert result["status"] == "fail"
    assert any("missing" in v.lower() for v in result["violations"]), result["violations"]


def test_missing_tier_declaration_is_a_finding() -> None:
    """A repo defn that does not name its tier cannot be evaluated against
    the enforcement matrix; fail loud rather than pass vacuously."""
    drifted = copy.deepcopy(REAL_REPO)
    del drifted["tier"]
    result = cc.check_sast_gate_wiring(
        _repos_with(drifted),
        REAL_GATES.get("gates", {}),
        REAL_ENFORCEMENT_MATRIX,
    )
    assert result["status"] == "fail"
    assert any("tier" in v for v in result["violations"]), result["violations"]


def test_mandatory_for_tier_string_is_parsed_not_ignored() -> None:
    """The gate can be spelled `mandatory_for_tier:governance,devops`.
    A check that only recognised the literal `mandatory` would silently miss
    this spelling. Pinned here."""
    gates = {"sast": {"enforcement": "mandatory_for_tier:governance,devops"}}
    # Enforcement matrix omits `sast` for governance — the gate's own
    # mandatory_for_tier string covers it.
    matrix = {"governance": {"required": [], "optional": []}}
    # Real repo has SAST context wired, so this MUST pass.
    result = cc.check_sast_gate_wiring(_repos_with(REAL_REPO), gates, matrix)
    assert result["status"] == "pass", result


def test_primary_context_string_is_the_exact_gha_job_name() -> None:
    """`SAST (semgrep)` must match the workflow's `jobs.semgrep.name:` byte
    for byte. A typo in either place makes the required context unsatisfiable
    under strict:true, which is exactly the D-44 class check_declared_contexts
    catches elsewhere. Pinned here as a redundant guard."""
    workflow = yaml.safe_load(
        (_ROOT / ".github" / "workflows" / "sast.yml").read_text(encoding="utf-8")
    )
    semgrep_job = workflow["jobs"]["semgrep"]
    assert semgrep_job["name"] == cc.SAST_PRIMARY_CONTEXT


# ── Wiring assertion: the script must actually call the new check ─────────────


def test_sast_gate_wiring_is_invoked_in_main() -> None:
    """A function that is not called is a hypothesis about a control. Pinned
    by reading main's call graph from source. The alternative is that
    compliance_check.py keeps passing while sast_gate_wiring is dead code."""
    src = (_ROOT / "scripts" / "compliance_check.py").read_text(encoding="utf-8")
    assert "check_sast_gate_wiring(repos" in src, "the check is defined but not invoked"
