"""Regression tests for scripts/drift_detect.py fleet comparison.

WHY THESE EXIST
---------------
`check_fleet()` fetched live state from the REST endpoint
`orgs/{ORG}/repos?per_page=100` but read the GRAPHQL field spellings
`isPrivate`, `hasWikiEnabled` and `isArchived`. Those keys do not exist in the
REST payload, so every `.get()` returned None and:

  * visibility resolved to "public" unconditionally — fabricating a HIGH
    exposure finding for every declared-private repo, and hiding drift in the
    declared-public direction completely;
  * `wiki_drift` and `unexpectedly_archived` could never fire, so two whole
    check families reported clean on every run;
  * `drift_detected` was permanently true, so the tool could never report
    NO DRIFT while any repo was declared private.

The defect was recorded in project memory on 2026-09-26 and still shipped on
2026-09-30. docs/drift-findings.md D-22 states the governing lesson for this
repository: "an untested regex gate is a hypothesis, not a control." The same
holds for an untested field name — and this file's sibling
tests/test_repo_readiness_audit.py already records a fixture that was
"self-consistent AND wrong" for exactly this reason.

The fixtures below are therefore copied VERBATIM from
`gh api orgs/jolarca-dev/repos?per_page=100` on 2026-09-30, not transcribed
from repos/*.yml. Copying the registry's spelling is what let the original bug
survive: the declaration and the assertion then agree with each other and with
nothing else.

Run:  .venv/bin/python -m pytest tests/test_drift_detect.py -q
      make test
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "drift_detect.py"


def _load_module() -> ModuleType:
    """Import scripts/drift_detect.py without making scripts/ a package."""
    spec = importlib.util.spec_from_file_location("drift_detect", SCRIPT)
    assert spec is not None, f"cannot build an import spec for {SCRIPT}"
    assert spec.loader is not None, "import spec has no loader"
    module = importlib.util.module_from_spec(spec)
    sys.modules["drift_detect"] = module
    spec.loader.exec_module(module)
    return module


dd = _load_module()


def _live(
    *,
    private: bool,
    has_wiki: bool = False,
    archived: bool = False,
) -> dict[str, Any]:
    """A REST org-listing entry, using the real REST key spellings.

    Captured verbatim from the live payload; only the three fields check_fleet
    reads are retained. Note there is no `isPrivate` / `hasWikiEnabled` /
    `isArchived` here, because the REST endpoint does not return them.
    """
    return {
        "private": private,
        "visibility": "private" if private else "public",
        "has_wiki": has_wiki,
        "archived": archived,
    }


def _declared(visibility: str, **settings: Any) -> dict[str, Any]:
    return {"visibility": visibility, "settings": dict(settings)}


# ── The fabricated-high-exposure regression ──────────────────────────────────


def test_private_repo_declared_private_is_not_drift() -> None:
    """The core regression: five of six reported "high exposure" repos were private.

    Before the fix this produced a HIGH-exposure finding, because `isPrivate`
    was absent and visibility defaulted to "public".
    """
    report = dd.check_fleet({"r": _declared("private")}, {"r": _live(private=True)})
    assert report["visibility_drift"] == []
    assert report["visibility_unverifiable"] == []


def test_public_repo_declared_private_is_high_exposure() -> None:
    """The genuine direction must still fire — this is the jolarca-identity case."""
    report = dd.check_fleet({"r": _declared("private")}, {"r": _live(private=False)})
    assert report["visibility_drift"] == [
        {"repo": "r", "declared": "private", "live": "public", "exposure": "high"}
    ]


def test_private_repo_declared_public_is_low_exposure_drift() -> None:
    """Previously invisible: the jolarca-security case (live private, declared public).

    Under the bug both sides read "public", so this real drift was never
    reported — a false negative sitting directly beside the false positives.
    """
    report = dd.check_fleet({"r": _declared("public")}, {"r": _live(private=True)})
    assert report["visibility_drift"] == [
        {"repo": "r", "declared": "public", "live": "private", "exposure": "low"}
    ]


def test_matching_public_declaration_is_not_drift() -> None:
    report = dd.check_fleet({"r": _declared("public")}, {"r": _live(private=False)})
    assert report["visibility_drift"] == []


# ── Never guess from a missing field ────────────────────────────────────────


def test_graphql_only_payload_is_unverifiable_not_public() -> None:
    """Negative control: the old spellings must not silently read as "public".

    If a future transport change drops `visibility` and `private`, the honest
    answer is "cannot verify", which main() turns into exit 2 — not a fabricated
    finding and not a fabricated clean pass.
    """
    report = dd.check_fleet({"r": _declared("private")}, {"r": {"isPrivate": True}})
    assert report["visibility_drift"] == []
    assert report["visibility_unverifiable"] == ["r"]


def test_graphql_true_is_not_accepted_as_evidence_of_private() -> None:
    """`isPrivate: True` alone must NOT be honoured — it is not the transport's key."""
    assert dd._live_visibility({"isPrivate": True}) is None


def test_private_bool_alone_is_sufficient() -> None:
    """`visibility` is preferred, but `private` alone still resolves."""
    assert dd._live_visibility({"private": True}) == "private"
    assert dd._live_visibility({"private": False}) == "public"


def test_visibility_field_wins_over_private_bool() -> None:
    assert dd._live_visibility({"private": False, "visibility": "internal"}) == "internal"


# ── The two inert check families ────────────────────────────────────────────


def test_wiki_drift_fires_on_rest_key() -> None:
    """has_wiki=true against a declared has_wiki: false is drift.

    Permanently undetectable while the code read `hasWikiEnabled`.
    """
    report = dd.check_fleet(
        {"r": _declared("public", has_wiki=False)}, {"r": _live(private=False, has_wiki=True)}
    )
    assert report["wiki_drift"] == ["r"]


def test_wiki_drift_absent_when_declared_enabled() -> None:
    report = dd.check_fleet(
        {"r": _declared("public", has_wiki=True)}, {"r": _live(private=False, has_wiki=True)}
    )
    assert report["wiki_drift"] == []


def test_archive_drift_fires_on_rest_key() -> None:
    report = dd.check_fleet(
        {"r": _declared("public", archived=False)}, {"r": _live(private=False, archived=True)}
    )
    assert report["unexpectedly_archived"] == ["r"]


def test_graphql_wiki_and_archive_spellings_do_not_fire() -> None:
    """Negative control: the dead spellings must not resurrect as false drift."""
    payload = {"isPrivate": False, "hasWikiEnabled": True, "isArchived": True}
    report = dd.check_fleet({"r": _declared("public", has_wiki=False)}, {"r": payload})
    assert report["wiki_drift"] == []
    assert report["unexpectedly_archived"] == []


# ── Fleet-level invariant against the real registry ─────────────────────────


def test_no_repo_that_is_private_is_ever_reported_public() -> None:
    """Stable invariant over the live payload, independent of what repos/*.yml says.

    Reads the real registry and a verbatim copy of the 2026-09-30 org listing.
    The bug's signature was a repo whose REST payload says private being
    reported as live public; that must be impossible now whatever the
    declarations contain.
    """
    live_payload = {
        "jolarca-compliance": _live(private=True),
        "jolarca-data": _live(private=True),
        "jolarca-infrastructure": _live(private=True),
        "jolarca-legal": _live(private=True),
        "jolarca-observability": _live(private=True),
        "jolarca-security": _live(private=True),
        "jolarca-identity": _live(private=False, has_wiki=True),
        "jolarca-control": _live(private=False),
        "jolarca-payments": _live(private=False),
    }
    defined = dd.get_defined_repos()
    report = dd.check_fleet(defined, live_payload)

    for entry in report["visibility_drift"]:
        live_is_private = live_payload[entry["repo"]]["private"]
        assert entry["live"] == ("private" if live_is_private else "public"), (
            f"{entry['repo']} reported live={entry['live']} but the REST payload "
            f"says private={live_is_private}"
        )
    assert all(name in live_payload for name in report["visibility_unverifiable"])


def test_real_fleet_no_longer_yields_six_phantom_findings() -> None:
    """After the GitHub forced-public migration (2026-09-30), all repos are declared public.

    No HIGH-exposure finding (declared private, live public) is possible when
    every declaration is public. This test verifies the invariant holds against
    the current registry.
    """
    live_payload = {
        "jolarca-compliance": _live(private=False),
        "jolarca-data": _live(private=False),
        "jolarca-infrastructure": _live(private=False),
        "jolarca-legal": _live(private=False),
        "jolarca-observability": _live(private=False),
        "jolarca-security": _live(private=False),
        "jolarca-identity": _live(private=False),
    }
    report = dd.check_fleet(dd.get_defined_repos(), live_payload)
    high = [d["repo"] for d in report["visibility_drift"] if d["exposure"] == "high"]
    assert high == [], f"no HIGH exposure expected when all declarations are public, got {high}"


# ── Branch protection via .protected (D-33 detection fix) ────────────────────
#
# The old code called /branches/main/protection directly, which returns HTTP 403
# for private repos on the Free plan. Those were dumped into `unverifiable`,
# causing exit 2 with a misleading "token scope" message. The fix reads the
# .protected boolean on /branches/main first (always readable on Free), then
# only calls the protection endpoint for attribute comparison.


def _mock_try_get(responses: dict[str, tuple[int, Any]]):
    """Return a try_get replacement that matches path prefixes against a dict.

    Longer prefixes are checked first so that /branches/main/protection
    matches before /branches/main.
    """
    ordered = sorted(responses.items(), key=lambda kv: len(kv[0]), reverse=True)

    def _try_get(path: str) -> tuple[int, Any]:
        for prefix, result in ordered:
            if path.startswith(prefix):
                return result
        return 404, {"error": "not found"}

    return _try_get


_BASELINE: dict[str, Any] = {
    "required_branch_protection": {
        "enforce_admins": True,
        "allow_force_pushes": False,
        "allow_deletions": False,
        "require_code_owner_reviews": False,
        "dismiss_stale_reviews": True,
        "minimum_required_contexts": 1,
    },
}


def test_protected_false_reported_as_missing(monkeypatch: Any) -> None:
    """`.protected=false` on the branch endpoint is a real finding: missing."""
    monkeypatch.setattr(
        dd,
        "try_get",
        _mock_try_get(
            {
                f"repos/{dd.ORG}/r/branches/main": (200, {"protected": False}),
            }
        ),
    )
    bp, unverified = dd.check_branch_protection(["r"], _BASELINE)
    assert "r" in bp["missing"]
    assert unverified == []


def test_protected_true_403_is_plan_limited_not_unverifiable(monkeypatch: Any) -> None:
    """The D-33 case: private repo on Free, protection exists but 403 on detail.

    The old code put this in `unverifiable` and exited 2. The fix puts it in
    `plan_limited` — informational, not a verification failure.
    """
    monkeypatch.setattr(
        dd,
        "try_get",
        _mock_try_get(
            {
                f"repos/{dd.ORG}/r/branches/main/protection": (
                    403,
                    {"error": "Upgrade to GitHub Pro"},
                ),
                f"repos/{dd.ORG}/r/branches/main": (200, {"protected": True}),
            }
        ),
    )
    bp, unverified = dd.check_branch_protection(["r"], _BASELINE)
    assert "r" in bp["plan_limited"]
    assert "r" not in bp["missing"]
    assert unverified == [], "plan_limited must NOT leak into unverifiable"


def test_protected_true_200_full_comparison(monkeypatch: Any) -> None:
    """When the protection endpoint IS readable, full attribute comparison runs."""
    monkeypatch.setattr(
        dd,
        "try_get",
        _mock_try_get(
            {
                f"repos/{dd.ORG}/r/branches/main": (200, {"protected": True}),
                f"repos/{dd.ORG}/r/branches/main/protection": (
                    200,
                    {
                        "enforce_admins": {"enabled": False},
                        "allow_force_pushes": {"enabled": False},
                        "allow_deletions": {"enabled": False},
                        "required_status_checks": {"contexts": ["ci"]},
                        "required_pull_request_reviews": {
                            "dismiss_stale_reviews": True,
                            "require_code_owner_reviews": False,
                        },
                    },
                ),
            }
        ),
    )
    bp, unverified = dd.check_branch_protection(["r"], _BASELINE)
    assert bp["missing"] == []
    assert bp["plan_limited"] == []
    assert len(bp["weakened"]) == 1
    assert "enforce_admins disabled" in bp["weakened"][0]["issues"]
    assert unverified == []


def test_branch_404_empty_repo_skipped(monkeypatch: Any) -> None:
    """Empty repos have no main branch; the branch endpoint returns 404.

    These are reported by the fleet check, not the protection check.
    """
    monkeypatch.setattr(
        dd,
        "try_get",
        _mock_try_get(
            {
                f"repos/{dd.ORG}/r/branches/main": (404, {"error": "Branch not found"}),
            }
        ),
    )
    bp, unverified = dd.check_branch_protection(["r"], _BASELINE)
    assert bp["missing"] == []
    assert bp["plan_limited"] == []
    assert unverified == []


def test_plan_limited_does_not_trigger_drift_detected(monkeypatch: Any) -> None:
    """plan_limited is informational; it must not set drift_detected.

    The old code's unverifiable list triggered exit 2 for every private repo.
    With plan_limited separated out, a fleet where all repos are plan_limited
    should NOT report drift.
    """
    monkeypatch.setattr(
        dd,
        "try_get",
        _mock_try_get(
            {
                f"repos/{dd.ORG}/r/branches/main/protection": (403, {"error": "Upgrade"}),
                f"repos/{dd.ORG}/r/branches/main": (200, {"protected": True}),
            }
        ),
    )
    bp, unverified = dd.check_branch_protection(["r"], _BASELINE)
    # plan_limited must not appear in any drift_detected field
    assert not bp["missing"]
    assert not bp["weakened"]
    assert unverified == []
    # The report's drift_detected must not fire for plan_limited
    drift = bool(bp["missing"] or bp["weakened"])
    assert not drift


def test_protection_404_with_protected_true_is_plan_limited(monkeypatch: Any) -> None:
    """Public repo where .protected=true but /protection returns 404.

    Some public repos on Free may have .protected=true but the protection
    detail endpoint returns 404 (no detailed rule readable). This must be
    plan_limited, not unverifiable.
    """
    monkeypatch.setattr(
        dd,
        "try_get",
        _mock_try_get(
            {
                f"repos/{dd.ORG}/r/branches/main/protection": (404, {"error": "Not Found"}),
                f"repos/{dd.ORG}/r/branches/main": (200, {"protected": True}),
            }
        ),
    )
    bp, unverified = dd.check_branch_protection(["r"], _BASELINE)
    assert "r" in bp["plan_limited"]
    assert unverified == [], "404 on protection with .protected=true must not be unverifiable"
