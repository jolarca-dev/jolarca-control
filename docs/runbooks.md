# Runbooks — Jolarca Control Plane Operations

All runbooks assume the org is `jolarca-dev` and that `gh` is authenticated.
Every one of them is read-only unless a step explicitly says otherwise.

> **Until `docs/state-migration-runbook.md` completes**, RB-01 and RB-02 cannot
> be executed — this control plane does not yet own the state. RB-03, RB-05,
> RB-06 and RB-07 are live now.

## RB-01: Add a New Repository

### Preconditions
- Change record opened per `docs/change-management.md`
- Name matches `jolarca` or `jolarca-<suffix>` — anything else fails the
  ADR-0004 R1 precondition in `repositories.tf`, the naming rule in
  `validate_repos.py`, **and** `check_fleet_separation.sh`. Three independent
  guards; do not weaken any of them to make a name fit.

### Steps
1. Create `repos/<repo-name>.yml`. Copy the closest existing entry as a
   starting point — `jolarca-data.yml` for platform, `jolarca-legal.yml` for
   governance, `jolarca-infrastructure.yml` for devops.
2. Set `compliance.data_classification`. If it is `confidential` or
   `restricted`, `visibility` **must** be `private` or validation fails.
3. Set `branch_protection.main.required_status_checks.contexts` to contexts
   that the repo's own workflows actually report. A context that never reports
   blocks every PR forever.
4. `python3 scripts/validate_repos.py` — must pass.
5. `python3 scripts/compliance_check.py` — `overall_status` must be `pass`.
6. Open a PR. `plan.yml` posts the plan as a sticky comment;
   `fleet-separation-guard.yml` re-checks the org.
7. Read the plan: exactly one new `github_repository`, one
   `github_repository_vulnerability_alerts`, one `github_branch_protection`.
   Anything else means the allow-list disagrees with reality.
8. Merge. `apply.yml` runs behind the `production` environment approval.

### Verification
```bash
gh repo view jolarca-dev/<repo-name> --json url,visibility,hasIssuesEnabled
python3 scripts/drift_detect.py            # expect drift_detected: false
bash scripts/check_fleet_separation.sh     # expect FLEET SEPARATION OK
```

## RB-02: Change Repository Visibility

**This is the highest-risk routine operation in the control plane.** A
public→private flip breaks forks, GitHub Pages, anonymous clones in other
orgs' CI, and any external contributor workflow. A private→public flip can
expose PCI-scope material.

### Preconditions
- Written risk assessment in the change record
- For public→private: enumerate what breaks (forks, Pages, anonymous CI clones)
- For private→public: `git log --all -p | grep -iE 'password|secret|token|BEGIN.*PRIVATE'`
  returns nothing, and history has been scanned by gitleaks

### Steps
1. Update `visibility` in `repos/<repo-name>.yml`.
2. `python3 scripts/validate_repos.py` — a `confidential`/`restricted` repo
   set to `public` fails here on purpose.
3. Open a PR and read the posted plan. Confirm the **only** change is
   `visibility`.
4. Merge. `apply.yml` will **refuse** — the
   `Refuse destructive or visibility-changing plans` step aborts on any
   `visibility` line in the plan. That is deliberate.
5. To proceed, run the apply manually inside the change window with the gate
   consciously overridden, and record the plan transcript as evidence:
   ```bash
   cd /opt/jolarca/repos/jolarca-control
   terraform init -input=false
   terraform plan -input=false -no-color -out=tfplan
   terraform show -no-color tfplan | tee visibility-change-plan.txt
   # READ IT. Then, and only then:
   terraform apply -input=false tfplan
   ```
6. Re-run `bash scripts/org_delivery_audit.sh` and archive the capture.

> Do not "fix" step 4 by deleting the gate from `apply.yml`. If visibility
> changes become routine, parameterise the gate with an explicit
> `ALLOW_VISIBILITY_CHANGE` variable so each override is a separate,
> attributable act.

## RB-03: Respond to Secret Exposure

### Steps
1. **Rotate first, clean second.** An unrotated secret in cleaned history is
   still live. Rotation: `docs/runbooks/github-token-rotation.md` for
   `TF_GITHUB_TOKEN` / `TF_GITHUB_TOKEN_READONLY`.
2. Confirm the exposure scope:
   ```bash
   gh api "repos/jolarca-dev/<repo>/commits?per_page=100" -q '.[].sha'
   ```
3. Purge from history:
   ```bash
   pip install git-filter-repo
   git filter-repo --replace-text expressions.txt --force
   ```
4. Force-push. Branch protection blocks this, so it needs a temporary
   override — which is itself a change requiring a record:
   ```bash
   gh api -X DELETE "repos/jolarca-dev/<repo>/branches/main/protection"
   git push --force origin main
   # Restore IMMEDIATELY from the allow-list, not from memory:
   ```
   Re-apply protection by running this control plane's apply, or with the exact
   JSON body recorded in `repos/<repo>.yml`. Never leave a repo unprotected
   overnight.
5. If the secret was a GitHub token, revoke it at
   `github.com/settings/tokens` **and** check the org audit log for use
   between exposure and revocation.
6. File the incident in `jolarca-compliance` with: timeline, exposure window,
   rotation evidence, audit-log review result, and whether GDPR Art. 33
   72-hour notification is triggered (`jolarca-compliance` holds the DPIA and
   the breach procedure).
7. Add the pattern to `policy/compliance-gates.yml` →
   `gates.secret_scan.implementation.custom_patterns` so it is caught next time.

## RB-04: Update a Compliance Gate

1. Edit `policy/compliance-gates.yml` — the gate definition.
2. Update `enforcement_matrix` if tier assignments change. Tiers here are
   `governance`, `platform`, `devops` only; `site` and `template` do not exist
   in the marketplace fleet.
3. Update the matching `required_status_checks.contexts` in `repos/*.yml`.
   **A gate whose context no repo requires is not a gate.**
4. `python3 scripts/validate_repos.py && python3 scripts/compliance_check.py`
5. If the gate needs a new required context on an existing repo, land the
   workflow **first**, confirm the context reports green, and only then add it
   to branch protection — otherwise every open PR blocks.
6. PR, review the plan, merge.
7. Tag-protection note: `policy/repo-defaults.yml` declares
   `tag_protection.enforced: false` because no rulesets exist org-wide (D-07).
   Implementing it means adding `github_repository_ruleset` resources — do not
   flip the policy flag without the resource behind it.

## RB-05: Quarterly Compliance Review

1. `python3 scripts/compliance_check.py --output quarterly-report.json`
2. Review each checklist: `audit/soc2-checklist.yml`,
   `audit/gdpr-checklist.yml`, `audit/iso27001-checklist.yml`,
   `audit/pci-dss-checklist.yml`
3. `bash scripts/org_delivery_audit.sh` — capture the live delivery chain for
   all six repos plus `.github`; archive into `jolarca-compliance`.
4. `python3 scripts/drift_detect.py` — investigate every line of output.
5. Re-verify the org-level findings that Terraform cannot manage:
   ```bash
   gh api orgs/jolarca-dev -q '{two_factor:.two_factor_requirement_enabled,
     members_create_repos:.members_can_create_repositories,
     default_perm:.default_repository_permission}'
   gh api orgs/jolarca-dev/teams -q length
   ```
   These close or reopen D-10, D-18 and D-19.
6. Walk `docs/drift-findings.md` end to end. Every finding must be either
   closed with evidence, or have a live review date.
7. Review `exceptions.active` in `policy/compliance-gates.yml` and the risk
   acceptance register in `docs/threat-model.md`. An exception past its expiry
   date is a finding.
8. Update `metadata.last_reviewed` / `next_review` in both policy files.
9. Archive the report and the audit capture in `jolarca-compliance`.

## RB-06: Fleet Separation Violation

Triggered by `fleet-separation-guard.yml` failing, or by
`check_fleet_separation.sh` printing `VIOLATION`.

**R2 — a `jolarca*` repo exists in the org but not in the allow-list:**
1. Identify it: `gh api orgs/jolarca-dev/repos -q '.[].name'`
2. Determine who created it and when:
   `gh api orgs/jolarca-dev/audit-log` (org owner token required).
3. Decide within 48 h (ADR-0004 R2): adopt or delete.
   - **Adopt** — add `repos/<name>.yml`, add an `import` block per runbook
     step 6, plan, apply.
   - **Delete** — only with a change record; check for open PRs, forks and
     CI references first.
4. File the incident in `jolarca-compliance` regardless of the choice.
   Out-of-band creation is an incident even when the repo turns out to be
   harmless.

**R3 — a `jol-*` entry appeared in this allow-list:** revert the PR. Mission
repos are governed by `jol-control`; there is no legitimate reason for one to
be here. If the intent was a shared repo, that is an architecture decision
requiring an ADR amendment, not an allow-list edit.

**R1 — a fleet entry is not named `jolarca*`:** rename the repo first, then the
allow-list entry. Renaming a repo invalidates Terraform's `for_each` key and
proposes destroy/recreate, so the state keys must be moved in the same window
— see `jolarca-infrastructure/scripts/terraform-state-rename-jolarca.sh` for
the precedent procedure.

## RB-07: Suspected State Compromise or Loss

See `docs/drift-findings.md` D-02 — state is currently a single local file.

1. Stop all applies in both roots.
2. If a backup exists (runbook step 0), restore and verify the SHA256.
3. If no backup exists, rebuild by import: the six repositories, six
   vulnerability-alert resources, six branch-protection rules and the health
   repo are all discoverable from the live API. Use the `import` block pattern
   in `docs/state-migration-runbook.md` step 6.
4. Never rebuild state by running `terraform apply` against an empty state —
   that attempts to create existing repositories.
5. File the incident in `jolarca-compliance`; loss of the sole record of
   resource ownership is itself reportable under ISO 27001 A.5.24.
