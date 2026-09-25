# Remote state for `jolarca-control` — Workload Identity Federation design

**Closes finding:** **D-02** (live Terraform state is single-copy, local, no
remote backend) — a **blocking** prerequisite for any `terraform apply`.

**Status: DESIGN — nothing is provisioned.** No state bucket, no workload
identity pool, no provider, and no `backend` block exists for this repository.
Verified 2026-09-25: `main.tf` has no `backend` stanza and
`.terraform.lock.hcl` lists exactly one provider (`integrations/github`).
Everything below is what *must be built*, not what is running.

> **Scope note (2026-09-25).** This document was carried from
> `jolarca-infrastructure`, where it described that repo's CI-to-GCP federation
> under ADR-0003. Copied verbatim it was actively misleading here: it pinned
> `attribute.repository == "journeyoflife-org/jolarca-infrastructure"` (wrong
> org **and** wrong repo), it named workflows that do not exist in this
> repository (`drift-detection.yml`, `terraform.yml`), and it asserted the
> workflows were "already wired behind the `TF_REMOTE_STATE` repository
> variable gate". **They are not.** Identifiers, workflow names and the gating
> story below have been corrected to match this repository. The
> `jolarca-infrastructure` copy remains the authority for *that* repo.

## Why this matters

This root is the sole declarative record of six PCI-DSS-scoped repositories in
`jolarca-dev`. Today that record is one file, `terraform.tfstate`, on one
workstation, and it is gitignored (correctly — state must never be committed).
Losing the host means losing the ability to reason about ownership; the only
recovery is hand-importing every resource. State locking is equally absent, so
two concurrent applies could corrupt it.

**Interim mitigation, already required before any apply:** the off-host
**verified** backup in `../state-migration-runbook.md` step 0. That reduces the
risk but does not close D-02 — a backup is not locking, versioning, or
attribution.

## Current behaviour of the workflows (verified, not assumed)

| Workflow | `terraform init` | Touches state? |
|---|---|---|
| `plan.yml` (PR) | `-input=false -backend=false` | **No** — deliberately backend-less, so PR plans are safe today and stay safe after migration |
| `apply.yml` (`production` env) | `-input=false` (**with** backend) | **Yes** — it will pick up a `backend` block the moment one is added |
| `compliance-scan.yml` (`drift-detection` job) | none — calls `scripts/drift_detect.py`, which reads the live GitHub API, not Terraform state | No |
| `Makefile` `tf-validate` | `-backend=false` | No |

**Ordering hazard.** Because `apply.yml` initialises *with* the backend, adding
a `backend "gcs" {}` block before the bucket, pool, provider and repository
variables exist will make every apply fail at `init`. Worse, a partially
configured backend can leave `apply.yml` running against an **empty** state —
which plans to create repositories that already exist. That is precisely the
dual-ownership catastrophe `vars.STATE_MIGRATION_COMPLETE` exists to prevent.
So: provision first, wire last, and keep the `STATE_MIGRATION_COMPLETE` gate
closed until both are done and verified.

## Backend decision — REQUIRED, not yet made

The `jolarca-infrastructure` doctrine (ADR-0003) is GCS + WIF with no
service-account JSON keys in CI. Consistency argues for the same here, so the
design below assumes it. But this is a genuine decision with cost implications
and it has **not** been recorded:

| Option | Fit | Notes |
|---|---|---|
| **GCS + WIF** (assumed below) | Consistent with ADR-0003; native locking and object versioning; no key material in CI | Requires bootstrapping a GCP project, bucket and pool — none exist yet. Adds a GCP dependency to the GitHub control plane |
| HCP Terraform / Terraform Cloud | Purpose-built for exactly this; free tier covers one operator; locking, versioning and run history included; no cloud infra to run | Introduces a third-party SaaS into the trust path for PCI-scope governance state. Needs its own data-processing assessment |
| S3 + DynamoDB | Change record `JOL-ORGTRANSFER-20260902-01` mentions commercial AWS accounts for `jolarca-dev`, so the account may exist | Locking via DynamoDB is more moving parts than GCS's native lock; no evidence an AWS state pattern is established here |
| Encrypted state in a git repo | **Rejected** | Violates boundary 6 in `../security/isolation-model.md` (no state in git, encrypted or not) |

Record the choice as an ADR before implementing. Do not let it be decided by
whichever runbook gets copied next.

## 1. One-time GCP setup (operator, change window)

Replace every `<...>` placeholder. Note `jolarca-dev`, not `journeyoflife-org`.

```bash
P=<PROJECT_ID>
POOL=github-actions
PROVIDER=jolarca-control          # NOT the legacy 'jolm-*' prefix — see ADR-0004 Amendment 2

gcloud iam workload-identity-pools create "$POOL" \
  --project="$P" --location=global \
  --display-name="GitHub Actions (jolarca-dev)"

gcloud iam workload-identity-pools providers create-oidc "$PROVIDER" \
  --project="$P" --location=global --workload-identity-pool="$POOL" \
  --display-name="jolarca-control repo" \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.ref=assertion.ref,attribute.actor=assertion.actor"
```

State bucket (separate from any infra bucket, its own prefix):

```bash
BUCKET=<PROJECT>-tfstate-jolarca-control
gsutil mb -p "$P" -l <REGION> "gs://$BUCKET"
gsutil versioning set on "gs://$BUCKET"          # mandatory: state rollback path
# CMEK per the infrastructure doctrine — see jolarca-infrastructure/security/key-custody.md
```

## 2. Attribute condition (pin WHO may federate)

Never bind the whole issuer — that would let any GitHub repository in the world
claim these credentials. Pin the repository, and for apply-grade access pin the
ref too:

```
attribute.repository == "jolarca-dev/jolarca-control"
```

For production state access additionally restrict the principal-set binding to
`attribute.ref == "refs/heads/main"`, so applies run only from main or manual
dispatch while PR plans stay read-scoped.

## 3. Bind the CI principal to the state service account

```
principalSet://iam.googleapis.com/projects/<PROJECT_NUMBER>/locations/global/workloadIdentityPools/github-actions/attribute.repository/jolarca-dev/jolarca-control
```

Grant that principal `roles/iam.serviceAccountTokenCreator` on the state SA
(`tfstate-jolarca-control@<PROJECT>.iam.gserviceaccount.com`). CI can
impersonate and nothing more. The state SA is the only identity that writes
state, which keeps attribution clean in Cloud Audit Logs.

## 4. GitHub repository variables and secrets (on `jolarca-control`)

Variables are identifiers, not secrets — they are safe to expose:

| Variable | Value |
|---|---|
| `TF_REMOTE_STATE` | `true` — flipped **after** migration is verified |
| `GCP_WORKLOAD_IDENTITY_PROVIDER` | `projects/<NUM>/locations/global/workloadIdentityPools/github-actions/providers/jolarca-control` |
| `GCP_STATE_SA_PRODUCTION` | `tfstate-jolarca-control@<PROJECT>.iam.gserviceaccount.com` |
| `GCP_STATE_BUCKET` | `<PROJECT>-tfstate-jolarca-control` |

This repository has **one** environment (`production`); there is no staging
root, so no staging SA is defined. Do not invent one.

## 5. Wiring the workflows (last step, not first)

Only after steps 1–4 are verified:

1. Add the `backend "gcs" {}` block to `main.tf` and set the bucket/prefix via
   `-backend-config` from the variables above.
2. Add a `google-github-actions/auth` step (**SHA-pinned**, as every other
   action here is) to `apply.yml` that exchanges the GitHub OIDC token for GCP
   credentials under the step-2 attribute condition.
3. Gate the new path on `vars.TF_REMOTE_STATE == 'true'` so a partially
   provisioned setup cannot silently run against empty state. Until it flips,
   `apply.yml` must keep refusing — it is already hard-gated on
   `vars.STATE_MIGRATION_COMPLETE`.
4. Leave `plan.yml` on `-backend=false`. A PR plan needs no state access, and
   keeping it backend-less preserves the property that pull requests cannot
   touch production.

## Acceptance criteria

- [ ] Backend choice recorded as an ADR.
- [ ] `gcloud iam workload-identity-pools providers describe` shows the
      attribute condition pinning `jolarca-dev/jolarca-control`.
- [ ] Bucket has object versioning **on** and a CMEK.
- [ ] A workflow run from a **different** repository is *refused* federation
      (negative test — this is the control that matters).
- [ ] `terraform init` in CI succeeds and reports the GCS backend.
- [ ] State migrated with `terraform state rm` / `import` per
      `../state-migration-runbook.md`, and `terraform plan` afterwards is a
      no-op.
- [ ] Local `terraform.tfstate` retained as a verified backup, then removed
      from the working path.
- [ ] D-02 marked closed in `../drift-findings.md` with the evidence.

## Incident pointers

- **Federated token misuse suspected** → delete the step-3 binding (instant
  revocation), then review Cloud Audit Logs for `sts.googleapis.com` and
  `storage.googleapis.com` DATA_READ events.
- **State exposure** → `jolarca-infrastructure/docs/runbooks/state-compromise.md`
  (CMEK revocation is the kill switch). That runbook was **not** ported here;
  it lives with the infrastructure that owns the keys.
- **Lost or corrupted state** → restore the previous version from the bucket's
  object history, or the off-host backup from runbook step 0. Never hand-edit
  state to make a plan look clean.
