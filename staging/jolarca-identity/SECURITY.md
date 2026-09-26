# Security Policy — jolarca-identity

## Scope

This repository contains **IAM policy definitions, RBAC configurations, and
access-control procedures** for the `jolarca-dev` marketplace. It does NOT
contain live credentials, access tokens, API keys, or production identity data.

## Reporting a Vulnerability

If you discover a security vulnerability in this repository (e.g., an RBAC
policy that inadvertently grants excessive permissions, or a procedural gap
that could allow unauthorised access), report it through the
[jolarca-dev security policy](https://github.com/jolarca-dev/.github/blob/main/SECURITY.md).

## What to Include

- Description of the vulnerability and its potential impact on access control
- Affected file(s) and the specific policy or procedure concerned
- Steps to reproduce or demonstrate the issue
- Suggested remediation (if any)

## Response Timeline

| Severity | Response | Remediation |
|---|---|---|
| Critical (unauthorised access path) | Immediate | Same-day policy patch |
| High (excessive privilege) | Within 24 hours | Within 72 hours |
| Medium (procedural gap) | Within 72 hours | Next scheduled review |
| Low (documentation inaccuracy) | Next business day | Next scheduled review |

## Compliance Context

This repository supports the following compliance controls:

- **SOC 2 Type II:** CC6.1 (logical access), CC6.2 (authentication), CC6.3 (security events)
- **ISO 27001:2022:** A.5.15 (identity management), A.5.16 (authentication information), A.5.17 (access rights), A.5.18 (access review)
- **PCI-DSS 4.0:** Req 7 (access control), Req 8 (authentication management)

## Do NOT

- Commit credentials, tokens, or secrets to this repository
- Use this repository to store live access review evidence (that belongs in `jolarca-compliance`)
- Reference mission-platform (`journeyoflife-org` / `jol-*`) resources (ADR-0004 R4)
