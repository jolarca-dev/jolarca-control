"""Regression tests for scripts/check_declared_contexts.py.

WHY THIS EXISTS
---------------
jolarca-control declared jolarca-identity required status checks [ci, security, lint], but that repo's
workflows publish `shellcheck` and `gitleaks (full history)`. None of the three declared names was
producible, so applying the declaration under strict=true would have made every PR there permanently
unmergeable. The check that computes this (repo_readiness_audit.py) exists and DID report it -- but it is
invoked by no workflow, so it only ever ran when someone remembered to type `make readiness`. That is
"an untested regex gate is a hypothesis, not a gate" (D-22) in a different costume: a detection that only
exists in a terminal is folklore.

Fixtures are copied from live payloads (GET /repos/.../contents/.github/workflows and the YAML bodies),
not transcribed from repos/*.yml -- copying the declaration into the assertion is what let the original
REST-versus-GraphQL field-name bug survive.
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import sys
from pathlib import Path
from typing import Any

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "check_declared_contexts.py"


def _load() -> Any:
    spec = importlib.util.spec_from_file_location("check_declared_contexts", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_declared_contexts"] = module
    spec.loader.exec_module(module)
    return module


cdc = _load()

# Verbatim shape of jolarca-identity's workflow today: job keys with `name:` overrides.
IDENTITY_LIVE = """name: CI
on:
  pull_request:
    branches: [main]
jobs:
  secret-scan:
    name: gitleaks (full history)
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262
  lint:
    name: shellcheck
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262
"""

# The shape produced by jolarca-identity#3 (display names removed -> contexts are the job keys).
IDENTITY_RENAMED = IDENTITY_LIVE.replace("    name: gitleaks (full history)\n", "").replace(
    "    name: shellcheck\n", ""
)


def test_contexts_come_from_job_name_else_key() -> None:
    """GitHub names a check after `name:` when present; assuming the key is how this went unnoticed."""
    assert cdc.contexts_from_yaml(IDENTITY_LIVE) == {"shellcheck", "gitleaks (full history)"}
    assert cdc.contexts_from_yaml(IDENTITY_RENAMED) == {"lint", "secret-scan"}


def test_declared_but_unproducible_contexts_are_a_finding() -> None:
    """The live jolarca-identity case, asserted directly."""
    problems = cdc.compare(
        "jolarca-identity", ["ci", "security", "lint"], cdc.contexts_from_yaml(IDENTITY_LIVE)
    )
    assert [p["repo"] for p in problems] == ["jolarca-identity"]
    assert set(problems[0]["unproducible"]) == {"ci", "security", "lint"}
    assert cdc.compare("r", ["lint", "secret-scan"], cdc.contexts_from_yaml(IDENTITY_RENAMED)) == []


def test_unparseable_or_missing_workflow_is_unverifiable_not_clean() -> None:
    """A repo whose workflows could not be read must never read as agreement (D-23)."""
    produced, errors, skipped = cdc.produced_contexts("r", probe=lambda *_: ([], ["boom"], False))
    assert produced == set()
    assert errors == ["boom"]
    assert skipped is False


def test_allow_missing_suppresses_but_reports_and_expires(monkeypatch: Any) -> None:
    """Time-boxed exception, mirroring ALLOW_MISSING/ALLOW_MISSING_UNTIL in fleet-separation-guard."""
    findings = [{"repo": "jolarca-identity", "unproducible": ["ci"]}]
    kept, notes = cdc.apply_allowance(
        findings, {"jolarca-identity"}, dt.date(2026, 11, 15), dt.date(2026, 10, 4)
    )
    assert kept == [] and len(notes) == 1 and "expires 2026-11-15" in notes[0]

    kept, notes = cdc.apply_allowance(
        findings, {"jolarca-identity"}, dt.date(2026, 10, 1), dt.date(2026, 10, 4)
    )
    assert [f["repo"] for f in kept] == ["jolarca-identity"], "an expired allowance must fail again"
    assert any("EXPIRED" in n for n in notes)


def test_exit_code_contract() -> None:
    """0 clean, 1 findings, 2 could-not-verify -- 2 is never a pass (D-23)."""
    assert cdc.exit_code(findings=[], unverifiable=[]) == 0
    assert cdc.exit_code(findings=[{"repo": "r", "unproducible": ["x"]}], unverifiable=[]) == 1
    assert cdc.exit_code(findings=[], unverifiable=["could not read"]) == 2


def test_script_is_wired_into_a_workflow(monkeypatch: Any) -> None:
    """The whole point: a detection that no pipeline runs is folklore.

    Written before the workflow existed, so it starts red on purpose.
    """
    root = Path(__file__).resolve().parent.parent
    hit = [
        p.name
        for p in (root / ".github" / "workflows").glob("*.yml")
        if "check_declared_contexts.py" in p.read_text(encoding="utf-8", errors="ignore")
    ]
    assert hit, (
        "scripts/check_declared_contexts.py is invoked by no workflow; the check would be manual only"
    )


def test_empty_repo_is_skipped_not_unverifiable() -> None:
    """A repo with no commits yet cannot be judged; that is not a verification failure.

    jolarca-observability (size 0, launch_status in-development) and jolarca-runbooks (size 0, planned)
    are the live cases. Folding them into `unverifiable` would make the weekly job permanently red for a
    reason nobody can fix, which is how real findings get their colour drained out.
    """
    # The real probe returns no error text for an empty repo: emptiness is answered, not unverified.
    empty = [], [], True
    produced, errors, skipped = cdc.produced_contexts("r", probe=lambda *_: empty)
    assert (produced, errors, skipped) == (set(), [], True)

    # A different failure must NOT be laundered into "skipped".
    forbidden = [], ["gh: Must have admin rights (HTTP 403)"], False
    produced, errors, skipped = cdc.produced_contexts("r", probe=lambda *_: forbidden)
    assert skipped is False
    assert errors == ["gh: Must have admin rights (HTTP 403)"]
    assert cdc.exit_code(findings=[], unverifiable=errors) == 2


def test_skipped_repo_becomes_a_finding_once_it_has_content() -> None:
    """The skip is conditional on emptiness, so the first push re-enables the check automatically."""
    bodies = ["name: CI\njobs:\n  lint:\n    runs-on: ubuntu-latest\n"], [], False
    produced, errors, skipped = cdc.produced_contexts("r", probe=lambda *_: bodies)
    assert (produced, errors, skipped) == ({"lint"}, [], False)
    assert cdc.compare("r", ["ci"], produced), "a now-non-empty repo must be judged again"
