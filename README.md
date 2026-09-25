# jolarca-control

> Central governance control plane for the **`jolarca-dev`** GitHub
> organization — the Journey of Life **marketplace** tree.

[![Compliance: SOC2 | GDPR | ISO27001 | PCI-DSS 4.0](https://img.shields.io/badge/compliance-SOC2%20%7C%20GDPR%20%7C%20ISO27001%20%7C%20PCIDSS-blue)](#)
[![Terraform](https://img.shields.io/badge/IaC-Terraform-7B42BC)](#)

---

## ⚠ NOT YET AUTHORITATIVE

This repository declares the governance of six live, PCI-DSS-scoped
repositories — but **it does not own their Terraform state yet**. That state is
still in
`jolarca-infrastructure/terraform/environments/production/terraform.tfstate`
(`module.github_org.*`).

Consequences, all deliberate:

- `make apply` **refuses** to run.
- `.github/workflows/apply.yml` aborts unless the repository variable
  `STATE_MIGRATION_COMPLETE` is `true`.
- `.github/workflows/plan.yml` skips the live plan and says so on the PR
  instead of showing a misleading empty diff.
- `make plan` only offers an offline `-refresh=false` plan.

Applying from an empty state would attempt to **create repositories that
already exist** while another Terraform root still owns them. That is dual
ownership of production PCI scope, and it is how repositories get destroyed.

**Read [`docs/state-migration-runbook.md`](docs/state-migration-runbook.md)
before running anything.** It is a gated, reversible procedure with a verified
off-host backup as step 0.

Also read [`docs/drift-findings.md`](docs/drift-findings.md): 22 findings,
each verified against the live GitHub API on 2026-09-25, including two
**blocking** ones (D-01 four PCI-scope repos are publicly readable; D-18
org-wide 2FA is not enforced).

---

## Purpose

`jolarca-control` manages the `jolarca-dev` marketplace organization through:

- **Declarative allow-list** — one YAML file per repository (`repos/*.yml`)
- **Policy baselines** — enforced settings for every repo (`policy/`)
- **Terraform IaC** — GitHub resources provisioned via `terraform apply`
- **Compliance gates** — automated security checks on every PR
- **Fleet separation guard** — ADR-0004 mission/marketplace boundary, checked
  in CI and weekly
- **Audit checklists** — SOC 2, GDPR, ISO 27001, PCI-DSS control mappings

### Relationship to `jol-control`

| | `jol-control` | `jolarca-control` (this repo) |
|---|---|---|
| Organization | `journeyoflife-org` | `jolarca-dev` |
| Scope | Mission / church platform | Marketplace (PCI-DSS, KYC/AML, VAT OSS) |
| Host tree | `/opt/jol` | `/opt/jolarca` |
| Repos | 40 | 6 + org health repo |
| PCI-DSS | Payment-related repos only | **Every repo** |
| Approving reviews | 2 (governance) | 0 — solo-era deviation D-04 |

The two are separate control planes over separate organizations with separate
credentials and separate state. That separation **is** the control
(ADR-0004, ISO 27001 A.8.13); it is not an accident of history. Three
independent guards enforce it: a Terraform `precondition` in
`repositories.tf`, the naming rule in `scripts/validate_repos.py`, and
`scripts/check_fleet_separation.sh` in CI.

## Compliance

| Framework | Scope |
|-----------|-------|
| SOC 2 Type II | All repositories |
| GDPR (EU 2016/679) | All repositories — 27 EU member states |
| ISO 27001:2022 | All repositories — Annex A controls |
| PCI-DSS 4.0 | **All repositories** |

## Repository Structure

```
jolarca-control/
├── repos/                          # One YAML per repo = the allow-list
│   ├── jolarca.yml
│   ├── jolarca-control.yml
│   ├── jolarca-compliance.yml
│   ├── jolarca-data.yml
│   ├── jolarca-infrastructure.yml
│   └── jolarca-legal.yml
├── policy/                         # Enforced baselines for EVERY repo
│   ├── repo-defaults.yml           # Settings, branch protection, classification
│   └── compliance-gates.yml        # Gates + enforcement matrix + exceptions
├── main.tf                         # GitHub provider, version pins, freeze banner
├── variables.tf                    # Input variables (config of record)
├── repositories.tf                 # Fleet repositories, from repos/*.yml
├── branch-protection.tf            # Protection for the fleet + health repo
├── health-repo.tf                  # Org .github repo + inherited SECURITY.md
├── org-settings.tf                 # Org-level audit-log webhook
├── outputs.tf                      # Terraform outputs
├── terraform.tfvars                # Variable values (no secrets)
├── .github/
│   ├── CODEOWNERS                  # Routing only — NOT an enforced gate (D-20)
│   └── workflows/
│       ├── plan.yml                # fmt + validate + gated plan as PR comment
│       ├── apply.yml               # single gated production apply
│       ├── compliance-scan.yml     # allow-list, policy, drift, secret sweep
│       └── fleet-separation-guard.yml
├── audit/                          # Compliance checklists
│   ├── soc2-checklist.yml
│   ├── gdpr-checklist.yml
│   ├── iso27001-checklist.yml
│   └── pci-dss-checklist.yml
├── scripts/
│   ├── validate_repos.py           # Allow-list validator (+ ADR-0004 naming)
│   ├── compliance_check.py         # Compliance posture report (JSON)
│   ├── drift_detect.py             # Allow-list vs live org drift
│   ├── check_fleet_separation.sh   # ADR-0004 R1/R2/R3 guard
│   └── org_delivery_audit.sh       # Org-wide delivery-chain evidence capture
└── docs/
    ├── architecture.md
    ├── change-management.md
    ├── data-classification.md
    ├── drift-findings.md           # ← verified findings register, read this
    ├── state-migration-runbook.md  # ← the gate, read this
    ├── runbooks.md                 # RB-01 … RB-07
    ├── threat-model.md             # STRIDE + risk acceptance register
    ├── adr/0004-mission-marketplace-separation.md
    ├── runbooks/github-token-rotation.md
    ├── runbooks/workload-identity-federation.md
    └── security/{isolation-model,key-custody}.md
```

## Managed Repositories

Six repositories plus the org health repo, across three tiers:

| Tier | Repositories |
|------|--------------|
| **governance** | `jolarca-control`, `jolarca-compliance`, `jolarca-legal` |
| **platform** | `jolarca`, `jolarca-data` |
| **devops** | `jolarca-infrastructure` |
| *(not in allow-list)* | `.github` — org health repo, declared in `health-repo.tf` |

`.github` is deliberately outside `repos/*.yml`: it must be public, must not
carry the fleet merge/CI policy, and its name is not a valid allow-list
filename. It is how GitHub serves the org-wide inherited `SECURITY.md`.

## Quick Start

### Prerequisites
- Python 3.12+ with `pyyaml`
- Terraform 1.16.x (state was written by 1.16.0 — see D-14)
- GitHub CLI (`gh`), authenticated to `jolarca-dev`
- `GITHUB_TOKEN` — `repo` + `read:org` for planning; `admin:org` only if the
  audit webhook is configured

### Validate everything offline (safe at any time)
```bash
python3 -m venv .venv && . .venv/bin/activate && pip install pyyaml requests
make lint          # terraform fmt -check + validate + allow-list validation
make compliance    # full policy report
```

### Read-only checks against the live org (safe)
```bash
make drift         # allow-list vs live org
make fleet-audit   # ADR-0004 separation guard
make org-audit     # delivery-chain evidence capture
```

### Plan / apply — **BLOCKED**
```bash
make plan          # offers an offline -refresh=false plan only
make apply         # refuses outright
```
Both are gated until `docs/state-migration-runbook.md` step 9 flips
`STATE_MIGRATION_COMPLETE`.

## Provenance

This control plane was extracted from
[`jolarca-infrastructure`](https://github.com/jolarca-dev/jolarca-infrastructure),
where GitHub-organization governance had accumulated inside an infrastructure
repository: `terraform/modules/github-org/`, `scripts/check-fleet-separation.sh`,
`scripts/org-delivery-audit.sh`, `.github/workflows/fleet-separation-guard.yml`
and the supporting ADRs and runbooks.

The extraction is **code-only so far**. The Terraform state has not moved, the
old root has not been decommissioned, and both are documented as such. See
`docs/state-migration-runbook.md` for the sequence and
`docs/drift-findings.md` D-13 for the dual-ownership risk that the sequence
exists to close.

Superseded paths in `jolarca-infrastructure`:

| Old | New |
|---|---|
| `terraform/modules/github-org/` | `repositories.tf`, `branch-protection.tf`, `health-repo.tf` |
| fleet map in `modules/github-org/variables.tf` | `repos/*.yml` |
| `scripts/check-fleet-separation.sh` | `scripts/check_fleet_separation.sh` |
| `scripts/org-delivery-audit.sh` | `scripts/org_delivery_audit.sh` |
| `.github/workflows/fleet-separation-guard.yml` | same name, allow-list driven |
| `docs/adr/0004-mission-marketplace-separation.md` | `docs/adr/` (copied; original stays as the ADR of record) |

## License

See [LICENSE](LICENSE). This repository is **private and internal** — it
contains the governance posture, control definitions and security doctrine of
a PCI-DSS scope. It is not open source, and the AGPL-3.0 license on the public
`jolarca` application does not extend to it.
