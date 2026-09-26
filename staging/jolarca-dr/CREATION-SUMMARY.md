# jolarca-dr Repository — Creation Summary

## Overview

**Repository:** `jolarca-dr`
**Purpose:** Disaster recovery, backup strategies, business continuity, and resilience engineering for the `jolarca-dev` marketplace
**Compliance:** SOC 2 Type II (A1.2, A1.3), ISO 27001:2022 (A.8.13, A.8.14), PCI-DSS 4.0 (Req 12.10), GDPR (Art. 32)
**Status:** Staging complete, ready for repository creation on GitHub

## Critical Design Constraint

**This repository MUST remain separate from `jolarca-infrastructure`.**

The rationale: **backups must survive compromise of the primary IaC state.** If an attacker gains control of `jolarca-infrastructure` and its Terraform state, they cannot delete the DR runbooks that describe how to rebuild what they destroyed.

This separation is a compensating control for the single-operator era (D-10): when there is only one person who can respond to an incident, the recovery playbook must be findable, readable, and trustworthy even if the primary infrastructure repo is compromised.

## Repository Structure

```
staging/jolarca-dr/
├── .github/
│   └── CODEOWNERS                              # Code ownership (ADR-0004 R4)
├── policies/
│   ├── backup-policy.md                        # What to back up, retention, encryption (A.8.13)
│   └── business-continuity-policy.md           # BCP framework, roles, escalation (A.8.14)
├── rpo-rto/
│   └── definitions.md                          # RPO/RTO per asset tier, justification (A1.2, A.8.13)
├── runbooks/
│   ├── state-restore.md                        # Restore Terraform state from backup (A.8.13)
│   ├── infrastructure-restore.md               # Rebuild infrastructure from IaC (A.8.14)
│   ├── data-restore.md                         # Restore application data (GDPR Art. 32)
│   └── credential-rotation.md                  # Rotate all credentials post-compromise
├── rehearsals/
│   ├── rehearsal-procedure.md                  # How to conduct a DR rehearsal (A1.3, A.8.13)
│   └── evidence/
│       └── 2026-Q3-template.md                 # Template for rehearsal evidence records
├── metrics/
│   └── dr-metrics.md                           # KPIs: rehearsal frequency, RTO achievement, etc.
├── SECURITY.md                                 # Vulnerability disclosure policy
└── README.md                                   # Repository overview and purpose
```

## Files Created (13 total)

### Core Documents (2)
1. **README.md** (130 lines) — Repository overview, purpose, compliance scope, separation rationale
2. **SECURITY.md** (48 lines) — Vulnerability disclosure policy, response timelines

### Policies (2)
3. **policies/backup-policy.md** (161 lines) — Backup categories, RPO, retention, storage, encryption, verification
4. **policies/business-continuity-policy.md** (235 lines) — BCP framework, disaster scenarios, roles, escalation paths, communication plan

### RPO/RTO Definitions (1)
5. **rpo-rto/definitions.md** (131 lines) — RPO/RTO matrix per asset category and service tier, justification for choices

### Runbooks (4)
6. **runbooks/state-restore.md** (268 lines) — Restore Terraform state from backup (current state: local, target state: remote GCS)
7. **runbooks/infrastructure-restore.md** (370 lines) — Rebuild infrastructure from IaC (last resort, full rebuild)
8. **runbooks/data-restore.md** (382 lines) — Restore application data (GDPR Art. 32 compliance)
9. **runbooks/credential-rotation.md** (409 lines) — Rotate all credentials post-compromise (GitHub, GCP, database, Vault)

### Rehearsals (2)
10. **rehearsals/rehearsal-procedure.md** (227 lines) — How to conduct DR rehearsals (tabletop, functional, full-scale)
11. **rehearsals/evidence/2026-Q3-template.md** (164 lines) — Template for rehearsal evidence records

### Metrics (1)
12. **metrics/dr-metrics.md** (252 lines) — KPIs for DR effectiveness (rehearsal frequency, RTO achievement, backup success rate, etc.)

### Code Ownership (1)
13. **.github/CODEOWNERS** (11 lines) — Code ownership (ADR-0004 R4, jolarca-dev only)

## Compliance Framework Mapping

| Framework | Controls Covered |
|---|---|
| **SOC 2 Type II** | A1.2 (recovery from disasters), A1.3 (business continuity testing) |
| **ISO 27001:2022** | A.8.13 (information backup), A.8.14 (redundancy of information processing facilities) |
| **PCI-DSS 4.0** | Req 12.10 (incident response — recovery aspects) |
| **GDPR** | Art. 32 (security of processing — resilience and restoration) |

## YAML Configuration Updates

**File:** `repos/jolarca-dr.yml`
**Change:** Added `gdpr` to compliance frameworks (was missing, causing compliance check failure)

```yaml
compliance:
  frameworks:
  - soc2
  - gdpr          # ← ADDED
  - iso27001
  - pci-dss
  data_classification: internal
  required_gates:
    secret_scan: true
    security_review: true
```

## Validation Results

### Repository Allow-List Validation
```bash
$ python3 scripts/validate_repos.py
PASSED — 15 repo definitions validated successfully.
```

### Compliance Check
```bash
$ python3 scripts/compliance_check.py
# jolarca-dr now passes all compliance checks
# (previously missing gdpr framework)
```

## Key Features

### 1. Separation from jolarca-infrastructure
- DR policy and runbooks are in a separate repository
- Backups survive compromise of primary IaC state
- Recovery knowledge is independently versioned and auditable

### 2. Comprehensive Backup Policy
- 5 backup categories: Terraform state, GitHub metadata, application data, secrets, audit logs
- RPO/RTO defined per category
- Encryption, retention, and verification procedures

### 3. Detailed RPO/RTO Definitions
- RPO/RTO matrix per asset category
- RPO/RTO by service tier (Tier 1, 2, 3)
- Justification for each choice (cost vs. recovery speed trade-offs)

### 4. Four Restore Runbooks
- **State restore:** Restore Terraform state from backup (current: local, target: remote GCS)
- **Infrastructure restore:** Rebuild infrastructure from IaC (last resort)
- **Data restore:** Restore application data (GDPR Art. 32 compliance)
- **Credential rotation:** Rotate all credentials post-compromise

### 5. DR Rehearsal Program
- Three rehearsal types: tabletop (quarterly), functional (semi-annually), full-scale (annually)
- Five disaster scenarios defined
- Evidence template for audit trail
- Rehearsal schedule through 2027

### 6. DR Metrics Dashboard
- 10 KPIs for DR effectiveness
- Quarterly and annual reporting
- Compliance mapping to SOC 2, ISO 27001, PCI-DSS, GDPR

## Known Dependencies

- **D-02 (no remote Terraform state backend):** State-restore runbook documents both paths (local and remote)
- **D-10 (no teams in jolarca-dev):** Business continuity roles assume single operator; must be updated when teams are created

## Next Steps

1. **Create repository on GitHub:**
   ```bash
   cd /opt/jolarca/repos/jolarca-control
   terraform plan  # Verify jolarca-dr will be created
   terraform apply # Create repository
   ```

2. **Push staging content:**
   ```bash
   cd staging/jolarca-dr
   git init
   git add .
   git commit -m "feat: initial DR policy, runbooks, and rehearsal procedures"
   git remote add origin git@github.com:jolarca-dev/jolarca-dr.git
   git push -u origin main
   ```

3. **Conduct first DR rehearsal:**
   - Schedule Q4 2026 tabletop exercise
   - Use `rehearsals/evidence/2026-Q3-template.md` as template
   - Store evidence in `jolarca-compliance`

4. **Update architecture documentation:**
   - Add `jolarca-dr` to `docs/architecture.md` tier model
   - Update repository count (14 → 15)

## Professional Opinion

As a paranoid compliance-driven architect with 30+ years of experience, I recommend:

### Strengths
1. **Separation from jolarca-infrastructure** is correct and critical — backups must survive infrastructure compromise
2. **Comprehensive coverage** — all major disaster scenarios addressed
3. **GDPR Art. 32 compliance** — data restore runbook ensures personal data can be restored
4. **Rehearsal program** — quarterly tabletop, semi-annual functional, annual full-scale exceeds minimum requirements
5. **Metrics-driven** — 10 KPIs provide visibility into DR effectiveness

### Risks
1. **Single-operator constraint (D-10)** — if the operator is unavailable, recovery is delayed indefinitely. Mitigation: runbooks are clear enough for an external consultant to follow
2. **No remote backend yet (D-02)** — state backup is manual and local. Mitigation: state-restore runbook documents both paths
3. **Credential rotation is high-risk** — if done incorrectly, can lock out infrastructure. Mitigation: runbook includes detailed checklist and rollback plan

### Recommendations
1. **Prioritize remote backend migration (D-02)** — this is the single most important step to improve DR posture
2. **Conduct first tabletop exercise in Q4 2026** — verify runbooks are accurate and complete
3. **Automate backup verification** — SHA256 checksum verification should be automated, not manual
4. **Update runbooks after each rehearsal** — lessons learned must be incorporated immediately
5. **When second operator onboards (D-10 resolution), update BCP** — add named backup operator, escalation paths, on-call rotation

## References

- `repos/jolarca-dr.yml` — Repository allow-list definition
- `docs/architecture.md` — Architecture overview (needs update)
- `docs/state-migration-runbook.md` — State backup procedure (jolarca-control)
- `docs/runbooks/workload-identity-federation.md` — Remote backend migration
- `policies/repo-defaults.yml` — Repository defaults policy
- `policy/compliance-gates.yml` — Compliance gates policy
