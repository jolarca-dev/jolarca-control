# raw probe — ctx.txt (wrapped 2026-10-26 so hash_evidence.sh:115 covers it)
```
=== FLEET SWEEP ===
repo	size_kb	protected	codeowners	secret_scan	push_prot	dep_alerts	license	branches	workflows	commits	open_prs	open_issues	last_commit
.github	27	true	.github/CODEOWNERS		disabled	204	NOASSERTION	3	3	1	1	1	2026-10-15T14:16:23Z
jolarca	2560	true	.github/CODEOWNERS		enabled	204	AGPL-3.0	21	4	1	16	16	2026-10-10T14:08:01Z
jolarca-compliance	255	true	.github/CODEOWNERS		enabled	204	NOASSERTION	3	10	1	2	3	2026-10-10T13:51:58Z
jolarca-consent	116	true	.github/CODEOWNERS		enabled	204	NOASSERTION	4	4	1	3	3	2026-10-15T14:25:39Z
jolarca-control	2074	true	.github/CODEOWNERS		enabled	204	NOASSERTION	11	8	1	7	8	2026-10-20T19:20:07Z
jolarca-data	131	true	.github/CODEOWNERS		enabled	204	NOASSERTION	1	9	1	0	1	2026-09-28T20:52:42Z
jolarca-docs	88	true	.github/CODEOWNERS		enabled	204	NOASSERTION	3	1	1	2	2	2026-09-30T14:57:46Z
jolarca-dr	47	true	.github/CODEOWNERS		enabled	204	NOASSERTION	2	1	1	1	1	2026-09-28T19:49:10Z
jolarca-hermes-agents	246	true	.github/CODEOWNERS		enabled	204	NONE	3	1	1	2	2	2026-10-04T13:43:56Z
jolarca-identity	46	true	.github/CODEOWNERS		enabled	204	NOASSERTION	3	1	1	1	1	2026-10-04T15:13:19Z
jolarca-infrastructure	439	true	{"message":"Not Found","documentation_url":"https://docs.github.com/rest/repos/contents#get-repository-content","status":"404"}{"message":"Not Found","documentation_url":"https://docs.github.com/rest/repos/contents#get-repository-content","status":"404"}ABSENT		enabled	204	NOASSERTION	8	8	1	6	9	2026-10-10T12:27:58Z
jolarca-legal	238	true	.github/CODEOWNERS		enabled	204	NOASSERTION	1	8	1	0	0	2026-09-28T21:47:53Z
jolarca-observability	66	true	.github/CODEOWNERS		enabled	204	NOASSERTION	3	2	1	2	2	2026-10-15T14:25:34Z
jolarca-payments	43	true	.github/CODEOWNERS		enabled	204	NONE	2	1	1	1	1	2026-10-10T14:08:10Z
jolarca-runbooks	84	true	.github/CODEOWNERS		enabled	204	NOASSERTION	4	1	1	3	3	2026-10-10T12:34:05Z
jolarca-security	125	true	.github/CODEOWNERS		enabled	204	NOASSERTION	2	2	1	1	1	2026-10-15T14:25:29Z
jolarca-vendor	134	true	.github/CODEOWNERS		enabled	204	NOASSERTION	3	1	1	1	1	2026-10-04T15:59:08Z

=== GIT LOG ===
1ef4f9b docs(classification): register data stores outside git, correct stale repo table (D-79)
2f2df3a fix(ci): plan.yml handed Terraform the runner-scoped token; use the read-only PAT (D-76) (#81)
e7e85dc fix(register): define the cited-but-undefined findings (D-53..D-57) and gate dangling references (D-73) (#80)
247f41a feat(register): finding-ID collision guard on the merge path (A-07); drop the stale truth pass (#51)
eee3abe ci(deploy-gates): verify the production apply gate on the merge path (D-58, D-70) (#41)
04444f8 docs(d70): the cancel window is proven usable, and the flag needed to use it (#78)

=== REGISTRY ===
jolarca-compliance.yml
jolarca-consent.yml
jolarca-control.yml
jolarca-data.yml
jolarca-docs.yml
jolarca-dr.yml
jolarca-hermes-agents.yml
jolarca-identity.yml
jolarca-infrastructure.yml
jolarca-legal.yml
jolarca-observability.yml
jolarca-payments.yml
jolarca-runbooks.yml
jolarca-security.yml
jolarca-vendor.yml
jolarca.yml

=== POLICY/AUDIT/DOCS ===
audit/:
gdpr-checklist.yml
iso27001-checklist.yml
pci-dss-checklist.yml
soc2-checklist.yml

docs/:
action-plan.md
adr
architecture.md
audit-plan-2026-10-06.md
change-management.md
data-classification.md
drift-findings.md
evidence-registry.csv
runbooks
runbooks.md
security
state-migration-runbook.md
threat-model.md

policy/:
compliance-gates.yml
contact-addresses.yml
repo-defaults.yml

staging/:
jolarca-dr
jolarca-identity
jolarca-payments
```
