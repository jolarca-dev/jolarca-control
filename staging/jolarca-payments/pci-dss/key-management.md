# Cryptographic Key Management — jolarca-payments

## Metadata

| Attribute | Value |
|---|---|
| Document Owner | jolarca-dev organization owner |
| Classification | Confidential |
| Compliance | PCI-DSS 4.0 Req. 3.5, 3.6, ISO 27001 A.8.24 |
| Last Reviewed | 2026-09-26 |
| Next Review | 2026-12-26 |
| Approved By | Gintoras Kazlauskas |

---

## 1. Purpose

This document defines the procedures for managing cryptographic keys used to
protect cardholder data within the `jolarca-dev` marketplace. It covers the
full key lifecycle from generation through destruction.

## 2. Key Hierarchy

```
┌─────────────────────────────────────────┐
│ Master Key (KEK)                        │
│ Stored in cloud KMS (HSM-backed)        │
│ Used to encrypt Data Encryption Keys    │
└─────────────────┬───────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────┐
│ Data Encryption Keys (DEK)              │
│ Encrypted by KEK, stored alongside data │
│ Used to encrypt cardholder data at rest │
└─────────────────┬───────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────┐
│ API Credentials / Tokens                │
│ Used for payment provider authentication│
│ Rotated every 90 days                   │
└─────────────────────────────────────────┘
```

## 3. Key Lifecycle Procedures

### 3.1 Generation

- Keys MUST be generated using a FIPS 140-2 validated random number generator
- Key generation events MUST be logged
- Generated keys MUST be immediately encrypted by the KEK
- Plaintext keys MUST NOT persist in memory longer than necessary

### 3.2 Distribution

- Keys MUST be distributed using the KMS; never via email, chat, or files
- Key material MUST NOT be committed to source control (any repository)
- Key access requires authentication and is logged

### 3.3 Storage

- Active keys MUST be stored in the cloud KMS (HSM-backed)
- Encrypted DEKs MAY be stored alongside encrypted data
- Plaintext keys MUST NOT be stored in configuration files or environment variables
- Key backups MUST be encrypted and stored in a separate location

### 3.4 Rotation

| Key Type | Rotation Period | Procedure |
|---|---|---|
| Master Key (KEK) | Annually | Re-encrypt all DEKs; see [Key Rotation Runbook](../runbooks/key-rotation.md) |
| Data Encryption Keys (DEK) | Annually | Re-encrypt data; old key retained for decryption of existing data |
| API Credentials | Every 90 days | Generate new credential; update services; revoke old credential |
| TLS Certificates | Annually | Reissue from CA; deploy to all endpoints; revoke old certificate |

### 3.5 Compromise Response

When key compromise is suspected:

1. Immediately revoke the compromised key
2. Generate a replacement key
3. Re-encrypt all data protected by the compromised key
4. Investigate the scope of potential exposure
5. Notify affected parties per the incident response runbook
6. Document the incident in `jolarca-compliance`

### 3.6 Destruction

- Keys MUST be securely destroyed when no longer needed
- Destruction MUST use cryptographic erasure (delete the KEK)
- Destruction events MUST be logged
- Confirmation of destruction MUST be retained for audit purposes

## 4. Key Custody

In the solo-operator era, key custody is as follows:

- The organization owner is the sole key custodian
- Key custodian access is authenticated via the cloud provider IAM
- When teams are created, key custody MUST follow dual-control principles:
  no single person should be able to access key material without a second
  person's authorization

## 5. Audit Requirements

Key management activities MUST be auditable:

- All key generation, rotation, and destruction events are logged
- Logs include: timestamp, actor, action, key identifier (not the key itself)
- Logs are retained for at least 12 months (PCI-DSS Req. 10.7)
- Logs are reviewed quarterly

## 6. Related Documents

- [Encryption Policy](../policies/encryption-policy.md)
- [Key Rotation Runbook](../runbooks/key-rotation.md)
- [Incident Response Runbook](../runbooks/incident-response.md)
- [Access Logging](access-logging.md)
