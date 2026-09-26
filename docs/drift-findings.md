# Drift & Findings Register — jolarca-dev control plane

**Created:** 2026-09-25
**Last verified:** 2026-09-26 (D-33 and the dated corrections to D-04 / D-08)
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

### D-02 · Live Terraform state is single-copy with no remote backend
| | |
|---|---|
| Evidence | `jolarca-infrastructure/.gitignore` lines 7–8 exclude `*.tfstate` / `*.tfstate.*`; `git ls-files \| grep tfstate` returns nothing. `terraform/environments/production/main.tf` has **no backend block** (ADR-0003 migration never completed; `vars.TF_REMOTE_STATE` is not `true`). On-disk: `terraform.tfstate` (24 520 B, Aug 31 23:15) + `terraform.tfstate.backup` — both on this host only. |
| Impact | The sole record of what Terraform believes it owns for six PCI-DSS-scoped repositories exists as one file on one machine. Host loss = permanent inability to reason about ownership; the only recovery path is `terraform import` of every resource by hand. |
| Required before any apply | Copy the state off-host **and** verify the copy, then complete the remote-backend migration (`docs/runbooks/workload-identity-federation.md`). Runbook step 0. |

### D-13 · Dual-ownership window between the two roots
| | |
|---|---|
| Evidence | `module.github_org.*` is live in `jolarca-infrastructure` production state. `jolarca-control/{repositories,branch-protection,health-repo}.tf` now declares the same real resources. |
| Impact | Two Terraform roots claiming the same GitHub objects. An apply from either side can undo the other; a `destroy` from the old root deletes real repositories. |
| Control in place | `lifecycle { prevent_destroy = true }` on every `github_repository`; `apply.yml` refuses plans containing destroy/replace; `vars.STATE_MIGRATION_COMPLETE` gate blocks apply entirely until the runbook completes. |
| Required | Execute `docs/state-migration-runbook.md` — the old root's GitHub section must be retired in the **same** change window that this one takes ownership. |

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

### D-18 · Org-wide two-factor authentication is NOT enforced — **BLOCKING, MANUAL ACTION REQUIRED**
| | |
|---|---|
| Evidence | `gh api orgs/jolarca-dev` → `"two_factor_requirement_enabled": false` (2026-09-25). |
| Impact | Any member account with a password-only login can be credential-stuffed into an organization that owns PCI-DSS-scoped repositories and holds a Terraform token capable of rewriting branch protection fleet-wide. PCI-DSS Req 8.3.1 requires multi-factor authentication for all access into the CDE; ISO 27001 A.5.17 requires authentication per policy; SOC 2 CC6.1. |
| Why it matters more here | `docs/threat-model.md` T-02 previously asserted "2FA required" as a mitigation. That assertion was inherited from `jol-control` and was never true of this org. The threat model has been corrected to show the gap. |
| Required | Enable org-enforced 2FA **manually in the GitHub UI** before the `TF_GITHUB_TOKEN` secret is created. This setting cannot be managed via the API (security feature). Navigate to: **Organization settings → Authentication security → Require two-factor authentication**. Note: this will immediately require all current members to have 2FA enabled or they will be removed from the org. |

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
| Evidence — Terraform manages none | `terraform.tfvars` sets `enable_branch_protection = false` (the `variables.tf` default is `true`), so `local.protected_repos` resolves to an empty map and `github_branch_protection.health` has `count = 0`. Local state (serial 128, TF 1.16.1) holds 7 `github_repository` and 7 `github_repository_vulnerability_alerts` instances and **zero `github_branch_protection`**. |
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
