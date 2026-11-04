#!/bin/bash
ORG=jolarca-dev
REPOS=$(gh repo list $ORG --limit 100 --json name -q '.[].name' | sort)
{
echo "=== T1. Do .github's three workflows even declare workflow_call? ==="
for f in ci-base.yml compliance-base.yml security-scan.yml; do
  echo "--- $f ---"
  gh api "repos/$ORG/.github/contents/.github/workflows/$f" -q .content | base64 -d 2>/dev/null \
    | awk '/^on:/{f=1} f&&/^[a-z]/&&!/^on:/{f=0} f{print "  "$0}' | head -12
done

echo
echo "=== T2. Fleet-wide search for cross-repo reusable-workflow calls ==="
hits=0
for r in $REPOS; do
  for f in $(gh api "repos/$ORG/$r/git/trees/main?recursive=1" -q '.tree[]|select(.path|startswith(".github/workflows"))|select(.path|test("\\.ya?ml$"))|.path' 2>/dev/null); do
    gh api "repos/$ORG/$r/contents/$f" -q .content | base64 -d 2>/dev/null \
     | grep -nE 'uses:[[:space:]]*[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/\.github/workflows/' \
     | awk -v R="$r" -v F="$f" '{print "CALL  " R "/" F "  " $0}'
  done
done
echo "--- (no CALL lines above = NOTHING in the fleet inherits .github's reusable workflows) ---"
} > /tmp/jaudit/sweep6.txt 2>&1
echo EXIT=$?
