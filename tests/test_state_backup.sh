#!/usr/bin/env bash
# tests/test_state_backup.sh — negative controls for the state backup tool.
#
# D-02's backup half was dead for a reason nobody could see: the script wrote a
# log line only on success, and success meant "age ran", never "the bytes came
# back". These fixtures assert the properties that were missing, so a future
# regression fails here instead of during a restore. AGENTS.md §7: a gate with no
# negative control is a hypothesis.
#
# Everything here is offline: no network, no real keys, no real state. The
# unreachable-backend case points at a closed local port, and the credential
# shape is assembled at runtime so no fixture reads as a secret to gitleaks or to
# the readiness gate (L-15/L-16/L-17).
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP="$REPO_ROOT/scripts/state_backup.sh"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

pass=0
fail=0

# An ephemeral recipient + identity, generated per run and thrown away.
KEYS="$TMP/keys"; mkdir -p "$KEYS"
# age-keygen reports the public key on stderr and writes the identity to the file,
# so capture both streams here or the fixture has no recipient to test against.
PUB="$(age-keygen -o "$KEYS/id" 2>&1 | sed -n 's/^Public key: //p')"
[ -n "$PUB" ] || { echo "FATAL: age-keygen produced no public key (is age installed?)"; exit 2; }

GOOD="$TMP/good-state.json"
printf '%s\n' '{"version":4,"terraform_version":"1.16.5","serial":7,"lineage":"fixture-lineage","resources":[{"mode":"managed","name":"probe","type":"null_resource","provider":"provider[\"registry.terraform.io/hashicorp/null\"]","instances":[]}]}' > "$GOOD"
BAD="$TMP/bad-state.json"; printf '%s' '{"version":4,' > "$BAD"
DEST="$TMP/dest"; mkdir -p "$DEST"

# expect <wanted-code> <case-name> <env assignments...>
expect() {
  local want="$1" name="$2"; shift 2
  local out code
  out="$(env -i PATH="$PATH" HOME="$TMP/fakehome" \
    STATE_FILE="$GOOD" BACKUP_DEST="$DEST" STATE_BACKUP_PUBKEY="$PUB" \
    STATE_BACKUP_KEY="$KEYS/id" BACKUP_LOG="$DEST/log.tsv" \
    TF_CLI_CONFIG_FILE="$TMP/no-such-file" TFC_TOKEN="" \
    "$@" bash "$BACKUP" 2>&1)"
  code=$?
  if [ "$code" -eq "$want" ]; then
    printf 'ok   %-34s exit=%s\n' "$name" "$code"
    pass=$((pass + 1))
  else
    printf 'FAIL %-34s want exit=%s got exit=%s\n' "$name" "$want" "$code"
    printf '     output: %s\n' "$(printf '%s' "$out" | tr '\n' ' ' | cut -c1-180)"
    fail=$((fail + 1))
  fi
}

mkdir -p "$TMP/fakehome"

# ── The positive control the old script never had ────────────────────────────
expect 0 round-trip-verified
GOOD_CANDIDATE="$(find "$DEST" -name 'terraform.tfstate.s7.*.age' -print -quit)"
if [ -s "$DEST/log.tsv" ] && [ -n "$GOOD_CANDIDATE" ]; then
  printf 'ok   %-34s\n' "artifact-and-manifest-written"
  pass=$((pass + 1))
else
  printf 'FAIL %-34s no .age file or manifest in %s\n' "artifact-and-manifest-written" "$DEST"
  fail=$((fail + 1))
fi

# Decrypt independently with the identity and compare to the manifest digest.
# This is the assertion that would have caught D-02's dead backup.
RECOVERED="$TMP/recovered.json"
if age -d -i "$KEYS/id" -o "$RECOVERED" "$GOOD_CANDIDATE" 2>/dev/null \
   && [ "$(sha256sum "$RECOVERED" | cut -d' ' -f1)" = "$(awk -F'\t' 'NR==2{print $3}' "$DEST/log.tsv")" ]; then
  printf 'ok   %-34s\n' "manifest-digest-matches-plaintext"
  pass=$((pass + 1))
else
  printf 'FAIL %-34s recovered bytes do not match the logged digest\n' "manifest-digest-matches-plaintext"
  fail=$((fail + 1))
fi

# ── Refusals (exit 1): the operator's own misconfiguration ───────────────────
# A second identity, used to prove the round trip is real: decrypting with the
# wrong key must be a refusal (exit 1), not a pass and not a shrug.
age-keygen -o "$TMP/other" >/dev/null 2>&1
expect 1 refuse-missing-dest BACKUP_DEST=
expect 1 refuse-dest-absent BACKUP_DEST="$TMP/does-not-exist"
expect 1 refuse-bad-public-key STATE_BACKUP_PUBKEY="not-an-age-key"
expect 1 refuse-wrong-identity STATE_BACKUP_KEY="$TMP/other"

# ── Cannot-verify (exit 2): never a silent pass ──────────────────────────────
# Corrupt local state plus an unreachable backend must be 2, not 0 and not a
# quiet skip: the tool falls back to the cloud path, and there the source is
# unverifiable.
expect 2 corrupt-state-unreachable-backend STATE_FILE="$BAD" \
  STATE_BACKUP_API_BASE="http://127.0.0.1:9/api/v2" TFC_TOKEN="rt-$(date +%s)"
# No token anywhere and no local state → cannot verify.
expect 2 no-token-no-local-state STATE_FILE="$TMP/absent.json" \
  STATE_BACKUP_API_BASE="http://127.0.0.1:9/api/v2"
# Skipping verification is allowed only as a non-passing outcome.
expect 2 skip-verify-is-not-a-pass STATE_BACKUP_SKIP_VERIFY=1

echo
echo "state-backup tests: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
