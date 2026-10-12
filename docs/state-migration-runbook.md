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

Branch protection import IDs are the part most likely to be wrong — and the
original instruction here ("key it by the GraphQL node ID of the rule, fetch
with `branchProtectionRules(first: 5)` on Repository") was **wrong on both
counts** and was corrected by reading the provider source rather than the docs:

- `integrations/github` v6.13.0, `github/resource_github_branch_protection.go`:
  `Importer: {State: resourceGithubBranchProtectionImport}` calls
  `parseID2(d.Id())` → `(repoName, pattern)`, then resolves the repository node
  ID and the rule ID itself via `getBranchProtectionID(repoID, pattern)` before
  calling Read. **The import ID is `<repo-name>:<pattern>`, e.g.
  `jolarca:main`.** A raw `BPR_…` node ID has no `:` and fails to parse.
- The `id` attribute *stored in state* is the `BPR_…` node ID (Read keys on
  `node(id: $id)`). Import ID ≠ state ID. That distinction is what makes this
  step look contradictory when compared with `terraform state show`.
- `Repository.branchProtectionRules` is not a field in the current GraphQL
  schema; the reachable path is
  `repository{branch(name:"main"){branchProtectionRule{id}}}`.

Verified inventory for `jolarca-dev` on 2026-10-12 (`gh api
repos/jolarca-dev/<repo>/branches/main/protection`, read-only):

| Live state | Repos |
|---|---|
| Rule exists, already in Terraform state | `jolarca-hermes-agents` |
| Rule exists, **not** in state → import | `jolarca`, `jolarca-compliance`, `jolarca-control`, `jolarca-data`, `jolarca-docs`, `jolarca-identity`, `jolarca-infrastructure`, `jolarca-legal`, `jolarca-observability`, `jolarca-payments`, `jolarca-runbooks`, `jolarca-security`, `.github` (`health[0]`) |
| **No rule** (HTTP 404 "Branch not protected") → cannot import, apply will create | `jolarca-consent`, `jolarca-dr`, `jolarca-vendor` |
| Rule exists with `required_status_checks: null` (no contexts configured) | `jolarca-data`, `jolarca-identity`, `jolarca-legal`, `jolarca-security` |

Import the thirteen existing rules (operator-run: §5 forbids an agent executing
`import`/`state rm`), then verify the count before planning:

```bash
cd /opt/jolarca/repos/jolarca-control
for r in jolarca jolarca-compliance jolarca-control jolarca-data jolarca-docs \
         jolarca-identity jolarca-infrastructure jolarca-legal \
         jolarca-observability jolarca-payments jolarca-runbooks jolarca-security; do
  terraform import -input=false "github_branch_protection.main[\"$r\"]" "$r:main" || echo "FAILED: $r"
done
terraform import -input=false 'github_branch_protection.health[0]' '.github:main'
terraform state list | grep -c branch_protection   # expect 14
```

> `terraform import` on a `for_each`/`count` address must be quoted exactly as
> above (the shell otherwise eats the brackets), and a `for` loop that errors on
> its first iteration can silently skip the rest — the `|| echo FAILED` and the
> post-loop count are both mandatory, per D-13's state-rm lesson.

**Do not apply on the strength of a green import.** The imports were run on
2026-10-12 and `terraform state list | grep -c branch_protection` returned
**14**, as predicted. A full-refresh plan with the operator's token then reported:

```
Plan: 3 to add, 25 to change, 0 to destroy
Outputs: compliance_summary.protected_repos 13 -> 16
```

The three adds are exactly `jolarca-consent`, `jolarca-dr`, `jolarca-vendor` — the
repos with no live rule — so the inventory above held. `0 to destroy` held too.
What did **not** hold is the idea that the remaining 25 are reconciliations: Terraform
itself lists six changes that alter a live control, and `check_plan_safety.sh`
would pass every one (it refuses destroy / replace / visibility only).

| Change in the plan | Repos | Direction | Why it needs a human, not a green gate |
|---|---|---|---|
| `require_code_owner_reviews = true -> false` | `jolarca-docs` | **removes** | the fleet's only live code-owner gate (D-54) |
| `require_signed_commits = true -> false` | `jolarca-docs` | **removes** | live requires signed commits; `terraform.tfvars` sets `enforce_signed_commits = false`, so the same unreviewed apply turns off a second control on the same repo (D-57) |
| `restrict_pushes { push_allowances = ["/JourneyOfLife"] -> null }` | `jolarca-payments` | **removes** | deletes the whole push-restriction rule from `main` on the PCI-scoped repo, so any writer can push there. The allowance is also a **cross-plane actor name** (ADR-0004) that no file-based audit can see — `check_fleet_separation.sh` greps files, not live GitHub config |
| `- restrict_pushes { blocks_creations = false, push_allowances = [] }` | 12 more | removes | an empty restriction rule disappears; low impact, but it is a change nobody asked for and it will recur until the config expresses it |
| `- template { owner = "journeyoflife-org", repository = "jol-repo-template" }` | `jolarca-legal` | removes | a live template source pointing at the **mission platform** org — the exact separation ADR-0004 exists to enforce. Removing it is right for separation and should be recorded as such, not landed as a side effect |
| `required_linear_history = false -> true`, `require_conversation_resolution = false -> true` | `.github`, `jolarca`, `jolarca-payments` | adds | strengthening; on a single-operator repo these are workflow rules that can block merges, so they are accepted in writing or deferred per repo |
| `has_issues` | `jolarca` `false -> true`, `jolarca-data` `true -> false` | both ways | declared settings disagree with live on both; `jolarca-data` loses its issue tracker on merge |
| `secret_scanning` / `secret_scanning_push_protection` `disabled -> enabled` | `jolarca-docs`, `-observability`, `-runbooks`, `-security` | adds | welcome, and it should land — as its own reviewed change |

Contexts are now reconciled and the plan proves it: after #67 there is **no
`~ contexts` line for `jolarca`** (12 declared = 12 live) and `jolarca-identity`
shows `+ contexts = ["gitleaks (full history)", "shellcheck"]` — the two names its
workflows actually report, instead of the unproducible `ci,security,lint`.

Apply is currently **blocked anyway**, and not by policy: `terraform plan` in
Actions cannot read organisation settings or acquire the state lock under
`TFC_TOKEN`, while the identical command succeeds with the operator's own user
token. The secret authenticates — `terraform init` selects
`jolarca-dev/jolarca-control` — but its identity lacks the org-level privileges a
run needs (D-56, root cause proven 2026-10-12). Fix it by issuing the token from
the owner account, or by granting the service account's team organisation read
plus workspace **Runs: Plan + Apply**.

Order matters: `apply.yml` uses the same secret, so repairing it re-enables an
unattended `terraform apply -auto-approve` of everything above. Attach required
reviewers to the `production` environment first (D-58 — it currently has
`protection_rules: []`). And do not work around the lock with `-lock=false` —
against single-copy state (D-55) the lock is the only thing preventing two
concurrent writers.

### Considered and rejected: moving the backend to local for the first deploy

Proposed 2026-10-12: drop the `cloud {}` block, apply from the laptop, pay for
HCP later, then restore `Validate & Plan`. It does not solve the problem it is
aimed at, and it opens two worse ones. Measured reasoning, kept here so nobody
re-litigates it:

1. **The blocker is a credential, not the backend, and it costs nothing.** The
   same plan that fails in Actions succeeds with the operator's own user token
   (exit 2, 623 lines). Putting a token from that identity into `TFC_TOKEN` makes
   `Validate & Plan` green for $0; the Free tier's 500-resource ceiling is
   irrelevant at 48. Paying is not a prerequisite for the gate.
2. **A local backend turns a read failure into a write hazard.** `terraform.tfstate`
   is gitignored, so CI would check out an *empty* state and plan to **create**
   all sixteen repositories, their branch protection and the
   `github_repository_file` SECURITY.md/CODEOWNERS contents. `apply.yml`'s only
   hard gate is `Assert state migration complete`, which reads
   `vars.STATE_MIGRATION_COMPLETE` and would still pass; `check_plan_safety.sh`
   refuses destroy / replace / visibility and demonstrably let `3 to add` through.
   This is the exact failure already lived once: applying from a root without
   state returned 422 "name already exists" and then needed `state rm` loops to
   unwind.
3. **State would have one copy on one disk, with the backup gate proven inert**
   (D-55: `scripts/state_backup.sh` exits 1 against the 0-byte file, no
   `docs/backup-log.tsv`). Migrating back later needs interactive
   `terraform init -migrate-state`, reopening a dual-ownership window (D-13).

What was done instead, immediately: a read-only `terraform state pull` (serial 14,
7 resource blocks) snapshotted to
`/opt/jolarca/backups/terraform/jolarca-control-hcp-serial14-2026-10-12.json.gz`
— gzip, **not** age-encrypted, so treat it as insurance against accidental loss,
not as the D-55 control. Current size of the authoritative state, measured the same
time: `terraform state list | wc -l` = **48** instance addresses and HCP
`resource-count: 48` (35 before the thirteen imports) — so the "35 resources"
figure dated 2026-10-12 in ADR-0006 §7 is a superseded observation, not a target.
The correct sequence is: gate the environment (D-58) → fix the token's identity
(D-56) → decide D-54 and D-57 → apply once, with a human reading the plan.

Plan, then read it line by line:

```bash
cd /opt/jolarca/repos/jolarca-control
terraform init -input=false
terraform plan -input=false -no-color -out=tfplan | tee plan.txt
```

**Acceptance criteria for this plan — all must hold.** Rewritten 2026-10-12: the
previous version of this list still described the pre-migration world ("six
repositories", "the only in-place updates are the D-01 visibility changes (four
repos `public → private`)"), and D-01 has since been resolved the other way —
GitHub moved the fleet public and every `repos/*.yml` now declares
`visibility: public`. Applying against the old list would have read a plan
containing real regressions as "as expected".

- [x] `0 to add` other than the three protection rules that genuinely do not
      exist live yet (`jolarca-consent`, `jolarca-dr`, `jolarca-vendor`) —
      measured: `3 to add`, those three, and no others
- [x] `0 to destroy`, no `must be replaced` — measured
- [x] **no `~ contexts` line on any repository** — satisfied by #67 for
      `jolarca` and `jolarca-identity`; `jolarca-data`, `-legal`, `-security`,
      `-consent`, `-dr`, `-vendor` still gain contexts, which Context Parity
      (`scripts/check_declared_contexts.py`, 16 checked / 16 clean) certifies as
      producible but does not certify as *intended*
- [ ] no `~ require_code_owner_reviews` / `~ require_signed_commits` where live
      is `true` — **currently violated on `jolarca-docs`** (D-54, D-57); the
      removal must be either exempted or accepted in writing before any apply
- [ ] no `- restrict_pushes` on `jolarca-payments` — **currently violated**
      (D-57); deleting the rule opens `main` to every writer on a PCI-scoped repo
- [x] every one of the **sixteen** allow-list repositories appears exactly once,
      plus `.github` as `github_branch_protection.health[0]` — 14 in state +
      3 created = 17 addresses
- [ ] `require_conversation_resolution` / `required_linear_history` changing
      `false → true` is either accepted in writing here or deferred per repo —
      it is a behaviour change on live repositories, not a no-op

If `destroy` or `replace` appears anywhere: **stop**, restore from the step-0
backup, and diagnose. `prevent_destroy` should already have aborted the plan.

---

## Step 7 — Decide the visibility question before applying — **SUPERSEDED**

This step asked the owner to choose between making four repos private and
keeping them public. The choice was taken out of the control plane's hands:
GitHub migrated the fleet public, `policy/compliance-gates.yml` records D-01 as
`RESOLVED — forced migration`, and all sixteen `repos/*.yml` entries now declare
`visibility: public`. Do not re-open it here.

What survives this step unchanged is its **doctrine**, and it is the reason step 6
carries the acceptance list above: *split the adoption from the contested change.*
Apply the imports with no other diff, then land each behavioural change as its own
reviewed PR. The live contested item is now **D-31 / D-52** — regulated records
(RoPA, KYC, DPAs, network topology) sitting in public git — and its remediation is
moving those records out, **not** flipping visibility: privating a governed repo
makes this control plane's `Context Parity` required context exit 2, which is why
D-31's original "flip private" option was withdrawn on 2026-10-06.

So the split still applies, just not to visibility: **apply the adoption first
with nothing else changing**, then land each behavioural change (contexts,
`strict`, linear history, code-owner reviews, conversation resolution) as its own
reviewed PR. Two small auditable changes beat one big one. The old instruction to
"temporarily set the four YAML entries to their live value (`public`)" is obsolete
— they already declare `public`.

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
