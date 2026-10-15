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
| `make lint` | fmt-check, tf-validate, validate, ruff, mypy, shellcheck, yamllint, tests. **Not** all of CI — see below |
| `make test` | Plan-safety fixtures + `pytest` |
| `make validate` | Validate `repos/*.yml` against policy |
| `make context-parity` | Declared contexts must be checks each fleet repo can report (live, `gh`) |
| `make context-baseline` | The `required_checks` policy baseline must equal the declaration AND be producible on a PR (D-62; offline) |
| `make backup BACKUP_DEST=<dir>` | Off-host age-encrypted state export, **with the decrypt round trip proven before it says OK** (D-02) |
| `make readiness REPO=<name>` | Pre-first-commit verdict: READY / READY-WITH-FIXES / BLOCKED |
| `make first-commit REPO=<name> STEP=A..F` | Read-only pipeline gate; prints commands, never runs them |
| `make evidence-check` | Verify evidence hashes against the **committed** registry |
| `make evidence-register` | Regenerate `docs/evidence-registry.csv`, then commit the diff in a PR |
| `make drift` / `make fleet-audit` / `make org-audit` | Live, read-only (need `gh` / token) |

Run Python through the venv: `.venv/bin/python -m pytest tests/ -q`. The system
`python3 -m pytest` can exit 1 with no output, which reads as a mystery failure.

**`make lint` is not the whole CI surface.** `compliance-scan.yml` additionally
runs `scripts/compliance_check.py` (`make compliance`) and
`scripts/repo_readiness_audit.py --no-live`, and neither is in `lint`. Run both
before pushing, or CI will surface failures the local gates never checked.
As of 2026-10-06 both required contexts pass on `main` (verified on PRs #42/#43);
§8 records the current control status.

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

- **No `terraform apply` from this root.** State is owned by
  `jolarca-infrastructure` until the migration runbook completes.
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
  must fail. `tests/test_check_plan_safety.sh` is the model (10 cases including
  empty and missing plan). An untested regex gate is a hypothesis: D-22 was an
  inline `visibility\s*:` pattern that never matched `terraform show` output, so
  the only control between an unattended apply and a fleet-wide visibility flip
  was inert.
- **Evidence must be retained to count.** Verification output that justified a
  merge is a deliverable, not a transient. Evidence files under `docs/adr/`,
  `audit/`, `policy/`, `repos/`, `docs/runbooks/`, `docs/security/` are hashed
  into the committed `docs/evidence-registry.csv`; edit one and re-register in
  the same PR or `make evidence-check` fails.
- **Do not trust a correct verdict.** A gate can report the right aggregate
  answer while silently skipping whole check families (an early `return` on a
  missing `.git` once skipped six filesystem checks and the entire secret sweep).
  Cross-check finding counts against an independent run.

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
  SHA-256** before claiming anything (`make backup BACKUP_DEST=…`; 10 fixtures in
  `tests/test_state_backup.sh`; skip the proof and it exits 2, never 0). Still
  missing: **a schedule and a genuinely off-host destination.** The age identity
  and `/opt/jolarca/backups/` both live on the machine holding the working copy,
  so this is a verified export path, not a 3-2-1 copy, and it is only as current
  as the last human who ran it. Do not delete an account, org or workspace, and
  do not treat D-02 as closed.
- **A merge to `main` that touches `apply.yml`'s own paths triggers a real
  apply.** `apply.yml` fires on `push: main` for `repos/**`, `policy/**`, `*.tf`,
  `*.tfvars` and itself, then runs `terraform apply -input=false -auto-approve
  tfplan`. The brakes are the execution-mode gate, `prevent_destroy`, and
  `check_plan_safety.sh`, which since 2026-10-15 refuses destroy, replace,
  visibility, **branch-protection creates and attribute changes (either
  direction)**, and security-feature **disables** (D-61) — so the older note
  that it "does not catch required-context, `strict`, linear-history or
  code-owner changes" is superseded for those attribute classes. What is still
  NOT caught: an attribute change to `github_repository` settings that is not in
  the refused list. Measured outcome of the merge of this repo's #69 (run
  38781192964, 2026-10-15): `Terraform Plan` failed on
  `Error acquiring the state lock / resource not found` and `Terraform Apply`
  was **skipped** — so no apply happened. Read that as the current state of a
  broken CI credential (D-56), not as a control; after the init fix in D-64 the
  plan gets further before dying, and once the token is repaired the refusal gate
  is what has to stop it.
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
