# Webhook Security — jolarca-payments

## Metadata

| Attribute | Value |
|---|---|
| Document Owner | jolarca-dev organization owner |
| Classification | Internal |
| Compliance | PCI-DSS 4.0 Req. 4, 6, SOC 2 CC6.1 |
| Last Reviewed | 2026-09-26 |
| Next Review | 2026-12-26 |
| Approved By | Gintaras Kazlauskas |

---

## 1. Purpose

This document defines the security requirements for receiving and processing
payment webhooks within the `jolarca-dev` marketplace. Webhooks are the
primary mechanism for receiving asynchronous payment event notifications
from the payment provider.

## 2. Threat Model

| Threat | Impact | Mitigation |
|---|---|---|
| Forged webhook (attacker sends fake event) | Fraudulent order fulfillment | HMAC signature verification |
| Replay attack (captured webhook resent) | Duplicate processing | Idempotency keys + timestamp validation |
| Man-in-the-middle (intercepted webhook) | Data tampering | TLS-only endpoint |
| Denial of service (webhook flood) | Service degradation | Rate limiting + queue-based processing |

## 3. Webhook Endpoint Requirements

### 3.1 Transport Security

- The webhook endpoint MUST use HTTPS (TLS 1.2 minimum)
- The endpoint MUST present a valid, non-expired TLS certificate
- HTTP requests MUST be rejected with 301 redirect to HTTPS

### 3.2 Signature Verification

Every incoming webhook MUST be verified before processing:

1. Extract the signature from the webhook header (e.g., `X-Signature-256`)
2. Compute the expected signature using the webhook secret and the raw
   request body:
   ```
   expected = HMAC-SHA256(webhook_secret, request_body)
   ```
3. Compare the computed signature with the received signature using a
   constant-time comparison function
4. Reject the webhook if signatures do not match

**Critical:** The webhook secret MUST be stored in the cloud secrets manager,
NOT in source code or environment variables.

### 3.3 Timestamp Validation

- Webhooks MUST include a timestamp in the header
- Webhooks older than 5 minutes MUST be rejected (prevents replay attacks)
- Clock skew between the marketplace and provider MUST be monitored

### 3.4 Idempotency

- Each webhook MUST include a unique event ID
- The marketplace MUST track processed event IDs
- Duplicate event IDs MUST be acknowledged (200 OK) but NOT processed again
- Processed event IDs MUST be retained for at least 24 hours

## 4. Webhook Processing

### 4.1 Queue-Based Architecture

```
Payment Provider
    │
    ▼
[Webhook Endpoint — validates signature, timestamps]
    │
    ▼
[Event Queue — decoupled processing]
    │
    ▼
[Event Processor — handles business logic]
    │
    ├── payment.authorized → reserve inventory
    ├── payment.captured   → fulfill order
    ├── payment.failed     → notify customer
    └── dispute.created    → trigger dispute workflow
```

### 4.2 Error Handling

- If processing fails, the webhook MUST be retried (exponential backoff)
- After 3 failed attempts, the event MUST be logged for manual review
- The provider MUST receive a 200 OK to prevent their retry mechanism
  from conflicting with the marketplace's retry logic

## 5. Webhook Secret Rotation

| Activity | Frequency | Procedure |
|---|---|---|
| Secret rotation | Every 90 days | Generate new secret; update provider; update secrets manager |
| Dual-secret period | During rotation | Accept both old and new signatures for 24 hours |
| Old secret revocation | After 24 hours | Remove old secret from provider and secrets manager |

## 6. Monitoring

- Webhook delivery latency MUST be monitored (alert if > 30 seconds)
- Failed signature verifications MUST trigger immediate alerts
- Webhook processing errors MUST be logged and reviewed daily
- Queue depth MUST be monitored (alert if backlog exceeds 100 events)

## 7. Related Documents

- [Provider Integration](provider-integration.md)
- [Payment Security Policy](../policies/payment-security-policy.md)
- [Key Management](../pci-dss/key-management.md)
- [Incident Response Runbook](../runbooks/incident-response.md)
