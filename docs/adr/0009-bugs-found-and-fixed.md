# Bugs Found and Fixed — 2026-09-28 Pre-Deployment Audit

This document records every defect discovered and remediated during the
pre-deployment compliance audit of 2026-09-28. Each bug is numbered,
categorised by severity, and linked to the compliance framework it implicates.

**SOC 2 CC8.1 / ISO 27001 A.8.32 / PCI-DSS 6.5.1** — change management
requires that defects found during pre-deployment are recorded and their
remediation verified.

---

## Bug F-01: Synthetic Secret Fixtures in Test Source (S0)

**Framework:** SOC 2 CC7.2 / ISO 27001 A.8.24 / GDPR Art.32
**Found in:** `tests/test_repo_readiness_audit.py` lines 515, 894
**Severity:** S0 (stop-work)

**Problem:** Two test fixtures contained literal strings matching secret
patterns:
- AWS access key ID fixture (matched `AKIA[0-9A-Z]{16}`)
- Stripe live secret key fixture (matched `sk_live_[0-9a-zA-Z]{24,}`)

Both were synthetic values, not real credentials. gitleaks and the readiness
audit's own regex sweep both flagged them, causing a permanent S0 BLOCK on
jolarca-control's readiness gate. An always-false S0 erodes control trust.

**Fix:** Runtime assembly via string concatenation:
```python
token = "AKIA" + "<body>"  # AWS fixture assembled at runtime
"config.py": "KEY = '" + ("sk_live_" + "<body>") + "'\n"  # Stripe fixture
```
Patterns used: `AKIA[0-9A-Z]{16}` and `sk_live_[0-9a-zA-Z]{24,}`.
The source no longer contains a literal matching either pattern. gitleaks
configured with path-based allowlist in `.gitleaks.toml` for historical
commits.

**Verification:** `gitleaks git . --no-banner` → "no leaks found" (exit 0).

**Correction (2026-10-07, A-04):** the working-tree fix stands and is
re-verified (`grep -c 'AKIA[0-9A-Z]{16}' tests/test_repo_readiness_audit.py`
returns 0, `gitleaks git . --config <title-only>` reports `no leaks found`
across 86 commits). Historical blobs at `0e17920` / `c4b6c5a` still contain
the pre-refactor literals; the readiness gate's own regex sweep flags them
as L-16 at S2 (not S0, because gitleaks corroborates). That residual is
accepted as a documented false positive in
`docs/security/f01-l16-synthetic-fixture-acceptance.md` rather than purged
via RB-03 history rewrite. The path-based allowlist in `.gitleaks.toml`
referenced above was also removed the same day — see F-04.

---

## Bug F-02: git config Write Hole in First-Commit Pipeline Allowlist (S2)

**Framework:** ISO 27001 A.8.9 / A.8.31
**Found in:** `scripts/first_commit_pipeline.py` (initial implementation)
**Severity:** S2 (fix soon)

**Problem:** The read-only allowlist permitted `git config` to read
`commit.gpgsign`, but the same permission also allowed
`git config --global name value` — a WRITE operation. A read-only gate
that permits writes through a subcommand is a security hole.

**Fix:** Added `_READ_ONLY_GIT_CONFIG_FLAGS` frozenset requiring explicit
read flags (`--get`, `--list`, etc.) for `git config` to pass the allowlist.
Without a read flag, `git config` is refused as a potential write.

**Verification:** 9 write attempts refused, 23 read commands permitted.

---

## Bug F-03: Policy Schema Inconsistency — `risk` Field (S3)

**Framework:** ISO 27001 A.5.31
**Found in:** `policy/compliance-gates.yml` exceptions.active
**Severity:** S3 (informational)

**Problem:** D-04, D-05, D-33 use `gate:` field. D-07 uses `risk:` field.
The readiness audit's test for "every active exception carries required
fields" was asserting `risk` but D-04/D-05/D-33 don't have it. The schema
is inconsistent — some entries use `gate:`, one uses `risk:`.

**Fix:** Pinned as a finding (`test_policy_risk_field_is_inconsistently_applied`).
Did not weaken the test or change the policy. The inconsistency is recorded
but not resolved — resolving it requires an owner decision on which field
to standardise.

**Verification:** Test suite asserts the inconsistency exists as a finding.

---

## Bug F-04: GitHub Push Protection Flags Allowlist as Secret

**Framework:** SOC 2 CC6.1
**Found in:** `.gitleaks.toml` (initial implementation)
**Severity:** S1 (fix before push)

**Problem:** The initial `.gitleaks.toml` used regex-based allowlisting
containing literal secret values (truncated: `AKIAQ3EG…B2M`,
`sk_live_abcdefghij…abc`). GitHub's push protection scanned
the config file and flagged the Stripe key pattern, blocking the push.

**Fix:** Replaced regex-based allowlisting with path-based exclusion only.
The test files are excluded entirely from gitleaks scanning. The runtime-
assembly fix in source is the primary defense; the config is defense in depth.

**Verification:** Push accepted by GitHub push protection after fix.

**Superseded (2026-10-07, A-04):** the path-based exclusion was subsequently
removed. Empirical re-verification with a title-only `.gitleaks.toml`
confirms both `gitleaks dir` and `gitleaks git` report `no leaks found`
across 86 commits, so the exclusion was not load-bearing at the time F-01
landed. Excluding `tests/**` from a secret sweep also violates RB-08
§"Known issue" step 4 ("A real secret pasted into a test file is still a
real secret") and AGENTS.md §5's weakening prohibition. The F-01 runtime-
assembly fix is now the sole defense, and `.gitleaksignore` remains as a
documented barrier for any future literal fixture that cannot be refactored.

---

## Bug D-28 Class: IDE Metadata in Index (Pre-existing, Verified)

**Framework:** ISO 27001 A.8.1
**Found in:** `scripts/repo_readiness_audit.py` (pre-existing check)
**Severity:** S1

**Problem:** `.idea/` directory in the git index while real files are
untracked. The readiness gate's forbidden-tracked check catches this.

**Status:** Check exists and fires correctly. `.gitignore` covers `.idea/`.
No current violation in jolarca-control.

---

## Bug F-05: Declared-Mandatory SAST Gate With No Enforcement (S1)

**Framework:** SOC 2 CC7.1/CC7.2 / ISO 27001 A.8.25 / PCI-DSS 6.3.1
**Found in:** `policy/compliance-gates.yml` (`sast: enforcement: mandatory`)
**Severity:** S1 (fix before relying on the control)

**Problem:** The `sast` gate was declared `mandatory` and listed in the
`required` set of every `enforcement_matrix` tier, but nothing enforced it:
the gate ID was `codeql-analysis` (a GHAS engine unavailable on the Free
plan, so it could not even be satisfied), Bandit ran only as a **non-required**
job over `scripts/` (not `tests/`), and no gate checked the wiring. A control
that is declared but never observed to fire is the D-22 class in gate form.

**Fix (A-08, 2026-10-08):** `.github/workflows/sast.yml` runs Semgrep OSS
(`p/default`+`p/python`), Bandit (`-ll -ii`, scope widened to `scripts/`
**and** `tests/`) and a Trivy config scan — all SHA-pinned, `contents: read`,
no GHAS dependency. `scripts/compliance_check.py` gained
`check_sast_gate_wiring()`, which fails when a repo is in a tier where `sast`
is mandatory but does not declare `SAST (semgrep)` as a required status check.
First-run findings were triaged (B108 false positive → `# nosec`; GIT-0004/GIT-0001
→ accepted in `.trivyignore.yaml` referencing D-05 / fleet-public-2026-10 with
expiries). Non-vacuity was proven with a throwaway negative-control PR whose
deliberate `shell=True`/`eval` payload turned **only** the two SAST contexts red.

**Verification:** see `docs/security/sast-mandatory-gate-2026-10-08.md` (run
`37699506676`: `SAST (semgrep)`+`SAST (bandit)` fail, all other checks pass).
The gate is *split across two PRs* on purpose — `check_declared_contexts.py`
reads live `main`, so the required context cannot be declared until the
workflow that emits it is merged (two-phase bootstrap, AGENTS.md §8).

---

## HCP Terraform migration bugs (2026-10-10)

### B-01 `terraform init -migrate-state` invalid for `cloud {}` backend

**Severity:** S2 (operational confusion, no data loss)
**Framework:** N/A (tooling)

`terraform init -migrate-state` aborts with "Invalid command-line option — HCP
Terraform migrations have additional steps, configured by interactive prompts."
The local state upload must use plain `terraform init`, which prompts
interactively to copy the existing `terraform.tfstate` into the workspace.

**Fix:** use plain `terraform init`; confirm upload with `terraform state list`.

### B-02 `terraform login` blocked by existing `~/.terraformrc`

**Severity:** S3 (confusing error)
**Framework:** N/A (tooling)

Once a `credentials "app.terraform.io" { token = ... }` block is written
manually into `~/.terraformrc`, `terraform login` aborts with "Credentials are
manually configured" and cannot proceed.

**Fix:** keep the manual token path; do not attempt `terraform login` after
writing the block.

### B-03 HCP org "not found" despite valid token

**Severity:** S2 (misread as invalid token)
**Framework:** N/A (tooling)

Even with a valid API token, `terraform init` fails until the organization and
workspace actually exist on app.terraform.io. The error surface reports the org
as "not existing", which reads as an invalid token.

**Fix:** create org `jolarca-dev` + workspace `jolarca-control` (CLI-Driven) in
the HCP UI first, then `terraform init`.

### B-04 `-local` flag rejected by setup-terraform wrapper

**Severity:** S1 (CI apply broken)
**Framework:** CC7.1 (change management)

`terraform plan -local` with a `cloud {}` backend is rejected by the
`hashicorp/setup-terraform` wrapper: "flag provided but not defined: -local".
The wrapper intercepts the command and does not pass the flag through.

**Fix:** set `TF_CLOUD_OPERATIONS: "false"` as a step env var instead of the
CLI flag. This is the documented way to force local execution with a cloud
backend.

### B-05 HCP remote plan timeout on free tier

**Severity:** S1 (CI apply hangs 48+ min)
**Framework:** CC7.1 (change management)

With a `cloud {}` backend, `terraform plan` triggers a remote run on HCP
workers. On the free tier the run queues and can exceed job timeouts (48+ min
observed, then cancelled).

**Fix:** `TF_CLOUD_OPERATIONS=false` forces the plan to execute on the GH
Actions runner while state remains in HCP.

### B-06 Missing `TF_GITHUB_TOKEN_READONLY` secret

**Severity:** S2 (post-apply verification fails)
**Framework:** CC7.2 (monitoring)

`apply.yml` uses `TF_GITHUB_TOKEN_READONLY` for the fleet-separation guard and
post-apply drift detection. Without it those steps fail even when the apply
succeeds.

**Fix:** create a read-only fine-grained PAT (Administration: read, Contents:
read, Metadata: read) scoped to `jolarca-dev` and store as the secret.

---

## Summary

| Bug | Severity | Framework | Status |
|-----|----------|-----------|--------|
| F-01 Synthetic secrets | S0 | CC7.2/A.8.24 | FIXED (source) — L-16 history residual accepted 2026-10-07 |
| F-02 git config write hole | S2 | A.8.9/A.8.31 | FIXED |
| F-03 Policy schema inconsistency | S3 | A.5.31 | RECORDED |
| F-04 Push protection flags allowlist | S1 | CC6.1 | SUPERSEDED 2026-10-07 — path exclusion removed, no allowlist needed |
| F-05 Mandatory SAST gate not enforced | S1 | CC7.1/A.8.25 | FIXED A-08 2026-10-08 — sast.yml + compliance wiring + negative-control proof |
| D-28 class IDE metadata | S1 | A.8.1 | CHECK EXISTS |
| B-01 migrate-state invalid for cloud | S2 | tooling | FIXED 2026-10-10 |
| B-02 login blocked by terraformrc | S3 | tooling | FIXED 2026-10-10 |
| B-03 org not found despite token | S2 | tooling | FIXED 2026-10-10 |
| B-04 -local flag rejected by wrapper | S1 | CC7.1 | FIXED 2026-10-10 (TF_CLOUD_OPERATIONS=false) |
| B-05 HCP remote plan timeout | S1 | CC7.1 | FIXED 2026-10-10 (local execution) |
| B-06 missing READONLY secret | S2 | CC7.2 | FIXED 2026-10-10 |

**Professional opinion:** Every finding except F-03 has been fixed or
superseded. F-03 is a schema inconsistency that requires an owner decision,
not a code fix. F-05 (SAST) was closed on 2026-10-08 across two PRs — the
workflow first, then the gate wiring — because `check_declared_contexts.py`
reads live `main` and correctly refuses a required-context declaration until the
workflow that emits it is merged; collapsing the two would have meant either a
permanently red Context Parity job or weakening it, both prohibited.
The fix pattern for F-01 (runtime assembly) and F-04 (no allowlist) should
be applied to every repo in the fleet that carries synthetic test fixtures.
