#!/usr/bin/env python3
"""Generate jolarca-observability schemas/ and compliance/ files."""

import os
from pathlib import Path

BASE = Path(
    os.environ.get(
        "JOLARCA_OBSERVABILITY_DIR",
        "/opt/jolarca/repos/jolarca-observability",
    )
)
files: dict[str, str] = {}

# ── schemas/README.md ──────────────────────────────────────────────────────────
files["schemas/README.md"] = """\
# Log Schemas

Defines the **mandatory fields** that every audit-log entry must contain.
A log entry missing a mandatory field is a compliance failure — it cannot
satisfy PCI-DSS Req. 10.2 (audit logs capture all actions) if the entry
does not record who did what and when.

## Schemas

| Schema | Domain | Key PCI-DSS Req. |
|--------|--------|-----------------|
| `audit-log-schema.yml` | All domains (base schema) | 10.2 |
| `payment-log-schema.yml` | Payment processing | 10.2.1 |
| `kyc-aml-log-schema.yml` | KYC/AML identity verification | 10.2.1 + GDPR Art. 30 |

## Validation

`scripts/verify_completeness.py` validates that log entries conform to these
schemas by checking that all mandatory fields are present and non-null.
"""

# ── schemas/audit-log-schema.yml ──────────────────────────────────────────────
files["schemas/audit-log-schema.yml"] = """\
# ──────────────────────────────────────────────────────────────────────────────
# Audit Log Schema — Mandatory Fields
# ──────────────────────────────────────────────────────────────────────────────
# Every audit-log entry across ALL domains must contain these fields.
# Domain-specific schemas extend this base with additional mandatory fields.
#
# Compliance: PCI-DSS Req. 10.2, SOC 2 CC7.1/CC8.1, ISO 27001 A.5.25
# ──────────────────────────────────────────────────────────────────────────────

version: "1.0.0"
schema_id: "audit-log-base"
compliance_frameworks: ["pci-dss", "soc2", "iso27001", "gdpr"]

# ── MANDATORY FIELDS ──────────────────────────────────────────────────────────
# An entry missing ANY of these fields FAILS validation and must be rejected
# by the log collector (not stored with incomplete data).

mandatory_fields:
  timestamp:
    type: "string"
    format: "ISO 8601 UTC"
    example: "2026-09-26T14:30:00.000Z"
    pci_requirement: "10.2 — when the event occurred"
    nullable: false

  event_id:
    type: "string"
    format: "UUID v4"
    example: "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
    description: "Unique identifier for this event"
    nullable: false

  event_type:
    type: "string"
    enum:
      - "chd_access"
      - "admin_action"
      - "audit_log_access"
      - "auth_failure"
      - "auth_config_change"
      - "audit_lifecycle"
      - "system_object_change"
      - "payment_initiated"
      - "payment_authorized"
      - "payment_settled"
      - "refund_initiated"
      - "chargeback_received"
      - "payment_config_change"
      - "identity_document_submitted"
      - "identity_verification_result"
      - "aml_screening_performed"
      - "sanctions_match_detected"
      - "suspicious_activity_reported"
      - "kyc_decision_override"
      - "identity_data_access"
      - "invalid_access_attempt"
      - "application_error"
      - "security_violation"
      - "ssh_login"
      - "ssh_logout"
      - "service_account_auth"
      - "network_deny"
      - "container_exec"
    pci_requirement: "10.2 — what type of event occurred"
    nullable: false

  actor_id:
    type: "string"
    description: "Unique identifier of the actor (user, service account, system)"
    example: "user:jol-12345"
    pci_requirement: "10.2 — who performed the action (linked to unique user)"
    nullable: false

  actor_type:
    type: "string"
    enum: ["user", "service_account", "system", "admin"]
    description: "Type of actor"
    nullable: false

  source_ip:
    type: "string"
    format: "IPv4 or IPv6"
    example: "203.0.113.42"
    pci_requirement: "10.2 — origin of the action"
    nullable: false

  domain:
    type: "string"
    enum: ["audit", "payment", "kyc_aml", "application", "system"]
    description: "Log domain this entry belongs to"
    nullable: false

  severity:
    type: "string"
    enum: ["info", "warn", "error", "critical"]
    description: "Event severity level"
    nullable: false

  description:
    type: "string"
    description: "Human-readable description of the event"
    max_length: 1000
    nullable: false

  hash_chain:
    type: "string"
    format: "SHA-256 hex digest (64 characters)"
    description: "Hash-chain integrity field — computed by the collector"
    pci_requirement: "10.5.5 — log integrity"
    nullable: false
    computed: true
    note: "Not emitted by the application; appended by the log collector"

# ── OPTIONAL FIELDS ───────────────────────────────────────────────────────────
optional_fields:
  target_resource:
    type: "string"
    description: "The resource that was accessed or modified"

  action:
    type: "string"
    enum: ["create", "read", "update", "delete", "execute", "login", "logout"]
    description: "The action performed"

  result:
    type: "string"
    enum: ["success", "failure", "denied", "error"]
    description: "Outcome of the action"

  data_categories:
    type: "array"
    items: "string"
    description: "Categories of data involved (e.g., 'chd', 'pii', 'kyc')"

  session_id:
    type: "string"
    description: "Session identifier (must not be usable to reconstruct the session)"

  correlation_id:
    type: "string"
    description: "Correlation ID for tracing related events across systems"

  metadata:
    type: "object"
    description: "Domain-specific additional fields"
"""

# ── schemas/payment-log-schema.yml ────────────────────────────────────────────
files["schemas/payment-log-schema.yml"] = """\
# ──────────────────────────────────────────────────────────────────────────────
# Payment Log Schema — Extends Audit Log Base Schema
# ──────────────────────────────────────────────────────────────────────────────
# Additional mandatory fields for payment-domain log entries.
# All fields from audit-log-schema.yml are also required.
#
# Compliance: PCI-DSS Req. 10.2.1 (all access to CHD)
# ──────────────────────────────────────────────────────────────────────────────

version: "1.0.0"
schema_id: "payment-log"
extends: "audit-log-schema.yml"
compliance_frameworks: ["pci-dss", "soc2"]

# ── ADDITIONAL MANDATORY FIELDS ───────────────────────────────────────────────
additional_mandatory_fields:
  transaction_id:
    type: "string"
    description: "Unique payment transaction identifier"
    pci_requirement: "10.2.1 — identify the specific transaction"
    nullable: false

  merchant_id:
    type: "string"
    description: "Merchant account identifier"
    nullable: false

  payment_method_type:
    type: "string"
    enum: ["card", "bank_transfer", "digital_wallet", "other"]
    description: "Type of payment method used"
    nullable: false

  amount_minor:
    type: "integer"
    description: "Amount in smallest currency unit (e.g., cents)"
    nullable: false

  currency:
    type: "string"
    format: "ISO 4217"
    example: "EUR"
    description: "Three-letter currency code"
    nullable: false

  access_type:
    type: "string"
    enum: ["view", "process", "transmit", "store", "delete"]
    description: "Type of access to cardholder data (when event_type is chd_access)"
    pci_requirement: "10.2.1 — what was done with CHD"
    conditionally_required: "when event_type == chd_access"

  data_element_accessed:
    type: "string"
    enum: ["pan", "expiry", "cardholder_name", "service_code", "full_track"]
    description: "Which cardholder data element was accessed"
    pci_requirement: "10.2.1 — which CHD element"
    conditionally_required: "when event_type == chd_access"

# ── REDACTION VERIFICATION ────────────────────────────────────────────────────
# Before storage, payment log entries are verified to NOT contain:
redaction_checks:
  - field: "pan"
    rule: "must be masked to last 4 digits or absent"
    pci_requirement: "3.3"
  - field: "cvv"
    rule: "must NEVER be present"
    pci_requirement: "3.2"
  - field: "pin"
    rule: "must NEVER be present"
    pci_requirement: "3.4"
  - field: "full_track_data"
    rule: "must NEVER be present"
    pci_requirement: "3.2"
"""

# ── schemas/kyc-aml-log-schema.yml ────────────────────────────────────────────
files["schemas/kyc-aml-log-schema.yml"] = """\
# ──────────────────────────────────────────────────────────────────────────────
# KYC/AML Log Schema — Extends Audit Log Base Schema
# ──────────────────────────────────────────────────────────────────────────────
# Additional mandatory fields for KYC/AML domain log entries.
# All fields from audit-log-schema.yml are also required.
#
# Compliance: PCI-DSS 10.2.1, GDPR Art. 30/32, AML Directives
# ──────────────────────────────────────────────────────────────────────────────

version: "1.0.0"
schema_id: "kyc-aml-log"
extends: "audit-log-schema.yml"
compliance_frameworks: ["pci-dss", "gdpr", "iso27001"]

# ── ADDITIONAL MANDATORY FIELDS ───────────────────────────────────────────────
additional_mandatory_fields:
  user_id:
    type: "string"
    description: "The user whose KYC/AML event this pertains to"
    nullable: false

  verification_method:
    type: "string"
    enum: ["document_verification", "biometric_match", "database_check", "manual_review", "enhanced_due_diligence"]
    description: "Method used for identity verification"
    conditionally_required: "when event_type involves verification"

  screening_type:
    type: "string"
    enum: ["sanctions", "pep", "adverse_media", "combined"]
    description: "Type of AML screening performed"
    conditionally_required: "when event_type is aml_screening_performed"

  lists_checked:
    type: "array"
    items: "string"
    description: "List of sanctions/PEP/adverse media lists checked"
    conditionally_required: "when event_type is aml_screening_performed"

  result:
    type: "string"
    enum: ["pass", "fail", "manual_review", "match_detected", "no_match"]
    description: "Outcome of the verification or screening"
    nullable: false

  confidence_score:
    type: "number"
    min: 0.0
    max: 1.0
    description: "Confidence score for the verification result"
    conditionally_required: "when event_type involves verification"

# ── REDACTION VERIFICATION ────────────────────────────────────────────────────
# KYC/AML logs must NEVER contain plaintext identity data
redaction_checks:
  - field: "document_number"
    rule: "must be SHA-256 hashed or absent"
  - field: "passport_number"
    rule: "must be SHA-256 hashed or absent"
  - field: "national_id"
    rule: "must be SHA-256 hashed or absent"
  - field: "date_of_birth"
    rule: "must be age range only, not exact date"
  - field: "full_address"
    rule: "must be country only, not full address"
  - field: "biometric_data"
    rule: "must NEVER be present"
  - field: "document_image"
    rule: "must NEVER be present"
"""

# ── compliance/README.md ──────────────────────────────────────────────────────
files["compliance/README.md"] = """\
# Compliance Mappings

Framework-specific compliance mappings that trace each configuration in this
repository to the specific control requirement it satisfies.

## Mappings

| File | Framework | Focus |
|------|-----------|-------|
| `pci-dss-req10-mapping.md` | PCI-DSS 4.0 | Req. 10 — Log and monitor all access |
| `soc2-cc7-mapping.md` | SOC 2 Type II | CC7 — System Operations |
| `gdpr-art30-32-mapping.md` | GDPR | Art. 30/32 — Records and security of processing |
| `iso27001-a5-mapping.md` | ISO 27001:2022 | A.5.24/A.5.25/A.8.15 — Logging and monitoring |

## How to Use

Each mapping traces a control requirement to the specific file(s) in this
repository that implement it. An auditor can:

1. Start with the framework requirement (e.g., PCI-DSS 10.5.1)
2. Read the mapping to find which config files implement it
3. Verify the configuration satisfies the requirement
4. Run the verification scripts to confirm compliance

## Cross-Reference with jolarca-control

The audit checklists in `jolarca-control/audit/` reference this repository
for logging and monitoring controls. The mappings here provide the detail
that the checklists summarize.
"""

# ── compliance/pci-dss-req10-checklist.yml ────────────────────────────────────
files["compliance/pci-dss-req10-checklist.yml"] = """\
# ──────────────────────────────────────────────────────────────────────────────
# PCI-DSS 4.0 Req. 10 — Self-Assessment Checklist
# ──────────────────────────────────────────────────────────────────────────────
# Use this checklist to verify that this repository's configurations satisfy
# all sub-requirements of PCI-DSS Req. 10.
#
# This is a governance-plane subset. Infrastructure-level controls (encryption,
# network segmentation, access control on log storage) are in
# jolarca-infrastructure.
# ──────────────────────────────────────────────────────────────────────────────

framework: "PCI-DSS 4.0"
requirement: "Req. 10"
title: "Log and monitor all access to system components and cardholder data"
version: "1.0.0"

checks:
  - id: "REQ10-01"
    requirement: "10.1 — Audit trails are implemented and linked to individual users"
    status: "implemented"
    evidence:
      - "schemas/audit-log-schema.yml — mandatory actor_id field"
      - "logging/configs/ — all domains require actor identification"

  - id: "REQ10-02"
    requirement: "10.2 — Audit logs capture all actions by individuals"
    status: "implemented"
    evidence:
      - "logging/configs/audit-log.yml — 7 mandatory event types"
      - "logging/configs/payment-log.yml — CHD access logging"
      - "logging/configs/kyc-aml-log.yml — identity data access logging"

  - id: "REQ10-03"
    requirement: "10.3 — Audit logs are protected from modification"
    status: "implemented"
    evidence:
      - "audit-trail/integrity/hash-chain.yml — SHA-256 hash chain"
      - "audit-trail/retention/retention-policy.yml — append-only storage"

  - id: "REQ10-04"
    requirement: "10.4 — Logs are reviewed regularly"
    status: "implemented"
    evidence:
      - "alerting/rules/ — real-time automated review"
      - "alerting/escalation-policy.yml — severity-based escalation"

  - id: "REQ10-05"
    requirement: "10.5 — Audit logs are retained and protected"
    status: "implemented"
    evidence:
      - "audit-trail/retention/retention-policy.yml — 12-month retention"
      - "audit-trail/integrity/hash-chain.yml — integrity protection"
      - "audit-trail/backup/backup-policy.yml — daily backup"

  - id: "REQ10-06"
    requirement: "10.6 — Security incidents identified from logs"
    status: "implemented"
    evidence:
      - "alerting/rules/security-alerts.yml — security event detection"
      - "runbooks/ — incident response procedures"

  - id: "REQ10-07"
    requirement: "10.5.1 — 12 months retention, 3 immediately available"
    status: "implemented"
    evidence:
      - "audit-trail/retention/retention-policy.yml — hot: 3mo, warm: 9mo"

  - id: "REQ10-08"
    requirement: "10.5.5 — File integrity monitoring on logs"
    status: "implemented"
    evidence:
      - "audit-trail/integrity/hash-chain.yml — hash-chain mechanism"
      - "scripts/verify_integrity.py — daily verification"
      - "alerting/rules/audit-tampering-alerts.yml — tamper detection"
"""

for relpath, content in files.items():
    target = BASE / relpath
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
    print(f"  created: {relpath}")

print(f"\nDone — {len(files)} schema + compliance files created.")
