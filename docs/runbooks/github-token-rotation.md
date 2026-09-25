# Runbook: GitHub token rotation

**Status: ACTIVE** — a GitHub PAT is the live credential plane for this control
plane (`jolarca-control`, root Terraform, `provider "github"` in `../../main.tf`).
Rotate every 90 days, on personnel change, or on any suspicion of exposure.
Basis: SOC 2 CC6.1, ISO 27001:2022 A.5.17.

> **Scope note (2026-09-25).** This runbook was carried from
> `jolarca-infrastructure`, where it described `terraform/modules/github-org`.
> That module is now superseded by this repository. Paths, script names,
> workflow names and secret names below have been corrected to match what
> actually exists here. Infrastructure credentials (SOPS, ansible-vault,
> Cloud KMS, WireGuard, Vault unseal) are **not** rotated from this repo — see
> `../security/key-custody.md`.

## Credentials in scope

| Secret | Type | Used by | Purpose |
|---|---|---|---|
| `TF_GITHUB_TOKEN_READONLY` | repo secret | `plan.yml`; `compliance-scan.yml` (policy, fleet-separation, drift jobs); `fleet-separation-guard.yml`; the plan step of `apply.yml` | read the org, plan, detect drift |
| `TF_GITHUB_TOKEN` | **environment** secret on `production` | `apply.yml` (the apply step only) | write to the live org |

Both fall back to the built-in `secrets.GITHUB_TOKEN` where a job can be
satisfied by it; that fallback cannot manage other repositories, so a missing
PAT surfaces as a permission error rather than a silent pass.

**Where the secrets live — repo, not org.** ADR-0004 R4 states marketplace
workflows use repo-scoped secrets only, never org secrets. Since the
marketplace moved to its own org on 2026-09-02 (ADR-0004 Amendment 2) an
org-level secret in `jolarca-dev` can no longer be read by a mission repo, so
R4's original leak concern is structurally resolved. Repo scope remains the
required default here anyway, on least-privilege grounds: this token is needed
by exactly one repository. Do not promote it to org scope without a recorded
reason.

## Preconditions

- You are a named custodian in `../security/key-custody.md`.
- A replacement token already generated (fine-grained PAT where the plan
  supports it, otherwise classic) with the minimum scope for its role — see
  the least-privilege note above `provider "github"` in `../../main.tf`:
  `repo` + `read:org` covers repository CRUD, branch protection and file
  content; `admin:org` is needed only for the org-level webhook in
  `org-settings.tf`, and only when `audit_webhook_url` is set.
- Announce the window in the operator channel (rotation is an audited event).
- The read-only and write tokens are **separate** credentials. If they are
  still the same shared PAT, this rotation must split them (tracked deviation 1
  in `../security/key-custody.md`).

## Steps

1. Generate the new PAT in GitHub with the shortest viable expiry (90 days).
2. Update the repo secret `TF_GITHUB_TOKEN_READONLY` on `jolarca-control`.
3. Update the environment secret `TF_GITHUB_TOKEN` on the `production`
   environment of `jolarca-control`.
4. **Verify the read path:** `python3 scripts/drift_detect.py` exits 0 against
   the live org with the new read token exported as `GITHUB_TOKEN`. Expect the
   known-open findings (D-01 visibility, and `jolarca-control` missing from the
   org until runbook step 2 lands) and no *new* ones.
5. **Verify the write path without applying.** `apply.yml` is hard-gated on
   `vars.STATE_MIGRATION_COMPLETE == 'true'`, so dispatching it proves nothing
   about the token — it exits at the gate. Instead check the token directly:
   ```bash
   GH_TOKEN="$NEW_WRITE_TOKEN" gh api -i orgs/jolarca-dev 2>&1 | grep -i '^x-oauth-scopes'
   GH_TOKEN="$NEW_WRITE_TOKEN" gh api orgs/jolarca-dev -q .login   # expect jolarca-dev
   ```
   Confirm the reported scopes match step 3's intent and nothing broader.
   After `STATE_MIGRATION_COMPLETE` flips, the plan step inside `apply.yml`
   exercises the write token end-to-end and this manual check becomes
   redundant — keep it only while the gate is closed.
6. **Revoke the old token.** An unrevoked old token defeats the rotation
   entirely; this is the step most often skipped.
7. Record: a `CHANGELOG.md` entry, the append-only log at the bottom of this
   file, and a compliance-evidence entry in `jolarca-compliance` (date,
   operator, reason). The access review that reconciles this register lives in
   `jolarca-infrastructure/security/access-review.md` — it was **not** ported to
   this repo, so raise the review there.

## Verification

- The scheduled `drift-detection` job inside `compliance-scan.yml` passes on
  its next run with the new token.
- `plan.yml` completes on a trivial PR (touch a `repos/*.yml` comment).
- No workflow references the old token — GitHub shows zero usage for it after
  24h.
- `fleet-separation-guard.yml` next run is green.

## If the token is suspected compromised

Skip the window: **revoke first**, then rotate, then treat as an incident
(`../../SECURITY.md`) and review recent workflow runs and apply history for
unauthorized changes. Because this token can write to every repository in a
PCI-DSS-scoped org, a suspected compromise additionally requires:

- checking for new/removed branch protections (`python3 scripts/drift_detect.py`
  plus a manual `gh api repos/jolarca-dev/<repo>/branches/main/protection`),
- checking for out-of-band repositories (`scripts/check_fleet_separation.sh`),
- and reviewing collaborator and deploy-key changes across the fleet.

## Environment gate — enforceability caveat

`apply.yml` declares `environment: production`, which is the intended manual
approval point. Whether a *required reviewer* can actually be attached depends
on the org plan and repository visibility; deviation 2 in
`../security/key-custody.md` records that it could not be enforced on private
repos under the plan in force when that note was written. While D-01 leaves the
fleet public, environment protection rules are available — but do **not** rely
on a gate whose enforceability you have not confirmed in the UI. Verify before
each rotation and update the deviation record with what you find.

## Log (append-only)

| Date | Operator | Reason | Read token split from write | Old token revoked | Verified |
|------|----------|--------|-----------------------------|-------------------|----------|
| —    | —        | —      | —                           | —                 | —        |
