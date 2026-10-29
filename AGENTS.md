# AGENTS.md — operating rules for AI agents in this repository

Versioned source of truth for how changes are made here. If an agent's memory and
this file disagree, **this file wins** — memory is a cache, not a record. Changes
to this file go through the same PR flow as any other governed artifact.

Scope: `jolarca-control`, the marketplace (`jolarca-dev`) governance control
plane. Public repository. Sole operator, no teams (ADR-0004 R4).

---

## 1. Non-negotiable workflow

```
VERIFY FIRST → COMMIT → PUSH → REVIEW → MERGE → VERIFY AGAIN
```

- Verify empirically. A tool's summary, a prior report, or an agent's own claim
  ("file updated successfully") is **not** evidence. Command output is.
- Search results are claims too. A grep that returns "no matches" or a truncated
  result set has not proven absence — read the file before asserting a defect.
- Re-verify after merge. Live state, not the merge banner.
- Never infer approval from a previous conversation. Approval lives in a dated
  record (`policy/compliance-gates.yml` `exceptions.active`) or it does not exist.

## 2. Commands

Setup and gates (all offline unless marked live):

| Command | Purpose |
|---|---|
| `make setup` | Create `.venv`, install pinned deps |
| `make lint` | fmt-check, tf-validate, validate, context-baseline, gate-parity, ruff check **and** `ruff format --check`, mypy, shellcheck, yamllint, tests. **Not** all of CI — see below |
| `make test` | Plan-safety fixtures + `pytest` |
| `make validate` | Validate `repos/*.yml` against policy |
| `make context-parity` | Declared contexts must be checks each fleet repo can report (live, `gh`) |
| `make context-baseline` | The `required_checks` policy baseline must equal the declaration AND be producible on a PR (D-62; offline) |
| `make backup BACKUP_DEST=<dir>` | Off-host age-encrypted state export, **with the decrypt round trip proven before it says OK** (D-02) |
| `make readiness REPO=<name>` | Pre-first-commit verdict: READY / READY-WITH-FIXES / BLOCKED |
| `make first-commit REPO=<name> STEP=A..F` | Read-only pipeline gate; prints commands, never runs them |
| `make evidence-check` | Verify evidence hashes against the **committed** registry |
| `make evidence-register` | Regenerate `docs/evidence-registry.csv`, then commit the diff in a PR |
| `make gate-parity` | Every gate must have a fixture that can fail, and every fixture must run on the merge path (D-80; offline) |
| `make apply-path-trigger` | Would this branch's diff arm a production apply, and is the author a bot? (D-81; reads `apply.yml`'s own `on.push.paths`) |
| `make drift` / `make fleet-audit` / `make org-audit` | Live, read-only (need `gh` / token) |

Run Python through the venv: `.venv/bin/python -m pytest tests/ -q`. The system
`python3 -m pytest` can exit 1 with no output, which reads as a mystery failure.

**`make lint` is not the whole CI surface.** `compliance-scan.yml` additionally
runs `scripts/compliance_check.py` (`make compliance`; also `apply.yml:160`), and that
one is not in `lint`. Run it before pushing, or CI will surface failures the local
gates never checked. The same sentence used to claim `repo_readiness_audit.py --no-live`
runs in CI too — it does not: measured 2026-10-26, `grep -rn readiness .github/workflows/`
matches only comment lines, and the audit is invoked solely by `make readiness`.
As of 2026-10-06 both required contexts pass on `main` (verified on PRs #42/#43);
§8 records the current control status.

The inverse gap existed too and is now closed (D-83, measured 2026-10-26): `lint`
claimed to cover the CI pre-plan surface while running no ruff formatter check, which
the `Lint` job does run — a branch passed `make lint` at exit 0 with a file that
`ruff format --check` wanted to reformat in 13 places. `py-fmt-check` is in `lint` now.
Say `lint` rather than "the local gates", because this repository has **three** overlapping
surfaces and compares none of them: `make lint`, the installed pre-commit hooks
(`.pre-commit-config.yaml` carries `ruff`, `ruff-format`, mypy, yamllint and terraform fmt,
and `pre-commit run --all-files` passes all twelve), and the CI jobs. A commit is checked by
the hooks; a session that only runs `make lint` never invokes them, and a fresh CI clone has
no hooks at all. Whether every command in one list appears in the other two is enforced by
nothing (FA-control-13, `status: gap`) — `check_gate_parity.py` asks the opposite question.

`make apply` is **REFUSED by design** (exit 1) and `make plan` prompts before an
offline `-refresh=false` plan. Do not "fix" either. Both read
`STATE_MIGRATION_COMPLETE` — and **that variable measures `'true'` today**
(`gh api repos/jolarca-dev/jolarca-control/actions/variables`, measured 2026-10-15),
so it is an OPEN gate, not a closed one: the refusal in the Makefile is local
only, and the CI apply path is live. What actually stands between a merge and an
apply is `scripts/check_plan_safety.sh` (see §8 and D-61).

## 3. Exit-code convention

Every gate in this repo is three-valued. Preserve this in any new gate:

| Code | Meaning |
|---|---|
| `0` | Verified safe / passed |
| `1` | Findings — a real refusal |
| `2` | **Could not verify.** Never a silent pass. |

An unreadable input, a missing baseline, or an unreachable API is `2`, not `0`.

**The three-valued code lives on the script, never on `make`.** GNU make returns
`2` for any failed recipe — proved, not assumed: a synthetic target that runs
`exit 1` also makes `make` exit `2`. So `make drift`, `make readiness`,
`make findings-check` and the rest cannot tell "findings" from "could not
verify", and two targets used to send their detail to `/dev/null` while the
surviving stderr table implied the gate had merely been terse (D-86). Automation,
evidence collection and any judgement that turns on `1` vs `2` must call
`.venv/bin/python scripts/<gate>` or `bash scripts/<gate>` directly and read that
exit code.

## 4. Change classification — route on blast radius, not diff size

A 3-line change here can be catastrophic; a 400-line docs change can be trivial.

**High blast radius** — requires a human-read plan and top-tier review, regardless
of size: `*.tf`, `*.tfvars`, `repos/**`, `policy/**`, `.github/workflows/**`,
`scripts/**`, `docs/evidence-registry.csv`.

**Lower blast radius:** `docs/**` (prose), `staging/**`, `audit/**` checklists.

Specific high-consequence edits:
- `repos/*.yml` `visibility` — a public/private flip is D-01 class: it changes
  what is publicly readable inside PCI-DSS/GDPR scope.
- `terraform.tfvars` `enable_branch_protection` — weakening fires D-26.
- Anything touching GitHub secret-scanning or push-protection configuration.

## 5. Hard boundaries

- **No `terraform apply` from this root.** The stated reason — "state is owned by
  `jolarca-infrastructure` until the migration runbook completes" — is **stale**:
  `docs/state-migration-runbook.md:3` declares the migration COMPLETE (2026-10-10),
  `STATE_MIGRATION_COMPLETE` measures `'true'`, and this root holds the state. The
  rule survives for the opposite reason: an apply here is *permitted* by CI and only
  stopped by `scripts/check_plan_safety.sh` and the operator's review (§8, D-61), so
  the local refusal exists to keep a human in front of a path that is no longer
  gated by the migration. See D-85 for what "the runbook says so" was worth while the
  freeze it claimed was uncommitted.
- **No `terraform state rm` / `state mv` / `import` by an agent.** Operator runs
  these; they are irreversible against a single local state copy (D-02).
- **No `gh api -X PATCH` for branch protection or repo settings.** Terraform is
  the source of truth; out-of-band PATCHes are silently reverted and create drift.
- **No `jol-*` / mission-platform references** in fleet files. ADR-0004 separates
  the mission platform from the marketplace; `make fleet-audit` enforces it.
- **No literal secrets or credential-shaped fixtures in tests or docs.** Push
  protection scans documentation, and a real-looking fixture can permanently
  S0-BLOCK the readiness gate. Use runtime-assembled synthetic values.
- **No new dependency, action, or tool version unpinned.** Dependencies pin in
  `requirements*.txt`; GitHub Actions pin to a full commit SHA with a `# vX.Y.Z`
  comment; ruff's rule set is pinned in `pyproject.toml` because its defaults
  move between releases.
- **Do not delete or weaken a gate to make CI pass.** If a gate is wrong, fix the
  gate and its fixtures in the same PR, and say so in the description.

## 6. Conventions

- Comments and documentation in English.
- Conventional Commits with a body that states *why*, not just *what*.
- Squash-merge PRs; keep history linear. Delete the feature branch.
- Match surrounding style. These files carry dense rationale comments explaining
  the defect that motivated them — that is deliberate, keep doing it.
- yamllint line length is 160 at **warning** level; prose-heavy compliance YAML
  is expected to warn. Do not reflow it to silence warnings.
- Documentation must state actual implementation status. Never describe a control
  as enforced when it is configured-but-inert or convention-only.
- Published contact addresses come from `policy/contact-addresses.yml` — define
  the role there, then point documents at it. Do not publish the base mailbox
  (D-60) and do not list any address whose delivery has not been tested: the
  fleet shipped `security@jolarca.com` as its disclosure channel in five repos
  while the domain had no MX record (D-59). Commit authorship uses the GitHub
  noreply form, not a mailbox, because commit metadata on a public repo is
  permanent publication.

## 7. Verification standards

- **Verify the verifier.** A gate that runs and reports green has not been shown
  to detect anything. Every gate needs a **negative control** — a fixture that
  must fail. `tests/test_check_plan_safety.sh` is the model (29 cases as of
  2026-10-26, including empty and missing plan — its own counter, not a
  hand-written number). An untested
  regex gate is a hypothesis: D-22 was an
  inline `visibility\s*:` pattern that never matched `terraform show` output, so
  the only control between an unattended apply and a fleet-wide visibility flip
  was inert.
  This rule is now itself enforced, by `scripts/check_gate_parity.py` inside the
  required `Validate Repo Allow-List` context (D-80, 2026-10-26): **R1** a new
  `scripts/<name>.{py,sh}` without `tests/test_<name>` fails the PR, **R1b** the
  fixture must name its subject, **R2** every `tests/*.sh` must be invoked by a
  `run:` step in a workflow that can trigger on `pull_request` — `pytest tests/`
  collects `.py` and cannot collect `.sh` — **R3** every script must be invoked by
  something executable (parsed `run:` bodies and Makefile recipes, comments
  stripped: prose is not an invocation), **R4** the no-fixture baseline may only
  shrink. Two self-caught lessons worth repeating: an exception that also silences
  a second rule is an off switch, and grepping for a filename cannot tell an
  invocation from a comment about it.
- **A gate's coverage is measured against the object classes it must see, not
  against its passing tests.** Before relying on any pattern-matched gate, ask
  which resource types it is structurally incapable of naming, and feed it one
  synthetic line of that shape. This found D-84: `check_plan_safety.sh` refused
  branch-protection mutations but `grep -ic ruleset` in it returned **0**, so a
  plan setting `enforcement = "active" -> "disabled"` on a ruleset exited 0 — and
  three fleet repos are protected by rulesets alone.
- **A gate's verdict must not depend on how its input was rendered.** Measured
  2026-10-15: the same Terraform plan file made `scripts/check_plan_safety.sh` exit
  0 when produced by `terraform show tfplan` (840 ANSI escape bytes) and exit 1 when
  produced by `terraform show -no-color tfplan` (0 escape bytes), because every
  pattern in that script anchors at line start and colour bytes sit in front of the
  `~`/`-` markers. Read plans with `-no-color`, and when you write a pattern-matched
  gate, make it refuse input shapes it cannot parse (exit 2) instead of reporting
  them as clean. CI passed only by accident there: `apply.yml` renders through
  `terraform show -json | jq -r`, which is plain text.

- **A claim about a fix must be verified against the artifact that carries it.**
  Measured 2026-10-26: three governed records (`docs/drift-findings.md` D-06 and
  D-13, `docs/state-migration-runbook.md` step 1) described a freeze as applied and
  in force while `origin/main` of the repo concerned still defaulted its provider
  `owner` to the other estate's organization, kept `module "github_org"` live, and
  carried no `lifecycle` block — the fix was real, and it lived only in one
  workstation's working tree (D-85). The runbook's own step-1 acceptance check was a
  set of `grep -n` commands on that working tree, so it printed "expected" and could
  not tell committed from typed. So: `git show origin/main:<path> | grep -n
  <marker>` and `git log --all -S '<marker>' | wc -l`, not `grep -n <marker>
  <path>`; and when a document's evidence line says "working-tree diff", read that as
  *not applied* — AGENTS.md §6 forbids publishing it any other way. Cheaper than
  either: read a fresh clone before you read a register.
- **Evidence must be retained to count.** Verification output that justified a
  merge is a deliverable, not a transient. Evidence files under `docs/adr/`,
  `audit/`, `policy/`, `repos/`, `docs/runbooks/`, `docs/security/` are hashed
  into the committed `docs/evidence-registry.csv`; edit one and re-register in
  the same PR or `make evidence-check` fails.
- **Read a gate's exit code before anything else runs.** Measured 2026-10-27: a loop of the form
  `printf '  %-40s rc=%s\n' "$(echo "$c" | cut -c1-40)" "$?"` reports **0 for a failing gate**,
  because bash expands the command substitution first and that substitution overwrites `$?`. A
  sixteen-gate sweep written that way printed every gate green while `hash_evidence.sh --check` was
  in fact exiting 1 — a false pass about evidence integrity, the exact class of thing §7 exists to
  prevent. Capture `rc=$?` on the line immediately after the command, then report; never let a
  substitution stand between the command and the read. This is the sibling of §3's "`make` collapses
  any non-zero to 2" and of D-86's recipes that sent their detail to `/dev/null`: the failure was
  real, the harness was the liar.

- **Do not trust a correct verdict.** A gate can report the right aggregate
  answer while silently skipping whole check families (an early `return` on a
  missing `.git` once skipped six filesystem checks and the entire secret sweep).
  Cross-check finding counts against an independent run.

- **A required status check must be proven PASSING, not merely producible.**
  `make context-parity` / `scripts/check_declared_contexts.py` answers one
  question: does a PR-triggerable workflow emit a job with this name. It does not
  answer whether that job can go green. Adding a context to a required list on the
  strength of exit 0 is how `jolarca-consent` was wedged (D-90): two of its seven
  declared contexts had been failing on its own `main` since 2026-10-15, so the
  moment the ruleset required them, **no PR could merge** — including the PRs that
  would have fixed them. Before requiring a context, read its recent history on the
  default branch and require observed successes:
  `gh run list --repo <r> --workflow <wf> --branch main --limit 5 --json conclusion`.
  Emission is necessary; satisfiability is what you are actually enacting.

## 8. Controls that are NOT currently enforced

Recorded so no agent assumes protection that does not exist. Verify live before
relying on any of these; details and expiries in `policy/compliance-gates.yml`.

- **Branch protection IS active on this repo's `main`** (verified 2026-10-06,
  legacy endpoint HTTP 200 at the time; re-proven 2026-10-12 when a direct `git push origin
  main` was refused with `GH006: Protected branch update failed` — "Changes must
  be made through a pull request" and "4 of 4 required status checks are
  expected"): `strict = true`, `enforce_admins = true`, **four** required
  contexts (`Validate Repo Allow-List`, `Policy Compliance Check`,
  `Repository Secret Pattern Scan`, `SAST (semgrep)` — the fourth was added by
  A-08 on 2026-10-08; this file said three until 2026-10-12),
  `required_approving_review_count = 0`. It is
  legacy branch protection created out-of-band, not a ruleset (this repo has none).
  Terraform holds the state now (D-02 backend migrated), and **most** protection
  rules are in state: `terraform state list` returns **14**
  `github_branch_protection` addresses on 2026-10-15 (`health[0]` plus
  `main["…"]` for 13 repos). Only `jolarca-consent`, `jolarca-dr` and
  `jolarca-vendor` are absent, and those three are what an apply would create —
  which `scripts/check_plan_safety.sh` now refuses until runbook step 6 is closed
  (D-61). This bullet previously claimed only `jolarca-hermes-agents` was in
  state; that was corrected by measurement, not by re-reading the runbook. The old D-33 Free-plan
  "cannot protect" rationale no longer applies here because this repo is public
  (corrects D-42).
- **`required_approving_review_count = 0`** — the sole operator can merge their
  own change (D-04, dated acceptance).
- **Tag protection is unenforceable** — release tags can be moved or deleted (D-07).
- **Open blocking findings.** The list in `exceptions.open_blocking` is stale in
  both directions and must be re-read before use. Measured 2026-10-12: D-01 is
  RESOLVED (GitHub moved the fleet public; every `repos/*.yml` now declares
  `visibility: public`), D-20's cross-org CODEOWNERS breach is FIXED though
  `require_code_owner_reviews` stays inert until `jolarca-dev` teams exist, and
  D-33 is closed (13 fleet repos now return a protection rule; `jolarca-consent`,
  `jolarca-dr` and `jolarca-vendor` return HTTP 404 "Branch not protected", so
  the first apply **creates** rules there). What genuinely still blocks an
  unreviewed apply is D-02's second half — the off-host state backup is inert
  (see the next bullet) — plus the unreconciled branch-protection declarations
  recorded in `docs/state-migration-runbook.md` step 6.
- **The state backup works when someone runs it — and that is all.**
  `scripts/state_backup.sh` had been dead since state moved to HCP Terraform: it
  read `$REPO_ROOT/terraform.tfstate` (0 bytes), so every run exited 1 and
  `docs/backup-log.tsv` never existed while the register cited it as the D-02
  interim control. Fixed 2026-10-15: it now pulls the current state version from
  the backend, encrypts to `$BACKUP_DEST`, and **decrypts and compares the
  SHA-256** before claiming anything (`make backup BACKUP_DEST=…`; 17 fixtures in
  `tests/test_state_backup.sh`; skip the proof and it exits 2, never 0). Since
  2026-10-27 "off-host" is **measured, not asserted**: the script compares
  `stat -c%d` of `$BACKUP_DEST` against the repository, writes the verdict to
  `backup-probes.tsv`, and `STATE_BACKUP_REQUIRE_OFF_HOST=1` turns a same-filesystem
  destination into a refusal that fires **before** anything is written (an earlier
  revision refused after the write, leaving an archive in the directory it had just
  declared unacceptable). Measured: `/opt/jolarca/backups` is device **64513** — the
  same ext4 volume as the working copy, so every archive ever taken there survives
  operator error and nothing else — while `/mnt/jol-backup/jol-state-backup` is
  device **2065** (`sdb1`, a separate physical disk), and that is the destination.
  **Read the schedule; do not trust this sentence to carry it.** The source of truth is the
  committed `systemd/jolarca-state-backup.{service,timer}`; `make backup-timer-install` copies it
  into `~/.config/systemd/user/` and **diffs after copying**, so the running unit and the reviewed
  unit cannot silently diverge. The installed copy is a build output on a third device (`/home`,
  66319) that sits in no archive — which is exactly why the definition belongs in the repository:
  measured 2026-10-28, zero tracked files mentioned the schedule and its only copy was one
  hand-written file in a home directory. Inspect with `make backup-timer-status`, or directly:
  `systemctl --user list-timers --all | grep jolarca` and
  `journalctl --user -u jolarca-state-backup -n 20`. The history of this bullet is the
  reason for that instruction: a crontab entry installed 2026-10-27 was documented here
  as the schedule and **never fired once** — the host was suspended across 04:17 and
  user crontabs do not backfill (measured: zero `CRON` syslog entries 04:00–06:00, the
  five-minute heartbeat gap 00:25→19:05, `Stopped target suspend.target` on resume).
  `uptime` reported "up 1 week" throughout, because **uptime measures *booted*, not
  *awake*** — which is why the check this file recommended the previous evening could
  not have found the failure. A `systemd` timer with `Persistent=true` replaces cron and
  backfills after a suspend; its own residual gap is that a **user** timer requires a
  login session, so a reboot with nobody logged in runs nothing until
  `loginctl show-user jol --property=Linger` reports `yes`.
  **What tonight proved (2026-10-29):** the backfill works and the failure was a race, not a
  misconfiguration. The host was asleep across 04:17, `Persistent=true` fired the unit at **12:16:50** —
  the instant of resume, while NetworkManager was still bringing the link up (8 connect/up events in that
  window) — and the run exited **2** with `CANNOT VERIFY: cloud state could not be retrieved from the
  backend — no backup was taken and no claim is made`. It wrote nothing and claimed nothing: the §3
  contract held under real conditions. The same unit at 22:12 exited 0 and archived serial 17, so the
  configuration was never wrong. The unit now retries (`Restart=on-failure`, `RestartSec=2min`, bounded
  by `StartLimitBurst` in `[Unit]`), because a scheduler that fires once at the moment the network
  returns is a scheduler that loses nights.
  **What is still not true:** the *cause* is not retained — the script's fetch log lives in a temp
  directory its trap deletes, so "could not be retrieved" carries no HTTP status and the reason had to
  be inferred from NetworkManager; and the age identity still lives on the same machine as the working
  copy. A second disk inside one host survives volume loss, not host loss. So this is a verified,
  scheduled, retrying, off-*volume* copy — **not** a 3-2-1 copy. Do not delete an account, org or
  workspace, and do not treat D-02 as closed.
- **A merge to `main` that touches `apply.yml`'s own paths triggers a real
  apply.** `apply.yml` fires on `push: main` for `repos/**`, `policy/**`, `*.tf`,
  `*.tfvars` and itself, then runs `terraform apply -input=false -auto-approve
  tfplan`. Because actions are SHA-pinned (§5), the pins live *inside* those trigger
  files, so **a dependency bump can arm the apply**: measured 2026-10-26, Dependabot PRs
  #87 (setup-python) and #68 (upload-artifact) both list `.github/workflows/apply.yml` in
  `gh pr diff --name-only`. Since D-81 there is a brake one layer earlier —
  `scripts/check_apply_path_trigger.py` runs inside the required
  `Validate Repo Allow-List` job and refuses a **bot-authored** PR touching those paths,
  while a human PR passes with a `NOTICE` (refusing Terraform work would manufacture an
  unsatisfiable check instead). Consequence to expect: a Dependabot bump that edits
  `apply.yml` now turns a required context red and becomes unmergeable until a person
  re-authors the same diff — that is the refusal working, so do not "fix" it by adding a
  Dependabot `ignore` entry or by widening the gate (§5). #87 and #68 are left open
  unmerged for exactly this reason; treat them as deploy decisions, not housekeeping.
  The gate itself reads the PR file list through `gh api …/pulls/<n>/files`, so the job
  must declare `pull-requests: read` at **job** level — a workflow-level scope is not
  inherited by a job that has its own `permissions:` block, and without it the required
  context 403s and fails on every PR (caught before push by
  `tests/test_check_apply_path_trigger.py`). The brakes inside the run are unchanged: the execution-mode
  gate, `prevent_destroy`, and
  `check_plan_safety.sh`, which since 2026-10-15 refuses destroy, replace,
  visibility, **branch-protection creates and attribute changes (either
  direction)**, **any create or change to a ruleset resource (D-84, added
  2026-10-26)**, and security-feature **disables** (D-61) — so the older note
  that it "does not catch required-context, `strict`, linear-history or
  code-owner changes" is superseded for those attribute classes. What is still
  NOT caught: an attribute change to `github_repository` settings that is not in
  the refused list. Measured outcome of the merge of this repo's #69 (run
  38781192964, 2026-10-15): `Terraform Plan` failed on
  `Error acquiring the state lock / resource not found` and `Terraform Apply`
  was **skipped** — so no apply happened. Read that as the current state of a
  broken CI credential (D-56), not as a control; after the init fix in D-64 the
  plan gets further before dying, and once the token is repaired the refusal gate
  is what has to stop it. Measured 2026-10-26 against HCP directly (D-82): the
  workspace has **three runs, all `Triggered via CLI`**, and none originated from
  GitHub Actions — the CI apply path has never reached the backend at all, so the
  48-resource state is what the last human CLI run left.
- **The production apply now has a 30-minute wait, and it is not an approval.**
  Measured 2026-10-16 after `gh api -X PUT
  repos/jolarca-dev/jolarca-control/environments/production -F wait_timer=30
  -F can_admins_bypass=false`: an independent GET returns
  `protection_rules: [{"type": "wait_timer", "wait_timer": 30}]` and
  `can_admins_bypass: false`. Consequences an agent must act on: (1) the
  `Production — Apply` job on a trigger-path merge now sits pending for ~30 minutes
  before its first step runs, so `gh run list` showing an in-progress apply is
  normal — use that window to cancel, not to wait idly. Cancelling is
  `gh run cancel <run-id> --force` (there is no `--yes`; without `--force` the CLI
  prompts and a non-interactive shell looks like it failed). Proven 2026-10-16 on
  run 38813823199: cancelled mid-wait with `steps_started: 0` and the workspace
  unchanged at 48 resources, i.e. nothing executed before the stop.
  (2) Delay is not approval —
  `required_approving_review_count` is still 0 and no reviewer signs anything, so
  treat the merge as the apply decision, as before; (3) assert on the **array**, not
  the scalar: the top-level `wait_timer` field reads `null` even when the timer is
  active (this is the trap that made an earlier probe report "no wait configured"
  when the row was then written as fact); (4) `-F` not `-f` — that endpoint wants an
  integer and a boolean, and `-f` answers HTTP 422 having changed nothing. Reviewers
  were deliberately **not** added: the solo-operator self-approval constraint is
  untested here, and an unsatisfiable reviewer would wedge every deploy. See D-70 and
  D-58.
- **There is no targeted-apply mechanism.** `apply.yml` runs a whole-state
  `terraform apply -auto-approve tfplan`; the safety comes from the pre-apply
  `check_plan_safety.sh` gate plus `prevent_destroy`. `terraform plan -target`
  appears only as printed advice in `scripts/repo_readiness_audit.py`.
- **The previously-red required contexts now pass AND are enforced.** Verified
  2026-10-06 on PRs #42/#43: `Policy Compliance Check` is green
  (`jolarca-hermes-agents` now declares `pci-dss`) and `Repository Secret Pattern
  Scan` is green. Because protection is live with `strict = true` on this public
  repo, a red required context genuinely blocks the merge — treat these as real
  gates, not decoration, and never "fix" one by editing the gate (D-42; §5).
  `make apply` remains refused locally, but the CI apply path is **not** blocked:
  `STATE_MIGRATION_COMPLETE` measures `'true'`. The refusal there is
  `scripts/check_plan_safety.sh`, which since 2026-10-15 also covers
  protection-layer changes and security-feature disables (D-61).
- **Three fleet repos are protected by rulesets that no configuration declares,
  and their declared required checks enforce nothing.** `jolarca-consent`
  (24087580), `jolarca-dr` (24136490) and `jolarca-vendor` (24138288) each run an
  active `protect-main` ruleset created out-of-band on 2026-09-28; the legacy
  `…/branches/main/protection` endpoint returns HTTP 404 for all three while
  `.protected` is `true`. **Status 2026-10-27: `jolarca-consent` is now adopted** — Step 6b steps
  1–3 were executed by the operator, `terraform state list` holds **1** ruleset address
  (`github_repository_ruleset.main["jolarca-consent"]`, state `id` 24087580) and the remote state
  serial moved **15 → 16**; the adoption was inert, proven per-address (`no-op`) and against the live
  object (`updated_at` still equals `created_at`, so the import wrote nothing to GitHub). `jolarca-dr`
  and `jolarca-vendor` remain unmanaged. Re-measured 2026-10-26 and unchanged by the adoption:
  **consent's ruleset has no `pull_request` rule and no `required_status_checks` rule at all** — so its
  7 declared contexts in `repos/jolarca-consent.yml` are enforced by nothing and `main` is directly
  pushable — while vendor's status-checks rule carries an **empty** context list.
  Do not read `.protected=true` here as enforcement. **Status later on 2026-10-27: Step 6b step 4 was
  hand-applied and consent's hole is CLOSED** — live ruleset `24087580` now carries `pull_request` plus
  `required_status_checks` with all seven contexts (`strict=true`, `bypass_actors: []`), and
  `drift_detect` no longer reports consent. The cost is **D-90**: two of those seven contexts
  (`Gitleaks (secret scanning)`, `Dependency review`) fail on consent's own `main`, so requiring them
  blocks every PR in that repo until the causes are fixed **in consent** (run the gitleaks **CLI** —
  free, as this repo does at `compliance-scan.yml:214-220` — and enable the Dependency graph). Do not
  answer it by trimming the required list: that re-opens the hole. `rulesets.tf` on `main` is now
  **stage 2**, matching live. The decision is recorded as option **A** (adopt
  the rulesets as `github_repository_ruleset`, consent first): the sequence, the HCL and the exact
  `terraform import` ids (`<repo>:<ruleset_id>` — the importer's `parseID2` splits on `:`) are in
  `docs/state-migration-runbook.md` **Step 6b**; **steps 1–4 have run** (4 was applied by hand, since
  the brake refuses ruleset edits by design), and §5 still
  reserves `import`/`state rm`/`state mv` to the operator. The prerequisite — the pre-apply gate could
  not see rulesets — is closed by D-84. **Corrected 2026-10-27 (D-87 row (6)):** provider 6.13.0 DOES
  express the three keys this bullet said it could not — `restrict_pushes` is `rules.update`,
  `require_conversation_resolution` is `rules.pull_request.required_review_thread_resolution`, and
  `enforce_admins` is the *absence* of a `bypass_actors` block; the claim came from grepping the
  registry's spelling into a provider that renames the concepts. What genuinely is not modelled: the
  two fields live in dr/vendor (`dismissal_restriction`, `require_extra_approval_for_unattributed_changes`),
  which is why those two adoptions are deferred.
- **A 404 from the branch-protection endpoint means nothing on its own.**
  Measured twice on 2026-10-15 with the same token and the same path:
  `gh api repos/jolarca-dev/jolarca-control/branches/main/protection` answered
  **HTTP 404** in one window (and the `…/required_status_checks` sub-endpoint
  with it) and **HTTP 200** with the full document hours later, while
  `.protected` was `true` and `…/rulesets` was `[]` throughout. Nothing about the
  protection changed. So: re-read before writing a finding, never infer
  "unprotected" from a single 404, and prefer the signals that stayed
  consistent — `.protected` on the branch, `gh pr view --json
  mergeStateStatus`, the `GH006` push rejection, and the declared list in
  `repos/jolarca-control.yml`. Cause of the blip is unexplained and cannot be
  chased from here (org audit log is HTTP 404 on the Free plan). See D-63.
- **`policy/repo-defaults.yml` used to name a required context that nothing
  reports** ("Fleet Separation Guard"; the job is "Fleet Separation (ADR-0004)"
  and it is path-filtered to `repos/**`) while omitting the fourth real one,
  `SAST (semgrep)`. Corrected 2026-10-15 and now enforced: `make
  context-baseline` / `scripts/check_required_context_baseline.py` compares the
  baseline against `repos/jolarca-control.yml` **and** against the job names a
  `pull_request` event can report, and it runs inside `Validate Repo Allow-List`
  — itself a required context (D-62).
- **Contact-address routing is convention-only.**
  `policy/contact-addresses.yml` defines the role mailboxes (D-59), but no gate
  in `scripts/` compares live SECURITY.md content against it and no inbound
  delivery test has been retained as evidence. Worse, the SECURITY.md GitHub
  actually serves org-wide lives in the `.github` repository and is edited by
  hand — `github_repository_file.security_md` is commented out in
  `health-repo.tf` (D-15), so `files/SECURITY.md` here is a reference copy: an
  edit that looks like a fix propagates nothing. Re-read
  `gh api repos/jolarca-dev/.github/contents/SECURITY.md` before asserting a
  security contact is in force. Side effect of the same change (D-60): commits
  authored by the new noreply identity report `verified: false, reason:
  "bad_email"` on GitHub, because a signature is only verified against emails
  registered on the account. Signed commits are still cryptographically valid
  (`git verify-commit` passes) but are no longer shown as verified until the
  noreply address is added in Settings → Emails.

- **The credential-expiry gate is red on purpose, and runs where red is safe.**
  `scripts/check_secret_inventory.sh` shipped in PR #86 (2026-10-20) defaulting to
  `docs/SECRETS_INVENTORY.md` — a path that has never existed — and invoked by nothing, so it
  exited 2 forever and nobody saw it (D-80). Repaired 2026-10-26: it now reads the table in
  `docs/security/key-custody.md` that declares itself the gate's input, and it runs as a step in
  `deploy-gates.yml`. `Deploy Gates` is **not** one of the four required contexts (measured via
  `gh api repos/jolarca-dev/jolarca-control/branches/main/protection`), which is deliberate: the
  `TFC_TOKEN` row says `expires = unknown` until the operator reads the real date in the HCP UI,
  the register calls that "red by design", and a permanently-red *required* check would wedge every
  merge (the A-01 deadlock shape). It is excluded from `make lint` for the adjacent reason — an
  always-red local gate trains everyone to append `|| true`. So: red in that job is expected, not
  a regression to fix by editing the gate; the fix is a dated row in the register.

## 9. Session discipline

One task per session; start fresh at completed task boundaries. Before ending a
session, persist to durable artifacts (spec, plan, or this file) — not to chat:
accepted scope, task status, files changed, exact verification commands and their
output, and open questions. A fresh session reads the artifacts and real
`git status`, and re-runs verification when the recorded baseline is stale.

Two failed attempts at the same step: **stop**. Capture `git status`, `git diff`
and the exact command output, confirm nothing out of scope was touched, then
escalate. Do not let a model loop — loops are where it starts "fixing" things
nobody asked it to touch.
