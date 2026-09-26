# Business Continuity Policy — jolarca-dr

## Purpose

This policy defines the **business continuity framework, roles, escalation
paths, and recovery priorities** for the `jolarca-dev` marketplace. It satisfies
ISO 27001 A.8.14 (redundancy of information processing facilities) and SOC 2
A1.3 (business continuity testing).

## Scope

This policy applies to all marketplace services, infrastructure, and governance
processes managed by the `jolarca-dev` organization.

## Business Continuity Objectives

### 1. Availability Targets

| Service Tier | Availability Target | Maximum Tolerable Downtime (MTD) |
|---|---|---|
| Tier 1 (payment processing, customer data) | 99.9% | 8.76 hours/year |
| Tier 2 (marketplace operations, compliance) | 99.5% | 43.8 hours/year |
| Tier 3 (internal tooling, documentation) | 95% | 438 hours/year |

### 2. Recovery Priorities

In a disaster, recovery follows this priority order:

1. **Tier 1 services** — payment processing, customer data access, security controls
2. **Tier 2 services** — marketplace operations, compliance reporting, audit trails
3. **Tier 3 services** — internal tooling, documentation, non-critical automation

Within each tier, recovery follows the RTO defined in `rpo-rto/definitions.md`.

### 3. Single-Operator Reality (D-10)

**Current state:** The marketplace has one operator (@JourneyOfLife). Business
continuity in the single-operator era means:

- **No redundancy in personnel** — if the operator is unavailable, recovery is delayed
- **Documentation is critical** — runbooks must be clear enough for an external
  consultant to follow in an emergency
- **Automation is a force multiplier** — automated backups, monitoring, and alerts
  reduce the operator's cognitive load during a crisis
- **Escalation is manual** — the operator must self-escalate; there is no backup

**Mitigation:** When a second operator onboards (D-10 resolution), this policy
must be updated to reflect:

- A named backup operator with DR training
- Escalation paths and on-call rotation
- Cross-training requirements (both operators must know the runbooks)

## Disaster Scenarios

### Scenario 1: Terraform State Corruption

**Impact:** Cannot manage infrastructure via IaC; manual intervention required.

**RTO:** 4 hours (Tier 1 services unaffected; governance control plane degraded).

**Response:**
1. Assess corruption scope (partial vs. total state loss)
2. Restore from backup (see `runbooks/state-restore.md`)
3. Verify state integrity (SHA256 checksum)
4. Run `terraform plan` to confirm no drift
5. Document incident in `jolarca-compliance`

### Scenario 2: Infrastructure Compromise

**Impact:** Attacker has control of live infrastructure; data exfiltration risk.

**RTO:** 24 hours (Tier 1 services may be offline during containment).

**Response:**
1. Contain: revoke compromised credentials (see `runbooks/credential-rotation.md`)
2. Assess: determine scope of compromise (audit logs, forensic analysis)
3. Rebuild: restore infrastructure from IaC (see `runbooks/infrastructure-restore.md`)
4. Restore: recover data from backup (see `runbooks/data-restore.md`)
5. Verify: confirm no residual compromise
6. Document: record incident in `jolarca-compliance`, notify affected parties if required (GDPR Art. 33)

### Scenario 3: GitHub Organization Compromise

**Impact:** Attacker has control of `jolarca-dev` org; repositories, secrets, and
settings at risk.

**RTO:** 48 hours (marketplace operations degraded; compliance reporting offline).

**Response:**
1. Contain: revoke GitHub token, enable org-wide 2FA (if not already enabled)
2. Assess: determine scope of compromise (which repos, secrets, settings)
3. Recover: restore repository settings from `jolarca-control` Terraform state
4. Rotate: rotate all secrets (see `runbooks/credential-rotation.md`)
5. Verify: confirm no residual compromise
6. Document: record incident in `jolarca-compliance`

### Scenario 4: Data Loss

**Impact:** Customer data, transaction records, or audit logs lost or corrupted.

**RTO:** 8 hours (Tier 1 services degraded; GDPR Art. 33 notification may be required).

**Response:**
1. Assess: determine scope of data loss (which data, what time range)
2. Restore: recover from backup (see `runbooks/data-restore.md`)
3. Verify: confirm data integrity (checksums, row counts, sample validation)
4. Notify: if personal data lost, assess GDPR Art. 33 notification requirement
5. Document: record incident in `jolarca-compliance`

### Scenario 5: Regional Outage (GCP)

**Impact:** Entire GCP region unavailable; marketplace offline.

**RTO:** 24 hours (cross-region failover required).

**Response:**
1. Assess: confirm regional outage (GCP status dashboard, multiple sources)
2. Failover: activate cross-region backup (to be implemented)
3. Restore: recover services in secondary region
4. Verify: confirm service availability
5. Communicate: notify users of outage and recovery status
6. Document: record incident in `jolarca-compliance`

## Roles and Responsibilities

### Current (Single-Operator Era)

| Role | Person | Responsibilities |
|---|---|---|
| Operator | @JourneyOfLife | Execute DR runbooks, make recovery decisions, document incidents |
| Auditor | External (quarterly) | Verify DR policy compliance, review rehearsal evidence |
| Legal counsel | External (as needed) | Advise on GDPR notification requirements, contractual obligations |

### Target State (Post-D-10)

| Role | Person | Responsibilities |
|---|---|---|
| Primary operator | @JourneyOfLife | Execute DR runbooks, make recovery decisions |
| Backup operator | TBD | Support primary operator, execute runbooks if primary unavailable |
| Security lead | TBD | Assess compromise scope, advise on containment, lead forensic analysis |
| Communications lead | TBD | Notify users, manage public communications during outage |
| Legal counsel | External | Advise on regulatory notification requirements |

## Escalation Path

### Current (Single-Operator Era)

```
Incident detected
    ↓
Operator assesses severity
    ↓
┌─────────────────┬──────────────────┬─────────────────┐
│ Low (Tier 3)    │ Medium (Tier 2)  │ High (Tier 1)   │
│ Document in     │ Document +       │ Document +      │
│ compliance repo │ schedule recovery│ immediate       │
│                 │ within 4 hours   │ recovery        │
└─────────────────┴──────────────────┴─────────────────┘
```

### Target State (Post-D-10)

```
Incident detected
    ↓
On-call operator assesses severity
    ↓
┌─────────────────┬──────────────────┬─────────────────┐
│ Low (Tier 3)    │ Medium (Tier 2)  │ High (Tier 1)   │
│ Document +      │ Document +       │ Document +      │
│ schedule within │ notify security  │ notify security │
│ 24 hours        │ lead, recover    │ lead, recover   │
│                 │ within 4 hours   │ immediately     │
└─────────────────┴──────────────────┴─────────────────┘
    ↓
If GDPR notification required (Art. 33):
    ↓
Legal counsel notified within 24 hours
    ↓
Supervisory authority notified within 72 hours (if required)
```

## Communication Plan

### Internal Communication

- **Incident detected:** Operator notified via monitoring alert (PagerDuty, Slack, email)
- **Recovery in progress:** Operator updates status in incident channel (Slack, Teams)
- **Recovery complete:** Operator posts incident summary in compliance repo

### External Communication

- **Users notified:** If Tier 1 services unavailable > 1 hour, post status update on marketplace status page
- **Customers notified:** If customer data affected, send email notification within 72 hours (GDPR Art. 34)
- **Regulators notified:** If personal data breach, notify supervisory authority within 72 hours (GDPR Art. 33)
- **Public statement:** If outage > 24 hours, post public statement on marketplace website

## Business Continuity Testing

### Rehearsal Schedule

- **Quarterly:** Tabletop exercise (walk through a disaster scenario, verify runbook steps)
- **Semi-annually:** Functional exercise (restore a non-production service from backup)
- **Annually:** Full-scale exercise (simulate regional outage, activate cross-region failover)

### Rehearsal Evidence

All rehearsals documented in `jolarca-compliance` (see
`rehearsals/rehearsal-procedure.md`). Evidence includes:

- Scenario description
- Steps taken
- Time to recovery (actual vs. RTO)
- Issues encountered
- Lessons learned
- Sign-off by operator

## Compliance Mapping

| Framework | Control | Requirement |
|---|---|---|
| ISO 27001 | A.8.14 | Redundancy of information processing facilities |
| SOC 2 | A1.3 | Business continuity and disaster recovery testing |
| PCI-DSS | Req 12.10 | Incident response — business recovery |
| GDPR | Art. 32 | Resilience of processing systems |

## References

- `rpo-rto/definitions.md` — RPO/RTO per asset tier
- `runbooks/state-restore.md` — Terraform state restore procedure
- `runbooks/infrastructure-restore.md` — Infrastructure rebuild procedure
- `runbooks/data-restore.md` — Application data restore procedure
- `runbooks/credential-rotation.md` — Credential rotation procedure
- `rehearsals/rehearsal-procedure.md` — DR rehearsal procedure
