# State Migration Runbook — `jolarca-infrastructure` → `jolarca-control`

**Status:** COMPLETE (2026-10-10) — HCP Terraform workspace `jolarca-dev/jolarca-control`
is live with 35 resources; `STATE_MIGRATION_COMPLETE=true` is set; `TFC_TOKEN`
secret is configured. `jolarca-control` is authoritative.
**Scope:** move ownership of the six `jolarca-dev` GitHub repositories, their
branch-protection rules and the org health repo from
`jolarca-infrastructure/terraform/environments/production` into this root.
**Compliance:** SOC 2 CC8.1 (change management), ISO 27001 A.8.32 (change
management) / A.8.13 (information backup) / A.5.9 (asset inventory),
PCI-DSS Req 6.5.1.
**Findings closed by this runbook:** D-02, D-03, D-06, D-08, D-13, D-15, D-16.

> **Read first.** This is a live-state operation on PCI-DSS-scoped production
> repositories. Every destructive-looking step below is chosen so that the
> *real GitHub objects are never touched* — `terraform state rm` forgets a
> resource without destroying it, and `import` adopts without recreating.
> There is no step in this runbook that runs `terraform apply` against the old
> root. If you find yourself about to, stop.

---

## Change record (fill in before starting)

| Field | Value |
|---|---|
| Change ID | |
| Date / window | |
| Operator | |
| Approver | |
| Rollback point (state backup path + SHA256) | |
| Terraform CLI version (pin 1.16.x — D-14) | |
| Provider version | `integrations/github 6.13.0` |
| Evidence destination | `jolarca-compliance` |

---

## Step 0 — Off-host state backup (BLOCKS EVERYTHING, closes D-02)

The production state is a single gitignored file on one host. There is no
rollback point until this step is done and verified.

```bash
OLD=/opt/jolarca/repos/jolarca-infrastructure/terraform/environments/production
STAMP=$(date +%Y%m%d-%H%M%S)
DEST=/opt/jolarca/backups/tfstate          # off the repo tree; ideally off-host

mkdir -p "$DEST"
cp -p "$OLD/terraform.tfstate"        "$DEST/github_org-$STAMP.tfstate"
cp -p "$OLD/terraform.tfstate.backup" "$DEST/github_org-$STAMP.tfstate.backup"

# Verify — a backup you have not checksummed is not a backup.
sha256sum "$OLD/terraform.tfstate" "$DEST/github_org-$STAMP.tfstate" \
  | tee "$DEST/github_org-$STAMP.sha256"
diff <(sha256sum < "$OLD/terraform.tfstate") <(sha256sum < "$DEST/github_org-$STAMP.tfstate") \
  && echo "BACKUP VERIFIED" || { echo "BACKUP MISMATCH — STOP"; exit 1; }

chmod 600 "$DEST"/github_org-$STAMP*
```

Record both SHA256 values in the change record. **Do not proceed on a
mismatch.**

Then, and only then, complete the remote-backend migration described in
[runbooks/workload-identity-federation.md](runbooks/workload-identity-federation.md)
so that neither root depends on a local file. A control plane whose state lives
on one laptop is not a control plane.

---

## Step 1 — Freeze the old root

Already applied in the `jolarca-infrastructure` working tree as part of this
change; verify before continuing:

```bash
cd /opt/jolarca/repos/jolarca-infrastructure
grep -n 'jolarca-dev' terraform/modules/github-org/variables.tf \
                      terraform/environments/production/variables.tf   # D-06 fix
grep -n 'prevent_destroy' terraform/modules/github-org/main.tf \
                          terraform/modules/github-org/github-health-repo.tf
grep -n 'FROZEN' terraform/modules/github-org/versions.tf
ls terraform/modules/github-org/*.bak* 2>/dev/null && echo "D-12 NOT FIXED" || echo "D-12 fixed"
```

Expected: `org` defaults to `jolarca-dev`, `prevent_destroy = true` on both
`github_repository` resources, a FROZEN banner in `versions.tf`, no `.bak`
file. Land this as a signed PR **before** step 2 so the freeze is in git
history, not just on disk.

From this point until step 8: **no `terraform plan/apply/destroy` in the old
root.** The `prevent_destroy` added in step 1 is the safety net if someone
forgets.

---

## Step 2 — Create `jolarca-control` on GitHub (closes D-16)

The chicken-and-egg: the repo must be created by the control plane that lives
inside it. Resolve by a one-time manual creation recorded as an explicit
ADR-0004 R2 exception — *not* by pretending it was IaC-created.

```bash
gh repo create jolarca-dev/jolarca-control \
  --private \
  --description "Central governance control plane for the jolarca-dev marketplace organization"
```

Then record the exception. Append to
`jolarca-infrastructure/docs/compliance/evidence/`:

```
change-record-jolarca-control-bootstrap-<YYYYMMDD>.md
  - ADR-0004 R2 out-of-band creation, authorised, single occurrence
  - Reason: bootstrap ordering — the control plane cannot create its own host repo
  - Reconciliation: imported into state at step 5, allow-list entry already
    present at repos/jolarca-control.yml (declared before creation)
  - 48h import rule satisfied by this runbook
```

Set the repository variables and secrets (Settings → Secrets and variables → Actions):

| Name | Kind | Value |
|---|---|---|
| `STATE_MIGRATION_COMPLETE` | Variable | leave **unset** until step 9 |
| `TF_GITHUB_TOKEN` | Secret (env `production`) | fine-grained PAT: `jolarca-dev`, Administration **read/write**, Contents read, Metadata read |
| `TF_GITHUB_TOKEN_READONLY` | Secret | fine-grained PAT: `jolarca-dev`, Administration **read**, Contents read, Metadata read |

Create the `production` **environment** with required reviewers = the operator.
That reviewer prompt is the manual gate `apply.yml` relies on.

Note: the workflow's default `GITHUB_TOKEN` cannot be used for any of this —
it has no rights over other repositories or org-level resources.

---

## Step 3 — Publish this repository

```bash
cd /opt/jolarca/repos/jolarca-control
git rm --cached -r .idea            # IDE config is gitignored, was pre-staged by PyCharm
git add -A
git status                          # REVIEW: confirm no .venv, no .idea, no tfstate
git commit -S -m "feat: bootstrap jolarca-control governance control plane for jolarca-dev"
git branch -M main
git remote add origin git@github.com:jolarca-dev/jolarca-control.git
git push -u origin main
```

The push will be rejected until the required status checks exist, or will pass
straight through because protection is not yet applied to this repo — either
is fine at this point. Apply protection **after** the first green run of
`compliance-scan.yml`, otherwise the three required contexts
(`Validate Repo Allow-List`, `Policy Compliance Check`,
`Repository Secret Pattern Scan`) will block the very PR that introduces them.

Local smoke test, no network, no state:

```bash
python3 -m venv .venv && . .venv/bin/activate && pip install pyyaml
python3 scripts/validate_repos.py
python3 scripts/compliance_check.py | python3 -m json.tool | head -30
terraform init -backend=false && terraform validate && terraform fmt -check -recursive
```

---

## Step 4 — Resolve the `.github` cross-scope leak (closes D-03)

The old state holds `journeyoflife-org/.github`. That is a **mission-platform**
repository and must never enter marketplace state. It is deliberately *not*
part of the migration.

Decide its correct owner:

- **Preferred** — hand it to `jol-control`: add a `health-repo.tf` there and
  import `journeyoflife-org/.github` into the church control plane.
- **Otherwise** — drop it from IaC entirely and manage it by hand, recording
  the decision.

Either way, in the old root:

```bash
cd /opt/jolarca/repos/jolarca-infrastructure/terraform/environments/production
terraform state rm 'module.github_org.github_repository.dot_github'
terraform state rm 'module.github_org.github_repository_file.security_md'   # 0 instances; harmless no-op, keeps the state tidy
```

`state rm` forgets, it does not delete. `journeyoflife-org/.github` is
untouched on GitHub.

---

## Step 5 — Move the fleet out of the old state

`terraform state rm` per resource. The real repositories are **not** affected —
this only removes Terraform's claim on them.

```bash
cd /opt/jolarca/repos/jolarca-infrastructure/terraform/environments/production

for r in jolarca jolarca-compliance jolarca-control jolarca-data \
         jolarca-infrastructure jolarca-legal; do
  terraform state rm "module.github_org.github_repository.repos[\"$r\"]" || true
  terraform state rm "module.github_org.github_repository_vulnerability_alerts.repos[\"$r\"]" || true
  terraform state rm "module.github_org.github_branch_protection.main[\"$r\"]" || true
done

# Only jolarca-control is expected to be absent here — it never existed in the
# old state. `|| true` covers it; confirm the count afterwards.
terraform state list | grep -c github_ || echo "0 github_ resources remain (expected)"
```

Expected result: **zero** `module.github_org.*` entries remain.

Immediately remove the GitHub section from the old root's config, in the same
window — otherwise its next plan proposes recreating everything just forgotten:

- `terraform/environments/production/main.tf` — delete the `provider "github"`
  block, the `module "github_org"` block, and the `repositories` /
  `health_repo` outputs. Keep the `github` entry in `required_providers` only
  if another module still needs it (nothing does).
- `terraform/environments/production/variables.tf` — delete `org` and
  `enable_branch_protection`.
- `terraform/environments/staging/versions.tf` — drop the orphan `github`
  provider pin (staging never instantiated the module).
- Delete `terraform/modules/github-org/` entirely, and
  `scripts/terraform-state-rename-jolarca.sh` (its subject no longer exists).
- Point `scripts/check-fleet-separation.sh` and
  `.github/workflows/fleet-separation-guard.yml` at this repo, or delete them —
  they are superseded by `scripts/check_fleet_separation.sh` here.

Verify the old root is still coherent:

```bash
cd /opt/jolarca/repos/jolarca-infrastructure/terraform/environments/production
terraform init -input=false && terraform validate
terraform plan -input=false -refresh=false    # must show NO github_* actions
```

---

## Step 6 — Adopt everything into `jolarca-control`

Use declarative `import` blocks so the adoption is reviewed as code in a PR
rather than typed as shell history. Create `imports.tf`:

```hcl
# TEMPORARY — delete this file once the apply that consumes it has succeeded.
import {
  for_each = toset([
    "jolarca", "jolarca-compliance", "jolarca-control",
    "jolarca-data", "jolarca-infrastructure", "jolarca-legal",
  ])
  to = github_repository.repo[each.value]
  id = "jolarca-dev/${each.value}"
}

import {
  for_each = toset([
    "jolarca", "jolarca-compliance", "jolarca-data",
    "jolarca-infrastructure", "jolarca-legal",
  ])
  to = github_repository_vulnerability_alerts.repo[each.value]
  id = each.value
}

import {
  to = github_repository.health
  id = "jolarca-dev/.github"
}

import {
  to = github_repository_vulnerability_alerts.health
  id = ".github"
}
```

Branch protection import IDs are the part most likely to be wrong, because the
provider keys that resource by the **GraphQL node ID of the protection rule**,
not by repo name. Fetch the real IDs first:

```bash
gh api graphql -f query='
{
  organization(login: "jolarca-dev") {
    repositories(first: 20) {
      nodes {
        name
        branchProtectionRules(first: 5) {
          nodes { id pattern }
        }
      }
    }
  }
}'
```

Then add one `import` block per rule using the returned `id`:

```hcl
import {
  to = github_branch_protection.main["jolarca"]
  id = "<node ID from the query above>"
}
# ... one per protected repo, plus:
import {
  to = github_branch_protection.health[0]
  id = "<node ID for .github>"
}
```

> Confirm the exact `id` format against the `integrations/github` **6.13.0**
> docs before applying. A wrong ID makes `terraform plan` fail loudly and
> harmlessly — that is the intended safety behaviour, so treat a plan failure
> here as information, not as something to force past.

Plan, then read it line by line:

```bash
cd /opt/jolarca/repos/jolarca-control
terraform init -input=false
terraform plan -input=false -no-color -out=tfplan | tee plan.txt
```

**Acceptance criteria for this plan — all must hold:**

- [ ] `0 to add` other than the `import` moves themselves
- [ ] `0 to destroy`
- [ ] no `must be replaced`
- [ ] the **only** in-place updates are the D-01 visibility changes (four
      repos `public → private`) and any `security_and_analysis` additions
- [ ] every one of the six repositories appears exactly once

If `destroy` or `replace` appears anywhere: **stop**, restore from the step-0
backup, and diagnose. `prevent_destroy` should already have aborted the plan.

---

## Step 7 — Decide D-01 before applying

The plan from step 6 will contain the visibility change. Choose, in writing,
in the change record:

- **(a) Make them private** — correct per the intent of record and per
  PCI-DSS Req 1.2 / GDPR Art. 32. First check what breaks: public forks,
  GitHub Pages, external contributor PRs, any CI in another org that clones
  over HTTPS anonymously.
- **(b) Keep them public** — edit the four `repos/*.yml` files to
  `visibility: public`, and add a signed risk acceptance to
  `docs/drift-findings.md` D-01 with compensating controls and a review date.
  Note that `scripts/validate_repos.py` will then fail the
  classification↔visibility coherence rule on all four (each is
  `confidential`, and `docs/data-classification.md` forbids `confidential` in a
  public repo). Reclassifying them is part of choosing (b), and
  reclassification is itself a decision that needs recording.

Either way, split it: **apply the adoption first with visibility unchanged**,
then land the visibility decision as its own reviewed PR. Two small auditable
changes beat one big one. To adopt without touching visibility, temporarily
set the four YAML entries to their live value (`public`), apply, then flip.

---

## Step 8 — Apply, then verify

```bash
terraform apply -input=false tfplan
rm -f imports.tf                    # TEMPORARY file — must not persist
terraform plan -input=false         # MUST now report "No changes"
```

Post-apply verification, all read-only:

```bash
python3 scripts/drift_detect.py             # expect drift_detected: false (modulo D-01 if deferred)
bash scripts/check_fleet_separation.sh      # expect FLEET SEPARATION OK, 6 repos
bash scripts/org_delivery_audit.sh          # capture the evidence bundle into jolarca-compliance
terraform output -json compliance_summary
```

Archive the `org_delivery_audit.sh` output directory and the final
`terraform plan` transcript into `jolarca-compliance` as the CC8.1 evidence
for this change.

---

## Step 9 — Hand over

```bash
gh variable set STATE_MIGRATION_COMPLETE --body true \
  --repo jolarca-dev/jolarca-control
```

From this moment `jolarca-control` is authoritative and `apply.yml` will run on
merge to `main`. Remove the `NOT YET AUTHORITATIVE` banner from `main.tf` and
`README.md` in the same PR that flips the variable.

---

## Rollback

Rollback is only meaningful **before** step 8.

1. Stop. Do not run any further `terraform` command in either root.
2. In `jolarca-control`: `terraform state pull > /tmp/abandoned.json`, then
   delete the local `terraform.tfstate`. Nothing was applied, so there is
   nothing to undo on GitHub.
3. In the old root: restore the step-0 backup over
   `terraform/environments/production/terraform.tfstate`, verify the SHA256
   matches, and `git revert` the config-freeze PR so the module is whole again.
4. Confirm with `terraform plan -refresh=false` in the old root that it shows
   no changes.
5. File the incident in `jolarca-compliance` with the plan transcript.

After step 8, rollback means reversing individual resources with targeted
`terraform state mv`/`rm` — not restoring a file, because by then the old
root's config no longer declares those resources.
