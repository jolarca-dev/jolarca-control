# Joiner / Mover / Leaver (JML) Automation — jolarca-dev Marketplace

**Status:** Procedure · Effective upon team creation
**Owner:** jolarca-dev organization owner
**Review cadence:** Annually or on process change
**Compliance:** SOC 2 CC6.2 · ISO 27001:2022 A.5.16 · PCI-DSS Req 8

---

## 1. Purpose

This document defines the procedures for provisioning, modifying, and
revoking access to the `jolarca-dev` marketplace throughout an identity's
lifecycle. Every joiner, mover, and leaver event must follow this procedure
to maintain the integrity of the access control framework defined in
[`policies/access-control-policy.md`](../policies/access-control-policy.md).

## 2. Scope

| Event | Description | Trigger |
|---|---|---|
| **Joiner** | New identity granted access to the marketplace | Employment, contract, or integration approval |
| **Mover** | Existing identity's role or permissions change | Role change, project reassignment, promotion |
| **Leaver** | Identity's access fully revoked | Departure, contract end, compromise |

This procedure applies to:
- Human operator accounts
- Service accounts and CI/CD identities
- Deploy keys and OAuth grants
- Temporary elevated-access grants

## 3. Joiner Procedure

### 3.1 Pre-Provisioning Checklist

| Step | Action | Responsible | Evidence |
|---|---|---|---|
| J-1 | Identity verification: confirm the individual's identity and authorization to access | Org owner | Identity document or contract |
| J-2 | Determine required role per [`roles/role-definitions.md`](../roles/role-definitions.md) | Org owner | Role assignment record |
| J-3 | Verify MFA is enabled on the individual's GitHub account | Org owner | GitHub API check |
| J-4 | Check for conflicts: no prohibited role combinations (see RBAC §5) | Org owner | RBAC matrix review |

### 3.2 Provisioning Steps

| Step | Action | Method | Verification |
|---|---|---|---|
| J-5 | Add user to `jolarca-dev` organization | GitHub UI or API | `gh api orgs/jolarca-dev/members` |
| J-6 | Assign to appropriate team(s) | GitHub team management | `gh api orgs/jolarca-dev/teams/{team}/members` |
| J-7 | Verify repository permissions match the role's permission set | GitHub API | `gh api repos/{repo}/collaborators/{user}/permission` |
| J-8 | Confirm no excess permissions (least privilege check) | Manual review against RBAC matrix | Access review record |
| J-9 | Schedule first access review within 30 days | Calendar/reminder | Review scheduled |
| J-10 | Record provisioning in the access log | File in `jolarca-compliance` | `jolarca-compliance/access-logs/` |

### 3.3 Joiner SLA

| Account type | Target completion |
|---|---|
| Human operator | Within 1 business day of authorization |
| Service account | Within 2 business days of IaC PR merge |
| Deploy key | Within 1 business day of repository request |
| OAuth integration | Within 5 business days of security review approval |

## 4. Mover Procedure

### 4.1 When a Mover Event Occurs

- Role change (promotion, demotion, lateral move)
- Project reassignment (different repository scope)
- Temporary elevated access (time-bounded permission increase)

### 4.2 Mover Steps

| Step | Action | Responsible | Verification |
|---|---|---|---|
| M-1 | Document the role change and new required permissions | Org owner | Change record |
| M-2 | **Revoke** all permissions from the previous role | Org owner | `gh api` verification |
| M-3 | Grant new permissions per the target role | Org owner | Permission check |
| M-4 | Verify no permission accumulation (old + new) | Manual review | RBAC matrix comparison |
| M-5 | Update team membership if applicable | GitHub team management | Team membership check |
| M-6 | Record the move in the access log | File in `jolarca-compliance` | Access log entry |
| M-7 | Schedule access review within 14 days of the move | Calendar/reminder | Review scheduled |

### 4.3 Critical Rule: Revoke Before Grant

> **The mover procedure MUST revoke previous permissions BEFORE granting new
> ones.** Adding permissions on top of existing ones without revoking the old
> set is the most common cause of privilege accumulation, and it violates
> least privilege (PCI-DSS Req 7.2).
>
> If the revocation would cause a service disruption (e.g., the individual is
> mid-deploy), coordinate the revocation with a maintenance window and
> document the temporary overlap.

### 4.4 Temporary Elevated Access

| Attribute | Requirement |
|---|---|
| Justification | Documented business need |
| Duration | Maximum 30 days |
| Auto-revocation | Access MUST be revoked at expiry — no silent extensions |
| Approval | Org owner |
| Evidence | Recorded in `jolarca-compliance` |

## 5. Leaver Procedure

### 5.1 Leaver Types

| Type | Notice | Access revocation timeline |
|---|---|---|
| Planned departure | Known end date | Access revoked on last working day |
| Immediate departure | No notice | Access revoked within 4 hours |
| Involuntary termination | No notice | Access revoked within 4 hours |
| Compromise suspected | Immediate | Access revoked immediately |

### 5.2 Leaver Steps

| Step | Action | Responsible | Timeline | Verification |
|---|---|---|---|---|
| L-1 | Remove from all GitHub teams | Org owner | Per §5.1 | `gh api` verification |
| L-2 | Remove as collaborator from all repositories | Org owner | Per §5.1 | `gh api` verification |
| L-3 | Revoke all personal access tokens | Org owner | Per §5.1 | Token inventory check |
| L-4 | Revoke or rotate all deploy keys owned by the leaver | Org owner | Per §5.1 | Deploy key inventory |
| L-5 | Revoke all OAuth grants associated with the leaver | Org owner | Per §5.1 | OAuth grant inventory |
| L-6 | Remove from `jolarca-dev` organization | Org owner | Per §5.1 | `gh api orgs/jolarca-dev/members` |
| L-7 | Rotate any shared secrets the leaver had access to | Org owner | Within 24 hours | Secret rotation log |
| L-8 | Record deprovisioning in the access log | File in `jolarca-compliance` | Within 1 business day | Access log entry |
| L-9 | Verify no residual access remains | Automated or manual | Within 48 hours | Full access audit |

### 5.3 Compromise Scenario — Immediate Actions

If a leaver event is triggered by suspected compromise:

1. **Immediately** remove the account from the organization
2. **Immediately** rotate ALL tokens the account could access (not just own)
3. **Immediately** review the account's recent activity for unauthorized changes
4. File an incident per `jolarca-security/incident-response/plan.md`
5. Assess whether the compromise is notifiable under GDPR Art. 33

### 5.4 Leaver Verification Checklist

After completing all leaver steps, verify:

```bash
# Verify the user is no longer an org member
gh api orgs/jolarca-dev/members -q '.[].login' | grep -c "^{username}$"
# Expected: 0

# Verify the user is not a collaborator on any fleet repo
for r in jolarca jolarca-control jolarca-compliance jolarca-data \
         jolarca-identity jolarca-infrastructure jolarca-legal; do
  gh api "repos/jolarca-dev/$r/collaborators/{username}" 2>&1 | grep -c "Not found"
done
# Expected: all return 1 (Not found)

# Verify no active tokens (manual inventory check)
# Review: GitHub Settings → Developer settings → Personal access tokens
```

## 6. Automation Opportunities

### 6.1 Current State (Manual)

In the solo-operator era, all JML events are executed manually by the org
owner. Each step is documented and verified against the live GitHub API.

### 6.2 Target State (Automated)

When teams exist and the second operator onboards:

| Automation | Description | Trigger |
|---|---|---|
| Joiner workflow | GitHub Actions workflow that provisions access from a YAML request | Approved PR to `jolarca-identity` |
| Mover workflow | Automated permission diff: revoke old, grant new | Approved PR to `jolarca-identity` |
| Leaver workflow | Automated full deprovision from a YAML request | Approved PR or incident trigger |
| Access inventory sync | Periodic reconciliation of live access vs. declared roles | Weekly cron |
| Stale access detector | Alert on accounts with no activity in 90 days | Weekly cron |

### 6.3 Request Format (Target State)

```yaml
# Example: joiner request (to be submitted as a PR to jolarca-identity)
apiVersion: identity.jolarca.dev/v1
kind: AccessRequest
metadata:
  name: joiner-jdoe-2026-10-01
  type: joiner
spec:
  identity: jdoe
  github_login: jdoe-github
  role: developer
  repositories:
    - jolarca
    - jolarca-data
  mfa_verified: true
  approved_by: JourneyOfLife
  valid_from: 2026-10-01
  review_due: 2026-10-31  # 30-day first review
```

## 7. Evidence and Audit Trail

Every JML event must produce evidence stored in `jolarca-compliance`:

| Event | Evidence | Retention |
|---|---|---|
| Joiner | Provisioning record with role, permissions, date, approver | Duration of access + 7 years |
| Mover | Change record with old/new permissions, revocation confirmation | Duration of access + 7 years |
| Leaver | Deprovisioning record with verification results | 7 years from departure |
| Compromise | Incident record with timeline and remediation | 7 years from resolution |

## 8. Compliance Mapping

| Control | Framework | How this procedure satisfies it |
|---|---|---|
| Authentication information management | ISO A.5.16 | Credentials provisioned and revoked per procedure |
| Access rights provisioning | ISO A.5.17 | Joiner/mover steps ensure correct rights assignment |
| Removal of access rights | ISO A.5.17 | Leaver steps ensure complete revocation |
| Unique identification | PCI-DSS Req 8.2 | Each identity individually provisioned and tracked |
| Logon review | SOC 2 CC6.2 | JML events logged and evidence retained |

---

**Last reviewed:** 2026-09-26
**Next review:** 2026-09-26 (annual)
**Approved by:** jolarca-dev organization owner
