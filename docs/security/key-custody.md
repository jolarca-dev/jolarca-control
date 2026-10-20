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
| AGE identity for state backup encryption | 1 operator | operator workstation `~/.config/age/state-backup-key.txt` (mode 600) | on personnel change or compromise | regenerate keypair with `age-keygen`, update `.state-backup-pubkey.txt` and `AGE_SECRET_KEY_CI` repo secret |
| Local Terraform state (`terraform.tfstate`) | 1 operator host | operator workstation only | n/a — see D-02 | restore from the off-host verified backup taken in `../state-migration-runbook.md` step 0 |

### Expiry register (machine-read by `scripts/check_secret_inventory.sh`)

Added 2026-10-20. This table is the single `expires`-bearing block the gate parses;
the custody table above stays prose-stable. `unknown` fails the gate on purpose —
verify, don't pad.

| Credential | Expires | Rotation | Last verified | Notes |
|---|---|---|---|---|
| GitHub PAT — TF read-only (fine-grained `jolarca-dev`) | 2027-01-08 | 90d | 2026-10-20 | inferred backing of `TF_GITHUB_TOKEN_READONLY` — Actions secrets are write-only, confirm in a plan run |
| GitHub PAT — TF write (fine-grained `jolarca-control-tf-write-2026-10-17`) | 2027-01-15 | 90d | 2026-10-20 | inferred backing of `TF_GITHUB_TOKEN` (production env); **Never used** since mint — revoke by 2026-11-15 if no apply exercises it |
| `TFC_TOKEN` (HCP Terraform) | unknown | manual | — | read the actual expiry in the HCP UI and replace `unknown` — until then the gate is red by design |
| Operator GitHub account (`JourneyOfLife`) | never | on-compromise | 2026-10-19 | org 2FA-required badge verified live on all three orgs 2026-10-19 |
| AGE identity for state backup | never | on-compromise | 2026-10-17 | `~/.config/age/state-backup-key.txt`, mode 600 |

> **Deviation 1 status hint (2026-10-20):** the two fine-grained PATs above were minted
> 2026-10-17, which *suggests* the read/write split has been performed since this note
> was written. Deviation 1 stays open until a plan/apply run proves each secret resolves
> to its own token (the write token must be unreachable from a PR-triggered job).

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
