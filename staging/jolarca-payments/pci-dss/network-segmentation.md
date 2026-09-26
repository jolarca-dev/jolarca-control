# Network Segmentation Controls — jolarca-payments

## Metadata

| Attribute | Value |
|---|---|
| Document Owner | jolarca-dev organization owner |
| Classification | Internal |
| Compliance | PCI-DSS 4.0 Req. 1, ISO 27001 A.8.20 |
| Last Reviewed | 2026-09-26 |
| Next Review | 2026-12-26 |
| Approved By | Gintaras Kazlauskas |

---

## 1. Purpose

This document defines the network segmentation controls that isolate the
cardholder-data environment (CDE) from non-CDE systems within the `jolarca-dev`
marketplace. Segmentation reduces the scope of PCI-DSS assessment and limits
the blast radius of a potential breach.

## 2. Segmentation Architecture

### 2.1 Network Zones

```
┌─────────────────────────────────────────────────────────────────┐
│ Internet                                                        │
│     │                                                           │
│     ▼                                                           │
│ ┌──────────────┐                                                │
│ │ WAF / CDN    │ ← DDoS protection, rate limiting               │
│ └──────┬───────┘                                                │
│        │                                                        │
│        ▼                                                        │
│ ┌──────────────┐    ┌──────────────────────────────────────┐    │
│ │ API Gateway  │───▶│ Payment Provider (Hosted Page/SDK)   │    │
│ │ (non-CDE)    │    │ (PCI Level 1 certified)              │    │
│ └──────┬───────┘    └──────────────────────────────────────┘    │
│        │                                                        │
│        │ (token only — no PAN)                                  │
│        ▼                                                        │
│ ┌──────────────────────────────────────────────────────────┐    │
│ │ CDE Zone                                                 │    │
│ │  ┌────────────────┐    ┌────────────────┐                │    │
│ │  │ Payment Svc    │───▶│ Token DB       │                │    │
│ │  │ (processes     │    │ (stores tokens │                │    │
│ │  │  tokens)       │    │  only)         │                │    │
│ │  └────────────────┘    └────────────────┘                │    │
│ │         │                                                 │    │
│ │         ▼                                                 │    │
│ │  ┌────────────────┐                                       │    │
│ │  │ Audit Log      │ ← Append-only, no PAN                │    │
│ │  └────────────────┘                                       │    │
│ └──────────────────────────────────────────────────────────┘    │
│                                                                 │
│ ┌──────────────────────────────────────────────────────────┐    │
│ │ Non-CDE Zone                                             │    │
│ │  Marketplace API · Content · Analytics · Admin           │    │
│ └──────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 Traffic Rules

| Source | Destination | Protocol | Allowed | Justification |
|---|---|---|---|---|
| Internet | WAF/CDN | HTTPS (443) | Yes | Customer payment traffic |
| WAF/CDN | API Gateway | HTTPS (443) | Yes | Validated requests |
| API Gateway | Payment Provider | HTTPS (443) | Yes | Token exchange |
| API Gateway | CDE Zone | HTTPS (443) | Yes | Token processing |
| CDE Zone | Token DB | TLS (5432) | Yes | Token storage |
| CDE Zone | Audit Log | TLS (5044) | Yes | Compliance logging |
| Non-CDE Zone | CDE Zone | Any | No | Segmented |
| CDE Zone | Internet | Any | No | No outbound from CDE |
| Internet | Non-CDE Zone | HTTPS (443) | Yes | General marketplace |

## 3. Segmentation Validation

Segmentation controls MUST be validated:

- At least annually
- After any network architecture change
- After any firewall rule change
- Before each SAQ submission

Validation includes:

1. Review of all firewall rules against the traffic rules table above
2. Penetration testing to verify CDE isolation
3. Network scan to confirm no unauthorized paths to CDE
4. Documentation of results in `jolarca-compliance`

## 4. Firewall Management

- All firewall rules MUST be reviewed and approved before implementation
- Rule changes MUST follow the change control process (PCI-DSS Req. 6.3)
- Unused or redundant rules MUST be removed during each review cycle
- All rule changes MUST be logged with business justification

## 5. Related Documents

- [Scope Definition](scope-definition.md)
- [Payment Security Policy](../policies/payment-security-policy.md)
- [Access Logging](access-logging.md)
