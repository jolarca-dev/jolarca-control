#!/bin/bash
ORG=jolarca-dev
REPOS=$(gh repo list $ORG --limit 100 --json name -q '.[].name' | sort)
{
echo "=== M2. ACTION PIN INTEGRITY (fixed verifier; uses: not on a 40-hex SHA) ==="
tot_unpinned=0; tot_uses=0
for r in $REPOS; do
  for f in $(gh api "repos/$ORG/$r/git/trees/main?recursive=1" -q '.tree[] | select(.path|startswith(".github/workflows")) | select(.path|endswith(".yml") or endswith(".yaml")) | .path' 2>/dev/null); do
    body=$(gh api "repos/$ORG/$r/contents/$f" -q '.content' 2>/dev/null | base64 -d 2>/dev/null)
    u=$(echo "$body" | grep -cE '^[[:space:]]*uses:' || true)
    tot_uses=$((tot_uses+u))
    echo "$body" | grep -nE '^[[:space:]]*uses:' | grep -vE 'uses:[[:space:]]*\./' | grep -vE '@[0-9a-f]{40}' | while IFS= read -r line; do
      echo "UNPINNED  ${r}/${f}  ${line}"
    done
  done
done
echo "TOTAL uses: lines scanned = $tot_uses"
echo "(UNPINNED lines listed above are real; if none, every third-party action is SHA-pinned)"

echo
echo "=== N. FULL RULESET PARAMETERS (consent / dr / vendor) ==="
for r in jolarca-consent jolarca-dr jolarca-vendor; do
  for id in $(gh api "repos/$ORG/$r/rulesets" -q '.[].id' 2>/dev/null); do
    echo "--- $r ruleset $id ---"
    gh api "repos/$ORG/$r/rulesets/$id" 2>/dev/null | jq '{enforcement, rules}'
  done
done

echo
echo "=== O. ORG TEAMS (error surfaced, not swallowed) ==="
gh api "orgs/$ORG/teams" 2>&1 | head -20
echo "-- team count via /orgs/ teams list length --"
gh api "orgs/$ORG/teams" -q 'length' 2>&1 | head -3

echo
echo "=== P. jolarca /secrets DIR (public AGPL repo) ==="
gh api "repos/$ORG/jolarca/git/trees/main?recursive=1" -q '.tree[] | select(.path|startswith("secrets")) | "\(.type) \(.path) \(.size // "")"' 2>/dev/null
echo "-- sops config --"
gh api "repos/$ORG/jolarca/contents/.sops.yaml" -q '.content' 2>/dev/null | base64 -d 2>/dev/null | head -30
echo "-- any obviously-plaintext secret material in secrets/ ? --"
for f in $(gh api "repos/$ORG/jolarca/git/trees/main?recursive=1" -q '.tree[] | select(.path|startswith("secrets")) | select(.type=="blob") | .path' 2>/dev/null | head -10); do
  echo "  [file] $f  first-lines:"
  gh api "repos/$ORG/jolarca/contents/$f" -q '.content' 2>/dev/null | base64 -d 2>/dev/null | head -4 | awk '{printf "      %s\n", substr($0,1,90)}'
done

echo
echo "=== Q. CODEQL / CODE-SCANNING ANALYSES PER REPO ==="
for r in $REPOS; do
  a=$(gh api "repos/$ORG/$r/code-scanning/analyses?per_page=1" 2>&1)
  if echo "$a" | grep -q '^\['; then echo "$r	analyses=$(echo "$a" | jq 'length')	last=$(echo "$a" | jq -r '.[0].commit_sha[0:8] // "-"')";
  else echo "$r	CODEQL=$(echo "$a" | jq -r '.message' 2>/dev/null | head -c 60)"; fi
done

echo
echo "=== R. DEPENDABOT CONFIG PRESENCE ==="
for r in $REPOS; do
  d=$(gh api "repos/$ORG/$r/contents/.github/dependabot.yml" -q '.size' 2>/dev/null || echo ABSENT)
  echo "$r	dependabot.yml=$d"
done

echo
echo "=== S. jolarca-control PRODUCTION ENVIRONMENT (verify D-70 wait_timer claim) ==="
gh api "repos/$ORG/jolarca-control/environments" 2>/dev/null | jq '.environments[] | {name, protection_rules, can_admins_bypass}'
echo "-- raw protection_rules array (assert on ARRAY not scalar) --"
gh api "repos/$ORG/jolarca-control/environments/production" 2>/dev/null | jq -c '{wait_timer_top: .wait_timer, rules: [.protection_rules[]? | {type, wait_timer}]}'
} > /tmp/jaudit/sweep4.txt 2>&1
echo EXIT=$?
