# ──────────────────────────────────────────────────────────────────────────────
# Organization-level Settings — security & compliance baseline
# ──────────────────────────────────────────────────────────────────────────────
# These settings apply to the entire GitHub organization.
# SOC2 CC6.1 · ISO 27001 A.5.1 · GDPR Art. 32
# ──────────────────────────────────────────────────────────────────────────────

# ── Organization security-manager role assignment — NOT IMPLEMENTED ──────────
# Deliberately absent, not overlooked. `github_organization_role_team` assigns
# the built-in security_manager role to a TEAM, and jolarca-dev has zero teams
# (verified 2026-09-25: `gh api orgs/jolarca-dev/teams` returns []). Declaring
# the resource here would fail at apply, and inventing a team to satisfy it
# would contradict policy/repo-defaults.yml (`teams: {}`, D-10).
#
# This is revisited on second-operator onboarding, which is the same trigger
# that raises D-04 and resolves the CODEOWNERS problem in D-20. Do one without
# the others and the access model becomes internally inconsistent.
#
# ── Org settings the provider CANNOT manage ──────────────────────────────────
# two_factor_requirement_enabled (D-18), members_can_create_repositories and
# default_repository_permission (D-19), web_commit_signoff_required (D-21) are
# org owner settings with no resource in integrations/github v6.x. They must be
# set by hand, and are continuously verified against
# policy/repo-defaults.yml#organization_baseline by scripts/drift_detect.py —
# which is the only control covering them.

# ── Webhook for audit-log streaming ──────────────────────────────────────────
# Only created in prod AND when a webhook URL is supplied (via TF_VAR_*), so an
# empty secret never produces a broken webhook resource.
resource "github_organization_webhook" "audit_stream" {
  count = var.environment == "prod" && var.audit_webhook_url != "" ? 1 : 0

  events = ["*"]

  configuration {
    url          = var.audit_webhook_url
    content_type = "json"
    insecure_ssl = false
    secret       = var.audit_webhook_secret
  }

  active = true
}
