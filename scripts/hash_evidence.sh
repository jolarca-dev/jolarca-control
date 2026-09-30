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
#   2  could not verify — no usable committed baseline. NEVER treated as a pass.
#      Mirrors scripts/check_plan_safety.sh, which separates "safe" from "cannot
#      check" for the same reason (D-22/D-23).
#
# THE BASELINE MUST BE COMMITTED
#   --check only means something if docs/evidence-registry.csv is under version
#   control. Regenerating the registry from the working tree and then verifying
#   it against itself always passes, which is how this control came to be
#   tautological: it reported OK for every input, including tampered evidence.
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

# ── Preconditions ────────────────────────────────────────────────────────────
# In --check mode a usable baseline must already exist. "No baseline" is not
# "no changes": without something to compare against, nothing has been proven.
if [ "$check_mode" -eq 1 ]; then
  if [ ! -f "$REGISTRY" ] || [ ! -r "$REGISTRY" ]; then
    echo "ERROR: no readable evidence registry at $REGISTRY" >&2
    echo "Cannot verify evidence against a baseline that does not exist." >&2
    echo "Fix: run 'bash scripts/hash_evidence.sh', then COMMIT the registry." >&2
    exit 2
  fi
  if [ "$(wc -l < "$REGISTRY")" -le 1 ]; then
    echo "ERROR: evidence registry holds no entries: $REGISTRY" >&2
    echo "A header-only registry proves nothing was registered, not that" >&2
    echo "everything matched. Refusing to report OK." >&2
    exit 2
  fi
fi

# ── Initialise registry (register mode only) ─────────────────────────────────
# Deliberately not created in --check mode: a leftover .csv.new is an untracked
# artifact that can be committed by accident.
if [ "$check_mode" -eq 0 ]; then
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
      # Exact field comparison, not a regex. rel_path contains '.' and '/', both
      # regex metacharacters, so a prefix pattern can match the wrong row or none
      # at all — the same bug class that made the D-22 plan gate inert.
      existing_hash="$(awk -F, -v target="$rel_path" '$1 == target { h = $2 } END { print h }' "$REGISTRY")"
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
      # Preserve the original registered_date when the hash is unchanged. A full
      # re-registration must not restate history: the column has to keep meaning
      # "when this hash entered the baseline", otherwise every row carries the
      # date of the last run and nobody can tell what actually changed.
      reg_date="$(date -u +%Y-%m-%d)"
      if [ -f "$REGISTRY" ]; then
        prior="$(awk -F, -v target="$rel_path" '$1 == target { h = $2; d = $3 } END { print h "," d }' "$REGISTRY")"
        if [ "${prior%,*}" = "$current_hash" ] && [ -n "${prior##*,}" ]; then
          reg_date="${prior##*,}"
        fi
      fi
      printf '%s,%s,%s\n' "$rel_path" "$current_hash" "$reg_date" >> "${REGISTRY}.new"
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
