# Payment Data Classification Policy — jolarca-payments

## Metadata

| Attribute | Value |
|---|---|
| Policy Owner | jolarca-dev organization owner |
| Classification | Internal |
| Compliance | PCI-DSS 4.0 Req. 9, GDPR Art. 32, ISO 27001 A.5.12 |
| Last Reviewed | 2026-09-26 |
| Next Review | 2026-12-26 |
| Approved By | Gintoras Kazlauskas |

---

## 1. Purpose

This policy defines the data classification scheme for payment data within the
`jolarca-dev` marketplace. It ensures that cardholder data and other sensitive
payment information are handled, stored, and transmitted in accordance with
their sensitivity level and regulatory requirements.

## 2. Scope

This policy applies to all data created, received, processed, stored, or
transmitted by the marketplace payment systems.

## 3. Classification Levels

### 3.1 Restricted (PCI-DSS Scope)

Data that, if disclosed, would directly result in financial fraud, regulatory
penalty, or card brand sanctions.

**Examples:**
- Primary Account Number (PAN) — full or truncated beyond first 6/last 4
- Card Verification Value (CVV2/CVC2)
- PIN blocks and PIN data
- Full magnetic stripe track data
- Cryptographic keys used to encrypt cardholder data

**Handling Requirements:**
- MUST be encrypted at rest (AES-256 minimum)
- MUST be encrypted in transit (TLS 1.2 minimum)
- MUST NOT be stored in logs, backups, or source control
- Access MUST be logged and auditable
- Retention MUST follow the minimum-necessary principle

### 3.2 Confidential

Data that, if disclosed, would damage the marketplace's security posture,
competitive position, or customer trust.

**Examples:**
- Payment provider API credentials and tokens
- Transaction records with customer PII
- Internal security procedures and CDE architecture details
- Audit reports and SAQ documentation

**Handling Requirements:**
- MUST be encrypted at rest
- MUST be encrypted in transit
- Access restricted to personnel with documented need-to-know
- MUST NOT be committed to public repositories

### 3.3 Internal

Data intended for internal use that does not directly expose cardholder data
or security controls.

**Examples:**
- Payment processing policies and procedures
- Integration specifications (without live credentials)
- Aggregate transaction statistics (non-PII)
- General compliance documentation

**Handling Requirements:**
- MUST NOT contain Restricted or Confidential data
- MAY be stored in internal repositories
- Access restricted to organization members

### 3.4 Public

Data approved for public disclosure.

**Examples:**
- Published compliance attestations (with approval)
- General payment security policies (sanitized)
- Public-facing documentation

**Handling Requirements:**
- MUST be reviewed and approved before publication
- MUST NOT contain any Restricted, Confidential, or Internal data

## 4. Data Flow Classification

All payment data flows MUST be classified at the point of entry and maintain
their classification throughout processing:

1. **Acquisition:** Data received from the customer (card details) is
   immediately classified as Restricted
2. **Processing:** Classification is maintained through authorization,
   capture, and settlement
3. **Storage:** Only tokenized references (non-Restricted) are retained
   long-term; full card data is purged after authorization
4. **Deletion:** Restricted data is securely deleted when no longer needed

## 5. Related Documents

- [Payment Security Policy](payment-security-policy.md)
- [Encryption Policy](encryption-policy.md)
- [PCI-DSS Scope Definition](../pci-dss/scope-definition.md)
- [Tokenization Procedures](../integration/tokenization.md)
