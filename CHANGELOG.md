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
