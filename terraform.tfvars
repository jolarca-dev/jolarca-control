# ──────────────────────────────────────────────────────────────────────────────
# Terraform variable values — Jolarca Control Plane
# ──────────────────────────────────────────────────────────────────────────────
# NOTE: Do NOT put secrets here. Use environment variables or Vaultwarden.
# NOTE: Do NOT run `terraform apply` from this root until the state migration
#       in docs/state-migration-runbook.md is complete. See main.tf header.
# ──────────────────────────────────────────────────────────────────────────────

github_org  = "jolarca-dev"
environment = "prod"

# ── Review policy (solo-era deviation — docs/security/key-custody.md) ────────
required_approving_review_count = 0
# CODEOWNERS reviews disabled: (1) inert until D-20 is fixed (no teams exist),
# (2) requires GitHub Pro for private repos on free plan. Re-enable when teams
# are created and org is upgraded.
require_code_owner_reviews = false

# Signature enforcement OFF: provider-seeded automation commits cannot be
# GPG-signed. Operator commits remain signed by policy. See D-05.
enforce_signed_commits = false

# ── Security scanning ────────────────────────────────────────────────────────
# Secret scanning disabled: not available for private repos on GitHub Free plan.
# Enable when upgrading to GitHub Team or if all repos are public.
enable_secret_scanning = false
enable_dependabot      = true

# Branch protection DISABLED: most branch protection features require GitHub Pro
# for private repos on the free plan. The existing branch protection rules were
# applied out-of-band (D-08) and will remain in place until the org is upgraded.
# Re-enable when upgrading to GitHub Team/Pro.
enable_branch_protection = false

compliance_frameworks = ["soc2", "gdpr", "iso27001", "pci-dss"]

# Inbound dependency licenses only — the `jolarca` application itself is
# deliberately AGPL-3.0 (repos/jolarca.yml). Do not "fix" that by adding an
# exception here; the gate applies to third-party dependencies.
denied_licenses = [
  "GPL-2.0",
  "GPL-3.0",
  "AGPL-3.0",
  "SSPL-1.0",
]

repo_definitions_dir = "repos"

# ── BLOCKING DECISION D-01 (docs/drift-findings.md) ──────────────────────────
# repos/jolarca-{compliance,data,infrastructure,legal}.yml declare
# visibility: private — that is the intent of record inherited from
# jolarca-infrastructure/terraform/modules/github-org/variables.tf. Live
# reality as of 2026-09-25 is that all four are PUBLIC. The first apply after
# the state migration will therefore flip four repositories to private.
# Confirm that is intended (it breaks any public fork/contributor workflow and
# GitHub Pages on those repos) BEFORE approving the apply. To keep them public
# instead, change the four YAML files — not this list.
sensitive_repos = []

# Org health repo: leave empty to defer SECURITY.md creation rather than ship
# placeholder policy text. Populate from Vaultwarden-backed content when the
# org-wide security policy is approved.
org_security_policy_content = ""

# Audit webhook URL/secret are NOT stored here (secrets must never live in git).
# Provide them at runtime via environment variables:
#   export TF_VAR_audit_webhook_url="https://..."
#   export TF_VAR_audit_webhook_secret="..."
# Their declarations live in variables.tf.
