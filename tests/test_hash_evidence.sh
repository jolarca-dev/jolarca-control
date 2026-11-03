#!/usr/bin/env bash
# tests/test_hash_evidence.sh — negative controls for the evidence-integrity gate.
#
# jolarca-control — marketplace (jolarca-dev) governance control plane.
# SOC 2 CC4.1 / ISO 27001 A.5.31 / PCI-DSS 12.10.1
#
# WHY THIS FILE EXISTS. scripts/hash_evidence.sh is the control that makes audit
# evidence tamper-evident, and it had no fixture at all (AGENTS.md §7: a gate with
# no negative control is a hypothesis). The hypothesis was wrong: --check only
# visits files found on disk, so deleting a registered file produced
# "0 files scanned, 0 mismatches / OK", exit 0 — established by hand in /tmp before
# the reverse pass was written (FA-control-01). Case `delete-is-a-finding` below is
# the regression that must never come back, because removing evidence is the
# cheapest way to pass a control that only looks at present files.
#
# Every tree here is a throwaway copy under mktemp -d: nothing in the repository is
# modified, and no run touches the real registry except the final read-only
# positive control. The gate under test is COPIED rather than parameterised — it
# derives REPO_ROOT from its own location, so a copy in <tree>/scripts/ makes
# <tree> the repository. Deliberate: a compliance control should not gain an
# EVIDENCE_REPO_ROOT switch that lets any caller redirect it at a chosen tree just
# so it can be tested.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="$REPO_ROOT/scripts/hash_evidence.sh"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

pass=0
fail=0
OUT="$TMP/last-output.txt"

# newtree <dir> — an isolated repository-shaped tree with the gate installed.
# `git init` + `git add -A` are mandatory, not decoration: the gate enumerates the
# TRACKED tree (git ls-files), so a tree with no index has no evidence at all and the
# gate correctly refuses to verify it (exit 2). Files deleted later stay in the index,
# which is exactly the "committed but removed from disk" shape CI sees.
newtree() {
  local d="$1"
  mkdir -p "$d/scripts" "$d/policy" "$d/docs/adr" "$d/audit" "$d/repos"
  cp "$SRC" "$d/scripts/hash_evidence.sh"
  printf 'policy one\n' > "$d/policy/a.yml"
  printf 'adr one\n' > "$d/docs/adr/0001-x.md"
  printf 'repo one\n' > "$d/repos/jolarca.yml"
  git -C "$d" init -q
  git -C "$d" add -A
}

# run_gate <tree> [args...] — capture stdout+stderr, return the gate's exit code.
run_gate() {
  local tree="$1"
  shift
  (cd "$tree" && bash ./scripts/hash_evidence.sh "$@") > "$OUT" 2>&1
}

# expect_code <want> <name> <tree> [args...]
expect_code() {
  local want="$1" name="$2" tree="$3"
  shift 3
  run_gate "$tree" "$@"
  local code=$?
  if [ "$code" -eq "$want" ]; then
    printf 'ok   %-36s exit=%s\n' "$name" "$code"
    pass=$((pass + 1))
  else
    printf 'FAIL %-36s want exit=%s got exit=%s\n' "$name" "$want" "$code"
    printf '     output: %s\n' "$(tr '\n' ' ' < "$OUT" | cut -c1-200)"
    fail=$((fail + 1))
  fi
}

# expect_contains <needle> <name> — asserts the verdict is not only correct but
# legible: an exit 1 that never names the deleted file is hard to act on.
expect_contains() {
  local needle="$1" name="$2"
  if grep -q "$needle" "$OUT"; then
    printf 'ok   %-36s\n' "$name"
    pass=$((pass + 1))
  else
    printf 'FAIL %-36s output lacks %s\n' "$name" "$needle"
    printf '     output: %s\n' "$(tr '\n' ' ' < "$OUT" | cut -c1-200)"
    fail=$((fail + 1))
  fi
}

# ── The happy path: register, then verify (must be exit 0) ────────────────────
T="$TMP/ok"
newtree "$T"
expect_code 0 register-succeeds "$T"
expect_code 0 check-after-register "$T" --check

# ── Modification: the case the gate always handled ────────────────────────────
printf 'policy one TAMPERED\n' > "$T/policy/a.yml"
expect_code 1 tampered-file-is-a-finding "$T" --check
expect_contains "CHANGED:" reports-changed-by-name

# ── Addition: evidence in the repository that nobody registered ──────────────
# `git add` is part of this case, not an afterthought. Since the tracked-tree fix a
# file that exists only on a developer disk is not evidence yet (asserted separately in
# `untracked-file-is-not-registered`), so the defect to model here is the CI one: a
# commit that adds a hashed file without adding its registry row.
T="$TMP/new"
newtree "$T"
run_gate "$T"
printf 'new policy\n' > "$T/policy/b.yml"
git -C "$T" add policy/b.yml
expect_code 1 unregistered-file-is-a-finding "$T" --check
expect_contains "UNREGISTERED:" reports-unregistered-by-name

# ── Deletion: THE REGRESSION THIS FILE WAS WRITTEN FOR (FA-control-01) ────────
# Before the reverse pass this printed "0 files scanned, 0 mismatches / OK" and
# exited 0. A registry row with no file behind it must be a finding.
T="$TMP/deleted"
newtree "$T"
run_gate "$T"
rm "$T/policy/a.yml"
expect_code 1 delete-is-a-finding "$T" --check
expect_contains "MISSING:" reports-deleted-file-by-name
expect_contains "policy/a.yml" names-the-exact-path

# Deleting a whole evidence directory is the same defect at larger scale — the
# registry covers many files, none of which are there any more.
T="$TMP/wiped"
newtree "$T"
run_gate "$T"
rm -rf "$T/policy" "$T/audit"
expect_code 1 whole-directory-wiped-is-a-finding "$T" --check

# ── Cannot verify (exit 2): never a silent pass ───────────────────────────────
T="$TMP/noreg"
newtree "$T"
expect_code 2 missing-baseline-cannot-verify "$T" --check

T="$TMP/emptyreg"
newtree "$T"
run_gate "$T"
printf 'file,sha256,registered_date\n' > "$T/docs/evidence-registry.csv"
expect_code 2 header-only-registry-cannot-verify "$T" --check

# Compared nothing, missing nothing: the registry lists a file whose extension is
# outside the hashed set, so the forward loop scans zero files and the reverse pass
# finds no gap. That is "could not verify", not "clean" — the aggregate must not
# read as OK when zero comparisons happened.
# An earlier draft of this case left the three hashable fixture files in place and
# only added the .txt row, so the gate correctly reported them UNREGISTERED and
# exited 1. The gate was right; the case was wrong. Deletion of the hashable files
# is what isolates the zero-comparison path.
T="$TMP/zeroscan"
newtree "$T"
rm "$T/policy/a.yml" "$T/docs/adr/0001-x.md" "$T/repos/jolarca.yml"
printf 'not hashed\n' > "$T/policy/a.txt"
printf 'file,sha256,registered_date\npolicy/a.txt,%s,2026-01-01\n' \
  "$(sha256sum "$T/policy/a.txt" | cut -d' ' -f1)" > "$T/docs/evidence-registry.csv"
expect_code 2 zero-comparisons-cannot-verify "$T" --check

# ── Re-registration must not restate history ─────────────────────────────────
# The registered_date column means "when THIS hash entered the baseline". Wiping it
# on every run makes it impossible to tell what actually changed, so the date is
# preserved for unchanged hashes and refreshed only for changed ones.
T="$TMP/dates"
newtree "$T"
run_gate "$T"
sed -i 's/,[0-9-]*$/,2026-01-01/' "$T/docs/evidence-registry.csv"
run_gate "$T"
if [ "$(grep -c ',2026-01-01$' "$T/docs/evidence-registry.csv")" -eq 3 ]; then
  printf 'ok   %-36s\n' "unchanged-hashes-keep-their-date"
  pass=$((pass + 1))
else
  printf 'FAIL %-36s dates were restated\n' "unchanged-hashes-keep-their-date"
  fail=$((fail + 1))
fi
printf 'adr one CHANGED\n' > "$T/docs/adr/0001-x.md"
run_gate "$T"
if grep -q '^docs/adr/0001-x.md,.*2026-01-01$' "$T/docs/evidence-registry.csv"; then
  printf 'FAIL %-36s new hash kept the old date\n' "changed-hash-gets-today"
  fail=$((fail + 1))
else
  printf 'ok   %-36s\n' "changed-hash-gets-today"
  pass=$((pass + 1))
fi

# ── Scope: the registry may only attest the TRACKED tree (FA-control-10) ──────
# The defect this asserts: 26 of 72 rows named files that existed on a developer disk
# and nowhere in git. CI scanned 46 files and reported OK over the other 26, because a
# working-tree scan cannot see that distinction. An untracked file under an evidence
# directory is not evidence yet, and must not acquire a registry row.
T="$TMP/untracked"
newtree "$T"
run_gate "$T"
rows_before="$(grep -c '^policy/\|^docs/\|^repos/\|^audit/' "$T/docs/evidence-registry.csv")"
printf 'draft, never committed\n' > "$T/policy/c.yml"
run_gate "$T"
rows_after="$(grep -c '^policy/\|^docs/\|^repos/\|^audit/' "$T/docs/evidence-registry.csv")"
if [ "$rows_before" -eq 3 ] && [ "$rows_after" -eq 3 ]; then
  printf 'ok   %-36s\n' "untracked-file-is-not-registered"
  pass=$((pass + 1))
else
  printf 'FAIL %-36s rows went %s -> %s\n' "untracked-file-is-not-registered" \
    "$rows_before" "$rows_after"
  fail=$((fail + 1))
fi
expect_code 0 check-ignores-untracked-additions "$T" --check

# A directory that is not a git repository has no tracked tree to attest, so the only
# honest answer is "could not verify" — exit 2, never a vacuous 0.
T="$TMP/nogit"
mkdir -p "$T/scripts" "$T/policy"
cp "$SRC" "$T/scripts/hash_evidence.sh"
printf 'policy one\n' > "$T/policy/a.yml"
expect_code 2 not-a-git-repo-cannot-verify "$T" --check

# ── Positive control against the real repository (read-only) ─────────────────
# The fixture is only meaningful if production state passes it too: every registry row
# names a tracked file that exists, and every hash matches the committed baseline.
expect_code 0 real-repository-registry-is-intact "$REPO_ROOT" --check

echo
echo "hash-evidence tests: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
