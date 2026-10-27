# Changelog

All notable changes to `jolarca-control` are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

This repository is the governance control plane for the `jolarca-dev`
marketplace organization. Changes here can alter branch protection, visibility
and scanning settings on six PCI-DSS-scoped repositories, so the changelog is
part of the SOC 2 CC8.1 / ISO 27001 A.8.32 audit trail and is not optional.

## [Unreleased]

### Fixed — 2026-10-27 (D-02: `state_backup.sh` now measures whether the destination is off-host instead of asserting it)

- The script's own header said `BACKUP_DEST` is an **off-host** directory, and it was never checked.
  Measured on this host: `/opt/jolarca/repos/jolarca-control` and `/opt/jolarca/backups` are both
  device **64513** on `/dev/mapper/vgopt-lv_jolarca` — different paths, same filesystem. So every
  "off-host" backup taken so far, including the decrypt-proven `s16`/`s17` archives, is insurance
  against operator error and **not** against host loss.
- `scripts/state_backup.sh` now compares device ids (`stat -c%d`, BSD fallback) and records the
  verdict in `$BACKUP_DEST/backup-probes.tsv` — a **separate** file, because `backup-log.tsv`'s
  7-column schema is read positionally by the fixture and by anyone auditing an archive, and
  silently widening it is how records rot.
- `STATE_BACKUP_REQUIRE_OFF_HOST=1` turns the finding into a refusal (exit 1). Default is **0**:
  making today's only destination fatal would stop backups happening at all, which is worse than a
  loud warning. Flip it when a real second destination exists.
- `tests/test_state_backup.sh`: 6 new cases, **proven red first** — against `origin/main`'s script
  they print `FAIL require-off-host-refuses-same-fs want exit=1 got exit=0` plus both probe-record
  failures (13 passed / 3 failed); with the change, **16 passed / 0 failed**. One case asserts the
  fixtures' own devices differ, because a same-device test of an off-host gate would pass while
  proving nothing.
- shellcheck clean; gate-parity, findings-register, evidence (46/0), yamllint, terraform fmt and
  validate, pytest all exit 0. No state change, no apply, no new trigger-path file.
- **Corrected after CI caught the author:** PR #105's `Regression Tests` failed on the runner with
  `fixture-devices-are-actually-different dest_dev=66305 same_fs_dev=66305 repo_dev=66305` — the new
  off-host cases had assumed `$TMP` sits on a different filesystem than the workspace, true on this
  dev box and false on `ubuntu-latest`. The script was right (it correctly refused under
  `STATE_BACKUP_REQUIRE_OFF_HOST=1`); the fixture asserted a host property instead of measuring one.
  It now probes `/dev/shm`, `/run`, `/tmp` for a device that differs from the repo's and asserts the
  `off_host=yes` branch only where one exists, with a loud `SKIP` otherwise. Verified 16/0 on this
  host **and** in a simulated runner tree whose device equals `/tmp`'s.


### Changed — 2026-10-27 (D-90 half-closed for free: gitleaks CLI passes in CI, and a rule so this cannot recur)

- consent PR #12 landed the license-free swap and it is **verified in CI, not just locally**: the
  rerun of `40570141865` shows `Gitleaks (secret scanning)` → `success` in 7s. The paid *Action* was
  the blocker; the free CLI performs the same scan, pinned to 8.30.1 and gated on a sha256 from the
  release's own checksums asset, with a negative control that plants a runtime-assembled credential
  and fails the job if gitleaks does **not** detect it.
- `Dependency review` is still red and `GET /dependency-graph/sbom` is still **404** after the rerun,
  so the free Dependency-graph toggle has not taken effect; all five open consent PRs remain
  `BLOCKED`. Recorded as unresolved rather than assumed fixed.
- **A correction against my own previous turn:** I asserted that enabling the graph "alone would not
  have made the context pass". The job log shows the refusal is the feature flag
  (`Dependency review is not supported on this repository`), so the toggle is the gate and the
  committed `requirements.txt` is what stops the control being hollow. Third time this session a
  cause was stated from inference while a log line was available.
- New AGENTS.md §7 rule, which is the durable part: **a required status check must be proven
  passing, not merely producible.** `check_declared_contexts.py` exiting 0 says a PR-triggerable
  workflow emits the name; it says nothing about whether the job can go green. Read
  `gh run list --repo <r> --workflow <wf> --branch main --limit 5 --json conclusion` and require
  observed successes before adding a context to a required list. This is the D-44/D-47/A-01 deadlock
  class, entered this time by me.
- Queue note: consent PR #2 bumps `gitleaks/gitleaks-action` 2.3.9 → 3.0.0. Once #12 merges that
  action is unreferenced, so **#2 must be closed, not merged** — merging it reinstalls the licensed
  Action and re-jams the repository it was opened to update.
- Fleet scope measured, so the fix is sized correctly: `jolarca-consent` is the **only** repo requiring
  `Dependency review`, and 7 of 17 have no dependency graph. No trim is needed for the other nine, and
  no repo in the org holds a `GITLEAKS_LICENSE` (secrets exist only on `jolarca-control` and
  `jolarca-infrastructure`), so the licensed Action was a fleet-wide liability rather than a consent
  quirk — the CLI swap is the pattern any repo adopting a secret-scan context should copy.
- D-89 stays open and decision-neutral: the §7 wording above does not presuppose whether the
  permanent `1 to change` on `jolarca-legal` is accepted or cleared by re-import. Both remain the
  operator's call; the fact (create-only attributes cannot converge) is recorded either way.


### Changed — 2026-10-27 (D-90 evidence: consent's two blocking contexts fail on `main` itself, and the graph needs a manifest)

- `gh workflow run security.yml --repo jolarca-dev/jolarca-consent --ref main` → run `40568417936`,
  `completed/failure`, **both** `Gitleaks (secret scanning)` and `Dependency review` red. Not a PR
  problem: the repository cannot produce a green required context today, so every PR there is blocked.
- `Dependency review` has a second cause than the settings toggle: `GET …/dependency-graph/sbom` is
  **404** and consent's tree carries **only `pyproject.toml`** — no `requirements.txt`, no lockfile.
  The action needs a resolvable manifest, so the fix is a committed pinned manifest.
- The command I first handed over for the dispatch was wrong (`-f ref=main` → HTTP 422). The workflow
  declares `workflow_dispatch:` with no inputs; `--ref` is the flag. Same class as the vacuous
  `until` loop and `python scripts/state_backup.sh` earlier today: an interface asserted from memory
  instead of from `--help`.
- State is unchanged at **serial 17**, matching `terraform.tfstate.s17.20261027T185757Z.age`;
  `main` is `f409402` with `rulesets.tf` at stage 2, so config, state and live agree for consent.


### Changed — 2026-10-27 (step 4 executed by the operator; config now catches the live ruleset)

- **Consent's direct-push exposure is closed.** Measured on GitHub, not from the apply output: ruleset
  `24087580` `updated_at 2026-10-27T20:53:08`, `rules` = `deletion`, `non_fast_forward`,
  `required_linear_history`, **`pull_request`**, **`required_status_checks`**; the PR rule carries 0
  approvals, code-owner off, dismiss-stale on, thread-resolution on, `allowed_merge_methods:
  ["squash"]`; the checks rule carries all seven declared contexts with
  `strict_required_status_checks_policy = true`; `bypass_actors: []`. Stage 1 survived the PUT, because
  `rules` is one full-PUT block and stage 1 was restated (D-87 row (5)). `drift_detect.py` no longer
  reports consent; only `jolarca-vendor` remains in `weakened`.
- **`rulesets.tf` moves to the stage-2 block it just adopted**, extracted from Step 6b 4b rather than
  retyped. Until this commit `main` declared three rules while live had five, so **the next apply of
  `main` would have reverted the protection** — the same `max_items = 1` semantics that made the fix
  safe made the divergence dangerous.
- D-57 row 14 executed as a rider: `jolarca-legal`'s `template {journeyoflife-org /
  jol-repo-template}` detach was applied (state serial 16 → 17, backed up as
  `terraform.tfstate.s17.20261027T185757Z.age`, decrypt round trip verified) — **but the attribute is
  still in state and still in every plan**, for the write-only reason in the last bullet. Whether the
  provenance changed server-side is *not observable*: `is_template = false` is real, and the API
  simply has no template-provenance field, so an earlier `template_repository_url: null` reading here
  was a jq fallback on a missing key, not a measurement. The register rows that called row 14
  "pending" are corrected in `docs/drift-findings.md`, not silently reticked.
- **Cost of enforcing, measured after the fact:** consent's `Gitleaks (secret scanning)` and
  `Dependency review` fail **on `main`** (since 2026-10-15), so requiring them blocks every PR merge
  there. Cause of each is a configuration gap, not a finding: the Action needs a paid
  `GITLEAKS_LICENSE` (`gh secret list` → none) and the Dependency graph is off. Free fixes, in
  consent's own repo: run the gitleaks **CLI** as this repo already does
  (`compliance-scan.yml:214-220`, pinned version, checksum verified — better than this repo's own
  unchecked `curl | tar`), and enable the dependency graph. The `pull_request` rule is not relaxed.
- Newly live and not sent by us: `require_extra_approval_for_unattributed_changes: true`, GitHub's
  default for a field provider 6.13.0 omits (D-46). Untested against `required_approving_review_count
  = 0` and D-60's `verified: false, bad_email` commit identity — recorded as a risk to probe, not as a
  conclusion.
- Verification, and one claim in this entry that was wrong before it was committed: `terraform plan`
  after the change is **`0 to add, 1 to change, 0 to destroy`**, not "No changes". The ruleset **did**
  converge — `terraform show -json` reports *no non-`no-op` ruleset change* — so the revert hazard is
  closed. The surviving line is `github_repository.repo["jolarca-legal"]`'s `template` block, and the
  reason is a provider artifact, not an unfinished apply: `template` is a **create-time, write-only**
  attribute (schema text: "Whether **the new repository should include** all the branches from the
  template repository"), GitHub exposes no provenance field to read, and the provider's Read never
  clears it — so `terraform state show` still prints the block after a `Modifications complete`, and
  `-refresh-only` reports "No changes". **The plan can never converge on that resource.** Remaining
  local gates all exit 0; suite 334 passed.


### Changed — 2026-10-27 (`rulesets.tf` lands: the adopted consent ruleset enters configuration, and the merge that lands it executes D-57 row 14)

- `rulesets.tf` is added, byte-identical to the block `make adoption-block` extracts from Step 6b
  (resource `github_repository_ruleset.main`, `for_each = toset(["jolarca-consent"])`). It was extracted
  rather than retyped, then `terraform fmt -check -recursive` **exit 0** and `terraform validate`
  **exit 0** with the file in the tree.
- **The adoption half is inert and proven per-address**: `terraform plan` on this branch reports
  `no-op` for `github_repository_ruleset.main["jolarca-consent"]`. The state already holds it
  (imported 2026-10-27, serial 16, covered by the decrypt-verified archive
  `terraform.tfstate.s16.20261027T181509Z.age`, SHA-256 round trip matched).
- **But this is the first trigger-path merge since the adoption, and it is not inert as a whole.**
  The same plan reads `0 to add, 1 to change, 0 to destroy`, and the one change is
  `github_repository.repo["jolarca-legal"]`: `before.template = [{owner: "journeyoflife-org",
  repository: "jol-repo-template", include_all_branches: false}]` → `after.template = []`. That is
  **D-57 packet row 14**, decided "REMOVE — ADR-0004 alignment" and never executed, and there is no
  targeted-apply mechanism in this root — so this PR is the vehicle for it, and the merge starts the
  apply job with `-auto-approve` after the 30-minute wait, with no reviewer. Whether that job reaches
  the backend is a separate question answered two bullets below (it does not, today). The brake does
  **not** stop it (`check_plan_safety.sh` exits **0**: a template provenance change is not a destroy,
  replace, visibility, protection or security-feature change).
- Stated plainly because it is the decision that matters: **this PR is the vehicle for D-57 row 14.**
  The direction is the one the register already chose; the sign-off box in step 6's table is the
  operator's to tick, and the runbook now names this branch as the execution vehicle so the audit trail
  says which merge did it.
- **Corrected the same day, against my own two bullets above: "the merge WILL start a production
  apply" is true of the JOB, not of the apply.** Measured on this PR's own `Validate & Plan` run
  (`40562611887`), the job dies at `Terraform Init` with
  `Error: Failed to read organization "jolarca-dev" at host app.terraform.io … unauthorized` on
  `main.tf:28` — the D-56 / D-77 credential gap, still open. So merging this lands the file and
  changes **no live object**: it is `UNSTABLE` (all four required contexts green; the red check is
  `Validate & Plan`, deliberately non-required), the apply job starts, and it fails before reaching
  the backend. Every `apply.yml` run in the log agrees — `cancelled`/`failure`, none successful, newest
  2026-10-17.
- Which is a warning, not reassurance. **The thing standing between a trigger-path merge and an
  unreviewed `terraform apply -auto-approve` is a broken token.** The moment D-56 is repaired, whatever
  the accumulated plans say will apply automatically — including D-57 row 14 and anything merged in
  between. AGENTS.md §8 already states this order ("once the token is repaired the refusal gate is what
  has to stop it"), and `check_plan_safety.sh` does exit **0** on this plan, so for D-57 the refusal
  gate is not what stops it either. Repair the token deliberately, with the pending diff read first —
  not as an incidental fix.
- `check_apply_path_trigger.py` on this branch reports **NOTICE — a human changed apply-path files; the
  merge WILL start a production apply** (exit 0 for a human author, by D-81's design). That is expected
  here, not a green light: watch the pending window and cancel with `gh run cancel <id> --force`.
- Files: `rulesets.tf` (new), `docs/state-migration-runbook.md` (one line naming the execution vehicle
  at step 6's table), this entry. No protection rule content changes; `strict` and `update` remain
  unset, which is step 4 and a separate reviewed PR.
### Changed — 2026-10-27 (`jolarca-consent`'s `protect-main` ruleset is now under Terraform; D-46 option A executed for consent, inertly)

- **This is a live state change, not a docs change.** The operator ran Step 6b steps 1–3: the adoption
  block was extracted by `make adoption-block`, `terraform import
  'github_repository_ruleset.main["jolarca-consent"]' 'jolarca-consent:24087580'` returned
  `Import successful!`, and the remote state serial moved **15 → 16**. `terraform state list |
  grep -c ruleset` went **0 → 1**; the state `id` at that address is the numeric `24087580`, not the
  `repo:id` pair typed (the import-id ≠ state-id trap, as documented for `github_branch_protection`).
- **Inertness proven two ways, not assumed.** Per-address the plan reads `no-op` — the mirror is
  faithful — and against the live object `updated_at` still equals `created_at`
  (`2026-09-28T02:07:06`), with `rules` unchanged and `bypass_actors: []`, so the import performed no
  write to GitHub. Whole plan `0 to add, 1 to change, 0 to destroy`; `check_plan_safety.sh` exits **0**.
- **What this does not fix:** consent still has no `pull_request` rule and no `required_status_checks`
  rule, so `main` is still directly pushable. `make drift` still exits **1** naming
  `no pull_request rule (no PR is required on main)`, and dr/vendor are unchanged: their status-check
  attributes still enforce nothing (dr requires `[lint, gitleaks]` strict false; vendor an empty list).
  Adoption made the object manageable; **step 4 is what makes it enforce**.
- **New dependency created by landing it:** `rulesets.tf` is now an in-scope `*.tf` file, so the next
  merge touching a trigger path will plan against an adopted ruleset (no-op, good) *and* carry D-57's
  `jolarca-legal` template detach, which the brake does not refuse. Decide D-57 before that merge, not
  inside it.
- **Operational exposure measured and flagged:** the newest archived backup is
  `terraform.tfstate.s14.20261015T180246Z.age` — **serial 14 against a workspace at 16** — and
  `/opt/jolarca/backups` is on the same host as the working copy. A restore today would lose the
  adoption plus twelve days. Run `BACKUP_DEST=… make backup` before step 4 changes state again (D-02).
- Records updated to stop asserting the old state: `docs/state-migration-runbook.md` (Step 6b's
  "Nothing in this section has been run" → an executed-status table), `AGENTS.md` §8 (0 → 1 ruleset
  address; the "provider cannot express three keys" sentence corrected per D-87 row (6); "nothing there
  has been run" → steps 1–3 run, step 4 not), `docs/drift-findings.md` (D-46 dated status; D-84
  residual (1) struck through where it is now false; **D-88 retitled so the collision guard's
  title-segment split does not truncate it** — the guard segments on the first em dash, and the
  previous heading put one inside the title).
- No agent-performed mutation: the import was the operator's, run under §5; no `apply`, no `state rm`/
  `state mv`, no org PATCH, and `rulesets.tf` remains **untracked** — committing it is a separate,
  reviewed `*.tf` change.

### Added — 2026-10-27 (`make adoption-block`: Step 6b step 1 must not be transcribed by hand)

Two hand-rolled replacements for the transcription both failed, one of them silently.

- `scripts/extract_adoption_block.py`, `tests/test_extract_adoption_block.py` (**13 cases**, re-derived
  from `--collect-only` each time it changed — it first claimed 13 by hand, measured 12, and returned
  to 13 when the trigger-path warning test was added),
  `Makefile` target `adoption-block`. This is D-87 row (8)'s remedy, and the row records why a
  one-liner was not enough: a `python -c` raised `IndexError` because the fenced adoption block opens
  with comments, and would anyway have disqualified it on the word `pull_request`, which the block's
  own explanatory comment contains; an `awk` variant anchored on a line with an em dash emitted **zero
  lines** and `terraform fmt -check` reported the empty file as **clean**. Both failures were caught
  only by asserting counts rather than reading an exit code.
- Selects by **block syntax** (an indented `name {`), not prose, and refuses to write unless exactly
  one candidate is provably inert: one resource block, named `main`, a `for_each` containing
  `"jolarca-consent"`, and no `pull_request` / `required_status_checks` / `bypass_actors` block. It
  will not overwrite an existing `rulesets.tf`. Codes per §3: **0** unique inert adoption · **1**
  refused · **2** could not verify — an absent fence is never a pass, which is the exact hole the awk
  version fell into.
- Step 1 of the runbook now gives the command instead of "land this file"; step 2 states the
  prerequisite the operator just discovered the hard way: Terraform refuses to import into an address
  the configuration does not declare (`resource address … does not exist in the configuration`), and
  that refusal writes nothing — `state list | grep -c ruleset` stayed **0** and the state serial was
  unchanged, so the failed attempt was safe but not a no-op proof.
- Wiring follows D-80: new script ⇒ new fixture naming its subject (R1/R1b), and the fixture must run
  while the script must be invoked by something executable (R2/R3) — the `Makefile` recipe is that
  invocation, because a mention in prose is not one. `make lint`'s `gate-parity` step enforces it.
- Blast radius: `scripts/**`, `tests/**` and `Makefile` are **not** in `apply.yml`'s push paths, so
  merging this arms no apply (`check_apply_path_trigger.py`: 6 files, none matched). No `.tf` touched,
  no Terraform mutation, no import. Suite **321 → 334**; `check_gate_parity.py` now counts **19** gate
  scripts (was 18), which is the evidence the new script's fixture and invocation are wired, not just
  claimed.
- Caught by running it rather than by reading it: the first harness reported `pytest_rc=0` over **2
  real failures** because the command was piped through `tail` — `tail`'s exit code, the §3 trap this
  register already documents — and the failures were a genuine bug in the new script (`^resource "`
  compiled without `re.M`, so it counted 0 resources in a block that starts with a comment). Both
  numbers and the fix are in D-87's Verified row.
- **A fourth metacharacter incident, this time `>` rather than a backtick.** While probing whether
  `rulesets.tf` was gitignored, a message string containing `-> it would be picked up by git add -A`
  sat inside a command substitution, so the shell treated `>` as a redirect and created a 55-byte file
  named `it` in the governed tree. Untracked, absent from the registry, not part of the 46-file
  evidence baseline — confirmed by `git ls-files it` → 0 and `git log --all -- it` → no commits — then
  removed after inspection. Recorded in D-87 row (8)(c): the rule is not "no backticks in strings", it
  is that **every** shell metacharacter in a message is code.

### Fixed — 2026-10-27 (D-88 retracted: it duplicates D-57; the genuine delta is that the template line is now the plan's only change and the brake passes it)

- **This entry opened as `### Found … no gate can see it`, and that framing was wrong.** D-57 (S1,
  OPEN, blocks apply) already records the same `- template { owner = "journeyoflife-org", repository =
  "jol-repo-template" }` line, already states that nothing in this repository declares a template
  source, already names the `check_fleet_separation.sh` blind spot in nearly the same words — "a green
  fleet audit does not establish that the live organization is separated" — and step 6's sign-off
  packet already **decides** it: row 14, "REMOVE — ADR-0004 alignment". So the "three options for the
  owner" I wrote were re-offering a decision the register had taken. Caught by `grep -rn
  jol-repo-template docs/`, one keystroke, run *after* publishing the row. Third novelty claim this
  session that failed against the register, after D-84 residual (2) and the D-46 capability sentence;
  the shared cause is searching for expected phrasing instead of searching for the subject. D-88 now
  states the retraction in its own heading and points at D-57 as the row to close.
- What the re-measurement actually adds: the plan went `0 to add, 20 to change` → **`0 to add, 1 to
  change`**, so this line is the sole pending change for the whole org; `check_plan_safety.sh` exits
  **0** over it, so D-57's "blocks apply" now describes the human sign-off rather than the brake; and
  `drift_detect.py` mentions `template` **0** times, a second blind gate beside fleet-separation.
  Because there is no targeted-apply mechanism here, executing it **rides along with any apply**
  performed for another reason — including the Step 6b adoption sequence — which is why it is called
  out before step 2 rather than after step 4.
- Measured on the tree while `rulesets.tf` existed un-imported, as a guard test rather than an
  assumption: `terraform plan` → `1 to add, 1 to change, 0 to destroy`, and
  `check_plan_safety.sh` exits **1** with three named refusals, one of which prints the import command
  as its remedy. So the brake catches the late-import shape; the extract tool now says so on the line
  after it writes the file, because the artifact it produces is an apply-trigger path.

### Found — 2026-10-27 (D-88 originally: the plan's only remaining change is a mission-platform template reference in remote state)

- Executing Step 6b step b meant running its step-3 plan rather than quoting it. Measured:
  `terraform plan -input=false -no-color -out=tfplan` → **`Plan: 0 to add, 1 to change,
  0 to destroy`**, identical with `-refresh=false`, and `check_plan_safety.sh` on the rendered file
  exits **0**. The register's `0 to add, 20 to change` — cited as current in six governed lines, one
  of them written by me an hour ago from D-84 rather than from the plan — is stale.
- The one change is `github_repository.repo["jolarca-legal"]` dropping
  `template { owner = "journeyoflife-org", repository = "jol-repo-template" }`. No config in this root
  declares a `template` block (`grep -rn template *.tf repos/jolarca-legal.yml` → only `is_template`
  and `license_template`), so a **foreign-estate provenance reference is held in remote state** on a
  governed marketplace repo, which ADR-0004 and §5 exist to prevent.
- Both gates built for this class are structurally blind: `check_fleet_separation.sh` matches org repo
  **names** and the `repos/*.yml` allow-list against `jol-*` and never reads state or the API, and
  `grep -c template scripts/drift_detect.py` → **0**. A green `make fleet-audit` therefore means no
  foreign-estate link is written in a *file*, not that none exists. Recorded rather than fixed: a real
  check needs negative controls (§7) and a fixture (D-80 R1/R3), so it is not a docs change.
- Consequence to act on, stated plainly: `apply.yml:133` plans with refresh and the apply path runs
  `-auto-approve`, so **the next merge touching a trigger path applies this detach unattended** —
  the brake passes it because it is not a destroy, replace, visibility, protection or
  security-feature change. Whether it changes anything live is **unknown**: the provider sends no
  `template` on update, so it may be state-only, and that cannot be measured without doing the very
  apply under discussion. Three options for the owner are in the register row; none is a bug fix.
- Also recorded against me: the scratch harness that printed these numbers put `20 to change` inside
  a **double-quoted** shell string, so the backticks executed (`line 13: 20: command not found`) —
  the third instance of the bug D-84's own row documents, reproduced in this session. No file was
  created and nothing was mutated, but it is the same mistake, and it is why the register keeps
  writing it down.
- Files: `docs/drift-findings.md` (**D-88** opened then retracted onto **D-57**, dated status on
  D-57, dated correction to D-87 row (2) and its "Fixed here" cell),
  `docs/state-migration-runbook.md` (Step 3 verdict rewritten to measured fact; Step 6's count line
  marked superseded), this entry. `check_findings_register.py --cross-pr` exits 0 over **87**
  parsed headings, D-88 unique, no dangling citations.

### Fixed — 2026-10-27 (D-87: the staged D-46 adoption could not be executed as written)

- `docs/state-migration-runbook.md` **Step 6b** — the "ready, staged" sequence for adopting
  `jolarca-consent`'s undeclared `protect-main` ruleset (D-46 option A) — was audited rather than
  re-used. Four defects, all reproducible offline; no Terraform command was run and no GitHub
  state was touched.
- The inertness proof could never pass. `check_plan_safety.sh <(terraform show -no-color tfplan)`
  exits **2** every time: the gate requires a regular file (`[ ! -f "$PLAN" ]`) and process
  substitution yields `/dev/fd/63`, so it prints `plan file not readable`. The identical bytes in a
  real file exit **0** — measured both ways. The gate is correct (§3: an unreadable input is never
  a pass; D-61 exists to refuse shapes it cannot parse); the runbook prescribed the one invocation
  that cannot succeed **and told the operator to expect `exit 0`** — the dangerous combination,
  because "not readable" reads as a tooling nuisance mid-procedure, not as a refusal.
- That `expect exit 0` also hid a precondition: Step 6's unreconciled protection changes are still
  open (`0 to add, 20 to change`, measured 2026-10-26) and since D-61 the gate refuses *every*
  protection attribute change, so a whole-state plan exits **1** whatever the adoption does.
  Demonstrated on synthetic input — one `~ dismiss_stale_reviews` line → 1, naming the line;
  `0 to add, 0 to change, 0 to destroy` → 0. Step 3 now renders `tfplan` / `plan.txt`, passes the
  real file, and judges inertness **per address** via
  `terraform show -json | jq '.resource_changes[] | select(.type=="github_repository_ruleset") | {address, actions: .change.actions}'`,
  expecting `["no-op"]` — machine-read, not grep-matched (§7: never infer coverage from an
  aggregate exit).
- The "ready to paste" HCL failed `terraform fmt -check` — **exit 3**, two misaligned `=` — so the
  very PR Step 6b instructs the operator to open would have reddened `Terraform Format` and
  `make lint` on first push. Re-aligned and verified **exit 0** by re-extracting the block from the
  runbook itself rather than re-typing it.
- Its filenames leaked: `tfplan6b` and `plan6b.txt` match no `.gitignore` entry (`git check-ignore`;
  `tfplan` and `plan.txt` are exact names, `*.tfplan` needs the suffix), so a rendered plan — the
  whole org inventory plus every repository's protection posture — would sit **untracked in a
  public governed repo**, the same no-recovery-path hazard this session found in its own tree.
- Provider capability re-derived from `terraform providers schema -json` for the pinned
  `integrations/github` 6.13.0: consent's three live rules *are* modelled (boolean attributes of
  `rules`) and `pull_request` / `required_status_checks` exist as nested blocks, so the mirror and
  the step-4 tightening are both expressible. A whole-file `grep -c dismissal_restriction` returns
  **1**, but the hit is on `github_branch_protection`, not on `github_repository_ruleset` — so
  D-46's dr/vendor deferral stands, and Step 5 now says so explicitly, because an unscoped grep
  will look like the refutation of a true claim.
- **The same name-matching method produced a false inexpressibility claim, and it took a second
  pass to catch it.** `github_repository_ruleset` exposes 52 attributes and **renames** several
  concepts the registry spells differently: `require_conversation_resolution` is
  `rules.pull_request.required_review_thread_resolution` (schema description: "All conversations on
  code must be resolved before a pull request can be merged"), and `enforce_admins` is expressed by
  the **absence** of a `bypass_actors` block — consent's live ruleset reports `bypass: []`. Grepping
  the registry's spelling and reading 0 hits as "cannot express" is invalid; a 0-hit grep proves a
  name is absent, never that a control is. Only `restrict_pushes` truly has no attribute, and a
  `pull_request` rule makes a direct push impossible, so it is recorded as a mapping note. **Net
  effect: D-46 option A needs no dated deviation for consent** — the "documented field mapping"
  branch of D-84 residual (3) is now written out, in Step 6b 4b.
- **`rules` is `max_items = 1`**, which makes step 4's wording dangerous: one block holds the entire
  ruleset and an update PUTs the whole thing, so "extend the block with a `pull_request` rule" read
  as an append would **drop stage 1** (`non_fast_forward`, `deletion`, `required_linear_history`) in
  the very apply that adds stage 2 — a protection weakening landed inside a protection fix. Step 6b
  now carries the complete stage-2 block with stage 1 restated and all seven contexts spelled out.
- **`restrict_pushes` maps too, which replaces this entry's own "subsumed" claim.** Reading
  `rules.update`'s provider description — "Only allow users with bypass permission to update
  matching refs" — shows it is the legacy `restrict_pushes` semantic, so **all three of consent's
  keys have a ruleset expression** and D-46 option A needs no dated deviation whatsoever. The
  caveat is that `update = true` is a strengthening, not a mirror: consent's live ruleset does not
  carry it, so putting it in the adoption block would break step 3's `no-op` proof and would also
  mean no direct push to `main` is ever possible, including in an incident. Step 6b 4b now states
  that as an explicit step-4 choice rather than an omission.
- **The remedy for the `max_items = 1` hazard introduced a bigger one, and review caught it.** The
  stage-2 block added to Step 6b declared `resource "github_repository_ruleset" "jolarca_consent"`,
  while step 1 declares `"main"` with `for_each = toset(["jolarca-consent"])` and step 2 imports
  `github_repository_ruleset.main["jolarca-consent"]`. Pasting the new block beside step 1 would
  have produced **two declarations over one live ruleset**, and the plan would then want to create a
  duplicate `protect-main` on a tier-1 GDPR repo next to the rule actually enforcing. `check_plan_safety.sh`
  refuses that create in CI (D-84) — but step 4 is the one step the runbook says to apply **by
  hand**, which is exactly where that brake is stepped around by design, so relying on the brake was
  the wrong layer. 4b now uses the imported address, states "edit it, do not add a second resource",
  and adds a pre-hand-apply guard: `terraform state list | grep -c ruleset` must be **1**, and any
  `create` line in the per-address query means stop. The checker written to validate that block also
  needed fixing: it flagged `for_each` as an unknown attribute because Terraform meta-arguments are
  language syntax, not provider schema — a false positive on the correct HCL, now allowlisted.
- The detector half **landed while this entry was being written: PR #99 squashed into `main` at
  `2ce3241`**, and the record was updated to say so instead of keeping the "open and unmerged as
  this is written" phrasing past the merge. Verified against live state rather than the merge
  banner: `drift_detect.py` now prints `protect-main: no pull_request rule (no PR is required on
  main)` for consent and `INFO: … ruleset observation: … strict_required_status_checks_policy=false`
  for dr and vendor, aggregate verdict still exit 1 with the same two repos in `weakened`; the
  merged branch runs **321 passed** (316 + #99's 5).
  `drift_detect.py` asserted nothing about whether an active branch ruleset carries a
  `pull_request` rule (D-84 residual (2)) *and* discarded every note it computed for a repo that
  cleared the context floor: a live `jolarca-dr` read found `strict_required_status_checks_policy
  =false` computed and printed nowhere. The two are coupled — asserting the rule without fixing the
  discard would have produced a detection nothing could read, since a ruleset can carry enough
  contexts while requiring no PR at all. 5 fixtures, proven red first (**4 failed / 29 passed**),
  suite **316 → 321**; drift's live verdict is unchanged (exit 1; consent and vendor were already
  findings) while consent now reports `no pull_request rule (no PR is required on main)`. `strict`
  is surfaced as an *observation*, not a finding, because `policy/repo-defaults.yml` declares no
  `strict` key and `test_protection_404_with_ruleset_requiring_contexts_is_not_drift` is a recorded
  decision, not an oversight. A self-caught defect rode along: `ruleset_covers_branch` returned
  `True` for a `target = "tag"` ruleset (no `ref_name`), which my new assertion would have turned
  into a false finding — proven red, then guarded.
- **Not closed:** consent's `main` is still directly pushable — this makes the remedy executable,
  it does not execute it. `terraform import` / `state rm` remain the operator's (§5); step 4 is
  refused by the brake by design and is applied by hand; and `repo_readiness_audit.py`'s `G-12c`
  probe is still behind the empty-repository `return`.
- **A claim this entry got wrong, corrected during its own review.** Step 4's precondition as
  written told the operator to resolve consent's three ruleset-inexpressible declaration keys "or
  `make drift` stays permanently red". That consequence was copied verbatim from D-84 residual (3)
  and reproduced here **without testing it** — the exact failure mode §7 warns about, one edit after
  writing a rule about it. Simulated against `drift_detect.py` using consent's own seven declared
  contexts: the ruleset path never reads `restrict_pushes`, `require_conversation_resolution` or
  per-rule `enforce_admins`; it compares required status checks, the `pull_request` rule,
  `non_fast_forward` and `deletion`. Consent clears once step 4 adds **both** `pull_request` and
  `required_status_checks` with ≥1 context — either alone still reports the other, and
  `strict=false` after step 4 yields an observation, not a finding. So the keys are **not** a
  prerequisite for step 4. What this bullet then said *in place of* that consequence was itself
  wrong — it claimed an adopted ruleset "cannot carry" `restrict_pushes` **and**
  `require_conversation_resolution`; see the two bullets above, `require_conversation_resolution`
  is expressible under a renamed attribute. The gate that reads those registry keys,
  `repo_readiness_audit.py`, is invoked by no workflow — so it cannot redden CI at all.
  Both D-84 and D-87 now carry dated corrections rather than deleted claims, and each correction
  names the method error that produced the wrong one.
- Files: `docs/state-migration-runbook.md` (Step 6b), `docs/drift-findings.md` (**D-87** + dated
  status on D-84 residual (2)), this entry. None is in `EVIDENCE_DIRS`, so no re-registration was
  required — verified by `grep -c` against the registry returning **0**, not assumed.
  `check_findings_register.py --cross-pr` exits 0 over **86** headings; `hash_evidence.sh --check`
  46 files / 0 mismatches.

### Fixed — 2026-10-26 (D-85: three governed records asserted a freeze that existed on no branch; D-86: `make` cannot carry the exit-code convention)

- Started repo 2 by reading its **committed** tree instead of this register. At
  `jolarca-infrastructure` `8f02d17` (public `origin/main`) `variable "org"` still
  defaults to `journeyoflife-org` in root and module, `module "github_org"` is live,
  the environment has no committed `terraform.tfvars`, `git grep -n lifecycle HEAD --
  environments/production modules/github-org` returns nothing, `git log --all -S
  "FROZEN — DO NOT PLAN OR APPLY"` returns **0 commits**, and
  `variables.tf.bak.20260831-2306` is still tracked — while D-06 said "Fix applied …
  see working-tree diff", D-13 said "`prevent_destroy = true` on every
  `github_repository` … Resolved", and the migration runbook said "COMPLETE
  (2026-10-10)". The fix was real and uncommitted: 9 dirty entries, +133/−98.
- Not hypothetical: that repo's `terraform.yml` runs a `plan` job on every
  `pull_request` touching `terraform/**`, and runs `39925547516` / `39925560368`
  (2026-10-23) **succeeded**, posting `Plan: 16 to add, 0 to change, 0 to destroy` on
  public PRs while the default named the mission-platform org. `apply` is gated to
  `workflow_dispatch`, which is the only reason nothing was written.
- Landed the freeze as `jolarca-infrastructure` **PR #49** (`2eab214` moves the
  on-disk change into history verbatim; `693ec82` adds the `.github/CODEOWNERS` that
  repo's required `compliance` context demands — the only fleet repo missing it, which
  is the mechanism that made every PR there fail with `enforce_admins = true` removing
  the bypass, i.e. nothing could merge since 2026-08-31). Both GPG-signed; `ci`,
  `security` and `compliance` now **pass**, `apply` **skipping**, PR **open**. No
  Terraform command was run in that root by this change.
- `docs/state-migration-runbook.md` step 1 rewritten to verify the committed tree
  (`git show origin/main:…`, `git grep … origin/main`) — its own acceptance check had
  been grepping a working tree, which is why it printed "expected" for a month — plus a
  note on reading `grep` exits and a caveat beside the "COMPLETE" status line: the
  legacy state is serial **37** with one live address
  (`github_repository_file.security_md`, `instances: 0`) and 8 stale copies on one host.
- D-06 and D-13 carry dated correction rows; the original text is kept, not deleted.
- D-86: `repo_readiness_audit.py --repo jolarca-data` exits **1** while
  `make readiness REPO=jolarca-data` exits **2**; a synthetic `@exit 1` target also
  gives 2, so GNU make cannot convey `1` and no `make <gate>` distinguishes findings
  from "could not verify". The `readiness` and `first-commit` recipes also sent stdout
  to `/dev/null`, discarding the detail while the stderr table survived — verified: the
  same target now prints 7849 bytes where it printed 85. AGENTS.md §2/§3 now state that
  the three-valued code lives on the script and evidence collection must call it
  directly; no script's own exit codes were altered to suit the wrapper.
- AGENTS.md §5's rationale for the no-apply boundary was stale ("state is owned by
  `jolarca-infrastructure` until the migration runbook completes"); the rule is kept and
  re-justified. §7 gains the rule that a fix claim must be verified against the artifact
  that carries it.
- Audit records: FA-control-14 flipped to `implemented` with a top-level
  `fixes_landed_pr97` block (PR #97 → `main` = `a720789`; fresh clone: 29 plan-gate
  fixtures, 18 gate scripts, 83 headings, 46/0 evidence, 316 tests, gitleaks clean, no
  `Terraform Apply` run — fourth consecutive merge with nothing armed). Added
  **FA-control-15** (S1) and **FA-control-16** (S2); control plane 16 controls,
  fleet totals re-derived by parse: **39 findings (1 S0 / 17 S1 / 19 S2 / 2 S3)**.
- `index.md`'s header claimed PR #85 was `OPEN, mergeStateStatus=BEHIND`; it is
  **CLOSED**, and the baseline row now reads `a720789`.
- Two of this session's own measurements were wrong in the direction that made a true
  claim look false — a repo-wide `prevent_destroy`/`FROZEN` grep that matched
  `modules/state-bucket` and bucket-name prose, and `grep -c "gh api -X PATCH"`
  returning 0 while f-strings emit four PATCH remediations. Recorded in method note 1
  rather than quietly re-run.

### Fixed — 2026-10-26 (D-84: the pre-apply brake could not see rulesets, and D-46's decision is now recorded)

- `scripts/check_plan_safety.sh` refused branch-protection creates and every protection
  attribute change, and mentioned rulesets **zero** times (`grep -ic ruleset` → 0) — while
  `jolarca-consent`, `jolarca-dr` and `jolarca-vendor` are protected *only* by rulesets
  (`terraform state list` → 14 `github_branch_protection`, 0 ruleset addresses).
- Blindness proven by feeding the unfixed gate plans, not by reading its patterns. Three
  synthetic renderings all exited **0**: a `github_repository_ruleset … will be created` block
  with only `deletion`/`non_fast_forward`; the same address `will be updated in-place` with
  `enforcement = "active" -> "disabled"`, both push rules turned off and a new
  `bypass_actors { actor_type = "RepositoryAdmin" }`; and an org-ruleset weakening. The middle
  one strips protection from a tier-1 GDPR repository, over the printed words "no …
  protection-layer change", with `apply.yml` ready to run `terraform apply -auto-approve`.
- Four refusals added: create by address, every other action by address, a resource-header belt,
  and a ruleset-only attribute vocabulary. Ruleset changes are refused in **both** directions —
  unlike the security-feature rule, which allows enabling — because requiring a context no
  workflow reports deadlocks every merge on that repo (`jolarca-identity` paid for that once,
  D-44/D-47). Generic tokens a ruleset also owns (`update`, `creation`, `deletion`, `include`,
  `exclude`, `target`, `name`) are deliberately not listed: a gate that refuses unrelated plans
  gets bypassed (§5).
- `tests/test_check_plan_safety.sh`: 4 new cases, **29 passed** (was 25). Includes the
  non-vacuity control `ruleset-refresh-only-noise` → 0, using Terraform's real
  `Refreshing state... [id=24087580]` line, so the step-6b adoption plan can pass its own gate.
  Run against the unfixed script the three refusal cases printed `FAIL … want exit=1 got=0`.
- A defect in the fix was caught by `make lint`'s own `sh-lint`: the refusal reasons are
  double-quoted shell arguments, so backticks in them were command substitution — a 0-byte file
  named `disabled` had appeared in the working tree. Rewritten with single quotes.
- **D-46 decided (option A) and staged, nothing executed.** Live ruleset bodies re-read today:
  consent has three push rules and **neither** `pull_request` **nor** `required_status_checks`
  (7 declared contexts enforced by nothing; `main` directly pushable); vendor's status-checks
  rule carries an **empty** context list; dr requires `[lint, gitleaks]` strict false. Provider
  6.13.0 can express the missing checks but does not model `dismissal_restriction` /
  `require_extra_approval_for_unattributed_changes` that are live in dr/vendor, and cannot
  express `restrict_pushes`, `require_conversation_resolution` or per-rule `enforce_admins` that
  these repos declare. **Corrected 2026-10-27, same entry, one day later: the last clause is wrong
  in two places** — `require_conversation_resolution` is `required_review_thread_resolution` on a
  ruleset and `enforce_admins` is the absence of `bypass_actors`; only `restrict_pushes` has no
  attribute, and a `pull_request` rule subsumes it. See **Step 6b 4b** for the mapping.
  Import id read from provider source (`parseID2` splits on `:`):
  `<repo>:<ruleset_id>`. Sequence, ready HCL and verification commands: `docs/state-migration-runbook.md`
  **Step 6b**; `terraform import` stays operator-run (§5). Option B (delete the rulesets) was
  rejected because CI has never reached the HCP workspace (D-82), so the unprotected window is
  unbounded rather than minutes.
- Records: `docs/drift-findings.md` D-84 + D-46 decision packet, `AGENTS.md` §7 (new coverage
  rule) and §8 (ruleset bullet), fleet-audit `FA-control-14` (S2) with the index totals re-parsed
  to 14 control-plane controls / 37 findings.

### Fixed — 2026-10-26 (D-83: `make lint` did not run the formatter step the CI Lint job runs)

- Found while reviewing D-81, not looked for: `make lint` exited **0** (313 passed) on a branch where
  `ruff format --check scripts/ tests/` — a step the CI `Lint` job runs — reported
  `1 file would be reformatted, 24 files already formatted` (13 hunks, all in the new
  `tests/test_check_apply_path_trigger.py`). `Makefile` describes `lint` as "Everything CI runs
  before a plan".
- **This entry was first written as an S2 absence — "nothing local runs the formatter" — and that
  was wrong.** `.pre-commit-config.yaml` declares `id: ruff-format`, the hook is installed
  (`.git/hooks/pre-commit`, 2026-09-26), `pre-commit run --all-files` passes all twelve hooks, and the
  commit attempt that prompted the check was itself refused by `end-of-file-fixer`. The formatter has
  a local enforcer; what it did not have was a place in the surface AGENTS.md §2 documents and agents
  are told to run. Graded **S3** on the measured premise.
- Fixed by `py-fmt-check`, now a `lint` prerequisite: a gate **strengthened**, never weakened (§5),
  and free at CI, which already ran the same command.
- Corrected a second stale claim in the same AGENTS.md §2 sentence: it asserted CI runs
  `repo_readiness_audit.py --no-live`. `grep -rn readiness .github/workflows/` matches only comments —
  that audit is local-only (`make readiness`) — while `compliance_check.py` genuinely is invoked
  (compliance-scan.yml:199, apply.yml:160). The instruction to run `make compliance` before pushing
  stands; the readiness claim was removed.
- Not fixed, and recorded rather than asserted: nothing compares the **three** surfaces — `make lint`,
  the pre-commit hooks, and the CI jobs — in any direction. `check_gate_parity.py` R2 asks whether a
  fixture that exists is invoked in CI; no control asks whether every command appearing in one list
  appears in the other two. Open as **FA-control-13** (`status: gap`), because writing that rule is
  itself a gate change needing its own negative control.

### Added — 2026-10-26 (D-81: an unattended PR cannot arm the production apply)

- `apply.yml` fires on `push: main` for `repos/**`, `policy/**`, `*.tf`, `*.tfvars` and **itself**,
  then runs `terraform apply -input=false -auto-approve tfplan`. Because §5 requires actions to be
  pinned to a full SHA, the pins live *in the workflow files* — so a dependency bump can edit an
  apply-path file. Measured: `gh pr diff 87 --name-only` (setup-python 7.0.0→7.1.0) and
  `gh pr diff 68 --name-only` (upload-artifact 7.0.1→7.0.2) **both list `.github/workflows/apply.yml`**.
  Merging either would start a whole-state apply that no person read, with
  `required_approving_review_count = 0`; D-58 already records that the 30-minute wait is delay, not
  approval.
- New required-context step `An unattended PR must not arm the production apply (D-81)`
  (`scripts/check_apply_path_trigger.py`, `pull_request` events only). The trigger set is **read from
  `apply.yml`'s own `on.push.paths`** (T1) rather than duplicated, and GitHub `paths:` glob semantics
  are implemented (T2: `*`/`?` do not cross `/`, `**` does) — `fnmatch` was rejected because its `*`
  crosses `/` and `*.tf` would fire on `modules/x.tf`, i.e. on changes that cannot trigger anything.
  Verdict is asymmetric on purpose: **bot/app → exit 1** (refused pre-merge, where a human can still
  author the same diff deliberately — so this is *not* the dependency-bump deadlock class), **human →
  exit 0 with a `NOTICE`** (refusing Terraform work would manufacture the A-01/FA-control-03 deadlock).
  Missing, empty or unreadable diff and unparseable `apply.yml` are exit **2** (T3); an unknown author
  kind is judged only when a path matches, then exit 2 (T4); a trigger set the script cannot model
  (`!` exclusions, `paths-ignore`) is exit 2 rather than approximated (T5). Fixtures:
  `tests/test_check_apply_path_trigger.py` (21 collected), including the real file lists of #87/#68 and
  the real D-80 PRs (which must read clean).
- Two defects found before wiring, both recorded in D-81: `path.lstrip("./")` is a character-set strip
  and silently unmatchable `.github/workflows/apply.yml` — caught by running the gate against live
  `gh pr diff` output, where it reported "no apply armed" on exactly the PRs to refuse; and
  `gh pr view --json author --jq .author.type` returns an empty string (the GraphQL `author` node has
  no `type`), so the CI step reads `github.event.pull_request.user.type` from the event payload.
- A third defect was in the gate's own plumbing. The step calls
  `gh api repos/…/pulls/<n>/files` from the `validate` job, and a job-level `permissions:` block sets
  every scope it does not name to `none` — so the workflow's `pull-requests: read` did not reach it,
  the call would 403, and a **required context would have failed on every PR in the repository**.
  `pull-requests: read` is now restated at job level, pinned by a fixture that reads the workflow YAML
  and was proved by deleting the line (`assert None == 'read'`). The workflow comment claiming the
  scope was unused by the required step was corrected in the same edit.
- New `make apply-path-trigger` (not a `lint` prerequisite: it needs a branch-relative diff that a
  detached checkout may not have).

### Fixed — 2026-10-26 (D-82: the credential register's unreadable expiry is now measured, and D-77 narrowed)

- `docs/security/key-custody.md`'s `TFC_TOKEN` row said "read the actual expiry in the HCP UI". That
  is still the only source of the date, and the row now records *why*, from reads rather than
  assumption: the operator's own `~/.terraformrc` CLI credential returns **HTTP 200** on
  `/api/v2/organizations` (lists `jolarca-dev`) and `/api/v2/account/details`, while the token-expiry
  routes (`organization-tokens`, `organization-token`, `teams/owners/team-tokens`, `state-versions`)
  answer **HTML 404** — a route that resolves nothing, which is not evidence that no organization
  token exists. The gate's verdict is unchanged and re-measured after the edit: exit 1,
  `::error::expiry unknown …`. No date was invented.
- Same read closes D-77's missing positive control and adds a fact: `…/workspaces/jolarca-control/runs`
  contains **three runs, all `Triggered via CLI`, none from Actions**, since the org was created
  2026-10-10 — so the CI path has never reached HCP at all, and `resource-count: 48` is what the last
  CLI run left. D-77 stays OPEN (operator-side); the search space is now much smaller.
- `docs/runbooks/github-token-rotation.md` gains "What the HCP API can and cannot tell you" with the
  endpoint table and the instruction not to pad the expiry, so the next session does not re-run the
  inert 2026-10-19 differential.

### Added — 2026-10-26 (D-80: every gate must have a control, and every control must run)

- New required check `scripts/check_gate_parity.py`, running inside `Validate Repo Allow-List`
  (one of the four live required contexts, `strict=true`), so it blocks a merge rather than
  advising. Rules: **R1** every `scripts/*.{py,sh}` needs `tests/test_<name>.{py,sh}`;
  **R1b** that fixture must name its subject (a placeholder is not a control); **R2** every
  `tests/*.sh` must be invoked by a `run:` step in a workflow that can trigger on
  `pull_request` — `pytest tests/` collects `.py` and cannot collect `.sh`, and a fixture that
  only runs after the merge is a report; **R3** every script must appear in a Makefile recipe
  or a parsed run step, with comment lines stripped from both corpora; **R4** the tolerated
  no-fixture baseline may only shrink, and a stale entry fails. Three-valued per AGENTS.md §3:
  unreadable input or an unparseable workflow exits 2, never 0.
- Why a rule and not three more files: AGENTS.md §7 (negative controls) and §3 (exit codes)
  were prose, enforced by nothing. `scripts/check_secret_inventory.sh` landed from PR #86 on
  2026-10-20 with no fixture and no invoker (`git grep -n check_secret_inventory origin/main --
  Makefile '.github/workflows'` → exit 1), and `tests/test_check_workspace_execution_mode.sh`
  (13 passing cases) ran only via `make test`. A gate designed to be red, wired to nothing,
  reports green forever.
- Fixtures: `tests/test_check_gate_parity.py` (18 cases) and
  `tests/test_check_secret_inventory.sh` (19 cases). Two defects in the gate were found by its
  own fixtures and fixed: a `continue` after a baseline hit also skipped liveness — a baselined
  **and** unwired script produced no finding at all — and raw text matching let a comment
  satisfy liveness. New targets: `make gate-parity` (in `lint`) and `make secrets-inventory`
  (deliberately not in `lint`; a permanently-red local gate trains everyone to add `|| true`).

### Fixed — 2026-10-26 (D-80: a dead default path in the credential-expiry gate)

- `scripts/check_secret_inventory.sh` defaulted to `docs/SECRETS_INVENTORY.md`, a file that has
  **never existed** (`git log --all --diff-filter=A -- docs/SECRETS_INVENTORY.md` → 0 lines), so
  run as documented it exited 2 every time and nobody saw it, because nothing invoked it. The
  default is now `docs/security/key-custody.md`, which `:33` already named as "the single
  `expires`-bearing block the gate parses". Against the real register it now reports its intended
  verdict: two dated rows `ok` (2027-01-08, 2027-01-15) and `::error::expiry unknown` for
  `TFC_TOKEN`, exit 1 — red by design until the operator records the actual date.
- Wired into `deploy-gates.yml` as an **advisory** step ("Deploy Gates" is not a required
  context), because promoting an intentionally-red check to a required context would wedge every
  PR. It reads one markdown table and prints metadata only: offline, credential-free.
- When that red is visible, stated rather than left to be discovered: `deploy-gates.yml` is
  path-filtered (`apply.yml`, `deploy-gates.yml`, `scripts/check_deploy_gates.py`) plus a
  Wednesday 08:00 UTC schedule and `workflow_dispatch`, so the signal runs on PRs/merges touching
  those files and weekly — not on every PR. A Dependabot PR bumping an action inside them now shows
  a red `Deploy Gates` (measured on #87: required contexts all green, `mergeStateStatus=BEHIND`,
  so nothing blocks). Promoting the job to a required context before `TFC_TOKEN` carries a real
  date would fail every such bump — the precondition is the dated row, not a weaker gate.

### Added — 2026-10-19 (D-79: data stores outside git are now registered)

- `docs/data-classification.md` gains a **Data stores outside git** section: Terraform
  state, the age-encrypted state backup, the application's S3-compatible object store and
  the marketplace database, each with classification, where it is configured and its
  measured status. Until now the policy enumerated repositories only, so the store that
  `jolarca` ADR-0005 names as holding **KYC identity documents and invoice PDFs** appeared
  nowhere in the control plane an auditor reads (GDPR Art. 30/32, PCI-DSS Req 3.5.1).
- New rule in that file: a data store is registered before it holds regulated data,
  mirroring the existing rule that a repository is classified before its first commit.
- The same file's repository table was **stale since `5a571ef` (2026-09-26)**: six
  repositories, five declared `confidential`/`private`, a claim that it matched
  `repos/*.yml` "exactly", and a blockquote citing **D-01** as an open blocking decision.
  Measured instead: 16 entries, every one `visibility: public`, classifications
  `internal` ×14 + `public` ×2 (`jolarca`, `jolarca-docs`). Corrected, with the superseded
  text kept as a dated historical note and the command to reproduce the table recorded.
- Answered by measurement and recorded, **not** changed: no AWS provider or S3 backend
  exists anywhere in the fleet (ADR-0006's rejection of S3 + DynamoDB stands), and the
  sibling `jolarca-infrastructure` GCS custody stack is **half-applied** — CMEK keyring/key
  and a service account in state at serial 11, `google_storage_bucket.state` and
  `.state_logs` never in state, no `production` bootstrap workspace. `gcloud storage ls`
  cannot authenticate from here, so whether those objects exist outside Terraform's record
  is logged as **could-not-verify**, never as "absent". No bucket, provider, credential or
  `*.tf` change is made by this entry — destination and key custody remain the owner's
  decision under AGENTS.md §5, and D-02/D-55 stay open.

### Fixed — 2026-10-19 (D-78)

- `plan.yml` ran `terraform plan -detailed-exitcode` under the Actions default `bash -e {0}`, so a
  plan with changes (exit 2) aborted the step before `Plan safety check` could read it, and
  `Fail on plan error` tested an output that could never be set. Now `shell: bash {0}`: the
  refusal gate runs on every plan the job produces. `apply.yml` never had this defect — it plans
  without `-detailed-exitcode`.
- `scripts/check_plan_safety.sh` exited **0** ("safe to auto-apply") on input that is not a
  rendered plan: the workflow's own `Record skipped plan` prose, and a bare
  `Error: Failed to read organization … unauthorized` block. Non-plan input is now exit 2
  (could-not-verify), ordered **after** the refusal rules so it cannot mask a real refusal. This
  also guards `apply.yml`'s pre-apply `terraform show` output — the D-74 version-skew case.
- `Comment plan on PR` no longer fails with `Either message or path input is required` when init
  died; gated on the file existing via `[ -s ]` rather than `hashFiles()`, because
  `plan-output.txt` is gitignored and hashFiles skips ignored paths.
- Negative controls first: `tests/test_check_plan_safety.sh` 22 → 25 cases, both new refusals run
  red (`want exit=2 got=0`) before the fix, plus a non-vacuity case so the guard cannot quietly
  start failing honest plans closed.

### Corrected — 2026-10-19 (D-76, D-77)

- The D-76 entry below is **incomplete as written**. Moving `plan.yml` onto
  `TF_GITHUB_TOKEN_READONLY` did not by itself let the plan read the fleet: the PAT then answered
  `403 Resource not accessible by personal access token` on all sixteen repositories until
  **Administration read** was granted to it. There is no `Vulnerability alerts` permission on a
  fine-grained PAT — GitHub lists `GET /repos/{owner}/{repo}/vulnerability-alerts` under
  Repository permissions → **Administration** (`read`; `PUT`/`DELETE` are `write`). Both scope
  tables (`docs/runbooks/github-token-rotation.md`, `docs/state-migration-runbook.md`) named the
  phantom scope and are corrected; `Contents read` is dropped, since both `github_repository_file`
  resources are commented out.
- **D-77 opened:** `TFC_TOKEN` now fails `terraform init` with `Failed to read organization
  "jolarca-dev" … unauthorized`, while the secret's `updated_at` is unchanged since it was placed
  — the credential stopped working, not the workflow. Cause is not established: the three-endpoint
  status probe written during this investigation was refuted by its own negative control (a
  garbage token and no token at all produce the identical pattern), so recovery needs a positive
  control, not more classification. `Validate & Plan` is **not** one of the four required contexts,
  so this does not block merges — it removes the PR-time plan-review signal entirely, which is the
  more serious reading.

### Fixed — 2026-10-17 (D-76)

- `plan.yml` handed Terraform the runner-scoped `secrets.GITHUB_TOKEN`, which cannot read the
  fifteen sibling repositories: every PR-mode plan failed with `403 Resource not accessible by
  integration` on `github_repository_vulnerability_alerts`. It now uses
  `secrets.TF_GITHUB_TOKEN_READONLY` — read scope for a read-only job.

### Added — 2026-10-17 (deployment gate)

- `production` now requires a **deploy reviewer** (`prevent_self_review: false`, the single
  org member), alongside the existing 30-minute wait. Recorded as **D-75**. This is an intent
  checkpoint with a recorded approval, not separation of duties — D-58 remains open.
- `scripts/check_deploy_gates.py` reached its fully-green path for the first time:
  `OK: 1 environment(s) examined; 1 gated`.

### Removed — 2026-10-17

- The dated allowance `ALLOW_UNPROTECTED_ENVS` / `ALLOW_UNPROTECTED_UNTIL` (expiry 2026-11-16)
  in `.github/workflows/deploy-gates.yml`, per that file's own instruction to delete it once
  reviewers exist.

### Changed — 2026-10-17 (credential placement)

- `TF_GITHUB_TOKEN` moved from a repository Actions secret to an **environment** secret on
  `production`, matching `docs/security/key-custody.md` and
  `docs/runbooks/github-token-rotation.md`. The inert org-level duplicate on `jolarca-dev`
  was deleted after proving it unreachable (`visibility: private`, no private repositories).
- Recorded as **D-74**: the 19 residual plan changes were applied out-of-band from the host,
  which consumes the sequencing brake D-56 relied on. `policy/repo-defaults.yml` `Req_8_2`
  no longer claims signed commits as a control — enforcement is off (`D-05`).

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

### Fixed — 2026-10-17 (eleventh batch: D-73 — ids cited across the repo with no row defining them)

- **`D-56` was cited 17 times and had no row.** Neither did `D-57` (3 citations) or `D-53` (8).
  `D-64`'s own title reads "D-56's actual root cause found and fixed". The definitions existed only on
  unmerged PR #67. `check_findings_register.py` (#51, landed 2026-10-17) answers "is this id used
  twice?" and was silent on "is this id used but never written?" — the class survived the guard built
  for its neighbour. Measured with `git grep -c D-56` per file against a heading scan of the register.
- **The 2026-10-12 section salvaged from #67 into the register** (`D-54`, `D-55`, `D-56`, `D-57`),
  each row carrying a dated *status at salvage* block corrected against measurements since: D-55's
  headline is fixed by the `state_backup.sh` rewrite (schedule and off-host destination are not);
  D-56 is scoped to the CI credential only (the `-backend=false` half landed as D-64); D-57 is split
  three ways (fixed / accepted-deviation / pending step-6 row 14). A `D-53` row was added to close its
  8 dangling references. #67's own `D-58` was deliberately **not** imported — `main`'s row is
  authoritative, and importing a second one would recreate the duplicate the guard detects.
- **New check `find_dangling_references()`**: every `D-nn` cited in tracked text needs a heading;
  `tests/` and `staging/` excluded because fixtures cite synthetic ids; register headings count as
  definitions not citations; an unusable file list lands on exit **2**, never a pass (§3). Runs in
  every mode including the required CI step, and `ROOT` is read at call time so a fixture can point it
  at a throwaway repo instead of silently scanning the real tree.
- **It flagged this changeset's own forward references**: a citation to the dead-pointer finding that
  exists only on unmerged PR #79, a synthetic fixture id named literally in the guard's comment, and
  its own id before its row was written. All three were rewritten to name a file or PR rather than
  padding the register to satisfy a tool.
- **One of my test assertions was wrong, not the gate**: the fixture must expect `D-56` to be reported
  dangling (it is undefined in that throwaway register) and a defined id never to be. Caught by
  running the suite rather than reasoning about it.
- Register parses clean: `OK: 72 ### D-nn headings parsed, no collisions, no dangling citations`.
  Consequence for #67: it can now be closed, because the only part of it `main` lacked was findings
  text, and that is here.

### Fixed — 2026-10-16 (ninth batch: D-71 reconciliation, part 1 — PR #41 landed, and D-58 finally has a row)

- **PR #41 rebased onto `main` and landed.** `scripts/check_deploy_gates.py` + `deploy-gates.yml` +
  17 fixtures. Its second commit was kept, not skipped: it fixes an output bug where one environment
  failing two rules printed two identical exemption notes next to a summary claiming "1 allowed" —
  the log and the total disagreed about how many objects existed.
- **A finding-ID collision, resolved rather than merged blind.** PR #41 wrote its finding up as
  `D-52` on 2026-10-05; `main` had already allocated D-52 to "Privating a governed fleet repo blinds
  the control plane". The rebase conflict surfaced it, and the row was renumbered to **D-58** — the id
  that `audit/soc2-checklist.yml`, `audit/pci-dss-checklist.yml`, `policy/compliance-gates.yml`,
  `Makefile` and `CHANGELOG.md` had all been citing **for a row that did not exist**. D-58 now has one.
  This is the failure mode PR #51's `check_findings_register.py` guards, met while reconciling the queue
  it belongs to.
- **The gate is on the merge path, not advisory.** It runs as a step inside the required
  `Validate Repo Allow-List` job (D-67's pattern: no fifth required context, therefore no
  branch-protection change). Against live state it exits **1** —
  `rules are ['wait_timer'], with no required_reviewers, so no human approves the deploy` — which is
  correct, because D-70 is delay and not approval. So the fix was a dated allowance, not a weaker rule:
  `ALLOW_UNPROTECTED_UNTIL: 2026-11-16` in both workflows, plus a real entry in
  `policy/compliance-gates.yml` `exceptions.active` with `approved_by`, `approved_on`, `expires` and an
  `exit_trigger`. An expired allowance fails again by itself (D-25).
- **Two stale claims about the apply path corrected at the source:** `apply.yml`'s header no longer says
  "manual approval gate" (it now states what the environment actually holds and names the gate that fails
  if it regresses), and `check_deploy_gates.py`'s docstring no longer describes `production` as having no
  rules or `STATE_MIGRATION_COMPLETE` as unset.
- **A trap recorded for the next reader:** the workflow told the operator to "enable prevent
  self-review". In a one-member organisation that option would wedge every deploy, so it is now explicitly
  forbidden in the exemption comment and in the exception's `exit_trigger`; whether solo self-approval is
  otherwise permitted remains measured-as-unknown, not asserted.

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
