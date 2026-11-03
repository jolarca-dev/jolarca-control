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
# inert. Extracting it here makes it testable; the fixtures are the inline
# heredoc cases in tests/test_check_plan_safety.sh (25 of them as of 2026-10-19,
# 29 as of 2026-10-26 after D-84 added the ruleset class).
#
# Usage: scripts/check_plan_safety.sh <plan.txt>
# Exit:  0 plan is safe to auto-apply
#        1 plan contains a refused action (destroy / replace / visibility /
#          branch-protection create or attribute change / ruleset create or any
#          ruleset change (D-84) / security-feature disable)
#        2 the plan could not be read — cannot-check is NEVER treated as safe.
#          This covers a missing file, an empty file, ANSI-coloured input, and
#          (since 2026-10-19) input that is not a rendered Terraform plan at
#          all: an error block or workflow prose used to exit 0, which reads as
#          "safe to auto-apply" for a plan that never happened.
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

# ── Ruleset-layer refusals (D-84) ────────────────────────────────────────────
# The two rules above are scoped to `github_branch_protection` — by address in the create
# rule, by attribute name in the change rule. jolarca-consent (24087580), jolarca-dr
# (24136490) and jolarca-vendor (24138288) are protected by repository RULESETS (D-46), and
# no ruleset vocabulary appears in either pattern. Measured 2026-10-26 against the unfixed
# gate: a plan creating a ruleset with only push rules exited 0, and a plan rendering
# `~ enforcement = "active" -> "disabled"` plus `~ deletion = true -> false` plus a new
# `RepositoryAdmin` bypass actor ALSO exited 0. The second is the total removal of
# protection on a GDPR-scoped tier-1 repo, reported by the brake AGENTS.md §8 names as "what
# actually stands between a merge and an apply" as safe to `terraform apply -auto-approve`.
# The hole was latent while nothing declared a ruleset resource; it becomes live the moment
# D-46 option A imports one, which is why this fix lands BEFORE any ruleset config.
#
# Anchored on the action line Terraform prints for every changed resource (`  # <address>
# will be created` / `will be updated in-place` / `must be replaced` / `will be destroyed`),
# not on attribute names, because a ruleset's whole surface — `enforcement`, `target`,
# `conditions.ref_name`, `bypass_actors`, `rules.creation` — is either absent from the legacy
# list or too generic (`update`, `include`, `exclude`, `name`) to list without refusing
# unrelated resources. Any change to a ruleset is by definition a protection-layer change,
# so unlike the security-feature rule above there is no "safe direction" to let through:
# requiring a context that no workflow reports (tightening) deadlocks a merge exactly as
# dropping one exposes main. `Refreshing state... [id=…]` lines do not start with `#`, so a
# fixtures 'ruleset-refresh-only-noise' and the pre-fix measurement in
# docs/drift-findings.md D-84 pin both halves. NOTE for anyone editing the reason
# strings below: they are DOUBLE-quoted shell arguments, so a backtick inside one is
# command substitution, not typography — shellcheck SC2006/SC2283 catches it and
# `make lint` runs shellcheck. Use single quotes for code fragments here.
refuse "a ruleset resource being created" \
  '^[[:space:]]*#[[:space:]].*github_(repository|organization)_ruleset.*will be created' \
  "D-84/D-46: a ruleset create means Terraform writing a protection object it never adopted (the three fleet rulesets were created out-of-band on 2026-09-28), or adding one beside the ruleset that already bites — GitHub enforces the union of both layers, so a create is never a no-op. Import it: terraform import '<address>' '<repo>:<ruleset_id>' (the provider's parseID2 splits on ':', so a bare numeric id fails to parse), or delete the ruleset out-of-band, then apply by hand."

refuse "any other change to a ruleset resource" \
  '^[[:space:]]*#[[:space:]].*github_(repository|organization)_ruleset.*(will be updated in-place|must be replaced|will be destroyed)' \
  "D-84/D-26: ruleset attributes are the same control surface as branch protection and none of them are in the legacy attribute list — 'enforcement = active -> disabled' turns protection off for every branch it matches while this gate's patterns stare through it. A provider that does not model a live field (6.13.0 omits 'dismissal_restriction' and 'require_extra_approval_for_unattributed_changes') also means an update silently resets what it never read. A human reads the diff first."

# Belt for the same class if a future Terraform stops printing the action line: the resource
# header itself carries the change marker, and ruleset-only attribute tokens catch a nested
# rendering. `+` is included deliberately — a create the action line does not announce is
# worse than one that does. The token list is limited to names no other resource in this
# root can produce: 'update', 'creation', 'deletion', 'include', 'exclude', 'target' and
# 'name' are real ruleset attributes but too generic to list here without refusing unrelated
# resources, and every change that touches only those still trips the address rules above.
refuse "a ruleset resource block marked for change (rendering belt)" \
  '^[[:space:]]*[~+-][[:space:]]+resource[[:space:]]+"github_(repository|organization)_ruleset"' \
  "D-84: same coverage as the two rules above, matched on the resource header instead of the action line, so a change in Terraform's rendering cannot silently narrow the refusal."

refuse "a ruleset attribute change (ruleset-only vocabulary)" \
  '^[[:space:]]*[~+-][[:space:]]+(enforcement|bypass_actors|actor_type|bypass_mode|non_fast_forward|update_allows_fetch_and_merge|required_signatures|strict_required_status_checks_policy|do_not_enforce_on_create|required_check|integration_id|allowed_merge_methods|dismiss_stale_reviews_on_push|require_code_owner_review|require_last_push_approval|required_review_thread_resolution|required_reviewers|ref_name|required_deployments|required_deployment_environments|merge_queue|copilot_code_review|file_path_restriction|file_extension_restriction|max_file_size|max_file_path_length|branch_name_pattern|tag_name_pattern|commit_message_pattern|committer_email_pattern|commit_author_email_pattern)[[:space:]]*(\{|=|->)' \
  "D-84/D-26: these tokens exist only on ruleset objects in this root, so a hit is unambiguous — and a ruleset has no safe direction: 'enforcement' off removes protection, 'required_check' on a context no workflow reports deadlocks every merge on that repo (the A-01/FA-control-03 shape). Either way a human reads it."

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
  # ── Plan-shape guard (found 2026-10-19, run 39062414977) ───────────────────
  # Two non-plans were reported SAFE by this gate:
  #   * plan.yml's `Record skipped plan` step writes prose into plan-output.txt,
  #     and `Plan safety check` exited 0 on it;
  #   * `Terraform Init` failed with `Error: Failed to read organization
  #     "jolarca-dev" ... unauthorized`, and a plan-output.txt containing only
  #     that error also exited 0.
  # Both matched nothing because every refusal pattern here looks for a change
  # marker — and an input with no markers is indistinguishable from a clean plan.
  # Silence is not evidence of absence here (§7: verify the verifier), so an input
  # that does not look like rendered Terraform at all is UNVERIFIABLE, exit 2.
  #
  # Ordered deliberately AFTER the refusal rules: a plan-shaped input carrying a
  # destroy still exits 1, so this guard can never mask a real refusal.
  if ! grep -qE '^[[:space:]]*#[[:space:]]+.+(will be|must be) |^[[:space:]]*[~+-][[:space:]]*[-+]?/?resource[[:space:]]+"|^Terraform will perform|^Plan:[[:space:]]+[0-9]+ to add|^No changes|Refreshing state\.\.\.' "$PLAN"; then
    echo "::error::Input is not a rendered Terraform plan — no plan header, no resource action line, no change marker and no 'No changes' verdict."
    echo "  why: refusing to call unparseable text safe. Measured 2026-10-19: workflow prose and a"
    echo "       bare 'Error: ... unauthorized' block both exited 0 here. Check the step that wrote"
    echo "       this file — if the plan never ran, nothing downstream may treat it as reviewed."
    exit 2
  fi

  echo "Plan contains no destroy, replace, visibility change, protection-layer change (branch protection or ruleset) or security-feature disable."
fi
exit "$status"
