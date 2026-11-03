#!/usr/bin/env bash
# check_secret_inventory.sh — expiry gate for the secret register (metadata only).
#
# Reads the `expires` column of the machine-read table in
# docs/security/key-custody.md and fails when any dated credential is expired or
# expires within WARN_DAYS (default 14) days.
#
# PATH HISTORY (D-80): this script landed on 2026-10-20 (PR #86) defaulting to
# docs/SECRETS_INVENTORY.md, a file that has never existed in this repository. Run as
# documented it exited 2 every time, and because nothing invoked it — no Makefile target,
# no workflow step — nobody saw that. key-custody.md:33 already stated its own table is
# "the single `expires`-bearing block the gate parses", so the register was present the
# whole time and only the pointer was dead. Same class as the guard-pointer defect PR #79
# and PR #40 record: a cited path that does not exist, here in a default argument instead
# of a comment.
#
# exit 0  every dated credential expires more than WARN_DAYS days ahead
# exit 1  a credential is expired, expires within WARN_DAYS, or has expiry=unknown
# exit 2  register missing or unparseable — an unreadable gate is never a pass
#
# Rows with a 2099-* placeholder ("no server-side expiry") and `never` (root keys)
# cannot be enforced by date; they surface as warnings/notices, never as passes.
# No secrets, no network: the step must fail on its own merits, before any
# credential-dependent step can mask it.
set -u

INV="${1:-docs/security/key-custody.md}"
WARN_DAYS="${WARN_DAYS:-14}"

if [ ! -r "$INV" ]; then
  echo "::error::$INV not readable — an unreadable register is not a pass"
  exit 2
fi

# Extract the `expires` column of the register table: find the header cell, then
# emit that field of every following table row, skipping the |---| separator.
CELLS=$(awk -F'|' '
  /^[[:space:]]*\|/ {
    if (!hdr) {
      for (i = 1; i <= NF; i++) {
        g = $i; gsub(/^[ \t]+|[ \t]+$/, "", g)
        if (tolower(g) == "expires") { hdr = 1; ci = i }
      }
      next
    }
    if ($0 ~ /^[[:space:]]*\|[ :|-]+$/) next
    v = $ci; gsub(/^[ \t]+|[ \t]+$/, "", v); print v
  }
' "$INV")

if [ -z "$CELLS" ]; then
  echo "::error::no 'expires' column or no rows found in $INV — unparseable register"
  exit 2
fi

rc=0
now=$(date -u +%s)
while IFS= read -r exp; do
  [ -z "$exp" ] && continue
  case "$exp" in
    never)
      echo "::notice::root-key row: rotation is on-compromise only"
      continue ;;
    unknown)
      echo "::error::expiry unknown for a row in $INV — verify and record it"
      rc=1
      continue ;;
    2099-*)
      echo "::warning::$exp is a no-server-side-expiry placeholder: enforce by rotation policy instead"
      continue ;;
    [0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9])
      ;; # fall through to the date math below
    *)
      echo "::error::unparseable expires value '$exp' in $INV"
      rc=2
      break ;;
  esac
  if ! e=$(date -u -d "$exp" +%s 2>/dev/null); then
    echo "::error::invalid date '$exp' in $INV"
    rc=2
    break
  fi
  days=$(( (e - now) / 86400 ))
  if [ "$days" -lt 0 ]; then
    echo "::error::credential EXPIRED $((-days)) days ago ($exp)"
    rc=1
  elif [ "$days" -le "$WARN_DAYS" ]; then
    echo "::error::credential expires in $days days (<= $WARN_DAYS): $exp — rotate now"
    rc=1
  else
    echo "ok: $exp ($days days out)"
  fi
done <<< "$CELLS"

exit "$rc"
