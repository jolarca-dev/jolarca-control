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

Current assignments, matching `repos/*.yml` exactly:

| Repository | Tier | Classification | Visibility (declared) | Rationale |
|---|---|---|---|---|
| `jolarca` | platform | public | public | Deliberately open-source marketplace application, AGPL-3.0 |
| `jolarca-control` | governance | confidential | private | Control definitions and the org's governance posture |
| `jolarca-compliance` | governance | confidential | private | DPIAs, RoPA, audit evidence |
| `jolarca-legal` | governance | confidential | private | Contracts, DPAs, terms, VAT OSS filings |
| `jolarca-data` | platform | confidential | private | Schemas and migrations disclose the PII and payment data model |
| `jolarca-infrastructure` | devops | confidential | private | Network topology, hostnames, WireGuard/VLAN layout, Vault config |

No repository in this fleet is classified `restricted`. That is a deliberate
invariant, not an omission: `jolarca-data` holds schemas and synthetic data
only, and cardholder data never enters git anywhere in the marketplace tree.
If a repo ever needs `restricted`, the data does not belong in that repo.

> The four `private` declarations above disagree with live reality — all four
> are currently public. That is **D-01**, an open blocking decision, not a
> settled state.

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

