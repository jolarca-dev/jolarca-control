# DR Rehearsal Evidence — 2026-Q3

## Rehearsal Metadata

| Field | Value |
|---|---|
| **Rehearsal ID** | DR-2026-Q3-001 |
| **Date** | 2026-09-26 |
| **Type** | [ ] Tabletop [ ] Functional [ ] Full-scale |
| **Scenario** | [Scenario description] |
| **Operator** | @JourneyOfLife |
| **Duration** | [Start time] to [End time] |
| **Runbook(s) Used** | [List of runbooks] |

## Scenario Description

**What disaster was simulated?**

[Describe the scenario in detail. What happened? What was the impact?]

**Example:**
"Terraform state file (`terraform.tfstate`) was corrupted. `terraform plan` failed
with 'state file is not valid JSON'. All infrastructure management via IaC was blocked."

## Rehearsal Execution

### Step-by-Step Record

| Step | Action | Timestamp | Result | Notes |
|---|---|---|---|---|
| 1 | [Action description] | [HH:MM] | [Pass/Fail] | [Any issues encountered] |
| 2 | [Action description] | [HH:MM] | [Pass/Fail] | [Any issues encountered] |
| 3 | [Action description] | [HH:MM] | [Pass/Fail] | [Any issues encountered] |

**Example:**

| Step | Action | Timestamp | Result | Notes |
|---|---|---|---|---|
| 1 | Located most recent backup | 14:30 | Pass | Backup from 2026-09-25 09:15 |
| 2 | Verified SHA256 checksum | 14:32 | Pass | Checksum matched recorded value |
| 3 | Copied backup to working directory | 14:33 | Pass | File size: 24,520 bytes |
| 4 | Ran `terraform init` | 14:35 | Pass | Initialized successfully |
| 5 | Ran `terraform plan` | 14:36 | Fail | Plan showed unexpected drift: 3 resources to be replaced |
| 6 | Investigated drift | 14:40 | Pass | Drift was expected (manual changes made after backup) |
| 7 | Ran `terraform apply` | 14:45 | Pass | Applied successfully |
| 8 | Verified infrastructure state | 14:50 | Pass | All resources present and running |

## RTO Achievement

| Metric | Target | Actual | Status |
|---|---|---|---|
| **RTO** | [Target from rpo-rto/definitions.md] | [Actual time] | [Pass/Fail] |
| **Time to detect** | N/A | [Time] | N/A |
| **Time to restore** | [Target] | [Actual time] | [Pass/Fail] |
| **Time to verify** | N/A | [Time] | N/A |

**Example:**

| Metric | Target | Actual | Status |
|---|---|---|---|
| **RTO** | 4 hours | 1 hour 20 minutes | Pass |
| **Time to detect** | N/A | 0 minutes (simulated) | N/A |
| **Time to restore** | 4 hours | 20 minutes | Pass |
| **Time to verify** | N/A | 1 hour | N/A |

## Success Criteria

| Criterion | Status | Evidence |
|---|---|---|
| [Criterion 1 from runbook] | [Pass/Fail] | [Link to evidence or description] |
| [Criterion 2 from runbook] | [Pass/Fail] | [Link to evidence or description] |
| [Criterion 3 from runbook] | [Pass/Fail] | [Link to evidence or description] |

**Example:**

| Criterion | Status | Evidence |
|---|---|---|
| State restored from verified backup | Pass | SHA256 checksum matched |
| `terraform plan` shows no unexpected drift | Pass | Plan showed only expected drift |
| All expected resources present in state | Pass | `terraform state list` showed 14 repositories |

## Issues Encountered

| Issue | Severity | Description | Resolution |
|---|---|---|---|
| [Issue description] | [High/Medium/Low] | [Detailed description] | [How it was resolved] |

**Example:**

| Issue | Severity | Description | Resolution |
|---|---|---|---|
| Unexpected drift in `terraform plan` | Medium | Plan showed 3 resources to be replaced | Investigated and confirmed drift was expected (manual changes made after backup) |

## Lessons Learned

### What Went Well

- [List things that went well]

**Example:**
- Backup was easy to locate and verify
- Restore procedure was clear and easy to follow
- `terraform plan` provided good visibility into state

### What Could Be Improved

- [List things that could be improved]

**Example:**
- Runbook should include a step to investigate drift before running `terraform apply`
- Checksum verification should be automated (currently manual)
- Backup directory structure could be clearer (currently flat, should be organized by date)

### Action Items

| Action | Owner | Due Date | Status |
|---|---|---|---|
| [Action description] | [Owner] | [Date] | [Open/Closed] |

**Example:**

| Action | Owner | Due Date | Status |
|---|---|---|---|
| Update `runbooks/state-restore.md` to include drift investigation step | @JourneyOfLife | 2026-10-10 | Open |
| Automate checksum verification | @JourneyOfLife | 2026-10-15 | Open |
| Reorganize backup directory structure | @JourneyOfLife | 2026-10-20 | Open |

## Sign-Off

**Operator:**

- Name: Gintaras Kazlauskas
- GitHub: @JourneyOfLife
- Date: 2026-09-26
- Signature: [Digital signature or confirmation]

**Auditor (if applicable):**

- Name: [Auditor name]
- Organization: [Auditor organization]
- Date: [Date]
- Signature: [Digital signature or confirmation]

## Attachments

- [ ] Rehearsal logs (if applicable)
- [ ] Screenshots (if applicable)
- [ ] Terraform plan output (if applicable)
- [ ] Other evidence (if applicable)

## Compliance Mapping

| Framework | Control | Requirement |
|---|---|---|
| SOC 2 | A1.3 | Business continuity testing — rehearsal conducted and documented |
| ISO 27001 | A.8.13 | Information backup — restore procedure tested |
| PCI-DSS | Req 12.10 | Incident response — recovery procedures tested |
| GDPR | Art. 32 | Resilience of processing systems — tested |

## References

- `rehearsals/rehearsal-procedure.md` — DR rehearsal procedure
- `runbooks/state-restore.md` — Terraform state restore procedure
- `rpo-rto/definitions.md` — RPO/RTO definitions
