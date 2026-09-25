# Isolation model — THE MOAT DOCTRINE (control-plane scope)

**Status:** doctrine. Changes require security review.

> **Scope note (2026-09-25).** This document was carried from
> `jolarca-infrastructure`, where the moat doctrine covers networks, hosts and
> cloud accounts. This repository is a **GitHub-organization control plane**: it
> holds no network, no hosts, and no workload. What follows is the doctrine
> rescoped to what this repo actually owns — organization identity, repository
> existence, branch protection, and the tokens that write them.
>
> The authoritative infrastructure moat (WireGuard mesh, GKE ingress/egress,
> nginx edge, Cloud NAT, host boundaries) remains
> `jolarca-infrastructure/security/isolation-model.md`. It was **not** copied
> here, because a duplicated doctrine drifts and two copies of a security
> policy is itself an ISO 27001 A.5.2 finding. Where this repo needs an
> infrastructure fact, it links to the owner.

Basis: ISO 27001:2022 A.5.2 (policies for information security), A.8.13
(segregation); SOC 2 CC6.1 (logical access); GDPR Art. 32 (security of
processing); PCI-DSS 4.0 Req. 7 (least privilege).

## Trust boundaries

| # | Boundary | Rule |
|---|---|---|
| 1 | **Marketplace org ↔ mission org** | `jolarca-dev` and `journeyoflife-org` are **separate GitHub organizations** since 2026-09-02 (ADR-0004 Amendment 2, change record `JOL-ORGTRANSFER-20260902-01`). No shared membership, tokens, secrets, CI configuration, or Terraform state may exist between them. This is now a structural boundary, not a naming convention. ONE sanctioned runtime crossing exists — the internal payment API (ADR-0005, contract in `jolarca-infrastructure/docs/payment-api-contract.md`): mTLS-only, PAN-free, and it shares no state, credentials, or CI. Any additional cross-org interface requires a new ADR. |
| 2 | **Control plane ↔ fleet** | This root can create, reconfigure and *destroy* every repository in a PCI-DSS-scoped org. That capability is the crown jewel here. It is constrained by `prevent_destroy` on every repository resource, the `^jolarca(-[a-z0-9-]+)?$` precondition in `repositories.tf`, the plan-refusal gate in `apply.yml`, and the `vars.STATE_MIGRATION_COMPLETE` hard gate. Removing any of those four is a security change, not a refactor. |
| 3 | **Read token ↔ write token** | `TF_GITHUB_TOKEN_READONLY` (repo secret) and `TF_GITHUB_TOKEN` (environment secret on `production`) are distinct credentials with distinct blast radii. Read scope must never be widened to satisfy a convenience; the write token must never be reachable from a PR-triggered job. See `key-custody.md`. |
| 4 | **PR ↔ apply** | `plan.yml` runs on `pull_request` with read scope only. `apply.yml` runs on push-to-main / manual dispatch inside the `production` environment. No pull-request-triggered job may hold the write token. A fork or external PR therefore cannot reach production. |
| 5 | **Allow-list ↔ live org** | `repos/*.yml` is the single declarative source of truth for what may exist. A repository present in the org but absent from the allow-list is an **incident** (ADR-0004 R2: import within 48h or delete), detected by `scripts/check_fleet_separation.sh` and `scripts/drift_detect.py`. |
| 6 | **Secrets ↔ everything** | Secrets exist only in GitHub Actions secret storage and the operator's password manager. Never in git, `terraform.tfstate`, `terraform.tfvars`, CI logs, or issue trackers. Enforced by the secret-pattern-scan job in `compliance-scan.yml`. |

## What may never leave this repository

- **Terraform state** — any copy, or any excerpt containing resource
  identifiers in bulk. State here contains repository node IDs and the full
  configuration of a PCI-DSS-scoped fleet. Note the current exposure: state is
  **local-only with a single copy** (finding **D-02**, blocking). Remediation is
  `../runbooks/workload-identity-federation.md`; compromise handling is
  `jolarca-infrastructure/docs/runbooks/state-compromise.md`.
- **The write PAT.** Not in a commit, not in a PR description, not in chat, not
  pasted into an issue to "debug CI". Rotation on suspicion is
  `../runbooks/github-token-rotation.md`, revoke-first.
- **Org-level configuration detail** that reduces attack cost — webhook
  endpoints and signing-secret handling (`org-settings.tf`), collaborator and
  membership lists, and any break-glass procedure.

## Scope segregation with the mission platform

The `jolarca*` fleet lives in `jolarca-dev`; the mission platform's `jol-*`
fleet lives in `journeyoflife-org`. This repository manages **only**
`jolarca-dev` — `variables.tf` carries a validation that rejects any other
value for `github_org`, so a mis-set variable fails at `plan` rather than
silently writing to the wrong organization.

Four known live deviations from clean segregation, all tracked in
`drift-findings.md`:

- **D-20 — CODEOWNERS points at the mission org (blocking).** All five
  `jolarca*` repositories carry `.github/CODEOWNERS` naming
  `@journeyoflife-org/*` teams (and `jolarca` names `@jol-infrastructure/*`, an
  organization that returns HTTP 404). This is a live breach of boundary 1 and
  of ADR-0004 R4's third clause. It is also a *functional* failure: `jolarca-dev`
  has zero teams, so `require_code_owner_reviews = true` has no satisfiable
  approver and the control is void. GitHub copied this content verbatim through
  the 2026-09-02 transfer — an org transfer does not rewrite team references.
- **D-03 — cross-scope leak.** The inherited Terraform state owns
  `journeyoflife-org/.github`, i.e. a *mission-org* repository is managed from
  *marketplace* Terraform. This is a direct boundary-1 violation and is the
  reason `health-repo.tf` carries a migration warning. Resolution is
  `state-migration-runbook.md` step 4.
- **D-01 — visibility.** All six repositories in `jolarca-dev` are `public`
  (verified 2026-09-25) while the intent of record is `private` for the five
  non-`jolarca` repos. `jolarca-data` was documented **private** at transfer
  time, so this includes at least one regression. Public PCI-scope
  repositories widen the audit surface that boundary 1 exists to limit.
- **D-18 — no enforced 2FA.** `two_factor_requirement_enabled` is `false` for
  the org. A control plane is only as strong as the identity that holds its
  write token.

Cross-scope contributions require explicit approval from both scopes' owners;
shared modules are forked, not symlinked (ADR-0004 R4).

## Violations

Any observed boundary crossing — a repository in the org that is not in the
allow-list, a branch protection removed out-of-band, an unexplained credential,
a mission-org resource appearing in this state — is treated as potential
compromise until explained by an approved change record. Unexplained means
incident (`../../SECURITY.md`).
