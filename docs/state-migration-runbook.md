# State Migration Runbook — `jolarca-infrastructure` → `jolarca-control`

**Status:** COMPLETE (2026-10-10) — HCP Terraform workspace `jolarca-dev/jolarca-control`
is live (35 resources at completion; **48** when re-measured 2026-10-15, execution
mode `local`); `STATE_MIGRATION_COMPLETE=true` is set — which means the CI apply
gate is **open**, not closed; `TFC_TOKEN`
secret is configured. `jolarca-control` is authoritative.
**Caveat added 2026-10-26 (D-85):** "COMPLETE" was true of *this* root's state and
false of step 1's deliverable in the other root — the freeze existed only on one
workstation until `jolarca-infrastructure` PR #49. The legacy root's local
`terraform.tfstate` also does not report zero resources: serial **37** with one
address, `github_repository_file.security_md` at `instances: 0`, plus 8 stale
state copies in the same gitignored directory. Read "complete" as "the new root is
authoritative", not as "the old root is inert".
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

**Status correction (2026-10-26, D-85).** This step was written up as "already
applied" and it was true of one workstation and false of the repository: at
`8f02d17` (`jolarca-infrastructure` `origin/main`, public) `var.org` still
defaulted to `journeyoflife-org` in both files, `module "github_org"` was live,
there was no committed `terraform.tfvars` for that environment, `git grep -n
lifecycle HEAD -- terraform/environments/production terraform/modules/github-org`
returned nothing, and `git log --all -S "FROZEN — DO NOT PLAN OR APPLY"` returned
zero commits. The check below could not have caught it, because every command in
it greps the **working tree**. It now greps the committed tree.

Applied in the working tree since 2026-09-25; landed as
`jolarca-infrastructure` **PR #49** (`2eab214` + `693ec82`, the second commit
adding the `.github/CODEOWNERS` that repo's required `compliance` context demands
— it was the only fleet repo missing it, which is why nothing had merged there
since 2026-08-31). Verify against git, not against this host:

```bash
cd /opt/jolarca/repos/jolarca-infrastructure
git fetch origin main
# Read the COMMITTED tree. `grep -n <path>` answers a question about one host.
git show origin/main:terraform/modules/github-org/variables.tf \
  | grep -n 'default' | grep -i org                                  # D-06 fix
git show origin/main:terraform/environments/production/variables.tf \
  | grep -n 'default' | grep -i org
git show origin/main:terraform/modules/github-org/main.tf \
  | grep -n 'prevent_destroy'
git grep -n 'prevent_destroy' origin/main -- terraform/modules/github-org
git grep -n 'FROZEN' origin/main -- terraform/modules/github-org/versions.tf
git ls-tree origin/main terraform/modules/github-org/ | grep -c '\.bak'  # D-12: 0
```

Reading the result: these are `grep` exits, so **no output plus exit 1 means the
marker is absent from the committed tree** — that is a finding, not §3's `2`
("could not verify"), which here would be a failed `git fetch` or a path git has
never seen. Run against `origin/main` on 2026-10-26 the block printed
`default     = "journeyoflife-org"` twice, nothing for `prevent_destroy`, and `1`
for the `.bak` count: step 1 is satisfied on `fix/land-frozen-root-step1`, not on
`main`, and this step is not closed until PR #49 merges.

Expected: `org` defaults to `jolarca-dev`, `prevent_destroy = true` on both
`github_repository` resources, a FROZEN banner in `versions.tf`, no `.bak`
file. Land this as a signed PR **before** step 2 so the freeze is in git
history, not just on disk — the sentence this runbook failed to obey for a
month, and the reason D-85 exists.

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
| `TF_GITHUB_TOKEN` | Secret (env `production`) | fine-grained PAT: `jolarca-dev`, Administration **read/write**, Metadata read |
| `TF_GITHUB_TOKEN_READONLY` | Secret | fine-grained PAT: `jolarca-dev`, Administration **read**, Metadata read |

Scope note corrected 2026-10-19 (D-76): the `github_repository_vulnerability_alerts` resources
at `repositories.tf:93` and `health-repo.tf:69` refresh over
`GET /repos/{owner}/{repo}/vulnerability-alerts`, and GitHub's own fine-grained permission
table puts that endpoint under **Repository permissions → Administration** at `read`
(`PUT`/`DELETE` at `write`). There is **no** separate `Vulnerability alerts` permission to
select — an earlier revision of this table (2026-10-17) named one, and it sent the operator
hunting for a scope that does not exist. What the plan actually needed was **Administration
read** on the read-only PAT; proven by `HTTP/2.0 204 No Content` from
`gh api -i repos/jolarca-dev/jolarca-dr/vulnerability-alerts` with that PAT. Without it every
`github_repository_vulnerability_alerts` read fails `403 Resource not accessible by personal
access token` in refresh, i.e. inside `terraform plan` itself.

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

### Step 6 status, re-measured 2026-10-15 — the imports are DONE, the reconciliation is not

The table above is a dated record of 2026-10-12 and is kept as written. It is no
longer the live picture, and reading it as one would send an operator to import
objects that are already adopted:

```bash
terraform state list | grep -c branch_protection     # → 14  (was 1 on 2026-10-12)
terraform state list | wc -l                         # → 48 addresses; workspace resource-count: 48
```

`github_branch_protection.health[0]` plus `main["…"]` for 13 repos are in state.
The three absentees — `jolarca-consent`, `jolarca-dr`, `jolarca-vendor` — have **no
live rule** either (`gh api repos/jolarca-dev/<r>/branches/main/protection` →
HTTP 404 `"Branch not protected"`, measured 2026-10-15), so there is nothing to
import for them and the plan's `3 to add` is not an overwrite of a legacy rule
either — all three carry an **active, undeclared `protect-main` ruleset**
(`gh api repos/jolarca-dev/jolarca-vendor/rulesets` → `protect-main`,
`enforcement: active`, `current_user_can_bypass: never`, measured 2026-10-15).
So the create would lay a **second, differently-configured enforcement mechanism**
beside the ruleset that is actually in force (D-46), not "add protection". An
earlier draft of this section and of D-61 said the creates merely add protection;
that was wrong and is corrected here. The open decision is D-46's: adopt the
rulesets as `github_repository_ruleset`, or delete them and let the legacy rule
stand — not a blind create.

A refreshed plan on 2026-10-15 rendered `3 to add, 25 to change, 0 to destroy`, and
`scripts/check_plan_safety.sh` refused it only after D-61's fix. Per-resource,
read from `terraform show`. **Two rows below are marked FIXED: the declaration was
repaired on 2026-10-15, which took the plan from 25 changes to 20** — and the
largest weakening in it disappeared entirely:

| Class | Change | Resources | Status |
|---|---|---|---|
| **WEAKEN → FIXED** | `- restrict_pushes { blocks_creations, push_allowances }` | 11 protection rules | `branch-protection.tf` never declared a block that policy (`repo-defaults.yml: restrict_pushes: true`) and all eleven live rules had, so any apply deleted the push restriction fleet-wide. Now declared per repo from `terraform state show`, **including `jolarca-payments`' `push_allowances = ["/JourneyOfLife"]`** — a blanket `[]` would have removed the operator's own allowance, i.e. fixing one regression by adding another. Zero `restrict_pushes` lines remain in the plan. |
| **WEAKEN → FIXED** | `~ required_status_checks { contexts = [ - "frontend-build", - "frontend-openapi-drift", - "frontend-unit" ] }` | `jolarca` | Those three are live-required and still produced: `gh api repos/jolarca-dev/jolarca/commits/main/check-runs` lists all of them among 17 recent checks. `repos/jolarca.yml` was stale at 9 of 12; now declares 12, so the flagship keeps its checks. |
| **WEAKEN → ACCEPTED** | `~ require_code_owner_reviews = true -> false`, `~ require_signed_commits = true -> false` | `jolarca-docs` | Deliberate, and aligned to policy: D-20 (no teams can satisfy code-owner review) and D-05 (`github_repository_file` automation commits to fleet repos and cannot sign). Recorded rather than quietly applied: `docs/drift-findings.md` D-20 correction (b) already tracks that seven repos declare `true` against the `false` baseline. |
| TIGHTEN (accepted, policy says on) | `~ require_conversation_resolution = false -> true`, `~ required_linear_history = false -> true` | `.github` (`health[0]`), `jolarca`, `jolarca-payments` | Enacts `repo-defaults.yml`; live is behind policy. |
| TIGHTEN (accepted, verified producible) | `+ required_status_checks { contexts = […] }` | `jolarca-data` (and `-legal`, `-security` where absent) | Live rule has no required contexts. `scripts/check_declared_contexts.py` (exit 1) flags only `jolarca-identity` as unproducible, so data's declared contexts are producible — adding them will not deadlock its merges. |
| TIGHTEN | `~ allow_merge_commit`/`~ allow_rebase_merge` → false, `~ delete_branch_on_merge` → true, `~ has_projects` → false, topics, description | `jolarca-docs`, `-observability`, `-runbooks`, `-security`, `-vendor`, `-identity`, `-dr`, `-legal`, `-payments`, `-control`, `-data`, `-compliance` | Enforces the squash-only linear-history baseline from `policy/repo-defaults.yml`. |
| NOT A DEFECT | `branch_protection`, `compliance_summary`, `protected_repos` | — | An earlier draft of this table listed these as "attributes that are not `github_repository` arguments" on `jolarca-vendor`. Wrong: they are the plan's **Outputs** section (`protected_repos = 13 -> 16`), which the attribute parser had swept into the last resource block. `terraform state show 'github_repository.repo["jolarca-vendor"]'` confirms no such attributes exist. Nothing to investigate. |

### Step 6 packet, walked line by line (re-measured 2026-10-15 on `main` 690dcff, after #72/#73/#74)

`terraform plan -input=false -no-color -out=tfplan` → **`0 to add, 19 to change, 0 to destroy`**.
Every line below was read from `terraform show -no-color`, not inferred. Sign off by ticking a
row; do not skip the gate to land them (`scripts/check_plan_safety.sh` exits 1 on all eight
protection lines, so no CI apply can run them).

**Two rows in this table are fixes rather than decisions**, because walking the plan exposed them
as declaration bugs (D-67, D-68): `jolarca-identity`'s required contexts were rewritten to the two
names its workflow actually reports, and `jolarca-data`'s `has_issues` was corrected to the live
`true`. Both are in the PR that carries this packet.

| # | Change | Object | Class | Basis | Sign-off |
|---|---|---|---|---|---|
| 1 | `~ require_conversation_resolution = false -> true`, `~ required_linear_history = false -> true` | `.github` (`health[0]`) | TIGHTEN | `policy/repo-defaults.yml` baseline; live is behind policy | [ ] |
| 2 | same two attributes | `github_branch_protection.main["jolarca"]` | TIGHTEN | same | [ ] |
| 3 | `~ require_conversation_resolution = false -> true` | `main["jolarca-payments"]` | TIGHTEN | same | [ ] |
| 4 | `+ required_status_checks { contexts = ["ci","compliance","security"], strict = true }` | `main["jolarca-data"]` | TIGHTEN | declared; **producible** — `check_declared_contexts.py` reports 16/16 clean | [ ] |
| 5 | `+ required_status_checks { contexts = ["gitleaks (full history)","shellcheck"], strict = true }` | `main["jolarca-identity"]` | TIGHTEN, **was a deadlock** | previously declared `ci/security/lint`, which that repo has never reported; applying it would have blocked every merge (D-68). Now the two real job names | [ ] |
| 6 | `+ required_status_checks { contexts = ["ci","security"], strict = true }` | `main["jolarca-legal"]` | TIGHTEN | declared, producible | [ ] |
| 7 | `+ required_status_checks { contexts = ["markdown-lint","policy-tests","secret-scan","yaml-lint"], strict = true }` | `main["jolarca-security"]` | TIGHTEN | declared, producible | [ ] |
| 8 | `~ require_signed_commits = true -> false` and `~ required_pull_request_reviews { require_code_owner_reviews = true -> false }` | `main["jolarca-docs"]` | **WEAKEN — policy-directed** | D-05 (`github_repository_file` automation cannot sign) and D-20 (no teams exist, so code-owner review is inert and unsatisfiable). Both deviations are dated in `policy/compliance-gates.yml` | [ ] |
| 9 | `~ has_issues = false -> true` | `repo["jolarca"]` | TIGHTEN (capability) | declares `has_issues: true`; flagship has 0 open issues today, so nothing is disturbed. Fleet default is false; per-repo override is legal | [ ] |
| 10 | `~ description` | `repo["jolarca-control"]` | METADATA | declared | [ ] |
| 11 | `~ allow_merge_commit true->false`, `~ allow_rebase_merge true->false`, `~ delete_branch_on_merge false->true`, `~ has_projects true->false`, `~ security_and_analysis { secret_scanning, secret_scanning_push_protection: "disabled" -> "enabled" }`, `+ description`, `+ ignore_vulnerability_alerts_during_read = false`, `~ topics` | `repo["jolarca-docs"]` | TIGHTEN + squash-only baseline | `repo-defaults.yml`; scanning enablement is mandatory per `compliance-gates.yml`. Consequences to notice before ticking: merge/rebase buttons stop working, and head branches are deleted on merge | [ ] |
| 12 | `+ description`, `+ ignore_vulnerability_alerts_during_read = false`, `~ topics` | `repo["jolarca-dr"]` | METADATA | declared | [ ] |
| 13 | squash-only + `delete_branch_on_merge`, `has_projects false`, description, topics, `ignore_vulnerability_alerts_during_read` | `repo["jolarca-identity"]` | TIGHTEN | as row 11, without the scanning block (already enabled live) | [ ] |
| 14 | **`- template { owner = "journeyoflife-org", repository = "jol-repo-template", include_all_branches = false }`** | `repo["jolarca-legal"]` | **REMOVE — ADR-0004 alignment** | Nothing in this repo declares a template source, so Terraform removes the live one. `journeyoflife-org` is the mission platform, not the marketplace: this is a cross-estate reference inside a PCI-scoped repo that `check_fleet_separation.sh` cannot see (file-based; D-57). Removing it is the ADR-aligned outcome; the residual is that new-repo-from-template sync stops, which `include_all_branches = false` meant it was barely doing | [ ] |
| 15 | squash-only block + `security_and_analysis` enable | `repo["jolarca-observability"]` | TIGHTEN | as row 11 | [ ] |
| 16 | `+ description`, `+ ignore_vulnerability_alerts_during_read = false`, `~ topics` | `repo["jolarca-payments"]` | METADATA | declared; payments' push allowance is unchanged (`/JourneyOfLife` kept, #72) | [ ] |
| 17 | squash-only block + `security_and_analysis` enable | `repo["jolarca-runbooks"]` | TIGHTEN | as row 11 | [ ] |
| 18 | squash-only block + `security_and_analysis` enable | `repo["jolarca-security"]` | TIGHTEN | as row 11 | [ ] |
| 19 | squash-only block, `has_projects false`, description, topics | `repo["jolarca-vendor"]` | TIGHTEN | as row 11, scanning already enabled live | [ ] |

`ignore_vulnerability_alerts_during_read = false` is a provider read-time flag meaning *do not*
ignore Dependabot alerts; it is not an alert suppression and changes nothing live.

**After all 19 are decided, the apply is still not safe by itself.** Remaining gates: D-46's
endgame (three repos whose declared checks are enforced by nothing), D-66 (six rules without a
push restriction while policy demands one), D-02's cadence/off-host destination, and D-56's CI
token — which must be last, because repairing it converts this table from "refused" into "applied".

Remaining before any apply: the D-46 decision itself (the three creates are suppressed
meanwhile by `local.ruleset_protected_repos`, which is an interim and NOT a resolution —
those repos' declared required contexts are enforced by nothing today), and the six repos
whose live rules lack a push restriction while policy demands one (`jolarca-docs`,
`jolarca-hermes-agents`, plus the three ruleset-only repos and `.github`) — recorded as
**D-66**, deliberately not tightened as a side effect of fixing the deletions.

Re-measured after #72 and that exclusion: `Plan: 0 to add, 20 to change, 0 to destroy`.
`check_plan_safety.sh` on the `-no-color` text exits **1**, naming 8 in-place
`github_branch_protection` updates — four adding `required_status_checks` (`jolarca-data`,
`-identity`, `-legal`, `-security`), three setting `required_linear_history` /
`require_conversation_resolution` false→true (`jolarca`, `.health`, `jolarca-payments`), and
two landing D-20's deliberate deviations (`jolarca-docs`, `jolarca-payments`:
`require_signed_commits`, `require_code_owner_reviews` true→false). So the remaining diff is
tightening toward the declarations, not a weakening — reaching `0 to change` is now a
per-line human decision. The 11 `restrict_pushes` removals and the three creates described
above are gone (fixed in #72; suppressed per D-46).

Render the plan with **`-no-color`** for this gate, or it cannot see anything: measured on
one plan file, `terraform show tfplan` (840 ANSI escape bytes) made `check_plan_safety.sh`
report the plan clean while `terraform show -no-color tfplan` made it refuse the same 8
changes. The script now exits **2** on ANSI input rather than passing it (D-61, fourth
correction); the command earlier in this step already carries the flag, which is the habit
to keep.

The operator's path, in order, is the same one step 7's doctrine states: **land the
adoption alone first.** Narrow `repos/*.yml` / `terraform.tfvars` to the live
values for the three WEAKEN rows (or record each as an accepted change here), so a
refreshed plan reads `0 to change` for everything except the deliberate
tightenings; then apply; then land each behavioural change as its own reviewed PR.
The refusal gate stays in front of all of it, so "forgot to reconcile" now fails
CI rather than shipping.


Import the thirteen existing rules (operator-run: §5 forbids an agent executing
`import`/`state rm`), then verify the count before planning. **Retained for the
record and for any future re-adoption — as measured above it is already done**
(`terraform state list | grep -c branch_protection` → 14 on 2026-10-15; re-running
`terraform import` on an address already in state is a no-op at best and re-reads
live rules over adopted state at worst).

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

**Do not apply on the strength of a green import.** With the thirteen rules
adopted, `terraform plan` still proposes in-place changes ~~that the plan-safety
gate does not refuse (it catches destroy/replace/visibility only)~~ — **corrected
2026-10-15: the gate now refuses those classes too** (D-61 added protection
creates, every protection attribute in either direction including
`restrict_pushes` removal, and security-feature disables), so an unreconciled plan
fails before `apply` rather than landing silently. Measured
declared-vs-live deltas on 2026-10-12 that a human must decide per repo first:

| Repo | Live | Declared | Effect of applying as declared |
|---|---|---|---|
| `jolarca` | 12 contexts | 9 | **removes** `frontend-unit`, `frontend-openapi-drift`, `frontend-build` from required checks — weakens the flagship gate |
| `jolarca` | `required_linear_history=false` | `true` | forces linear history on the app repo |
| `jolarca-docs` | `require_code_owner_reviews=true` | `false` (tfvars) | **removes** code-owner review |
| `jolarca-identity` | no contexts | `ci,security,lint` | those three are **not producible** by its workflows (it reports `gitleaks (full history)`, `shellcheck`) → every merge deadlocks (L-19, S1) |
| `jolarca-data`, `jolarca-legal`, `jolarca-security` | no contexts | 2–3 each | adds required checks that do exist — strengthening, but unreviewed |
| 13 repos | `require_conversation_resolution` unset | `true` | turns the requirement on fleet-wide |

The repo's own doctrine is to encode the **verified live** value and raise it
deliberately (see D-08, D-20 correction (b)). So: reconcile `repos/*.yml` and
`terraform.tfvars` to the table above, or record each strengthening as an
accepted change, before letting `apply.yml` land it.

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

- [ ] `0 to add`. Historical note: for a while this line allowed three exceptions
      (`jolarca-consent`, `jolarca-dr`, `jolarca-vendor`), on the belief that applying
      would add protection there. Wrong twice over — those repos are enforced by ACTIVE
      undeclared rulesets (D-46), so a create layered a second mechanism, and their
      declared contexts were not being enforced by anything. They are now excluded from
      the resource until D-46 is decided, so `0 to add` is the real criterion.
- [ ] `0 to destroy`, no `must be replaced`
- [ ] **no `~ contexts` line on any repository** — a context list changing means
      `repos/<repo>.yml` disagrees with the live rule. The measured conflicts on
      2026-10-12 are `jolarca` (live 12 → declared 9) and `jolarca-identity`
      (declares `ci,security,lint`, which its workflows cannot report).
      ~~`check_plan_safety.sh` does not catch this class.~~ **Corrected
      2026-10-15: it does now** — `required_status_checks`, `restrict_pushes` and
      every other protection attribute are refused classes under D-61, so an
      unreconciled plan fails `Plan safety check` instead of reaching `apply`.
- [ ] no `~ require_code_owner_reviews` where live is `true` — `jolarca-docs` is
      live `true` and the fleet default in `terraform.tfvars` is `false`, so an
      unreviewed apply removes the only live code-owner gate in the fleet
- [ ] every one of the **sixteen** allow-list repositories appears exactly once,
      plus `.github` as `github_branch_protection.health[0]`
- [ ] `require_conversation_resolution` changing `unset → true` on the other 13
      repos is either accepted in writing here or deferred per repo — it is a
      behaviour change on live repositories, not a no-op

If `destroy` or `replace` appears anywhere: **stop**, restore from the step-0
backup, and diagnose. `prevent_destroy` should already have aborted the plan.

---

## Step 6b — The three ruleset-only repos (D-46 option A) — STAGED, NOT EXECUTED

`jolarca-consent`, `jolarca-dr` and `jolarca-vendor` are excluded from
`github_branch_protection.main` by `local.ruleset_protected_repos` and are protected only
by an active `protect-main` ruleset that no configuration declares. The decision was taken
on 2026-10-26 in favour of **option A — adopt the rulesets into Terraform**, with consent
first. The measured case for it is in `docs/drift-findings.md` D-46's decision packet, and
the prerequisite (the pre-apply gate could not see rulesets at all) is closed by D-84.

**Nothing in this section has been run.** Steps 2 and 3 are `terraform import`, which
AGENTS.md §5 reserves to the operator, and step 4 changes live protection, which
`scripts/check_plan_safety.sh` now refuses by design.

**1. Declare the resource with no intent to change it.** The HCL below mirrors consent's
live ruleset *exactly* (measured 2026-10-26 from `gh api repos/jolarca-dev/jolarca-consent/rulesets/24087580`),
so the plan after import must read `0 to add, 0 to change` for this address. It is written
here rather than committed as `rulesets.tf` deliberately: a declared-but-unimported ruleset
makes the plan want to **create a second ruleset beside the one in force**, and a `.tf`
merge arms `apply.yml`. Land this file only in the PR that runs step 2 immediately after.

```hcl
# rulesets.tf — D-46 option A, consent first.
# Mirrors live content measured 2026-10-26; changes NOTHING about what GitHub enforces.
# Import it before any plan that includes this file (step 2), and require 0 changes.
resource "github_repository_ruleset" "main" {
  for_each = toset(["jolarca-consent"]) # dr and vendor follow after a provider bump

  repository  = each.value
  name        = "protect-main"
  target      = "branch"
  enforcement = "active"

  conditions {
    ref_name {
      include = ["~DEFAULT_BRANCH"]
      exclude = []
    }
  }

  rules {
    deletion             = true
    non_fast_forward     = true
    required_linear_history = true
    # Deliberately absent, because live lacks them: pull_request and
    # required_status_checks. Adding them is step 4, a separate reviewed change.
  }

  # Live `bypass_actors` is [] and `current_user_can_bypass` is never. Do not add a
  # bypass_actors block: an empty list here means nobody, including admins, gets around it.
}
```

**2. Import (operator-run).** The provider's importer calls `parseID2`, which splits on
`:` — so the id is `<repo>:<ruleset_id>`, and the **numeric** ruleset id from the list call,
not the name (the `…/rulesets/protect-main` form returns HTTP 404).

```bash
cd /opt/jolarca/repos/jolarca-control
terraform init -input=false
terraform import -input=false \
  'github_repository_ruleset.main["jolarca-consent"]' 'jolarca-consent:24087580'
# Import ID ≠ state ID again (D-56's sibling trap): state `id` becomes 24087580, and
# `terraform state show` prints the numeric ruleset id, not the pair you typed.
terraform state list | grep -c ruleset   # expect 1
```

**3. Prove the adoption is inert before doing anything else.**

```bash
terraform plan -input=false -no-color -out=tfplan6b
bash scripts/check_plan_safety.sh <(terraform show -no-color tfplan6b)   # expect exit 0
terraform show -no-color tfplan6b | grep -A3 'github_repository_ruleset'  # expect: no change block
```

`-no-color` is not optional (D-61's fourth correction: ANSI bytes defeat every pattern in
that gate, which is why the script now exits 2 on coloured input). If the plan shows *any*
change on the ruleset address, stop: the config does not mirror live content, and applying
it would rewrite a protection object this root has just adopted.

**4. Then, and only then, close the actual gap** — consent declares 7 required contexts and
nothing enforces them; its ruleset also has **no `pull_request` rule**, so `main` is directly
pushable (the mechanism behind the historical no-PR commit). That change is
`rules { pull_request { … } required_status_checks { required_check { context = … } } }`.
It is a protection-layer mutation and `check_plan_safety.sh` now refuses it by name, so it is
applied by hand after (a) `make context-parity` proves each of the 7 names is producible on a
PR in that repo — the D-44/D-47 deadlock class, already paid for once on `jolarca-identity`,
and (b) the three inexpressible declaration keys (`restrict_pushes`,
`require_conversation_resolution`, per-rule `enforce_admins`) are either dropped from
`repos/jolarca-consent.yml` or recorded as a dated deviation in
`policy/compliance-gates.yml#exceptions.active`, so `make drift` stops reporting a permanent
false red.

**5. dr and vendor wait.** Their payloads carry `dismissal_restriction` and
`require_extra_approval_for_unattributed_changes`, neither of which provider 6.13.0 models
(`grep -c` over `resource_github_repository_ruleset.go` at tag v6.13.0 → 0). An update PUTs
only what the provider knows, so both revert to GitHub's defaults on the first change. They
are at their defaults today, so the expected delta is nil — but that is an inference, not a
measurement, and this runbook does not accept inference as a reason to touch protection.
Revisit after a provider bump models the fields, or after the defaults are accepted in
writing.

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
