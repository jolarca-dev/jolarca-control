# Comprehensive Audit Plan — `jolarca-control` + `jolarca-dev` fleet

**Created:** 2026-10-06
**Author:** compliance-architecture review (paranoid, evidence-first)
**Status:** In progress — Phases **0, 1, 2 executed** (offline + live read-only,
2026-10-06), findings **A-01–A-21**. Phases 3–4 pending; all remediation requires
operator authorization (live mutations) or a plan-tier decision. **`Bash` stdout
was dead for the whole session; every live check ran through a write-to-file →
`Read` channel** (see "Phase 0 results" method note).
**Scope:** the `jolarca-control` control plane **and** the 16-repo `jolarca-dev`
fleet it governs, plus the org itself.
**Frameworks:** SOC 2 Type II · GDPR (EU 2016/679) · ISO 27001:2022 · PCI-DSS 4.0.
**Lens:** risk-sequenced (Phase 0 reconcile → 1 drift → 2 gate effectiveness →
3 compliance conformance → 4 state/org custody → 5 remediation + re-verify),
with the per-repo **D1–D9 matrix** as the Phase 1 instrument and a **framework
crosswalk** as the Phase 3 appendix.

> **Authoring constraint (recorded for honesty, per AGENTS.md §3).** The `Bash`
> tool returned empty output for every command during authoring — including
> `echo`/`pwd`. Therefore **no live command was run**: git state, the GitHub API,
> and Terraform state are all **UNVERIFIED (exit-code 2 class)**, not "clean".
> Everything marked *Verified* below was proven by reading repository files with
> `Read`/`Grep`/`Glob`. Everything marked *Assumed* comes from prior reports or
> memory and **must be re-verified live** before it is treated as fact. This plan
> is written so that a future session with a working shell can execute it verbatim.

---

## 1. Why this audit, and why this shape

`jolarca-control` is the governance control plane for a PCI-DSS/GDPR-scoped
marketplace org. Its whole job is to make the fleet's security posture
*declarative, verifiable, and auditable*. The offline grounding pass found that
the governance **record currently disagrees with itself**:

- One artifact (`policy/compliance-gates.yml`) records a blocking PCI finding
  (**D-01**) as *RESOLVED*; another (`docs/drift-findings.md` **D-31**) records
  the same resolution path as *not implementable* and *S1, BLOCKING, OPEN*.
- `docs/action-plan.md` still lists 2FA as *PENDING* although `drift-findings.md`
  **D-18** marks it *FIXED (2026-10-01)*, and cites "seven private repos"
  although **D-37/D-39** record a fleet-wide migration to public.
- `README.md` says "six repositories"; `docs/architecture.md` says "14 YAML
  files"; the allow-list actually holds **16** `repos/*.yml`.
- A prior *live* audit (memory) reports that **D-20**'s "FIXED" claim is false
  against production — CODEOWNERS exist in only 5 of 16 repos.

**You cannot audit against a record that is provably false.** An auditor reading
only the policy file gets a materially rosier picture than one reading the
findings register. That is why this plan front-loads **Phase 0 — reconcile the
record** before any control is assessed, and why every finding carries an
explicit *Verified vs. Assumed* flag.

---

## 2. Rules of evidence (the audit's constitution)

These bind every phase. They are lifted from AGENTS.md §1/§3/§5/§7 and the
three-valued exit-code convention, and they are non-negotiable.

1. **Three-valued verdicts.** Every check reports `0` pass / `1` finding /
   `2` **could not verify**. An unreadable input, a missing baseline, or an
   unreachable API is `2`, **never** a silent `0`.
2. **Verify the verifier.** A gate that reports green has not been shown to
   detect anything. Every gate must be exercised with a **negative control** — a
   fixture that *must* fail. Model: `tests/test_check_plan_safety.sh` (10 cases
   incl. empty and missing plan). An untested gate is a hypothesis (D-22 class).
3. **No false empties.** Any empty `Glob`/`Grep`/API result is cross-verified by
   a **second independent method** before absence is asserted. *Proven this
   session:* `Glob .github/workflows/*.yml` returned **0 files** (hidden-dir
   skip) while the workflows demonstrably exist.
4. **Verified vs. Assumed on every finding.** File-read evidence = *Verified*.
   Memory, prior reports, or a tool summary = *Assumed* until re-verified live.
5. **Recount from source of truth, never from docs.** Enumerate repos from
   `gh api orgs/jolarca-dev/repos --paginate`, not from `README.md` or the
   registry being audited (circular scope hides drift).
6. **Do not trust a correct verdict.** Cross-check aggregate answers and finding
   *counts* against an independent run — a gate can report the right answer while
   silently skipping whole check families (early `return` on a missing `.git`).
7. **No fabricated compliance records.** An approval exists **only** as a dated
   entry in `policy/compliance-gates.yml` `exceptions.active`. Never invent an
   ADR, an approver, or an acceptance date.
8. **Read-only.** The audit changes no live state: no `terraform apply`, no
   `terraform state rm|mv|import`, no `gh api -X PATCH` (AGENTS.md §5). Findings
   propose diffs; the operator applies them through the governed PR flow.
9. **Evidence is retained.** Command output that justifies a finding is captured
   verbatim (command + output + HTTP status where relevant) into the audit
   report, not summarized away.

---

## 3. Severity model & finding schema

Reuse the register's existing scale (verified in `docs/drift-findings.md`):

| Severity | Meaning |
|---|---|
| **S0** | Stop-work. Blocks any `terraform apply` / production trust. |
| **S1** | Fix before first apply / before relying on the control. |
| **S2** | Fix soon — degrades the compliance narrative or a control. |
| **S3** | Tracked hygiene. |

**Finding-ID namespace (approved decision):** new audit findings use **`A-nn`**
(`A-01`, `A-02`, …) and **cross-reference** the existing `D-nn` register rather
than appending to it. Rationale: the live register is concurrently edited (its
own history records D-20/D-21/D-22 ID collisions); a separate namespace avoids
racing it. On closure, an `A-nn` finding is either folded into a `D-nn` entry by
the operator or retired with a pointer.

**Every finding is recorded as:**

```
ID:            A-nn
Title:         <one line>
Severity:      S0 | S1 | S2 | S3
Status:        OPEN | FIXED | ACCEPTED | BLOCKING
Verified/Assumed:  which — and the evidence class
Framework IDs: SOC2 CC…, GDPR Art…, ISO A…, PCI-DSS Req…
Evidence:      exact command + output, or file:line
Impact:        what breaks / what is exposed
Remediation:   the specific change
Owner:         jolarca-dev organization owner (solo era)
Expiry:        ISO-8601 (mandatory if Status=ACCEPTED)
Cross-ref:     D-nn (if it duplicates/extends a register entry)
```

---

## 4. Phase 0 — Reconcile the record  *(OFFLINE, runnable now)*

**Objective.** Establish documentary ground truth before any control is assessed.
Two governance artifacts that contradict each other are worse than one honest gap.

**Scope.** `README.md`, `docs/architecture.md`, `docs/action-plan.md`,
`AGENTS.md`, `policy/compliance-gates.yml`, `policy/repo-defaults.yml`,
`docs/drift-findings.md`, `docs/change-management.md`, `docs/threat-model.md`,
`audit/*.yml`, and all 16 `repos/*.yml`.

**Procedures.**
1. Recount the allow-list: `Glob repos/*.yml` → **16** (verified). Reconcile
   against README ("six"), architecture.md ("14 YAML files"), and any "15" in
   memory. The live recount (`gh api`) is deferred to Phase 1.
2. Build a **contradiction table**: for each of D-01, D-18, D-20, D-33, repo
   count, branch-protection coverage, secret-scan mechanism — list what *each*
   artifact claims, with `file:line`.
3. Resolve **D-01 vs D-31**: is the fleet public (D-37/D-39 "migrated") or is
   "accept public" not implementable because the four repos hold live regulated
   records (D-31)? This is an **owner decision**, not an audit call — record it
   as such and require a dated entry in `compliance-gates.yml`.
4. Resolve the **`require_code_owner_reviews`** conflict: `repo-defaults.yml` L69
   = `false` vs `repos/jolarca-control.yml` L72 = `true`. Determine which
   `validate_repos.py` treats as authoritative and whether the divergence is
   intentional override or drift.
5. Enumerate **every "FIXED"/"RESOLVED" claim** in `drift-findings.md` into a
   re-verification queue for Phase 1 (each becomes a live check).
6. Flag stale cross-repo references (e.g. `docs/superpowers/plans/…` does not
   exist in this repo).

**Evidence required.** The contradiction table with `file:line` for every claim.
**Acceptance criteria.** Every artifact either agrees, or the disagreement is
logged as an `A-nn` finding with a named owner decision.
**Negative control.** Introduce a deliberate contradiction in a *scratch copy*
and confirm the reconciliation procedure surfaces it (proves the procedure is not
a rubber stamp).
**Exit criteria.** No unexplained contradiction remains in the documentation set.

**Provisional Phase 0 findings (from the offline grounding pass — *Verified from
files* unless flagged; all Status=OPEN pending full Phase 0 execution):**

| ID | Title | Sev | V/A | Framework | Cross-ref |
|---|---|---|---|---|---|
| **A-01** | Repo count disagrees: allow-list=16, README="six", architecture.md="14" | S2 | Verified | SOC2 CC8.1 · ISO A.5.1 | — |
| **A-02** | D-01 recorded *RESOLVED* in `compliance-gates.yml` but *S1 BLOCKING OPEN* as D-31 in `drift-findings.md` | **S1** | Verified | PCI 1.2 · GDPR Art5(1)(f)/32 · SOC2 CC9.2 | D-01, D-31 |
| **A-03** | `AGENTS.md` §8 misstates the secret-scan context (claims readiness `--no-live`→exit 2; actual `compliance-scan.yml` runs gitleaks) | S2 | Verified | SOC2 CC8.1 · ISO A.8.32 | D-42, D-50 |
| **A-04** | `action-plan.md` stale: 2FA "PENDING" vs D-18 FIXED; "seven private repos" vs all-public; "2/16 protected" vs "6 protected" | S2 | Verified | SOC2 CC8.1 | D-18, D-37, D-39 |
| **A-05** | `require_code_owner_reviews` policy(`false`)↔`jolarca-control.yml`(`true`) conflict | S2 | Verified | SOC2 CC6.1 · ISO A.5.3 | D-20 |
| **A-06** | D-20 "FIXED" is **false live** (§0.4): 5/17 repos carry forbidden cross-org CODEOWNERS refs, 3 have none; 3 of 4 PCI-scope repos (compliance, data, legal) unfixed | **S1** | **Verified live** | ISO A.5.3 · ADR-0004 R4 · SOC2 CC6.1 | D-20 |
| **A-07** | CI supply-chain integrity family: fabricated/nonexistent action SHAs, `@master` pins, false version labels, `\|\|` verdict-swallowing fallbacks | **S1** | Verified (status from files) | SOC2 CC7.1/CC8.1 · ISO A.8.8/A.8.19 · PCI 6.3 | D-43, D-45, D-50, D-51 |
| **A-08** | Live branch-protection rulesets exist outside the declared Terraform source of truth | **S1** | Verified (status from files) | SOC2 CC8.1 · ISO A.8.32 · PCI 6.3 | D-46 |
| **A-09** | State custody: HCP `cloud{}` declared but workspace absent; local `terraform.tfstate` frozen; no verified off-host backup | **S0** | Verified (status from files) | ISO A.8.13 · SOC2 CC9.2/A.1 | D-02 |
| **A-10** | Audit-methodology trap: hidden-dir `Glob`/`Grep` return false empties | S3 | Verified (live, §0.5) | (process control → Rule 3) | — |
| **A-11** | `threat-model.md` risk register contradicts the findings register + `compliance-gates.yml`: D-18 shown "NOT enforced" (actually FIXED) and D-20 "OPEN — NOT ACCEPTED" (actually the A-06 false-fixed) | S2 | Verified | SOC2 CC8.1 · ISO A.5.1 | D-18, D-20 |

---

## 5. Phase 1 — Declared-vs-live drift, fleet-wide  *(LIVE — gated on shell + `gh`)*

**Objective.** Verify every `repos/*.yml` declaration against live GitHub for all
16 repos + `.github` + the org. Detect the D-20 class (documented fix that is
false in production).

**Instrument — D1–D9 per-repo matrix:**

| Dim | Check | Live probe |
|---|---|---|
| D1 | Ownership (org-owned, not personal) | `gh api orgs/jolarca-dev/repos` `.owner.login`/`.owner.type` |
| D2 | Classification ↔ visibility coherence | `.visibility`/`.private` vs `repos/*.yml` `data_classification`; policy `max_classification_for_public: internal` |
| D3 | Branch protection status | `repos/{o}/{r}/branches/main` `.protected`, then `/protection` (403 on Free private = `plan_limited`) |
| D4 | CODEOWNERS presence + correctness | `contents/.github/CODEOWNERS` → `contents/CODEOWNERS` fallback → recursive tree search |
| D5 | Secret scanning + push protection | `.security_and_analysis.secret_scanning.status` |
| D6 | Dependabot + CodeQL | `vulnerability-alerts` (204=on), `code-scanning/analyses` |
| D7 | Team bindings | `repos/{o}/{r}/teams` (expect empty — D-10) |
| D8 | Tier-gate compliance | declared `required_gates`/contexts vs live protection contexts |
| D9 | License / SPDX | `.license.spdx_id` vs declared |

**Procedures.**
1. Enumerate from live: `gh api orgs/jolarca-dev/repos --paginate` (**not** the
   registry). Record the true count and compare to the 16 allow-list entries.
2. For each repo, populate D1–D9. Read the raw HTTP status code, not a shell
   truthiness wrapper (a masked 403/404 reads as a clean negative).
3. Empty repo (size 0, no `main`) → branch checks are `n/a` (404 "Branch not
   found"), **not** `protected=false`.
4. Run `make drift` (`scripts/drift_detect.py`) and **cross-check its finding
   count against the manual matrix** (Rule 6). Investigate any cell the script
   marks `unverifiable`/`plan_limited` and confirm the classification is honest.
5. **Re-verify A-06 (D-20)** specifically: CODEOWNERS presence across all 16 +
   `.github`, and `grep -E '@journeyoflife-org|@jol-infrastructure'` in each.
6. Check the **stale-clone resurrection risk**: for each local clone under
   `/opt/jolarca/repos/`, compare `git rev-parse main` to `git ls-remote origin`;
   confirm no clone would re-push pre-fix cross-org CODEOWNERS.
7. Verify D-33/D-37/D-39 live: are the repos actually public now, and which are
   actually `.protected=true`? Resolve the "2/16 vs 6 protected" contradiction.

**Evidence required.** The completed 16×9 matrix + raw API outputs + HTTP codes.
**Acceptance criteria.** Every cell is live-verified **or** carries an explicit
HTTP-coded `plan_limited`/`unverifiable`/`n/a` with the code shown.
**Negative control.** Deliberately mis-state one cell and confirm the
`make drift` cross-check (or the matrix reconciliation) flags the discrepancy.
**Exit criteria.** 16/16 repos matrix-complete; all drift logged with severity.

---

## 6. Phase 2 — Control & gate effectiveness ("verify the verifier")  *(OFFLINE mostly; some LIVE)*

**Objective.** Prove each automated gate detects what it claims. A control that
is present in configuration and never fires is not a control (D-20/D-22 class).

**Gate inventory (verified present):**
- Scripts: `validate_repos.py`, `compliance_check.py`, `drift_detect.py`,
  `check_fleet_separation.sh`, `check_plan_safety.sh`, `repo_readiness_audit.py`,
  `first_commit_pipeline.py`, `check_declared_contexts.py`,
  `org_delivery_audit.sh`, `hash_evidence.sh`, `state_backup.sh`.
- CI: `compliance-scan.yml` (3 required contexts + Regression Tests / Lint /
  SAST-bandit / Terraform Format), `plan.yml`, `apply.yml`,
  `fleet-separation-guard.yml`, `evidence-integrity.yml`, `security-scan.yml`.

**Per-gate procedure.** For each gate answer, with evidence:
1. **Negative control?** Is there a must-fail fixture/test? Run it
   (`tests/test_check_plan_safety.sh` → expect 10/10; the gitleaks
   emptied-ruleset negative control → expect build failure).
2. **Exit-code semantics?** Does it honor `0/1/2` and treat "cannot verify" as
   `2`, never `0`? (Check `drift_detect.py`, `repo_readiness_audit.py`,
   `check_plan_safety.sh`, `first_commit_pipeline.py`.)
3. **Can it pass while detecting nothing?** Look for early `return`/`exit 0` on
   a missing precondition (the AGENTS.md §7 "missing `.git` skipped six checks"
   failure), `|| true`, or `cmd || fallback` that lets the fallback own the
   verdict (D-50).
4. **Supply-chain integrity (A-07 / G7):** every action pinned to a **full
   commit SHA** with a correct `# vX.Y.Z` comment; no `@master`; no fabricated or
   nonexistent SHAs; no false version labels (D-43/D-45/D-51). Verify each pinned
   SHA resolves to the claimed tag.
5. **Context parity (D-47/D-48):** run `scripts/check_declared_contexts.py`
   (`make context-parity`). Every declared required context must correspond to a
   job that can actually report it; the `branch_protection_baseline_exempt` list
   must not exempt a repo whose own declaration requires contexts.
6. **AGENTS.md §8 accuracy (A-03):** confirm which contexts are *actually* red on
   `main` today and why — reconcile the doc's "structurally incapable of green"
   claim against the current gitleaks-based secret scan.

**Evidence required.** A gate-by-gate table: `gate · has negative control? ·
exit-code semantics · inert-risk · pinned-SHA status · verdict`.
**Acceptance criteria.** Every gate is classified **effective / inert /
unverifiable**; any gate without a passing negative control is a finding.
**Exit criteria.** No gate remains "assumed effective".

---

## 7. Phase 3 — Compliance conformance (risk-based) + crosswalk  *(OFFLINE map + LIVE evidence)*

**Objective.** Map the risk-bearing controls to framework IDs with evidence and
gap. Risk-based depth (approved) — deep on the controls that gate real PCI/GDPR/
SOC 2 risk here, with a full crosswalk appendix for traceability.

**Risk-based control set** (anchored on `policy/repo-defaults.yml`
`compliance_mapping` + the verified risk picture):

| Control | Framework anchors | Primary evidence source |
|---|---|---|
| Visibility ↔ classification coherence | GDPR Art5(1)(f)/Art32 · PCI 1.2 · SOC2 CC6.1 | Phase 1 D2; `validate_repos.py` |
| Branch protection + required checks | SOC2 CC6.1/CC8.1 · ISO A.8.32 · PCI 6.3 | Phase 1 D3/D8; `branch-protection.tf` |
| Segregation of duties / CODEOWNERS / teams | ISO A.5.3/A.6.1 · PCI 7 · SOC2 CC6.1 | Phase 1 D4/D7; D-10/D-20 |
| Secret scanning + push protection | SOC2 CC6.3 · PCI 3.5/8.3 · ISO A.5.10 | Phase 1 D5; `security-scan.yml` |
| Signed commits / attribution | SOC2 CC6.2 · ISO A.6.6 · PCI 8.2 | `commit_signing_policy`; D-05 |
| State custody & backup | ISO A.8.13 · SOC2 A.1/CC9.2 | Phase 4; D-02 |
| Drift detection | SOC2 CC9.2 | `drift_detect.py`; Phase 1 |
| Evidence integrity | SOC2 CC4.1 · ISO A.5.31 · PCI 12.10.1 | `hash_evidence.sh`; `evidence-integrity.yml` |
| Audit-log streaming | PCI 10.2 | `org-settings.tf` (note: `/audit-log` 404 on Free) |
| Org 2FA / defaults | PCI 8.3.1 · ISO A.5.17 · SOC2 CC6.1 | Phase 4 org baseline; D-18/D-19 |

**Appendix — full crosswalk.** A table over SOC 2 TSC, GDPR articles, ISO 27001
Annex A, and PCI-DSS 4.0 requirements → applicability → evidence pointer → gap →
`A-nn`/`D-nn`. Honest **"N/A — solo operator / no teams"** rows are expected and
correct; do not fabricate enforcement that does not exist (AGENTS.md §6).

**Negative control.** Confirm at least one control documented as "enforced" is
actually **inert** (D-20 CODEOWNERS / D-40 `secret_scan: true` is intent, not a
merge-blocking check). If the phase finds zero inert controls, treat that as
suspicious and re-examine.
**Acceptance criteria.** Every risk-based control has an evidence pointer or a
gap finding; the crosswalk appendix is complete and traceable.

---

## 8. Phase 4 — State custody, Terraform & org controls  *(OFFLINE + gated LIVE)*

**Objective.** Audit the most dangerous surface: production state and the org
settings the provider cannot manage.

**Procedures.**
1. **D-02 (A-09, S0).** Confirm `main.tf` declares a `cloud {}` (HCP) backend;
   determine whether the HCP workspace exists. Verify the local
   `terraform.tfstate` is frozen (`terraform state list` fails with "HCP
   Terraform initialization required") — record serial + resource count. Confirm
   whether an **off-host AGE backup** exists (`.state-backup-pubkey.txt`,
   `scripts/state_backup.sh`) and whether a **restore was ever rehearsed**
   (`docs/runbooks/deployment-rehearsal.md`). An unbacked single-copy state for a
   PCI control plane is S0.
2. **D-46 (A-08, S1).** Dump live rulesets
   (`gh api repos/jolarca-dev/{repo}/rulesets`) and reconcile against
   `branch-protection.tf` + `terraform.tfvars` `enable_branch_protection`. Any
   live rule not owned by Terraform violates "Terraform is the source of truth"
   (AGENTS.md §5) and can be silently reverted.
3. **Apply-gate chain.** Confirm `apply.yml` refuses unless
   `STATE_MIGRATION_COMPLETE=true`, runs `check_plan_safety.sh` pre-apply, and
   that every `github_repository` carries `lifecycle { prevent_destroy = true }`.
4. **Org baseline** (`repo-defaults.yml organization_baseline`): verify live 2FA,
   `members_can_create_repositories=false`, `default_repository_permission=none`,
   `members_can_fork_private_repositories=false`, `web_commit_signoff_required`,
   and `allowed_admins` (unexpected-admin detection).
5. **terraform.tfvars** `enable_branch_protection` — confirm current value and
   whether weakening it would fire D-26.

**Evidence required.** State serial/resource list, backup verification, ruleset
dump, tfvars-vs-live protection diff.
**Acceptance criteria.** State custody is verified recoverable **or** logged S0;
every live ruleset is either Terraform-owned or logged.
**Negative control.** Confirm `check_plan_safety.sh` refuses a destroy / replace /
visibility-flip plan and exits `2` on empty/missing plan (fixtures exist).
**Exit criteria.** No unowned production state or ruleset; backup recoverable or
S0 open with a dated owner decision.

---

## 9. Phase 5 — Remediation backlog + re-verification  *(synthesis)*

**Objective.** Convert findings into a risk-ranked, owner-assigned, time-bound
backlog with a re-verification schedule.

**Procedures.**
1. Rank all `A-nn`/`D-nn` findings by **severity × blast radius** (AGENTS.md §4:
   route on blast radius, not diff size — `*.tf`, `repos/**`, `policy/**`,
   `.github/workflows/**`, `scripts/**` are high blast radius).
2. Partition into three actionable buckets:
   - **Budget-free now:** documentation reconciliation (A-01/A-03/A-04), resolve
     A-05 policy conflict, remove `@master` pins / fix false SHA labels (A-07),
     reconcile stale cross-repo references.
   - **Gated on plan-tier upgrade:** D-07 tag protection, D-33 branch protection
     + secret scanning + CodeQL on private repos (all unlock together on GitHub
     Team).
   - **Gated on external action:** D-02 HCP workspace creation + `TFC_TOKEN` +
     `terraform init -migrate-state`; second-operator onboarding for teams/D-04.
3. Each finding gets: remediation, owner, **ISO-8601 expiry** (mandatory if
   accepted), and the **exact re-verification command**.
4. **Propose** register diffs (`drift-findings.md`, `compliance-gates.yml`
   `exceptions.active`); do **not** edit the live register during the audit
   (concurrent-edit collision risk). The operator applies them via PR.
5. **Re-verify after merge** (AGENTS.md §1): live state, not the merge banner.

**Exit criteria.** Every finding has owner + expiry + re-verify command; every
budget-free fix is immediately actionable; no S0 lacks a dated decision.

---

## 10. Risk-ranked execution order

| Stage | Requires | Phases |
|---|---|---|
| **Now (offline)** | files only | Phase 0 (complete the reconciliation) → Phase 2 (offline gate inventory, negative-control fixtures, pin/label review) → Phase 3 (control mapping + crosswalk skeleton) |
| **Shell restored** | working `Bash` + `gh` auth to `jolarca-dev` | Phase 1 (live D1–D9 matrix) → Phase 4 (state/rulesets/org) → Phase 2 (live gate runs) → Phase 3 (live evidence) → Phase 5 (synthesis) |

**Rationale.** Prove everything offline first (cheap, no API churn, and it
de-risks the live pass by telling you exactly which claims to test), then do all
live work in a single authenticated pass.

---

## 11. Success criteria (measurable)

- [ ] Zero unexplained contradictions across the documentation set (Phase 0).
- [ ] 16/16 repos matrix-complete; every cell live-verified or HTTP-coded (Phase 1).
- [ ] Every gate classified **effective / inert / unverifiable**, each with a
      negative control result (Phase 2).
- [ ] Every risk-based control has an evidence pointer or a gap finding; the
      crosswalk appendix is complete (Phase 3).
- [ ] State custody verified recoverable **or** S0 open with a dated decision;
      no unowned live ruleset (Phase 4).
- [ ] Every finding has owner + ISO-8601 expiry + re-verification command; no S0
      without a dated decision (Phase 5).

---

## 12. Constraints & caveats

- **`Bash` unavailable during authoring.** All LIVE phases are gated; nothing
  live was verified. Treat every *Assumed* finding as unproven.
- **GitHub Free plan** structurally blocks: branch protection / secret scanning /
  push protection / Dependabot updates / CodeQL on **private** repos, org
  rulesets, and tag protection (D-07/D-33). Some findings cannot be closed by
  configuration alone — they need a plan-tier decision. (Note the D-37/D-39
  migration to *public* changes this calculus — re-verify live in Phase 1.)
- **Solo operator, zero teams (D-10).** Segregation of duties (ISO A.5.3),
  least-privilege enforcement (PCI 7), and non-self access review are
  structurally unsatisfiable until a second operator onboards. The crosswalk must
  state this honestly, not paper over it.
- **Frozen state (D-02/A-09).** Until the HCP workspace exists, no `terraform
  plan/apply/import` and no CLI state read can run — Phase 4's state checks are
  gated on that external action.
- **No secret-shaped fixtures.** This plan and its evidence must contain no
  literal secrets or credential-shaped strings (AGENTS.md §5); gitleaks scans the
  whole tree and a real-looking fixture can S0-BLOCK the readiness gate.

---

## 13. Professional opinion

*(Distinguishes verified evidence from assumption; fabricates no compliance
record.)*

**Overall posture.** The control plane's **design** is strong and, in places,
exemplary: three-valued exit codes, a *tested* plan-safety gate born from a real
defect (D-22), evidence hashing against a committed baseline, and a
fleet-separation guard with independent enforcement. Whoever built this
understands that a gate without a negative control is a hypothesis.

**The weakest link is record integrity, not engineering.** Verified from files
this session: the governance artifacts **contradict each other** —
`compliance-gates.yml` calls a blocking PCI finding resolved while
`drift-findings.md` keeps it S1/BLOCKING/OPEN (**A-02**); `action-plan.md` and
`AGENTS.md §8` are stale against the register (**A-03/A-04**); repo counts differ
three ways (**A-01**). A compliance assertion is only as defensible as the record
behind it. **Until Phase 0 reconciles the record, no assertion from this repo is
auditor-defensible** — an external auditor who spots one artifact calling a
blocking finding "resolved" will discount the entire register.

**Highest technical risks (verified status from files; live re-verify pending):**
1. **A-09 / D-02 (S0)** — single-copy Terraform state, HCP workspace absent, no
   *verified* off-host backup. For a PCI control plane this is the one finding
   that can cause irreversible loss. Close it first among the live items.
2. **A-07 (S1)** — the CI supply-chain family (fabricated/nonexistent SHAs,
   `@master` pins, false version labels, `||` fallbacks that swallow verdicts).
   These defects sit in the layer that *proves* everything else; a gate that
   cannot fail, or an action that does not resolve, silently nullifies the
   control it appears to enforce.
3. **A-08 / D-46 (S1)** — live rulesets outside the Terraform source of truth.
   Out-of-band protection is silently revertible and creates the exact drift the
   control plane exists to prevent.
4. **A-06 / D-20 (S1, now VERIFIED live — see §0.4)** — a documented "FIXED" that
   live production **disproves**: 5 of 17 repos still carry forbidden cross-org
   CODEOWNERS references and 3 have no CODEOWNERS at all. This is the pattern that
   most damages auditor trust — a register claiming a fix production does not have
   — and `threat-model.md` RA-07 states the ADR-0004 R4 breach behind it **cannot
   be risk-accepted**. Remediating it needs live CODEOWNERS rewrites in 5 repos,
   not a documentation edit in this control plane.

**Required changes (recommendation).**
- Execute **Phase 0 immediately** (offline; no shell needed) and land the
  documentation reconciliation as a single PR that fixes A-01/A-03/A-04/A-05 and
  forces an owner decision on A-02. This is budget-free and restores the record's
  credibility.
- Do **not** merge any further remediation into `drift-findings.md` until the
  "FIXED" re-verification queue (Phase 0 step 5) has been run against live — the
  register's fix-claims are currently untrustworthy.
- Treat the **plan-tier decision** (GitHub Team) as gating D-07/D-33 together;
  until then, keep those as *dated, compensating-controlled* acceptances — not
  silent gaps.
- Restore a working shell, then run Phases 1/4/2/3 in one authenticated pass.

**Verified vs. Assumed ledger (this session).**
- *Verified (file-read + live probe, 2026-10-06):* A-01–A-06, A-10, A-11. A-06
  and the **17-repo count are now live-confirmed**; git = 59 commits, tree clean
  (only the untracked plan file), and the **6** CI workflows confirmed present
  (`context-parity.yml` included). A-07/A-08/A-09 *status text* is from
  `drift-findings.md` headers.
- *Assumed (re-verify in later phases):* A-07/A-08/A-09 **live state** (pin
  resolution, out-of-band rulesets, off-host backup), the remaining ~40 "FIXED"
  register claims (§0.6), branch-protection `.protected` per repo, and whether the
  HCP Terraform workspace exists.

*Bottom line:* this is a well-engineered control plane carrying an
**unreconciled record** and a **frozen, singly-held state**. Neither is a code
quality problem; both are governance-trust problems, and both are exactly what a
SOC 2 Type II observation window (ADR-0008) will test. Fix the record first
(free), then the state custody (S0), then the supply-chain and ruleset-ownership
gates (S1) — in that order.

---

## Phase 0 results — record reconciliation *(executed 2026-10-06)*

Phase 0 was executed offline and, once a read-only channel to the live org was
established, with live verification. **Method note (honesty):** the `Bash` tool's
stdout capture failed for the entire session (empty even for `echo`). Verification
was completed through a **write-to-file → `Read`-back** channel, and the org was
confirmed authenticated as `JourneyOfLife` (`admin:org`/`repo`/`workflow`) so
read-only live checks ran. **No mutating command was run** — no `terraform`, no
`gh … PATCH`/`edit`, no push (AGENTS.md §5). Live outputs are retained on the
audit host at `/tmp/probe_a.txt` and `/tmp/probe_b.txt`.

### 0.1 Documentary contradiction table (Verified, `file:line`)

| Artifact | Claim | Reality | Finding |
|---|---|---|---|
| `README.md` L13/L138, `threat-model.md` L26, `change-management.md` L6 | "six repos" | **17 live** (16 allow-list + `.github`) | A-01 |
| `architecture.md` L43 | "14 YAML files" | 16 allow-list | A-01 |
| `compliance-gates.yml` L409 | D-01 "RESOLVED" | D-31 S1 BLOCKING OPEN | A-02 |
| `threat-model.md` L58/L85 | D-18 2FA "NOT enforced" | D-18 FIXED; `repo-defaults.yml` L151 `true` | A-11 |
| `threat-model.md` L86 | D-20 "OPEN — NOT ACCEPTED" | `drift-findings` "FIXED" — but **live: false** | A-11, A-06 |
| `repo-defaults.yml` L69 vs `repos/jolarca-control.yml` L72 | `require_code_owner_reviews` false vs true | validator checks neither | A-05 |
| `action-plan.md` L8/L46 | 2FA PENDING; "seven private repos" | D-18 FIXED; fleet public | A-04 |
| `AGENTS.md` §8 | secret-scan context runs readiness `--no-live`→deadlock | `compliance-scan.yml` runs gitleaks | A-03 |

### 0.2 A-05 — resolved (Verified)

`validate_repos.py` validates `require_signed_commits` **from policy** (L174) but
never reads `require_code_owner_reviews` (its branch-protection checks are
force-push/deletion/admins/linear-history/signed-count/contexts — L163-197). So
`repo-defaults.yml`(`false`) vs `repos/jolarca-control.yml`(`true`) is an
**unconstrained** inconsistency that no gate reconciles — the D-20/D-22
"declared control nobody verifies" class.

### 0.3 A-02 — the PCI visibility gate is satisfiable by editing a label (Verified + live)

`compliance_check.py`/`validate_repos.py` prohibit `confidential`/`restricted`
classification in a public repo (L50/L216). Therefore making a repo public
requires simultaneously **down-classifying it to `internal`**. All 16 repos are
now `visibility: public` (grep, 16/16) with `data_classification` internal(14)/
public(2) and **zero** confidential/restricted. Yet `compliance-gates.yml`
L388-396 records the classification was "*downgraded from confidential since the
content is now world-readable by force*," and D-31 / README / threat-model T-08
still describe the four repos holding DPIA / RoPA / contracts / PII / WireGuard
records. **If that content is genuinely regulated, the `internal` label is false
and the public exposure persists while the gate passes**; the automated control's
verdict is contradicted by the human register. *Decision required:* the owner must
re-classify the four repos on their **actual** content, independent of the
visibility outcome, before accepting public.

### 0.4 A-06 — **VERIFIED LIVE: D-20 "FIXED" is false**

Live CODEOWNERS probe (all 17 repos), `gh api …/contents/{.github/CODEOWNERS,
CODEOWNERS}` decoded in-process:
- **14** carry a CODEOWNERS; **3 absent**: `jolarca-infrastructure`,
  `jolarca-observability`, `jolarca-runbooks`.
- **5 carry forbidden cross-org refs** (`@journeyoflife-org/*` /
  `@jol-infrastructure/*`): **`jolarca-compliance`, `jolarca-consent`,
  `jolarca-data`, `jolarca-legal`, `jolarca-infrastructure`**.

`drift-findings.md` D-20 L85 asserts the five files (jolarca, jolarca-data,
jolarca-compliance, jolarca-legal, jolarca-infrastructure) were rewritten to
`@JourneyOfLife` and that "grep … returns no matches in any of the six CODEOWNERS
files." **Live disproves this for 3 of the 4 PCI-scope repos** (compliance, data,
legal) and shows jolarca-infrastructure now has **no** CODEOWNERS at all.
*Severity S1 (arguably S0):* an ADR-0004 R4 separation breach is live in
production under a register entry that declares it fixed, and `threat-model`
RA-07 states this breach **cannot be risk-accepted**. This is the single most
damaging finding for record credibility.

### 0.5 G10 — false-empty confirmed live

`ls .github/workflows` returns **6** files — `apply.yml`, `compliance-scan.yml`,
`context-parity.yml`, `evidence-integrity.yml`, `fleet-separation-guard.yml`,
`plan.yml` — whereas `Glob .github/workflows/*.yml` returned **0**. Hidden-dir
glob/grep results are unreliable here; every "absence" must be confirmed by a
second method (Rules of evidence §2.3).

### 0.6 "FIXED" re-verification queue for the remaining live phases

**FIXED/RESOLVED:** D-06, D-11, D-12, D-13, D-15, D-18, D-19, D-21, D-22, D-30,
D-32, D-34, D-35, D-36, D-38, D-47, D-49; B1, B3, B5, B6, H1, H2 (and the
`adr/0009-bugs-found-and-fixed.md` series). **PARTIALLY / pending merge:** D-02
(S0), D-39, D-50, D-51. **Still open:** D-01, D-03, D-08, D-09, D-10, D-14, D-16,
D-17, D-31, D-33, D-40, D-41, D-42, D-43, D-44, D-45, D-46, D-48. Each FIXED claim
becomes a live check in Phase 1/2; **A-06 already failed.**

### 0.7 Phase 0 conclusion

The governance record is **materially unreliable**: two artifacts disagree on
D-01/D-18/D-20, a false repo count propagates through four documents, and a
register "FIXED" claim is disproven against live production (A-06). Per the plan's
sequencing, **no downstream compliance assertion should be trusted until the
record is corrected** — which is the budget-free, immediately actionable first
remediation.

---

## Phase 1 results — declared-vs-live, fleet-wide *(executed 2026-10-06, read-only)*

Live sweep of all 17 repos + the org via authenticated read-only `gh api`
(evidence retained at `/tmp/p1.txt`, `/tmp/p1prot.txt`, `/tmp/p1q.txt`; no
mutations). The headline: **the register is correct on more org-level claims than
I assumed — but two live controls are weaker than the register lets on.**

### 1.1 "FIXED" claims CONFIRMED live (register was right)

| Claim | Live evidence | Verdict |
|---|---|---|
| D-18 org 2FA enforced | `two_factor_requirement_enabled=true` | **CONFIRMED** (and `threat-model.md` T-02/RA-06 "NOT enforced" is **false** → A-11 confirmed) |
| D-19 permissive defaults fixed | `members_can_create_repositories=false`, `default_repository_permission=none` | **CONFIRMED** |
| D-36 wikis disabled | `has_wiki=false` on 17/17 | **CONFIRMED** |
| D-33/D-39 branch protection | `.protected=true` on **15/15** content repos (2 empty: observability, runbooks) | **CONFIRMED present** — see 1.2 caveat |
| D-01/D-31/A-02 visibility | all 17 live `public` = declared | **coherent by declaration** — see 1.2 (classification integrity) |

### 1.2 NEW live findings

| ID | Sev | Finding (verified live) | Cross-ref |
|---|---|---|---|
| **A-12** | **S1** | `.protected=true` is **largely cosmetic fleet-wide**: **10 of 15** protected repos have **0 required status checks** — including every regulated repo: `jolarca-compliance`, `jolarca-data`, `jolarca-legal`, `jolarca-infrastructure`, `jolarca-identity`, `jolarca-security` (plus `consent`, `dr`, `vendor`, `.github`). Only `jolarca`(11), `jolarca-control`(3), `jolarca-hermes-agents`(3), `jolarca-payments`(2), `jolarca-docs`(1) enforce any check. By `repo-defaults.yml` doctrine a protected branch with zero contexts "enforces nothing" — so **no automated gate blocks a merge on 2/3 of the fleet**, voiding the "non-empty required status checks" compensating control cited for D-04. `enforce_admins=true` on the 12 readable, so where contexts exist they bind admins. | D-04, D-33, D-39, D-40, D-44, D-48 |
| **A-13** | **S1** | `secret_scanning` is **disabled on `jolarca-control` itself** (plus `.github`, `jolarca-observability`, `jolarca-docs`, `jolarca-runbooks`) while 11 repos have it enabled — yet `repo-defaults.yml` declares `secret_scanning: true` and `required_gates.secret_scan: true` fleet-wide. D-40 ("intent, not enforcement") live-confirmed and extended to the control plane. | D-40, D-05 |
| **A-14** | **S1** | All 15 live protections are **unmanaged**: `terraform.tfvars enable_branch_protection=false`, so Terraform owns **zero** `github_branch_protection` resources — the fleet's branch protection is entirely out-of-band and silently revertible. This is the concrete, live form of **A-08/D-46**. | D-08, D-46, A-08 |

### 1.3 D1-D9 matrix coverage

| Dim | Covered live this pass | Result |
|---|---|---|
| D2 visibility↔classification | yes | all public; none confidential/restricted → passes validator, but A-02 flags the label-move |
| D3 branch protection | yes (presence + strength, 15/15) | 15 present; **0 required contexts on 10/15** (A-12); `enforce_admins=true` on 12/15 readable |
| D4 CODEOWNERS | yes (Phase 0 §0.4) | 5 cross-org, 3 absent (A-06) |
| D5 secret scanning | yes | 11 enabled / 6 disabled incl. control plane (A-13) |
| D1 ownership, D6 Dependabot+CodeQL, D7 teams, D8 tier-gates, D9 license | **queued** | not re-probed this pass |

### 1.4 Could-not-verify (exit 2 — recorded honestly, not asserted)

- `enforce_admins` — verified `true` on 12/15; `jolarca-consent`, `jolarca-dr`,
  `jolarca-vendor` returned no `enforce_admins` key → **unverified** (ruleset-backed
  or partial payload — Phase 2 follow-up).
- `require_code_owner_reviews` live value — null/absent on 14/15, `true` only on
  `jolarca-docs` → code-owner review is effectively unset fleet-wide (consistent
  with D-20 being inert).
- Dependabot / CodeQL per-repo status; Terraform state contents / HCP workspace
  existence (D-02) — deferred to Phase 4.

### 1.5 Phase 1 conclusion

The migration to public **closed the D-33 protection-*presence* gap** and the
org-level "FIXED" claims (D-18/19/36) **hold live** — the register is more sound
than Phase 0 suggested. But protection **presence ≠ enforcement**: **10 of 15**
protected repos carry no required status checks at all (A-12), the control plane
itself lacks secret scanning (A-13), and none of the rules are under Terraform
(A-14). The compensating-control narrative for D-04 therefore needs to be
downgraded to "real automated gating exists on only 5 of 15 repos; the regulated
repos are unprotected-in-substance." **Do not re-close D-33/D-39 as FIXED** until
required contexts are populated and Terraform-managed.

**Root cause of A-12 (verified from `repo-defaults.yml` L201-208):** the
`branch_protection_baseline_exempt` list is exactly `{.github, jolarca-compliance,
jolarca-data, jolarca-identity, jolarca-infrastructure, jolarca-legal,
jolarca-security}` — precisely the regulated repos showing 0 contexts — so
`drift_detect` skips their `minimum_required_contexts` comparison and cannot flag
the gap (D-48). This is the **same carve-out-to-pass-a-check pattern as A-02**
(down-classify to go public): the control plane's gates are being satisfied by
exemptions and label changes rather than by enforcement.

---

## Recommended remediation path (professional opinion)

Sequenced by risk and by what is free vs authorization-gated vs blocked. **No
step below is executed** — every live mutation needs explicit owner authorization
(verify-after + dated deviation), and some are blocked by upstream work. This is a
recommendation, not an approval.

**Tier 0 — immediate, stop-work (S0, cross-repo, needs authorization):**
- **A-15** — `jolarca-docs`: rotate the 2 exposed credentials (gitleaks-verified),
  purge them from history (`git filter-repo`/BFG), enable secret scanning on that
  public repo, and open a GDPR/PCI incident record if they touch personal or
  cardholder data. Do **not** push from `jolarca-infrastructure` (A-16) or
  `jolarca-runbooks` (A-17) until their clones are re-synced / a remote is set,
  to avoid resurrecting remediated state.

**Tier 1 — free, safe, first (documentation-only signed PR here; no live change):**
- Correct the record: A-01 ("six/fourteen" → 16 allow-list, 17 live), A-03
  (AGENTS.md §8 secret-scan), A-04 (`action-plan.md` statuses), A-11
  (`threat-model.md` D-18/D-20), A-05 (`require_code_owner_reviews`).
- Re-open honestly in the register: D-20 **FIXED → OPEN** (A-06); add A-12/A-13/A-14;
  annotate D-33/D-39 as "present-but-exempt". Propose diffs; do not edit during the
  audit (concurrency). *This restores auditor credibility — the precondition for
  every other claim.*

**Tier 2 — prerequisite analysis, read-only (Phase 2):**
- **A-12 cannot be fixed safely yet.** Working hypothesis for the 10 zero-context
  repos (from D-47/D-48 + prior context-parity findings; **not** re-verified this
  pass): they declared required-context names matching no real CI job, so contexts
  were stripped to `0` to avoid a merge **deadlock**. Confirm per-repo with
  `scripts/check_declared_contexts.py` before any fix — the repair is two-sided (CI
  must emit the context on `pull_request` *and* the registry must name the real job).
  Force-enabling protection or contexts without this **deadlocks every merge**.

**Tier 3 — live mutations (owner authorization required):**
- **A-13** — enable secret scanning + push protection on the 6 public repos lacking
  it (incl. `jolarca-control`). Cheapest, highest signal; Free-plan-available.
- **A-12** — after Tier 2, attach the *real* required contexts to the 10 repos.
- **A-06** — rewrite CODEOWNERS to `@JourneyOfLife` in `compliance`, `consent`,
  `data`, `legal`, `infrastructure` — **cross-repo PRs**, not fixable from this
  control plane.
- **A-14** — bring protection under Terraform (`enable_branch_protection=true` +
  reconcile `branch-protection.tf`) — **blocked by D-02**: the state must migrate
  first, or Terraform fights the out-of-band rules.

**Tier 4 — structural / plan-tier (decision required):**
- **A-02** — owner re-classification of the four regulated repos on their *actual*
  content; if genuinely regulated, public is not acceptable regardless of label.
- **D-02 / A-09 (S0)** — HCP workspace + state migration + verified off-host AGE
  backup restore.
- **D-04 / D-10** — second-operator onboarding to restore real human review.

**Recommended immediate action:** land the **Tier 1** documentation PR (free, no
authorization risk) and run **Phase 2 (Tier 2)** read-only now — it needs no
authorization, keeps `gh` warm, and is the only path that turns A-12 from a finding
into an executable fix without risking a fleet-wide merge deadlock.

---

## Phase 2 results — control & gate effectiveness ("verify the verifier") *(read-only)*

Ran the repo's own gates (evidence: `/tmp/p2a.txt`, `/tmp/p2b.txt`, `/tmp/p2c.txt`,
`/tmp/p2docs.txt`; exit codes captured). **The detection engine is largely
effective** — it caught the S0 below and corroborated A-06/A-12 — but two of its
outputs are easy to misread, and the failures remain in *wiring*, not detection.

### 2.1 Gate effectiveness

| Gate | Fires on defects? | Exit here | Verdict |
|---|---|---|---|
| `check_declared_contexts.py` | **yes** — flagged `jolarca-identity` unproducible contexts | **1** | Effective, **but skips empty/no-commit repos** so it under-reports L-19 |
| `repo_readiness_audit.py --no-live` | **yes** — found the S0 leak + L-19/L-11/L-18/L-03/L-07/L-14 | **2** | Effective, **but exit 2 (live-unverifiable) understates its own decisive findings** |
| `compliance_check.py` | declared-config only (self-declared) | 0 (pass) | Honest, but `branch_protection: pass 16/16` is invisible to live A-12/A-14 |
| `gitleaks git jolarca-docs` (independent re-run) | **yes** | 1 | Confirms A-15 (2 leaks) |

**Methodological finding (A-20, S2):** no single gate is sufficient. `check_declared_contexts`
skips the empty repos where `repo_readiness_audit` finds L-19; and the readiness
gate's `--no-live` exit 2 conflates "found a stop-work S0" with "couldn't check
live." Severity should dominate exit code. The audit must run **both** gates and
read the report, not the exit code alone.

### 2.2 New verified findings

| ID | Sev | Finding (verified live / by independent re-run) | Cross-ref |
|---|---|---|---|
| **A-15** | **S0** | `jolarca-docs`: **2 secret leaks**. Independently reproduced — `gitleaks git` exits 1 ("leaks found: 2", 6 commits). Aggravated because `jolarca-docs` is **public with secret scanning disabled** (A-13), so push-protection could not have blocked them. Remediation is cross-repo: rotate, purge history, enable scanning, and open a GDPR/PCI incident record if the secrets touch personal/cardholder data. | D-40, A-13 |
| **A-16** | **S1** | `jolarca-infrastructure`: local clone **diverged from remote** (`L-18`: local `663839c` ≠ remote `7930bec`, not an ancestor) **and** live cross-org CODEOWNERS (`L-11`) → a push can resurrect the pre-fix refs. **Corroborates A-06** by a second, independent gate. | A-06, D-20 |
| **A-17** | **S1** | `jolarca-runbooks`: local clone has **no `origin` remote** (`L-03`) → commits invisible to protection/scanning/CI; detached branch. | — |
| **A-18** | **S1** | `jolarca-observability`: local dir **is not a git repo** (`L-02`) → all git-dependent checks skipped locally; plus L-19 context defect. | A-12 |
| **A-12+** | S1 | Context-parity **L-19** confirmed systemic: `jolarca-identity`, `jolarca-observability`, `jolarca-runbooks` (and `consent` prior) declare `ci`/`security`/`compliance`/`lint` contexts that no job emits → enforced-as-declared would deadlock every merge; this is *why* those repos show `CTX=0`. | D-47, D-48 |
| **A-21** | S2 | Recurring fleet hygiene: `.gitignore` missing policy-mandated patterns (`secrets.json`, `credentials.json`, `*.tfstate`, `.terraform/`) on `data`/`legal`/`security`/`vendor`/`runbooks`/`hermes-agents`; `pre-commit` hook not installed on `consent`/`docs`/`vendor` (`L-07`). | D-28 |

### 2.3 Phase 2 conclusion

The gates **detect** the problems (S0 leak, false-FIXED CODEOWNERS, context
deadlocks, mutable pins) — so "verify the verifier" is largely satisfied. The
material gaps are: (1) the gates' findings are **not reflected in the register or
docs** (record rot, Phase 0), and (2) on the regulated repos the gates are **not
wired as merge-blockers** (A-12 vacuous protection, A-14 unmanaged). The
newly-verified **A-15 S0 leak is now the top of the queue**, above D-02.

---

## Appendix A — Grounding evidence index (verified from files, 2026-10-06)

| Ref | Claim | Source |
|---|---|---|
| G1 | Allow-list = 16 `repos/*.yml` | `Glob repos/*.yml` |
| G1 | README "six repositories" | `README.md` L13, L138 |
| G1 | architecture "14 YAML files" | `docs/architecture.md` L43 |
| G2 | D-01 "RESOLVED" | `policy/compliance-gates.yml` L409-411 |
| G2 | D-31 "S1, BLOCKING, OPEN" | `docs/drift-findings.md` L207 |
| G3 | Secret scan runs gitleaks | `.github/workflows/compliance-scan.yml` L53-72 |
| G3 | AGENTS.md §8 stale claim | `AGENTS.md` §8 (tracked as D-42) |
| G4 | 2FA "PENDING" | `docs/action-plan.md` L8-12 |
| G4 | D-18 "FIXED 2026-10-01" | `docs/drift-findings.md` L149, L158 |
| G5 | `require_code_owner_reviews: false` | `policy/repo-defaults.yml` L69 |
| G5 | `require_code_owner_reviews: true` | `repos/jolarca-control.yml` L72 |
| G7 | D-43 / D-45 / D-50 / D-51 headers | `docs/drift-findings.md` L654, L784, L731, L746 |
| G8 | D-46 rulesets outside source of truth | `docs/drift-findings.md` L799 |
| G9 | D-02 "PARTIALLY FIXED" (S0) | `docs/drift-findings.md` L22-32 |
| G10 | Hidden-dir glob false empty | `Glob .github/workflows/*.yml` = 0 vs `Read` of `compliance-scan.yml` |
| — | Evidence-hashed dirs | `scripts/hash_evidence.sh` L35-42 (`docs/adr`, `audit`, `policy`, `repos`, `docs/runbooks`, `docs/security`) |
| — | Required contexts | `.github/workflows/compliance-scan.yml` L31, L43, L60 |

*End of plan.*
