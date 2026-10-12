#!/usr/bin/env bash
# check_workspace_execution_mode.sh — refuse a CI apply whose plan will run on
# HCP Terraform's remote workers.
#
# jolarca-control — marketplace (jolarca-dev) governance control plane.
# SOC 2 CC7.1 / CC8.1 · ISO 27001 A.8.32 · PCI-DSS 6.5.1
#
# WHY THIS EXISTS
#   apply.yml runs `terraform plan` then `terraform apply -auto-approve tfplan`.
#   With a `cloud {}` backend and the workspace in REMOTE execution mode, the
#   plan is queued on HashiCorp's workers instead of running on the runner. On
#   the Free plan that queue is not bounded by anything this repo controls:
#   run 38239257880 (2026-10-12, merge of #64) sat in `Terraform Plan` for
#   33 minutes, was force-cancelled by the operator, and the `-auto-approve`
#   apply behind it never ran. A hang that long on a job that ends in an
#   unattended apply is not a slow pipeline — it is an apply nobody read.
#
#   Two fixes were tried first and both were NO-OPS, recorded here so nobody
#   re-introduces them:
#     * `terraform plan -local` — no such flag in Terraform 1.16.1 (measured:
#       `terraform plan -help` / `terraform apply -help` contain no `-local`).
#     * `TF_CLOUD_OPERATIONS: "false"` — not a documented Terraform environment
#       variable at all. The runs kept landing on remote workers with it set.
#
#   The only real lever is the workspace setting `execution-mode = local`
#   (HCP Terraform API: PATCH /organizations/:org/workspaces/:name). This gate
#   checks that setting BEFORE any plan is attempted, so a misconfigured
#   workspace fails in seconds rather than occupying a runner for half an hour.
#
# Usage: scripts/check_workspace_execution_mode.sh <workspace.json> [expected-mode]
#        <workspace.json> is the response body of GET /api/v2/workspaces/<id>
#        or GET /api/v2/organizations/<org>/workspaces/<name>.
# Exit:  0 workspace uses the expected execution mode
#        1 wrong execution mode — a real refusal, with the fix printed
#        2 the response could not be read or parsed. Never treated as a pass.

usage() {
  echo "usage: $0 <workspace-json-file> [expected-mode]" >&2
  exit 2
}

[ "$#" -ge 1 ] || usage
WS_JSON="$1"
EXPECTED="${2:-local}"

if [ ! -f "$WS_JSON" ] || [ ! -r "$WS_JSON" ]; then
  echo "ERROR: workspace response not readable: $WS_JSON" >&2
  echo "Refusing to proceed: an unreadable response proves nothing about execution mode." >&2
  exit 2
fi

if [ ! -s "$WS_JSON" ]; then
  echo "ERROR: workspace response is empty: $WS_JSON" >&2
  echo "An empty file usually means curl failed, not that the workspace is misconfigured." >&2
  exit 2
fi

# python3 is used rather than grep so that a JSON error and a missing attribute
# are distinguishable from a real value — the failure mode that made the old
# inline plan-safety grep inert (D-22).
mode="$(python3 - "$WS_JSON" <<'PY'
import json
import sys

try:
    doc = json.load(open(sys.argv[1]))
except Exception as exc:  # noqa: BLE001 - any parse failure is "cannot verify"
    print(f"PARSE_ERROR:{exc}", file=sys.stderr)
    sys.exit(3)

if "errors" in doc:
    print(f"API_ERROR:{doc['errors']}", file=sys.stderr)
    sys.exit(3)

try:
    value = doc["data"]["attributes"].get("execution-mode")
except Exception:
    print("API_ERROR:response has no data.attributes", file=sys.stderr)
    sys.exit(3)

print(value if value else "")
sys.exit(0)
PY
)"
parse_rc=$?

if [ "$parse_rc" -ne 0 ]; then
  echo "ERROR: could not determine the workspace execution mode from $WS_JSON" >&2
  echo "Could-not-verify is not a pass (AGENTS.md §3)." >&2
  exit 2
fi

if [ -z "$mode" ]; then
  echo "ERROR: workspace response carries no execution-mode value." >&2
  echo "A null/absent mode means the workspace inherits a project default, which this" >&2
  echo "control plane cannot reason about. Set execution-mode explicitly." >&2
  exit 2
fi

if [ "$mode" = "$EXPECTED" ]; then
  echo "Workspace execution mode is '${mode}': plan and apply run on the runner, state stays in HCP Terraform."
  exit 0
fi

cat >&2 <<MSG
ERROR: workspace execution mode is '${mode}', this gate requires '${EXPECTED}'.

With '${mode}' execution, 'terraform plan' is queued on remote workers rather than
running on the GitHub runner. On the Free plan that queue ran 33 minutes on
2026-10-12 while 'terraform apply -auto-approve' waited behind it unattended.

Fix (requires an HCP Terraform token with workspace admin; the API demands the
JSON:API media type — a POST/PATCH without it is refused with HTTP 415):

  curl -sS -X PATCH \\
    -H "Authorization: Bearer \$TFC_TOKEN" \\
    -H "Content-Type: application/vnd.api+json" \\
    https://app.terraform.io/api/v2/organizations/jolarca-dev/workspaces/jolarca-control \\
    --data '{"data":{"type":"workspaces","attributes":{"execution-mode":"local"}}}'

Consequences of switching, stated rather than discovered later: HCP Terraform
does not evaluate workspace variables or variable sets in local execution mode,
and remote (VCS-triggered) runs stop. Both are already true of this pipeline —
apply.yml supplies the provider token itself, and no workspace variable set is
in use.
MSG
exit 1
