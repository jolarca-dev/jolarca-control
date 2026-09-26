# jolarca-payments

**Payment processing, billing, PCI-DSS compliance, and cardholder-data
environment (CDE) governance for the `jolarca-dev` marketplace.**

> **Compliance:** PCI-DSS 4.0 (Req 1–12) · SOC 2 Type II (CC6.1–CC6.3, CC7.1–CC7.5)
> · ISO 27001:2022 (A.5, A.8) · GDPR (Art. 32)

---

## Purpose

This repository is the **authoritative source for payment processing policy,
PCI-DSS compliance, and CDE governance** in the marketplace fleet. It defines:

- **How** payment data flows through the system (data-flow diagrams, network segmentation)
- **What** PCI-DSS requirements apply and how they are met (SAQ, scope definition)
- **Where** cryptographic keys are managed (key lifecycle, rotation procedures)
- **Who** may access CDE components (access logging, need-to-know enforcement)
- **When** and **how** payment incidents are responded to (IR runbooks)

## What this repository is NOT

**This repository holds the policy and integration code, not the live payment
infrastructure.**

Evidence of completed PCI-DSS assessments, audit reports, and compliance
attestations is stored in [`jolarca-compliance`](https://github.com/jolarca-dev/jolarca-compliance).
An auditor examining the marketplace's payment-security posture reads *this*
repo for the policy and *jolarca-compliance* for the proof that the policy was
followed. The separation is deliberate: policy and evidence must not share a
repository, because the same repository cannot be both the rule-maker and the
proof-of-compliance.

| Repository | Role |
|---|---|
| `jolarca-payments` (this repo) | Payment policy, PCI-DSS scope, CDE governance, provider integration specs, key management procedures, incident response runbooks |
| `jolarca-compliance` | Evidence: completed SAQ records, audit reports, signed attestations, QSA correspondence |
| `jolarca-security` | Cross-cutting threat models, vulnerability management, incident response coordination |

## CDE Boundary Statement

**This repository is within the cardholder-data environment (CDE) boundary.**

All code, configuration, and policy in this repository is subject to PCI-DSS
requirements. Any change to this repository is a change to the CDE and MUST
follow the PCI-DSS change-control process (Req. 6.3):

- All changes require a documented change request
- All changes are reviewed for PCI-DSS impact before merge
- All changes are logged and auditable
- Cryptographic key material is NEVER committed to this repository

## Repository Structure

```
jolarca-payments/
├── .github/
│   └── CODEOWNERS                  # Code ownership — CDE access control (ADR-0004 R4, Req. 7)
├── policies/
│   ├── payment-security-policy.md  # Master payment security policy (Req. 12.1)
│   ├── data-classification.md      # Payment data classification (Req. 9, Art. 32)
│   └── encryption-policy.md        # Encryption standards for data at rest/transit (Req. 3, 4)
├── pci-dss/
│   ├── scope-definition.md         # CDE scope and network segmentation (Req. 1)
│   ├── self-assessment-questionnaire.md # SAQ Type and completion guidance (Req. 12.10)
│   ├── network-segmentation.md     # Network segmentation controls (Req. 1)
│   ├── key-management.md           # Cryptographic key lifecycle procedures (Req. 3)
│   └── access-logging.md           # Access logging and monitoring (Req. 10)
├── integration/
│   ├── provider-integration.md     # Payment provider integration specifications
│   ├── tokenization.md             # Tokenization and PAN handling procedures (Req. 3)
│   └── webhook-security.md         # Webhook signature verification and security
├── runbooks/
│   ├── incident-response.md        # Payment-specific incident response (Req. 12.10)
│   └── key-rotation.md             # Cryptographic key rotation procedures (Req. 3)
├── .gitignore                      # PCI-DSS prohibited artifacts
├── SECURITY.md                     # Vulnerability disclosure — CDE-specific
├── README.md                       # This file
└── LICENSE                         # License (if applicable)
```

## Compliance Framework Mapping

| Framework | Controls Covered |
|---|---|
| PCI-DSS 4.0 | Req 1 (network segmentation), Req 3 (data protection), Req 4 (encryption in transit), Req 6 (secure development), Req 7 (access control), Req 8 (authentication), Req 9 (physical security), Req 10 (logging/monitoring), Req 11 (testing), Req 12 (policy/IR) |
| SOC 2 Type II | CC6.1 (logical access), CC6.2 (authentication), CC6.3 (security events), CC7.1–CC7.5 (system operations, vulnerability management) |
| ISO 27001:2022 | A.5 (policies), A.8 (technical controls — encryption, logging, access control) |
| GDPR | Art. 32 (security of processing — payment data as personal data) |

## Current Status

**Planned.** This repository is declared in the
[`jolarca-control`](https://github.com/jolarca-dev/jolarca-control) fleet
allow-list (`repos/jolarca-payments.yml`) but is not yet populated on GitHub.

### Known Dependencies

- **D-10 (no teams in `jolarca-dev`):** The CDE access list is effectively the
  entire org (one person). When teams are created, this repo MUST have a
  smaller access list than the general marketplace fleet — PCI-DSS Req. 7
  requires documented need-to-know.
- **D-18 (2FA not enforced):** Payment system access requires MFA by PCI-DSS
  Req. 8. Until org-wide 2FA is enabled, this is an aspirational control.

## Contributing

See [`CONTRIBUTING.md`](https://github.com/jolarca-dev/jolarca-control/blob/main/CONTRIBUTING.md)
in `jolarca-control`. Changes to payment policy or CDE configuration are
**security changes** and require the full compliance gate set: dependency scan,
secret scan, license check, code quality, and security review.

## License

This repository contains governance policy and integration specifications, not
software. No OSS license is declared. See `jolarca-control` for the governance
framework.
