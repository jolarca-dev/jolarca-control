# RBAC Policy as Code — jolarca-dev Marketplace

**Status:** Policy · Effective upon population
**Owner:** jolarca-dev organization owner
**Review cadence:** Quarterly or on role change
**Compliance:** SOC 2 CC6.1 · ISO 27001:2022 A.5.15 · PCI-DSS Req 7

---

## 1. Purpose

This document defines the Role-Based Access Control (RBAC) model for the
`jolarca-dev` marketplace as machine-readable policy. RBAC definitions here
are the **authoritative source** for who may do what within the marketplace
fleet.

## 2. RBAC Model

### 2.1 Core Concepts

```
Identity → Role → Permissions → Resources
```

| Concept | Definition | Example |
|---|---|---|
| **Identity** | A named account (human or machine) | `@JourneyOfLife`, `ci-deploy-bot` |
| **Role** | A named set of permissions | `platform-admin`, `auditor` |
| **Permission** | An allowed action on a resource class | `repo:write`, `branch:protect` |
| **Resource** | A protected object in the marketplace | A repository, a branch, a secret |

### 2.2 Design Principles

1. **Roles are additive.** An identity's effective permissions are the union of
   all permissions from all assigned roles.
2. **No implicit escalation.** A role cannot grant permissions that exceed the
   organization's maximum delegation (org owner retains all permissions).
3. **Roles are scoped.** Each role is defined per-tier (governance, platform,
   devops) — a role in one tier does not automatically confer permissions in another.
4. **Separation of duties is a role constraint.** Certain role combinations are
   prohibited (e.g., the identity that writes code cannot also approve its merge
   in a governance-tier repository).

## 3. Role Definitions

### 3.1 Organization Owner

| Attribute | Value |
|---|---|
| Scope | Entire `jolarca-dev` organization |
| Permissions | Full administrative access |
| Assignment | By GitHub org settings |
| Current holders | `@JourneyOfLife` (sole operator — D-10) |
| Review cadence | Quarterly |

**Permissions:**
- `org:*` — all organization-level actions
- `repo:*` — all repository-level actions on all fleet repos
- `team:*` — create, modify, delete teams
- `billing:*` — manage billing and plan settings
- `policy:*` — modify fleet-wide policy in `jolarca-control`

### 3.2 Platform Administrator

| Attribute | Value |
|---|---|
| Scope | Platform-tier repositories |
| Permissions | Repository administration, branch protection, secret management |
| Assignment | By org owner |
| Current holders | None (pending team creation — D-10) |

**Permissions:**
- `repo:admin` on platform-tier repos (`jolarca`, `jolarca-data`, `jolarca-identity`)
- `branch:protect` — manage branch protection rules
- `secret:manage` — manage Actions secrets (non-production)
- `deploy:key:manage` — manage deploy keys
- `collaborator:add` — add collaborators to platform repos

### 3.3 Developer

| Attribute | Value |
|---|---|
| Scope | Assigned repositories |
| Permissions | Push branches, create PRs, review code |
| Assignment | By platform administrator or org owner |
| Current holders | None (pending team creation — D-10) |

**Permissions:**
- `repo:write` on assigned repos
- `pr:create` — create pull requests
- `pr:review` — review and approve pull requests (on non-governance repos)
- `branch:create` — create feature branches
- `issue:manage` — create and manage issues

### 3.4 Auditor (Read-Only)

| Attribute | Value |
|---|---|
| Scope | All fleet repositories |
| Permissions | Read-only access for compliance verification |
| Assignment | By org owner |
| Current holders | None (pending team creation — D-10) |

**Permissions:**
- `repo:read` on all fleet repos
- `branch:view` — view branch protection rules
- `audit:read` — view audit log entries (if API access granted)
- `compliance:read` — read access to `jolarca-compliance` evidence

**Restrictions:**
- No write access to any repository
- No ability to merge PRs or modify branch protection
- No access to Actions secrets or deploy keys

### 3.5 Security Reviewer

| Attribute | Value |
|---|---|
| Scope | Governance-tier and security-relevant repositories |
| Permissions | Security review, policy change approval |
| Assignment | By org owner |
| Current holders | None (pending team creation — D-10) |

**Permissions:**
- `repo:read` on governance-tier repos
- `pr:review` on governance-tier repos (including `jolarca-control`, `jolarca-identity`)
- `security:read` — view security alerts and Dependabot findings
- `policy:review` — review proposed policy changes

## 4. Permission Matrix

The following matrix maps roles to permissions across repository tiers:

| Permission | Org Owner | Platform Admin | Developer | Auditor | Security Reviewer |
|---|---|---|---|---|---|
| `org:*` | ✓ | — | — | — | — |
| `repo:admin` (governance) | ✓ | — | — | — | — |
| `repo:admin` (platform) | ✓ | ✓ | — | — | — |
| `repo:admin` (devops) | ✓ | — | — | — | — |
| `repo:write` (governance) | ✓ | — | — | — | — |
| `repo:write` (platform) | ✓ | ✓ | ✓* | — | — |
| `repo:read` (all) | ✓ | ✓ | ✓* | ✓ | ✓ |
| `pr:review` (governance) | ✓ | — | — | — | ✓ |
| `pr:review` (platform) | ✓ | ✓ | ✓ | — | ✓ |
| `branch:protect` | ✓ | ✓* | — | — | — |
| `secret:manage` | ✓ | ✓* | — | — | — |
| `deploy:key:manage` | ✓ | ✓* | — | — | — |
| `collaborator:add` | ✓ | ✓* | — | — | — |
| `audit:read` | ✓ | — | — | ✓ | ✓ |

\* Restricted to assigned repositories only.

## 5. Prohibited Role Combinations

The following combinations violate segregation of duties (ISO 27001 A.5.3):

| Combination | Reason |
|---|---|
| Developer + Security Reviewer (same repo) | Author cannot review their own changes |
| Platform Admin + Auditor (same scope) | Administrator cannot audit their own administration |
| Any role + Org Owner (second person) | Org owner has unilateral authority; second owner requires explicit justification |

## 6. Implementation Status

> **Current state:** `jolarca-dev` has **zero teams** (D-10). All access is via
> org ownership by the single operator. The RBAC model above is the
> **target-state definition** — it becomes enforceable when teams are created.

### 6.1 Activation Triggers

| Event | Action |
|---|---|
| Second operator onboards | Create teams: `platform-admins`, `developers`, `auditors` |
| Teams created | Update CODEOWNERS in all fleet repos to reference team slugs |
| Teams active | Raise `required_approving_review_count` to 1 (close D-04) |
| Roles assigned | This RBAC model becomes the enforcement baseline |

### 6.2 Mapping to GitHub Teams

| RBAC Role | GitHub Team (planned) | Tier |
|---|---|---|
| Organization Owner | N/A (org setting) | Org-wide |
| Platform Administrator | `platform-admins` | Platform repos |
| Developer | `developers` | Assigned repos |
| Auditor | `auditors` | All repos (read) |
| Security Reviewer | `security-reviewers` | Governance repos |

## 7. Review and Change Management

- **Quarterly review:** All role assignments reviewed by the org owner
- **On change:** Role changes trigger the mover procedure
  (`lifecycle/joiner-mover-leaver.md`)
- **Evidence:** Completed reviews recorded in `jolarca-compliance/access-reviews/`
- **Policy changes:** Changes to this RBAC model require a PR to this repository
  with full compliance gates passing

## 8. Compliance Mapping

| Control | Framework | How this section satisfies it |
|---|---|---|
| Identity management | ISO A.5.15 | Roles and identities explicitly defined |
| Access rights provisioning | ISO A.5.17 | Permission matrix defines what each role may access |
| Least privilege | PCI-DSS Req 7.2 | Roles grant minimum necessary permissions |
| Logical access | SOC 2 CC6.1 | Role-to-permission mapping is documented and reviewable |
| Segregation of duties | ISO A.5.3 | Prohibited combinations table enforces separation |

---

**Last reviewed:** 2026-09-26
**Next review:** 2026-12-26
**Approved by:** jolarca-dev organization owner
