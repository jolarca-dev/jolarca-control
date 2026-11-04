#!/bin/bash
ORG=jolarca-dev
{
echo "=== G. RULESETS on consent/dr/vendor (what do they ACTUALLY enforce?) ==="
for r in jolarca-consent jolarca-dr jolarca-vendor; do
  echo "--- $r ---"
  gh api "repos/$ORG/$r/rulesets" -q '.[] | "id=\(.id) name=\(.name) target=\(.target) enforcement=\(.enforcement)"' 2>/dev/null
  for id in $(gh api "repos/$ORG/$r/rulesets" -q '.[].id' 2>/dev/null); do
    gh api "repos/$ORG/$r/rulesets/$id" 2>/dev/null | jq -c '{name,enforcement,conditions,rules:[.rules[].type],bypass:[.bypass_actors[]?.actor]}'
  done
done

echo
echo "=== H. ORG TEAMS (is require_code_owner_reviews satisfiable?) ==="
gh api "orgs/$ORG/teams" -q 'length as \$n | "team_count=\$n"' 2>/dev/null || echo "TEAMS-UNREADABLE"
gh api "orgs/$ORG/teams" -q '.[] | "team=\(.slug) priv=\(.privacy) members=\(.members_count) repos=\(.repos_count)"' 2>/dev/null

echo
echo "=== I. ORG SECURITY / 2FA / MEMBER COUNT ==="
gh api "orgs/$ORG" -q '"two_factor=\(.two_factor_auth_enabled) plan=\(.plan.name) members=\(.members_count // "?") default_perm=\(.default_repository_permission) blog=\(.blog)"' 2>/dev/null
echo "-- org-level security.md served from .github repo --"
gh api "repos/$ORG/.github/contents/SECURITY.md" -q '"exists bytes=\(.size) sha=\(.sha)"' 2>/dev/null || echo "ABSENT"

echo
echo "=== J. LICENSE FILE REALITY CHECK (recursive tree, independent of /license API) ==="
for r in jolarca-hermes-agents jolarca-payments jolarca-infrastructure; do
  echo "--- $r ---"
  gh api "repos/$ORG/$r/git/trees/main?recursive=1" -q '.tree[] | select(.path|test("LICENSE|COPYING|NOTICE";"i")) | "\(.path) bytes=\(.size)"' 2>/dev/null
  echo "  CODEOWNERS paths:"
  gh api "repos/$ORG/$r/git/trees/main?recursive=1" -q '.tree[] | select(.path|test("CODEOWNERS")) | "  \(.path)"' 2>/dev/null
  echo "  (empty above = genuinely absent)"
done

echo
echo "=== K. .github REPO: shared workflows + action pin integrity ==="
gh api "repos/$ORG/.github/git/trees/main?recursive=1" -q '.tree[].path' 2>/dev/null
echo "-- reusable workflows referenced BY the fleet --"
for r in jolarca-consent jolarca-dr jolarca-vendor jolarca-identity; do
  echo "--- $r workflows ---"
  gh api "repos/$ORG/$r/git/trees/main?recursive=1" -q '.tree[] | select(.path|startswith(".github/workflows")) | .path' 2>/dev/null
done

echo
echo "=== L. jolarca (app repo) tree: what is actually being deployed ==="
gh api "repos/$ORG/jolarca/git/trees/main?recursive=1" -q '[.tree[].path] | length as \$n | "total_paths=\$n"' 2>/dev/null
gh api "repos/$ORG/jolarca/git/trees/main" -q '.tree[] | "\(.type)\t\(.path)"' 2>/dev/null
echo "-- backend/frontend/docker presence --"
gh api "repos/$ORG/jolarca/git/trees/main?recursive=1" -q '.tree[].path | select(test("Dockerfile|docker-compose|requirements|package.json|settings|manage.py|nginx|Caddyfile"))' 2>/dev/null | head -40

echo
echo "=== M. WORKFLOW ACTION PIN AUDIT (fleet-wide: uses: lines not pinned to 40-hex SHA) ==="
for r in $(gh repo list $ORG --limit 100 --json name -q '.[].name' | sort); do
  for f in $(gh api "repos/$ORG/$r/git/trees/main?recursive=1" -q '.tree[] | select(.path|startswith(".github/workflows")) | select(.path|endswith(".yml") or endswith(".yaml")) | .path' 2>/dev/null); do
    gh api "repos/$ORG/$r/contents/$f" -q '.content' 2>/dev/null | base64 -d 2>/dev/null | \
      grep -nE '^\s*uses:' | grep -vE 'uses:\s*\./' | grep -vE '@[0-9a-f]{40}' | \
      sed "s|^|$r/$f:|UNPINNED |"
  done
done
echo "(no UNPINNED lines above = every third-party action is SHA-pinned)"
} > /tmp/jaudit/sweep3.txt 2>&1
echo EXIT=$?
