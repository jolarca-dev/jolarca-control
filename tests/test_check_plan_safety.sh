#!/usr/bin/env bash
# test_check_plan_safety.sh — regression tests for the plan-safety gate.
#
# The inline apply.yml check this replaced was broken for its entire life
# because nothing exercised it. These cases are derived from real
# `terraform show -no-color` output (verified 2026-09-25 against an offline
# plan of this root), not from guesses about the format.
#
# Usage: bash tests/test_check_plan_safety.sh
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GATE="$ROOT/scripts/check_plan_safety.sh"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

pass=0
fail=0

# assert <expected-exit> <fixture-name> <<'PLAN'
assert() {
  local want="$1" name="$2" f="$TMP/$2.txt" got
  cat > "$f"
  bash "$GATE" "$f" >"$TMP/$name.out" 2>&1
  got=$?
  if [ "$got" -eq "$want" ]; then
    printf 'ok   %-28s exit=%s\n' "$name" "$got"
    pass=$((pass + 1))
  else
    printf 'FAIL %-28s want exit=%s got=%s\n' "$name" "$want" "$got"
    sed 's/^/       /' "$TMP/$name.out"
    fail=$((fail + 1))
  fi
}

# ── Must be REFUSED (exit 1) ─────────────────────────────────────────────────
assert 1 visibility-flip <<'PLAN'
Terraform will perform the following actions:

  # github_repository.repo["jolarca-data"] will be updated in-place
  ~ resource "github_repository" "repo" {
        id               = "jolarca-data"
        name             = "jolarca-data"
      ~ visibility       = "private" -> "public"
    }

Plan: 0 to add, 1 to change, 0 to destroy.
PLAN

assert 1 visibility-flip-public-to-private <<'PLAN'
  # github_repository.repo["jolarca-legal"] will be updated in-place
  ~ resource "github_repository" "repo" {
      ~ visibility = "public" -> "private"
    }
PLAN

assert 1 destroy <<'PLAN'
  # github_repository.repo["jolarca-data"] will be destroyed
  - resource "github_repository" "repo" {
      - name = "jolarca-data" -> null
    }

Plan: 0 to add, 0 to change, 1 to destroy.
PLAN

assert 1 replace <<'PLAN'
  # github_repository.repo["jolarca"] must be replaced
  -/+ resource "github_repository" "repo" {
      ~ name = "jolarca" -> "jolarca-app"
    }
PLAN

assert 1 unmarked-visibility-transition <<'PLAN'
        visibility = "private" -> "public"
PLAN

# ── Protection-layer refusals (D-61 / D-26), added 2026-10-15 ────────────────
# These four negative controls exist because the gate passed a REAL plan it
# should have refused: a refreshed `terraform plan` on 2026-10-15 rendered
# "3 to add, 25 to change" — including branch-protection creates for repos
# whose live rules were never imported, and `~ required_status_checks {` on the
# rest — and exited 0. Shapes below are transcribed from `terraform show`.
assert 1 protection-create-unimported <<'PLAN'
  # github_branch_protection.main["jolarca-consent"] will be created
  + resource "github_branch_protection" "main" {
      + enforce_admins = true
      + pattern        = "main"
      + repository     = "jolarca-consent"
    }
PLAN

assert 1 protection-weaken-code-owner <<'PLAN'
  # github_branch_protection.main["jolarca-docs"] will be updated in-place
  ~ resource "github_branch_protection" "main" {
        id                          = "MDP:1234"
      ~ require_code_owner_reviews  = true -> false
      ~ required_pull_request_reviews {
        }
    }
PLAN

assert 1 protection-status-checks-change <<'PLAN'
  # github_branch_protection.main["jolarca"] will be updated in-place
  ~ resource "github_branch_protection" "main" {
      ~ required_status_checks {
          ~ contexts = [
              - "ci",
            ]
          ~ strict   = true -> false
        }
    }
PLAN

assert 1 security-feature-disabled <<'PLAN'
  # github_repository.repo["jolarca-vendor"] will be updated in-place
  ~ resource "github_repository" "repo" {
      ~ secret_scanning              = true -> false
      ~ secret_scanning_push_protection = true -> false
    }
PLAN

# Added 2026-10-15 after the first version of these rules was written against an
# imagined rendering. Terraform puts the transition on a NESTED `status` and marks
# a removed block with `-`, so both of the real weakenings slipped past. Fixtures
# below are transcribed from `terraform show` of the live plan.
assert 1 protection-restrict-pushes-removed <<'PLAN'
  # github_branch_protection.main["jolarca-compliance"] will be updated in-place
  ~ resource "github_branch_protection" "main" {
        id                              = "BPR_kwDOT4w_Rs4FCtBP"
      - restrict_pushes {
          - blocks_creations = false -> null
          - push_allowances  = [] -> null
        }
    }
PLAN

assert 1 secret-scanning-nested-disable <<'PLAN'
  # github_repository.repo["jolarca-docs"] will be updated in-place
  ~ resource "github_repository" "repo" {
      ~ security_and_analysis {
          ~ secret_scanning {
              ~ status = "enabled" -> "disabled"
            }
        }
    }
PLAN

# Transcribed verbatim from `terraform show -no-color` of the live post-#73 plan. An ADDED
# nested block carries `+`, not `~` or `-`, and four of the 20 changes are `+ required_status_checks`
# — including jolarca-identity, whose declared contexts its workflows cannot report (D-44/D-47),
# which would deadlock every merge on that repo. The `[~-]`-only pattern missed all four.
assert 1 protection-status-checks-added <<'PLAN'
  # github_branch_protection.main["jolarca-data"] will be updated in-place
  ~ resource "github_branch_protection" "main" {
        id                              = "BPR_kwDOT5dta84FAePQ"
        # (10 unchanged attributes hidden)

      + required_status_checks {
          + contexts = [
              + "ci",
              + "compliance",
              + "security",
            ]
          + strict   = true
        }

        # (2 unchanged blocks hidden)
    }
PLAN

# ── Repository rulesets (D-84) ────────────────────────────────────────────────
# Every protection pattern above is scoped to `github_branch_protection`: the create rule
# matches that address, and the attribute rule lists its attribute names. jolarca-consent,
# jolarca-dr and jolarca-vendor are protected by RULESETS (D-46), so from 2026-10-15 until
# this PR the gate had no rule that could see them. Measured before the fix, with these two
# inputs: a ruleset create carrying only push rules exited 0, and an update that set
# `enforcement = "active" -> "disabled"`, turned deletion and non_fast_forward off and added
# a RepositoryAdmin bypass actor ALSO exited 0 — i.e. the brake that AGENTS.md §8 calls "what
# actually stands between a merge and an apply" reported the total removal of a GDPR-scoped
# repo's protection as safe to auto-apply. Case A below is the exact shape consent's live
# ruleset (24087580) renders in, transcribed from `gh api repos/…/rulesets/24087580`.
assert 1 ruleset-create-push-only <<'PLAN'
Terraform will perform the following actions:

  # github_repository_ruleset.main["jolarca-consent"] will be created
  + resource "github_repository_ruleset" "main" {
      + enforcement = "active"
      + name        = "protect-main"
      + repository  = "jolarca-consent"
      + target      = "branch"
      + rules {
          + deletion         = true
          + non_fast_forward = true
        }
      + conditions {
          + ref_name {
              + include = ["~DEFAULT_BRANCH"]
            }
        }
    }

Plan: 1 to add, 0 to change, 0 to destroy.
PLAN

# The dangerous one: nothing here is named in the legacy attribute list, and the aggregate
# verdict says "1 to change, 0 to destroy", so a whole-state `-auto-approve` apply would
# have run it. A `+ bypass_actors` block is how an attacker-shaped config hands admins a
# way around main.
assert 1 ruleset-enforcement-disabled <<'PLAN'
Terraform will perform the following actions:

  # github_repository_ruleset.main["jolarca-consent"] will be updated in-place
  ~ resource "github_repository_ruleset" "main" {
      ~ enforcement = "active" -> "disabled"
        name        = "protect-main"
      ~ rules {
          ~ deletion         = true -> false
          ~ non_fast_forward = true -> false
        }
      ~ bypass_actors {
          + actor_type  = "RepositoryAdmin"
            bypass_mode = "always"
            id          = 0
        }
    }

Plan: 0 to add, 1 to change, 0 to destroy.
PLAN

# Organization rulesets are the same object class at a higher blast radius: one
# `github_organization_ruleset` covers every repository in jolarca-dev, and the provider
# models it with the same `enforcement` / `bypass_actors` / `rules` vocabulary.
assert 1 organization-ruleset-weakened <<'PLAN'
Terraform will perform the following actions:

  # github_organization_ruleset.default["block-force-push"] will be updated in-place
  ~ resource "github_organization_ruleset" "default" {
      ~ enforcement = "active" -> "evaluate"
      ~ conditions {
          ~ repository_id = [
              - 1387897455,
            ]
        }
    }

Plan: 0 to add, 1 to change, 0 to destroy.
PLAN

# Non-vacuity of the new rules: a ruleset that is merely REFRESHED and reported unchanged
# must stay clean. This is Terraform's real refresh line for the address, not an invented
# one — refusing it would mean every plan of this root dies once a ruleset is in state, and
# a gate that always refuses is indistinguishable from a gate that detects nothing.
assert 0 ruleset-refresh-only-noise <<'PLAN'
github_repository_ruleset.main["jolarca-consent"]: Refreshing state... [id=24087580]
github_repository.repo["jolarca-consent"]: Refreshing state... [id=r_KslIM0B99HlbgDzu]

No changes. Your infrastructure matches the configuration.
PLAN

# Colourised input is the fourth way this gate was fooled, and it was found by running the
# same plan twice: `terraform show tfplan` (colour on) exited 0 while `terraform show
# -no-color tfplan` exited 1 on the identical 370-line plan, because every pattern here
# anchors at line start and ANSI bytes sit in front of the markers. Colourised text is now
# exit 2 (cannot verify). The pair below proves both halves: the guard fires, and it is the
# FORMAT that changed — strip the escapes and the same content is still refused.
colour_case() {
  local name="$1" want="$2" f="$TMP/$1.txt" got
  printf '' > "$f"
  { printf '  # github_branch_protection.main["jolarca"] will be updated in-place\n'
    printf '  # github_repository.repo["jolarca"] will be updated in-place\n'
    printf '  ~ resource "github_branch_protection" "main" {\n'
    printf '  \033[0m~ required_status_checks {\n'
    printf '  \033[0m~ strict   = true -> false\n'
    printf '        }\n    }\n'; } >> "$f"
  bash "$GATE" "$f" >"$TMP/$name.out" 2>&1
  got=$?
  if [ "$got" -eq "$want" ]; then
    printf 'ok   %-28s exit=%s\n' "$name" "$got"
    pass=$((pass + 1))
  else
    printf 'FAIL %-28s want exit=%s got=%s\n' "$name" "$want" "$got"
    sed 's/^/       /' "$TMP/$name.out"
    fail=$((fail + 1))
  fi
}
colour_case coloured-plan 2

# Non-vacuity for the guard: the escape-stripped twin of the same fixture must still be
# refused, so a passing guard cannot be hiding a broken protection rule.
stripped_case() {
  local f="$TMP/coloured-plan.txt" out="$TMP/stripped-plan.txt" esc
  # GNU sed does not expand \033 inside a BRE, so the escape byte comes from printf.
  esc=$(printf '\033')
  sed "s/${esc}\[0m//g" "$f" > "$out"
  bash "$GATE" "$out" >"$TMP/stripped.out" 2>&1
  local got=$?
  if [ "$got" -eq 1 ]; then
    printf 'ok   %-28s exit=%s\n' "stripped-still-refused" "$got"
    pass=$((pass + 1))
  else
    printf 'FAIL %-28s want exit=1 got=%s\n' "stripped-still-refused" "$got"
    sed 's/^/       /' "$TMP/stripped.out"
    fail=$((fail + 1))
  fi
}
stripped_case

# ── Must be ALLOWED (exit 0) ─────────────────────────────────────────────────
# Real shape of the bootstrap plan: every repo created, visibility SET (not
# changed). Refusing this would block the legitimate first apply.
assert 0 create-only-sets-visibility <<'PLAN'
  # github_repository.repo["jolarca-control"] will be created
  + resource "github_repository" "repo" {
      + allow_merge_commit = false
      + name               = "jolarca-control"
      + visibility         = "private"
    }

Plan: 6 to add, 0 to change, 0 to destroy.
PLAN

assert 0 no-op-plan <<'PLAN'
github_repository.repo["jolarca"]: Refreshing state... [id=jolarca]

No changes. Your infrastructure matches the configuration.
PLAN

assert 0 unrelated-attribute-change <<'PLAN'
  # github_repository.repo["jolarca"] will be updated in-place
  ~ resource "github_repository" "repo" {
        id          = "jolarca"
      ~ description = "old" -> "new"
        visibility  = "public"
    }
PLAN

# Non-vacuity in the other direction: a refresh that reads a protection rule and
# finds nothing to change must NOT be refused, or the new rules would be a
# blanket block and someone would delete them under pressure (AGENTS.md §5).
assert 0 protection-refresh-no-change <<'PLAN'
github_branch_protection.main["jolarca"]: Refreshing state... [id=MDP:1234]

No changes. Your infrastructure matches the configuration.
PLAN

# Strengthening a security feature is allowed by design: only the disable
# direction is refused, so the gate does not fight the fix it is meant to permit.
assert 0 security-feature-enabled <<'PLAN'
  # github_repository.repo["jolarca-security"] will be updated in-place
  ~ resource "github_repository" "repo" {
      ~ secret_scanning                 = false -> true
      ~ secret_scanning_push_protection = false -> true
    }
PLAN

# The nested form of the same allowance. The live 2026-10-15 plan turns secret
# scanning ON for five repos; if the refusal rule caught enabling, no apply could
# ever land that fix and someone would eventually delete the rule (AGENTS.md §5).
assert 0 security-and-analysis-nested-enabling <<'PLAN'
  # github_repository.repo["jolarca-docs"] will be updated in-place
  ~ resource "github_repository" "repo" {
        name         = "jolarca-docs"
      ~ has_projects = true -> false
      ~ security_and_analysis {
          ~ secret_scanning {
              ~ status = "disabled" -> "enabled"
            }
          ~ secret_scanning_push_protection {
              ~ status = "disabled" -> "enabled"
            }
        }
    }

Plan: 0 to add, 1 to change, 0 to destroy.
PLAN

# ── Cannot-check must NEVER be safe (exit 2) ─────────────────────────────────
: > "$TMP/empty.txt"
bash "$GATE" "$TMP/empty.txt" >/dev/null 2>&1
if [ $? -eq 2 ]; then
  printf 'ok   %-28s exit=2\n' "empty-plan-refused"
  pass=$((pass + 1))
else
  printf 'FAIL %-28s want exit=2\n' "empty-plan-refused"
  fail=$((fail + 1))
fi

bash "$GATE" "$TMP/does-not-exist.txt" >/dev/null 2>&1
if [ $? -eq 2 ]; then
  printf 'ok   %-28s exit=2\n' "missing-plan-refused"
  pass=$((pass + 1))
else
  printf 'FAIL %-28s want exit=2\n' "missing-plan-refused"
  fail=$((fail + 1))
fi

# ── "Not a plan at all" must be exit 2, never exit 0 (measured 2026-10-19) ─────
# Two inputs reached this gate in CI and both were reported SAFE:
#   1. plan.yml's `Record skipped plan` step writes prose into plan-output.txt, and
#      the gate read it as "no destroy, no visibility change" -> exit 0.
#   2. run 39062414977 (rerun 2026-10-19): `Terraform Init` died with
#      `Error: Failed to read organization "jolarca-dev" ... unauthorized`, and a
#      plan-output.txt carrying only that error also exited 0.
# A verdict of "safe to auto-apply" on text that is not a rendered plan is the D-22
# class again: the gate answers a question nobody asked (AGENTS.md §7). The guard
# below is deliberately ordered AFTER the refusal rules, so a plan-shaped input with
# a refused action still exits 1 -- see the non-vacuity case at the end.
assert 2 not-a-plan-workflow-stub <<'PLAN'
terraform plan SKIPPED — STATE_MIGRATION_COMPLETE is not 'true'.

The variable is the operator's switch on this workflow, nothing more.
State itself already lives in the HCP Terraform workspace
jolarca-dev/jolarca-control (see docs/state-migration-runbook.md,
status COMPLETE 2026-10-10) and the legacy jolarca-infrastructure root
was drained of github_* resources by `terraform state rm` (D-13), so
this control plane IS the sole declarative owner.

No plan was produced, so no apply may proceed from this run.
Validate + fmt + init-only checks above DID run and passed.
PLAN

assert 2 not-a-plan-error-output <<'PLAN'
Initializing HCP Terraform...

Error: Failed to read organization "jolarca-dev" at host app.terraform.io

  on main.tf line 28, in terraform:
  28:     organization = "jolarca-dev"

Encountered an unexpected error while reading the organization settings:
unauthorized
PLAN

# Non-vacuity for the guard: real plan output carries warning noise and refresh
# lines around the markers. If this flips to 2, the guard is matching too narrowly
# and would fail every honest plan closed.
assert 0 plan-shaped-with-warning-noise <<'PLAN'
Warning: Value for previously declared attribute is null

  on repositories.tf line 93, in resource "github_repository_vulnerability_alerts" "repo":

github_repository.repo["jolarca"]: Refreshing state... [id=jolarca]
github_branch_protection.main["jolarca"]: Refreshing state... [id=MDP:1234]

No changes. Your infrastructure matches the configuration.
PLAN

echo
echo "plan-gate tests: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
