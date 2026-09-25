# ──────────────────────────────────────────────────────────────────────────────
# Outputs — Jolarca Control Plane
# ──────────────────────────────────────────────────────────────────────────────

output "repository_names" {
  description = "List of all managed marketplace repository names (allow-list fleet)."
  value       = [for r in github_repository.repo : r.name]
}

output "repository_urls" {
  description = "Map of repository names to their GitHub URLs."
  value       = { for name, r in github_repository.repo : name => r.html_url }
}

output "health_repo" {
  description = "Org community-health repo serving the inherited SECURITY.md."
  value       = github_repository.health.html_url
}

output "branch_protection" {
  description = "Fleet repos with branch protection on main."
  value       = { for name, bp in github_branch_protection.main : name => bp.pattern }
}

output "total_managed_repos" {
  description = "Total number of repositories managed by jolarca-control (excludes the org health repo)."
  value       = length(github_repository.repo)
}

output "compliance_summary" {
  description = "Compliance posture summary for the marketplace org."
  value = {
    frameworks         = var.compliance_frameworks
    signed_commits     = var.enforce_signed_commits
    code_owner_reviews = var.require_code_owner_reviews
    approving_reviews  = var.required_approving_review_count
    secret_scanning    = var.enable_secret_scanning
    dependabot         = var.enable_dependabot
    total_repos        = length(github_repository.repo)
    protected_repos    = length(github_branch_protection.main)
    environment        = var.environment
    solo_era_deviation = var.required_approving_review_count == 0
  }
}
