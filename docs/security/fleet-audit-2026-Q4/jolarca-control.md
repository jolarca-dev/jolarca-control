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

## Method notes

1. Three of my own probes were wrong and are recorded as wrong: a `sed`-based script↔test comparison
   that falsely indicted 15 gates (fixed in Python — the truth is 12 of 15 covered); a `yaml.safe_load`
   read of `on:` that returned `None` for every workflow because YAML 1.1 parses bare `on` as `True`;
   and a `--json defaultBranchRef.name` field path `gh` rejected. An empty or odd result is a
   property of my tooling until proven otherwise.
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
   prose). The severity cells are parsed from the registers, never hand-added:

   ```bash
   .venv/bin/python - <<'PY'
   import yaml, pathlib, collections
   for p in sorted(pathlib.Path("docs/security/fleet-audit-2026-Q4").glob("*.yml")):
       c = collections.Counter(f["severity"] for f in (yaml.safe_load(p.read_text())["controls"])
                               if isinstance(f, dict) and "severity" in f)
       print(p.name, sum(c.values()), dict(c))
   PY
   ```

   Measured 2026-10-26: `dot-github.yml` 13 (`S1` 5 / `S2` 7 / `S3` 1), `jolarca-consent.yml` 10
   (`S0` 1 / `S1` 4 / `S1 (latent)` 1 / `S2` 4), `jolarca-control.yml` 11 (`S1` 6 / `S2` 5) →
   **34 findings: 1 S0, 16 S1 (counting the latent one as S1, as the index prose does), 16 S2,
   1 S3**. Two caveats the parse hides: the literal label `S1 (latent)` is a separate key, so a
   naive `Counter` will not merge it into `S1`; and a register counts *controls*, so a control
   whose defect was fixed but not yet merged stays in the total — the status field, not the count,
   carries that distinction (FA-control-05/11 read `implemented-pending-merge` in the PR and
   `implemented` with a `fixes_landed_pr91` block once `4e0c22b` shipped).
