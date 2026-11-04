# THE SAME BLOCK AS STEP 1 -- edit it, do not add a second resource.
# Address after step 2 is github_repository_ruleset.main["jolarca-consent"];
# a new name here would declare a SECOND ruleset over the same live object.
resource "github_repository_ruleset" "main" {
  for_each = toset(["jolarca-consent"])

  repository  = each.value
  name        = "protect-main"
  target      = "branch"
  enforcement = "active"

  # No bypass_actors block: consent's live ruleset reports `bypass: []`, and absence is how a
  # ruleset enforces on admins. Adding `actor_type = "OrganizationAdmin"` would silently
  # un-protect main for every owner while looking like an improvement.

  conditions {
    ref_name {
      include = ["~DEFAULT_BRANCH"]
      exclude = []
    }
  }

  rules {
    # stage 1, restated verbatim from the live payload — omit any of these and the PUT drops it
    deletion                = true
    non_fast_forward        = true
    required_linear_history = true
    # update = true is the `restrict_pushes` analogue. Deliberately NOT set here: it is a
    # strengthening, not a mirror of live state, and adding it would break step 3's no-op proof.
    # Set it in step 4 only if you accept that no direct push to main is possible, ever.

    # stage 2, the part that closes the direct-push hole
    pull_request {
      required_approving_review_count   = 0
      require_code_owner_review         = false
      require_last_push_approval        = false
      dismiss_stale_reviews_on_push     = true
      required_review_thread_resolution = true
      allowed_merge_methods             = ["squash"] # consent's settings, not vendor's live list
    }

    required_status_checks {
      strict_required_status_checks_policy = true

      required_check {
        context = "Lint (ruff)"
      }
      required_check {
        context = "Type check (mypy)"
      }
      required_check {
        context = "Test (pytest)"
      }
      required_check {
        context = "Repository smoke-check"
      }
      required_check {
        context = "Gitleaks (secret scanning)"
      }
      # `Dependency review` is suspended for a bounded window under exception D-91
      # (policy/compliance-gates.yml). It was made required by the stage-2 adoption on
      # 2026-10-27 without ever having been observed passing -- the exact defect AGENTS.md §7
      # records as D-90, written the same day by the same author.
      # Why it cannot pass yet, measured: consent's main declares only pyproject.toml, which
      # dependency-review-action cannot resolve, so `GET /dependency-graph/sbom` exits 1 on
      # both main and the PR head, and the check fails on all six open PRs. The pinned
      # manifest that would build the graph lives only on the branch this requirement
      # blocks. That is a required-but-unsatisfiable check (the A-01/D-44/D-47 class), so the
      # requirement has to come off for the fix to land, then go straight back on.
      # `pull_request` and the other six contexts are untouched: the direct-push exposure
      # closed in D-46 stays closed for the duration.
      required_check {
        context = "CodeQL (python)"
      }
    }
  }
}
