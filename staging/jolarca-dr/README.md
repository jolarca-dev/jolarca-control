# jolarca-dr

**Disaster recovery, backup strategies, business continuity, and resilience
engineering for the `jolarca-dev` marketplace.**

> **Compliance:** SOC 2 Type II (A1.2, A1.3) · ISO 27001:2022 (A.8.13, A.8.14)
> · PCI-DSS 4.0 (Req 12.10) · GDPR (Art. 32)

---

## Purpose

This repository is the **authoritative source for disaster recovery policy,
backup procedures, and business continuity planning** in the marketplace fleet.
It defines:

- **What** must be backed up and how often (RPO — Recovery Point Objective)
- **How fast** systems must be restored (RTO — Recovery Time Objective)
- **How** to restore Terraform state, infrastructure, and data after a disaster
- **When** and **how** DR procedures are tested (rehearsal schedule and evidence)

## What this repository is NOT

**This repository holds the machinery, not the records.**

Evidence of completed DR rehearsals, signed attestations, and audit trails is
stored in [`jolarca-compliance`](https://github.com/jolarca-dev/jolarca-compliance).
An auditor examining the marketplace's resilience posture reads *this* repo for
the policy and *jolarca-compliance* for the proof that the policy was followed.
The separation is deliberate: policy and evidence must not share a repository,
because the same repository cannot be both the rule-maker and the proof-of-compliance.

| Repository | Role |
|---|---|
| `jolarca-dr` (this repo) | DR policy, backup procedures, RPO/RTO definitions, restore runbooks, rehearsal procedures |
| `jolarca-compliance` | Evidence: completed rehearsal records, signed attestations, audit logs |
| `jolarca-infrastructure` | Live Terraform state and IaC code (the thing being recovered) |

## Critical Design Constraint: Separation from jolarca-infrastructure

**This repository MUST remain separate from `jolarca-infrastructure`.**

The rationale is a core resilience principle: **backups must survive compromise
of the primary IaC state.** If an attacker gains control of `jolarca-infrastructure`
and its Terraform state, they can:

- Destroy or corrupt live infrastructure
- Modify the IaC code to re-deploy compromised configurations
- Potentially tamper with local state backups stored alongside the IaC

By keeping DR policy, restore procedures, and RPO/RTO definitions in a
**separate repository**, we ensure that:

1. **Recovery knowledge survives infrastructure compromise** — an attacker cannot
   delete the runbooks that describe how to rebuild what they destroyed
2. **Restore procedures are independently versioned** — changes to DR policy
   require a separate PR and review, not buried in infrastructure changes
3. **Auditors can verify DR controls without accessing IaC state** — the policy
   is in one place, the live infrastructure in another
4. **Rehearsal evidence is tamper-evident** — stored in `jolarca-compliance`,
   not in the same repo as the infrastructure being tested

This separation is a compensating control for the single-operator era (D-10):
when there is only one person who can respond to an incident, the recovery
playbook must be findable, readable, and trustworthy even if the primary
infrastructure repo is compromised.

## Repository Structure

```
jolarca-dr/
├── .github/
│   └── CODEOWNERS                  # Code ownership (ADR-0004 R4)
├── policies/
│   ├── backup-policy.md            # What to back up, retention, encryption (A.8.13)
│   └── business-continuity-policy.md # BCP framework, roles, escalation (A.8.14)
├── rpo-rto/
│   └── definitions.md              # RPO/RTO per asset tier, justification (A1.2, A.8.13)
├── runbooks/
│   ├── state-restore.md            # Restore Terraform state from backup (A.8.13)
│   ├── infrastructure-restore.md   # Rebuild infrastructure from IaC (A.8.14)
│   ├── data-restore.md             # Restore application data (GDPR Art. 32)
│   └── credential-rotation.md      # Rotate all credentials post-compromise
├── rehearsals/
│   ├── rehearsal-procedure.md      # How to conduct a DR rehearsal (A1.3, A.8.13)
│   └── evidence/
│       └── 2026-Q3-template.md     # Template for rehearsal evidence records
├── metrics/
│   └── dr-metrics.md               # KPIs: rehearsal frequency, RTO achievement, etc.
├── SECURITY.md                     # Vulnerability disclosure policy
├── README.md                       # This file
└── LICENSE                         # License (if applicable)
```

## Compliance Framework Mapping

| Framework | Controls Covered |
|---|---|
| SOC 2 Type II | A1.2 (recovery from disasters), A1.3 (business continuity testing) |
| ISO 27001:2022 | A.8.13 (information backup), A.8.14 (redundancy of information processing facilities) |
| PCI-DSS 4.0 | Req 12.10 (incident response — recovery aspects) |
| GDPR | Art. 32 (security of processing — resilience and restoration) |

## Current Status

**Planned.** This repository is declared in the
[`jolarca-control`](https://github.com/jolarca-dev/jolarca-control) fleet
allow-list (`repos/jolarca-dr.yml`) but is not yet populated on GitHub.

### Known Dependencies

- **D-02 (no remote Terraform state backend):** The state-restore runbook
  assumes a remote backend exists. Until the migration in
  `docs/state-migration-runbook.md` is complete, state backup is a local copy
  and restore is manual. The runbook documents both paths.
- **D-10 (no teams in `jolarca-dev`):** Business continuity roles and escalation
  paths assume a single operator. When teams are created, the BCP must be
  updated to reflect the new roster.

## Contributing

See [`CONTRIBUTING.md`](https://github.com/jolarca-dev/jolarca-control/blob/main/CONTRIBUTING.md)
in `jolarca-control`. Changes to DR policy are **security changes** and require
the full compliance gate set: dependency scan, secret scan, license check, code
quality, and security review.

## License

This repository contains governance policy, not software. No OSS license is
declared. See `jolarca-control` for the governance framework.
