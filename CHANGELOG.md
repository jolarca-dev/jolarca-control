# Changelog

All notable changes to `jolarca-control` are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

This repository is the governance control plane for the `jolarca-dev`
marketplace organization. Changes here can alter branch protection, visibility
and scanning settings on six PCI-DSS-scoped repositories, so the changelog is
part of the SOC 2 CC8.1 / ISO 27001 A.8.32 audit trail and is not optional.

## [Unreleased]

### Added — 2026-09-25

Initial control plane, extracted from
[`jolarca-infrastructure`](https://github.com/jolarca-dev/jolarca-infrastructure),
where GitHub-organization governance had accumulated inside an infrastructure
repository.

**Allow-list and policy**

- `repos/*.yml` — six repository definitions (`jolarca`, `jolarca-control`,
  `jolarca-compliance`, `jolarca-data`, `jolarca-infrastructure`,
  `jolarca-legal`). Every setting was transcribed from live `gh api` output on
  2026-09-25, not from the stale Terraform state snapshot of 2026-08-31.
- `policy/repo-defaults.yml` — enforced baseline, with the solo-era deviations
  recorded in the file rather than hidden in Terraform comments.
- `policy/compliance-gates.yml` — ten gates, per-tier enforcement matrix, and
  an `exceptions.active` register carrying D-04 and D-05 with named
  compensating controls.

**Terraform**

- `repositories.tf` — fleet repositories driven by the allow-list, with an
  ADR-0004 R1/R3 `precondition` that rejects any non-`jolarca*` name at plan
  time, and `lifecycle { prevent_destroy = true }` on every repository.
- `branch-protection.tf` — one resource for the fleet and one for the health
  repo, encoding verified live values.
- `health-repo.tf` — the org `.github` repository and its inherited
  `SECURITY.md`, carried over from the old `github-health-repo.tf`. Kept out of
  the allow-list because its name is not a valid allow-list filename and its
  policy is deliberately different.
- `org-settings.tf`, `outputs.tf`, `variables.tf`, `main.tf`,
  `terraform.tfvars`.

**Automation**

- `scripts/validate_repos.py` — adds the ADR-0004 naming rule and a
  data-classification ↔ visibility coherence rule (the check that makes D-01
  visible); reads the signed-commit expectation from policy instead of
  hardcoding it.
- `scripts/compliance_check.py` — seven checks including fleet separation and
  merge policy; surfaces the D-04 deviation as information rather than failing
  on it.
- `scripts/drift_detect.py` — now diffs visibility, wiki and archive state as
  well as fleet membership, against `jolarca-dev`.
- `scripts/check_fleet_separation.sh` — ported and rewritten to parse
  `repos/*.yml` instead of a Terraform variable default; adds R3 (mission-repo
  intrusion) and a time-boxed `ALLOW_MISSING` bootstrap exemption.
- `scripts/org_delivery_audit.sh` — ported; `jolarca-control` added to the
  audited fleet.
- Four workflows (`plan`, `apply`, `compliance-scan`, `fleet-separation-guard`),
  every action pinned to a full commit SHA.

**Documentation**

- `docs/drift-findings.md` — 22 findings, each with the command that verifies
  it.
- `docs/state-migration-runbook.md` — the gated procedure that makes this
  repository authoritative.
- `docs/architecture.md`, `docs/threat-model.md`, `docs/change-management.md`,
  `docs/data-classification.md`, `docs/runbooks.md` (RB-01 … RB-07).
- `docs/adr/0004-mission-marketplace-separation.md`,
  `docs/runbooks/github-token-rotation.md`,
  `docs/runbooks/workload-identity-federation.md`,
  `docs/security/{isolation-model,key-custody}.md` — carried from
  `jolarca-infrastructure`.
- `audit/pci-dss-checklist.yml` — new; PCI-DSS 4.0 applies to every repository
  in this fleet, unlike the mission platform.

### Added — 2026-10-08 (A-08: mandatory SAST gate made real)

The `sast` gate was declared `enforcement: mandatory` in
`policy/compliance-gates.yml` but nothing ran it — a D-22-class control
(AGENTS.md §7). Closed in two PRs (workflow, then gate wiring) because
`check_declared_contexts.py` reads live `main` and a required context cannot be
declared before the workflow that emits it is merged.

- `.github/workflows/sast.yml` — Semgrep OSS (`p/default`+`p/python`), Bandit
  (`-ll -ii`, scope widened from `scripts/` to `scripts/ tests/`) and a Trivy
  config scan over the Terraform/workflow/policy YAML. All actions SHA-pinned,
  `permissions: contents: read`, `pull_request` (not `pull_request_target`),
  **no GHAS/CodeQL dependency** (CodeQL is unavailable on the Free plan, so the
  `codeql-analysis` gate ID could never have been satisfied here).
- `scripts/compliance_check.py` — `check_sast_gate_wiring()` fails when a repo
  is in a tier where `sast` is mandatory but does not declare
  `SAST (semgrep)` as a required status check.
- `.trivyignore.yaml` — accepted Trivy misconfigurations `GIT-0004` (→ D-05,
  expires 2026-12-24) and `GIT-0001` (→ fleet-public-2026-10, expires
  2026-12-29), each naming its exception ID and expiry.
- `tests/test_compliance_check.py` — positive **and** negative controls for the
  wiring check (AGENTS.md §7 non-vacuity).
- `docs/security/sast-mandatory-gate-2026-10-08.md` — triage of every first-run
  finding plus the throwaway negative-control proof (run `37699506676`:
  deliberate `shell=True`/`eval` turned **only** `SAST (semgrep)` and
  `SAST (bandit)` red; all other checks stayed green).

### Fixed — 2026-10-15 (D-61 → D-64: the apply path was measured, then made honest)

Executing "merge only after reading what the apply will do" turned up four
findings, all fixed in-repo rather than only registered:

- **D-61 · the pre-apply refusal gate had a blind spot.** A *refreshed* plan from
  this root renders `3 to add, 25 to change, 0 to destroy` and
  `scripts/check_plan_safety.sh` exited **0** on it — the refusal seen earlier
  came only from `-refresh=false` carrying stale `private` values, i.e. a gate
  firing for the wrong reason. The script now also refuses branch-protection
  **creates**, any change to 13 protection attributes (either direction — a
  tightening can deadlock a merge as well as a weakening can expose the fleet,
  and Terraform renders both identically), and secret-scanning / push-protection
  / Dependabot / vulnerability-alerts **disables**. Enabling stays allowed.
  Verified three ways: 16 fixtures (4 new refusals + 2 non-vacuity controls), the
  real refreshed plan text which now exits **1** naming the three creates, and
  `policy/compliance-gates.yml` `plan_review` updated with the new
  `blocked_actions` plus an `operator_path` and no skip flag.
- **D-64 · D-56's real cause was a workflow bug, not a credential.** `plan.yml`
  ran `terraform init -backend=false` against a `cloud {}` root, so every
  PR-time plan aborted with `HCP Terraform initialization required` — reproduced
  byte-for-byte on a clean tree and fixed. Consequence stated, not buried: the
  plan now renders, so "Validate & Plan" fails at the refusal step until runbook
  step 6 is reconciled. That is the intended posture — a readable refusal
  replaces a broken automation.
- **D-62 · the policy baseline named a required context that nothing reports**
  ("Fleet Separation Guard"; the job is "Fleet Separation (ADR-0004)" and it is
  path-filtered) **and omitted a real one** (`SAST (semgrep)`). Corrected; no
  script reads that block, so the fix is documentary and the follow-up (point
  `check_declared_contexts.py` at it, or delete it) is an owner decision.
- **D-63 · three documents described a closed apply gate and a thin state
  inventory.** Measured: `STATE_MIGRATION_COMPLETE` = `"true"` (gate OPEN),
  workspace `resource-count: 48` / `execution-mode: local`, and **14**
  `github_branch_protection` addresses are in state — not "only
  `jolarca-hermes-agents`" as AGENTS.md §8 claimed. Corrected across AGENTS.md
  §2/§8, ADR-0006, the runbook status line, the repo-request template, the
  `make apply` message, and the SOC 2 / PCI-DSS checklists (CC8.1-03 → gap/D-56,
  CC8.1-04 → gap/D-58 with the environment's measured empty
  `protection_rules`, CC8.1-05 → implemented, 6.5.3-01 → partial). Dated
  historical readings (the 2026-10-12 `resource-count: 35`) were annotated, not
  rewritten. One half stays open and is recorded as such: `…/branches/main/protection`
  now returns **HTTP 404** while `.protected = true` and repo rulesets are `[]`;
  the cause was not established in two probe attempts, so nobody should read
  that 404 as "unprotected".
- `files/SECURITY.md` was re-mirrored to the live `.github` copy (byte-identical,
  verified by re-read) — the divergence was created by editing the reference copy
  in the first half of this change, which is precisely the D-15 trap.
- `prevent_destroy` was observed working, not assumed: a probe tree missing
  `repos/*.yml` (so every instance plans for deletion) aborted with
  `Error: Instance cannot be destroyed` instead of producing a destroy plan.

### Fixed — 2026-10-15 (fourth batch: the step-6 packet turned into two declaration repairs, D-65/D-66)

Working the packet's WEAKEN rows rather than just listing them found two
declarations that had drifted far enough that an apply would have enacted the
drift as a control removal (D-65):

- **`restrict_pushes` was declared nowhere but lived everywhere.** Policy says
  `true`, eleven live rules have the block, `branch-protection.tf` contained the
  string zero times — so the plan deleted the push restriction from all eleven
  rules (11 of 25 changes). Now declared via a `dynamic` block over
  `local.restrict_pushes_rules`, keyed **per repository** from
  `terraform state show`: `jolarca-payments` allows `/JourneyOfLife`, the other ten
  allow nobody. The first draft used a blanket `push_allowances = []`, which would
  have removed the operator's own allowance — i.e. fixing one regression by
  introducing another; re-planning caught it, reading did not.
- **`repos/jolarca.yml` declared 9 of the 12 required contexts** the flagship live
  rule enforces, and all twelve are still produced (verified from
  `jolarca/commits/main/check-runs`) — an apply would have dropped three required
  checks from the application repository in silence.

Measured result: plan went `3 to add, 25 to change` → `3 to add, 20 to change`,
with **zero** `restrict_pushes` lines and zero `frontend-*` removals, while
`check_plan_safety.sh` still exits **1** on the residue (three creates + remaining
attribute drift) — the fix removes weakenings, it does not rubber-stamp the apply.

Two honesty items, both written up rather than buried:

- **D-61's own correction was wrong and is corrected a third time.** The three
  creates do not "add protection": `jolarca-consent`, `-dr` and `-vendor` run an
  **active undeclared `protect-main` ruleset** (D-46), so a create layers a second
  mechanism beside the one in force. One un-run command (`…/rulesets`) was the
  difference — the register's recurring error, asserting absence from a partial
  probe.
- **D-66, opened deliberately instead of closed silently.** Policy demands a push
  restriction that six rules do not have (`jolarca-docs`, `jolarca-hermes-agents`,
  `.github`, and the three ruleset-only repos). Extending the new declaration to
  them would have *added* a control as a side effect of removing a weakening — and
  would start failing `codeowners.tf`'s own `github_repository_file` commits to
  `main`. That belongs in its own reviewed change, so it is recorded as open.
- The packet's "UNRESOLVED" row was also my own parsing artifact: `branch_protection`,
  `compliance_summary` and `protected_repos` are the plan's **Outputs** section, not
  `github_repository` attributes (`state show` confirms), and the row now says so.

Verification: `terraform fmt -check` and `terraform validate` clean ·
`validate_repos.py` 16/16 · refreshed plan 3/20 with the two classes gone ·
`check_plan_safety.sh` exit 1 on the residue · `make lint` ·
`compliance_check.py` pass · evidence re-registered (`repos/jolarca.yml` is hashed)
and `--check` exit 0.

### Fixed — 2026-10-15 (sixth batch: the gate passed the one tightening that deadlocks a repo)

Verifying the merged result on `main` found the plan-safety gate still blind to a class
it was described as refusing. Four of the 20 remaining changes are **added** nested blocks,
`+ required_status_checks { … }` on `jolarca-data`, `-identity`, `-legal`, `-security`; the
refusal pattern matched `[~-]` only, so all four passed silently and the named-line list in
the output proved it (`grep -c github_branch_protection` on the refusal → 0 protection
headers, only `~` attribute lines). The dangerous one is `jolarca-identity`: its declared
contexts are not producible by its workflows (D-44/D-47), so requiring them would have
deadlocked every merge on that repository — exactly the outcome the rule's own comment says
it exists to prevent, defeated by a missing `+`.

- `scripts/check_plan_safety.sh`: marker class widened to `[~+-]` for protection attributes.
- `tests/test_check_plan_safety.sh`: `protection-status-checks-added`, transcribed verbatim
  from `terraform show -no-color` of the live plan. **22/22 cases pass.**
- Re-asserted against the real artifact: the gate now names all four added blocks, identity
  included (previously zero of them).
- D-61 corrected a fifth time, including the sentence in this register that claimed "the gate
  still refuses all of it" — written from the aggregate exit code instead of the named lines.
- This is the third distinct rendering/input defect in one gate: `-` removed blocks, nested
  `status = "enabled" -> "disabled"`, and now `+` added blocks. Every one was found by feeding
  it real output, never by reading the regex.

Verification: plan on `main` `0 to add, 20 to change, 0 to destroy` · gate exit **1** naming 12
lines (4 of them `+ required_status_checks`) · plan-gate fixtures 22/22 · `make lint` · evidence
re-registered and `--check` exit 0. `scripts/**` is not an `apply.yml` trigger path, so this PR
starts no apply.

### Changed — 2026-10-16 (eighth batch: the production apply got a 30-minute wait; two checklists corrected)

- **D-70 · a real, mechanical stop now exists.** `production` environment:
  `wait_timer=30` and `can_admins_bypass=false`, applied by `gh api -X PUT` on the
  owner's instruction and verified by an independent GET re-read
  (`protection_rules: [{"type":"wait_timer","wait_timer":30}]`, `updated_at` moved).
  Explicitly **not** an approval gate: reviews are still 0, no reviewer exists, so
  PCI-DSS Req 6.5.1 change control and D-58 stay open and CC8.1-04 moved only
  gap → `partial`. Two API traps recorded: `-f` sends strings where that endpoint wants
  an integer/boolean (HTTP 422, nothing changed — verified, not assumed), and the
  response's scalar `wait_timer` stays `null` while the live value sits in
  `protection_rules[]`, which is how a "no wait configured" reading can be written into a
  checklist as fact. Environment reviewers were deliberately left untested: the old claim
  that a solo operator cannot self-approve is contradicted by the *Prevent self-review*
  option, and an unsatisfiable reviewer would wedge every deploy.
- **Brake proven, not asserted.** The first trigger-path merge after D-70 (run 38813823199, merge of #76) shows `Production — Apply` in `status: waiting` with **zero started steps** — the wait blocks ahead of "Set up job" — plus a `production` deployment object and an untouched workspace (`resource-count: 48`, unlocked). Recorded in D-70; `main` CI is otherwise all green except `Validate & Plan` (D-56).
- **Cancel path proven too.** Run 38813823199 was cancelled mid-wait with `gh run cancel 38813823199 --force`: conclusion `cancelled`, `steps started: 0`, workspace still 48 resources. The window is therefore usable, not decorative. (`--yes` does not exist; the first attempt errored and cancelled nothing — recorded so the next agent does not repeat it.) Added to D-70 and to AGENTS.md §8.
- Not out-of-band drift: this root declares no `github_environment`
  (`terraform state list | grep -ic environment` → 0), so the write cannot diverge from
  Terraform; recorded as a dated deviation like D-34…D-38.
- **Status prose updated where the control is asserted**, not just here:
  `audit/soc2-checklist.yml` CC8.1-04 (+ summary counts: gap 7→6, new `partial: 1`),
  `audit/pci-dss-checklist.yml` 6.5.3-01, `policy/compliance-gates.yml#plan_review`,
  and a new AGENTS.md §8 bullet telling an agent that an in-progress `Production — Apply`
  run is now normal and that the cancel window is the point.
- **D-71 · the change queue is unreconciled.** 9 open PRs, oldest 2026-09-26; #41, #51 and
  #54 carry files `main` does not have, while #29 and #33 describe defects #75 already
  landed — merging #29 today would revert identity's registry to a 2026-10-04 view.
  Verified per PR with `git cat-file -e origin/main:<path>`, not by reading titles.

Verification: PUT rc 0 + independent GET re-read as above - `yamllint` clean on the three
edited YAML files - `compliance_check.py` `overall_status: pass` - evidence re-registered
(`audit/**` and `policy/**` are hashed) and `--check` exit 0. This PR touches `policy/**`,
so it triggers an apply attempt - which will now **wait ~30 minutes** before its first
step, then fail at the state lock (D-56) with `Terraform Apply` skipped.

### Fixed — 2026-10-15 (seventh batch: walking the 19 found two declarations that remove capability)

Reading D-61's plan line by line — the thing this changelog kept saying must happen — turned up
two declarations that were wrong in the destructive direction, and one control that could not
have caught them:

- **D-68 · `jolarca-identity` would have been frozen.** Its `required_status_checks` declared
  `ci`, `security`, `lint`; the repository's only workflow (`ci.yml`) reports
  `gitleaks (full history)` and `shellcheck`. Live protection has no required checks, so the plan
  carried `+ required_status_checks` — *adding* an unsatisfiable requirement under `strict: true`,
  which makes every future PR on that repo unmergeable. Declaration rewritten to the two real
  check-run names.
- **D-68 · `jolarca-data` would have hidden live work.** It declared `has_issues: false` (the fleet
  default) while live is `true` with **open issue #4, "i.SAF FR0600 export: monthly
  invoice-register XML from finance marts"**. The plan rendered `~ has_issues = true -> false`:
  the apply removes the Issues tab and freezes a tracked PCI-scoped finance requirement, with a
  policy default reading as the justification. Now `has_issues: true` as a documented per-repo
  override (identity and security already do this and validate clean). Measured: plan
  `0 to add, 20 to change` → **`0 to add, 19 to change`**.
- **D-67 · the detecting gate was advisory and exempted its own offenders.**
  `check_declared_contexts.py` exited **1** on `main` (`unproducible: ci/security/lint`, note
  "every PR there would block forever") but ran only in path-filtered `context-parity.yml`, which
  is not a required context — and that job passed
  `ALLOW_MISSING_REPOS: "jolarca-identity jolarca-security"`, naming exactly the repos whose
  declarations were broken. Exempting a repo from the check that detects an unsatisfiable
  declaration hides the report, not the defect. The script now also runs inside the required
  **`Validate Repo Allow-List`** job, and `ALLOW_MISSING_REPOS` is empty (both entries measured
  satisfiable). Trade-off recorded rather than buried: the step reads the live API, so a GitHub
  outage can redden a required context; the script exits 2 on an unreadable repo instead of
  passing, which is the point (§3, D-23).
- **Step 6 packet rewritten as a 19-row sign-off table** in `docs/state-migration-runbook.md`,
  each line read from `terraform show -no-color`: 3 tightenings of
  `required_linear_history`/`require_conversation_resolution`, 4 added `required_status_checks`
  blocks (with the check names, so the reviewer can verify producibility without rerunning
  anything), the one genuine weakening (row 8: `jolarca-docs` signed commits and code-owner
  review true→false, both D-05/D-20 dated deviations), 1 capability change (`jolarca` issues
  false→true), and row 14 — the live `template { owner = "journeyoflife-org" }` on
  `jolarca-legal`, a cross-estate reference `check_fleet_separation.sh` cannot see, which the
  apply removes (ADR-0004, D-57).

- **D-69 · the last privacy-arguing comment in the fleet contradicted its own field.** Found by
  reading `repos/jolarca-identity.yml` after editing it, not by trusting my own summary: its header
  said "Private: this repo defines RBAC policy… Evidence stays in jolarca-compliance (also
  private)" four lines above `visibility: public`. Measured `grep -h '^visibility:' repos/*.yml`
  → 16 public, and `grep -rn '^# Private\|(also private)' repos/*.yml` → only these two lines in
  the whole fleet. That is an instruction to reverse a field AGENTS.md §4 classes as D-01-grade,
  aimed at whoever is told to "fix the drift" — and D-52 measured the cost (privating a governed
  repo makes `Context Parity` exit 2, because the token cannot read private siblings; the
  2026-10-06 flips were reverted the same day). The comment now states the measured fact and the
  hazard, keeps the 2026-09-25 rationale as a dated quotation, and names the actual compensating
  control. The file's CI caveat got the same treatment; the access-review half of its promotion
  rubric was deliberately left unverified rather than asserted.

Verification: `check_declared_contexts.py` **exit 0, "OK: 16 checked; 16 clean"** (was exit 1) ·
`validate_repos.py` 16/16 · yamllint clean on both workflows · refreshed plan
`0 to add, 19 to change, 0 to destroy` · `check_plan_safety.sh` still **exit 1** on all eight
protection lines · `make lint` exit 0 · evidence re-registered (`repos/*.yml` are hashed) and
`--check` exit 0.

### Fixed — 2026-10-15 (fifth batch: D-46 interim, and the gate defeated by its own input format)

- **D-46 interim.** The packet's last create-class item was the three
  `github_branch_protection` rules for `jolarca-consent`, `-dr` and `-vendor`. Those repos are
  enforced by **active undeclared `protect-main` rulesets**, whose content is now measured
  rather than assumed: consent `24087580` = deletion + non-fast-forward + required linear
  history, **no PR rule and no status-checks rule at all**; dr `24136490` = those plus a PR rule
  (0 approvals) and required `[lint, gitleaks]`, strict false; vendor `24138288` = those plus a
  PR rule allowing merge/squash/rebase and a status-checks rule with an **empty context list**.
  GitHub enforces the union of both layers, so creating the legacy resource would have made the
  Terraform object look like the control while the ruleset is what actually bites. The three are
  excluded via `local.ruleset_protected_repos`. Measured: `3 to add, 20 to change` →
  **`0 to add, 20 to change`**, with nothing destroyed (they were never in state). **D-46 stays
  OPEN** — this is an interim, and its cost is stated plainly: those repos' declared required
  contexts (consent 7, dr 1, vendor 1) are enforced by nothing, before and after. Reusable API
  detail: `/rulesets/{numeric-id}` returns the rule bodies; `/rulesets/protect-main` is HTTP 404.
- **The gate's verdict depended on its input format.** One plan file (`tfplan7`, 370 lines,
  8 `github_branch_protection` resources updating in-place), rendered two ways and handed to the
  same script: `terraform show tfplan7` → **840 ANSI escape bytes → exit 0**, "no
  protection-layer change"; `terraform show -no-color tfplan7` → **0 escape bytes → exit 1**,
  naming those 8 changes. Every pattern anchors at line start, so colour bytes sitting in front
  of `~`/`-` defeat the entire protection rule set. CI was safe only by accident, because
  `apply.yml` renders through `terraform show -json | jq -r`, which is plain text. Fixed inside
  the gate instead of being pushed onto operator habit: ANSI input now exits **2** ("cannot
  verify", never a silent pass — §3). 21 fixtures pass, including the pair that pins this:
  `coloured-plan` → 2 and `stripped-still-refused` → 1, the second proving the guard keys on
  FORMAT and is not a way to smother the detection underneath it. Writing that fixture also
  showed GNU sed does not expand `\033` inside a BRE, so the escape byte comes from `printf`.
- **Register and runbook honesty.** D-61 gains a fourth correction plus the measured state of the
  plan: the residual 20 changes are tightenings toward the declarations (four add
  `required_status_checks`, three set linear history / conversation resolution true, two land
  D-20's deliberate deviations), and the gate still refuses them. D-46 gains the ruleset content
  and the interim. The runbook's step-6 acceptance list no longer permits "three creates as
  exceptions" and now states the `-no-color` requirement for reading a plan.
- **Two claims retracted in place, both mine.** (1) Mid-stream I asserted "the plan touches no
  protection at all" before reading the captured output — wrong, and the numbers above are the
  re-measured ones. (2) I then reported a *committed CHANGELOG regression* ("released sections
  lost"); `git log --all -S '## [0.2.0]'` shows **no commit ever added or removed** those
  headings, the file was created by `a62234d` with a single `## [Unreleased]` section, and the
  alarm came from a stale snapshot served by the file-read tool. This is the fourth time this work
  stream has asserted from an unread or stale source (`commits/HEAD`, `STATE_MIGRATION_COMPLETE`,
  the "no protection" line, this one), and the register's rule — verify the verifier, and re-read
  through an independent channel before declaring loss — is what caught it.

Verification: `terraform fmt -check` · `terraform validate` · refreshed plan
`0 to add, 20 to change, 0 to destroy` · gate exits **2** on colourised text and **1** on plain
text of that same plan · plan-gate fixtures 21/21 · `make lint` · `compliance_check.py` pass ·
evidence re-registered (`branch-protection.tf` is hashed) and `--check` exit 0.

### Fixed — 2026-10-15 (third batch: two holes in the D-61 gate, and the 404 that wasn't)

Preparing the step-6 packet and testing the plan-safety refusal **against real
Terraform output instead of shapes I had assumed** found that half of yesterday's
fix could not fire:

- **`- restrict_pushes` was invisible to it.** Terraform marks a removed nested
  block with `-`, and 11 of the 25 live changes are `- restrict_pushes {
  blocks_creations, push_allowances }` — deleting the push restriction, the
  plan's dominant weakening. The refusal pattern allowed only `~`. Now both
  markers, plus the block-level names (`restrict_pushes`, `push_allowances`,
  `blocks_creations`, `dismissal_restrictions`, `lock_branch`,
  `allows_force_pushes`, `allows_deletions`, …).
- **The security-feature rule could never match.** The transition renders on a
  nested `status = "disabled" -> "enabled"` inside `security_and_analysis`, not on
  the feature name. Added the nested pattern, disable direction only, with
  fixtures proving enabling is still allowed — a gate that blocks the fleet's own
  remediation gets deleted under pressure (AGENTS.md §5).
- Re-checked against the real plan: exit **1**, naming all 11 `restrict_pushes`
  removals. Fixtures 19/19 (was 16); `shellcheck` also caught a backtick inside
  a double-quoted rationale, which would have been command substitution at runtime.
- **D-61's premise about the three creates was wrong and is corrected.**
  `jolarca-consent`, `jolarca-dr` and `jolarca-vendor` return HTTP 404
  `"Branch not protected"` — there is no live rule to overwrite, so those creates
  *add* protection. Adoption is otherwise complete: 14 `github_branch_protection`
  addresses in state, so step 6's "import the thirteen" is done and what remains
  is attribute reconciliation. The refusal stays (a human should approve a
  protection change), the justification is fixed.
- **New: the step-6 packet** in `docs/state-migration-runbook.md` — the 28 changes
  classified WEAKEN / TIGHTEN / NEUTRAL / UNRESOLVED per resource, read from
  `terraform show`, with the operator's ordering (land adoption alone first, then
  one behavioural change per PR). Includes the flagged oddity that `jolarca-vendor`
  diffs three attributes that are not `github_repository` arguments and must be
  inspected with `terraform state show` before anything is applied there.
- **D-63's open half resolved itself:** the branch-protection endpoints that
  returned 404 twice earlier in the day return **200** on the same token hours
  later, with `.protected=true` and `rulesets=[]` throughout — a transient API
  response, not a settings change and not a scope artefact. AGENTS.md §8 now says
  what it means: one 404 proves nothing, re-read before writing a finding.

### Fixed — 2026-10-15 (second batch: D-02's backup, and D-62 made enforceable)

Continued the "fix every material finding in-repo" pass after #69 merged.

- **`scripts/state_backup.sh` rewritten and proven (D-02 second half).** It was
  dead since state moved to HCP Terraform — keyed to a 0-byte
  `terraform.tfstate`, exiting 1 every run, while the register cited it as the
  interim control. It now pulls the workspace's current state version (org and
  workspace parsed from `main.tf`'s `cloud {}`), rejects HCP's *sanitized*
  `hosted-json-state-download-url` in favour of the real
  `hosted-state-download-url`, encrypts to `$BACKUP_DEST`, and **decrypts and
  compares SHA-256** before reporting. Live run: 7 resource blocks / 6 outputs /
  87,803 bytes, serial 14, digest match, artifact + manifest written. Exit codes
  follow §3 — skipping the proof exits 2, never 0. `make backup` wraps it;
  `tests/test_state_backup.sh` adds 10 fixtures including wrong-identity and
  unreachable-backend. **Still open, and recorded as open:** no schedule, and
  the destination plus age key are on the same host — a verified export path, not
  yet a 3-2-1 copy.
- **New gate for D-62: `scripts/check_required_context_baseline.py`.** Compares
  `policy/repo-defaults.yml` `required_checks.control_plane`, the
  `repos/jolarca-control.yml` declaration, and the job names a `pull_request`
  event can report; wired into `Validate Repo Allow-List` (a required context)
  and `make lint`. Writing it surfaced two bugs in the gate itself before it went
  green — notably `pull_request:` with no value parses to `None` and was read as
  "absent", which made it call all four real contexts unproducible; both are now
  regression-locked by fixtures, and the register corrects the earlier claim that
  this file would stay "convention-only".
- **AGENTS.md §2/§8 updated to match measurement**, not the other way round: the
  plan-safety refusal list now includes protection-layer and security-feature
  classes, the merge of #69 is recorded with its real outcome (plan failed on the
  state lock, apply **skipped**, so nothing applied), and §8's backup bullet now
  says what works and what does not.

Verification: `make lint` (including the new `context-baseline` step) ·
`bash tests/test_state_backup.sh` 10/10 · `bash tests/test_check_plan_safety.sh`
16/16 · pytest with the two new suites · live `BACKUP_DEST=/opt/jolarca/backups`
run with the round trip matched · evidence registry re-hashed and `--check`
green.

### Changed — 2026-10-15 (D-59, D-60: published contacts and commit identity)

- **New `policy/contact-addresses.yml`** — the single definition of the five
  role mailboxes (dev / github / security / privacy / billing), which are
  published, which are retired, and the exact cross-repo targets still naming
  dead addresses. Convention-only: no gate reads it yet, and the file says so.
- **Every published contact was undeliverable.** `jolarca.com` and
  `jolarca.dev` have no MX and no DMARC (measured: `dig MX`, `dig TXT _dmarc`,
  no listener on 25/587, no mail container), so `security@jolarca.com`,
  `legal@jolarca.com`, `security@jolarca.dev` and `legal@jolarca.dev` could
  never receive a report — 34 hits across 6 repositories, including the
  `jolarca-security` audit's own open Critical finding F-05 (2026-09-28).
  `files/SECURITY.md` now names the interim security and privacy aliases.
- **GitHub organisation contact updated and re-read.** `orgs/jolarca-dev`
  `billing_email` and profile `email` moved from the general dev alias to the
  GitHub-operations alias. No Terraform drift is possible: no
  `github_organization` resource exists in state.
- **Commit identity no longer publishes a personal mailbox.** Global
  `git config user.email` (inherited by all 16 fleet repos on this host) is now
  the ID-prefixed GitHub noreply address. Existing history keeps the old
  address; a fleet-wide rewrite was rejected as disproportionate and is an
  operator-only action (AGENTS.md §5).
- **ADR-0006 and ADR-0007 amended, not silently rewritten.** The HCP Terraform
  org billing email is re-measured and still the base mailbox — recorded as an
  outstanding owner-executed UI change rather than restated as an alias nobody
  has confirmed at the provider. ADR-0007's assumption that SECURITY.md provides
  a working disclosure route is corrected by a dated amendment.
- **`policy/compliance-gates.yml`** gains `contact-alias-interim` (approved
  2026-10-15, expires 2027-01-13) stating what the aliases do and do not buy:
  routing and leak attribution, not segregation of duties or an independent DPO.
- **AGENTS.md §6 and §8** record the convention and the trap: `files/SECURITY.md`
  is a reference copy, because `github_repository_file.security_md` is
  commented out and the served file lives in the `.github` repository (D-15).

### Changed

- **Apply is a single gated production stage.** `jol-control`'s
  dev → staging → prod promotion was deliberately not replicated: an
  organization control plane has one target, so promoting one plan three times
  would apply identical changes to the same repositories three times.
- **Approving-review count is 0, not 2.** Matches verified live reality and the
  solo-era deviation. Recorded as D-04 with four compensating controls.
- **Signed-commit enforcement is off** at the branch-protection layer
  (D-05), while `commit_signing_policy` keeps the human obligation explicit.
- **LICENSE is proprietary**, not MIT. This repository is private and holds the
  governance posture of a PCI-DSS scope; the AGPL-3.0 on the public `jolarca`
  application does not extend to it.

### Fixed — inherited defects corrected during the port

- **False compliance assertions removed.** The inherited SOC 2 and ISO 27001
  checklists claimed as `implemented`: org-wide MFA (verified **disabled**,
  D-18), team-based access control (no teams exist, D-10), signed-commit
  enforcement (verified `null`, D-05), and Terraform state encrypted in AWS
  `eu-central-1` with SSE (there is no AWS backend anywhere in the marketplace
  tree — state is a local file, D-02). Each is now recorded as a gap with a
  finding ID. A checklist that overstates controls is a worse audit outcome
  than an honest gap.
- **False GDPR data-residency claim removed** (Art44-02) and replaced with the
  verified GCP `europe-west1` default plus an explicit gap for state residency.
- **Unpinned GitHub Actions.** The inherited workflows used floating tags
  (`actions/checkout@v4`). All are now pinned to full commit SHAs, matching the
  doctrine already applied across the fleet.
- **Dead `data "github_team" "security"` block** inherited from `jol-control`
  was dropped — it is referenced nowhere and would fail every plan in an org
  with no teams.
- **`apply.yml` used `secrets.GITHUB_TOKEN`**, which cannot manage other
  repositories or org-level resources. Replaced with a least-privilege
  fine-grained PAT split into read-only and read/write secrets.

### Security

- `apply.yml` refuses any plan containing a destroy, a replace, or a visibility
  change.
- `prevent_destroy` on every `github_repository`.
- Both `plan` and `apply` are gated on the `STATE_MIGRATION_COMPLETE`
  repository variable, which is intentionally unset.
- `make apply` refuses outright; `make plan` offers only an offline
  `-refresh=false` plan.

### Known limitations

This control plane is **not yet authoritative**. It declares the governance of
six live repositories but does not own their Terraform state. See the README
banner, `docs/state-migration-runbook.md`, and findings D-02, D-13.

Three findings block the first apply: **D-01** (four PCI-scope repositories
publicly readable), **D-02** (single-copy local state, no backend, no
locking), **D-18** (org-wide MFA not enforced). D-18 is a single organization
setting and can be closed immediately with no code change.
