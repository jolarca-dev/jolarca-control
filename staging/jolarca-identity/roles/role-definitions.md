# Role Definitions — jolarca-dev Marketplace

**Status:** Reference · Effective upon team creation
**Owner:** jolarca-dev organization owner
**Review cadence:** Quarterly or on role change
**Compliance:** SOC 2 CC6.1 · ISO 27001:2022 A.5.15 · PCI-DSS Req 7

---

## 1. Purpose

This document is the **role catalogue** for the `jolarca-dev` marketplace. It
defines every role that may be assigned to an identity (human or machine), the
permissions each role carries, and the constraints on role assignment.

This catalogue is the operational reference for:
- The RBAC policy ([`policies/rbac.md`](../policies/rbac.md))
- The JML procedure ([`lifecycle/joiner-mover-leaver.md`](../lifecycle/joiner-mover-leaver.md))
- The access review procedure ([`access-reviews/procedure.md`](../access-reviews/procedure.md))

## 2. Role Catalogue

### 2.1 Organization Owner

| Attribute | Value |
|---|---|
| **Role ID** | `org-owner` |
| **Scope** | Entire `jolarca-dev` organization |
| **Assignment authority** | By GitHub org settings (manual) |
| **Maximum holders** | 2 (recommended); currently 1 (D-10) |
| **Review cadence** | Quarterly |

**Permissions:**

| Permission | GitHub equivalent | Scope |
|---|---|---|
| `org:admin` | Organization owner | All org settings |
| `repo:admin` | Admin on all repos | All fleet repos |
| `team:admin` | Team maintainer | All teams |
| `billing:admin` | Billing manager | Plan and billing |
| `policy:write` | Push to `jolarca-control` main | Governance tier |
| `secret:admin` | Manage all Actions secrets | Org-wide |

**Constraints:**
- Must have hardware MFA (FIDO2/WebAuthn)
- Must use signed commits
- Cannot be a service account

---

### 2.2 Platform Administrator

| Attribute | Value |
|---|---|
| **Role ID** | `platform-admin` |
| **Scope** | Platform-tier repositories |
| **Assignment authority** | Org owner |
| **Maximum holders** | 3 |
| **Review cadence** | Quarterly |

**Permissions:**

| Permission | GitHub equivalent | Scope |
|---|---|---|
| `repo:admin` | Admin | `jolarca`, `jolarca-data`, `jolarca-identity` |
| `branch:protect` | Manage branch protection | Platform repos |
| `secret:write` | Manage Actions secrets | Platform repos (non-production) |
| `deploy:key:write` | Manage deploy keys | Platform repos |
| `collaborator:add` | Add collaborators | Platform repos |
| `pr:merge` | Merge pull requests | Platform repos |

**Constraints:**
- Must have MFA enabled
- Cannot also hold the `auditor` role (segregation of duties)
- Cannot admin governance-tier repos (`jolarca-control`, `jolarca-compliance`, `jolarca-legal`)

---

### 2.3 Developer

| Attribute | Value |
|---|---|
| **Role ID** | `developer` |
| **Scope** | Assigned repositories |
| **Assignment authority** | Platform admin or org owner |
| **Maximum holders** | Unlimited |
| **Review cadence** | Quarterly |

**Permissions:**

| Permission | GitHub equivalent | Scope |
|---|---|---|
| `repo:write` | Write | Assigned repos only |
| `pr:create` | Create PRs | Assigned repos |
| `pr:review` | Review PRs | Assigned repos (non-governance) |
| `branch:create` | Create branches | Assigned repos |
| `issue:write` | Create/manage issues | Assigned repos |

**Constraints:**
- Must have MFA enabled
- Cannot review own PRs (enforced by branch protection when teams exist)
- Cannot push directly to `main` (enforced by branch protection)
- Cannot access governance-tier repos unless explicitly assigned

---

### 2.4 Auditor (Read-Only)

| Attribute | Value |
|---|---|
| **Role ID** | `auditor` |
| **Scope** | All fleet repositories (read-only) |
| **Assignment authority** | Org owner |
| **Maximum holders** | 5 |
| **Review cadence** | Quarterly |

**Permissions:**

| Permission | GitHub equivalent | Scope |
|---|---|---|
| `repo:read` | Read | All fleet repos |
| `branch:read` | View protection rules | All fleet repos |
| `audit:read` | View audit log (if granted) | Org-wide |
| `compliance:read` | Read | `jolarca-compliance` |

**Constraints:**
- No write access to any repository
- Cannot merge PRs
- Cannot manage secrets, deploy keys, or branch protection
- Cannot also hold the `platform-admin` role (segregation of duties)
- Ideal for external auditors with time-bounded access

---

### 2.5 Security Reviewer

| Attribute | Value |
|---|---|
| **Role ID** | `security-reviewer` |
| **Scope** | Governance-tier repositories |
| **Assignment authority** | Org owner |
| **Maximum holders** | 3 |
| **Review cadence** | Quarterly |

**Permissions:**

| Permission | GitHub equivalent | Scope |
|---|---|---|
| `repo:read` | Read | Governance repos |
| `pr:review` | Review PRs | Governance repos |
| `security:read` | View security alerts | All fleet repos |
| `policy:review` | Review policy changes | `jolarca-control`, `jolarca-identity` |
| `dependabot:read` | View Dependabot alerts | All fleet repos |

**Constraints:**
- Cannot push to governance repos (review only)
- Cannot admin any repository
- Cannot manage secrets or deploy keys
- Should have security training or certification

---

### 2.6 Service Account

| Attribute | Value |
|---|---|
| **Role ID** | `service-account` |
| **Scope** | Specific repositories or CI/CD pipelines |
| **Assignment authority** | Platform admin or org owner |
| **Maximum holders** | Unlimited |
| **Review cadence** | Quarterly |

**Permissions:**

| Permission | GitHub equivalent | Scope |
|---|---|---|
| Variable by sub-type | CI/CD, deploy, or read | As configured |

**Sub-types:**

| Sub-type | Purpose | Token type | Rotation |
|---|---|---|---|
| `service-account:ci` | CI/CD pipeline execution | `GITHUB_TOKEN` (automatic) | Per-job (short-lived) |
| `service-account:deploy` | Deployment automation | PAT or deploy key | 90 days |
| `service-account:monitor` | Monitoring and alerting | Read-only PAT | 90 days |
| `service-account:integration` | Third-party integration | OAuth grant | 90 days |

**Constraints:**
- Must not hold interactive session access
- Token scope must be minimum necessary
- Must be inventoried in the access review
- Must not be assigned to a human identity

## 3. Role Assignment Register

> **Current state:** `jolarca-dev` has zero teams (D-10). The register below is
> empty. When teams are created, this section records the live assignments.

| Identity | Role | Assigned date | Assigned by | Next review |
|---|---|---|---|---|
| `@JourneyOfLife` | `org-owner` | (org founding) | N/A | 2026-12-26 |

## 4. Role Compatibility Matrix

| | `org-owner` | `platform-admin` | `developer` | `auditor` | `security-reviewer` |
|---|---|---|---|---|---|
| `org-owner` | — | ✗ | ✗ | ✗ | ✗ |
| `platform-admin` | ✗ | — | ✓ | ✗ | ✓ |
| `developer` | ✗ | ✓ | — | ✓ | ✓ |
| `auditor` | ✗ | ✗ | ✓ | — | ✓ |
| `security-reviewer` | ✗ | ✓ | ✓ | ✓ | — |

**Key:** ✓ = compatible · ✗ = prohibited (segregation of duties violation)

**Rationale for prohibitions:**
- `org-owner` + any other role: Org owner has unilateral authority; combining with other roles is unnecessary and obscures audit trails
- `platform-admin` + `auditor`: Administrator cannot audit their own administration
- `developer` + `org-owner`: Developer with org admin bypasses the tier model

## 5. GitHub Team Mapping (Planned)

| Role | GitHub Team | Repository scope |
|---|---|---|
| `org-owner` | N/A | Org-wide |
| `platform-admin` | `platform-admins` | `jolarca`, `jolarca-data`, `jolarca-identity` |
| `developer` | `developers` | Assigned repos |
| `auditor` | `auditors` | All repos (read) |
| `security-reviewer` | `security-reviewers` | `jolarca-control`, `jolarca-identity`, `jolarca-compliance`, `jolarca-legal` |

## 6. Review and Change Management

- **Changes to role definitions** require a PR to this repository
- **Role assignments** are changed via the JML procedure
- **Quarterly review** of all assignments per the access review procedure
- **Evidence** of reviews stored in `jolarca-compliance/access-reviews/`

---

**Last reviewed:** 2026-09-26
**Next review:** 2026-12-26
**Approved by:** jolarca-dev organization owner
