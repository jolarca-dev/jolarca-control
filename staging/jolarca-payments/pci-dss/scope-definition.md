# PCI-DSS Scope Definition — jolarca-payments

## Metadata

| Attribute | Value |
|---|---|
| Document Owner | jolarca-dev organization owner |
| Classification | Internal |
| Compliance | PCI-DSS 4.0 Req. 1, 2, 6, 12 |
| Last Reviewed | 2026-09-26 |
| Next Review | 2026-12-26 |
| Approved By | Gintaras Kazlauskas |

---

## 1. Purpose

This document defines the scope of the cardholder-data environment (CDE) for
the `jolarca-dev` marketplace. It identifies the systems, networks, people,
and processes that are within PCI-DSS scope, and those that are explicitly
out of scope.

## 2. CDE Boundary

### 2.1 In Scope

The following are within the CDE boundary:

**Systems:**
- Payment processing application servers
- Database servers storing tokenized payment references
- API gateways handling payment requests
- Load balancers terminating payment traffic
- Logging and monitoring systems that receive payment event logs

**Networks:**
- The payment processing subnet(s)
- Network segments between payment components
- Firewall rules governing CDE access

**People:**
- The organization owner (sole operator in the current era)
- Any personnel granted access to CDE systems (documented in access register)
- Third-party payment provider support personnel with CDE access

**Processes:**
- Payment authorization and capture
- Refund and chargeback processing
- Tokenization and detokenization
- Payment data encryption and key management
- Payment-related logging and monitoring

### 2.2 Out of Scope

The following are explicitly out of scope:

- General marketplace application servers (non-payment processing)
- Content delivery networks and static asset hosting
- Marketing and analytics systems (unless they receive CDE data)
- Development and staging environments that do not process live card data
- Corporate IT systems (unless used for CDE administration)
- Mission-platform systems (`jol-*` repos and infrastructure — ADR-0004)

### 2.3 Connected but Segmented

The following systems connect to the CDE but are segmented:

| System | Connection Type | Segmentation Control |
|---|---|---|
| General marketplace API | REST API calls | Network ACL + service account |
| Customer notification service | Event queue | Queue-level ACL, no PAN in events |
| Accounting system | Settlement reports | Batch transfer, aggregated data only |
| Monitoring platform | Log forwarding | Log scrubbing (no PAN in logs) |

## 3. Data Flow Diagram

```
Customer Browser
    │
    ▼
[Payment Form — Hosted Payment Page or Elements SDK]
    │ (PAN goes directly to payment provider)
    ▼
[Payment Provider API]
    │ (token returned)
    ▼
[Marketplace API — receives token, NOT PAN]
    │
    ▼
[Payment Processing Service — CDE]
    │ (uses token to authorize/capture)
    ▼
[Database — stores token + transaction record]
    │
    ▼
[Settlement + Reporting — aggregated, no PAN]
```

**Critical:** The PAN never touches the marketplace infrastructure. The payment
provider's hosted payment page or client-side SDK handles card data directly,
and only a non-sensitive token is returned to the marketplace.

## 4. Scope Reduction Controls

The marketplace reduces PCI-DSS scope through:

1. **Tokenization:** Card data is tokenized by the payment provider before
   reaching marketplace infrastructure
2. **Hosted Payment Page:** Customer card entry occurs on the provider's
   PCI-compliant infrastructure
3. **Network Segmentation:** CDE components are isolated from general
   marketplace infrastructure
4. **Data Minimization:** Only tokens and transaction metadata are stored;
   no PAN, CVV, or track data is retained

## 5. Scope Validation

Scope MUST be reviewed and validated:

- At least annually
- When significant changes are made to the payment architecture
- When new systems are connected to the CDE
- When network configurations change

## 6. Related Documents

- [Network Segmentation Controls](network-segmentation.md)
- [Self-Assessment Questionnaire](self-assessment-questionnaire.md)
- [Payment Security Policy](../policies/payment-security-policy.md)
- [Tokenization Procedures](../integration/tokenization.md)
