#!/usr/bin/env bash
# check_fleet_separation.sh — ADR-0004 guard: marketplace fleet integrity.
#
# The GitHub estate hosts TWO projects that must never mix (ADR-0004):
#   - marketplace       : jolarca*  (this control plane's fleet, PCI-DSS scope)
#   - mission platform  : jol-*     (governed by jol-control, out of scope here)
#
# This guard FAILS when:
#   R1  an allow-list entry doesn't match jolarca* naming (defense in depth
#       next to the Terraform precondition in repositories.tf), or
#   R2  an org repo named jolarca* is NOT in the repos/*.yml allow-list —
#       out-of-band marketplace repo creation is an INCIDENT: import into
#       Terraform within 48h (ADR-0004 R2), or
#   R3  a mission-platform (jol-*) entry has been added to this allow-list, or
#   4.  an allow-list repo is missing from the org (drift / deletion).
#
# The org community-health repo `.github` is intentionally out of scope: it is
# declared in health-repo.tf, not in the allow-list, and it does not carry the
# jolarca prefix.
#
# Usage: scripts/check_fleet_separation.sh
# Auth:  gh CLI token (GH_TOKEN / GITHUB_TOKEN) with org repo read.
#
# Bootstrap: while jolarca-control itself is still being created, check 4 would
# fail on a declared-but-not-yet-existing repo. Pass BOTH
#   ALLOW_MISSING="name1 name2"   ALLOW_MISSING_UNTIL="YYYY-MM-DD"
# to whitelist specific names for that window. The date is mandatory and
# enforced: an undated or expired exemption exits 2 rather than being honoured,
# because an open-ended bypass of the ADR-0004 R2 out-of-band-creation detector
# is worse than no detector at all (D-24 — the exemption used to be documented
# as "time-boxed" while the code accepted it indefinitely). The script also
# refuses to whitelist a name that is not in the allow-list, and prints a loud
# warning so the exemption cannot pass unnoticed in CI logs.
#
# Exit codes: 0 clean · 1 violation · 2 the guard itself could not run.
#
# Supersedes jolarca-infrastructure/scripts/check-fleet-separation.sh, which
# parsed the fleet map out of terraform/modules/github-org/variables.tf. The
# fleet map now lives in repos/*.yml.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPOS_DIR="$REPO_ROOT/repos"
ORG="${JOLARCA_CONTROL_ORG:-jolarca-dev}"
ALLOW_MISSING="${ALLOW_MISSING:-}"
ALLOW_MISSING_UNTIL="${ALLOW_MISSING_UNTIL:-}"

# ── Validate the bootstrap exemption window once, up front ───────────────────
allow_missing_active=0
if [ -n "$ALLOW_MISSING" ]; then
  if [ -z "$ALLOW_MISSING_UNTIL" ]; then
    echo "ERROR: ALLOW_MISSING='$ALLOW_MISSING' is set without ALLOW_MISSING_UNTIL." >&2
    echo "  An undated exemption is a permanent bypass of the ADR-0004 R2" >&2
    echo "  out-of-band-creation detector. Refusing to honour it." >&2
    exit 2
  fi
  if ! printf '%s' "$ALLOW_MISSING_UNTIL" | grep -qE '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'; then
    echo "ERROR: ALLOW_MISSING_UNTIL must be YYYY-MM-DD, got '$ALLOW_MISSING_UNTIL'." >&2
    exit 2
  fi
  today="$(date -u +%Y-%m-%d)"
  # ISO-8601 dates compare correctly as strings.
  if [[ ! "$ALLOW_MISSING_UNTIL" > "$today" ]]; then
    echo "ERROR: ALLOW_MISSING exemption expired on $ALLOW_MISSING_UNTIL (today: $today)." >&2
    echo "  Remove ALLOW_MISSING and fix the underlying drift, or record a new" >&2
    echo "  time-boxed exception in docs/drift-findings.md." >&2
    exit 2
  fi
  allow_missing_active=1
  echo "WARNING: ALLOW_MISSING='$ALLOW_MISSING' honoured until $ALLOW_MISSING_UNTIL (today: $today)."
fi

if [ ! -d "$REPOS_DIR" ]; then
  echo "ERROR: allow-list directory not found: $REPOS_DIR" >&2
  exit 1
fi

# Fleet = the `name:` field of every allow-list entry. Derived from the YAML
# rather than the filename so a mismatch between the two is caught (R1 below
# compares them).
fleet="$(sed -nE 's/^name:[[:space:]]*([A-Za-z0-9._-]+)[[:space:]]*$/\1/p' "$REPOS_DIR"/*.yml | sort -u)"
if [ -z "$fleet" ]; then
  echo "ERROR: could not parse any fleet entries from $REPOS_DIR/*.yml" >&2
  exit 1
fi

status=0

# ── Filename/name coherence ──────────────────────────────────────────────────
for f in "$REPOS_DIR"/*.yml; do
  base="$(basename "$f" .yml)"
  n="$(sed -nE 's/^name:[[:space:]]*([A-Za-z0-9._-]+)[[:space:]]*$/\1/p' "$f" | head -1)"
  if [ "$base" != "$n" ]; then
    echo "VIOLATION: $f declares name='$n' but the filename is '$base'."
    status=1
  fi
done

# ── R1 + R3: naming and mission/marketplace separation ──────────────────────
while IFS= read -r name; do
  [ -z "$name" ] && continue
  case "$name" in
    jolarca|jolarca-*) ;;
    jol-*|jol)
      echo "VIOLATION: '$name' is a mission-platform repo in the marketplace allow-list (ADR-0004 R3)."
      echo "  -> mission repos are governed by jol-control; remove this entry."
      status=1
      ;;
    *)
      echo "VIOLATION: fleet entry '$name' doesn't match jolarca* naming (ADR-0004 R1)."
      status=1
      ;;
  esac
done <<< "$fleet"

# ── Live org listing (read-only) ────────────────────────────────────────────
command -v gh >/dev/null 2>&1 || { echo "ERROR: gh CLI is required" >&2; exit 1; }
org_fleet="$(gh api "orgs/$ORG/repos" --paginate -q '.[].name' | grep '^jolarca' | sort)"

# ── R2: out-of-band marketplace repos (in org, absent from allow-list) ──────
while IFS= read -r name; do
  [ -z "$name" ] && continue
  if ! grep -qx "$name" <<< "$fleet"; then
    echo "VIOLATION: org repo '$name' is jolarca* but NOT in the repos/*.yml allow-list."
    echo "  -> out-of-band creation is an incident (ADR-0004 R2): import within 48h."
    status=1
  fi
done <<< "$org_fleet"

# ── 4: allow-list repos missing from the org (drift / deletion) ─────────────
while IFS= read -r name; do
  [ -z "$name" ] && continue
  if ! grep -qx "$name" <<< "$org_fleet"; then
    if [ "$allow_missing_active" -eq 1 ] && grep -qw "$name" <<< "$ALLOW_MISSING"; then
      echo "WARNING: '$name' is missing from org '$ORG' but ALLOW_MISSING-exempted until $ALLOW_MISSING_UNTIL."
      continue
    fi
    echo "VIOLATION: allow-list repo '$name' not found in org '$ORG'."
    status=1
  fi
done <<< "$fleet"

if [ "$status" -eq 0 ]; then
  echo "FLEET SEPARATION OK: org jolarca* set == repos/*.yml allow-list ($(grep -c . <<< "$fleet") repos)."
fi
exit "$status"
