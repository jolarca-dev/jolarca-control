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
# Secret scanning ENABLED: public repos get free secret scanning on GitHub Free.
# D-33 compensating control: secret scanning is now configured.
enable_secret_scanning = true
enable_dependabot      = true

# Branch protection DISABLED: branch protection is not available for PRIVATE
# repos below GitHub Team/Pro, so these resources would fail on the seven
# private repos in the fleet.
# CORRECTION 2026-09-26: the out-of-band rules from D-08 do NOT "remain in
# place" once a repo is private. They are neither readable (HTTP 403) nor
# enforced (.protected = false); only jolarca and .github are still guarded, so
# 2 of 16 repos have enforceable protection and none of the private ones do.
# The flag is also fleet-wide, so it withholds protection from the nine PUBLIC
# repos where branch protection IS free on this plan.
# Open blocking gap: docs/drift-findings.md D-33 (also compliance-gates.yml
# exceptions.open_blocking). Re-enable after a GitHub Team upgrade, per repo,
# and reconcile branch-protection.tf with policy/repo-defaults.yml first.
# Branch protection ENABLED for public repos (free on GitHub Free plan).
# jolarca-control is public; branch protection is enforceable.
# D-33 compensating control: protection is now configured.
enable_branch_protection = true

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
