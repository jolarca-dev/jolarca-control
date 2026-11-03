# Fleet Audit 2026-Q4 — index

Control plane baseline: `jolarca-control` `a720789dae6ff3cc83a493e487d3ca8afb1a4da2`
(`main`; the earlier `1ef4f9b…` row was a branch head whose PR **#85 is CLOSED/merged**, and
the header here had kept saying `OPEN, mergeStateStatus=BEHIND` — corrected 2026-10-26 on the
same principle as D-85: a record must state the live state, not the state when it was written).
Method: stages A–L (A population, B baseline, C environment, D read-before-run, E enforcement
layer, F trace a change, G data classification, H secrets, I supply chain, J tenant isolation,
K agent/MCP surface, L resilience). Records are `<repo>.yml` (register) + `<repo>.md`
(narrative). Raw probe output belongs in `evidence/<repo>/*.md` — only
`*.yml *.md *.sh *.py *.tf` are hashed by `scripts/hash_evidence.sh:115`, so a `.txt`/`.json`
sweep is **not** tamper-evident no matter where it is committed.

Population reconciliation (STAGE A, measured 2026-10-26):
`gh repo list jolarca-dev` → **17 repos, all PUBLIC, none empty** = 16 entries in `repos/*.yml`
+ `.github`, which is created by `health-repo.tf:26` and is therefore **outside** the YAML allow-list
(see FA-dotgithub-04).

| # | Repo | Baseline SHA (main) | Verdict | S0 | S1 | S2 | S3 | NOT RUN | Date |
|---:|---|---|---|---:|---:|---:|---:|---:|---|
| 1 | `jolarca` | — | NOT RUN | — | — | — | — | — | |
| 2 | `jolarca-infrastructure` | — | NOT RUN | — | — | — | — | — | |
| 3 | [`jolarca-control`](jolarca-control.yml) | `a720789dae6ff3cc83a493e487d3ca8afb1a4da2` (`main`) | **NO-GO (assurance)** · CONDITIONALLY OPERATIONAL (control plane) — FA-control-12 **landed `7048116` PR #95**, FA-control-14 **landed `a720789` PR #97**; open: FA-control-03, FA-control-08, FA-control-13 (`gap`), FA-control-15 and FA-control-16 (`implemented-pending-merge`) | 0 | 7 | 8 | 1 | 4 | 2026-10-26 |
| 4 | `jolarca-hermes-agents` | — | NOT RUN | — | — | — | — | — | |
| 5 | `jolarca-identity` | — | NOT RUN | — | — | — | — | — | |
| 6 | `jolarca-payments` | — | NOT RUN | — | — | — | — | — | |
| 7 | [`jolarca-consent`](jolarca-consent.yml) | `7e5f84045ae0ff0dc590aa5a60ce4639f26ae1a7` | **NO-GO** | **1** | 5 | 4 | 0 | 5 | 2026-10-26 |
| 8 | `jolarca-data` | — | NOT RUN | — | — | — | — | — | |
| 9 | `jolarca-security` | — | NOT RUN | — | — | — | — | — | |
| 10 | `jolarca-compliance` | — | NOT RUN | — | — | — | — | — | |
| 11 | `jolarca-observability` | — | NOT RUN | — | — | — | — | — | |
| 12 | `jolarca-dr` | — | NOT RUN | — | — | — | — | — | |
| 13 | `jolarca-runbooks` | — | NOT RUN | — | — | — | — | — | |
| 14 | `jolarca-vendor` | — | NOT RUN | — | — | — | — | — | |
| 15 | `jolarca-legal` | — | NOT RUN | — | — | — | — | — | |
| 16 | `jolarca-docs` | — | NOT RUN | — | — | — | — | — | |
| 17 | [`.github`](dot-github.yml) | `48b96656c6779788cf84444fc0973f9697d18dcb` | **NO-GO** | 0 | 5 | 7 | 1 | 3 | 2026-10-26 |

Totals are parsed from the three YAML registers, not counted by hand — `.github` 13 controls
(5 S1 / 7 S2 / 1 S3), consent 10 (1 S0 / 5 S1 / 4 S2, one of those S1 labelled `S1 (latent)` in its
register), control plane 16 (7 S1 / 8 S2 / 1 S3), i.e. **39 findings across 3 of 17 repositories:
1 S0, 17 S1, 19 S2, 2 S3**. An earlier
draft of this index carried hand-counted totals that were wrong in three cells, the same class of
defect recorded in the 2026-10-24 audit; the count is now derived from the machine-readable source
and re-checked by parsing the registers after every edit. That re-check caught a fresh instance of
the same class in this very file on 2026-10-26 — a hand-added S2 total of 17 where the registers sum
16 — corrected by the parse, not by recounting by hand. The parse command is recorded in
`jolarca-control.md` (method notes) so the numbers below are reproducible, not trusted.

**Fleet verdict so far: NO-GO.** One S0 open (`FA-consent-01`). Three of seventeen repositories
audited; the remaining fourteen are **NOT RUN**, which is a status, not a pass.

## Cross-organisation findings (not per-repo)

| ID | Sev | Finding | Status |
|---|---|---|---|
| FA-cross-01 | S2 | `make drift` cannot express "findings": `drift_detect.py` exits `1`, the Makefile recipe turns it into `2` — the code AGENTS.md §3 reserves for "could not verify". Proven twice on one tree (`SCRIPT_EXIT=1`, `DRIFT_EXIT=2`). | VERIFIED |
| FA-cross-02 | S1 | No gate asserts that a **`pull_request` ruleset rule exists** on a non-empty repo. `rulesets_covering_default_branch()` is called only inside the empty-repo branch (`repo_readiness_audit.py:1844`); `drift_detect.ruleset_protection_state()` checks `non_fast_forward`/`deletion` only (`:326-329`) and disclaims review attributes (`:336-340`). Consent is caught today only via its empty context count. | VERIFIED |
| FA-cross-03 | S2 | `.protected=true` on all 17 while three repos gate nothing — the metric that closed D-33 is insensitive to its own subject (`policy/compliance-gates.yml:555-556` still says "FULLY RESOLVED … verified via gh api .protected=true"). | VERIFIED |
| FA-cross-04 | S1 | Audit evidence retention. Measured 2026-10-26: the former `/tmp/jaudit` sweeps now exist at `docs/security/pre-deployment-audit-2026-10-25/` (26 files, 356K) and are registered **8** rows in `docs/evidence-registry.csv` — the 2 `.md` + 6 `.sh`. The other **18** (17 `.txt` + 1 `.tsv`) are outside `hash_evidence.sh:115`'s extension filter, so they survive a reboot but are **not tamper-evident**. The directory itself is still **untracked** — `git log -- docs/security/pre-deployment-audit-2026-10-25/` returns nothing — so no finding is yet attributable to a commit SHA. **Update, same day:** all 18 non-hashable probes now have `.md` wrappers (`gates.txt` 33 528 B → `gates.md` 33 617 B, i.e. header + fence only, content byte-identical). **Resolution decided, not yet landed:** the directory cannot be committed as it stands, because its raw `gh pr list` output quotes a finding id that only unmerged PR #79 defines — the citation gate (`check_findings_register.py`) matches every `D-nn` token in tracked text, so committing the sweep either falsifies captured output or requires widening the gate's exclusions, and AGENTS.md §5 forbids both. The directory therefore stays untracked and the registry no longer attests it (see FA-cross-07). Unblock: merge #79, then commit and re-register. | OPEN — blocked on PR #79, registry corrected |
| FA-cross-05 | S2 | Two byte-identical copies of the same audit documents exist: `docs/master-architect-prompt.md` (`733cf259…`, 1290 lines) and its copy `docs/security/pre-deployment-audit-2026-10-25/master-architect-prompt.md`; likewise `docs/pre-deployment-audit-2026-10-24.md` (`fcd0532c…`, 835 lines) and its copy. **Only the copies inside that directory are registered** — the `docs/` root copies are untracked and un-hashed, so the file an editor naturally opens is the file nothing checks. Identical bytes as measured 2026-10-26; divergence is the predictable next state. One fact, one owner. | OPEN — verified identical at time of writing |
| FA-cross-07 | S1 | **A gate's verdict depended on the working tree, not the committed tree.** `hash_evidence.sh` enumerated files on disk, so `make evidence-register` attested 26 rows for files git had never seen; CI, which only ever checks out the commit, scanned 46 files and reported `OK: all registered evidence hashes match` over 26 vacuous attestations. Found only by running the newly added reverse pass inside a clean clone (`git clone` → overlay script → `--check` → `46 files scanned, 26 mismatches`, exit 1). Fixed at the root: enumeration is now `git ls-files -z`, a non-repo or empty index exits 2, and a fixture proves an untracked file acquires no row. Registry corrected from 72 to 46 rows, all tracked. | FIXED — LANDED (`main` = `e5b9b3f`, PR #89) — lesson generalises to every fleet gate that reads `$REPO_ROOT` |
| FA-cross-08 | S2 | The register-integrity gate scans only `git ls-files` output (`check_findings_register.py:161`), so a dangling citation in an uncommitted draft is invisible until it is committed — proven in sequence here: 12:55 `no dangling citations`, then after `git commit` the same command reported the citation this audit had introduced. Correct-by-design (CI sees the committed tree) but the local reading must be stated, not assumed: `make findings-check` green does **not** cover work in progress. | VERIFIED — documented, not changed |
| FA-cross-09 | S2 | **Prose is not an invocation, and an exception that forgives two rules is an off switch.** Two shapes, both reproduced while building the D-80 parity gate and both fleet-wide. (a) Matching script names against raw workflow/Makefile *text* let a YAML comment — and a `#` line inside a shell `run:` block, and the gate's own docstring — satisfy "this gate is invoked", so the draft reported green on `check_secret_inventory.sh`, the very unwired gate it was written to catch. Fix: parse the YAML, take only `- run:` bodies, strip comment lines from both corpora. (b) `continue` after a baseline exception also skipped the liveness rule: measured pre-fix, a script that was *both* baselined *and* unwired produced `findings: []`, i.e. adding a dead gate to the exception list switched the meta-gate off (§5 forbids exactly that). Fix: an exception forgives one rule, named in the comment, and a fixture pins it (`test_baseline_entry_does_not_excuse_liveness`). Third-party corollary: `pytest tests/` collects `.py` and cannot collect `.sh`, so an unwired shell fixture is invisible to every merge. Known limit, checked not assumed: R2/R3 read `run:` steps only, which is safe here because this repo makes no reusable-workflow calls (`uses: ./`, `uses: jolarca` → no matches); a fleet repo that later calls a shared workflow needs those rules to follow `uses:` too. | FIXED — LANDED (`main` = `4e0c22b`, PR #91) — generalises to any repo whose CI counts greps as coverage |
| FA-cross-10 | S2 | **A dependency pin inside a deploy-triggering file makes dependency automation a change-management actor.** `apply.yml` triggers on `push: main` for `repos/**`, `policy/**`, `*.tf`, `*.tfvars` and **itself**, then runs `terraform apply -auto-approve tfplan`; §5 requires actions pinned to a full SHA, so the pins live in those very files. Measured: `gh pr diff 87 --name-only` and `gh pr diff 68 --name-only` (both Dependabot, both open) include `.github/workflows/apply.yml`. Nothing in the repo said that merging a routine version bump is a deploy decision — the D-58 exception already concedes nobody signs the apply and the 30-minute wait is delay, not approval. Fixed by `scripts/check_apply_path_trigger.py` (bot → refuse pre-merge; human → notice + pass), which **reads** the trigger set from `apply.yml` rather than restating it. The same shape exists in any repo where workflow files are inside their own deploy filter; fleet propagation is not done here. | FIXED in `jolarca-control` (pending merge) — fleet-general, one D-81 row per repo otherwise |
| FA-cross-11 | S2 | **A job-level `permissions:` block silently un-grants whatever the workflow granted.** GitHub's rule is "If you specify the access for any of these permissions, all of those that are not specified are set to `none`", and the job block is applied after the workflow block. In this repo the `validate` job declares `contents`/`actions` while the workflow also declares `pull-requests: read`, so nothing in that job can call the pulls API — a step added there that does so fails, and because the job's name *is* a required context, the failure blocks every PR in the repository, not just the one that added the step. Precedent already in the same job: #41 needed `actions: read` restated for the environments API. Every fleet repo that gates merges on a job with its own `permissions:` block inherits this trap. Caught here before push by asserting the scope against the workflow YAML (`tests/test_check_apply_path_trigger.py`), which is the practice worth propagating. | VERIFIED — fixed in this repo (D-81), fleet-general |
| FA-cross-06 | S3 | Concurrent tree modification observed mid-audit: `docs/evidence-registry.csv` gained 8 rows (` M`, registered 2026-10-26) and the rescue directory appeared between two probes of the same session. Verified **not** caused by the audit pass — `Makefile:33` (`lint:` = fmt-check tf-validate validate context-baseline py-lint py-type sh-lint yaml-lint test) contains no `hash_evidence.sh` call; register mode exists only at the `evidence-register` target (`Makefile:87`), which this pass never invoked. Recorded so a later reader does not attribute it to these findings. **Annotation 2026-10-26 (D-80):** `Makefile:33` is still the `lint:` line and still calls no `hash_evidence.sh`, but its prerequisites now read `fmt-check tf-validate validate context-baseline gate-parity py-lint py-type sh-lint yaml-lint test` — the parenthetical above quotes the pre-#91 list, and `evidence-register` remains the only target that writes the registry. | VERIFIED — not audit-caused |

## Local gate baseline (jolarca-control, 2026-10-25, tree `1ef4f9b`)

| Gate | Exit | Status |
|---|---|---|
| `make lint` (fmt, tf-validate, validate, context-baseline, gate-parity, ruff, mypy, shellcheck, yamllint, pytest, shell fixtures) | 0 | VERIFIED PASS — 295 pytest tests + five shell fixtures whose own counters read 25 (plan-safety) / 19 (hash-evidence) / 19 (secret-inventory) / 13 (workspace-mode) / 10 (state-backup) |
| `make gate-parity` (`scripts/check_gate_parity.py`, D-80) | 0 | VERIFIED PASS — `OK: 17 gate scripts each have a fixture or a dated baseline entry`; negative controls on a copy of the real tree: untested script → exit 1 (`R1=1, R3=1`), unwired script → exit 1 (`R2=1, R3=1`), placeholder fixture → exit 1 (`R1b=1`), unparseable workflow → exit **2**, restored → 0 |
| `scripts/check_apply_path_trigger.py` (D-81), live inputs | 1 / 0 | VERIFIED — against real PR file lists: #87 and #68 (both Dependabot) name `.github/workflows/apply.yml` → exit **1** for a bot author; #93 (human, docs) → exit 0 "no apply armed". The first draft reported "no apply armed" on #87 too, because `lstrip("./")` mangled the leading dot — this row is the corrected reading |
| `scripts/check_apply_path_trigger.py` (D-81), its own job wiring | 1 → 0 | VERIFIED — the step calls `gh api …/pulls/<n>/files`, and the required `validate` job's own `permissions:` block set `pull-requests` to `none`. Proved the negative control by deleting the restated scope (`assert None == 'read'`, exit 1), then restored and confirmed byte-identical (`diff` exit 0). Without the fix the 403 would have failed a **required context on every PR** |
| `ruff format --check scripts/ tests/` vs `make lint` (D-83) | 1 then 0 | VERIFIED DIVERGENCE — `make lint` exit 0 (313 passed) while the CI `Lint` job's formatter step reported "1 file would be reformatted, 24 files already formatted" (13 hunks, all in the new fixture). Fixed by adding `py-fmt-check` to `lint`. **Premise corrected after drafting:** the formatter was not unenforced locally — `pre-commit run --all-files` passes all twelve hooks including `ruff-format`, the hook is installed, and the commit attempt was itself refused by `end-of-file-fixer`. The finding is the un-compared trio of surfaces (`lint` / hooks / CI), graded S3, open as FA-control-13 |
| `make lint` (with `py-fmt-check`), 2026-10-26 | 0 | VERIFIED PASS — `316 passed in 12.85s` (the tool's own line; 313 before the three D-81 review cases were added, and the count is read from output rather than derived by hand) + the five shell fixtures at 25/19/19/13/10 (plan-safety, hash-evidence, secret-inventory, workspace-mode, state-backup) |
| `bash tests/test_check_plan_safety.sh` (D-84 ruleset cases) | 0 → 1 → 0 | VERIFIED BLIND, THEN FIXED — three synthetic ruleset plans in Terraform's own rendering were fed to the **unfixed** gate and all three exited **0**: a `github_repository_ruleset … will be created` block with only push rules, an update setting `enforcement = "active" -> "disabled"` with `deletion`/`non_fast_forward` off plus a `RepositoryAdmin` bypass actor, and an org-ruleset weakening. The fixture printed `FAIL … want exit=1 got=0` for each, and `ok ruleset-refresh-only-noise exit=0` — the non-vacuity half. After adding four ruleset refusals: **29 passed, 0 failed** (25 before). `grep -ic ruleset scripts/check_plan_safety.sh` was **0** pre-fix while three fleet repos are ruleset-protected (D-46) |
| D-46 option A staging (read-only probes) | n/a | DECISION RECORDED, NOTHING EXECUTED — live ruleset bodies re-read today (consent 24087580: three push rules, **no `pull_request` rule, no `required_status_checks` rule**, never updated since 2026-09-28; dr 24136490: +PR +`[lint, gitleaks]` strict false; vendor 24138288: +PR +**empty** context list). Provider 6.13.0 models `github_repository_ruleset` including `required_status_checks.required_check`, so consent's 7 declared contexts ARE expressible; it does **not** model `dismissal_restriction` / `require_extra_approval_for_unattributed_changes` that are live in dr/vendor. Import id format read from provider source (`parseID2` splits on `:`): `<repo>:<ruleset_id>`. Sequence and the ready HCL are in `docs/state-migration-runbook.md` **Step 6b**; the operator runs the `terraform import` (§5) |
| Required-check blocking, direct observation (PR #94, closed unmerged) | 1 | VERIFIED PASS — a throwaway `scripts/probe_untested.sh` with no fixture reddened `Validate Repo Allow-List` (`RESULT: 2 parity finding(s): R1=1, R3=1`) and independently reddened `Regression Tests`; `mergeable=MERGEABLE` with **`mergeStateStatus=BLOCKED`**. This closes the register's standing `not_run` item, which had rested on the 2026-10-12 GH006 push rejection |
| `make compliance` | 0 | VERIFIED PASS — 16 repos, declared configuration only (`live_state_verified: false`) |
| `make evidence-check` | 0 | VERIFIED PASS at baseline — 39 files, 0 mismatches |
| `make evidence-check` (after registration of the 8 rescued files) | 0 | VERIFIED PASS — 52 files scanned, 0 mismatches (operator-run `make evidence-register`, +13 CSV rows) |
| `make evidence-check` (after the 18 `.md` wraps + repo-3 records) | 1 | VERIFIED FAIL — **72 files scanned, 21 mismatches**: 20 `UNREGISTERED` (the 18 probe wrappers plus `jolarca-control.yml` and `jolarca-control.md`) and 1 `CHANGED` (this `index.md`, edited after registration). Expected, not a regression: `evidence-register` has not been re-run since. Reproduce the split with `bash scripts/hash_evidence.sh --check \| grep -cE '^UNREGISTERED:'` → 20 |
| `make evidence-check` (after the tracked-tree fix) | 0 | VERIFIED PASS — **46 files scanned, 0 mismatches**, and the 26 rows naming untracked files are gone. `OK` now also asserts every registered file exists. Clean-clone equivalent re-run: same 46/0 |
| `make validate` | 0 | VERIFIED PASS |
| `scripts/repo_readiness_audit.py --no-live` | 1 | VERIFIED FAIL — 1 READY / 10 READY-WITH-FIXES / 5 BLOCKED (pre-existing, not caused by this audit) |
| `make drift` | 2 | VERIFIED FAIL — consent + vendor `weakened`; `.github` in `hollow_rules` (informational) |
| Org 2FA enforcement | 200 | **VERIFIED PASS** — `orgs/jolarca-dev two_factor_requirement_enabled = true`. Corrects the earlier "BLOCKED: `two_factor_auth_enabled` returns null on Free": that field is indeed null, but a sibling field is readable. PCI-DSS 8.3 / SOC 2 CC6.1 evidence now available |
| Org members creating repositories | 200 | **VERIFIED PASS** — `members_can_create_repositories = false`, `default_repository_permission = none`. Closes D-19's "detection, not prevention" gap |
| Org audit log | 404 | BLOCKED — not readable on the Free plan (D-63); permanent evidence gap for the SOC 2 narrative |

## Post-merge verification (2026-10-26, `main` = `e5b9b3f6a3e70119374a5cabcf807d3d445c6b89`)

| Check | Result | Status |
|---|---|---|
| Push-triggered `Compliance Scan` run 40329048473 (`event=push`, `head_sha=e5b9b3f`) | `conclusion=success` | VERIFIED PASS |
| New step inside the **required** `Validate Repo Allow-List` job | printed `Evidence check: 46 files scanned, 0 mismatches` + `OK: … and every registered file exists` | VERIFIED PASS — enforcement observed on `main`, not inferred from config |
| `Static Analysis (SAST)` push run on the same SHA | `success` | VERIFIED PASS |
| `Terraform Apply` triggered by the merge? | no run created; latest apply run remains `2026-10-17T19:07:46Z` (cancelled) | VERIFIED PASS — the no-apply-path claim held |
| Fresh clone of `main`: `hash_evidence.sh --check` | 46 scanned, 0 mismatches, exit 0 | VERIFIED PASS |
| Fresh clone of `main`: `gitleaks git .` (full history, 2.17 MB) | no leaks, exit 0 | VERIFIED PASS |
| Declared vs live visibility for this repo | `repos/jolarca-control.yml` declares `public`; live `public`; `forks_count=0` | VERIFIED PASS (declared==live, not a hardcoded expectation) |
| Branch protection re-read after merge | 4 required contexts, `strict=true`, `enforce_admins=true`, `required_linear_history.enabled=true` | VERIFIED PASS |
| PR #85 (superseded by this branch lineage) | its 3 files are byte-identical to `main`; closed with the diff evidence cited, remote branch deleted | CLOSED — content landed |

This is a **Type I** observation on the day the control landed. Operating effectiveness over a period
(SOC 2 Type II) requires the weeks of run history that do not exist yet, and no framework claim in
this directory should be read as certification.

## Post-merge verification, PR #91 (2026-10-26, `main` = `4e0c22bd64fe9d7ab3ff44eabf7242e322555f34`)

| Check | Result | Status |
|---|---|---|
| Push run 40338769793 (`Compliance Scan`, `event=push`) | `success`; all six jobs success including the required `Validate Repo Allow-List` | VERIFIED PASS |
| New step inside that required job | printed `OK: 17 gate scripts each have a fixture or a dated baseline entry; every shell fixture runs in a PR-triggerable workflow; no gate is unreferenced` | VERIFIED PASS — the parity rule is on the merge path, observed not configured |
| Evidence step in the same job | `Evidence check: 46 files scanned, 0 mismatches` | VERIFIED PASS — the #89 control still holds after #91 |
| `Deploy Gates` push run on `4e0c22b` | `failure` at `Credential expiry register is dated and unexpired (D-80)`, annotation `expiry unknown for a row in docs/security/key-custody.md — verify and record it` | VERIFIED — **designed red**, non-required, non-blocking; it is the signal PR #86 could not produce |
| `mergeStateStatus` on #91 before merge | `UNSTABLE` (`mergeable=MERGEABLE`): all required checks passed, one non-required check failed | VERIFIED PASS — blocking derives from the required-context list, not from a red job |
| Fresh clone of `main` | gate parity exit 0; `hash_evidence.sh --check` 46/0; `gitleaks git .` over 2.60 MB no leaks | VERIFIED PASS |
| `make findings-check` on `main` | 79 `D-nn` headings, no collisions, no dangling citations | VERIFIED PASS — D-80 is defined, not merely cited |
| `Terraform Apply` triggered by the merge? | no run created; latest remains `2026-10-17T19:07:46Z` (cancelled) | VERIFIED PASS — second consecutive merge with no apply path touched |
| Branch protection re-read | 4 required contexts, `strict=true`, `enforce_admins=true`, linear history, `required_approving_review_count=0`, rulesets `[]`, `.protected=true` | VERIFIED PASS — unchanged by this PR (as required: no protection attribute was edited) |
| Declared vs live visibility | `repos/jolarca-control.yml` `public` = live `public`, `forks_count=0` | VERIFIED PASS |

### How often that red is actually visible (measured on `main` = `20e4dc4`)

`deploy-gates.yml` is path-filtered — `pull_request` and `push: main` fire only on
`.github/workflows/apply.yml`, `.github/workflows/deploy-gates.yml` and
`scripts/check_deploy_gates.py` — plus `schedule: cron "0 8 * * 3"` (Wed 08:00 UTC) and
`workflow_dispatch`. So the credential-expiry signal runs on PRs and merges touching those three
files, weekly, and on demand; **not on every PR** (the docs-only #92 merge created no
`Deploy Gates` run). Two consequences recorded at the time rather than rediscovered later:

1. Dependabot PRs that bump an action inside those files now show a red `Deploy Gates`. Measured
   on PR #87 (`actions/setup-python` 7.0.0→7.1.0, head `357fc84`): `Deploy Gates` = `FAILURE` with
   all four required contexts `SUCCESS`, `mergeable=MERGEABLE`, `mergeStateStatus=BEHIND` — noise,
   not a block, and the reason the wording in `D-80` spells it out.
2. Promoting `Deploy Gates` to a required context while `expires = unknown` stands would fail every
   such Dependabot PR (the dependency-bump deadlock shape the fleet has recorded before). The
   precondition for promotion is a dated row in `docs/security/key-custody.md`, not a weaker gate.

## Post-merge verification, PR #95 (2026-10-26, `main` = `7048116a04ba01c69daf5c1d8220a415862d1262`)

| Check | Result | Status |
|---|---|---|
| Merge itself | squash, `mergedAt` `2026-10-26T17:23:58Z`, 13 files `+1140/-30`; remote branch deleted (`git ls-remote --heads origin fix/apply-path-trigger-guard-d81` → 0 rows) | VERIFIED PASS |
| Pre-merge CI on the final head `403ad80` | all ten reported checks `pass` (incl. the four required), `mergeStateStatus=CLEAN`, `mergeable=MERGEABLE` | VERIFIED PASS |
| D-81 step, live observation (PR run 40358205519, inside the **required** `Validate Repo Allow-List`) | printed `OK: 13 changed file(s), none in apply.yml's push paths (5 pattern(s) read from apply.yml) — no apply armed` with `PR_ACTOR_TYPE: User`, shell `/usr/bin/bash -e {0}` | VERIFIED PASS — first operating observation, and proof the job-level `pull-requests: read` reaches `gh api …/pulls/<n>/files` |
| Same step on the merge's push run (40368243557, `conclusion=success`) | `conclusion=skipped` | VERIFIED — **by design**: the brake is gated to `pull_request`, so it cannot observe a merge in progress. Stated rather than glossed: the **bot-refusal path has never rejected a live PR** (21 fixtures + a committed-tree run → exit 1 for a Bot author are the assurance so far) |
| Fresh clone of `main` | `hash_evidence.sh --check` 46/0 exit 0 · `check_gate_parity.py` "OK: 18 gate scripts…" exit 0 · `pytest tests/ -q` **316 passed** · `gitleaks git .` over 2.25 MB → no leaks · `check_findings_register.py` 82 headings, none dangling | VERIFIED PASS |
| Guard non-vacuity in the clone | Bot + `.github/workflows/apply.yml,README.md` → exit **1** with the refusal text; User + `docs/x.md` → exit 0 "no apply armed" | VERIFIED PASS — the gate detects its own defect class on the committed tree |
| Branch protection re-read | contexts exactly `[Validate Repo Allow-List, Policy Compliance Check, Repository Secret Pattern Scan, SAST (semgrep)]`, `strict=true`, `enforce_admins=true`, `required_approving_review_count=0`, `required_linear_history=true`, `required_conversation_resolution=true`, `allow_force_pushes=false`, `allow_deletions=false`, `required_signatures.enabled=false`, rulesets `[]`, `.protected=true` | VERIFIED PASS — unchanged by this PR; note `restrictions` users/teams/apps all 0 and that `allow_force_pushes`/`allow_deletions` read as **present objects** (`{enabled: false}`), the naming the earlier `strict: null` probe got wrong |
| Declared vs live visibility | `repos/jolarca-control.yml:21` `public` = live `public`, `private=false`, `forks_count=0` | VERIFIED PASS |
| `Terraform Apply` triggered by the merge? | no run created; latest remains `2026-10-17T19:07:46Z` (cancelled) | VERIFIED PASS — third consecutive merge on a repo whose CI has never reached HCP (D-82) |
| Claims this PR corrected about itself | D-83's "nothing local runs the formatter" (refuted: `ruff-format` is an installed pre-commit hook, all twelve pass) → regraded S2→S3; FA-control-11's D-22a note was briefly overwritten with a false absence read from an **empty grep through an unreliable capture channel** → restored (`### D-22a` is at `docs/drift-findings.md:235`; parser 82 vs raw 83) | VERIFIED — both kept in the text, not deleted; the intermediate wrong commit `e07dc54` was superseded by `403ad80` before the squash, so it never reached `main` |

## Post-merge verification, PR #97 (2026-10-26, `main` = `a720789dae6ff3cc83a493e487d3ca8afb1a4da2`)

| Check | Result | Verdict |
|---|---|---|
| Fresh clone of `main`, commands run directly so exit codes are the scripts' own (D-86) | `grep -c '^### D-84' docs/drift-findings.md` → **1**; `bash tests/test_check_plan_safety.sh` → **29 passed, 0 failed**; `check_gate_parity.py` → "OK: 18 gate scripts…"; `check_findings_register.py` → "OK: 83 headings parsed, no collisions, no dangling citations"; `hash_evidence.sh --check` → 46 files / 0 mismatches; `pytest tests/ -q` → **316 passed**; `gitleaks git .` → 113 commits, ~2.53 MB, **no leaks** | VERIFIED PASS |
| CI on the merged head | `Compliance Scan` (run 40404668351) and `Static Analysis (SAST)` push runs on `a720789` both `success`; all 10 PR checks on `c9408fc` passed before the merge | VERIFIED PASS |
| D-81 guard's own verdict on the merged branch | printed `OK: 10 changed file(s), none in apply.yml's push paths (5 pattern(s) read from apply.yml) — no apply armed`, `PR_ACTOR_TYPE: User` | VERIFIED PASS — second operating observation, and the first on a branch that changed the pre-apply brake itself |
| `Terraform Apply` triggered by the merge? | no run created; latest remains `2026-10-17T19:07:46Z` (cancelled) | VERIFIED PASS — fourth consecutive merge with no apply |
| Ruleset adoption executed? | **no.** `docs/state-migration-runbook.md` step 6b is staged; `terraform import` is the operator's (§5), and no ruleset is in state, so the new refusals have been proven against synthetic plans only | RECORD, not a pass |

## What rejecting step (b) found (D-85, D-86) — 2026-10-26

| Check | Result | Verdict |
|---|---|---|
| Committed vs working tree, `jolarca-infrastructure` `8f02d17` (fresh clone, public) | `var.org` default `journeyoflife-org` in root `variables.tf:79` and module `variables.tf:4`; `module "github_org"` live; no committed `terraform.tfvars`; `git grep -n lifecycle HEAD -- environments/production modules/github-org` → **no matches**; `git log --all -S "FROZEN — DO NOT PLAN OR APPLY"` → **0 commits**; `variables.tf.bak.20260831-2306` tracked at HEAD | GAP — **S1**, D-85; register rows D-06/D-13 and runbook step 1 asserted the opposite |
| Where the fix was | 9 uncommitted entries, +133/−98 (banner, `prevent_destroy` ×3, org default ×2, `.bak` deletion, guard header) | landed as infra **PR #49** (`2eab214` + `693ec82`), both `%G?` = `G`; **open**, not merged |
| Why it lingered | required contexts `ci, security, compliance` with `enforce_admins = true`; `compliance-check.yml` demands 7 governance files and this is the **only** fleet repo missing `.github/CODEOWNERS` → `compliance` failed on every PR, including all 8 Dependabot runs | MECHANISM FOUND — the repo was welded shut, not neglected |
| Was the wrong-org plan hypothetical? | `terraform.yml` `plan` job runs on every `pull_request` touching `terraform/**`; runs `39925547516` / `39925560368` (2026-10-23) **succeeded** and posted `Plan: 16 to add, 0 to change, 0 to destroy` as comments on public PRs; `apply` is `if: github.event_name == 'workflow_dispatch'` | IMPACT CONFIRMED, mitigated only by a job condition |
| `make` vs script exit codes | `repo_readiness_audit.py --repo jolarca-data` → **1**; `make readiness REPO=jolarca-data` → **2**; synthetic `@exit 1` target → **2** (make cannot convey 1); `readiness`/`first-commit` discarded stdout (85 / 128 B) while the table survived on stderr (373 / 808 B) | GAP — **S2**, D-86, fixed in this change |
| Claims this change corrected about **its own** measurements | first `grep -rc prevent_destroy`/`FROZEN` repo-wide looked like a refutation of D-85 — it matched `modules/state-bucket` (GCS) and bucket-name prose; `grep -c "gh api -X PATCH"` returned **0** while the f-strings at `:1308/:1319/:1387/:2161` do emit PATCH remediations | TWO SELF-CAUGHT BAD GREPS, reported rather than quietly re-run |

## Standing rule for this directory

Edit any file here and re-register in the same PR
(`make evidence-register` then `make evidence-check`), or `make evidence-check` fails with
`UNREGISTERED`. Until new files are registered, that failure is **expected and correct** — it is the
control working, not a defect to silence. Two properties now hold that did not when this section was
written: a registered file that goes **missing** is a finding (`MISSING:`, exit 1), a run that
compared **nothing** is exit 2 rather than OK, and only files **tracked by git** can enter the
registry at all. Measured state: `46 files scanned, 0 mismatches`, exit `0`.

Verification practice adopted from FA-cross-07: run `--check` inside a clean clone
(`git clone` the branch, run it there) before asserting evidence integrity. A green result in a
working tree says nothing about the commit that CI will actually see.
