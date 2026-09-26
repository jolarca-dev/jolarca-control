# PCI-DSS Self-Assessment Questionnaire — jolarca-payments

## Metadata

| Attribute | Value |
|---|---|
| Document Owner | jolarca-dev organization owner |
| Classification | Confidential |
| Compliance | PCI-DSS 4.0 Req. 12.10 |
| Last Reviewed | 2026-09-26 |
| Next Review | 2026-12-26 |
| Approved By | Gintaras Kazlauskas |

---

## 1. Purpose

This document provides guidance on completing the PCI-DSS Self-Assessment
Questionnaire (SAQ) for the `jolarca-dev` marketplace. It identifies the
applicable SAQ type, maps requirements to implemented controls, and documents
the evidence location for each requirement.

## 2. SAQ Type Determination

### 2.1 Applicable SAQ Type

Based on the marketplace's payment processing model:

**SAQ Type: SAQ A**

Criteria met:
- Cardholder data is processed only via fully outsourced, isolated, and
  PCI-validated third-party services
- The marketplace does not store, process, or transmit cardholder data on
  its own systems
- Paper and/or electronic cardholder data is not received
- The marketplace's only interaction with cardholder data is through:
  - A payment form embedded on the website that posts directly to the
    payment provider
  - A client-side SDK (e.g., payment elements) that sends card data
    directly to the payment provider

### 2.2 Why Not Other SAQ Types

| SAQ Type | Why Not Applicable |
|---|---|
| SAQ A-EP | The marketplace does not control the payment page; it uses the provider's hosted solution |
| SAQ B | No standalone imprint machines or card-present terminals |
| SAQ C | No payment application systems connected to the internet |
| SAQ D | Scope is fully reduced via tokenization and hosted pages |

## 3. Requirement Mapping

### 3.1 SAQ A Requirements

| Req # | Requirement | Implemented Control | Evidence Location |
|---|---|---|---|
| 1 | Install and maintain network security controls | Payment provider manages CDE network | Provider attestation |
| 2 | Apply secure configurations | Payment provider manages system hardening | Provider attestation |
| 3 | Protect stored account data | No card data stored; tokens only | Tokenization spec |
| 4 | Protect cardholder data with strong cryptography | TLS for all payment API calls | Encryption policy |
| 5 | Protect systems from malware | Marketplace systems scanned; provider manages CDE | Security scanning |
| 6 | Develop and maintain secure systems | Code review + dependency scanning | CI/CD pipeline |
| 7 | Restrict access by business need to know | Solo operator; access documented | CODEOWNERS |
| 8 | Identify users and authenticate access | Unique account + MFA (when enabled) | Org settings |
| 9 | Restrict physical access | Cloud provider manages physical security | Provider attestation |
| 10 | Log and monitor access | Access logging enabled | Access logging doc |
| 11 | Test security regularly | Vulnerability scanning + Dependabot | CI/CD pipeline |
| 12 | Support information security with policies | This documentation set | policies/ |

## 4. Annual Completion Schedule

| Activity | Frequency | Responsible | Next Due |
|---|---|---|---|
| SAQ completion | Annual | Org owner | 2026-12-31 |
| Attestation of Compliance (AOC) | Annual | Org owner | 2026-12-31 |
| ASV scan (if applicable) | Quarterly | Payment provider | Ongoing |
| Scope validation | Annual | Org owner | 2026-12-26 |

## 5. Evidence Collection

Evidence for SAQ completion is stored in
[`jolarca-compliance`](https://github.com/jolarca-dev/jolarca-compliance):

- Provider Attestations of Compliance (AOC)
- Network scan reports
- Policy review records
- Access review records
- Vulnerability scan results

## 6. Related Documents

- [Scope Definition](scope-definition.md)
- [Network Segmentation Controls](network-segmentation.md)
- [Payment Security Policy](../policies/payment-security-policy.md)
- [Access Logging](access-logging.md)
