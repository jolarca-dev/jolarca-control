# Fleet Audit 2026-Q4 — index

Control plane baseline: `jolarca-control` `1ef4f9b05addc795a1dc8cafa18f1049ca7932fa`
(branch `docs/register-data-stores-d79`, PR #85 OPEN, `mergeStateStatus=BEHIND`).
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
| 3 | [`jolarca-control`](jolarca-control.yml) | `1ef4f9b05addc795a1dc8cafa18f1049ca7932fa` (branch head; `origin/main` = `bdbe971…`) | **NO-GO (assurance)** · CONDITIONALLY OPERATIONAL (control plane) — 3 of the S1s fixed in this PR, pending merge | 0 | 5 | 5 | 0 | 4 | 2026-10-26 |
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
(5 S1 / 7 S2 / 1 S3), consent 10 (1 S0 / 5 S1 / 4 S2), control plane 10 (5 S1 / 5 S2), i.e. **33
findings across 3 of 17 repositories: 1 S0, 15 S1, 16 S2, 1 S3**. An earlier
draft of this index carried hand-counted totals that were wrong in three cells, the same class of
defect recorded in the 2026-10-24 audit; the count is now derived from the machine-readable source
and re-checked by parsing the registers after every edit. That re-check caught a fresh instance of
the same class in this very file on 2026-10-26 — a hand-added S2 total of 17 where the registers sum
16 — corrected by the parse, not by recounting by hand.

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
| FA-cross-07 | S1 | **A gate's verdict depended on the working tree, not the committed tree.** `hash_evidence.sh` enumerated files on disk, so `make evidence-register` attested 26 rows for files git had never seen; CI, which only ever checks out the commit, scanned 46 files and reported `OK: all registered evidence hashes match` over 26 vacuous attestations. Found only by running the newly added reverse pass inside a clean clone (`git clone` → overlay script → `--check` → `46 files scanned, 26 mismatches`, exit 1). Fixed at the root: enumeration is now `git ls-files -z`, a non-repo or empty index exits 2, and a fixture proves an untracked file acquires no row. Registry corrected from 72 to 46 rows, all tracked. | FIXED IN THIS PR — lesson generalises to every fleet gate that reads `$REPO_ROOT` |
| FA-cross-08 | S2 | The register-integrity gate scans only `git ls-files` output (`check_findings_register.py:161`), so a dangling citation in an uncommitted draft is invisible until it is committed — proven in sequence here: 12:55 `no dangling citations`, then after `git commit` the same command reported the citation this audit had introduced. Correct-by-design (CI sees the committed tree) but the local reading must be stated, not assumed: `make findings-check` green does **not** cover work in progress. | VERIFIED — documented, not changed |
| FA-cross-06 | S3 | Concurrent tree modification observed mid-audit: `docs/evidence-registry.csv` gained 8 rows (` M`, registered 2026-10-26) and the rescue directory appeared between two probes of the same session. Verified **not** caused by the audit pass — `Makefile:33` (`lint:` = fmt-check tf-validate validate context-baseline py-lint py-type sh-lint yaml-lint test) contains no `hash_evidence.sh` call; register mode exists only at the `evidence-register` target (`Makefile:87`), which this pass never invoked. Recorded so a later reader does not attribute it to these findings. | VERIFIED — not audit-caused |

## Local gate baseline (jolarca-control, 2026-10-25, tree `1ef4f9b`)

| Gate | Exit | Status |
|---|---|---|
| `make lint` (fmt, tf-validate, validate, ruff, mypy, shellcheck, yamllint, pytest, shell fixtures) | 0 | VERIFIED PASS — 277 pytest + 67 shell cases: plan-gate 25, workspace-mode 13, hash-evidence 19 (new), state-backup 10 |
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
