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
closed: exit 0 only when exactly one adoption candidate exists and it is provably inert.

Exit codes follow AGENTS.md §3: 0 verified, 1 refused (a real finding), 2 could not verify.
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys

RUNBOOK = "docs/state-migration-runbook.md"
RESOURCE = "github_repository_ruleset"

_HEADER = re.compile(r'^resource "github_repository_ruleset"', re.M)
_RULE_BLOCK = re.compile(r"^\s*(pull_request|required_status_checks|bypass_actors)\s*\{", re.M)
_RESOURCE_BLOCK = re.compile(r'^resource "', re.M)
_FOR_EACH = re.compile(r"^\s*for_each\s*=", re.M)
_REPO_KEY = re.compile(r'toset\(\["jolarca-consent"\]\)')


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


def select(text: str) -> tuple[list[str], list[str]]:
    adopted = fences(text)
    return adopted, [b for b in adopted if is_adoption(b)]


def vet(block: str) -> list[str]:
    """Structural requirements for a block an operator is about to import."""
    problems: list[str] = []
    if len(_RESOURCE_BLOCK.findall(block)) != 1:
        problems.append(
            f"{len(_RESOURCE_BLOCK.findall(block))} resource blocks; expected exactly 1"
        )
    if 'resource "github_repository_ruleset" "main"' not in block:
        problems.append('resource is not named "main" -> the step-2 import address would not exist')
    if not _FOR_EACH.search(block):
        problems.append('no for_each -> address main["jolarca-consent"] does not exist')
    if not _REPO_KEY.search(block):
        problems.append('for_each does not include "jolarca-consent"')
    if _RULE_BLOCK.search(block):
        found = sorted({m.group(1) for m in _RULE_BLOCK.finditer(block)})
        problems.append(f"carries rule block(s) {found} -> adopting it would MUTATE protection")
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--runbook", default=RUNBOOK, help="override the source document (for fixtures)"
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

    all_blocks, candidates = select(text)
    print(
        f"ruleset fences in {path.name}: {len(all_blocks)}  adoption candidates: {len(candidates)}"
    )
    for block in all_blocks:
        head = next(ln for ln in block.splitlines() if _HEADER.match(ln))
        kind = "adoption (inert mirror)" if is_adoption(block) else "stage-2 (adds rules)"
        print(f"  {kind:22} {head}")

    if not all_blocks:
        print("CANNOT-VERIFY: no github_repository_ruleset fence found", file=sys.stderr)
        return 2
    if len(candidates) != 1:
        print(
            f"REFUSED: expected exactly 1 adoption candidate, found {len(candidates)}. "
            "Extracting the wrong fence would import a non-inert adoption or fail in step 2.",
            file=sys.stderr,
        )
        return 1

    body = candidates[0].rstrip() + "\n"
    problems = vet(body)
    if problems:
        print("REFUSED: the selected block is not a safe adoption:", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1

    print(f"OK: {len(body.splitlines())} lines, 1 resource, 0 rule blocks, for_each present")
    out = pathlib.Path(args.out)
    if args.check:
        print(f"--check: nothing written (would write {out})")
        return 0
    if out.exists():
        print(f"REFUSED: {out} already exists; refusing to overwrite silently", file=sys.stderr)
        return 1
    out.write_text(body, encoding="utf-8")
    print(f"wrote {out}")
    # The artifact this tool produces is a `*.tf` file, and `apply.yml` triggers on `*.tf`. Committing
    # it BEFORE the import is therefore a production apply whose plan wants to CREATE a duplicate
    # ruleset beside the live one. Measured 2026-10-27: with the file present and no import the plan
    # reads `1 to add, 1 to change` and check_plan_safety.sh exits 1 naming the create -- the brake
    # holds, but the merge is already the act. Say it out loud instead of relying on the reader to
    # have read step 1's warning paragraph.
    print(
        "WARNING: rulesets.tf is an apply-trigger path (*.tf). Import it (step 2) BEFORE committing, "
        "or delete it: a declared-but-unimported ruleset plans a create beside the live one (D-46)."
    )
    print(
        "next: terraform import -input=false "
        "'github_repository_ruleset.main[\"jolarca-consent\"]' 'jolarca-consent:24087580'"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
