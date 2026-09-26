# RPO/RTO Definitions — jolarca-dr

## Purpose

This document defines the **Recovery Point Objective (RPO)** and **Recovery
Time Objective (RTO)** for each asset category in the `jolarca-dev` marketplace.
It satisfies SOC 2 A1.2 (recovery from disasters) and ISO 27001 A.8.13 (information
backup).

## Definitions

- **RPO (Recovery Point Objective):** The maximum acceptable amount of data loss
  measured in time. If RPO is 1 hour, you can lose up to 1 hour of data in a
  disaster and still meet your business objectives.

- **RTO (Recovery Time Objective):** The maximum acceptable amount of time to
  restore a service after a disaster. If RTO is 4 hours, the service must be
  back online within 4 hours of the incident.

- **MTD (Maximum Tolerable Downtime):** The longest time a service can be
  unavailable before the business suffers irreparable harm. RTO must be ≤ MTD.

## RPO/RTO Matrix

| Asset Category | RPO | RTO | MTD | Justification |
|---|---|---|---|---|
| **Terraform state** (governance control plane) | 1 hour | 4 hours | 24 hours | State corruption blocks IaC management but does not affect live services. 4-hour RTO allows time for backup restore and verification. |
| **GitHub repository metadata** (settings, branch protection) | 24 hours | 8 hours | 48 hours | Metadata changes are infrequent. 8-hour RTO allows time for Terraform state restore and `terraform apply`. |
| **Application data** (customer transactions, user data) | 1 hour | 8 hours | 24 hours | Customer data loss directly impacts business operations and GDPR compliance. 1-hour RPO minimizes data loss; 8-hour RTO allows time for database restore and verification. |
| **Secrets and credentials** (API keys, tokens, certificates) | 24 hours | 4 hours | 12 hours | Secrets are rotated regularly. 4-hour RTO allows time for Vault restore or manual re-issuance. |
| **Audit logs** (GitHub, GCP, application) | 1 hour | 12 hours | 24 hours | Audit logs are critical for incident response and compliance. 12-hour RTO allows time for log restore from GCS archive. |
| **Infrastructure** (compute, network, storage) | N/A | 24 hours | 48 hours | Infrastructure is rebuilt from IaC (not restored from backup). 24-hour RTO allows time for `terraform apply` and service verification. |

## RPO/RTO by Service Tier

| Service Tier | RPO | RTO | MTD | Examples |
|---|---|---|---|---|
| **Tier 1** (payment processing, customer data) | 1 hour | 4 hours | 8 hours | Payment API, customer database, authentication service |
| **Tier 2** (marketplace operations, compliance) | 4 hours | 8 hours | 24 hours | Marketplace API, compliance reporting, audit log ingestion |
| **Tier 3** (internal tooling, documentation) | 24 hours | 24 hours | 72 hours | Internal dashboards, documentation sites, non-critical automation |

## Justification for RPO/RTO Choices

### Terraform State (RPO: 1h, RTO: 4h)

**Why 1-hour RPO?** Terraform state changes infrequently (only during `terraform apply`).
A 1-hour RPO means we can lose up to 1 hour of state changes — acceptable because
state changes are rare and the allow-list in `repos/*.yml` is the source of truth.

**Why 4-hour RTO?** State restore involves:
1. Locating the most recent backup (5 minutes)
2. Verifying SHA256 checksum (5 minutes)
3. Copying backup to working directory (5 minutes)
4. Running `terraform plan` to verify no drift (10 minutes)
5. Running `terraform apply` if drift detected (30 minutes)
6. Verifying infrastructure state (30 minutes)

Total: ~1.5 hours. 4-hour RTO provides a 2.5-hour buffer for complications.

### Application Data (RPO: 1h, RTO: 8h)

**Why 1-hour RPO?** Customer transactions must be recoverable with minimal data loss.
A 1-hour RPO means we can lose up to 1 hour of transactions — acceptable for a
marketplace where transactions are batched and reconciled daily.

**Why 8-hour RTO?** Database restore involves:
1. Identifying the point of failure (30 minutes)
2. Locating the most recent backup (15 minutes)
3. Restoring database from backup (2 hours)
4. Applying transaction logs to reach point of failure (1 hour)
5. Verifying data integrity (1 hour)
6. Reconnecting application services (30 minutes)
7. Running smoke tests (30 minutes)

Total: ~5.5 hours. 8-hour RTO provides a 2.5-hour buffer for complications.

### Infrastructure (RPO: N/A, RTO: 24h)

**Why N/A RPO?** Infrastructure is rebuilt from IaC, not restored from backup.
There is no "data loss" — the infrastructure is re-deployed from code.

**Why 24-hour RTO?** Infrastructure rebuild involves:
1. Assessing scope of failure (1 hour)
2. Running `terraform plan` to determine what needs to be rebuilt (30 minutes)
3. Running `terraform apply` to rebuild infrastructure (4 hours)
4. Verifying infrastructure state (2 hours)
5. Reconnecting services (2 hours)
6. Running smoke tests (2 hours)

Total: ~11.5 hours. 24-hour RTO provides a 12.5-hour buffer for complications.

## RPO/RTO Trade-offs

### Cost vs. Recovery Speed

- **Shorter RPO** requires more frequent backups → higher storage costs
- **Shorter RTO** requires more automation → higher development costs

The RPO/RTO choices above balance cost against business impact:

- Tier 1 services have short RPO/RTO because downtime directly impacts revenue and compliance
- Tier 3 services have long RPO/RTO because downtime is tolerable and recovery costs would exceed the cost of the outage

### Single-Operator Constraint (D-10)

The current single-operator era constrains RTO:

- **Cognitive load:** One person must execute all recovery steps → slower recovery
- **No redundancy:** If the operator is unavailable, recovery is delayed indefinitely
- **Mitigation:** Automated backups, monitoring, and alerts reduce cognitive load;
  runbooks are clear enough for an external consultant to follow

When a second operator onboards (D-10 resolution), RTOs can be shortened by
distributing recovery tasks and enabling parallel execution.

## Compliance Mapping

| Framework | Control | Requirement |
|---|---|---|
| SOC 2 | A1.2 | Recovery from disasters — RPO/RTO defined and tested |
| ISO 27001 | A.8.13 | Information backup — RPO defined per asset category |
| PCI-DSS | Req 12.10 | Incident response — recovery objectives defined |
| GDPR | Art. 32 | Resilience of processing systems — RTO defined |

## References

- `policies/backup-policy.md` — Backup frequency and retention
- `policies/business-continuity-policy.md` — Business continuity framework
- `runbooks/state-restore.md` — Terraform state restore procedure
- `runbooks/infrastructure-restore.md` — Infrastructure rebuild procedure
- `runbooks/data-restore.md` — Application data restore procedure
