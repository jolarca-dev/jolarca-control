# ADR-0010: Per-Repository Toolchain Configuration (mise)

**Date:** 2026-11-03
**Status:** Accepted
**Deciders:** Gintaras Kazlauskas (organization owner)
**Scope:** all 17 `jolarca-dev` repositories; 17 draft PRs open on 2026-11-03

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

- **M-01 — config discovery is unbounded in all 17 drafts.** No `.miserc.toml`
  is present in any of them (all 17 file lists read, 2026-11-03). This matters
  because `ceiling_paths` set under `[settings]` in `mise.toml` "has no effect on
  config discovery": mise reads `.miserc.toml` *before* any `mise.toml`. It is
  also the one config file that loads without trust, precisely because "it can
  only choose which config files load". *Control to add:* a committed
  `.miserc.toml` bounding the search at the repository root, or
  `MISE_CEILING_PATHS` set in the workflow. Until one of those exists,
  Rationale 2 is a live exposure, not a theoretical one.
- **M-02 — `--locked` binds the CI job, not the repository.** The workflows pass
  `install_args: --locked`, so a developer running plain `mise install` resolves
  unlocked against whatever the lockfile does not constrain. *Control to add:*
  `[tool_config] locked = true` in each `mise.toml`, which "requires this config
  root's tools to resolve and install from their lockfiles" and travels with the
  repository instead of with the invocation. Its documented limit — it "does not
  affect tools inherited from global, system, or parent config roots" — is why
  M-02 must ship together with M-01.
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
  not a control.
- **M-07 — the action pin is unenforced by the platform.** Both the org and
  `jolarca-security` return `sha_pinning_required: false` (measured 2026-11-03).
  AGENTS.md §5 requires every GitHub Action to be pinned to a full commit SHA,
  and the mise smoke workflows do comply — but nothing on the platform refuses a
  tag or a branch ref, here or in the other 16 repositories. This is a
  pre-existing gap, not one mise introduces; mise adoption inherits it and adds
  17 more workflows that depend on review alone. *Control to add:* set
  `sha_pinning_required: true` fleet-wide, or add a gate that reads each
  workflow's `uses:` lines and refuses a ref that is not 40 hex characters.
  Until one of those exists, "SHA-pinned" describes a convention.

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

- when M-01 and M-02 are implemented, to replace the finding text with the
  shipped control;
- when a second platform's lock entries exist (M-05);
- when the machine baseline for M-04 is recorded;
- before any workflow migration that makes `mise` the CI entry point — that
  change needs its own ADR, because it converts a declaration surface into an
  execution surface;
- if a self-hosted runner is ever introduced. A hosted runner cannot see
  `/etc/mise` or `~/.config/mise`; a self-hosted one can, and inheritance then
  becomes an attacker-reachable input on every PR from a fork.

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
