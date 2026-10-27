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

# ── Off-host probe (D-02: the destination was always on the same disk) ───────
# Measured on a GitHub runner 2026-10-27: /tmp and the workspace are the SAME device
# (66305), so an off-host case that assumes "$TMP is elsewhere" fails there while
# passing on a dev box where /tmp is its own mount. The rule that broke was asserting
# a device relationship instead of measuring one, so the layout is probed here and the
# off_host=yes branch is only asserted where a genuinely different filesystem exists.
REPO_DEV="$(stat -c%d "$REPO_ROOT" 2>/dev/null || stat -f%d "$REPO_ROOT")"
SAME_FS="$(mktemp -d -p "$REPO_ROOT" .state-backup-fs-XXXXXX)"
trap 'rm -rf "$SAME_FS"' EXIT
SAME_DEV="$(stat -c%d "$SAME_FS" 2>/dev/null || stat -f%d "$SAME_FS")"

OTHER_FS=""; OTHER_DEST=""
for c in /dev/shm /run /tmp; do
  d="$(stat -c%d "$c" 2>/dev/null || stat -f%d "$c" 2>/dev/null || echo "")"
  if [ -n "$d" ] && [ "$d" != "$REPO_DEV" ] && [ -w "$c" ]; then
    OTHER_FS="$c"; break
  fi
done
[ -n "$OTHER_FS" ] && OTHER_DEST="$(mktemp -d -p "$OTHER_FS" jolarca-bkfix-XXXXXX)"

# The meta-assertion that caught this bug: the same-device case is only meaningful if
# the directory really is on the repo's device.
if [ -n "$REPO_DEV" ] && [ "$SAME_DEV" = "$REPO_DEV" ]; then
  printf 'ok   %-34s dev=%s\n' "same-device-dest-is-really-same" "$SAME_DEV"
  pass=$((pass + 1))
else
  printf 'FAIL %-34s same_fs_dev=%s repo_dev=%s\n' "same-device-dest-is-really-same" "$SAME_DEV" "$REPO_DEV"
  fail=$((fail + 1))
fi

expect 0 same-filesystem-still-backs-up BACKUP_DEST="$SAME_FS"
PROBE="$SAME_FS/backup-probes.tsv"
if [ -f "$PROBE" ] && awk -F'\t' 'NR==2 && $6=="no"' "$PROBE" | grep -q .; then
  printf 'ok   %-34s\n' "probe-records-off-host-no"
  pass=$((pass + 1))
else
  printf 'FAIL %-34s expected an off_host=no row in %s\n' "probe-records-off-host-no" "$PROBE"
  fail=$((fail + 1))
fi

# Refusing is opt-in, but when opted in it must actually refuse: a green backup that
# is not off-host is the claim D-02 was opened for.
expect 1 require-off-host-refuses-same-fs BACKUP_DEST="$SAME_FS" STATE_BACKUP_REQUIRE_OFF_HOST=1

# The refusal must PRECEDE the write. Asserting only the exit code would have passed on
# the first version of this script, which encrypted, wrote the archive, and only then
# refused — leaving a backup in the directory it had just declared unacceptable.
STRICT_FS="$(mktemp -d -p "$REPO_ROOT" .state-backup-strict-XXXXXX)"
strict_out="$(env -i PATH="$PATH" HOME="$TMP/fakehome" \
  STATE_FILE="$GOOD" BACKUP_DEST="$STRICT_FS" STATE_BACKUP_PUBKEY="$PUB" \
  STATE_BACKUP_KEY="$KEYS/id" BACKUP_LOG="$STRICT_FS/log.tsv" \
  STATE_BACKUP_REQUIRE_OFF_HOST=1 TF_CLI_CONFIG_FILE="$TMP/no-such-file" TFC_TOKEN="" \
  bash "$BACKUP" 2>&1)"
strict_rc=$?
# find, not ls: the filenames are generated and shellcheck is right that ls splits them.
strict_contents="$(find "$STRICT_FS" -mindepth 1 -maxdepth 1 -printf '%f ' 2>/dev/null)"
if [ "$strict_rc" -eq 1 ] && [ -z "$strict_contents" ]; then
  printf 'ok   %-34s exit=1, destination left empty\n' "refuses-before-writing-anything"
  pass=$((pass + 1))
else
  printf 'FAIL %-34s exit=%s contents=[%s]\n' "refuses-before-writing-anything" "$strict_rc" \
    "$strict_contents"
  printf '     output: %s\n' "$(printf '%s' "$strict_out" | tr '\n' ' ' | cut -c1-180)"
  fail=$((fail + 1))
fi
rm -rf "$STRICT_FS"

if [ -n "$OTHER_DEST" ]; then
  # And the flag must not manufacture a refusal when the device genuinely differs.
  expect 0 require-off-host-passes-different-fs BACKUP_DEST="$OTHER_DEST" STATE_BACKUP_REQUIRE_OFF_HOST=1
  if awk -F'\t' 'NR==2 && $6=="yes"' "$OTHER_DEST/backup-probes.tsv" 2>/dev/null | grep -q .; then
    printf 'ok   %-34s\n' "probe-records-off-host-yes"
    pass=$((pass + 1))
  else
    printf 'FAIL %-34s expected an off_host=yes row for %s\n' "probe-records-off-host-yes" "$OTHER_DEST"
    fail=$((fail + 1))
  fi
  rm -rf "$OTHER_DEST"
else
  # Loud skip, never a silent pass: on a host where every candidate shares the repo's
  # device, the off_host=yes branch is simply not observable here.
  printf 'SKIP %-34s no candidate filesystem differs from dev=%s\n' \
    "off-host-yes-branch-not-observable" "$REPO_DEV"
fi
rm -rf "$SAME_FS"

echo
echo "state-backup tests: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
