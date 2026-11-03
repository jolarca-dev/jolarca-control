#!/usr/bin/env python3
"""check_findings_register.py -- every `### D-nn` heading in the register must be unique.

Why this exists
---------------
`docs/drift-findings.md` is the authoritative D-series register. Its finding IDs are
referenced from SECURITY.md, `audit/*.yml`, `docs/threat-model.md`, `policy/**`,
`repos/*.yml` `# related D-nn` comments, and Terraform rationale blocks. A duplicated
ID silently corrupts every one of those cross-references -- the register no longer
names one thing per symbol.

The defect this guards against was measured live on 2026-10-07 (audit A-02). PR #41
introduced `### D-52 · apply.yml claims "a manual approval gate"` on its branch while
main simultaneously landed a different `### D-52 · Privating a governed fleet repo`
(commit `0a90135`, D-31 remediation). The branch's merge-base was older than main's
D-52, so nothing on the branch's CI flagged the collision -- the merge would have
produced two D-52 sections in the same file, referring to different defects. The
register at that moment was the source of truth for a SOC 2 / ISO 27001 audit
surface, and it was about to lie.

Detection scope
---------------
1) **Intra-file** -- same `D-nn` heading appearing twice in `docs/drift-findings.md`.
2) **Cross-PR** (CI only, needs `gh` + `pull-requests: read`) -- same `D-nn` used
   with a different *title* on `main` and/or on another open PR branch. Titles are
   compared, not full heading lines, so legitimate status annotations (
   `— **OPEN**` -> `— **FIXED**`) do not read as collisions. A real rename of a
   finding's subject must allocate a new D-nn and cross-reference the old one from
   the register body -- this is the same rule AGENTS.md §6 enforces on documentation.

Exit-code contract (AGENTS.md §3)
---------------------------------
0 clean, 1 collision detected, 2 could-not-verify. 2 is never a pass (D-23).
"""

from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
REGISTER_PATH = ROOT / "docs" / "drift-findings.md"

# Heading form: `### D-<digits> · <title>[ — <status or sub-title>]`
# Em dash is U+2014 (—). Two-hyphen (--) is also accepted for older prose.
HEADING_RE = re.compile(r"^###\s+(D-\d+)\s+·\s+(.+?)\s*$")
TITLE_SPLIT = re.compile(r"\s+(?:—|--)\s+")

# Register file path used for cross-branch fetches. Kept as a literal string so a
# rename of the register file cannot silently disable the cross-PR check.
REGISTER_REF_PATH = "docs/drift-findings.md"


def parse_headings(text: str) -> list[tuple[str, str]]:
    """Extract `(id, title)` for every `### D-nn · <title>` heading.

    `title` is the segment before the first em-dash separator, so status annotations
    do not affect collision detection. A heading with no separator contributes the
    whole remainder as the title.
    """
    out: list[tuple[str, str]] = []
    for raw in text.splitlines():
        m = HEADING_RE.match(raw.rstrip())
        if not m:
            continue
        id_ = m.group(1)
        rest = m.group(2)
        title = TITLE_SPLIT.split(rest, maxsplit=1)[0].strip()
        out.append((id_, title))
    return out


def find_intra_duplicates(headings: list[tuple[str, str]]) -> list[dict[str, Any]]:
    """One finding per `D-nn` appearing more than once in the same source."""
    by_id: dict[str, list[str]] = {}
    for id_, title in headings:
        by_id.setdefault(id_, []).append(title)
    return [
        {
            "id": id_,
            "occurrences": titles,
            "scope": "intra-file",
            "note": "same heading id used more than once in a single register copy",
        }
        for id_, titles in by_id.items()
        if len(titles) > 1
    ]


def check_cross_source(
    sources: dict[str, list[tuple[str, str]]],
) -> list[dict[str, Any]]:
    """One finding per `D-nn` whose title differs across `sources`.

    Sources are keyed by label (e.g. `"main"`, `"PR #28 (fix/branch-name)"`). Only
    collisions with a distinct title per id are reported -- same title in two
    sources is a normal inheritance relationship (the PR carries main's unchanged
    heading). Same id + different title in the SAME source is caught by
    find_intra_duplicates instead; here we surface the cross-source variant.
    """
    per_id: dict[str, list[tuple[str, str]]] = {}
    for label, headings in sources.items():
        for id_, title in headings:
            per_id.setdefault(id_, []).append((label, title))
    findings: list[dict[str, Any]] = []
    for id_, occurrences in per_id.items():
        distinct_titles = {title for _, title in occurrences}
        if len(distinct_titles) <= 1:
            continue
        findings.append(
            {
                "id": id_,
                "conflict": [{"source": s, "title": t} for s, t in occurrences],
                "scope": "cross-source",
                "note": (
                    "same finding id carries different titles across main and/or open PRs; "
                    "renumber the new claim (A-02 precedent: PR #41 D-52 -> D-53)"
                ),
            }
        )
    return findings


# A citation is any `D-<digits>` token. Bounded to 1-3 digits so hex digests or long
# numbers inside evidence tables are not mistaken for finding ids.
REFERENCE_RE = re.compile(r"\bD-(\d{1,3})\b")

# tests/** cites SYNTHETIC ids on purpose (fixture finding ids that exist only inside a
# temporary register copy), and this script must not cite one literally: a citation here
# would itself be a dangling reference.
# and the register's own heading lines are definitions rather than references. Excluding
# the fixture directory keeps this check about prose a reader would act on; the exclusion
# is stated here rather than left as an unexplained `continue`.
NON_EVIDENCE_PREFIXES = ("tests/", "staging/")


def find_dangling_references(
    headings: list[tuple[str, str]], root: Path = ROOT
) -> tuple[list[dict[str, Any]], list[str]]:
    """Every `D-nn` cited in tracked text must have a heading in the register.

    Why the collision check is not enough: measured on 2026-10-17, `D-56` was cited 17 times
    across `AGENTS.md`, `Makefile`, `audit/`, `policy/` and this register -- including inside the
    title of `D-64` ("D-56's actual root cause found and fixed") -- while **no `### D-56` heading
    existed anywhere on `main`**. The only definition lived on unmerged PR #67. Same story for
    `D-57` and `D-53`. A citation without a definition is worse than no citation: the reader
    believes a documented decision and compensating control exist, and goes looking for a row that
    is not there. Duplicates were gated; undefined references were not, which is how the class
    survived several "the register claims X" corrections; see the D-73 row for this class.

    Returns `(dangling, gaps)`. `gaps` is non-empty when the file list or a read failed, and the
    caller must treat that as could-not-verify, never as clean (§3, D-23).
    """
    defined = {f"{id_}" for id_, _ in headings}
    listing = subprocess.run(["git", "ls-files"], cwd=str(root), capture_output=True, text=True)
    if listing.returncode != 0:
        return [], [f"cannot list tracked files: {(listing.stderr or '').strip()[:160]}"]
    files = [f for f in listing.stdout.split() if f and (root / f).is_file()]
    if not files:
        return [], ["git ls-files returned no readable tracked files (non-vacuity guard)"]

    seen: dict[str, dict[str, Any]] = {}
    gaps: list[str] = []
    for rel in files:
        if rel.startswith(NON_EVIDENCE_PREFIXES):
            continue
        try:
            text = (root / rel).read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            gaps.append(f"cannot read {rel}: {exc}")
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            if HEADING_RE.match(line):
                continue  # a definition, not a reference
            for match in REFERENCE_RE.finditer(line):
                fid = f"D-{match.group(1)}"
                if fid in defined:
                    continue
                entry = seen.setdefault(
                    fid, {"id": fid, "count": 0, "first": f"{rel}:{lineno}", "scope": "dangling"}
                )
                entry["count"] += 1
    dangling = sorted(
        (
            {
                **item,
                "note": (
                    "cited "
                    f"{item['count']} time(s), first at {item['first']}, but no "
                    "`### <id> · <title>` heading exists in docs/drift-findings.md; add the row "
                    "(or re-point the citation at the finding that actually carries it)"
                ),
            }
            for item in seen.values()
        ),
        key=lambda d: int(d["id"].split("-")[1]),
    )
    return dangling, gaps


def gh_api(path: str) -> tuple[int, Any]:
    """GET via `gh api`. Non-2xx or unparseable returns status 0 -> caller files unverifiable."""
    proc = subprocess.run(["gh", "api", path], capture_output=True, text=True)
    if proc.returncode == 127:
        return 0, "gh CLI not found on PATH"
    if proc.returncode != 0:
        return 0, (proc.stderr or f"gh api {path} failed").strip()[:200]
    try:
        return 200, json.loads(proc.stdout or "null")
    except json.JSONDecodeError as exc:
        return 0, f"unparseable JSON from {path}: {exc}"


def fetch_headings_from_ref(repo: str, ref: str) -> tuple[list[tuple[str, str]], str | None]:
    """Read one branch's copy of the register via the contents API."""
    status, body = gh_api(f"repos/{repo}/contents/{REGISTER_REF_PATH}?ref={ref}")
    if status != 200 or not isinstance(body, dict):
        return [], f"cannot read {repo}@{ref}: {body}"
    encoding = str(body.get("encoding", "base64"))
    if encoding != "base64":
        return [], f"unexpected encoding {encoding!r} for {repo}@{ref}"
    try:
        text = base64.b64decode(str(body.get("content", ""))).decode("utf-8")
    except (ValueError, UnicodeDecodeError) as exc:
        return [], f"undecodable content {repo}@{ref}: {exc}"
    return parse_headings(text), None


def list_open_prs(repo: str) -> tuple[list[dict[str, Any]], str | None]:
    """Enumerate open PRs; returns [] with error string on failure (never silently empty)."""
    status, body = gh_api(f"repos/{repo}/pulls?state=open&per_page=100")
    if status != 200 or not isinstance(body, list):
        return [], f"cannot list open PRs for {repo}: {body}"
    return [p for p in body if isinstance(p, dict)], None


def resolve_repo_slug() -> str | None:
    """Under GitHub Actions `GITHUB_REPOSITORY` is `owner/name`; locally use `gh`'s view."""
    env = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if env:
        return env
    proc = subprocess.run(
        ["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"],
        capture_output=True,
        text=True,
    )
    if proc.returncode == 0 and proc.stdout.strip():
        return proc.stdout.strip()
    return None


def main(argv: list[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    cross_pr = "--cross-pr" in args
    try:
        working_text = REGISTER_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"ERROR: cannot read {REGISTER_PATH}: {exc}", file=sys.stderr)
        return 2

    working_headings = parse_headings(working_text)
    if not working_headings:
        print(
            f"ERROR: {REGISTER_PATH} parsed with 0 `### D-nn` headings; "
            "the register is expected to carry many (non-vacuity guard, AGENTS §7)",
            file=sys.stderr,
        )
        return 2

    findings: list[dict[str, Any]] = []
    unverifiable: list[str] = []

    # Intra-file collisions on the working copy.
    findings.extend(find_intra_duplicates(working_headings))

    # Citations with no definition (D-73). Runs in every mode, including inside the
    # required CI step, because it needs nothing but the working tree. `ROOT` is read here
    # rather than as a default argument so a fixture can point the whole check at a
    # throwaway repo -- a default evaluated at import time would keep scanning the real
    # tree and make every tmp_path test meaningless.
    dangling, ref_gaps = find_dangling_references(working_headings, ROOT)
    findings.extend(dangling)
    unverifiable.extend(ref_gaps)

    if cross_pr:
        repo = resolve_repo_slug()
        if not repo:
            unverifiable.append("cannot resolve repo slug (no GITHUB_REPOSITORY, gh view failed)")
        else:
            prs, err = list_open_prs(repo)
            if err:
                unverifiable.append(err)
            else:
                # Assemble sources: main + every open PR + working copy under "PR (local)".
                sources: dict[str, list[tuple[str, str]]] = {}
                main_headings, err = fetch_headings_from_ref(repo, "main")
                if err:
                    unverifiable.append(err)
                else:
                    sources["main"] = main_headings
                for pr in prs:
                    num = pr.get("number")
                    head = pr.get("head") or {}
                    ref = head.get("ref") if isinstance(head, dict) else None
                    if not isinstance(num, int) or not isinstance(ref, str) or not ref:
                        unverifiable.append(f"PR entry missing number/head.ref: {pr!r:.120}")
                        continue
                    headings, err = fetch_headings_from_ref(repo, ref)
                    if err:
                        unverifiable.append(err)
                        continue
                    sources[f"PR #{num} ({ref})"] = headings
                # Add the working copy as a distinct source so this PR's own
                # new/changed headings surface even before it is on a remote ref.
                sources["working copy"] = working_headings
                findings.extend(check_cross_source(sources))

    for f in findings:
        label = "DANGLING" if f.get("scope") == "dangling" else "COLLISION"
        printable = {k: v for k, v in f.items() if k not in ("note", "first", "count")}
        print(
            f"{label} {f['id']} [{f['scope']}]: {f['note']}\n  "
            + json.dumps(printable, ensure_ascii=False),
            file=sys.stderr,
        )
    for u in unverifiable:
        print(f"UNVERIFIABLE: {u}", file=sys.stderr)

    if unverifiable:
        print(
            f"RESULT: could not verify ({len(unverifiable)}); {len(findings)} collisions seen",
            file=sys.stderr,
        )
        return 2
    if findings:
        n_col = sum(1 for f in findings if f.get("scope") != "dangling")
        n_dang = len(findings) - n_col
        print(
            f"RESULT: {n_col} finding-id collision(s) and {n_dang} dangling citation(s) "
            f"across {len(working_headings)} headings on the working copy",
            file=sys.stderr,
        )
        return 1
    print(
        f"OK: {len(working_headings)} `### D-nn` headings parsed, no collisions, "
        "no dangling citations" + (" (cross-PR mode)" if cross_pr else ""),
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
