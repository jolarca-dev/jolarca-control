# Backup Policy — jolarca-dr

## Purpose

This policy defines **what must be backed up, how often, where backups are
stored, and how long they are retained** for the `jolarca-dev` marketplace.
It satisfies ISO 27001 A.8.13 (information backup) and SOC 2 A1.2 (recovery
from disasters).

## Scope

This policy applies to all marketplace infrastructure, application data, and
governance artifacts managed by the `jolarca-dev` organization.

## Backup Categories

### 1. Terraform State

**What:** All Terraform state files (`*.tfstate`, `*.tfstate.*`) managed by
`jolarca-control` and `jolarca-infrastructure`.

**RPO:** 1 hour (state changes are infrequent; a 1-hour window is acceptable
for a governance control plane).

**Retention:** 30 days of daily backups + 12 monthly backups.

**Storage:**
- **Primary:** Remote GCS bucket ( Workload Identity Federation — see
  `docs/runbooks/workload-identity-federation.md`)
- **Secondary:** Local copy on operator workstation (transitional — D-02
  requires migration to remote backend)
- **Tertiary:** Off-site backup to a separate GCP project or object storage
  (to be implemented)

**Encryption:** AES-256 at rest (GCS default). Encryption keys managed by GCP
KMS (to be implemented).

**Verification:** SHA256 checksum recorded at backup time; verified before
restore. A backup without a verified checksum is not a backup.

### 2. GitHub Repository Metadata

**What:** Repository settings, branch protection rules, CODEOWNERS, webhooks,
and secrets (metadata only — not code or state).

**RPO:** 24 hours (metadata changes are infrequent; daily backup is sufficient).

**Retention:** 90 days.

**Storage:**
- **Primary:** `jolarca-control` Terraform state (the allow-list in `repos/*.yml`
  is the source of truth; state captures the live configuration)
- **Secondary:** GitHub API export (to be implemented — `scripts/backup_github_metadata.sh`)

**Encryption:** In transit (HTTPS). At rest: same as Terraform state.

### 3. Application Data

**What:** Database dumps, file uploads, user-generated content, and any
persistent data stored by marketplace applications.

**RPO:** 1 hour (customer transactions must be recoverable with minimal data loss).

**Retention:** 30 days of hourly backups + 12 monthly backups + 7 yearly backups.

**Storage:**
- **Primary:** Database-native backup (e.g., PostgreSQL WAL archiving, MySQL binlog)
- **Secondary:** Daily snapshot to GCS
- **Tertiary:** Weekly snapshot to a separate GCP region (cross-region redundancy)

**Encryption:** AES-256 at rest. Encryption keys managed by GCP KMS.

**Verification:** Automated restore test monthly (see `rehearsals/rehearsal-procedure.md`).

### 4. Secrets and Credentials

**What:** API keys, tokens, certificates, and other secrets managed by
`jolarca-infrastructure` (e.g., Vault secrets, GitHub Actions secrets).

**RPO:** 24 hours (secrets are rotated regularly; a 24-hour window is acceptable).

**Retention:** 90 days (secrets expire; retaining them longer increases risk).

**Storage:**
- **Primary:** Vault (encrypted at rest, access-controlled)
- **Secondary:** Vault snapshot (daily)
- **Tertiary:** Encrypted export to GCS (to be implemented)

**Encryption:** AES-256 at rest. Vault unseal keys stored in separate locations
(to be implemented — see `runbooks/credential-rotation.md`).

**Verification:** Automated secret rotation test quarterly.

### 5. Audit Logs

**What:** GitHub audit logs, GCP audit logs, application logs, and security
event logs.

**RPO:** 1 hour (audit logs are critical for incident response and compliance).

**Retention:** 1 year (PCI-DSS Req 10.7 requires 1-year retention; 3 months
online, 9 months archived).

**Storage:**
- **Primary:** GCP Logging (online, searchable)
- **Secondary:** GCS bucket (archived, immutable)
- **Tertiary:** Cross-region GCS bucket (to be implemented)

**Encryption:** AES-256 at rest. Immutable storage (Object Versioning + Retention Policy).

**Verification:** Automated log ingestion test weekly.

## Backup Schedule

| Category | Frequency | Retention | Verification |
|---|---|---|---|
| Terraform state | Hourly | 30 days + 12 months | SHA256 checksum before restore |
| GitHub metadata | Daily | 90 days | Manual review quarterly |
| Application data | Hourly | 30 days + 12 months + 7 years | Automated restore test monthly |
| Secrets | Daily | 90 days | Automated rotation test quarterly |
| Audit logs | Hourly | 1 year | Automated ingestion test weekly |

## Backup Security

- **Access control:** Only the operator (and future DR team) may access backups.
  Access is logged and reviewed quarterly.
- **Encryption:** All backups encrypted at rest (AES-256) and in transit (TLS 1.3).
- **Integrity:** SHA256 checksums recorded at backup time; verified before restore.
- **Isolation:** Backups stored in separate GCP projects/regions to survive
  compromise of the primary infrastructure.

## Backup Testing

Backups are tested quarterly via DR rehearsals (see
`rehearsals/rehearsal-procedure.md`). A backup that has not been tested is not
a backup — it is a hope.

## Responsibilities

- **Operator:** Ensure backups run on schedule, verify checksums, conduct
  quarterly rehearsals.
- **Auditor:** Verify backup policy compliance, review rehearsal evidence.
- **Incident responder:** Use backups to restore systems after a disaster
  (see `runbooks/state-restore.md`, `runbooks/infrastructure-restore.md`).

## Compliance Mapping

| Framework | Control | Requirement |
|---|---|---|
| ISO 27001 | A.8.13 | Backup policy for information, software, and systems |
| SOC 2 | A1.2 | Recovery from disasters, hardware/software failures |
| PCI-DSS | Req 12.10 | Incident response — recovery procedures |
| GDPR | Art. 32 | Resilience and restoration of personal data |

## References

- `runbooks/state-restore.md` — How to restore Terraform state
- `runbooks/infrastructure-restore.md` — How to rebuild infrastructure
- `runbooks/data-restore.md` — How to restore application data
- `rehearsals/rehearsal-procedure.md` — How to conduct a DR rehearsal
- `docs/state-migration-runbook.md` — State backup procedure (jolarca-control)
