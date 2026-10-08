# Drift & Findings Register — jolarca-dev control plane

**Created:** 2026-09-25
**Last verified:** 2026-10-03 (read-only live protection check on `jolarca-hermes-agents`; declared-vs-enforced gap recorded as D-40, stale `branch-protection.tf` rationale as D-41); 2026-10-04 fleet-wide pin scan across the 16 allow-listed repos plus `jolarca-dev/.github` (D-43); 2026-10-04 context-parity check first live run (D-47); 2026-10-04 declared-vs-enforced sweep over the exempt list (D-48); 2026-10-04 recount from refs (D-43 correction) + security scan failure (D-49); 2026-10-04 D-47 re-measured end to end -- jolarca-security#2 4/4 green; 2026-10-05 chain landed -- jolarca-security main 904a699 reports all four contexts green on push, jolarca-control main f35c69e declares them, parity check finds jolarca-security clean and jolarca-identity still dirty; enforcement pending apply; 2026-10-05 CI regression step ran through a swallowed fallback to an interpreter no workflow installs (D-50); 2026-10-05 actions/checkout pinned to v5.0.0 under a # v4.3.0 comment, carried onto v7.0.1 by the bump (D-51); 2026-10-04 declared-vs-live settings audit and shared CI base failure audit (D-44, D-45); 2026-10-04 ruleset reality check against branch-protection.tf (D-46)
**Method:** every row below was verified empirically against the live GitHub
API (`gh api`, read-only) and against
`jolarca-infrastructure/terraform/environments/production/terraform.tfstate`.
Nothing here is inferred from documentation.

**Why this file exists:** `jolarca-control` declares *intended* state. Where
intent and live reality differ, the difference is recorded here with a
decision owner and a blocking flag, so the first `terraform apply` cannot
silently make a large change nobody approved.

Severity: **S0** stop-work · **S1** fix before first apply · **S2** fix soon ·
**S3** tracked hygiene.

---

## S0 — stop-work

### D-02 · Live Terraform state is single-copy with no remote backend — **PARTIALLY FIXED**
| | |
|---|---|
| Evidence | `main.tf` has `cloud {}` block (HCP Terraform, ADR-0006). Workflows updated with `cli_config_credentials_token`. **Local state frozen:** `terraform.tfstate` (67KB, serial 151, 6 resources) exists on disk but `terraform state list` fails with "HCP Terraform initialization required" — the cloud block prevents local state access until `terraform init -migrate-state` runs. |
| Impact | State file safe on disk but inaccessible via Terraform CLI. No `terraform plan`, `apply`, or `import` can run until the HCP account is created and state is migrated. |
| Fix in progress | **Blocked on manual step:** owner must sign up at https://portal.terraform.io/, create org `jolarca-dev`, workspace `jolarca-control`, generate API token, set `TFC_TOKEN` GitHub secret, then run `terraform init -migrate-state`. |
| Local state contents | 2 `github_repository`, 2 `github_repository_vulnerability_alerts`, 1 `github_branch_protection`, 1 `github_organization_webhook`. |
| Interim control | AGE-encrypted state backup via `scripts/state_backup.sh` (pubkey at `.state-backup-pubkey.txt`, identity at `~/.config/age/state-backup-key.txt`). Legacy state (jolarca-infrastructure) is empty — D-13 fully resolved. |

### D-13 · Dual-ownership window between the two roots — **FIXED**
| | |
|---|---|
| Evidence | `module.github_org.*` is live in `jolarca-infrastructure` production state. `jolarca-control/{repositories,branch-protection,health-repo}.tf` now declares the same real resources. |
| Impact | Two Terraform roots claiming the same GitHub objects. An apply from either side can undo the other; a `destroy` from the old root deletes real repositories. |
| Control in place | `lifecycle { prevent_destroy = true }` on every `github_repository`; `apply.yml` refuses plans containing destroy/replace; `vars.STATE_MIGRATION_COMPLETE` gate blocks apply entirely until the runbook completes. |
| Fix applied | **2026-10-01:** All 12 GitHub resources removed from legacy state via `terraform state rm` in `/opt/jolarca/repos/jolarca-infrastructure/terraform/environments/production/`. Removed: 1 `github_branch_protection`, 6 `github_repository` (5 repos + dot_github), 5 `github_repository_vulnerability_alerts`. Verified: legacy `terraform state list` returns empty (zero resources). Pre-cleanup backup saved as `terraform.tfstate.pre-d13-cleanup.bak`. New root (jolarca-control) unaffected: 35 resources, serial 151. |
| Resolved | Dual ownership eliminated. The new root is now the sole Terraform authority for all fleet GitHub resources. |

---

## S1 — fix before first apply

### D-01 · Four repositories are PUBLIC but declared private — **BLOCKING DECISION**
| | |
|---|---|
| Evidence | Live API 2026-09-25 (re-verified): **all six** repositories in `jolarca-dev` return `visibility: public` / `private: false` — `jolarca`, `jolarca-compliance`, `jolarca-data`, `jolarca-infrastructure`, `jolarca-legal`, `.github`. Intent of record — `jolarca-infrastructure/terraform/modules/github-org/variables.tf` marks the four above `visibility = "private"`, and its `main.tf` states *"The infrastructure, compliance, legal, and data repos in this fleet are private."* Terraform state (Aug 31) also records `private: true` for all four. **Dated baseline:** change record `JOL-ORGTRANSFER-20260902-01` captured pre-transfer visibility on 2026-09-02 as `jolarca` public, `jolarca-infrastructure` public, `jolarca-compliance` public, `jolarca-legal` public, **`jolarca-data` private**. |
| Impact | Publicly readable inside a PCI-DSS / KYC-AML / VAT-OSS scope: DPIAs and RoPA entries, executed contracts and DPAs, the full PII and payment data model, and network topology / hostnames / WireGuard layout. GDPR Art. 5(1)(f) and Art. 32; PCI-DSS Req 1.2 scope definition. |
| How it drifted | Two distinct events, not one. (1) `jolarca-compliance`, `jolarca-infrastructure` and `jolarca-legal` were **already public on 2026-09-02**, i.e. before the org transfer — they diverged from the module's declared `private` at some point after the state was last written (Aug 31 23:15). (2) `jolarca-data` has a *documented* private baseline on 2026-09-02 and is public on 2026-09-25, so it regressed **within that window** — a verifiable change against a dated record, not merely an undeclared divergence. The 2026-09-17 delivery-chain audit recorded "six public repos" as a *baseline observation* and did not remediate. Because Terraform was never re-applied, none of this ever surfaced as a plan diff. The exact flip timestamps cannot be pinned: `GET /orgs/jolarca-dev/audit-log` returns **HTTP 404** on this org's plan. |
| What this repo declares | `visibility: private` for all four — the intent of record. **This is a decision, not a default.** |
| Required | Owner must explicitly choose: (a) keep private → first apply flips four repos private, breaking any public fork/Pages/external-contributor workflow; or (b) accept public → edit the four `repos/*.yml` files and record the risk acceptance here. `apply.yml` hard-refuses any plan that changes visibility, so neither path can happen by accident. |

### D-03 · Marketplace state owns the MISSION org's `.github` repo
| | |
|---|---|
| Evidence | State: `module.github_org.github_repository.dot_github` → `full_name = "journeyoflife-org/.github"`, `html_url = https://github.com/journeyoflife-org/.github`. The provider owner was `journeyoflife-org`. A separate `jolarca-dev/.github` also exists (verified live) and is managed by **nothing**. |
| Impact | Direct ADR-0004 / ISO 27001 A.8.13 cross-scope violation: the marketplace (PCI) root holds a write-capable resource handle on a mission-platform repository. It also means `jolarca-dev`'s own health repo has never been under IaC control. |
| Required | Do **not** migrate this state entry into `jolarca-control`. Either hand it to `jol-control` (correct owner) or `terraform state rm` it from the old root. `jolarca-control/health-repo.tf` then adopts `jolarca-dev/.github` by import. Runbook step 4. |

### D-06 · Provider owner pointed at the wrong organization — **FIXED in this change**
| | |
|---|---|
| Evidence | `modules/github-org/variables.tf` `variable "org"` default `= "journeyoflife-org"`; `environments/production/variables.tf` same; `provider "github" { owner = var.org }`. The fleet was transferred to `jolarca-dev` on 2026-09-02 (`docs/compliance/evidence/change-record-org-transfer-jolarca-dev-20260902.md`). State file mtime is **Aug 31 23:15** — it predates the transfer. Meanwhile `scripts/check-fleet-separation.sh` and `scripts/org-delivery-audit.sh` already hardcode `ORG="jolarca-dev"`. |
| Impact | Any `terraform plan` run today addresses `journeyoflife-org`, where the `jolarca*` names survive only as 2-hop redirect stubs. Depending on how the provider resolves the redirect, that risks planning changes against — or destroying — the real repositories now living in `jolarca-dev`. |
| Fix applied | `var.org` default corrected to `jolarca-dev` in both files; the old root is additionally marked FROZEN with `prevent_destroy` added. See `jolarca-infrastructure` working-tree diff. |

### D-08 · Branch protection was applied out-of-band, not by Terraform
| | |
|---|---|
| Evidence | State contains `github_branch_protection.main` for **`jolarca` only** (1 of 5). Live API shows protection on **all six** repos including `.github`. `docs/superpowers/plans/2026-09-17-delivery-chain-audit-all-repos.md` documents the mechanism: `gh api .../branches/main/protection -X PUT --input`. |
| Impact | Five of six protection rules are unmanaged. Config also disagrees with reality: the old module passed `require_code_owner_reviews = false`, live value is `true` on all five `jolarca*` repos. A refresh-and-apply from the old root would have *weakened* CODEOWNERS enforcement. |
| Fix applied | `jolarca-control` encodes the **verified live** values per repo (`require_code_owner_reviews = true`, `strict = true`, per-repo contexts). Runbook step 5 imports all six protection rules into the new state. **Note:** encoding the live value faithfully reproduces the defect described in **D-20** — `require_code_owner_reviews = true` is currently unsatisfiable fleet-wide. Fixing it is a deliberate decision, not a migration side effect. **Correction (2026-09-26):** the premise above — and the `terraform.tfvars` comment derived from it — that the out-of-band rules "remain in place" is **false for private repositories**. Since four of the six repos were flipped private inside a Free-plan org, their protection is neither readable (HTTP 403) nor enforced (`.protected = false`), and there are no six rules left for runbook step 5 to import: two survive, on `jolarca` and `.github`. See **D-33**. |

### D-20 · CODEOWNERS is fleet-wide unresolvable and points at the MISSION org — **FIXED**
| | |
|---|---|
| Evidence | All six repos carry `.github/CODEOWNERS` (**not** at the repo root — a root-only check misses it). Verified team inventory: `gh api orgs/jolarca-dev/teams` → **zero teams**; `gh api orgs/journeyoflife-org/teams` → exactly `backend`, `data`, `devops`, `frontend`, `security`; `gh api orgs/jol-infrastructure` → **HTTP 404, no such organization**. Against that, the entries in force are: `jolarca` → `@jol-infrastructure/{payments,compliance,platform}-owners`; `jolarca-data` → `@journeyoflife-org/{data-operators,compliance,finance,marketplace-product,security}`; `jolarca-compliance` → `@journeyoflife-org/{compliance-leads,dpo,legal}`; `jolarca-legal` → `@journeyoflife-org/{general-counsel,retained-counsel,security}`; `jolarca-infrastructure` → `@journeyoflife-org/{infra-operators,security,compliance}`; `.github` → `@jolarca-dev/{infrastructure,security}`. Branch protection requires code-owner review on all five `jolarca*` repos (`require_code_owner_reviews = true`, `enforce_admins = true`, `required_approving_review_count = 0`). |
| Resolution analysis | **Not one entry resolves to a team that can review a `jolarca-dev` pull request.** `@jol-infrastructure/*` names an organization that does not exist. Every `@journeyoflife-org/*` entry except `security` names a team that does not exist, and `security` exists in the *mission* org — GitHub cannot grant review rights across organizations, so it is inert here too. `@jolarca-dev/{infrastructure,security}` are correctly scoped but **no teams exist in `jolarca-dev` at all**. The org has exactly one member (`JourneyOfLife`), who cannot approve their own pull request. |
| Impact | Three distinct failures. **(1) The control is vacuous, not blocking — proven empirically.** `jolarca-infrastructure` PR #26 merged 2026-09-18T10:59:05Z (42 files, 27 commits) with `review_decision: null`, **zero reviews**, and `requested_reviewers` empty for both users and teams — i.e. GitHub requested no code owner at all despite the setting being on. The same holds fleet-wide: every sampled merged PR (`jolarca` #92/#89, `jolarca-data` #6/#5/#3, `jolarca-compliance` #12/#11/#10, `jolarca-legal` #10/#9/#8) shows zero reviews. So `require_code_owner_reviews = true` neither routes review nor gates merge; it is inert. **The correct conclusion is that no human review occurs on any change in this org — not that the owner is locked out.** (An earlier draft of this finding asserted a lockout risk; that was wrong and is corrected here, because a PR merged under the identical configuration.) **(2) ADR-0004 R4 is violated in live production:** R4 forbids "no CODEOWNERS, workflow, or module in one project references the other's", yet five PCI-DSS-scoped marketplace repositories name mission-org teams as their reviewers. This survived the 2026-09-02 org transfer because GitHub copies CODEOWNERS content verbatim and does not rewrite team references. **(3) Segregation of duties is fictional:** the DPO, general-counsel, compliance-leads and security review paths the compliance narrative depends on designate principals that do not exist in the governing org. ISO 27001 A.5.3/A.5.4, SOC 2 CC6.1/CC8.1, PCI-DSS Req 7. |
| Documentation impact | Because the setting is inert, every document claiming CODEOWNERS as a working human gate is **factually false** and was corrected in this change: `docs/change-management.md`, `docs/architecture.md`, `CONTRIBUTING.md`, `README.md`, `docs/threat-model.md` (T-01, RA-02), `policy/repo-defaults.yml`, `policy/compliance-gates.yml`, `variables.tf`, `.github/CODEOWNERS`, `docs/security/key-custody.md`, and the SOC 2 / ISO 27001 / PCI-DSS checklists. The claim "satisfiable because the sole operator is a listed code owner" is doubly wrong: the operator is the PR *author* and cannot approve their own pull request, and GitHub does not enforce the requirement here at all. |
| Why it was missed | The `integrations/github` provider does not manage CODEOWNERS content, so Terraform never saw it. The old `github-org` module set `require_code_owner_reviews = false`, so the setting was inert until it was flipped to `true` out-of-band (D-08) — after which nothing validated that a code owner actually existed. This register previously claimed "CODEOWNERS review ON" as a compensating control for D-04; **that claim was wrong** and is corrected below. |
| Fix applied | **2026-09-25:** All five `.github/CODEOWNERS` files (jolarca, jolarca-data, jolarca-compliance, jolarca-legal, jolarca-infrastructure) were rewritten to reference `@JourneyOfLife` instead of cross-org teams. Each file includes a header comment explaining the separation (ADR-0004 R4), the current single-operator state, and that teams should be created when the second operator arrives. The `.github` repo's CODEOWNERS was already correct (using `@jolarca-dev/*`). Verified: `grep -E '@journeyoflife-org|@jol-infrastructure'` returns no matches in any of the six CODEOWNERS files. The control remains inert (one member cannot approve their own PR), but the cross-org violation is resolved and the documentation now accurately reflects reality. When teams are created, update CODEOWNERS to use team slugs and raise `required_approving_review_count` to 1. |
| **Correction (2026-10-06, definitive probe)** | jolarca-infrastructure has **no CODEOWNERS at any path**: recursive `GET /repos/jolarca-dev/jolarca-infrastructure/git/trees/7930bec?recursive=1` returns `[]` for `CODEOWNERS$`, and its `.github/` lists only `ISSUE_TEMPLATE`, `PULL_REQUEST_TEMPLATE.md`, `actions`, `dependabot.yml`, `workflows`. The `grep ... returns no matches` that previously "verified" the rewrite was therefore **vacuous for that repo** — an absent file trivially matches nothing (AGENTS.md §7: do not trust a correct verdict). Cross-org ownership refs remain absent fleet-wide, so the ADR-0004 R4 breach is genuinely resolved for the five repos that DO carry CODEOWNERS. Residual defects recorded (not silently fixed): **(a)** jolarca-infrastructure needs its own CODEOWNERS — a cross-repo PR, outside this control plane; **(b)** `repos/jolarca-infrastructure.yml` declares `require_code_owner_reviews: true` while live reports `false`, against the `policy/repo-defaults.yml` baseline of `false` ("to match live reality; raise to true when teams are created") — seven repos (compliance, control, data, docs, infrastructure, legal, observability) declare `true` against that baseline; **(c)** its `required_status_checks.contexts: [ci, security, compliance]` are unverified as producible (D-44/D-47 class). (b)/(c) touch `repos/**` (high blast radius, evidence-hashed) and are an owner decision — recorded here, not applied. |

### D-22 · Plan-safety gate matched a pattern that never occurs — **FIXED in this change**
| | |
|---|---|
| Evidence | `apply.yml` originally refused unsafe plans with an inline grep for `^\s+visibility\s*:`. That is HCL/YAML syntax. `terraform show -no-color` on a saved plan renders the attribute as `~ visibility = "public" -> "private"` or `+ visibility = "private"` — an equals sign, **never a colon**. Verified empirically: against a synthetic plan containing a visibility transition, the old pattern matched **0** lines while `visibility[[:space:]]*=` matched **1**. |
| Impact | The single control standing between an unattended `terraform apply` and a fleet-wide visibility flip (D-01) was **inert**. Because it was inline in a workflow it was also untestable, so nothing ever exercised it. This is the same failure class as D-20 — a control that is present in configuration and never fires — which is why it is recorded here rather than treated as a typo. |
| Fix applied | The patterns were extracted into `scripts/check_plan_safety.sh` and are covered by `tests/test_check_plan_safety.sh` (10 cases: visibility flip both directions, destroy, replace, unmarked transition, create-only, no-op, unrelated attribute, empty plan, missing plan). Exit codes distinguish *safe* (0), *refused* (1) and *cannot check* (2) — an unreadable or empty plan is treated as unsafe rather than as "no changes", which is the failure mode that matters. `apply.yml` now calls the script. All 10 tests pass. |
| Lesson | A gate that cannot be tested will not be tested, and an untested regex gate is a hypothesis, not a control. Any future plan-inspection rule must ship with a fixture under `tests/fixtures/plan/`. |

---

## S2 — fix soon

### D-21 · `web_commit_signoff_required` declared in policy but live false and unenforced — **FIXED**
| | |
|---|---|
| Evidence | `policy/repo-defaults.yml` declares `web_commit_signoff_required: true`. Live API 2026-09-25: **`false` on all six** repositories. No Terraform resource set it. |
| Impact | Policy asserted a control that did not exist. Signed-off-by enforcement for web-UI edits was absent. |
| Fix applied | Added `web_commit_signoff_required` to `repositories.tf` (reads from `repos/*.yml` settings). Added `web_commit_signoff_required: true` to all six `repos/*.yml` files. On first apply, this will flip the setting from false to true on the live fleet. |

### D-10 · No teams in `jolarca-dev` — zero RBAC segregation
| | |
|---|---|
| Evidence | `gh api orgs/jolarca-dev/teams` returns an empty list. All access is via org ownership by one operator. |
| Impact | ISO 27001 A.5.3 (segregation of duties) and A.6.1 cannot be satisfied; every access review is self-review; PCI-DSS Req 7 (least privilege) has no enforcement mechanism. |
| Note | `policy/repo-defaults.yml` declares `teams: {}` on purpose rather than inventing teams that do not exist. |
| Required | Second-operator onboarding is the trigger: create `platform-admins` / `developers` / `auditors`, then raise D-04. |

### D-04 · Zero approving reviews fleet-wide — accepted deviation
| | |
|---|---|
| Evidence | `required_approving_review_count = 0` on all six repos (live API). Declared `0` in the old `environments/production/main.tf` with a `checkov:skip=CKV_GIT_5` rationale. |
| Impact | SOC 2 CC8.1 change approval rests entirely on automated gates. |
| Compensating controls | Required status checks non-empty and reporting, squash-only linear history, `enforce_admins = true`, signed operator commits, and the CI policy/drift gates in this repo. **Correction (2026-09-25):** this row previously also claimed "CODEOWNERS review ON (all five `jolarca*`)". That was **false as a control** — see **D-20**. Code-owner review is *enabled* but *unsatisfiable*, because no referenced team exists in `jolarca-dev`. It provides no compensating assurance and has been removed from this list. The residual position is therefore weaker than first recorded: change approval rests on automated gates alone. **Correction (2026-09-26):** two of the controls still listed in this row — "required status checks non-empty and reporting" and "`enforce_admins = true`" — hold only on the two public repos (`jolarca`, `.github`). Every private repository, including all four PCI-DSS-scoped ones, has **no enforceable branch protection at all** (**D-33**), so on the regulated fleet the automated gates still *run* but nothing *requires* them: `jolarca-security` has 14 commits directly on `main` and zero pull requests. Squash-only linear history is likewise a repository setting, not an enforced rule, wherever protection is absent. |
| Encoded as | `var.required_approving_review_count = 0` with validation allowing 0 only under this documented deviation; registered in `policy/compliance-gates.yml` `exceptions.active`. The exception record must cite D-20 as well, since one of its stated compensating controls is void. |

### D-07 · Tag protection declared in policy but unenforced
| | |
|---|---|
| Evidence | `gh api repos/jolarca-dev/{jolarca,jolarca-infrastructure}/rulesets` → `0`. `policy/repo-defaults.yml` declares `tag_protection.pattern: "v*"`. |
| Impact | Release tags can be moved or deleted after the fact, breaking the release-to-commit audit trail (SOC 2 CC8.1, ISO 27001 A.8.32). |
| Encoded as | `tag_protection.enforced: false` in policy — declared honestly rather than claiming a control that does not exist. Ruleset definitions intentionally deferred. Now also registered in `policy/compliance-gates.yml` `exceptions.active` with a date-bound expiry, an approver and a compensating control. |
| Blocked by — **plan tier** | The deferral is not a soft target; on the current plan there is **no available mechanism**. Verified 2026-09-25: `gh api orgs/jolarca-dev` → `plan.name = "free"`; `gh api orgs/jolarca-dev/rulesets` → **HTTP 403 "Upgrade to GitHub Team to enable this feature"**; `gh api repos/jolarca-dev/jolarca/tags/protection` → **HTTP 404** (GitHub removed the classic tag-protection API). Repository-level rulesets are queryable today only because all six repos are still *public* — rulesets on **private** repositories require GitHub Team or higher, and making the fleet private is the intended end state (D-01). So closing D-07 by configuration alone is impossible: it needs a plan upgrade, or a recorded decision to accept the gap. |
| Required | Owner decision: upgrade `jolarca-dev` to GitHub Team and add a `github_repository_ruleset` protecting `refs/tags/v*`, or re-review and extend the exception with the risk restated. Do not leave it as "deferred" without a date. |

### D-15 · Org-wide SECURITY.md inheritance is not under IaC — **FIXED**
| | |
|---|---|
| Evidence | State had 0 instances of `github_repository_file.security_md`. Live: `jolarca-dev/.github/SECURITY.md` existed, created out-of-band. |
| Impact | The org-wide security policy was unmanaged and unreviewed. |
| Fix applied | Created `files/SECURITY.md` with the live content (adopted from the org .github repo). Updated `health-repo.tf` to read from the file with `overwrite_on_create = false`. On first apply, Terraform will import the existing file into state without overwriting it. |

### D-05 · Signed commits not enforced at branch-protection level — accepted deviation
| | |
|---|---|
| Evidence | `required_signature` is `null` on all six repos. Old module carried `checkov:skip=CKV_GIT_6` because provider-seeded automation commits cannot be GPG-signed. |
| Impact | ISO 27001 A.6.6 / SOC 2 CC6.2 attribution relies on policy rather than enforcement. |
| Encoded as | `var.enforce_signed_commits = false`; `policy/repo-defaults.yml` `commit_signing_policy.required_for_human_operators: true` keeps the human obligation explicit, and `validate_repos.py` reads the expectation from policy instead of hardcoding `true`. |

### D-16 · `jolarca-control` does not exist on GitHub yet
| | |
|---|---|
| Evidence | `gh api orgs/jolarca-dev/repos` returns six repos, none named `jolarca-control`. The local directory has **no commits and no git remote**. |
| Impact | Bootstrap chicken-and-egg: the repo must be created by the control plane that lives inside it. Creating it by hand is an ADR-0004 R2 out-of-band creation. |
| Encoded as | Declared in `repos/jolarca-control.yml`; `check_fleet_separation.sh` supports a time-boxed `ALLOW_MISSING` exemption; runbook step 2 resolves the ordering and records the R2 exception. |

### D-18 · Org-wide two-factor authentication is NOT enforced — **FIXED**
| | |
|---|---|
| Evidence | `gh api orgs/jolarca-dev` → `"two_factor_requirement_enabled": false` (2026-09-25). |
| Impact | Any member account with a password-only login can be credential-stuffed into an organization that owns PCI-DSS-scoped repositories and holds a Terraform token capable of rewriting branch protection fleet-wide. PCI-DSS Req 8.3.1 requires multi-factor authentication for all access into the CDE; ISO 27001 A.5.17 requires authentication per policy; SOC 2 CC6.1. |
| Why it matters more here | `docs/threat-model.md` T-02 previously asserted "2FA required" as a mitigation. That assertion was inherited from `jol-control` and was never true of this org. The threat model has been corrected to show the gap. |
| Fix applied | Org-enforced 2FA enabled (verified 2026-10-01): `gh api orgs/jolarca-dev -q .two_factor_requirement_enabled` → `true`. This setting cannot be changed through the GitHub API (security feature); it was enabled manually in the GitHub UI. drift_detect `organization_baseline` already declared `two_factor_requirement_enabled: true` and now matches live. |
| Resolved | D-18 removed from `open_blocking` in `policy/compliance-gates.yml`. |

### D-19 · Permissive org defaults undermine the allow-list — **FIXED**
| | |
|---|---|
| Evidence | `gh api orgs/jolarca-dev` → `"members_can_create_repositories": true`, `"default_repository_permission": "read"` (2026-09-25). |
| Impact | Members could create repositories out-of-band, and `default_repository_permission: read` granted every member read access to every repo automatically. |
| Fix applied | Changed via GitHub API on 2026-09-25: `members_can_create_repositories = false`, `default_repository_permission = "none"`. Org owners retain creation rights, so the control plane is unaffected. |

---

## S3 — tracked hygiene

### D-09 · Issues disabled on five of six repos
Live `has_issues: false` everywhere except `jolarca-dev/.github`. There is no
issue tracker on the repos where incidents and decisions would be filed;
`docs/superpowers/plans/…` markdown files are acting as the tracker instead.
Encoded as-is in the allow-list (reality), with `jolarca-control` overriding to
`true` so governance work has a home.

### D-11 · Stale `jol-m-*` naming in CI comments — **FIXED**
`.github/workflows/fleet-separation-guard.yml` described the fleet as `jol-m-*`
throughout, three weeks after the 2026-08-31 rename and the 2026-09-02 org
transfer. Comments corrected to `jolarca*` in `jolarca-infrastructure`; the
ported copy in this repo was rewritten against the allow-list model.

### D-12 · Stray backup file committed in the module directory — **FIXED**
`terraform/modules/github-org/variables.tf.bak.20260831-2306` (3 360 B) was
tracked in git. Deleted; history retains it, which is where a backup belongs.

### D-14 · State written by Terraform 1.16.0, local CLI is 1.16.1
State `terraform_version = 1.16.0`, `serial = 25`. Local `terraform version`
reports `v1.16.1`, provider `integrations/github v6.13.0`. Compatible, but the
runbook pins the CLI to 1.16.x for the migration window so state is not
upgraded as a side effect.

### D-17 · `jolarca` carries mission-scope topics
Live topics include `baltic`, and the stale state snapshot recorded `catholic`
and `liturgy` on the marketplace flagship. Mission/marketplace metadata bleed.
Cosmetic, but it weakens the ADR-0004 story an auditor reads. Left as verified
reality for now; refresh deliberately, not as a side effect of a migration.

---

## Findings added by the 2026-09-25 control-plane audit

Added by an independent re-audit that verified every row against the live
GitHub API and by executing the gates, rather than reading the documentation.
Numbering continues from D-22. Each row states whether it is fixed in this
change or still open.

### D-31 · "Accept public" is not implementable — the four repos hold live regulated records — **S1, BLOCKING, OPEN**
| | |
|---|---|
| Evidence | `repos/jolarca-{compliance,data,infrastructure,legal}.yml` all declare `compliance.data_classification: confidential`, and `scripts/validate_repos.py` hard-fails a `confidential`/`restricted` repo whose `visibility` is `public`. The classification is **correct**, not conservative: the live public contents were enumerated on 2026-09-25 and include `jolarca-compliance/ropa/master-register.csv` (1 150 B, populated — columns `id,system,purpose,lawful_basis,data_categories,subjects,retention_class,recipients,transfer_mechanism`; rows include `ROPA-001 users-app … Identity; contact; auth credentials … Identity provider; Bitrix24 support` and `ROPA-002 sellers-app … Seller onboarding & KYC verification … Identity documents; business registry data … VIES`), `jolarca-compliance/ropa/by-system/{users-app,shipping}.md`, `jolarca-compliance/vendor-assessments/{stripe,tia,hetzner,proxmox,omniva,dpd,letsencrypt}/assessment.md`, and `jolarca-legal/contracts/vendors/_register.csv` plus DPA/NDA/employment templates and per-subprocessor folders (anthropic, bitrix24, deepl, dpd, google-cloud, omniva, openai). |
| Impact | This is not a configuration preference. The organization's **GDPR Art. 30 record of processing is publicly readable on the internet today**, together with its lawful bases, data categories, retention classes, subprocessor list, cross-border transfer mechanisms, and its third-party risk and Transfer Impact Assessments including the payment processor. That is a complete map of the PII and payment estate for anyone planning an attack, and for any complainant or regulator. GDPR Art. 5(1)(f) and Art. 32; PCI-DSS Req 1.2 scope. |
| Decision requested | "Accept public — change the YAMLs" was selected, but it **cannot be executed as stated**: it would require either downgrading four `confidential` classifications (factually false — the RoPA and KYC records are confidential) or bypassing the one validator rule that made D-01 visible. No file was changed. The defensible options are **(a)** flip the four live repositories to private (recommended; this is remediation of an ongoing exposure, not a policy change), or **(b)** split each repo so only genuinely public content remains public and move the RoPA, assessments and contracts into a private repository. Option (a) is available immediately and is reversible; option (b) is the correct long-term shape but takes real work. |
| Interim | `sensitive_repos` in `terraform.tfvars` can force the four private on first apply without editing the YAMLs. Because `apply.yml` refuses visibility-changing plans, that apply must be run deliberately per RB-02 with the plan transcript archived. Assess under **GDPR Art. 33** whether the exposure to date is notifiable — that assessment belongs in `jolarca-compliance`, not here. |
| Correction (2026-10-06) | **Option (a) "flip private" is withdrawn.** It was executed on `jolarca-compliance` + `jolarca-infrastructure` and reverted the same day: privating a governed fleet repo makes the control plane's **Context Parity** required context exit **2** (the workflow `GITHUB_TOKEN` cannot read a private sibling's `.github/workflows`, so `check_declared_contexts.py` files them `unverifiable`). Remediation is **option (b)** — move the regulated records out of public git; full evidence and plan in **D-52**. D-31 remains **S1, BLOCKING, OPEN**; the `confidential`→`internal` downgrade recorded in D-37 masked rather than resolved it. |

### D-23 · `drift_detect.py` reported success when it could not read live state — **S1, FIXED**
| | |
|---|---|
| Evidence | The previous version did `if not live_list: print("WARNING: could not fetch GitHub repos — skipping drift detection"); return 0`. Reproduced empirically: with `GITHUB_TOKEN=gho_INVALID…` the script printed `ERROR: gh CLI failed: HTTP 401: Bad credentials` and exited **0**. `get_github_repos()` also returned `[]` on `FileNotFoundError`, so a missing `gh` produced the same green result. |
| Impact | The control whose entire purpose is "proof, not hope" passed while proving nothing. An expired or absent `TF_GITHUB_TOKEN_READONLY` would silently disable fleet-wide drift detection indefinitely, and CI history would show a continuous run of successes. Aggravating factor verified the same day: `gh api orgs/jolarca-dev/actions/secrets` returns an **empty list**, so neither `TF_GITHUB_TOKEN` nor `TF_GITHUB_TOKEN_READONLY` exists yet — the silent path was the *default* path, not a corner case. |
| Fix applied | Three-valued exit codes: `0` no drift, `1` drift, `2` **could not verify**. An empty repository list is also treated as unverifiable rather than as a deleted fleet. Verified: valid token → exit 1 with the real findings; invalid token → exit 2 with an explicit refusal message. `apply.yml`'s post-apply drift step now has no `GITHUB_TOKEN` fallback, since the default token cannot read org-wide metadata and a fallback would only have manufactured another silent pass. |

### D-26 · Drift detection covered 1 of the 3 mandated signals, and alerted nobody — **S1, FIXED**
| | |
|---|---|
| Evidence | The requirement is to alert if a repository *flips public*, *loses branch protection*, or *gains an unexpected admin*. The previous script compared only fleet membership, visibility, wiki and archived state — it never called the branch-protection or collaborator endpoints, and never read org settings. Separately, `compliance-scan.yml` granted `permissions: issues: write` but **no step ever created an issue**; results went to stdout and were retained only in the run log. Cadence was `0 2 * * 6` (weekly), not daily. |
| Impact | Two of three mandated signals were undetected. Losing branch protection on a PCI-scoped repo — the exact change D-08 shows has already happened once out-of-band — would not have been noticed. And detection without notification means drift lived in CI logs nobody reads. |
| Fix applied | `scripts/drift_detect.py` now also checks: branch protection (reported as `missing` when a repo has **no** rule at all, which is distinguished from a 404 caused by an absent repo, and as `weakened` when `enforce_admins`, force-push, deletion, CODEOWNERS review, stale-review dismissal or context count fall below baseline); administrators against `allowed_admins`; and the seven org owner settings the provider cannot manage. Expected values live in `policy/repo-defaults.yml#organization_baseline` rather than in code, matching how the signed-commit expectation is already sourced. `.github` is listed in `branch_protection_baseline_exempt` because its rule is deliberately minimal — but a rule must still **exist** there, so the exemption cannot be used to leave a repo unprotected. Cadence is now daily (`17 2 * * *`), and drift opens or updates a single issue so its age shows how long the condition has been outstanding; exit 2 files a separate "could not verify" issue because the remedy is token scope, not repo config. |
| Verified | Against the live org the extended script reports the missing `jolarca-control`, four HIGH-EXPOSURE visibility drifts, and six org-setting violations (2FA off, three repo-creation flags on, `default_repository_permission: read`, web sign-off off). No false positive on `.github`. |

### D-22a · `apply.yml` post-apply verification could not fail — **S1, FIXED**
See D-22 for the inert plan-safety regex. The related defect fixed here: the
post-apply drift step inherited the D-23 silent-pass behaviour, so an apply
could complete with **no** verification and the workflow still report green.

### D-24 · `ALLOW_MISSING` was documented as time-boxed but was permanent — **S2, FIXED**
| | |
|---|---|
| Evidence | The script header said the exemption was "for that window ONLY" and D-16 recorded that `check_fleet_separation.sh` "supports a time-boxed `ALLOW_MISSING` exemption". `grep -nE "date\|expire\|until" scripts/check_fleet_separation.sh` returned **no date logic at all** — the exemption was a bare environment variable with no expiry. |
| Impact | An indefinite, unaudited bypass of the ADR-0004 R2 detector for out-of-band repository creation. Worse than no detector: the register asserted a control that did not exist, which is the failure mode this file exists to prevent. |
| Fix applied | `ALLOW_MISSING_UNTIL=YYYY-MM-DD` is now mandatory whenever `ALLOW_MISSING` is set. Undated, malformed or expired values exit **2** rather than being honoured. Verified all four paths: no exemption → 1 (correctly reports `jolarca-control` missing), undated → 2, expired → 2, valid future date → 0 with a loud warning naming the expiry. |

### D-25 · The exceptions register violated its own 90-day rule — **S2, FIXED**
| | |
|---|---|
| Evidence | `policy/compliance-gates.yml` `exceptions.requirements` mandates "Time-bound acceptance (max 90 days, then re-evaluate)", and `CONTRIBUTING.md` instructs contributors to add "a compensating control and an expiry date". Both active entries used **events**, not dates: `expires: "on second-operator onboarding"` and `expires: "when automation commit signing lands"`. Neither carried an approver. |
| Impact | An event-based expiry has no deadline and can remain open forever, so D-04 and D-05 were effectively permanent acceptances recorded as temporary ones. An auditor testing the 90-day control would find it fails on its own two entries. |
| Fix applied | Every entry now carries `approved_by`, `approved_on`, an ISO-8601 `expires` (2026-12-24, i.e. 90 days from the review date) and an `exit_trigger` that preserves the intended event. D-07 was added as a third entry because it is a genuine accepted gap, with `blocked_by` recording the plan-tier constraint. Lapse requires a fresh PR restating the compensating controls. |

### D-27 · The `code_quality` gate named tools that nothing ran — **S2, FIXED**
| | |
|---|---|
| Evidence | `policy/compliance-gates.yml` declares `code_quality` **mandatory** for `tier:governance` with `python: [ruff, mypy --strict, pytest]` and `terraform: [terraform fmt -check, terraform validate, tflint, checkov]`. No workflow ran ruff, mypy, shellcheck or any test. Executing them found the claim was already false: `mypy --strict` reported **14 errors** across `validate_repos.py` and `compliance_check.py`, and neither `ruff` nor `mypy` had any configuration file, so "passes" depended on whichever version a contributor happened to have installed. |
| Impact | The declared standard was unverifiable and unmet. `jolarca-control` is `tier: governance`, so this gate is mandatory for exactly the repository where it was absent. |
| Fix applied | `pyproject.toml` now pins the ruff rule selection and mypy strictness; `requirements.txt` / `requirements-dev.txt` pin the tool versions; all 14 mypy errors are fixed and `ruff check` is clean. A new **Static Analysis & Gate Tests** CI job runs ruff, `mypy --strict`, `shellcheck` and the plan-gate regression tests, and `make lint` runs the same set locally. Per CONTRIBUTING's own rule the new job is **not yet a required status check** — land it, confirm green, then require it. |
| Still open | `tflint` and `checkov` remain declared but unrun, and there is no `pytest` suite. `yamllint` is declared in CONTRIBUTING with no config and no CI step. These are recorded rather than quietly dropped. |

### D-29 · Dependencies were unpinned and included a package nothing imports — **S3, FIXED**
| | |
|---|---|
| Evidence | No `requirements.txt` existed. CI ran `pip install pyyaml` (and `pyyaml requests` in the drift job) with no version constraint, while every GitHub Action in the same workflows is pinned to a full commit SHA for supply-chain reasons (T-12). `grep -rn "^import requests\|^from requests" scripts/` returns **nothing** — the library is unused; `drift_detect.py` shells out to `gh`. The local `.venv` did not even have `pyyaml`, so all three validators failed on import with `ModuleNotFoundError`. |
| Impact | Non-reproducible validation: the gates that decide whether a PR may merge could change behaviour between runs with no diff to review. The unused dependency added supply-chain surface for no benefit, and the inconsistency undercut the repo's own stated policy. |
| Fix applied | Pinned `requirements.txt` (runtime) and `requirements-dev.txt` (lint/type tools), `requests` deliberately excluded with a comment saying so, all workflows and CONTRIBUTING switched to `pip install -r …`, and `make setup` provisions the venv. |

### D-30 · The compliance report presented declared-config results as organizational evidence — **S3, FIXED**
| | |
|---|---|
| Evidence | `compliance_check.py` is documented as producing "a JSON compliance report suitable for audit evidence (SOC 2 CC4.1, ISO 27001 A.5.31 / A.8.8, PCI-DSS 12.10)" and emits `overall_status: pass`. Every check reads `repos/*.yml` and `policy/` only — it never calls the GitHub API. On 2026-09-25 it returned `pass` while four repos classified `confidential` were publicly readable (D-01, D-31). |
| Impact | An auditor handed this artifact would reasonably read `pass` as a statement about the organization. It is a statement about the allow-list's internal consistency. Presenting it without that distinction is the kind of overclaim that damages credibility across the whole evidence set. |
| Fix applied | The report now carries `scope`, `scope_warning`, `live_state_verified: false` and `live_state_source`, and the module docstring states the distinction. The field `overall_status` is unchanged so CI keeps working. |

### D-28 · The git index held IDE metadata while every real file was untracked — **S2, FIXED**
| | |
|---|---|
| Evidence | `git status --short` on a repository with **zero commits** showed staged: `.idea/.gitignore`, `.idea/inspectionProfiles/profiles_settings.xml`, `.idea/jolarca-control.iml`, `.idea/misc.xml`, `.idea/modules.xml`, `.idea/vcs.xml`, and `main.py` (status `AD` — staged add, deleted from the worktree; a PyCharm scaffold). Meanwhile `.github/`, `docs/`, `repos/`, `policy/`, `scripts/` and every `*.tf` file were untracked (`??`). `.gitignore` correctly lists `.idea/`, but the entries were already in the index. |
| Impact | The first `git commit` would have contained **only** IDE metadata and a stray scaffold file, and none of the control plane. The bootstrap commit of a PCI-scoped governance repository would have shipped without its own governance, and `.idea/` leaks local paths and interpreter configuration into a repo that is meant to be private. |
| Fix applied | `.idea/` and `main.py` removed from the index (files left on disk), and the real tree staged. No commit was created — the bootstrap commit belongs to whoever executes `docs/state-migration-runbook.md` step 2, and must be signed per D-05. |

### D-32 · CODEOWNERS cross-project references had no automated detection — **S1, FIXED**
| | |
|---|---|
| Evidence | D-20 identified that five fleet repos had CODEOWNERS pointing at mission-platform orgs (`@journeyoflife-org/*`, `@jol-infrastructure/*`) that don't exist in `jolarca-dev`, making `require_code_owner_reviews` inert. However, there was no automated check to detect this drift. The drift detection script checked branch protection, admins, org settings, visibility, wiki, archived state — but not CODEOWNERS content. |
| Impact | Cross-project CODEOWNERS references violate ADR-0004 R4 (no CODEOWNERS, workflow, or module in one project may reference the other's). Without automated detection, new cross-project references could be added without alerting, and the existing violations would persist undetected. |
| Fix applied | Added `check_codeowners()` to `scripts/drift_detect.py` that fetches `.github/CODEOWNERS` from each repo, decodes the base64 content, and checks for references to forbidden orgs (`journeyoflife-org`, `jol-infrastructure`). Violations are reported in the drift JSON and stderr output, and included in the issue alert. Added `codeowners.tf` with `github_repository_file.codeowners` resources that overwrite each repo's CODEOWNERS with jolarca-dev-only content (`* @JourneyOfLife`), excluding `.github` which is managed by `health-repo.tf`. The resource uses `overwrite_on_create = true` and ignores commit author/email changes. |
| Verified | Drift detection now reports 18 cross-project references across 5 repos: `jolarca` (3), `jolarca-compliance` (3), `jolarca-data` (5), `jolarca-infrastructure` (3), `jolarca-legal` (4). Terraform validate passes. |

---

## Findings added by the 2026-09-26 plan-tier verification

Added after the fleet grew from six to sixteen repositories and seven of them
(including the four PCI-DSS-scoped ones) were made private. Every row below was
re-verified against the live GitHub API on 2026-09-26, read-only. Numbering
continues from D-32.

### D-33 · Branch protection is unenforceable on every private repo — only 2 of 16 repositories are guarded — **S1, BLOCKING, OPEN**
| | |
|---|---|
| Evidence — plan tier | `gh api orgs/jolarca-dev -q .plan.name` → **`free`**. `GET /repos/jolarca-dev/{repo}/branches/main/protection` returns **HTTP 403 `{"message":"Upgrade to GitHub Pro or make this repository public to enable this feature."}`** for all seven private repositories: `jolarca-infrastructure`, `jolarca-compliance`, `jolarca-legal`, `jolarca-data`, `jolarca-control`, `jolarca-security`, `jolarca-identity`. The 403 is a plan-tier refusal, not a token-scope failure — the same token reads those repositories without error. |
| Evidence — enforcement signal | The dedicated endpoint is unreadable, but `GET …/branches/main` is not: it reports **`.protected = false` on all seven** private repos. `.protected = true` only on `jolarca` and `.github` — the two public repos still carrying the out-of-band rules from D-08 (`jolarca`: 9 required contexts, `enforce_admins = true`, `strict = false`). |
| Evidence — rest of the fleet | The remaining seven public repos (`jolarca-observability`, `-dr`, `-consent`, `-docs`, `-runbooks`, `-vendor`, `-payments`) are still empty (`size: 0`; `GET …/branches/main` → HTTP 404 "Branch not found"), so there is no branch to protect yet and `drift_detect.py` correctly reports them as `missing`. **Net: enforceable branch protection exists on 2 of 16 repositories, and on none of the private ones.** |
| Evidence — no substitute mechanism | `gh api orgs/jolarca-dev/rulesets` → HTTP 403 "Upgrade to GitHub Team"; `gh api repos/jolarca-dev/jolarca-control/rulesets` → HTTP 403 "Upgrade to GitHub Pro or make this repository public". Rulesets cannot be used instead — the same constraint recorded for tag protection in D-07. |
| Evidence — Terraform manages none | `terraform.tfvars` sets `enable_branch_protection = false` (the `variables.tf` default is `true`), so `local.protected_repos` resolves to an empty map and `github_branch_protection.health` has `count = 0`. Local state (serial 128, TF 1.16.1) holds 7 `github_repository` and 7 `github_repository_vulnerability_alerts` instances and **zero `github_branch_protection`**. **Correction (2026-09-30):** `jolarca-control` now has branch protection enabled out-of-band (**D-35**), so the control plane is guarded. The Terraform state still holds zero `github_branch_protection` resources; the out-of-band change is safe because the declared config matches. All other repos remain as described below. |
| Evidence — proven by behaviour, not inferred | `jolarca-security` (private) has **0 pull requests in any state** and 14 commits sitting directly on `main`. `jolarca-control` (private) took 7 of its 9 commits as direct pushes to `main` — only #2 and #3 came through a PR — and although its HEAD reports `Fleet Separation Guard` and `Production — Apply` check runs, nothing requires them to pass. Direct pushes to `main` therefore succeed on private repos today, which is the only claim that matters: a 403 could in principle mean "configured but unreadable", and `jolarca-security`'s history proves it does not. |
| Impact | `main` on the four PCI-DSS-scoped repositories, on this control plane, and on `jolarca-security` / `jolarca-identity` can be force-pushed, deleted, or pushed to directly — no review, no required check, no admin enforcement. A history rewrite also destroys the signed-commit attribution that **D-04** and **D-05** cite as their compensating control, so the compensation for the zero-review deviation is itself unguarded. `policy/compliance-gates.yml` maps SOC 2 CC6.1 to "Branch protection + required status checks + CODEOWNERS": on the private fleet all three are absent or inert (CODEOWNERS — D-20). ISO 27001 A.8.32 / A.5.1; PCI-DSS Req 6.3 / 6.5. |
| How it happened | This is a **consequence of remediating D-01**, not an unrelated oversight. Branch protection is free for public repositories and unavailable for private ones below Team/Pro. The four regulated repos are private as of 2026-09-26 — the outcome D-31 recommended, given the publicly readable RoPA / KYC / contract material — and that flip silently withdrew the change-control layer from exactly the repositories that hold regulated records. Nothing in this repo noticed: a security fix produced a compliance regression. |
| Rows this voids | **D-08**: "the existing rules … will remain in place until the org is upgraded" is false for private repos, and runbook step 5 can import two rules, not six. **D-04**: "required status checks non-empty and reporting" and "`enforce_admins = true`" hold only on `jolarca` and `.github`. Both rows carry a dated correction above. `SECURITY.md`'s "No `--force` push to `main`, ever. Branch protection blocks it" was also false and is corrected in this change. |
| Detection is blind | `scripts/drift_detect.py` maps the 403 to `unverifiable` (7 entries) and exits **2** with the message "Pass `--allow-unverifiable` only if the token genuinely lacks scope". The token is not the problem — the plan tier is — so the guidance names the wrong remedy, and anyone who clears the exit 2 with that flag drops all seven private repos from the check silently. The script never reads the `.protected` boolean, which *is* readable on Free and would report the absence directly. Consequence: the mandated signal "alert if a repository loses branch protection" (D-26) cannot fire for any private repo. |
| Encoded vs declared baseline | `policy/repo-defaults.yml#branch_protection.main` requires `strict: true`, `dismiss_stale_reviews: true`, `require_code_owner_reviews: true`, `require_linear_history: true`, `require_conversation_resolution: true`; `branch-protection.tf` hardcodes **all five to `false`**, each annotated "requires GitHub Pro for private repos on free plan" — a limitation that does not apply to the nine *public* repos. `organization_baseline.required_branch_protection` still demands code-owner review and stale-review dismissal, so the day protection is enabled with the current HCL, `drift_detect.py` will report every protected repo as `weakened`. The flag is also fleet-wide: it cannot express "protect the public repos now, the private ones after an upgrade". |
| Why this is not "Phase 4" | `docs/action-plan.md` records the gap as Step 4.2 "Re-enable advanced branch protection", priority **OPTIONAL**, "when budget approved". It is not an enhancement to an existing control; it is the absence of the control on 14 of 16 repositories, including every private one. Cross-referenced there in this change. |
| Required — owner decision | **(a)** Upgrade `jolarca-dev` to GitHub Team, then set `enable_branch_protection = true`, reconcile `branch-protection.tf` with `policy/repo-defaults.yml` before applying (otherwise D-26's `weakened` check fires immediately), and import the two surviving rules on `jolarca` / `.github`. This also unblocks D-07, secret scanning and real code-owner enforcement. **(b)** Do **not** close it by making the repositories public again — D-31 records why that is the worse failure. **(c)** If the upgrade is not funded now, record a dated acceptance in `policy/compliance-gates.yml` `exceptions.active` with `approved_by`, an ISO-8601 `expires`, an `exit_trigger` and `blocked_by: plan tier` — the D-07 pattern — and stand up the interim controls below. What is not acceptable is leaving it filed as an optional enhancement. |
| Interim — available without an upgrade | 1. **Fix detection first**: read `.protected` from `branches/main` and classify the private-repo 403 as a plan-tier finding rather than `unverifiable`, so the daily run reports "unguarded" instead of "could not check". 2. **Protect the public repos** — branch protection is free there — verifying the per-attribute availability of `strict` / linear history / conversation resolution on one repo (`jolarca`) before applying fleet-wide, since none of those has been tested against a Free-plan public repo in this change. 3. Keep merges PR-based by convention, and treat signed operator commits (D-05) as *attribution*, not prevention. 4. The off-host state backup in D-02 becomes more urgent, not less: with no force-push block, recovery of rewritten history depends entirely on a copy that is not on the pushing host. |

---

---

## Findings added by the 2026-09-28 pre-deployment audit

The external pre-deployment audit (2026-09-28, unauthenticated GitHub API +
raw file reads) identified six blockers (B1–B6) and six high findings (H1–H6).
The remediation actions taken in this change are recorded below.

### B1 · Dead security contact — **FIXED**
| | |
|---|---|
| Evidence | `jolarca/SECURITY.md` line 17 directed researchers to `security@jol-infrastructure.example` — an RFC-2606 `.example` domain that cannot receive mail. The org `.github/SECURITY.md` correctly says `security@jolarca.com`. |
| Fix applied | Changed to `security@jolarca.com` to match the org-level security contact. |

### B3 · Branch protection safe four — **FIXED**
| | |
|---|---|
| Evidence | `branch-protection.tf` hardcoded `strict`, `dismiss_stale_reviews`, `required_linear_history`, and `require_conversation_resolution` to `false`. The audit recommended enabling the "safe four" that work on Free plan for public repos. |
| Fix applied | All four attributes set to `true` in `branch-protection.tf`. These work on Free for PUBLIC repos (`jolarca`, `.github`). Private repos still need GitHub Pro (D-33). `require_code_owner_reviews` set to `false` in `repos/jolarca.yml` per the audit's dated-deviation recommendation (G-15 self-approval trap). Header comment updated to reflect the new status. |

### B5 · Issues disabled — **FIXED**
| | |
|---|---|
| Evidence | `repos/jolarca.yml` had `has_issues: false`. A marketplace processing GDPR Art. 17 erasures needs a durable intake trail for DSARs and incidents. |
| Fix applied | Changed `has_issues: false` to `has_issues: true` in `repos/jolarca.yml`. |

### B6 · Public repo ADR — **FIXED**
| | |
|---|---|
| Evidence | The audit recommended recording an ADR accepting the attack-surface publication if the AGPL-3.0 strategy is deliberate. |
| Fix applied | Created `docs/adr/0007-public-marketplace-repository.md` documenting the deliberate public visibility with rationale, constraints, compensating controls, and residual risks. |

### H1 · Mutable action tags — **FIXED**
| | |
|---|---|
| Evidence | All four workflow files used mutable `@vN` tags for GitHub Actions. |
| Fix applied | All actions SHA-pinned across `deploy-production.yml`, `deploy-staging.yml`, `security.yml`, and `ci.yml`. SHAs verified via `gh api` on 2026-09-28. |

### H2 · Unpinned tool downloads — **FIXED**
| | |
|---|---|
| Evidence | gitleaks fetched via `curl | tar` without checksum verification; `pip-audit` installed unpinned. |
| Fix applied | gitleaks download now verified against SHA-256 checksum (`5bc41815...`). `pip-audit` pinned to `==2.10.1`. |

### H3 · Coverage gate 20% — **RISK ACCEPTANCE RECORDED**
| | |
|---|---|
| Evidence | Backend coverage gate is 20% with a TODO to raise toward 80%. For PCI-DSS scope, SOC 2 CC7.2 change-evaluation evidence at 20% won't survive an examiner. |
| Action | Risk acceptance comment added to `ci.yml`. Owner to raise toward 80% before production traffic. Tracked in jolarca-compliance risk register. |

### H5 · Doc drift (DEPLOYMENT.md, SECURITY_POSTURE.md 404s) — **FALSE FINDING**
| | |
|---|---|
| Evidence | The audit claimed README links to `docs/DEPLOYMENT.md` and `docs/SECURITY_POSTURE.md` return 404. Both files exist: `DEPLOYMENT.md` (207 lines) and `SECURITY_POSTURE.md` (98 lines). README links are correct. |
| Conclusion | No action required. The finding does not match the current repository state. |

### Medium · Image tag discipline — **FIXED**
| | |
|---|---|
| Evidence | `deploy-production.yml` pushed `:latest` tags alongside immutable `v*` tags. |
| Fix applied | `:latest` tags removed. Only immutable `${{ github.ref_name }}` tags are pushed. |

### Medium · Secrets directory guard — **FIXED**
| | |
|---|---|
| Evidence | `secrets/` directory exists with only a README, but no CI guard prevents future blob commits. |
| Fix applied | Created `scripts/check_secrets_dir.sh` and added it to the `secrets` CI job in `ci.yml`. Fails if any non-README file lands in `secrets/`. |


## Verification commands

All read-only. Reproduce every row above:

```bash
# D-01 visibility, D-09 issues, D-17 topics
for r in jolarca jolarca-compliance jolarca-data jolarca-infrastructure jolarca-legal; do
  gh api "repos/jolarca-dev/$r" \
    -q '[.name,.visibility,.has_issues,.license.spdx_id]|@tsv'
done

# D-04, D-05, D-08 protection
for r in jolarca jolarca-compliance jolarca-data jolarca-infrastructure jolarca-legal .github; do
  gh api "repos/jolarca-dev/$r/branches/main/protection" \
    -q '{rev:.required_pull_request_reviews.required_approving_review_count,
         codown:.required_pull_request_reviews.require_code_owner_reviews,
         sig:.required_signature.enabled,
         ctx:(.required_status_checks.contexts|length)}'
done

# D-03, D-15 health repo ownership and content
gh api repos/jolarca-dev/.github/contents/SECURITY.md -q .path

# D-07 rulesets
gh api repos/jolarca-dev/jolarca/rulesets -q length

# D-10 teams
gh api orgs/jolarca-dev/teams -q length

# D-20 CODEOWNERS resolution — the check that was missing.
# Lists every CODEOWNERS file (note: .github/, not root) and every team it
# names, then shows which of those teams actually exist in either org.
for r in jolarca jolarca-compliance jolarca-data jolarca-infrastructure jolarca-legal .github; do
  echo "--- $r"
  for p in CODEOWNERS .github/CODEOWNERS docs/CODEOWNERS; do
    gh api "repos/jolarca-dev/$r/contents/$p" -q .content 2>/dev/null \
      | base64 -d 2>/dev/null | grep -vE '^\s*#|^\s*$'
  done | grep -oE '@[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+' | sort -u
done
echo "--- teams that actually exist"
gh api orgs/jolarca-dev/teams      -q '"jolarca-dev: "+([.[].slug]|join(", "))'
gh api orgs/journeyoflife-org/teams -q '"journeyoflife-org: "+([.[].slug]|join(", "))'
gh api orgs/jol-infrastructure -q .login || echo "jol-infrastructure: NO SUCH ORG"

# D-20 required contexts vs contexts actually produced on HEAD of main
for r in jolarca jolarca-data jolarca-compliance jolarca-legal jolarca-infrastructure; do
  echo "--- $r"
  gh api "repos/jolarca-dev/$r/branches/main/protection" \
    -q '.required_status_checks.contexts|join(", ")'
  gh api "repos/jolarca-dev/$r/commits/main/check-runs" \
    -q '[.check_runs[].name]|unique|join(", ")'
done

# D-02, D-06, D-14 state inspection
python3 - <<'PY'
import json
s = json.load(open('/opt/jolarca/repos/jolarca-infrastructure/'
                   'terraform/environments/production/terraform.tfstate'))
print('serial', s['serial'], 'tf', s['terraform_version'])
for r in s['resources']:
    if r['type'].startswith('github_'):
        print(r.get('module'), r['type'], r['name'],
              [(i.get('index_key'),
                (i.get('attributes') or {}).get('full_name'))
               for i in r.get('instances', [])])
PY

# ── Findings added 2026-09-25 (D-22a … D-31) ─────────────────────────────────

# D-23 drift detection must fail loudly, never silently.
# First command MUST exit 2; the old code exited 0 here.
GITHUB_TOKEN=gho_invalid .venv/bin/python scripts/drift_detect.py; echo "exit=$? (want 2)"
.venv/bin/python scripts/drift_detect.py --issue-body /tmp/drift.md; echo "exit=$? (1 = drift)"

# D-23 aggravating factor: the tokens the workflows expect do not exist yet.
gh api orgs/jolarca-dev/actions/secrets   -q '.total_count'
gh api orgs/jolarca-dev/actions/variables -q '.total_count'

# D-26 org baseline and admins are now covered.
gh api orgs/jolarca-dev -q '{two_factor:.two_factor_requirement_enabled,
  def_perm:.default_repository_permission, mem_create:.members_can_create_repositories,
  web_signoff:.web_commit_signoff_required, plan:.plan.name}'
for r in jolarca jolarca-compliance jolarca-data jolarca-infrastructure jolarca-legal .github; do
  printf '%-22s ' "$r"
  gh api "repos/jolarca-dev/$r/collaborators?affiliation=all&permission=admin" \
    -q '[.[].login]|join(",")'
done

# D-24 the ALLOW_MISSING exemption is date-bound; both MUST exit 2.
ALLOW_MISSING=jolarca-control bash scripts/check_fleet_separation.sh; echo "exit=$? (undated)"
ALLOW_MISSING=jolarca-control ALLOW_MISSING_UNTIL=2026-01-01 \
  bash scripts/check_fleet_separation.sh; echo "exit=$? (expired)"

# D-22 / D-22a the plan gate is tested, not trusted.
bash tests/test_check_plan_safety.sh

# D-27 the declared code standard is now actually executed.
.venv/bin/ruff check scripts/ tests/ && .venv/bin/mypy \
  && shellcheck -x scripts/*.sh tests/*.sh && echo "code_quality gate: PASS"

# D-07 tag protection has no mechanism on the current plan.
gh api orgs/jolarca-dev/rulesets                     # -> 403 Upgrade to GitHub Team
gh api repos/jolarca-dev/jolarca/tags/protection     # -> 404, API removed

# D-31 the RoPA and vendor assessments are publicly readable right now.
gh api repos/jolarca-dev/jolarca-compliance/contents/ropa/master-register.csv -q .size
gh api "repos/jolarca-dev/jolarca-compliance/git/trees/main?recursive=1" \
  -q '[.tree[].path]|map(select(test("ropa/|vendor-assessments/.*assessment")))|length'
gh api "repos/jolarca-dev/jolarca-legal/git/trees/main?recursive=1" \
  -q '[.tree[].path]|map(select(test("contracts/")))|length'

# D-28 the index must not hold IDE metadata.
git status --short | grep -E '^A.*(\.idea/|main\.py)' && echo "FAIL" || echo "index clean"

# ── D-33 branch protection on the Free plan (added 2026-09-26) ───────────────

gh api orgs/jolarca-dev -q .plan.name          # -> free

# The dedicated protection endpoint 403s on private repos, but the enforcement
# signal on the branch object does not. This is the check that works on Free,
# and the one drift_detect.py does not currently perform.
for r in $(gh api orgs/jolarca-dev/repos -q '.[].name'); do
  vis=$(gh api "repos/jolarca-dev/$r" -q .visibility)
  prot=$(gh api "repos/jolarca-dev/$r/branches/main" -q .protected 2>/dev/null | tail -n1)
  case "$prot" in true|false) ;; *) prot="n/a (no main branch yet)";; esac
  printf '%-24s %-8s protected=%s\n' "$r" "$vis" "$prot"
done
# Expect: protected=false on all seven private repos, true only on jolarca and
# .github, "n/a" on the seven still-empty public repos.

# No ruleset substitute exists either.
gh api orgs/jolarca-dev/rulesets                  # -> 403 Upgrade to GitHub Team
gh api repos/jolarca-dev/jolarca-control/rulesets # -> 403 Upgrade to GitHub Pro

# Proof by behaviour: a private repo with zero PRs and direct pushes to main.
gh api "repos/jolarca-dev/jolarca-security/pulls?state=all" -q length   # -> 0
gh api "repos/jolarca-dev/jolarca-security/commits?per_page=50" \
  -q '[.[] | select((.commit.message | contains("(#")) | not)] | length'   # -> 14

# Terraform manages no protection while the fleet-wide flag is false.
grep -n enable_branch_protection terraform.tfvars variables.tf
python3 - <<'PY'
import json, collections
s = json.load(open('terraform.tfstate'))
c = collections.Counter(r['type'] for r in s['resources'] for _ in r.get('instances', []))
print(dict(c))
print('github_branch_protection instances:', c.get('github_branch_protection', 0))
PY

# The encoded baseline contradicts the declared one.
grep -nE 'strict|dismiss_stale_reviews|require_code_owner_reviews|required_linear_history|require_conversation_resolution' branch-protection.tf
grep -n -A 32 '^branch_protection:' policy/repo-defaults.yml

# And the detection control files the gap as "could not check", not as drift.
.venv/bin/python scripts/drift_detect.py 2>/tmp/d33.err >/dev/null; echo "drift exit=$? (want 2)"
grep -c 'protection HTTP 403' /tmp/d33.err   # -> 7 private repos, all "unverifiable"
```

## 2026-09-29 — L-16 secret-pattern triage (jolarca-control)

**Finding:** L-16 (S2) — secret-pattern match in git history: AWS access key ID `AKIAQ3EG...B2M` and Stripe live secret key `sk_live_...`.

**Triage decision:** **FALSE POSITIVE — documented test fixtures.**

Both patterns are explicitly documented as test fixtures:
- `docs/adr/0009-bugs-found-and-fixed.md` — documents the bug found and fixed related to these patterns.
- `docs/runbooks/first-commit-pipeline.md` — runbook documenting the fixtures.
- `tests/test_repo_readiness_audit.py` — test fixtures (lines 488, 646, 895, 903, 905).
- `scripts/repo_readiness_audit.py:192` — the pattern definition itself.

The ADR 0009 explicitly states these are fixtures planted to prove gitleaks fires. Gitleaks reported NO leak (exit 0), confirming these are regex-only matches, not real secrets.

**Action:** No rotation required. Finding L-16 is closed as a documented false positive.

**Triaged by:** Gintaras Kazlauskas, 2026-09-29.

## 2026-09-30 — Out-of-band live mutations

### D-34 · `jolarca-identity` flipped to private out-of-band — **FIXED**
| | |
|---|---|
| Evidence | `gh repo edit jolarca-dev/jolarca-identity --visibility private --accept-visibility-change-consequences` executed 2026-09-30. Verified: `gh api repos/jolarca-dev/jolarca-identity -q .visibility` → `private`. Previously live `public`, declared `private` in `repos/jolarca-identity.yml`. |
| Impact | HIGH-exposure IAM policy repo (PCI-DSS-scoped, identity/access policies) was publicly readable. Now aligned with declaration. |
| Trade-off | `jolarca-identity` is now private on the Free plan, so GitHub's built-in secret scanning (available only on public Free repos) is lost. Compensating: gitleaks runs in CI on every PR and full-history scan, which covers the same surface. |
| Terraform impact | `jolarca-identity` is not yet in Terraform state (D-02/D-13 state migration pending). When imported, the declared `visibility: private` will match live state — no visibility flip on first apply. |
| Related | D-01 (visibility drift), D-31 (accept-public infeasible), D-33 (private repos lose branch protection on Free). |

### D-35 · `jolarca-control` branch protection enabled out-of-band — **FIXED**
| | |
|---|---|
| Evidence | `PUT /repos/jolarca-dev/jolarca-control/branches/main/protection` executed 2026-09-30 with the config declared in `repos/jolarca-control.yml`. Verified: `.protected = true`, all 3 required contexts active (`Validate Repo Allow-List`, `Policy Compliance Check`, `Repository Secret Pattern Scan`), `enforce_admins: true`, `block_force_pushes: true`, `block_deletions: true`, `require_linear_history: true`, `require_conversation_resolution: true`, `restrictions: {users: [], teams: []}` (admins only). |
| Impact | The control plane now has the branch protection it declared but never had. Direct pushes to `main` are blocked; all changes must go through PRs with the required status checks passing. |
| Deviation from declared config | `require_code_owner_reviews: false` (D-20: inert without teams in `jolarca-dev`). Matches the B3 remediation decision. |
| Terraform impact | Terraform state holds zero `github_branch_protection` resources (`enable_branch_protection = false` in `terraform.tfvars`). This out-of-band change will NOT be reverted by `terraform apply`. When the fleet-wide flag flips, the declared config in `repos/jolarca-control.yml` matches what was applied here. |
| Related | D-08 (out-of-band protection history), D-33 (private repos unprotected on Free), D-04 (zero-review deviation). |

### D-36 · Wiki drift on 3 repos disabled out-of-band — **FIXED**
| | |
|---|---|
| Evidence | `PATCH /repos/jolarca-dev/{jolarca-docs,jolarca-runbooks,jolarca-vendor}` with `{"has_wiki": false}` executed 2026-09-30. Verified: `has_wiki=false` on all 3. Previously live `has_wiki=true`, declared `has_wiki: false` in `repos/*.yml`. All 3 wikis were empty (no pages, no git refs) — zero data loss. |
| Impact | Policy (`has_wiki: false` in `policy/repo-defaults.yml`) is security-driven: wikis bypass PR review, cannot be GPG-checked, and have no audit trail. For governance/compliance repos every change must go through the reviewable path. |
| Terraform impact | `repositories.tf` reads `has_wiki` from `repos/*.yml`; declared value was already `false`. On first apply, Terraform will set `has_wiki=false` matching live state — no drift. |
| jolarca-identity | Was already `has_wiki=false` live (flipped with visibility change to private). No action needed. |
| Related | D-26 (drift detection covers wiki state). |

## 2026-09-30 — GitHub forced-public migration

### D-37 · GitHub migrating all repos to public within 10 days — **DECLARATIONS ALIGNED**
| | |
|---|---|
| Evidence | GitHub notified the org that all repositories will be made public within 10 days. As of 2026-09-30, 4 repos already live-public that were declared private: `jolarca-compliance`, `jolarca-data`, `jolarca-identity`, `jolarca-legal`. Remaining private: `jolarca-infrastructure`, `jolarca-observability`, `jolarca-security`. |
| Impact | D-01 (visibility drift) is resolved — all declarations updated to `visibility: public`. D-31 (accept-public infeasible) is superseded — the decision was made for us. Data classifications downgraded from `confidential` to `internal` for 5 repos (compliance, data, infrastructure, legal, observability) since public repos cannot hold confidential-classified content. |
| Compliance exposure | `jolarca-compliance` held the GDPR Art. 30 RoPA register, KYC vendor assessments, and cross-border transfer mechanisms. `jolarca-legal` held contracts and DPAs. These are now world-readable. Assess under GDPR Art. 33 whether the exposure to date is notifiable. |
| Actions taken | 1. All 7 private repos declared `visibility: public`. 2. Five `confidential` classifications downgraded to `internal`. 3. `documented_risk_acceptance: true` added to jolarca-compliance, jolarca-infrastructure, jolarca-legal (PCI-DSS operational repos). 4. Exception `fleet-public-2026-10` added to `policy/compliance-gates.yml`. 5. D-01 and D-33 in `open_blocking` marked RESOLVED. |
| Branch protection | All repos will be public, so Free plan ALLOWS branch protection on all of them. D-33 (private repos unprotected) is resolved for public repos. Remaining: enable protection on repos that get content after the migration. |
| Related | D-01 (resolved), D-31 (superseded), D-33 (resolved for public repos). |
| Correction (2026-10-06) | "D-31 … superseded" is **wrong and is reversed here**: the forced-public migration did not supersede D-31, it **instantiated** it — the `confidential`-classified RoPA / KYC / vendor-TIA that D-31 said must not be public became public, and the `confidential`→`internal` downgrade in the Impact row above was made *to stop the validator flagging the exposure*, i.e. the masked-classification defect itself. D-31 stands **OPEN/blocking**; see D-52 for the chosen remediation. |

### D-38 · `jolarca` stale-review dismissal enabled out-of-band — **FIXED**
| | |
|---|---|
| Evidence | `PUT /repos/jolarca-dev/jolarca/branches/main/protection` with `dismiss_stale_reviews: true` executed 2026-09-30. Verified: `dismiss_stale_reviews=true` live. Previously live `false`, policy baseline `true` in `policy/repo-defaults.yml#organization_baseline.required_branch_protection`. |
| Impact | drift_detect reported `weakened: jolarca — stale reviews not dismissed`. Now aligned with policy. |
| Terraform impact | `branch-protection.tf` declares `dismiss_stale_reviews = true` for jolarca. On first apply, Terraform will match live state — no drift. |
| Related | D-08 (out-of-band protection history), D-33 (branch protection on public repos). |

### D-39 · Remaining private repos flipped to public + 6 repos protected — **FIXED**
| | |
|---|---|
| Evidence | 2026-10-01: (1) `jolarca-infrastructure`, `jolarca-observability`, `jolarca-security` flipped to public via `gh repo edit --visibility public --accept-visibility-change-consequences`. Verified live `visibility=public`. (2) Branch protection enabled on 6 repos (`jolarca-compliance`, `jolarca-data`, `jolarca-identity`, `jolarca-infrastructure`, `jolarca-legal`, `jolarca-security`) via `PUT /branches/main/protection`. Verified `.protected=true` on all 6. (3) Wiki disabled on `jolarca-identity` and `jolarca-observability` via PATCH. Verified `has_wiki=false`. |
| Impact | Completes the D-37 forced-public migration: all repos now declared==live for visibility. All non-empty repos now have branch protection. Drift detect exits 0 (no drift) for the first time. |
| Policy update | `branch_protection_baseline_exempt` expanded to include the 6 repos with repo-specific CI contexts (not the compliance-scan triplet). Protection is enforced; only the minimum-contexts comparison is skipped. |
| Protection config | Minimal: `enforce_admins=true`, `block_force_pushes=true`, `block_deletions=true`, `required_linear_history=true`, `required_conversation_resolution=true`, `restrictions={users:[],teams:[]}`. No required status checks (repos use their own CI). |
| Related | D-34 (identity flip), D-35 (control protection), D-36 (wiki drift), D-37 (forced migration). |

## 2026-10-03 — Declared gate vs server-side enforcement (`jolarca-hermes-agents`)

### D-40 · `required_gates.secret_scan: true` is intent, not a merge-blocking check — **OPEN**

|  |  |
|---|---|
| Evidence | 2026-10-03, read-only `gh api repos/jolarca-dev/jolarca-hermes-agents/branches/main/protection`: `strict=true`, `contexts=lint,test,security`, `enforce_admins=true`. That repository's `ci.yml` **does** define a `secrets-scan` job (checksum-verified gitleaks CLI over full history, `--exit-code 1`) and it has passed on every run since its PR #23, but the job name is absent from `contexts`, so a failing secret scan cannot block a merge. `repos/jolarca-hermes-agents.yml` nevertheless declares `compliance.required_gates.secret_scan: true`. |
| Consumed by | Nothing. `git grep -rn required_gates -- scripts *.tf policy` returns no hits: the block is declarative metadata whose *shape* is exercised only by `tests/test_validate_repos.py:118`. No script, policy check or Terraform resource reads it, so no gate outcome depends on it and changing the value would be theatre. |
| Impact | By this repo's own §6 ("never describe a control as enforced when it is configured-but-inert"), the declaration asserts a required gate the live rule does not require. The overstatement propagated outward into `jolarca-hermes-agents/QODER.md` §7.10, which said secret scanning "is enforced by the CI `secrets-scan` job" — corrected there by PR #32. No actual exposure found: gitleaks over full history exits 0 locally and the CI job is green. |
| Why not fixed here | Promotion cannot be performed from either repository. `terraform state list` in this root exits 1 with "Terraform has not yet made changes to your existing configuration or state", so there is no state to plan against and no incremental apply to review. §5 forbids an agent both `apply`/`import` here and any `gh api -X PATCH` of branch protection; §8 records D-01/D-02/D-18/D-20/D-33 blocking the first apply with no targeted-apply mechanism, and `make apply` is refused by design. The live rule was created out-of-band (cf. D-38, D-39 `PUT /branches/main/protection`). |
| Not a first-apply blocker | Deliberately **not** added to `exceptions.open_blocking`: this finding does not make an apply dangerous, and filing it there would misrepresent it as one. It is an attestation-accuracy defect, not a state-danger defect. |
| Decision owner | Operator. Either (a) promote `secrets-scan` into `required_status_checks.contexts` once this root genuinely owns branch protection (state import plus resolution of the five existing blockers), or (b) leave the live rule where it originated and treat `required_gates` here as declared intent only. This entry records (b) as the honest current state; (a) stays open as a migration decision. |
| Related | D-02 (no remote state, so no plan/apply/import), D-08 (out-of-band protection history), D-33 (protection on public repos), D-38, D-39. |

### D-41 · `branch-protection.tf` STATUS comment contradicts `terraform.tfvars` — **OPEN, fix proposed not applied**

|  |  |
|---|---|
| Evidence | `branch-protection.tf` lines 18–20 state "terraform.tfvars still sets `var.enable_branch_protection = false`, so these resources still create nothing until the operator flips the flag". `terraform.tfvars:46` sets `enable_branch_protection = true`. |
| Impact | The rationale is stale in the direction that matters. `locals.protected_repos` filters on `&& var.enable_branch_protection`, so the guard now evaluates true and `github_branch_protection.main` **would** be created on a first apply — while D-38/D-39 show equivalent protection already exists live, created out-of-band. A reader trusting the comment concludes nothing is managed; a reader trusting the tfvars plans a create against existing rules. Both readings are wrong, in a file this repo classifies high-blast-radius (§4). |
| Proposed fix | Replace the false clause in the STATUS block with the measured value and the surviving caveat: the flag is true, yet the resources remain inert because this root holds no state (D-02). Comment-only, zero semantic change. Not applied here because §4 puts any `*.tf` edit in the human-read-plan class, and the fix belongs with the D-02 migration rather than beside it. |
| Decision owner | Operator, as part of the D-02 remote-state-backend migration. |
| Related | D-02, D-38, D-39, D-40. |

### D-42 · `AGENTS.md` §8 misstates live branch protection on this repo main — **CORRECTED 2026-10-06 (§8 rewritten on operator delegation)**

|  |  |
|---|---|
| Evidence | 2026-10-03, read-only `gh api repos/jolarca-dev/jolarca-control/branches/main/protection`: `strict=true`, `enforce_admins=true`, `required_approving_review_count=0`, `contexts=Validate Repo Allow-List, Policy Compliance Check, Repository Secret Pattern Scan`. Recent runs of `compliance-scan.yml`: `main` 2026-09-30T21:55 `success`; this PR #25 all 7 checks `pass`. |
| Impact | Section 8 asserts two things that are false as measured. (a) "Branch protection is not active on this repos `main`... enforceable by nothing today (D-33)" — protection IS active, with three required contexts and `enforce_admins=true`. (b) "`Policy Compliance Check` fails... `Repository Secret Pattern Scan`... a required context that is structurally incapable of going green... neither blocks a merge, because nothing server-side enforces them" — both are REQUIRED contexts and both PASS. |
| Which half is hazardous | (b). A required gate documented as permanently broken invites an agent to dismiss a genuine failure, or to "fix" a phantom red by editing the gate — the exact move section 5 prohibits. It also propagated outward: this session an agent repeated the "nothing server-side enforces them" framing into another repository report before measuring. (a) fails safe, since a direct push is simply rejected, but it still breaches section 6 ("documentation must state actual implementation status"). |
| Why D-33 no longer explains it | D-33 was the Free-plan restriction on protecting PRIVATE repos. D-37 and D-39 record the forced-public migration completing, so protection is permissible here and was in fact applied. Section 8 still cites D-33 as the reason, which is now history rather than status. |
| Proposed fix | Rewrite the first bullet to state protection is live and name the three required contexts; replace the two-red-contexts bullet with the measured status (both contexts pass, and with `strict = true` on this public repo a red context now blocks a merge); drop D-18 from the open-blocking list (org 2FA enforced 2026-10-01) and record D-20's cross-org CODEOWNERS breach as resolved. APPLIED 2026-10-06 on operator delegation ("use judgement and fix every material finding") via the `AGENTS.md` §8/§2 rewrite; §1's PR route is satisfied by this PR. |
| Related | D-33 (superseded rationale), D-37, D-39 (public migration enabling protection), D-40. |
## 2026-10-04 — Fleet pin discipline: a non-existent commit SHA and mutable branch refs

### D-43 · `.github/security-scan.yml` pins gitleaks-action to a commit that does not exist, and five steps pin `@master` — **OPEN, decision requested (fleet convention)**

|  |  |
|---|---|
| Rule at issue | `AGENTS.md` §5: "GitHub Actions pin to a full commit SHA with a `# vX.Y.Z` comment". As written the rule is **Actions-specific**; it says nothing about pre-commit `rev:`. Enforced by test only in `jolarca-hermes-agents` (`tests/test_ci_hardening.py`); no equivalent guard was found in this repo. |
| Evidence — the hard failure | `jolarca-dev/.github`, `.github/workflows/security-scan.yml`: `uses: gitleaks/gitleaks-action@4f9a10a3b6e2a7a1b5d6b5a5e5e5e5e5e5e5e5e5 # v2.3.4`. `GET /repos/gitleaks/gitleaks-action/git/commits/4f9a10a3…` returns **HTTP 404**. Control sample in the same call shape: `…/git/commits/e6dab246340401bf53eec993b8f05aebe80ac636` returns **HTTP 200**, and `git/ref/tags/v2.3.4` resolves to that commit. The pinned object is not permission-hidden — it does not exist, and the version comment does not describe it. |
| Evidence — mutable branch pins | same file: `aquasecurity/trivy-action@master` (lines 75, 86, 128) and `bridgecrewio/checkov-action@master` (lines 161, 172). `@master` floats on every run; this is the retarget vector §5 exists to close, in the workflow whose declared purpose is secret and IaC scanning. |
| Evidence — latent, not live | No allow-listed repo references a `jolarca-dev/` reusable workflow: `grep -rn "uses: jolarca-dev/" */.github/workflows/` matched only `.github` itself, which self-references `@main`. The three shared workflows are therefore **unused**, so a call would fail at job startup rather than silently produce results. Configured-and-never-executed is precisely how a false control survives. |
| Evidence — `.github` is outside the registry | `repos/*.yml` declares 16 entries; `.github` is **not** among them. The org repository whose workflows the fleet is told to consume carries no allow-list entry and no validator. |
| Evidence — allow-listed repos violating §5 | tag-pinned Actions refs: `jolarca` 45, `jolarca-infrastructure` 3, `jolarca-identity` 2, `jolarca-vendor` 2, `jolarca-data` 1. Zero tag refs: `jolarca-hermes-agents` (31 SHA), `jolarca-control` (24), `jolarca-consent` (17), `jolarca-compliance` (16), `jolarca-legal` (10), `jolarca-security` (5), `jolarca-dr` (3), `jolarca-payments` (3), `jolarca-runbooks` (3), `jolarca-docs` (1). `jolarca-observability`: sha=10 tags=0. |
| Evidence — the pre-commit gap is compliance-as-written | Twelve repos carry `.pre-commit-config.yaml` and every one pins `rev:` by version tag (`jolarca-hermes-agents`: v8.30.1, v5.0.0, v0.9.1; `jolarca-control`: v5.0.0, v0.16.9, v2.3.1, v1.97.3, v1.38.0; `jolarca-compliance`: v4.6.0, v8.30.1). Resolved commits for the hermes-agents three, measured via `git/ref/tags`: 83d9cd684c…, cef0300fd0…, 18ba2d02dc… (all tag objects resolving directly to commits, so SHA pinning is technically available). Because §5 names only Actions, tag-pinned revs **comply**. |
| Impact | Two exposures, different kinds. (1) A pin to a non-existent commit claims provenance that cannot be verified, reviewed or re-fetched — an auditor cannot trace what would have run. (2) `@master` plus 51 tag refs across five allow-listed repos mean an upstream retarget silently changes what CI executes. Neither is currently load-bearing, which is why it survived. |
| Why not fixed here | The edits belong to **other repositories**, and `.github` is unregistered. §4 classes `.github/workflows/**` as high blast radius requiring a human-read plan; a cross-repo sweep by an agent is not the sanctioned route. Nothing outside this file was modified. |
| Proposed decision — in sequence | **(1)** Fix what the rule already forbids, needing no policy change: correct the gitleaks pin to `e6dab246340401bf53eec993b8f05aebe80ac636 # v2.3.4`, SHA-pin the five `@master` refs, and bring `jolarca`, `jolarca-identity`, `jolarca-infrastructure`, `jolarca-vendor`, `jolarca-data` into §5 compliance. **(2)** Then settle `rev:` explicitly, once, fleet-wide: **(A)** extend §5 to pre-commit `rev:` SHAs — which requires *also* naming the tool it displaces, because `pre-commit autoupdate` rewrites `rev:` back to tags on its next run; or **(B)** keep version-tag revs, state the trade-off, and rely on update monitoring (dependabot/npm-style) plus exact versions; or **(C)** decide nothing and accept that CI actions and local hooks give different guarantees permanently. **(3)** Register `.github` in `repos/`, or record why the repo that executes fleet CI is exempt from the registry. |
| Recommendation | **(1) now** — it enforces a rule already in force, and the gitleaks pin is the one item where provenance is claimed *and* false. For **(2)** I would choose **B** and write it down. pre-commit's update path is tag-shaped by design, hooks run only per installed clone, and every job that decides a merge outcome is already SHA-pinned. Adopting A while leaving `autoupdate` in the documented workflow would create a rule its own tooling breaks on the next run — folklore, not a control. |
| Decision owner | Operator. Part (3) touches the allow-list, a high blast-radius path. |
| Not verified | Whether `.github`'s workflows are invoked from organisation-level settings rather than repo files; what `trivy-action@master` and `checkov-action@master` currently resolve to; whether the 51 tag refs sit in steps that actually execute (files were read, runs were not); and whether the corrected gitleaks pin would even run — prior evidence is that `gitleaks-action` needs `GITLEAKS_LICENSE` for org-owned repos and its `@v2` tag resolves to an annotated tag object, which Actions rejects as a pin. Verify before any repo is wired to that workflow. |
| Related | D-40 (declared gate vs server-side enforcement), D-42 (`AGENTS.md` §8 stale), `jolarca-hermes-agents` `QODER.md` §7.1 and §7.12, `tests/test_ci_hardening.py`. |
| Correction (2026-10-04) | This row's framing that `.github` is "not in `repos/*.yml`, so no validator covers it" overstated the case. `scripts/drift_detect.py` sets `HEALTH_REPO = ".github"`, excludes it from allow-list comparison by design, and `health-repo.tf` manages the repository itself; `scripts/validate_repos.py` and `scripts/check_fleet_separation.sh` both carry documented exceptions for it. So it is not a forgotten repo -- it is the designated organization health repository. The real and narrower gap: `health-repo.tf` declares no `github_branch_protection` resource, while the live rule requires zero status checks (measured: protection readable, `contexts = []`, `required_approving_review_count = 0`), and D-45's proposed "register `.github` in `repos/`" would conflict with that deliberate exclusion rather than fix it. Corrected in D-48. |
| Part 1 status | Executed: `jolarca-dev/.github#4` pins the four remaining floating setup refs, replaces the fabricated gitleaks SHA in `ci-base.yml:109` (PR #1 fixed only `security-scan.yml`), and corrects two `# master` version comments. Deliberately untouched and recorded instead: `codeql-action/upload-sarif@v3`, which has no `tags/v3` and no `heads/v3` (both HTTP 404) and so cannot be pinned -- only upgraded. |
| Measurement correction (2026-10-04) | This row's per-repo counts were taken from **checked-out working trees** rather than fetched refs, and they are wrong for several repositories. Recomputed from `refs/remotes/origin/main` blobs, counting only enabled workflow files (`*.yml`/`*.yaml`, excluding `*.disabled`), as SHA-pinned vs moving-tag `uses:` refs: `jolarca` 2/45 (as published); `jolarca-compliance` **0/16** (published 16 SHA, 0 tags -- inverted, and listed as clean); `jolarca-security` **0/5** (same inversion, listed as clean); `jolarca-payments` **1/2** (listed as clean); `jolarca-data` 11/1 and `jolarca-infrastructure` 14/3 (tag counts as published); `jolarca-consent` 17/0, `jolarca-control` 24/0, `jolarca-docs` 1/0, `jolarca-dr` 3/0, `jolarca-hermes-agents` 31/0, `jolarca-legal` 10/0 (as published). `jolarca-identity` and `jolarca-vendor` now read 2/0 and 2/0 because this workstream's own PRs merged; the published 2 and 2 were correct when written. `jolarca-observability` and `jolarca-runbooks` cannot be recomputed from a fetched `origin/main` in this clone, so 10/0 and 3/0 stand as **unverified** rather than confirmed. |
| Cause, so it is not repeated | The scanned trees carry unlanded work: `jolarca-compliance` 29 dirty tracked files, `jolarca-consent` 21, `jolarca-payments` 4, and `jolarca-infrastructure` 9 with its local `main` two commits behind `origin/main`. Those trees already SHA-pin refs that `main` still floats, which is how three non-compliant repositories were reported clean. Rule for anyone re-measuring: read `git show <ref>:<path>`, never the working directory, and state whether `.disabled` files are counted. |
| Consequence for part 1 of the proposal | "Bring violating repos into §5 compliance" is partly drafted and unlanded -- remediation already exists as uncommitted or unmerged work in compliance, consent, infrastructure and payments. The efficient path is reviewing and landing that work; parallel PRs from here would collide with it. |



### D-47 · `jolarca-security` declared required status checks that no job in the repo could report — **FIX LANDED 2026-10-05; enforcement pending `terraform apply`**

|  |  |
|---|---|
| Evidence | `repos/jolarca-security.yml` declares `branch_protection.main.required_status_checks.contexts: [lint, security]`. `GET /repos/jolarca-dev/jolarca-security/contents/.github/workflows` returns `gitleaks.yml` and `lint.yml`, whose jobs publish the contexts `Markdown lint`, `YAML syntax validation` and `gitleaks` (GitHub names a check after a job's `name:` when set, else the job key). Neither `lint` nor `security` is producible. The repo is public with content (`size` 58), `launch_status: planned`, so unlike `jolarca-observability` and `jolarca-runbooks` -- both empty, both skipped by the new check -- this is not a not-yet-started repository. |
| How found | By `scripts/check_declared_contexts.py` on its first live run, alongside the jolarca-identity case in D-44. That is the point of wiring the check: the identity defect had previously been found only because someone ran a manual audit, and this one had gone unnoticed entirely. |
| Impact | Same class, larger blast radius: applying the declaration under `strict: true` makes every future PR in jolarca-security unmergeable, and the repo is the fleet's security-scanning reference whose workflow others copy. Today nothing enforces the declaration, so the mismatch is latent -- which is exactly the state that made it invisible. |
| Proposed fix | Follow the identity sequence: first rename the jobs in jolarca-security so the contexts are stable lowercase keys (`lint`, `secret-scan`), then align `repos/jolarca-security.yml` in a PR that regenerates `docs/evidence-registry.csv`. Declaring the current display names instead would work but is the brittle option: a reworded job title would silently un-required a check. |
| Interim handling | Added to the time-boxed `ALLOW_MISSING_REPOS` in `.github/workflows/context-parity.yml` with `ALLOW_MISSING_UNTIL: 2026-11-15`, so the job is green now and red on purpose after the date. Recorded here rather than only in the env line, so the register carries the reason. |
| Decision owner | Operator, for the naming choice; the rename PR itself is an ordinary review PR. |
| Related | D-44 (identity, declared-vs-producible), D-46 (rulesets outside the source of truth), D-22 (an unwired detection is folklore), D-23 (unverifiable is never a pass). |
| Status (2026-10-04, corrects the row it replaces) | The rename-then-declare **pair** is a three-link **chain**, and the pair framing would itself have bricked the repo. `jolarca-security#1` (three keys, cut against `main`) is CLOSED as superseded: its own CI measured `markdown-lint` red (238 findings across 10 files -- no markdownlint config exists on `main`) and `secret-scan` reporting **nothing at all**, because the gitleaks workflow cannot load (D-49). Declaring three contexts there meant binding one red check and one impossible one. The chain is: `jolarca-security#2` (make the jobs runnable and passing) -> `jolarca-security#3` (drop the four prose `name:` overrides so the keys become `markdown-lint`, `policy-tests`, `secret-scan`, `yaml-lint`) -> `jolarca-control#32` (declare those four). `policy-tests` is a genuine addition, not a rename: it is the policy-as-code suite #2 introduces. |
| Landed (2026-10-05) | All three links merged. `jolarca-security` main is `904a699`; deriving contexts from its workflow blobs (the rule GitHub uses -- `name:` if set, else the job key) yields exactly `markdown-lint`, `policy-tests`, `secret-scan`, `yaml-lint`, with no job-level `name:` left, and the push-triggered runs on that commit report all four **success**. `jolarca-control` main is `f35c69e` with the four keys declared and `docs/evidence-registry.csv` carrying the matching hash row. Re-running `scripts/check_declared_contexts.py` against main's declarations shows `jolarca-security` **absent from the findings** -- it is producible now, not excused: the run had no `ALLOW_MISSING_REPOS` set, so the earlier time-boxed exception was not applied. |
| What is still missing | Enforcement. No `terraform apply` has run, so the live rule on that repository is still the out-of-band minimal one recorded in D-39 (protection exists, zero required status checks). This row is therefore NOT closed: the declaration is now true and satisfiable, but the checks do not block a merge until the operator applies it (D-40's declared-vs-enforced distinction applies verbatim). A further precondition is measured in D-44/D-48: an **untargeted** apply would also bind `jolarca-identity`, whose declaration is still unsatisfiable while #29 and jolarca-identity#3 remain open. |
| Lesson worth keeping | A name is only half of an enforceable check. A required status check must (a) exist as a reportable name, (b) be capable of passing, and (c) have been observed passing. The first cut of this fix addressed (a) alone and would have handed (b) and (c) to the operator as a surprise after `terraform apply`. A fourth lesson arrived while landing it: because `delete_branch_on_merge` is on and #3 was stacked on #2's branch, merging #2 **first** would have deleted #3's base and closed #3 unrecoverably -- the dependent PR had to be retargeted before its prerequisite merged. |
| Lesson worth keeping | A name is only half of an enforceable check. A required status check must (a) exist as a reportable name, (b) be capable of passing, and (c) have been observed passing. The first cut of this fix addressed (a) alone and would have handed (b) and (c) to the operator as a surprise after `terraform apply`. |


## 2026-10-04 — Six allow-listed repositories declare required status checks that their live rules do not enforce

### D-48 · The `branch_protection_baseline_exempt` list spans six repos whose own declarations require contexts — **OPEN, policy decision required**

|  |  |
|---|---|
| Evidence | Measured 2026-10-04 by comparing `repos/*.yml` declarations against each repo's live branch protection and its workflows' reportable contexts (job `name:` if set, else job key). Six exempt repos declare contexts while their live rules enforce none: `jolarca-compliance` (declares 4, all producible), `jolarca-data` (3, all producible), `jolarca-infrastructure` (3, all producible), `jolarca-legal` (2, all producible), `jolarca-identity` (3, **none** producible -- see D-44), `jolarca-security` (2, **none** producible -- see D-47). `.github` also appears in the hollow set but declares no allow-list entry at all, so it has no declaration to enforce (see D-43's correction row). |
| Evidence — rule layering | GitHub's own documentation states that rulesets and branch protection "work alongside each other, and all applicable rules are enforced", and that aggregated rules resolve to the most restrictive version. Verified from the docs page, NOT reproduced experimentally on these repos. Consequence: adding legacy `github_branch_protection` does not fight a hollow ruleset -- it layers on top of it. |
| Why it matters | `policy/repo-defaults.yml` says of the exemption: "A rule must still EXIST -- only the attribute baseline above is skipped. That keeps the exemption from becoming a way to leave a repo unprotected." Measured reality is weaker than that sentence: the exemption currently hides six repos whose own declarations require checks. The comment promises one thing; the code delivers another. |
| Interim state in code | `jolarca-control#28` already surfaces all six in `hollow_rules`, deliberately informational: making it fail would turn `make drift` red across six repositories before any fix exists, and a permanently red signal is worth less than a green-when-clean one. This row is the place the decision is recorded, not silently deferred. |
| Proposed fix, ordered | (1) Apply for the four where the declaration is already satisfiable (compliance, data, infrastructure, legal) -- nothing else is needed, and the union rule means no ruleset edit is required. (2) For identity and security, land the rename-then-declare sequence (identity #3 / control #29; D-47 for security) before applying, since their declarations are currently unsatisfiable. (3) Then tighten the semantics: exempt repos should still be required to enforce at least `minimum_required_contexts` when they DECLARE contexts, which makes the code match the comment in `policy/repo-defaults.yml`. Repos that declare none (the health repo) stay exempt legitimately. |
| Decision owner | Operator. Step (3) is a policy change with an immediate red pipeline until steps (1) and (2) land, which is exactly why it is recorded rather than implemented in a bug-fix PR. |
| Related | D-44 (identity, and the exempt-blind-spot mechanism), D-47 (security), D-46 (rulesets outside the source of truth), D-43 (`.github` framing corrected here), D-22, D-23. |

### D-49 · jolarca-security's secret-scanning workflow could not load on its own default branch — **RESOLVED 2026-10-05, merged as `jolarca-security#2`**

|  |  |
|---|---|
| Evidence | On `main`, gitleaks run 37232416751 is **`startup_failure`** with `jobs: []` -- not a job that ran and failed. `.github/workflows/gitleaks.yml` declares `uses: gitleaks/gitleaks-action@e0c47f4`; that ref is real but **abbreviated** -- it expands to `e0c47f4f8be36e29cdc102c57e68cb5cbf0e8d1e`, tag v3.0.0 (measured: `/commits/e0c47f4` resolves, `/git/commits/e0c47f4` 404s because that route needs the full object id). Actions refuses shortened SHAs when loading a workflow, so nothing starts. The consequence for branch protection is the point: **a workflow that fails to load emits no check run at all**, so a required context bound to it can never be satisfied -- a permanently unmergeable repository, not a red X. Separately, `lint.yml` has run **exactly once in this repository's history** (today, 20:31Z, on my own PR): it triggered on `pull_request` only, while all 14 commits on `main` were pushed directly and none carries a PR reference. |
| Compounding cause | The file header itself states the action "Requires GITLEAKS_LICENSE for organization repos", and prior fleet evidence is that `gitleaks-action` fails on org-owned repos without a licence secret while its `@v2` tag resolves to an annotated tag object that Actions rejects as a pin. Two independent reasons the step cannot pass. |
| Impact | The repository named `jolarca-security` runs a non-functioning secret scan on its default branch. §5's pin rule is what makes the failure instant and visible -- an unresolvable ref is a job-start error rather than a silent pass -- yet the control is still absent where it matters most. On a SOC 2 / ISO 27001 surface, "the security repo's scanner fails on main" is a finding an auditor should read, and describing secret scanning as enforced here would be exactly the D-40 error. |
| Already drafted; not duplicated here | The unmerged branch `chore/readiness-audit-remediation` (24 files, +2203 lines) replaces the action with a checksum-verified gitleaks CLI download -- the pattern already proven in `jolarca-identity` and in `jolarca-hermes-agents`' `secrets-scan`. This is a landing problem, not a missing implementation, so a parallel PR from here would collide with in-flight work. |
| Caveat for whoever rebases it | That branch re-adds display-name overrides ('gitleaks (full history)', 'Policy-as-code tests') and a `policy-tests` job. After `jolarca-security#1`, contexts must stay stable job keys or D-47 returns through the back door -- and `repos/jolarca-security.yml` must then declare four keys, not three. |
| Status (2026-10-04) | Remediation pushed as `jolarca-security#2`, and **green**: run 37234191952 (gitleaks full history, checksum-verified CLI) and run 37234191960 (yaml, markdown, policy tests) both SUCCESS -- 4/4 on the PR. The asset digest was checked against the publisher, not trusted: the release API for v8.30.1 reports `sha256:551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb` for `gitleaks_8.30.1_linux_x64.tar.gz`, matching the workflow constant exactly. This is the first completed secret scan in the repository's history, so "is the history clean?" now has a measured answer instead of an assumption. The caveat proved exact: #2 keeps the prose overrides, so the rename was re-cut as #3 on top of it and `jolarca-control#32` names four keys. |
| Resolved (2026-10-05) | Merged as `6ca8cc9`, then superseded by `904a699` (#3). On that commit the push-triggered gitleaks run is `success` and its check reports the context `secret-scan` -- the name the allow-list now declares. `compliance.required_gates.secret_scan: true` in `repos/jolarca-security.yml` is consequently no longer the D-40 pattern of intent-without-a-gate: the check exists, runs on `main`, and passes. Enforcement still awaits the apply. |
| Follow-on the fleet should notice | Adding `.github/dependabot.yml` in that same PR immediately produced two real update PRs (`jolarca-security#4` checkout v6.1.0 -> v7.0.1, `#5` markdownlint-cli2-action v20 -> v24.2.0), both correctly re-pinned to full 40-character SHAs with version comments. #5 changes the **lint engine**, not just a ref, so it must be measured on its branch rather than waved through -- which is the whole reason D-49's measurement-correction row below exists. |
| Measurement correction (2026-10-04) | My first verification of #2 ran `markdownlint-cli2@0.22.1` (markdownlint v0.40.0), but CI's `@v20` reported **cli2 v0.18.1 (markdownlint v0.38.0)** -- a different engine. Re-measured against 0.18.1: still 0 errors, and the action pins its engine exactly (`"markdownlint-cli2": "0.18.1"`, no caret), so the pin is honest. Recorded because "I ran the linter locally and it was clean" is only evidence when the engine matches what the runner reports -- and MD060, which #2's config disables, does not exist in the engine CI actually uses. |
| Decision owner | Operator: rebase and land the existing remediation, keeping the key naming; then confirm which contexts become required once protection is actually applied. |
| Related | D-47 (naming), D-43 (pin discipline, with its measurement correction above), D-44/D-48 (declared vs enforced), D-40 (never call a configured control enforced). |


## 2026-10-05 — A CI gate step whose real command could never run, and a fallback that owned the verdict

### D-50 · `compliance-scan.yml` ran the regression suite through `||`, against a `.venv` no workflow creates — **OPEN, fix in review**

|  |  |
|---|---|
| Evidence | `.github/workflows/compliance-scan.yml:85` on `ab0d28f` read `- run: .venv/bin/python -m pytest tests/ -q \|\| python -m pytest tests/ -q`. Three measurements make the first command dead code: none of the six workflows creates a virtualenv (no `python -m venv`, `virtualenv` or `tox` in any file); `.venv/` is listed in `.gitignore`, so a clean checkout cannot contain it; and CI's own log for run 3723… / 37243451777 prints `line 1: .venv/bin/python: No such file or directory` immediately followed by `209 passed in 2.49s`. The fallback has therefore decided the verdict on every run this job has ever had. Measured also: exactly one `\|\|` exists across all of control's workflow run steps, and zero `continue-on-error` at step or job level. |
| Why it matters, stated precisely | The job is **not** a required status check -- `repos/jolarca-control.yml` declares `[Validate Repo Allow-List, Policy Compliance Check, Repository Secret Pattern Scan]` with `strict: true`, and job `test` is not among them -- so this cannot block a merge and is not a D-40-style overclaim: the `compliance.required_gates` block does not assert a test gate either. The harm is epistemic. A green `Regression Tests` check is read as evidence that the suite ran under the pinned interpreter, and it is not: the command that was named never executed. I read that log line as proof minutes before writing this row, which is the best available demonstration that the green is load-bearing in practice. |
| The failure it enables | `A \|\| B` transfers the verdict to B. If a `.venv` ever does appear -- a contributor adds venv bootstrapping, or an action caches one -- then A starts running, fails on something real, and B still answers green. The suite would then be genuinely un-guarded while the UI shows two invocations and only one of them can fail the job. Today's state is not "tests skipped"; it is "tests run, but not by the step's declared interpreter, and the declared failure is silenced". |
| Fix in this PR | Step becomes `- name: Regression tests` / `run: python -m pytest tests/ -q`, which is the interpreter CI actually installs `requirements-dev.txt` into (pinned exactly: `pytest==9.1.1`, `ruff==0.16.9`, `mypy==2.3.1`, `yamllint==1.38.0`, and it pulls `requirements.txt`). Naming the step matters independently: the defective step had no `name:`, so its log line was attributed to `test#run`. |
| New guard | `tests/test_ci_gates_are_real.py`, named to match its fleet sibling in `jolarca-hermes-agents`, five tests: no `\|\|` in any run step; no `continue-on-error` at step **or job** level; no `.venv/bin/` reference in a workflow that never builds one; the pytest step must exist and be named; and a non-vacuity test asserting the parser really sees 15+ run steps including `compliance-scan.yml`. Mutation-proved: reintroducing the exact old step produced `3 failed, 2 passed`, and restoring it left the file byte-identical (sha256 `4da4085caf4d8882` before and after). |
| Deliberately broader than the sibling | The hermes module matches OR-true (`\|\|` followed by `true`). That regex does **not** match this defect, whose right-hand side is a second real invocation -- the variant that can mask a genuine red while printing plausible test output. So this module forbids any `\|\|` inside a gate step. Cost: a legitimate shell conditional containing `\|\|` would also fail here and must be argued for in that file. Accepted, because ambiguity inside a gate step is exactly where this class hides. |
| Not verified | Whether the job-level `continue-on-error` clause has ever bitten: measured zero occurrences, so that clause is currently a ratchet, not a bug report. Whether a `.venv` exists on any other runner image -- irrelevant here, since the path is created by neither the workflow nor the checkout. |
| Comment correction (2026-10-05) | The fix shipped a comment reading `# Guarded by tests/test_ci_steps_are_real.py`, but the module had already been renamed to `tests/test_ci_gates_are_real.py` before the commit was made, so the pointer was dead on arrival at `compliance-scan.yml:89`. Nothing caught it -- the test suite passes whatever a comment claims. Corrected in `jolarca-control#40`, which also adds the rule that catches it: every `tests/…py` or `scripts/…` path cited inside a workflow must exist, with its own non-vacuity assertion that the scan found references at all. Observed red first (`1 failed, 5 passed`, naming the line), green after. A guard's own documentation is subject to the same standard it enforces. |
| Decision owner | Operator: merge. Nothing here needs a policy choice; the guard and the fix are one commit. |
| Related | D-22 (a control that cannot fail is unverified), D-23 (a swallowed status must never read as a pass), D-29 (an undeclared or unavailable tool makes a gate unreproducible), D-40 (declared versus enforced -- here the green is neither), D-49 (same session, same lesson: verify which command actually ran). Deliberately NOT citing D-44/D-45/D-46: those headings exist only on unmerged branches, and referencing them here would repeat the dangling-citation defect D-47 was caught creating. |


### D-51 · `actions/checkout` was pinned to v5.0.0 under a `# v4.3.0` comment, and the bump carried that false label onto v7.0.1 — **labels fixed in #34 (pending merge); offline detection added here; live resolution still unbuilt**

|  |  |
|---|---|
| Evidence | Resolved against actions/checkout's own tag list, read from the API rather than typed: `v7.0.1` -> `3d3c42e5aac5…`, `v5.0.0` -> `08c6903cd8c0…`, `v4.3.0` -> `08eba0b27e82…`. Eleven lines across five of this repo's workflows pin `08c6903cd8c0…` with the comment `# v4.3.0` -- the object is **v5.0.0**, so the comment has been false on main the whole time. jolarca-control#34 replaced the SHA with `3d3c42e5aac5…` (v7.0.1) and left all eleven `# v4.3.0` labels in place, while `apply.yml:53`, pinning that same commit, read `# v7.0.1`: one commit, two version claims, in one repository at the same time. The identical mislabel exists at `jolarca-dr/.github/workflows/ci.yml:50` and `:66` (2 lines, read directly from the file). |
| Why it matters | AGENTS.md §5 requires "a full commit SHA with a `# vX.Y.Z` comment", and the comment is the half a human or an auditor actually reads. A SHA that exists but is described as a different release is a subtler failure than a tag ref: the discipline looks satisfied in review, the runner executes what the SHA says, and anyone tracing provenance -- which checkout ran when this protection was applied -- is handed a release that never ran. D-43 was the same rule broken by an object that did not exist; this one is worse-looking, because every object involved is real. |
| How it was found | Not by a check -- by a contradiction. Dependabot's title said "from 5.0.0 to 7.0.1" while the files said `# v4.3.0`, and one workflow already disagreed with the other eleven. Settling it required resolving tags inside the action's own repository, which is the procedure D-43 recorded after the wrong-repo SHA pin. |
| Detection added in this PR | `tests/test_action_pin_labels.py`: four offline rules -- every third-party `uses:` is a full 40-char SHA carrying a label; one commit never carries two labels; one label never points at two commits; and a non-vacuity rule requiring the scan to see 15+ refs including `actions/checkout`. Proved against history rather than asserted: run against dependabot's pre-fix commit `5298819` it reports `1 failed, 3 passed` and names all twelve lines; against main and against the corrected branch `e052241` it reports `4 passed`. |
| Stated limit of that guard | It is offline, so it cannot catch a label that is wrong *consistently* -- which is exactly main's condition today, and the test passes there. Catching that needs live tag resolution (`git/ref/tags/{label}`, peeled if annotated, compared to the pinned SHA) in a CI job: a token, the three-valued exit contract used by `check_declared_contexts.py` (0 clean / 1 finding / 2 could-not-verify, and 2 never reads as a pass), and a supplementary-before-required wiring decision. Recorded as unfinished rather than presented as solved. |
| Where the fix actually landed | The eleven false labels were corrected in a maintainer commit on `jolarca-control#34` itself (`e052241`), because that branch is where the pins change; relabelling main's v5.0.0 lines from a separate PR would collide with the bump on the same eleven lines. Consequence: #34 is now simultaneously the version bump and the provenance fix, and main's labels only become true when it merges. |
| Open | 1. `jolarca-dr`'s two lines are unfixed -- another repository, no dependabot coverage, and this repo's test cannot guard it. 2. Whether the live-resolution check is built, and as a scheduled job or a required context. 3. Fleet exposure was scanned only for this SHA/label pair; no other repo's labels have been resolved against their actions' tags. |
| Decision owner | Operator: merge #34 (bump + truthful labels) and this PR (detection + record), then decide on live resolution and the jolarca-dr correction. |
| Related | D-43 (same §5 rule; fabricated SHA and `@master` floats), D-22 (a detection no pipeline runs is folklore -- why the guard ships with the finding rather than after it), D-49 (a version claim must be measured on the engine that runs, not read off a label), D-50 (this session's shared theme: a green that does not mean what it appears to). |
## 2026-10-04 — Declared repo settings vs live API, and the shared CI base's failure modes

D-43 part 1 (enforce the existing Actions SHA rule) was executed in `jolarca-identity#2`,
`jolarca-vendor#2` and `jolarca-dev/.github#4`. D-43 parts 2 and 3 (the pre-commit `rev:` decision and
registering `.github`) remain open operator decisions. The two findings below came out of doing that work.

### D-44 · `repos/*.yml` settings for identity and vendor do not match GitHub reality — **OPEN, operator decision**

|  |  |
|---|---|
| Evidence — settings | `repos/jolarca-identity.yml` and `repos/jolarca-vendor.yml` were compared against `GET /repos/jolarca-dev/<repo>` on 2026-10-04. The drift is identical in both repos: `allow_merge_commit` declared false, actual **true**; `allow_rebase_merge` declared false, actual **true**; `delete_branch_on_merge` declared true, actual **false**; `has_projects` declared false, actual **true**. Matching: `web_commit_signoff_required`, `has_issues`, `has_wiki`, `archived`, `is_template`. |
| Evidence — protection, identity | Legacy branch protection exists (`GET .../protection` HTTP 200) but `required_status_checks` is **null**, while `repos/jolarca-identity.yml` declares `strict: true` with `contexts: [ci, security, lint]`. Worse: none of those three names is producible. Identity's two jobs report as `shellcheck` and `gitleaks (full history)` (GitHub names a check after the job's `name:`), so applying the declaration **as written** would require three contexts that no workflow can ever report, and every future PR there would be permanently unmergeable. |

| Evidence — protection, vendor and the ruleset blind spot | Vendor's legacy endpoint returns **HTTP 404 `Branch not protected`**, which an earlier draft of this row mis-read as 'no protection at all'. That was wrong and is corrected here: `GET /branches/main` reports `protected=true`, because protection is delivered by an **active repo ruleset** `protect-main` (created 2026-09-28, `bypass_actors: []`) which the legacy endpoint does not describe. Its rules: deletion blocked, non-fast-forward blocked, required linear history, `pull_request` with `required_approving_review_count: 0`, and `required_status_checks` with **`required_status_checks: []` and `strict_required_status_checks_policy: false`** -- so zero contexts are required and the declared `lint` is not enforced. The same rulesets exist on `jolarca-consent` (three rules, no PR or status-check rule at all) and `jolarca-dr` (which DOES require `[lint, gitleaks]`, strict false). Org-wide ruleset listing is unavailable on this plan (HTTP 403, 'Upgrade to GitHub Team'), so per-repo rulesets are the only visible layer. |
| Evidence — update monitoring | Neither repo declares `.github/dependabot.yml` (absent in identity and vendor; present in `jolarca`, `jolarca-infrastructure`, `jolarca-data`). Both repos' action refs were SHA-pinned today, so they are now **frozen with nothing proposing updates**. |
| Impact | Three things, differently weighted than first drafted. (a) Unchanged: four settings per repo are wrong in the declared source of truth, so any attestation citing `repos/*.yml` is inaccurate -- D-40's class at settings scale. (b) Restated: vendor is NOT unguarded -- force-push and deletion are blocked by its ruleset -- but it requires **no status checks and runs strict=false**, so a PR can merge there with its `lint` job red or never run, while `repos/jolarca-vendor.yml` implies `lint` is required. The accurate defect is 'protection without enforcement', not 'no protection'. (c) Unchanged: pinned-plus-unmonitored is silent aging. (d) NEW and arguably the most consequential: `scripts/drift_detect.py` reads only the legacy protection endpoint, so it cannot see rulesets at all. It classifies vendor, consent and dr as `plan_limited` with the message 'has branch protection but attributes are unreadable (GitHub Free plan -- private repos)', which is wrong twice over -- the repos are public, and the 404 is a ruleset/legacy mismatch, not a plan limit. It then exits 0 with **"NO DRIFT -- branch protection and org baseline verified"**. A detector that reports verification while blind to the layer that actually holds the controls is worse than one that admits it cannot see. |
| Why not fixed here | Every remedy is either a Terraform apply -- blocked: HCP backend needs `terraform init` with the operator's cloud token and then a human-read plan, and AGENTS.md §5 forbids agent apply and any out-of-band `gh api -X PATCH` of repo settings -- or an edit to the evidence-hashed `repos/*.yml` that would then disagree with live reality until applied. This is a decision record, not a repo edit. |
| Proposed fix, in order | (1) **Fix the detector first**: teach `drift_detect.py` to read `GET /repos/{repo}/rulesets` and each ruleset's `required_status_checks`, and split three outcomes it currently merges: genuinely unprotected, protected-but-requires-no-checks, and unreadable-attributes. A `plan_limited` label must require an actual 403, not a 404 against a public repo, and the summary must not say 'verified' while any repo sits in an unevaluated bucket. (2) **Fix identity's declaration before applying anything**, because applying it as written bricks merges: either declare the contexts identity can report (`shellcheck`, `gitleaks (full history)`) or give its jobs stable names (`lint`, `secret-scan`) and declare those. Do not choose by editing the declaration alone -- a context name that renames itself later silently un-requireds the check. (3) Populate vendor's ruleset `required_status_checks` with the job it runs (`lint`) and decide strict-mode explicitly; consent and dr need the same pass. (4) Exemption hygiene: `branch_protection_baseline_exempt` currently lets identity pass while its rule requires nothing. The comment in `policy/repo-defaults.yml` says exemption 'can never be used to leave a repo unprotected' -- hold that to its word by still requiring `minimum_required_contexts >= 1` for exempt repos. (5) Then, and only then, the operator's `terraform init` / `plan` / `apply`. (6) Add the two missing `dependabot.yml` files. |
| Decision owner | Operator. |
| Self-correction | The first draft of this row, written from the legacy endpoint alone, asserted vendor had no branch protection and that PRs there merge with no checks and force-push possible. Both were false; `protected=true` plus an active ruleset contradicted them. Caught while preparing the fix, before the row merged. |
| Detector fix, delivered in #28 | `check_branch_protection()` now consults `GET /repos/{repo}/rulesets` when the legacy endpoint returns 404, keeps 403 as the genuine plan-limited case, files an active ruleset that requires fewer than `minimum_required_contexts` as `weakened` (or `hollow_rules` when the repo is exempt -- informational, because making exemption fatal is a policy decision, not a bug fix), and stops the summary claiming `verified` while any repo sits in an unevaluated bucket. |
| Detector fix, live outcome | Re-run against the org after the change: `weakened` = jolarca-consent and jolarca-vendor (`ruleset requires 0 status check(s), need >= 1` plus `strict_required_status_checks_policy=false`); `ruleset_protected` = jolarca-dr; `plan_limited` = empty, confirming the whole bucket was this one misdiagnosis; `unverifiable` = empty. `hollow_rules` = the seven exempt repos (.github, jolarca-compliance, jolarca-data, jolarca-identity, jolarca-infrastructure, jolarca-legal, jolarca-security) -- so identity's require-nothing rule is now visible instead of exempt-and-silent. Exit code became 1 with `drift_detected: true`, where before the same tree reported no drift. |
| Consequence for the apply path | `apply.yml` runs `drift_detect.py` as its `Post-apply drift detection` step, whose own comment states a red job there means `applied but not verified`. After #28 the next apply run goes RED on consent and vendor until those rulesets require a status check. That is the finding surfacing, not a malfunction -- but it should not be a surprise, and the remedy is operator action outside this repo. |
| Related | D-02 (no applied state), D-40 (declared gate vs enforcement), D-42 (AGENTS.md §8 stale), D-43 (fleet pin discipline), D-45 (same blind-spot class in the shared CI base). |

### D-45 · the shared CI base contains 11 steps that cannot fail, a fabricated SHA PR #1 missed, and an action major that no longer exists — **OPEN, one fix in review**

|  |  |
|---|---|
| Evidence — cannot fail | In `jolarca-dev/.github`: 11 steps carry `continue-on-error: true` -- 10 in `.github/workflows/security-scan.yml` and the gitleaks step at `.github/workflows/ci-base.yml:112`. A secret-scanning step that cannot fail is the exact class this fleet bans elsewhere (`jolarca-hermes-agents` `tests/test_ci_gates_are_real.py`; ADR-0004 R3's inverse: a job that cannot fail manufactures assurance). |
| Evidence — fabricated SHA, half fixed | PR #1 (`77011f8`, 2026-09-18) replaced `gitleaks/gitleaks-action@4f9a10a3b6e2a7a1b5d6b5a5e5e5e5e5e5e5e5e5` with the real `e6dab246340401bf53eec993b8f05aebe80ac636 # v2.3.4` **in security-scan.yml only**; the identical fabricated line is still at `ci-base.yml:109`. Measured with a negative control in one call shape: old SHA `GET git/commits/...` returns HTTP 404, new SHA returns HTTP 200. `jolarca-dev/.github#4` removes the last occurrence. |
| Evidence — unresolvable major | `github/codeql-action/upload-sarif@v3` (security-scan.yml:97 and :183): `git/ref/tags/v3` and `git/ref/heads/v3` both return HTTP 404 while the action's current tags are v4.x. There is no commit to pin, so these steps cannot resolve as written and any change here is a version upgrade, not a pin. Left untouched deliberately and recorded instead. |
| Evidence — untagged trunk | PR #2 (`7fdbd5f`) pinned `trivy-action` to `d2a0b60797ff03db6132bd4e2b293f9b37081297` with the comment `# master`. That commit carries **no release tag** (latest release v0.36.0 sits on `ed142fd0`; master's tip has since moved to `c03d123c`). `checkov-action`'s `444c9db6fa75e2d9c19ebf1fde7322089be9009e` is genuinely tagged v12.3125.0 but was also commented `# master`. AGENTS.md §5 asks for a `# vX.Y.Z` comment; "master" is not a version. PR #4 corrects both comments without changing any SHA. |
| Evidence — no signal possible | All three shared workflows are `on: workflow_call` only; no allow-listed repo references a `jolarca-dev/` reusable workflow; and PRs in `.github` report **zero checks** (protection exists with `contexts = []`, `required_approving_review_count = 0`). Changes here can never be validated by a pipeline, so every claim about them must be static-analysis-plus-API proof, and "the pipeline is green" is not available as evidence. |
| Impact | Latent but severe. If any repo ever calls these workflows it inherits a secret scan that always passes, a step that cannot resolve, and scanners pinned to untagged trunk. This is D-43's mechanism -- declared, never executed -- with the concrete failure modes enumerated. |
| Proposed fix | (1) Land `.github#4`. (2) Decide the `continue-on-error` policy per step; removing it from the gitleaks step makes secret scanning real, which will start failing PRs -- that is the intent, and it should be a stated decision rather than a surprise. (3) Replace `codeql-action/upload-sarif@v3` with a current v4 commit SHA in its own PR. (4) Do NOT register `.github` in `repos/`: measurement shows it is the designated HEALTH_REPO (excluded from allow-list comparison by design in `scripts/drift_detect.py`, managed by `health-repo.tf`, with documented exceptions in `validate_repos.py` and `check_fleet_separation.sh`). The actionable gap is that `health-repo.tf` declares no `github_branch_protection` resource while its live rule requires zero contexts -- see D-48.
| Decision owner | Operator. Parts (2) and (3) are behaviour changes, not pinning. |
| Not verified | Whether an org-level setting wires these workflows outside repo files; whether `gitleaks-action` can run at all on an org-owned repo without `GITLEAKS_LICENSE` -- prior evidence says it fails every run -- so even a correctly pinned step may be non-functional. Verify before treating (1) as making the secret control real. |
| Related | D-43 (pin discipline, the `rev:` question, `.github` unregistered), D-40, D-44. |

### D-46 · Active branch-protection rulesets exist outside the declared source of truth, and the Terraform baseline asserts none exist — **OPEN, decision required**

|  |  |
|---|---|
| Evidence | `GET /repos/jolarca-dev/{jolarca-vendor,jolarca-consent,jolarca-dr}/rulesets` each returns one ruleset `protect-main`, `enforcement: active`, `bypass_actors: []`, `created_at` 2026-09-28T22:55 (+03:00). All three repos are public, `GET /branches/main` reports `protected=true`, and the legacy `GET /branches/main/protection` returns HTTP 404 -- which is why D-44 first mis-read vendor as unprotected. Org-level listing `GET /orgs/jolarca-dev/rulesets` returns HTTP 403 "Upgrade to GitHub Team to enable this feature", so there is no single place to audit them. |
| Evidence — the contradiction | `branch-protection.tf` stated "The 2026-09-17 delivery-chain audit verified NO rulesets exist org-wide." The rulesets were created 2026-09-28, eleven days later. The claim is not merely stale, it is the opposite of current reality, and it is the documented reason no ruleset resource exists in this configuration. |
| Evidence — what they enforce | vendor: deletion block, non-fast-forward, required linear history, `pull_request` with 0 approvals, and `required_status_checks` with an EMPTY context list and `strict_required_status_checks_policy=false`. consent: the same minus any PR or status-check rule. dr: same shape but genuinely requires `[lint, gitleaks]`. So two of three require no checks at all while their allow-list entries declare contexts. |
| Impact | Enforcement that no declared source of truth describes. `terraform apply` neither creates, repairs nor destroys these rulesets, so the fleet's protection posture is partly hand-configured; the Terraform comment tells a reader otherwise; and before #28 the detector could not see the layer at all, reporting "NO DRIFT ... branch protection ... verified" for exactly these repos. An auditor asked "is main protected?" would get a true answer ("yes") for the wrong reason (not because the control plane manages it). |
| Why not fixed here | Two decisions, both operator-level. Adding `github_repository_ruleset` resources means importing live objects into state -- AGENTS.md §5 forbids agent import and apply, and §4 classes both `*.tf` and `repos/**` as high blast radius needing a human-read plan. Deleting or editing the rulesets by hand is the same out-of-band pattern this register exists to condemn (D-34, D-35, D-36, D-38 were all out-of-band mutations). |
| Proposed fix | Choose one, explicitly: (A) bring rulesets under Terraform -- add the resource, `terraform import` the three objects, then let drift detection compare them; or (B) declare rulesets unsupported and move required-status-check enforcement entirely into legacy `github_branch_protection`, accepting that GitHub applies the union of both layers so the ruleset can still block what the declaration allows. Either way, keep #28's ruleset read in place: it is the only thing that currently makes this layer visible. Also worth deciding: who created these on 2026-09-28, since no commit, runbook step or finding in this repo accounts for them. |
| Decision owner | Operator. |
| Related | D-44 (declared-vs-live protection and settings; fixed for identity in #29), D-43 (pin discipline), D-07 and RB-04 (the unfinished ruleset strategy this defers to), D-23 (never report unverified as verified), D-34 to D-38 (out-of-band mutation precedent). |

## 2026-10-06 — D-31 remediation decision: option (a) attempted and reverted; option (b) chosen

### D-52 · Privating a governed fleet repo blinds the control plane — D-31 must be remediated by content removal, not visibility — **D-31 remains OPEN/blocking**

|  |  |
|---|---|
| Why this row exists | D-31 recommended **option (a): flip the four repos private** ("available immediately and reversible"). On 2026-10-06 (a) was **executed** on the two sharpest repos and **reverted** the same day once it proved unsafe for this control plane. This row corrects the register's own recommendation against measured evidence, and resolves the D-31↔D-37 contradiction ("OPEN" vs "superseded"). |
| Live re-enumeration (same day) | Recursive `GET /repos/jolarca-dev/<r>/git/trees/main?recursive=1` returned `TRUNC=false` (complete) with all four repos `private:false`. Confirmed populated regulated records: `jolarca-compliance` `ropa/master-register.csv` (1150 B), `ropa/by-system/*`, `dpia/002-ai-processing/dpia.md` (4567 B), `risk-register/register.md` (2767 B), `vendor-assessments/*/assessment.md` (anthropic 9935 B, openai 9926 B, google-cloud 7198 B); `jolarca-infrastructure` `security/deviation-register.md` (4961 B) + payment-boundary docs. `jolarca-legal` `contracts/vendors/*` are `.gitkeep`-only (no countersigned agreements leaked). Sizes/paths only — record bodies were deliberately not opened. |
| What was tried | `gh api -X PATCH repos/jolarca-dev/{jolarca-compliance,jolarca-infrastructure} -F private=true`, each confirmed by independent GET re-read `private:true, visibility:private` (a PATCH 2xx does not prove the field changed). The live read-exposure was thereby temporarily closed. |
| Why it backfired — the reusable constraint | The required context **Context Parity** runs `scripts/check_declared_contexts.py`, which lists each fleet repo's `.github/workflows` via the workflow `GITHUB_TOKEN` scoped to `jolarca-control` (that script, L72). The token reads **public** sibling repos but **not private** ones; a private repo lands in `unverifiable[]` and the script exits **2** ("could not verify", never a pass — D-23). Proven on the SAME commit both ways: CI Context Parity → **exit 2, required context red, `mergeStateStatus: UNSTABLE`**; a local run under the operator `gh` token (which sees private) → `unverifiable: []`, exit 1. Discriminator is token scope, not a code bug. **Conclusion: on the GitHub Free plan you cannot both private a governed fleet repo and keep the control plane able to verify it. D-31's option (a) is therefore unsound and withdrawn.** |
| Reverted | Both repos flipped back to `visibility: public` (independent re-read `private:false`). The private-flip PR was **closed unmerged**, so `main` never declared private — no half-applied record, no drift. The revert also restores Free-plan branch protection / secret scanning / push protection on both (undoing the D-33 loss that privating caused). |
| D-31 status | **Still S1, BLOCKING, OPEN.** Reverting (a) does not resolve it; the records are world-readable again. Remediation = **option (b)**. |
| Option (b) plan (owner-executed, cross-repo) | **(1) Stage** the records into an access-controlled destination *before* deleting — recommended: encrypted non-git store (age + object storage, matching the fleet's WORM/backup conventions); for `jolarca-infrastructure` a split keeps publishable IaC public and ships only `deviation-register.md`. The GDPR Art. 30 RoPA must stay *maintained and available throughout* — no custody gap. **(2) Verify** the destination holds intact copies. **(3) Remove** from HEAD in `jolarca-compliance` / `jolarca-infrastructure`. **(4) Purge history** — HEAD-delete is insufficient: the blobs persist in every past commit of a *public* repo, so remediation needs `git filter-repo`/BFG + force-push + a **GitHub Support request** to detach/purge cached and network copies and re-contact forks. **(5) Re-classify** the two repos honestly (`internal`→`confidential`) once only publishable content remains. |
| Parallel duty (owner) | **GDPR Art. 32/33**: the disclosure already happened (public since at least the 2026-09-25 enumeration). Run the security-of-processing assessment and the notifiability determination in `jolarca-compliance` regardless of cleanup timing. |
| Blast radius / who executes | The actual remediation is **cross-repo** (`jolarca-compliance`, `jolarca-infrastructure`) and includes an **irreversible history rewrite** + support purge — AGENTS.md §5 reserves those to the operator. This repo's contribution is the accurate register + the enumerated artifact inventory as the runbook seed. No live mutation or cross-repo change is executed from here. |
| Verified vs assumed | **Verified:** privating breaks Context Parity (CI exit 2 vs local exit 1, same commit); the records are present/public/populated (recursive tree, `TRUNC=false`). **Assumed:** that an age/encrypted destination exists or is provisionable; that the file *bodies* are confidential as-written (paths + sizes confirmed, bodies not read — the classification call is the owner's); that a history rewrite will not break downstream consumers of those repos. |
| Related | D-31 (the finding this remediates — its option (a) is withdrawn here), D-37 (its "D-31 superseded" claim corrected), D-33 (private repos unprotected — compounds why privating is not a fix), D-23 (exit 2 is never a pass), D-02 (apply blocked, hence out-of-band was the only live channel), D-34/D-35/D-36/D-38/D-39 (recorded out-of-band mutation precedent). |
