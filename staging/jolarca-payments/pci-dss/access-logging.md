# Access Logging and Monitoring — jolarca-payments

## Metadata

| Attribute | Value |
|---|---|
| Document Owner | jolarca-dev organization owner |
| Classification | Internal |
| Compliance | PCI-DSS 4.0 Req. 10, SOC 2 CC7.1–CC7.3, ISO 27001 A.8.15 |
| Last Reviewed | 2026-09-26 |
| Next Review | 2026-12-26 |
| Approved By | Gintoras Kazlauskas |

---

## 1. Purpose

This document defines the access logging and monitoring requirements for the
cardholder-data environment (CDE) within the `jolarca-dev` marketplace. It
ensures that all access to cardholder data and CDE systems is logged,
monitored, and auditable.

## 2. Logging Requirements

### 2.1 What to Log

All access to cardholder data MUST be logged, including:

| Event Type | Log Content |
|---|---|
| User login/logout | User ID, timestamp, source IP, success/failure |
| Access to cardholder data | User ID, timestamp, data accessed, action taken |
| Administrative actions | User ID, timestamp, action, target system |
| Authentication failures | User ID, timestamp, source IP, reason |
| Key management operations | Actor, timestamp, action, key identifier |
| Configuration changes | Actor, timestamp, change details, approval reference |
| API access to CDE | Service account, timestamp, endpoint, result |

### 2.2 Log Format

Logs MUST include:

- **Timestamp:** UTC, ISO 8601 format, millisecond precision
- **Actor:** Unique user or service account identifier
- **Action:** What was attempted or performed
- **Resource:** What system or data was accessed
- **Result:** Success or failure (with failure reason)
- **Source:** IP address or network origin of the request

### 2.3 What NOT to Log

Logs MUST NOT contain:

- Primary Account Numbers (PAN) — full or partial
- Card Verification Values (CVV2/CVC2)
- PINs or PIN blocks
- Full authentication credentials
- Session tokens or API keys

## 3. Log Storage

### 3.1 Retention

- Logs MUST be retained for at least 12 months (PCI-DSS Req. 10.7)
- At least the most recent 3 months MUST be immediately available for analysis
- Older logs MAY be archived but MUST be recoverable within 24 hours

### 3.2 Protection

- Logs MUST be stored in a system that is:
  - Write-once or append-only (tamper-evident)
  - Accessible only to authorized personnel
  - Separate from the systems generating the logs
- Log integrity MUST be verified daily (hash check or equivalent)

## 4. Monitoring

### 4.1 Real-Time Monitoring

The following events MUST trigger immediate alerts:

- Failed authentication attempts (3+ in 10 minutes)
- Access to cardholder data outside business hours
- Access from unrecognized IP addresses
- Privilege escalation attempts
- Log tampering or deletion attempts
- Configuration changes to CDE systems

### 4.2 Daily Review

The following MUST be reviewed daily:

- Security events and alerts
- Failed login attempts
- Access to critical systems
- Anomalous activity patterns

### 4.3 Quarterly Review

The following MUST be reviewed quarterly:

- Access logs for all CDE systems
- Administrative access patterns
- Service account activity
- Log retention compliance
- Segmentation control effectiveness

## 5. Alert Response

| Alert Type | Response Time | Escalation |
|---|---|---|
| CDE unauthorized access | Immediate | Incident response runbook |
| Credential compromise | Immediate | Key rotation + incident response |
| Log tampering | Immediate | Full investigation |
| Anomalous access pattern | Within 1 hour | Review and investigate |
| Failed authentication spike | Within 30 minutes | Review and block if needed |

## 6. Related Documents

- [Payment Security Policy](../policies/payment-security-policy.md)
- [Key Management](key-management.md)
- [Incident Response Runbook](../runbooks/incident-response.md)
- [Scope Definition](scope-definition.md)
