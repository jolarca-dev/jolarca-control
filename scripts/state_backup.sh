#!/usr/bin/env bash
# state_backup.sh — encrypted off-host backup of Terraform state (D-02).
#
# jolarca-control — marketplace (jolarca-dev) governance control plane.
# SOC 2 CC7.1 / ISO 27001 A.8.13 / GDPR Art.32(1)(c) — 3-2-1 rule.
#
# WHAT THIS DOES
#   1. Verifies terraform.tfstate exists and is valid JSON.
#   2. Computes SHA-256 digest of the state file.
#   3. Encrypts with age (public key from STATE_BACKUP_PUBKEY env var or
#      the file at .state-backup-pubkey.txt — public key, safe to commit).
#   4. Writes the encrypted backup to the designated off-host path.
#   5. Records the backup in the backup log with hash, timestamp, size.
#
# WHAT THIS DOES NOT DO
#   - Does NOT push to a remote repository (the off-host path IS the remote).
#   - Does NOT decrypt or restore (see docs/runbooks/state-restore.md).
#   - Does NOT manage key rotation (see docs/security/key-custody.md).
#
# PREREQUISITES
#   - age installed (https://github.com/FiloSottile/age)
#   - STATE_BACKUP_PUBKEY env var set, OR .state-backup-pubkey.txt present
#   - BACKUP_DEST env var set (off-host directory, e.g. mounted volume or NFS)
#
# EXIT CODES
#   0  backup successful, log entry written
#   1  backup failed (missing prerequisites, invalid state, encryption error)
#
# Usage: scripts/state_backup.sh
#        BACKUP_DEST=/mnt/backup scripts/state_backup.sh
#        STATE_BACKUP_PUBKEY="age1..." BACKUP_DEST=/backup scripts/state_backup.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATE_FILE="$REPO_ROOT/terraform.tfstate"
BACKUP_LOG="$REPO_ROOT/docs/backup-log.tsv"

# ── Prerequisites ─────────────────────────────────────────────────────────────
command -v age >/dev/null 2>&1 || {
  echo "ERROR: age is not installed. Install: https://github.com/FiloSottile/age" >&2
  exit 1
}

[ -f "$STATE_FILE" ] || {
  echo "ERROR: terraform.tfstate not found at $STATE_FILE" >&2
  echo "  Run 'terraform init' first, or check that the state migration has not" >&2
  echo "  moved the state to a remote backend." >&2
  exit 1
}

# Validate JSON
python3 -c "import json, sys; json.load(open(sys.argv[1]))" "$STATE_FILE" 2>/dev/null || {
  echo "ERROR: terraform.tfstate is not valid JSON" >&2
  exit 1
}

# Resolve public key
pubkey="${STATE_BACKUP_PUBKEY:-}"
if [ -z "$pubkey" ] && [ -f "$REPO_ROOT/.state-backup-pubkey.txt" ]; then
  pubkey="$(cat "$REPO_ROOT/.state-backup-pubkey.txt")"
fi
[ -n "$pubkey" ] || {
  echo "ERROR: no age public key provided." >&2
  echo "  Set STATE_BACKUP_PUBKEY or create .state-backup-pubkey.txt" >&2
  echo "  See docs/security/key-custody.md for key generation procedure." >&2
  exit 1
}

# Resolve destination
dest="${BACKUP_DEST:-}"
[ -n "$dest" ] || {
  echo "ERROR: BACKUP_DEST is not set." >&2
  echo "  Set BACKUP_DEST to an off-host directory (mounted volume, NFS, etc.)" >&2
  exit 1
}
[ -d "$dest" ] || {
  echo "ERROR: backup destination does not exist: $dest" >&2
  exit 1
}

# ── Create backup ─────────────────────────────────────────────────────────────
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
digest="$(sha256sum "$STATE_FILE" | cut -d' ' -f1)"
encrypted_name="terraform.tfstate.${timestamp}.age"
encrypted_path="$dest/$encrypted_name"

age -r "$pubkey" -o "$encrypted_path" "$STATE_FILE" || {
  echo "ERROR: age encryption failed" >&2
  exit 1
}

encrypted_size="$(stat -c%s "$encrypted_path" 2>/dev/null || stat -f%z "$encrypted_path")"
state_size="$(stat -c%s "$STATE_FILE" 2>/dev/null || stat -f%z "$STATE_FILE")"

# ── Log entry ─────────────────────────────────────────────────────────────────
# TSV format: timestamp  state_sha256  state_size  encrypted_size  encrypted_path
if [ ! -f "$BACKUP_LOG" ]; then
  printf 'timestamp\tstate_sha256\tstate_size\tencrypted_size\tencrypted_path\n' > "$BACKUP_LOG"
fi
printf '%s\t%s\t%s\t%s\t%s\n' \
  "$timestamp" "$digest" "$state_size" "$encrypted_size" "$encrypted_path" \
  >> "$BACKUP_LOG"

echo "BACKUP OK"
echo "  timestamp:      $timestamp"
echo "  state SHA-256:  $digest"
echo "  state size:     $state_size bytes"
echo "  encrypted size: $encrypted_size bytes"
echo "  encrypted path: $encrypted_path"
echo "  log entry:      $BACKUP_LOG"
