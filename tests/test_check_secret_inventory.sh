#!/usr/bin/env bash
# tests/test_check_secret_inventory.sh — negative controls for the credential expiry gate.
#
# jolarca-control — marketplace (jolarca-dev) governance control plane.
# SOC 2 CC6.1 / CC7.1 · PCI-DSS 8.3.1 · ISO/IEC 27001 A.5.17, A.8.25
#
# WHY THIS FILE EXISTS (D-80). scripts/check_secret_inventory.sh landed on 2026-10-20 with
# no fixture and no invocation, defaulting to docs/SECRETS_INVENTORY.md — a path that has
# never existed in this repository. Run as documented it exited 2 forever; wired to nothing,
# that verdict was never read. Its own register had meanwhile stated that an `unknown`
# expiry means "the gate is red by design" (docs/security/key-custody.md), so the intended
# fail-closed signal was swallowed twice over: a dead pointer, then absence.
#
# The last case is the regression that matters most and it asserts only that the gate is
# NOT unable to verify: the register's contents legitimately change when a credential is
# rotated, so pinning 0 or 1 here would make this fixture the thing that goes stale.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GATE="$REPO_ROOT/scripts/check_secret_inventory.sh"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

pass=0
fail=0

# reg <file> <rows...> — a register shaped like the real one: header row, separator, data.
reg() {
  local f="$1"
  shift
  printf '| Credential | Expires | Rotation | Last verified | Notes |\n' > "$f"
  printf '|---|---|---|---|---|\n' >> "$f"
  while [ $# -gt 0 ]; do
    printf '| %s | %s | manual | 2026-10-20 | fixture |\n' "$1" "$2" >> "$f"
    shift 2
  done
}

# expect <want-code> <case-name> <register-file-or-absent> [extra args...]
expect() {
  local want="$1" name="$2" file="$3"
  shift 3
  local out code
  out="$(env WARN_DAYS="${WARN_DAYS_OVERRIDE:-14}" bash "$GATE" "$file" "$@" 2>&1)"
  code=$?
  if [ "$code" -eq "$want" ]; then
    printf 'ok   %-34s exit=%s\n' "$name" "$code"
    pass=$((pass + 1))
  else
    printf 'FAIL %-34s want exit=%s got exit=%s\n' "$name" "$want" "$code"
    printf '     output: %s\n' "$(printf '%s' "$out" | tr '\n' ' ' | cut -c1-180)"
    fail=$((fail + 1))
  fi
  LAST_OUT="$out"
}

contains() {
  local needle="$1" name="$2"
  if printf '%s' "$LAST_OUT" | grep -q "$needle"; then
    printf 'ok   %-34s\n' "$name"
    pass=$((pass + 1))
  else
    printf 'FAIL %-34s output lacks %s\n' "$name" "$needle"
    fail=$((fail + 1))
  fi
}

# ── Pass: dated credentials comfortably ahead ────────────────────────────────
GOOD="$TMP/good.md"; reg "$GOOD" "admin token" "2099-01-01" "read-only PAT" "2027-06-01"
expect 0 healthy-register "$GOOD"

# ── Refusals (exit 1): the states a rotation gate exists to catch ────────────
EXPIRED_DATE="$(date -u -d '-30 days' +%Y-%m-%d)"
EXPIRED="$TMP/expired.md"; reg "$EXPIRED" "old PAT" "$EXPIRED_DATE"
expect 1 expired-credential-is-a-finding "$EXPIRED"
contains "EXPIRED" names-the-expiry-in-the-verdict

# The date is computed, never hardcoded: a fixed "soon" row silently becomes a far row as
# the clock moves, and the case would stop testing anything (the D-46 stale-window class).
SOON_DATE="$(date -u -d '+7 days' +%Y-%m-%d)"
SOON="$TMP/soon.md"; reg "$SOON" "rotating PAT" "$SOON_DATE"
expect 1 within-warning-window-is-a-finding "$SOON"
contains "rotate now" tells-the-operator-what-to-do

UNKNOWN="$TMP/unknown.md"; reg "$UNKNOWN" "TFC token" "unknown"
expect 1 unknown-expiry-is-a-finding "$UNKNOWN"
contains "expiry unknown" refuses-to-pad

# A row far enough out to pass at 14 days must fail at 400: the window is a parameter,
# not a constant dressed up as policy.
env WARN_DAYS=400 bash "$GATE" "$GOOD" > "$TMP/w.out" 2>&1
if [ $? -eq 1 ] && grep -q "expires in" "$TMP/w.out"; then
  printf 'ok   %-34s\n' "warn-window-is-respected"
  pass=$((pass + 1))
else
  printf 'FAIL %-34s WARN_DAYS=400 did not refuse a 2027 row\n' "warn-window-is-respected"
  fail=$((fail + 1))
fi

# ── Non-date-enforceable rows: notice or warning, never silence ─────────────
NEVER="$TMP/never.md"; reg "$NEVER" "root age key" "never"
expect 0 root-key-row-is-a-notice "$NEVER"
contains "root-key row" says-why-it-is-not-date-enforced

PLACEHOLDER="$TMP/placeholder.md"; reg "$PLACEHOLDER" "session token" "2099-12-31"
expect 0 placeholder-is-a-warning "$PLACEHOLDER"
contains "no-server-side-expiry" does-not-read-as-clean

# ── Cannot verify (exit 2): never a silent pass ─────────────────────────────
expect 2 missing-register-cannot-verify "$TMP/absent.md"

NOCOL="$TMP/nocol.md"
printf '| Credential | Notes |\n|---|---|\n| x | y |\n' > "$NOCOL"
expect 2 register-without-expires-column "$NOCOL"

EMPTY="$TMP/empty.md"
printf '| Credential | Expires | Rotation |\n|---|---|---|\n' > "$EMPTY"
expect 2 header-only-register-is-not-a-pass "$EMPTY"

JUNK="$TMP/junk.md"; reg "$JUNK" "typo row" "next tuesday"
expect 2 unparseable-date-cannot-verify "$JUNK"

# ── The D-80 regression: the default pointer must resolve ───────────────────
# Run with NO argument from the repository root, exactly as CI and an operator run it: the
# default is a relative path, so this is also the check that the path is repo-rooted.
# Before the fix this printed "docs/SECRETS_INVENTORY.md not readable" and exited 2 —
# permanently, invisibly.
DEFAULT_OUT="$(cd "$REPO_ROOT" && bash "$GATE" 2>&1)"
DEFAULT_CODE=$?
if [ "$DEFAULT_CODE" -ne 2 ]; then
  printf 'ok   %-34s exit=%s\n' "default-path-is-alive" "$DEFAULT_CODE"
  pass=$((pass + 1))
else
  printf 'FAIL %-34s default path still cannot be read\n' "default-path-is-alive"
  printf '     output: %s\n' "$(printf '%s' "$DEFAULT_OUT" | tr '\n' ' ' | cut -c1-180)"
  fail=$((fail + 1))
fi
if printf '%s' "$DEFAULT_OUT" | grep -q "SECRETS_INVENTORY"; then
  printf 'FAIL %-34s still citing the dead path\n' "no-dead-pointer-remains"
  fail=$((fail + 1))
else
  printf 'ok   %-34s\n' "no-dead-pointer-remains"
  pass=$((pass + 1))
fi

# And the cited file must actually exist in git, not merely resolve at runtime.
if [ -r "$REPO_ROOT/docs/security/key-custody.md" ]; then
  printf 'ok   %-34s\n' "register-file-exists"
  pass=$((pass + 1))
else
  printf 'FAIL %-34s register file missing\n' "register-file-exists"
  fail=$((fail + 1))
fi

echo
echo "secret-inventory tests: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
