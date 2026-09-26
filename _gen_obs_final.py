#!/usr/bin/env python3
"""Generate jolarca-observability runbooks/, tests/, .github/, Makefile, pyproject.toml."""

from pathlib import Path

BASE = Path("/opt/jolarca/repos/jolarca-observability")
files: dict[str, str] = {}

# ── runbooks/audit-log-gap.md ─────────────────────────────────────────────────
files["runbooks/audit-log-gap.md"] = """\
# Runbook: Audit Log Gap Investigation

**Severity:** CRITICAL
**Trigger:** `AUDIT_GAP_5MIN` alert — no audit entries for 5+ minutes
**PCI-DSS:** Req. 10.5.5 (log integrity)

## Immediate Actions (0-15 minutes)

1. **Acknowledge the alert** — log the acknowledgement timestamp
2. **Check log collector health** — is the OpenTelemetry collector running?
   ```bash
   systemctl status otel-collector
   journalctl -u otel-collector --since "10 minutes ago"
   ```
3. **Check log source connectivity** — are application components emitting events?
   ```bash
   # Check if the application is running
   systemctl status jolarca-app
   # Check network connectivity to the collector
   curl -s http://localhost:4318/v1/logs  # OTLP HTTP endpoint
   ```
4. **Check log storage** — is the storage system accepting writes?
   ```bash
   # Check storage health
   curl -s https://log-storage.internal/health
   ```

## Investigation (15-60 minutes)

5. **Determine the gap window** — when did entries stop? When did they resume (if at all)?
6. **Check for deployments or changes** — was anything deployed during the gap?
   ```bash
   # Check recent deployments
   gh api repos/jolarca-dev/jolarca/deployments --jq '.[0:5]'
   ```
7. **Check system access logs** — did anyone access the log infrastructure?
8. **Check for infrastructure failures** — network partition, disk full, OOM?

## Escalation

- If the gap cannot be explained within 1 hour → escalate to org owner
- If the gap exceeds 30 minutes with no explanation → treat as potential tampering
- If evidence of unauthorized access → initiate incident response per `jolarca-security`

## Post-Incident

9. **Document the root cause** — what caused the gap?
10. **Document the duration** — how long was logging interrupted?
11. **Assess compliance impact** — were any events lost permanently?
12. **File a compliance event** — record in `jolarca-compliance`
13. **Update alerting rules** — if the gap was a false positive, adjust thresholds

## Evidence to Retain

- Collector logs for the gap window
- System metrics (CPU, memory, disk, network) for the gap window
- Deployment records for the gap window
- This completed runbook with timestamps
"""

# ── runbooks/audit-log-tampering.md ───────────────────────────────────────────
files["runbooks/audit-log-tampering.md"] = """\
# Runbook: Audit Log Tampering Response

**Severity:** CRITICAL
**Trigger:** `HASH_CHAIN_BREAK` alert — hash-chain integrity verification failed
**PCI-DSS:** Req. 10.5.5 (file-integrity monitoring)

## IMMEDIATE: Preserve Evidence (0-15 minutes)

1. **DO NOT restart, rotate, or modify log storage** — the current state is forensic evidence
2. **Acknowledge the alert** — log the acknowledgement timestamp
3. **Restrict access to log storage** — if possible, limit to read-only
4. **Notify the organization owner** — this is a potential security incident

## Investigation (15-60 minutes)

5. **Identify the affected entries** — which hash-chain position broke?
   ```bash
   python scripts/verify_integrity.py 2>&1 | tee /tmp/integrity-report.txt
   ```
6. **Determine the time window** — when was the last known-good hash? When is the first bad hash?
7. **Check access logs for the log storage system**:
   - Who accessed the storage in the time window?
   - Were there any write operations outside the collector pipeline?
   - Were there any backup/restore operations?
8. **Check system access logs** — who logged into the log storage host?
9. **Check for authorized changes** — was a backup restore or migration performed?

## Escalation Criteria

- **Confirmed unauthorized modification** → GDPR Art. 33 breach assessment
- **Cannot determine cause** → treat as potential compromise
- **Authorized change without documentation** → process failure, not security incident

## GDPR Art. 33 Assessment

If unauthorized modification is confirmed:
1. **Assess affected data subjects** — whose audit trail was modified?
2. **Assess likelihood of harm** — can the modified logs hide a data breach?
3. **72-hour notification clock** — if notifiable, the clock started at detection
4. **Document the assessment** — in `jolarca-compliance`

## Post-Incident

10. **Rebuild the hash chain** — from the last known-good entry forward
11. **Verify the rebuilt chain** — run `verify_integrity.py` again
12. **Document the root cause** — how was the modification possible?
13. **Strengthen controls** — what additional access control is needed?
14. **File a compliance event** — record in `jolarca-compliance`
"""

# ── runbooks/retention-breach.md ──────────────────────────────────────────────
files["runbooks/retention-breach.md"] = """\
# Runbook: Retention Policy Breach Response

**Severity:** HIGH
**Trigger:** `RETENTION_PREMATURE_DELETE` or `RETENTION_HOT_EXPIRED` alert
**PCI-DSS:** Req. 10.5.1 (retention)

## Immediate Actions (0-1 hour)

1. **Acknowledge the alert** — log the acknowledgement timestamp
2. **Determine the scope**:
   - Which log domain is affected?
   - What time range of logs is missing or inaccessible?
   - Was the deletion authorized?
3. **Check backup availability**:
   ```bash
   # List recent backups
   # (command depends on backup infrastructure — see jolarca-infrastructure)
   ```
4. **If logs can be restored from backup** → restore immediately
5. **If logs cannot be restored** → escalate to org owner

## Investigation (1-4 hours)

6. **Determine the cause**:
   - Was a retention policy misconfigured?
   - Was a storage system failure responsible?
   - Was the deletion deliberate and unauthorized?
7. **Check for correlated events** — does the loss coincide with any other incident?
8. **Assess compliance impact**:
   - Are the missing logs within the 12-month retention window?
   - Are they needed for any ongoing investigation?
   - Are they needed for any regulatory filing?

## Post-Incident

9. **Restore from backup** if possible
10. **Document the root cause** — what failed?
11. **Document the data loss** — what logs are permanently lost?
12. **Assess regulatory impact** — is this notifiable?
13. **Strengthen controls** — prevent recurrence
14. **File a compliance event** — record in `jolarca-compliance`
"""

# ── runbooks/audit-log-backup-restore.md ──────────────────────────────────────
files["runbooks/audit-log-backup-restore.md"] = """\
# Runbook: Audit Log Backup and Restore

**Purpose:** Restore audit logs from backup after data loss or corruption
**Related:** `audit-trail/backup/backup-policy.yml`

## Backup Verification

Before any restore, verify the backup integrity:

1. **Check backup manifest** — does the entry count match?
2. **Verify hash chain** — recompute hashes on the backup copy
3. **Check encryption** — can the backup be decrypted with the current key?

## Restore Procedure

1. **Identify the restore point** — which backup contains the needed logs?
2. **Create an isolated restore environment** — do NOT restore to production
3. **Restore the backup** to the isolated environment
4. **Verify the restored data**:
   - Hash chain integrity: `python scripts/verify_integrity.py`
   - Schema completeness: `python scripts/verify_completeness.py`
   - Entry count matches backup manifest
5. **Copy verified data** to production log storage
6. **Verify production data** — run verification scripts against production
7. **Document the restore** — record timestamps, entry counts, verification results

## Quarterly Restore Test

Per `audit-trail/backup/backup-policy.yml`, a test restore is performed quarterly:

1. Restore latest full backup to isolated environment
2. Run all verification scripts
3. Measure restore time (must be within RTO of 4 hours)
4. Record results as compliance evidence
"""

# ── tests/test_verify_retention.py ────────────────────────────────────────────
files["tests/test_verify_retention.py"] = """\
\"\"\"Tests for verify_retention.py — retention policy verification.\"\"\"
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SCRIPT = BASE_DIR / "scripts" / "verify_retention.py"


def test_retention_script_exists() -> None:
    \"\"\"The retention verification script must exist.\"\"\"
    assert SCRIPT.exists(), f"Script not found: {SCRIPT}"


def test_retention_script_runs_clean() -> None:
    \"\"\"The retention verification script must pass against current configs.\"\"\"
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True,
        text=True,
        cwd=str(BASE_DIR),
    )
    assert result.returncode == 0, (
        f"Retention verification failed:\\nstdout: {result.stdout}\\nstderr: {result.stderr}"
    )


def test_retention_policy_file_exists() -> None:
    \"\"\"The retention policy YAML must exist.\"\"\"
    policy = BASE_DIR / "audit-trail" / "retention" / "retention-policy.yml"
    assert policy.exists(), f"Retention policy not found: {policy}"
"""

# ── tests/test_verify_integrity.py ────────────────────────────────────────────
files["tests/test_verify_integrity.py"] = """\
\"\"\"Tests for verify_integrity.py — hash-chain integrity verification.\"\"\"
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SCRIPT = BASE_DIR / "scripts" / "verify_integrity.py"


def test_integrity_script_exists() -> None:
    \"\"\"The integrity verification script must exist.\"\"\"
    assert SCRIPT.exists(), f"Script not found: {SCRIPT}"


def test_integrity_script_runs_clean() -> None:
    \"\"\"The integrity verification script must pass against current configs.\"\"\"
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True,
        text=True,
        cwd=str(BASE_DIR),
    )
    assert result.returncode == 0, (
        f"Integrity verification failed:\\nstdout: {result.stdout}\\nstderr: {result.stderr}"
    )


def test_hash_chain_config_exists() -> None:
    \"\"\"The hash-chain configuration YAML must exist.\"\"\"
    config = BASE_DIR / "audit-trail" / "integrity" / "hash-chain.yml"
    assert config.exists(), f"Hash-chain config not found: {config}"
"""

# ── tests/test_verify_completeness.py ─────────────────────────────────────────
files["tests/test_verify_completeness.py"] = """\
\"\"\"Tests for verify_completeness.py — log schema completeness verification.\"\"\"
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SCRIPT = BASE_DIR / "scripts" / "verify_completeness.py"


def test_completeness_script_exists() -> None:
    \"\"\"The completeness verification script must exist.\"\"\"
    assert SCRIPT.exists(), f"Script not found: {SCRIPT}"


def test_completeness_script_runs_clean() -> None:
    \"\"\"The completeness verification script must pass against current configs.\"\"\"
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True,
        text=True,
        cwd=str(BASE_DIR),
    )
    assert result.returncode == 0, (
        f"Completeness verification failed:\\nstdout: {result.stdout}\\nstderr: {result.stderr}"
    )


def test_schema_files_exist() -> None:
    \"\"\"All schema YAML files must exist.\"\"\"
    schemas_dir = BASE_DIR / "schemas"
    assert (schemas_dir / "audit-log-schema.yml").exists()
    assert (schemas_dir / "payment-log-schema.yml").exists()
    assert (schemas_dir / "kyc-aml-log-schema.yml").exists()
"""

# ── tests/fixtures/sample-audit-entry.json ────────────────────────────────────
files["tests/fixtures/sample-audit-entry.json"] = """\
{
  "timestamp": "2026-09-26T14:30:00.000Z",
  "event_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "event_type": "admin_action",
  "actor_id": "user:jol-12345",
  "actor_type": "admin",
  "source_ip": "203.0.113.42",
  "domain": "audit",
  "severity": "info",
  "description": "Repository branch protection rule updated",
  "hash_chain": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
  "target_resource": "github:jolarca-dev/jolarca/branches/main/protection",
  "action": "update",
  "result": "success"
}
"""

# ── .github/workflows/compliance-scan.yml ─────────────────────────────────────
files[".github/workflows/compliance-scan.yml"] = """\
# ──────────────────────────────────────────────────────────────────────────────
# Compliance Scan — jolarca-observability
# ──────────────────────────────────────────────────────────────────────────────
# Runs verification scripts on every PR and weekly schedule.
# Managed by jolarca-control governance.
# ──────────────────────────────────────────────────────────────────────────────

name: compliance-scan

on:
  pull_request:
    paths:
      - 'logging/**'
      - 'alerting/**'
      - 'audit-trail/**'
      - 'schemas/**'
      - 'scripts/**'
  schedule:
    - cron: '23 3 * * 1'  # Weekly Monday 03:23 UTC
  workflow_dispatch:

permissions:
  contents: read

jobs:
  verify-retention:
    name: "Verify Retention Policy"
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683  # v4.2.2
      - uses: actions/setup-python@0b93645e9fea7318ecaed2b359559ac225c90a2b  # v5.3.0
        with:
          python-version: "3.12"
      - run: pip install -r requirements.txt
      - run: python scripts/verify_retention.py

  verify-integrity:
    name: "Verify Hash-Chain Integrity"
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683  # v4.2.2
      - uses: actions/setup-python@0b93645e9fea7318ecaed2b359559ac225c90a2b  # v5.3.0
        with:
          python-version: "3.12"
      - run: pip install -r requirements.txt
      - run: python scripts/verify_integrity.py

  verify-completeness:
    name: "Verify Log Schema Completeness"
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683  # v4.2.2
      - uses: actions/setup-python@0b93645e9fea7318ecaed2b359559ac225c90a2b  # v5.3.0
        with:
          python-version: "3.12"
      - run: pip install -r requirements.txt
      - run: python scripts/verify_completeness.py
"""

# ── .github/workflows/ci.yml ──────────────────────────────────────────────────
files[".github/workflows/ci.yml"] = """\
# ──────────────────────────────────────────────────────────────────────────────
# CI — jolarca-observability
# ──────────────────────────────────────────────────────────────────────────────
# Lint, type-check, and test on every PR.
# ──────────────────────────────────────────────────────────────────────────────

name: ci

on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  lint:
    name: "Lint & Type Check"
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683  # v4.2.2
      - uses: actions/setup-python@0b93645e9fea7318ecaed2b359559ac225c90a2b  # v5.3.0
        with:
          python-version: "3.12"
      - run: pip install -r requirements-dev.txt
      - run: ruff check scripts/ tests/
      - run: mypy --strict scripts/ tests/
      - run: yamllint -c .yamllint logging/ alerting/ audit-trail/ schemas/ compliance/
      - run: shellcheck -x scripts/*.py 2>/dev/null || true

  test:
    name: "Tests"
    runs-on: ubuntu-latest
    needs: lint
    steps:
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683  # v4.2.2
      - uses: actions/setup-python@0b93645e9fea7318ecaed2b359559ac225c90a2b  # v5.3.0
        with:
          python-version: "3.12"
      - run: pip install -r requirements.txt -r requirements-dev.txt
      - run: pytest tests/ -v --tb=short
"""

# ── requirements.txt ──────────────────────────────────────────────────────────
files["requirements.txt"] = """\
# Runtime dependencies for verification scripts
pyyaml==6.0.2
"""

# ── requirements-dev.txt ──────────────────────────────────────────────────────
files["requirements-dev.txt"] = """\
# Development dependencies — lint, type-check, test
-r requirements.txt
ruff==0.16.9
mypy==1.15.0
pytest==8.3.4
yamllint==1.35.1
"""

# ── pyproject.toml (overwrite existing) ───────────────────────────────────────
files["pyproject.toml"] = """\
[project]
name = "jolarca-observability"
version = "0.1.0"
description = "Centralized logging, alerting, audit-trail retention and log-integrity for the jolarca-dev marketplace"
requires-python = ">=3.12"
dependencies = [
    "pyyaml>=6.0.2",
]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "W", "I", "N", "UP", "S", "B", "A", "COM", "C4", "RET", "SIM", "ARG", "PTH", "RUF"]

[tool.mypy]
python_version = "3.12"
strict = true
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
python_functions = ["test_*"]
"""

# ── Makefile ──────────────────────────────────────────────────────────────────
files["Makefile"] = """\
# ──────────────────────────────────────────────────────────────────────────────
# Makefile — jolarca-observability
# ──────────────────────────────────────────────────────────────────────────────
# Compliance: SOC 2 Type II · GDPR · ISO 27001:2022 · PCI-DSS 4.0
# ──────────────────────────────────────────────────────────────────────────────

.PHONY: help setup lint test verify-all verify-retention verify-integrity verify-completeness clean

help:  ## Show this help
\t@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \\033[36m%-20s\\033[0m %s\\n", $$1, $$2}'

setup:  ## Install dependencies into .venv
\tpython3 -m venv .venv
\t.venv/bin/pip install -r requirements-dev.txt

lint:  ## Run ruff, mypy, yamllint
\t.venv/bin/ruff check scripts/ tests/
\t.venv/bin/mypy --strict scripts/ tests/
\t.venv/bin/yamllint -c .yamllint logging/ alerting/ audit-trail/ schemas/ compliance/

test:  ## Run pytest
\t.venv/bin/pytest tests/ -v --tb=short

verify-retention:  ## Verify retention policy compliance (PCI-DSS 10.5.1)
\t.venv/bin/python scripts/verify_retention.py

verify-integrity:  ## Verify hash-chain integrity config (PCI-DSS 10.5.5)
\t.venv/bin/python scripts/verify_integrity.py

verify-completeness:  ## Verify log schema completeness (PCI-DSS 10.2)
\t.venv/bin/python scripts/verify_completeness.py

verify-all: verify-retention verify-integrity verify-completeness  ## Run all verification scripts

clean:  ## Remove build artifacts
\trm -rf .venv __pycache__ .mypy_cache .ruff_cache .pytest_cache
\tfind . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
"""

for relpath, content in files.items():
    target = BASE / relpath
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
    print(f"  created: {relpath}")

print(f"\nDone — {len(files)} runbook/test/CI/build files created.")
