# ──────────────────────────────────────────────────────────────────────────────
# CODEOWNERS — managed by jolarca-control
# ──────────────────────────────────────────────────────────────────────────────
# ADR-0004 R4: no CODEOWNERS, workflow, or module in the marketplace fleet may
# reference the mission platform (journeyoflife-org / jol-infrastructure).
#
# D-20 found that five fleet repos had CODEOWNERS pointing at mission-org teams
# that don't exist in jolarca-dev, making require_code_owner_reviews inert.
# This resource overwrites those files with jolarca-dev-only content.
#
# When teams are created in jolarca-dev (D-10 trigger), update this file to
# reference them. Until then, @JourneyOfLife is the sole code owner.
# ──────────────────────────────────────────────────────────────────────────────

locals {
  codeowners_content = <<-EOT
    # CODEOWNERS — jolarca-dev marketplace fleet
    #
    # ADR-0004 R4: no mission-platform references allowed.
    # D-20: previous version referenced @journeyoflife-org/* and @jol-infrastructure/*
    # which don't exist in this org, making require_code_owner_reviews inert.
    #
    # jolarca-dev has zero teams (D-10). Until teams are created, the sole
    # operator (@JourneyOfLife) is the code owner for everything.
    #
    # When teams are created, update this file to reference them.

    * @JourneyOfLife
  EOT
}

# CODEOWNERS management is DEFERRED due to branch protection requirements.
# The fleet repos have branch protection requiring PRs and status checks,
# which prevents Terraform from updating CODEOWNERS directly.
#
# To fix D-20 (cross-project CODEOWNERS references), either:
# (a) Manually update each repo's .github/CODEOWNERS via PR, or
# (b) Temporarily disable branch protection, run terraform apply, then re-enable, or
# (c) Use a separate workflow that creates PRs for CODEOWNERS changes.
#
# The drift detection (scripts/drift_detect.py) will continue to alert on
# cross-project references until they are removed.
#
# resource "github_repository_file" "codeowners" {
#   for_each = {
#     for name, def in local.repo_defs : name => def
#     if name != ".github"
#   }
#   repository          = github_repository.repo[each.key].name
#   file                = ".github/CODEOWNERS"
#   content             = local.codeowners_content
#   commit_message      = "chore: enforce jolarca-dev-only CODEOWNERS (ADR-0004 R4, D-20)"
#   commit_author       = "jolarca-control-automation"
#   commit_email        = "jolarca-control@jolarca.dev"
#   overwrite_on_create = true
#   lifecycle {
#     ignore_changes = [commit_author, commit_email]
#   }
# }
