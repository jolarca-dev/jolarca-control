"""Actions pins must be SHA-pinned, labelled, and self-consistent across workflows.

WHY THIS EXISTS
---------------
Measured 2026-10-05 on jolarca-control#34, which bumped `actions/checkout` to
`3d3c42e5aac5ba805825da76410c181273ba90b1`. That commit is v7.0.1. Eleven workflow lines labelled it
`# v4.3.0` -- a comment dependabot did not rewrite -- while `apply.yml:53`, pinning the SAME commit,
labelled it `# v7.0.1`. One commit, two version claims, both in this repository at the same time. The
contradiction is what a reviewer can catch; a *uniformly* wrong label is not, and main's `08c6903cd8c0`
was labelled `# v4.3.0` while actually being v5.0.0 (v4.3.0 is `08eba0b27e82`).

AGENTS.md §5 requires "a full commit SHA with a `# vX.Y.Z` comment". A comment that contradicts its SHA
satisfies the letter and defeats the purpose: the reader trusts a provenance claim that points at a
different release than the code that runs.

WHAT THIS CAN AND CANNOT PROVE
------------------------------
These rules are deliberately offline -- no API calls, no token, deterministic in any environment. They
catch:
  * a tag ref or abbreviated SHA where §5 demands a full SHA with a label,
  * the same (action, commit) carrying two different labels across workflows,
  * the same (action, label) pointing at two different commits.
They cannot catch a label that is wrong in *every* file consistently -- that needs live tag resolution,
which is the recorded follow-up in docs/drift-findings.md D-51. The mixed-label case is not hypothetical
either: it is how this defect was actually noticed.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = REPO_ROOT / ".github" / "workflows"

FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
PIN = re.compile(r"^\s*(?:-\s*)?uses:\s*(?P<ref>[^\s#]+)(?:\s*#\s*(?P<label>\S+))?\s*$")
# `uses: ./` and `uses: ./.github/...` are local/composite refs, not third-party pins.
LOCAL_REF = re.compile(r"^\./")


def _step_uses() -> list[tuple[str, int, str, str | None]]:
    """(workflow, line, ref, label) for every `uses:` in every workflow.

    Read from the raw text, not the parsed YAML: a `uses:` inside a multi-line `run:` block would be
    missed by neither, but a parsed dict loses the line number that makes the finding actionable.
    """
    found: list[tuple[str, int, str, str | None]] = []
    for path in sorted(WORKFLOWS.glob("*.yml")):
        for number, line in enumerate(path.read_text(encoding="utf-8").split("\n"), 1):
            m = PIN.match(line)
            if m:
                found.append((path.name, number, m.group("ref"), m.group("label")))
    return found


def _third_party() -> list[tuple[str, int, str, str, str]]:
    """(workflow, line, action_repo, sha, label) for owner/repo@sha pins."""
    out: list[tuple[str, int, str, str, str]] = []
    for fname, number, ref, label in _step_uses():
        if LOCAL_REF.match(ref):
            continue
        repo, _, sha = ref.partition("@")
        out.append((fname, number, repo, sha, label or ""))
    return out


def test_every_third_party_action_is_pinned_to_a_full_sha_with_a_label() -> None:
    """§5: no tag refs, no 7-character refs, no unlabelled SHAs."""
    offenders: list[str] = []
    for fname, number, repo, sha, label in _third_party():
        if not FULL_SHA.match(sha):
            offenders.append(f"{fname}:{number} {repo}@{sha} is not a full 40-char SHA")
        elif not label:
            offenders.append(f"{fname}:{number} {repo}@{sha[:12]} has no `# vX.Y.Z` comment")
    assert not offenders, "pin discipline violated:\n  " + "\n  ".join(offenders)


def test_a_commit_never_carries_two_version_labels() -> None:
    """The defect actually observed: one commit, labelled two different ways in one repo."""
    seen: dict[tuple[str, str], set[str]] = {}
    where: dict[tuple[str, str], list[str]] = {}
    for fname, number, repo, sha, label in _third_party():
        if label:
            seen.setdefault((repo, sha), set()).add(label)
            where.setdefault((repo, sha), []).append(f"{fname}:{number}")
    bad = [
        f"{repo}@{sha[:12]} labelled {sorted(labels)} at {locs}"
        for (repo, sha), labels in sorted(seen.items())
        if len(labels) > 1
        for locs in [where[(repo, sha)]]
    ]
    assert not bad, "same commit, conflicting version claims:\n  " + "\n  ".join(bad)


def test_a_version_label_never_points_at_two_commits() -> None:
    """The mirror image: vX.Y.Z must name one commit, or the label means nothing."""
    seen: dict[tuple[str, str], set[str]] = {}
    for _fname, _number, repo, sha, label in _third_party():
        if label:
            seen.setdefault((repo, label), set()).add(sha)
    bad = [
        f"{repo} {label} -> {sorted(s[:12] for s in shas)}"
        for (repo, label), shas in sorted(seen.items())
        if len(shas) > 1
    ]
    assert not bad, "one version claimed for multiple commits:\n  " + "\n  ".join(bad)


def test_the_yaml_also_parses_and_the_rules_see_real_pins() -> None:
    """Non-vacuity: if nothing parsed, the three rules above are free passes."""
    uses = _step_uses()
    assert len(uses) >= 15, (
        f"parsed only {len(uses)} uses: refs -- the scan is not seeing the workflows"
    )
    repos = {repo for _f, _n, repo, _s, _l in _third_party()}
    assert "actions/checkout" in repos, sorted(repos)
    for path in sorted(WORKFLOWS.glob("*.yml")):
        doc: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert isinstance(doc, dict) and doc.get("jobs"), (
            f"{path.name} does not parse to a workflow"
        )
