#!/usr/bin/env bash
# test_check_workspace_execution_mode.sh — regression tests for the execution-mode gate.
#
# Fixtures are the JSON:API shapes measured live on 2026-10-12 against
# GET /api/v2/workspaces/ws-w6NSnTXXmYgh78Su (execution-mode "remote") and the
# documented "local"/"agent" values — not guesses.
#
# The negative controls are the point: a gate that only ever sees the passing
# shape has not been shown to detect the hang it exists to prevent (AGENTS.md §7).
#
# Usage: bash tests/test_check_workspace_execution_mode.sh
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GATE="$ROOT/scripts/check_workspace_execution_mode.sh"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

pass=0
fail=0

# assert <expected-exit> <fixture-name> [expected-mode-arg] <<'JSON'
assert() {
  local want="$1" name="$2" mode_arg="${3:-}" f="$TMP/$2.json" got
  cat > "$f"
  if [ -n "$mode_arg" ]; then
    bash "$GATE" "$f" "$mode_arg" >"$TMP/$name.out" 2>&1
  else
    bash "$GATE" "$f" >"$TMP/$name.out" 2>&1
  fi
  got=$?
  if [ "$got" -eq "$want" ]; then
    printf 'ok   %-32s exit=%s\n' "$name" "$got"
    pass=$((pass + 1))
  else
    printf 'FAIL %-32s want exit=%s got=%s\n' "$name" "$want" "$got"
    sed 's/^/       /' "$TMP/$name.out"
    fail=$((fail + 1))
  fi
}

# ── Must be ALLOWED (exit 0) ─────────────────────────────────────────────────
assert 0 local-mode <<'JSON'
{"data":{"id":"ws-w6NSnTXXmYgh78Su","type":"workspaces","attributes":{
  "name":"jolarca-control","execution-mode":"local","resource-count":35,
  "terraform-version":"1.16.5"}}}
JSON

# ── Must be REFUSED (exit 1) — the negative controls ─────────────────────────
assert 1 remote-mode-is-refused <<'JSON'
{"data":{"id":"ws-w6NSnTXXmYgh78Su","type":"workspaces","attributes":{
  "name":"jolarca-control","execution-mode":"remote","resource-count":35,
  "terraform-version":"1.16.5"}}}
JSON

assert 1 agent-mode-is-refused <<'JSON'
{"data":{"id":"ws-y","type":"workspaces","attributes":{"execution-mode":"agent","agent-pool-id":"apool-z"}}}
JSON

# Refusal must name the mechanism, not just the code — the operator reads this
# output on a red pipeline at speed. Read into a variable rather than piping
# into `grep -q`: with pipefail the writer dies of SIGPIPE when grep exits on
# first match, and the pipeline then reports 141 — a false failure.
refusal_out="$(bash "$GATE" "$TMP/remote-mode-is-refused.json" 2>&1 || true)"
if grep -q 'execution-mode":"local' <<< "$refusal_out"; then
  printf 'ok   %-32s\n' "refusal-prints-fix"
  pass=$((pass + 1))
else
  printf 'FAIL %-32s refusal did not print the PATCH fix\n' "refusal-prints-fix"
  fail=$((fail + 1))
fi

# The second argument overrides the expected mode, so the same gate can assert a
# workspace that is deliberately kept remote instead of local.
bash "$GATE" "$TMP/remote-mode-is-refused.json" remote \
  >"$TMP/arg-override.out" 2>&1
arg_rc=$?
if [ "$arg_rc" -eq 0 ]; then
  printf 'ok   %-32s exit=0\n' "expected-mode-arg-override"
  pass=$((pass + 1))
else
  printf 'FAIL %-32s want exit=0 got=%s (second arg must override the default)\n' \
    "expected-mode-arg-override" "$arg_rc"
  sed 's/^/       /' "$TMP/arg-override.out"
  fail=$((fail + 1))
fi

# ── Cannot-check must NEVER be safe (exit 2) ─────────────────────────────────
assert 2 invalid-json <<'JSON'
{"data": {"attributes": {"execution-mode": "local"
JSON

assert 2 api-error-payload <<'JSON'
{"errors":[{"status":"404","title":"not found"}]}
JSON

assert 2 null-execution-mode <<'JSON'
{"data":{"id":"ws-z","type":"workspaces","attributes":{"execution-mode":null}}}
JSON

assert 2 missing-attributes <<'JSON'
{"data":{"id":"ws-z","type":"workspaces"}}
JSON

assert 2 empty-object <<'JSON'
{}
JSON

: > "$TMP/empty.json"
bash "$GATE" "$TMP/empty.json" >/dev/null 2>&1
if [ $? -eq 2 ]; then
  printf 'ok   %-32s exit=2\n' "empty-response-refused"
  pass=$((pass + 1))
else
  printf 'FAIL %-32s want exit=2\n' "empty-response-refused"
  fail=$((fail + 1))
fi

bash "$GATE" "$TMP/does-not-exist.json" >/dev/null 2>&1
if [ $? -eq 2 ]; then
  printf 'ok   %-32s exit=2\n' "missing-response-refused"
  pass=$((pass + 1))
else
  printf 'FAIL %-32s want exit=2\n' "missing-response-refused"
  fail=$((fail + 1))
fi

bash "$GATE" >/dev/null 2>&1
if [ $? -eq 2 ]; then
  printf 'ok   %-32s exit=2\n' "no-argument-refused"
  pass=$((pass + 1))
else
  printf 'FAIL %-32s want exit=2\n' "no-argument-refused"
  fail=$((fail + 1))
fi

echo
echo "workspace-execution-mode tests: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
