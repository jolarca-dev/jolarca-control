# Payment Provider Integration — jolarca-payments

## Metadata

| Attribute | Value |
|---|---|
| Document Owner | jolarca-dev organization owner |
| Classification | Internal |
| Compliance | PCI-DSS 4.0 Req. 6, 12.8 |
| Last Reviewed | 2026-09-26 |
| Next Review | 2026-12-26 |
| Approved By | Gintaras Kazlauskas |

---

## 1. Purpose

This document specifies the integration requirements for payment providers
within the `jolarca-dev` marketplace. It defines the security requirements
that any payment provider MUST meet before being connected to the marketplace.

## 2. Provider Requirements

### 2.1 PCI-DSS Compliance

- The payment provider MUST hold a current PCI-DSS Level 1 Attestation of
  Compliance (AOC)
- The provider's AOC MUST be verified before integration and re-verified
  annually
- A copy of the provider's AOC MUST be stored in `jolarca-compliance`

### 2.2 Data Handling

- The provider MUST support tokenization of cardholder data
- The provider MUST NOT return PAN to the marketplace after authorization
- The provider MUST support 3D Secure 2.0 (SCA compliance)
- The provider MUST support webhook notifications for payment events

### 2.3 Security

- All API communication MUST use TLS 1.2 or higher
- API authentication MUST use OAuth 2.0 or API keys with rotation support
- Webhook payloads MUST be signed with HMAC-SHA256
- The provider MUST support IP allowlisting for API access

### 2.4 Operational

- The provider MUST guarantee 99.95% uptime for payment processing
- The provider MUST offer a sandbox environment for testing
- The provider MUST support automated settlement reporting
- The provider MUST have a documented incident response process

## 3. Integration Architecture

### 3.1 Payment Flow

```
1. Customer initiates checkout
2. Marketplace redirects to hosted payment page (or loads Elements SDK)
3. Customer enters card details directly with provider
4. Provider processes payment, returns token to marketplace
5. Marketplace stores token + transaction metadata
6. Provider sends webhook confirmation (authorized/captured/failed)
7. Marketplace updates order status
```

### 3.2 API Integration Points

| Endpoint | Purpose | Authentication |
|---|---|---|
| `/v1/payments` | Create payment intent | API key (Bearer token) |
| `/v1/payments/{id}` | Retrieve payment status | API key (Bearer token) |
| `/v1/payments/{id}/capture` | Capture authorized payment | API key (Bearer token) |
| `/v1/payments/{id}/refund` | Process refund | API key (Bearer token) |
| `/v1/webhooks` | Receive payment events | HMAC-SHA256 signature |

### 3.3 Webhook Events

| Event | Description | Action |
|---|---|---|
| `payment.authorized` | Payment authorized | Reserve inventory |
| `payment.captured` | Payment captured | Fulfill order |
| `payment.failed` | Payment failed | Notify customer |
| `payment.refunded` | Refund processed | Update order status |
| `dispute.created` | Chargeback initiated | Trigger dispute workflow |

## 4. Provider Onboarding Checklist

- [ ] Verify provider PCI-DSS Level 1 AOC
- [ ] Review provider's security documentation
- [ ] Test integration in sandbox environment
- [ ] Verify webhook signature validation
- [ ] Confirm tokenization behavior (no PAN returned)
- [ ] Test error handling and retry logic
- [ ] Verify settlement reporting format
- [ ] Document provider contact for security incidents
- [ ] Store AOC copy in `jolarca-compliance`
- [ ] Complete security review and approval

## 5. Provider Review Schedule

| Activity | Frequency | Responsible |
|---|---|---|
| AOC re-verification | Annual | Org owner |
| Integration security review | Annual | Org owner |
| Webhook reliability review | Quarterly | Org owner |
| Fee and settlement review | Quarterly | Org owner |

## 6. Related Documents

- [Tokenization Procedures](tokenization.md)
- [Webhook Security](webhook-security.md)
- [Payment Security Policy](../policies/payment-security-policy.md)
- [PCI-DSS Scope Definition](../pci-dss/scope-definition.md)
