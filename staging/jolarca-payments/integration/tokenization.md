# Tokenization Procedures — jolarca-payments

## Metadata

| Attribute | Value |
|---|---|
| Document Owner | jolarca-dev organization owner |
| Classification | Internal |
| Compliance | PCI-DSS 4.0 Req. 3, 3.4, 3.5 |
| Last Reviewed | 2026-09-26 |
| Next Review | 2026-12-26 |
| Approved By | Gintaras Kazlauskas |

---

## 1. Purpose

This document defines the tokenization procedures for handling payment data
within the `jolarca-dev` marketplace. Tokenization is the primary control
that reduces PCI-DSS scope by ensuring that cardholder data never enters the
marketplace infrastructure.

## 2. Tokenization Model

### 2.1 How It Works

1. Customer enters card details on the payment provider's hosted page or
   client-side SDK
2. The payment provider validates the card and returns a **payment token**
   (a random, non-mathematical reference) to the marketplace
3. The marketplace stores the token and uses it for subsequent operations
   (capture, refund, recurring payments)
4. The token has no intrinsic value and cannot be reverse-engineered to
   reveal the original card number

### 2.2 Token Properties

| Property | Description |
|---|---|
| Format | Alphanumeric string (provider-specific) |
| Scope | Single-use or multi-use (per provider configuration) |
| Reversibility | Not reversible — token cannot reveal PAN |
| Expiry | Tokens may expire per provider policy |
| Storage | Safe to store in marketplace database |

## 3. What the Marketplace Stores

| Data Element | Stored? | Format |
|---|---|---|
| Payment token | Yes | Provider-issued token string |
| Card brand | Yes | Visa, Mastercard, etc. |
| Last 4 digits | Yes | For display purposes (first 6 / last 4 allowed) |
| Expiry month/year | Yes | For display and recurring payment validation |
| PAN (full) | **NO** | Never stored |
| CVV2/CVC2 | **NO** | Never stored after authorization |
| Track data | **NO** | Never stored |

## 4. Token Usage

### 4.1 Authorized Operations

The marketplace MAY use tokens to:

- Capture an authorized payment
- Process a refund against a captured payment
- Initiate a recurring payment (subscription)
- Retrieve payment status from the provider

### 4.2 Prohibited Operations

The marketplace MUST NOT:

- Attempt to detokenize (retrieve PAN from token)
- Store tokens in plaintext in logs
- Transmit tokens over unencrypted channels
- Share tokens with unauthorized third parties
- Use tokens for any purpose other than the original transaction intent

## 5. Token Lifecycle

```
1. CREATE — Payment provider issues token during authorization
2. STORE  — Marketplace saves token in payment record
3. USE    — Token used for capture/refund/status checks
4. EXPIRE — Token expires per provider policy (or on card replacement)
5. DELETE — Token reference removed when no longer needed (retention policy)
```

## 6. Token Security

- Tokens MUST be stored in encrypted database fields
- Access to token storage MUST be logged
- Token database MUST be included in CDE scope for PCI-DSS assessment
- Token compromise (if suspected) MUST trigger the incident response runbook
- Token rotation is not required (tokens are non-reversible by design)

## 7. Related Documents

- [Provider Integration](provider-integration.md)
- [Payment Security Policy](../policies/payment-security-policy.md)
- [Data Classification Policy](../policies/data-classification.md)
- [PCI-DSS Scope Definition](../pci-dss/scope-definition.md)
- [Encryption Policy](../policies/encryption-policy.md)
