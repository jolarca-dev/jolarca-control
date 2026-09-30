# SOC 2 Type I Readiness Assessment

**Created:** 2026-10-01
**Authority:** ADR-0008 (Option C: pursue Type I within 30 days)
**Deadline:** Engage auditor by 2026-10-28
**Status:** READY FOR AUDITOR ENGAGEMENT

---

## 1. Purpose

This document assesses whether the jolarca-dev control plane is ready for a
SOC 2 Type I examination (controls suitably designed as of a point in time).
It identifies what evidence is available, what gaps remain, and what an
auditor will need.

Type I validates **design suitability** — are the controls properly designed
to meet the trust service criteria? It does NOT test operating effectiveness
(that is Type II, planned for 2027-Q1 per ADR-0008).

## 2. Trust Service Criteria Readiness

### CC6.1 — Logical and Physical Access Controls

| Control | Evidence | Status |
|---------|----------|--------|
| Branch protection on all repos | `drift_detect.py` + live verification | **READY** — all non-empty repos protected |
| 2FA enforced org-wide | GitHub org setting verified | **READY** — D-18 resolved |
| Default permission = none | GitHub org setting verified | **READY** — D-19 resolved |
| Member repo creation disabled | GitHub org setting verified | **READY** — D-19 resolved |
| No teams (solo operator) | `gh api orgs/jolarca-dev/teams` → empty | **READY** — documented in D-10 |

### CC6.2 — Authentication and Authorization

| Control | Evidence | Status |
|---------|----------|--------|
| Signed commits (policy) | `commit_signing_policy` in repo-defaults.yml | **ACCEPTED** — D-05, policy-only |
| GPG signing by operator | `git log --show-signature` | **READY** |
| Secret scanning (CI) | gitleaks in compliance-scan.yml | **READY** |
| No secrets in git | `.gitleaks.toml`, `.gitleaksignore` | **READY** |

### CC6.6 — Security for Externally-Facing Systems

| Control | Evidence | Status |
|---------|----------|--------|
| Fleet separation (ADR-0004) | `check_fleet_separation.sh` in CI | **READY** |
| No cross-org references | `check_codeowners()` in drift_detect.py | **READY** — D-20 resolved |
| Mission/marketplace isolation | ADR-0004 verified | **READY** |

### CC7.1 — System Operations and Monitoring

| Control | Evidence | Status |
|---------|----------|--------|
| Drift detection (daily) | `drift_detect.py` in CI | **READY** — exit 0 |
| Org audit log | GitHub org audit log (owner-accessible) | **GAP** — not streamed externally (Art30-03) |
| Vulnerability scanning | dependency_scan + SAST + gitleaks in CI | **READY** |
| Compliance gates | `policy/compliance-gates.yml` | **READY** |

### CC7.2 — Change Management

| Control | Evidence | Status |
|---------|----------|--------|
| PR-only merges (branch protection) | All repos protected | **READY** |
| Plan safety gate | `check_plan_safety.sh` + tests | **READY** — D-22 fixed |
| Visibility change refusal | `apply.yml` refuses visibility plans | **READY** |
| Exception register | `compliance-gates.yml` exceptions.active | **READY** — D-25 fixed |
| Evidence integrity | SHA-256 hashes in evidence-registry.csv | **READY** |

### CC8.1 — Change Approval

| Control | Evidence | Status |
|---------|----------|--------|
| Required status checks | 3 contexts on control plane repos | **READY** |
| Squash-only linear history | Enforced on all repos | **READY** |
| CODEOWNERS (inert, documented) | D-20 documented, D-04 exception | **ACCEPTED** |
| Enforce admins | true on all protected repos | **READY** |

### CC9.2 — Risk Mitigation

| Control | Evidence | Status |
|---------|----------|--------|
| Risk register | `docs/drift-findings.md` (40+ findings) | **READY** |
| Exception expiry | D-25 dated acceptances | **READY** |
| PCI-DSS guard | `validate_repos.py` pci-dss check | **READY** |
| Data classification | `repos/*.yml` + `validate_repos.py` | **READY** |

## 3. Gaps That Will Concern an Auditor

| Gap | Finding | Severity | Mitigation |
|-----|---------|----------|------------|
| Terraform state local-only | D-02 (partial) | HIGH | Cloud backend configured; migration pending HCP account |
| No tag protection | D-07 | MEDIUM | Free plan limitation; documented exception |
| Audit log not streamed | Art30-03 | MEDIUM | Org audit log accessible but not retained externally |
| 6 private repos unprotected | D-33 (partial) | MEDIUM | Free plan limitation; all PUBLIC repos protected |
| CODEOWNERS inert | D-20, D-04 | LOW | Documented deviation; compensating controls in place |
| Signed commits not enforced | D-05 | LOW | Policy-only; accepted deviation |

## 4. Evidence Package for Auditor

The following artifacts are available for auditor review:

1. **Control design documentation:**
   - `policy/repo-defaults.yml` — fleet-wide policy baseline
   - `policy/compliance-gates.yml` — gate definitions + exceptions
   - `docs/change-management.md` — change management procedure
   - `docs/architecture.md` — system architecture

2. **Audit trail:**
   - `docs/drift-findings.md` — 40+ findings with evidence and remediation
   - `docs/evidence-registry.csv` — SHA-256 hashed evidence
   - Git history (all changes via PR with CI gates)

3. **Compliance framework mapping:**
   - `audit/soc2-checklist.yml` — SOC 2 control mapping
   - `audit/gdpr-checklist.yml` — GDPR control mapping
   - `audit/iso27001-checklist.yml` — ISO 27001 control mapping
   - `audit/pci-dss-checklist.yml` — PCI-DSS control mapping

4. **Risk management:**
   - `docs/threat-model.md` — threat model
   - `docs/security/dpia-marketplace-launch.md` — DPIA (conditionally signed)
   - `docs/adr/` — architecture decision records

5. **Technical controls:**
   - `.github/workflows/compliance-scan.yml` — CI pipeline
   - `scripts/drift_detect.py` — drift detection
   - `scripts/validate_repos.py` — allow-list validation
   - `scripts/check_plan_safety.sh` — plan safety gate

## 5. Auditor Engagement Checklist

- [ ] Select auditor (firms experienced with GitHub-native orgs preferred)
- [ ] Define scope: all trust service criteria or subset?
- [ ] Provide this readiness assessment + evidence package
- [ ] Schedule examination (Type I is typically 2-4 weeks)
- [ ] Prepare for auditor questions on:
  - Solo operator model (no teams, no segregation of duties)
  - Free plan limitations (tag protection, audit log streaming)
  - Out-of-band changes (documented as deviations in drift-findings.md)
  - Exception register (compliance-gates.yml)

## 6. Timeline

| Milestone | Target | Status |
|-----------|--------|--------|
| ADR-0008 accepted | 2026-09-28 | DONE |
| Readiness assessment | 2026-10-01 | DONE (this document) |
| Engage auditor | 2026-10-28 | PENDING |
| Type I examination | 2026-Q4 | PENDING |
| Type I report issued | 2027-Q1 (estimated) | PENDING |
| Begin Type II observation | 2027-Q1 (after Type I + 2-3 months steady state) | PENDING |

---

**Prepared by:** Control plane automation (jolarca-control)
**Reviewed by:** [PENDING — controller review]
**Next action:** Controller to select auditor and initiate engagement by 2026-10-28.
