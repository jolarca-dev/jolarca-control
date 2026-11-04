#!/usr/bin/env python3
"""Extract Step 6b step 1's ADOPTION block from the runbook into a file Terraform can import.

Why this exists as a gate and not a one-liner: the operator instruction was "land this file only in
the PR that runs step 2", i.e. transcribe a protection object by hand — the exact friction D-87 row
(3) says trains humans to write protection objects themselves. A first replacement selected the
fenced block by ``startswith('resource "github_repository_ruleset"')`` and the absence of the string
``pull_request``. Both were wrong, in the instructive direction:

* the fence begins with comment lines, so nothing matched (an ``IndexError``, loud);
* the adoption block's own comment says "Deliberately absent, because live lacks them: pull_request
  and required_status_checks", so a word filter rejects the one block it should accept — prose used
  as a structural test, which is the same class of error as D-87 row (6)'s attribute-name grep.

An ``awk`` variant then emitted zero lines and ``terraform fmt -check`` on the empty file exited
**0**, so a passing format check proved nothing. This script therefore asserts structure and fails
closed: exit 0 only when exactly one adoption candidate exists for the requested repository and it is
provably inert.

Repository selection (D-94, 2026-10-31). The first version hard-coded ``jolarca-consent`` in four
places, which made Step 6b a one-shot tool: adopting a second ruleset-only repo (vendor, per D-93)
was impossible without hand-editing generated config, and the printed next-step hint carried a
literal numeric ruleset id — a wrong command that looks right, for any repo but one. The target is
now an argument, the assertions are made against it, and the emitted hint contains a placeholder plus
the command that discovers the real id. ``--repo`` defaults to the historical target so existing
invocations and fixtures behave identically.

Resource naming (D-94, second half). Parameterising the *target* left a second consent-specificity
behind: the block it emitted was always labelled ``"main"``. That label is not free — ``rulesets.tf``
is tracked, declares ``resource "github_repository_ruleset" "main"`` for the historical target, and
that address is in state, so a second file reusing it fails ``terraform validate`` with a duplicate
resource error. ``default_resource_name()`` derives a per-repo label and ``main`` is grandfathered
only for the historical target, so the tree this tool can emit is always planable. The label is
**derived, never supplied**: ``--resource-name`` was added and removed the same day, because ``vet()``
compared the fence against the value the flag provided while emitting the block verbatim, so passing the
fence's own ``"main"`` satisfied the check and wrote a duplicate -- reproduced with ``terraform validate``
on Terraform v1.16.1. A flag whose only effect is to weaken a contract is deleted, not documented.
:func:`label_problem` further refuses a derivation that lands on ``main`` for a second repository, on an
identifier Terraform would reject, or on a slug that quietly dropped case. The contract is enforced in
one place, :func:`vet`, before anything is written.

Exit codes follow AGENTS.md §3: 0 verified, 1 refused (a real finding), 2 could not verify.
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys

RUNBOOK = "docs/state-migration-runbook.md"
RESOURCE = "github_repository_ruleset"
DEFAULT_REPO = "jolarca-consent"
REPO_PREFIX = "jolarca-"
# Terraform resource labels begin with a letter or underscore, then letters, digits or underscores.
# The derived label is checked against this grammar before it is enforced, because the alternative is
# to demand a name `terraform validate` will reject.
_LABEL_RE = re.compile(r"[a-z_][a-z0-9_]*")

_HEADER = re.compile(r'^resource "github_repository_ruleset"', re.M)
_RULE_BLOCK = re.compile(r"^\s*(pull_request|required_status_checks|bypass_actors)\s*\{", re.M)
_RESOURCE_BLOCK = re.compile(r'^resource "', re.M)
_FOR_EACH = re.compile(r"^\s*for_each\s*=", re.M)
# The repo a block targets, read out of its own for_each rather than compared against a constant.
_FOR_EACH_ITEM = re.compile(r"toset\(\[([^\]]*)\]")
_RESOURCE_NAMED = re.compile(r'resource "github_repository_ruleset" "([^"]+)"')
_STRING_ITEM = re.compile('"([^"]+)"')


def default_resource_name(repo: str) -> str:
    """`main` is grandfathered for the historical target only.

    Every other repository needs its own resource name: two files declaring
    `resource "github_repository_ruleset" "main"` for different repositories are a hard
    `terraform validate` error (measured 2026-10-31: "Duplicate resource
    \"github_repository_ruleset\" configuration"), so a generator that always emitted `main`
    produced a tree that could not be planned. D-94's first fix parameterised selection and
    left this second consent-specificity in place.
    """
    if repo == DEFAULT_REPO:
        return "main"
    slug = re.sub(r"[^a-z0-9_]", "_", repo.replace(REPO_PREFIX, "")).strip("_")
    return slug or "main"


def label_problem(repo: str, want: str) -> str | None:
    """Why ``want`` cannot be this repository's resource label, or ``None`` when it can.

    Terraform resource labels are one namespace shared by every ``.tf`` file, and the tracked
    ``rulesets.tf`` already declares ``"main"`` for the historical target. The failure modes refused
    here are the same mistake in different clothing: a derivation that lands on a value another
    repository owns, or one ``terraform validate`` would reject outright. Neither is a reason to
    guess -- a colliding label and an invalid label both fail at apply time, quietly.
    """
    if repo != DEFAULT_REPO and want == "main":
        return (
            f'cannot derive a resource label for {repo!r}: the fallback "main" is already declared '
            f"for {DEFAULT_REPO} in the tracked rulesets.tf"
        )
    if not _LABEL_RE.fullmatch(want):
        return (
            f"derived resource label {want!r} for {repo!r} is not a valid Terraform identifier "
            "(must start with a letter or underscore, then letters, digits or underscores)"
        )
    stem = repo[len(REPO_PREFIX) :] if repo.startswith(REPO_PREFIX) else repo
    if stem != stem.lower():
        return (
            f"repository name {repo!r} contains uppercase, which the label would silently drop "
            f"({stem!r} -> {want!r}); refusing rather than emitting a name nobody asked for"
        )
    return None


def _repo_pattern(repo: str) -> re.Pattern[str]:
    """Match a for_each list that names `repo`, wherever it sits in the list."""
    return re.compile(r'toset\(\[[^\]]*"' + re.escape(repo) + r'"[,\]]')


def _targeted_repos(block: str) -> list[str]:
    """Every repository named in the block's toset(...) list."""
    m = _FOR_EACH_ITEM.search(block)
    if not m:
        return []
    return _STRING_ITEM.findall(m.group(1))


def fences(text: str) -> list[str]:
    """Every ```hcl fence in the runbook that declares a repository ruleset."""
    return [b for b in re.findall(r"```hcl\n(.*?)\n```", text, re.S) if _HEADER.search(b)]


def is_adoption(block: str) -> bool:
    """The adoption block mirrors live state and therefore carries NO rule blocks.

    Keyed on block syntax (an indented ``name {``), never on whether the word appears somewhere in
    the text — the comment inside the adoption block mentions both rule names precisely to explain
    their absence.
    """
    return _RULE_BLOCK.search(block) is None


def select(text: str, repo: str = DEFAULT_REPO) -> tuple[list[str], list[str]]:
    """(all ruleset fences, adoption fences targeting `repo`).

    Filtering by target is what makes a second repo adoptable without ambiguity: two adoption fences
    in one document are fine as long as exactly one of them names the repo being adopted.
    """
    adopted = fences(text)
    return adopted, [b for b in adopted if is_adoption(b) and _repo_pattern(repo).search(b)]


def adoption_repos(text: str) -> list[str]:
    """Repositories that DO have an adoption fence — for a useful refusal when the wrong one is asked for."""
    seen: list[str] = []
    for block in fences(text):
        if is_adoption(block):
            for name in _targeted_repos(block):
                if name not in seen:
                    seen.append(name)
    return seen


def vet(block: str, repo: str = DEFAULT_REPO) -> list[str]:
    """Structural requirements for a block an operator is about to import.

    The label is derived from ``repo`` and never supplied: an argument that could set ``want`` made
    this check vacuous, because passing the fence's own colliding label satisfied it.
    """
    problems: list[str] = []
    want = default_resource_name(repo)
    bad = label_problem(repo, want)
    if bad:
        problems.append(bad)
    if len(_RESOURCE_BLOCK.findall(block)) != 1:
        problems.append(
            f"{len(_RESOURCE_BLOCK.findall(block))} resource blocks; expected exactly 1"
        )
    if f'resource "{RESOURCE}" "{want}"' not in block:
        named = _RESOURCE_NAMED.findall(block)
        problems.append(
            f'resource is not named "{want}" (found {named}) -> the step-2 import address '
            f'`{RESOURCE}.{want}["{repo}"]` would not exist, and a label two repos both declare '
            "is a hard `terraform validate` error (measured 2026-10-31: Duplicate resource "
            '"github_repository_ruleset" configuration) -- `rulesets.tf` is tracked and declares '
            f'"main" for {DEFAULT_REPO}. Rename the fence in the runbook to `{want}`.'
        )
    if not _FOR_EACH.search(block):
        problems.append(f'no for_each -> address {want}["{repo}"] does not exist')
    if not _repo_pattern(repo).search(block):
        named = _targeted_repos(block)
        problems.append(
            f'for_each does not name "{repo}"'
            + (f" (it names {named})" if named else " (no toset list found)")
        )
    if _RULE_BLOCK.search(block):
        found = sorted({m.group(1) for m in _RULE_BLOCK.finditer(block)})
        problems.append(f"carries rule block(s) {found} -> adopting it would MUTATE protection")
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--runbook", default=RUNBOOK, help="override the source document (for fixtures)"
    )
    ap.add_argument(
        "--repo",
        default=DEFAULT_REPO,
        help=f"ruleset-only repository to adopt (default: {DEFAULT_REPO}, the historical target)",
    )
    ap.add_argument("--out", default="rulesets.tf")
    ap.add_argument("--check", action="store_true", help="select and vet, write nothing")
    args = ap.parse_args(argv)

    path = pathlib.Path(args.runbook)
    if not path.is_absolute():
        path = pathlib.Path(__file__).resolve().parent.parent / path
    if not path.is_file():
        print(f"CANNOT-VERIFY: runbook not found: {path}", file=sys.stderr)
        return 2
    text = path.read_text(encoding="utf-8")

    all_blocks, candidates = select(text, args.repo)
    print(
        f"ruleset fences in {path.name}: {len(all_blocks)}  "
        f"adoption candidates for {args.repo}: {len(candidates)}"
    )
    for block in all_blocks:
        head = next(ln for ln in block.splitlines() if _HEADER.match(ln))
        kind = "adoption (inert mirror)" if is_adoption(block) else "stage-2 (adds rules)"
        print(f"  {kind:22} targets={','.join(_targeted_repos(block)) or '?'}  {head}")

    if not all_blocks:
        print("CANNOT-VERIFY: no github_repository_ruleset fence found", file=sys.stderr)
        return 2
    if not candidates:
        available = adoption_repos(text)
        print(
            f"REFUSED: no inert adoption fence targets {args.repo}"
            + (
                f"; adoption fences exist for {available}"
                if available
                else "; no adoption fences at all"
            )
            + ". Pass --repo <name>, or add the repo's Step 6b step-1 block to the runbook first.",
            file=sys.stderr,
        )
        return 1
    if len(candidates) != 1:
        print(
            f"REFUSED: expected exactly 1 adoption candidate for {args.repo}, found "
            f"{len(candidates)}. Extracting the wrong fence would import a non-inert adoption "
            "or fail in step 2.",
            file=sys.stderr,
        )
        return 1

    body = candidates[0].rstrip() + "\n"
    label = default_resource_name(args.repo)
    problems = vet(body, args.repo)
    if problems:
        print("REFUSED: the selected block is not a safe adoption:", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1

    print(
        f"OK: {len(body.splitlines())} lines, 1 resource, 0 rule blocks, for_each names {args.repo}"
    )
    out = pathlib.Path(args.out)
    if args.check:
        print(f"--check: nothing written (would write {out})")
        return 0
    if out.exists():
        print(f"REFUSED: {out} already exists; refusing to overwrite silently", file=sys.stderr)
        return 1
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(body, encoding="utf-8")
    print(f"wrote {out}")
    # The artifact this tool produces is a `*.tf` file, and `apply.yml` triggers on `*.tf`. Committing
    # it BEFORE the import is therefore a production apply whose plan wants to CREATE a duplicate
    # ruleset beside the live one. Measured 2026-10-27: with the file present and no import the plan
    # reads `1 to add, 1 to change` and check_plan_safety.sh exits 1 naming the create -- the brake
    # holds, but the merge is already the act. Say it out loud instead of relying on the reader to
    # have read step 1's warning paragraph.
    print(
        f"WARNING: {out} is an apply-trigger path (*.tf). Import it (step 2) BEFORE committing, "
        "or delete it: a declared-but-unimported ruleset plans a create beside the live one (D-46)."
    )
    # Deliberately a placeholder, not a literal id (D-94): the previous version printed
    # 'jolarca-consent:24087580' unconditionally, so adopting any other repository produced a
    # confident, specific, WRONG import command.
    print(
        "next: discover the ruleset id, then import --\n"
        f"      gh api repos/jolarca-dev/{args.repo}/rulesets --jq '.[] | \"\\(.id)\\t\\(.name)\"'\n"
        f"      terraform import -input=false "
        f"'{RESOURCE}.{label}[\"{args.repo}\"]' '{args.repo}:<ruleset-id>'"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
