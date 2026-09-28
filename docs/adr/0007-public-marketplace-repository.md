# ADR-0007: Accept Public Visibility for jolarca Marketplace Repository

**Date:** 2026-09-28
**Status:** Accepted
**Deciders:** Gintaras Kazlauskas (organization owner)
**Pre-deployment audit reference:** B6

---

## Context

The `jolarca` repository is the flagship B2C/B2B2C marketplace application
(PCI-DSS payments, KYC/AML, VAT OSS scope). It is licensed AGPL-3.0 and
deployed as a public repository on GitHub under the `jolarca-dev` organization.

The pre-deployment audit (2026-09-28) flagged this as finding B6:

> PCI/KYC-scope codebase is public pre-launch, AGPL-3.0,
> `pull_request_creation_policy: all`, 22 open PRs. If disclosure is
> deliberate (AGPL strategy), record an ADR accepting the attack-surface
> publication — auditors will ask.

The governing policy (`policy/repo-defaults.yml`) records
`max_classification_for_public: "internal"`, and `jolarca.yml` declares
`data_classification: public` with `visibility: public`. This is consistent —
the marketplace code is deliberately public. However, the decision was never
formally recorded as an ADR with an explicit risk acceptance, which is what
auditors expect for a tier-1 PCI-DSS-scoped repository.

## Decision

We accept the public visibility of the `jolarca` repository as a deliberate
business and technical strategy, with the following rationale and constraints.

### Rationale

1. **AGPL-3.0 network-use copyleft.** The license is chosen deliberately to
   require any network-use derivative to also be open-sourced. This is only
   meaningful if the source is publicly visible. A private AGPL-3.0 repository
   would undermine the license's copyleft intent.

2. **Community and ecosystem positioning.** The Baltic-first marketplace
   targets LT/LV/EE sellers and buyers. Public source builds trust with
   regional partners, regulators, and potential contributors who can verify
   the GDPR and payment-security claims independently.

3. **Transparency as a compliance signal.** Public visibility means the
   security controls (CI gates, dependency scanning, secret scanning, signed
   commits) are externally auditable. This is stronger than private
   self-attestation.

### Constraints and compensating controls

Public visibility does NOT mean all content is appropriate for public
consumption. The following constraints apply:

1. **No PII in fixtures or seed data.** `make seed` and test fixtures must
   contain zero realistic personal data. All test users use synthetic
   identities (e.g., `test-user-001@example.com`, fictional addresses).
   Verified by the `check_no_secrets.sh` CI gate and gitleaks.

2. **No production secrets in history.** The repository has never contained
   real credentials. gitleaks scans the full history on every PR (165 commits,
   0 leaks as of 2026-09-28). The `secrets/` directory contains only a
   README explaining the SOPS workflow.

3. **Environment templates use placeholders.** `.env.example` and
   `.env.prod.example` contain `CHANGE_ME` placeholders, never real values.
   CI fails if real patterns are detected.

4. **Private repos hold regulated records.** The compliance, legal, data, and
   infrastructure repositories are PRIVATE (D-01, D-31). RoPA registers,
   vendor assessments, contracts, DPIAs, and network topology are NOT in the
   public repository.

5. **Vulnerability reporting is private.** SECURITY.md directs researchers to
   GitHub's private vulnerability disclosure or `security@jolarca.com`. Public
   issues are not used for security reports.

6. **Issues enabled for DSAR/intake trail.** As of 2026-09-28, `has_issues`
   is enabled to provide a durable, auditable intake trail for GDPR Art. 17
   erasure requests and other compliance tracking (B5).

### Residual risks

- **Attack surface publication.** The full application code, including payment
  integration logic and KYC flows, is readable by anyone. This is accepted as
  a consequence of the AGPL-3.0 strategy. The compensating control is that
  the security gates (dependency scanning, SAST, secret scanning, container
  scanning) are also public and verifiable.

- **Pre-launch disclosure.** The application is not yet live in production.
  Public pre-launch disclosure means potential competitors can see the
  architecture. This is accepted as a trade-off for the AGPL-3.0 positioning.

- **Open PR queue.** At the time of this ADR, 22 PRs are open (mostly
  Dependabot updates). These are being triaged per the pre-deployment audit
  recommendations.

## Consequences

- **Positive:** The AGPL-3.0 license intent is fulfilled. Security controls
  are externally auditable. Regional trust is built through transparency.

- **Negative:** The full attack surface is visible. Competitors can see the
  architecture. The organization must maintain the discipline of keeping
  regulated records in private repositories.

- **Neutral:** The decision is recorded and auditable. Auditors can verify
  that the public visibility was a deliberate choice with compensating
  controls, not an oversight.

## Review

This ADR should be reviewed:
- When the second operator onboards (team creation may change visibility strategy)
- If the repository is ever made private (would require a new ADR)
- Annually as part of the compliance review cycle

---

**References:**
- `repos/jolarca.yml` — visibility: public, data_classification: public
- `policy/repo-defaults.yml` — max_classification_for_public: "internal"
- `docs/drift-findings.md` D-01, D-31 — visibility drift and regulated records
- Pre-deployment audit 2026-09-28, finding B6
- ISO 27001 A.5.9 (inventory), A.5.14 (secure disposal — inverse: publication)
