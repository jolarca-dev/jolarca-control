# Architecture — Jolarca Control Plane

## Overview

`jolarca-control` is the governance control plane for the `jolarca-dev` GitHub
organization — the **marketplace** tree. It enforces a consistent security and
compliance baseline across six repositories using Infrastructure as Code
(Terraform), a declarative YAML allow-list, and automated compliance gates.

It is the marketplace counterpart of `jol-control`, which governs the
**mission-platform** tree (`journeyoflife-org`). The two are deliberately
separate control planes over separate organizations: ADR-0004 requires that
PCI-DSS-scoped marketplace governance never share state, credentials, or
resource handles with mission-platform governance. `scripts/check_fleet_separation.sh`
and the `precondition` in `repositories.tf` both enforce that boundary.

> **Current status: NOT YET AUTHORITATIVE.** The GitHub resources described
> here are still owned by the Terraform state in `jolarca-infrastructure`.
> See `docs/state-migration-runbook.md` and the banner in `main.tf`.

## Compliance Scope

| Framework | Version | Scope |
|-----------|---------|-------|
| SOC 2 Type II | 2017 TSC | All repositories |
| GDPR | Regulation (EU) 2016/679 | All repositories (27 EU member states) |
| ISO 27001 | 2022 Annex A | All repositories |
| PCI-DSS | 4.0 | **All repositories** — the entire marketplace tree is in or adjacent to the CDE |

PCI-DSS applying fleet-wide is the main divergence from `jol-control`, where it
is scoped to payment-related repos only.

## Architecture Diagram

```
┌────────────────────────────────────────────────────────────────────┐
│                      jolarca-control (this repo)                    │
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│  repos/*.yml              policy/                 Terraform         │
│  ───────────              ──────                  ─────────         │
│  Per-repo allow-list      repo-defaults.yml       main.tf           │
│  (6 YAML files)           compliance-gates.yml    variables.tf      │
│                                                   repositories.tf   │
│                                                   branch-protection │
│                                                   health-repo.tf    │
│                                                   org-settings.tf   │
│                                                   outputs.tf        │
│                                                                    │
│  .github/workflows/       audit/                  scripts/          │
│  ──────────────────       ─────                   ────────          │
│  plan.yml                 soc2-checklist.yml      validate_repos.py │
│  apply.yml                gdpr-checklist.yml      compliance_check  │
│  compliance-scan.yml      iso27001-checklist.yml  drift_detect.py   │
│  fleet-separation-        pci-dss-checklist.yml   check_fleet_      │
│    guard.yml                                        separation.sh  │
│                                                   org_delivery_     │
│                                                     audit.sh        │
└───────────────────────────────┬────────────────────────────────────┘
                                │
                         Terraform Apply
                    (gated: STATE_MIGRATION_COMPLETE)
                                │
               ┌────────────────┴────────────────┐
               │   GitHub Organization           │
               │   jolarca-dev                   │
               ├─────────────────────────────────┤
               │                                 │
               │  ┌────────────────────────┐     │
               │  │ governance (3)         │     │  status checks only (D-20)
               │  │ control, compliance,   │     │  0 approving reviews (D-04)
               │  │ legal                  │     │
               │  └────────────────────────┘     │
               │  ┌────────────────────────┐     │
               │  │ platform (2)           │     │  status checks only (D-20)
               │  │ jolarca, data          │     │
               │  └────────────────────────┘     │
               │  ┌────────────────────────┐     │
               │  │ devops (1)             │     │  status checks only (D-20)
               │  │ infrastructure         │     │  + IaC scan/policy
               │  └────────────────────────┘     │
               │  ┌────────────────────────┐     │
               │  │ org health repo        │     │  minimal protection,
               │  │ .github (health-repo.tf)│    │  serves SECURITY.md org-wide
               │  └────────────────────────┘     │
               └─────────────────────────────────┘
```

## Tier Model

| Tier | Repos | Approving reviews | Code Owners | Compliance gates |
|------|-------|-------------------|-------------|------------------|
| governance | 3 — `jolarca-control`, `jolarca-compliance`, `jolarca-legal` | 0 (D-04) | Required but **inert** (D-20) | All, incl. IaC scan + IaC policy + plan review |
| platform | 2 — `jolarca`, `jolarca-data` | 0 (D-04) | Required but **inert** (D-20) | dependency, secret, license, quality, SAST, container |
| devops | 1 — `jolarca-infrastructure` | 0 (D-04) | Required but **inert** (D-20) | dependency, secret, license, quality, SAST, IaC, container |

The `site` and `template` tiers used by `jol-control` do not exist here — the
marketplace has no per-church site fleet.

**Approving-review count is 0 fleet-wide**, verified against the live API on
2026-09-25. This is a tracked solo-era deviation, not an oversight: with one
operator a count of 1+ is unsatisfiable and would lock the maintainer out.

**Enforcement therefore rides on required status checks ALONE.** CODEOWNERS
review is configured (`require_code_owner_reviews = true`) but **does not fire**
— see **D-20**. The referenced teams do not exist in `jolarca-dev`, which has
zero teams, and five of the six repositories name *mission-org* teams. Proven
empirically: `jolarca-infrastructure` PR #26 merged with zero reviews and zero
requested reviewers, and every other sampled merged PR in the fleet also shows
zero reviews. An earlier revision of this document claimed CODEOWNERS "is
satisfiable because the sole operator is a listed code owner"; that was wrong on
two counts — the operator is the PR *author* and cannot approve their own pull
request, and GitHub does not enforce the requirement here at all.

The practical consequence for this architecture: **there is no human review
gate in the fleet today.** Change control rests on automated gates — required
status checks, the `apply.yml` plan-refusal gate, `prevent_destroy`, and the
`STATE_MIGRATION_COMPLETE` hard gate. See `docs/drift-findings.md` D-04/D-20 and
`docs/security/key-custody.md`.

## Data Flow

1. **Define** — edit `repos/<name>.yml`; that file is the single source of truth
   for the repository's settings.
2. **Validate** — `scripts/validate_repos.py` checks the YAML against
   `policy/repo-defaults.yml`, including the ADR-0004 naming rule and the
   data-classification ↔ visibility coherence rule.
3. **Plan** — a PR triggers `plan.yml`: `fmt -check` → `init` → `validate` →
   gated `plan`, posted back as a sticky PR comment.
4. **Guard** — `fleet-separation-guard.yml` proves the org's `jolarca*` set
   still equals the allow-list (ADR-0004 R2).
5. **Apply** — merge to `main` triggers `apply.yml`, which runs behind the
   `production` environment's manual approval gate and **refuses any plan
   containing a destroy, a replace, or a visibility change**.
6. **Monitor** — weekly `compliance-scan.yml` re-validates the allow-list,
   re-runs the compliance report, and diffs declared state against the live
   org via `drift_detect.py`.

## State Management

**Current reality, not aspiration:**

- No remote backend. Both this root and the predecessor root in
  `jolarca-infrastructure` use **local** `terraform.tfstate`.
- `*.tfstate` / `*.tfstate.*` are gitignored — state is never committed.
- The predecessor state is a **single copy on one host** plus one `.backup`.
  That is finding **D-02** and it blocks the migration.
- Concurrency is controlled by the `terraform-apply-jolarca-dev` workflow
  concurrency group with `cancel-in-progress: false`, so a second apply queues
  rather than racing.

Target state is a remote GCS backend reached through Workload Identity
Federation — see `docs/runbooks/workload-identity-federation.md`. Completing
that migration is prerequisite step 0 of `docs/state-migration-runbook.md`.

State contains resource IDs and repository metadata but no credentials; the
GitHub token is read from `GITHUB_TOKEN` at runtime and never written to state
or to `terraform.tfvars`.

## Team Access

**Verified 2026-09-25: `jolarca-dev` has no teams.** `gh api
orgs/jolarca-dev/teams` returns an empty list. The org has exactly one member
and all access is via org ownership.

`policy/repo-defaults.yml` therefore declares `teams: {}` rather than
inventing teams that do not exist — a control plane that asserts a nonexistent
RBAC model is worse than one that admits the gap. Consequences, tracked as
**D-10**:

- ISO 27001 A.5.3 (segregation of duties) is unsatisfiable.
- Every access review is self-review.
- PCI-DSS Req 7 (least privilege) has no enforcement mechanism.
- Org defaults are permissive: `default_repository_permission = read`,
  `members_can_create_repositories = true`, and **two-factor authentication is
  not enforced org-wide** (D-18).

Team creation is the second-operator onboarding task; raising D-04 to 1
approving review is gated on it.
