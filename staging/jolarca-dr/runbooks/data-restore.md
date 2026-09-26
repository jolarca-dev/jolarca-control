# Data Restore Runbook — jolarca-dr

## Purpose

This runbook describes how to **restore application data** (databases, file
uploads, user-generated content) from backup after data loss or corruption. It
satisfies GDPR Art. 32 (resilience and restoration of personal data) and ISO
27001 A.8.13 (information backup).

## When to Use This Runbook

- Database is corrupted or deleted
- Application data is lost (e.g., accidental deletion, ransomware)
- Data integrity is compromised (e.g., SQL injection, malicious modification)
- Storage volumes are lost or inaccessible

## Prerequisites

- Access to backup storage (GCS bucket, database snapshots)
- Database CLI tools (`psql`, `mysql`, `mongorestore`, etc.)
- `gcloud` CLI installed and authenticated
- Understanding of the database schema and data model
- SHA256 checksum of backup file (for verification)

## Critical Considerations

### GDPR Art. 32 — Restoration of Personal Data

GDPR requires that systems processing personal data can **restore availability
and access to personal data in a timely manner** after an incident. This means:

- **RPO for personal data:** 1 hour (see `rpo-rto/definitions.md`)
- **RTO for personal data:** 8 hours (see `rpo-rto/definitions.md`)
- **Notification requirement:** If personal data is lost and cannot be restored,
  notify the supervisory authority within 72 hours (GDPR Art. 33)

### Data Integrity vs. Data Availability

After a restore, you must verify **both**:
1. **Data availability:** Data is accessible
2. **Data integrity:** Data is correct and has not been tampered with

A restore that makes data accessible but corrupt is worse than no restore at all.

## Procedure

### Phase 1: Assess the Situation

#### Step 1: Identify the Scope of Data Loss

```bash
# Check database connectivity
psql -h <db-host> -U marketplace -d marketplace -c "SELECT 1;"

# Check if tables are accessible
psql -h <db-host> -U marketplace -d marketplace -c "\dt"

# Check row counts for critical tables
psql -h <db-host> -U marketplace -d marketplace -c "SELECT COUNT(*) FROM users;"
psql -h <db-host> -U marketplace -d marketplace -c "SELECT COUNT(*) FROM transactions;"
```

**Decision point:**
- If database is accessible and data is intact → **STOP.** This runbook is not needed.
- If database is inaccessible → proceed to Step 2
- If data is corrupted or missing → proceed to Step 2

#### Step 2: Determine the Point of Failure

```bash
# Check database logs for errors
gcloud logging read "resource.type=cloudsql_database AND severity>=ERROR" --limit=100

# Check application logs for database errors
gcloud logging read "resource.type=gae_app AND textPayload:database" --limit=100
```

**Identify:**
- When did the data loss occur?
- What caused the data loss? (accidental deletion, corruption, ransomware)
- What data is affected? (which tables, which time range)

#### Step 3: Locate the Most Recent Backup

```bash
# List database snapshots
gcloud sql backups list --instance=marketplace-db --project=jolarca-marketplace

# List GCS backups
gsutil ls gs://jolarca-backups/ | grep db-export

# Example output:
# gs://jolarca-backups/db-export-20260926-143022.sql
# gs://jolarca-backups/db-export-20260925-091544.sql
```

**Select the most recent backup** that predates the incident.

### Phase 2: Prepare for Restore

#### Step 4: Verify Backup Integrity

```bash
# Download the backup
gsutil cp gs://jolarca-backups/db-export-20260926-143022.sql /tmp/db-restore.sql

# Compute SHA256
sha256sum /tmp/db-restore.sql

# Compare with recorded checksum (if available)
gsutil cat gs://jolarca-backups/checksums.txt | grep db-export-20260926-143022
```

**A backup without a verified checksum is not a backup.** If you cannot verify
the checksum, the backup may be corrupted.

#### Step 5: Create a Safety Backup

Before restoring, backup the current (corrupted) state:

```bash
# Export current database state (even if corrupted)
gcloud sql export gs://jolarca-backups/db-corrupted-$(date +%Y%m%d-%H%M%S).sql \
  --instance=marketplace-db \
  --database=marketplace
```

**Why?** If the restore fails or makes things worse, you can revert to the
pre-restore state.

#### Step 6: Notify Stakeholders

```bash
# Post status update
echo "Database restore in progress. Expected downtime: 8 hours."

# If personal data is at risk:
# Notify legal counsel immediately (GDPR Art. 33 may apply)
```

### Phase 3: Restore the Data

#### Step 7: Restore the Database

**Option A: Restore to a new instance (recommended)**

```bash
# Create a new database instance
gcloud sql instances create marketplace-db-restore \
  --database-version=POSTGRES_14 \
  --tier=db-custom-2-7680 \
  --region=us-central1 \
  --project=jolarca-marketplace

# Import the backup into the new instance
gcloud sql import sql marketplace-db-restore \
  gs://jolarca-backups/db-export-20260926-143022.sql \
  --database=marketplace \
  --project=jolarca-marketplace
```

**Why restore to a new instance?**
- Safer: original instance is untouched
- Allows side-by-side comparison
- Can switch back to original if restore fails

**Option B: Restore in place (faster, riskier)**

```bash
# Drop the existing database
psql -h <db-host> -U marketplace -c "DROP DATABASE marketplace;"

# Create a new database
psql -h <db-host> -U marketplace -c "CREATE DATABASE marketplace;"

# Import the backup
gcloud sql import sql marketplace-db \
  gs://jolarca-backups/db-export-20260926-143022.sql \
  --database=marketplace \
  --project=jolarca-marketplace
```

#### Step 8: Apply Transaction Logs (Point-in-Time Recovery)

If you need to recover to a specific point in time (e.g., just before the data
loss), apply transaction logs:

```bash
# List available transaction logs
gcloud sql operations list --instance=marketplace-db --project=jolarca-marketplace

# Restore to a specific timestamp
gcloud sql backups restore <backup-id> \
  --restore-time=2026-09-26T14:30:00Z \
  --project=jolarca-marketplace
```

**Note:** Point-in-time recovery requires continuous WAL archiving (PostgreSQL)
or binlog (MySQL). Verify this is configured in `policies/backup-policy.md`.

#### Step 9: Switch to the Restored Database

If you restored to a new instance (Option A):

```bash
# Update application configuration to point to the new instance
# This depends on your deployment method (environment variable, config file, etc.)

# Example: update environment variable
export DATABASE_HOST=marketplace-db-restore

# Restart application services
systemctl restart marketplace-api
```

### Phase 4: Verify Data Integrity

#### Step 10: Verify Data Availability

```bash
# Check database connectivity
psql -h <db-host> -U marketplace -d marketplace -c "SELECT 1;"

# Check if tables are accessible
psql -h <db-host> -U marketplace -d marketplace -c "\dt"
```

#### Step 11: Verify Data Integrity

```bash
# Check row counts
psql -h <db-host> -U marketplace -d marketplace -c "SELECT COUNT(*) FROM users;"
psql -h <db-host> -U marketplace -d marketplace -c "SELECT COUNT(*) FROM transactions;"

# Compare with pre-incident counts (if available)
# Example:
# Pre-incident: users=10,000, transactions=50,000
# Post-restore: users=10,000, transactions=50,000 → OK
# Post-restore: users=9,500, transactions=48,000 → Data loss detected
```

**Verify:**
- Row counts match expectations
- Sample data is correct (spot-check critical records)
- No data corruption detected (run application-level validation)

#### Step 12: Verify Application Functionality

```bash
# Run smoke tests
curl -I https://marketplace.jolarca.dev/health
curl -I https://api.marketplace.jolarca.dev/users

# Run automated test suite (if available)
pytest tests/
```

**Verify:**
- Application can connect to the database
- API endpoints respond correctly
- User workflows function as expected

### Phase 5: Post-Restore Tasks

#### Step 13: Assess Data Loss

If data loss is detected (row counts do not match):

```bash
# Identify missing data
psql -h <db-host> -U marketplace -d marketplace -c "
  SELECT MIN(created_at), MAX(created_at)
  FROM transactions
  WHERE created_at > '2026-09-26T14:00:00Z';
"
```

**Decision point:**
- If data loss is acceptable (within RPO) → proceed to Step 14
- If data loss is unacceptable → **STOP. Escalate to operator.** Additional
  recovery methods may be available (e.g., application logs, third-party backups)

#### Step 14: GDPR Notification Assessment

If personal data was lost and cannot be restored:

```bash
# Assess notification requirement
# GDPR Art. 33: notify supervisory authority within 72 hours
# GDPR Art. 34: notify data subjects if high risk to rights and freedoms
```

**Consult legal counsel** before making notification decisions.

#### Step 15: Document the Restore

Record the restore in `jolarca-compliance`:

- **Timestamp:** When the restore was performed
- **Backup used:** Which backup file was restored
- **Checksum verification:** SHA256 of the backup
- **Data loss:** What data was lost (if any)
- **Downtime:** Total downtime duration
- **Operator:** Who performed the restore
- **Incident reference:** Link to incident record

#### Step 16: Clean Up

```bash
# Delete the temporary restore instance (if created)
gcloud sql instances delete marketplace-db-restore --project=jolarca-marketplace

# Delete temporary backup files
rm /tmp/db-restore.sql
```

## Post-Restore Checklist

- [ ] Database restored from verified backup
- [ ] Data availability verified (tables accessible)
- [ ] Data integrity verified (row counts match)
- [ ] Application functionality verified (smoke tests pass)
- [ ] Data loss assessed (if any)
- [ ] GDPR notification assessment completed (if personal data lost)
- [ ] Restore documented in `jolarca-compliance`
- [ ] Temporary resources cleaned up

## Troubleshooting

### "Import fails with 'database already exists'"

**Cause:** Database already exists on the target instance.

**Resolution:**
```bash
# Drop the existing database
psql -h <db-host> -U marketplace -c "DROP DATABASE marketplace;"

# Retry the import
gcloud sql import sql marketplace-db \
  gs://jolarca-backups/db-export-20260926-143022.sql \
  --database=marketplace \
  --project=jolarca-marketplace
```

### "Row counts do not match after restore"

**Cause:** Backup predates some transactions, or data was lost during the incident.

**Resolution:**
1. Assess the scope of data loss (which transactions are missing)
2. Check if application logs can be used to reconstruct missing data
3. If data loss is unacceptable → **STOP. Escalate to operator.**

### "Application cannot connect to restored database"

**Cause:** Database credentials changed during restore, or connection string is incorrect.

**Resolution:**
```bash
# Verify database credentials
gcloud sql users list --instance=marketplace-db --project=jolarca-marketplace

# Update application configuration with correct credentials
# (depends on your deployment method)
```

## Compliance Mapping

| Framework | Control | Requirement |
|---|---|---|
| GDPR | Art. 32 | Resilience and restoration of personal data |
| ISO 27001 | A.8.13 | Information backup — restore procedure tested |
| SOC 2 | A1.2 | Recovery from disasters — data restore tested |
| PCI-DSS | Req 12.10 | Incident response — recovery procedures |

## References

- `policies/backup-policy.md` — Backup frequency and retention
- `rpo-rto/definitions.md` — RPO/RTO for application data
- `runbooks/state-restore.md` — Terraform state restore procedure
- `runbooks/infrastructure-restore.md` — Infrastructure rebuild procedure
