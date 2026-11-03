#!/usr/bin/env bash
# hash_evidence.sh — assemble and hash evidence files into the registry.
#
# jolarca-control — marketplace (jolarca-dev) governance control plane.
# SOC 2 CC4.1 / ISO 27001 A.5.31 / PCI-DSS 12.10.1
#
# WHAT THIS DOES
#   1. Enumerates the TRACKED tree (git ls-files) and keeps only the hashed evidence
#      directories and extensions.
#   2. Computes SHA-256 for each file.
#   3. Writes/updates docs/evidence-registry.csv with file, hash, date.
#   4. Flags files that have changed since last registration (hash mismatch).
#   5. Flags registered paths whose file no longer exists (the reverse check).
#
# USAGE
#   scripts/hash_evidence.sh                    # register all evidence files
#   scripts/hash_evidence.sh --check            # verify existing registrations
#
# EXIT CODES
#   0  all hashes match AND every registered path still exists
#   1  findings — a hash mismatch, an unregistered file, or a registered file
#      that has been deleted
#   2  could not verify — no usable committed baseline, nothing at all was compared,
#      or the tracked tree could not be enumerated. NEVER treated as a pass.
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

# ── Enumerate the TRACKED tree, not the working tree ───────────────────────
# Two independent reasons this is the only sound input:
#  1. A registry row must name a file the repository CONTAINS. Hashing whatever sits on
#     disk let `make evidence-register` attest files that were never committed —
#     measured here: 26 of 72 rows named such files, and CI, which only ever sees the
#     committed tree, scanned 46 files and reported OK over 26 vacuous attestations
#     (FA-control-10). The register is an assertion about the repository, so the
#     repository's index is the only honest source of its scope.
#  2. scripts/check_findings_register.py already scopes itself to `git ls-files` for the
#     same reason: a verdict must not depend on incidental local state (§7).
# Not a git repo, or an empty index, is exit 2 — could not verify, never a pass (§3).
if ! git -C "$REPO_ROOT" rev-parse --git-dir >/dev/null 2>&1; then
  echo "ERROR: $REPO_ROOT is not a git repository." >&2
  echo "Evidence is enumerated from the tracked tree, so nothing can be verified here." >&2
  exit 2
fi
TRACKED_LIST="$(mktemp)"
trap 'rm -f "$TRACKED_LIST"' EXIT
if ! git -C "$REPO_ROOT" ls-files -z > "$TRACKED_LIST"; then
  echo "ERROR: git ls-files failed; the tracked tree cannot be enumerated." >&2
  exit 2
fi
if [ ! -s "$TRACKED_LIST" ]; then
  echo "ERROR: git ls-files returned no paths — nothing tracked to register or verify." >&2
  exit 2
fi

# ── Initialise registry (register mode only) ─────────────────────────────────
# Deliberately not created in --check mode: a leftover .csv.new is an untracked
# artifact that can be committed by accident.
if [ "$check_mode" -eq 0 ]; then
  printf 'file,sha256,registered_date\n' > "${REGISTRY}.new"
fi

mismatches=0
missing=0
total=0

for dir in "${EVIDENCE_DIRS[@]}"; do
  while IFS= read -r -d '' rel_path; do
    # The extension set is the hashable surface of the evidence dirs; a .txt or .tsv
    # probe is retained on disk but is outside it (that gap is FA-cross-04, and the
    # .md wrappers exist precisely because this filter decides what is tamper-evident).
    case "$rel_path" in
      "$dir"/*.yml | "$dir"/*.md | "$dir"/*.sh | "$dir"/*.py | "$dir"/*.tf) ;;
      *) continue ;;
    esac
    file="$REPO_ROOT/$rel_path"
    # In the index but not on disk is the deletion case, reported by the reverse pass
    # below — skipping it here keeps the two verdicts from double-counting one defect.
    [ -f "$file" ] || continue
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
  done < "$TRACKED_LIST"
done

# ── Reverse pass: every registered path must still name a file ───────────────
# The loop above only ever visits files that exist, so it structurally cannot see
# a registered path whose file was deleted. Measured by experiment before this
# block existed: register a file, delete it, run --check →
# "0 files scanned, 0 mismatches / OK: all registered evidence hashes match",
# exit 0. Tamper-evidence has to survive DELETION, not only modification, or the
# cheapest way to pass the control is to remove what it covers (FA-control-01).
if [ "$check_mode" -eq 1 ]; then
  while IFS= read -r registered_path; do
    [ -n "$registered_path" ] || continue
    if [ ! -f "$REPO_ROOT/$registered_path" ]; then
      echo "MISSING:      $registered_path"
      missing=$((missing + 1))
    fi
  done < <(tail -n +2 "$REGISTRY" | cut -d, -f1)
  mismatches=$((mismatches + missing))
fi

if [ "$check_mode" -eq 1 ]; then
  echo ""
  echo "Evidence check: $total files scanned, $mismatches mismatches"
  # Scanning nothing proves nothing. A run that compared zero files is "could not
  # verify", not a pass — the exit-2 half of the three-valued convention (AGENTS.md
  # §3), which is what made the pre-fix "0 files scanned / OK" reading so dangerous.
  if [ "$total" -eq 0 ] && [ "$missing" -eq 0 ]; then
    echo "CANNOT VERIFY: no evidence files were found under the hashed directories." >&2
    echo "Nothing was compared, so nothing is proven. Refusing to report OK." >&2
    exit 2
  fi
  if [ "$mismatches" -gt 0 ]; then
    if [ "$missing" -gt 0 ]; then
      echo "FAIL: $missing registered evidence file(s) no longer exist. Restore the"
      echo "file or re-register — a registry row with no file behind it is a finding,"
      echo "never a pass. Deleting evidence must not be able to clear the control."
    fi
    echo "FAIL: evidence has changed since registration. Re-run without --check to update."
    exit 1
  fi
  echo "OK: all registered evidence hashes match, and every registered file exists"
  exit 0
fi

# ── Finalise registry ─────────────────────────────────────────────────────────
mv "${REGISTRY}.new" "$REGISTRY"
echo "Evidence registry updated: $total files registered in $REGISTRY"
