# Action Plan — jolarca-control Remaining Work

**Created:** 2026-09-25
**Status:** IN PROGRESS

## Phase 1: Critical Security (BLOCKING)

### Step 1.1: Enable 2FA on jolarca-dev org
- **Priority:** CRITICAL (BLOCKING for TF_GITHUB_TOKEN)
- **Action:** Manual enablement in GitHub UI
- **Verification:** `gh api orgs/jolarca-dev -q .two_factor_requirement_enabled`
- **Status:** PENDING

### Step 1.2: Create TF_GITHUB_TOKEN secret
- **Priority:** HIGH (required for CI/CD)
- **Action:** Create fine-grained PAT with repo + admin:org scope
- **Verification:** `gh api orgs/jolarca-dev/actions/secrets -q .total_count`
- **Status:** PENDING (blocked by 1.1)

### Step 1.3: Create TF_GITHUB_TOKEN_READONLY secret
- **Priority:** HIGH (required for drift detection)
- **Action:** Create fine-grained PAT with read-only scope
- **Verification:** `gh api orgs/jolarca-dev/actions/secrets -q .total_count`
- **Status:** PENDING (blocked by 1.1)

### Step 1.4: Set STATE_MIGRATION_COMPLETE variable
- **Priority:** HIGH (unlocks terraform apply)
- **Action:** `gh variable set STATE_MIGRATION_COMPLETE --org jolarca-dev --body "true"`
- **Verification:** `gh api orgs/jolarca-dev/actions/variables -q '.variables[] | select(.name=="STATE_MIGRATION_COMPLETE")'`
- **Status:** PENDING

## Phase 2: Fix Pre-Existing CI Failures

### Step 2.1: Investigate trivy failure on jolarca
- **Priority:** MEDIUM (security scan)
- **Action:** Check trivy logs, identify vulnerability or config issue
- **Verification:** trivy check passes on next PR
- **Status:** PENDING

### Step 2.2: Investigate dependency-audit failure on jolarca
- **Priority:** MEDIUM (dependency check)
- **Action:** Check Dependabot alerts, fix or dismiss
- **Verification:** dependency-audit check passes on next PR
- **Status:** PENDING

### Step 2.3: Fix drift detection for the Free-plan protection gap
- **Priority:** HIGH (the detection control is blind where it matters most)
- **Action:** In `scripts/drift_detect.py`, read `.protected` from
  `GET /repos/{org}/{repo}/branches/main` (readable on Free) and classify the
  private-repo HTTP 403 on the protection endpoint as a plan-tier finding,
  not as `unverifiable` — today all seven private repos land in `unverifiable`,
  the run exits 2, and the error message blames token scope (D-33). Separately,
  `check_fleet()` reads `isPrivate` / `hasWikiEnabled` / `isArchived` from a
  **REST** payload whose fields are `private` / `has_wiki` / `archived`, so every
  declared-private repo is reported as a false HIGH-EXPOSURE visibility drift and
  the wiki/archive checks can never fire.
- **Verification:** `.venv/bin/python scripts/drift_detect.py` reports the seven
  private repos as unguarded rather than unverifiable, and reports visibility
  drift only for `jolarca-observability` and `jolarca-security`
- **Status:** PENDING

## Phase 3: Documentation & Tracking

### Step 3.1: Update drift-findings.md with final status
- **Priority:** LOW
- **Action:** Mark D-20, D-21, D-19 as FIXED, update D-15, D-18 status
- **Verification:** Document reflects current state
- **Status:** PENDING

### Step 3.2: Create change record for org settings
- **Priority:** LOW
- **Action:** Document D-19 fix in docs/change-management.md
- **Verification:** Change record exists
- **Status:** PENDING

## Phase 4: Optional Enhancements (GitHub Team upgrade)

### Step 4.1: Upgrade to GitHub Team
- **Priority:** OPTIONAL (when budget approved)
- **Action:** Upgrade jolarca-dev org to GitHub Team plan
- **Verification:** `gh api orgs/jolarca-dev -q .plan.name` returns "team"
- **Status:** PENDING (optional)

### Step 4.2: Re-enable branch protection
- **Priority:** HIGH once 4.1 lands — **not optional.** Tracked as open blocking
  gap **D-33**: enforceable protection currently exists on 2 of 16 repositories
  (`jolarca`, `.github`) and on none of the private ones, so `main` on this
  control plane and on the four PCI-DSS-scoped repos accepts direct and
  force-pushes today. What is genuinely optional is the *timing*, not the fix.
- **Action:** After the upgrade, reconcile `branch-protection.tf` with
  `policy/repo-defaults.yml#branch_protection.main` (five attributes are
  hardcoded `false` against a baseline that requires `true`), make
  `enable_branch_protection` per-repo rather than fleet-wide, import the two
  surviving rules, then set the flag to `true`
- **Verification:** `gh api repos/jolarca-dev/<repo>/branches/main -q .protected`
  returns `true` fleet-wide and `terraform.tfstate` holds one
  `github_branch_protection` instance per repo
- **Status:** PENDING (blocked by 4.1)

### Step 4.3: Re-enable secret scanning
- **Priority:** OPTIONAL (requires GitHub Team)
- **Action:** Set `enable_secret_scanning = true` in terraform.tfvars
- **Verification:** Secret scanning enabled on all repos
- **Status:** PENDING (blocked by 4.1)

### Step 4.4: Re-enable CODEOWNERS management
- **Priority:** OPTIONAL (requires branch protection changes)
- **Action:** Uncomment `github_repository_file.codeowners` in codeowners.tf
- **Verification:** CODEOWNERS managed by Terraform
- **Status:** PENDING (blocked by 4.2)

### Step 4.5: Re-enable SECURITY.md management
- **Priority:** OPTIONAL (requires branch protection changes)
- **Action:** Uncomment `github_repository_file.security_md` in health-repo.tf
- **Verification:** SECURITY.md managed by Terraform
- **Status:** PENDING (blocked by 4.2)

## Execution Order

1. **Phase 1** (CRITICAL) — Steps 1.1 → 1.2 → 1.3 → 1.4
2. **Phase 2** (MEDIUM/HIGH) — Steps 2.1 → 2.2 → 2.3
3. **Phase 3** (LOW) — Steps 3.1 → 3.2
4. **Phase 4** (upgrade-dependent) — Steps 4.1 → 4.2 → 4.3 → 4.4 → 4.5

## Success Criteria

- [ ] 2FA enabled on jolarca-dev
- [ ] TF_GITHUB_TOKEN and TF_GITHUB_TOKEN_READONLY secrets created
- [ ] STATE_MIGRATION_COMPLETE variable set
- [ ] trivy and dependency-audit failures resolved
- [ ] drift-findings.md reflects current state
- [ ] Branch protection gap (D-33) has an owner decision: GitHub Team upgrade,
      or a dated acceptance in `policy/compliance-gates.yml` `exceptions.active`
- [ ] Drift detection reports unguarded private repos instead of `unverifiable`
- [ ] All gates pass (terraform validate, linters, tests)
- [ ] Drift detection runs successfully in CI
