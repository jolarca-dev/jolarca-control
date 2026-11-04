#!/bin/bash
# Read-only fleet evidence sweep. No writes to GitHub.
ORG=jolarca-dev
OUT=/tmp/jaudit/fleet.tsv
: > "$OUT"
printf 'repo\tsize_kb\tprotected\tcodeowners\tsecret_scan\tpush_prot\tdep_alerts\tlicense\tbranches\tworkflows\tcommits\topen_prs\topen_issues\tlast_commit\n' >> "$OUT"
for r in $(gh repo list $ORG --limit 100 --json name -q '.[].name' | sort); do
  size=$(gh api "repos/$ORG/$r" -q '.size' 2>/dev/null || echo NA)
  prot=$(gh api "repos/$ORG/$r/branches/main" -q '.protected' 2>/dev/null || echo "no-main")
  co=$(gh api "repos/$ORG/$r/contents/.github/CODEOWNERS" -q '.path' 2>/dev/null || \
       gh api "repos/$ORG/$r/contents/CODEOWNERS" -q '.path' 2>/dev/null || echo ABSENT)
  ss=$(gh api "repos/$ORG/$r" -q '.security_and_analysis.advanced_security.status' 2>/dev/null || echo NA)
  pp=$(gh api "repos/$ORG/$r" -q '.security_and_analysis.secret_scanning_push_protection.status' 2>/dev/null || echo NA)
  va=$(gh api "repos/$ORG/$r/vulnerability-alerts" -i 2>&1 | head -1 | grep -o '204\|404\|403' || echo NA)
  lic=$(gh api "repos/$ORG/$r" -q '.license.spdx_id // "NONE"' 2>/dev/null || echo NA)
  nb=$(gh api "repos/$ORG/$r/branches" -q 'length' 2>/dev/null || echo 0)
  wf=$(gh api "repos/$ORG/$r/contents/.github/workflows" -q 'length' 2>/dev/null || echo 0)
  nc=$(gh api "repos/$ORG/$r/commits?per_page=1" -q 'length' 2>/dev/null || echo 0)
  pr=$(gh api "repos/$ORG/$r/pulls?state=open&per_page=100" -q 'length' 2>/dev/null || echo 0)
  is=$(gh api "repos/$ORG/$r" -q '.open_issues_count' 2>/dev/null || echo NA)
  lc=$(gh api "repos/$ORG/$r/commits?per_page=1" -q '.[0].commit.committer.date' 2>/dev/null || echo NA)
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
    "$r" "$size" "$prot" "$co" "$ss" "$pp" "$va" "$lic" "$nb" "$wf" "$nc" "$pr" "$is" "$lc" >> "$OUT"
  echo "done: $r"
done
