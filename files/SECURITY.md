# Security Policy

## Supported Versions

This repository contains organizational configuration. Security updates are
applied immediately upon discovery.

## Reporting a Vulnerability

**Do not open a public issue for security vulnerabilities.**

### Private Vulnerability Disclosure

GitHub's private vulnerability disclosure is enabled for this organization.
To report a security issue:

1. Go to the affected repository
2. Click **Security** → **Report a vulnerability**
3. Provide details of the vulnerability

Alternatively, email: **journey4oflife+jolarca.security@gmail.com**

Privacy enquiries and data-subject requests (GDPR Art. 12–22): **journey4oflife+jolarca.privacy@gmail.com**

> **Why a Gmail alias and not `security@jolarca.com`** (D-59, 2026-10-15): the
> address formerly published here cannot receive mail. Verified the same day:
> `dig MX jolarca.com` and `dig MX jolarca.dev` both return nothing, no DMARC
> record exists, and nothing listens on port 25 or 587 on the host that
> operates this fleet. Publishing an undeliverable disclosure channel is worse
> than publishing none — researchers believe they reported.
>
> This is an **interim** contact. All five role addresses are plus-aliases on
> one personal mailbox, so they give routing and leak attribution, not
> independent handling or separate retention, and the alias discloses the base
> mailbox name. The exit condition is a real role mailbox on `jolarca.com`
> (MX + DMARC + SPF/DKIM), tracked in `policy/contact-addresses.yml` and
> `policy/compliance-gates.yml` (`contact-alias-interim`, expires 2027-01-13).
> Delivery of the alias itself has not yet been proven by a test message —
> that evidence is outstanding, not assumed.

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
