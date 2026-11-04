# QODER.md — how an agent behaves in `jolarca-control`

The behavioural layer for AI agents working in this repository through Qoder. It carries four
principles, each bound to a gate, a file or a recorded failure that already exists here, so that
"be careful" is something an agent can execute rather than something it can agree with.

**Precedence.** `AGENTS.md` is the versioned source of truth for how changes are made in this
repository. It wins over this file, over agent memory and over any prior conversation. Where the
two overlap, `AGENTS.md` is normative and this file is explanatory. Nothing here relaxes a hard
boundary in `AGENTS.md` §5, and nothing here records an approval — approval lives in a dated entry
in `policy/compliance-gates.yml` `exceptions.active` or it does not exist.

**Provenance.** The four principles are derived from Andrej Karpathy's published observations on
how LLM coding agents fail — assuming on the user's behalf without checking, overcomplicating until
1000 lines do what 100 would, and changing code and comments they do not sufficiently understand —
in the formulation circulated as the `andrej-karpathy-skills` guideline set. The bindings to this
repository are original, and were measured against the tree rather than recalled.

| Principle | Failure it addresses | Where this repository already pays for it |
|---|---|---|
| 1. Think Before Coding | wrong assumptions, hidden confusion, unstated tradeoffs | `AGENTS.md` §4 blast-radius routing, §8 controls not enforced |
| 2. Simplicity First | bloat, speculative abstraction, unpinned additions | §5 pinning rule, `scripts/check_gate_parity.py` |
| 3. Surgical Changes | orthogonal edits, deleted rationale, cosmetic churn | §6 rationale-comment rule, evidence + changelog companions |
| 4. Goal-Driven Execution | unverified claims of success | §3 exit codes, §7 verify-the-verifier |

**Tradeoff.** These principles bias toward caution over speed. For a typo in prose, use judgement.
The purpose is to stop costly mistakes on high-blast-radius work, not to make every one-line change
into a project.

---

## 0. Three facts to load before the first edit

1. **This is a control plane, not an application.** A three-line diff to `repos/*.yml`, `policy/**`,
   `*.tf` or `.github/workflows/**` can change visibility, branch protection or secret scanning on
   repositories inside PCI-DSS and GDPR scope. Route on blast radius, never on diff size (§4).
2. **A merge to `main` can arm a real production apply.** `apply.yml` fires on `push: main` for the
   paths in its own `on.push.paths` and then runs `terraform apply -input=false -auto-approve`.
   Read that block, or run `make apply-path-trigger`, before asserting that an edit is inert.
3. **Most prose you will be tempted to tidy is evidence.** Comments in `scripts/`, `tests/`,
   `Makefile` and `AGENTS.md` carry dated measurements and the defect that motivated the code.
   They are load-bearing (§6).

Session start, in this order:

```
git status --short && git branch --show-current   # the tree may hold work that is not yours
make help                                          # the command surface, from the file that runs it
```

Then read `AGENTS.md` §8 — the controls that are **not** enforced. Assuming protection that does
not exist is the precise mistake that section was written to prevent. Read the section of
`AGENTS.md` that governs the file you are about to touch; it is long, and loading all of it to
change one YAML key is context flooding, not diligence.

---

## 1. Think Before Coding

Don't assume. Don't hide confusion. Surface tradeoffs.

- State assumptions explicitly. If uncertain, ask.
- If more than one reading exists, present them — do not pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what is unclear. Ask.

What that means here:

**a. Classify the change before opening the file.** High blast radius, regardless of size: `*.tf`,
`*.tfvars`, `repos/**`, `policy/**`, `.github/workflows/**`, `scripts/**`,
`docs/evidence-registry.csv`. Lower: `docs/**` prose, `staging/**`, `audit/**` checklists. State
the class in the PR description — it tells the operator how hard to read the plan.

**b. When the answer is live state, read it; do not infer it.** Whether a repository is protected
by legacy branch protection or by a ruleset, whether a required context is passing, whether an
organisation variable is set — these are `gh api` reads. §7 records a governed claim about a
provider freeze that was true only inside one workstation's working tree while `origin/main` still
carried the unfrozen configuration. "Is it so on `origin/main`?" is not a rhetorical question.

**c. Stop-and-ask triggers.** Present the tradeoff and wait for a human decision if the request
would:

- flip `visibility` in any `repos/*.yml`;
- weaken `enable_branch_protection`, a required-context list, `strict`, linear history, or any
  ruleset enforcement;
- disable a security feature — secret scanning, push protection, SAST, dependency review;
- delete or weaken a gate so that CI goes green (§5 forbids this outright: fix the gate and its
  fixtures in the same PR and say so in the description);
- run `terraform apply`, `terraform state rm`, `state mv` or `import`;
- add a required status context. Emission is not satisfiability: a context that the repository
  cannot currently pass makes every PR unmergeable, including the PRs that would fix it. Require
  observed successes on the default branch first.

**d. Surface confusion in a fixed shape**, so it is cheap to answer:

```
UNCLEAR:   <the exact thing, with the file that makes it ambiguous>
READING A: <interpretation> → consequence
READING B: <interpretation> → consequence
SETTLES IT: <the read-only command whose output decides>
→ which reading, or shall I run the command?
```

An agent that names its confusion costs one round trip. An agent that guesses silently costs a
revert, a finding, and a paragraph of dated evidence explaining why the revert happened.

---

## 2. Simplicity First

Minimum code that solves the problem. Nothing speculative.

- No features beyond what was asked.
- No abstraction for single-use code.
- No "flexibility" or "configurability" nobody requested.
- No error handling for impossible states.
- If 200 lines could be 50, rewrite it.
- Test: would a senior engineer call this overcomplicated? If yes, simplify.

What that means here:

**a. Find the gate that already exists before writing one.** `scripts/` holds the gates and
`.github/workflows/` holds the pipelines; `make help` lists the invocations. A second gate that
overlaps a first is worse than either alone, because the two drift apart and only one gets fixed —
§2 records that this repository already has three overlapping check surfaces and enforces the
parity of none of them.

**b. A new gate is never one file.** `scripts/check_gate_parity.py` runs inside a required context
and enforces, among others: **R1** a new `scripts/<name>.{py,sh}` without `tests/test_<name>` fails
the PR; **R1b** the fixture must name its subject; **R2** every `tests/*.sh` must be invoked by a
`run:` step in a workflow that can trigger on `pull_request`, because `pytest tests/` collects `.py`
and cannot collect `.sh`; **R3** every script must be invoked by something executable, with comments
stripped — prose is not an invocation; **R4** the no-fixture baseline may only shrink. Extending an
existing gate is therefore usually cheaper *and* smaller than adding one.

**c. An unpinned addition is refused, and pinning is a project.** Dependencies pin in
`requirements*.txt`; GitHub Actions pin to a full commit SHA with a `# vX.Y.Z` comment; ruff's rule
set pins in `pyproject.toml` because its defaults move between releases; and the approved toolchain
is catalogued in `docs/security/toolchain-catalogue.yml`, which `scripts/check_toolchain_baseline.py`
diffs the fleet against. Propose reuse first. If an addition is genuinely needed, state its pinning
cost in the same breath as the proposal.

**d. Prefer a step inside an existing required job over a new required context.** A new context adds
a way for the merge path to wedge; a step inside a job that already reports adds a check with no new
failure surface.

**e. Do not simplify prose to silence a linter.** yamllint's line length is 160 at **warning** level
and prose-heavy compliance YAML is expected to warn (§6). Reflowing it to make a warning disappear
destroys rationale and produces a diff no reviewer can read. The same applies to the dense comments
in `scripts/` and `tests/`: their length is the artefact.

---

## 3. Surgical Changes

Touch only what you must. Clean up only your own mess.

- Don't "improve" adjacent code, comments or formatting.
- Don't refactor what isn't broken.
- Match existing style, even where you would have written it differently.
- Unrelated dead code: mention it, don't delete it.
- Imports, variables and functions that **your** change orphaned: remove them.
- Test: every changed line traces directly to the request.

What that means here:

**a. Rationale comments are this repository's memory, not noise.** These files carry dense comments
explaining the defect that motivated them, deliberately (§6). Never delete, reword, re-wrap or
modernise a comment you have not fully understood — several are the only surviving evidence that a
control exists, and one recorded a measurement that a passing gate could not. If a comment looks
wrong, that is a finding to report in the PR description, not a line to fix.

**b. Two companion edits are mandatory and in scope, not drive-by.**

- **Evidence.** Edit anything under `docs/adr/`, `audit/`, `policy/`, `repos/`, `docs/runbooks/` or
  `docs/security/` and re-run `make evidence-register` in the same PR, or `make evidence-check`
  fails. Those directories are `EVIDENCE_DIRS` in `scripts/hash_evidence.sh`; repository-root files,
  including this one, are outside them and need no registration.
- **Changelog.** Add the entry under the single `## [Unreleased]` anchor in `CHANGELOG.md`. It is
  part of the SOC 2 CC8.1 / ISO 27001 A.8.32 audit trail and is not optional. `CHANGELOG.md` uses a
  union merge driver, which can silently produce **two** anchors when two branches touch the same
  line; `tests/test_changelog_anchor.py` turns that red. Never resolve a changelog conflict by
  keeping both headings.

**c. Location is a design decision, not a detail.** The same sentence at the repository root is
inert: it matches no `apply.yml` trigger path and no evidence directory. Placed under `policy/` it
arms a production apply on merge and is hashed as evidence. Choose deliberately and say why in the
PR description.

**d. Don't reformat.** `ruff format` applies to `scripts/` and `tests/`; `terraform fmt` applies to
`.tf`. Markdown and YAML have no formatter here, so whitespace churn in them is hand-made, and
hand-made churn is the part of a diff a reviewer cannot skim past safely.

**e. Don't touch GitHub settings out of band.** No `gh api -X PATCH` for branch protection or
repository settings (§5). Terraform is the source of truth; an out-of-band PATCH is silently
reverted by the next apply and leaves drift that reads as a mystery.

**f. Leave the working tree as you found it.** If `git status` showed unrelated modifications when
you arrived, they are not yours to commit, stash, revert or "finish". Stage your own paths
explicitly; never `git add -A` in a tree you did not empty.

**g. Conventions that look like style but are contract (§6).** English comments and documentation.
Conventional Commits with a body that states *why*. Squash-merge, keep history linear, delete the
branch. Commit authorship uses the GitHub noreply form, because commit metadata on a public
repository is permanent publication. Published contact addresses come from
`policy/contact-addresses.yml` and must have been delivery-tested — the fleet once shipped a
disclosure mailbox whose domain had no MX record. No literal secrets and no credential-shaped
fixtures, even synthetic-looking ones: push protection scans documentation, and a real-looking
fixture can permanently block a repository's readiness gate.

---

## 4. Goal-Driven Execution

Define success criteria. Loop until verified.

| Instead of | Transform to |
|---|---|
| "Add validation" | write tests for the invalid inputs, then make them pass |
| "Fix the bug" | write a test that reproduces it, then make it pass |
| "Refactor X" | prove the tests pass before and after |
| "Harden the gate" | feed it one synthetic line of the shape it must catch, and show it refuses |

For multi-step work, state the plan with its checks before executing:

```
1. <step> → verify: <command> → expect: <output or exit code>
2. <step> → verify: <command> → expect: <output or exit code>
3. <step> → verify: <command> → expect: <output or exit code>
```

Strong criteria let an agent loop independently. Weak criteria ("make it work") guarantee a round
trip after every step. In this repository the principle is not aspiritional — §7 makes it mandatory.

**a. Success criteria are command output, not a sentence.** A tool's summary, a prior report, or an
agent's own claim that a file was updated is not evidence (§1). Neither is a search result: a grep
that returns no matches, or a truncated result set, has not proven absence — read the file.

**b. Prove a gate can fail before trusting it green.** A gate that runs and reports green has not
been shown to detect anything. Every gate needs a negative control, and the convention here is
*proven red before green*: revert the fix, record the fixtures that fail, restore, record the count
that passes. `tests/test_check_plan_safety.sh` is the model. §7 also asks the sharper question —
which object classes is this pattern-matched gate structurally incapable of naming? Feeding it one
synthetic line of that shape is how an inert regex and a missing resource class were both found.

**c. Read exit codes correctly.** `0` verified safe, `1` findings, `2` **could not verify** — and
`2` is never a silent pass. The three-valued code lives on the script, never on `make`: GNU make
returns `2` for any failed recipe, so a target cannot distinguish "findings" from "could not
verify". Any judgement that turns on that distinction calls `.venv/bin/python scripts/<gate>` or
`bash scripts/<gate>` directly and reads that code.

**d. Capture `rc=$?` on the line immediately after the command.** Bash expands command
substitutions before the surrounding command runs, so a `printf` whose arguments contain `$(…)`
reports the substitution's status, not the gate's. A sweep written that way once printed every gate
green while an evidence-integrity check was exiting 1 (§7). The harness was the liar, not the gate.

**e. Run Python through the venv:** `.venv/bin/python -m pytest tests/ -q`. The system
`python3 -m pytest` can exit 1 with no output, which reads as a mystery failure.

**f. Check all three surfaces before pushing (§2).** `make lint`, the installed pre-commit hooks,
and the CI jobs overlap and nothing enforces their parity. Concretely: `make lint` does **not** run
`scripts/compliance_check.py`, and CI does — so run `make compliance` too, or CI will surface a
failure no local gate checked. With hooks installed, `pre-commit run --all-files`; in a fresh CI
clone there are none.

**g. Verify against `origin/main`, not the working tree.** After a merge:
`git show origin/main:<path> | grep -n <marker>` and `git log --all -S '<marker>' | wc -l`. A
document whose evidence line says "working-tree diff" means *not applied*, and §6 forbids
publishing it any other way. Cheaper than either: read a fresh clone before reading a register.

**h. Do not trust a correct verdict.** A gate can report the right aggregate answer while silently
skipping whole check families — an early `return` on a missing `.git` once skipped six filesystem
checks and an entire secret sweep. Cross-check finding counts against an independent run.

---

## Definition of done

1. **Scope stated.** Blast-radius class, files touched, and why each one is in the diff.
2. **Local gates green, with their exit codes read.** `make lint`, `make compliance`, and
   `pre-commit run --all-files` where hooks are installed.
3. **New or changed gate carries a fixture that can fail**, proven red before green, invoked by
   something executable rather than described in prose.
4. **Companion edits landed.** Evidence re-registered if a hashed directory was touched; changelog
   entry under the single `## [Unreleased]` anchor.
5. **Nothing unrelated in the diff.** Every changed line traces to the request; no rewrapped
   comments, no reformatting, no drive-by refactors.
6. **Claims verified against live state or `origin/main`**, with the command and its output quoted
   in the PR description rather than summarised.
7. **No boundary crossed.** No weakened gate, no unpinned addition, no out-of-band settings change,
   no apply or state surgery, no secret-shaped fixture (§5).

## How to know it is working

- Fewer unnecessary lines in diffs — only requested changes appear.
- Clarifying questions arrive **before** implementation, not after a mistake.
- No drive-by refactoring, no reworded rationale, no whitespace churn.
- Every "done" is backed by a command and its output, and the exit code was read on the line after.
- PRs stay small enough that the operator can read every line — which is the only review this
  repository gets, since `required_approving_review_count` is 0 (§8).

## What this file is not

- **Not a second source of truth.** If this file and `AGENTS.md` disagree, `AGENTS.md` wins and this
  file has a defect — fix it in the same PR that exposed the disagreement.
- **Not a copy of volatile facts.** The required-context list, the backup schedule, the status of
  any finding and the set of enforced controls all change and all live somewhere that is read
  mechanically. Point at them:

  | Question | Read it here |
  |---|---|
  | Which controls are *not* enforced | `AGENTS.md` §8 |
  | Approvals and dated exceptions | `policy/compliance-gates.yml` |
  | Open findings and their status | `docs/drift-findings.md` |
  | Declared required status checks | `policy/repo-defaults.yml` |
  | State-backup schedule | `systemd/jolarca-state-backup.timer`, via `make backup-timer-status` |
  | Approved toolchain | `docs/security/toolchain-catalogue.yml` |
  | Command surface | `make help` |

  A sentence that carries a schedule has gone stale five times in `AGENTS.md` chasing one value.
  That history is the entire argument for pointing instead of describing.

- **Not a place to record a fix.** A fix that exists only in a working tree is not a fix; §7 has the
  measurement that proved it.
