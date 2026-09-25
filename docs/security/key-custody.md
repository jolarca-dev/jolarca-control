# Key custody — who holds what (control-plane scope)

Every credential this repository depends on has a named custodian, a rotation
cadence, and a loss/recovery path. An unnamed secret is an unmanaged risk
(SOC 2 CC6.1, ISO 27001:2022 A.5.17).

> **Scope note (2026-09-25).** This register was carried from
> `jolarca-infrastructure`, whose version lists SOPS age identities,
> ansible-vault passwords, Cloud KMS CMEKs, WireGuard keys, Vault unseal keys
> and a break-glass service-account key. **This repository holds none of
> those.** Keeping them here would create a second, stale copy of a security
> register — a duplicate source of truth, which is itself an ISO 27001 A.5.2
> finding. The authoritative infrastructure register is
> `jolarca-infrastructure/security/key-custody.md`; it is **not** mirrored here.
> What follows is only what `jolarca-control` genuinely depends on.

**Rule of dual control:** any credential marked *(dual)* requires two named
custodians; no single person may hold, use, or rotate it alone. See deviation 3
— no *(dual)* item can currently be satisfied.

## Register — credentials this repo depends on

| Credential | Custody | Storage | Rotation | Loss path |
|---|---|---|---|---|
| GitHub PAT — TF read-only | CI secret, 1 operator | **repo** secret `TF_GITHUB_TOKEN_READONLY` on `jolarca-control` | 90d | `../runbooks/github-token-rotation.md` |
| GitHub PAT — TF write | CI environment secret, 1 operator | **environment** secret `TF_GITHUB_TOKEN` on the `production` environment | 90d | same runbook; applies require re-review |
| Operator GitHub account (`JourneyOfLife`) — org owner | 1 operator *(should be dual)* | GitHub, with account-level 2FA | on personnel change or compromise | account recovery + org owner transfer; this is the **root of trust** for everything below |
| Local Terraform state (`terraform.tfstate`) | 1 operator host | operator workstation only | n/a — see D-02 | restore from the off-host verified backup taken in `../state-migration-runbook.md` step 0 |

### Why the operator account is the real crown jewel

The write PAT can reconfigure or destroy every repository in a PCI-DSS-scoped
organization, but the PAT is only as strong as the account that minted it.
`jolarca-dev` has **one member** and **zero teams** (verified 2026-09-25), and
`two_factor_requirement_enabled` is **`false`** at the org level (finding
**D-18**, blocking). That means the org-level 2FA floor does **not** protect
this control plane — only the operator's own account-level 2FA does. Until
D-18 is closed, account-level 2FA on `JourneyOfLife` is a **hard** custody
requirement, not a recommendation, and its recovery codes must be in offline
custody. Enabling org-enforced 2FA is a one-line change in `org-settings.tf`.

## Known interim deviations (tracked)

1. **Shared interim PAT.** Both TF tokens currently hold the SAME classic PAT
   (the active operator token) instead of separate fine-grained read/write
   PATs. Rotation to the doctrinal pair is a tracked issue — the first rotation
   must split them. Until then, boundary 3 in `isolation-model.md`
   (read/write separation) is **declared but not enforced**.
2. **Environment approval gate may not be enforceable.** Required reviewers on
   private repositories need GitHub Team+; the plan in force when this note was
   written could not enforce the manual approval step on `production` applies.
   Compensating controls: the write token is isolated in an environment secret,
   dispatch is limited to repo collaborators, `apply.yml` refuses any plan that
   destroys or replaces a repository, and every apply is followed by drift
   detection. **Re-verify, do not assume:** while D-01 leaves the fleet public,
   environment protection rules are available on a free plan — confirm in the UI
   and update this deviation with what you find.
3. **Solo-era operation.** Exactly one operator exists today; a second person
   is not yet engaged. All human review gates — branch-protection review counts,
   CODEOWNERS reviews, dual control — are unavailable, and enforcement rides on
   automated gates (required status checks, policy scans, drift detection).
   Note that CODEOWNERS review is *configured* (`require_code_owner_reviews =
   true`) yet **inert**: the sole member authors every PR and cannot approve it,
   and GitHub does not block the merge — verified by `jolarca-infrastructure`
   PR #26 merging with zero reviews (**D-20**). This is recorded as deviation
   **D-04** in `../drift-findings.md` and is the reason `variables.tf` sets
   `required_approving_review_count = 0` to match live reality instead of
   asserting a control that cannot fire. Activation checklist:
   `../../CONTRIBUTING.md` ("Onboarding trigger"). Until then the sole operator
   is custodian of every credential above, and every *(dual)* requirement is
   held in escrow-as-design only — logged in the quarterly access review.

## Invariants

1. Custodians are named people, not teams. Leaving the org is a rotation event.
2. Rotation is always logged in `../../CHANGELOG.md`, in the append-only log of
   the relevant runbook, and as compliance evidence in `jolarca-compliance`.
3. No credential lives in git, state, `terraform.tfvars`, container images, or
   CI logs — enforced by the **Repository Secret Pattern Scan** job in
   `.github/workflows/compliance-scan.yml`.
4. Quarterly, this register is reconciled against reality. The procedure lives
   in `jolarca-infrastructure/security/access-review.md`; the evidence lands in
   `jolarca-compliance/audits/access-reviews/`, whose due-date is tracked by
   that repo's `access-review-due.yml` workflow. Neither was ported here —
   raise the review there, then record the outcome in this repo's CHANGELOG.
   Mismatches are findings, not footnotes.
