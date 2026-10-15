# Changelog

All notable changes to `jolarca-control` are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

This repository is the governance control plane for the `jolarca-dev`
marketplace organization. Changes here can alter branch protection, visibility
and scanning settings on six PCI-DSS-scoped repositories, so the changelog is
part of the SOC 2 CC8.1 / ISO 27001 A.8.32 audit trail and is not optional.

## [Unreleased]

### Added — 2026-09-25

Initial control plane, extracted from
[`jolarca-infrastructure`](https://github.com/jolarca-dev/jolarca-infrastructure),
where GitHub-organization governance had accumulated inside an infrastructure
repository.

**Allow-list and policy**

- `repos/*.yml` — six repository definitions (`jolarca`, `jolarca-control`,
  `jolarca-compliance`, `jolarca-data`, `jolarca-infrastructure`,
  `jolarca-legal`). Every setting was transcribed from live `gh api` output on
  2026-09-25, not from the stale Terraform state snapshot of 2026-08-31.
- `policy/repo-defaults.yml` — enforced baseline, with the solo-era deviations
  recorded in the file rather than hidden in Terraform comments.
- `policy/compliance-gates.yml` — ten gates, per-tier enforcement matrix, and
  an `exceptions.active` register carrying D-04 and D-05 with named
  compensating controls.

**Terraform**

- `repositories.tf` — fleet repositories driven by the allow-list, with an
  ADR-0004 R1/R3 `precondition` that rejects any non-`jolarca*` name at plan
  time, and `lifecycle { prevent_destroy = true }` on every repository.
- `branch-protection.tf` — one resource for the fleet and one for the health
  repo, encoding verified live values.
- `health-repo.tf` — the org `.github` repository and its inherited
  `SECURITY.md`, carried over from the old `github-health-repo.tf`. Kept out of
  the allow-list because its name is not a valid allow-list filename and its
  policy is deliberately different.
- `org-settings.tf`, `outputs.tf`, `variables.tf`, `main.tf`,
  `terraform.tfvars`.

**Automation**

- `scripts/validate_repos.py` — adds the ADR-0004 naming rule and a
  data-classification ↔ visibility coherence rule (the check that makes D-01
  visible); reads the signed-commit expectation from policy instead of
  hardcoding it.
- `scripts/compliance_check.py` — seven checks including fleet separation and
  merge policy; surfaces the D-04 deviation as information rather than failing
  on it.
- `scripts/drift_detect.py` — now diffs visibility, wiki and archive state as
  well as fleet membership, against `jolarca-dev`.
- `scripts/check_fleet_separation.sh` — ported and rewritten to parse
  `repos/*.yml` instead of a Terraform variable default; adds R3 (mission-repo
  intrusion) and a time-boxed `ALLOW_MISSING` bootstrap exemption.
- `scripts/org_delivery_audit.sh` — ported; `jolarca-control` added to the
  audited fleet.
- Four workflows (`plan`, `apply`, `compliance-scan`, `fleet-separation-guard`),
  every action pinned to a full commit SHA.

**Documentation**

- `docs/drift-findings.md` — 22 findings, each with the command that verifies
  it.
- `docs/state-migration-runbook.md` — the gated procedure that makes this
  repository authoritative.
- `docs/architecture.md`, `docs/threat-model.md`, `docs/change-management.md`,
  `docs/data-classification.md`, `docs/runbooks.md` (RB-01 … RB-07).
- `docs/adr/0004-mission-marketplace-separation.md`,
  `docs/runbooks/github-token-rotation.md`,
  `docs/runbooks/workload-identity-federation.md`,
  `docs/security/{isolation-model,key-custody}.md` — carried from
  `jolarca-infrastructure`.
- `audit/pci-dss-checklist.yml` — new; PCI-DSS 4.0 applies to every repository
  in this fleet, unlike the mission platform.

### Added — 2026-10-08 (A-08: mandatory SAST gate made real)

The `sast` gate was declared `enforcement: mandatory` in
`policy/compliance-gates.yml` but nothing ran it — a D-22-class control
(AGENTS.md §7). Closed in two PRs (workflow, then gate wiring) because
`check_declared_contexts.py` reads live `main` and a required context cannot be
declared before the workflow that emits it is merged.

- `.github/workflows/sast.yml` — Semgrep OSS (`p/default`+`p/python`), Bandit
  (`-ll -ii`, scope widened from `scripts/` to `scripts/ tests/`) and a Trivy
  config scan over the Terraform/workflow/policy YAML. All actions SHA-pinned,
  `permissions: contents: read`, `pull_request` (not `pull_request_target`),
  **no GHAS/CodeQL dependency** (CodeQL is unavailable on the Free plan, so the
  `codeql-analysis` gate ID could never have been satisfied here).
- `scripts/compliance_check.py` — `check_sast_gate_wiring()` fails when a repo
  is in a tier where `sast` is mandatory but does not declare
  `SAST (semgrep)` as a required status check.
- `.trivyignore.yaml` — accepted Trivy misconfigurations `GIT-0004` (→ D-05,
  expires 2026-12-24) and `GIT-0001` (→ fleet-public-2026-10, expires
  2026-12-29), each naming its exception ID and expiry.
- `tests/test_compliance_check.py` — positive **and** negative controls for the
  wiring check (AGENTS.md §7 non-vacuity).
- `docs/security/sast-mandatory-gate-2026-10-08.md` — triage of every first-run
  finding plus the throwaway negative-control proof (run `37699506676`:
  deliberate `shell=True`/`eval` turned **only** `SAST (semgrep)` and
  `SAST (bandit)` red; all other checks stayed green).

### Fixed — 2026-10-15 (D-61 → D-64: the apply path was measured, then made honest)

Executing "merge only after reading what the apply will do" turned up four
findings, all fixed in-repo rather than only registered:

- **D-61 · the pre-apply refusal gate had a blind spot.** A *refreshed* plan from
  this root renders `3 to add, 25 to change, 0 to destroy` and
  `scripts/check_plan_safety.sh` exited **0** on it — the refusal seen earlier
  came only from `-refresh=false` carrying stale `private` values, i.e. a gate
  firing for the wrong reason. The script now also refuses branch-protection
  **creates**, any change to 13 protection attributes (either direction — a
  tightening can deadlock a merge as well as a weakening can expose the fleet,
  and Terraform renders both identically), and secret-scanning / push-protection
  / Dependabot / vulnerability-alerts **disables**. Enabling stays allowed.
  Verified three ways: 16 fixtures (4 new refusals + 2 non-vacuity controls), the
  real refreshed plan text which now exits **1** naming the three creates, and
  `policy/compliance-gates.yml` `plan_review` updated with the new
  `blocked_actions` plus an `operator_path` and no skip flag.
- **D-64 · D-56's real cause was a workflow bug, not a credential.** `plan.yml`
  ran `terraform init -backend=false` against a `cloud {}` root, so every
  PR-time plan aborted with `HCP Terraform initialization required` — reproduced
  byte-for-byte on a clean tree and fixed. Consequence stated, not buried: the
  plan now renders, so "Validate & Plan" fails at the refusal step until runbook
  step 6 is reconciled. That is the intended posture — a readable refusal
  replaces a broken automation.
- **D-62 · the policy baseline named a required context that nothing reports**
  ("Fleet Separation Guard"; the job is "Fleet Separation (ADR-0004)" and it is
  path-filtered) **and omitted a real one** (`SAST (semgrep)`). Corrected; no
  script reads that block, so the fix is documentary and the follow-up (point
  `check_declared_contexts.py` at it, or delete it) is an owner decision.
- **D-63 · three documents described a closed apply gate and a thin state
  inventory.** Measured: `STATE_MIGRATION_COMPLETE` = `"true"` (gate OPEN),
  workspace `resource-count: 48` / `execution-mode: local`, and **14**
  `github_branch_protection` addresses are in state — not "only
  `jolarca-hermes-agents`" as AGENTS.md §8 claimed. Corrected across AGENTS.md
  §2/§8, ADR-0006, the runbook status line, the repo-request template, the
  `make apply` message, and the SOC 2 / PCI-DSS checklists (CC8.1-03 → gap/D-56,
  CC8.1-04 → gap/D-58 with the environment's measured empty
  `protection_rules`, CC8.1-05 → implemented, 6.5.3-01 → partial). Dated
  historical readings (the 2026-10-12 `resource-count: 35`) were annotated, not
  rewritten. One half stays open and is recorded as such: `…/branches/main/protection`
  now returns **HTTP 404** while `.protected = true` and repo rulesets are `[]`;
  the cause was not established in two probe attempts, so nobody should read
  that 404 as "unprotected".
- `files/SECURITY.md` was re-mirrored to the live `.github` copy (byte-identical,
  verified by re-read) — the divergence was created by editing the reference copy
  in the first half of this change, which is precisely the D-15 trap.
- `prevent_destroy` was observed working, not assumed: a probe tree missing
  `repos/*.yml` (so every instance plans for deletion) aborted with
  `Error: Instance cannot be destroyed` instead of producing a destroy plan.

### Changed — 2026-10-15 (D-59, D-60: published contacts and commit identity)

- **New `policy/contact-addresses.yml`** — the single definition of the five
  role mailboxes (dev / github / security / privacy / billing), which are
  published, which are retired, and the exact cross-repo targets still naming
  dead addresses. Convention-only: no gate reads it yet, and the file says so.
- **Every published contact was undeliverable.** `jolarca.com` and
  `jolarca.dev` have no MX and no DMARC (measured: `dig MX`, `dig TXT _dmarc`,
  no listener on 25/587, no mail container), so `security@jolarca.com`,
  `legal@jolarca.com`, `security@jolarca.dev` and `legal@jolarca.dev` could
  never receive a report — 34 hits across 6 repositories, including the
  `jolarca-security` audit's own open Critical finding F-05 (2026-09-28).
  `files/SECURITY.md` now names the interim security and privacy aliases.
- **GitHub organisation contact updated and re-read.** `orgs/jolarca-dev`
  `billing_email` and profile `email` moved from the general dev alias to the
  GitHub-operations alias. No Terraform drift is possible: no
  `github_organization` resource exists in state.
- **Commit identity no longer publishes a personal mailbox.** Global
  `git config user.email` (inherited by all 16 fleet repos on this host) is now
  the ID-prefixed GitHub noreply address. Existing history keeps the old
  address; a fleet-wide rewrite was rejected as disproportionate and is an
  operator-only action (AGENTS.md §5).
- **ADR-0006 and ADR-0007 amended, not silently rewritten.** The HCP Terraform
  org billing email is re-measured and still the base mailbox — recorded as an
  outstanding owner-executed UI change rather than restated as an alias nobody
  has confirmed at the provider. ADR-0007's assumption that SECURITY.md provides
  a working disclosure route is corrected by a dated amendment.
- **`policy/compliance-gates.yml`** gains `contact-alias-interim` (approved
  2026-10-15, expires 2027-01-13) stating what the aliases do and do not buy:
  routing and leak attribution, not segregation of duties or an independent DPO.
- **AGENTS.md §6 and §8** record the convention and the trap: `files/SECURITY.md`
  is a reference copy, because `github_repository_file.security_md` is
  commented out and the served file lives in the `.github` repository (D-15).

### Changed

- **Apply is a single gated production stage.** `jol-control`'s
  dev → staging → prod promotion was deliberately not replicated: an
  organization control plane has one target, so promoting one plan three times
  would apply identical changes to the same repositories three times.
- **Approving-review count is 0, not 2.** Matches verified live reality and the
  solo-era deviation. Recorded as D-04 with four compensating controls.
- **Signed-commit enforcement is off** at the branch-protection layer
  (D-05), while `commit_signing_policy` keeps the human obligation explicit.
- **LICENSE is proprietary**, not MIT. This repository is private and holds the
  governance posture of a PCI-DSS scope; the AGPL-3.0 on the public `jolarca`
  application does not extend to it.

### Fixed — inherited defects corrected during the port

- **False compliance assertions removed.** The inherited SOC 2 and ISO 27001
  checklists claimed as `implemented`: org-wide MFA (verified **disabled**,
  D-18), team-based access control (no teams exist, D-10), signed-commit
  enforcement (verified `null`, D-05), and Terraform state encrypted in AWS
  `eu-central-1` with SSE (there is no AWS backend anywhere in the marketplace
  tree — state is a local file, D-02). Each is now recorded as a gap with a
  finding ID. A checklist that overstates controls is a worse audit outcome
  than an honest gap.
- **False GDPR data-residency claim removed** (Art44-02) and replaced with the
  verified GCP `europe-west1` default plus an explicit gap for state residency.
- **Unpinned GitHub Actions.** The inherited workflows used floating tags
  (`actions/checkout@v4`). All are now pinned to full commit SHAs, matching the
  doctrine already applied across the fleet.
- **Dead `data "github_team" "security"` block** inherited from `jol-control`
  was dropped — it is referenced nowhere and would fail every plan in an org
  with no teams.
- **`apply.yml` used `secrets.GITHUB_TOKEN`**, which cannot manage other
  repositories or org-level resources. Replaced with a least-privilege
  fine-grained PAT split into read-only and read/write secrets.

### Security

- `apply.yml` refuses any plan containing a destroy, a replace, or a visibility
  change.
- `prevent_destroy` on every `github_repository`.
- Both `plan` and `apply` are gated on the `STATE_MIGRATION_COMPLETE`
  repository variable, which is intentionally unset.
- `make apply` refuses outright; `make plan` offers only an offline
  `-refresh=false` plan.

### Known limitations

This control plane is **not yet authoritative**. It declares the governance of
six live repositories but does not own their Terraform state. See the README
banner, `docs/state-migration-runbook.md`, and findings D-02, D-13.

Three findings block the first apply: **D-01** (four PCI-scope repositories
publicly readable), **D-02** (single-copy local state, no backend, no
locking), **D-18** (org-wide MFA not enforced). D-18 is a single organization
setting and can be closed immediately with no code change.
