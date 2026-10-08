# Threat Model — Jolarca Control Plane

## Methodology

STRIDE (Spoofing, Tampering, Repudiation, Information Disclosure, Denial of
Service, Elevation of Privilege).

Every mitigation below states the control that **actually exists today**.
Where a control is aspirational, it is marked as a gap with its finding ID from
`docs/drift-findings.md` rather than being listed as if it worked.

## System Boundaries

```
                ┌──────────────────────────────────────┐
                │           GitHub Platform            │
                │  ┌────────────────────────────────┐  │
                │  │  jolarca-dev (marketplace org) │  │
                │  │  ┌──────────────────────────┐  │  │
                │  │  │      jolarca-control     │  │  │
                │  │  │  (Terraform + policy +   │  │  │
                │  │  │   allow-list + gates)    │  │  │
                │  │  └────────────┬─────────────┘  │  │
                │  │               │                │  │
                │  │  ┌────────────▼─────────────┐  │  │
                │  │  │  6 managed repos +       │  │  │
                │  │  │  org health repo .github │  │  │
                │  │  └──────────────────────────┘  │  │
                │  └────────────────────────────────┘  │
                └──────────────────┬───────────────────┘
                                   │
                ┌──────────────────▼───────────────────┐
                │   Operator host (/opt/jolarca)       │
                │  ┌────────────────────────────────┐  │
                │  │  LOCAL terraform.tfstate       │  │
                │  │  no remote backend  ← D-02     │  │
                │  │  gitignored, single copy       │  │
                │  └────────────────────────────────┘  │
                │  ┌────────────────────────────────┐  │
                │  │  GITHUB_TOKEN (env, runtime)   │  │
                │  │  TF_GITHUB_TOKEN (Actions)     │  │
                │  └────────────────────────────────┘  │
                └──────────────────────────────────────┘

   SEPARATE ORG — no shared state, credentials or resource handles:
                journeyoflife-org  ←  jol-control (mission platform)
```

The org boundary between `jolarca-dev` and `journeyoflife-org` is a compliance
control (ADR-0004, ISO 27001 A.8.13), not a convenience. D-03 records a live
breach of it in the predecessor state.

## Threat Register

| ID | Category | Threat | Risk | Mitigation **as implemented** | Control | Gap |
|----|----------|--------|------|-------------------------------|---------|-----|
| T-01 | Tampering | Unreviewed code pushed to `main` | High | Branch protection on all six repos: `enforce_admins`, force-push and deletion blocked, linear history, conversation resolution, non-empty required status checks | `github_branch_protection.main` | **No human review exists.** Approving-review count is 0 (D-04) and CODEOWNERS review is configured but inert (D-20 — verified: PR #26 merged with zero reviews). Mitigation is automated-only. |
| T-02 | Spoofing | Compromised operator account | **Critical** | Signed operator commits attribute every change to a key holder; token rotation runbook | `commit_signing_policy` | **Org-wide 2FA is NOT enforced** (verified `two_factor_requirement_enabled: false`) — D-18. Signature enforcement at the protection layer is off — D-05 |
| T-03 | Info Disclosure | Secrets committed to git | Critical | Secret scanning + push protection declared on every repo; gitleaks in fleet CI; secret-pattern sweep in `compliance-scan.yml`; `*.tfstate`, `.env`, key patterns gitignored | `security_and_analysis`, `.gitignore` | — |
| T-04 | Info Disclosure | Terraform state exposes resource metadata | Medium | State gitignored and never committed; token supplied at runtime only, never stored in state or tfvars | `.gitignore` | **No encryption at rest and no access control** — state is a plaintext file on one host: D-02 |
| T-05 | Elevation | Attacker gains org admin | Critical | Single-member org reduces the attack surface; org audit-log webhook declared in `org-settings.tf` when a URL is supplied | `github_organization_webhook` | No teams, so no least-privilege separation — D-10. Audit webhook is not currently configured |
| T-06 | Tampering | Concurrent applies corrupt state | High | `concurrency: terraform-apply-jolarca-dev` with `cancel-in-progress: false` serialises runs; `prevent_destroy` on every repository | `apply.yml` | **No state locking** — there is no backend, so nothing prevents a local apply racing a CI apply: D-02 |
| T-07 | DoS | GitHub API rate limiting during apply | Medium | Single-stage apply (no dev→staging→prod re-planning); fleet is six repos | `apply.yml` | — |
| T-08 | Info Disclosure | Public repos expose PCI-scope detail | **Critical** | `validate_repos.py` fails any repo whose `data_classification` is confidential/restricted while `visibility` is public; `apply.yml` refuses plans that change visibility | allow-list coherence rule | **Live right now**: `jolarca-compliance`, `jolarca-legal`, `jolarca-data`, `jolarca-infrastructure` are public — D-01, UNDECIDED |
| T-09 | Repudiation | Change without an audit trail | High | Squash-only merges keep one commit per change; PR + `production` environment approval; compliance snapshot uploaded as a 90-day artifact; change record required per `docs/change-management.md` | `apply.yml`, `policy/` | — |
| T-10 | Tampering | Rogue `terraform destroy` deletes real repos | **Critical** | `lifecycle { prevent_destroy = true }` on `github_repository.repo` and `.health`; `apply.yml` aborts on any `will be destroyed` or `must be replaced` in the plan | Terraform lifecycle + CI gate | Old root in `jolarca-infrastructure` is frozen with the same guard — verify per runbook step 1 |
| T-11 | Elevation | Unauthorized team or membership change | High | No teams exist to tamper with; membership changes are visible in the org audit log | org settings | 2FA not enforced — D-18; `members_can_create_repositories: true` and `default_repository_permission: read` are permissive — D-19 |
| T-12 | Info Disclosure | Supply-chain attack via dependency or CI action | High | Dependency-review gate; Dependabot alerts on all six repos; **every** action in this repo's workflows is pinned to a full commit SHA, not a tag | `dependency_scan` gate, SHA pins | — |
| T-13 | Tampering | Mission/marketplace scope bleed | High | ADR-0004 enforced three ways: `precondition` in `repositories.tf`, naming rule in `validate_repos.py`, and `check_fleet_separation.sh` R1/R2/R3 in CI | defense in depth | Predecessor state owns `journeyoflife-org/.github` — D-03 |
| T-14 | Tampering | Out-of-band repo creation escapes the allow-list | Medium | `check_fleet_separation.sh` R2 compares the live org against `repos/*.yml` on every relevant change and weekly; ADR-0004 R2 requires import within 48 h | `fleet-separation-guard.yml` | `members_can_create_repositories: true` — D-19 |
| T-15 | Repudiation | Dual ownership — two roots manage one repo | **Critical** | `STATE_MIGRATION_COMPLETE` gate blocks apply entirely; migration runbook sequences `state rm` before `import` | `apply.yml`, runbook | **Open until runbook step 9** — D-13 |

## Risk Acceptance Register

An entry here means the organization owner has *decided*, in writing, with a
review date. Nothing is pre-accepted on the owner's behalf.

| ID | Risk | Status | Owner decision | Review by |
|----|------|--------|----------------|-----------|
| RA-01 | D-01 — four PCI-scope repos publicly readable | **OPEN — NOT ACCEPTED** | Required before first apply; see `docs/drift-findings.md` D-01 and runbook step 7 | — |
| RA-02 | D-04 — zero approving reviews fleet-wide, compounded by D-20 (CODEOWNERS inert) | Accepted (compensating controls: non-empty required status checks + signed operator commits + `enforce_admins` + `apply.yml` plan-refusal gate + `prevent_destroy`). **CODEOWNERS was removed from this list on 2026-09-25** — it was cited as compensating but provably never fires. | Remediate D-20 (create `jolarca-dev` teams, rewrite the six CODEOWNERS), then raise D-04 to 1 | On second-operator onboarding |
| RA-03 | D-05 — signature enforcement off at protection layer | Accepted (provider automation cannot sign; humans sign by policy) | Revisit when automation commit signing lands | 2026-12-25 |
| RA-04 | D-07 — `v*` tag protection declared but unenforced | Accepted, recorded honestly as `enforced: false` in policy | Implement via `github_repository_ruleset` | 2026-12-25 |
| RA-05 | D-02 — single-copy local state, no locking | **NOT ACCEPTABLE as a steady state** | Prerequisite step 0 of the migration runbook | Before apply |
| RA-06 | D-18 — org-wide 2FA | **CLOSED — enforced** | Verified live `two_factor_requirement_enabled: true` (2026-10-06); enabled in GitHub UI (not API-manageable). Satisfies PCI-DSS Req 8.3.1 / ISO 27001 A.5.17 | — |
| RA-07 | D-20 — fleet CODEOWNERS name mission-org teams (`@journeyoflife-org/*`, `@jol-infrastructure/*`) inside five PCI-scope marketplace repos | **OPEN — NOT ACCEPTED** | Live breach of ADR-0004 R4 and of boundary 1 in `docs/security/isolation-model.md`. Cannot be risk-accepted: the separation doctrine is the basis of the whole scope argument. Rewrite all six `.github/CODEOWNERS` to `jolarca-dev` principals; this needs a PR in each repo, not a change here | Before first apply |
