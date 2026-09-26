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
# STATUS 2026-09-26 — THESE RESOURCES CREATE NOTHING. terraform.tfvars sets
# var.enable_branch_protection = false, so local.protected_repos is empty and
# github_branch_protection.health has count = 0; local state holds zero
# github_branch_protection instances. On the Free plan protection is also
# unavailable for PRIVATE repos (HTTP 403 on the protection endpoint,
# .protected = false on the branch), so the "verified live / no-op plan" note
# above no longer holds for the seven private repos — only jolarca and .github
# are still guarded. Two further defects are recorded with this file:
#   1. The five attributes hardcoded false below contradict
#      policy/repo-defaults.yml#branch_protection.main, which requires strict,
#      dismiss_stale_reviews, require_code_owner_reviews, required_linear_history
#      and require_conversation_resolution to be TRUE. Enabling protection with
#      this HCL would make scripts/drift_detect.py report every repo `weakened`.
#      The "requires GitHub Pro" rationale is a PRIVATE-repo limitation and does
#      not apply to the nine public repos.
#   2. The fleet-wide flag cannot express "protect the public repos now, the
#      private ones after an upgrade"; it needs per-repo granularity.
# Open blocking gap: docs/drift-findings.md D-33.
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
    # strict mode disabled: requires GitHub Pro for private repos on free plan
    strict   = false
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
    # dismiss_stale_reviews disabled: requires GitHub Pro for private repos on free plan
    dismiss_stale_reviews = false
    # D-20: this is set false (see terraform.tfvars) — inert until teams exist,
    # and requires GitHub Pro for private repos on free plan.
    require_code_owner_reviews = var.require_code_owner_reviews
    require_last_push_approval = false
  }

  # ── Enforcement ───────────────────────────────────────────────────────────
  enforce_admins         = true
  require_signed_commits = var.enforce_signed_commits
  # required_linear_history and require_conversation_resolution disabled:
  # require GitHub Pro for private repos on free plan
  required_linear_history         = false
  require_conversation_resolution = false
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

  enforce_admins                  = true
  require_signed_commits          = false
  required_linear_history         = false
  require_conversation_resolution = false
  allows_force_pushes             = false
  allows_deletions                = false

  lifecycle {
    prevent_destroy = true
  }
}

# NOTE: Release-tag protection (v* tags) is enforced via GitHub Rulesets, which
# the integrations/github provider v6.x models as github_repository_ruleset.
# The 2026-09-17 delivery-chain audit verified NO rulesets exist org-wide.
# Ruleset definitions stay out of this baseline until the org ruleset strategy
# is finalized — see docs/runbooks.md RB-04 and docs/drift-findings.md D-07.
