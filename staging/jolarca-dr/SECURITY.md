# Security Policy — jolarca-dr

## Scope

This repository contains **disaster recovery policies, backup procedures,
business continuity plans, and restore runbooks** for the `jolarca-dev`
marketplace. It does NOT contain live credentials, access tokens, API keys,
Terraform state files, or production infrastructure configurations.

## Reporting a Vulnerability

If you discover a security vulnerability in this repository (e.g., a gap in
backup coverage, a restore procedure that could fail silently, or a procedural
weakness that could delay recovery), report it through the
[jolarca-dev security policy](https://github.com/jolarca-dev/.github/blob/main/SECURITY.md).

## What to Include

- Description of the vulnerability and its potential impact on recovery capabilities
- Affected file(s) and the specific policy or procedure concerned
- Steps to reproduce or demonstrate the issue
- Suggested remediation (if any)

## Response Timeline

| Severity | Response | Remediation |
|---|---|---|
| Critical (recovery impossible) | Immediate | Same-day policy patch |
| High (RTO/RPO violation likely) | Within 24 hours | Within 72 hours |
| Medium (procedural gap) | Within 72 hours | Next scheduled review |
| Low (documentation inaccuracy) | Next business day | Next scheduled review |

## Compliance Context

This repository supports the following compliance controls:

- **SOC 2 Type II:** A1.2 (recovery from disasters), A1.3 (business continuity testing)
- **ISO 27001:2022:** A.8.13 (information backup), A.8.14 (redundancy of information processing facilities)
- **PCI-DSS 4.0:** Req 12.10 (incident response — recovery aspects)
- **GDPR:** Art. 32 (security of processing — resilience and restoration)

## Do NOT

- Commit credentials, tokens, or secrets to this repository
- Commit Terraform state files (*.tfstate, *.tfstate.*) — they are gitignored by policy
- Use this repository to store live rehearsal evidence (that belongs in `jolarca-compliance`)
- Reference mission-platform (`journeyoflife-org` / `jol-*`) resources (ADR-0004 R4)
- Store infrastructure-specific configurations here — keep them in `jolarca-infrastructure`
