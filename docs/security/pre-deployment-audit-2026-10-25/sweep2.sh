#!/bin/bash
ORG=jolarca-dev
{
echo "=== A. SECRET SCANNING / PUSH PROTECTION / VULN ALERTS ==="
for r in $(gh repo list $ORG --limit 100 --json name -q '.[].name' | sort); do
  j=$(gh api "repos/$ORG/$r" 2>/dev/null)
  ss=$(echo "$j" | jq -r '.security_and_analysis.secret_scanning.status // "NULL"')
  pp=$(echo "$j" | jq -r '.security_and_analysis.secret_scanning_push_protection.status // "NULL"')
  adv=$(echo "$j" | jq -r '.security_and_analysis.advanced_security.status // "NULL"')
  echo "$r	secret_scan=$ss	push_prot=$pp	adv_sec=$adv"
done

echo
echo "=== B. BRANCH PROTECTION DETAIL (main) ==="
for r in $(gh repo list $ORG --limit 100 --json name -q '.[].name' | sort); do
  p=$(gh api "repos/$ORG/$r/branches/main/protection" 2>/dev/null)
  if [ -z "$p" ]; then echo "$r	UNREADABLE-OR-404"; continue; fi
  echo "$r	reviews=$(echo "$p"|jq -r '.required_pull_request_reviews.required_approving_review_count // "none"')	codeowner=$(echo "$p"|jq -r '.required_pull_request_reviews.require_code_owner_reviews // "n/a"')	strict=$(echo "$p"|jq -r '.required_status_checks.strict // "n/a"')	enforce_admins=$(echo "$p"|jq -r '.enforce_admins.enabled // "n/a"')	contexts=$(echo "$p"|jq -rc '.required_status_checks.contexts // []')	linear=$(echo "$p"|jq -r '.required_linear_history.enabled // "n/a"')"
done

echo
echo "=== C. RULESETS ==="
for r in $(gh repo list $ORG --limit 100 --json name -q '.[].name' | sort); do
  echo "$r	rulesets=$(gh api "repos/$ORG/$r/rulesets" -q 'length' 2>/dev/null || echo ERR)"
done

echo
echo "=== D. COMMIT VOLUME / FIRST+LAST COMMIT ==="
for r in $(gh repo list $ORG --limit 100 --json name -q '.[].name' | sort); do
  tot=$(gh api "repos/$ORG/$r/contributors?per_page=100&anon=true" -q 'map(.contributions)|add // 0' 2>/dev/null || echo NA)
  last=$(gh api "repos/$ORG/$r/commits?per_page=1" -q '.[0].commit.committer.date // "NA"' 2>/dev/null || echo NA)
  contribs=$(gh api "repos/$ORG/$r/contributors?per_page=100" -q 'map(.login)|join(",")' 2>/dev/null || echo NA)
  echo "$r	commits~=$tot	last=$last	contributors=$contribs"
done

echo
echo "=== E. OPEN PRs (all repos, with author + age) ==="
for r in $(gh repo list $ORG --limit 100 --json name -q '.[].name' | sort); do
  gh pr list -R $ORG/$r --state open --limit 100 --json number,title,author,createdAt,isDraft,mergeable \
     -q "\"$r\" as \$r | .[] | \"\(\$r)\t#\(.number)\t\(.author.login)\tdraft=\(.isDraft)\tmergeable=\(.mergeable)\t\(.createdAt)\t\(.title)\"" 2>/dev/null
done

echo
echo "=== F. LICENSE FILE IDENTIFICATION ==="
for r in $(gh repo list $ORG --limit 100 --json name -q '.[].name' | sort); do
  l=$(gh api "repos/$ORG/$r/license" -q '.license.spdx_id + " | " + .path' 2>/dev/null || echo "NO-LICENSE-ENDPOINT")
  first=$(gh api "repos/$ORG/$r/contents/LICENSE" -q '.content' 2>/dev/null | head -c 200 | base64 -d 2>/dev/null | head -2 | tr '\n' ' ')
  echo "$r	spdx=$l	head=${first:0:120}"
done
} > /tmp/jaudit/sweep2.txt 2>&1
echo EXIT=$?
