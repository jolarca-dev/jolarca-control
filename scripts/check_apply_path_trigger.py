#!/usr/bin/env python3
"""check_apply_path_trigger.py — an unattended PR must not arm a production apply.

jolarca-control — marketplace (jolarca-dev) governance control plane.
SOC 2 CC8.1 / CC7.1 · ISO/IEC 27001 A.8.32 · PCI-DSS Req 12.10.1

WHY THIS EXISTS (measured, 2026-10-26, main `c3ff906`)
---------------------------------------------------------------------------
`apply.yml` fires on `push: main` for `repos/**`, `policy/**`, `*.tf`, `*.tfvars` and
**itself** (`.github/workflows/apply.yml`), then runs `terraform apply -input=false
-auto-approve tfplan`. AGENTS.md §8 records that. What had not been recorded is the
consequence for dependency automation:

    gh pr diff 87 --name-only  ->  apply.yml compliance-scan.yml context-parity.yml
                                   deploy-gates.yml plan.yml sast.yml
    gh pr diff 68 --name-only  ->  apply.yml evidence-integrity.yml

Both are Dependabot PRs that bump a **SHA-pinned action**. Both therefore edit
`apply.yml`, which is in `apply.yml`'s own push paths — so merging a routine-looking
version bump starts a production apply. Nothing said so, and nothing stopped it: the
brakes (`check_plan_safety.sh`, `prevent_destroy`, the 30-minute wait) all act *after*
the merge, on the apply run itself, and D-58's exception is recorded precisely because
no person signs that decision. A wait timer is delay, not approval.

The asymmetry this gate encodes is deliberate and narrow:

  * a **human** PR touching those paths is a considered act -> `::notice::` and exit 0
    (this repo must keep landing Terraform changes; refusing them would be a new way to
    wedge the fleet, the A-01/FA-control-03 deadlock class);
  * a **bot** PR touching those paths is not a considered act -> exit 1, so a required
    context refuses it and the change has to be re-authored by a person who is then
    choosing the apply deliberately.

That is not a dependency-bump deadlock (the class the fleet hit when severity-gated
scanners failed every one-package PR): the bump is still mergeable, by a human, on the
same diff. What it blocks is the *unattended* merge.

RULES
---------------------------------------------------------------------------
T1  the trigger set is READ from `apply.yml`'s own `on.push.paths`, never hardcoded —
    a second source of truth would drift the moment someone edits the workflow, which
    is how `policy/repo-defaults.yml` came to name a context nothing reports (D-62).
T2  glob semantics follow GitHub's filter syntax, taken from the workflow-syntax reference
    rather than guessed: `*` "matches any character, but does not match slash (/)", `**`
    matches across slashes, and `'*.js'` explicitly "Matches all `.js` files at the root of
    the repository" (the at-any-depth form is `'**.js'`). So `*.tf` here does NOT match
    `modules/x.tf`, and a gate built on fnmatch would fire on changes that cannot trigger
    anything — a required check that cries wolf is a gate people route around.
T3  the changed-file list must come from the caller. Missing input, an unreadable list or
    an unparseable `apply.yml` is exit 2, never 0 (§3): a gate that cannot see the diff
    must not report "no apply will happen".
T4  an unknown author kind is judged only when a path matches, so ordinary PRs are
    unaffected; then it is exit 2, because "we could not tell whether a bot wrote this"
    is not evidence of safety.
T5  a trigger set this gate cannot model is refused, not approximated. Exclusion patterns
    (`!foo`) and `paths-ignore` invert the question "does this diff arm the apply?", and
    guessing either way is a verdict the input does not support -> exit 2.

KNOWN DIVERGENCES FROM GITHUB'S OWN EVALUATION (all of them narrow, none of them a pass)
  * GitHub runs the workflow regardless of filters if a push carries >1,000 commits, or if
    diff generation times out. This gate cannot see commit counts from a file list.
  * Both sides truncate huge diffs (GitHub at 3,000 files, the REST list at 3,000 too), so a
    >3,000-file PR is the one shape where the gate and the trigger could disagree.
  * `workflow_dispatch:` on apply.yml bypasses `paths:` entirely — by design, because it is a
    human clicking. This gate models the `push: main` route, which is what a merge takes.

EXIT CODES (AGENTS.md §3 — never a silent pass)
   0  no apply-path file changed, or a human changed one (announced)
   1  a bot/app PR changes a file in apply.yml's own push paths
   2  could not verify — no diff, unreadable diff, unparseable apply.yml, no paths,
      a trigger set this gate cannot model (`!` exclusions, `paths-ignore`),
      or a matching PR whose author kind is unknowable
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
APPLY_WORKFLOW = ".github/workflows/apply.yml"

# `github.event.pull_request.user.type` values that mean "nobody read this diff".
BOT_ACTOR_TYPES = frozenset({"Bot", "App"})
HUMAN_ACTOR_TYPES = frozenset({"User", "Organization"})


class CannotVerify(Exception):
    """Input needed to reach a verdict is missing or unreadable -> exit 2."""


def _glob_to_regex(pattern: str) -> re.Pattern[str]:
    """Compile a GitHub path-filter pattern into a regex with GitHub's segment rules.

    The rules are quoted from the workflow-syntax reference's filter-pattern cheat sheet:
    `*` "matches any character, but does not match slash (/)", `**` matches any character
    including slashes, and `'*.js'` "Matches all `.js` files at the root of the repository"
    while `'**.js'` matches them at any depth. fnmatch is therefore NOT usable: its `*`
    crosses `/`, so a root pattern would fire on paths that cannot trigger anything.
    """
    out: list[str] = []
    i = 0
    while i < len(pattern):
        ch = pattern[i]
        if ch == "*":
            if pattern[i + 1 : i + 2] == "*":
                # `**/` -> "zero or more directories"; bare `**` -> "anything".
                if pattern[i + 2 : i + 3] == "/":
                    out.append("(?:[^/]+/)*")
                    i += 3
                    continue
                out.append(".*")
                i += 2
                continue
            out.append("[^/]*")
            i += 1
            continue
        if ch == "?":
            out.append("[^/]")
            i += 1
            continue
        out.append(re.escape(ch))
        i += 1
    return re.compile("^" + "".join(out) + "$")


def read_trigger_paths(workflow: Path) -> list[str]:
    """`on.push.paths` from the workflow itself (T1). Any failure is CannotVerify."""
    try:
        text = workflow.read_text(encoding="utf-8")
    except OSError as exc:
        raise CannotVerify(f"cannot read {workflow.name}: {exc.strerror or exc}") from exc
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise CannotVerify(f"cannot parse {workflow.name}: {str(exc)[:120]}") from exc
    if not isinstance(doc, dict):
        raise CannotVerify(f"{workflow.name} did not parse to a mapping")
    # YAML 1.1 resolves the bare key `on` to True, so GitHub's own files arrive as {True: …}.
    trig = doc.get("on", doc.get(True))
    if not isinstance(trig, dict):
        raise CannotVerify(f"{workflow.name} has no mapping-valued `on:` block")
    push = trig.get("push")
    if push is None:
        raise CannotVerify(f"{workflow.name} declares no `push:` trigger")
    if isinstance(push, dict):
        paths = push.get("paths")
        ignored = push.get("paths-ignore")
    else:
        raise CannotVerify(f"{workflow.name} `push:` is not a mapping — cannot read its paths")
    if paths is None:
        if ignored is not None:
            # `paths-ignore` asks the opposite question ("everything EXCEPT these"), which this
            # gate cannot answer by widening to `**` — that would refuse every bot PR, including
            # ones GitHub never triggers. Refuse and say why (T5).
            raise CannotVerify(
                f"{workflow.name} uses `push.paths-ignore`, which this gate does not model "
                "(T5). Re-read what arms the apply and update this script in the same PR."
            )
        # No path filter means EVERY push to main triggers it: the widest case, not the empty one.
        return ["**"]
    if not isinstance(paths, list) or not paths:
        raise CannotVerify(f"{workflow.name} `push.paths` is not a non-empty list")
    patterns = [str(p) for p in paths]
    negated = [p for p in patterns if p.startswith("!")]
    if negated:
        raise CannotVerify(
            f"{workflow.name} `push.paths` contains exclusion pattern(s) {negated} — last-match "
            "semantics decide whether a file arms the apply, and this gate refuses to guess (T5)."
        )
    return patterns


def matching_paths(patterns: list[str], changed: list[str]) -> list[str]:
    """Which changed files satisfy at least one pattern. Pure, so fixtures can drive it.

    Normalisation strips a leading `./` ONLY. The first draft used `path.lstrip("./")`, which
    is a character-set operation, not a prefix strip: it ate the leading dot of
    `.github/workflows/apply.yml` and made the one path Dependabot actually edits unmatchable.
    Caught by running the gate against the live `gh pr diff --name-only` output for PRs #87/#68,
    not by the fixtures alone — a gate whose happy path is a false clean is worse than no gate.
    """
    compiled = [_glob_to_regex(p) for p in patterns]
    hits: list[str] = []
    for path in changed:
        norm = path[2:] if path.startswith("./") else path
        for rx in compiled:
            if rx.match(norm):
                hits.append(path)
                break
    return hits


def read_changed_files(files_from: str | None, raw: str | None) -> list[str]:
    """T3: the diff comes from the caller, as a file or a newline/comma-separated string."""
    source = files_from or os.environ.get("CHANGED_FILES_FROM")
    if source:
        p = Path(source)
        try:
            text = p.read_text(encoding="utf-8")
        except OSError as exc:
            raise CannotVerify(f"cannot read the changed-file list at {source}") from exc
    else:
        text = raw if raw is not None else os.environ.get("CHANGED_FILES", "")
        if text is None:
            raise CannotVerify("no changed-file input: pass --files-from or set CHANGED_FILES")
    changed = [line.strip() for line in re.split(r"[\n,]", text or "") if line.strip()]
    if not changed:
        raise CannotVerify(
            "the changed-file list is empty — a PR always has files, so this is a lost input, "
            "not a clean diff"
        )
    return changed


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--files-from", help="file listing changed paths, one per line")
    ap.add_argument("--changed", help="changed paths, comma or newline separated")
    ap.add_argument("--actor-type", default=os.environ.get("PR_ACTOR_TYPE", ""))
    ap.add_argument("--actor", default=os.environ.get("PR_ACTOR", ""))
    ap.add_argument("--workflow", default=str(ROOT / APPLY_WORKFLOW))
    ap.add_argument(
        "--report-only",
        action="store_true",
        help="print the verdict and never fail (live dry-run against existing PRs)",
    )
    args = ap.parse_args(argv)

    def refuse(msg: str) -> int:
        print(f"CANNOT-VERIFY: {msg}", file=sys.stderr)
        return 2

    try:
        patterns = read_trigger_paths(Path(args.workflow))
        changed = read_changed_files(args.files_from, args.changed)
    except CannotVerify as exc:
        return refuse(str(exc))

    hits = matching_paths(patterns, changed)
    if not hits:
        print(
            f"OK: {len(changed)} changed file(s), none in apply.yml's push paths "
            f"({len(patterns)} pattern(s) read from {Path(args.workflow).name}) — no apply armed"
        )
        return 0

    actor = args.actor or "(unknown)"
    kind = args.actor_type.strip()
    print(f"APPLY-PATH CHANGE ({len(hits)} file(s)):")
    for h in hits:
        print(f"  {h}")

    if kind in BOT_ACTOR_TYPES:
        print(
            f"\nRESULT: '{actor}' is a {kind.lower()} — merging this would run "
            "`terraform apply -auto-approve` with nobody having read the plan (D-81).\n"
            "fix: re-author the same change in a human PR (the diff is fine, the absence of a "
            "human is not), or move the pin bump out of apply.yml's own paths. Do not weaken "
            "this gate to let a bot through (AGENTS.md §5).",
        )
        return 0 if args.report_only else 1

    if kind in HUMAN_ACTOR_TYPES:
        print(
            f"\nNOTICE: author '{actor}' is a {kind.lower()}, so this is treated as a considered "
            "act. The merge WILL start a production apply: watch the 30-minute wait window, "
            "`gh run cancel <id> --force` is the brake, and check_plan_safety.sh is the refusal."
        )
        return 0

    # T4: a matching PR whose author kind we cannot read. Silence here would be a pass on
    # ignorance, and ignorance is what D-81 is about.
    return refuse(
        f"apply-path files changed but the author kind is unknown (PR_ACTOR_TYPE='{args.actor_type}'). "
        "Verdict requires knowing whether a bot wrote this — pass --actor-type"
    )


if __name__ == "__main__":
    raise SystemExit(main())
