# ADR-0004: Mission platform / marketplace separation (one org, two projects)

- **Status:** Accepted (operator directive, 2026-08-15) — **partly superseded
  by fact; see Amendment 2**
- **Date:** 2026-08-15
- **Deciders:** org owner (solo era)

> ### Porting note (2026-09-25) — read before relying on any path below
>
> This is a **dated decision record**. Under the rename-registry immutability
> doctrine (`jol-infrastructure/docs/compliance/rename-registry-jolm-to-jolarca.md`)
> the body below is preserved **verbatim and is not rewritten**, even where it
> is now stale. This block resolves the stale names; the body stays as evidence
> of what was decided on 2026-08-15.
>
> | In the body below (2026-08-15) | True today (2026-09-25) |
> |---|---|
> | prefix `jol-m-*` | `jolarca*` (renamed 2026-08-31) |
> | org `journeyoflife-org` hosts both projects | marketplace moved to its own org **`jolarca-dev`** (2026-09-02) — Amendment 2 |
> | local tree `/opt/jol-m/repos/` | `/opt/jolarca/repos/` |
> | `terraform/modules/github-org` (in `jolarca-infrastructure`) | this repo: `repositories.tf`, `branch-protection.tf`, `health-repo.tf`, `org-settings.tf` |
> | fleet map in `modules/github-org/variables.tf` | `repos/*.yml` declarative allow-list |
> | `scripts/check-fleet-separation.sh` | `scripts/check_fleet_separation.sh` |
> | `security/access-review.md` | lives in `jolarca-infrastructure`; **not ported** — see `docs/security/key-custody.md` |
>
> The title's premise "(one org, two projects)" described the state of the world
> on 2026-08-15 and is retained because that is what was decided. It is no
> longer true; Amendment 2 records why.

## Context

The `journeyoflife-org` GitHub organization hosts TWO distinct projects
that share nothing but the org shell:

| Project | Scope | Prefix | Local tree | Compliance scope |
|---|---|---|---|---|
| Journey of Life — Roman Catholic digital mission platform | pastoral/mission services | `jol-*` | `/opt/jol/repos/` | outside marketplace scope |
| Journey of Life — Marketplace | Baltic B2C/B2B commerce | `jol-m-*` (m = marketplace) | `/opt/jol-m/repos/` | PCI-DSS (Stripe), GDPR, KYC/AML, VAT OSS, SOC 2 / ISO 27001 evidence |

Mixing them is a compliance boundary violation, not a style preference:

- **GDPR purpose limitation (Art. 5(1)(b), Art. 32):** mission data
  (religious-context processing) and marketplace data
  (commercial/financial processing) are different processing purposes;
  shared tooling, tokens, or agent context creates unlawful scope bleed.
- **PCI-DSS scope control:** the marketplace carries card-payment scope;
  every person/token/repo with access to it expands the audit surface.
  Mission repos must stay OUT of that surface.
- **SOC 2 CC6.1:** logical access boundaries must be defined and
  enforced between distinct systems.

GitHub has no folder/group construct for repositories — "marketplace/"
naming is not available. Separation must therefore be conventional,
technical, and monitored.

## Decision — the rules (R1–R7)

- **R1 — Prefix covenant.** Marketplace repositories are `jol-m-*` and
  NOTHING else; mission repositories are `jol-*` (without `m`). No other
  prefix joins either fleet. The marketplace fleet is exactly:
  `jolarca`, `jolarca-infrastructure`, `jolarca-compliance`,
  `jolarca-legal`, `jolarca-data`.
- **R2 — Terraform is the only creator.** Marketplace repos are created
  ONLY via `terraform/modules/github-org`. Out-of-band creation is an
  incident: import into state within 48h or delete the repo.
- **R3 — Enforced, not hoped for.**
  - module validation rejects non-`jol-m-*` fleet keys
    (`terraform/modules/github-org/variables.tf`);
  - `scripts/check-fleet-separation.sh` + the
    `fleet-separation-guard.yml` workflow fail when the org's `jol-m-*`
    set ≠ the fleet map (weekly + on change).
- **R4 — No cross-project access artifacts.** No shared repo/environment
  secrets across projects; marketplace workflows use repo-scoped
  secrets only (never org secrets); no CODEOWNERS, workflow, or module
  in one project references the other's repos.
- **R5 — Local and agent separation.** Distinct directory trees
  (`/opt/jol/repos` vs `/opt/jol-m/repos`); one project root per IDE
  window; agent memory/instructions must not span both projects.
- **R6 — Metadata marking.** Marketplace repos carry the `marketplace`
  topic; visibility/license policy lives in the fleet map
  (`jolarca` public+AGPL-3.0 by doctrine, all others private).
- **R7 — Split triggers.** The shared org is re-evaluated — migrating
  marketplace to its own org — upon ANY of: a second operator joins;
  marketplace gains external contributors; PCI scope expands beyond the
  current boundary; billing must separate. A separate org is the only
  true hard boundary; until then R1–R6 are the compensating controls.

## Alternatives considered

- **Separate GitHub org now** (e.g. `jol-marketplace` org): strongest
  isolation (IAM, secrets, policies, billing) but doubles Team-plan
  cost and migration effort (remotes, CI tokens, WIF trust, TF org
  variable) for a solo operator. Deferred to the R7 triggers.
- **Repo "folders"/groups: not a GitHub feature.** Naming prefix +
  topics + teams are the available constructs; prefix is the only one
  that is grep-able, guard-able, and typo-proof.
- **Status quo (convention only):** already failed once — repos created
  out-of-band, protections missing, drift undocumented. Rejected.

## Consequences

- (+) Mission platform stays outside the PCI/marketplace audit surface.
- (+) Any marketplace repo drift becomes a failing CI check, not folklore.
- (−) Every new marketplace repo must go through Terraform (by design).
- (−) Org-level settings (secrets, webhooks, apps) remain shared and
  MUST be audited: org secrets must never be visible to marketplace
  workflows (token-scope gap: current CI token cannot list org secrets).
  **Closed 2026-08-15:** org owner audited the org settings UI and
  verified no org-level secret is visible to marketplace workflows
  (R4 evidence; re-verify on every access review —
  `security/access-review.md`).

## Compliance mapping

GDPR Art. 5(1)(b)/Art. 32 (purpose limitation, security of processing);
PCI-DSS scope isolation; SOC 2 CC6.1 (logical access), CC8.1 (change
control — Terraform-only creation); ISO 27001 A.5.2/A.5.15 (governance
of information security, access control).

## Amendments

### Amendment 1 — payment-boundary exception (2026-08-17, via ADR-0005)

Ratified with ADR-0005 (Model A — single payment boundary). This is the
ONE documented exception to the Two-Program Doctrine; all other rules
stand unchanged.

- **R4 gains a single documented exception.** Cross-program code
  dependency between mission and marketplace remains FORBIDDEN, EXCEPT
  the payment API: the designed shared boundary exposed by the
  marketplace `payments_app` and consumed by `jol-hub`, with its own
  security requirements (mTLS, HMAC-signed requests with replay TTL,
  mandatory idempotency keys, service-account caller binding, PAN-free
  payloads) defined in ADR-0005 and `docs/payment-api-contract.md`.
  Governance documents may reference the boundary; shared code, state,
  secrets, and CI remain forbidden. Adding any other cross-program
  interface requires a new ADR.
- **Hub prohibitions (enforced, not advisory).** jol-hub must NOT import
  `stripe` (server-side), must NOT hold Stripe API keys, and must NEVER
  see PAN data. Enforcement is structural: CI grep + dependency
  allow-list guard in hub (ADR-0005 E1/E2) and network egress denial to
  `api.stripe.com` (E3, `security/network-policy.md`). The only
  sanctioned hub-side Stripe artifact is the browser-only Stripe.js
  Elements include required by the SAQ-A donation flow.
- **R1 clarification.** The mission program's flagship repository is
  `jol-hub`; it complies with the mission prefix `jol-*` (without `m`).
  It is created/managed by mission-program IaC (future mission infra
  root under `/opt/jol/repos/`), NOT by this repo's `github-org` module
  (mission resources must never enter marketplace Terraform state); the
  fleet guard compares only the `jol-m-*` set and does not flag it.

### Amendment 2 — the R7 split trigger FIRED (2026-09-25, recorded in `jolarca-control`)

**R7 is no longer a deferred option. It happened.** The marketplace fleet was
transferred out of `journeyoflife-org` into its own GitHub organization,
**`jolarca-dev`**, on **2026-09-02** (evidence:
`jol-infrastructure/docs/compliance/evidence/change-record-org-transfer-jolarca-dev-20260902.md`).
This amendment records the consequence for each rule. The dated body above is
unchanged.

- **The title's premise is superseded by fact.** "One org, two projects" was
  the accepted design on 2026-08-15. Since 2026-09-02 the two programs occupy
  **separate organizations**, which is exactly the hard boundary R7 named as
  "the only true hard boundary". The separation is now structural rather than
  conventional.
- **R1–R6 change status: compensating controls → defence in depth.** The body
  says "until then R1–R6 are the compensating controls". That condition has
  lapsed. R1–R6 all still stand and are still enforced, but they are no longer
  load-bearing on their own — org-level IAM, secrets, and policies now provide
  the primary boundary. **Practical effect: a mission token can no longer reach
  a marketplace repo at all**, which is a strictly stronger guarantee than the
  prefix convention ever gave.
- **R1 (prefix covenant) is unaffected in substance but renamed.** The
  marketplace prefix is now `jolarca*`, not `jol-m-*` (renamed 2026-08-31).
  Enforcement is unchanged and now stricter: the regex
  `^jolarca(-[a-z0-9-]+)?$` is asserted as a Terraform `precondition` in
  `repositories.tf`, so a non-conforming fleet entry fails `plan` rather than
  only failing a weekly guard.
- **R2 (Terraform is the only creator) now lives in this repository.** The
  marketplace GitHub-org control plane moved from
  `jolarca-infrastructure/terraform/modules/github-org` to `jolarca-control`
  (`repositories.tf`, `branch-protection.tf`, `health-repo.tf`,
  `org-settings.tf`). **One documented exception is recorded here:** creating
  `jolarca-control` itself could not be done by Terraform, because a root that
  manages its own repository cannot bootstrap itself. It was created
  out-of-band on 2026-09-25 and is being imported into state per
  `docs/state-migration-runbook.md` step 2. The 48-hour import-or-delete rule
  in R2 is satisfied by that runbook.
- **R3 (enforced, not hoped for) — both halves still run.** Allow-list
  validation moved into `scripts/validate_repos.py` + the `repositories.tf`
  precondition; the org-vs-fleet comparison moved into
  `scripts/check_fleet_separation.sh` + `.github/workflows/fleet-separation-guard.yml`
  and is additionally checked by `scripts/drift_detect.py` (membership,
  visibility, wiki, archive state).
- **R4 (no cross-project access artifacts) is now structurally satisfied for
  secrets and CI**, because org secrets and org-level CI configuration are
  per-org and the two programs no longer share an org. The Amendment 1 payment
  API exception (ADR-0005) is **unchanged and remains the only sanctioned
  crossing**. **However R4 is violated in live production on its third
  clause** — "no CODEOWNERS, workflow, or module in one project references the
  other's". Five PCI-DSS-scoped marketplace repositories carry
  `.github/CODEOWNERS` files naming `@journeyoflife-org/*` teams (and `jolarca`
  names `@jol-infrastructure/*`, an organization that does not exist). GitHub
  copied that content verbatim through the 2026-09-02 transfer and does not
  rewrite team references, so the marketplace's reviewer-of-record points at the
  mission org. Recorded as **D-20 (blocking)** in `docs/drift-findings.md`,
  which also documents that this voids the code-owner control the compliance
  narrative relied on. Correcting the CODEOWNERS files is required by R4
  independently of any team-creation decision.
- **R5 (local and agent separation) is unchanged and now matches the org
  boundary:** `/opt/jol/repos` ↔ `journeyoflife-org`, `/opt/jolarca/repos` ↔
  `jolarca-dev`. One project root per IDE window still applies.
- **R6 (metadata marking) is unchanged**, and `drift_detect.py` now detects
  visibility drift too — which is how the open finding **D-01** (four
  PCI-DSS-scoped repositories found `public` in the live org while the intent
  of record is `private`) was discovered. See `docs/drift-findings.md`.
- **R7 status: CLOSED — trigger fired and was acted on.** R7 stays on the books
  as a standing obligation: if the marketplace org boundary is ever weakened
  (e.g. merging orgs, or granting a mission identity access to `jolarca-dev`),
  R7 re-opens and requires a new decision record.

**Which R7 trigger fired, per the record of authority.** Change record
`JOL-ORGTRANSFER-20260902-01` (status EXECUTED, effective 2026-09-02) gives
three reasons, quoted in substance:

1. **Audit narrative / liability commingling** — if the mission is ever audited
   (canonical or civil), the `journeyoflife-org` repositories must prove they
   are not operating a for-profit SaaS; commingled repos equal commingled
   liability.
2. **Secret isolation** — `jolarca-dev` can hold commercial CI/CD secrets
   (Stripe, commercial cloud accounts) without exposing the mission's donation
   processor keys.
3. **ISO 27001:2022 A.8.13** — the two-tree segregation already enforced at the
   filesystem and OS-identity layers now extends to the source-control layer.

Its stated authority is SOC 2 CC8.1 change control and ISO 27001 A.8.13.
Reasons 1 and 2 are the **billing must separate** and **PCI scope expands
beyond the current boundary** triggers in R7's list, so the decision is executed
as written rather than renegotiated. The record also confirms R5: the mission
org holds only church-platform repos (GDPR Art. 9, donation PCI-DSS) and the
commercial org holds marketplace repos (KYC/AML, VAT OSS, commercial PCI-DSS,
Stripe keys).

**Post-transfer observation carried into this repo (finding D-01).** The change
record's pre-transfer table lists `jolarca-data` as **private** and the other
four as public. Re-verified against the live API on 2026-09-25, **all six**
repositories in `jolarca-dev` are now `visibility: public`, including
`jolarca-data`. The intent of record in the fleet definition is `private` for
all five non-`jolarca` repos. `jolarca-data` therefore has a *dated* private
baseline and a *verified* public present state — a regression, not merely an
undeclared divergence. The exact flip time cannot be pinned from here: the REST
audit-log endpoint returns HTTP 404 for this org plan. Tracked as **D-01**
(blocking) in `docs/drift-findings.md`; resolution is gated by
`docs/state-migration-runbook.md` step 7.

**Compliance mapping (unchanged, now stronger):** GDPR Art. 5(1)(b)/Art. 32;
PCI-DSS scope isolation; SOC 2 CC6.1, CC8.1; ISO 27001 A.5.2/A.5.15/A.8.13.
