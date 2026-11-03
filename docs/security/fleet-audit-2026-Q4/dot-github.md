# Fleet Audit 2026-Q4 — `jolarca-dev/.github` (organization health / shared CI)

**Verdict: NO-GO.** Five S1, six S2, one S3.
Baseline `main` = `48b96656c6779788cf84444fc0973f9697d18dcb`, manifest fingerprint `e6238ace…e1fb`,
13 blobs, 4 commits. Machine-readable register: [`dot-github.yml`](dot-github.yml).
Measured 2026-10-26, read-only. (Repo is literally named `.github`; the record file is
`dot-github.yml` because a dotfile named `.github.yml` would be skipped by glob-based tooling.)

**Why this repo is audited first.** It is the only repo in the fleet that simultaneously
(a) publishes the organization's vulnerability-disclosure policy, (b) contains the fleet's only
implementation of five *mandatory* compliance gates, and (c) is protected by nothing. Its file
count is 13 and its risk rank is first.

---

## The five questions, answered for `.github`

| Question | Answer | Evidence |
|---|---|---|
| Can a commit reach `main` without a PR? | **No rule forbids a PR-less merge**; and with 0 required contexts a PR needs nothing green | `required_pull_request_reviews.required_approving_review_count=0`, `required_status_checks.contexts=[]` |
| Can it reach `main` with red CI? | **Yes — there is no check that must be green at all** | `contexts=[]`, `strict=false`, `rulesets=[]` |
| Can an admin bypass it? | **No** — `enforce_admins.enabled=true` | protection document |
| Is the required list non-empty? | **Empty.** `rulesets=0` means no second layer either | `gh api …/rulesets -q length` → `0` |
| Does a `pull_request` rule exist? | No ruleset at all; legacy protection has the review block with `0` approvals and `require_code_owner_reviews=false` | protection document |

Historical note that matters for severity, not for comfort: all three non-root commits on `main`
arrived through PRs (#1, #2, #5). The weak gates have not been abused **yet**. Capability, not
incident.

---

## FA-dotgithub-01 · S1 — every secret-detection layer is off

`security_and_analysis` returns `secret_scanning=disabled`,
`secret_scanning_push_protection=disabled`, `secret_scanning_non_provider_patterns=disabled`,
`secret_scanning_validity_checks=disabled`, `dependabot_security_updates=disabled`.

**Reproduce.**
```bash
gh api repos/jolarca-dev/.github -q '.security_and_analysis'
```
**Why it happens.** This repo was created as a GitHub convention repo, not through the fleet's
Terraform path with `var.enable_secret_scanning = true`. It is managed by `health-repo.tf`, and
`compliance_check.py` iterates `repos/*.yml`, which does not contain it (FA-dotgithub-04). So the
setting was never propagated. Compare `jolarca-consent`, where all three are enabled.

**Impact.** A credential pasted into a workflow file here is neither detected on push nor flagged
afterwards, in the repo whose workflows 16 other repos are documented to call. It is also the repo
whose `SECURITY.md` GitHub serves organization-wide — the disclosure channel for all 17 — so the
weakest-scanning repo is the one external researchers write into.

**Fix.** Enable secret scanning + push protection; add `dependabot.yml`; then re-read to confirm,
because GitHub's `security_and_analysis` on Free has previously answered inconsistently (D-63).

**Test.** `gh api repos/jolarca-dev/.github -q '.security_and_analysis.secret_scanning.status'`
must print `enabled`, plus a negative control: a synthetic runtime-assembled credential pushed to a
scratch branch must be refused. Never commit a real-looking fixture (AGENTS.md §5).

**Rollback.** Settings-only; disable again. Note that rollback restores the exposure, so it should
not be the default mitigation for anything else that breaks.

---

## FA-dotgithub-02 · S1 — zero required contexts on the organization's own repo

Protection exists (`.protected=true`, `enforce_admins=true`, linear history, no force-push, no
deletion, conversation resolution) yet `required_status_checks.contexts=[]` and
`strict=false`. So *nothing* has to pass, and *nothing* has to be up to date.

**Reproduce.**
```bash
gh api repos/jolarca-dev/.github/branches/main/protection \
  -q '{ctx:.required_status_checks.contexts, strict:.required_status_checks.strict,
       rarc:.required_pull_request_reviews.required_approving_review_count,
       cor:.required_pull_request_reviews.require_code_owner_reviews,
       admins:.enforce_admins.enabled}'
```
**Why it happens.** `required_status_checks` requires a context name that a job actually reports on
a `pull_request` event. This repo has **no workflow with a `pull_request` trigger** — all three
files are `on: workflow_call` only — so there was never a candidate name to add. That is not an
excuse; it is the mechanism, and it points at FA-dotgithub-11.

**Impact.** Any future workflow added here (or any edit to the 17 existing jobs) merges unverified.
Because reusable workflows run with the **caller's** token and repository context, an unreviewed
edit here is a latent supply-chain entry for all 16 callers the day anyone wires them up.

**Fix.** Add a minimal `pull_request`-triggered lint workflow here (`yamllint` + `actionlint` +
a pin-integrity check), then require it. Order matters: **pin the actions first**
(FA-dotgithub-10, PR #4), require contexts second, wire callers last.

**Test.** The new context must appear in `…/protection/required_status_checks`; then open a scratch
PR with a deliberately bad YAML file and confirm the check goes red and the merge is refused.

---

## FA-dotgithub-03 · S1 — the control plane is built to report this as acceptable

`policy/repo-defaults.yml:216` lists `.github` under `branch_protection_baseline_exempt`. In
`scripts/drift_detect.py`, an exempt repo with too few contexts is routed to `hollow_rules`
(informational), and `drift_detected` (lines 870-881) does **not** include `hollow_rules`. Measured
output from a live run:

```json
"hollow": [{"repo": ".github", "issues": ["exempt rule requires 0 status check(s), need >= 1"]}]
```

**Why this is the most important finding in this file.** The exemption was written to skip
*attribute comparison* for repos whose protection is intentionally minimal — not to certify an
empty check list. As implemented, once consent and vendor are fixed, `drift_detect.py` can print
`NO DRIFT` while this repo gates nothing at all. That is AGENTS.md §7's "a gate that runs and
reports green has not been shown to detect anything", in configuration rather than code.

**Fix.** Either include `hollow_rules` in `drift_detected`, or split the exemption into
"skip attribute comparison" and "may require zero checks" and give `.github` only the former.

**Test (negative control, mandatory).** A fixture shaped exactly like this repo's live document —
legacy protection present, `contexts=[]`, exempt — must produce exit `1`. Use
`tests/test_check_plan_safety.sh` as the model. Without it, the fix is another unverified regex.

---

## FA-dotgithub-04 · S1 — the repo is outside every declared-configuration gate

`repos/` holds 16 YAML entries and no `.github`; the fleet registry grep returns 0. `.github` is
created by `health-repo.tf:26` (`resource "github_repository" "health"`). Consequences measured:
`compliance_check.py` reports `total_repos: 16`; `repo_readiness_audit.py` prints 16 rows with no
`.github`; `validate_repos.py` never sees it. `drift_detect.py` is the one tool that knows it exists
(`HEALTH_REPO = ".github"`, line 60) — and it deliberately excludes it from fleet/visibility drift
(line 820) while including it in protection, admins and CODEOWNERS (line 827).

**Impact.** A whole class of policy — data classification vs visibility, merge method, wiki/projects,
declared contexts — has no expression for this repo at all. FA-dotgithub-05 is the direct result.

**Fix.** Add `repos/dot-github.yml` (or teach the loaders that `health-repo.tf` is a fleet source),
and let `validate_repos.py` classify it as `internal`/public-coherent like any other repo.

**Risk during remediation.** `check_declared_contexts.py` / `check_required_context_baseline.py`
compare declarations against jobs a `pull_request` can report. Declaring contexts here before the
lint workflow exists (FA-dotgithub-02's fix) would fail D-62's baseline gate. Declare after.

---

## FA-dotgithub-05 · S2 — live settings contradict the fleet baseline, undetectably

Live: `allow_merge_commit=true`, `allow_rebase_merge=true`, `has_projects=true`,
`delete_branch_on_merge=false`. `policy/repo-defaults.yml:30-37`: `allow_merge_commit: false`,
`allow_rebase_merge: false`, `has_projects: false`, squash-only justified as
"squash-only keeps a linear, auditable history" (also cited as SOC 2 CC8.1 at line 253).

Note the nuance a careless auditor gets wrong: `required_linear_history.enabled=true` **is** set, so
history stays linear despite the merge options being open. The defect is declaration drift and a
wider merge surface, not a broken linear history.

---

## FA-dotgithub-06 · S1 — the published security policy asserts controls that are not in place

The `SECURITY.md` GitHub serves organization-wide contains a "Security Controls" section claiming:
"Branch protection: Required reviews, status checks" (measured: 0 approvals required, 0 checks
required); "Dependency scanning: Dependabot alerts enabled" (alerts endpoint returns 204 = enabled,
but there is no `dependabot.yml` and security updates are disabled); "Pre-commit hooks: gitleaks"
(no `.pre-commit-config.yaml` anywhere in the 13-blob tree); "Signed commits: GPG verification
recommended" (`required_signatures.enabled=false`).

**Why S1 and not S2.** AGENTS.md §6 requires documents to state actual implementation status, and
§8 exists precisely to stop a reader assuming protection that is not there. This file does the
opposite, in public, for every repo in the organization. An external researcher told "required
reviews and status checks" may reasonably delay disclosure — a process risk on the disclosure
channel itself.

**Counter-evidence worth recording, because the file is not all wrong.** The same document is
honest about the hard part: it names `journey4oflife+jolarca.security@gmail.com` as the working
route, states that `security@jolarca.com` is **undeliverable** (`jolarca.com` has no MX and no
DMARC, measured 2026-10-15), refuses to assert that private vulnerability reporting is enabled
because "GitHub does not expose this setting through the API", and labels the Gmail plus-aliases as
interim routing with a named exit condition. That was fixed by PR #5, merged 2026-10-15. The contact
paragraph is accurate; the "Security Controls" paragraph is not.

**Fix.** Delete or rewrite the four claims to say what is configured *and* what is enforced; move
the file under Terraform (`health-repo.tf`, D-15) so an edit here propagates instead of being a
reference copy.

**Test.** A gate that compares published `SECURITY.md` against `policy/contact-addresses.yml` and
against live protection state — the gap AGENTS.md §8 records as "convention-only" (D-59).

---

## FA-dotgithub-07/08/09/10/11/12/13 — summary

| ID | Sev | Defect | Evidence |
|---|---|---|---|
| FA-dotgithub-07 | S3 | `SECURITY.md:102` cites "ISO 27001 A.12.6.1" — 2013 Annex A numbering, superseded by ISO/IEC 27001:2022 | file read |
| FA-dotgithub-08 | S2 | `LICENSE` = "INTERNAL USE ONLY / © 2026 **JOL Infrastructure** … confidential and proprietary" on a **public** repo: mission-platform entity inside the marketplace (ADR-0004 R4) + a confidentiality claim contradicted by visibility + no licence grant | `contents/LICENSE` |
| FA-dotgithub-09 | S2 | `CODEOWNERS` assigns `@jolarca-dev/infrastructure` and `@jolarca-dev/security`; org teams = `[]`; `require_code_owner_reviews=false` → inert by two independent causes | `contents/.github/CODEOWNERS`, `orgs/jolarca-dev/teams` |
| FA-dotgithub-10 | S2 | 11 tag-referenced actions in 3 reusable workflows (`setup-python@v5` ×6, `setup-node@v4`, `setup-terraform@v3`, `upload-sarif@v3` ×2). Documented call form is `@main` — a mutable ref into a repo with no required checks | `uses:` scan, line numbers in register |
| FA-dotgithub-11 | S2 | 17 defined jobs, **zero** consumers, **zero** workflow runs ever (`gh run list` → `[]`), while they are the fleet's only implementation of 5 gates declared mandatory | run list + fleet-wide `uses:` scan excluding comments |
| FA-dotgithub-12 | S2 | Merge method allows merge-commit and rebase; subsumed by FA-dotgithub-05 but named because CC8.1 cites squash-only | `allow_*` fields |
| FA-dotgithub-13 | S2 | PR #4 ("finish pinning the shared workflows; remove the last fabricated SHA (D-43 part 1)") OPEN since 2026-10-04, `mergeable=MERGEABLE`, 22 days | `gh pr view 4` |

---

## Remediation order for this repository

Ordering is not cosmetic — the wrong sequence turns a hardening into a supply-chain incident.

1. **Merge PR #4 / pin the 11 references** (FA-dotgithub-10). Do this while nothing calls these workflows.
2. **Enable secret scanning + push protection**, add `dependabot.yml` (FA-dotgithub-01).
3. **Add a `pull_request`-triggered lint workflow**, then require it (FA-dotgithub-02).
4. **Fix the exemption semantics + negative control** (FA-dotgithub-03).
5. **Bring `.github` into the declared fleet registry** (FA-dotgithub-04), then let drift detection
   resolve the settings divergence (FA-dotgithub-05, -12).
6. **Rewrite the four false claims in `SECURITY.md`** and move it under Terraform (FA-dotgithub-06, -07).
7. **Decide FA-dotgithub-11 deliberately**: wire the shared workflows up (pinned to a SHA, never
   `@main`, and only after steps 1-3) **or** delete them and re-declare the five gates against what
   actually runs. Leaving them is the worst option: policy claims them, code exists, nothing executes,
   and a comment says it does.
8. Resolve the licence question once for the fleet: `.github` is public because GitHub requires the
   org-health repo to be, so either give it a real SPDX licence or state "no grant; public by
   necessity" — and fix the `JOL Infrastructure` holder string (FA-dotgithub-08).

**Blocked, not skipped:** creating `@jolarca-dev/*` teams is not possible while the org has 0 teams
and D-04's solo-operator constraint stands, so FA-dotgithub-09 cannot be closed by configuration
alone. Record that as an accepted risk with its compensating controls, per
`policy/compliance-gates.yml#exceptions.active`, rather than leaving the CODEOWNERS file implying
review that cannot happen.
