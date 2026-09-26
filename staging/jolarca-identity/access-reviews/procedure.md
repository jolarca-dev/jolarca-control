# Access Review Procedure — jolarca-dev Marketplace

**Status:** Procedure · Effective upon team creation
**Owner:** jolarca-dev organization owner
**Review cadence:** Quarterly
**Compliance:** SOC 2 CC6.1 · ISO 27001:2022 A.5.18 · PCI-DSS Req 7.2

---

## 1. Purpose

This procedure defines how access rights across the `jolarca-dev` marketplace
are periodically reviewed to ensure they remain appropriate, least-privilege,
and aligned with current role assignments. It is the **procedural
counterpart** of the RBAC policy defined in
[`policies/rbac.md`](../policies/rbac.md).

> **System of record:** This document defines HOW access reviews are conducted.
> The EVIDENCE of completed reviews (signed attestations, review logs,
> exception records) is stored in
> [`jolarca-compliance`](https://github.com/jolarca-dev/jolarca-compliance),
> NOT in this repository. This repo holds the procedure; `jolarca-compliance`
> holds the proof.

## 2. Scope

This procedure covers:

| Review target | What is checked |
|---|---|
| Organization membership | Is every org member still authorized? |
| Team membership | Does each team contain only the correct members? |
| Repository permissions | Do team/individual permissions match the RBAC matrix? |
| Service accounts | Are all service accounts still needed and correctly scoped? |
| Deploy keys | Are deploy keys inventoried and still required? |
| OAuth grants | Are third-party integrations still authorized? |
| Personal access tokens | Are PATs within their rotation window? |
| Branch protection | Are protection rules consistent with `repos/*.yml`? |

## 3. Review Schedule

| Review type | Frequency | Due date | Responsible |
|---|---|---|---|
| Full access review | Quarterly | Last business day of each quarter | Org owner |
| Service account review | Quarterly | Same as full review | Org owner |
| Leaver verification | Per event | Within 48 hours of departure | Org owner |
| Privileged access review | Quarterly | Same as full review | Org owner |
| Emergency review | Per trigger | Within 24 hours of trigger | Org owner |

**Emergency review triggers:**
- Suspected compromise of any account
- Detection of unauthorized access (drift finding)
- Organization security incident
- Regulatory inquiry or audit notification

## 4. Quarterly Review Procedure

### 4.1 Preparation (Day 1)

| Step | Action | Output |
|---|---|---|
| P-1 | Export current org membership | `gh api orgs/jolarca-dev/members` |
| P-2 | Export all team memberships | `gh api orgs/jolarca-dev/teams/{team}/members` for each team |
| P-3 | Export repository collaborator lists | `gh api repos/jolarca-dev/{repo}/collaborators` for each repo |
| P-4 | Export branch protection rules | `gh api repos/jolarca-dev/{repo}/branches/main/protection` |
| P-5 | Run `drift_detect.py` from `jolarca-control` | Drift report |
| P-6 | Compile the review package | All exports + RBAC matrix + previous review findings |

### 4.2 Review Execution (Days 2–5)

For each identity in the review scope:

| Step | Check | Pass criteria | Action on fail |
|---|---|---|---|
| R-1 | Is this identity still authorized? | Present in current personnel/contract records | Initiate leaver procedure |
| R-2 | Does the identity's role match their current function? | Role in RBAC matrix matches actual work | Initiate mover procedure |
| R-3 | Are permissions consistent with the role? | No excess permissions per RBAC matrix | Revoke excess, record change |
| R-4 | Has the identity been active within 90 days? | At least one login/action in 90 days | Flag for review; possible leaver |
| R-5 | Are the identity's tokens within rotation window? | All tokens rotated within 90 days | Rotate immediately |
| R-6 | Does the identity have access to repos outside their tier? | No cross-tier access without documented exception | Revoke or document exception |

### 4.3 Privileged Access Review

For identities with elevated permissions (org owner, platform admin):

| Step | Additional check | Pass criteria |
|---|---|---|
| PA-1 | Is elevated access still required? | Business justification current |
| PA-2 | Are all elevated actions logged? | Audit trail exists for privileged operations |
| PA-3 | Has the privileged identity been used for non-privileged work? | Separation maintained |
| PA-4 | Is MFA active and using a hardware key (preferred)? | Hardware key enrolled |

### 4.4 Service Account Review

| Step | Check | Pass criteria |
|---|---|---|
| SA-1 | Is the service account still needed? | Active use in the last 90 days |
| SA-2 | Are its tokens within rotation window? | Rotated within 90 days |
| SA-3 | Is its scope still minimal? | No scope creep since last review |
| SA-4 | Is its access documented? | Listed in the access inventory |

### 4.5 Documentation and Evidence (Day 5)

| Step | Action | Evidence location |
|---|---|---|
| D-1 | Record review findings (pass/fail per identity) | `jolarca-compliance/access-reviews/YYYY-QN/` |
| D-2 | Record all remediation actions taken | Same location, remediation log |
| D-3 | Record any exceptions granted | `jolarca-compliance/access-reviews/YYYY-QN/exceptions/` |
| D-4 | Sign the review attestation | Org owner digital signature |
| D-5 | Update `metrics/access-review-metrics.md` with results | This repository |

## 5. Review Template

Use this template for each quarterly review:

```markdown
# Access Review — YYYY QN

**Reviewer:** [name]
**Date:** YYYY-MM-DD
**Scope:** Full / Service accounts / Privileged / Emergency

## Summary

| Metric | Value |
|---|---|
| Total identities reviewed | N |
| Passed without change | N |
| Changes required | N |
| Exceptions granted | N |
| Accounts flagged for removal | N |

## Findings

### Finding 1: [title]
- **Identity:** [account name]
- **Issue:** [description]
- **Severity:** Critical / High / Medium / Low
- **Action taken:** [remediation]
- **Evidence:** [link to proof]

## Attestation

I certify that this access review was conducted in accordance with the
procedure defined in `jolarca-identity/access-reviews/procedure.md` and that
all findings are accurately recorded.

**Signed:** [name]
**Date:** YYYY-MM-DD
```

## 6. Exception Handling

If an access review identifies a deviation from the RBAC policy:

1. **Document** the deviation with a business justification
2. **Assess** the risk (likelihood × impact)
3. **Determine** compensating controls
4. **Time-bound** the exception (maximum 90 days)
5. **Approve** via the org owner
6. **Record** in `jolarca-compliance/access-reviews/YYYY-QN/exceptions/`
7. **Register** in `jolarca-control/policy/compliance-gates.yml#exceptions` if fleet-wide

## 7. Remediation SLA

| Severity | Remediation deadline | Escalation |
|---|---|---|
| Critical (unauthorised access) | Immediate — within 4 hours | Incident response |
| High (excess privilege) | Within 24 hours | Org owner |
| Medium (stale access) | Within 7 business days | Next quarterly review |
| Low (documentation gap) | Within 30 business days | Next quarterly review |

## 8. Metrics and Reporting

Access review metrics are tracked in
[`metrics/access-review-metrics.md`](../metrics/access-review-metrics.md) and
include:

- Percentage of identities reviewed on schedule
- Number of findings by severity
- Mean time to remediate by severity
- Exception count and ageing
- Stale account detection rate

## 9. Compliance Mapping

| Control | Framework | How this procedure satisfies it |
|---|---|---|
| Access rights review | ISO A.5.18 | Quarterly review of all access rights |
| Logical access | SOC 2 CC6.1 | Systematic verification of who has access to what |
| Least privilege | PCI-DSS Req 7.2 | Each review checks for excess permissions |
| Monitoring and testing | SOC 2 CC9.2 | Metrics track review effectiveness over time |
| Record keeping | ISO A.5.18, SOC 2 CC8.1 | Evidence retained in `jolarca-compliance` |

---

**Last reviewed:** 2026-09-26
**Next review:** 2026-12-26
**Approved by:** jolarca-dev organization owner
