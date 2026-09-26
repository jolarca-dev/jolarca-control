# Authentication Standards — jolarca-dev Marketplace

**Status:** Policy · Effective upon publication
**Owner:** jolarca-dev organization owner
**Review cadence:** Quarterly or on material change
**Compliance:** SOC 2 CC6.3 · ISO 27001:2022 A.5.17 · PCI-DSS Req 8

---

## 1. Purpose

This document defines the authentication requirements for all identities
accessing the `jolarca-dev` marketplace. It establishes minimum standards for
identity verification, credential management, and session security.

## 2. Scope

These standards apply to:

- All human operator accounts in `jolarca-dev`
- All service accounts and CI/CD identities
- All API tokens, deploy keys, and OAuth grants used to access marketplace resources
- All third-party integrations that authenticate against marketplace systems

## 3. Multi-Factor Authentication (MFA)

### 3.1 Requirement

**MFA is mandatory for all human operators.** This is a non-negotiable
requirement derived from:

- PCI-DSS Req 8.3.1 (multi-factor authentication for CDE access)
- SOC 2 CC6.1-03 (logical access controls)
- ISO 27001 A.5.17-01 (authentication information)

### 3.2 Current Status — DEVIATION D-18

> **CRITICAL GAP:** Org-wide 2FA enforcement is currently **disabled** on
> `jolarca-dev` (`two_factor_requirement_enabled: false`). This is tracked as
> **D-18** in `jolarca-control/docs/drift-findings.md` and is a **blocking**
> finding.
>
> **Remediation:** Enable manually in the GitHub UI:
> **Organization settings → Authentication security → Require two-factor
> authentication.** This cannot be managed via the API.

### 3.3 Accepted MFA Methods

| Method | Acceptable | Notes |
|---|---|---|
| Hardware security key (FIDO2/WebAuthn) | Preferred | YubiKey, Titan, etc. |
| TOTP authenticator app | Acceptable | Google Authenticator, Authy, Aegis |
| SMS-based 2FA | Not acceptable | Susceptible to SIM-swap attacks |

### 3.4 Enforcement Timeline

| Milestone | Target | Dependency |
|---|---|---|
| 2FA enabled org-wide | Before first production apply | D-18 remediation |
| Hardware key for org owners | Immediate when second operator onboards | Second operator |
| All operators on hardware keys | Within 90 days of org-wide 2FA | Hardware key procurement |

## 4. Credential Management

### 4.1 Passwords

- GitHub account passwords must meet GitHub's password policy
- Passwords must not be reused across marketplace and non-marketplace accounts
- Password changes are recommended annually and mandatory after any suspected compromise

### 4.2 Personal Access Tokens (PATs)

| Attribute | Requirement |
|---|---|
| Scope | Minimum necessary (never `admin:org` unless required) |
| Expiry | Maximum 90 days; rotation tracked |
| Storage | Password manager only — never in git, CI logs, or chat |
| Rotation | On expiry, on suspicion of compromise, and quarterly |
| Revocation | Immediate on operator departure (leaver procedure) |

### 4.3 Service Account Tokens

| Attribute | Requirement |
|---|---|
| Ownership | Named in `jolarca-control`'s key custody policy |
| Scope | Repository or environment scoped, never org-wide |
| Rotation | Every 90 days (aligned with `github-token-rotation.md` runbook) |
| Storage | GitHub Actions secrets (environment-scoped for production) |
| Audit | Token usage logged; anomalies trigger incident response |

### 4.4 Deploy Keys

- Read-only deploy keys preferred wherever possible
- Read-write deploy keys require documented justification
- All deploy keys are inventoried and reviewed quarterly
- Key rotation aligned with the repository's lifecycle

## 5. Session Security

### 5.1 Session Duration

| Context | Maximum session |
|---|---|
| GitHub web UI | GitHub default (managed by GitHub) |
| API tokens | Bound by token expiry (see §4.2) |
| CI/CD jobs | Duration of the job; no persistent sessions |
| SSH sessions | Idle timeout: 30 minutes |

### 5.2 Concurrent Sessions

- No limit on concurrent sessions for human operators (GitHub manages this)
- Service accounts must not maintain persistent interactive sessions
- CI/CD jobs must use short-lived tokens (`GITHUB_TOKEN` in Actions)

## 6. OAuth and Third-Party Integrations

### 6.1 Approval Process

1. Integration request documented with business justification
2. Security review assessing scope of access requested
3. Organization owner approval
4. Integration registered in the access inventory

### 6.2 Grant Management

- OAuth grants must request minimum scopes
- Grants are reviewed quarterly as part of the access review
- Unused grants are revoked within 30 days of detection

## 7. Authentication for Automated Processes

### 7.1 CI/CD Authentication

- GitHub Actions jobs use the automatic `GITHUB_TOKEN` (short-lived)
- Cross-repository access uses environment-scoped secrets
- No long-lived tokens in workflow files; all tokens referenced as secrets

### 7.2 Terraform Authentication

- `TF_GITHUB_TOKEN` stored as a `production` environment secret (manual approval)
- `TF_GITHUB_TOKEN_READONLY` stored as a repository secret (read-only scope)
- Tokens are distinct credentials with distinct blast radii
- See `jolarca-control/docs/security/key-custody.md` and
  `jolarca-control/docs/security/isolation-model.md`

## 8. Incident Response for Authentication Failures

| Scenario | Response | Timeline |
|---|---|---|
| Suspected credential compromise | Revoke immediately, rotate all tokens, investigate | Immediate |
| Failed MFA attempts (pattern) | Lock account, verify identity, reset | Within 1 hour |
| Service account token leak | Rotate token, audit usage, file incident | Immediate |
| Unauthorized OAuth grant | Revoke grant, assess data exposure | Within 4 hours |

See `jolarca-security/incident-response/plan.md` for the full incident response
procedure.

## 9. Compliance Mapping

| Control | Framework | Implementation |
|---|---|---|
| MFA required | PCI-DSS 8.3.1, SOC 2 CC6.1-03, ISO A.5.17-01 | GitHub org setting (D-18 gap) |
| Token rotation | PCI-DSS 8.3.6, SOC 2 CC6.1 | `github-token-rotation.md` runbook |
| Unique identification | PCI-DSS 8.2, SOC 2 CC6.1 | Signed commits, named accounts |
| Session management | PCI-DSS 8.6 | Token expiry, short-lived CI tokens |
| Credential protection | ISO A.5.17, SOC 2 CC6.7 | Secret scanning, no secrets in git |

---

**Last reviewed:** 2026-09-26
**Next review:** 2026-12-26
**Approved by:** jolarca-dev organization owner
