# ──────────────────────────────────────────────────────────────────────────────
# Branch Protection — enforced on `main` for every fleet repository
# ──────────────────────────────────────────────────────────────────────────────
# Implements SOC 2 CC6.1/CC8.1, ISO 27001 A.5.1/A.8.1, PCI-DSS 6.3
#
# Every value below was verified against the live GitHub API on 2026-09-25 for
# all six jolarca-dev repositories, so the first post-migration plan should be
# a no-op for branch protection. Per-repo required status-check contexts live
# in repos/*.yml because they legitimately differ per repository.
#
# Supersedes: jolarca-infrastructure/terraform/modules/github-org/
#             branch-protection.tf
# ──────────────────────────────────────────────────────────────────────────────
# STATUS 2026-09-28 — THE SAFE FOUR ARE NOW ENABLED. Pre-deployment audit B3
# recommended shipping require_linear_history, require_conversation_resolution,
# strict status checks, and dismiss_stale_reviews. These four work on the Free
# plan for PUBLIC repos (jolarca, .github). They remain unavailable for PRIVATE
# repos without GitHub Pro (D-33). terraform.tfvars still sets
# var.enable_branch_protection = false, so these resources still create nothing
# until the operator flips the flag. Two attributes remain off:
#   - require_code_owner_reviews: false (D-20, solo-era deviation — inert with
#     a single operator who cannot approve their own PR; pre-deployment audit B3
#     confirmed the "safe four" approach with a dated deviation for this flag).
#   - require_signed_commits: false (D-05, provider automation cannot sign).
# Open blocking gap: docs/drift-findings.md D-33 (private repos unguarded).
# ──────────────────────────────────────────────────────────────────────────────

locals {
  # Repos that declare branch protection in their allow-list entry. The org
  # health repo is handled separately below — it carries a deliberately
  # minimal rule (content-only repo, no CI to gate on).
  protected_repos = {
    for name, def in local.repo_defs : name => def
    if can(def.branch_protection.main) && var.enable_branch_protection
  }
}

resource "github_branch_protection" "main" {
  for_each = local.protected_repos

  repository_id = github_repository.repo[each.key].node_id
  pattern       = lookup(each.value.branch_protection.main, "pattern", "main")

  # ── Required status checks ────────────────────────────────────────────────
  required_status_checks {
    # strict mode: requires up-to-date branches. Works on Free for PUBLIC repos;
    # private repos need GitHub Pro (D-33). Enabled now so public repos get it.
    strict   = true
    contexts = each.value.branch_protection.main.required_status_checks.contexts
  }

  # ── Pull-request reviews ──────────────────────────────────────────────────
  required_pull_request_reviews {
    # SOLO-ERA DEVIATION: 0 approving reviews (docs/security/key-custody.md,
    # docs/drift-findings.md D-04). checkov CKV_GIT_5 equivalent — with one
    # operator a count of 1+ is unsatisfiable and would lock the maintainer
    # out. Enforcement rides on the required status checks above. Raise when
    # the second operator onboards.
    required_approving_review_count = var.required_approving_review_count
    # dismiss_stale_reviews: works on Free for PUBLIC repos; private need Pro (D-33).
    dismiss_stale_reviews = true
    # D-20: this is set false (see terraform.tfvars) — inert until teams exist,
    # and requires GitHub Pro for private repos on free plan.
    require_code_owner_reviews = var.require_code_owner_reviews
    require_last_push_approval = false
  }

  # ── Enforcement ───────────────────────────────────────────────────────────
  enforce_admins         = true
  require_signed_commits = var.enforce_signed_commits
  # required_linear_history and require_conversation_resolution: enabled for
  # public repos (Free plan). Private repos need GitHub Pro (D-33).
  # Works on Free for PUBLIC repos; private repos need Pro (D-33).
  required_linear_history = true
  # Works on Free for PUBLIC repos; private repos need Pro (D-33).
  require_conversation_resolution = true
  allows_force_pushes             = false
  allows_deletions                = false

  lifecycle {
    prevent_destroy = true
  }
}

# ── Org community-health repo (.github) ──────────────────────────────────────
# Deliberately minimal: a content-only repo with no CI, so requiring status
# checks would block every change forever. Verified live state 2026-09-25:
# enforce_admins=true, dismiss_stale_reviews=true, zero required contexts,
# require_code_owner_reviews=FALSE, linear history and conversation resolution
# OFF. Note a `.github/CODEOWNERS` file IS present in that repository — the
# REQUIREMENT is off, not the file. Its entries name jolarca-dev teams that do
# not exist, so enabling the requirement would change nothing (D-20). Because
# this repo's rule is deliberately weaker than the fleet baseline, it is listed
# in policy/repo-defaults.yml `branch_protection_baseline_exempt`; drift_detect
# still asserts that a protection rule EXISTS here.
resource "github_branch_protection" "health" {
  count = var.enable_branch_protection ? 1 : 0

  repository_id = github_repository.health.node_id
  pattern       = "main"

  required_status_checks {
    strict   = false
    contexts = []
  }

  required_pull_request_reviews {
    required_approving_review_count = 0
    dismiss_stale_reviews           = true
    require_code_owner_reviews      = false
    require_last_push_approval      = false
  }

  enforce_admins         = true
  require_signed_commits = false
  # Works on Free for PUBLIC repos; private repos need Pro (D-33).
  required_linear_history = true
  # Works on Free for PUBLIC repos; private repos need Pro (D-33).
  require_conversation_resolution = true
  allows_force_pushes             = false
  allows_deletions                = false

  lifecycle {
    prevent_destroy = true
  }
}

# NOTE: Release-tag protection (v* tags) would be enforced via GitHub Rulesets,
# which the integrations/github provider models as github_repository_ruleset.
# The 2026-09-17 audit's conclusion that NO rulesets exist org-wide is now FALSE
# and was superseded by measurement on 2026-10-04 (D-46): three repositories
# -- jolarca-vendor, jolarca-consent, jolarca-dr -- carry an ACTIVE ruleset
# named protect-main, created 2026-09-28, i.e. eleven days after that audit and
# outside this configuration. Org-wide ruleset listing is unavailable on the
# current plan (HTTP 403), so this repo cannot enumerate them centrally; the
# per-repo endpoint can, and scripts/drift_detect.py now does exactly that
# because the legacy /protection endpoint returns 404 for ruleset-protected
# branches and previously filed that as an unreadable plan limitation.
# Consequence to keep in view: that layer is real enforcement with no declared
# source of truth. `terraform apply` neither creates, repairs nor destroys it,
# and `terraform destroy` would not notice it. Ruleset definitions stay out of
# this baseline only until the strategy in RB-04 / D-07 is decided -- see D-46.
