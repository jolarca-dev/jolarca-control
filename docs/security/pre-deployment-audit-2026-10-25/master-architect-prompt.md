# Jolarca — Master Architect Prompt, expanded

**Companion to:** `docs/pre-deployment-audit-2026-10-24.md` (the findings this document is built to prevent)
**Written for:** a student who can use a shell and `git`, and has never run a compliance programme
**Version:** 1.0 · 2026-10-24

---

## 0. How to read this document

There are two different things here, and confusing them is the most common mistake.

- **§1–§4 are the *system*.** They describe properties the system must have whether or not anyone
  remembers to ask for them. Read these once, carefully.
- **§5 is the *procedure*.** It is your original ten steps, plus eight I added, each broken into
  sub-steps with the exact commands to run. Read these while working, one at a time.
- **§6 is the toolchain verdict.** Which machines and identities do which jobs.
- **§7 is the prompt itself**, copy-paste ready.
- **§8 is what to do next**, in order.

Every claim in this document about the current state of `jolarca-dev` was measured live on
2026-10-24 and is cited in the companion audit report. Where something could **not** be measured, it
says so. That is not hedging — it is the single most important habit in this document, and §5.11
explains why.

**Three terms, used precisely:**

| Term | Meaning here |
|---|---|
| **Control** | Something that *prevents* or *detects* a bad outcome. A control that nobody runs is not a control. |
| **Gate** | A control wired into a path so that the path **cannot complete** unless the control passes. |
| **Evidence** | Retained, dated output proving a control operated. Evidence you did not keep did not happen. |

The difference between "we have a policy" and "we have a gate" is the entire subject of this document.

---

## 1. The problem statement: why a good prompt is not a control

Your own diagnosis is correct and worth stating plainly, because everything after it follows from it:

> *"The most important improvement is to make scope, permissions, evidence and independent
> verification enforceable properties of the system, rather than relying on the quality of an AI
> prompt alone."*

Here is the mechanism of failure. A prompt is an instruction to a model. A model is a probabilistic
text generator. Under four conditions its instructions degrade:

1. **Length.** At ~40k tokens of context, an instruction given at the start competes with everything
   since. It is not deleted; it is *outweighed*.
2. **Conflict.** When a user request and a standing rule disagree, the model must choose. It usually
   chooses the recent, specific, human request. That is often right — and it is exactly wrong for
   "never delete a gate to make CI pass".
3. **Plausible completion.** A model asked to "verify X" will produce *the shape of verification* —
   a confident sentence — because that is what verification looks like in text. The shape is cheap;
   the measurement is not.
4. **Self-assessment.** A model that implemented a change is being asked to judge it. There is no
   adversarial pressure. It will find what it looked for.

The fleet already contains proof of each. Four real examples, all from this repository's own record:

- **D-22.** The gate that stood between an unattended `terraform apply` and a fleet-wide visibility
  flip was an inline regex written `visibility\s*:`. `terraform show` emits `visibility = `. The
  pattern never matched, once, in its entire life. It reported *safe* every time it ran. Nothing in
  the system distinguished "the gate checked and found nothing" from "the gate could not see
  anything".
- **The ANSI trap (measured 2026-10-15).** The *same* plan file made `check_plan_safety.sh` exit `0`
  when rendered by `terraform show tfplan` and exit `1` when rendered by `terraform show -no-color
  tfplan`, because 840 ANSI escape bytes sat in front of the `~`/`-` markers every pattern anchored
  at line start. The verdict depended on *how the input was coloured*.
- **The silent early return.** A gate that hit a missing `.git` returned early, skipping six
  filesystem checks and the entire secret sweep — while still reporting the correct aggregate
  verdict.
- **PDA-14 (found yesterday).** `policy/compliance-gates.yml` closed blocking finding D-33 on the
  signal `.protected = true`. That signal is `true` for `jolarca` (12 required contexts) **and** for
  `jolarca-consent` (direct push to `main` allowed, zero required checks). The metric used to close
  the finding was insensitive to the property the finding was about.

**And one from the writing of this very document — the most instructive of the five.**

The audit behind `docs/pre-deployment-audit-2026-10-24.md` measured that `.github` holds three
reusable workflows with 17 jobs and 11 unpinned action references. From that, it concluded —
confidently, in writing, with a severity of **S0** — that a compromised upstream tag would become code
execution across every fleet repo, because reusable workflows run with the *caller's* `GITHUB_TOKEN`.
That reasoning is textbook-correct. It was also **false here**, because the premise was never tested:
no repository in the fleet calls those workflows. A scan of all 17 repos for
`uses: <owner>/<repo>/.github/workflows/…` returned three matches, and all three were the *comment
lines inside `.github` itself* that document how the workflows would be called. The finding was
downgraded to S1 and the correction recorded in the report rather than quietly edited out.

Note what did **not** catch it: re-reading. The paragraph was internally consistent, technically
accurate about how `workflow_call` works, and matched the evidence gathered so far. Only a *new
measurement aimed at the claim itself* falsified it. That is mechanism 3 — plausible completion —
observed in the auditor rather than in the code.

A second, smaller instance happened in the same session: a tally of per-repo verdicts was written as
"4 FAIL, 11 PASS, 2 THIN" when recounting the rows gave 6/10/1. The summary was written from
impression of the table rather than from the table. **Summaries of evidence are not evidence** —
count the rows.

**The lesson, generalised.** A control is only real if three things are true simultaneously:

1. it is on the path (the path cannot complete without it),
2. it can fail (someone has demonstrated it failing on a bad input), and
3. it fails **closed** (when it cannot read its input, it says "I don't know", never "fine").

Everything else — policy prose, an agent's memory, a well-written prompt, a human's intention — is
*convention*. Convention is worth having. It is not worth *relying on*, and AGENTS.md §6 forbids
describing it as if it were enforcement.

---

## 2. The three-valued exit code: the smallest idea with the largest effect

Before anything else, internalise this, because it is the load-bearing convention of the whole fleet
(AGENTS.md §3):

| Code | Meaning | What it forces you to say |
|---|---|---|
| `0` | Verified safe | "I checked, and it is fine." |
| `1` | Findings — a real refusal | "I checked, and it is **not** fine." |
| `2` | **Could not verify** | "I could not check. Treat as not fine." |

Two-valued gates (`pass`/`fail`) collapse "could not check" into one of the other two. Every collapse
goes the same way in practice: an unreadable file, a 404, a timeout or an empty variable becomes
"no findings" → exit `0`. That is how D-22 survived.

**Sub-steps to apply this to any new gate:**

a. Write the gate's three outcomes on paper *before* writing code. If you cannot name a concrete
   situation that produces `2`, you have not thought about it enough.
b. Make every input read fail loudly into `2`:
   ```bash
   plan=$(terraform show -no-color tfplan 2>/dev/null) || { echo "cannot read plan"; exit 2; }
   [ -s "$plan" ] || { echo "plan is empty"; exit 2; }
   ```
   Note `-s` (exists **and** non-empty), not `-f`. A zero-byte plan is `2`, not `0`.
c. Add the two negative controls that prove `2` is reachable: an empty input and a missing input.
   `tests/test_check_plan_safety.sh` does this — 19 fixtures including both.
d. Never let a caller treat a non-zero exit as pass. In CI:
   ```yaml
   - run: bash scripts/check_plan_safety.sh plan.txt   # no `|| true`, no `continue-on-error`
   ```

**Why a student should care:** this one convention converts "we hope the gate works" into "the gate
either proved something or told us it couldn't". It is the cheapest control in this document and the
one most often skipped.

---

## 3. The four enforceable properties

Your thesis names four: **scope, permissions, evidence, independent verification**. Here is each one
as a system property — what it means, why prose fails, the mechanism that enforces it, and the
negative control that proves the mechanism works.

### 3.1 Scope — the agent may only touch what the task names

**What it means.** A change to `docs/` must not be able to modify `*.tf`. A task about
`jolarca-vendor` must not be able to edit `jolarca-payments`. "Do not touch anything out of scope"
becomes a fact about the filesystem and the repository, not a sentence in a prompt.

**Why prose fails.** Models drift. A 40-minute debugging session accumulates small "while I'm here"
edits. Nobody notices until the diff is reviewed — and in this fleet
`required_approving_review_count = 0` on 17/17 repos (PDA-12), so *nobody reviews the diff at all*.

**Mechanisms, weakest to strongest:**

1. **Path allow-list checked by a gate.** A script compares `git diff --name-only origin/main...HEAD`
   against the scope declared in the task record and exits `1` on anything outside it. Cheap, and it
   catches the common case. Weakness: the gate lives in the repo the agent can edit.
2. **`git worktree` per task.** A separate working directory on a separate branch. The agent cannot
   see the other tasks' trees. Strong against cross-task contamination, weak against in-scope-repo
   overreach.
3. **CODEOWNERS + `require_code_owner_reviews`.** Path-scoped *approval* authority. Currently **inert
   fleet-wide**: 16 CODEOWNERS files exist, `require_code_owner_review = false` everywhere, and
   `gh api orgs/jolarca-dev/teams` returns `[]` (zero teams), so there is nobody for the files to
   name. Do not cite CODEOWNERS as a scope control until teams exist (D-20).
4. **Repository-level isolation via credentials.** Give the agent a fine-grained PAT scoped to
   *exactly* the repositories in the task. Then out-of-scope writes are not "discouraged" — they are
   HTTP 403. **This is the strongest available control on a Free plan** and it is the one this fleet
   does not yet use. See §6.
5. **A ruleset that blocks direct pushes to `main`.** Makes "scope" include "you must go through a
   PR", so the diff exists as an object before it lands. `jolarca-consent` lacks this today
   (PDA-02): its ruleset has `deletion`, `non_fast_forward`, `required_linear_history` and no
   `pull_request` rule, so `git push origin main` succeeds.

**Negative control.** Deliberately make an out-of-scope edit and confirm the gate refuses it. If you
cannot produce a refusal, you have a hypothesis, not a scope control. Concretely:
```bash
git checkout -b test/scope-negative-control
echo "# scope probe" >> repositories.tf          # a high-blast-radius file, out of scope for a docs task
bash scripts/check_scope.sh docs-task.yml; echo "exit=$?"   # must print exit=1
git checkout -- repositories.tf && git checkout -
```

### 3.2 Permissions — the agent may only do what its role requires

**What it means.** Least privilege, enforced by the credential, not by the instruction.

**Why prose fails — and a finding about this very audit.** The sweeps behind the companion report ran
with the token in this machine's keyring:
```
Token scopes: 'admin:gpg_key', 'admin:org', 'gist', 'read:user', 'repo', 'user:email', 'workflow'
```
A read-only audit needs `public_repo` read. It was holding `admin:org` — the scope that can change
organisation membership, security settings and every repository in the fleet — plus `workflow`, which
can write Actions definitions. **The auditor had the capability to do the thing the audit was
checking for.** Nothing in the system prevented it; only the operator's discipline did. That is a
live demonstration of your thesis, produced accidentally, in the first hour of the audit.

**Mechanism, concretely:**

1. Create **two** fine-grained PATs and nothing else:
   - `jolarca-auditor` — Repository permissions: *Contents: Read-only*, *Metadata: Read-only*,
     *Pull requests: Read-only*, *Workflows: Read-only*. Organisation permissions: none.
     Repository access: **all 17**. This token *cannot* write. An audit run with it is
     capability-limited, not promise-limited.
   - `jolarca-implementer` — Contents: Read/Write, Workflows: Read/Write, on a **named subset** of
     repos (start with the one you are working on). No `admin:org`. No `delete` on anything.
2. Store them in separate files with `chmod 600`, referenced by environment variable, never in
   shell history and never in a prompt:
   ```bash
   export GH_TOKEN="$(cat ~/.config/jolarca/auditor.token)"    # for audit sessions
   export GH_TOKEN="$(cat ~/.config/jolarca/implementer.token)" # for change sessions
   ```
3. Add a **capability assertion** at the start of every audit session — this is the gate that would
   have caught the finding above:
   ```bash
   gh api -X GET /user -q .login            # which identity am I?
   gh auth status 2>&1 | grep -i 'scopes'   # what can I do?
   ```
   An audit session that reports `admin:org` or `repo` (write) should refuse to proceed.
4. Keep `terraform` state mutation (`state rm`, `state mv`, `import`) out of every agent credential
   entirely. AGENTS.md §5 already forbids it for agents; a credential that cannot do it makes the
   rule self-enforcing.

**Negative control.** With the auditor token, attempt a write and confirm HTTP 403:
```bash
GH_TOKEN="$(cat ~/.config/jolarca/auditor.token)" \
  gh api -X PATCH repos/jolarca-dev/jolarca-vendor -f description="probe" -i 2>&1 | head -1
# expected: HTTP/2 403. If this returns 200, your "read-only" auditor can write.
```
**Do not run this against a resource you care about.** Description is chosen because it is trivially
revertible; and if it returns 200 you have just proven the point that mattered.

### 3.3 Evidence — proof is retained, hashed, and cannot be silently edited

**What it means.** The output that justified a decision is a committed artefact with a hash, not a
sentence in a chat transcript or a report a tool printed.

**Why prose fails.** Chat is transient and unattributable. An agent's "verified: passed" is a claim
about a command nobody can see. AGENTS.md §1: *"A tool's summary, a prior report, or an agent's own
claim ('file updated successfully') is **not** evidence. Command output is."* And §7: *"Evidence must
be retained to count."*

**Mechanism — this fleet already has it; use it properly:**

1. `scripts/hash_evidence.sh` SHA-256s every `*.yml|*.md|*.sh|*.py|*.tf` under `EVIDENCE_DIRS`
   (`scripts/hash_evidence.sh:35-43`): `docs/adr`, `audit`, `policy`, `repos`, `docs/runbooks`,
   `docs/security`. It writes `docs/evidence-registry.csv`.
2. `make evidence-check` compares live files to the **committed** registry. Edit an evidence file
   without re-registering → the gate fails. That is what makes evidence tamper-evident rather than
   merely stored.
3. `make evidence-register` regenerates the CSV; commit the diff **in the same PR**.
4. **The trap.** `hash_evidence.sh --check` "only means something if `docs/evidence-registry.csv` is
   under version control" (`scripts/hash_evidence.sh:25-28`) — checking a file against a registry in
   the same uncommitted tree is tautological. It once reported OK for tampered evidence. Always check
   against the committed registry.
5. **Second trap.** Regeneration re-stamps the date on *every* row, so the diff is huge and hides the
   one row that actually changed. Read the diff by hash column, not by line count.
6. **Files at `docs/` root are NOT hashed.** That is why the companion audit report lives at
   `docs/pre-deployment-audit-2026-10-24.md` while its raw sweep outputs should be committed under
   `docs/security/pre-deployment-audit-2026-10-24/` — inside `EVIDENCE_DIRS`, therefore hashed.

**What to retain for each verification, every time:**
- the exact command,
- its full stdout and stderr,
- the exit code,
- an ISO-8601 timestamp,
- the git commit SHA the measurement was taken against.

A convenient shape:
```bash
{ echo "# cmd: $CMD"; echo "# at:  $(date -u +%FT%TZ)"; echo "# sha: $(git rev-parse HEAD)"; \
  eval "$CMD"; echo "# exit=$?"; } 2>&1 | tee -a evidence/$(date -u +%F)-probe.log
```

**Negative control.** Tamper with an evidence file and confirm `make evidence-check` fails:
```bash
cp policy/repo-defaults.yml /tmp/rd.bak
printf '\n# tamper probe\n' >> policy/repo-defaults.yml
make evidence-check; echo "exit=$?"     # must be non-zero
cp /tmp/rd.bak policy/repo-defaults.yml  # restore
make evidence-check; echo "exit=$?"     # must be 0
```
If the first `exit=` is `0`, your evidence registry is decorative.

### 3.4 Independent verification — the judge is not the author

**What it means.** The entity that accepts a change must be a different entity from the one that made
it, and must reach its verdict from evidence the author cannot alter.

**Why prose fails.** Your requirement — *"Do not let the same agent be the sole authority for both its
own implementation and its own final acceptance"* — is currently unmet **and unmeetable by GitHub
configuration alone**. Measured: `required_approving_review_count = 0` on 17/17;
`require_code_owner_review = false` on 17/17; zero teams; one human contributor
(`JourneyOfLife`, plus `dependabot[bot]`). The `production` environment now has
`required_reviewers: [JourneyOfLife]` with **`prevent_self_review: false`** — an approval gate that
the author satisfies themselves. `policy/compliance-gates.yml:310-314` records that
`prevent_self_review` was deliberately *not* enabled, because with one member it would wedge every
deploy. **That reasoning is correct. Keep it.** But state the consequence honestly: the four-eyes
principle is not available from GitHub here. Standing acceptance D-04 covers it and
**expires 2026-12-24**.

**So how do you get independence with one human?** Four mechanisms, in increasing strength. Use all
four; they are cheap.

**(a) Role separation by credential, not by intention.** The *implementer* holds a write token
scoped to the target repo. The *reviewer* holds `jolarca-auditor` — read-only, all 17 repos. The
reviewer physically cannot "fix" what it finds; it can only record. This makes the two roles
different *capability classes*, which survives a model's drift far better than "now act as a
different reviewer".

**(b) Context separation.** The reviewer gets a **fresh session** with only: the diff, the task
record, and the acceptance criteria. It does *not* get the implementer's reasoning transcript. A
reviewer that has read the author's justification is primed to agree with it. AGENTS.md §9 already
requires session discipline ("start fresh at completed task boundaries") — this is the same rule
applied to review.

**(c) Machine-checkable acceptance criteria written *before* implementation.** This is the strongest
one and the one most often skipped. Instead of "review whether the change is good", the acceptance
record contains commands and their required exit codes:
```yaml
# acceptance.yml — written by the requester BEFORE the implementer starts
task: PDA-02-consent-ruleset
acceptance:
  - id: AC1
    assert: "consent ruleset requires a PR"
    cmd: gh api repos/jolarca-dev/jolarca-consent/rulesets/24087580 -q '[.rules[].type]|index("pull_request") != null'
    expect: "true"
  - id: AC2
    assert: "consent requires >=5 status contexts"
    cmd: gh api repos/jolarca-dev/jolarca-consent/rulesets/24087580 -q '[.rules[]|select(.type=="required_status_checks")|.parameters.required_status_checks]|length'
    expect_gte: 5
  - id: AC3
    assert: "the change did not touch any other repo"
    cmd: git diff --name-only origin/main...HEAD | grep -vc '^repos/jolarca-consent.yml$'
    expect: "0"
```
Now "independent verification" is a script that runs commands and compares strings. Any agent, any
session, any model gets the same verdict — and it cannot be satisfied by eloquence.

**(d) A negative control on the acceptance criteria themselves.** Prove each AC can fail. Run it
against the *pre-fix* state and confirm it reports false. An acceptance criterion that passes before
the fix is not testing anything. This is the same discipline as §5.11 applied to acceptance rather
than to gates — and it is how you catch an AC written so loosely that the current broken state
already satisfies it.

**What independence is NOT:** a second agent in the same session with the same token reading the same
transcript. That is one reviewer with two mouths.

---

## 4. The role model (who is allowed to do what)

Five roles. One human occupies several of them — that is unavoidable — but each role has a distinct
credential and a distinct session, so the *system* can tell them apart and the evidence shows which
hat was on.

| Role | Holds | May | May NOT | Session |
|---|---|---|---|---|
| **Requester / Owner** | human, `admin:org` in a password manager, not in a shell | define scope, write `acceptance.yml`, approve, sign risk acceptances with a date | implement, self-review | n/a |
| **Architect** | `jolarca-auditor` (read-only, 17 repos) | read everything, measure live state, write findings and plans | write to any repo, apply Terraform | fresh |
| **Implementer** | `jolarca-implementer` (write, named repos) | edit in-scope paths, run local gates, open a PR | merge, edit `acceptance.yml`, edit gates to make them pass, `terraform apply` | fresh |
| **Reviewer** | `jolarca-auditor` (read-only) | run `acceptance.yml`, inspect the diff, record PASS/FAIL with evidence | fix anything, approve its own prior work | **fresh, no implementer transcript** |
| **Deployer** | CI only (`apply.yml`), no human token | apply a plan that passed `check_plan_safety.sh` after the 30-min wait | decide, review, or bypass | GitHub Actions |

Two rules make this more than a diagram:

- **The Reviewer's credential cannot write.** So when the Reviewer says PASS, the only thing it could
  have done to reach that verdict is read and measure. That is what makes the verdict trustworthy
  without trusting the model.
- **The Deployer is not a person.** The human decision is the *merge*. Everything after is
  mechanical, gated and delayed. Treat the merge as the apply decision (AGENTS.md §8).

**The honest limitation, stated once:** with one human, roles (1) and (5) collapse — the owner
approves and CI deploys what the owner approved. Independence is therefore *procedural and
evidentiary*, not *social*. It is weaker than a real second person and stronger than a prompt. Record
it as such in the SOC 2 narrative rather than overclaiming it. If you overclaim four-eyes to an
auditor and they find `prevent_self_review: false`, you lose credibility on everything else.

---

## 5. The procedure — your ten steps, expanded, plus eight more

Each step below has the same six parts. Read them in order; do not skip "Exit criteria", because
that is the part that stops a step from being performed *approximately*.

- **What** — plain language
- **Why** — the specific failure it prevents, with a real example from this fleet where one exists
- **How** — numbered sub-steps with commands
- **Exit criteria** — measurable, binary
- **Evidence** — what to retain
- **Failure mode** — how this step gets faked, and the negative control that catches it

---

### 5.1 Audit the code against the specification

**What.** Take the written requirement and the running code and put them side by side. Find every
place they disagree — in *both* directions.

**Why.** Two distinct defects hide here, and teams always look for only the first.
- *Code does not do what the spec says* — the obvious one.
- **Spec claims a control that does not operate** — the dangerous one, because the spec is what an
  auditor reads. Live example: `policy/compliance-gates.yml:135-148` declares gate `sast` /
  `codeql-analysis` as `enforcement: mandatory` for SOC 2, ISO 27001 and PCI-DSS. CodeQL analyses
  exist on **2 of 17** repos (PDA-06). The code is not broken; the *specification is wrong*, and it
  is wrong in the direction that flatters the organisation.

**How.**
a. List every normative statement in the spec. In YAML policies, these are the fields
   `enforcement:`, `mandatory`, `fail_on:`, `blocked_actions:`, `required:`, and any sentence
   containing "must" or "prevents".
b. For each one, write down the single command that would prove it *operates*. Not "is configured" —
   *operates*. Configuration is `contexts = ["SAST (semgrep)"]`; operation is a green run on a real
   PR.
c. Run the command. Record output.
d. Classify each statement into exactly one of four boxes — this taxonomy is the deliverable:

| Box | Meaning | Example from this fleet |
|---|---|---|
| **Enforced** | gate on the path, proven to fail on bad input | `check_plan_safety.sh` (19 fixtures, negative controls per refusal class) |
| **Configured but inert** | the setting exists, nothing reads it or nobody satisfies it | 16 CODEOWNERS files with `require_code_owner_review=false` and zero teams (D-20) |
| **Convention only** | prose + human discipline | contact-address routing (`policy/contact-addresses.yml` — no gate compares live SECURITY.md to it, D-60) |
| **False** | the spec asserts something measurably untrue | `sast: codeql` declared mandatory; CodeQL runs on 2/17 (PDA-06) |

e. Every **False** box is an S1 finding: fix the *specification* or fix the *system*, and say which
   in the PR description. AGENTS.md §6 forbids leaving it.

**Exit criteria.** Every normative statement in the spec is in one of the four boxes, with a command
and its output recorded beside it. Zero statements unclassified.

**Evidence.** The classified table, committed. Plus the raw command outputs.

**Failure mode.** Auditing only the direction that finds bugs in code, and never the direction that
finds lies in documentation. **Negative control:** pick one statement you classified as "Enforced"
and deliberately break it in a scratch branch; confirm a gate goes red. If nothing goes red, it was
"Configured but inert" and you mis-filed it.

---

### 5.2 Test permission boundaries

**What.** Attempt things the actor should not be able to do, and confirm refusal.

**Why.** A permission you did not test is a permission you assume. §3.2 records that this audit ran
with `admin:org` — a scope an auditor must never hold — and nothing detected it. The boundary existed
only on paper.

**How.** Build a **denial matrix**: rows are actors, columns are the actions that must be refused.
Each cell is a command and an expected HTTP status or exit code.

| Actor → Action | Expected | Command |
|---|---|---|
| Auditor PAT → write repo contents | 403 | `GH_TOKEN=$AUD gh api -X PATCH repos/jolarca-dev/jolarca-vendor -f description=probe -i \| head -1` |
| Auditor PAT → change branch protection | 403 | `GH_TOKEN=$AUD gh api -X PUT repos/jolarca-dev/jolarca-vendor/branches/main/protection …` |
| Implementer PAT → touch an out-of-scope repo | 404 (fine-grained PATs hide inaccessible repos) | `GH_TOKEN=$IMPL gh api repos/jolarca-dev/jolarca-payments -i \| head -1` |
| Implementer → push to `main` | rejected `GH006` | `git push origin main` |
| Implementer → force-push | rejected | `git push --force origin <branch>` |
| Any agent → `terraform apply` locally | exit 1 by design | `make apply` |
| Any agent → `terraform state rm` | must not be possible | credential cannot; plus AGENTS.md §5 |
| Merge → apply without the safety gate | impossible | `apply.yml` runs `check_plan_safety.sh` first |

a. Write the matrix as a shell script that prints PASS/FAIL per row and exits `2` if any probe could
   not be run.
b. Run it with each credential in turn.
c. **Confirm the push rejection is real, not a network error.** The fleet's own record shows a direct
   `git push origin main` refused with `GH006: Protected branch update failed … Changes must be made
   through a pull request … 4 of 4 required status checks are expected` (2026-10-12). That message is
   the evidence. A timeout is not.
d. Test the **boundary of the boundary**: what happens at 00:00 when an exception expires? D-58's
   `expires: 2026-11-16` and D-04's `expires: 2026-12-24` should turn a gate red by themselves.

**Exit criteria.** Every cell in the matrix has a recorded actual status; every expected-refusal cell
shows a refusal; every probe that could not run is marked `exit 2`, not skipped.

**Evidence.** The matrix with actual outputs and timestamps.

**Failure mode.** Testing only the happy path ("can the implementer push a branch? yes → PASS") and
never the denial. **Negative control:** one row must be *expected to succeed* — otherwise the matrix
proves only that everything is forbidden, which would also block legitimate work and would not
survive contact with a real task.

---

### 5.3 Test malformed and adversarial inputs

**What.** Feed every parser, gate and validator input it was not designed for, and confirm it
refuses rather than guesses.

**Why.** This fleet's gates are almost all pattern-matchers over rendered text, which is the most
fragile shape possible. Two real defects: D-22 (regex that never matched) and the ANSI-colour trap
(same plan file, opposite verdicts depending on rendering). Both were *silent* — the gate exited `0`.

**How.** For every gate, work through this list. It is derived from defects that actually happened
here, so each item is worth its weight.

a. **Empty input.** Zero-byte file. Expected `2`. (`-s` test, not `-f`.)
b. **Missing input.** Path does not exist. Expected `2`.
c. **Unreadable input.** `chmod 000`. Expected `2`, not a stack trace and not `0`.
d. **Colourised / ANSI-escaped input.** The plan-safety lesson. Fix: always render with
   `-no-color`, and make the gate *detect* escape bytes and refuse:
   ```bash
   if LC_ALL=C grep -qP '\x1b\[' "$input"; then echo "ANSI escapes present"; exit 2; fi
   ```
e. **Different renderer for the same data.** `terraform show` vs `terraform show -json | jq -r` vs
   `-no-color`. Run the gate on all three; the verdict must be identical. If it is not, the gate is
   reading *format*, not *content*.
f. **Truncated input.** Valid header, cut off mid-record. Expected `2`.
g. **Alternative but valid syntax.** For a YAML registry gate: `visibility: public`,
   `visibility: "public"`, `visibility: 'public'`, a flow mapping `{visibility: public}`, an anchor
   reference, and key reordering. A gate that matches one spelling is a hypothesis (this is exactly
   how D-22's `visibility\s*:` missed `visibility = `).
h. **Unicode homoglyphs and whitespace.** Full-width colon, non-breaking space, zero-width joiner in
   a repository name. For `check_fleet_separation.sh`, a repo named `joIarca-vendor` (capital i)
   should not satisfy an allow-list match for `jolarca-vendor`.
i. **Injection into a shell-interpolated context.** A finding title containing `$(…)` or a backtick.
   This repo already hit the shell-interpolated commit-body variant. Fix: pass values via
   environment variables or `--arg` to `jq`, never by string-building.
j. **Path traversal.** A PR touching `../../etc/passwd`, a symlink in the tree, or a filename with a
   newline. Relevant to `hash_evidence.sh`'s `find` (it uses `-print0`/`sort -z` — correct; keep it).
k. **Oversized input.** A 200 MB plan file. Confirm the gate does not silently truncate to nothing
   and report clean.
l. **Semantically inverted input.** A plan that *enables* a security feature. The gate must allow it —
   `check_plan_safety.sh` deliberately has "two allowed-direction controls (no-op refresh,
   security-feature ENABLING)" so it is not a blanket block (`policy/compliance-gates.yml:214`).
   A gate that refuses everything is not safe; it is unused, and then it is bypassed.
m. **Adversarial *content*, not just shape.** For secret scanners: a synthetic credential assembled
   at runtime, a base64-encoded token, a token split across two lines, a token in a file the scanner
   ignores (`.gitignore`d, binary, symlinked). **Critical constraint:** AGENTS.md §5 forbids literal
   secrets or credential-shaped fixtures in tests or docs — push protection scans documentation and
   a real-looking fixture can permanently S0-BLOCK the readiness gate. Assemble synthetic values at
   runtime from fragments.

**Exit criteria.** Every gate has a fixture file per letter above, wired into `make test`, and each
fixture's expected exit code is asserted. Adding a gate without these fixtures fails review.

**Evidence.** The fixture files themselves, committed, plus a CI run showing them exercised.

**Failure mode.** Writing positive fixtures only. **Negative control:** this *is* the negative
control step. If your test suite has no case that must fail, delete the suite's claim to test
anything.

---

### 5.4 Verify failure handling and recovery

**What.** Prove the system behaves correctly when a component dies — and that you can get back.

**Why.** Failure handling and *recovery* are different tests, and only the first is usually done.
Live example: `apply.yml` on run 38781192964 (2026-10-15) failed at `Terraform Plan` with
`Error acquiring the state lock / resource not found`, and `Terraform Apply` was **skipped**. The
fleet recorded that as evidence the apply path is safe. It is not — it is evidence of a **broken CI
credential (D-56)**. The safe outcome was an accident. AGENTS.md §8 says to read it as the current
state of a broken automation, "not as a control".

**How.**
a. **Enumerate the failure points**: state lock held, backend unreachable, token expired, runner
   out of disk, gate exit `2`, network partition mid-apply, workflow cancelled mid-run, dependency
   registry down.
b. For each, decide the **required** behaviour: fail closed? retry? halt and page? Then provoke it.
   - State lock: hold it deliberately, run the plan, confirm refusal and that no partial apply
     occurred.
   - Expired token: revoke a scratch token, run, confirm exit `2` and not `0`.
   - Runner disk-full: the fleet has a real incident (`JOL-PROC-20261008-01`, closed by
     `jolarca#198`) — read it and confirm the fix is in place.
c. **Test the cancel path**, because it is the only human brake on a 30-minute-wait deploy:
   ```bash
   gh run list -R jolarca-dev/jolarca-control --workflow apply.yml --limit 5
   gh run cancel <run-id> --force      # --force is REQUIRED; without it the CLI prompts and a
                                       # non-interactive shell looks like it failed
   gh api repos/jolarca-dev/jolarca-control/actions/runs/<run-id> -q '{status,steps_started}'
   ```
   This was proven on run 38813823199 (2026-10-16): cancelled mid-wait with `steps_started: 0`,
   workspace unchanged at 48 resources. **That proof is the control.** Retain it.
d. **Test recovery, not just failure.** For state: `make backup BACKUP_DEST=<dir>`, which since
   2026-10-15 pulls the current state version from the HCP backend, age-encrypts to `$BACKUP_DEST`,
   and **decrypts and compares the SHA-256 before claiming success** (skip the proof → exit `2`).
   10 fixtures in `tests/test_state_backup.sh`. Then confirm the *restore* direction works from the
   artefact you just produced, on a scratch workspace.
e. **State the residual honestly.** AGENTS.md §8: the backup "works when someone runs it — and that
   is all". There is **no schedule** and **no genuinely off-host destination**: the age identity and
   `/opt/jolarca/backups/` both live on the machine holding the working copy. That is a verified
   export path, not a 3-2-1 copy. D-02 is **not** closed. Do not let a green `make backup` become a
   claim of disaster recovery.

**Exit criteria.** Every enumerated failure point has a provoked test with recorded output; the
cancel path is proven with `steps_started: 0`; the backup round trip is proven by hash comparison;
and the *restore* has been executed at least once from a real artefact.

**Evidence.** Run IDs, timestamps, the backup log, the hash comparison output.

**Failure mode.** Reading an accidental failure as a control (the 38781192964 mistake).
**Negative control:** for each failure test, confirm the *bad* thing did not happen by an
**independent** measurement — read the live resource count, not the workflow's own conclusion.

---

### 5.5 Check dependency and configuration security

**What.** Every third-party thing you execute or ship: pinned, scanned, licensed, and current.

**Why.** Measured live: **13 unpinned actions** across 55 `uses:` lines, **11 of them in `.github`
shared workflows** that other repos call with their own tokens (PDA-13); **49 open PRs** including
`hashicorp/google` 6.50.0 → **8.7.0** (two majors) on the repo that owns the apply path; four repos
with **no `dependabot.yml`**; two major-version action bumps (`actions/checkout` 4 → 7) open 26 days.

**How.**
a. **Pin audit.** Enumerate every `uses:` and every dependency spec:
   ```bash
   for r in $(gh repo list jolarca-dev --limit 100 --json name -q '.[].name'); do
     for f in $(gh api repos/jolarca-dev/$r/git/trees/main?recursive=1 \
          -q '.tree[]|select(.path|startswith(".github/workflows"))|select(.path|test("\\.ya?ml$"))|.path'); do
       gh api repos/jolarca-dev/$r/contents/$f -q .content | base64 -d \
        | grep -nE '^[[:space:]]*uses:' | grep -vE 'uses:[[:space:]]*\./' | grep -vE '@[0-9a-f]{40}' \
        | awk -v R="$r" -v F="$f" '{print "UNPINNED " R "/" F " " $0}'
     done; done
   ```
   Rule (AGENTS.md §5): full 40-hex SHA + a `# vX.Y.Z` comment. Ruff's rule set is pinned in
   `pyproject.toml` because its defaults move between releases — pin *behaviour*, not just versions.
b. **Verify the pin resolves to the tag you think it does.** A SHA is only meaningful if it matches
   the claimed release: `gh api repos/actions/setup-python/git/ref/tags/v5 -q .object.sha` and
   compare. `.github#4` exists precisely because a SHA was **fabricated** (D-43).
c. **Vulnerability scanning.** `dependabot.yml` present on 17/17; vulnerability alerts on (HTTP 204
   from `…/vulnerability-alerts`); `pip-audit`/`npm audit`/`trivy` versions pinned identically in CI,
   pre-commit and locally (the gitleaks 8.30.1 pattern).
d. **Licence compliance.** `deny_licenses: [GPL-3.0, AGPL-3.0, SSPL-1.0]` applies to **inbound
   dependencies only** — `policy/compliance-gates.yml:105-109` explicitly protects the app's own
   AGPL-3.0. Do not "fix" that.
e. **Configuration security** — the half everyone forgets. Review, per repo:
   - `terraform.tfvars`: `enable_branch_protection` (weakening fires D-26)
   - workflow `permissions:` blocks — default to `contents: read`, elevate per-job only
   - `GITHUB_TOKEN` scope in each job; a reusable workflow inherits the **caller's** token
   - org `default_repository_permission = none` ✔ (verified)
   - secrets inventory: which secret exists, which workflow may read it, in which environment
   - `.env.example` vs `.env.prod.example`: confirm no real value ever lands in the example
f. **Age SLA.** Detection without landing is not a control (PDA-09). Define a maximum age for an open
   security PR and make a gate fail on *age*, not on scanner presence.

**Exit criteria.** Zero unpinned actions; every pin's SHA verified against its tag; `dependabot.yml`
on 17/17; no open security PR older than the SLA; every workflow's `permissions:` block explicitly
set.

**Evidence.** The pin-audit output (empty), the tag↔SHA comparison table, the PR-age report.

**Failure mode.** Trusting the scanner's existence rather than the queue's state.
**Negative control:** introduce a deliberately unpinned `uses:` in a scratch branch and confirm the
pin gate refuses it. Then confirm the gate is itself pinned.

---

### 5.6 Review the CI workflow

**What.** Read the workflows as an adversary and as an auditor: what triggers them, what they may
touch, what must be green, and what happens when they cannot run.

**Why.** The most dangerous property of CI is that it is *trusted*. A required context that never
triggers is indistinguishable, from the merge button, from one that passed. This fleet has a
first-hand precedent: `policy/repo-defaults.yml` named a required context — `"Fleet Separation Guard"`
— that **no job reports** (the job is `Fleet Separation (ADR-0004)`), while omitting a real one,
`SAST (semgrep)`. It sat that way for ten days. A required context that cannot be reported
**deadlocks every merge**; one that is never produced **silently passes**. Both are invisible from
the branch-protection screen.

**How.**
a. **Trigger audit.** For each workflow: `on:` events, `paths:` filters, `branches:`. Then answer:
   *can a `pull_request` event actually produce this job?* A `paths:` filter that excludes the PR's
   files means the job never runs — and if it is a required context, the PR can never merge, or (with
   a lenient setting) merges untested. Note `plan.yml` has **no `workflow_dispatch`** and narrower
   `push` paths than `pull_request` paths.
b. **Context-name parity.** The declared required context string must equal the job's **reported
   name** — `job.name:` if set, else the job key. Verified clean for all 17 repos on 2026-10-24
   (companion report §3, deadlock test). Keep it that way with
   `make context-baseline` / `scripts/check_required_context_baseline.py`, which compares the policy
   baseline against `repos/jolarca-control.yml` **and** against the job names a `pull_request` can
   report, and runs *inside* a required context (`Validate Repo Allow-List`) — D-62.
c. **`make lint` is not the whole CI surface.** `compliance-scan.yml` additionally runs
   `scripts/compliance_check.py` at line 128 (`make compliance`), which is not in `lint`. Run it before
   pushing. Note the correction this audit made: AGENTS.md §2 also names
   `scripts/repo_readiness_audit.py --no-live`, but **no workflow invokes it** (PDA-15) — its only
   appearances under `.github/workflows/` are comments. `compliance-scan.yml`'s real surface is:
   `validate_repos.py`, `check_required_context_baseline.py`, `check_declared_contexts.py`,
   `check_deploy_gates.py`, `check_findings_register.py`, `compliance_check.py`, `gitleaks git .`,
   `tests/test_state_backup.sh`, `pytest tests/`, `ruff check` + `format --check`, `shellcheck -x`,
   `terraform fmt -check -recursive`. Run all of them locally, or read the job list before assuming.
d. **Permissions and secrets.** Every job's `permissions:` block; every `secrets.` reference mapped
   to a real secret; no secret available to a job that does not need it; `pull_request_target` never
   used with a checkout of untrusted code.
e. **Self-referential triggers.** `apply.yml` fires on `push: main` for paths including **itself**.
   A merge that edits `apply.yml` triggers `apply.yml`. Confirm the safety gate runs *before* the
   apply in that path.
f. **Failure semantics.** No `|| true`, no `continue-on-error: true` on a security step, no
   `if: always()` masking a prior failure. And remember `plan.yml` exits on
   `detailed-exitcode 2`, which *skips* the downstream Plan safety check — a skip is not a pass.
g. **Path existence.** A workflow that cites a script path that does not exist fails only when that
   branch runs. `jolarca-control#79` is exactly this ("workflows may not cite paths that do not
   exist", D-72) — and it was open 7 days at measurement. Make it a gate, not a review habit.

**Exit criteria.** For every required context on every repo: a named workflow, a trigger that a
`pull_request` satisfies with no excluding path filter, and a job whose reported name equals the
declared string exactly. Recorded per repo.

**Evidence.** The parity table; a live PR's `statusCheckRollup` per repo showing all contexts
actually reported.

**Failure mode.** Reading the workflow file and concluding it runs. **Negative control:** open a
deliberately trivial PR and confirm every required context actually reports on it — including the
path-filtered ones. `jolarca-control#42/#43` are the precedent for this measurement.

---

### 5.7 Verify the documentation against actual behaviour

**What.** Every sentence that asserts the system does something, tested against the system.

**Why.** AGENTS.md §6: *"Documentation must state actual implementation status. Never describe a
control as enforced when it is configured-but-inert or convention-only."* This is not a stylistic
rule. In a SOC 2 Type II examination, **your documentation is the control description**. An auditor
tests what you claim. A claim you cannot evidence is a finding; a claim that is measurably false is
worse — it undermines every other claim.

Three live examples of documentation drifting from behaviour:
- `sast: codeql-analysis`, `enforcement: mandatory` → CodeQL analyses on 2/17 repos (PDA-06).
- D-33 "FULLY RESOLVED … verified via `gh api .protected=true`" → `.protected=true` on a repo where
  direct push to `main` is allowed (PDA-14).
- `AGENTS.md:48-51` says `compliance-scan.yml` "additionally runs … `scripts/repo_readiness_audit.py
  --no-live`" → **no workflow invokes it**; every occurrence under `.github/workflows/` is a comment
  (PDA-15). The companion claim about `compliance_check.py` in the same sentence is *true*
  (`compliance-scan.yml:128`) — which is why a narrow grep would have produced a false finding
  against both. Read the file.
- `.github`'s three reusable workflows each say "Called by individual repos via …" → zero callers
  (PDA-16).
- AGENTS.md §8 itself records that it said "three required contexts" until 2026-10-12 when the fourth
  (`SAST (semgrep)`, added by A-08 on 2026-10-08) was found. **The most carefully maintained document
  in the fleet was wrong for four days** — and PDA-15 shows it is wrong again now, elsewhere.

**How.**
a. Extract every assertive sentence. Search for the tell-tale verbs: *enforced, prevents, blocks,
   requires, guarantees, mandatory, always, never, verified, FIXED, RESOLVED, CLOSED*.
   ```bash
   grep -rnE '\b(enforced|prevents|blocks|guarantees|mandatory|FIXED|RESOLVED|CLOSED)\b' \
        AGENTS.md docs/ policy/ audit/ repos/ | wc -l
   ```
b. For each, write the disproving test. Not "is it true?" but **"what observation would prove it
   false?"** If you cannot construct one, the sentence is unfalsifiable — rewrite it as an intention,
   or delete it.
c. Pay special attention to any sentence containing a **date** and the word *verified*. Those decay.
   Re-run them. A verification dated six weeks ago is a claim about the past.
d. Check the **"FIXED" queue**. The companion audit found the register's own warning:
   `exceptions.open_blocking` "is stale in both directions and must be re-read before use". Re-read
   means re-measure.
e. **Do not infer absence from a search.** AGENTS.md §1: *"Search results are claims too. A grep that
   returns 'no matches' or a truncated result set has not proven absence — read the file before
   asserting a defect."* When a document seems to omit something, confirm by a second method. This
   audit confirmed `jolarca-infrastructure` has no CODEOWNERS by *both* the contents API (404 at two
   paths) *and* a recursive git tree listing, precisely because one method alone is not proof.
f. Fix the document **and** the code in the same PR when they disagree, and say which one was wrong.

**Exit criteria.** Every assertive sentence either has a passing disproving test, or has been
rewritten to state its real status (inert / convention-only / intended). Zero unqualified "FIXED"
claims without a dated measurement beside them.

**Evidence.** The sentence → test → output table.

**Failure mode.** Verifying documentation by reading it again. **Negative control:** insert a
deliberately false claim into a scratch copy and confirm your review process catches it. If a human
or an agent read the copy and did not notice, the process does not detect this class.

---

### 5.8 Have a separate reviewer inspect the implementation

**What.** A different identity, a fresh context, read-only credentials, and pre-written acceptance
criteria.

**Why.** See §3.4. Summarised: the author has no adversarial pressure on their own work, and in this
fleet `required_approving_review_count = 0` on 17/17, so **no human review happens at all** unless
you build it procedurally.

**How.**
a. The **Requester** writes `acceptance.yml` (§3.4c) *before* the Implementer starts. This is the
   single highest-leverage step in the whole procedure, because it converts "is this good?" into
   "do these commands return these values?".
b. The **Implementer** works in a fresh session with the write token, opens a PR, and stops. It does
   **not** mark the task done.
c. The **Reviewer** is dispatched in a **fresh session** with:
   - the read-only `jolarca-auditor` token,
   - the diff (`gh pr diff <n>`),
   - `acceptance.yml`,
   - the relevant policy files,
   - and **not** the Implementer's transcript.
   Its instructions: run every AC, record actual output, verdict PASS or FAIL per AC with evidence.
   It may not edit anything — its credential cannot.
d. The Reviewer must also run the **negative control on the ACs** (§3.4d): confirm each AC fails
   against the pre-fix state. This catches acceptance criteria written so loosely that the broken
   state already satisfies them.
e. FAIL → back to the Implementer with the specific AC ids. Not "looks wrong" — "AC2 expected ≥5,
   got 0".
f. The **Owner** reads the Reviewer's evidence and merges. The merge is the decision.
g. **Re-verify after merge** (AGENTS.md §1: `VERIFY AGAIN`). Live state, not the merge banner.
   Post-merge, re-read the live resource and compare against the declared registry — the fleet's
   own test specification calls this the declared-vs-live visibility check.

**Exit criteria.** A Reviewer verdict exists, produced by a different session under a read-only
credential, covering every AC, with the AC negative control recorded. The Owner's merge references it.

**Evidence.** `acceptance.yml`, the Reviewer's per-AC output, the merge commit, the post-merge
re-verification output.

**Failure mode.** "Review" performed by the same session that implemented, or by a subagent given the
implementer's reasoning. That is one reviewer with two mouths. **Negative control:** plant a
deliberate defect in the implementation before review and confirm the Reviewer finds it. If the
planted defect survives review, your review is theatre — and you now know that, which is worth the
cost of the exercise.

---

### 5.9 Remediate material findings

**What.** Fix what matters, in blast-radius order, without weakening a gate to get there.

**Why.** AGENTS.md §5: *"Do not delete or weaken a gate to make CI pass. If a gate is wrong, fix the
gate and its fixtures in the same PR, and say so in the description."* Under pressure to go green,
the cheapest edit is always to the thing that is complaining.

**How.**
a. **Classify by blast radius, not diff size** (AGENTS.md §4). A 3-line change can be catastrophic;
   a 400-line docs change can be trivial.
   - **High:** `*.tf`, `*.tfvars`, `repos/**`, `policy/**`, `.github/workflows/**`, `scripts/**`,
     `docs/evidence-registry.csv` → human-read plan + top-tier review regardless of size.
   - **Lower:** `docs/**` prose, `staging/**`, `audit/**` checklists.
   - **Highest consequence:** a `repos/*.yml` `visibility` flip (D-01 class — changes what is publicly
     readable inside PCI-DSS/GDPR scope); `terraform.tfvars` `enable_branch_protection` (D-26);
     anything touching secret-scanning or push-protection configuration.
b. **Sequence by risk reduction per unit of risk introduced.** The companion report §6 gives the
   order for the 14 PDA findings: consent ruleset → `.github` pins + secret scanning →
   infrastructure action pins → infrastructure CODEOWNERS → vendor context list → dependabot → SAST
   declaration → register hardening → control-plane PR backlog → PR queue → licences → naming.
c. **One finding per PR.** Mixed remediation is unreviewable and unrevertable.
d. **Every remediation PR carries**: the finding id, the measurement that proved it, the change, the
   re-verification command, and its output.
e. **Fix the class, not the instance.** PDA-08 found two ADR-0004 breaches in `LICENSE` files. The
   fix is not two strings — it is extending `check_fleet_separation.sh` to scan `LICENSE`/`NOTICE`,
   plus a negative control proving it fires. Otherwise the next file with the same defect ships.
f. **If the fix must weaken something, stop and escalate.** Record it as an exception with a date,
   an approver, compensating controls and an `expires` (§5.14) — never as a silent edit.
g. **Never fix a gate by deleting its assertion.** If a gate is wrong, the fixtures change with it,
   in the same PR, and the description explains why the old behaviour was wrong.

**Exit criteria.** Each material finding is closed by a merged PR whose description contains the
re-verification command and output, or is recorded as a dated, approved exception.

**Evidence.** PR links, the re-verification outputs, the updated register.

**Failure mode.** Closing a finding by editing the register. **Negative control:** re-run the original
measurement after remediation. If it still reports the finding, the remediation did not happen.
PDA-14 exists because a finding was closed on a signal that could not have detected it.

---

### 5.10 Repeat the relevant verification tests

**What.** Re-run the measurements, not the tests you wrote while fixing.

**Why.** AGENTS.md §1: `VERIFY FIRST → COMMIT → PUSH → REVIEW → MERGE → VERIFY AGAIN`. *"Re-verify
after merge. Live state, not the merge banner."* A fix merged is a fix *claimed*. The fleet's own
record shows why: PR #69 merged on 2026-10-15 and the expected apply **did not happen** — run
38781192964 failed on a state lock and the apply was skipped. Reading the merge banner would have
produced a false conclusion in either direction.

**How.**
a. Re-run **every** command recorded in the finding's "Re-verify" block.
b. Re-run them **against live state**, after the merge, from a clean checkout — not against your
   working tree.
c. Re-run the **negative controls** too. A fix that also breaks a gate's ability to fail is a
   regression, and it is invisible unless you re-test the failure.
d. Re-run the **adjacent** checks: `make lint` **plus** `make compliance` **plus**
   `repo_readiness_audit.py --no-live` (the two that `lint` does not cover), and
   `make evidence-check` if any hashed file moved.
e. Compare **counts**, not just verdicts. AGENTS.md §7: *"Do not trust a correct verdict … Cross-check
   finding counts against an independent run."* A gate can report the right aggregate answer while
   silently skipping whole check families.
f. Record the re-verification with timestamp and commit SHA, and commit it.

**Exit criteria.** Post-merge live measurements match the intended state; negative controls still
fail as designed; finding counts from an independent run agree.

**Evidence.** The re-verification log, committed under `docs/security/` so it is hashed.

**Failure mode.** Accepting the CI green tick as verification. **Negative control:** pick one thing
CI reported green and measure it independently by a different method. This audit did exactly that
with `.protected=true` vs the ruleset document — and found PDA-02, PDA-03 and PDA-14.

---

### 5.11 *(added)* Verify the verifier

**What.** Prove each gate detects the thing it exists to detect, using a fixture that must fail.

**Why.** AGENTS.md §7: *"A gate that runs and reports green has not been shown to detect anything."*
D-22 is the canonical case: an inert regex was the **only** control between an unattended apply and a
fleet-wide visibility flip. And PDA-03 is the same defect in configuration form — a
`required_status_checks` rule that exists, is reported as present, and contains an empty list.

**How.**
a. For every gate, write at least one **negative control** per refusal class.
   `tests/test_check_plan_safety.sh` is the model: 19 fixtures, every refusal class has a negative
   control transcribed from real `terraform show` output, plus two **allowed-direction** controls
   (no-op refresh, security-feature *enabling*) proving it is not a blanket block.
b. Transcribe fixtures from **real** output, not invented output. D-22 happened because the author
   guessed the rendering (`visibility:`) instead of reading it (`visibility = `).
c. Assert the exit code, not just non-zero. `1` and `2` mean different things (§2).
d. Confirm the gate is **wired**. A tested script that nothing calls is a library.
   `tests/test_check_required_context_baseline.py` includes an assertion that the script is wired
   into a required job — that assertion is the part that matters.
e. Confirm the gate **cannot be bypassed by a flag**. `check_plan_safety.sh` deliberately has no skip
   flag: "a bypass switch is the thing that made the D-22 inline grep useless"
   (`policy/compliance-gates.yml:233-237`).
f. Re-run the negative controls after every change to the gate.

**Exit criteria.** Every gate has ≥1 negative control per refusal class, transcribed from real
output, asserting an exact exit code, and wired into CI or `make test`.

**Failure mode.** Testing that the gate runs. **Negative control:** the negative control *is* the
test. If removing the defect from a fixture still lets the gate pass, the gate is inert.

---

### 5.12 *(added)* Make every gate fail closed

**What.** Audit every gate for the "could not verify" path and confirm it exits `2`.

**Why.** §2. Concretely: `plan.yml` exits on `detailed-exitcode 2` so the *Plan safety check* is
skipped; and `hashFiles` misses the gitignored `plan-output.txt`, so a hash-based condition can
evaluate against nothing. Both are ways a "could not verify" becomes a "proceed".

**How.** For each gate: (a) list its inputs; (b) for each input, ask what happens if it is missing,
empty, unreadable, or malformed; (c) confirm the answer is `2`; (d) confirm no caller converts `2`
into a skip or a pass; (e) confirm the CI step has no `continue-on-error` and no `|| true`.

**Exit criteria.** No gate can exit `0` on an input it could not parse. No CI step treats a non-zero
exit as success.

---

### 5.13 *(added)* Time-bound every exception, and make expiry automatic

**What.** Every risk acceptance carries an ISO-8601 `expires`, an `approved_by`, a compensating
control and an `exit_trigger`. On the expiry date the gate goes **red by itself**.

**Why.** `policy/compliance-gates.yml:321-328` records the lesson: *"an event-only expiry ('when X
happens') has no deadline and can stay open indefinitely, which is precisely how these two entries
came to violate the policy they live under (D-25)."* D-33's exit condition was "GitHub Team plan
enabled" — an event that never came, so the acceptance never lapsed.

**Live expiries to diary now:**

| ID | Subject | Expires |
|---|---|---|
| D-58 | production apply has no independent human approval | **2026-11-16** (23 days) |
| D-04 | `required_approving_review_count = 0` | 2026-12-24 |
| D-05 | `require_signed_commits = false` | 2026-12-24 |
| D-07 | tag protection unenforceable | 2026-12-24 |
| D-33 | branch protection / plan-tier | 2026-12-27 |
| payments-public | PCI-DSS repo public | 2026-12-29 |
| control-plane-public | PCI-DSS operational repo public | 2026-12-29 |
| fleet-public-2026-10 | three PCI repos public | 2026-12-29 |
| contact-alias-interim | Gmail plus-aliases as role contacts | 2027-01-13 |

**How.** (a) A gate that parses every `expires` and fails when one is past — the fleet already
requires the date form; make it fail, not warn. (b) A lapse is closed by *a PR that restates the
compensating controls*, not by silence. (c) Never infer approval from a conversation: AGENTS.md §1 —
*"Approval lives in a dated record (`policy/compliance-gates.yml` `exceptions.active`) or it does not
exist."*

**Exit criteria.** Every active exception has `expires` + `approved_by` + compensating control +
`exit_trigger`; a gate fails on lapse; D-58's 2026-11-16 lapse has a plan.

---

### 5.14 *(added)* Reconcile the record before trusting it

**What.** Treat the findings register itself as an audit target.

**Why.** PDA-14: D-33 was closed on `.protected=true`, a signal that reads identically for "12
required contexts" and "direct push allowed". The register was reassuring and wrong. AGENTS.md §8
already warns that `open_blocking` "is stale in both directions". And the fleet has a precedent for a
documented remediation claim being false against production: D-20 claimed five CODEOWNERS files were
rewritten while live inspection showed four repos had none at any path.

**How.** (a) For every finding marked FIXED/RESOLVED/CLOSED, re-run its measurement. (b) For every
finding marked open, confirm it is *still* open — closure by staleness is as common as false closure.
(c) Ask of each closure signal: **"could this signal read the same way if the property were absent?"**
If yes, the signal is insensitive and the closure is unsupported. (d) Harden the detector to read
**content** rather than **presence** — for protection, the required-context list and whether a
`pull_request` rule exists, not `.protected`.

**Exit criteria.** Every FIXED claim has a fresh dated measurement; every closure signal passes the
insensitivity test; `drift_detect.py` reads rule content and has a negative control built from
`jolarca-consent`'s real ruleset JSON.

---

### 5.15 *(added)* Audit the trust you inherit

**What.** Everything that executes in your context but is not yours: reusable workflows, composite
actions, base images, Terraform providers and modules, pre-commit hooks, MCP servers, model tooling.

**Why.** Two live examples, and the second is the more instructive.

- **PDA-13 — inherited code that runs.** `actions/github-script@v9` in
  `jolarca-infrastructure/terraform.yml:87` is arbitrary JavaScript holding the token of the repo that
  owns the Terraform apply path, referenced by a mutable tag. That workflow *runs today*. Same file,
  `terraform-linters/setup-tflint@v6` at line 40. Plus `actions/upload-artifact@v7` in `jolarca/ci.yml`.
- **PDA-16 — inherited code that does not run, but says it does.** `.github` holds three reusable
  workflows declaring `workflow_call:`, carrying **17 jobs** that are the fleet's only implementation
  of five *mandatory* gates (`dependency_scan`, `license_check`, `container_scan`, `iac_scan`,
  `iac_policy`), with **zero callers** anywhere in 17 repos. Line 2 of each file documents them as
  *"Called by individual repos via: `uses: jolarca-dev/.github/.github/workflows/<f>@main`"*. Two
  problems compound: five mandatory gates are inert fleet-wide, and the documented call form is
  `@main` — a **mutable branch ref** pointing at a repo with secret scanning off and zero required
  contexts. Wiring this up as documented would create the supply-chain edge that the previous draft of
  this audit wrongly assumed already existed.

The general rule: **map the trust you inherit, then test the map.** Do not reason about what a
reusable workflow *would* do if called — measure whether anything calls it.

**How.** (a) Map the inheritance graph **and verify it has edges**: scan every workflow in every repo
for `uses: <owner>/<repo>/.github/workflows/…`, then subtract the comment lines. An empty result is a
finding (PDA-16), not a clean bill. (b) Apply §5.5's pin audit to the *provider* repos, not just your
own. (c) Pin Terraform providers and modules by version **and** confirm `.terraform.lock.hcl` is
committed (it is here). (d) Treat a major-version provider bump as a reviewed change with a plan diff,
never as a Dependabot auto-merge — `hashicorp/google` 6.50.0 → 8.7.0 crosses two majors (PDA-04).
(e) Pin the **agent toolchain** too: Qoder CLI version, MCP server versions, model configuration.
AGENTS.md §5 says "no new dependency, action, or tool version unpinned" — an MCP server is a tool
version. (f) When calling a reusable workflow, pin to a **SHA**, never `@main` or `@v1`.

**Exit criteria.** A complete inheritance map **with its edges verified by measurement**; every
inherited executable pinned to an immutable reference; every major-version bump has a recorded plan
review; and zero shared workflows whose documentation claims consumers they do not have.

---

### 5.16 *(added)* Prove the data-classification boundary

**What.** Show that no regulated data lives where the classification says it must not.

**Why.** The whole fleet is public (`visibility: public` on 17/17, forced by GitHub's migration and
accepted under `fleet-public-2026-10`). Public + "adjacent to the cardholder-data environment"
(`policy/compliance-gates.yml:9-10`) means the **only** thing protecting regulated data is that it is
not in git. That has to be *proven*, not assumed — repeatedly, and by a scanner with a negative
control.

**How.** (a) Full-history secret scan on every repo — `jolarca-identity` already requires a context
literally named `gitleaks (full history)`; that is the right shape. (b) Confirm the data stores live
outside git: the current branch of this repo is `docs/register-data-stores-d79`, whose head commit is
*"docs(classification): register data stores outside git"* — that register is the artefact to check.
(c) Verify encryption-at-rest config is not itself secret-bearing: `jolarca/.sops.yaml` publishes an
**age public key**, which is correct; `jolarca/secrets/` holds only `encrypted/README.md`. Both were
measured, and both are fine — but "fine" here is a *measurement*, and it needs re-taking after every
change to those paths. (d) Test the classification gate: `validate_repos.py` has a PCI-DSS
operational-public guard that fires only when `launch_status` is `operational`. Confirm which repos
are `planned` and what happens the day one flips — `payments-public` exists to pre-position that
override.

**Exit criteria.** A clean full-history scan per repo with a proven negative control; a register of
data stores outside git; the classification gate demonstrated to fire on a synthetic violation.

---

### 5.17 *(added)* Plan for the single operator disappearing

**What.** Bus-factor continuity, treated as a compliance control rather than an inconvenience.

**Why.** One human, `JourneyOfLife`, is the sole contributor to 17/17 repos, the sole holder of every
credential, the sole approver on the `production` environment, and the only person who knows where
the age identity for the state backup lives. AGENTS.md §8: the backup's age identity **and**
`/opt/jolarca/backups/` both live on the machine holding the working copy — so it is not a 3-2-1
copy, and "it is only as current as the last human who ran it". There is **no schedule**. D-02's
second half is open, and AGENTS.md §8 says plainly: *"Do not delete an account, org or workspace, and
do not treat D-02 as closed."*

**How.** (a) Put the backup on a schedule (cron/systemd timer) to a destination on a **different
machine**, and retain `docs/backup-log.tsv` as evidence — the register cites that file and it did not
exist until the script was fixed. (b) Record key custody: `docs/security/key-custody.md` exists —
verify it names a recovery path that does not require the operator's laptop. (c) Write the
runbooks so a stranger can execute them: `docs/runbooks/` has deployment-rehearsal,
github-token-rotation, workload-identity-federation, first-commit-pipeline, d31-regulated-records
removal. **Rehearse** them (`docs/runbooks/deployment-rehearsal.md`, `jolarca-dr/rehearsals/`),
because an unrehearsed runbook is documentation, not recovery. (d) Escrow: a second holder for the
age key and the org owner credential, or a documented legal process.

**Exit criteria.** A scheduled backup to an off-host destination with a retained log; at least one
completed restore rehearsal with evidence; key custody documented with a recovery path that survives
loss of the primary machine.

---

### 5.18 *(added)* Make the audit itself reproducible by a stranger

**What.** Someone who was not you, and not your agent, must be able to re-run this audit and reach the
same conclusions.

**Why.** This is the property that turns an audit into a control. If the result depends on which
model ran it, or on a transcript nobody retained, then the next audit can silently disagree and
nobody can tell which is right.

**How.** (a) Commit the sweep scripts alongside their outputs. The companion report §1 lists five
sweeps; they should live in the repo, not in `/tmp`. (b) Record the tool versions (`gh --version`,
`jq --version`) and the token's scopes — because, as §3.2 shows, the scopes change what you can see.
(c) Record every `exit 2` — the "could not verify" list is part of the result, not an appendix.
(d) Record what was **out of scope** and why. This audit did not inspect
`backend/project/settings/production.py`, `nginx.prod.conf`, `docker-compose.prod.yml` or
`.env.prod.example` line-by-line; that is stated in the companion report §5 rather than left
implicit.

**Exit criteria.** A stranger running the committed scripts on the stated date reproduces the matrix
in the companion report §3, including the "could not verify" list.

---

## 6. Toolchain and topology — what is necessary, and what is not

You named five components. Here is the verdict on each, and the two you did not name but need.

| Component | Verdict | Role it must play | Role it must NOT play |
|---|---|---|---|
| **`jolarca-control`** | Necessary — already the control plane | Single declarative source for repo/protection/policy state; the gates that refuse unsafe applies | The place where audit evidence is *only* stored (evidence must be hashed — §3.3) |
| **`jolarca-hermes-agents`** | Necessary, **conditional** | Agent definitions, role prompts, the acceptance-criteria schema, and the reviewer contract | Holding a write credential, or being self-hosted on the same identity as the implementer |
| **`mcp-prod-lt01`** (your Ubuntu 24.04 server) | Necessary as a **target**, wrong as a **workspace** | Runs the deployed workload; is the subject of DR/restore rehearsal | Running an agent that both changes and approves; holding the only copy of the state backup |
| **Qoder CLI / SDK / MCP** | Necessary | The execution harness. Pin the version like any dependency (§5.15e) | Being treated as trusted-by-default: an MCP server is third-party code with your token |
| **Work machine (Ubuntu 24.04)** | Necessary | Implementer + Reviewer sessions, with the two tokens in separate `chmod 600` files | Being the same host as the backup destination (that is why D-02 is not closed) |

**Two components you did not name, both necessary:**

1. **A separately-credentialed reviewer identity.** Not a second human — a second *GitHub identity*
   (a machine user or a fine-grained PAT with read-only scope across all 17 repos). This is the only
   way to make §3.4 real with one operator: the reviewer's independence becomes a property of its
   credential, which cannot be argued away by a persuasive model. Cost: zero on the Free plan.
2. **An evidence store that is not the working copy.** Any second host, object store, or even a
   separate local disk satisfies "off-host" better than today's arrangement, where the age identity
   and `/opt/jolarca/backups/` sit on the same machine as the working copy. Without this, D-02 stays
   open and the DR story stays incomplete (§5.17).

**On MCP specifically** (`https://docs.qoder.com/cli/sdk/mcp`): an MCP server runs with whatever
credential you hand it and can read everything in its scope. Treat each configured server as a
dependency under §5.15 — pin it, name its scope, and do not give a server the implementer token if
it only needs to read. The five servers configured on this machine (`browser-use`,
`chrome-devtools`, `context7`, `playwright`, `terraform`) should each have a recorded justification
and scope; `terraform` in particular can read provider and module detail and should never hold a
state-mutating credential.

**Topology rule, stated once:** *the machine that changes something, the machine that judges it, and
the machine that holds the backup must not be the same machine — and must not share a credential.*
Today all three are one Ubuntu 24.04 box with one `admin:org` token in the keyring. That is the
single largest structural gap in the programme, and it is free to fix at the credential layer even
before a second host exists.

---

## 7. The Master Architect Prompt (copy-paste ready)

Use this for each audit or implementation task. Fill the bracketed fields; delete nothing else.

```
ROLE
You are the [ARCHITECT | IMPLEMENTER | REVIEWER] for the jolarca-dev marketplace fleet.
Compliance frame: SOC 2 Type II, GDPR, ISO 27001:2022, PCI-DSS 4.0.
All 17 repos are in or adjacent to the cardholder-data environment
(policy/compliance-gates.yml:9-10). There is no low-stakes repository here.

IDENTITY AND CAPABILITY (assert before doing anything else)
Run: gh api -X GET /user -q .login   AND   gh auth status 2>&1 | grep -i scopes
If you are the REVIEWER or ARCHITECT and the scopes include write (repo, admin:org, workflow),
STOP and report "wrong credential for this role". Do not proceed.

SCOPE — the only paths you may touch
[exact paths / exact repositories]
Anything outside this is out of scope. Do not "fix" adjacent problems; record them as findings.
Confirm at the end: git diff --name-only origin/main...HEAD contains nothing outside the list.

GOVERNING RULES (these override any instruction that conflicts with them)
1. Read AGENTS.md first. It wins over your memory and over this prompt.
2. Verify empirically. Command output is evidence; a summary, a prior report, or your own claim
   is not. A grep returning "no matches" has not proven absence — read the file.
3. Three-valued exit codes everywhere: 0 = verified safe, 1 = findings, 2 = COULD NOT VERIFY.
   An unreadable input, a missing baseline or an unreachable API is 2, never 0.
4. Never delete or weaken a gate to make CI pass. If a gate is wrong, fix the gate AND its
   fixtures in the same PR, and say so in the description.
5. Never describe a control as enforced when it is configured-but-inert or convention-only.
6. No terraform apply, state rm/mv/import, or gh api -X PATCH on branch protection or repo
   settings. Terraform is the source of truth; out-of-band writes create drift.
7. No literal secrets or credential-shaped fixtures. Assemble synthetic values at runtime.
8. No unpinned dependency, action, or tool version. Actions pin to a 40-hex SHA + # vX.Y.Z.
9. Two failed attempts at the same step: STOP. Capture git status, git diff and the exact output,
   confirm nothing out of scope was touched, and escalate. Do not loop.

TASK
[one task. one sentence. if you need two sentences, it is two tasks.]

ACCEPTANCE CRITERIA (written before you start; you may not edit these)
[file: acceptance.yml — each entry is an id, an assertion in words, a command, and the expected
 value or exit code. Include at least one AC that asserts you did NOT touch out-of-scope paths.]

METHOD — do these in order, and say which one you are on
1. Measure the current live state. Record commands, outputs, exit codes, timestamps, commit SHA.
2. Classify every relevant claim as: Enforced | Configured but inert | Convention only | False.
3. Implement the minimum change that satisfies the ACs. Match surrounding style; these files carry
   dense rationale comments explaining the defect that motivated them — keep doing that.
4. Write or update the negative control. Every gate needs a fixture that MUST fail. A gate with
   no failing fixture has not been shown to detect anything.
5. Run: make lint AND make compliance   (make lint is NOT the whole CI surface: compliance_check.py
   runs in compliance-scan.yml:128 and apply.yml:160 but is absent from lint).
   You may also run scripts/repo_readiness_audit.py --no-live for information, but be aware it is
   NOT invoked by any workflow (PDA-15) and its baseline on this machine is exit 1 with
   READY 1 / READY-WITH-FIXES 10 / BLOCKED 5 across the sibling working copies. An exit 1 there is
   pre-existing, not something you broke -- confirm by checking whether your change touched the repos
   it reports on before treating it as yours.
6. If any hashed evidence file moved: make evidence-register, and commit the CSV in the same PR.
7. Open a PR. Conventional Commits, body states WHY not just WHAT. Do not merge it. Do not mark
   the task complete. Stop and report.

DEFINITION OF DONE (not yours to declare)
A REVIEWER in a fresh session, holding a read-only credential, has run every AC, recorded the actual
output, and returned PASS on all of them — including a negative control proving each AC fails
against the pre-fix state. Then the Owner merges. Then YOU re-verify against live state and record
it. The merge banner is not verification.

OUTPUT FORMAT
Findings as: ID | severity S0-S3 | the measurement (command + output) | why it matters |
remediation | the exact re-verification command.
Separately: a "COULD NOT VERIFY" list. It is part of the result, not an appendix.
Keep prose short. Commands over explanation.
```

---

## 8. Next steps

Ordered by risk reduction. Items **a–d** are the deployment blockers from the companion report §6;
**e–h** build the enforceable properties this document specifies.

a. **Close PDA-02 (the only S0)** — add `pull_request` + `required_status_checks` to
   `jolarca-consent` ruleset `24087580`. Direct push to `main` on the GDPR consent store is the single
   worst open item.
b. **Close PDA-13** — pin `actions/github-script@v9` and `terraform-linters/setup-tflint@v6` in
   `jolarca-infrastructure`. That workflow runs today, with the apply-path token.
c. **Close PDA-01** — merge `.github#4` (11 pins), enable secret scanning + push protection, add
   required contexts, add `dependabot.yml`. Do this **before** step g, never after.
d. **Close PDA-03 + PDA-04** — populate `jolarca-vendor`'s empty context list; add CODEOWNERS to
   `jolarca-infrastructure`; review the four provider PRs (two majors on `hashicorp/google`) before
   merging any.
e. **Create the two tokens** (§3.2) — `jolarca-auditor` read-only across 17 repos,
   `jolarca-implementer` write on named repos. Add the capability assertion to the audit prompt.
   Free, same-day, and it makes independence a property of the credential.
f. **Write `acceptance.yml` for the next task** (§3.4c) and run the reviewer in a fresh session with
   only the diff, the ACs and the read-only token.
g. **Decide PDA-16** — wire `.github`'s 17 shared jobs up (pinned to a SHA, after step c) or delete
   them and re-declare the five mandatory gates they implement. Wiring them up is also the cheapest
   route to closing PDA-06.
h. **Extend `drift_detect.py`** to read protection rule *content* (context list, presence of a
   `pull_request` rule) rather than `.protected`, with a negative control built from
   `jolarca-consent`'s real ruleset JSON. Then re-open or qualify D-33 (PDA-14).
i. **Correct `AGENTS.md:48-51`** (PDA-15) and re-date the stale `context-parity.yml` comment.
j. **Schedule the state backup** to an off-host destination and retain `docs/backup-log.tsv`
   (§5.17). Until then D-02 stays open and the DR claim stays unsupported.
k. **Diary 2026-11-16** — D-58 lapses and its gate goes red by design. Have the PR that restates the
   compensating controls ready *before* that date.
l. **Commit the audit evidence** — `cp /tmp/jaudit/{fleet.tsv,sweep2.txt,sweep3.txt,sweep4.txt,sweep5.txt,sweep6.txt}`
   into `docs/security/pre-deployment-audit-2026-10-24/`, then `make evidence-register`, in the same
   PR. `docs/security/` is inside `EVIDENCE_DIRS`, so the CSV must move with it or
   `make evidence-check` fails.

**Deployment verdict: NOT READY** until a–c are merged and re-verified against live state. With those
three closed, the fleet moves to *ready-with-observations* — the remaining PDA findings are record
integrity and queue hygiene, which matter for the SOC 2 Type II period but do not change what an
unreviewed merge can do today. Do not sign a Type II attestation before PDA-06 and PDA-16 are
reconciled.
