# ──────────────────────────────────────────────────────────────────────────────
# Organization community-health repository (.github)
# ──────────────────────────────────────────────────────────────────────────────
# GitHub serves SECURITY.md and the other community-health files from this repo
# to every org repository that lacks its own copy — this is how "SECURITY.md
# inherited from the org .github repo" is realized; no per-repo resource is
# needed for the inheritance itself. It also hosts the org's reusable
# workflows, issue/PR templates and profile README.
#
# Kept OUTSIDE the repos/*.yml allow-list on purpose: it is structurally
# different (must be public, must not carry the fleet merge/CI policy, and its
# name is not a valid allow-list filename). scripts/validate_repos.py and
# scripts/check_fleet_separation.sh both treat it as a known exception.
#
# Supersedes: jolarca-infrastructure/terraform/modules/github-org/
#             github-health-repo.tf
#
# MIGRATION WARNING — the live state for this resource currently points at
# journeyoflife-org/.github, NOT jolarca-dev/.github. The marketplace module
# adopted the mission org's health repo, which is an ADR-0004 cross-scope
# leak. Do NOT migrate that state entry here; it must be handed to jol-control
# or `terraform state rm`'d from the old root. See docs/drift-findings.md D-03
# and docs/state-migration-runbook.md step 4.
# ──────────────────────────────────────────────────────────────────────────────

resource "github_repository" "health" {
  # checkov:skip=CKV_GIT_1: must be public — GitHub only serves org-wide
  # community health files from a public .github repository.
  # checkov:skip=CKV2_GIT_1: carries a deliberately minimal branch protection
  # rule (github_branch_protection.health) — content-only repo, no CI to gate.
  # checkov:skip=CKV_GIT_3: Dependabot alerts are enabled below.
  name        = var.health_repo_name
  description = "Organization-wide defaults: reusable workflows, templates, and profile"
  visibility  = "public"

  # Verified live values, 2026-09-25 — this repo predates the control plane and
  # keeps GitHub's permissive defaults so org-wide templates stay easy to land.
  has_issues      = true
  has_wiki        = false
  has_projects    = true
  has_discussions = false

  allow_merge_commit = true
  allow_squash_merge = true
  allow_rebase_merge = true
  allow_auto_merge   = false

  delete_branch_on_merge = false
  archived               = false
  is_template            = false

  topics = [
    "ci-cd",
    "compliance",
    "github-actions",
    "marketplace",
    "organization",
    "reusable-workflows",
    "security",
    "templates",
  ]

  lifecycle {
    prevent_destroy = true
    ignore_changes  = [auto_init]
  }
}

resource "github_repository_vulnerability_alerts" "health" {
  repository = github_repository.health.name
  enabled    = var.enable_dependabot
}

# SECURITY.md is managed manually for now (D-15). The .github repo has branch
# protection requiring PRs, which prevents Terraform from updating the file
# directly. To bring it under IaC, either:
# (a) Temporarily disable the PR requirement on .github main branch, or
# (b) Use a separate workflow that creates a PR for SECURITY.md changes.
# The live content is preserved in files/SECURITY.md for reference.
# resource "github_repository_file" "security_md" {
#   repository = github_repository.health.name
#   file       = "SECURITY.md"
#   content    = file("${path.module}/files/SECURITY.md")
#   branch     = "main"
#   commit_author  = var.health_repo_commit_author
#   commit_email   = "${var.health_repo_commit_author}@users.noreply.github.com"
#   commit_message = "docs(security): org default SECURITY.md (adopted from live)"
#   overwrite_on_create = true
# }
