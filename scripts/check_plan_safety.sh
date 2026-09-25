#!/usr/bin/env bash
# check_plan_safety.sh — refuse Terraform plans that a human must read first.
#
# SOC 2 CC8.1 / ISO 27001 A.8.32 / PCI-DSS 6.5.1. Referenced by
# policy/compliance-gates.yml as gate `plan_review`.
#
# This script exists because the equivalent check used to live inline in
# .github/workflows/apply.yml, where it could not be tested. Its visibility
# pattern was written as `visibility\s*:` but `terraform show` renders
# `+ visibility = "private"` / `~ visibility = "public" -> "private"` — a colon
# never appears. The gate therefore never fired, and the one control standing
# between an unattended apply and a fleet-wide visibility flip (D-01) was
# inert. Extracting it here makes it testable; see tests/fixtures/plan/*.txt.
#
# Usage: scripts/check_plan_safety.sh <plan.txt>
# Exit:  0 plan is safe to auto-apply
#        1 plan contains a refused action (destroy / replace / visibility)
#        2 the plan could not be read — cannot-check is NEVER treated as safe
set -uo pipefail

usage() {
  echo "usage: $0 <terraform-plan-text-file>" >&2
  exit 2
}

[ "$#" -eq 1 ] || usage
PLAN="$1"

if [ ! -f "$PLAN" ] || [ ! -r "$PLAN" ]; then
  echo "ERROR: plan file not readable: $PLAN" >&2
  echo "Refusing to proceed: an unreadable plan cannot be proven safe." >&2
  exit 2
fi

if [ ! -s "$PLAN" ]; then
  echo "ERROR: plan file is empty: $PLAN" >&2
  echo "An empty plan usually means 'terraform show' failed, not 'no changes'." >&2
  exit 2
fi

status=0

# Rendered plan lines are indented and prefixed with a change marker:
#   # <address> will be destroyed
#   # <address> must be replaced
#   ~ visibility = "public" -> "private"
#   + visibility = "private"
refuse() { # <label> <egrep-pattern> <why>
  local label="$1" pattern="$2" why="$3" hits
  hits="$(grep -nE "$pattern" "$PLAN" || true)"
  if [ -n "$hits" ]; then
    echo "::error::Plan contains ${label}. Manual review required."
    echo "  why: ${why}"
    while IFS= read -r hit; do
      printf '  %s\n' "$hit"
    done <<< "$hits"
    status=1
  fi
}

refuse "a destroy action" \
  '^[[:space:]]*#[[:space:]].*will be destroyed' \
  "prevent_destroy is set on every github_repository; a destroy means the fleet allow-list and the live org have diverged (possible deletion — open an incident)."

refuse "a replace action" \
  '^[[:space:]]*#[[:space:]].*must be replaced' \
  "Replacing a repository destroys and recreates it, losing issues, PRs, wiki and branch protection history."

# In-place visibility change only. A `+ visibility` line is initial creation,
# which is legitimate during bootstrap and is already constrained by
# validate_repos.py (confidential/restricted may not be declared public).
refuse "a repository visibility change" \
  '^[[:space:]]*~[[:space:]]+visibility[[:space:]]*=' \
  "Visibility flips are D-01: they change what is publicly readable inside a PCI-DSS/GDPR scope. Never auto-approved."

# Defense in depth: catch a visibility change rendered without a marker, e.g.
# by a future Terraform version or a `terraform show -json` conversion.
refuse "an unmarked visibility transition" \
  '^[[:space:]]*visibility[[:space:]]*=[[:space:]]*".*"[[:space:]]*->' \
  "Same as above, matched on the transition arrow rather than the change marker."

if [ "$status" -eq 0 ]; then
  echo "Plan contains no destroy, replace or visibility change."
fi
exit "$status"
