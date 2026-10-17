"""Regression tests for scripts/check_deploy_gates.py.

WHY THIS EXISTS
---------------
Every environment this organisation references is unprotected, measured 2026-10-05 from the live API:

    jolarca-control/production            rules=[]              can_admins_bypass=True
    jolarca/staging                       rules=[]              can_admins_bypass=True
    jolarca-infrastructure/production     rules=[]              can_admins_bypass=True
    jolarca-infrastructure/staging-readonly rules=[]            can_admins_bypass=True
    jolarca-infrastructure/github-pages   rules=[branch_policy] can_admins_bypass=True

`apply.yml` says "Single-stage production apply with a manual approval gate" in its own header comment,
and `environment: production` is what it points at -- an environment with zero protection rules, so
nothing between a merge to main and `terraform apply -auto-approve` is a human. GitHub creates a
referenced-but-missing environment empty, which is why this is structural rather than someone's choice
(D-22: a control nobody's pipeline verifies is folklore).

Fixtures are copied from those live payloads, not invented -- except test_protected_environment_is_clean,
whose `required_reviewers` object shape is inferred from the documented PUT body because NO environment in
this org currently has reviewers, so the green path cannot be observed. That limit is stated in the
script's docstring rather than hidden.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import importlib.util
import io
import sys
from pathlib import Path
from typing import Any

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "check_deploy_gates.py"


def _load() -> Any:
    spec = importlib.util.spec_from_file_location("check_deploy_gates", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_deploy_gates"] = module
    spec.loader.exec_module(module)
    return module


cdg = _load()

# Verbatim shapes from GET /repos/jolarca-dev/jolarca-control/environments/production and the
# jolarca-infrastructure/github-pages equivalent.
PROD_UNPROTECTED = {
    "name": "production",
    "can_admins_bypass": True,
    "protection_rules": [],
    "deployment_branch_policy": None,
}
PAGES_BRANCH_ONLY = {
    "name": "github-pages",
    "can_admins_bypass": True,
    "protection_rules": [{"id": 12345, "type": "branch_policy"}],
    "deployment_branch_policy": {"protected_branches": False, "custom_branch_policies": True},
}
# Inferred from the documented Create-or-update body; see module docstring. Not observed in this org.
PROTECTED = {
    "name": "production",
    "can_admins_bypass": False,
    "protection_rules": [
        {
            "id": 99,
            "type": "required_reviewers",
            "wait_timer": 0,
            "reviewers": [{"type": "User", "id": 1}],
        }
    ],
    "deployment_branch_policy": None,
}


def _evaluate(env: dict[str, Any], name: str = "production") -> list[str]:
    return cdg.assess(f"o/r/{name}", env)


def test_environment_with_no_rules_is_a_finding() -> None:
    assert _evaluate(PROD_UNPROTECTED), (
        "an environment with zero protection rules must be a finding"
    )


def test_admins_bypass_is_a_finding_even_when_a_rule_exists() -> None:
    out = _evaluate(PAGES_BRANCH_ONLY, "github-pages")
    assert out and any("bypass" in line.lower() for line in out), (
        "branch_policy present but admins can bypass: still not a human gate"
    )


def test_protected_environment_is_clean() -> None:
    assert _evaluate(PROTECTED) == []


def test_missing_environment_is_a_finding_not_a_pass() -> None:
    """GitHub creates a referenced environment empty on first run, so 404 means 'no gate', not 'skip'."""
    findings, unverifiable = cdg.classify_missing("o/r/production", status=404)
    assert findings and not unverifiable, (findings, unverifiable)
    assert any("empty" in f.lower() or "404" in f for f in findings)


def test_api_error_is_unverifiable_not_clean() -> None:
    findings, unverifiable = cdg.classify_missing("o/r/production", status=403)
    assert not findings and unverifiable, (findings, unverifiable)


def test_dynamic_environment_name_is_unverifiable() -> None:
    """`environment: ${{ inputs.environment }}` cannot be resolved from the YAML; it must not read as safe."""
    findings, unverifiable, name = cdg.resolve_environment("${{ inputs.environment }}")
    assert not findings and unverifiable and name is None, (findings, unverifiable, name)


def test_static_environment_object_form_is_read() -> None:
    assert cdg.resolve_environment({"name": "production"})[2] == "production"


def test_allow_missing_without_expiry_is_a_finding() -> None:
    """Mirrors check_fleet_separation.sh: an exception with no expiry is how a gap becomes permanent."""
    assert (
        cdg.allowance_error(
            {
                "ALLOW_UNPROTECTED_ENVS": "jolarca-dev/jolarca-control:production",
                "ALLOW_UNPROTECTED_UNTIL": "",
            }
        )
        is not None
    )


def test_allowance_suppresses_until_the_date_and_then_reports() -> None:
    # apply_allowance takes date objects, not the ISO strings the env parser produces from them.
    past = dt.date.today() - dt.timedelta(days=1)
    future = dt.date.today() + dt.timedelta(days=30)
    target = "jolarca-dev/jolarca-control:production"

    kept, notes = cdg.apply_allowance([f"{target}: no protection rules"], {target: future})
    assert kept == [] and len(notes) == 1 and notes[0].startswith("ALLOWED"), (kept, notes)
    assert target in notes[0], notes

    kept2, notes2 = cdg.apply_allowance([f"{target}: no protection rules"], {target: past})
    assert kept2 and any("EXPIRED" in n for n in notes2), (kept2, notes2)


def test_summary_never_claims_gated_when_something_was_allowed() -> None:
    """The wording must expose an exemption, and must not read as a clean bill when nothing was seen.

    Note the shape of the negative assertion: `"all" not in line` would be satisfied by the word
    "allowed", so the check names the overclaim phrasing it actually forbids.
    """
    line = cdg.summary(gated=1, findings=0, allowed=1, unverifiable=0)
    assert "allowed" in line and "0 gated" in line and "1 environment(s) examined" in line, line
    assert "all clean" not in line.lower() and "all gated" not in line.lower(), line

    ok = cdg.summary(gated=2, findings=0, allowed=0, unverifiable=0)
    assert ok.startswith("OK") and "2 gated" in ok, ok

    none = cdg.summary(gated=0, findings=0, allowed=0, unverifiable=0)
    assert "0 environment(s) examined" in none and "0 gated" in none, none

    bad = cdg.summary(gated=1, findings=1, allowed=0, unverifiable=0)
    assert bad.startswith("FAIL") and "1 finding" in bad, bad

    # One environment failing two rules must stay "1 allowed", never the "2 allowed" this replaced.
    one_env_two_rules = cdg.summary(gated=1, findings=0, allowed=1, unverifiable=0)
    assert "1 environment(s) examined" in one_env_two_rules and "1 allowed" in one_env_two_rules, (
        one_env_two_rules
    )
    with pytest.raises(ValueError):
        cdg.summary(gated=1, findings=0, allowed=2, unverifiable=0)


def test_exit_code_contract(monkeypatch: Any) -> None:
    """0 clean, 1 findings, 2 could-not-verify. 2 is never a pass (D-23)."""
    assert cdg.exit_code(findings=[], unverifiable=[]) == 1 - 1
    assert cdg.exit_code(findings=["x"], unverifiable=[]) == 1
    assert cdg.exit_code(findings=["x"], unverifiable=["y"]) == 2
    assert cdg.exit_code(findings=[], unverifiable=["y"]) == 2


def test_no_token_is_unverifiable_not_clean(monkeypatch: Any) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "")
    with contextlib.redirect_stderr(io.StringIO()) as err:
        rc = cdg.main([])
    assert rc == 2, err.getvalue()
    assert "token" in err.getvalue().lower()


def test_script_is_wired_into_a_workflow() -> None:
    """A detection no pipeline runs is folklore (D-22): the guard must be invoked by CI, not just exist."""
    root = Path(__file__).resolve().parent.parent
    hits = [
        p.name
        for p in (root / ".github" / "workflows").glob("*.yml")
        if "check_deploy_gates.py" in p.read_text(encoding="utf-8", errors="ignore")
    ]
    assert hits, "scripts/check_deploy_gates.py is invoked by no workflow"


def test_two_rules_on_one_environment_produce_one_note() -> None:
    """The log must not read as two exempted environments when one environment failed two rules."""
    target = "jolarca-dev/jolarca-control:production"
    future = dt.date.today() + dt.timedelta(days=30)
    kept, notes = cdg.apply_allowance(
        [f"{target}: no protection rule of any kind", f"{target}: can_admins_bypass=True"],
        {target: future},
    )
    assert kept == [] and len(notes) == 1, (kept, notes)
    assert notes[0].startswith("ALLOWED") and target in notes[0], notes


def test_target_of_reads_both_message_shapes() -> None:
    """A finding and an exemption note put the same target in different places in the string."""
    finding = "jolarca-dev/jolarca-control:production: no protection rule of any kind (protection_rules is empty)"
    note = "ALLOWED (expires 2026-10-19): jolarca-dev/jolarca-control:production"
    assert cdg.target_of(finding) == "jolarca-dev/jolarca-control:production", cdg.target_of(
        finding
    )
    assert cdg.target_of(note) == "jolarca-dev/jolarca-control:production", cdg.target_of(note)


def test_summary_counts_environments_not_findings_end_to_end() -> None:
    """Two rules failing on one exempted environment must produce 1 examined / 1 allowed / 0 gated."""
    target = "jolarca-dev/jolarca-control:production"
    future = dt.date.today() + dt.timedelta(days=30)
    messages = [
        f"{target}: no protection rule of any kind",
        f"{target}: can_admins_bypass=True -- the gate is skippable",
    ]
    kept, notes = cdg.apply_allowance(messages, {target: future})
    failing = {cdg.target_of(m) for m in kept}
    exempt = {cdg.target_of(n) for n in notes if n.startswith("ALLOWED")} - failing
    line = cdg.summary(gated=1, findings=len(failing), allowed=len(exempt), unverifiable=0)
    assert kept == [] and exempt == {target} and failing == set(), (kept, notes)
    assert "1 environment(s) examined" in line and "1 allowed" in line, line
    assert "2 allowed" not in line, line


def test_scanner_sees_the_real_deploy_job() -> None:
    """Non-vacuity for the local scan: apply.yml's environment must be found and resolvable.

    `environment:` in that workflow is a mapping (`name: production` plus a `url:`), so the value is
    resolved through the same helper the script uses instead of being compared as a bare string --
    comparing strings here would have passed only if the workflow happened to use the short form.
    """
    root = Path(__file__).resolve().parent.parent
    refs = cdg.local_environment_refs(root / ".github" / "workflows")
    apply_refs = [(job, value) for wf, job, value in refs if wf == "apply.yml"]
    assert apply_refs, refs
    names = [cdg.resolve_environment(value)[2] for _job, value in apply_refs]
    assert "production" in names, names
