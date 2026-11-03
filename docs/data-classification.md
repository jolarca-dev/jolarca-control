# Data Classification Policy

## Classification Levels

| Level | Description | Examples | Git allowed | Repo visibility |
|-------|-------------|---------|-------------|-----------------|
| **Public** | Approved for public disclosure | Open-source application code, public docs | Yes | public |
| **Internal** | Internal use only, low harm if disclosed | Non-sensitive configs, internal tooling | Yes | public or private |
| **Confidential** | Sensitive business information | Audit evidence, contracts, data models, network topology, control definitions | Yes | **private — mandatory** |
| **Restricted** | PII, cardholder data, credentials, keys | Production customer records, PANs, private keys, API tokens | **No — vault only** | n/a |

`scripts/validate_repos.py` enforces the visibility column: a repository
classified `confidential` or `restricted` with `visibility: public` fails
validation. That check is the control that surfaced finding **D-01**.

## Repository Classification Assignments

Current assignments, read from `repos/*.yml` (16 entries) on 2026-10-19. The
command that reproduces this table is stated in **D-79**; do not hand-edit it
from memory — the previous table, last touched 2026-09-26 (`5a571ef`), still
listed six repositories with five of them `private`.

| Repository | Tier | Classification | Visibility (declared) |
|---|---|---|---|
| `jolarca` | platform | public | public |
| `jolarca-docs` | governance | public | public |
| the other 14 fleet repositories | governance / platform / devops | internal | public |

**How the visibility guard behaves today.** `scripts/validate_repos.py` refuses
a `confidential`/`restricted` repository declared `visibility: public` (GDPR
Art. 32, PCI-DSS Req 1.2), and separately refuses a `pci-dss` +
`launch_status: operational` repo that is public without
`documented_risk_acceptance: true` plus a dated entry in
`policy/compliance-gates.yml` `exceptions.active`. With all sixteen repos
classified `internal` or `public`, the first guard **fires on nothing** — it is
not a proof of safety. That is the recorded consequence of the
`confidential` → `internal` downgrade (**D-37**), which masked rather than
resolved **D-31**; the attempt to restore privacy by flipping repos private was
reverted the same day because it blinds Context Parity (**D-52**). The
remediation of D-31 is removing regulated records from public git, not
re-tagging the YAMLs.

No repository in this fleet is classified `restricted`, and that is a deliberate
invariant rather than an omission: `jolarca-data` holds schemas and synthetic
data only, and cardholder data never enters git anywhere in the marketplace
tree. If a repository ever needs `restricted`, the data does not belong in that
repository — see the store table below for where restricted data does live.

> Historical note, kept rather than deleted: until 2026-10-19 this section
> listed six repositories and asserted they matched `repos/*.yml` "exactly",
> with `jolarca-control`, `jolarca-compliance`, `jolarca-legal`, `jolarca-data`
> and `jolarca-infrastructure` classified `confidential`/`private`, plus a
> blockquote calling the resulting disagreement "**D-01**, an open blocking
> decision". All three claims were false when read: D-01 is resolved (GitHub
> moved the fleet public; every declaration now reads `visibility: public`),
> and no repo in the registry still declares `confidential`. This is the
> AGENTS.md §6 rule — documentation must state actual implementation status —
> applied to this file's own past text.

## Data stores outside git

Classification of a *repository* does not classify the data the fleet holds.
The regulated stores that live outside version control were registered here for
the first time on 2026-10-19 (**D-79**): before that, an auditor reading this
policy could conclude that no object store existed, while the marketplace
application's own ADR-0005 (in `jolarca`) names one as the location of KYC
documents.

| Store | Holds | Classification | Configured in | Status measured 2026-10-19 |
|---|---|---|---|---|
| Terraform state, marketplace estate | Handles and attributes for all 16 repos, branch protection, org webhook | Confidential | `main.tf` `cloud {}` → HCP Terraform org `jolarca-dev`, workspace `jolarca-control` (ADR-0006) | Live. Single authoritative copy; the off-host half of D-02 is still open (**D-55**). No S3/DynamoDB backend exists anywhere in the fleet — ADR-0006 rejected it, and a GCS custody stack in the sibling `jolarca-infrastructure` root is **half-applied** (CMEK keys and a service account in state, the buckets never in state; `gcloud` unreadable here, so live existence is could-not-verify). See **D-79**. |
| Terraform state backup | age-encrypted state export + `backup-log.tsv` manifest | Confidential | `scripts/state_backup.sh`, destination `BACKUP_DEST` | Verified export path with a proven decrypt round trip; **no schedule**, and destination plus age identity are on the same host as the working copy. |
| Application object storage (S3 API) | Media, **KYC identity documents, invoice PDFs** — `jolarca/docs/ARCHITECTURE_DECISION_RECORDS.md` ADR-0005 | **Restricted** | `jolarca` deployment: `AWS_S3_*` settings (`django-storages`), MinIO service in `jolarca/docker-compose.dev.yml` | Dev is visible in tracked files (MinIO + `mc anonymous set download`, so unauthenticated read). **No tracked file declares the production bucket**: `.env`/`.env.prod` are gitignored (`.gitignore:68-69`), only `.env.example` is tracked, and the local `.env.prod` read 2026-10-19 has `AWS_S3_ENDPOINT_URL`, `AWS_S3_BUCKET`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` and `BACKUP_S3_BUCKET` empty. The deployed value is therefore unverifiable from the repositories — which is the finding, not "prod has no bucket". |
| PostgreSQL of the marketplace application | Customer records, orders, ledger | Restricted | Outside this control plane (application deployment) | Not enumerated here; the record of processing is `jolarca-compliance/ropa/master-register.csv`, and this repo holds no evidence about its contents. |

Rules that follow from the table:

- **A new data store is registered here before it holds regulated data**, on the
  same terms as a new repository must be classified before its first commit
  (see Review Cadence). "It is only dev" is not an exemption.
- **Restricted data never enters git**, encrypted or not — the same boundary
  `docs/security/isolation-model.md` draws for state files.
- **Object-store exposure is not covered by the repository guard.**
  `validate_repos.py` reads YAML declarations, so a bucket's access policy is
  enforced by the bucket itself and not by this file. The measured dev exposure
  is the counter-example to the application's own claim: `jolarca` ADR-0005
  states "no public buckets anywhere", while
  `jolarca/docker-compose.dev.yml:64` runs `mc anonymous set download
  local/${AWS_S3_BUCKET}` — unauthenticated read on the dev bucket. Anything
  written there is readable by whoever can reach the host.
- **Backup claims must name a destination that exists in a governed artifact.**
  `jolarca/docs/DEPLOYMENT.md` lists "Media (S3/MinIO) → mirror to backup VM,
  nightly". Nothing tracked declares the bucket that row mirrors, so the claim
  cannot be verified, scheduled or evidenced from the repositories — the D-55
  failure class, a control present in documentation and never exercised. A
  non-secret identifier (bucket name, endpoint host, region) belongs in a
  tracked file; only the credentials belong in the vault.

## Handling Rules

### For Git Repositories
- **Public / Internal** — may be stored in public repositories.
- **Confidential** — private repository, mandatory. No exceptions via
  "there is nothing sensitive in it yet": classification follows the
  repository's purpose, not its current contents.
- **Restricted** — NEVER in git. Use Vaultwarden / HashiCorp Vault / GitHub
  Actions secrets. A restricted value found in git is an incident:
  `docs/runbooks.md` RB-03.

### Required .gitignore Patterns
All repositories MUST include these patterns in their `.gitignore`:
```
*.pem
*.key
*.p12
secrets.json
credentials.json
.env
.env.*
*.tfstate
*.tfstate.*
.terraform/
```

`policy/repo-defaults.yml` → `data_handling.required_gitignore_patterns` is the
machine-readable copy of this list; keep the two in sync.

## Review Cadence
- Classification assignments reviewed quarterly (`docs/runbooks.md` RB-05)
- Any new repository must be classified before its first commit
- Reclassification requires an organization-owner decision recorded in
  `docs/change-management.md`, and — when it lowers a classification — a
  written risk acceptance
