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
#        1 plan contains a refused action (destroy / replace / visibility /
#          branch-protection create or attribute change / security-feature
#          disable)
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
#   # <address> will be created
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

# ── Input format guard (found 2026-10-15) ────────────────────────────────────
# Measured on ONE plan file (tfplan7, 370 lines, 8 branch-protection resources changing):
#   terraform show tfplan        > coloured.txt   # 840 ESC bytes  -> this gate EXITED 0
#   terraform show -no-color     > plain.txt      #   0 ESC bytes  -> this gate EXITED 1
# Every pattern below anchors at line start, so ANSI colour bytes in front of `~`/`-`
# defeat all of them and a plan that changes branch protection reads as clean. CI was safe
# only by accident (apply.yml renders via `terraform show -json | jq -r`, which is plain).
# A verdict that depends on whether the author remembered a flag is not a control, so
# colourised input is refused as UNVERIFIABLE (exit 2) rather than passed: §3.
if LC_ALL=C grep -q "$(printf '\033')" "$PLAN" 2>/dev/null; then
  echo "::error::Plan text contains ANSI colour escapes — patterns cannot match across them." >&2
  echo "  why: measured 2026-10-15, the same plan exits 0 colourised and 1 plain. This is" >&2
  echo "       'cannot verify', not 'safe'. Re-render with 'terraform show -no-color tfplan'." >&2
  exit 2
fi

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

# Defense in depth: catch a visibility transition rendered without a marker, e.g.
# by a future Terraform version or a `terraform show -json` conversion.
refuse "an unmarked visibility transition" \
  '^[[:space:]]*visibility[[:space:]]*=[[:space:]]*".*"[[:space:]]*->' \
  "Same as above, matched on the transition arrow rather than the change marker."

# ── Protection-layer refusals (D-61, D-26) ───────────────────────────────────
# Added 2026-10-15 because the three rules above did NOT cover the only plan
# this root can actually produce today. A refreshed `terraform plan` rendered
# "3 to add, 25 to change" and this gate reported it safe to auto-apply: the
# creates and attribute changes were invisible to it. Unrefreshed state made the
# gate refuse, but only because stale `private` values produced visibility lines
# — a refusal that comes from staleness rather than from detection is not a
# control (AGENTS.md §7).

# github_branch_protection is live on the fleet but absent from state (created
# out-of-band, D-08), so Terraform renders it as a CREATE while the rule already
# exists. Applying that overwrites live protection with declared values nobody
# compared. Bootstrap of a genuinely new repo is refused too, on purpose: a
# human runs it, per AGENTS.md §4 (protection is high blast radius).
refuse "a branch-protection resource being created" \
  '^[[:space:]]*#[[:space:]].*github_branch_protection.*will be created' \
  "D-61/D-08: the fleet's protection rules were created out-of-band and are not in state, so a create means Terraform writes over rules it never adopted. Reconcile docs/state-migration-runbook.md step 6 (import or declare) first; the operator then applies by hand."

# Any change to a protection attribute, in either direction. Direction is not
# parsed because tightening looks identical to weakening in a plan diff
# (`~ strict = true -> false` and `false -> true`), and both need a human eye.
# The block-level names (`restrict_pushes`, `push_allowances`,
# `dismissal_restrictions`) are listed too because Terraform renders a REMOVED
# nested block with a `-` marker: 11 of the 25 changes in the real 2026-10-15
# plan were `- restrict_pushes { blocks_creations, push_allowances }` — deleting
# the "only these actors may push" rule. The first version of this rule matched
# only `~`, so it stared straight through the plan's dominant weakening.
#
# `+` is now in the marker class as well, for the mirror-image miss: an ADDED nested
# block renders `+ required_status_checks {`, and four of the 20 changes in the
# post-#73 plan are exactly that (jolarca-data, -identity, -legal, -security acquire
# required contexts they do not live with today). Matching only `[~-]` let the gate
# wave through the single tightening most likely to deadlock a merge — `jolarca-identity`
# declares contexts its workflows cannot report (D-44/D-47), so requiring them means no
# PR on that repo can ever merge. The refusal text already argued "either direction";
# the pattern did not implement it.
refuse "a branch-protection attribute change" \
  '^[[:space:]]*[~+-][[:space:]]+(require_signed_commits|require_code_owner_reviews|requires_approving_reviews|required_status_checks|required_pull_request_reviews|dismiss_stale_reviews|dismissal_restrictions|require_last_push_approval|required_linear_history|require_conversation_resolution|block_force_pushes|block_deletions|allows_force_pushes|allows_deletions|enforce_admins|strict|lock_branch|restrict_pushes|push_allowances|blocks_creations)[[:space:]]*(\{|=|->)' \
  "D-26: protection attributes are the gate between an unreviewed change and main. Weakening is a fleet-wide exposure; tightening can deadlock merges (a required context that no workflow can report — see the Context Parity class). Either way a human reads it."

# Security-feature switches. Terraform renders the change on the NESTED `status`
# attribute inside `security_and_analysis { secret_scanning { … } }`, so matching
# on the feature name alone never fires on real output — the first draft of this
# rule was inert against the very plan it was written for. The nested `status`
# line is matched directly, in the disable direction only: the real 2026-10-15
# plan moves several repos `"disabled" -> "enabled"`, and refusing that would
# block the fix this repo exists to make.
refuse "a security feature being disabled" \
  '^[[:space:]]*~[[:space:]]+(secret_scanning|secret_scanning_push_protection|dependabot_security_updates|vulnerability_alerts|has_security_policies)[[:space:]]*=.*(->[[:space:]]*(false|"disabled"))' \
  "compliance-gates.yml declares secret scanning, push protection and Dependabot alerts mandatory; a plan that turns one off is a compliance regression, not a cleanup."

refuse "a security feature being disabled (nested status form)" \
  '^[[:space:]]*~[[:space:]]+status[[:space:]]*=[[:space:]]*"enabled"[[:space:]]*->[[:space:]]*"disabled"' \
  "Same rule, real Terraform rendering: the transition lives on a nested status attribute under security_and_analysis, not on the feature name. Enabling (disabled -> enabled) is deliberately not refused."

if [ "$status" -eq 0 ]; then
  echo "Plan contains no destroy, replace, visibility change, protection-layer change or security-feature disable."
fi
exit "$status"
