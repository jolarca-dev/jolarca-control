# Encryption Policy — jolarca-payments

## Metadata

| Attribute | Value |
|---|---|
| Policy Owner | jolarca-dev organization owner |
| Classification | Internal |
| Compliance | PCI-DSS 4.0 Req. 3, 4, GDPR Art. 32, ISO 27001 A.8.24 |
| Last Reviewed | 2026-09-26 |
| Next Review | 2026-12-26 |
| Approved By | Gintoras Kazlauskas |

---

## 1. Purpose

This policy defines the encryption requirements for protecting cardholder data
and other sensitive payment information within the `jolarca-dev` marketplace.
It covers encryption at rest, in transit, and the cryptographic key management
practices that support both.

## 2. Scope

This policy applies to all systems, processes, and data within the cardholder-
data environment (CDE) of the marketplace.

## 3. Encryption at Rest

### 3.1 Requirements

- All cardholder data stored in databases, file systems, or backups MUST be
  encrypted using AES-256 or equivalent (PCI-DSS Req. 3.4)
- Encryption keys MUST be stored separately from the encrypted data
- Full disk encryption MUST be used for systems storing cardholder data

### 3.2 Approved Algorithms

| Use Case | Algorithm | Key Length |
|---|---|---|
| Data at rest | AES-256 (GCM or CBC with HMAC) | 256 bits |
| Key encryption | AES-256 | 256 bits |
| Hashing (passwords) | bcrypt or Argon2id | N/A |
| Digital signatures | RSA-PSS or Ed25519 | 2048+ bits / 256 bits |

### 3.3 Prohibited

- DES, 3DES, RC4, and other deprecated algorithms MUST NOT be used
- Custom cryptographic implementations MUST NOT be used
- Hardcoded keys or initialization vectors are prohibited

## 4. Encryption in Transit

### 4.1 Requirements

- All transmission of cardholder data over open, public networks MUST use
  strong encryption (PCI-DSS Req. 4.1)
- TLS 1.2 is the minimum acceptable version; TLS 1.3 is preferred
- All certificates MUST be valid, not expired, and issued by a trusted CA

### 4.2 TLS Configuration

| Parameter | Minimum Requirement |
|---|---|
| Protocol version | TLS 1.2 (TLS 1.3 preferred) |
| Cipher suites | AEAD ciphers only (AES-GCM, ChaCha20-Poly1305) |
| Key exchange | ECDHE or DHE (forward secrecy required) |
| Certificate | RSA 2048+ or ECDSA P-256+ |
| HSTS | Enabled with max-age >= 31536000 |

### 4.3 Internal Network Encryption

- Even within the CDE, all inter-service communication MUST use TLS
- Service mesh or mTLS is recommended for microservice architectures

## 5. Key Management

Cryptographic key management MUST follow the procedures defined in
[`pci-dss/key-management.md`](../pci-dss/key-management.md). Key principles:

- Keys MUST be generated using a FIPS 140-2 validated random number generator
- Keys MUST be stored in a dedicated key management system (KMS)
- Key access MUST be logged and auditable
- Keys MUST be rotated at least annually
- Compromised keys MUST be revoked and replaced immediately

## 6. Key Rotation Schedule

| Key Type | Rotation Frequency | Method |
|---|---|---|
| Data encryption keys (DEK) | Annually or on compromise | Re-encrypt data with new key |
| Key encryption keys (KEK) | Annually or on compromise | Re-encrypt DEKs |
| API credentials | Every 90 days | Provider-specific rotation |
| TLS certificates | Annually or on compromise | Reissue and redeploy |

## 7. Related Documents

- [Key Management Procedures](../pci-dss/key-management.md)
- [Key Rotation Runbook](../runbooks/key-rotation.md)
- [Payment Security Policy](payment-security-policy.md)
- [Data Classification Policy](data-classification.md)
