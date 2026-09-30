# ──────────────────────────────────────────────────────────────────────────────
# Terraform — GitHub Provider & Backend Configuration
# ──────────────────────────────────────────────────────────────────────────────
# Jolarca Control Plane — manages ALL jolarca-dev repositories
# Compliance: SOC 2 Type II · GDPR · ISO 27001:2022 · PCI-DSS 4.0
# ──────────────────────────────────────────────────────────────────────────────
#
# AUTHORITATIVE — sole Terraform root for all jolarca-dev GitHub resources.
# Legacy state (jolarca-infrastructure) was emptied on 2026-10-01 (D-13 FIXED).
# State is stored in HCP Terraform (ADR-0006) — see cloud block below.
# ──────────────────────────────────────────────────────────────────────────────

terraform {
  required_version = ">= 1.9.0"

  required_providers {
    github = {
      source  = "integrations/github"
      version = "~> 6.0"
    }
  }

  # HCP Terraform remote backend (ADR-0006, accepted 2026-09-25).
  # State is stored in the `jolarca-control` workspace of the `jolarca-dev`
  # organization on HCP Terraform (free tier). Authentication via TFC_TOKEN
  # (GitHub secret) or TF_TOKEN_app_terraform_io (local credentials file).
  cloud {
    organization = "jolarca-dev"

    workspaces {
      name = "jolarca-control"
    }
  }
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
