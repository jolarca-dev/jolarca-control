"""Regression tests for scripts/check_findings_register.py.

WHY THIS EXISTS
---------------
AGENTS.md §7 ("verify the verifier") makes this mandatory: a gate that reports
green has not been shown to detect anything. Every test below drives a fixture
that MUST fail on the collision case, not just "look at the code and agree".

The class of defect is documented in D-22 (an inert regex in a workflow) and in the
2026-10-07 A-02 finding: PR #41 and main simultaneously introduced different `### D-52`
headings, and nothing anywhere would have caught the merge producing two D-52 records.
The last test in this file is the wiring guard -- same shape as
`test_ci_gates_are_real.py` for the pytest step -- because a check no workflow runs
is folklore, not a control.
"""

from __future__ import annotations

import importlib.util
import io
import sys
from pathlib import Path
from typing import Any

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "check_findings_register.py"
ROOT = Path(__file__).resolve().parent.parent


def _load() -> Any:
    spec = importlib.util.spec_from_file_location("check_findings_register", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_findings_register"] = module
    spec.loader.exec_module(module)
    return module


cfr = _load()

# Two distinct D-52 headings that were the real A-02 collision shape: same ID,
# different titles, from main and PR #41 respectively.
MAIN_D52 = "### D-52 · Privating a governed fleet repo blinds the control plane — D-31 remains OPEN/blocking\n"
PR41_D52 = (
    '### D-52 · `apply.yml` claims "a manual approval gate"; '
    "`environment: production` has zero protection rules — OPEN\n"
)
LEGIT_D53 = '### D-53 · `apply.yml` claims "a manual approval gate" — OPEN\n'


def test_parse_headings_splits_id_and_title_before_first_em_dash() -> None:
    """Titles are the segment before the first ` — `, so status annotations do not affect matching."""
    parsed = cfr.parse_headings(MAIN_D52)
    assert parsed == [
        ("D-52", "Privating a governed fleet repo blinds the control plane"),
    ], parsed


def test_parse_headings_accepts_double_hyphen_as_separator() -> None:
    """Older prose in the register uses ` -- ` as the em-dash substitute; must not be treated as title text."""
    line = '### D-31 · "Accept public" is not implementable -- the four repos hold live regulated records\n'
    parsed = cfr.parse_headings(line)
    assert parsed == [("D-31", '"Accept public" is not implementable')], parsed


def test_intra_file_duplicate_is_a_finding() -> None:
    """The A-02 merge shape: same D-nn appearing twice in one register copy."""
    text = MAIN_D52 + PR41_D52
    findings = cfr.find_intra_duplicates(cfr.parse_headings(text))
    assert [f["id"] for f in findings] == ["D-52"], findings
    assert findings[0]["scope"] == "intra-file"


def test_cross_source_same_title_is_not_a_collision() -> None:
    """A PR branch inherits main's heading unchanged -- identical title is expected, not a conflict."""
    sources = {
        "main": cfr.parse_headings(MAIN_D52),
        "PR #45 (fix/doc)": cfr.parse_headings(MAIN_D52),
    }
    assert cfr.check_cross_source(sources) == []


def test_cross_source_different_titles_is_a_collision() -> None:
    """main and PR #41 both claiming D-52 with different titles -- the exact A-02 defect."""
    sources = {
        "main": cfr.parse_headings(MAIN_D52),
        "PR #41 (feat/deploy-gate-check)": cfr.parse_headings(PR41_D52),
    }
    findings = cfr.check_cross_source(sources)
    assert [f["id"] for f in findings] == ["D-52"], findings
    conflict = findings[0]["conflict"]
    labels = {c["source"] for c in conflict}
    assert labels == {"main", "PR #41 (feat/deploy-gate-check)"}


def test_renumbered_collision_closes(monkeypatch: Any, tmp_path: Path) -> None:
    """Positive control: the fix that closed A-02 (branch renames D-52 -> D-53) yields exit 0."""
    fixed = tmp_path / "docs"
    fixed.mkdir()
    (fixed / "drift-findings.md").write_text(
        MAIN_D52 + LEGIT_D53,
        encoding="utf-8",
    )
    monkeypatch.setattr(cfr, "REGISTER_PATH", fixed / "drift-findings.md")
    rc = cfr.main([])
    assert rc == 0, rc


def test_duplicate_ids_on_working_copy_exit_one(monkeypatch: Any, tmp_path: Path) -> None:
    """Negative control: intra-file collision in the working copy must exit 1 (findings, real refusal)."""
    bad = tmp_path / "docs"
    bad.mkdir()
    (bad / "drift-findings.md").write_text(MAIN_D52 + PR41_D52, encoding="utf-8")
    monkeypatch.setattr(cfr, "REGISTER_PATH", bad / "drift-findings.md")
    err = io.StringIO()
    old = sys.stderr
    sys.stderr = err
    try:
        rc = cfr.main([])
    finally:
        sys.stderr = old
    assert rc == 1, rc
    assert "COLLISION D-52" in err.getvalue(), err.getvalue()


def test_missing_register_is_could_not_verify_not_pass(monkeypatch: Any, tmp_path: Path) -> None:
    """AGENTS.md §3: an unreadable input is exit 2, never a silent pass."""
    monkeypatch.setattr(cfr, "REGISTER_PATH", tmp_path / "no-such-file.md")
    rc = cfr.main([])
    assert rc == 2, rc


def test_zero_headings_parse_is_could_not_verify(monkeypatch: Any, tmp_path: Path) -> None:
    """Non-vacuity: a parse that returns 0 headings on a supposedly-populated register must fail loudly.

    The register is not allowed to be "verified clean" if the reader found nothing -- a
    silent rename of the heading pattern (e.g. dropping the space around `·`) would
    otherwise look like a green check while detecting zero findings.
    """
    empty = tmp_path / "docs"
    empty.mkdir()
    (empty / "drift-findings.md").write_text("# nothing here\n", encoding="utf-8")
    monkeypatch.setattr(cfr, "REGISTER_PATH", empty / "drift-findings.md")
    rc = cfr.main([])
    assert rc == 2, rc


def test_main_real_register_is_clean() -> None:
    """Positive control against the actual register file: as of 2026-10-07 main has
    no intra-file collision and is expected to stay that way. If this test ever
    fails, someone landed a duplicate heading without renumbering -- which is the
    whole reason this script exists."""
    text = (ROOT / "docs" / "drift-findings.md").read_text(encoding="utf-8")
    headings = cfr.parse_headings(text)
    assert len(headings) > 30, f"expected dozens of D-nn headings, saw {len(headings)}"
    assert cfr.find_intra_duplicates(headings) == [], cfr.find_intra_duplicates(headings)


def test_script_is_wired_into_a_workflow() -> None:
    """The whole point: a detection that no pipeline runs is folklore (D-22)."""
    hit = [
        p.name
        for p in (ROOT / ".github" / "workflows").glob("*.yml")
        if "check_findings_register.py" in p.read_text(encoding="utf-8", errors="ignore")
    ]
    assert hit, (
        "scripts/check_findings_register.py is invoked by no workflow; "
        "the check would only run when someone remembers to type `make findings-check`"
    )
