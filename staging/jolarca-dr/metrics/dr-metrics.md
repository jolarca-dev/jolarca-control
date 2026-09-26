# DR Metrics — jolarca-dr

## Purpose

This document defines the **key performance indicators (KPIs)** for measuring
the effectiveness of disaster recovery and business continuity practices in the
`jolarca-dev` marketplace. It satisfies SOC 2 A1.3 (business continuity testing)
and ISO 27001 A.8.13 (information backup — monitoring and measurement).

## Metrics Overview

### 1. Rehearsal Frequency

**Definition:** Number of DR rehearsals conducted per quarter.

**Target:** Minimum 1 tabletop exercise per quarter, 1 functional exercise per
semi-annual period, 1 full-scale exercise per year.

**Measurement:**
- Count rehearsals completed each quarter
- Track rehearsal type (tabletop, functional, full-scale)
- Compare actual vs. target

**Current Status:**
- Q3 2026: 0 rehearsals (repository not yet populated)
- Q4 2026: Target 1 tabletop exercise
- 2027: Target 4 tabletop, 2 functional, 1 full-scale

**Why it matters:** Regular rehearsals verify that backups can be restored and
runbooks are accurate. A rehearsal gap > 6 months indicates a control weakness.

### 2. RTO Achievement

**Definition:** Percentage of rehearsals where actual RTO ≤ target RTO.

**Target:** 100% of rehearsals achieve target RTO.

**Measurement:**
- For each rehearsal, measure actual time to restore
- Compare with target RTO from `rpo-rto/definitions.md`
- Calculate achievement rate: (rehearsals achieving RTO / total rehearsals) × 100

**Current Status:**
- No rehearsals conducted yet
- Target: 100% achievement rate once rehearsals begin

**Why it matters:** RTO achievement demonstrates that recovery procedures are
effective and can meet business requirements. Missing RTO indicates a need to
improve procedures, invest in automation, or adjust RTO targets.

### 3. RPO Achievement

**Definition:** Percentage of rehearsals where actual data loss ≤ target RPO.

**Target:** 100% of rehearsals achieve target RPO.

**Measurement:**
- For each rehearsal, measure actual data loss (time between backup and incident)
- Compare with target RPO from `rpo-rto/definitions.md`
- Calculate achievement rate: (rehearsals achieving RPO / total rehearsals) × 100

**Current Status:**
- No rehearsals conducted yet
- Target: 100% achievement rate once rehearsals begin

**Why it matters:** RPO achievement demonstrates that backup frequency is
sufficient to meet business requirements. Missing RPO indicates a need to
increase backup frequency or improve backup reliability.

### 4. Backup Success Rate

**Definition:** Percentage of scheduled backups that complete successfully.

**Target:** 99.9% success rate (no more than 8.76 hours of missed backups per year).

**Measurement:**
- Count scheduled backups per category (Terraform state, application data, etc.)
- Count successful backups
- Calculate success rate: (successful backups / scheduled backups) × 100

**Current Status:**
- Terraform state: Manual backups (success rate depends on operator discipline)
- Application data: Automated backups (success rate TBD)
- Target: 99.9% once automated backup system is in place

**Why it matters:** Backup success rate indicates the reliability of the backup
system. A success rate < 99.9% means data loss is likely in a disaster.

### 5. Backup Verification Rate

**Definition:** Percentage of backups with verified SHA256 checksums.

**Target:** 100% of backups verified.

**Measurement:**
- Count backups with recorded SHA256 checksums
- Count total backups
- Calculate verification rate: (verified backups / total backups) × 100

**Current Status:**
- Terraform state: Checksums recorded in `/opt/jolarca/backups/tfstate/checksums.txt`
- Application data: Checksum verification TBD
- Target: 100% verification rate

**Why it matters:** A backup without a verified checksum is not a backup — it is
a hope. Verification ensures backups can be restored and have not been corrupted.

### 6. Mean Time to Detect (MTTD)

**Definition:** Average time from incident occurrence to incident detection.

**Target:** < 1 hour for Tier 1 services, < 4 hours for Tier 2 services.

**Measurement:**
- For each incident, measure time from occurrence to detection
- Calculate average: sum(MTTD) / count(incidents)
- Track by service tier

**Current Status:**
- No incidents tracked yet
- Target: < 1 hour for Tier 1 once monitoring is in place

**Why it matters:** Faster detection means faster recovery. High MTTD indicates
a need for better monitoring, alerting, or observability.

### 7. Mean Time to Recover (MTTR)

**Definition:** Average time from incident detection to service recovery.

**Target:** < RTO for each service tier (see `rpo-rto/definitions.md`)

**Measurement:**
- For each incident, measure time from detection to recovery
- Calculate average: sum(MTTR) / count(incidents)
- Track by service tier

**Current Status:**
- No incidents tracked yet
- Target: < RTO for each tier

**Why it matters:** MTTR indicates the effectiveness of recovery procedures. High
MTTR indicates a need to improve procedures, invest in automation, or adjust RTO
targets.

### 8. Credential Rotation Compliance

**Definition:** Percentage of credentials rotated within the required timeframe.

**Target:** 100% of credentials rotated per policy (quarterly or post-incident).

**Measurement:**
- Count credentials requiring rotation
- Count credentials rotated within timeframe
- Calculate compliance rate: (credentials rotated / credentials requiring rotation) × 100

**Current Status:**
- No rotation tracking yet
- Target: 100% compliance once rotation schedule is established

**Why it matters:** Credential rotation reduces the risk of credential compromise.
Non-compliance indicates a control weakness.

### 9. DR Documentation Freshness

**Definition:** Age of DR runbooks and policies (time since last review).

**Target:** All documents reviewed and updated within the last 6 months.

**Measurement:**
- For each DR document, check last modified date
- Calculate age: current date - last modified date
- Flag documents > 6 months old

**Current Status:**
- All documents created 2026-09-26 (this repository)
- Next review: 2027-03-26

**Why it matters:** Stale documentation leads to failed recoveries. Regular
reviews ensure procedures are accurate and reflect current infrastructure.

### 10. Incident Response Time

**Definition:** Time from incident declaration to first response action.

**Target:** < 15 minutes for Tier 1 incidents, < 1 hour for Tier 2 incidents.

**Measurement:**
- For each incident, measure time from declaration to first action
- Calculate average: sum(response times) / count(incidents)
- Track by incident severity

**Current Status:**
- No incidents tracked yet
- Target: < 15 minutes for Tier 1 once incident response process is established

**Why it matters:** Faster response means faster containment and recovery. High
response time indicates a need for better alerting or on-call processes.

## Metrics Dashboard

| Metric | Q3 2026 | Q4 2026 | Q1 2027 | Q2 2027 | Trend |
|---|---|---|---|---|---|
| Rehearsal frequency | 0 | Target: 1 | Target: 1 | Target: 1 | ↑ |
| RTO achievement | N/A | Target: 100% | Target: 100% | Target: 100% | → |
| RPO achievement | N/A | Target: 100% | Target: 100% | Target: 100% | → |
| Backup success rate | Manual | Target: 99.9% | Target: 99.9% | Target: 99.9% | ↑ |
| Backup verification rate | Partial | Target: 100% | Target: 100% | Target: 100% | ↑ |
| MTTD (Tier 1) | N/A | Target: < 1h | Target: < 1h | Target: < 1h | → |
| MTTR (Tier 1) | N/A | Target: < 4h | Target: < 4h | Target: < 4h | → |
| Credential rotation compliance | N/A | Target: 100% | Target: 100% | Target: 100% | → |
| DR documentation freshness | 0 days | < 180 days | < 180 days | < 180 days | → |
| Incident response time | N/A | Target: < 15m | Target: < 15m | Target: < 15m | → |

## Reporting

### Quarterly Report

Generate a quarterly DR metrics report and store in `jolarca-compliance`:

- Rehearsals conducted (count, type, scenarios)
- RTO/RPO achievement rates
- Backup success and verification rates
- Incidents and response times
- Credential rotation compliance
- Documentation freshness
- Lessons learned and action items

### Annual Report

Generate an annual DR metrics report for auditors:

- Summary of all quarterly reports
- Year-over-year trends
- Compliance with SOC 2 A1.3, ISO 27001 A.8.13, PCI-DSS Req 12.10, GDPR Art. 32
- Recommendations for improvement

## Compliance Mapping

| Framework | Control | Requirement |
|---|---|---|
| SOC 2 | A1.3 | Business continuity testing — metrics tracked and reported |
| ISO 27001 | A.8.13 | Information backup — monitoring and measurement |
| PCI-DSS | Req 12.10 | Incident response — metrics tracked |
| GDPR | Art. 32 | Resilience of processing systems — metrics tracked |

## References

- `rehearsals/rehearsal-procedure.md` — DR rehearsal procedure
- `rehearsals/evidence/2026-Q3-template.md` — Rehearsal evidence template
- `rpo-rto/definitions.md` — RPO/RTO definitions
- `policies/backup-policy.md` — Backup policy
- `policies/business-continuity-policy.md` — Business continuity policy
