# Security Policy — jolarca-payments

## Scope

This repository contains **payment processing policy, PCI-DSS compliance
documentation, CDE governance, and payment provider integration specifications**
for the `jolarca-dev` marketplace. It does NOT contain live payment credentials,
API keys, cryptographic key material, PAN data, or production payment
configurations.

**This repository is within the cardholder-data environment (CDE) boundary.**
All contents are subject to PCI-DSS requirements and must not expose
cardholder data, authentication data, or cryptographic keys.

## Reporting a Vulnerability

If you discover a security vulnerability in this repository (e.g., a gap in
payment security policy, a CDE scope definition error, a key management
procedure weakness, or an integration specification that could expose payment
data), report it through the
[jolarca-dev security policy](https://github.com/jolarca-dev/.github/blob/main/SECURITY.md).

## What to Include

- Description of the vulnerability and its potential impact on payment security or CDE integrity
- Affected file(s) and the specific policy, procedure, or specification concerned
- PCI-DSS requirement(s) potentially affected (if known)
- Steps to reproduce or demonstrate the issue
- Suggested remediation (if any)

## Response Timeline

| Severity | Response | Remediation |
|---|---|---|
| Critical (CDE boundary breach, PAN exposure risk) | Immediate | Same-day policy patch |
| High (key management weakness, access control gap) | Within 24 hours | Within 72 hours |
| Medium (procedural gap, logging deficiency) | Within 72 hours | Next scheduled review |
| Low (documentation inaccuracy) | Next business day | Next scheduled review |

## Compliance Context

This repository supports the following compliance controls:

- **PCI-DSS 4.0:** Req 1 (network segmentation), Req 3 (data protection), Req 4 (encryption in transit), Req 6 (secure development), Req 7 (access control), Req 8 (authentication), Req 10 (logging/monitoring), Req 12 (policy/IR)
- **SOC 2 Type II:** CC6.1 (logical access), CC6.2 (authentication), CC6.3 (security events), CC7.1–CC7.5 (system operations)
- **ISO 27001:2022:** A.5 (policies), A.8 (technical controls)
- **GDPR:** Art. 32 (security of processing — payment data as personal data)

## Do NOT

- Commit credentials, tokens, API keys, or cryptographic key material to this repository
- Commit PAN data, cardholder data, or authentication data (CVV, PIN blocks)
- Commit payment provider API credentials or production configuration
- Commit Terraform state files (*.tfstate, *.tfstate.*) — they are gitignored by policy
- Use this repository to store live audit evidence (that belongs in `jolarca-compliance`)
- Reference mission-platform (`journeyoflife-org` / `jol-*`) resources (ADR-0004 R4)
- Store infrastructure-specific configurations here — keep them in `jolarca-infrastructure`
