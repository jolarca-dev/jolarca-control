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

1. **Sign up** at https://portal.terraform.io/ . The account that actually owns the
   state is the HCP Terraform account whose organization billing email is
   `journey4oflife@gmail.com` — re-verified live 2026-10-15 (see *Account custody*
   below). The original instruction here named the `JourneyOfLife` GitHub account;
   that identity is **not** what `app.terraform.io/api/v2/organizations/jolarca-dev`
   reports as the org email, so it is recorded as corrected rather than assumed.
   Do not delete either HashiCorp identity to "clean this up": the state-bearing
   identity is singular and deleting it removes the org and its state.
   **Address policy (2026-10-15, D-59/D-60):** the bare mailbox above is no longer
   the address to publish anywhere. The HashiCorp billing contact should become
   `journey4oflife+jolarca.billing@gmail.com` per `policy/contact-addresses.yml`,
   but that change is **outstanding and owner-executed**: the org email on
   `app.terraform.io` is set in the account UI, and this ADR keeps recording the
   *measured* value rather than the intended one — a custody record that states an
   address nobody has confirmed at the provider is worse than an ugly true one.
   Nothing here may be read as "the HCP account is already on a role alias".
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

- [x] `terraform init` succeeds and reports HCP Terraform backend.
- [ ] `terraform plan` shows no changes after migration.
- [x] HCP Terraform UI shows the workspace and state.
- [ ] CI workflow (`apply.yml`) can authenticate and run.
- [ ] Local `terraform.tfstate` is removed from the working path. **Not done** as of
      2026-10-12: `terraform.tfstate` (0 bytes) and `terraform.tfstate.backup`
      (67 KB, pre-migration serial 151 snapshot, 6 resources) still sit in the
      working tree. Both are gitignored, so this is a stale-read risk, not a leak
      into history — and see *Backup* below for why the 0-byte file is now a
      functional defect rather than mere litter.
- [ ] D-02 marked closed in `docs/drift-findings.md`. **Not closed** — the register
      row is still `PARTIALLY FIXED` and D-02 is still listed in
      `policy/compliance-gates.yml` `open_blocking`. The backend migration landed;
      the off-host backup half of D-02 did not.

### 7. Account custody (verified 2026-10-12)

One ambiguity the operator raised: a registration at `developer.hashicorp.com`
alongside the workspace at `app.terraform.io` looked like a second Terraform
account. Resolved empirically, not by inference:

| Fact | Value | How shown |
|---|---|---|
| Orgs visible to the local credential | `jolarca-dev` only | `GET /api/v2/organizations` with the `~/.terraformrc` token |
| Org billing email | `journey4oflife@gmail.com` (re-read 2026-10-15; unchanged. Policy target `journey4oflife+jolarca.billing@gmail.com` — **not yet applied**, UI-only) | `GET /api/v2/organizations/jolarca-dev` |
| Org id / plan | `org-3zNQFys8XA3HNPCF`, free tier (`audit-logging: false`) | `GET /api/v2/organizations/jolarca-dev/entitlement-set` |
| Workspace id | `ws-w6NSnTXXmYgh78Su`, TF 1.16.5, **35 resources** | `GET .../workspaces/jolarca-control` |
| Runs | 3, all `source: terraform+cloud` ("Triggered via CLI") | `GET /api/v2/workspaces/ws-.../runs` |

`developer.hashicorp.com` is the documentation, Learn and download portal. It
carries **no organization, no workspace and no state**, so it is not a competing
state store even when it is a separate login. The confusion risk is therefore
*not* the number of accounts, and the decision is to **keep both identities and
document the sole owner here** rather than delete anything — deleting the
state-bearing account would orphan all 35 tracked `github_*` resources while
leaving the repositories themselves alive on GitHub. Whether the docs-portal login
is a *separate* identity or the same one cannot be settled from here — no API
exposes it — but it is immaterial: no state lives on either reading of it, so the
only record needed is the owner table above. Deletion was refused outright because
of the single-copy finding below.

Remaining local ambiguity, checked rather than assumed: the legacy root at
`jolarca-infrastructure/terraform/environments/production/` is **not** a second
state authority. Its `terraform.tfstate` reads serial 37 with one resource block
(`github_repository_file.security_md`) carrying **zero instances**, i.e. the
2026-10-01 `terraform state rm` pass behind D-13 did drain every `github_*`
address. It is the frozen leftovers (six `.backup`/`.pre-d13-cleanup` copies) that
look like competing state, not competing claims.

**Backup — measured, and it is broken.** The D-02 interim control recorded in
`docs/drift-findings.md` ("AGE-encrypted state backup via `scripts/state_backup.sh`")
does not work against the cloud backend: the script is keyed to
`$REPO_ROOT/terraform.tfstate`, and running it on 2026-10-12 exits **1** with
`ERROR: terraform.tfstate is not valid JSON` — the file is 0 bytes. There is no
`docs/backup-log.tsv`, and no `*.age` or state copy exists under
`/opt/jolarca/backups/` (that tree holds PostgreSQL and Redis dumps only). The
authoritative 35-resource state therefore has **exactly one copy, in HashiCorp's
cloud** — which is the concrete reason no account, org or workspace may be deleted
before an HCP state export is taken and verified. Not fixed in this change:
closing it needs a `terraform pull`-equivalent path for a `cloud {}` workspace
plus a `BACKUP_DEST`, and the script's own fixture set has no negative control
for the cloud case (§7: an untested gate is a hypothesis).

Credential hygiene finding from the same check: `~/.terraformrc` was mode `0664`
(group-readable) while holding a live `atlasv1` API token, and a verification
probe echoed it into a tool transcript. Mitigation: `chmod 600`, rotate the token
in the HCP Terraform UI, and update the `TFC_TOKEN` repository secret in the same
step — the old token is to be treated as exposed.

### 8. CI execution path — incident 2026-10-12

The merge of #64 (`fix(ci): disable setup-terraform wrapper for local plan
execution`) triggered `Terraform Apply` run **38239257880** at 10:54:39Z. Its
`Terraform Plan` step never finished: HCP run **run-SLzZdT5C4AeyhptB** sat in
`planning` for **33 minutes** (status timestamps stop at `planning-at:
10:54:58Z`), with `terraform apply -input=false -auto-approve tfplan` queued
behind it. The operator force-cancelled the Actions run; this ADR's author then
cancelled the HCP run (`force-canceled-at: 11:28:02Z`). Verified unchanged after
cancel: `resource-count: 35`, no workspace lock, and `terraform state list` → 35
addresses. Nothing was applied.

Two beliefs this incident disproved, both of which were live in `apply.yml`:

| Claim | Measured reality |
|---|---|
| `TF_CLOUD_OPERATIONS: "false"` forces local plan/apply | Not a Terraform environment variable. Present on the plan and apply steps while runs kept landing on HCP workers. Removed. |
| `terraform plan -local` is the alternative | No `-local` flag exists in Terraform 1.16.1 — `terraform plan -help` and `terraform apply -help` list no such option. |

The setting that actually controls this is the workspace's **`execution-mode`**,
which was measured live as `remote` (`GET /api/v2/workspaces/ws-w6NSnTXXmYgh78Su`).
`local` makes the workspace state storage only, so plan and apply execute on the
runner — which is what a CI-driven pipeline needs, and what ADR-0006 assumed the
free tier would provide. Consequence to keep visible: HCP does not evaluate
workspace variables or variable sets in local mode, and VCS-triggered remote runs
stop. Neither is used here — `apply.yml` supplies its own provider token and no
HCP variable set exists.

New control: `scripts/check_workspace_execution_mode.sh`, called by `apply.yml`
before `terraform init`, refuses a non-`local` workspace in seconds instead of
hanging, with negative controls in
`tests/test_check_workspace_execution_mode.sh` (13 cases: local accepted, remote
and agent refused, unparseable/empty/missing responses exit **2**). `timeout-minutes:
20` was added to the job as a backstop. Both patterns are the D-22 lesson applied
again: a gate written inline in a workflow cannot be exercised, and a flag or
environment variable nobody verified became the whole control.

Also recorded because it will bite the next runbook line: HCP Terraform POST and
PATCH endpoints reject the usual `application/json` — the media type must be
`application/vnd.api+json` or the call fails with **HTTP 415** (`content-type must
be application/vnd.api+json`), measured on the cancel and again on the retry.

## Consequences

**(+) Positive:**
- State is durable, versioned, and locked.
- CI can access state without long-lived cloud credentials.
- Web UI for state inspection and run history.
- No ongoing infrastructure costs (free tier).
- No GCP/AWS project management overhead.
- Closes the **remote-backend half** of D-02: locking, versioning and a single
  authoritative copy now exist. The off-host backup obligation in D-02 is **not
  closed** — see *Backup* above, and `docs/drift-findings.md` still reads
  `PARTIALLY FIXED`.

**(−) Negative:**
- Introduces HashiCorp SaaS into the trust path for PCI-scope governance state.
- Requires GDPR Art. 28 data-processing assessment (HashiCorp as subprocessor).
- Free tier lacks team management and advanced audit logs (needed when scaling beyond one operator).
- Dependency on HashiCorp's service availability.

**(?) Risks:**
- HashiCorp account compromise could expose state (mitigated by strong password, 2FA, and API token rotation).
- **A second HashiCorp login may exist** (docs portal vs the state-bearing HCP
  Terraform account). Immaterial to custody: only `jolarca-dev` on
  `app.terraform.io` holds state, and the table in *Account custody* is the record.
  Deleting an identity is refused as an irreversible action, not a cleanup.
- Account deletion is **not** a cleanup option: it removes the org and its state
  while the GitHub resources keep running, leaving 35 resources unowned.
- HCP Terraform outage could block applies. **The stated mitigation does not
  currently hold** — "local state backup" assumes a readable `terraform.tfstate`,
  and `scripts/state_backup.sh` exits 1 against the 0-byte placeholder, so there is
  no local copy to fall back to. Recovery depends on HashiCorp's own retention.
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
- **D-02**: This ADR closes the remote-backend half of the finding; the off-host
  state backup remains open and is recorded as broken in *Account custody*.
- **D-13**: State migration runbook depends on this backend being provisioned.

## Review date

2027-09-25 (one year from decision, or on second-operator onboarding, or if state exceeds 5GB).
