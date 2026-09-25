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

Alternatively, email: **security@jolarca.com**

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
