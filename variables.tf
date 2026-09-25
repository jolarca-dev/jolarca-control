# ──────────────────────────────────────────────────────────────────────────────
# Variables — Jolarca Control Plane
# ──────────────────────────────────────────────────────────────────────────────
# Values here are the CONFIG OF RECORD for the jolarca-dev marketplace org.
# Where a default encodes verified live reality rather than aspiration, the
# gap is registered in docs/drift-findings.md (D-nn) — do not "fix" a default
# here without first recording the decision there.
# ──────────────────────────────────────────────────────────────────────────────

variable "github_org" {
  description = "GitHub organization name (marketplace scope)."
  type        = string
  default     = "jolarca-dev"

  validation {
    condition     = var.github_org == "jolarca-dev"
    error_message = "This control plane governs jolarca-dev ONLY. Mission-platform repos (journeyoflife-org) are governed by jol-control; mixing the two violates ADR-0004 mission/marketplace separation."
  }
}

variable "environment" {
  description = "Deployment environment (dev, staging, prod)"
  type        = string
  default     = "prod"

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Environment must be one of: dev, staging, prod."
  }
}

variable "default_license" {
  description = "Default SPDX license identifier applied to repos that do not declare their own license_template."
  type        = string
  default     = "agpl-3.0"
}

# ── Review policy ────────────────────────────────────────────────────────────
# SOLO-ERA DEVIATION (carried from jolarca-infrastructure, tracked in
# docs/security/key-custody.md). Verified against the live API on 2026-09-25:
# every jolarca-dev repo currently has required_approving_review_count = 0.
# With a single operator, 1+ approving reviews are unsatisfiable and would
# lock the sole maintainer out. Enforcement rides on required status checks.
# Raise this to 1 when the second operator onboards — but only AFTER D-20 is
# remediated (create jolarca-dev teams, rewrite the six .github/CODEOWNERS to
# reference them). See docs/drift-findings.md D-04 and D-20.
variable "required_approving_review_count" {
  description = "Minimum number of approving reviews required before merge."
  type        = number
  default     = 0

  validation {
    condition     = var.required_approving_review_count >= 0 && var.required_approving_review_count <= 6
    error_message = "Review count must be between 0 and 6. 0 is permitted only under the documented solo-era deviation."
  }
}

variable "require_code_owner_reviews" {
  description = "Enforce CODEOWNERS approval on protected branches."
  type        = bool
  # TRUE matches verified live reality on all five jolarca* repos (2026-09-25).
  # Note this diverges from jolarca-infrastructure/terraform/environments/
  # production/main.tf, which passed false; CODEOWNERS enforcement was applied
  # out-of-band via `gh api` during the 2026-09-17 delivery-chain audit.
  #
  # WARNING — THIS SETTING IS INERT (docs/drift-findings.md D-20). The fleet's
  # .github/CODEOWNERS files reference teams that do not exist in jolarca-dev
  # (the org has ZERO teams), and five of the six name mission-org teams, which
  # also breaches ADR-0004 R4. Verified empirically: jolarca-infrastructure
  # PR #26 merged with zero reviews and an empty requested_reviewers list, as
  # did every other sampled merged PR in the fleet. Kept true only so the first
  # post-migration plan is a no-op against live reality. It must NOT be cited as
  # an operating control until D-20 is remediated.
  default = true
}

variable "enforce_signed_commits" {
  description = "Require GPG/SSH signed commits at the branch-protection layer."
  type        = bool
  # FALSE is the config of record, not an oversight: provider-seeded automation
  # commits (github_repository_file) cannot be GPG-signed, so signature
  # enforcement would break the org-health SECURITY.md path. Operator commits
  # are still signed by policy (git commit -S). See docs/drift-findings.md D-05.
  default = false
}

variable "enable_secret_scanning" {
  description = "Enable GitHub secret scanning + push protection on all repositories."
  type        = bool
  default     = true
}

variable "enable_dependabot" {
  description = "Enable Dependabot vulnerability alerts on all repositories."
  type        = bool
  default     = true
}

variable "compliance_frameworks" {
  description = "Active compliance frameworks for the marketplace organization."
  type        = list(string)
  default     = ["soc2", "gdpr", "iso27001", "pci-dss"]
}

# NOTE: these gate INBOUND DEPENDENCY licenses (policy/compliance-gates.yml
# license_check). They do not constrain a repository's OWN license — the
# flagship `jolarca` application is deliberately AGPL-3.0 (see repos/jolarca.yml).
variable "denied_licenses" {
  description = "SPDX license identifiers NOT permitted in inbound dependencies."
  type        = list(string)
  default     = ["GPL-2.0", "GPL-3.0", "AGPL-3.0", "SSPL-1.0"]
}

variable "repo_definitions_dir" {
  description = "Path to directory containing per-repo YAML definitions."
  type        = string
  default     = "repos"
}

variable "sensitive_repos" {
  description = "Repos forced to private regardless of their YAML visibility."
  type        = list(string)
  default     = []
}

# ── Two-phase bootstrap gate (carried from the github-org module) ────────────
variable "enable_branch_protection" {
  description = "false = phase 1 (create/adopt repos unprotected so workflows can be seeded); true = phase 2 (apply branch protection)."
  type        = bool
  default     = true
}

# ── Org community-health repository (.github) ────────────────────────────────
variable "health_repo_name" {
  description = "Name of the org community-health repository serving inherited SECURITY.md."
  type        = string
  default     = ".github"
}

variable "org_security_policy_content" {
  description = "Content for the org-wide SECURITY.md in the health repo. Empty string defers file creation (avoids shipping placeholder policy)."
  type        = string
  default     = ""
}

variable "health_repo_commit_author" {
  description = "Commit author for provider-seeded health-repo content."
  type        = string
  default     = "jolarca-control-automation"
}

# ── Audit-log streaming (org-level webhook) ──────────────────────────────────
variable "audit_webhook_url" {
  description = "URL for audit-log streaming webhook (set via TF_VAR_audit_webhook_url)."
  type        = string
  default     = ""
  sensitive   = true
}

variable "audit_webhook_secret" {
  description = "Shared secret for audit-log webhook HMAC verification (set via TF_VAR_audit_webhook_secret)."
  type        = string
  default     = ""
  sensitive   = true
}
