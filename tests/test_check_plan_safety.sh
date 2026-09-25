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
