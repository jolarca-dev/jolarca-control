# Infrastructure Restore Runbook — jolarca-dr

## Purpose

This runbook describes how to **rebuild infrastructure from IaC** after a
catastrophic failure where Terraform state cannot be restored. It satisfies
ISO 27001 A.8.14 (redundancy of information processing facilities) and SOC 2
A1.2 (recovery from disasters).

## When to Use This Runbook

- Terraform state is lost and no backup exists
- Infrastructure is corrupted beyond repair
- Attacker has compromised both infrastructure and state
- Regional outage requires rebuild in a different region

## Prerequisites

- Access to `jolarca-control` repository (IaC code)
- Access to `jolarca-infrastructure` repository (IaC code)
- `terraform` CLI installed
- `GITHUB_TOKEN` environment variable set
- Access to GCP project (for infrastructure resources)
- Understanding of the current infrastructure topology

## Critical Warning

**This runbook is a LAST RESORT.** It rebuilds infrastructure from scratch,
which means:

- All existing resources are destroyed and recreated
- Data not backed up is lost permanently
- Downtime is extended (24+ hours)
- IP addresses, DNS records, and other ephemeral identifiers change

**Only use this runbook if:**
1. State restore failed (see `runbooks/state-restore.md`)
2. Infrastructure is confirmed unrecoverable
3. Operator has authorized a full rebuild

## Procedure

### Phase 1: Assess the Situation

#### Step 1: Confirm Infrastructure Failure

```bash
# Check if infrastructure is accessible
curl -I https://marketplace.jolarca.dev

# Check GCP resources
gcloud compute instances list --project=jolarca-marketplace
gcloud sql instances list --project=jolarca-marketplace
gcloud container clusters list --project=jolarca-marketplace
```

**Decision point:**
- If infrastructure is accessible → **STOP.** This runbook is not needed.
- If infrastructure is inaccessible → proceed to Step 2

#### Step 2: Confirm State is Unrecoverable

```bash
# Check if state file exists
ls -lh terraform.tfstate

# Check if backups exist
ls -lh /opt/jolarca/backups/tfstate/

# Try to restore state (see runbooks/state-restore.md)
```

**Decision point:**
- If state can be restored → **STOP.** Use `runbooks/state-restore.md` instead.
- If state cannot be restored → proceed to Phase 2

### Phase 2: Prepare for Rebuild

#### Step 3: Document Current State

Before destroying anything, document what exists:

```bash
# List all GCP resources
gcloud compute instances list --project=jolarca-marketplace --format="csv(name,zone,status)" > /tmp/instances-before-rebuild.csv
gcloud sql instances list --project=jolarca-marketplace --format="csv(name,region,status)" > /tmp/sql-before-rebuild.csv
gcloud container clusters list --project=jolarca-marketplace --format="csv(name,location,status)" > /tmp/gke-before-rebuild.csv

# List all GitHub repositories
gh repo list jolarca-dev --json name,url,visibility > /tmp/repos-before-rebuild.json
```

**This documentation is critical for:**
- Post-rebuild verification
- Incident investigation
- Compliance evidence

#### Step 4: Backup What Remains

```bash
# Backup any accessible databases
gcloud sql export gs://jolarca-backups/db-export-$(date +%Y%m%d-%H%M%S).sql \
  --instance=marketplace-db \
  --database=marketplace

# Backup any accessible GCS buckets
gsutil -m rsync -r gs://jolarca-marketplace-data gs://jolarca-backups/marketplace-data-backup-$(date +%Y%m%d-%H%M%S)
```

#### Step 5: Notify Stakeholders

```bash
# Post status update
echo "Infrastructure rebuild in progress. Expected downtime: 24+ hours."

# If GDPR notification required (customer data at risk):
# Notify legal counsel immediately
```

### Phase 3: Rebuild Infrastructure

#### Step 6: Initialize Terraform

```bash
# Clone jolarca-control
git clone git@github.com:jolarca-dev/jolarca-control.git
cd jolarca-control

# Initialize Terraform (no state file — fresh start)
terraform init

# Verify configuration
terraform validate
```

#### Step 7: Plan the Rebuild

```bash
# Generate a plan to see what will be created
terraform plan -out=rebuild.plan

# Review the plan carefully
# Expected: all resources will be created (no existing state to compare against)
```

**Decision point:**
- If plan looks correct → proceed to Step 8
- If plan shows unexpected resources → **STOP. Review IaC code.**

#### Step 8: Apply the Rebuild

```bash
# Apply the plan
terraform apply rebuild.plan

# This will create all infrastructure from scratch
# Expected duration: 2-4 hours
```

**Monitor the apply:**
- Watch for errors (resource creation failures)
- Monitor GCP console for resource creation
- Check Terraform logs for warnings

#### Step 9: Import Existing Resources (If Any)

If some resources survived the failure (e.g., GCS buckets, DNS records), import
them into state to avoid duplication:

```bash
# Example: import an existing GCS bucket
terraform import google_storage_bucket.marketplace_data jolarca-marketplace-data

# Example: import an existing GitHub repository
terraform import github_repository.repo[\"jolarca-control\"] jolarca-control
```

**After import:**
```bash
# Verify state matches live infrastructure
terraform plan

# Expected: "No changes."
```

### Phase 4: Verify Infrastructure

#### Step 10: Verify Core Infrastructure

```bash
# Check GCP resources
gcloud compute instances list --project=jolarca-marketplace
gcloud sql instances list --project=jolarca-marketplace
gcloud container clusters list --project=jolarca-marketplace

# Compare with pre-rebuild documentation
diff /tmp/instances-before-rebuild.csv <(gcloud compute instances list --project=jolarca-marketplace --format="csv(name,zone,status)")
```

**Verify:**
- All expected resources exist
- Resources are in the correct regions/zones
- Resources are running (not terminated or failed)

#### Step 11: Verify GitHub Configuration

```bash
# Check repository settings
gh repo view jolarca-dev/jolarca-control --json name,visibility,defaultBranchRef
gh repo view jolarca-dev/jolarca-infrastructure --json name,visibility,defaultBranchRef

# Check branch protection
gh api repos/jolarca-dev/jolarca-control/branches/main/protection
gh api repos/jolarca-dev/jolarca-infrastructure/branches/main/protection

# Compare with repos/*.yml definitions
```

**Verify:**
- All repositories exist
- Visibility matches `repos/*.yml`
- Branch protection rules are enforced
- Required status checks are configured

#### Step 12: Verify Network Connectivity

```bash
# Test marketplace access
curl -I https://marketplace.jolarca.dev

# Test API endpoints
curl -I https://api.marketplace.jolarca.dev/health

# Test database connectivity
gcloud sql connect marketplace-db --user=marketplace
```

**Verify:**
- Marketplace is accessible
- API endpoints respond
- Database is accessible

#### Step 13: Verify Data Integrity

```bash
# Check database row counts
psql -h <db-host> -U marketplace -d marketplace -c "SELECT COUNT(*) FROM users;"
psql -h <db-host> -U marketplace -d marketplace -c "SELECT COUNT(*) FROM transactions;"

# Compare with pre-rebuild counts (if available)
```

**Verify:**
- Data is accessible
- Row counts match expectations
- No data corruption detected

### Phase 5: Post-Rebuild Tasks

#### Step 14: Rotate Credentials

After a full rebuild, **all credentials must be rotated** (see
`runbooks/credential-rotation.md`):

- GitHub tokens
- GCP service account keys
- Database passwords
- API keys
- Certificates

**Why?** If the rebuild was triggered by a compromise, the attacker may have
access to the old credentials.

#### Step 15: Update DNS Records

If IP addresses changed during the rebuild, update DNS records:

```bash
# Get new IP addresses
gcloud compute addresses list --project=jolarca-marketplace

# Update DNS records (manual or via Terraform)
# This step depends on your DNS provider
```

#### Step 16: Document the Rebuild

Record the rebuild in `jolarca-compliance`:

- **Timestamp:** When the rebuild started and completed
- **Reason:** Why the rebuild was necessary
- **Resources rebuilt:** List of resources created
- **Data loss:** What data was lost (if any)
- **Downtime:** Total downtime duration
- **Operator:** Who performed the rebuild
- **Incident reference:** Link to incident record

#### Step 17: Conduct Post-Mortem

Within 48 hours of rebuild completion:

1. **Root cause analysis:** What caused the infrastructure failure?
2. **Timeline:** When was the failure detected? When was it resolved?
3. **Impact:** What services were affected? What data was lost?
4. **Lessons learned:** What could be done differently next time?
5. **Action items:** What changes will prevent this from happening again?

Document the post-mortem in `jolarca-compliance`.

## Post-Rebuild Checklist

- [ ] Infrastructure rebuilt from IaC
- [ ] All expected resources present and running
- [ ] GitHub configuration verified
- [ ] Network connectivity verified
- [ ] Data integrity verified
- [ ] Credentials rotated
- [ ] DNS records updated (if needed)
- [ ] Rebuild documented in `jolarca-compliance`
- [ ] Post-mortem completed
- [ ] Action items tracked

## Troubleshooting

### "terraform apply fails with resource already exists"

**Cause:** Resource exists but is not in state.

**Resolution:**
```bash
# Import the existing resource
terraform import <resource_address> <resource_id>

# Example:
terraform import google_compute_instance.marketplace projects/jolarca-marketplace/zones/us-central1-a/instances/marketplace-vm
```

### "terraform apply fails with quota exceeded"

**Cause:** GCP project has reached resource quota limit.

**Resolution:**
1. Request quota increase from GCP
2. Wait for approval (may take 24-48 hours)
3. Retry `terraform apply`

### "Infrastructure is accessible but data is missing"

**Cause:** Data was not backed up before rebuild.

**Resolution:**
1. Restore data from backup (see `runbooks/data-restore.md`)
2. If no backup exists → **data is lost permanently**

## Compliance Mapping

| Framework | Control | Requirement |
|---|---|---|
| ISO 27001 | A.8.14 | Redundancy of information processing facilities |
| SOC 2 | A1.2 | Recovery from disasters — infrastructure rebuild tested |
| PCI-DSS | Req 12.10 | Incident response — recovery procedures |
| GDPR | Art. 32 | Resilience of processing systems |

## References

- `runbooks/state-restore.md` — Terraform state restore procedure
- `runbooks/data-restore.md` — Application data restore procedure
- `runbooks/credential-rotation.md` — Credential rotation procedure
- `policies/business-continuity-policy.md` — Business continuity framework
- `rpo-rto/definitions.md` — RPO/RTO for infrastructure
