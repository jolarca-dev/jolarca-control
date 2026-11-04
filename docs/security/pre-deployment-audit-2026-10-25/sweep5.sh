#!/bin/bash
ORG=jolarca-dev
{
for r in jolarca-consent jolarca-dr jolarca-vendor jolarca-identity jolarca-payments .github; do
  echo "=== $r ==="
  echo "  -- declared required contexts --"
  gh api "repos/$ORG/$r/branches/main/protection/required_status_checks" -q '.contexts[]' 2>/dev/null | awk '{print "    legacy: "$0}'
  for id in $(gh api "repos/$ORG/$r/rulesets" -q '.[].id' 2>/dev/null); do
    gh api "repos/$ORG/$r/rulesets/$id" 2>/dev/null | jq -r '.rules[] | select(.type=="required_status_checks") | .parameters.required_status_checks[]?.context' | awk '{print "    ruleset: "$0}'
  done
  echo "  -- job names a pull_request can actually report --"
  for f in $(gh api "repos/$ORG/$r/git/trees/main?recursive=1" -q '.tree[] | select(.path|startswith(".github/workflows")) | select(.path|endswith(".yml") or endswith(".yaml")) | .path' 2>/dev/null); do
    gh api "repos/$ORG/$r/contents/$f" -q '.content' 2>/dev/null | base64 -d 2>/dev/null | \
      awk -v F="$f" '
        /^on:/        {inon=1}
        /^[a-z]/ && !/^on:/ {inon=0}
        inon && /pull_request/ {pr=1}
        /^jobs:/      {injobs=1; next}
        injobs && /^  [A-Za-z0-9_.-]+:[ ]*$/ {job=$1; sub(/:$/,"",job); getline_done=0; curjob=job}
        injobs && /^    name:/ {n=$2; for(i=3;i<=NF;i++) n=n" "$i; gsub(/^["'"'"']|["'"'"']$/,"",n); print "    job: " curjob " -> reported-as: " n " (" F ")"; n=""}
      '
  done
  echo
done
} > /tmp/jaudit/sweep5.txt 2>&1
echo EXIT=$?
