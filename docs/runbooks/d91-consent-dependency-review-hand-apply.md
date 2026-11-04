# Enacting the D-91 suspension (consent `Dependency review`) by hand

**Why this runbook exists.** PR #107 merged the suspension into configuration, and the apply it armed was
cancelled. The exception is therefore **committed, not enacted**: `main` declares six required contexts for
`jolarca-dev/jolarca-consent` while live ruleset `24087580` still enforces seven, `Dependency review` among
them, and `Dependency review` still concludes `failure` on every open consent PR. Until the steps below run,
consent's merge queue is jammed and the 82-day expiry of D-91 is burning without the relief being real.

**Why CI cannot do it.** `.github/workflows/apply.yml` runs `check_plan_safety.sh` before
`terraform apply -auto-approve`, and that script refuses **every** change to a ruleset resource in either
direction (D-84, D-26). Measured on this branch's own plan: exit `1` with four `::error::` classes naming
the lines of `github_repository_ruleset.main["jolarca-consent"]`. That refusal is the control, not a bug —
do not widen the pattern list to make CI pass (§5). It is also why the job never reaches the gate: the
`Production — Apply` job is environment-gated, so without an approval nothing in it runs at all.

**Who runs it.** The operator only. `terraform apply`, `state rm`, `state mv` and `import` from this root are
reserved to a human by AGENTS.md §5, and the environment reviewer is self-approvable
(`prevent_self_review=false`, `can_admins_bypass=false`), so an agent approving it would be the same single
signature wearing both hats — D-58 stays open for exactly that reason.

## Before: confirm the starting state

```bash
gh api repos/jolarca-dev/jolarca-consent/rulesets/24087580 \
  --jq '[.rules[] | select(.type == "required_status_checks")][0].parameters'
```

Expect **seven** contexts including `Dependency review`, and `updated_at` still `2026-10-27T20:53:08`
(the stage-2 hand apply). The context list lives under `parameters.required_status_checks`, and the strict
flag is named `strict_required_status_checks_policy` — the legacy `branches/main/protection` endpoint
answers HTTP 404 for this repo, so do not go looking there.

## 1. Plan, and read it per address

```bash
git fetch origin main && git checkout main && git reset --hard origin/main   # operator-only; agents do not
terraform init -input=false
terraform plan -input=false -no-color -out=tfplan
terraform show -no-color tfplan > plan.txt
grep -nE '^  # |^Plan:' plan.txt                                            # every address that will change
bash scripts/check_plan_safety.sh plan.txt; echo "gate rc=$?"              # expect 1
```

- Feed the gate a **real file**. `check_plan_safety.sh:37` rejects a non-regular file, so a process
  substitution returns `2` — could-not-verify — never `0`.
- Read `-no-color`. The gate anchors patterns at line start, and colour bytes in front of `~`/`-` have made
  the same plan pass one way and fail another (AGENTS.md §7).
- Expect `Plan: 0 to add, 2 to change, 0 to destroy`. The second change is this root's **permanent**
  `github_repository.repo["jolarca-legal"]` write-only `template` line (D-89): the gate waves it through and
  it will never converge, so do not read it as unfinished work and do not let it make you distrust the
  ruleset line, which is the one that matters.
- `gate rc=1` is the expected outcome. Its four messages are the protection refusals; if any message names
  something other than the consent ruleset or the legal `template` line, **stop** — the plan is not what this
  runbook describes.

## 2. Apply the saved plan

```bash
terraform apply -input=false tfplan
```

Apply the **same file you just read**; do not re-plan without `-out` and read again.

## 3. Prove the live effect — the plan is not evidence

Provider 6.13.0 does not read back every ruleset field, so verify against GitHub:

```bash
gh api repos/jolarca-dev/jolarca-consent/rulesets/24087580 \
  --jq '[.rules[] | select(.type == "required_status_checks")][0].parameters.required_status_checks
         | map(.context) | {count: length, dependency_review: (index("Dependency review") != null)}'
```

Expected: `count: 6`, `dependency_review: false`, and `updated_at` newer than `2026-10-27T20:53:08`.
Then confirm nothing else moved: `pull_request` must still be present (that is what keeps consent's `main`
un-pushable and D-46 closed) and the other six contexts must all still be listed.

```bash
.venv/bin/python scripts/drift_detect.py; echo "rc=$?"   # consent must not be reported as weakened
```

## 4. Only now: unblock consent PR #12, then restore the check

1. Merge `jolarca-consent#12` — it carries the pinned `requirements.txt` that lets
   `dependency-review-action` resolve a graph. It cannot merge before step 3, which is the whole jam.
2. Let the dependency graph build, and require `Dependency review` to be **observed `success`** on a consent
   pull request. Emission is not enough: `check_declared_contexts.py` exiting `0` proves only that a context
   is producible, and that mistake is what created D-90.
3. Open the closing PR that re-adds the context to **both** governed places — `rulesets.tf` and
   `repos/jolarca-consent.yml`, in the same commit, or `drift_detect` reports a protection change that never
   happened — and deletes the D-91 entry from `policy/compliance-gates.yml`. `policy/` is hashed, so stage
   that file before running `make evidence-register` and commit the registry diff in the same PR.
4. Expect this runbook's steps 1–3 again for that apply: it is also a ruleset change, so the gate refuses it
   and it lands by hand.

## Rollback

`git revert` the closing commit restores both the requirement and the D-91 entry in one step, and the
registry needs no surgery because `policy/compliance-gates.yml` and `repos/jolarca-consent.yml` are attested
by hash. Reaching the *live* state still needs another hand apply; reverting the commit alone changes only
the declaration.

## What this runbook does not close

D-91's expiry is `2027-01-25`. D-58 (no human approval between merge and apply) stays open. Consent's
`Gitleaks (secret scanning)` context is satisfied by the license-free CLI path, not by a paid Action. D-89's
plan line remains. If the armed `Production — Apply` run is not wanted, cancel it with
`gh run cancel <id> --force` — proven harmless at `steps_started=0`.
