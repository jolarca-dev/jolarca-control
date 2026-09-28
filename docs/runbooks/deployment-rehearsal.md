# RB-09: Deployment Rehearsal Procedure

**SOC 2 CC8.1 / ISO 27001 A.8.32, A.5.30 / PCI-DSS 11.3.1**

> **Status:** DRAFT — requires owner sign-off before first execution.
> **Cadence:** Quarterly, or after every infrastructure change.
> **Evidence destination:** `jolarca-compliance/audits/deployment-rehearsals/`

---

## Preconditions

1. `terraform.tfstate` is backed up (RB-09 step 0 — `scripts/state_backup.sh`).
2. All CI checks green on `main` (`make lint`).
3. `GITHUB_TOKEN` set with `repo` + `read:org` scope.
4. `gh` CLI authenticated (`gh auth status`).
5. `age` installed for state backup verification.

## Step 1 — Happy Path: dev → staging

```bash
# 1a. Verify the plan is clean for the staging environment
cd /opt/jolarca/repos/jolarca-control
make validate
make compliance

# 1b. Run the plan (offline — state migration not yet complete)
make plan
# Expected: plan shows no destructive changes

# 1c. Verify fleet separation
make fleet-audit
# Expected: FLEET SEPARATION OK
```

**Checkpoint:** All three commands exit 0. Record timestamps.

## Step 2 — Failure Path: Blocked Apply

```bash
# 2a. Attempt apply (should be REFUSED)
make apply
# Expected: exit 1, "REFUSED. See docs/state-migration-runbook.md."
```

**Checkpoint:** Apply is correctly refused. This proves the gate works.

## Step 3 — Failure Path: Plan Safety Refusal

```bash
# 3a. Create a test plan that would destroy a repo
# (DO NOT actually run this against the live org)
echo '# github_repository.repo["jolarca"] will be destroyed' > /tmp/test-plan.txt
bash scripts/check_plan_safety.sh /tmp/test-plan.txt
# Expected: exit 1, "Plan contains a destroy action"
rm /tmp/test-plan.txt
```

**Checkpoint:** Plan safety gate correctly refuses destructive plans.

## Step 4 — Failure Path: Credential Failure

```bash
# 4a. Run with an invalid token
GITHUB_TOKEN=invalid_token make validate
# Expected: validate_repos.py exits 0 (offline check, no API call)

# 4b. Run drift detection with invalid token (should fail loudly)
GITHUB_TOKEN=invalid_token python3 scripts/drift_detect.py 2>&1 || true
# Expected: non-zero exit, clear error message about authentication
```

**Checkpoint:** Offline checks work without credentials. Live checks fail
loudly (never silently pass) when credentials are invalid.

## Step 5 — Rollback Simulation

```bash
# 5a. Verify state backup exists and is valid
ls -la docs/backup-log.tsv
# Expected: at least one entry

# 5b. Verify the backup can be decrypted (requires age identity)
# age --decrypt -i ~/.key.txt -o /tmp/restored.tfstate <latest-backup>
# Expected: restored file matches the original SHA-256

# 5c. Compare restored state hash with backup log
sha256sum /tmp/restored.tfstate
# Expected: matches the state_sha256 in backup-log.tsv
```

**Checkpoint:** Backup → restore → verify cycle completes within RTO.

## Step 6 — Evidence Collection

For each step above, record:

| Field | Value |
|-------|-------|
| Date | YYYY-MM-DD |
| Operator | Name |
| Step | 1-6 |
| Exit code | 0/1/2 |
| Timestamp | HH:MM:SS UTC |
| Evidence | Screenshot or terminal capture |
| Notes | Any deviations or observations |

Save evidence to `jolarca-compliance/audits/deployment-rehearsals/YYYY-MM-DD-rehearsal.md`.

## Sign-off

- [ ] All 6 steps completed
- [ ] All happy-path checkpoints passed
- [ ] All failure-path checkpoints passed (gates correctly refused)
- [ ] Backup restore verified within RTO
- [ ] Evidence saved to jolarca-compliance
- [ ] Any deviations recorded in drift-findings.md

---

## Professional Opinion

This rehearsal covers four failure classes:
1. **Clean deploy** (step 1) — proves the pipeline works
2. **Blocked apply** (step 2) — proves the migration gate holds
3. **Destructive plan** (step 3) — proves the safety gate holds
4. **Credential failure** (step 4) — proves fail-loud behaviour
5. **Rollback** (step 5) — proves recovery is possible

The rehearsal does NOT test live apply (step 2 is deliberately refused).
Live apply testing requires the state migration to complete first
(docs/state-migration-runbook.md). Until then, this rehearsal validates
the gates, not the deployment.
