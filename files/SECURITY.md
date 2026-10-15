# Security Policy

## Supported Versions

This repository contains organizational configuration. Security updates are
applied immediately upon discovery.

## Reporting a Vulnerability

**Do not open a public issue for security vulnerabilities.**

### Private Vulnerability Disclosure

If the affected repository shows **Security** → **Report a vulnerability**,
use it — that channel keeps the report private. GitHub does not expose this
setting through the API, so it cannot be asserted as enabled for every
repository here: if the option is not visible, use the email below rather than
assuming a report arrived.

1. Go to the affected repository
2. Click **Security** → **Report a vulnerability**
3. Provide details of the vulnerability

Email: **journey4oflife+jolarca.security@gmail.com**

Privacy enquiries and data-subject requests (GDPR Art. 12–22):
**journey4oflife+jolarca.privacy@gmail.com**

> `security@jolarca.com` was published here as the primary contact and is
> **undeliverable** — `jolarca.com` has no MX and no DMARC record, and
> `jolarca.dev` has neither (measured 2026-10-15: `dig MX`, `dig TXT _dmarc`).
> Do not add it back. The Gmail plus-aliases above are an interim measure
> tracked as D-59 in
> [`jolarca-control`](https://github.com/jolarca-dev/jolarca-control/blob/main/docs/drift-findings.md):
> they reach a real inbox, but all five share one mailbox and each discloses its
> base name, so they are message routing, not a separate security function or an
> independent DPO. Domain role mailboxes (MX + DMARC + SPF/DKIM) are the exit
> condition.

### What to Include

- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

### Response Timeline

| Severity | Initial Response | Resolution Target |
|----------|------------------|-------------------|
| Critical | 24 hours | 7 days |
| High | 48 hours | 14 days |
| Medium | 5 business days | 30 days |
| Low | 10 business days | Next release |

## Security Controls

This repository follows:

- **Pre-commit hooks**: gitleaks (secret scanning)
- **Branch protection**: Required reviews, status checks
- **Signed commits**: GPG verification recommended
- **Dependency scanning**: Dependabot alerts enabled

## Compliance

Security controls align with:

- SOC 2 CC7.1, CC7.2 (system monitoring)
- ISO 27001 A.12.6.1 (vulnerability management)
- GDPR Art. 32 (security of processing)
