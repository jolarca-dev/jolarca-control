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

### Step 4.2: Re-enable advanced branch protection
- **Priority:** OPTIONAL (requires GitHub Team)
- **Action:** Set `enable_branch_protection = true` in terraform.tfvars
- **Verification:** Branch protection managed by Terraform
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
2. **Phase 2** (MEDIUM) — Steps 2.1 → 2.2
3. **Phase 3** (LOW) — Steps 3.1 → 3.2
4. **Phase 4** (OPTIONAL) — Steps 4.1 → 4.2 → 4.3 → 4.4 → 4.5

## Success Criteria

- [ ] 2FA enabled on jolarca-dev
- [ ] TF_GITHUB_TOKEN and TF_GITHUB_TOKEN_READONLY secrets created
- [ ] STATE_MIGRATION_COMPLETE variable set
- [ ] trivy and dependency-audit failures resolved
- [ ] drift-findings.md reflects current state
- [ ] All gates pass (terraform validate, linters, tests)
- [ ] Drift detection runs successfully in CI
