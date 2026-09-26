# ADR-0006: Remote Terraform state backend for jolarca-control

**Status:** Accepted
**Date:** 2026-09-25
**Deciders:** org owner (solo era)

## Context

`jolarca-control` manages six PCI-DSS-scoped repositories in `jolarca-dev`. The Terraform state file (`terraform.tfstate`) is the sole record of what this control plane owns. Currently:

- State is a **single local file** on one workstation (D-02)
- No remote backend, no locking, no versioning
- Host loss = permanent inability to reason about repository ownership
- Two concurrent applies could corrupt state (no locking)
- CI workflows cannot access state, so `apply.yml` is blocked until this is resolved

This is a **blocking** prerequisite for any `terraform apply` and must be resolved before the state migration runbook can execute.

## Decision

**Use HCP Terraform (free tier)** for remote state storage.

### Rationale

1. **Purpose-built:** HCP Terraform is designed specifically for Terraform state management, providing remote state, locking, versioning, and a web UI out of the box.

2. **No cloud infrastructure to manage:** Unlike GCS or S3, HCP Terraform requires no bucket provisioning, IAM configuration, or lifecycle management. The free tier covers one operator with all necessary features.

3. **Cost:** Free tier is sufficient for jolarca-control's needs (one workspace, one operator, <5GB state). No ongoing infrastructure costs.

4. **GCP cost avoidance:** GCP projects incur costs for API calls, storage, and IAM management. HCP Terraform's free tier eliminates these costs entirely.

5. **Simpler CI integration:** HCP Terraform provides native GitHub Actions integration without requiring Workload Identity Federation setup or service account management.

6. **Run history and UI:** Web UI provides state inspection, run history, and manual trigger capability — valuable for debugging and audit.

### Alternatives considered

**GCS + Workload Identity Federation**
- **Pros:** Consistent with `jolarca-infrastructure` doctrine (ADR-0003); native locking; no long-lived credentials.
- **Cons:** Requires GCP project with billing enabled; incurs ongoing costs for API calls, storage, and IAM management; requires WIF pool/provider/service account provisioning; more operational complexity for a single-workspace use case.
- **Rejected:** GCP project costs are too high for a single Terraform workspace. Over-engineering for the use case.

**S3 + DynamoDB**
- **Pros:** Change record `JOL-ORGTRANSFER-20260902-01` mentions commercial AWS accounts for `jolarca-dev`, so the account may exist.
- **Cons:** Locking via DynamoDB is more moving parts than HCP Terraform's native lock; requires bucket provisioning, IAM policies, and DynamoDB table management; no web UI for state inspection.
- **Rejected:** More complexity than HCP Terraform, no UI, and still incurs AWS costs.

**Encrypted state in a git repository**
- **Pros:** No external dependencies.
- **Cons:** Violates boundary 6 in `docs/security/isolation-model.md` ("no state in git, encrypted or not"). State contains resource IDs and metadata that must not be in version control.
- **Rejected:** Violates established security doctrine.

## Implementation

### 1. HCP Terraform account setup (operator, one-time)

1. **Sign up** at https://portal.terraform.io/ using the `JourneyOfLife` GitHub account.
2. **Create an organization** named `jolarca-dev` (matches the GitHub org name for consistency).
3. **Create a workspace** named `jolarca-control` with:
   - **Execution mode:** Remote (default)
   - **Terraform version:** Match `main.tf` `required_version` (currently `>= 1.9.0`)
   - **Working directory:** `/` (root of the repository)
4. **Generate an API token** for the workspace:
   - Go to User Settings → Tokens → Create API Token
   - Name: `jolarca-control-ci`
   - Scopes: `read-workspaces`, `write-state`, `apply:run`
   - Copy the token (shown once)

### 2. GitHub repository variables and secrets

Add to `jolarca-control` repository settings:

**Variables (not secrets):**

| Variable | Value |
|---|---|
| `TF_CLOUD_ORGANIZATION` | `jolarca-dev` |
| `TF_CLOUD_WORKSPACE` | `jolarca-control` |

**Secrets:**

| Secret | Value |
|---|---|
| `TFC_TOKEN` | The API token from step 1.4 |

### 3. Terraform backend configuration

Add to `main.tf`:

```hcl
terraform {
  cloud {
    organization = "jolarca-dev"

    workspaces {
      name = "jolarca-control"
    }
  }
}
```

**Note:** The `cloud` block replaces any `backend` block. Terraform will prompt to migrate state on the next `terraform init`.

### 4. Workflow updates

**`apply.yml`** — add HCP Terraform authentication:

```yaml
- name: Setup Terraform
  uses: hashicorp/setup-terraform@b9cd54a3c349d3f384f39d0e570d19711a8f0b8c # v3.1.2
  with:
    cli_config_credentials_token: ${{ secrets.TFC_TOKEN }}
```

**`plan.yml`** — same setup step for PR plans.

**`compliance-scan.yml`** — no changes needed (does not touch state).

### 5. State migration

1. **Backup local state:**
   ```bash
   cp terraform.tfstate terraform.tfstate.backup.$(date +%Y%m%d-%H%M%S)
   ```

2. **Initialize with cloud backend:**
   ```bash
   terraform init -migrate-state
   ```
   Terraform will prompt to copy local state to HCP Terraform. Confirm with `yes`.

3. **Verify migration:**
   ```bash
   terraform plan
   ```
   Should show no changes (state is now in HCP Terraform).

4. **Remove local state:**
   ```bash
   rm terraform.tfstate terraform.tfstate.backup
   ```

### 6. Verification

- [ ] `terraform init` succeeds and reports HCP Terraform backend.
- [ ] `terraform plan` shows no changes after migration.
- [ ] HCP Terraform UI shows the workspace and state.
- [ ] CI workflow (`apply.yml`) can authenticate and run.
- [ ] Local `terraform.tfstate` is removed from the working path.
- [ ] D-02 marked closed in `docs/drift-findings.md`.

## Consequences

**(+) Positive:**
- State is durable, versioned, and locked.
- CI can access state without long-lived cloud credentials.
- Web UI for state inspection and run history.
- No ongoing infrastructure costs (free tier).
- No GCP/AWS project management overhead.
- Closes D-02 (blocking).

**(−) Negative:**
- Introduces HashiCorp SaaS into the trust path for PCI-scope governance state.
- Requires GDPR Art. 28 data-processing assessment (HashiCorp as subprocessor).
- Free tier lacks team management and advanced audit logs (needed when scaling beyond one operator).
- Dependency on HashiCorp's service availability.

**(?) Risks:**
- HashiCorp account compromise could expose state (mitigated by strong password, 2FA, and API token rotation).
- HCP Terraform outage could block applies (mitigated by local state backup and manual recovery procedure).
- Free tier limits (5GB state, 500 runs/month) are sufficient for jolarca-control but may require upgrade if scaling.

## Compliance mapping

- **SOC 2 CC6.1:** Logical access controls on state via HCP Terraform workspace permissions and API token scoping.
- **ISO 27001 A.8.13:** Segregation of processing facilities — state is stored in HashiCorp's cloud, separate from application infrastructure.
- **PCI-DSS Req 1.2:** State storage scope definition; HashiCorp's PCI-DSS certification covers the subprocessor requirement.
- **PCI-DSS Req 10:** Audit trail via HCP Terraform run history.
- **GDPR Art. 28:** Data-processing agreement with HashiCorp (required — see `jolarca-legal/contracts/vendors/hashicorp/`).
- **GDPR Art. 32:** Security of processing — encryption at rest and in transit (HashiCorp-managed).

## Relationships

- **ADR-0003** (in `jolarca-infrastructure`): Establishes GCS + WIF doctrine for infrastructure state. **This ADR diverges from that doctrine** due to cost constraints. Documented exception.
- **ADR-0004**: Mission/marketplace separation — HCP Terraform organization is in marketplace scope (`jolarca-dev`), not mission scope.
- **D-02**: This ADR closes the finding.
- **D-13**: State migration runbook depends on this backend being provisioned.

## Review date

2027-09-25 (one year from decision, or on second-operator onboarding, or if state exceeds 5GB).
