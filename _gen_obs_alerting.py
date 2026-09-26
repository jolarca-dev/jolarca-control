#!/usr/bin/env python3
"""Generate jolarca-observability alerting/ and audit-trail/ files."""

from pathlib import Path

BASE = Path("/opt/jolarca/repos/jolarca-observability")
files: dict[str, str] = {}

# ── alerting/README.md ─────────────────────────────────────────────────────────
files["alerting/README.md"] = """\
# Alerting Rules

Defines **when and how the marketplace alerts on logging anomalies, security
events, and compliance failures**.

## Directory Structure

```
rules/
  audit-gap-alerts.yml        Audit log gap detection (Req. 10.5.5)
  audit-tampering-alerts.yml  Hash-chain break / log tampering (Req. 10.5.5)
  payment-access-alerts.yml   Unusual payment system access patterns
  retention-breach-alerts.yml Retention policy violation detection
  security-alerts.yml         Security event alerting (auth failures, privilege escalation)
escalation-policy.yml         Severity-based escalation procedures
```

## Alert Severity Levels

| Severity | Response Time | Escalation | Example |
|----------|---------------|------------|---------|
| CRITICAL | Immediate | Org owner, on-call | Audit log gap, hash-chain break |
| HIGH | 1 hour | Org owner | Unusual payment access, retention breach |
| MEDIUM | 4 hours | Review in next business day | Elevated auth failures |
| LOW | 24 hours | Weekly review | Informational security events |
"""

# ── alerting/escalation-policy.yml ─────────────────────────────────────────────
files["alerting/escalation-policy.yml"] = """\
# ──────────────────────────────────────────────────────────────────────────────
# Escalation Policy
# ──────────────────────────────────────────────────────────────────────────────
# Defines severity levels, response times, and escalation paths for all
# observability alerts.
#
# Compliance: PCI-DSS Req. 10.6, SOC 2 CC7.2/CC7.3, ISO 27001 A.5.25
# ──────────────────────────────────────────────────────────────────────────────

version: "1.0.0"
compliance_frameworks: ["pci-dss", "soc2", "iso27001"]

severity_levels:
  critical:
    response_time: "immediate"
    escalation_after: "15 minutes"
    escalate_to: "organization owner"
    notification_channels: ["pager", "email", "slack"]
    description: "Active security incident or compliance control failure"
    examples:
      - "Audit log gap > 5 minutes (potential log tampering)"
      - "Hash-chain integrity break (log modification detected)"
      - "Audit logging system offline"

  high:
    response_time: "1 hour"
    escalation_after: "4 hours"
    escalate_to: "organization owner"
    notification_channels: ["email", "slack"]
    description: "Security event requiring investigation"
    examples:
      - "Unusual payment admin access pattern"
      - "Retention policy violation (log deleted before expiry)"
      - "Multiple auth failures from single source"

  medium:
    response_time: "4 hours"
    escalation_after: "1 business day"
    escalate_to: "next business day review"
    notification_channels: ["email"]
    description: "Security event requiring attention but not urgent"
    examples:
      - "Elevated auth failure rate"
      - "New service account created"
      - "Configuration change to payment system"

  low:
    response_time: "24 hours"
    escalation_after: "weekly review"
    escalate_to: "weekly security review"
    notification_channels: ["slack"]
    description: "Informational security event"
    examples:
      - "Successful admin login from new IP"
      - "Scheduled audit log rotation completed"
      - "Certificate approaching expiry"

# ── ESCALATION PROCEDURE ──────────────────────────────────────────────────────
escalation_procedure:
  step_1: "Alert fires — notification sent per severity level"
  step_2: "Acknowledgement expected within response time"
  step_3: "If unacknowledged, escalate to next level"
  step_4: "CRITICAL alerts not acknowledged in 15 min → direct owner contact"
  step_5: "All CRITICAL and HIGH alerts logged as security events"
  step_6: "Post-incident: root cause analysis within 48 hours"

# ── SILENCE POLICY ────────────────────────────────────────────────────────────
# Alert silencing is a compliance risk — a silenced alert is an undetected
# incident. All silencing must be:
# 1. Time-bounded (max 4 hours for CRITICAL, 24 hours for others)
# 2. Approved by the organization owner
# 3. Recorded in the audit log with reason and approver
silence_policy:
  max_silence_duration:
    critical: "4 hours"
    high: "24 hours"
    medium: "7 days"
    low: "30 days"
  requires_owner_approval: ["critical", "high"]
  silence_must_be_logged: true
"""

# ── alerting/rules/audit-gap-alerts.yml ────────────────────────────────────────
files["alerting/rules/audit-gap-alerts.yml"] = """\
# ──────────────────────────────────────────────────────────────────────────────
# Audit Log Gap Detection — PCI-DSS Req. 10.5.5
# ──────────────────────────────────────────────────────────────────────────────
# Detects gaps in the audit log stream that may indicate logging failure or
# deliberate log suppression. A gap in audit logging is a gap in compliance.
# ──────────────────────────────────────────────────────────────────────────────

version: "1.0.0"
compliance_frameworks: ["pci-dss", "soc2", "iso27001"]

rules:
  - id: "AUDIT_GAP_5MIN"
    name: "Audit log gap exceeds 5 minutes"
    severity: critical
    description: >
      No audit-log entries received for any domain in the last 5 minutes.
      This may indicate the logging pipeline has failed, a system component
      has stopped emitting events, or an attacker has suppressed logging.
    condition: "time_since_last_audit_entry > 300s"
    scope: "all log domains"
    pci_requirement: "10.5.5"
    action:
      - "Page organization owner immediately"
      - "Check log collector health"
      - "Verify all log sources are connected"
      - "If gap confirmed: initiate runbooks/audit-log-gap.md"
    false_positive_handling: >
      Expected during planned maintenance windows. Maintenance must be
      pre-registered with a silence window (max 4 hours per silence_policy).

  - id: "AUDIT_GAP_PER_DOMAIN"
    name: "Domain-specific audit log gap"
    severity: high
    description: >
      No entries from a specific log domain (audit, payment, kyc-aml) for
      10 minutes while other domains continue to emit events.
    condition: "time_since_last_entry_per_domain > 600s AND other_domains_active"
    scope: "per domain"
    action:
      - "Notify organization owner within 1 hour"
      - "Check domain-specific log source health"
      - "Verify the application component is running"

  - id: "AUDIT_VOLUME_ANOMALY"
    name: "Audit log volume anomaly"
    severity: medium
    description: >
      Audit log volume deviates more than 80% from the 7-day rolling average
      for the same time-of-day window. May indicate selective logging failure
      or unusual activity.
    condition: "abs(current_volume - rolling_avg) / rolling_avg > 0.8"
    scope: "all log domains, per-hour window"
    action:
      - "Review in next 4-hour window"
      - "Compare with deployment/change logs for correlation"
"""

# ── alerting/rules/audit-tampering-alerts.yml ──────────────────────────────────
files["alerting/rules/audit-tampering-alerts.yml"] = """\
# ──────────────────────────────────────────────────────────────────────────────
# Audit Log Tampering Detection — PCI-DSS Req. 10.5.5
# ──────────────────────────────────────────────────────────────────────────────
# Detects potential modification, deletion, or corruption of audit logs.
# Uses hash-chain verification to detect any change to log entries.
# ──────────────────────────────────────────────────────────────────────────────

version: "1.0.0"
compliance_frameworks: ["pci-dss", "soc2", "iso27001"]

rules:
  - id: "HASH_CHAIN_BREAK"
    name: "Hash-chain integrity break detected"
    severity: critical
    description: >
      The hash-chain verification found a break: the computed hash of a log
      entry does not match the stored hash, or the previous-hash link is
      broken. This is strong evidence of log modification.
    condition: "verify_integrity.py detects hash mismatch"
    pci_requirement: "10.5.5"
    action:
      - "Page organization owner IMMEDIATELY"
      - "Preserve all log storage — do NOT restart or rotate"
      - "Initiate runbooks/audit-log-tampering.md"
      - "Assess under GDPR Art. 33 whether this is a notifiable breach"
    investigation:
      - "Identify the specific log entry and time range affected"
      - "Check access logs for the log storage system"
      - "Correlate with system access logs for the time window"
      - "Determine if the change was authorized (backup restore, migration)"

  - id: "HASH_CHAIN_MISSING"
    name: "Log entry found without hash-chain field"
    severity: critical
    description: >
      A log entry exists in storage without the required hash_chain field.
      This indicates the entry was inserted outside the normal pipeline.
    condition: "entry.hash_chain is null or missing"
    action:
      - "Quarantine the entry"
      - "Alert per CRITICAL escalation"
      - "Investigate the source of the unchained entry"

  - id: "LOG_STORAGE_WRITE_OUTSIDE_PIPELINE"
    name: "Write to log storage outside the collector pipeline"
    severity: critical
    description: >
      A write operation to the audit-log storage was performed by a process
      that is not the authorized log collector. This is direct evidence of
      potential log tampering.
    condition: "log_storage_write.source != authorized_collector"
    action:
      - "Block the write if possible"
      - "Page organization owner"
      - "Preserve forensic evidence"
      - "Initiate incident response"

  - id: "LOG_DELETION_ATTEMPT"
    name: "Attempt to delete audit log entries"
    severity: critical
    description: >
      Any attempt to delete or truncate audit log entries before the
      retention period expires. The storage is append-only; a deletion
      attempt is always unauthorized.
    condition: "DELETE or TRUNCATE on audit_log storage"
    pci_requirement: "10.5.1"
    action:
      - "Block the operation"
      - "Alert per CRITICAL escalation"
      - "Record the attempt as a security event"
"""

# ── alerting/rules/payment-access-alerts.yml ───────────────────────────────────
files["alerting/rules/payment-access-alerts.yml"] = """\
# ──────────────────────────────────────────────────────────────────────────────
# Payment Access Alerting Rules
# ──────────────────────────────────────────────────────────────────────────────
# Detects unusual access patterns to payment processing systems and
# cardholder data.
#
# Compliance: PCI-DSS Req. 10.2.1, 10.2.4, SOC 2 CC7.1
# ──────────────────────────────────────────────────────────────────────────────

version: "1.0.0"
compliance_frameworks: ["pci-dss", "soc2", "iso27001"]

rules:
  - id: "PAYMENT_ADMIN_OFF_HOURS"
    name: "Payment admin access outside business hours"
    severity: high
    description: >
      Administrative access to payment configuration or cardholder data
      outside defined business hours (06:00-22:00 UTC). May indicate
      compromised credentials or insider threat.
    condition: "payment_admin_access AND time NOT IN 06:00-22:00 UTC"
    action:
      - "Notify organization owner within 1 hour"
      - "Verify the actor's identity and authorization"
      - "Check for correlated auth failures"

  - id: "PAYMENT_ADMIN_NEW_IP"
    name: "Payment admin access from new IP address"
    severity: high
    description: >
      Administrative access to payment systems from an IP address not
      seen in the last 90 days.
    condition: "payment_admin_access AND source_ip NOT IN known_ips_90d"
    action:
      - "Notify organization owner within 1 hour"
      - "Verify the actor's identity"
      - "Check if IP belongs to known VPN/proxy"

  - id: "CHD_ACCESS_BULK"
    name: "Bulk cardholder data access"
    severity: critical
    description: >
      A single actor accesses cardholder data for more than 50 transactions
      in a 10-minute window. May indicate data exfiltration.
    condition: "chd_access_count_per_actor > 50 IN 600s"
    action:
      - "Page organization owner immediately"
      - "Consider temporarily suspending the actor's access"
      - "Initiate forensic investigation"

  - id: "PAYMENT_CONFIG_CHANGE"
    name: "Payment configuration change"
    severity: high
    description: >
      Any change to payment processing configuration (merchant accounts,
      API keys, webhook endpoints, settlement parameters).
    condition: "event_type == payment_config_change"
    action:
      - "Notify organization owner within 1 hour"
      - "Verify the change was authorized"
      - "Record in change management log"

  - id: "AUTH_FAILURE_THRESHOLD"
    name: "Authentication failure threshold exceeded"
    severity: medium
    description: >
      More than 5 authentication failures for payment systems from the
      same source within 15 minutes.
    condition: "auth_failure_count_per_source > 5 IN 900s AND target == payment_system"
    action:
      - "Notify within 4 hours"
      - "Consider temporary IP block"
      - "Check for credential stuffing pattern"
"""

# ── alerting/rules/retention-breach-alerts.yml ────────────────────────────────
files["alerting/rules/retention-breach-alerts.yml"] = """\
# ──────────────────────────────────────────────────────────────────────────────
# Retention Breach Detection
# ──────────────────────────────────────────────────────────────────────────────
# Detects when audit logs are deleted, archived prematurely, or when the
# retention policy is not being met.
#
# Compliance: PCI-DSS Req. 10.5.1, SOC 2 CC8.1
# ──────────────────────────────────────────────────────────────────────────────

version: "1.0.0"
compliance_frameworks: ["pci-dss", "soc2", "iso27001"]

rules:
  - id: "RETENTION_PREMATURE_DELETE"
    name: "Audit log deleted before retention period expires"
    severity: high
    description: >
      An audit log entry was deleted or made inaccessible before the
      minimum retention period (12 months) has elapsed.
    condition: "log_entry.deleted AND age < 12_months"
    pci_requirement: "10.5.1"
    action:
      - "Notify organization owner within 1 hour"
      - "Attempt to restore from backup"
      - "Investigate the deletion source"
      - "Record as a security event"

  - id: "RETENTION_HOT_EXPIRED"
    name: "Hot retention period not maintained"
    severity: high
    description: >
      Logs from the last 3 months are not immediately available for
      search/retrieval. PCI-DSS Req. 10.5.1 requires at least 3 months
      to be immediately available.
    condition: "hot_storage.missing_entries_for_last_3_months"
    action:
      - "Notify organization owner within 1 hour"
      - "Restore from warm/cold storage if available"
      - "Investigate why hot storage is incomplete"

  - id: "BACKUP_FAILURE"
    name: "Audit log backup failure"
    severity: high
    description: >
      The scheduled backup of audit logs failed. Without current backups,
      log recovery after a failure is not possible.
    condition: "last_successful_backup > 25_hours"
    action:
      - "Notify organization owner within 1 hour"
      - "Investigate backup system health"
      - "Verify primary storage is still intact"

  - id: "STORAGE_CAPACITY_WARNING"
    name: "Log storage capacity approaching limit"
    severity: medium
    description: >
      Log storage is above 80% capacity. If storage fills, new log
      entries cannot be written, creating an audit gap.
    condition: "storage_usage_percent > 80"
    action:
      - "Notify within 4 hours"
      - "Plan capacity expansion"
      - "Verify retention policy is correctly pruning expired entries"
"""

# ── alerting/rules/security-alerts.yml ────────────────────────────────────────
files["alerting/rules/security-alerts.yml"] = """\
# ──────────────────────────────────────────────────────────────────────────────
# Security Event Alerting Rules
# ──────────────────────────────────────────────────────────────────────────────
# General security event alerting: authentication failures, privilege
# escalation, unauthorized access, and suspicious patterns.
#
# Compliance: PCI-DSS Req. 10.2.4, 10.6, SOC 2 CC7.1, ISO 27001 A.5.25
# ──────────────────────────────────────────────────────────────────────────────

version: "1.0.0"
compliance_frameworks: ["pci-dss", "soc2", "iso27001"]

rules:
  - id: "PRIVILEGE_ESCALATION"
    name: "Privilege escalation detected"
    severity: critical
    description: >
      A user's access level was elevated without a corresponding approved
      change record. May indicate compromised credentials or insider threat.
    condition: "user.role_changed AND change NOT IN approved_changes"
    action:
      - "Page organization owner immediately"
      - "Consider reverting the privilege change"
      - "Investigate the source of the change"

  - id: "ROOT_ACCESS_USED"
    name: "Root/admin access used on system component"
    severity: high
    description: >
      Root or administrator access was used on any system component in
      the cardholder-data environment.
    condition: "access.user IN [root, admin] AND target IN cde_systems"
    pci_requirement: "10.2.2"
    action:
      - "Notify organization owner within 1 hour"
      - "Verify the access was authorized"
      - "Record in audit trail"

  - id: "SHARED_ACCOUNT_DETECTED"
    name: "Possible shared account usage"
    severity: high
    description: >
      An account is used from multiple source IPs within a short time
      window, suggesting the credentials may be shared (PCI-DSS Req. 8.2
      requires unique IDs).
    condition: "unique_source_ips_per_actor > 2 IN 3600s"
    pci_requirement: "8.2"
    action:
      - "Notify within 1 hour"
      - "Verify the account holder"
      - "Consider forcing password reset"

  - id: "KYC_DECISION_OVERRIDE"
    name: "KYC decision manually overridden"
    severity: high
    description: >
      A KYC verification decision was manually overridden. This is a
      compliance-sensitive event that may indicate fraud facilitation.
    condition: "event_type == kyc_decision_override"
    action:
      - "Notify organization owner within 1 hour"
      - "Verify the override was authorized and documented"
      - "Flag for compliance review"

  - id: "SAR_FILED"
    name: "Suspicious activity report filed"
    severity: high
    description: >
      A suspicious activity report was filed. This is a regulatory
      obligation with strict confidentiality requirements.
    condition: "event_type == suspicious_activity_reported"
    action:
      - "Notify organization owner within 1 hour"
      - "Ensure SAR confidentiality is maintained"
      - "Verify filing with the appropriate authority"
"""

# ── audit-trail/README.md ─────────────────────────────────────────────────────
files["audit-trail/README.md"] = """\
# Audit Trail

Defines **how audit logs are retained, protected, and backed up** to satisfy
PCI-DSS Req. 10.5 and equivalent requirements across all compliance frameworks.

## Directory Structure

```
retention/
  retention-policy.yml    Retention periods per log domain
integrity/
  hash-chain.yml          Hash-chain integrity mechanism specification
  verification-config.yml Configuration for integrity verification scripts
backup/
  backup-policy.yml       Audit-log backup schedule and restore procedures
```

## Key Requirements

| Requirement | Source | Implementation |
|---|---|---|
| 12-month minimum retention | PCI-DSS 10.5.1 | `retention/retention-policy.yml` |
| 3 months immediately available | PCI-DSS 10.5.1 | `retention/retention-policy.yml` (hot tier) |
| Logs protected from modification | PCI-DSS 10.5 | `integrity/hash-chain.yml` |
| File-integrity monitoring | PCI-DSS 10.5.5 | `integrity/verification-config.yml` |
| Promptly backed up | PCI-DSS 10.5.3 | `backup/backup-policy.yml` |
"""

# ── audit-trail/retention/retention-policy.yml ─────────────────────────────────
files["audit-trail/retention/retention-policy.yml"] = """\
# ──────────────────────────────────────────────────────────────────────────────
# Audit Trail Retention Policy
# ──────────────────────────────────────────────────────────────────────────────
# Defines how long audit logs are retained per domain and per tier.
#
# PCI-DSS Req. 10.5.1: retain audit log history for at least 12 months,
# with at least the most recent 3 months immediately available.
#
# AML directives may require longer retention (5+ years) for KYC-related
# logs — check local jurisdiction requirements.
# ──────────────────────────────────────────────────────────────────────────────

version: "1.0.0"
compliance_frameworks: ["pci-dss", "soc2", "gdpr", "iso27001"]

# ── GLOBAL MINIMUMS ───────────────────────────────────────────────────────────
# These apply to ALL log domains. Per-domain policies may extend but never
# shorten these minimums.

global_minimums:
  total_retention_months: 12     # PCI-DSS Req. 10.5.1
  immediately_available_months: 3  # PCI-DSS Req. 10.5.1
  backup_retention_months: 13    # At least 1 month beyond total retention

# ── STORAGE TIERS ─────────────────────────────────────────────────────────────
storage_tiers:
  hot:
    description: "Immediately available for search and retrieval"
    retention_months: 3
    retrieval_latency: "real-time"
    storage_type: "encrypted block storage"
    pci_requirement: "10.5.1 — 3 months immediately available"

  warm:
    description: "Archived but retrievable within 48 hours"
    retention_months: 9
    retrieval_latency: "48 hours"
    storage_type: "encrypted object storage (IA tier)"
    note: "Covers months 4-12 of the 12-month retention requirement"

  cold:
    description: "Long-term archive for compliance and legal hold"
    retention_months: 60
    retrieval_latency: "5 business days"
    storage_type: "encrypted archive storage"
    note: "Exceeds PCI-DSS minimum; supports AML 5-year retention"

# ── PER-DOMAIN RETENTION ──────────────────────────────────────────────────────
domain_retention:
  audit:
    hot_months: 3
    warm_months: 9
    cold_months: 60
    note: "Administrative and privileged access — full 12-month PCI retention"

  payment:
    hot_months: 3
    warm_months: 9
    cold_months: 84
    note: "Payment events — 7 years for payment card brand requirements"

  kyc_aml:
    hot_months: 3
    warm_months: 9
    cold_months: 84
    note: "KYC/AML events — 5+ years per AML directives, 7 years for best practice"

  application:
    hot_months: 3
    warm_months: 9
    cold_months: 24
    note: "Application events — 2 years for operational troubleshooting"

  system:
    hot_months: 3
    warm_months: 9
    cold_months: 24
    note: "System access — 2 years for infrastructure forensics"

# ── RETENTION ENFORCEMENT ─────────────────────────────────────────────────────
enforcement:
  auto_delete_after_retention: false
  note: >
    Logs are NEVER automatically deleted. Retention expiry triggers a review:
    the org owner must explicitly approve deletion. This prevents accidental
    loss of logs that may be needed for ongoing investigations or legal holds.
  legal_hold_override: true
  note_legal_hold: >
    A legal hold freezes retention for the specified log range. No deletion
    is permitted while a legal hold is active, regardless of retention expiry.
  deletion_must_be_logged: true
  note_deletion: >
    Every deletion of audit logs (after retention expiry, with approval) is
    itself logged as an audit event with: who approved, what was deleted,
    the retention period that had elapsed, and the legal-hold check result.
"""

# ── audit-trail/integrity/hash-chain.yml ──────────────────────────────────────
files["audit-trail/integrity/hash-chain.yml"] = """\
# ──────────────────────────────────────────────────────────────────────────────
# Hash-Chain Integrity Mechanism
# ──────────────────────────────────────────────────────────────────────────────
# Specifies the cryptographic integrity mechanism that protects audit logs
# from undetected modification.
#
# PCI-DSS Req. 10.5.5: Use file-integrity monitoring or change-detection
# software on logs to detect unauthorized modifications.
# ──────────────────────────────────────────────────────────────────────────────

version: "1.0.0"
compliance_frameworks: ["pci-dss", "soc2", "iso27001"]

# ── HASH-CHAIN SPECIFICATION ──────────────────────────────────────────────────
hash_chain:
  algorithm: "SHA-256"
  description: >
    Every audit-log entry includes a hash_chain field computed as:

      hash_chain = SHA-256(
        timestamp || "|" ||
        event_id  || "|" ||
        actor_id  || "|" ||
        event_type || "|" ||
        previous_hash
      )

    where previous_hash is the hash_chain of the preceding entry.
    For the first entry in a daily batch, previous_hash is the last
    hash of the previous day (or a genesis hash for day 1).

  input_fields:
    - "timestamp"       # ISO 8601 UTC
    - "event_id"        # UUID v4
    - "actor_id"        # Authenticated user identifier
    - "event_type"      # Controlled vocabulary
    - "previous_hash"   # SHA-256 hex digest of preceding entry

  output: "hex-encoded SHA-256 digest (64 characters)"

# ── GENESIS HASH ──────────────────────────────────────────────────────────────
genesis:
  hash: "0000000000000000000000000000000000000000000000000000000000000000"
  description: "All-zeros genesis hash for the first entry in the chain"
  note: >
    The genesis hash is a constant. It marks the beginning of the chain.
    Any change to the genesis hash would invalidate the entire chain,
    so it is hardcoded and verified by the integrity check script.

# ── VERIFICATION ──────────────────────────────────────────────────────────────
verification:
  frequency: "daily"
  script: "../../scripts/verify_integrity.py"
  scope: "all entries in hot and warm storage"
  on_failure:
    severity: "critical"
    action: "alert + preserve storage + initiate runbooks/audit-log-tampering.md"

  # Verification must detect:
  detects:
    - "modification of any log entry field"
    - "insertion of a forged entry"
    - "deletion of an entry (gap in the chain)"
    - "reordering of entries"
    - "replacement of an entry with a different version"

  # Verification cannot prevent:
  limitations:
    - "an attacker who controls the log collector can forge entries before chaining"
    - "defense in depth: access control on log storage is the primary control"
    - "hash-chain is the DETECTION control, not the PREVENTION control"

# ── KEY MANAGEMENT ────────────────────────────────────────────────────────────
# The hash chain uses SHA-256 (unkeyed). No secret key is involved.
# Integrity relies on the chain structure, not on a secret.
# This means:
# - An attacker who modifies an entry must recompute all subsequent hashes,
#   which is detectable because the stored hashes no longer match.
# - An attacker who can write to the log storage AND recompute hashes
#   would need to modify every entry from the tampered point forward —
#   this is detected by the verification script comparing stored vs computed.
key_management:
  algorithm_type: "unkeyed hash (SHA-256)"
  note: "No key rotation needed — integrity is structural, not cryptographic-secret-based"
"""

# ── audit-trail/integrity/verification-config.yml ─────────────────────────────
files["audit-trail/integrity/verification-config.yml"] = """\
# ──────────────────────────────────────────────────────────────────────────────
# Integrity Verification Configuration
# ──────────────────────────────────────────────────────────────────────────────
# Configuration for scripts/verify_integrity.py — defines what to verify,
# how often, and what to do on failure.
# ──────────────────────────────────────────────────────────────────────────────

version: "1.0.0"

verification:
  # ── Schedule ─────────────────────────────────────────────────────────────
  schedule:
    full_verification: "daily at 03:00 UTC"
    incremental_verification: "hourly (last 1000 entries)"
    note: >
      Full verification recomputes every hash in the chain. Incremental
      verification checks only the most recent entries for faster feedback.

  # ── Scope ────────────────────────────────────────────────────────────────
  scope:
    domains: ["audit", "payment", "kyc_aml", "application", "system"]
    storage_tiers: ["hot", "warm"]
    note: "Cold storage is verified on access and during annual compliance review"

  # ── Failure Handling ─────────────────────────────────────────────────────
  on_failure:
    severity: "critical"
    actions:
      - "Halt verification and preserve current state"
      - "Alert per escalation-policy.yml CRITICAL path"
      - "Log the failure as a security event"
      - "Do NOT attempt automatic repair"
      - "Initiate runbooks/audit-log-tampering.md"

  # ── Reporting ────────────────────────────────────────────────────────────
  reporting:
    format: "json"
    output_path: "reports/integrity-verification-{date}.json"
    retain_reports_months: 12
    include_in_compliance_scan: true
"""

# ── audit-trail/backup/backup-policy.yml ──────────────────────────────────────
files["audit-trail/backup/backup-policy.yml"] = """\
# ──────────────────────────────────────────────────────────────────────────────
# Audit Log Backup Policy
# ──────────────────────────────────────────────────────────────────────────────
# Defines the backup schedule, storage, and restore procedures for audit logs.
#
# PCI-DSS Req. 10.5.3: Audit trails are promptly backed up.
# ──────────────────────────────────────────────────────────────────────────────

version: "1.0.0"
compliance_frameworks: ["pci-dss", "soc2", "iso27001"]

# ── BACKUP SCHEDULE ───────────────────────────────────────────────────────────
schedule:
  incremental:
    frequency: "daily"
    window: "02:00-03:00 UTC"
    scope: "entries since last backup"
    type: "incremental (delta from last full/incremental)"

  full:
    frequency: "weekly"
    day: "Sunday"
    window: "01:00-03:00 UTC"
    scope: "all entries across all domains"
    type: "full snapshot"

  on_demand:
    trigger: "before any maintenance window or system change"
    scope: "all entries"
    type: "full snapshot"

# ── BACKUP STORAGE ────────────────────────────────────────────────────────────
storage:
  primary:
    location: "EU region (same as primary log storage)"
    encryption: "AES-256-GCM with CMEK"
    access_control: "restricted to backup service account + org owner break-glass"
    immutability: "object lock (WORM) for 13 months minimum"

  secondary:
    location: "separate EU availability zone"
    encryption: "AES-256-GCM with distinct CMEK"
    access_control: "same as primary"
    immutability: "object lock (WORM) for 13 months minimum"
    note: "Geographic separation protects against single-zone failure"

# ── RESTORE PROCEDURE ─────────────────────────────────────────────────────────
restore:
  rto: "4 hours"    # Recovery Time Objective
  rpo: "24 hours"   # Recovery Point Objective (max data loss)
  procedure: "runbooks/audit-log-backup-restore.md"

  # Restore verification:
  verification:
    - "Recompute hash chain on restored entries"
    - "Verify entry count matches backup manifest"
    - "Spot-check 10 random entries for field completeness"
    - "Verify no entries outside the restore range were affected"

# ── BACKUP VERIFICATION ──────────────────────────────────────────────────────
verification:
  test_restore:
    frequency: "quarterly"
    scope: "restore latest full backup to isolated environment"
    success_criteria:
      - "Hash chain verifies with zero breaks"
      - "Entry count matches within 0.1%"
      - "All mandatory fields present per schema"
      - "Restore completed within RTO"
    note: "Results retained as compliance evidence (ISO 27001 A.8.13)"
"""

for relpath, content in files.items():
    target = BASE / relpath
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
    print(f"  created: {relpath}")

print(f"\nDone — {len(files)} alerting + audit-trail files created.")
