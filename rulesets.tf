# rulesets.tf — D-46 option A, consent first.
# Mirrors live content measured 2026-10-26; changes NOTHING about what GitHub enforces.
# Import it before any plan that includes this file (step 2), and require 0 changes.
resource "github_repository_ruleset" "main" {
  for_each = toset(["jolarca-consent"]) # dr and vendor follow after a provider bump

  repository  = each.value
  name        = "protect-main"
  target      = "branch"
  enforcement = "active"

  conditions {
    ref_name {
      include = ["~DEFAULT_BRANCH"]
      exclude = []
    }
  }

  rules {
    deletion                = true
    non_fast_forward        = true
    required_linear_history = true
    # Deliberately absent, because live lacks them: pull_request and
    # required_status_checks. Adding them is step 4, a separate reviewed change.
  }

  # Live `bypass_actors` is [] and `current_user_can_bypass` is never. Do not add a
  # bypass_actors block: an empty list here means nobody, including admins, gets around it.
}
