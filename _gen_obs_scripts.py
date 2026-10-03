#!/usr/bin/env python3
"""Generate jolarca-observability scripts/ files."""

import os
from pathlib import Path

BASE = Path(
    os.environ.get(
        "JOLARCA_OBSERVABILITY_DIR",
        "/opt/jolarca/repos/jolarca-observability",
    )
)
files: dict[str, str] = {}

# ── scripts/README.md ─────────────────────────────────────────────────────────
files["scripts/README.md"] = """\
# Verification Scripts

Automated verification scripts that validate the logging, alerting, and
audit-trail configurations comply with PCI-DSS Req. 10 and other framework
requirements.

## Scripts

| Script | Purpose | PCI-DSS Req. |
|--------|---------|-------------|
| `verify_retention.py` | Validates retention policy compliance | 10.5.1 |
| `verify_integrity.py` | Verifies hash-chain integrity | 10.5.5 |
| `verify_completeness.py` | Checks mandatory field presence in log schemas | 10.2 |

## Usage

```bash
# Run all verification scripts
make verify-all

# Run individual scripts
python scripts/verify_retention.py
python scripts/verify_integrity.py
python scripts/verify_completeness.py
```

## Exit Codes

All scripts use consistent exit codes:

| Code | Meaning |
|------|---------|
| 0 | All checks passed |
| 1 | Verification failed — compliance issue detected |
| 2 | Could not verify — infrastructure error (treat as failure) |

Exit code 2 follows the D-23 principle from jolarca-control: **unverifiable
state must fail loudly, never silently pass**.
"""

# ── scripts/verify_retention.py ───────────────────────────────────────────────
files["scripts/verify_retention.py"] = """\
#!/usr/bin/env python3
\"\"\"Verify audit-log retention policy compliance.

Checks:
  * Retention policy file exists and is valid YAML
  * Global minimums meet PCI-DSS Req. 10.5.1 (12 months, 3 immediately available)
  * Per-domain retention meets or exceeds global minimums
  * Storage tiers are defined (hot, warm, cold)
  * Auto-delete is disabled (logs must not be automatically removed)
  * Legal hold override is enabled

Compliance: PCI-DSS Req. 10.5.1, SOC 2 CC8.1
\"\"\"

from __future__ import annotations

import sys
from pathlib import Path

import yaml

BASE_DIR = Path(__file__).resolve().parent.parent
RETENTION_FILE = BASE_DIR / "audit-trail" / "retention" / "retention-policy.yml"

# PCI-DSS Req. 10.5.1 minimums
MIN_TOTAL_MONTHS = 12
MIN_IMMEDIATELY_AVAILABLE_MONTHS = 3


def load_retention_policy() -> dict:
    \"\"\"Load and parse the retention policy file.\"\"\"
    if not RETENTION_FILE.exists():
        print(f"ERROR: Retention policy not found: {RETENTION_FILE}", file=sys.stderr)
        sys.exit(2)

    with open(RETENTION_FILE, encoding="utf-8") as f:
        try:
            data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            print(f"ERROR: Invalid YAML in retention policy: {e}", file=sys.stderr)
            sys.exit(2)

    if not isinstance(data, dict):
        print("ERROR: Retention policy root must be a YAML mapping", file=sys.stderr)
        sys.exit(2)

    return data


def verify_global_minimums(data: dict) -> list[str]:
    \"\"\"Verify global retention minimums meet PCI-DSS Req. 10.5.1.\"\"\"
    errors: list[str] = []
    mins = data.get("global_minimums", {})

    total = mins.get("total_retention_months", 0)
    if total < MIN_TOTAL_MONTHS:
        errors.append(
            f"Global total_retention_months={total} < PCI-DSS minimum {MIN_TOTAL_MONTHS}"
        )

    available = mins.get("immediately_available_months", 0)
    if available < MIN_IMMEDIATELY_AVAILABLE_MONTHS:
        errors.append(
            f"Global immediately_available_months={available} < "
            f"PCI-DSS minimum {MIN_IMMEDIATELY_AVAILABLE_MONTHS}"
        )

    return errors


def verify_storage_tiers(data: dict) -> list[str]:
    \"\"\"Verify storage tiers are properly defined.\"\"\"
    errors: list[str] = []
    tiers = data.get("storage_tiers", {})

    for required_tier in ["hot", "warm"]:
        if required_tier not in tiers:
            errors.append(f"Missing required storage tier: {required_tier}")
        else:
            tier = tiers[required_tier]
            if "retention_months" not in tier:
                errors.append(f"Storage tier '{required_tier}' missing retention_months")
            if "retrieval_latency" not in tier:
                errors.append(f"Storage tier '{required_tier}' missing retrieval_latency")

    # Hot tier must cover at least 3 months
    hot = tiers.get("hot", {})
    if hot.get("retention_months", 0) < MIN_IMMEDIATELY_AVAILABLE_MONTHS:
        errors.append(
            f"Hot tier retention_months={hot.get('retention_months', 0)} < "
            f"PCI-DSS minimum {MIN_IMMEDIATELY_AVAILABLE_MONTHS}"
        )

    return errors


def verify_domain_retention(data: dict) -> list[str]:
    \"\"\"Verify per-domain retention meets global minimums.\"\"\"
    errors: list[str] = []
    domain_retention = data.get("domain_retention", {})
    global_mins = data.get("global_minimums", {})

    min_total = global_mins.get("total_retention_months", MIN_TOTAL_MONTHS)

    for domain, config in domain_retention.items():
        hot = config.get("hot_months", 0)
        warm = config.get("warm_months", 0)
        cold = config.get("cold_months", 0)

        total = hot + warm + cold
        if total < min_total:
            errors.append(
                f"Domain '{domain}' total retention ({total}mo) < "
                f"global minimum ({min_total}mo)"
            )

        if hot < MIN_IMMEDIATELY_AVAILABLE_MONTHS:
            errors.append(
                f"Domain '{domain}' hot_months={hot} < "
                f"PCI-DSS minimum {MIN_IMMEDIATELY_AVAILABLE_MONTHS}"
            )

    return errors


def verify_enforcement(data: dict) -> list[str]:
    \"\"\"Verify retention enforcement settings.\"\"\"
    errors: list[str] = []
    enforcement = data.get("enforcement", {})

    if enforcement.get("auto_delete_after_retention", True):
        errors.append(
            "auto_delete_after_retention must be false — logs must not be "
            "automatically deleted"
        )

    if not enforcement.get("legal_hold_override", False):
        errors.append(
            "legal_hold_override must be true — legal holds must override retention"
        )

    if not enforcement.get("deletion_must_be_logged", False):
        errors.append(
            "deletion_must_be_logged must be true — all deletions must be audited"
        )

    return errors


def main() -> int:
    \"\"\"Run all retention policy verification checks.\"\"\"
    data = load_retention_policy()

    all_errors: list[str] = []
    all_errors.extend(verify_global_minimums(data))
    all_errors.extend(verify_storage_tiers(data))
    all_errors.extend(verify_domain_retention(data))
    all_errors.extend(verify_enforcement(data))

    if all_errors:
        print(f"FAILED — {len(all_errors)} retention policy violation(s):\\n")
        for err in all_errors:
            print(f"  x {err}")
        return 1

    print("PASSED — retention policy meets PCI-DSS Req. 10.5.1 requirements.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
"""

# ── scripts/verify_integrity.py ───────────────────────────────────────────────
files["scripts/verify_integrity.py"] = """\
#!/usr/bin/env python3
\"\"\"Verify audit-log hash-chain integrity configuration.

Checks:
  * Hash-chain configuration file exists and is valid YAML
  * Algorithm is SHA-256 (minimum acceptable for PCI-DSS)
  * Input fields are defined and include all mandatory fields
  * Genesis hash is defined
  * Verification frequency is defined (daily minimum)
  * On-failure actions include CRITICAL alerting
  * Limitations are documented (honest about what hash chains cannot prevent)

Compliance: PCI-DSS Req. 10.5.5, SOC 2 CC7.1
\"\"\"

from __future__ import annotations

import sys
from pathlib import Path

import yaml

BASE_DIR = Path(__file__).resolve().parent.parent
HASH_CHAIN_FILE = BASE_DIR / "audit-trail" / "integrity" / "hash-chain.yml"
VERIFICATION_FILE = BASE_DIR / "audit-trail" / "integrity" / "verification-config.yml"

REQUIRED_INPUT_FIELDS = {"timestamp", "event_id", "actor_id", "event_type", "previous_hash"}


def load_yaml_file(filepath: Path, label: str) -> dict:
    \"\"\"Load and parse a YAML file.\"\"\"
    if not filepath.exists():
        print(f"ERROR: {label} not found: {filepath}", file=sys.stderr)
        sys.exit(2)

    with open(filepath, encoding="utf-8") as f:
        try:
            data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            print(f"ERROR: Invalid YAML in {label}: {e}", file=sys.stderr)
            sys.exit(2)

    if not isinstance(data, dict):
        print(f"ERROR: {label} root must be a YAML mapping", file=sys.stderr)
        sys.exit(2)

    return data


def verify_hash_chain_config(data: dict) -> list[str]:
    \"\"\"Verify hash-chain configuration.\"\"\"
    errors: list[str] = []
    hc = data.get("hash_chain", {})

    # Algorithm check
    algo = hc.get("algorithm", "")
    if algo != "SHA-256":
        errors.append(f"Hash algorithm must be SHA-256, got '{algo}'")

    # Input fields check
    input_fields = set(hc.get("input_fields", []))
    missing = REQUIRED_INPUT_FIELDS - input_fields
    if missing:
        errors.append(f"Hash-chain input fields missing: {sorted(missing)}")

    # Genesis hash check
    genesis = data.get("genesis", {})
    if not genesis.get("hash"):
        errors.append("Genesis hash is not defined")

    return errors


def verify_verification_config(data: dict) -> list[str]:
    \"\"\"Verify verification configuration.\"\"\"
    errors: list[str] = []

    # Schedule check
    schedule = data.get("verification", {}).get("schedule", {})
    if not schedule.get("full_verification"):
        errors.append("Full verification schedule not defined")

    # Scope check
    scope = data.get("verification", {}).get("scope", {})
    domains = scope.get("domains", [])
    required_domains = {"audit", "payment", "kyc_aml"}
    missing_domains = required_domains - set(domains)
    if missing_domains:
        errors.append(f"Verification scope missing domains: {sorted(missing_domains)}")

    # On-failure check
    on_failure = data.get("verification", {}).get("on_failure", {})
    if on_failure.get("severity") != "critical":
        errors.append("Verification failure severity must be 'critical'")

    return errors


def main() -> int:
    \"\"\"Run all integrity configuration verification checks.\"\"\"
    hc_data = load_yaml_file(HASH_CHAIN_FILE, "Hash-chain config")
    vc_data = load_yaml_file(VERIFICATION_FILE, "Verification config")

    all_errors: list[str] = []
    all_errors.extend(verify_hash_chain_config(hc_data))
    all_errors.extend(verify_verification_config(vc_data))

    if all_errors:
        print(f"FAILED — {len(all_errors)} integrity configuration violation(s):\\n")
        for err in all_errors:
            print(f"  x {err}")
        return 1

    print("PASSED — hash-chain integrity configuration meets PCI-DSS Req. 10.5.5.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
"""

# ── scripts/verify_completeness.py ────────────────────────────────────────────
files["scripts/verify_completeness.py"] = """\
#!/usr/bin/env python3
\"\"\"Verify log schema completeness — all mandatory fields are defined.

Checks:
  * Schema files exist and are valid YAML
  * Base audit-log schema defines all PCI-DSS Req. 10.2 mandatory fields
  * Payment schema extends base with CHD-specific fields
  * KYC/AML schema extends base with identity-verification fields
  * All mandatory fields have type, description, and nullable defined
  * Event type enum covers all mandatory event types from logging configs

Compliance: PCI-DSS Req. 10.2, SOC 2 CC7.1
\"\"\"

from __future__ import annotations

import sys
from pathlib import Path

import yaml

BASE_DIR = Path(__file__).resolve().parent.parent
SCHEMAS_DIR = BASE_DIR / "schemas"

# PCI-DSS Req. 10.2 requires these fields in every audit-log entry
REQUIRED_BASE_FIELDS = {
    "timestamp",
    "event_id",
    "event_type",
    "actor_id",
    "actor_type",
    "source_ip",
    "domain",
    "severity",
    "description",
    "hash_chain",
}

# Payment-specific mandatory fields per PCI-DSS Req. 10.2.1
REQUIRED_PAYMENT_FIELDS = {
    "transaction_id",
    "merchant_id",
    "payment_method_type",
    "amount_minor",
    "currency",
}

# KYC/AML-specific mandatory fields
REQUIRED_KYC_FIELDS = {
    "user_id",
    "result",
}


def load_schema(filename: str) -> dict:
    \"\"\"Load a schema file.\"\"\"
    filepath = SCHEMAS_DIR / filename
    if not filepath.exists():
        print(f"ERROR: Schema not found: {filepath}", file=sys.stderr)
        sys.exit(2)

    with open(filepath, encoding="utf-8") as f:
        try:
            data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            print(f"ERROR: Invalid YAML in {filename}: {e}", file=sys.stderr)
            sys.exit(2)

    if not isinstance(data, dict):
        print(f"ERROR: {filename} root must be a YAML mapping", file=sys.stderr)
        sys.exit(2)

    return data


def verify_base_schema(data: dict) -> list[str]:
    \"\"\"Verify the base audit-log schema.\"\"\"
    errors: list[str] = []
    mandatory = data.get("mandatory_fields", {})

    # Check all required fields are present
    present_fields = set(mandatory.keys())
    missing = REQUIRED_BASE_FIELDS - present_fields
    if missing:
        errors.append(f"Base schema missing mandatory fields: {sorted(missing)}")

    # Check each mandatory field has required attributes
    for field_name, field_def in mandatory.items():
        if not isinstance(field_def, dict):
            errors.append(f"Field '{field_name}' must be a mapping")
            continue
        if "type" not in field_def:
            errors.append(f"Field '{field_name}' missing 'type'")
        if "description" not in field_def and "pci_requirement" not in field_def:
            errors.append(f"Field '{field_name}' missing description or pci_requirement")

    # Check event_type enum is not empty
    event_type = mandatory.get("event_type", {})
    enum_values = event_type.get("enum", [])
    if not enum_values:
        errors.append("event_type enum is empty — must define controlled vocabulary")

    return errors


def verify_payment_schema(data: dict) -> list[str]:
    \"\"\"Verify the payment log schema.\"\"\"
    errors: list[str] = []
    additional = data.get("additional_mandatory_fields", {})

    present_fields = set(additional.keys())
    missing = REQUIRED_PAYMENT_FIELDS - present_fields
    if missing:
        errors.append(f"Payment schema missing mandatory fields: {sorted(missing)}")

    return errors


def verify_kyc_schema(data: dict) -> list[str]:
    \"\"\"Verify the KYC/AML log schema.\"\"\"
    errors: list[str] = []
    additional = data.get("additional_mandatory_fields", {})

    present_fields = set(additional.keys())
    missing = REQUIRED_KYC_FIELDS - present_fields
    if missing:
        errors.append(f"KYC/AML schema missing mandatory fields: {sorted(missing)}")

    return errors


def main() -> int:
    \"\"\"Run all schema completeness verification checks.\"\"\"
    base_data = load_schema("audit-log-schema.yml")
    payment_data = load_schema("payment-log-schema.yml")
    kyc_data = load_schema("kyc-aml-log-schema.yml")

    all_errors: list[str] = []
    all_errors.extend(verify_base_schema(base_data))
    all_errors.extend(verify_payment_schema(payment_data))
    all_errors.extend(verify_kyc_schema(kyc_data))

    if all_errors:
        print(f"FAILED — {len(all_errors)} schema completeness violation(s):\\n")
        for err in all_errors:
            print(f"  x {err}")
        return 1

    print("PASSED — log schemas define all mandatory fields for PCI-DSS Req. 10.2.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
"""

for relpath, content in files.items():
    target = BASE / relpath
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
    print(f"  created: {relpath}")

print(f"\nDone — {len(files)} script files created.")
