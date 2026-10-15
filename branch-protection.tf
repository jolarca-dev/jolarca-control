# ──────────────────────────────────────────────────────────────────────────────
# Branch Protection — enforced on `main` for every fleet repository
# ──────────────────────────────────────────────────────────────────────────────
# Implements SOC 2 CC6.1/CC8.1, ISO 27001 A.5.1/A.8.1, PCI-DSS 6.3
#
# Every value below was verified against the live GitHub API on 2026-09-25 for
# all six jolarca-dev repositories. The claim that followed — "so the first
# post-migration plan should be a no-op for branch protection" — was FALSE and is
# retired: a refreshed plan on 2026-10-15 still rendered 25 changes and 3 creates
# against these rules (D-61, D-63, and the packet in
# docs/state-migration-runbook.md step 6). Per-repo required status-check contexts
# live in repos/*.yml because they legitimately differ per repository, which means
# a stale repos/*.yml is a live weakening: repos/jolarca.yml had fallen to 9 of the
# 12 contexts the flagship actually requires and still produces.
#
# Supersedes: jolarca-infrastructure/terraform/modules/github-org/
#             branch-protection.tf
# ──────────────────────────────────────────────────────────────────────────────
# STATUS 2026-09-28 — THE SAFE FOUR ARE NOW ENABLED. Pre-deployment audit B3
# recommended shipping require_linear_history, require_conversation_resolution,
# strict status checks, and dismiss_stale_reviews. These four work on the Free
# plan for PUBLIC repos (jolarca, .github). They remain unavailable for PRIVATE
# repos without GitHub Pro (D-33). terraform.tfvars now sets
# var.enable_branch_protection = true, so these resources ARE declared in the
# plan; whether an apply lands is decided elsewhere. `STATE_MIGRATION_COMPLETE`
# measures 'true' (set 2026-10-10), so apply.yml is NOT blocked by it, and this
# root does own the live github_* state: `terraform state list` holds 48 addresses
# including 14 github_branch_protection (D-02's backend half landed; its off-host
# backup half is D-02 and D-61's remaining concern). The brakes that actually hold
# are `scripts/check_plan_safety.sh`, which refuses protection creates and attribute
# changes since 2026-10-15 (D-61), plus the CI plan step currently failing on the
# state lock (D-56) — the first is a control, the second is not.
# The protection these repos actually run today was created out-of-band via
# `gh api PUT` (including the A-08 SAST (semgrep) required context); the three
# fleet repos with no legacy rule (jolarca-consent, jolarca-dr, jolarca-vendor) are
# protected by an undeclared ACTIVE ruleset instead (D-46), so a create here layers
# a second mechanism rather than adding protection. Two
# attributes remain off:
#   - require_code_owner_reviews: false (D-20, solo-era deviation — inert with
#     a single operator who cannot approve their own PR; pre-deployment audit B3
#     confirmed the "safe four" approach with a dated deviation for this flag).
#     Exception noted 2026-10-15: jolarca-docs runs live TRUE while the fleet
#     default is false, so the plan removes it there. Accepted deliberately: with
#     zero teams no principal can satisfy it, and the provider itself commits to
#     fleet repositories via github_repository_file (codeowners.tf), which cannot
#     carry the second flag below. See the packet in
#     docs/state-migration-runbook.md step 6.
#   - require_signed_commits: false (D-05, provider automation cannot sign).
# Open blocking gap: docs/drift-findings.md D-33 (private repos unguarded).
# ──────────────────────────────────────────────────────────────────────────────

locals {
  # Repos that declare branch protection in their allow-list entry. The org
  # health repo is handled separately below — it carries a deliberately
  # minimal rule (content-only repo, no CI to gate on).
  #
  # INTERIM MITIGATION for D-46 (decided 2026-10-15, pending the owner's endgame):
  # jolarca-consent, jolarca-dr and jolarca-vendor are excluded from the legacy
  # resource even though their repos/*.yml declares branch_protection.main. Measured
  # content of their ACTIVE `protect-main` rulesets (`gh api repos/jolarca-dev/<r>/rulesets`
  # then `/rulesets/{numeric-id}`; the NAME form 404s):
  #   consent (24087580) — deletion + non-fast-forward + linear history only, no PR rule,
  #            no status-checks rule at all
  #   dr      (24136490) — plus a PR rule (0 approvals) and required [lint, gitleaks],
  #            strict false
  #   vendor  (24138288) — plus a PR rule allowing merge/squash/rebase and a
  #            status-checks rule whose context list is EMPTY, strict false
  # Creating a legacy rule beside those would give each repo TWO mechanisms with
  # different content, and GitHub enforces the union — so the resource would read as
  # the control while the ruleset is what actually bites. The exclusion costs nothing
  # in state (these three were never imported: `terraform state list` holds 14
  # addresses, `3 to add` included them), and it removes the only remaining create from
  # D-61's plan. Read the trade-off honestly: their declared required_status_checks
  # (consent's 7, vendor's and dr's `lint`) are enforced by NOTHING today, and stay that
  # way until D-46's option A (import rulesets as github_repository_ruleset) or B
  # (delete rulesets, let the legacy rule be the single source) is executed by the
  # operator. B has an exposure window unless sequenced after a working apply.
  protected_repos = {
    for name, def in local.repo_defs : name => def
    if can(def.branch_protection.main) && var.enable_branch_protection
    && !contains(local.ruleset_protected_repos, name)
  }

  # Repos whose main branch is enforced by an undeclared ruleset rather than a legacy
  # rule. Kept as its own local so the exclusion is greppable and D-46's resolution is
  # a one-line deletion rather than a search through a comprehension.
  ruleset_protected_repos = ["jolarca-consent", "jolarca-dr", "jolarca-vendor"]

  # Repos whose live branch protection actually carries a push restriction,
  # enumerated from `terraform state show` on 2026-10-15 (11 of the 14
  # addresses; `health[0]`, jolarca-docs and jolarca-hermes-agents do not).
  #
  # policy/repo-defaults.yml says `restrict_pushes: true` for the fleet, and this
  # file used to declare the block nowhere — which is worse than a policy gap: an
  # apply would have DELETED the restriction from all eleven rules that have it.
  # That was 11 of the 25 changes in D-61's plan and the safety gate could not see
  # it (removed nested blocks render with `-`).
  #
  # Declaring it for exactly the eleven keeps the plan honest — no unreviewed
  # tightening — and leaves the remaining disagreement visible instead of quietly
  # resolved in either direction: docs and hermes-agents are recorded as
  # policy-vs-live drift (D-66), and jolarca-consent / jolarca-dr /
  # jolarca-vendor carry protection as an undeclared ACTIVE ruleset (D-46), so
  # their pending create is not the place to invent a new push posture. Adding a
  # repo here should be its own reviewed change, because empty push_allowances
  # blocks direct pushes to main for anyone without bypass — including
  # github_repository_file automation (codeowners.tf).
  #
  # Values are per-repo, read from `terraform state show`, not one blanket list:
  # jolarca-payments allows "/JourneyOfLife" and the other ten allow nobody.
  # Writing `push_allowances = []` for all of them would have silently removed the
  # operator's own allowance from the payments rule — a regression introduced by
  # fixing a regression, which is why this map is keyed per repository.
  restrict_pushes_rules = {
    jolarca                = []
    jolarca-compliance     = []
    jolarca-control        = []
    jolarca-data           = []
    jolarca-identity       = []
    jolarca-infrastructure = []
    jolarca-legal          = []
    jolarca-observability  = []
    jolarca-payments       = ["/JourneyOfLife"]
    jolarca-runbooks       = []
    jolarca-security       = []
  }
}

resource "github_branch_protection" "main" {
  for_each = local.protected_repos

  repository_id = github_repository.repo[each.key].node_id
  pattern       = lookup(each.value.branch_protection.main, "pattern", "main")

  # ── Required status checks ────────────────────────────────────────────────
  required_status_checks {
    # strict mode: requires up-to-date branches. Works on Free for PUBLIC repos;
    # private repos need GitHub Pro (D-33). Enabled now so public repos get it.
    strict   = true
    contexts = each.value.branch_protection.main.required_status_checks.contexts
  }

  # ── Pull-request reviews ──────────────────────────────────────────────────
  required_pull_request_reviews {
    # SOLO-ERA DEVIATION: 0 approving reviews (docs/security/key-custody.md,
    # docs/drift-findings.md D-04). checkov CKV_GIT_5 equivalent — with one
    # operator a count of 1+ is unsatisfiable and would lock the maintainer
    # out. Enforcement rides on the required status checks above. Raise when
    # the second operator onboards.
    required_approving_review_count = var.required_approving_review_count
    # dismiss_stale_reviews: works on Free for PUBLIC repos; private need Pro (D-33).
    dismiss_stale_reviews = true
    # D-20: this is set false (see terraform.tfvars) — inert until teams exist,
    # and requires GitHub Pro for private repos on free plan.
    require_code_owner_reviews = var.require_code_owner_reviews
    require_last_push_approval = false
  }

  # ── Enforcement ───────────────────────────────────────────────────────────
  enforce_admins         = true
  require_signed_commits = var.enforce_signed_commits
  # required_linear_history and require_conversation_resolution: enabled for
  # public repos (Free plan). Private repos need GitHub Pro (D-33).
  # Works on Free for PUBLIC repos; private repos need Pro (D-33).
  required_linear_history = true
  # Works on Free for PUBLIC repos; private repos need Pro (D-33).
  require_conversation_resolution = true
  allows_force_pushes             = false
  allows_deletions                = false

  # ── Push restrictions ─────────────────────────────────────────────────────
  # Declared 2026-10-15 for exactly the repos whose live rule has it, per
  # local.restrict_pushes_rules above. Before this the block was absent from the
  # configuration while eleven live rules and policy/repo-defaults.yml had it, so
  # any apply silently removed the "only these actors may push to main" restriction
  # fleet-wide — the largest weakening in D-61's plan, invisible to the safety gate
  # until removed nested blocks were matched on `-` as well as `~`.
  dynamic "restrict_pushes" {
    for_each = contains(keys(local.restrict_pushes_rules), each.key) ? [true] : []
    content {
      blocks_creations = false
      push_allowances  = lookup(local.restrict_pushes_rules, each.key, [])
    }
  }

  lifecycle {
    prevent_destroy = true
  }
}

# ── Org community-health repo (.github) ──────────────────────────────────────
# Deliberately minimal: a content-only repo with no CI, so requiring status
# checks would block every change forever. Verified live state 2026-09-25:
# enforce_admins=true, dismiss_stale_reviews=true, zero required contexts,
# require_code_owner_reviews=FALSE, linear history and conversation resolution
# OFF. Note a `.github/CODEOWNERS` file IS present in that repository — the
# REQUIREMENT is off, not the file. Its entries name jolarca-dev teams that do
# not exist, so enabling the requirement would change nothing (D-20). Because
# this repo's rule is deliberately weaker than the fleet baseline, it is listed
# in policy/repo-defaults.yml `branch_protection_baseline_exempt`; drift_detect
# still asserts that a protection rule EXISTS here.
resource "github_branch_protection" "health" {
  count = var.enable_branch_protection ? 1 : 0

  repository_id = github_repository.health.node_id
  pattern       = "main"

  required_status_checks {
    strict   = false
    contexts = []
  }

  required_pull_request_reviews {
    required_approving_review_count = 0
    dismiss_stale_reviews           = true
    require_code_owner_reviews      = false
    require_last_push_approval      = false
  }

  enforce_admins         = true
  require_signed_commits = false
  # Works on Free for PUBLIC repos; private repos need Pro (D-33).
  required_linear_history = true
  # Works on Free for PUBLIC repos; private repos need Pro (D-33).
  require_conversation_resolution = true
  allows_force_pushes             = false
  allows_deletions                = false

  lifecycle {
    prevent_destroy = true
  }
}

# NOTE: Release-tag protection (v* tags) would be enforced via GitHub Rulesets,
# which the integrations/github provider models as github_repository_ruleset.
# The 2026-09-17 audit's conclusion that NO rulesets exist org-wide is now FALSE
# and was superseded by measurement on 2026-10-04 (D-46): three repositories
# -- jolarca-vendor, jolarca-consent, jolarca-dr -- carry an ACTIVE ruleset
# named protect-main, created 2026-09-28, i.e. eleven days after that audit and
# outside this configuration. Org-wide ruleset listing is unavailable on the
# current plan (HTTP 403), so this repo cannot enumerate them centrally; the
# per-repo endpoint can, and scripts/drift_detect.py now does exactly that
# because the legacy /protection endpoint returns 404 for ruleset-protected
# branches and previously filed that as an unreadable plan limitation.
# Consequence to keep in view: that layer is real enforcement with no declared
# source of truth. `terraform apply` neither creates, repairs nor destroys it,
# and `terraform destroy` would not notice it. Ruleset definitions stay out of
# this baseline only until the strategy in RB-04 / D-07 is decided -- see D-46.
