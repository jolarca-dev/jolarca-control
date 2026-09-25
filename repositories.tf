# ──────────────────────────────────────────────────────────────────────────────
# Repository Resources — generated from repos/*.yml allow-list
# ──────────────────────────────────────────────────────────────────────────────
# Each repository is defined in repos/<name>.yml. Changes to repo settings MUST
# go through repos/*.yml → terraform plan → PR → apply. Never mutate a
# repository setting out-of-band in the GitHub UI: ADR-0004 R2 treats
# out-of-band fleet changes as an incident (48h reconciliation rule).
#
# Supersedes: jolarca-infrastructure/terraform/modules/github-org/main.tf
# (the fleet map moved from a Terraform variable default to the YAML
# allow-list; resource addresses change accordingly — see
# docs/state-migration-runbook.md for the address mapping).
# ──────────────────────────────────────────────────────────────────────────────

locals {
  # Load all repo definitions from YAML files
  repo_files = fileset(path.module, "${var.repo_definitions_dir}/*.yml")
  repo_defs = {
    for f in local.repo_files :
    trimsuffix(basename(f), ".yml") => yamldecode(file("${path.module}/${f}"))
  }
}

# ── Repository creation & configuration ──────────────────────────────────────
resource "github_repository" "repo" {
  for_each = local.repo_defs

  name        = each.value.name
  description = each.value.description
  visibility  = contains(var.sensitive_repos, each.value.name) ? "private" : each.value.visibility

  # Feature flags
  has_issues      = lookup(each.value.settings, "has_issues", true)
  has_wiki        = lookup(each.value.settings, "has_wiki", false)
  has_projects    = lookup(each.value.settings, "has_projects", false)
  has_discussions = false

  # Merge strategy — squash-only keeps linear history (SOC 2 CC8.1 audit trail)
  allow_merge_commit = lookup(each.value.settings, "allow_merge_commit", false)
  allow_squash_merge = lookup(each.value.settings, "allow_squash_merge", true)
  allow_rebase_merge = lookup(each.value.settings, "allow_rebase_merge", true)
  allow_auto_merge   = false

  # Lifecycle
  delete_branch_on_merge = lookup(each.value.settings, "delete_branch_on_merge", true)
  archived               = lookup(each.value.settings, "archived", false)
  auto_init              = lookup(each.value.settings, "auto_init", false)
  is_template            = lookup(each.value.settings, "is_template", false)

  # Web commit sign-off (D-21)
  web_commit_signoff_required = lookup(each.value.settings, "web_commit_signoff_required", false)

  # License — only set where the YAML declares it; the flagship `jolarca` app
  # is AGPL-3.0, the governance repos carry no OSS license template.
  license_template = lookup(each.value.settings, "license_template", null)

  # Security
  security_and_analysis {
    dynamic "secret_scanning" {
      for_each = var.enable_secret_scanning ? [1] : []
      content {
        status = "enabled"
      }
    }
    dynamic "secret_scanning_push_protection" {
      for_each = var.enable_secret_scanning ? [1] : []
      content {
        status = "enabled"
      }
    }
  }

  # Topics
  topics = lookup(each.value, "topics", [])

  lifecycle {
    prevent_destroy = true # never accidentally delete a PCI-scoped repository
    ignore_changes  = [auto_init]

    # ADR-0004 R1/R3 — mission/marketplace separation, defense in depth.
    # This root's jurisdiction is the MARKETPLACE fleet (jolarca*) only.
    # Mission-platform repos (jol-*) are governed by jol-control and must
    # never enter this state; scripts/check_fleet_separation.sh enforces the
    # reverse direction against the live org.
    precondition {
      condition     = can(regex("^jolarca(-[a-z0-9-]+)?$", each.value.name))
      error_message = "Fleet entry '${each.value.name}' is not named jolarca or jolarca-<suffix>. Mission-platform repos belong to jol-control, not this control plane (ADR-0004 mission/marketplace separation)."
    }
  }
}

# ── Vulnerability alerts (separate resource — inline arg deprecated) ─────────
resource "github_repository_vulnerability_alerts" "repo" {
  for_each = local.repo_defs

  repository = github_repository.repo[each.key].name
  enabled    = lookup(each.value.settings, "vulnerability_alerts", true)
}
