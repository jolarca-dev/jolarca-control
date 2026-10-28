"""Guard the merge driver in .gitattributes by checking what it can silently break.

`CHANGELOG.md merge=union` exists because every PR inserts its section at the same anchor
("## [Unreleased]") and the resolution is always "keep both". Union is the right driver for an
append-only-at-anchor file, but it never conflicts: measured in a scratch clone, two branches that
edit the *same* line merge to exit 0 with **two** `## [Unreleased]` headings. That is the one failure
mode this file turns red, because a changelog with a duplicated anchor is a changelog whose history a
reader cannot trust -- and section 6 forbids publishing a record that quietly stopped being true.
"""

from __future__ import annotations

import pathlib
import re

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
CHANGELOG = REPO_ROOT / "CHANGELOG.md"
GITATTRIBUTES = REPO_ROOT / ".gitattributes"
ANCHOR = "## [Unreleased]"


def _changelog_text() -> str:
    return CHANGELOG.read_text(encoding="utf-8")


def test_changelog_has_exactly_one_unreleased_anchor() -> None:
    """The union driver's silent failure: both sides edited the anchor line, both copies landed."""
    occurrences = [ln for ln in _changelog_text().splitlines() if ln.strip() == ANCHOR]
    assert len(occurrences) == 1, (
        f"CHANGELOG.md must carry exactly one {ANCHOR!r} heading, found {len(occurrences)}. "
        "A duplicated anchor means two branches changed the same line and `merge=union` kept both "
        "copies without ever reporting a conflict; collapse them by hand."
    )


def test_anchor_precedes_every_released_version_section() -> None:
    """The anchor is where PRs insert; if a version heading came first, their entries would strand.

    The file legitimately opens with an H1 (`# Changelog`) and prose, so the assertion is about the
    first H2 -- not the first heading of any level, which is the wrong expectation this test was
    originally written with and which failed against the real file on its first run.
    """
    lines = _changelog_text().splitlines()
    h2 = [i for i, ln in enumerate(lines) if ln.startswith("## ")]
    assert h2, "CHANGELOG.md has no H2 section at all"
    assert lines[h2[0]].strip() == ANCHOR, (
        f"the first H2 must be {ANCHOR!r}, got {lines[h2[0]]!r}; every PR inserts its section at the "
        "anchor, so an anchor that is not first strands the entries already merged"
    )


def test_sections_are_not_duplicated_by_a_merge() -> None:
    """A union merge that kept both sides of a *reworded* section leaves two identical headings."""
    headings = [ln.strip() for ln in _changelog_text().splitlines() if ln.startswith("### ")]
    dupes = sorted({h for h in headings if headings.count(h) > 1})
    assert not dupes, f"duplicated section headings in CHANGELOG.md: {dupes}"


def test_union_driver_and_this_guard_are_declared_together() -> None:
    """The pairing is the point: the driver without the guard is a silent-corruption switch.

    Removing `merge=union` re-exposes the loud conflict, which is safe. Removing this file while the
    driver stays converts every future same-line collision into a silent duplicate. Only the second
    direction is worth failing a build over, so that is the only direction asserted here.
    """
    attrs = GITATTRIBUTES.read_text(encoding="utf-8")
    union_declared = bool(re.search(r"^CHANGELOG\.md\s+merge=union\s*$", attrs, re.M))
    if not union_declared:
        raise AssertionError(
            ".gitattributes no longer declares `CHANGELOG.md merge=union`, but this guard file still "
            "exists. If dropping the driver is deliberate, delete this file too -- a guard for an absent "
            "driver misleads the next reader into thinking anchor collisions are still handled."
        )
