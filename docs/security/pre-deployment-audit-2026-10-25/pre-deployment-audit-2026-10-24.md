# Jolarca Marketplace — Pre-Deployment Independent Audit

**Audit date:** 2026-10-24 (live measurement)
**Auditor posture:** independent read-only; no GitHub write, no `PATCH`, no state mutation
**Scope:** all 17 repositories in the `jolarca-dev` organisation, each audited individually
**Compliance frame:** SOC 2 Type II · GDPR · ISO 27001:2022 · PCI-DSS 4.0
**Finding prefix:** `PDA-nn` — deliberately NOT `D-nn`/`A-nn`, so this report cannot collide with the
`docs/drift-findings.md` register that `scripts/check_findings_register.py` guards (A-07 collision
guard, D-73 dangling-reference guard). Crosswalks to existing IDs are given inline.

> **Read this first.** `policy/compliance-gates.yml:9-10` states that *"unlike jol-control, pci-dss
> applies to EVERY repo here: the whole marketplace tree sits in or adjacent to the cardholder-data
> environment."* So there is no "low-stakes" repository in this fleet. A gap in `jolarca-vendor` is a
> PCI-DSS scope gap, not a documentation nit.

---

## 1. Method (so the result is reproducible, not merely asserted)

Every row below came from a command, not from a document. The five sweeps are retained as evidence:

| Sweep | What it measured | Artifact |
|---|---|---|
| 1 | Repo inventory, visibility, size, `.protected`, CODEOWNERS path, workflows, PR/issue counts | `fleet.tsv` |
| 2 | Secret scanning / push protection, full legacy protection document, ruleset counts, commit volume + contributors, every open PR with author + age + mergeability, `/license` endpoint | `sweep2.txt` |
| 3 | Ruleset rule types, org teams, org plan/2FA/default permission, LICENSE presence by **recursive git tree** (independent of the `/license` API), `.github` repo tree, app-repo tree | `sweep3.txt` |
| 4 | Action-pin integrity across all 55 `uses:` lines, full ruleset **parameters**, `secrets/` directory contents, CodeQL analyses per repo, `dependabot.yml` presence, `production` environment protection rules | `sweep4.txt` |
| 5 | Declared required contexts **vs** the job `name:` a `pull_request` event can actually report (deadlock test) | `sweep5.txt` |
| 6 | Whether `.github`'s three reusable workflows declare `workflow_call`, and whether **any** repo actually calls them | `sweep6.txt` |
| — | Whether `AGENTS.md` §2's CI-surface claim matches the workflow files it names | `verify5.txt` |

Sweep 6 exists because sweep 4 produced a claim this report had already written down and shipped: that
`.github`'s shared workflows are *inherited by the fleet*. That claim was **false** and is corrected in
PDA-01. It was caught only because the claim was testable. See PDA-16 — and note that the first,
narrow grep (`grep 'repo_readiness_audit' … \| grep -v '^\s*#'`) also nearly produced a false finding
against `compliance_check.py`, which *is* invoked at `compliance-scan.yml:128`; multi-line `run: |`
blocks and reusable-workflow calls hide from a line-anchored pattern.

Two method rules were applied throughout, both learned the hard way in this repo:

- **A verifier that errors is not a pass.** Sweep 3's pin audit used `sed "s|^|…|UNPINNED |"` — a
  delimiter collision that made `sed` fail on every line while still printing
  *"(no UNPINNED lines above = every third-party action is SHA-pinned)"*. That claim was **false**,
  and it was only caught by re-running it in sweep 4 with `awk`. 13 unpinned actions then appeared.
- **A 404 is a measurement, not a verdict.** `…/branches/main/protection` returned HTTP 404
  "Branch not protected" for `jolarca-consent`, `-dr` and `-vendor` while `.protected` on the same
  branch returned `true`. Both are true: those three are protected **by ruleset**, and the legacy
  endpoint cannot see rulesets (AGENTS.md §8, D-63). The ruleset document is what had to be read.

---

## 2. Fleet-wide posture — what is genuinely strong

Recorded first so this report cannot be read as only criticism. Verified 2026-10-24:

- **17/17 repos report `.protected = true` on `main`.** (D-33's claim holds at that level.)
- **16/17 have secret scanning AND push protection enabled.** One month ago this was 1/16.
- **16/17 carry a `.github/CODEOWNERS`.**
- **14/17 have `enforce_admins = true` + `strict = true` + required contexts + linear history** on
  the legacy protection path — the real, strong shape.
- **13/17 have a `dependabot.yml`.**
- **`default_repository_permission = none`** at org level — correct least-privilege baseline.
- **`jolarca` (the deployed application) has 12 required contexts** including `codeql`, `trivy`,
  `docker-scan`, `gitleaks`, `secrets`, `dependency-audit`, `backend`, and four frontend gates —
  and CodeQL genuinely produces analyses there (last `794ad55a`).
- **`jolarca-control` `production` environment now has a real protection array:**
  `wait_timer = 30`, `can_admins_bypass = false`, plus a `required_reviewers` entry (D-70 landed).
- **No plaintext secret material in `jolarca/secrets/`** — the directory holds only
  `encrypted/README.md` (730 bytes); `.sops.yaml` publishes an **age public key**, which is correct.

---

## 3. Per-repository audit matrix (17 individual verdicts)

Legend — **Prot shape:** `LEGACY(n)` = legacy protection with *n* required contexts;
`RULESET(…)` = ruleset-only, listing the rules actually present; `EMPTY` = protection object exists,
enforces nothing. **CO** = CODEOWNERS present. **SS/PP** = secret scanning / push protection.
**DB** = `dependabot.yml`. **CQL** = CodeQL analyses exist. **Lic** = `/license` SPDX result.

| # | Repository | Prot shape | CO | SS/PP | DB | CQL | Lic | Open PRs | Verdict |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `.github` | **EMPTY** — `contexts=[]` | ✔ | **✘/✘** | **✘** | ✘ | `NOASSERTION` ("INTERNAL USE ONLY") | 1 | **FAIL — PDA-01, PDA-16** |
| 2 | `jolarca` | LEGACY(12), strict, admins | ✔ | ✔/✔ | ✔ 7688B | ✔ | `AGPL-3.0` | 16 | PASS w/ obs — PDA-09, PDA-11 |
| 3 | `jolarca-compliance` | LEGACY(4), strict, admins | ✔ | ✔/✔ | ✔ | ✘ | `NOASSERTION` | 2 | PASS w/ obs — PDA-06 |
| 4 | `jolarca-consent` | **RULESET** — deletion, non_fast_forward, linear_history **only** | ✔ | ✔/✔ | ✔ | ✔ | `NOASSERTION` | 3 | **FAIL — PDA-02** |
| 5 | `jolarca-control` | LEGACY(4), strict, admins | ✔ | ✔/✔ | ✔ | ✘ (semgrep instead) | `NOASSERTION` | 7 | PASS w/ obs — PDA-06, PDA-10 |
| 6 | `jolarca-data` | LEGACY(3), strict, admins | ✔ | ✔/✔ | ✔ | ✘ | `NOASSERTION` | 0 | PASS w/ obs — PDA-06 |
| 7 | `jolarca-docs` | LEGACY(1 `lint`), strict, admins | ✔ | ✔/✔ | ✔ | ✘ | `NOASSERTION` | 2 | THIN — PDA-06, PDA-09 |
| 8 | `jolarca-dr` | RULESET — PR(0 reviews) + checks(**`lint`,`gitleaks`**) | ✔ | ✔/✔ | **✘** | ✘ | `NOASSERTION` ("JOL Infrastructure") | 1 | PASS w/ obs — PDA-07, PDA-08 |
| 9 | `jolarca-hermes-agents` | LEGACY(3), strict, admins | ✔ | ✔/✔ | ✔ | ✘ | **53-byte LICENSE** | 2 | FAIL — PDA-05 |
| 10 | `jolarca-identity` | LEGACY(2 `shellcheck`,`gitleaks (full history)`), strict | ✔ | ✔/✔ | **✘** | ✘ | `NOASSERTION` | 1 | PASS w/ obs — PDA-07 |
| 11 | `jolarca-infrastructure` | LEGACY(3), strict, admins | **✘ ABSENT** | ✔/✔ | ✔ | ✘ | `NOASSERTION` | 6 | **FAIL — PDA-04** |
| 12 | `jolarca-legal` | LEGACY(2), strict, admins | ✔ | ✔/✔ | ✔ | ✘ | `NOASSERTION` | 0 | PASS w/ obs — PDA-06 |
| 13 | `jolarca-observability` | LEGACY(2), strict, admins | ✔ | ✔/✔ | ✔ | ✘ | `NOASSERTION` | 2 | PASS w/ obs — PDA-06 |
| 14 | `jolarca-payments` | LEGACY(2 `ci`,`security`), strict | ✔ | ✔/✔ | ✔ | ✘ | **NO LICENSE FILE** | 1 | FAIL — PDA-05 |
| 15 | `jolarca-runbooks` | LEGACY(2), strict, admins | ✔ | ✔/✔ | ✔ | ✘ | `NOASSERTION` | 3 | PASS w/ obs — PDA-09 |
| 16 | `jolarca-security` | LEGACY(4), strict, admins | ✔ | ✔/✔ | ✔ | ✘ | `NOASSERTION` | 1 | PASS w/ obs — PDA-06 |
| 17 | `jolarca-vendor` | **RULESET** — PR(0 reviews) + checks(**empty list**) | ✔ | ✔/✔ | **✘** | ✘ | `NOASSERTION` ("journeyoflife-org") | 1 | **FAIL — PDA-03** |

**Tallies:** **6 FAIL** (`.github`, `jolarca-consent`, `jolarca-hermes-agents`,
`jolarca-infrastructure`, `jolarca-payments`, `jolarca-vendor`), **10 PASS-with-observations**,
**1 THIN** (`jolarca-docs`). Zero repos are unconditionally clean.
`required_approving_review_count = 0` and `require_code_owner_review = false` on **17/17** — see PDA-12.

> A previous draft of this table read "4 FAIL, 11 PASS-with-observations, 2 THIN". Recounting the
> verdict column gives 6/10/1. The tally was written from impression rather than from the rows above
> it — the exact defect §5.10e warns about ("compare **counts**, not just verdicts"). Corrected here
> rather than quietly, for the same reason as PDA-01.

**Deadlock test (sweep 5) — no repo is currently wedged.** For every repo with declared contexts,
the declared string equals a job's reported `name:`: `jolarca-dr` → `lint`,`gitleaks` ✔;
`jolarca-identity` → `shellcheck`,`gitleaks (full history)` ✔; `jolarca-payments` → `ci`,`security` ✔.
This matters because a mismatch deadlocks merges silently (a required context that can never be
reported). It was checked, not assumed.

---

## 4. Findings register

Severity: **S0** blocks deployment · **S1** blocks a compliance claim · **S2** material, scheduled ·
**S3** hygiene. Every finding carries the exact re-verification command, because a finding without a
re-test is an opinion.

---

### PDA-01 · S1 — `.github`: shared CI that nothing calls, secret scanning off, zero required contexts

> **Severity corrected during this audit, from S0 to S1.** The first draft asserted that `.github`'s
> reusable workflows are inherited by the fleet, which would have made this a fleet-wide supply-chain
> S0. Sweep 6 tested that and **falsified it** — no repo calls them. The reasoning below is the
> corrected version. The original claim is retained here rather than silently deleted, because a
> correction you cannot see is indistinguishable from a claim that was never wrong.

**Evidence (all live, 2026-10-24):**
- `security_and_analysis.secret_scanning.status = disabled` and
  `secret_scanning_push_protection.status = disabled` — the **only** repo of 17 with both off.
- `branches/main/protection.required_status_checks.contexts = []` — merges with **zero** checks.
- `rulesets = 0`, so there is no second layer.
- It holds three reusable workflows — `ci-base.yml`, `compliance-base.yml`, `security-scan.yml` —
  all declaring `workflow_call:`, carrying **17 jobs** between them (Governance Files, Evidence
  Integrity, Dependency Scan, Container Scan, IaC Scan, License Compliance, Secret Scan, DSR SLA
  Monitoring, Retention Compliance, …). Line 2 of each says:
  *"Called by individual repos via: `uses: jolarca-dev/.github/.github/workflows/<f>@main`"*.
- **Sweep 6 result: nothing in the fleet calls them.** A scan of every workflow file in all 17 repos
  for `uses: <owner>/<repo>/.github/workflows/…` returned three matches — all three are the comment
  lines quoted above, inside `.github` itself. **Zero consumers.** → PDA-16.
- **11 of the 13 unpinned actions in the entire fleet live here** (see PDA-13).
- Open PR **#4**, unmerged since **2026-10-04** (20 days): *"ci: finish pinning the shared workflows;
  remove the last fabricated SHA (D-43 part 1)"*.
- Its `LICENSE` reads `INTERNAL USE ONLY` while the repo is `visibility: public` — a contradiction.
- It also serves the org-wide `SECURITY.md` (2420 bytes, blob `a7c5165a…`), which AGENTS.md §8 says
  is **edited by hand** because `github_repository_file.security_md` is commented out in
  `health-repo.tf` (D-15).
- No `dependabot.yml`.

**Why S1, not S0.** The confused-deputy argument does **not** apply, because there is no deputy: no
repo calls these workflows, so nothing inherits their unpinned actions or their `GITHUB_TOKEN`
context. What remains is serious but different in kind:
1. **The org-health repo is its weakest.** Secret scanning and push protection both off, zero required
   contexts, no ruleset, no Dependabot — on the repo that serves the org-wide `SECURITY.md`, i.e. the
   vulnerability-disclosure channel for all 17. A token pasted here is not caught, and nothing has to
   be green to merge it.
2. **A loaded gun.** 17 jobs of shared CI sit one `uses:` line away from running inside every caller
   with the caller's token — while holding 11 mutable-tag action references and being documented as
   callable `@main`, itself a mutable ref. The day someone wires this up (which is the obvious
   remediation for PDA-06's missing SAST coverage), they inherit all of it at once.
3. **Twenty days of known-unpinned shared CI**, with the fix written and unmerged.

**Remediation.**
1. Merge PR #4 (or supersede it): pin all 11 references to full 40-hex SHAs with a `# vX.Y.Z` comment.
   Do this **before** any repo starts calling these workflows, not after.
2. Enable secret scanning + push protection on `.github`.
3. Add `required_status_checks` covering at minimum `Secret Scan (gitleaks)` and `Governance Files`.
4. Resolve the LICENSE contradiction — either a real SPDX licence or an explicit
   "public-by-necessity, no grant" note, decided deliberately, not left as `INTERNAL USE ONLY`.
5. Move `SECURITY.md` under Terraform (`health-repo.tf` D-15) so an edit here propagates.
6. Add a `dependabot.yml`.
7. Then decide PDA-16 deliberately: wire these workflows up (and pin the call to a SHA, not `@main`),
   or delete them. Do not leave 17 jobs that nothing runs and a comment saying otherwise.

**Re-verify.**
```bash
gh api repos/jolarca-dev/.github -q '.security_and_analysis | {ss:.secret_scanning.status, pp:.secret_scanning_push_protection.status}'
gh api repos/jolarca-dev/.github/branches/main/protection -q '.required_status_checks.contexts'
for f in ci-base.yml compliance-base.yml security-scan.yml; do \
  gh api repos/jolarca-dev/.github/contents/.github/workflows/$f -q .content | base64 -d \
  | grep -nE '^\s*uses:' | grep -vE '@[0-9a-f]{40}' && echo "UNPINNED in $f"; done; echo "clean if nothing above"
```
Expected after fix: `ss=enabled pp=enabled`; a non-empty contexts array; no `UNPINNED` output.

---

### PDA-02 · S0 — `jolarca-consent` can be pushed to `main` with no PR and no checks

**Evidence.** Ruleset `protect-main` (id `24087580`, `enforcement: active`) contains exactly three
rules — `deletion`, `non_fast_forward`, `required_linear_history`. There is **no `pull_request`
rule** and **no `required_status_checks` rule**. `bypass_actors = []`. Legacy
`…/required_status_checks` → HTTP 404 "Branch not protected".

Meanwhile the repo's CI is *good*: 8 jobs exist and are producible on a PR —
`Lint (ruff)`, `Type check (mypy)`, `Test (pytest)`, `Repository smoke-check`, `CodeQL (python)`,
`Verify Chain`, `Gitleaks (secret scanning)`, `Dependency review`. CodeQL genuinely runs here
(analyses present, last `7e5f8404`) — one of only two repos where it does.

**Why S0.** None of those 8 gates is required. A failing `CodeQL (python)` or a failing
`Gitleaks (secret scanning)` merges cleanly; and because there is no `pull_request` rule, a direct
`git push origin main` succeeds — `non_fast_forward` only blocks *force*-push. This is the GDPR
consent-record repository: Art. 7(1) requires the controller to *demonstrate* consent, and
Art. 5(2) makes that demonstrability an obligation. A consent store whose integrity controls are
advisory cannot support that claim. Compare `jolarca-dr` and `jolarca-vendor`, whose rulesets *do*
carry `pull_request` + `required_status_checks` — so this is an incomplete remediation, not a design
choice.

**Remediation.** Add to ruleset `24087580`: a `pull_request` rule
(`required_approving_review_count: 0` is acceptable while D-04 stands, but
`required_review_thread_resolution: true` and `dismiss_stale_reviews_on_push: true` should be set —
`jolarca-dr` already has both) and a `required_status_checks` rule naming
`Lint (ruff)`, `Type check (mypy)`, `Test (pytest)`, `CodeQL (python)`, `Gitleaks (secret scanning)`,
`Dependency review` with `strict_required_status_checks_policy: true`. Prefer declaring this in
`branch-protection.tf`/`repos/jolarca-consent.yml` so Terraform owns it — but note `check_plan_safety.sh`
refuses protection-layer changes until runbook step 6 closes (D-61), so the ruleset edit is the
faster path and the Terraform reconciliation follows.

**Re-verify.**
```bash
gh api repos/jolarca-dev/jolarca-consent/rulesets/24087580 \
  | jq '{rules:[.rules[].type], checks:[.rules[]|select(.type=="required_status_checks")|.parameters.required_status_checks[].context]}'
```
Expected after fix: `rules` includes `pull_request` and `required_status_checks`; `checks` is non-empty.

---

### PDA-03 · S1 — `jolarca-vendor` has a `required_status_checks` rule with an empty list

**Evidence.** Ruleset `24138288` (`active`) → `required_status_checks` rule present,
`parameters.required_status_checks = []`, `strict_required_status_checks_policy = false`.
Also `required_review_thread_resolution: false` (where `jolarca-dr` has `true`).
The repo produces a `lint` job that *could* be required. No `dependabot.yml`.

**Why this shape is worse than an absent rule.** Any inventory that asks "does this repo have a
required-status-checks rule?" answers **yes** and moves on. This is precisely the failure AGENTS.md §7
names — *"a gate that runs and reports green has not been shown to detect anything"* — applied to
configuration rather than code. It also means the fleet's own drift tooling must be checked: if
`scripts/drift_detect.py` tests for rule presence rather than rule content, it reports this repo as
conformant.

**Remediation.** Populate the list with `lint` (the job exists), set
`strict_required_status_checks_policy: true`, set `required_review_thread_resolution: true`, and add
a `dependabot.yml`. Open PR **#3** (*"enable dependabot for the SHA pins added under D-44"*,
2026-10-04) is already the fix for part of this — merge it.

**Re-verify.**
```bash
gh api repos/jolarca-dev/jolarca-vendor/rulesets/24138288 \
  | jq '[.rules[]|select(.type=="required_status_checks")|.parameters.required_status_checks]|length'
gh api repos/jolarca-dev/jolarca-vendor/contents/.github/dependabot.yml -q .size
```
Expected after fix: a length ≥ 1 and a byte size, not a 404.

---

### PDA-04 · S1 — `jolarca-infrastructure` has no CODEOWNERS and carries unreviewed major-version provider bumps

**Evidence.** CODEOWNERS confirmed absent by **two independent methods** — the contents API 404s at
both `.github/CODEOWNERS` and `CODEOWNERS`, and `git/trees/main?recursive=1` filtered on `CODEOWNERS`
returns nothing. 16/17 repos have one; this is the only exception, and it is the repo that owns the
Terraform state and the production apply path.

Six open PRs, four of them Dependabot, opened **2026-10-23** and unreviewed:
- `hashicorp/google` **6.50.0 → 8.7.0** in `terraform/environments/staging` (**two** major versions)
- `hashicorp/google` 8.1.0 → 8.7.0 in `terraform/environments/production`
- `bpg/proxmox` 0.113.1 → 0.117.0 in **both** staging and production
- `ansible-core` `<2.19,>=2.17` → `>=2.17,<2.20`; `ansible-lint` 24.10.0 → **26.9.0**

Two unpinned actions in `.github/workflows/terraform.yml`: `terraform-linters/setup-tflint@v6`
(line 40) and **`actions/github-script@v9`** (line 87). `github-script` unpinned is the worst case in
the fleet: that action executes arbitrary JavaScript holding the repository token.

**Why S1.** A provider jump of two major versions changes resource schemas; on a repo whose apply is
`terraform apply -input=false -auto-approve tfplan`, an unreviewed merge is an unreviewed
infrastructure change. `check_plan_safety.sh` will catch destroy/replace/visibility/protection-layer
moves, but not a semantically different resource that plans as an in-place attribute change outside
the refused list (AGENTS.md §8 names this exact residual gap).

**Remediation.** (a) Add `.github/CODEOWNERS`. (b) Pin both actions to SHAs. (c) Review the four
provider PRs against the provider upgrade guides **before** merge; run
`terraform plan -refresh=false` per environment and read the diff, do not rely on the gate alone.
(d) Do not merge `hashicorp/google` 6.50.0 → 8.7.0 in one step without reading the 7.0.0 and 8.0.0
breaking-change notes.

**Re-verify.**
```bash
gh api repos/jolarca-dev/jolarca-infrastructure/git/trees/main?recursive=1 \
  -q '[.tree[].path|select(test("CODEOWNERS"))]|length'
gh api repos/jolarca-dev/jolarca-infrastructure/contents/.github/workflows/terraform.yml -q .content \
  | base64 -d | grep -nE '^\s*uses:' | grep -vE '@[0-9a-f]{40}'
```
Expected after fix: `1` and no output.

---

### PDA-05 · S1 — Licence integrity: one repo has no licence, one has a 53-byte stub

**Evidence (recursive git tree — independent of the `/license` API, which 404s and can mislead).**
- `jolarca-payments`: **no** `LICENSE`, `COPYING` or `NOTICE` anywhere in the tree. PCI-DSS-scoped,
  public.
- `jolarca-hermes-agents`: `LICENSE` exists but is **53 bytes** — a copyright line, not a grant.
- `jolarca`: `AGPL-3.0` — the only repo with a real, SPDX-recognised licence.
- The other 14: `NOASSERTION`, i.e. a file GitHub cannot classify.

**Note on the AGPL.** This is **not** a defect to remediate. `policy/compliance-gates.yml:105-109`
records a deliberate `scope_note: "inbound dependencies only"` and explicitly warns: *"the flagship
`jolarca` application is deliberately AGPL-3.0 … Do not 'remediate' an AGPL finding on jolarca's own
LICENSE file."* The `license_check` gate's `denied_licenses` list (`GPL-2.0`, `GPL-3.0`, `AGPL-3.0`,
`SSPL-1.0`) governs **third-party dependencies only**. Flagging the app's own AGPL would be the
false positive that note exists to prevent. What *is* worth a decision: AGPL-3.0 §13's network clause
obliges source disclosure to network users of a modified service — confirm that is the intended
commercial posture for a marketplace, and confirm no AGPL-incompatible dependency entered the
backend/frontend.

**Remediation.** Add a proper licence file to `jolarca-payments` and expand `jolarca-hermes-agents`.
Then decide the fleet-wide posture once and apply it uniformly (see PDA-08).

**Re-verify.**
```bash
for r in jolarca-payments jolarca-hermes-agents; do \
  echo -n "$r: "; gh api repos/jolarca-dev/$r/git/trees/main?recursive=1 \
  -q '[.tree[]|select(.path|test("LICENSE|COPYING";"i"))|.path+" "+((.size//0)|tostring)]|join(", ")'; done
```
Expected after fix: a path with a plausible byte size (a real licence is > 1 KB), not empty and not 53.

---

### PDA-06 · S1 — the declared `sast` gate names CodeQL, but CodeQL analyses exist on 2 of 17 repos

**Evidence.** `policy/compliance-gates.yml:135-148` declares gate `sast`, id `codeql-analysis`,
`enforcement: mandatory`, `frameworks: [soc2, iso27001, pci-dss]`,
`languages: [python, javascript, typescript]`, `queries: security-extended`,
`fail_on: [error, warning]`. Live `code-scanning/analyses` per repo:

- analyses present: **`jolarca`** (`794ad55a`), **`jolarca-consent`** (`7e5f8404`)
- `no analysis found`: the other **15**, including `jolarca-control`, `jolarca-payments`,
  `jolarca-infrastructure`, `jolarca-compliance`, `jolarca-security`

`jolarca-control`'s required SAST context is **`SAST (semgrep)`** — a different tool than the
declared gate names.

**Why S1.** AGENTS.md §6: *"Documentation must state actual implementation status. Never describe a
control as enforced when it is configured-but-inert or convention-only."* A mandatory gate mapped to
SOC 2 CC7.1/CC7.2, ISO A.8.8/A.8.25 and PCI 6.3.1/6.3.2 that produces no analysis on 15 repos is
configured-but-inert. An auditor sampling the policy file and asking for the CodeQL evidence trail
gets nothing for 88% of the fleet. Note the honesty of the *naming* here: this repo's own context is
called `SAST (semgrep)`, so the drift is in `compliance-gates.yml`, not in `jolarca-control`'s CI.

**Remediation.** Pick one and make the policy say it:
- **(a)** wire CodeQL into the 15 repos that have code — free on public repos, so the `plan=free`
  constraint is not an excuse here; or
- **(b)** re-declare the gate as `sast` with `tool: semgrep` for the governance repos and
  `tool: codeql` for `jolarca`/`jolarca-consent`, listing per-repo which applies.
Option (b) is cheaper and matches reality; option (a) is stronger. Do **not** leave the file claiming
CodeQL fleet-wide.

**Re-verify.**
```bash
for r in $(gh repo list jolarca-dev --limit 100 --json name -q '.[].name'); do \
  echo -n "$r "; gh api repos/jolarca-dev/$r/code-scanning/analyses?per_page=1 \
  -q 'if type=="array" then "analyses=\(length)" else "none" end' 2>/dev/null || echo none; done
```

---

### PDA-07 · S2 — Dependabot absent on the four weakest repos

**Evidence.** `dependabot.yml` ABSENT on: `.github`, `jolarca-dr`, `jolarca-identity`,
`jolarca-vendor` — i.e. exactly the repos in PDA-01, PDA-02 (adjacent), PDA-03 and the repo whose
only gates are `shellcheck` + gitleaks. Present on the other 13.

Three of the four already have the fix written and unmerged for ~20 days:
`jolarca-identity#4` and `jolarca-vendor#3` (*"enable dependabot for the SHA pins added under D-44"*),
`jolarca-dr#1` (*"the actions/checkout pin is v5.0.0, not v4.3.0"*).

**Why this pattern matters more than the four gaps.** The remediation exists as an open PR and is not
being merged. That is a **process** finding, not a knowledge finding, and it recurs across the fleet
(PDA-10). Detection without a landing path is not a control.

**Remediation.** Merge the three PRs; add `dependabot.yml` to `.github`. Then set a weekly SLA for
the Dependabot queue and measure it, because the backlog is the real defect.

---

### PDA-08 · S2 — eight different copyright-holder identities; two breach ADR-0004 R4

**Evidence** (first line of each `LICENSE`, read live):

| Holder string | Repos |
|---|---|
| `Journey of Life` | control, data, docs, infrastructure, legal |
| `jolarca-dev` | compliance, hermes-agents |
| `Jolarca (jolarca-dev)` | consent |
| `Jolarca` | runbooks |
| `JolArca / jolarca-dev` | security |
| `JOL Infrastructure / jolarca-dev` | **dr** |
| `Journey Of Life (journeyoflife-org)` | **vendor** |
| `INTERNAL USE ONLY` | **.github** (on a public repo) |
| *(none)* | payments |

**Why S2.** (1) **ADR-0004 R4 breach:** AGENTS.md §5 forbids `jol-*` / mission-platform references in
fleet files. `JOL Infrastructure` and `journeyoflife-org` are exactly those. `make fleet-audit` /
`scripts/check_fleet_separation.sh` enforces the rule but evidently does not scan `LICENSE` — so the
guard's path scope is the defect, not just the strings. (2) **Legal-entity ambiguity:** for GDPR the
controller's identity must be unambiguous (Art. 13(1)(a)); eight spellings across one organisation
invites exactly that question in a DSR or an audit. (3) `INTERNAL USE ONLY` on a world-readable repo
is self-contradictory.

**Remediation.** Decide the single legal holder name. Rewrite all 17 `LICENSE` headers in one PR per
repo. Extend `check_fleet_separation.sh` to scan `LICENSE` and `NOTICE` so the class is caught, not
just these instances — and add a negative control proving it fires.

---

### PDA-09 · S2 — 49 open PRs fleet-wide; dependency remediation detects but does not land

**Evidence.** Open PRs: `jolarca` 16, `jolarca-control` 7, `jolarca-infrastructure` 6,
`jolarca-consent` 3, `jolarca-runbooks` 3, `jolarca-compliance` 2, `jolarca-docs` 2,
`jolarca-observability` 2, `jolarca-hermes-agents` 2, and 1 each on `.github`, `jolarca-dr`,
`jolarca-identity`, `jolarca-payments`, `jolarca-security`, `jolarca-vendor`. **49 total.**

Oldest: `jolarca#91` and `jolarca-docs#1` (2026-09-17 / 2026-09-28 — 37 / 26 days).
Two `CONFLICTING` (`jolarca#159`, `jolarca#91`), two drafts.
Unreviewed **major**-version security-relevant bumps include: `actions/checkout` 4.2.2 → **7.0.1**
(three majors, three repos), `actions/setup-python` 5.x → **7.0.0** (four repos),
`github/codeql-action` 3.38.2 → **4.39.0** (two repos), `gitleaks-action` 2.3.9 → **3.0.0**,
`zod` 3.25.76 → **4.6.5**, `@tanstack/react-table` 8.21.3 → **9.2.6**, `next-toolchain-major`,
`ansible-lint` 24.10.0 → **26.9.0**, `hashicorp/google` 6.50.0 → **8.7.0**.

**Why S2.** PCI-DSS 6.3.3 and SOC 2 CC7.1 require security patches inside a defined window. A
37-day-old bump is outside any window a policy could defend, and `jolarca` also carries 21 branches
against AGENTS.md §6's "delete the feature branch".

**Remediation.** Triage in one session: close superseded Dependabot PRs, resolve the two conflicts,
merge patch/minor bumps, and schedule the major bumps as reviewed changes. Then define the SLA in
`policy/compliance-gates.yml` and make it measurable — the gate should fail on *age of open security
PR*, not merely on the presence of a scanner.

---

### PDA-10 · S2 — `jolarca-control` has 7 open PRs, 5 of them governance fixes aged 5–19 days

**Evidence.** `#85` D-79 (2026-10-19, this branch), `#84` D-77 (2026-10-19), `#82` ruff 0.16.10 →
0.17.1 (2026-10-19), `#79` D-72 (2026-10-17), `#68` upload-artifact 7.0.1 → 7.0.2 (2026-10-12),
`#54` D-33 rehearsal (2026-10-07), `#40` dead-path fix (2026-10-05). All `mergeable=UNKNOWN` —
GitHub has not computed mergeability, which for a `strict=true` branch usually means the branch is
behind and needs a refresh.

**Why it matters.** The control plane is the repo whose documentation the rest of the fleet is
audited against. Five unmerged correction PRs mean the **committed** record on `main` still contains
statements these PRs were opened to fix (D-72's "12-day dead guard pointer", D-77's "the positive
control failed", D-33's unreconciled protection declarations). An auditor reading `main` today reads
the stale version.

**Remediation.** Rebase/refresh and land `#40`, `#54`, `#79`, `#84`, `#85` before the audit evidence
is cited externally. They are docs/CI corrections on the repo that defines what "correct" means.

---

### PDA-11 · S3 — mission-platform naming has leaked into the app repo's secrets configuration

**Evidence.** `jolarca/.sops.yaml` line 1: `# JOL Platform — SOPS creation rules (ADR-003 amendment
PR #35; Gate 8 GO 2026-08-27)`; line 2 references `TREE: Marketplace (/opt/jol-m/**)`;
line 4 references `Counterpart config: church: jol-infrastructure .sops.yaml`.

**Positive control passed:** `jolarca/secrets/` holds only `encrypted/README.md` (730 bytes). No
plaintext secret material. The `.sops.yaml` value is an **age public key** (`age1h6knx…`) — public
keys are not secrets, and `# pragma: allowlist secret` is the correct way to stop a scanner
false-positiving on them.

**Why S3 but worth fixing.** ADR-0004 R4 separates the mission platform from the marketplace;
`check_fleet_separation.sh` enforces that on **fleet** files, and `jolarca/.sops.yaml` is an app-repo
file, so the guard's scope misses it. A stale cross-tree reference also misdirects an operator during
an incident — the worst time to discover the comment points at the wrong tree.

**Remediation.** Update the header to marketplace naming and drop or correct the
`church: jol-infrastructure` cross-reference. Consider extending the separation guard to the app repo.

---

### PDA-12 · S1 — no separation of duties is enforceable anywhere in the fleet

This is the structural finding, and it is the direct answer to the audit's own governing requirement:
*the same actor must not be the sole authority for both implementation and acceptance.*

**Evidence.**
- `required_approving_review_count = 0` on **17/17** (legacy path and ruleset path alike).
- `require_code_owner_reviews` / `require_code_owner_review = false` on **17/17**.
- `gh api orgs/jolarca-dev/teams` → `[]`, **team_count = 0**.
- 16 CODEOWNERS files exist and, with zero teams and the flag false, **all 16 are inert** (D-20).
- Contributors on every repo: `JourneyOfLife` (+ `dependabot[bot]` on 9). One human.
- `jolarca-control` `production` environment now has `required_reviewers: [JourneyOfLife]` with
  **`prevent_self_review: false`** — so the deploy approval exists but is self-approval.
- Standing acceptance **D-04** covers this, `approved_on: 2026-09-25`, **`expires: 2026-12-24`**.

**Assessment.** The compensating controls D-04 cites are real and were re-verified here:
required status checks (14/17 strong), `enforce_admins`, `check_plan_safety.sh` refusals,
`prevent_destroy` on every `github_repository`, squash-only linear history. Those constrain *what a
merge can do*. They do not provide *independent judgement on whether it should happen*. And D-04
expires in **61 days** — its `exit_trigger` is second-operator onboarding, which is a plan-tier and
people problem, not a configuration problem.

`policy/compliance-gates.yml:310-314` records the deliberate decision **not** to enable
`prevent_self_review` (one member → it would wedge every deploy). That reasoning is sound and should
stand. The consequence must still be stated plainly: **the "independent reviewer" requirement cannot
be met by GitHub configuration today.** It has to be met by process design — which is what
`docs/master-architect-prompt.md` §4 specifies (role separation across distinct agent identities
with distinct tokens, plus evidence that is machine-checkable rather than self-attested).

---

### PDA-13 · S1 — 13 unpinned third-party GitHub Actions, 11 of them in shared workflows

**Evidence.** 55 `uses:` lines scanned fleet-wide; 13 are tag-referenced, not SHA-pinned:

| Location | Line | Reference |
|---|---|---|
| `.github/.github/workflows/ci-base.yml` | 139 | `actions/setup-python@v5` |
| `.github/.github/workflows/ci-base.yml` | 157 | `actions/setup-node@v4` |
| `.github/.github/workflows/ci-base.yml` | 175 | `hashicorp/setup-terraform@v3` |
| `.github/.github/workflows/compliance-base.yml` | 64, 102, 136, 170, 223 | `actions/setup-python@v5` ×5 |
| `.github/.github/workflows/security-scan.yml` | 97, 183 | `github/codeql-action/upload-sarif@v3` ×2 |
| `jolarca/.github/workflows/ci.yml` | 299 | `actions/upload-artifact@v7` |
| `jolarca-infrastructure/.github/workflows/terraform.yml` | 40 | `terraform-linters/setup-tflint@v6` |
| `jolarca-infrastructure/.github/workflows/terraform.yml` | 87 | `actions/github-script@v9` |

**AGENTS.md §5 is explicit:** *"GitHub Actions pin to a full commit SHA with a `# vX.Y.Z` comment."*
So this is a violation of a rule the fleet already adopted — not a new standard being imposed.

**Ranking by consequence.**
1. **`actions/github-script@v9`** in `jolarca-infrastructure/terraform.yml:87` — arbitrary JavaScript
   holding the token of the repo that owns the Terraform apply path. Worst in the fleet, and it is
   *live*: that workflow runs.
2. **The 8 in `.github`'s reusable workflows** — **inert today** (PDA-16: zero callers), so they
   cannot currently execute anywhere. They become fleet-wide the moment a caller is added, which is
   why PDA-01 orders "pin before wiring up".
3. **`actions/upload-artifact@v7`** (`jolarca/ci.yml:299`) and **`setup-tflint@v6`**
   (`jolarca-infrastructure/terraform.yml:40`) — single-repo, lower privilege.

**Remediation.** Merge `.github#4`; pin the remaining two. Then make the class unrepeatable: add a
fleet gate that fails on any `uses:` matching `@[^0-9a-f]{1,39}$` excluding `@./`, **with a negative
control fixture** proving the pattern fires — because an untested regex gate is a hypothesis
(AGENTS.md §7, and D-22 is the precedent).

---

### PDA-14 · S2 — the metric used to close D-33 cannot distinguish strong protection from none

**Evidence.** `policy/compliance-gates.yml:554-560` records D-33 as *"FULLY RESOLVED 2026-10-10 — all
17 fleet repos now have branch protection enabled on main (**verified via `gh api .protected=true`**)"*.

That signal is `true` on all 17 — and this audit measured the same 17 as: 14 with real required
contexts, and **3 where `.protected=true` coexists with zero enforced checks** (`jolarca-consent` —
direct push allowed; `jolarca-vendor` — empty context list) or with a 404 on the legacy endpoint.

**Why this is a finding about the register, not about the repos.** The property D-33 was about is
*"main cannot be changed without review and required checks."* The property `.protected` measures is
*"some protection object is attached."* The second does not imply the first. Closing a blocking
finding on a signal that is insensitive to the finding's own subject is how a register becomes
reassuring and wrong — and AGENTS.md §8 already warns that `open_blocking` "is stale in both
directions and must be re-read before use."

**Remediation.** Reopen D-33 as *partially* resolved with the per-repo shape recorded, or add a
successor finding. Then harden `scripts/drift_detect.py` to read **rule content** — the required
context list and whether a `pull_request` rule exists — rather than `.protected`, and give it a
negative control built from `jolarca-consent`'s actual ruleset JSON.

---

### PDA-15 · S2 — `AGENTS.md` §2 names a CI step that no workflow runs

**Evidence.** `AGENTS.md:48-51` states:

> *"**`make lint` is not the whole CI surface.** `compliance-scan.yml` additionally runs
> `scripts/compliance_check.py` (`make compliance`) and `scripts/repo_readiness_audit.py --no-live`,
> and neither is in `lint`. Run both before pushing, or CI will surface failures the local gates never
> checked."*

Measured against the workflow files:

| Claim | Verdict | Evidence |
|---|---|---|
| `compliance-scan.yml` runs `compliance_check.py` | **TRUE** | `compliance-scan.yml:128` — `run: python3 scripts/compliance_check.py`; also `apply.yml:160` |
| `compliance-scan.yml` runs `repo_readiness_audit.py --no-live` | **FALSE** | No workflow invokes it. Every occurrence in `.github/workflows/` is a **comment**: `compliance-scan.yml:131`, `context-parity.yml:10`, `sast.yml:118` |

`compliance-scan.yml`'s actual invocations are: `validate_repos.py:65`,
`check_required_context_baseline.py:71`, `check_declared_contexts.py:88`,
`check_deploy_gates.py:102`, `check_findings_register.py:116`, `compliance_check.py:128`,
`gitleaks git .:149`, `tests/test_state_backup.sh:173`, `pytest tests/:180`, `ruff:192-193`,
`shellcheck:197`, `terraform fmt:207`.

**Why S2.** Two reasons, and the second matters more than the first.
1. An agent following `AGENTS.md` §2 runs a gate locally believing CI will run it too. It will not. The
   instruction is harmless-but-wrong in the safe direction here (running an extra gate costs time),
   which is why it is S2 and not S1 — the same defect pointed the other way ("CI covers this, skip it
   locally") would be S1.
2. **`AGENTS.md` is the fleet's highest-authority document** — §1 says it wins over an agent's memory,
   and its own preamble says it wins over memory generally. §8 already records that this file said
   "three required contexts" until 2026-10-12 when a fourth was found. This is the same document being
   wrong again, in a different section, about a different fact. A document that overrides memory has to
   be *right*, because nothing else gets to correct it.

`context-parity.yml:13-15` also states the readiness audit "currently reports 15 of 16 repos BLOCKED".
Measured today: `{'READY': 1, 'READY-WITH-FIXES': 10, 'BLOCKED': 5}` over 16 repos. That comment is
stale in the same way — a dated observation presented as a current fact.

**Remediation.** Correct `AGENTS.md:48-51` to name only what runs, and add a gate that catches the
class: every `scripts/*.py` named in a workflow comment must actually be invoked by some workflow, or
the comment must be marked as historical. `jolarca-control#79` (D-72, "workflows may not cite paths
that do not exist") is the same gate applied to *paths*; extend it to *script names in prose*.
Re-date the `context-parity.yml` comment.

**Re-verify.**
```bash
grep -rn 'repo_readiness_audit\|compliance_check' .github/workflows/ | grep -v ':\s*#'
# expected: ONLY real invocations (compliance-scan.yml:128, apply.yml:160). No comment-only hits.
```

---

### PDA-16 · S2 — 17 shared CI jobs exist that nothing runs, documented as though they do

**Evidence (sweep 6).** `.github` holds `ci-base.yml`, `compliance-base.yml` and `security-scan.yml`.
All three declare `on: workflow_call:` with typed inputs — they are correctly built to be called. Line
2 of each states: *"Called by individual repos via:
`uses: jolarca-dev/.github/.github/workflows/<file>@main`"*. Between them they define **17 jobs**,
including the fleet's only implementations of Dependency Scan, Container Scan, IaC Scan, License
Compliance, Evidence Integrity, Policy Review Dates, Vendor Assessment Dates, DSR SLA Monitoring and
Retention Compliance.

A scan of **every workflow file in all 17 repositories** for
`uses: <owner>/<repo>/.github/workflows/…` returned exactly three matches — and all three are the
comment lines quoted above, inside `.github` itself.

**Consumers: zero.**

**Why S2.** This is *detection without landing* in its purest form, and it connects three other
findings:
- `policy/compliance-gates.yml` declares `dependency_scan`, `license_check`, `container_scan`,
  `iac_scan` and `iac_policy` as **mandatory** gates with named tools and `run_on: [pull_request]`.
  Their only implementations in the fleet are these 17 jobs. Nothing calls them. So five mandatory
  gates are, fleet-wide, **Configured but inert** in the §5.1d taxonomy — present in policy, present
  in code, executed nowhere.
- PDA-06 (CodeQL on 2/17) is the same shape for SAST.
- The comment asserting they are called is a **false documentation claim** of exactly the kind
  AGENTS.md §6 forbids, and it is the claim that made this audit's own first draft wrong.
- The suggested call form is `@main` — a **mutable branch reference**. Wiring these up as documented
  would create a supply-chain edge whose target moves on every push to `.github`'s `main`, a repo with
  zero required contexts (PDA-01).

**Remediation — decide, do not drift.** Either:
- **(a)** wire them up: add `uses: jolarca-dev/.github/.github/workflows/<file>@<40-hex-sha>` to the
  repos that need each gate, **after** PDA-01's pins land and **after** `.github` has required
  contexts; then add the reported job names to each repo's declared required contexts and re-run
  `make context-baseline` so the parity gate covers them; or
- **(b)** delete the three workflows and re-declare the five gates in
  `policy/compliance-gates.yml` with whatever actually implements them.

Option (a) is the better outcome and is the cheapest route to closing PDA-06. Do not leave the current
state, which is the worst of the three: the policy claims the gates, the code exists, nothing runs,
and a comment says it does.

**Re-verify.**
```bash
for r in $(gh repo list jolarca-dev --limit 100 --json name -q '.[].name'); do
  for f in $(gh api repos/jolarca-dev/$r/git/trees/main?recursive=1 \
       -q '.tree[]|select(.path|startswith(".github/workflows"))|select(.path|test("\\.ya?ml$"))|.path'); do
    gh api repos/jolarca-dev/$r/contents/$f -q .content | base64 -d \
     | grep -nE 'uses:[[:space:]]*[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/\.github/workflows/' \
     | grep -v '^[0-9]*:#' | awk -v R="$r" -v F="$f" '{print "REAL-CALL " R "/" F " " $0}'
  done; done
```
Expected after (a): one `REAL-CALL` line per wired repo, each pinned to a 40-hex SHA.
Expected after (b): no output, and the three files gone from `.github`.

---

## 5. Could not verify — recorded as exit 2, never as a pass

AGENTS.md §3: an unreachable API or unreadable input is `2`, not `0`. These are **open**, not clean:

| Item | Why unverifiable from here | How to close it |
|---|---|---|
| **Org 2FA enforcement** | `gh api orgs/jolarca-dev` returns `two_factor_auth_enabled = null` on the Free plan; the field is not exposed | GitHub UI → Org Settings → Authentication security. PCI-DSS 8.3, SOC 2 CC6.1 — must be evidenced, not assumed |
| **Org audit log** | HTTP 404 on Free plan (AGENTS.md §8, D-63) | Cannot be closed without a plan upgrade; record as a permanent evidence gap in the SOC 2 narrative |
| **Whether required contexts actually run on PRs** | Context names match job names (sweep 5 ✔), but a path filter can still stop a job triggering | Check a live PR's `statusCheckRollup` per repo — `gh pr checks <n> -R jolarca-dev/<repo>` |
| **Semgrep/CodeQL rule severity + fail thresholds** | Not readable from protection metadata | Read each repo's SAST workflow and confirm `fail_on` matches `compliance-gates.yml:147` |
| **Off-host state backup currency** | `make backup` works when a human runs it; there is no schedule and no `docs/backup-log.tsv` to date (AGENTS.md §8, D-02) | Run it, retain the log, and put it on a schedule |
| **Contact-address deliverability** | No inbound test message has been retained as evidence; `policy/contact-addresses.yml` routing is convention-only (D-59/D-60) | Send one test per role, retain headers as hashed evidence |
| **`jolarca` runtime configuration** | Out of scope for this read-only pass: `.env.prod.example`, `nginx.prod.conf`, `docker-compose.prod.yml`, `backend/project/settings/production.py` all exist and were **not** inspected line-by-line | Separate deep-dive — this is the app that actually processes cardholder-adjacent data |

---

## 6. Remediation sequencing (blast-radius order, not effort order)

Do these in this order. Items 1–3 change what an attacker or an unreviewed merge can actually do;
4–8 change what the compliance record can honestly claim; the rest are hygiene. Severity after
correction: **1 × S0, 7 × S1, 8 × S2, 1 × S3**.

1. **PDA-02 (S0)** — `jolarca-consent`: add `pull_request` + `required_status_checks` to ruleset
   `24087580`. *Closes a direct-push path on the GDPR consent store. The only S0.*
2. **PDA-13 (S1)** — pin `actions/github-script@v9` and `setup-tflint@v6` in
   `jolarca-infrastructure`. *The one unpinned action that executes today with the apply-path token.*
3. **PDA-01 (S1)** — merge `.github#4` (11 pins), enable secret scanning + push protection, add
   required contexts, add `dependabot.yml`. *Hardens the org-health repo **before** anyone wires up
   its shared workflows — order matters, see step 7.*
4. **PDA-04 (S1)** — add CODEOWNERS to `jolarca-infrastructure`; review the four provider PRs (two
   majors on `hashicorp/google`) before merging any of them.
5. **PDA-03 (S1)** — populate `jolarca-vendor`'s empty context list with `lint`; merge `#3`.
6. **PDA-12 (S1)** — stand up the read-only auditor token and the `acceptance.yml` reviewer contract
   (`docs/master-architect-prompt.md` §3.2, §3.4, §4). *Free, same-day, and the only available form of
   independence with one operator.*
7. **PDA-16 (S2)** — decide on `.github`'s 17 inert shared jobs: wire them up (pinned to a SHA, after
   step 3) or delete them and re-declare the five mandatory gates they were built to satisfy.
8. **PDA-06 (S1)** — reconcile the `sast` gate declaration with reality. Step 7 option (a) is the
   cheapest route; otherwise option (b), re-declare per-repo tooling.
9. **PDA-07 (S2)** — merge `jolarca-identity#4`, `jolarca-dr#1`; add `dependabot.yml` to `.github`.
10. **PDA-14 (S2)** — reopen/qualify D-33; harden `drift_detect.py` to read rule **content**, with a
    negative control built from `jolarca-consent`'s real ruleset JSON.
11. **PDA-15 (S2)** — correct `AGENTS.md:48-51`; re-date the stale `context-parity.yml` comment; extend
    the D-72 dead-path gate to script names cited in prose.
12. **PDA-10 (S2)** — land `jolarca-control` `#40`, `#54`, `#79`, `#84`, `#85` so the committed record
    stops contradicting the open corrections.
13. **PDA-09 (S2)** — clear the 49-PR backlog; define a security-PR age SLA and make a gate fail on
    *age*, not on scanner presence.
14. **PDA-05 / PDA-08 (S1/S2)** — licences and holder identity, one uniform decision across 17 repos.
15. **PDA-11 (S3)** — `.sops.yaml` header naming.

---

## 7. Professional opinion

**What this fleet has achieved is real and should not be undersold.** In roughly four weeks it went
from 1/16 repos with secret scanning to 16/17, from 2/16 with branch protection to 17/17 reporting
`.protected`, and it built a genuinely unusual asset: `check_plan_safety.sh` with 19 fixtures and
negative controls per refusal class, a three-valued exit-code convention that refuses to treat
"could not check" as "clean", and a `production` environment with a 30-minute non-bypassable wait
whose cancel window was *proven* on a real run. Most organisations at this size have none of that.

**The residual risk has moved.** It is no longer "controls are missing". It is now three things:

1. **Heterogeneity at the edges.** Three repos were onboarded by ruleset rather than legacy
   protection, and the rulesets were built inconsistently — `jolarca-dr` correct, `jolarca-vendor`
   present-but-empty, `jolarca-consent` missing two rules entirely. Uniform *intent*, non-uniform
   *implementation*. This is what happens when protection is applied out-of-band instead of from one
   declarative source. D-61's refusal to let an apply create those three rules is therefore
   **correct and should not be relaxed** — but the consequence is that the three stay hand-managed
   and will keep drifting. Closing `docs/state-migration-runbook.md` step 6 is what actually fixes
   this class.

2. **Detection without landing.** This is now the dominant defect and it appears in four independent
   forms: CodeQL declared mandatory and running on 2 repos (PDA-06); **17 fully-built shared CI jobs
   implementing five mandatory gates, with zero callers** (PDA-16); Dependabot configured on 13 repos
   producing 49 unmerged PRs (PDA-09); and three fixes sitting as open PRs for 20 days
   (PDA-07). The controls *see*; nothing *closes*. For SOC 2 Type II this is the most dangerous shape,
   because Type II tests operation over a period — a scanner that has been alerting into an unworked
   queue for 37 days is evidence **against** you, not for you. PDA-16 is the sharpest version: the
   fleet wrote the control, documented it as running, and never turned it on.

3. **The register can be reassured by an insensitive metric.** PDA-14 is the finding I would raise
   first with an auditor, because it is a finding about the *audit system itself*: D-33 was closed on
   `.protected=true`, a signal that reads identically for "12 required contexts" and "direct push
   allowed". This repo's own §7 says "do not trust a correct verdict" — this is that lesson
   recurring one level up, in the findings register rather than in a gate.

**On the "enforceable properties" thesis: it is correct, and it is already half-built here.** The
proof is `check_plan_safety.sh`: it does not ask anyone to be careful, it refuses the plan. The same
treatment now needs to be applied to the four properties that are still carried by prose —
scope, permissions, evidence, independent verification. `docs/master-architect-prompt.md` specifies
that concretely, including the uncomfortable part: with one human operator and zero teams,
independent verification cannot be a *person*, so it must be a *separately-credentialed reviewer
identity plus machine-checkable evidence* — and the system must fail when that evidence is absent,
not when someone forgets to ask nicely.

**Deployment verdict: NOT READY.** One S0 and seven S1 findings stand between this fleet and a
defensible attestation. The S0 is PDA-02 — direct push to `main` on the GDPR consent repository, where
nothing has to be green and no PR is required. The S1s cluster on the repos carrying the most trust:
`jolarca-infrastructure` (unpinned `github-script` with the apply-path token, no CODEOWNERS, two-major
provider bumps unreviewed), `.github` (secret scanning off, zero required contexts, no Dependabot),
`jolarca-vendor` (a required-checks rule with an empty list), the licence gaps on `jolarca-payments`
and `jolarca-hermes-agents`, the SAST declaration 15 repos cannot evidence, the absence of any
enforceable separation of duties, and the 13 unpinned actions.

Steps 1–3 of §6 are small, mostly single-PR changes and would move this to *ready-with-observations*.
I would not sign a SOC 2 Type II or PCI-DSS attestation before **PDA-06 and PDA-16 are reconciled**,
because `policy/compliance-gates.yml` currently asserts five mandatory gates whose only
implementations nothing executes, and a SAST gate that operates on 12% of the fleet. A Type II
examination tests exactly that gap.

**One closing observation, because it is the point of the exercise.** This audit falsified two of its
own claims before shipping — the `.github` supply-chain inheritance argument (PDA-01, corrected S0 →
S1) and the per-repo verdict tally (§3, corrected 4/11/2 → 6/10/1). Both were written confidently,
both were wrong, and neither was caught by re-reading. They were caught by running a test against
live state. That is the entire argument of `docs/master-architect-prompt.md` §1, demonstrated on the
document that makes it.

---

## Appendix — evidence retention

The five sweeps referenced in §1 are the primary evidence for every finding above. They are
**not** yet committed, and per AGENTS.md §7 *"verification output that justified a merge is a
deliverable, not a transient."* Before citing this report externally, retain them:

```bash
# from the machine that ran the audit
mkdir -p docs/security/pre-deployment-audit-2026-10-24
cp /tmp/jaudit/{fleet.tsv,sweep2.txt,sweep3.txt,sweep4.txt,sweep5.txt,sweep6.txt} \
   docs/security/pre-deployment-audit-2026-10-24/
make evidence-register   # docs/security/ IS in hash_evidence.sh's EVIDENCE_DIRS
```

Note the trap: `docs/security/` **is** inside `EVIDENCE_DIRS`
(`scripts/hash_evidence.sh:35-43`), so committing evidence there **requires** re-registering in the
same PR or `make evidence-check` fails. This file, at `docs/` root, is **not** hashed — verified:
`make evidence-check` reported `39 files scanned, 0 mismatches` both before and after these two
documents were written.

**Gates re-run after writing these two documents** (AGENTS.md §2 — `make lint` is not the whole
surface):

| Gate | Result |
|---|---|
| `make lint` | exit **0** — 277 pytest passed, state-backup 10/10, workspace-execution-mode 13/13 |
| `make compliance` | exit **0** |
| `make evidence-check` | exit **0** — 39 files, 0 mismatches |
| `make validate` | exit **0** — 16 repo definitions |
| `check_findings_register.py` | exit **0** — 78 `### D-nn` headings, no collisions, no dangling citations. The `PDA-nn` prefix is deliberately outside its scan scope (`SECURITY.md`, `audit/*.yml`, `docs/threat-model.md`, `policy/**`), so these documents cannot collide with the D-series |
| `repo_readiness_audit.py --no-live` | exit **1** — `READY 1 / READY-WITH-FIXES 10 / BLOCKED 5`. **Pre-existing, not caused by these documents**: verified by removing both files and re-running (baseline also exit 1). Not a CI gate — see PDA-15 |
