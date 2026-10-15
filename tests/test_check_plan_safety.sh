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

echo
echo "plan-gate tests: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
