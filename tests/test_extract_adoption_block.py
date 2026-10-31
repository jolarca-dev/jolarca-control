#!/usr/bin/env python3
"""Negative controls for scripts/extract_adoption_block.py (D-80 R1: every gate needs a fixture
that can fail).

The subject is a selector that decides which fenced HCL block an operator imports as a protection
object. A wrong choice here is not cosmetic: importing the stage-2 block as if it were the adoption
would PUT new rules on `jolarca-consent` at the moment of adoption, and importing nothing would fail
in step 2 with "resource address does not exist in the configuration" — which is the error the
operator actually hit, after a hand-written one-liner selected no block at all.

Each test states which defect it exists to catch, and three of them assert non-zero exits.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import extract_adoption_block as ex  # noqa: E402

RUNBOOK = ROOT / "docs" / "state-migration-runbook.md"

ADOPTION = """```hcl
# rulesets.tf — D-46 option A, consent first.
# Mirrors live content measured 2026-10-26; changes NOTHING about what GitHub enforces.
resource "github_repository_ruleset" "main" {
  for_each = toset(["jolarca-consent"])

  repository  = each.value
  name        = "protect-main"
  target      = "branch"
  enforcement = "active"

  rules {
    deletion                = true
    # Deliberately absent, because live lacks them: pull_request and
    # required_status_checks. Adding them is step 4, a separate reviewed change.
  }
}
```"""

STAGE2 = """```hcl
resource "github_repository_ruleset" "main" {
  for_each = toset(["jolarca-consent"])

  repository  = each.value
  name        = "protect-main"
  target      = "branch"
  enforcement = "active"

  rules {
    deletion                = true
    pull_request {
      required_approving_review_count = 0
    }
    required_status_checks {
      strict_required_status_checks_policy = true
      required_check {
        context = "Lint (ruff)"
      }
    }
  }
}
```"""


def write_runbook(tmp_path: pathlib.Path, body: str) -> pathlib.Path:
    p = tmp_path / "runbook.md"
    p.write_text(f"# doc\n\n{body}\n", encoding="utf-8")
    return p


def test_the_real_runbook_yields_exactly_one_inert_adoption_candidate() -> None:
    """Non-vacuity: the shipped artifact must satisfy the selector, or the gate tests nothing."""
    all_blocks, candidates = ex.select(RUNBOOK.read_text(encoding="utf-8"))
    assert len(all_blocks) == 2, f"expected 2 ruleset fences, got {len(all_blocks)}"
    assert len(candidates) == 1, "the adoption fence must be uniquely identifiable"
    assert not ex.vet(candidates[0] + "\n"), ex.vet(candidates[0] + "\n")


def test_prose_mention_of_a_rule_name_does_not_disqualify_the_adoption() -> None:
    """The bug this fixture exists to keep dead: the first attempt filtered on the *word*
    `pull_request`, and the adoption block's own comment contains it to explain the absence. That
    made the selector return zero candidates and the operator's import failed on missing config."""
    blocks = ex.fences(ADOPTION)
    assert len(blocks) == 1
    assert ex.is_adoption(blocks[0]), "a comment naming pull_request is not a pull_request block"


def test_a_contaminated_adoption_is_not_selected(tmp_path: pathlib.Path) -> None:
    """If someone pastes a rule block into the adoption fence, it must stop looking inert —
    otherwise `--out` writes a mutation-carrying 'adoption'."""
    contaminated = ADOPTION.replace(
        "  rules {\n    deletion                = true",
        "  rules {\n    pull_request {\n      required_approving_review_count = 0\n    }\n"
        "    deletion                = true",
    )
    assert contaminated != ADOPTION, "injection did not apply; this test proved nothing"
    _, candidates = ex.select(contaminated)
    assert candidates == []


def test_main_refuses_when_two_fences_both_look_inert(tmp_path: pathlib.Path) -> None:
    """Two candidates is an ambiguity, not a choice. Exit 1, and write nothing."""
    rb = write_runbook(tmp_path, ADOPTION + "\n\n" + ADOPTION)
    out = tmp_path / "rulesets.tf"
    rc = ex.main(["--runbook", str(rb), "--out", str(out)])
    assert rc == 1
    assert not out.exists()


def test_main_returns_2_not_0_when_the_source_has_no_fences(tmp_path: pathlib.Path) -> None:
    """AGENTS.md §3: 'could not verify' is never a silent pass. An empty or unrelated document is
    the input shape that made an awk variant print nothing and `terraform fmt -check` exit 0."""
    rb = write_runbook(tmp_path, "no hcl fences here")
    out = tmp_path / "rulesets.tf"
    assert ex.main(["--runbook", str(rb), "--out", str(out)]) == 2
    assert not out.exists()


def test_main_returns_2_when_the_runbook_path_is_missing(tmp_path: pathlib.Path) -> None:
    assert ex.main(["--runbook", str(tmp_path / "absent.md")]) == 2


def test_main_writes_only_after_passing_every_structural_assertion(tmp_path: pathlib.Path) -> None:
    rb = write_runbook(tmp_path, ADOPTION + "\n\n" + STAGE2)
    out = tmp_path / "rulesets.tf"
    assert ex.main(["--runbook", str(rb), "--out", str(out)]) == 0
    body = out.read_text(encoding="utf-8")
    assert "pull_request {" not in body
    assert 'resource "github_repository_ruleset" "main"' in body
    assert body.count('resource "') == 1


def test_main_refuses_to_overwrite_an_existing_file(tmp_path: pathlib.Path) -> None:
    """Silently replacing a half-finished rulesets.tf is how a reviewed object gets swapped."""
    rb = write_runbook(tmp_path, ADOPTION)
    out = tmp_path / "rulesets.tf"
    out.write_text("# operator started this\n", encoding="utf-8")
    assert ex.main(["--runbook", str(rb), "--out", str(out)]) == 1
    assert out.read_text(encoding="utf-8") == "# operator started this\n"


def test_vet_names_the_rule_blocks_it_rejects() -> None:
    """The refusal must be diagnosable, not just non-zero."""
    blocks = ex.fences(STAGE2)
    assert len(blocks) == 1
    problems = ex.vet(blocks[0] + "\n")
    assert any("pull_request" in p for p in problems)
    assert any("required_status_checks" in p for p in problems)


def test_vet_rejects_a_missing_for_each_because_the_import_address_dependson_it() -> None:
    no_each = ADOPTION.replace('  for_each = toset(["jolarca-consent"])\n\n', "")
    assert no_each != ADOPTION
    assert any("for_each" in p for p in ex.vet(no_each))


def test_write_warns_that_the_artifact_is_an_apply_trigger_path(
    tmp_path: pathlib.Path, capsys
) -> None:
    """The file this tool produces is `*.tf`, i.e. an `apply.yml` trigger path. Committing it before
    the import is a production apply whose plan wants to create a duplicate ruleset -- measured on
    2026-10-27 as `1 to add, 1 to change` with check_plan_safety.sh refusing it. The tool must say so
    at the moment it writes, not only in a runbook paragraph the operator may have scrolled past."""
    rb = write_runbook(tmp_path, ADOPTION)
    out = tmp_path / "rulesets.tf"
    assert ex.main(["--runbook", str(rb), "--out", str(out)]) == 0
    printed = capsys.readouterr().out
    assert "WARNING" in printed and "trigger" in printed.lower()
    assert "import" in printed


@pytest.mark.parametrize("rule", ["bypass_actors", "required_status_checks"])
def test_each_rule_shape_is_treated_as_mutation(rule: str) -> None:
    injected = ADOPTION.replace(
        "  rules {\n    deletion                = true",
        f"  rules {{\n    {rule} {{\n      x = true\n    }}\n    deletion                = true",
    )
    assert injected != ADOPTION
    assert ex.select(injected)[1] == []


# --- D-94: the generator used to be consent-only. These fixtures keep it multi-repo. -----------

VENDOR_ADOPTION = """```hcl
# rulesets-vendor.tf — D-46 option A, vendor next (D-93 step 1).
# Mirrors live ruleset 24138288 measured 2026-10-31; changes NOTHING about what GitHub enforces.
resource "github_repository_ruleset" "main" {
  for_each = toset(["jolarca-vendor"])

  repository  = each.value
  name        = "protect-main"
  target      = "branch"
  enforcement = "active"

  rules {
    deletion                = true
    non_fast_forward        = true
    required_linear_history = true
    # Deliberately absent: the live pull_request rule carries dismissal_restriction and
    # require_extra_approval_for_unattributed_changes, which provider 6.13.0 cannot send.
  }
}
```"""


def test_a_second_repository_can_be_adopted_by_name(tmp_path: pathlib.Path) -> None:
    """D-94's core defect: the selector matched a literal repo constant, so Step 6b was one-shot."""
    rb = write_runbook(tmp_path, VENDOR_ADOPTION)
    out = tmp_path / "rulesets-vendor.tf"
    assert ex.main(["--runbook", str(rb), "--repo", "jolarca-vendor", "--out", str(out)]) == 0
    assert 'toset(["jolarca-vendor"])' in out.read_text(encoding="utf-8")


def test_the_wrong_repo_is_refused_rather_than_silently_picking_the_only_block(
    tmp_path: pathlib.Path, capsys
) -> None:
    """The dangerous failure is not an error, it is a confident wrong choice: a runbook holding only
    consent's fence must never produce a file that imports consent while the operator asked for vendor."""
    rb = write_runbook(tmp_path, ADOPTION)
    out = tmp_path / "rulesets-vendor.tf"
    rc = ex.main(["--runbook", str(rb), "--repo", "jolarca-vendor", "--out", str(out)])
    assert rc == 1
    assert not out.exists(), "it wrote a block for the wrong repository"
    err = capsys.readouterr().err
    assert "jolarca-vendor" in err and "jolarca-consent" in err, err


def test_two_adoption_fences_for_two_repos_are_selected_independently(
    tmp_path: pathlib.Path,
) -> None:
    """The old single-candidate guard turned a second repo into an ambiguity. Target filtering is what
    makes both adoptable without ever guessing."""
    rb = write_runbook(tmp_path, ADOPTION + "\n\n" + VENDOR_ADOPTION)
    for repo, marker in (
        ("jolarca-consent", "D-46 option A, consent first"),
        ("jolarca-vendor", "vendor next"),
    ):
        out = tmp_path / f"out-{repo}.tf"
        assert ex.main(["--runbook", str(rb), "--repo", repo, "--out", str(out)]) == 0, repo
        assert marker in out.read_text(encoding="utf-8"), repo


def test_two_fences_for_the_same_repo_are_still_refused(tmp_path: pathlib.Path) -> None:
    """Per-repo selection must not weaken the original guarantee: ambiguity within one repo is fatal."""
    rb = write_runbook(tmp_path, VENDOR_ADOPTION + "\n\n" + VENDOR_ADOPTION)
    out = tmp_path / "dup.tf"
    assert ex.main(["--runbook", str(rb), "--repo", "jolarca-vendor", "--out", str(out)]) == 1
    assert not out.exists()


def test_the_emitted_import_command_carries_no_hardcoded_ruleset_id(
    tmp_path: pathlib.Path, capsys
) -> None:
    """D-94's sharpest edge: the old hint printed 'jolarca-consent:24087580' unconditionally, so for any
    other repo it produced a specific, plausible, WRONG command. A placeholder plus a discovery command
    cannot mislead."""
    rb = write_runbook(tmp_path, VENDOR_ADOPTION)
    out = tmp_path / "rulesets-vendor.tf"
    assert ex.main(["--runbook", str(rb), "--repo", "jolarca-vendor", "--out", str(out)]) == 0
    printed = capsys.readouterr().out
    assert "24087580" not in printed, "a literal ruleset id leaked back into the hint"
    assert "<ruleset-id>" in printed
    assert "gh api repos/jolarca-dev/jolarca-vendor/rulesets" in printed
    assert 'github_repository_ruleset.main["jolarca-vendor"]' in printed


def test_vet_reports_the_repo_it_was_asked_for_not_a_default_one() -> None:
    """A refusal that names the wrong repository sends the operator debugging the wrong file."""
    blocks = ex.fences(VENDOR_ADOPTION)
    problems = ex.vet(blocks[0] + "\n", "jolarca-consent")
    assert any("jolarca-consent" in p and "jolarca-vendor" in p for p in problems), problems
