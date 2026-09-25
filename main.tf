# ──────────────────────────────────────────────────────────────────────────────
# Terraform — GitHub Provider & Backend Configuration
# ──────────────────────────────────────────────────────────────────────────────
# Jolarca Control Plane — manages ALL jolarca-dev repositories
# Compliance: SOC 2 Type II · GDPR · ISO 27001:2022 · PCI-DSS 4.0
# ──────────────────────────────────────────────────────────────────────────────
#
# NOT YET AUTHORITATIVE — see docs/state-migration-runbook.md
#
# The github_* resources declared by this root are STILL OWNED by the live
# Terraform state in jolarca-infrastructure
# (terraform/environments/production/terraform.tfstate, module.github_org.*).
# Do NOT run `terraform apply` here until that state has been migrated per the
# runbook. Applying from an empty state attempts to CREATE repositories that
# already exist and, with the old root still wired, produces dual ownership of
# PCI-DSS-scoped production repositories.
#
# `terraform init`, `validate`, `fmt` and `plan -refresh=false` are safe.
# ──────────────────────────────────────────────────────────────────────────────

terraform {
  required_version = ">= 1.9.0"

  required_providers {
    github = {
      source  = "integrations/github"
      version = "~> 6.0"
    }
  }

  # State stored locally (terraform.tfstate). A remote backend is prerequisite
  # step 0 of the migration runbook — see docs/state-migration-runbook.md and
  # docs/runbooks/workload-identity-federation.md.
}

# ── GitHub Provider ──────────────────────────────────────────────────────────
# Authentication via GITHUB_TOKEN environment variable (set in CI/CD).
# Least privilege for this root: 'repo' + 'read:org' covers repository CRUD,
# branch protection and file content. 'admin:org' is needed only for the
# org-level webhook in org-settings.tf, and only when audit_webhook_url is set.
provider "github" {
  owner = var.github_org
  # token is read from GITHUB_TOKEN env var — NEVER hardcode
}
