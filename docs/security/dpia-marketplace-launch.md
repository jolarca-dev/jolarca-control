# DPIA — Data Protection Impact Assessment: Marketplace Launch

**Document ID:** DPIA-MKT-001
**Date:** 2026-09-28
**Status:** Draft — requires DPO sign-off
**Controller:** jolarca-dev organization (Gintaras Kazlauskas, org owner)
**DPO:** [TO BE APPOINTED — see Art37-01 gap in audit/gdpr-checklist.yml]

---

## 1. Scope

This DPIA covers the launch of the jolarca marketplace — a digital goods
marketplace operating in the EU (27 member states, VAT OSS) that processes:

- **KYC/AML identity documents** — identity verification for sellers and
  buyers (potentially Art. 9 special-category if biometric photos on ID
  documents are processed)
- **Payment data** — PCI-DSS-scoped cardholder data via Stripe integration
- **Consent records** — systematic tracking of consent state per purpose
  (marketing, location, AI) with append-only hash chain
- **User profiles** — email, display name, transaction history
- **Location data** — geolocation for VAT OSS and marketplace proximity features

### Systems in scope

| System | Repository | Data categories | Hosting |
|---|---|---|---|
| Product (marketplace) | jolarca | user profiles, listings, transactions | GKE (europe-west1) |
| Consent registry | jolarca-consent | subject_id UUID, IP, user agent, consent state | GKE + bare-metal PostgreSQL |
| Payment processing | jolarca-payments | payment tokens (Stripe), transaction amounts | GKE (europe-west1) |
| Identity verification | jolarca-data | KYC/AML identity documents | GKE (europe-west1) |
| Governance control plane | jolarca-control | repository metadata, Terraform state | operator workstation |

### Systems out of scope

- jolarca-control (this repo) processes no personal data directly. Its
  Terraform state contains repository metadata (names, descriptions, settings)
  but no user data, payment data, or identity documents.
- jolarca-infrastructure — covered by its own DPIA in
  `jolarca-infrastructure/docs/DPIA-template.md`

## 2. Necessity assessment (Art. 35(1))

A DPIA is **required** under Art. 35(1) because the processing involves:

- [x] **Systematic and extensive profiling** — consent registry tracks
  per-purpose consent state with timestamps, IP addresses, and user agents
- [x] **Large-scale processing of special-category data** — KYC/AML identity
  documents may contain biometric data (Art. 9(1))
- [x] **Systematic monitoring** — consent registry's hash chain provides
  immutable audit trail of all consent operations
- [x] **Automated decision-making** — AI feature consent purpose suggests
  automated profiling is planned
- [x] **Data transfers to third countries** — GitHub (US-based processor)
  receives repository metadata; Stripe (US-based) receives payment tokens

**Conclusion:** DPIA is mandatory. The marketplace launch cannot proceed
without DPO sign-off on this assessment.

## 3. Description of the processing (Art. 35(7)(a))

### 3.1 Nature of the processing

The marketplace processes personal data for five distinct purposes:

1. **Contract performance** (Art. 6(1)(b)) — user registration, listings,
   transactions, payment processing
2. **Legal obligation** (Art. 6(1)(c)) — KYC/AML identity verification
   (EU AMLD, national implementations)
3. **Consent** (Art. 6(1)(a)) — marketing communications, location features,
   AI features (each purpose separately consented via jolarca-consent)
4. **Legitimate interests** (Art. 6(1)(f)) — fraud detection, security
   logging, abuse prevention
5. **Tax compliance** (Art. 6(1)(c)) — VAT OSS reporting for digital goods
   sold across EU member states

### 3.2 Scope of the processing

| Data category | Source | Retention | Erasure method |
|---|---|---|---|
| User profile (email, name) | registration | account lifetime + 30d | anonymize (ADR-0003) |
| KYC/AML documents | identity verification | 5 years (AMLD) | secure deletion |
| Payment tokens | Stripe | 7 years (tax) | token revocation |
| Consent records | consent registry | consent lifetime + 5 years | anonymize (ADR-0003) |
| Location data | geolocation API | session only | automatic deletion |
| AI feature data | AI processing | per-purpose consent | anonymize on withdrawal |

### 3.3 Context of the processing

- **EU market** — 27 member states, VAT OSS, GDPR, ePrivacy Directive
- **Multi-jurisdictional** — data subjects in all EU/EEA states
- **Third-country transfers** — GitHub (US, DPF-certified), Stripe (US, DPF-certified)
- **Special-category data** — KYC documents may contain biometric photos
- **Children** — marketplace is 18+ only; age verification at registration

## 4. Assessment of necessity and proportionality (Art. 35(7)(b))

### 4.1 Lawful basis assessment

Each processing activity has a documented lawful basis (see §3.1). The
controller has determined that:

- Consent is **not** bundled with T&C acceptance (Art. 7(4))
- Each consent purpose has a separate toggle (granularity)
- Withdrawal is no more than one click from any screen
- KYC processing is required by EU AMLD — not optional

### 4.2 Data minimisation

- User profiles contain only what is necessary for marketplace operation
- KYC documents are collected only when legally required (threshold-based)
- Location data is session-scoped, not stored persistently
- AI feature data requires separate, explicit consent

### 4.3 Retention

Retention periods are defined per data category (see §3.2). The consent
registry enforces TTL per purpose — records past their retention date are
anonymized (not deleted, per ADR-0003's anonymize-don't-delete principle).

**Gap:** TTL enforcement is not yet implemented as code (Art5-03 in
audit/gdpr-checklist.yml). Retention is currently a policy document, not a
technical control.

## 5. Risks to rights and freedoms (Art. 35(7)(c))

| Risk ID | Risk description | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R-01 | KYC document breach exposes identity documents (passport, ID card) | Medium | High | Encryption at rest (CMEK), access logging, PCI-DSS scope controls |
| R-02 | Consent record tampering — hash chain compromise | Low | High | Append-only storage, hash chain verification, breach runbook |
| R-03 | Payment token exposure via Stripe webhook | Low | High | Webhook signature verification, tokenization, PCI-DSS controls |
| R-04 | Profiling without valid consent — AI features enabled without granular consent | Medium | Medium | Separate consent purpose, consent registry enforces granularity |
| R-05 | Third-country transfer — GitHub receives repository metadata | Certain | Low | EU-US Data Privacy Framework, GitHub DPA held in jolarca-legal |
| R-06 | DSAR not fulfilled within 30 days — manual process at scale | High | Medium | DSAR pipeline needs cross-service coordination (Art12-01 gap) |
| R-07 | Consent UX is coercive — dark patterns in consent collection | Medium | High | Independent UX review required (Art7-01 gap) |

## 6. Measures to address the risks (Art. 35(7)(d))

### Technical measures

- Encryption at rest (CMEK) for all data stores (GCP, PostgreSQL)
- Encryption in transit (TLS 1.3) for all API endpoints
- Secret scanning (gitleaks + GitHub push protection) prevents credential leaks
- Append-only consent registry with hash chain integrity verification
- PCI-DSS-compliant payment processing via Stripe (tokenization)
- Access logging on all systems processing personal data

### Organizational measures

- DPO appointment (Art37-01 — gap, requires decision)
- DPIA sign-off before marketplace launch (this document)
- Breach notification procedure (72h to supervisory authority, Art. 33)
- Quarterly access reviews (jolarca-identity)
- Annual DPIA review (Art. 35(11))

### Remaining gaps (must be closed before launch)

1. **DPO appointment** (Art37-01) — marketplace + KYC/AML scope likely
   requires a DPO; decision not yet documented
2. **DSAR pipeline** (Art12-01) — cross-service DSAR coordination not
   implemented; manual handling will breach 30-day deadline
3. **Consent UX review** (Art7-01) — no independent review for dark patterns
4. **TTL enforcement** (Art5-03) — retention not enforced as code
5. **Subprocessor register** (Art28-03) — consent-data subprocessors not
   fully enumerated

## 7. DPO opinion (Art. 35(2))

**[PENDING — DPO not yet appointed]**

The DPO must review this assessment and provide a written opinion on whether
the processing is lawful, necessary, and proportionate. The DPO's opinion
must be documented and retained as evidence of compliance (Art. 30).

## 8. Sign-off

| Role | Name | Date | Signature |
|---|---|---|---|
| Controller (org owner) | Gintaras Kazlauskas | 2026-09-28 | [PENDING] |
| DPO | [TO BE APPOINTED] | — | [PENDING] |

**This DPIA must be signed before the marketplace launches.** The marketplace
cannot lawfully process KYC/AML data, payment data, or consent records without
DPO sign-off on this assessment.

## 9. Review schedule

- **Annual review** (Art. 35(11)) — at minimum, or when the nature/scope/
  purposes of processing change
- **Post-incident review** — after any personal data breach involving the
  systems in scope
- **Post-launch review** — within 90 days of marketplace launch, assess
  whether the risks materialised and whether additional measures are needed

---

**Cross-references:**
- audit/gdpr-checklist.yml — Art35 controls
- docs/adr/0003-consent-registry.md — anonymize-don't-delete principle
- jolarca-compliance — RoPA/ERoPA records, DPIA evidence
- jolarca-legal — DPAs, privacy notices, legal bases
- jolarca-consent — consent registry architecture and threat model
