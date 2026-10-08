# RB-08: First-Commit Pipeline — New Repository Delivery Gate

**Scope:** every `jolarca-dev` marketplace repository receiving its first real
commit, and every subsequent change to one.
**Tool:** `scripts/first_commit_pipeline.py` (`make first-commit`)
**Compliance:** SOC 2 CC8.1 / CC6.1 · ISO 27001 A.8.32 / A.8.25 · GDPR Art. 32 ·
PCI-DSS Req. 6.3 / 6.5
**Mode:** STRICTLY READ-ONLY. The tool verifies and instructs. **You** run every
command that changes anything.

---

## Why this runbook exists

`make readiness` answers *"may this repository receive its first commit?"* and
stops there. Nothing governed what happened next, so the six-step delivery
pipeline existed only as prose. That is the D-22 failure class — a control that
lives in a document and never fires. D-33 records the result: `jolarca-security`
took 14 commits directly onto `main` with zero pull requests.

This runbook plus its tool is the control that fires.

## The pipeline

```
VERIFY FIRST → COMMIT → PUSH → REVIEW → MERGE → VERIFY AGAIN
     A            B        C       D        E          F
```

Run one step, read every line of output, run the command it prints, then advance.
A step **refuses to run** if any earlier step did not reach `PASS`.

```bash
make first-commit REPO=<name> STEP=A SNAPSHOT=1          # always start here
make first-commit REPO=<name> STEP=B MESSAGE="feat: ..."
make first-commit REPO=<name> STEP=C
make first-commit REPO=<name> STEP=D
make first-commit REPO=<name> STEP=E
make first-commit REPO=<name> STEP=F ATTEST="<Your Full Name>" EVIDENCE=/tmp/<name>-evidence.md
```

Exit codes are three-valued and never ambiguous:

| Exit | Meaning | What you do |
| --- | --- | --- |
| `0` | every step PASSED | continue |
| `1` | findings, or a tracked exception | read them; fix, or record the decision |
| `2` | **could not verify** | STOP. A control that cannot read its subject must never be treated as a pass |

## Statuses

| Status | Meaning |
| --- | --- |
| `PASS` | verified from evidence read in this run |
| `TRACKED-EXCEPTION` | the control cannot be enforced on this plan tier; a dated acceptance in `policy/compliance-gates.yml` covers it, and its compensating control is named in the output |
| `BLOCKED` | real defect, or an acceptance that has lapsed, or a finding still in `open_blocking`. **STOP.** |
| `UNVERIFIABLE` | the tool could not read the subject. **STOP** — this is not a pass |

---

## Step A — VERIFY FIRST

```bash
make first-commit REPO=<name> STEP=A SNAPSHOT=1
```

`SNAPSHOT=1` writes `/tmp/<name>-readiness-snapshot.json`. Step F diffs against
it to prove nothing but your change moved. **Skipping the snapshot silently
disables that proof.**

Checks: allow-list entry present · readiness verdict · feature branch · snapshot.

Step A **consumes** `make readiness`; it does not re-implement it. Everything
structural — governance files, CODEOWNERS, hooks, `commit.gpgsign`, cleanliness,
forbidden paths, secrets in tree **and history**, live settings, secret scanning,
Dependabot, collaborators, deploy keys, branch protection, org baselines — is
decided there. Two gates that each implement a check are two gates that
eventually disagree.

**Checkpoint:** verdict is `READY`, and you are on a feature branch.

**STOP if:** the verdict is `BLOCKED`, or you are on `main`.

---

## Step B — COMMIT

```bash
make first-commit REPO=<name> STEP=B MESSAGE="feat(<scope>): <what and why>"
```

Checks: not on the default branch · something is staged · no forbidden path is
staged · subject is Conventional Commits · `commit.gpgsign` · gitleaks on the
staged diff.

Then run the command it prints. `-S` is not decorative: signed commits are the
compensating control for the 0-review deviation (D-04), because they attribute
every change to a key holder.

```bash
git commit -S -m "feat(<scope>): <what and why>"
```

One logical change per commit. Never `--no-verify`: the pre-commit hooks are the
only secret control that actually runs on the Free plan (see below).

**Checkpoint:** the commit exists and `git log -1 --show-signature` verifies.

---

## Step C — PUSH

```bash
make first-commit REPO=<name> STEP=C
```

Checks: not pushing the default branch · `origin` matches `jolarca-dev/<name>.git`
· commits exist to push · push-protection state.

```bash
git push -u origin <feature-branch>
```

**Never push to `main`.** On the Free plan nothing server-side will stop you,
which is precisely why this step checks first.

**Checkpoint:** the branch exists on GitHub and the working tree is clean.

### If a secret is EVER detected — STOP

1. **Stop.** Do not push. Do not "clean it up and continue".
2. **Rotate it at the issuer, even if it is brand new.** A secret that reached
   the working tree must be assumed compromised.
   See `docs/runbooks/github-token-rotation.md`.
3. Remove it: `git restore --staged <file>`, then add the path to `.gitignore`.
4. If it was already committed, purge history — RB-03 steps 3–5.
5. Record the incident in `jolarca-compliance`: timeline, exposure window,
   rotation evidence, and whether GDPR Art. 33 72-hour notification is triggered.
6. Add the pattern to `policy/compliance-gates.yml` →
   `gates.secret_scan.implementation.custom_patterns`.
7. Only then re-run Step A.

**A synthetic fixture is not a credential.** If the hit is a test fixture (a
string that was never issued by anyone), rotation is impossible and must not be
faked. Assemble it at runtime — `token = "AKIA" + "Q3EG..."` — so the literal
never lands in source or history, and record the false positive as a finding.
See *Known issue* below.

---

## Step D — REVIEW

```bash
make first-commit REPO=<name> STEP=D
```

Checks: PR exists · description non-empty · every context declared in
`repos/<name>.yml` is reported and green · no forbidden or unrelated file in the
diff.

Open a PR even though the Free plan does not require one. The PR *is* the change
record for SOC 2 CC8.1; without it there is no auditable rationale for the change.

```bash
gh pr create --repo jolarca-dev/<name> --base main --head <branch> \
  --title "<type>: <subject>" --body "<what and why>"
```

**Checkpoint:** description present, linked context, CI green, diff contains only
what you intended.

---

## Step E — MERGE

```bash
make first-commit REPO=<name> STEP=E
```

Checks: not `CONFLICTING` · all checks green · zero unresolved review threads ·
approvals meet policy · squash-only.

```bash
gh pr merge <number> --repo jolarca-dev/<name> --squash --delete-branch
```

Squash is mandatory (`allow_merge_commit: false`) — it keeps history linear and
auditable, one PR per change.

**Checkpoint:** the PR is merged and the feature branch is deleted.

---

## Step F — VERIFY AGAIN

```bash
make first-commit REPO=<name> STEP=F ATTEST="<Your Full Name>" \
  EXPECTED_SHA=<sha> EVIDENCE=/tmp/<name>-evidence.md
```

Checks: CI green on `main` · the commit landed on `main` · **settings unchanged
since the Step A snapshot** · operator sign-off.

`--attest` is not optional. The evidence file renders
`- [ ] NOT SIGNED OFF` without it, and that file is the artifact an auditor reads.
The sign-off line is the one a student must not skip.

**Checkpoint:** the evidence file shows no `BLOCKED` and no `UNVERIFIABLE` row.

---

## Plan-tier reality — read this before you "fix" a finding

`jolarca-dev` is on the **GitHub Free** plan. Several controls the ideal pipeline
assumes **cannot be enforced**. The tool reports them as `TRACKED-EXCEPTION`
naming the finding, the compensating control and the expiry date — read live from
`policy/compliance-gates.yml`, never hardcoded.

| Ideal control | Reality | Finding | Compensating control | Expires |
| --- | --- | --- | --- | --- |
| ≥1 PR approval | `required_approving_review_count: 0` | D-04 | signed commits + PR opened anyway + recorded self-review | 2026-12-24 |
| GitHub-enforced signed commits | `require_signed_commits: false` | D-05 | `commit.gpgsign=true`, verified locally in Step B | 2026-12-24 |
| Branch protection / push protection / secret scanning / CodeQL on private repos | HTTP 403; `enable_branch_protection = false`, `enable_secret_scanning = false` | **D-33** | squash-only PRs by convention, GPG-signed commits, gitleaks 8.30.1 pinned across CI/pre-commit/local with a negative control, Dependabot alerts | **2026-12-27 — CONDITIONAL, see below** |

**Do not "remediate" a tracked exception.** It is an accepted, dated, signed
decision. Re-opening it is a change under `docs/change-management.md`.

### A CONDITIONAL acceptance says so out loud

`D-33` is listed in **both** `exceptions.active` and `exceptions.open_blocking`.
That is deliberate, not a contradiction: the owner approved a dated acceptance
(2026-09-28 → 2026-12-27) while keeping the `open_blocking` row until four interim
controls are stood up. Its recorded outstanding items are:

1. `drift_detect.py` does not read `.protected` and still files the private-repo
   403 as `unverifiable`, so "a repository lost branch protection" cannot fire.
2. Public repos are unprotected too — `enable_branch_protection = false`.
3. PR-by-convention is unenforced and bypassable without trace.
4. No off-host state backup exists (D-02), so rewritten history is unrecoverable.

When a finding is dual-listed like this, the tool reports `TRACKED-EXCEPTION` and
appends **`CONDITIONAL`** plus a pointer to the policy file. The dated acceptance
governs — blocking would contradict an approved decision — but you must read those
four items before relying on it. Note item 3 in particular: on the Free plan
nothing stops a direct push to `main`, so **this runbook is the control**.

### Expiry is enforced, not decorative

When an acceptance's `expires` date passes, this gate starts returning `BLOCKED`
on its own — no code change, no reminder. That is deliberate (the D-25 lesson: an
event-only expiry has no deadline and stays open forever). A lapse is closed by a
PR that restates the compensating controls, **not by silence**.

Expect `D-04` and `D-05` to start blocking on **2026-12-25**, and `D-33` on
**2026-12-28**. Nothing needs editing for that to happen.

### `--strict`

```bash
make first-commit REPO=<name> STEP=all STRICT=1
```

Refuses every tracked exception. This is the posture to adopt the day the org
moves to GitHub Team — flip one default and the gate hardens with no rewrite.

---

## Known issue — the gate reports S0 on this repository

**Status: RESOLVED AT SOURCE 2026-09-28, HISTORY ACCEPTED AS FALSE POSITIVE 2026-10-07.**
See `docs/security/f01-l16-synthetic-fixture-acceptance.md`.

Historically (before the 2026-09-28 runtime-assembly refactor landed in
`ac0da96`), `make readiness REPO=jolarca-control` reported three S0
stop-work findings (`L-15`, `L-16`, `L-17`) because the readiness gate's
own secret sweep and gitleaks both matched **synthetic fixtures** in
`tests/test_repo_readiness_audit.py`. That framing is preserved below for
audit trail; the actual 2026-10-07 state is one S2 finding on history
matches only.

| String (redacted here on purpose) | Line | Nature |
| --- | --- | --- |
| `AKIAQ3EG…B2M` | 515 | fixture for `test_redaction_never_emits_the_full_secret`; committed in `0e17920`, so it is also in **git history** |
| `sk_live_abcdefghij…` | 894 | fixture whose own docstring notes it must be ≥24 chars to match the pattern |

> Both are written here in **truncated** form. Reproducing them in full would make
> this runbook match the same patterns and trip the same scanner — a governance
> document that BLOCKs its own repository for containing a fake credential. Run
> `gitleaks detect --source . --no-git` to see the exact literals and locations.

Neither was ever issued by AWS or Stripe. **Rotation is not applicable and must
not be faked.**

Consequences — original framing (pre-2026-09-28), preserved verbatim:

1. The control plane cannot pass its own readiness gate, so Step A of this
   pipeline blocks for `jolarca-control` permanently.
2. Once push protection is enabled (GitHub Team), GitHub will **refuse pushes**
   to this repository.
3. Worst of all: an S0 that is always a false positive trains operators to ignore
   S0. The readiness gate's own source warns about exactly this — *"an auditor who
   learns to ignore the secret check has lost the one check that matters."*

Consequences — actual 2026-10-07 state:

1. Step A no longer BLOCKs. Readiness on `jolarca-control` returns
   `verdict_counts: {READY: 0, READY-WITH-FIXES: 1, BLOCKED: 0}`.
2. `secret_hits_head: []` — no regex hit anywhere in tracked files.
3. `secret_hits_history: 2 matches` — L-16 fires at **S2** (not S0) because
   the audit's own logic requires gitleaks corroboration for S0; gitleaks
   reports `no leaks found` and cannot be corroborated.
4. The S2 is accepted as a documented false positive. No history rewrite.
   No `.gitleaksignore` entry needed (gitleaks is not what fires here).

Remediation status, in the original order:

1. **Assemble fixtures at runtime** so no literal credential shape lands in
   source. DONE 2026-09-28 in `ac0da96`. Verified: `grep -c 'AKIA[0-9A-Z]{16}'
   tests/test_repo_readiness_audit.py` returns 0; `gitleaks dir .` returns
   `no leaks found`.
2. Add `.gitleaksignore` for any fixture that must stay literal. NOT NEEDED.
   `.gitleaksignore` exists with zero entries as a documented placeholder;
   the runtime-assembly fix means no literal remains.
3. Purge history to clear `L-16` on the pre-`ac0da96` blobs. NOT DONE — owner
   decision. The 2026-10-07 acceptance in
   `docs/security/f01-l16-synthetic-fixture-acceptance.md` records why the
   risk-reward is negative: gitleaks does not flag the historical blobs
   anyway, and force-push under RB-03 on a public governance repo with
   downstream references is disproportionate to a documented S2.
4. Do **not** solve this by excluding `tests/` from the secret sweep. A real
   secret pasted into a test file is still a real secret. RESPECTED 2026-10-07
   — the path-based exclusion previously present in `.gitleaks.toml` under
   ADR-0009 F-04 has been removed.

---

## Sign-off checklist

Do not proceed to launch until every box is ticked with evidence attached.

- [ ] Step A readiness verdict is `READY` (or every finding is S2/S3 with a
      recorded decision)
- [ ] Settings snapshot taken **before** the first commit
- [ ] No secret in the working tree, the index, or git history — or the hit is a
      documented synthetic fixture with the false positive recorded as a finding
- [ ] Every commit is signed and attributable (`git log --show-signature`)
- [ ] Every commit subject is Conventional Commits and classifiable
- [ ] Nothing was ever pushed directly to the default branch
- [ ] A PR exists for the change, with a description and linked context — even
      though the plan does not require one
- [ ] Every status context declared in `repos/<name>.yml` reported and is green
- [ ] Merged with `--squash --delete-branch`; feature branch deleted
- [ ] Step F confirms the commit landed on `main` and CI on `main` is green
- [ ] Step F confirms **settings unchanged** against the Step A snapshot
- [ ] Every `TRACKED-EXCEPTION` in the run names a finding, a compensating
      control and an unexpired date
- [ ] `EVIDENCE` file written, archived into `jolarca-compliance`, and signed
      with `--attest`
- [ ] Zero `BLOCKED` and zero `UNVERIFIABLE` rows in the evidence file

**Sign-off:** `____________________________________  Date: ____________`

An unsigned evidence file is not evidence.
