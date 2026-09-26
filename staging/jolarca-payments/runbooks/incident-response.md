# Payment Incident Response Runbook — jolarca-payments

## Metadata

| Attribute | Value |
|---|---|
| Document Owner | jolarca-dev organization owner |
| Classification | Confidential |
| Compliance | PCI-DSS 4.0 Req. 12.10, SOC 2 CC7.3–CC7.5 |
| Last Reviewed | 2026-09-26 |
| Next Review | 2026-12-26 |
| Approved By | Gintaras Kazlauskas |

---

## 1. Purpose

This runbook defines the incident response procedures for payment security
incidents within the `jolarca-dev` marketplace. It covers detection,
containment, eradication, recovery, and post-incident review.

## 2. Incident Classification

| Severity | Definition | Response Time | Examples |
|---|---|---|---|
| P1 — Critical | Cardholder data breach confirmed or highly likely | Immediate | PAN in logs, CDE compromise, token DB breach |
| P2 — High | Payment system compromise suspected | Within 1 hour | Unauthorized API access, webhook forgery, key leak |
| P3 — Medium | Security control failure | Within 4 hours | TLS certificate expiry, logging gap, access anomaly |
| P4 — Low | Policy violation or procedural gap | Next business day | Documentation inaccuracy, minor configuration drift |

## 3. Response Procedures

### 3.1 P1 — Cardholder Data Breach

**Immediate Actions (0–15 minutes):**

1. Confirm the incident — verify that cardholder data may have been exposed
2. Activate incident response: notify the organization owner immediately
3. Isolate affected systems — revoke API keys, disable compromised endpoints
4. Preserve evidence — do NOT delete logs or restart affected systems

**Containment (15–60 minutes):**

5. Rotate all payment provider API credentials
6. Rotate all cryptographic keys in the CDE
7. Block suspicious IP addresses at the WAF/firewall level
8. Enable enhanced logging on all CDE systems

**Notification (1–24 hours):**

9. Assess scope: how many cardholders may be affected?
10. Notify payment provider's fraud/security team
11. Notify card brands per their breach notification requirements
12. Notify acquiring bank
13. Assess GDPR notification requirements (Art. 33 — 72-hour window)
14. Engage legal counsel

**Recovery (24–72 hours):**

15. Deploy patched/fixed systems
16. Re-enable payment processing with new credentials
17. Verify segmentation controls are intact
18. Confirm logging and monitoring are operational

**Post-Incident (1–2 weeks):**

19. Conduct post-incident review
20. Document lessons learned in `jolarca-compliance`
21. Update policies and procedures
22. Schedule follow-up security assessment

### 3.2 P2 — Suspected Payment System Compromise

**Immediate Actions:**

1. Investigate the alert — review logs, access patterns, API calls
2. If compromise confirmed, escalate to P1
3. If inconclusive, isolate the affected component and monitor

**Containment:**

4. Rotate credentials for the affected system
5. Review recent changes that may have introduced the vulnerability
6. Enable enhanced monitoring

**Resolution:**

7. Patch or remediate the vulnerability
8. Verify the fix in staging before deploying to production
9. Document the incident and resolution

### 3.3 P3 — Security Control Failure

**Response:**

1. Identify the failed control (e.g., expired certificate, logging gap)
2. Assess risk: is cardholder data exposed during the failure?
3. Remediate the control (renew certificate, fix logging configuration)
4. Review logs for the period during which the control was failed
5. Document the incident and remediation

## 4. Communication Plan

| Audience | When | Method |
|---|---|---|
| Organization owner | Immediately for P1/P2 | Direct notification |
| Payment provider | P1 — confirmed breach | Provider's security contact |
| Card brands | P1 — per brand requirements | Brand-specific breach hotline |
| Acquiring bank | P1 — per acquiring agreement | Bank's security contact |
| Data Protection Authority | P1 — GDPR Art. 33 (72 hours) | DPA notification portal |
| Affected customers | P1 — if required by law | Email notification |
| Legal counsel | P1 — before external notifications | Legal contact |

## 5. Evidence Preservation

All incident evidence MUST be preserved:

- Logs (do NOT delete or rotate during investigation)
- Screenshots of affected systems
- Network captures (if available)
- Timeline of events and actions taken
- All communications related to the incident

Evidence MUST be stored in `jolarca-compliance` and retained for at least
12 months (or longer if required by legal/regulatory obligations).

## 6. Post-Incident Review

Within 2 weeks of incident resolution:

1. Conduct a blameless post-mortem
2. Identify root cause
3. Document lessons learned
4. Create action items for preventing recurrence
5. Update relevant policies and procedures
6. Share findings with `jolarca-security` for cross-repo learning

## 7. Related Documents

- [Key Rotation Runbook](key-rotation.md)
- [Payment Security Policy](../policies/payment-security-policy.md)
- [Access Logging](../pci-dss/access-logging.md)
- [Key Management](../pci-dss/key-management.md)
