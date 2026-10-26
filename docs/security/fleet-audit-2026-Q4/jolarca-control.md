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
| FA-control-05 | S2 | 3 of 15 gates have no dedicated test file: `check_fleet_separation`, `hash_evidence`, `org_delivery_audit` — the two that matter are ADR-0004 separation and evidence integrity | script↔test name mapping |
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

**What should change.** (a) Require `Regression Tests` and `Evidence Integrity Check`. (b) Rehearse
the apply path on a synthetic plan that *must* be refused, in a controlled window, and retain the
refusal log as evidence — the rehearsal is the thing that converts a hypothesis into a control.
(c) Add a gate that fails when a workflow cites a secret that is not defined at repo, org **or**
environment scope — the D-72 rule (no dead path pointers) extended to credential names.

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
