# ADR-0010: Per-Repository Toolchain Configuration (mise)

**Date:** 2026-11-03
**Status:** Accepted
**Deciders:** Gintaras Kazlauskas (organization owner)
**Scope:** all 17 `jolarca-dev` repositories. Seventeen draft PRs were open when
this was published on 2026-11-03; `jolarca-control` PR #121 has since merged as
`42f309a`, leaving sixteen drafts. Front matter is read as current state, not as a
dated claim, so it is amended in place; every narrative sentence below keeps its
timestamp and is answered by the dated Status change, Closure and Landed sections.

---

## Context

`jolarca-dev` has 17 repositories and no single answer to "which version of
Python is approved". The declarations that exist disagree with each other, and
they disagree *inside one repository*. Measured in `jolarca-control` on
2026-11-03 at `8f24aac` (== `origin/main`):

| Tool | Declaration A | Declaration B | Effect |
|---|---|---|---|
| ruff | `.pre-commit-config.yaml:22` `rev: v0.16.9` | `requirements-dev.txt:31` `ruff==0.16.10` | Two ruff versions decide "lint passes", depending on whether the check ran as a hook or in the venv. ruff's default rule set moves between releases, which is the stated reason the file pins at all. |
| mypy | `.pre-commit-config.yaml:30` `rev: v2.3.1` | `requirements-dev.txt:32` `mypy==2.4.0` | Same class of skew on a `--strict` gate. |
| terraform | `plan.yml:61` / `apply.yml:88` `terraform_version: "1.16.1"` | `compliance-scan.yml:295` `hashicorp/setup-terraform` with **no** `terraform_version`, then `terraform fmt -check -recursive` | The required compliance surface format-checks with a floating Terraform while the apply path is pinned. |
| python | `python-version: "3.12"` — 10 occurrences across 6 workflows | nothing | `"3.12"` is a version *request*, not a pin. Each runner image resolves it to whatever patch it happens to carry. |

This is not a style problem. Under SOC 2 CC8.1 and ISO 27001 A.8.32 a change
control record has to name the configuration item it changed. When the same
repository declares one tool at two versions on two surfaces, "the build passed"
does not identify what built it.

`mise` (<https://mise.jdx.dev>) was proposed as the declaration and
verification surface. On 2026-11-03 seventeen draft PRs were opened, one per
repository, each adding exactly four files — `mise.toml`, `mise.lock`,
`MISE-ADOPTION.md` and `.github/workflows/mise-toolchain.yml` — verified by
reading `gh pr view <n> --json files` for all 17, not a sample. `jolarca-consent`
adds a fifth, `CHANGELOG.md`, as that repository requires. `jolarca-control` #121
reports 10/10 checks green including the new `mise toolchain (Linux x64)` job.

The question this ADR answers is the one the rollout did not record: **does
toolchain configuration belong in each repository, or in one central place?**

## Decision

Toolchain configuration is **per repository**. The baseline that governs it is
**central**. The two must not be conflated, and the split is by layer:

| Layer | Scope | Reason |
|---|---|---|
| The `mise` executable | once per workstation and per runner image, one approved version, one recorded digest | It is the trust root. Seventeen installers would be seventeen independent supply-chain decisions with one reviewer. |
| The approved tool catalogue, the exception process, the drift gate | central, owned by `jolarca-control` | One register, one review cadence, one place an auditor is pointed at. |
| `mise.toml`, `mise.lock`, `.miserc.toml` | **per repository, mandatory** | The repository is the review boundary and the independently versioned unit. |
| Package dependencies (`requirements*.txt`, `package-lock.json`, `.terraform.lock.hcl`) | per repository, unchanged | mise manages tool executables. A pinned interpreter does not make an unpinned `pip install` reproducible. |

### Rationale

1. **A central config is not merely unwise, it is mechanically impossible.**
   mise inherits by *filesystem ancestry*, not by organisation membership: it
   loads "config files in every directory from the filesystem root down to the
   current directory" (<https://mise.jdx.dev/configuration.html>, retrieved
   2026-11-03). A hosted runner checks out to
   `/home/runner/work/<repo>/<repo>/`; no sibling repository and no org-level
   parent exists there. There is no directory a central `mise.toml` could live
   in that all 17 CI checkouts would inherit from. `.github` PR #6 accordingly
   gives even the central repository its own local config.

2. **Inheritance is a hazard, so per-repository config is necessary but not
   sufficient.** `[tools]` merges *per tool*: "the nearest file's entry replaces
   that tool's whole entry, including its options. Other tools are inherited."
   One stray `/opt/jolarca/repos/mise.toml` would therefore inject tools into all
   17 checkouts on this workstation and into none in CI — the same commit
   resolving to different toolchains on different machines. That is an
   unrecorded configuration item (ISO 27001 A.8.32) and it defeats the
   reproducibility claim the lockfile exists to make. See M-01.

3. **The repository is already the enforcement boundary.** Branch protection,
   required status checks, CODEOWNERS and Actions allow-lists are per-repository
   objects; no central file can express them. Proven live on 2026-11-03, not taken
   from the rollout report: `GET /repos/jolarca-dev/jolarca-security/actions/permissions`
   returns `allowed_actions: "selected"`, and
   `.../permissions/selected-actions` returns `github_owned_allowed: true`,
   `patterns_allowed: ["DavidAnson/*"]`, `verified_allowed: false`. Third-party
   actions are therefore refused **in that repository only** — the org-level
   `GET /orgs/jolarca-dev/actions/permissions` returns `allowed_actions: "all"`,
   `enabled_repositories: "all"`. The consequence is measured, not inferred: run
   `41654550029`, workflow `mise toolchain`, event `pull_request`, branch
   `codex/mise-adoption-2026-11-03`, concluded **`startup_failure`** — the only
   mise run that repository has, so `gh pr checks 9` lists four passing checks
   and no mise check at all, because a workflow that cannot start emits no check
   run. The fleet result is 16 of 17 green, not 17 of 17. Because the
   configuration is local, that divergence is visible in the one repository that
   owns it; a central configuration would have had nowhere to record it.

4. **Lockfiles are per-config-root by construction.** For a remote `include`,
   "its tools are locked in the *including* file's lockfile". Centralising the
   declaration would therefore not centralise the lock: each repository would
   still carry its own resolved digests, while additionally taking a network
   fetch at config-load time. The coupling cost is paid without the
   reproducibility benefit.

### Rejected alternatives

- **A. One org-level `mise.toml` in `.github`, inherited by the fleet.**
  Rejected — the mechanism does not exist (Rationale 1). It would appear to work
  on a workstation where all 17 are siblings and would silently not apply in CI.
- **B. Remote `include` of a central baseline.** Rejected. Supported as
  `git::https://…//mise.toml?ref=<40-or-64-hex>` or `oci://…@sha256:<64-hex>`,
  but under paranoid mode "a branch, a tag or a missing ref fails to load", and
  the tools land in the including repository's lockfile regardless (Rationale 4).
  A mutable `?ref=main` include makes identical repository commits behave
  differently over time — the exact property a lockfile is supposed to remove.
  The catalogue stays central as **reviewed data**, materialised into each
  repository by a generator, so the diff is reviewable in the PR that changes it.
- **C. Parent-directory config above the checkout tree.** Rejected —
  Rationale 2. It is machine-local, unversioned and invisible to review.

### Constraints and compensating controls

Findings are numbered `M-nn` in this ADR. They are recorded here rather than
appended to the `docs/drift-findings.md` D-series because they arise from an
assessment of an unmerged proposal, not from measured drift in live state; each
should be promoted into the D-series if and when it is accepted for remediation.

- **M-01 — config discovery was unbounded in all 17 drafts.** No `.miserc.toml`
  was present in any of them (all 17 file lists read, 2026-11-03). This matters
  because `ceiling_paths` set under `[settings]` in `mise.toml` "has no effect on
  config discovery": mise reads `.miserc.toml` *before* any `mise.toml`. It is
  also the one config file that loads without trust, precisely because "it can
  only choose which config files load". _(Amended the same day — the control was
  built and measured on twelve repositories' draft branches, and the wording this
  bullet first used, "bounding the search at the repository root", was wrong: a
  ceiling directory is not searched itself, so a ceiling naming the root stops mise
  loading the root's own `mise.toml`. Read the second Amendment section before
  acting on this bullet.)_ *Control:* a committed `.miserc.toml` whose
  `ceiling_paths` names the **parent** of the repository root, or
  `MISE_CEILING_PATHS` set in the workflow. _(Further amended the same day: this is
  now on `jolarca-control`'s default branch as of `42f309a`, and on none of the
  other sixteen.)_
- **M-02 — `--locked` binds the CI job, not the repository.** The workflows pass
  `install_args: --locked`, so a developer running plain `mise install` resolves
  unlocked against whatever the lockfile does not constrain. *Control to add:*
  `[tool_config] locked = true` in each `mise.toml`, which "requires this config
  root's tools to resolve and install from their lockfiles" and travels with the
  repository instead of with the invocation. Its documented limit — it "does not
  affect tools inherited from global, system, or parent config roots" — is why
  M-02 must ship together with M-01. _(Amended the same day: measured on twelve
  repositories' draft branches, one of which tests shellcheck rather than python,
  so the bound is not python-specific. On no default branch yet.)_ _(Further
  amended: enforced on this repository's default branch as of `42f309a`; the other
  sixteen remain without it.)_
- **M-03 — provenance strength is asymmetric inside one lockfile.** In
  `jolarca-control`'s `mise.lock`, python (`backend = "core:python"`) carries
  `provenance = "github-attestations"`, while terraform
  (`backend = "aqua:hashicorp/terraform"`) carries a checksum and a URL only.
  A checksum fetched from the same origin as the artifact is integrity, not
  publisher identity. *Control to add:* enable paranoid mode's `provenance`
  category on workstations, which re-runs the backend's SLSA / Cosign /
  attestation checks on every install and fails where the registry says
  attestations must exist. Whether the aqua terraform recipe declares them is
  **not verified here** and must be checked before the control is claimed.
- **M-04 — the strongest controls cannot be enforced per repository at all.**
  The `paranoid` setting "is global-only, so a project cannot change it". A
  repository cannot opt itself into content-bound trust, plugin refusal or
  provenance re-verification. *Consequence:* part of the baseline is unavoidably
  a **machine** baseline — documented, and verified per workstation and per
  runner image. Any claim that the fleet's mise configuration is hardened is
  false while that machine baseline is unrecorded.
- **M-05 — one platform is locked.** Every lockfile supplies `platforms.linux-x64`
  only. A Linux x64 artifact is not usable on an Apple Silicon laptop, and a
  developer on any other platform installs unlocked. *Control:* generate and
  clean-install-test the additional platform entry before support is claimed for
  it; do not describe the fleet as locked while one platform is.
- **M-06 — no central drift gate yet.** Per-repository lockfiles make one Python
  CVE 17 separate PRs, and make divergence possible by omission. *Control to
  add:* a fleet check comparing each repository's locked versions against the
  approved catalogue, following the existing `scripts/drift_detect.py` and
  `make fleet-audit` pattern. Without it the central catalogue is documentation,
  not a control. _(Amended the same day: `docs/security/toolchain-catalogue.yml`
  and `scripts/check_toolchain_baseline.py` now exist, so the finding is
  half-closed — the catalogue and its offline validation are wired into the required
  job, and the fleet comparison runs through `make toolchain-baseline` but is
  deliberately not a required context because it cannot go green today. It is
  renumbered below rather than deleted, because "the gate exists" and "the gate is
  enforced" are different claims.)_
- **M-07 — the platform does not enforce the action pin, and the remedy first
  written here was wrong.** Both the org and `jolarca-security` return
  `sha_pinning_required: false` (measured 2026-11-03), so GitHub itself accepts a
  tag or a branch ref anywhere in the fleet. _(Amended the same day — the two
  claims that followed were inaccurate: an offline guard that does refuse a tag
  ref already exists in this repository and is already enforced on the merge
  path, and the `sha_pinning_required` PATCH is refused by the API. Read the
  Amendment section at the end of this file before acting on this bullet.)_ What
  survives is narrower: the **platform** enforces nothing, and the 16 sibling
  repositories carry no equivalent of this repository's guard, so the 17 new mise
  smoke workflows land on the fleet with pin review enforced in one repository out
  of seventeen. The unbuilt residual — live tag resolution, the one thing the
  offline guard structurally cannot catch — is already registered as **D-51**.
  This is a pre-existing gap, not one mise introduces; mise adoption inherits it.
- **M-08 — a shared artifact is judged by each repository's own lint limit.**
  Propagating one guard file broke `ci` in exactly two repositories and nowhere
  else, and the reason is in the files rather than the code: `jolarca-data` and
  `jolarca-legal` run `yamllint` with `line-length: {max: 140}`, while this
  repository's `.yamllint` allows 160. A 141-character line passed locally and
  failed there. Attributed to my own commit by an A/B on the same workflow —
  `jolarca-legal` `ci` was success at `61102be5` and failure at `c13a8c4f`, with
  only my push between — not assumed from its merely being red. *Control:* write
  anything intended to cross repositories to the **strictest limit in the fleet**
  and lint it locally at that limit before pushing, not at the local one. This is
  Rationale 3 arriving as a defect: centralising a file does not centralise the
  rules that judge it.
- **M-09 — an exception that names no rules pardons all of them.** Found while
  building the M-06 gate, and the gate caught it in its own first draft. The
  catalogue's `jolarca-security` entry explained why the CI **proof** cannot run
  there, and the implementation keyed suppression on repository name alone — so it
  also silenced L1, "this repository is not adopted", which is a different gap the
  recorded reason does not cover. The first live run reported **15 findings where
  the true count was 16**, and the missing one was exactly that repository. The
  hand-built probe that motivated the gate had counted correctly, so the new tool
  was about to disagree with the evidence that justified it. *Control:* `covers` is
  now a required field on every exception and names the rule ids it excuses; an
  exception without it is a C6 finding, and an exception that does not list a rule
  cannot silence it. Proven by
  `tests/test_check_toolchain_baseline.py::test_an_exception_does_not_silence_a_rule_it_does_not_cover`.
  Same shape as the gate-parity lesson in AGENTS.md §7 — "an exception that also
  silences a second rule is an off switch" — arriving a third time, inside a gate
  written to detect drift in the others.
- **M-10 — the gate cannot see the interpreter the required checks actually run
  on.** `docs/security/toolchain-catalogue.yml` approves python `3.12.16` and
  `scripts/check_toolchain_baseline.py` validates that approval — but it reads
  `mise.toml`, and `grep -c 'python-version'` inside the gate returns **0**. Ten
  `python-version:` declarations across six workflows on `main` (`apply.yml` 1,
  `compliance-scan.yml` 4, `context-parity.yml` 1, `deploy-gates.yml` 1, `plan.yml` 1,
  `sast.yml` 2) all request `"3.12"`, which is a prefix and not a release.
  The consequence was measured as an A/B rather than argued: run `41690569251` job
  `126107728895`, on PR head `2d6c049`, reported
  `pythonLocation: /opt/hostedtoolcache/Python/3.12.15/x64`; run `41693066694` job
  `126116360439`, on `main` at `5a7237c` an hour later, reported
  `…/Python/3.12.16/x64`. **No file in this repository changed between them** — the
  declarations sit at identical line numbers (77, 212, 245, 294) in both commits and
  `actions/setup-python` appears four times in each. The required checks' green
  verdict is therefore produced by an interpreter announced nowhere and attested by
  nothing, and its current agreement with the catalogue is coincidence.
  *Why this is a compliance finding and not a cosmetic one:* SOC 2 CC7.1 and ISO
  27001 A.8.19 ask which version was in force when a control produced its evidence.
  "Whatever the runner image happened to ship" cannot answer that. This is the same
  defect ADR-0010 §Context measured to justify the whole exercise, still live in
  this repository, and invisible to the gate built to detect it.
  *Two ways to close it, different blast radius:* **(a)** extend the gate to read
  `python-version:` from every workflow and require the approved release — offline,
  deterministic, no protection mutation, but it will fail on first run, so it must
  land together with the ten declarations it turns into pins, in one PR; **(b)**
  make the workflows consume mise, which is the workflow migration the next section
  defers to its own ADR. (a) is the next step. _(Closed the same day by route (a)
  for nine of the ten declarations, plus the Terraform format skew; `apply.yml` is
  the deliberate exception, recorded below.)_

### What this decision does not do

It does not make `mise` a task runner, a CI entry point or a secrets store; the
existing `Makefile`, workflows and required status checks stay authoritative and
unchanged. It does not certify any version as vulnerability-free. It does not
make the new smoke workflow a required branch-protection check — that needs
observed successes on the default branch first, because a required context that
cannot go green wedges every PR in the repository, including the ones that would
fix it. And it does not unify application and deployment workflows onto mise;
those still select their tools independently and migrate only in a later,
separately reviewed change.

### Residual risks

- **Seventeen lockfiles, one reviewer.** Accepted with M-06 as the compensating
  control. `required_approving_review_count` is 0 on this repository (D-04), so
  the review is self-review; that is recorded, not disguised as independent
  two-person approval.
- **Third-party action in the trust path.** `jdx/mise-action` is pinned to a full
  commit SHA and the extracted binary to a SHA-256, which is three distinct pins
  (action, mise version, binary digest). It remains third-party code executing on
  the runner. Compensating controls in the smoke workflow: `permissions:
  contents: read`, hosted `ubuntu-24.04`, `persist-credentials: false`, no
  secrets, no deployment access.
- **Runtime selections are new patch versions.** Python 3.12.16 and Node 22.23.4
  were resolved from official release indexes on 2026-11-03. They preserve the
  observed major/minor families but are not proven compatible; repositories
  relying on runner-provided runtimes need compatibility review before merge.
  Terraform selections were deliberately left at each repository's existing value
  (1.16.1 here, 1.9.8 in infrastructure) so a toolchain adoption is not silently
  combined with a state/provider compatibility change.

## Consequences

- **Positive:** each repository's tool selection is reviewable in the same PR
  that changes it, under that repository's own protection and ownership rules.
  Identical commits resolve identically on any machine that has no stray parent
  config — and once M-01 is closed, on any machine at all. Divergence such as
  `jolarca-security`'s allow-list refusal becomes visible in the repository that
  owns it.
- **Negative:** seventeen lockfiles to update for one upstream fix, and a real
  risk of skew by omission. Both are M-06's job.
- **Neutral:** the ruff/mypy/terraform/python skews measured in Context are
  **not** fixed by this decision. mise adds a fourth declaration surface; it
  removes the older three only when the workflows are migrated to read from it,
  which is a later change. Until then the skew persists and should be closed on
  its own merits.

## Review

Revisit this ADR:

- when the M-01 and M-02 branches merge, to move them from findings to controls on
  the default branch — until then they are proven only in CI on open draft
  branches, and every default branch in the fleet is still unbounded;
- when the four repositories whose drafts were already blocked by unrelated failing
  checks receive the same two files (M-01, M-02) and the lint discipline (M-08);
- when a second platform's lock entries exist (M-05);
- when the machine baseline for M-04 is recorded;
- when `apply.yml`'s own `python-version` is pinned in the deploy decision that
  removes its `workflow_exceptions` entry — until then R8 is excused on exactly one
  file, and the exception expires 2027-05-03;
- when M-10 is closed — until then the catalogue's approved python is connected to
  nothing that executes, and the required checks' interpreter is chosen by a runner
  image that changes on its own schedule;
- before any workflow migration that makes `mise` the CI entry point — that
  change needs its own ADR, because it converts a declaration surface into an
  execution surface;
- if a self-hosted runner is ever introduced. A hosted runner cannot see
  `/etc/mise` or `~/.config/mise`; a self-hosted one can, and inheritance then
  becomes an attacker-reachable input on every PR from a fork.

---

## Amendment — 2026-11-03 (M-07): the finding overstated the gap and its remedy is refused

M-07 was published in `b3fba1b` claiming that "nothing on the platform refuses a
 tag or a branch ref, **here** or in the other 16 repositories", and prescribing
`sha_pinning_required: true` as the cheap fix. Both halves failed on contact with
the artifacts. Recorded here rather than silently rewritten, because a corrected
record has to show what was wrong.

**The guard already exists, and it is already enforced.**
`tests/test_action_pin_labels.py` (125 lines) asserts over every `.github/workflows/*.yml`:
that each `uses:` ref is a 40-hex full SHA, that one `(action, commit)` never
carries two different labels across workflows, and that one `(action, label)`
never points at two commits. Run today: `4 passed in 0.07s`. It reaches the merge
path because `compliance-scan.yml:269` runs `python -m pytest tests/ -q` inside
the required `Validate Repo Allow-List` job — the context list M-07 was written
to complain about. So "here" was false: in this repository a tag ref does fail a
required check. The word that should have carried the claim is **platform**, alone.

**The residual is already registered, with a date and a status.** That test's own
docstring limits it: it "cannot catch a label that is wrong in *every* file
consistently — that needs live tag resolution". `docs/drift-findings.md:776`
records exactly that as **D-51**, from the real defect it was built for
(`actions/checkout` pinned to v5.0.0 under a `# v4.3.0` comment, the false label
then carried onto v7.0.1 by a bump), and its heading states the current position:
"labels fixed in #34 (pending merge); offline detection added here; **live
resolution still unbuilt**". A fleet-wide pin scan across the 16 allow-listed
repos plus `.github` was also already performed on 2026-10-04 and is registered as
D-43. M-07 re-derived a known gap and cited neither entry, which is the failure
mode AGENTS.md §7 exists to catch — and caught here only because the user acted on
the prescription before I had tested it.

**The prescribed remedy is refused by the API, and would have been wrong anyway.**
Measured when `gh api -X PATCH orgs/jolarca-dev/actions/permissions -f
allowed_actions=all -f sha_pinning_required=true` was run against live state:
HTTP **404**. Re-read after the failure confirms **nothing was mutated** —
`{"enabled_repositories":"all","allowed_actions":"all","sha_pinning_required":false}`,
byte-identical to the pre-change GET. The cause is not established by these two
requests and must not be asserted: a Free-plan capability gate is the likely
reading, consistent with this repository's measured history that
`orgs/jolarca-dev/audit-log` likewise returns 404 on the same plan, but a
plan-tier conclusion needs evidence this probe does not carry.

It should not have been recommended regardless of the outcome, for a reason
stronger than the API refusing it. Actions permissions are **outside Terraform's
scope entirely**: a broad grep over every `*.tf` for
`actions_permis|allowed_actions|sha_pinning|selected_actions` returns nothing
(exit 1), and `terraform state list` exits **0 with 49 addresses**, none of which
match `action|organiz` — so this is a genuine empty result, not a failed command.
The only organisation-scoped resource declared here is
`github_organization_webhook.audit_stream`. A successful PATCH would therefore
have changed a live setting that no declaration names and that `drift_detect.py`
cannot observe — an invisible setting is worse than a silently reverted one, and
AGENTS.md §5's stated mechanism ("Terraform is the source of truth, out-of-band
PATCHes are reverted") does not cover this object, which is exactly why the
command should have been recognised as ungoverned before it was written out.

**What M-07 should have said, and what is now the action:** the platform enforces
nothing; this repository's offline guard does, on the merge path; the unbuilt
residual is live tag resolution, already tracked as D-51; and the fleet gap is
that the 16 sibling repositories have no copy of the guard. Closing it is a
per-repository test file plus its workflow wiring, reviewed in each repo — which
is the same conclusion this ADR reaches about configuration, arrived at from the
other direction.

**References added by this amendment:**
- `tests/test_action_pin_labels.py` — the guard M-07 failed to find; `4 passed` on 2026-11-03
- `.github/workflows/compliance-scan.yml:269` — `python -m pytest tests/ -q`, inside the required job
- `docs/drift-findings.md:776` **D-51** — "offline detection added here; live resolution still unbuilt"
- `docs/drift-findings.md:4` **D-43** — fleet-wide pin scan across the 16 repos plus `.github`, 2026-10-04
- `scripts/repo_readiness_audit.py:722,796` — `workflow_action_pins()` enumerates workflow pins;
  whether it refuses a non-SHA ref was **not established**, and nothing above rests on it
- Measured 2026-11-03: `gh api -X PATCH orgs/jolarca-dev/actions/permissions` → HTTP 404,
  re-read unchanged; `grep -rn` over `*.tf` → no match; `terraform state list` → rc 0, 49 addresses

---

## Amendment — 2026-11-03 (M-01, M-02, M-08): the bound was built, measured, and broke two repositories on the way

**Status in one line: proven in CI on twelve repositories' open draft branches;
enforced on none of their default branches.** Every one of those pull requests is
still `isDraft: true`, so `main` in all thirteen remains unbounded as this is
written. A control that exists only on an unmerged branch is a hypothesis with
better evidence than before, not a control — which is why M-01 and M-02 stay open
above rather than being marked closed.

**What was added.** `.miserc.toml` with
`ceiling_paths = ["{{ config_root | dirname }}"]`, `[tool_config] locked = true` in
`mise.toml`, and a `mise-config-scope` job. The first draft of the bound said
"bound the search at the repository root", which is wrong in a way that would have
passed unnoticed: a ceiling directory is not searched itself, so a ceiling naming
the root stops mise loading the root's own `mise.toml`. The bound would have
"succeeded" by disabling the thing it guards. The value must name the parent.

**What was measured, and why it is not vacuous.** The guard has four legs, and each
negative leg is paired with a positive one, because a guard that only asserts
absence also passes when the command printed nothing at all.

| Leg | Assertion | Printed evidence from the runner |
|---|---|---|
| 1 | with `MISE_CEILING_PATHS=""` the decoy **must** be discovered | `~/work/jolarca-control/mise.toml  bidi-decoy` |
| 2 | with the committed `.miserc.toml` the decoy must be absent **and** every declared version still selected | `OK: python 3.12.16 is the selected version.` / `OK: terraform 1.16.1 is the selected version.` |
| 3 | plain `mise install`, no `--locked` anywhere, must succeed from the lock | `OK: no --locked flag was passed anywhere and the lock still governed resolution.` |
| 4 | the same plain install must be refused when `mise.lock` is absent | `python@3.12.16 is not in the lockfile`, hint naming `tool_config.locked`, 0 ms |

Runs: `41677451440` job `126061779796` (jolarca-control, portable form),
`41669118323` job `126032389384` (its first version), `41678304758` job
`126064791417` (jolarca-docs), `41679375350` (`.github`), `41679434760`
(jolarca-identity), `41679517782` (jolarca-vendor). Leg 4 in jolarca-identity
tested `shellcheck@0.11.0` rather than python, because the job reads the declared
tool set out of each repository's own `mise.toml` instead of naming versions. That
is what makes one file correct across the fleet — and it is this ADR's own
per-repository conclusion, applied to the guard that carries it.

**Three failures are part of the evidence, not footnotes.**

1. `tests/test_ci_gates_are_real.py::test_no_run_step_swallows_its_exit_status`
   named four of my steps for using a shell fallback, in this repository, before CI
   could. The rule is AGENTS.md §3 in executable form: a verdict handed to a
   fallback reports an unreadable input as a clean scan.
2. The decoy assertion matched a path spelling mise does not print — mise
   abbreviates `HOME`, so `~/work/...` never equals `$GITHUB_WORKSPACE/...`. The leg
   failed **while the decoy was genuinely loaded**. Had the matcher been quietly
   satisfied instead, the inheritance would have been recorded as bounded on
   evidence of nothing at all.
3. Propagation broke `ci` in jolarca-data and jolarca-legal only, because their
   yamllint limit is 140 and this repository's is 160. Registered as **M-08**. The
   file is now 119 characters at its longest and is linted locally at 140 and 120
   before any push.

**What the bound does not reach.** A project `.miserc.toml` cannot ignore global or
system config; the same documentation page that offers `ignored_config_paths`
states that a project's file cannot ignore global or system config, and a project
`.miserc.toml` leaves `env` empty, so the file cannot read the environment to
compensate.
`~/.config/mise/config.toml` and `/etc/mise` therefore still merge into every
project on the machine, and `ceiling_paths` **fails open** — an unrendered template
becomes a literal path matching nothing, silently, because the file is read before
logging starts. **M-04 remains the load-bearing open finding:** the other half of
the bound is a machine baseline and nothing in any repository enforces it. Leg 2 is
what converts a fail-open declaration into a control; deleting that leg deletes the
control.

**jolarca-security is the honest exception, and is not counted among the twelve.**
Its `.miserc.toml` and `locked = true` are committed on the branch, but no CI proof
is available there: runs `41654550029`, `41678712745` and `41679508071` all
concluded `startup_failure`, and its `selected-actions` still reads
`github_owned_allowed: true`, `patterns_allowed: ["DavidAnson/*"]`,
`verified_allowed: false`. The configuration there is **declared and unproven**.

**Not propagated:** jolarca, jolarca-compliance, jolarca-consent and
jolarca-infrastructure, whose draft PRs were already blocked by failing checks this
work did not touch. Four repositories unbounded while twelve are bounded is exactly
the divergence-by-omission M-06 predicts, and it is recorded here rather than
smoothed over.

**References added by this amendment:**
- `jolarca-control` PR #121, branch `codex/mise-adoption-2026-11-03`, head `5f88618a`
- `.github/workflows/mise-toolchain.yml`, job `mise-config-scope` — the four-leg guard, portable
- `tests/test_ci_gates_are_real.py` — the no-swallow rule that rejected the first draft
- Measured 2026-11-03: `gh pr checks` across 13 repositories; `gh run view --log --job`
  for each quoted verdict;
  `gh api repos/jolarca-dev/jolarca-security/actions/permissions/selected-actions`

---

## Status change — 2026-11-03 (later): one default branch is now bounded

The sentence above that "every one of those pull requests is still `isDraft: true`,
so `main` in all thirteen remains unbounded as this is written" was true when
written at `3436a55` and is falsified by a later merge. It is kept rather than
edited: this register polices the error of describing unmerged work as delivered,
and the same discipline applies to the inverse — prose that was accurate at its
timestamp must not be retrodated into a claim about a later state.

- PR #124, this ADR's second amendment, merged as `3436a55`.
- PR #121 merged as `42f309a`, putting `.miserc.toml`, `[tool_config] locked = true`
  and the `mise-config-scope` job on `jolarca-control`'s default branch.

**M-01 and M-02 are therefore enforced on one default branch — this repository — and
on none of the other sixteen.** The "twelve draft branches" count in the section
above still describes the eleven repositories that remain drafts plus this one's
history; `jolarca-control` has moved from that column to this one.

Proof that the bound holds on the default branch is the guard's own printed output on
the merge push — run `41683853027`, job `126084253752` — which is the first time it
executed outside a pull request:

```text
~/work/jolarca-control/mise.toml                  bidi-decoy        (leg 1, unbounded)
OK: with no ceiling mise discovers the parent config and adopts its tool.
OK: python 3.12.16 is the selected version.
OK: terraform 1.16.1 is the selected version.
OK: decoy excluded and every declared pin is the one mise actually selects.
OK: no --locked flag was passed anywhere and the lock still governed resolution.
python@3.12.16  0ms · failed: python@3.12.16 is not in the lockfile
hint: Run `mise lock` to update the lockfile, or disable `tool_config.locked`
OK: refused, and the refusal names the lockfile.
```

**Post-merge live state, read rather than inferred from the merge banner.**
`gh api …/pulls/121` → `merged: true`, `merged_at: 2026-11-03T17:23:52Z`; `main` =
`42f309a`; all four required contexts `pass` (`Validate Repo Allow-List`, `Policy
Compliance Check`, `Repository Secret Pattern Scan`, `SAST (semgrep)`); a clean clone
of `main` reports `hash_evidence.sh --check` 47 files / 0 mismatches rc=0,
`pytest tests/` 351 passed rc=0, and gitleaks over 126 commits "no leaks found".

**No `apply.yml` run was created by either merge** — newest remains `40568492494` of
2026-10-27. That is the pre-merge intersection test doing its job, not luck: #124
touched three `docs/` files, and #121 touched `.miserc.toml`, `mise.toml`,
`mise.lock`, `MISE-ADOPTION.md` and `.github/workflows/mise-toolchain.yml`, none of
which matches `apply.yml`'s own `on.push.paths` (`repos/**`, `policy/**`, `*.tf`,
`*.tfvars`, `.github/workflows/apply.yml`), verified both through
`scripts/check_apply_path_trigger.py` (rc=0, "no apply armed") and by grepping each
pattern against the API-returned file list independently of the gate.

One procedural note: #121 was a draft, and `gh pr merge` refuses drafts, so it was
marked ready for review immediately before merging. That is a state change on the
pull request and is recorded rather than glossed.

**Still open after this:** M-03, M-04 unchanged and load-bearing — the bound reaches
neither global nor system config, and every workstation is still unbounded — plus
M-05, M-06, M-07, M-08, and sixteen repositories whose default branches carry no
bound at all.

---

## Closure — 2026-11-03 (later): M-10, route (a), nine of ten plus a bonus skew

**Rule R8** now reads every `.github/workflows/*.yml` in this repository, finds each
`actions/setup-python` and `hashicorp/setup-terraform` step, and requires the
approved release. It is offline, deterministic and token-free, so it runs in
`make lint` and as a step inside the required `Validate Repo Allow-List` job — the
same placement that made M-06's check enforceable.

**Observed firing before it was fixed, not assumed correct.** First run:
`FAIL: 10 finding(s)` — nine `python-version: "3.12"` requests plus
`compliance-scan.yml:terraform runs hashicorp/setup-terraform with no
terraform_version; the version is whatever the action defaults to`. `runtime_steps_examined`
reported 13, which is the non-vacuity count: 10 python + 3 terraform steps.

**What changed:** 9 python declarations pinned to `3.12.16` across
`compliance-scan.yml` (4), `sast.yml` (2), `context-parity.yml`, `deploy-gates.yml`
and `plan.yml`; and the Terraform Format job given `terraform_version: "1.16.1"`.
That last one closes row 3 of this ADR's Context table — `terraform fmt -check` ran
with no version while `plan.yml` and `apply.yml` pinned 1.16.1 — which was a
pre-existing defect the M-10 rule happened to expose. A rule found by accident is
still a rule found.

**What was deliberately not changed, and why.** `apply.yml` holds the tenth
declaration and is **one of `apply.yml`'s own `on.push.paths`**, so editing it arms a
real `terraform apply -input=false -auto-approve tfplan` on merge, gated only by the
production environment's 30-minute wait timer — which AGENTS.md §8 records as delay,
not approval (D-58, D-70) — plus `check_plan_safety.sh`. Pinning it inside a toolchain
PR would bundle a production apply attempt into a documentation-class change. It is
instead excused by a dated `workflow_exceptions` entry covering **R8 only**, expiring
2027-05-03, and the exception is enforced by C8 to name the rules it excuses — the
M-09 lesson applied before it could repeat.

**Non-vacuity, proven three ways.** (1) `runtime_steps_examined` is printed in the OK
line, so a clean pass over zero files is visible rather than silent; (2) if the
catalogue approves python or terraform and no consuming step is found, the gate exits
**2** `CANNOT VERIFY`, never 0; (3) reverting one pin in `sast.yml` turned the
shipped-artifact test red with the exact R8 line and the file restored byte-identical
(`48 passed` again). Nine further R8 fixtures show the rule firing on a floating
request, a wrong-but-exact release, a missing `python-version`, a missing
`terraform_version`, an override honoured, an exception that does not cover R8
failing to suppress it, and an empty workflows directory refusing to pass.

**Limits of this closure, stated.** R8 reads **this repository's** workflows. The
other sixteen are not covered by it — their runtime declarations are their own
repositories' decision, and per ADR-0010 that is the correct arrangement, not an
oversight. And R8 says nothing about the interpreter a *self-hosted* runner uses, nor
about the operator's workstation: M-04 is untouched and remains the load-bearing open
finding.

**Verification:** gate rc=0 `13 workflow runtime step(s) examined`; 48 fixture tests
pass; `terraform fmt -check -recursive` rc=0; `apply.yml` absent from the diff.

### Landed — PR #128, and the head I verified is not the head that merged

The section above was written while #128 was open. It merged as `0ebc198` at
`2026-11-03T20:29:43Z`, so rule R8, the nine pins and the `apply.yml` exception are on
this repository's default branch. The step's own printed verdict on the merge push —
run `41713077841`, job `126185936151` — is the evidence, not the badge:

```text
OK: catalogue coherent (toolchain-catalogue.yml); 4 approved tool(s);
    13 workflow runtime step(s) examined against the approved releases
```

**The commit I signed is not the commit that merged.** I pushed `2ed617d`; the PR
merged from `5d016f2`, which synced `main` into the branch and back-filled
`CHANGELOG.md` — a file this change had not touched, and a gap another session closed
while I was reporting the PR as open. Two consequences stated rather than smoothed:
the verification I ran against `2ed617d` was not, strictly, verification of what
landed; and a CHANGELOG entry I did not write is now attributed to this change. So the
merged tree was re-verified rather than assumed:

| check on the merged tree | result |
|---|---|
| previously merged steps still in `compliance-scan.yml` | **12 of 12** — the silent-step-deletion regression this repository's history records did not recur |
| `def runtime_errors` / `runtime_steps_examined` / non-vacuity exit 2 | 1 / 1 / 1 |
| catalogue `workflow_exceptions` / `test_r8*` cases | 1 / 8 |
| pins | 9 × `3.12.16`, **0 unpinned**, except `apply.yml` (1, intended) |
| fmt job `terraform_version` | 1 |
| clean clone at `956efc2` | evidence 48 files / 0 mismatches rc=0 · `pytest` 403 passed · `bandit -ll -ii` rc=0 with 0 issues · gate rc=0 |
| gitleaks, full history | 150 commits scanned, `no leaks found` |
| new `apply.yml` run | **none** — newest remains `40568492494` of 2026-10-27 |
| `Deploy Gates`, `Validate & Plan` | fail, and **neither is a required context**; the plan dies at `terraform init` on the D-56 credential |

M-10 is therefore closed on `main` for nine of ten declarations. What remains open is
`apply.yml`'s own pin — a deploy decision behind a dated exception expiring
2027-05-03 — and the fact that R8 governs only this repository's workflows, which is
the arrangement ADR-0010 argues for rather than an oversight.
---

**References:**

- <https://mise.jdx.dev/configuration.html> — config load order, per-tool merge
  and inheritance, `.miserc.toml` and `ceiling_paths`, `[tool_config] locked`,
  `include` (retrieved 2026-11-03)
- <https://mise.jdx.dev/paranoid.html> — the four paranoid categories, the
  global-only restriction, remote-include pinning (retrieved 2026-11-03)
- <https://mise.jdx.dev/security.html> — configuration trust and safe mode
- `docs/architecture.md` §Toolchain Management — the pointer to this decision
- `jolarca-control` PR #121, branch `codex/mise-adoption-2026-11-03`, base
  `8f24aac2cef544836bb458bb0768d4f7972d9bbf`
- PR #128 (rule R8): pushed `2ed617d`, merged from `5d016f2` as `0ebc198` at
  `2026-11-03T20:29:43Z`; CI evidence run `41713077841` job `126185936151`
- Measured 2026-11-03 via `gh`: `gh pr view <n> --json files` for all 17 draft
  PRs; `gh pr checks 121 --repo jolarca-dev/jolarca-control` (10 green);
  `gh api repos/jolarca-dev/jolarca-security/actions/permissions[/selected-actions]`;
  `gh api orgs/jolarca-dev/actions/permissions`;
  `gh run list --repo jolarca-dev/jolarca-security --workflow mise-toolchain.yml`
  (run 41654550029, `startup_failure`)
- SOC 2 CC8.1 (change management), CC7.1 (vulnerability detection), CC6.1
  (logical access)
- ISO 27001 A.8.32 (change management), A.8.19 (installation of software on
  operational systems), A.8.9 (configuration management), A.5.9 (inventory of
  associated and other assets)
- GDPR Art. 32(1)(b) and 32(1)(d) — integrity and confidentiality of processing,
  and regular testing of technical measures
- PCI-DSS 2.2.x (secure configuration standards), 6.5.1 (change control),
  11.5.x (change detection)
- `docs/drift-findings.md` D-04 — `required_approving_review_count = 0`;
  D-94 — the adoption generator's single-target defect
