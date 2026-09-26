# Key Rotation Runbook — jolarca-payments

## Metadata

| Attribute | Value |
|---|---|
| Document Owner | jolarca-dev organization owner |
| Classification | Confidential |
| Compliance | PCI-DSS 4.0 Req. 3.5, 3.6 |
| Last Reviewed | 2026-09-26 |
| Next Review | 2026-12-26 |
| Approved By | Gintaras Kazlauskas |

---

## 1. Purpose

This runbook provides step-by-step procedures for rotating cryptographic keys
and API credentials within the `jolarca-dev` marketplace payment system.
Regular key rotation is a PCI-DSS requirement (Req. 3.5) and a critical
control for limiting the impact of key compromise.

## 2. Rotation Schedule

| Key Type | Frequency | Procedure Reference |
|---|---|---|
| Payment provider API credentials | Every 90 days | Section 3 |
| Webhook signing secrets | Every 90 days | Section 4 |
| Data Encryption Keys (DEK) | Annually | Section 5 |
| Master Key (KEK) | Annually | Section 6 |
| TLS certificates | Annually | Section 7 |

## 3. API Credential Rotation

### Pre-Rotation Checklist

- [ ] Confirm maintenance window (if needed)
- [ ] Verify new credentials are generated in the provider dashboard
- [ ] Confirm rollback plan is documented
- [ ] Notify monitoring systems of expected credential change

### Rotation Steps

1. **Generate new API credentials** in the payment provider dashboard
2. **Store new credentials** in the cloud secrets manager
3. **Deploy updated configuration** to payment processing service
   - The service should support both old and new credentials during transition
4. **Verify** that payments process successfully with new credentials
5. **Revoke old credentials** in the payment provider dashboard
6. **Remove old credentials** from the secrets manager
7. **Verify** that no services are using the old credentials
8. **Document** the rotation in the key management log

### Rollback

If new credentials fail:

1. Immediately revert to old credentials (if not yet revoked)
2. If already revoked, generate a fresh set of credentials
3. Investigate the failure before retrying

## 4. Webhook Secret Rotation

### Rotation Steps

1. **Generate new webhook secret** in the payment provider dashboard
2. **Update the secrets manager** with the new secret
3. **Deploy updated verification code** — accept BOTH old and new signatures
4. **Wait 24 hours** (dual-secret period) to ensure all in-flight webhooks
   are processed with the new secret
5. **Remove old secret** from the provider dashboard and secrets manager
6. **Update verification code** to accept only the new signature
7. **Document** the rotation in the key management log

## 5. Data Encryption Key (DEK) Rotation

### Rotation Steps

1. **Generate new DEK** using the cloud KMS
2. **Configure the application** to use the new DEK for new writes
3. **Re-encrypt existing data** with the new DEK (background job)
4. **Verify** that all data is accessible with the new DEK
5. **Mark old DEK** as "pending destruction" (retain for 30 days)
6. **After 30 days**, destroy the old DEK (cryptographic erasure)
7. **Document** the rotation in the key management log

### Important

- Old DEKs MUST be retained until all data encrypted with them is
  re-encrypted or deleted
- Old DEKs MUST NOT be used for new encryption operations
- The KMS MUST maintain an audit trail of all key operations

## 6. Master Key (KEK) Rotation

### Rotation Steps

1. **Generate new KEK** in the cloud KMS (HSM-backed)
2. **Re-encrypt all DEKs** with the new KEK
   - This is a batch operation that decrypts each DEK with the old KEK
     and re-encrypts with the new KEK
3. **Verify** that all DEKs are accessible with the new KEK
4. **Update KMS configuration** to use the new KEK as the primary
5. **Mark old KEK** as "pending destruction" (retain for 90 days)
6. **After 90 days**, destroy the old KEK
7. **Document** the rotation in the key management log

### Important

- KEK rotation MUST NOT cause downtime — the KMS supports multiple active KEKs
- All DEKs MUST be re-encrypted before the old KEK is destroyed
- This operation MUST be performed during a maintenance window with monitoring

## 7. TLS Certificate Rotation

### Rotation Steps

1. **Request new certificate** from the CA (or via ACME/Let's Encrypt)
2. **Deploy new certificate** to all endpoints (WAF, API gateway, services)
3. **Verify** that all clients can connect with the new certificate
4. **Monitor** for any TLS errors in logs
5. **Revoke old certificate** after confirming new certificate is operational
6. **Document** the rotation in the key management log

## 8. Emergency Key Rotation

If key compromise is suspected:

1. **Immediately revoke** the compromised key
2. **Generate replacement key** following the relevant procedure above
3. **Deploy replacement** immediately (skip the dual-secret period)
4. **Investigate** the scope of potential exposure
5. **Follow the incident response runbook** for notification requirements
6. **Document** the emergency rotation and investigation

## 9. Related Documents

- [Key Management Procedures](../pci-dss/key-management.md)
- [Encryption Policy](../policies/encryption-policy.md)
- [Incident Response Runbook](incident-response.md)
- [Webhook Security](../integration/webhook-security.md)
