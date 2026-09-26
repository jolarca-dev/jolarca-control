# Access Control Policy — jolarca-dev Marketplace

**Status:** Policy · Effective upon publication
**Owner:** jolarca-dev organization owner
**Review cadence:** Quarterly or on material change
**Compliance:** SOC 2 CC6.1 · ISO 27001:2022 A.5.15 · PCI-DSS Req 7

---

## 1. Purpose

This policy defines the principles, roles, and controls governing logical access
to all systems, repositories, and data within the `jolarca-dev` marketplace
fleet. It applies to all human operators, service accounts, and automated
processes that access marketplace resources.

## 2. Scope

| In scope | Out of scope |
|---|---|
| All `jolarca-dev` GitHub repositories | Mission-platform (`journeyoflife-org` / `jol-*`) resources |
| All marketplace infrastructure and services | Personal accounts not affiliated with the organization |
| Human operator accounts and service accounts | Third-party SaaS not integrated with the marketplace |
| API tokens, deploy keys, and OAuth grants | Credentials managed exclusively by third-party providers |

## 3. Principles

### 3.1 Least Privilege (PCI-DSS Req 7.2)

Every identity — human or machine — receives the **minimum permissions
necessary** to perform its assigned function. Permissions beyond the minimum
are not granted proactively; they must be requested, justified, and
time-bounded.

### 3.2 Need-to-Know (GDPR Art. 5(1)(f))

Access to personal data is restricted to identities with a documented business
need. The data classification of each repository (`public`, `internal`,
`confidential`, `restricted`) determines the minimum clearance required.

### 3.3 Separation of Duties (ISO 27001 A.5.3)

No single identity may both **request** and **approve** a permission change.
In the current solo-operator era (D-10), this principle is structurally
unsatisfiable for human review; compensating controls are:

- Automated status checks on every PR
- Signed commits attributing every change
- The `apply.yml` plan-refusal gate blocking destructive changes
- `prevent_destroy` lifecycle on all repository resources

Segregation of duties becomes enforceable when the second operator onboards
and teams are created in `jolarca-dev`.

### 3.4 Defence in Depth

Access control operates at multiple layers:

1. **Organization membership** — who may be a member at all
2. **Team membership** — which functional group an identity belongs to
3. **Repository permissions** — what each team can do in each repository
4. **Branch protection** — what each role can do on each branch
5. **Status checks** — automated gates that must pass before changes apply

## 4. Identity Types

| Type | Description | Authentication | Lifecycle |
|---|---|---|---|
| Human operator | Named individual with org membership | GitHub account + MFA | JML procedure |
| Service account | Automated identity for CI/CD or integrations | Token (rotated per policy) | Provisioned via IaC |
| Deploy key | Repository-scoped SSH key | SSH key pair | Bound to repository lifecycle |
| OAuth app | Third-party integration | OAuth 2.0 grant | Approved via security review |

## 5. Access Provisioning

### 5.1 New Joiners

See [`lifecycle/joiner-mover-leaver.md`](../lifecycle/joiner-mover-leaver.md)
for the complete joiner procedure. Summary:

1. Identity verified by the organization owner
2. Account added to `jolarca-dev` with minimum default permissions
3. Role assigned per [`roles/role-definitions.md`](../roles/role-definitions.md)
4. Access review scheduled within 30 days of provisioning

### 5.2 Role Changes (Movers)

When an operator's role changes:

1. Previous permissions are **revoked** (not merely supplemented)
2. New role permissions are granted per the RBAC matrix
3. The change is recorded in the access review log (evidence in `jolarca-compliance`)

### 5.3 Deprovisioning (Leavers)

See [`lifecycle/joiner-mover-leaver.md`](../lifecycle/joiner-mover-leaver.md)
for the complete leaver procedure. Summary:

1. Access revoked within **24 hours** of departure (critical) or **4 hours** for involuntary termination
2. All tokens, deploy keys, and OAuth grants rotated or revoked
3. Repository collaborator access removed
4. Deprovisioning confirmed and recorded

## 6. Data Classification and Access

| Classification | Who may access | Visibility | Examples |
|---|---|---|---|
| `public` | Anyone | Public | `jolarca` (flagship) |
| `internal` | Org members + approved collaborators | Public or private | `jolarca-identity` (this repo's policies) |
| `confidential` | Named teams with documented need | Private | `jolarca-compliance`, `jolarca-data` |
| `restricted` | Org owner only | Private | Credentials, break-glass procedures |

## 7. Enforcement

| Control | Mechanism | Owner |
|---|---|---|
| Org membership | GitHub org settings | Org owner |
| Team-based access | GitHub teams + repository permissions | Org owner (until teams exist) |
| Branch protection | `branch-protection.tf` + `repos/*.yml` | `jolarca-control` |
| Secret scanning | GitHub native + gitleaks in CI | Automated |
| Access review | Quarterly procedure (this repo) | Org owner |
| Drift detection | `drift_detect.py` in `jolarca-control` | Automated |

## 8. Exceptions

Exceptions to this policy must be:

1. Documented in `jolarca-compliance` with a risk assessment
2. Approved by the organization owner
3. Time-bounded (maximum 90 days, then re-evaluated)
4. Recorded in `jolarca-control`'s exception register
   (`policy/compliance-gates.yml#exceptions`)

## 9. Review and Approval

| Activity | Cadence | Evidence location |
|---|---|---|
| Policy review | Quarterly | This file's `last_reviewed` date |
| Access review | Quarterly | `jolarca-compliance/access-reviews/` |
| RBAC matrix review | On role change + quarterly | `roles/role-definitions.md` history |
| JML procedure test | Annually | `jolarca-compliance/drills/` |

---

**Last reviewed:** 2026-09-26
**Next review:** 2026-12-26
**Approved by:** jolarca-dev organization owner
