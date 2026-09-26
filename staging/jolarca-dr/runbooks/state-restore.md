# State Restore Runbook — jolarca-dr

## Purpose

This runbook describes how to **restore Terraform state** from backup after
corruption, loss, or compromise. It satisfies ISO 27001 A.8.13 (information
backup) and is referenced in `docs/state-migration-runbook.md` (jolarca-control).

## When to Use This Runbook

- Terraform state file (`terraform.tfstate`) is corrupted or deleted
- Terraform state is out of sync with live infrastructure (drift detected)
- Terraform state is compromised (attacker gained access to state)
- Remote backend is unavailable (GCS bucket deleted or inaccessible)

## Prerequisites

- Access to backup storage (GCS bucket or local backup directory)
- `terraform` CLI installed
- `GITHUB_TOKEN` environment variable set (for Terraform GitHub provider)
- SHA256 checksum of backup file (for verification)

## Current State (D-02: No Remote Backend)

**Until the remote backend migration is complete** (see
`docs/state-migration-runbook.md`), Terraform state is stored locally:

- `jolarca-control/terraform.tfstate` — governance control plane state
- `jolarca-infrastructure/terraform/terraform.tfstate` — infrastructure state

Backups are manual copies taken before each `terraform apply` (see
`docs/state-migration-runbook.md` Step 0).

### Restore Procedure (Local State)

#### Step 1: Assess the Situation

```bash
# Check if state file exists
ls -lh terraform.tfstate

# Check if backup exists
ls -lh terraform.tfstate.backup
ls -lh /opt/jolarca/backups/tfstate/  # off-host backup directory
```

**Decision point:**
- If `terraform.tfstate` exists but is corrupted → proceed to Step 2
- If `terraform.tfstate` is missing → proceed to Step 2
- If no backup exists → **STOP. Escalate to operator.** State cannot be restored;
  infrastructure must be rebuilt from scratch via `terraform import` (see
  `runbooks/infrastructure-restore.md`)

#### Step 2: Locate the Most Recent Backup

```bash
# List backups by timestamp
ls -lht /opt/jolarca/backups/tfstate/

# Example output:
# github_org-20260926-143022.tfstate
# github_org-20260925-091544.tfstate
# github_org-20260924-162033.tfstate.backup
```

**Select the most recent backup** that predates the incident.

#### Step 3: Verify Backup Integrity

```bash
# Compute SHA256 of backup
sha256sum /opt/jolarca/backups/tfstate/github_org-20260926-143022.tfstate

# Compare with recorded checksum (if available)
# Checksums are recorded in /opt/jolarca/backups/tfstate/checksums.txt
cat /opt/jolarca/backups/tfstate/checksums.txt | grep github_org-20260926-143022

# If checksums do not match → DO NOT USE THIS BACKUP. Try the next most recent.
```

**A backup without a verified checksum is not a backup.** If you cannot verify
the checksum, the backup may be corrupted and restore will fail.

#### Step 4: Restore the Backup

```bash
# Backup the current (corrupted) state file
cp terraform.tfstate terraform.tfstate.corrupted.$(date +%Y%m%d-%H%M%S)

# Copy the verified backup to the working directory
cp /opt/jolarca/backups/tfstate/github_org-20260926-143022.tfstate terraform.tfstate

# Verify the restored file
ls -lh terraform.tfstate
```

#### Step 5: Verify State Integrity

```bash
# Initialize Terraform (if not already initialized)
terraform init

# Run terraform plan to check for drift
terraform plan

# Expected output: "No changes. Your infrastructure matches the configuration."
```

**Decision point:**
- If `terraform plan` shows no drift → restore successful, proceed to Step 6
- If `terraform plan` shows drift → state is out of sync with live infrastructure
  - If drift is acceptable (e.g., manual changes made after backup) → proceed to Step 6
  - If drift is unexpected → **STOP. Escalate to operator.** State may be stale.

#### Step 6: Verify Infrastructure State

```bash
# List all resources in state
terraform state list

# Spot-check critical resources
terraform state show github_repository.repo[\"jolarca-control\"]
terraform state show github_repository.repo[\"jolarca-infrastructure\"]

# Verify branch protection
terraform state show github_branch_protection.main[\"jolarca-control\"]
```

**Verify:**
- All expected repositories are in state
- Branch protection rules are present
- Settings match expected values (see `repos/*.yml`)

#### Step 7: Document the Restore

Record the restore in `jolarca-compliance`:

- **Timestamp:** When the restore was performed
- **Backup used:** Which backup file was restored
- **Checksum verification:** SHA256 of the backup
- **Drift detected:** Yes/no, and if yes, what drift
- **Operator:** Who performed the restore
- **Incident reference:** Link to incident record (if applicable)

## Target State (Post-D-02: Remote Backend)

**After the remote backend migration** (see
`docs/runbooks/workload-identity-federation.md`), Terraform state is stored in
GCS:

```hcl
terraform {
  backend "gcs" {
    bucket = "jolarca-tfstate"
    prefix = "jolarca-control"
  }
}
```

### Restore Procedure (Remote State)

#### Step 1: Assess the Situation

```bash
# Check if remote state is accessible
terraform init

# If init fails → GCS bucket may be deleted or inaccessible
# Proceed to Step 2
```

#### Step 2: Locate the Most Recent Backup

```bash
# List backups in GCS
gsutil ls gs://jolarca-tfstate-backups/jolarca-control/

# Example output:
# gs://jolarca-tfstate-backups/jolarca-control/terraform.tfstate-20260926-143022
# gs://jolarca-tfstate-backups/jolarca-control/terraform.tfstate-20260925-091544
```

#### Step 3: Verify Backup Integrity

```bash
# Download the backup
gsutil cp gs://jolarca-tfstate-backups/jolarca-control/terraform.tfstate-20260926-143022 /tmp/terraform.tfstate

# Compute SHA256
sha256sum /tmp/terraform.tfstate

# Compare with recorded checksum
gsutil cat gs://jolarca-tfstate-backups/jolarca-control/checksums.txt | grep terraform.tfstate-20260926-143022
```

#### Step 4: Restore the Backup

```bash
# Upload the verified backup to the primary GCS bucket
gsutil cp /tmp/terraform.tfstate gs://jolarca-tfstate/jolarca-control/terraform.tfstate

# Re-initialize Terraform
terraform init
```

#### Step 5: Verify State Integrity

```bash
# Run terraform plan
terraform plan

# Expected output: "No changes."
```

## Post-Restore Checklist

- [ ] State file restored from verified backup
- [ ] `terraform plan` shows no unexpected drift
- [ ] All expected resources present in state
- [ ] Branch protection rules verified
- [ ] Restore documented in `jolarca-compliance`
- [ ] Incident record updated (if applicable)

## Troubleshooting

### "terraform plan shows drift after restore"

**Cause:** State is out of sync with live infrastructure.

**Resolution:**
1. Review drift carefully — is it expected (manual changes) or unexpected (compromise)?
2. If expected: run `terraform apply` to update state
3. If unexpected: **STOP. Escalate to operator.** State may be stale or compromised.

### "No backups found"

**Cause:** Backups were not taken, or backup storage is also compromised.

**Resolution:**
1. Check if local backups exist (`ls -lh terraform.tfstate.backup`)
2. Check if off-host backups exist (`ls -lh /opt/jolarca/backups/tfstate/`)
3. If no backups exist → **STOP. Escalate to operator.** State cannot be restored;
   infrastructure must be rebuilt from scratch via `terraform import` (see
   `runbooks/infrastructure-restore.md`)

### "Checksum mismatch"

**Cause:** Backup file is corrupted or tampered with.

**Resolution:**
1. Try the next most recent backup
2. If all backups fail checksum verification → **STOP. Escalate to operator.**
   Backup storage may be compromised.

## Compliance Mapping

| Framework | Control | Requirement |
|---|---|---|
| ISO 27001 | A.8.13 | Information backup — restore procedure tested |
| SOC 2 | A1.2 | Recovery from disasters — state restore tested |
| PCI-DSS | Req 12.10 | Incident response — recovery procedures |

## References

- `docs/state-migration-runbook.md` — State backup procedure (jolarca-control)
- `docs/runbooks/workload-identity-federation.md` — Remote backend migration
- `policies/backup-policy.md` — Backup frequency and retention
- `rpo-rto/definitions.md` — RPO/RTO for Terraform state
