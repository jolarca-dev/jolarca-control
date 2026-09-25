#!/usr/bin/env bash
# org-delivery-audit.sh — READ-ONLY capture of the delivery chain across the jolarca-dev org.
#
# Prints one TSV row per repository covering: repo visibility/merge policy, main-branch
# protection flags, required status-check contexts, open PR count, and recent CI health
# on main. Raw API payloads are kept under $OUT for the audit trail.
#
# This script makes no writes to GitHub. Usage:
#   ./scripts/org_delivery_audit.sh                 # all repos, capture under ../jolarca-audit-*
#   REPOS="jolarca .github" OUT=/tmp/x ./scripts/org_delivery_audit.sh
set -euo pipefail

ORG="${ORG:-jolarca-dev}"
# jolarca-control added 2026-09-25 — this control plane is itself part of the
# audited fleet. Override with REPOS="..." for a targeted capture.
REPOS="${REPOS:-jolarca jolarca-control jolarca-infrastructure jolarca-compliance jolarca-data jolarca-legal .github}"
OUT="${OUT:-$(pwd)/../jolarca-audit-$(date +%Y%m%d-%H%M%S)}"

command -v gh >/dev/null || { echo "gh is required" >&2; exit 1; }
command -v jq >/dev/null || { echo "jq is required" >&2; exit 1; }
mkdir -p "${OUT}"

fetch_json() { # <outfile> <gh-api-args...>
  local f="$1"; shift
  if ! gh api "$@" > "${f}" 2>"${f}.err"; then
    echo '{"message":"fetch-failed"}' > "${f}"
    sed "s|^|$(basename "${f}"): |" "${f}.err" >&2
  fi
}

printf '%s\n' \
  "repo	visibility	def_branch	prot	squash_only	auto_merge	signed	strict	linear	conv_res	code_owner	admin_enforced	req_reviews	req_ctxs	open_prs	main_fail	main_last" \
  > "${OUT}/audit.tsv"

for r in ${REPOS}; do
  meta="${OUT}/${r}.meta.json"
  prot="${OUT}/${r}.protection.json"
  runs="${OUT}/${r}.runs.json"
  prs="${OUT}/${r}.prs.json"

  fetch_json "${meta}" "repos/${ORG}/${r}"
  fetch_json "${prot}" "repos/${ORG}/${r}/branches/main/protection"
  fetch_json "${runs}" "repos/${ORG}/${r}/actions/runs?branch=main&per_page=20"
  fetch_json "${prs}" --paginate "repos/${ORG}/${r}/pulls?state=open&per_page=100"

  jq -n -r \
    --slurpfile M "${meta}" \
    --slurpfile P "${prot}" \
    --slurpfile R "${runs}" \
    --slurpfile X "${prs}" \
    '
    ($M[0] // {}) as $m |
    ($P[0] // {}) as $p |
    ($R[0].workflow_runs // []) as $runs |
    ($X[0] // []) as $prs |
    def yesno(v): (if v == true then "yes" elif v == false then "no" else "n/a" end);
    def protstate:
      (if ($p | has("required_status_checks")) then "ok"
       elif (($p.message // "") | test("Not Found")) then "none"
       else "err" end);
    [
      ($m.name // "?"),
      ($m.visibility // "?"),
      ($m.default_branch // "?"),
      protstate,
      yesno(($m.allow_merge_commit | not) and ($m.allow_rebase_merge | not)),
      yesno($m.allow_auto_merge),
      yesno($p.required_signatures.enabled),
      yesno($p.required_status_checks.strict),
      yesno($p.required_linear_history.enabled),
      yesno($p.required_conversation_resolution.enabled),
      yesno($p.required_pull_request_reviews.require_code_owner_reviews),
      yesno($p.enforce_admins.enabled),
      (($p.required_pull_request_reviews.required_approving_review_count // "n/a") | tostring),
      ((([$p.required_status_checks.contexts // [] | .[]]
         + [$p.required_status_checks.checks[]?.context]) | unique) | join("+")),
      (($prs | length) | tostring),
      ([$runs[] | select(.conclusion == "failure")] | length | tostring),
      ($runs[0] | if . == null then "n/a" else (.name + " " + (.conclusion // .status)) end)
    ] | @tsv
    ' >> "${OUT}/audit.tsv"
done

echo "raw payloads: ${OUT}" >&2
column -t -s $'\t' "${OUT}/audit.tsv"
