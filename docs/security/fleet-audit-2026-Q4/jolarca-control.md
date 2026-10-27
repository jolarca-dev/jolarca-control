# Fleet Audit 2026-Q4 — `jolarca-dev/jolarca-control` (the control plane)

**Verdict: NO-GO as an assurance claim · CONDITIONALLY OPERATIONAL as a control plane.**
Four S1, five S2. No S0 — this repo's merge path really is gated, unlike the two
repositories audited before it.
Register: [`jolarca-control.yml`](jolarca-control.yml). Measured 2026-10-26.
Baseline: branch `docs/register-data-stores-d79` @ `1ef4f9b…`, `origin/main` @ `bdbe971…`,
PR #85 open (`BEHIND`), 7 open PRs, 15 scripts, 15 test files, 5 288 test lines, 277 tests collected.

Auditing the control plane against itself produces a different kind of evidence than auditing a
service repo: here the "system under attack" is **our own tooling's blind spots**. Three findings
below came from running a control against input it was never shown — including one experiment
that cost nothing and destroyed nothing.

---

## FA-control-01 · S1 — the evidence gate reports success over zero inputs

**What is wrong.** `scripts/hash_evidence.sh --check` compares files it finds on disk against the
committed registry. It never asks the reverse question: *does every registered row still have a
file?* The precondition guard (lines 52-64) catches a missing or header-only baseline, but nothing
floors the scanned count.

**How it was identified — by experiment, not by reading.** The script was copied to an isolated
tree, a file registered, the file deleted, and `--check` re-run:

```
$ mkdir -p /tmp/fakerepo/{scripts,policy,docs}; cp scripts/hash_evidence.sh /tmp/fakerepo/scripts/
$ printf 'policy A\n' > /tmp/fakerepo/policy/a.yml
$ bash /tmp/fakerepo/scripts/hash_evidence.sh
$ rm /tmp/fakerepo/policy/a.yml
$ bash /tmp/fakerepo/scripts/hash_evidence.sh --check
Evidence check: 0 files scanned, 0 mismatches
OK: all registered evidence hashes match
REVERSE_CHECK_EXIT=0
```

**Reproduce.** The block above, verbatim. No repository file is touched.

**Why it happens.** The loop is `find … -print0 | while read file` → for each file, look up its row.
A row with no file is never visited. A "0 files scanned" aggregate is printed from `total`, which
counts discoveries, not expectations.

**Impact.** Deleting evidence — `git rm docs/security/key-custody.md` — passes the control whose
whole purpose is to detect evidence tampering (SOC 2 CC4.1, ISO A.5.31, PCI-DSS 12.10.1). The
registry would keep asserting a hash for a file that no longer exists, and CI would go green.
**Current real state measured: 52 rows, 0 registered-but-missing** — so nothing is lost today. This
is a detection gap, not an incident.

**Compensating control, named honestly.** Git history records the deletion; an auditor diffing the
tree finds it. The point of a gate is that nobody has to — and this one does not fire.

**What should change.** Add a reverse pass in `--check`: for every row in the registry, assert the
path exists; missing → print `MISSING: <path>`, count it as a mismatch, exit 1. Optionally floor the
scanned count (a run over zero files is exit 2 "could not verify", never exit 0).

**How the fix is tested.** The /tmp fixture above becomes `tests/test_hash_evidence.sh` with three
cases: (1) register → check → exit 0; (2) delete a registered file → check → exit **1** with
`MISSING:`; (3) empty evidence dirs → check → exit **2**, not 0. This is the repo's own standard
(AGENTS.md §7) applied to a control that currently lacks any test.

**What could go wrong during remediation.** Every registered file must exist in CI's checkout, or
the new assertion turns a required-adjacent job red. Measured today: all 52 exist, so the change is
safe to introduce — but `docs/security/**` files added by an unregistered PR would fail *correctly*.
Do not "fix" that by relaxing the check; re-register in the same PR.

**Rollback.** Revert the script commit. The registry format is unchanged, so no data migration.

---

## FA-control-02 · S1 — evidence integrity runs, and cannot block

Live required contexts on `main` are exactly four: `Validate Repo Allow-List`,
`Policy Compliance Check`, `Repository Secret Pattern Scan`, `SAST (semgrep)`. The workflow's job
name is **`Evidence Integrity Check`** — not in that list. It triggers on `schedule` and on
`pull_request` for precisely the paths that matter (`docs/adr/**`, `audit/**`, `policy/**`,
`repos/**`, `docs/runbooks/**`, `docs/security/**`, the registry CSV, and `hash_evidence.sh`).

So: the control is *well built* — its header (lines 36-48) documents removing the register step from
the automatic path after the check was found to be tautological, which is exactly the right fix,
correctly reasoned. But the wiring makes it advisory: a PR that edits `policy/compliance-gates.yml`
without re-registering goes red **and merges**. This is my methodology's rule "it runs ≠ it is
required", applied to the repo that wrote the rule.

**Fix.** Add `Evidence Integrity Check` as a fifth required context. Order matters: land
FA-control-01's reverse check first, or you enshrine a gate that can pass on zero inputs.
Then `make context-baseline` / `check_required_context_baseline.py` must be updated in the same PR,
because that gate compares the declared baseline to the declaration — a mismatch there blocks the
very job it is describing.

**Risk.** Five required contexts on a Free-plan repo with `strict=true` means one more way for a PR
to wedge on an unrelated infrastructure flake. Acceptable for a governance repo; state the trade-off
in the PR description rather than discovering it during an incident.

---

## FA-control-03 · S1 — the tests that prove the deploy gate can fail are not merge-blocking

`Regression Tests` (job `test`) holds the negative controls for this repo's most dangerous path:
`tests/test_check_plan_safety.sh` (25 cases, including empty-plan and missing-plan → exit 2) and
`tests/test_state_backup.sh` (10 cases, including `skip-verify-is-not-a-pass` → exit 2). It also runs
the 277-test suite. **None of it is required.** `Lint` and `Terraform Format` are advisory too.

Why that matters concretely: `apply.yml:150` runs `bash scripts/check_plan_safety.sh plan.txt`
immediately before `terraform apply -input=false -auto-approve tfplan`. The refusal gate is the last
brake, because `STATE_MIGRATION_COMPLETE` measures `true` (so the Makefile refusal is not the
protection). If a refactor quietly breaks the patterns, the *fixtures that would catch it* are a red
tick mark on a PR that still merges — and the next merge into an apply path meets a weakened gate.

**Fix.** Make `Regression Tests` a required context. It passes today (exit 0, 277 passed), so it can
be required without deadlocking anything — the check to do first is exactly that: **never require a
context that has not reported green** (the A-01/`Verify Chain` lesson from `jolarca-consent`).

**Countervailing risk.** Requiring tests on every PR plus `strict=true` means every Dependabot PR
must pass 277 tests; today Dependabot PRs #82 and #68 sit open 6-14 days. That is a queue problem,
not a reason to keep the gate advisory — fix the queue (FA-control-09).

---

## FA-control-04/05/06/07/09 — summary

| ID | Sev | Defect | Evidence (measured 2026-10-26) |
|---|---|---|---|
| FA-control-04 | S2 | `code_quality` is `enforcement: mandatory` and lists `"pytest --cov --cov-fail-under=80"`, but CI runs a bare `pytest tests/ -q` (`compliance-scan.yml:180`) and `pyproject.toml` has **no** `[tool.coverage]` block and no `fail_under` | grep for `--cov` across `.github/workflows/` → none |
| FA-control-05 | S2 | 3 of 16 gates have no dedicated test file: `check_fleet_separation`, `org_delivery_audit`, `check_secret_inventory` — and `check_secret_inventory` landed from PR #86 **while this audit was running**, so the finding is a process gap, not a one-off: nothing in CI asks whether a new gate carries a negative control. `hash_evidence` was in the original three and is now covered by this PR's 19-case fixture | script↔test name mapping, re-measured after merging `origin/main` |
| FA-control-06 | S2 | `Lint` (ruff, mypy, shellcheck, yamllint) and `Terraform Format` run on PRs but are not required | context list vs job names |
| FA-control-07 | S2 | `required_signatures.enabled=false` while signed commits are policy (D-05 pattern; `jolarca-consent`'s commits are all `verified=true`) | protection document |
| FA-control-09 | S2 | 7 open PRs, #40 (2026-10-05) and #79 (2026-10-17) are documentation-accuracy fixes unmerged 9-19 days, so `main` still carries the text they were opened to correct | `gh pr list` |

---

## FA-control-08 · S1 — the apply path: what is actually true today

Read carefully, because this is the highest-consequence surface in the fleet and several
long-standing notes about it are imprecise.

**Measured:**
- `apply.yml` triggers on `push: main` for `repos/**`, `policy/**`, `*.tf`, `*.tfvars`, and itself.
- Job `prod-apply` declares `environment: production` (lines 57-59). **Consequence:** the
  environment-level secret `TF_GITHUB_TOKEN` is reachable by that job. Repo-level secrets are
  `TFC_TOKEN` and `TF_GITHUB_TOKEN_READONLY`; there are **no org-level secrets**.
  *(I nearly recorded "workflow cites a missing secret" — checking environment and org scopes first
  killed that finding. A repo-secret listing is not the set of secrets a job can see.)*
- `actions/variables`: `STATE_MIGRATION_COMPLETE=true` → the Makefile refusal is not the brake; the
  brake is `check_plan_safety.sh`.
- `production` environment protection: `wait_timer=30`, `required_reviewers=[JourneyOfLife]`,
  `prevent_self_review=false`, `can_admins_bypass=false`.
- `apply.yml` runs, last 8 (2026-10-15→10-17): **4 failure, 4 cancelled, 0 success**.

**Two conclusions an operator should act on:**
1. **The approval is self-approval.** The sole reviewer *is* the sole author and self-review is
   allowed by design (deliberate, recorded in `policy/compliance-gates.yml`). So the 30-minute wait
   buys a **cancel window**, not a decision. Treat a merge into an apply path as the apply decision —
   as AGENTS.md already says — and use `gh run cancel <id> --force` inside those 30 minutes.
2. **The refusal gate has never been observed firing in production.** No successful apply in the
   window means `check_plan_safety.sh` has never refused a real plan on that path; the evidence that
   it works is its 25 fixtures — which are advisory (FA-control-03). That is a thin chain for the one
   control standing between a merge and a fleet-wide mutation.

**What should change.** (a) ~~Require `Regression Tests` and `Evidence Integrity Check` as required
contexts~~ — **this proposal was withdrawn on 2026-10-26 after measurement**; see "Reviewing my own
proposal" below. (b) Rehearse
the apply path on a synthetic plan that *must* be refused, in a controlled window, and retain the
refusal log as evidence — the rehearsal is the thing that converts a hypothesis into a control.
(c) Add a gate that fails when a workflow cites a secret that is not defined at repo, org **or**
environment scope — the rule PR #79 proposes ("workflows may not cite paths that do not exist");
note that its register id is not on `main` while #79 stays open, which is why this file cites the PR
and not the finding id.

**Rollback / blast radius.** Every item here is configuration in this repo: reverting the PR restores
the prior state. Nothing above touches `*.tf` semantics or live GitHub resource state, so no
`terraform apply` is implied — which matters, because a merge to `main` changing
`branch-protection.tf` or `repos/**` *would* reach the apply path.

---

## Two previously-unverifiable items are now verified (corrections to the record)

`index.md` and the 2026-10-24 audit both carried org 2FA and org repo-creation as BLOCKED/unreadable
on the Free plan. Re-measured with the correct field names:

| Item | Old claim | Measured 2026-10-26 |
|---|---|---|
| Org 2FA | "`two_factor_auth_enabled = null` on Free → cannot verify" | **`two_factor_requirement_enabled = true`** — the readable field exists; `two_factor_auth_enabled` is indeed `null`. PCI-DSS 8.3 / SOC 2 CC6.1 evidence now available |
| Members creating repos | D-19: "detection, not prevention — `members_can_create_repositories` is still true" | **`false`** — prevention exists; `default_repository_permission = none` |

Both were closed by looking for a sibling field rather than accepting the unreadable one — the
`plan_limited`-vs-`missing` distinction `drift_detect.py` already draws for branch protection.

## Reviewing my own proposal (the reason two of these fixes look different from the plan)

The remediation plan this file first carried said: *require `Evidence Integrity Check` and
`Regression Tests` as required contexts 5 and 6, both pass today, so no deadlock.* That was wrong,
and the repository's own gate is what proved it.

1. `evidence-integrity.yml` triggers on `pull_request` **with** a path filter — eight patterns
   (`docs/adr/**`, `audit/**`, `policy/**`, `repos/**`, `docs/runbooks/**`, `docs/security/**`,
   the registry CSV, `scripts/hash_evidence.sh`). A PR touching anything else never starts that job,
   so the context never reports. With `strict = true`, every such PR sits forever on "Expected —
   Waiting for status to be reported". **Requiring that job would have wedged the control plane.**
2. `scripts/check_required_context_baseline.py:140-141` already encodes exactly this rule
   (`continue  # path-filtered: cannot report on every PR, so cannot be required`), with a named
   fixture `test_path_filtered_workflow_cannot_back_a_required_context`. So the change I proposed
   would have been refused by CI on the PR that proposed it. Recorded here because the near-miss is
   the lesson: **read the gate before proposing the wiring.**
3. `Regression Tests` *is* producible on every PR (its workflow has no path filter), so it is not
   unsafe — but making it required is a **live branch-protection mutation**, and every channel for
   that is closed to an agent by design: AGENTS.md §5 forbids out-of-band `gh api -X PATCH`, the
   rules are Terraform-owned, and `check_plan_safety.sh` refuses protection attribute changes in
   either direction (D-61) until state-migration runbook step 6 closes. It is therefore left as an
   operator decision (FA-control-03), not smuggled in.

What was implemented instead achieves the same enforcement with no protection change: the evidence
verdict runs as a step **inside** the already-required `Validate Repo Allow-List` job, which is this
repo's established convention for exactly this problem (`check_deploy_gates.py`,
`check_findings_register.py` and `check_declared_contexts.py` are all wired that way, and
`compliance-scan.yml:45-49` documents a gate that once lived only in a path-filtered workflow and
"could describe a merge-killing declaration and still let the PR merge").

## What the reverse check found the moment it ran against CI-equivalent state

Locally the fixed gate passes (72 scanned, 0 mismatches) — which is not the interesting result, because
the working tree has files that **git does not have**. Cloning the branch to `/tmp`, overlaying the new
script, and running `--check` there:

```
MISSING:      docs/security/pre-deployment-audit-2026-10-25/sweep6.sh
… 24 more …
Evidence check: 46 files scanned, 26 mismatches
FAIL: 26 registered evidence file(s) no longer exist.
CI_EXIT=1
```

**26 of the 72 registry rows attest hashes for files that were never committed.** Before the fix,
CI saw 46 files, found nothing wrong, and reported OK — 26 attestations were vacuously true in the
one environment that matters. That is FA-cross-04's "not attributable to a commit SHA" made
concrete, and it is why the reverse check had to be written before it could be run: no amount of
reading the local output would have shown it.

The fix is to commit the evidence, not to relax the check. Before doing that the directory was
scanned for publication risk, because this repository is **public**: `gitleaks dir` over 471 KB
returned no leaks; no private-key or token-shaped material anywhere; the only addresses present are
the role mailboxes the fleet already publishes in its SECURITY.md files plus the GitHub noreply
identity, so committing quotes nothing that was not already public (D-59 context noted in the
record). 44 files, 552 KB.

## Landed: what main proves today

PR #89 squash-merged to `main` as **`e5b9b3f6a3e70119374a5cabcf807d3d445c6b89`** on 2026-10-26.
The three closed S1s are now observed, not configured:

- push run **40329048473** (`event=push`, `head_sha=e5b9b3f`, `success`) ran the step
  `Evidence hashes match the committed registry (CC4.1)` **inside the required**
  `Validate Repo Allow-List` job and printed `Evidence check: 46 files scanned, 0 mismatches`.
  That line is the enforcement proof — a config file only claims intent.
- fresh clone of `main`: `--check` → 46/0 exit 0; `gitleaks git .` over 2.17 MB → no leaks.
- no `Terraform Apply` run was created by the merge (latest remains 2026-10-17, cancelled), so
  the "no apply path touched" claim in the PR held under real conditions.
- protection re-read after merge: 4 required contexts, `strict=true`, `enforce_admins=true`,
  `required_linear_history.enabled=true`; declared visibility (`repos/jolarca-control.yml`: `public`)
  equals live, `forks_count=0`.

**What this does not buy.** A Type I observation dated today. CC4.1/A.5.31/12.10.1 cannot be claimed
for any period *before* 2026-10-26, because the control demonstrably reported OK over zero inputs and
over 26 unattestable rows throughout that period — recorded in
`framework_claims_not_supported`, not smoothed over. Type II needs run history that does not exist yet.

PR #85 was closed as superseded: this branch was cut from its head commit, and
`git diff --numstat origin/main 1ef4f9b` returns nothing for all three of its files, so its content
landed inside #89. Closing (not merging) states the true history; GitHub still lists those files
because the PR's diff is computed against its merge base.

Open S1s on this repo after the merge: **FA-control-03** (fixtures advisory — needs a live
protection change, operator decision) and **FA-control-08** (apply path never observed refusing).

## Landed, second observation: PR #91 (`main` = `4e0c22b`)

PR #91 squash-merged at 2026-10-26T14:20:37Z as **`4e0c22bd64fe9d7ab3ff44eabf7242e322555f34`**,
closing **FA-control-05** (no parity rule existed) and **FA-control-11** (the unwired, dead-path
gate).

- Push run **40338769793** (`event=push`, `success`) shows the step
  `Gate parity — every gate has a control that can fail (D-80)` **inside the required**
  `Validate Repo Allow-List` job, printing `OK: 17 gate scripts each have a fixture or a dated
  baseline entry; every shell fixture runs in a PR-triggerable workflow; no gate is unreferenced`.
  All six jobs on that run succeeded, and the evidence step again printed `46 files scanned,
  0 mismatches`.
- Independent read rather than a re-read of the log: fresh clone of `main` → gate parity exit 0,
  `hash_evidence.sh --check` 46/0, `gitleaks git .` over 2.60 MB → no leaks; `make findings-check`
  → 79 headings, no collisions, no dangling citations (so D-80 is defined, not merely cited).
- **The designed red is now visible in CI, which is the whole point of the change**: the
  `Deploy Gates` push run on the same SHA failed at `Credential expiry register is dated and
  unexpired (D-80)` with the annotation `expiry unknown for a row in
  docs/security/key-custody.md — verify and record it`. Before this change that verdict existed
  nowhere. #91's `mergeStateStatus` read `UNSTABLE` — required checks green, one non-required check
  red — so the signal costs no merge capacity and blocks nothing (FA-control-03 is still the reason
  it cannot block).
- No `Terraform Apply` run was created by the merge (latest remains 2026-10-17T19:07:46Z,
  cancelled); the diff touched no `*.tf`, `*.tfvars`, `repos/**` or `policy/**` path.
- Blind spot checked rather than assumed: this repo makes no reusable-workflow calls (grep for
  `uses: ./` and `uses: jolarca` under `.github/workflows/` → no matches), so R2/R3 reading only
  `run:` steps costs nothing today. If a fleet repo later calls a shared workflow, those two rules
  must learn to follow `uses:` — otherwise a real invocation would look like a finding, and a
  fixture hosted only in the shared workflow would look unrun.

## FA-control-11 · S1 — a gate that runs nowhere, reading a path that never existed (D-80)

The audit's own FA-control-05 recurred while its fix was being written, which is the clearest
possible argument for a rule instead of more files.

`scripts/check_secret_inventory.sh` arrived on 2026-10-20 in PR #86 (adding commit `bdbe971`):

| Component | Measured 2026-10-26 | Consequence |
|---|---|---|
| Input | default `docs/SECRETS_INVENTORY.md`; `git log --all --oneline --diff-filter=A -- docs/SECRETS_INVENTORY.md` → 0 lines; `git ls-files` → empty | run as documented, `::error::… not readable — an unreadable register is not a pass`, exit **2**, forever |
| Invoker | `git grep -n check_secret_inventory origin/main -- Makefile '.github/workflows'` → exit 1 | the verdict was read by nobody; `git grep -l` finds the name only in prose |
| Intent | `docs/security/key-custody.md:33` — its table is "the single `expires`-bearing block the gate parses"; `:41` — `TFC_TOKEN` `expires = unknown`, "until then the gate is red by design" | pointed at the real register: two `ok:` rows (2027-01-08, 2027-01-15) then `::error::expiry unknown`, exit **1** |
| Sister defect | `tests/test_check_workspace_execution_mode.sh` self-reports `13 passed, 0 failed`, invoked only by the Makefile; `origin/main` had four `.sh` fixtures and three were wired | `pytest tests/` cannot collect `.sh`, so 13 real cases could never fail a merge |

A control designed to be red, connected to nothing, reports green forever. The fail-closed signal
was swallowed not by `|| true` or `continue-on-error` — the classes `test_ci_gates_are_real.py`
already hunts — but by absence, which no existing gate could see.

### The control that gates the controls

`scripts/check_gate_parity.py`, wired into `Validate Repo Allow-List` (a live required context, so
it blocks a merge): **R1** every `scripts/*.{py,sh}` needs `tests/test_<name>.{py,sh}`; **R1b** that
fixture must name its subject; **R2** every `tests/*.sh` must be invoked by a `run:` step in a
workflow that can trigger on `pull_request`; **R3** every script must appear in a Makefile recipe or
a parsed run step; **R4** the no-fixture baseline may only shrink, and a stale entry fails.

| Negative control (on a copy of the real tree) | Result |
|---|---|
| baseline | `OK: 17 gate scripts each have a fixture or a dated baseline entry`, exit 0 |
| add `scripts/check_brand_new_gate.sh`, no fixture | `R1=1, R3=1`, exit 1 |
| add a script whose fixture is wired nowhere | `R2=1, R3=1`, exit 1 |
| replace `tests/test_hash_evidence.sh` with `exit 0` | `R1b=1`, exit 1 |
| restore | exit 0 |
| add an unparseable workflow | exit **2**, `CANNOT-VERIFY: cannot parse …/broken.yml` |

Two defects in the new gate were found by its own fixtures, and both are the interesting kind.
(a) The first draft `continue`d after hitting a `NO_FIXTURE_BASELINE` entry, which also skipped
R3 — measured before the fix: a script that was *both* baselined *and* unwired produced
`findings: []`. An exception that forgives two rules is an off switch, and §5 forbids turning a
gate off to make a pipeline pass, so R3 is now unconditional with a fixture pinning it. (b) Raw
text matching let **prose** satisfy liveness — a YAML comment, a `#` line inside a shell `run:`
block, and this gate's own docstring all named scripts without running them, so the draft passed
the exact defect it was written to find. Workflows are now parsed for `- run:` bodies and comment
lines are stripped from both corpora.

**Judgement on where the red signal belongs.** `check_secret_inventory.sh` runs in
`deploy-gates.yml`, an *advisory* job — verified: `gh api
repos/jolarca-dev/jolarca-control/branches/main/protection --jq
.required_status_checks.contexts` → `Validate Repo Allow-List`, `Policy Compliance Check`,
`Repository Secret Pattern Scan`, `SAST (semgrep)`. Promoting an intentionally-red check to a
required context would wedge every PR (the A-01 deadlock shape), and its register row cannot be
fixed from here: the `TFC_TOKEN` expiry is a production-scope secret that HCP Terraform describes
only to its holder, so the honest interim state is a visible red in a non-blocking job — not an
absent signal, and not a weaker gate. It is excluded from `make lint` for the adjacent reason: a
permanently-red local gate trains everyone to append `|| true`.

Not claimed: that the credential risk is closed, that any other repository is covered (the parity
gate reads this repo's `Makefile` and workflows only), or that this is Type II evidence. What lands
is one S1 control operating on the merge path, and a rule that makes the class expensive to repeat.

## Controls that came out of verifying the first one (D-81, D-82, D-83)

The instruction was "housekeeping: re-run/sync the Dependabot PRs, then resume the audit". Both
halves turned into findings, which is what measuring instead of assuming tends to do here.

**D-81 — a dependency bump can be a deploy decision.** `apply.yml`'s `push.paths` include
`.github/workflows/apply.yml` itself, and §5 forces actions to be pinned by SHA, so the pins live in
the files the trigger watches. `gh pr diff 87 --name-only` and `gh pr diff 68 --name-only` both list
it. Merging either would emit a `main` commit that arms `terraform apply -input=false -auto-approve`
with nobody having read a plan — the fleet's own D-58 exception says the 30-minute wait is delay,
not approval. `scripts/check_apply_path_trigger.py` now runs inside the required
`Validate Repo Allow-List` job for `pull_request` events, **reads** the trigger set from `apply.yml`
(so it cannot drift the way the required-context baseline did, D-62), refuses **bot/app** authors and
passes **human** authors with a `NOTICE`. The asymmetry is the point: refusing human Terraform work
would manufacture the A-01/FA-control-03 deadlock, while a bot's bump stays mergeable — by a person,
same diff, deliberate. Verified against live inputs before wiring: #87 and #68 → exit 1, this repo's
own docs PR #93 → exit 0. Two bugs were caught first, one by fixtures and one only by the live run:
`path.lstrip("./")` is a character-set strip and had made `.github/workflows/apply.yml` unmatchable
(the gate reported "no apply armed" on precisely the PRs to refuse), and
`gh pr view --json author --jq .author.type` returns an empty string, so the actor kind must come
from `github.event.pull_request.user.type`.

**D-82 — "operator-only" was re-probed, and the probe moved D-77.** The pending action said the
`TFC_TOKEN` expiry can only be read in the HCP UI. Testing that claim rather than inheriting it:
the operator's own CLI credential in `~/.terraformrc` (never printed) returns **HTTP 200** on
`/api/v2/organizations` → `['jolarca-dev']`, on `/api/v2/account/details` → user `journey4oflife`,
on the workspace, and on `…/runs`. Every token-expiry route tried (`organization-tokens`,
`organization-token`, `teams/owners/team-tokens`, `state-versions`) answers **HTML 404** — a route
that resolves nothing, which per §3 is "could not verify", not "does not exist". So the date really
is UI-only and `unknown` stays (padding it would convert a visible red into a silent false clean —
the D-80 class). But the 200s are the positive control D-77 said was missing: the API host, the org
name, the workspace slug and the auth-header shape are all proven correct from this host, leaving
the CI credential as the only unproven input. And `…/runs` shows **three runs in the org's whole
history, all `Triggered via CLI`** — the GitHub Actions path has never produced an HCP run, so
`resource-count: 48` is what the last CLI run left, and D-77 blocks every route through the remote
backend, not just the PR-time plan.

**The blocking claim is now observed, not inferred.** Throwaway PR #94 added
`scripts/probe_untested.sh` with no fixture and no invoker, deliberately unmerged:
`Validate Repo Allow-List` failed with `RESULT: 2 parity finding(s): R1=1, R3=1`, `Regression Tests`
failed independently on `test_real_repository_has_parity`, and the PR read
`mergeable=MERGEABLE` / **`mergeStateStatus=BLOCKED`**. That retires the register's longest-standing
`not_run` item, which had leaned on a 2026-10-12 `GH006` push rejection — evidence about the push
path, not about required checks.

**The third D-81 defect was in the gate's own wiring, and only a fixture could have caught it in
time.** The new step fetches the PR's file list with `gh api repos/…/pulls/<n>/files`. GitHub's rule
is that a `permissions:` block sets every scope it does not name to `none`, and a job's block is
applied after the workflow's — so the `validate` job, which declares only `contents` and `actions`,
could not reach the pulls API even though the workflow declares `pull-requests: read`. The call
would 403 under `bash -e`, the step would fail, and because that job's name **is** one of the four
required contexts, every PR in the repository would have become unmergeable — the deadlock shape
this gate was explicitly written to avoid. Found offline by asserting the scope against the
workflow YAML; the assertion was then proved by deleting the line (`assert None == 'read'`), and the
file restored to byte-identical (`diff` exit 0). Same job, same class, already in git history: #41
had to add `actions: read` for the environments API.

**D-83 — three gate surfaces, none of them compared to another.** Reviewing D-81 meant running the
CI `Lint` job's commands, and `ruff format --check scripts/ tests/` wanted to reformat 13 hunks in
the new fixture while `make lint` had exited 0 on the same tree. `lint`'s own Makefile description
says "Everything CI runs before a plan"; `py-fmt-check` is in `lint` now — a gate strengthened, not
weakened (§5).

This row began as an S2 claiming the formatter was unenforced locally, and **that premise was wrong**.
Two commands refute it: `.pre-commit-config.yaml` declares `id: ruff-format`, the hook is installed
(`.git/hooks/pre-commit`, 2026-09-26), `pre-commit run --all-files` passes all twelve hooks, and the
very commit attempt that prompted the check was *refused* by `end-of-file-fixer` — direct evidence the
mechanism fires here. Severity revised to **S3** on the measured premise, keeping the row rather than
deleting it. What survives is the narrower and still real observation: this repository has three
overlapping gate surfaces — `make lint`, the hooks, the CI jobs — and nothing asks whether a command
in one appears in the others. AGENTS.md §2 instructs an agent to run `make lint`, and a session can
live inside it without ever invoking the hooks (this one did, dozens of times); hooks see staged files
only; a fresh CI clone has no hooks at all. Recorded as FA-control-13 (`status: gap`) rather than
closed by assertion, because writing that comparison rule is itself a gate change needing its own
negative control.

## The brake could not see the second protection layer (D-84, and the D-46 decision it unblocks)

Answering the consent ruleset question required knowing what the provider can express, so
the schema was read — and the first question a schema raises is what enforces the object
before and after it enters state. `grep -ic ruleset scripts/check_plan_safety.sh` → **0**. The
fleet's pre-apply brake (AGENTS.md §8 calls it the thing that stands between a merge and an
apply; `apply.yml` then runs `terraform apply -input=false -auto-approve tfplan`) refuses
branch-protection creates and attribute changes, and has no rule that can see a ruleset at
all — while consent, dr and vendor are protected **only** by rulesets (D-46).

Blindness was proven by feeding the gate plans, not by reading its patterns. Three synthetic
renderings in Terraform's own format, run against the unfixed script, all exited **0**: a
`github_repository_ruleset.main["jolarca-consent"] will be created` block carrying only
`deletion` + `non_fast_forward`; the same address `will be updated in-place` with
`enforcement = "active" -> "disabled"`, `deletion = true -> false`, `non_fast_forward = true ->
false` and a fresh `bypass_actors { actor_type = "RepositoryAdmin" }`; and an org-ruleset
weakening. The middle one removes protection from a tier-1 GDPR repository and the gate prints
"Plan contains no … protection-layer change …" over it. This is D-22's class for the fourth
time in this register: the gate's real coverage was defined by the first object it was written
for, and it passed ruleset plans only where they incidentally touched a shared token
(`required_status_checks`).

The fix is four refusals — create by address, every other action by address, a resource-header
belt, and a ruleset-only attribute vocabulary — refusing ruleset changes in **both**
directions, unlike the security-feature rule that allows enabling: requiring a context no
workflow reports deadlocks every merge on that repo (`jolarca-identity` already paid for that
once, D-44/D-47). Four fixtures, one of them the non-vacuity control (`ruleset-refresh-only-noise`
must exit 0, or the adoption plan in step 6b could never pass its own gate). 29 cases pass,
25 before. `make lint`'s shellcheck step then caught a defect in the fix itself: the reason
strings are double-quoted shell arguments, so backticks in them were command substitution —
which had already created a 0-byte file named `disabled` in the working tree from
`… -> "disabled"`. Rewritten with single quotes, file deleted; recorded because the local
surface that caught it is the one D-83 said was not compared to CI.

The decision itself, with the measurement behind it, is written into `docs/drift-findings.md`
D-46 and the operator procedure into `docs/state-migration-runbook.md` **Step 6b**: option **A**
(adopt the rulesets as `github_repository_ruleset`), consent first, because option B (delete the
rulesets, let the legacy rule be the single source) would leave all three repos with **no**
protection layer at all until an apply lands — and CI has never reached the HCP workspace
(D-82), so the window is unbounded. What was measured, not assumed: consent's ruleset carries
three push rules and **neither** `pull_request` **nor** `required_status_checks` (so its 7
declared contexts are enforced by nothing and `main` is directly pushable — the mechanism of
the historical no-PR commit, still open); provider 6.13.0 **can** express the missing status
checks (`rules.required_status_checks.required_check`) but **cannot** model
`dismissal_restriction` or `require_extra_approval_for_unattributed_changes`, both live in dr's
and vendor's payloads; and the import id is `<repo>:<ruleset_id>` because the importer calls
`parseID2`, which splits on `:` — the same import-id ≠ state-id trap that broke the runbook's
original branch-protection instructions. Nothing was imported, patched or planned against
production: §5 reserves `terraform import` to the operator, and the staged HCL stays in the
runbook until the PR that lands it is run immediately followed by the import, because a
declared-but-unimported ruleset makes the plan want to create a **second** ruleset beside the
one in force.

## Landed, third observation: PR #95 (`main` = `7048116`)

Squash-merged 2026-10-26T17:23:58Z with the branch deleted. What `main` proves today, per the
table in `index.md`:

- **The D-81 brake runs on the merge path.** In the required `Validate Repo Allow-List` job of PR
  run 40358205519 it printed `OK: 13 changed file(s), none in apply.yml's push paths (5 pattern(s)
  read from apply.yml) — no apply armed`, with `PR_ACTOR_TYPE: User` and shell `bash -e {0}`. That
  single line also disproves the 403 I had written into the wiring: the job-level
  `pull-requests: read` scope really does reach `gh api …/pulls/<n>/files`.
- **What it does *not* prove, stated because it is tempting to assume.** The step is gated to
  `pull_request`, so on the merge's own push run it reports `skipped`; and the bot-refusal branch
  has still never rejected a live PR — #87/#68 were left open and un-rerun on purpose. The assurance
  for that path is 21 fixtures plus a run against the committed tree (Bot + `apply.yml` → exit 1).
  A control observed in one event class is a control observed in one event class.
- **Nothing armed.** No `Terraform Apply` run exists after `2026-10-17T19:07:46Z` (cancelled), which
  now corroborates D-82's separate HCP read: three runs in the workspace's history, all CLI.
- **Protection unchanged** and re-read after the merge: 4 contexts, strict, admins, linear history,
  conversation resolution, `allow_force_pushes=false`, `allow_deletions=false`, signatures off,
  rulesets `[]`. Two fields had to be read as objects (`{enabled: false}`) rather than scalars — the
  same jq-path trap that made an earlier probe report `strict: null`.
- **Two of this PR's own claims were refuted and kept.** D-83's "nothing local runs the formatter"
  (all twelve pre-commit hooks pass, including `ruff-format`, and a commit on this branch was refused
  by `end-of-file-fixer`) → regraded S2→S3. FA-control-11's `D-22a` note was briefly overwritten with
  the opposite claim after an **empty grep output through an unreliable capture channel** was read as
  absence; the heading is at `docs/drift-findings.md:235` and `parse_headings()` returns 82 where the
  raw count is 83. The wrong text lived only in the branch's intermediate commit `e07dc54` and was
  superseded by `403ad80` before the squash, so `main` never carried it.

Regression surface on `main`: 316 pytest tests, five shell fixtures at 25/19/19/13/10, gate parity
18 scripts, evidence 46 files / 0 mismatches, gitleaks clean over 2.25 MB of history.

## The register asserted a fix that was on no branch (D-85, D-86)

The next planned step was to start repo 2 by running `make readiness
REPO=jolarca-infrastructure` and filling in the audit template. That step was
rejected before execution, and the rejection is the finding: the instrument would
have produced a tidy verdict over a repository whose committed tree did not contain
the safety controls this register says were applied on 2026-09-25.

The method was the one D-84 records — do not read a claim, read the artifact the
claim names. A fresh clone of `jolarca-dev/jolarca-infrastructure` at `8f02d17`
(`origin/main`, public) gives `variable "org"` default `journeyoflife-org` in
`terraform/environments/production/variables.tf:79` and
`terraform/modules/github-org/variables.tf:4`; `provider "github" { owner = var.org }`
and `module "github_org"` are live, declaring `github_repository.repos`,
`github_repository_vulnerability_alerts.repos` and `branch-protection.tf`; there is no
committed `terraform.tfvars` for that environment, so the default is what a plan uses;
`git grep -n lifecycle HEAD -- terraform/environments/production terraform/modules/github-org`
returns nothing — the four committed `prevent_destroy` are all in
`modules/state-bucket`, on GCS/KMS objects — and every committed `FROZEN` match is
about bucket *names*, not a plan/apply banner. `git log --all -S "FROZEN — DO NOT PLAN
OR APPLY"` returns **0 commits**, and the last commit touching that module is
`0f5e34a` on **2026-08-31**, a month before the date the fixes claim. Meanwhile
`docs/drift-findings.md` D-06 said "Fix applied … See `jolarca-infrastructure`
**working-tree diff**", D-13 said "Control in place: `prevent_destroy = true` on every
`github_repository`" and "Resolved — dual ownership eliminated", and
`docs/state-migration-runbook.md` said "**Status:** COMPLETE (2026-10-10)" while its own
step 1 instructed the reader to "Land this as a signed PR **before** step 2 so the
freeze is in git history, not just on disk". All four step-1 expectations fail at HEAD.

The fix was real. It was nine uncommitted entries, +133/−98, on one workstation:
the banner, `prevent_destroy` in three files, `default = "jolarca-dev"` twice, the
`.bak` deletion and the superseded guard header. That is FA-cross-07's class — a
verdict that depends on how the input was rendered, here on which tree was read —
recurring inside the change register a SOC 2 CC8.1 / ISO 27001 A.8.32 auditor would
use to decide what to test. It is worse than the gap it hides, because a correct
record of an unclosed gap is actionable.

**It was not hypothetical, and the mechanism of the delay was not negligence.**
That repo's `terraform.yml` runs a `plan` job on every `pull_request` touching
`terraform/**` (`terraform init -backend=false && terraform plan -lock=false`,
`TF_GITHUB_TOKEN_READONLY`). Runs `39925547516` and `39925560368` (2026-10-23,
Dependabot, both **success**) posted `Plan: 16 to add, 0 to change, 0 to destroy` as
comments on public PRs, with the mission-platform org as the target. `apply` is
`if: github.event_name == 'workflow_dispatch'` — the only thing that kept it a read.
And the reason no PR had landed the freeze since `0f5e34a`: required contexts are
`ci, security, compliance` with `enforce_admins = true`, and `compliance-check.yml`
demands seven governance files. `jolarca-infrastructure` is the **only** fleet repo
without `.github/CODEOWNERS` (10 of 11 others have one), so the required `compliance`
context failed on every PR, Dependabot's included, and the admin bypass that would
normally rescue a repo like that was switched off. Welded shut, which from outside is
indistinguishable from abandoned.

Landed as infra **PR #49**: `2eab214` moves the on-disk freeze into history verbatim —
no re-authoring, no new decisions — and `693ec82` adds the missing `.github/CODEOWNERS`
with the identical entry `jolarca-control` publishes (`require_code_owner_reviews` is
false as declared and as live, so it adds no review burden and only clears the
file-existence check). Both signed (`%G?` = `G`); that repo's own pre-commit ran
`terraform fmt`, `terraform validate`, `tflint` and Checkov, all offline. After the
second commit `ci`, `security` and `compliance` all read **pass** and `apply` reads
**skipping**. **No Terraform command was run by this change and none was run in that
root** — but the honest caveat is that CI's plan job fires on any PR touching
`terraform/**`, so a plan against the corrected default did run as part of the PR.
It is open, not merged; the freeze is not in `main` until the operator merges it.

D-86 is the quieter half of the same episode. `repo_readiness_audit.py --repo
jolarca-data` exits **1**; `make readiness REPO=jolarca-data` exits **2** — and a
synthetic Makefile target that runs `exit 1` also makes make exit **2**, so this is
GNU make's contract, not a bug in a recipe: no `make <gate>` can ever carry §3's
three-valued code. Eleven scripts here do implement that code. Two targets
(`readiness`, `first-commit`) additionally ended in `>/dev/null`, and because these
scripts put their one-line table on stderr and their detail on stdout, what survived
looked like a terse gate rather than a muzzled one (85 and 128 bytes of make echoing
its own recipe, versus 373 and 808 bytes of table). The recipes no longer discard
stdout — verified: the same command now yields 7849 bytes of detail — and AGENTS.md §2
and §3 now say the three-valued code lives on the script, so evidence collection calls
the script. No script's own codes were changed to suit the wrapper; that would invert
the convention §3 exists to protect.

Two of my own measurements were wrong on the way here and are recorded rather than
quietly re-run. A repo-wide `grep -rc prevent_destroy` returned non-zero counts and
`FROZEN` returned three, which read as a refutation of the report I was validating —
but they were `modules/state-bucket`'s GCS guards and bucket-name prose, and the
scoping `git grep` against the GitHub path was the measurement that mattered. A
`grep -c "gh api -X PATCH"` over `repo_readiness_audit.py` returned **0**, which read
as a refutation of the claim that the gate emits §5-forbidden remediations; the
f-strings build those strings with `{ORG}` in the middle, so the literal never
appears, and `grep -n PATCH` found all four sites including `-F private=` — a
visibility flip. Same lesson as D-85, applied to myself: a zero from a pattern is a
claim about the pattern.

## Method notes

1. Three of my own probes were wrong and are recorded as wrong: a `sed`-based script↔test comparison
   that falsely indicted 15 gates (fixed in Python — the truth is 12 of 15 covered); a `yaml.safe_load`
   read of `on:` that returned `None` for every workflow because YAML 1.1 parses bare `on` as `True`;
   and a `--json defaultBranchRef.name` field path `gh` rejected. An empty or odd result is a
   property of my tooling until proven otherwise. This session added a fourth instance of exactly that
   lesson, and it went the other way: an **empty** result was trusted. A `grep` for sub-lettered `### D-\d+[a-z]`
   headings returned nothing through the shell tool's capture channel while the tool's side effects
   still ran, the emptiness was read as absence, and a correct audit note was overwritten with a false
   one in commit `e07dc54`. Caught by re-running the claim through the parser itself (82 parsed vs 83
   raw) and repaired in `403ad80` before the merge. Corollary for any session on this host: when a
   command prints nothing, that is an *unread* result, not a measurement — re-issue it through a file
   and read the file back, and prefer calling the program that owns the pattern over emulating it.
   Validating another session's report on 2026-10-26 produced a fifth and sixth instance, both of
   which pointed the wrong way — they made a true claim look false. A repo-wide `grep -rc
   prevent_destroy` and `grep -rn FROZEN` returned counts that appeared to refute "the guard is
   absent": the hits were `modules/state-bucket`'s GCS/KMS guards and prose about frozen *bucket
   names*, not the GitHub path the claim was about, and the scoping `git grep … -- <two paths>` was the
   measurement that settled it. Then `grep -c "gh api -X PATCH"` over `repo_readiness_audit.py`
   returned **0**, appearing to refute "the gate emits forbidden PATCH remediations"; the strings are
   f-strings interpolating `{ORG}` between `api` and `-X`, so the literal never occurs, and `grep -n
   PATCH` found all four sites, one of which flips visibility. Both errors are the same shape as D-22:
   a pattern's zero-count is a claim about the pattern, not about the file. Countermeasure used here:
   before reporting any absence, run the looser pattern and read the matching lines.
2. The "missing secret" finding was killed by measuring environment- and org-scoped secrets before
   asserting. Scope the namespace before claiming absence.
3. FA-control-01 was found by *experiment*, which cost one `mkdir` in `/tmp` and destroyed nothing in
   the repository. When a control is cheap to falsify safely, falsify it.
4. Strengths are listed first-class in the register, including the correct `prevent_destroy`
   placement — verified by reading the resource block boundaries (`:25`→`:77`→`:90`), not by grepping
   the keyword, because the nearest `for_each` above line 77 belongs to a *different* resource.
5. **The audit's own citation was caught by the gate it audited.** `check_findings_register.py`
   reported a dangling reference at this file's line 164 once the file was committed: the finding id
   I cited is claimed by open PR #79 and has no row on `main` — main's register runs D-71, then
   D-73. The same run also showed the
   gate scans only `git ls-files` output (`:161`), so an uncommitted draft carries no citation check
   at all — a local "OK" does not cover work in progress. Both are recorded (FA-cross-08), the
   citation is re-pointed at the PR, and the fix that surfaced it is the reverse check in FA-control-01.
6. **Why this file names no id for that finding.** The gate matches `\bD-\d{1,3}\b` in any tracked
   file, so even prose explaining that an id is *absent* counts as a citation of it. That is
   deliberate and correct — a reader cannot be trusted to tell the two apart — but it means the only
   compliant wording is to cite the PR number. Retained raw evidence has the same constraint: the
   `gh pr list` sweep quotes #79's own title, which contains the id, so that probe cannot be
   committed until #79 merges. Editing a captured output to satisfy a gate would be falsifying
   evidence (§5), and widening `NON_EVIDENCE_PREFIXES` to cover it would be weakening the gate to
   make CI pass — also §5. So the sweep directory stays untracked for now, and the registry no
   longer attests it (FA-control-10's root fix: register only what git tracks).
7. **How `index.md`'s totals are derived** (so a reader reproduces them rather than trusting the
   prose). The severity cells are parsed from the registers, never hand-added. Current parse after
   D-81/D-82/D-83/D-84/D-85/D-86: `jolarca-control.yml` **16** controls (7 S1 / 8 S2 / 1 S3) → index
   totals **39 findings (1 S0 / 17 S1 incl. the latent one / 19 S2 / 2 S3)**. Re-run the block below; if
   it disagrees with the table, the table is wrong.

   ```bash
   .venv/bin/python - <<'PY'
   import yaml, pathlib, collections
   for p in sorted(pathlib.Path("docs/security/fleet-audit-2026-Q4").glob("*.yml")):
       c = collections.Counter(f["severity"] for f in (yaml.safe_load(p.read_text())["controls"])
                               if isinstance(f, dict) and "severity" in f)
       print(p.name, sum(c.values()), dict(c))
   PY
   ```

   Measured earlier the same day, before FA-control-12/13 were added: `dot-github.yml` 13 (`S1` 5 /
   `S2` 7 / `S3` 1), `jolarca-consent.yml` 10 (`S0` 1 / `S1` 4 / `S1 (latent)` 1 / `S2` 4),
   `jolarca-control.yml` 11 (`S1` 6 / `S2` 5) →
   **34 findings: 1 S0, 16 S1 (counting the latent one as S1, as the index prose does), 16 S2,
   1 S3**. Two caveats the parse hides: the literal label `S1 (latent)` is a separate key, so a
   naive `Counter` will not merge it into `S1`; and a register counts *controls*, so a control
   whose defect was fixed but not yet merged stays in the total — the status field, not the count,
   carries that distinction (FA-control-05/11 read `implemented-pending-merge` in the PR and
   `implemented` with a `fixes_landed_pr91` block once `4e0c22b` shipped). A third reading of the
   same rule was needed on 2026-10-26: FA-control-15 is graded **S1 while the fix is merged-ready
   but unmerged**, because the register's own claim — not the missing `prevent_destroy` — is what an
   auditor reads; the record stays honest about the distinction rather than lowering the severity to
   match the merge state.
