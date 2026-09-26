# Access Review Metrics — jolarca-dev Marketplace

**Status:** Reporting · Updated quarterly
**Owner:** jolarca-dev organization owner
**Compliance:** SOC 2 CC6.1, CC9.2 · ISO 27001:2022 A.5.18 · PCI-DSS Req 7.2

---

## 1. Purpose

This document tracks the effectiveness of the access review programme for the
`jolarca-dev` marketplace. Metrics are updated after each quarterly review and
provide evidence that access controls are actively monitored and enforced.

> **Evidence location:** Completed review records and signed attestations are
> stored in `jolarca-compliance/access-reviews/`. This document summarises the
> metrics; the detailed evidence lives in the compliance repository.

## 2. Key Performance Indicators

### 2.1 Review Coverage

| KPI | Target | Measurement |
|---|---|---|
| Identities reviewed on schedule | 100% | (Identities reviewed in quarter) / (Total identities in scope) × 100 |
| Service accounts reviewed on schedule | 100% | (Service accounts reviewed) / (Total service accounts) × 100 |
| Privileged accounts reviewed | 100% | (Privileged accounts reviewed) / (Total privileged accounts) × 100 |
| Reviews completed by due date | ≥ 95% | (Reviews completed on time) / (Total reviews due) × 100 |

### 2.2 Finding Metrics

| KPI | Target | Measurement |
|---|---|---|
| Findings per review | Decreasing trend | Total findings per quarterly review |
| Critical findings | 0 | Count of critical-severity findings |
| Mean time to remediate (critical) | < 4 hours | Average hours from finding to remediation |
| Mean time to remediate (high) | < 24 hours | Average hours from finding to remediation |
| Mean time to remediate (medium) | < 7 business days | Average business days from finding to remediation |
| Mean time to remediate (low) | < 30 business days | Average business days from finding to remediation |

### 2.3 Exception Metrics

| KPI | Target | Measurement |
|---|---|---|
| Active exceptions | Minimised | Count of currently active exceptions |
| Exceptions past expiry | 0 | Count of exceptions that have lapsed without renewal |
| Exception renewal rate | 100% on time | Exceptions reviewed before expiry |

### 2.4 Stale Access Metrics

| KPI | Target | Measurement |
|---|---|---|
| Stale accounts detected | N/A (informational) | Accounts with no activity in 90 days |
| Stale accounts remediated | 100% within 30 days | Stale accounts removed or re-justified |
| Orphaned service accounts | 0 | Service accounts not linked to an active pipeline |

## 3. Quarterly Reports

### 2026 Q3 (Baseline)

> **Status:** No reviews conducted yet. Repository is in `planned` status.
> This section will be populated after the first quarterly review following
> the repository becoming `operational`.

| Metric | Value | Target | Status |
|---|---|---|---|
| Identities reviewed | — | 100% | Not yet started |
| Critical findings | — | 0 | — |
| Mean time to remediate (critical) | — | < 4h | — |
| Active exceptions | — | Minimised | — |
| Stale accounts detected | — | Informational | — |

**Notes:**
- Repository is `planned`; no access reviews have been conducted
- `jolarca-dev` has zero teams (D-10); the first review will establish the baseline
- D-18 (2FA not enforced) is the most critical identity-related gap

## 4. Trend Analysis

> This section will be populated after two or more quarterly reviews, enabling
> trend comparison.

| Quarter | Identities | Findings | Critical | Exceptions | Stale |
|---|---|---|---|---|---|
| 2026 Q3 | — | — | — | — | — |

## 5. Audit Trail

| Date | Action | By | Evidence |
|---|---|---|---|
| 2026-09-26 | Metrics document created | `@JourneyOfLife` | This file |

## 6. Compliance Mapping

| Control | Framework | How these metrics satisfy it |
|---|---|---|
| Access rights review | ISO A.5.18 | Coverage metrics prove reviews happen |
| Monitoring | SOC 2 CC9.2 | Trend analysis demonstrates continuous improvement |
| Least privilege | PCI-DSS Req 7.2 | Finding metrics track privilege creep |
| Exception management | SOC 2 CC9.2 | Exception metrics track risk acceptance hygiene |

---

**Last updated:** 2026-09-26
**Next update:** After first quarterly review (target: 2026-12-31)
