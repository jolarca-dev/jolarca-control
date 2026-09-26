# DR Rehearsal Procedure — jolarca-dr

## Purpose

This procedure defines **how to conduct disaster recovery rehearsals** to verify
that backup and restore procedures work as documented. It satisfies SOC 2 A1.3
(business continuity testing) and ISO 27001 A.8.13 (information backup — testing).

## Why Rehearse?

**A backup that has not been tested is not a backup — it is a hope.**

Rehearsals verify:
- Backups can be restored successfully
- Restore procedures are accurate and complete
- RPO/RTO targets are achievable
- Operators are familiar with the restore process
- Compliance requirements are met

## Rehearsal Types

### 1. Tabletop Exercise (Quarterly)

**What:** Walk through a disaster scenario step-by-step, discussing each action
without actually executing it.

**When:** Quarterly (minimum)

**Duration:** 2-3 hours

**Participants:** Operator (required), legal counsel (optional), external
auditor (optional)

**Scope:**
- Select a disaster scenario (see Scenarios below)
- Walk through the relevant runbook (`runbooks/state-restore.md`,
  `runbooks/infrastructure-restore.md`, or `runbooks/data-restore.md`)
- Identify gaps, ambiguities, or missing steps
- Update runbooks as needed

**Deliverables:**
- Rehearsal record (see `evidence/2026-Q3-template.md`)
- Updated runbooks (if gaps identified)
- Lessons learned document

### 2. Functional Exercise (Semi-Annually)

**What:** Restore a non-production service from backup in an isolated environment.

**When:** Semi-annually (minimum)

**Duration:** 4-8 hours

**Participants:** Operator (required)

**Scope:**
- Select a disaster scenario
- Execute the relevant runbook in a non-production environment
- Verify the restore was successful
- Measure actual RTO vs. target RTO

**Deliverables:**
- Rehearsal record (see `evidence/2026-Q3-template.md`)
- Updated runbooks (if gaps identified)
- Lessons learned document
- RTO achievement report

### 3. Full-Scale Exercise (Annually)

**What:** Simulate a regional outage and activate cross-region failover.

**When:** Annually (minimum)

**Duration:** 24-48 hours

**Participants:** Operator (required), external consultant (recommended), legal
counsel (optional)

**Scope:**
- Simulate a regional outage (GCP region unavailable)
- Activate cross-region backup (to be implemented)
- Verify services are operational in the secondary region
- Measure actual RTO vs. target RTO

**Deliverables:**
- Rehearsal record (see `evidence/2026-Q3-template.md`)
- Updated runbooks (if gaps identified)
- Lessons learned document
- RTO achievement report
- Post-exercise report for auditors

## Rehearsal Scenarios

### Scenario 1: Terraform State Corruption

**Scenario:** Terraform state file is corrupted. You cannot run `terraform plan`
or `terraform apply`.

**Runbook:** `runbooks/state-restore.md`

**Success criteria:**
- State restored from backup
- `terraform plan` shows no unexpected drift
- All expected resources present in state

### Scenario 2: Infrastructure Compromise

**Scenario:** Attacker has compromised the infrastructure. You must rebuild from
scratch.

**Runbook:** `runbooks/infrastructure-restore.md`

**Success criteria:**
- Infrastructure rebuilt from IaC
- All expected resources present and running
- Credentials rotated
- Services operational

### Scenario 3: Database Corruption

**Scenario:** Database is corrupted. Application data is inaccessible.

**Runbook:** `runbooks/data-restore.md`

**Success criteria:**
- Database restored from backup
- Data integrity verified (row counts match)
- Application functionality verified

### Scenario 4: Credential Exposure

**Scenario:** GitHub token has been leaked to a public repository. All credentials
must be rotated.

**Runbook:** `runbooks/credential-rotation.md`

**Success criteria:**
- All credentials rotated
- Applications updated with new credentials
- Services operational

### Scenario 5: Regional Outage

**Scenario:** GCP region is unavailable. Services must be restored in a secondary
region.

**Runbook:** `runbooks/infrastructure-restore.md` (cross-region variant)

**Success criteria:**
- Services operational in secondary region
- Data restored from cross-region backup
- RTO achieved (24 hours)

## Rehearsal Schedule

| Quarter | Rehearsal Type | Scenario |
|---|---|---|
| Q1 2027 | Tabletop | Terraform state corruption |
| Q2 2027 | Functional | Database restore |
| Q3 2027 | Tabletop | Credential rotation |
| Q4 2027 | Full-scale | Regional outage |

**Note:** The schedule is a minimum. Additional rehearsals may be conducted in
response to incidents, infrastructure changes, or auditor requests.

## Rehearsal Procedure

### Before the Rehearsal

1. **Select a scenario** from the list above (or define a custom scenario)
2. **Review the relevant runbook** — ensure it is up to date
3. **Prepare the environment** — for functional exercises, provision an isolated
   test environment
4. **Notify stakeholders** — inform them of the rehearsal and potential downtime
5. **Prepare the evidence template** — copy `evidence/2026-Q3-template.md` to a
   new file (e.g., `evidence/2027-Q1-tabletop.md`)

### During the Rehearsal

1. **Execute the runbook** step-by-step
2. **Record timestamps** for each major step
3. **Note any issues** — gaps, ambiguities, missing steps, errors
4. **Measure RTO** — time from "incident detected" to "services operational"
5. **Verify success criteria** — confirm each criterion is met

### After the Rehearsal

1. **Complete the evidence record** — fill in all sections of the template
2. **Update runbooks** — fix any gaps or ambiguities identified
3. **Document lessons learned** — what went well, what could be improved
4. **Submit evidence** — store the completed record in `jolarca-compliance`
5. **Schedule follow-up** — if issues were identified, schedule a follow-up
   rehearsal to verify fixes

## Rehearsal Evidence

All rehearsal evidence is stored in `jolarca-compliance` (not in this repository).
The evidence must include:

- **Scenario description** — what disaster was simulated
- **Steps taken** — what actions were performed
- **Timestamps** — when each step was performed
- **RTO achievement** — actual time vs. target time
- **Issues encountered** — what went wrong
- **Lessons learned** — what could be improved
- **Sign-off** — operator signature and date

**Example:** `evidence/2026-Q3-template.md`

## Compliance Mapping

| Framework | Control | Requirement |
|---|---|---|
| SOC 2 | A1.3 | Business continuity testing — rehearsals conducted and documented |
| ISO 27001 | A.8.13 | Information backup — restore procedure tested |
| PCI-DSS | Req 12.10 | Incident response — recovery procedures tested |
| GDPR | Art. 32 | Resilience of processing systems — tested |

## References

- `evidence/2026-Q3-template.md` — Rehearsal evidence template
- `runbooks/state-restore.md` — Terraform state restore procedure
- `runbooks/infrastructure-restore.md` — Infrastructure rebuild procedure
- `runbooks/data-restore.md` — Application data restore procedure
- `runbooks/credential-rotation.md` — Credential rotation procedure
- `policies/business-continuity-policy.md` — Business continuity framework
- `rpo-rto/definitions.md` — RPO/RTO definitions
