#!/usr/bin/env bash
# state_backup.sh — encrypted off-host backup of Terraform state (D-02).
#
# jolarca-control — marketplace (jolarca-dev) governance control plane.
# SOC 2 CC7.1 / ISO 27001 A.8.13 / GDPR Art. 32(1)(c) — the 3-2-1 rule.
#
# WHY THIS WAS REWRITTEN (2026-10-15)
#   The script only knew how to back up `$REPO_ROOT/terraform.tfstate`. State
#   moved to HCP Terraform (ADR-0006, D-02 backend half), that file became a
#   0-byte placeholder, and every run since exited 1 with
#   "terraform.tfstate is not valid JSON". The D-02 interim control recorded in
#   docs/drift-findings.md — "AGE-encrypted state backup via
#   scripts/state_backup.sh" — had therefore been dead while the authoritative
#   state existed in exactly one copy. It also never proved recoverability:
#   "success" meant `age` ran, never that the bytes came back. A backup nobody
#   has decrypted is a hope, not a control (AGENTS.md §7).
#
# SOURCE SELECTION
#   1. `$STATE_FILE` / $REPO_ROOT/terraform.tfstate, when it is real JSON.
#   2. otherwise the workspace's current state version from the cloud backend,
#      with organization and workspace parsed out of main.tf's `cloud {}` block
#      so the tool cannot drift from the backend it is backing up.
#      Measured route on this deployment: `GET /workspaces/{id}` with
#      `include=current-state-version`, then the state version's
#      `hosted-state-download-url` (the real tfstate document: version 4,
#      serial, resources, outputs). Do NOT use
#      `hosted-json-state-download-url` — that one serves HCP's *sanitized*
#      public state output (`format_version`/`values`), which would back up a
#      redacted document and look like a success.
#
# WHAT IS NEVER PRINTED
#   The signed download URL and the state body. The state carries resource
#   attributes and outputs; only hashes, sizes, serial and resource counts are
#   written to stdout and to the manifest.
#
# EXIT CODES (three-valued per AGENTS.md §3 — cannot-verify is never a pass)
#   0  backup written AND round-trip verified
#   1  refused: bad prerequisite, unusable source, encryption failure,
#      round-trip mismatch
#   2  could not verify: no API token, backend unreachable or rejected, no state
#      version, downloaded document not a real state file, verification skipped
#
# ENVIRONMENT
#   BACKUP_DEST       required — off-host directory (mounted volume, NFS)
#   BACKUP_LOG        default: $BACKUP_DEST/backup-log.tsv (travels with the
#                     backups instead of churning a file inside a repository that
#                     may itself be lost)
#   STATE_BACKUP_PUBKEY  age recipient; else .state-backup-pubkey.txt
#   STATE_BACKUP_KEY     age identity for the round trip; else
#                        ~/.config/age/state-backup-key.txt
#   STATE_BACKUP_SKIP_VERIFY  =1 skips the round trip → exits 2, never 0
#   STATE_BACKUP_REQUIRE_OFF_HOST  =1 refuses (exit 1) when BACKUP_DEST shares a
#                        filesystem with this repository. Off-host is the whole
#                        point of D-02; a backup on the same disk is insurance
#                        against operator error, not against host loss. Default 0
#                        so backups keep happening while no second destination
#                        exists — the probe is recorded either way.
#   STATE_BACKUP_PROBE_LOG  default: $BACKUP_DEST/backup-probes.tsv (kept separate
#                        from backup-log.tsv so that file's 7-column schema does
#                        not silently change under existing readers)
#   TFC_TOKEN         HCP API token; else the credentials block of
#                     $TF_CLI_CONFIG_FILE or ~/.terraformrc
#   STATE_BACKUP_API_BASE  default https://app.terraform.io/api/v2 (tests point
#                          this at a closed local port)
#   STATE_FILE        override the local source path (tests use this)
#
# Negative controls: tests/test_state_backup.sh, run by `make test`.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATE_FILE="${STATE_FILE:-$REPO_ROOT/terraform.tfstate}"
dest="${BACKUP_DEST:-}"

die() { echo "ERROR: $*" >&2; exit 1; }
unverifiable() { echo "CANNOT VERIFY: $*" >&2; exit 2; }

command -v age >/dev/null 2>&1 || die "age is not installed. See https://github.com/FiloSottile/age"
command -v python3 >/dev/null 2>&1 || die "python3 is not installed"
[ -n "$dest" ] || die "BACKUP_DEST is not set. Point it at an off-host directory."
[ -d "$dest" ] || die "backup destination does not exist: $dest"

pubkey="${STATE_BACKUP_PUBKEY:-}"
if [ -z "$pubkey" ] && [ -f "$REPO_ROOT/.state-backup-pubkey.txt" ]; then
  pubkey="$(tr -d ' \t\r\n' < "$REPO_ROOT/.state-backup-pubkey.txt")"
fi
[ -n "$pubkey" ] || die "no age public key: set STATE_BACKUP_PUBKEY or create .state-backup-pubkey.txt"

BACKUP_LOG="${BACKUP_LOG:-$dest/backup-log.tsv}"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
plain="$work/state.json"
source_kind=""

# ── Source 1: a real local state file ────────────────────────────────────────
if [ -s "$STATE_FILE" ] && python3 -c "import json,sys; json.load(open(sys.argv[1]))" "$STATE_FILE" 2>/dev/null; then
  cp "$STATE_FILE" "$plain"
  source_kind="local file $STATE_FILE"
else
  # ── Source 2: current state version from the cloud backend ────────────────
  # Exit status from the helper: 0 ok · 1 unusable input · 2 cannot verify.
  if ! python3 - "$REPO_ROOT" "$plain" > "$work/fetch.log" 2>&1 <<'PY'
import json, os, pathlib, re, sys, urllib.error, urllib.request

root, out = pathlib.Path(sys.argv[1]), sys.argv[2]
api = os.environ.get("STATE_BACKUP_API_BASE", "https://app.terraform.io/api/v2").rstrip("/")


def die(code, msg):
    print(msg, file=sys.stderr)
    raise SystemExit(code)


main = (root / "main.tf").read_text(errors="replace")
if "cloud {" not in main:
    die(1, "no cloud {} block in main.tf and no usable local state file")
org = re.search(r'organization\s*=\s*"([^"]+)"', main)
ws = re.search(r'name\s*=\s*"([^"]+)"', main[main.find("cloud {"):])
if not (org and ws):
    die(1, "could not read organization/workspace from the cloud {} block")

token = os.environ.get("TFC_TOKEN", "").strip()
if not token:
    cfg = pathlib.Path(os.environ.get("TF_CLI_CONFIG_FILE") or (pathlib.Path.home() / ".terraformrc"))
    if cfg.exists():
        m = re.search(
            r'credentials\s+"app\.terraform\.io"\s*\{[^}]*?token\s*=\s*"([^"]+)"',
            cfg.read_text(errors="replace"), re.S)
        token = m.group(1) if m else ""
if not token:
    die(2, f"no HCP Terraform token available (TFC_TOKEN unset, no credentials block in {cfg})")

hdr = {"Authorization": "Bearer " + token}


def get(url, want_json=True):
    req = urllib.request.Request(url, headers=hdr)
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            body = r.read()
        return json.loads(body) if want_json else body
    except urllib.error.HTTPError as e:
        die(2, f"backend returned HTTP {e.code} for {url.split('?')[0]}")
    except Exception as e:  # unreachable, DNS, TLS, timeout — never a silent pass
        die(2, f"backend unreachable at {url.split('?')[0]}: {type(e).__name__}: {e}")


wsid = ""
try:
    w = get(f"{api}/organizations/{org.group(1)}/workspaces/{ws.group(1)}?include=current-state-version")
    wsid = w["data"]["id"]
    versions = [i for i in w.get("included", []) if i.get("type") == "state-versions"]
except SystemExit:
    raise
except Exception as e:
    die(2, f"could not read workspace {org.group(1)}/{ws.group(1)}: {type(e).__name__}: {e}")
if not versions:
    die(2, f"workspace {wsid} reports no current state version — nothing to back up")

sv = versions[0]
url = sv["attributes"].get("hosted-state-download-url")
if not url:
    die(2, f"state version {sv['id']} exposes no hosted-state-download-url")

raw = get(url, want_json=False)
try:
    state = json.loads(raw)
except ValueError:
    die(2, f"downloaded state for {sv['id']} is not valid JSON")
if "resources" not in state or "values" in state:
    die(2, f"downloaded document for {sv['id']} is HCP's sanitized state output, not the real state")

pathlib.Path(out).write_bytes(raw)
os.chmod(out, 0o600)
print("%s\t%s\t%s\t%d\t%d" % (
    sv["id"], state.get("serial", "na"), len(state.get("resources", [])),
    len(state.get("outputs", {})), len(raw)))
PY
  then
    cat "$work/fetch.log" >&2 || true
    code="$(sed -n 's/^.*HTTP \([0-9]\{3\}\).*$/\1/p' "$work/fetch.log" | head -1)"
    unverifiable "cloud state could not be retrieved from the backend${code:+ (HTTP $code)} — no backup was taken and no claim is made"
  fi
  # Here-string, not a pipe: a pipe would run `read` in a subshell and the
  # fetched values would vanish before the summary could use them.
  IFS=$'\t' read -r svid sv_serial sv_resources sv_outputs sv_bytes <<EOF
$(tail -n 1 "$work/fetch.log")
EOF
  [ -s "$plain" ] || unverifiable "helper reported success but wrote no state file"
  source_kind="HCP state version $svid (serial $sv_serial)"
  echo "  fetched:        $sv_resources resource blocks, $sv_outputs outputs, $sv_bytes bytes"
fi

# ── Digest, encrypt, then prove decryption ───────────────────────────────────
digest="$(sha256sum "$plain" | cut -d' ' -f1)"
serial="$(python3 -c "import json,sys; print(json.load(open(sys.argv[1])).get('serial','na'))" "$plain")"
resources="$(python3 -c "import json,sys; print(len(json.load(open(sys.argv[1])).get('resources',[])))" "$plain")"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
encrypted_path="$dest/terraform.tfstate.s${serial}.${timestamp}.age"

age -r "$pubkey" -o "$encrypted_path" "$plain" || die "age encryption failed"
chmod 600 "$encrypted_path" 2>/dev/null || true

identity="${STATE_BACKUP_KEY:-$HOME/.config/age/state-backup-key.txt}"
if [ "${STATE_BACKUP_SKIP_VERIFY:-0}" = "1" ]; then
  echo "Wrote $encrypted_path but the round trip was skipped on purpose." >&2
  echo "  An encrypted file nobody has decrypted is not evidence of recoverability," >&2
  echo "  so this exits 2 (cannot verify) rather than 0. Drop STATE_BACKUP_SKIP_VERIFY." >&2
  exit 2
fi
[ -f "$identity" ] || unverifiable "no age identity at $identity — encrypted but not decryptable-proven, which is not a verified backup"

recovered="$work/recovered.json"
age -d -i "$identity" -o "$recovered" "$encrypted_path" 2>/dev/null \
  || die "round-trip FAILED: the backup could not be decrypted with the expected identity"
recovered_digest="$(sha256sum "$recovered" | cut -d' ' -f1)"
if [ "$recovered_digest" != "$digest" ]; then
  die "round-trip FAILED: decrypted sha256 $recovered_digest != source $digest"
fi

# ── Off-host probe (D-02: "off-host" was a claim, never a measurement) ───────
# Device ids, not paths: /opt/jolarca/backups and /opt/jolarca/repos/* are different
# directories on the SAME ext4 filesystem, which is exactly the case a human eyeballing
# the paths would call off-host. stat -c%d is GNU, stat -f%d is the BSD/macOS form.
dev_of() {
  stat -c%d "$1" 2>/dev/null || stat -f%d "$1" 2>/dev/null || echo ""
}
dest_dev="$(dev_of "$dest")"
repo_dev="$(dev_of "$REPO_ROOT")"
require_off="${STATE_BACKUP_REQUIRE_OFF_HOST:-0}"
if [ -z "$dest_dev" ] || [ -z "$repo_dev" ]; then
  off_host="unknown"
elif [ "$dest_dev" = "$repo_dev" ]; then
  off_host="no"
else
  off_host="yes"
fi

probe_log="${STATE_BACKUP_PROBE_LOG:-$dest/backup-probes.tsv}"
if [ ! -f "$probe_log" ]; then
  printf 'timestamp\tdest\tdest_dev\trepo_root\trepo_dev\toff_host\tround_trip\n' > "$probe_log"
  chmod 600 "$probe_log" 2>/dev/null || true
fi
printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
  "$timestamp" "$dest" "$dest_dev" "$REPO_ROOT" "$repo_dev" "$off_host" "verified" >> "$probe_log"

if [ "$off_host" != "yes" ]; then
  echo "::warning::BACKUP_DEST is NOT off-host (off_host=$off_host, dest_dev=$dest_dev, " \
       "repo_dev=$repo_dev). This copy survives operator error, not host loss (D-02)." >&2
  echo "  off-host:       $off_host  (dest_dev=$dest_dev repo_dev=$repo_dev)"
  echo "  probe log:      $probe_log"
  if [ "$require_off" = "1" ]; then
    die "STATE_BACKUP_REQUIRE_OFF_HOST=1 but the destination is on the same filesystem " \
        "as the repository (off_host=$off_host) — refusing to call this a 3-2-1 copy"
  fi
else
  echo "  off-host:       yes  (dest_dev=$dest_dev != repo_dev=$repo_dev)"
fi

# ── Manifest (travels with the backups) ──────────────────────────────────────
encrypted_size="$(stat -c%s "$encrypted_path" 2>/dev/null || stat -f%z "$encrypted_path")"
state_size="$(stat -c%s "$plain" 2>/dev/null || stat -f%z "$plain")"
if [ ! -f "$BACKUP_LOG" ]; then
  printf 'timestamp\tserial\tstate_sha256\tstate_size\tencrypted_size\tsource\tencrypted_path\n' > "$BACKUP_LOG"
  chmod 600 "$BACKUP_LOG" 2>/dev/null || true
fi
printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
  "$timestamp" "$serial" "$digest" "$state_size" "$encrypted_size" "$source_kind" "$encrypted_path" >> "$BACKUP_LOG"

echo "BACKUP OK (round-trip verified)"
echo "  source:         $source_kind"
echo "  serial:         $serial"
echo "  resources:      $resources resource blocks"
echo "  state SHA-256:  $digest"
echo "  recovered:      $recovered_digest (match)"
echo "  state size:     $state_size bytes"
echo "  encrypted size: $encrypted_size bytes"
echo "  encrypted path: $encrypted_path"
echo "  manifest:       $BACKUP_LOG"
