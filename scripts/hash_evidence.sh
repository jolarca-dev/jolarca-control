#!/usr/bin/env bash
# hash_evidence.sh — assemble and hash evidence files into the registry.
#
# jolarca-control — marketplace (jolarca-dev) governance control plane.
# SOC 2 CC4.1 / ISO 27001 A.5.31 / PCI-DSS 12.10.1
#
# WHAT THIS DOES
#   1. Scans docs/adr/, audit/, policy/, repos/ for evidence files.
#   2. Computes SHA-256 for each file.
#   3. Writes/updates docs/evidence-registry.csv with file, hash, date.
#   4. Flags files that have changed since last registration (hash mismatch).
#
# USAGE
#   scripts/hash_evidence.sh                    # register all evidence files
#   scripts/hash_evidence.sh --check            # verify existing registrations
#
# EXIT CODES
#   0  all hashes match (or registration successful)
#   1  hash mismatch detected (evidence has changed since registration)
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REGISTRY="$REPO_ROOT/docs/evidence-registry.csv"

# Evidence directories — files in these dirs are audit evidence
EVIDENCE_DIRS=(
  "docs/adr"
  "audit"
  "policy"
  "repos"
  "docs/runbooks"
  "docs/security"
)

check_mode=0
if [ "${1:-}" = "--check" ]; then
  check_mode=1
fi

# ── Initialise registry ──────────────────────────────────────────────────────
if [ ! -f "$REGISTRY" ] || [ "$check_mode" -eq 0 ]; then
  printf 'file,sha256,registered_date\n' > "${REGISTRY}.new"
fi

mismatches=0
total=0

for dir in "${EVIDENCE_DIRS[@]}"; do
  target="$REPO_ROOT/$dir"
  [ -d "$target" ] || continue

  while IFS= read -r -d '' file; do
    rel_path="${file#"$REPO_ROOT"/}"
    current_hash="$(sha256sum "$file" | cut -d' ' -f1)"
    total=$((total + 1))

    if [ "$check_mode" -eq 1 ]; then
      # Look up existing hash
      existing_hash="$(grep "^${rel_path}," "$REGISTRY" 2>/dev/null | tail -1 | cut -d, -f2 || true)"
      if [ -z "$existing_hash" ]; then
        echo "UNREGISTERED: $rel_path"
        mismatches=$((mismatches + 1))
      elif [ "$current_hash" != "$existing_hash" ]; then
        echo "CHANGED:      $rel_path"
        echo "  registered: $existing_hash"
        echo "  current:    $current_hash"
        mismatches=$((mismatches + 1))
      fi
    else
      printf '%s,%s,%s\n' "$rel_path" "$current_hash" "$(date -u +%Y-%m-%d)" >> "${REGISTRY}.new"
    fi
  done < <(find "$target" -type f \( -name '*.yml' -o -name '*.md' -o -name '*.sh' -o -name '*.py' -o -name '*.tf' \) -print0 | sort -z)
done

if [ "$check_mode" -eq 1 ]; then
  echo ""
  echo "Evidence check: $total files scanned, $mismatches mismatches"
  if [ "$mismatches" -gt 0 ]; then
    echo "FAIL: evidence has changed since registration. Re-run without --check to update."
    exit 1
  fi
  echo "OK: all registered evidence hashes match"
  exit 0
fi

# ── Finalise registry ─────────────────────────────────────────────────────────
mv "${REGISTRY}.new" "$REGISTRY"
echo "Evidence registry updated: $total files registered in $REGISTRY"
