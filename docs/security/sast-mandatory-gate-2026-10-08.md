# A-08 — Mandatory SAST gate made real (evidence record)

**Date:** 2026-10-08
**Finding class:** D-22 — "a detection no pipeline runs is folklore, not a control"
(AGENTS.md §7)
**Frameworks:** SOC 2 CC7.1/CC7.2 · ISO 27001 A.8.8/A.8.25/A.8.29 ·
PCI-DSS 6.3.1/6.3.2 · GDPR Art.32

---

## 1. The gap this closes

`policy/compliance-gates.yml` declares the gate

```yaml
  sast:
    id: codeql-analysis
    enforcement: mandatory
```

and `enforcement_matrix` lists `sast` in the `required` set for all three fleet
tiers. `jolarca-control` is `tier: governance`. So the repository asserted, on
paper, that static analysis was mandatory.

Before A-08 that assertion was inert:

- **Nothing ran Semgrep at all.** The `codeql-analysis` gate ID names a
  GHAS/CodeQL capability that is **unavailable on the GitHub Free plan**
  (private-repo 403 / no CodeQL on Free) — so the declared control could not
  even be satisfied by the engine it was named after.
- **Bandit ran only as a non-required job** inside `compliance-scan.yml`, over
  `scripts/` and **not** `tests/`, and its result did not gate a merge.
- **No gate checked the wiring.** `scripts/compliance_check.py` validated seven
  other concerns but had no notion of the SAST gate.

That is the D-22 class in gate form: a control declared, not verified to
detect, therefore a hypothesis.

---

## 2. What now exists

Three scanners, three independent signals, one workflow
(`.github/workflows/sast.yml`), triggered on `pull_request` and `push: main`
with **no path filter** (a path-filtered required context deadlocks docs-only
PRs — the failure mode recorded at `repos/jolarca-control.yml`).

| Job (`name:` = status context) | Engine / scope | Blocking behaviour |
|---|---|---|
| `SAST (semgrep)` | Semgrep OSS `1.179.0`, `p/default` + `p/python`, `scripts/` + `tests/` | `--error --severity ERROR --severity WARNING` → exit 1 on any ERROR/WARNING |
| `SAST (bandit)` | Bandit `1.9.4`, `-r scripts/ tests/ -ll -ii` | exit 1 on MEDIUM+ severity AND MEDIUM+ confidence |
| `Trivy Config Scan` | Trivy `0.75.0` config scan, repo root (Terraform + `.github/workflows/` + `policy/`/`repos/`/`audit/` YAML) | `--severity HIGH,CRITICAL --exit-code 1`, structured `.trivyignore.yaml` |

Constraints honoured:

- **No GHAS/CodeQL dependency.** Semgrep OSS runs identically on Free, public
  *or* private, with no license — so the gate is satisfiable on this plan.
- **Every action SHA-pinned.** `actions/checkout@3d3c42e5… # v7.0.1`,
  `actions/setup-python@5fda3b95… # v7.0.0`; Trivy installed by exact version
  via `curl` (mirroring the gitleaks pattern), because the `trivy-action`
  wrapper's `install.sh` failed on the release-asset fetch in CI 2026-10-08 and
  because the wrapper added two more supply-chain pins to keep honest.
- **`permissions: contents: read`** at workflow scope; no job escalates.
- **`pull_request`, not `pull_request_target`** — a fork PR never runs this with
  write access to the base repo.

---

## 3. First-run triage (every finding, with disposition)

The scanners were run against the clean tree (local venv + CI) before anything
was declared green.

### Semgrep — 0 findings on `scripts/` + `tests/`
No triage required. (CI confirms green on PR #55.)

### Bandit — 1 finding, a false positive → suppressed at source
- **B108** (`hardcoded_tmp_directory`) at `tests/test_repo_readiness_audit.py:489`.
  The literal `Path("/tmp/example")` is a pure-function *argument* in a unit
  test, not an insecure temp-file creation. Disposition: inline
  `# nosec B108` with a rationale comment — Bandit's own, reviewable suppression
  mechanism. No dated exception is warranted for a test fixture that never
  touches the filesystem; the suppression is the fix.

### Trivy config — 2 pre-existing findings, both accepted with expiry
Recorded in `.trivyignore.yaml` (structured form, passed explicitly via
`--ignorefile` — Trivy does **not** auto-load the YAML schema):

| ID | Severity | Location | Disposition | Expiry |
|---|---|---|---|---|
| `GIT-0004` | HIGH | `branch-protection.tf` — `require_signed_commits=false` | Accepted deviation **D-05** (`policy/compliance-gates.yml` `exceptions.active`); compensating control = every human commit here is GPG-signed; only provider automation is exempt | **2026-12-24** |
| `GIT-0001` | CRITICAL | `health-repo.tf` — org `.github` repo `visibility=public` | GitHub only serves community-health files from a **public** `.github`; a product-level impossibility, not a config choice. Covered by **fleet-public-2026-10** + existing inline `checkov:skip` | **2026-12-29** |

The gate was **not** weakened to make these pass (AGENTS.md §5): the severity
filter stays `HIGH,CRITICAL` and each accepted finding is named, referenced to
its exception ID, and expires with it. If D-05 lapses without renewal,
`GIT-0004` goes red again and forces an RB-04 decision.

---

## 4. Negative-control proof (non-vacuity)

Per AGENTS.md §7, a green scan proves nothing until it is shown to fire. A
throwaway PR (#56) introduced `scripts/_sast_negative_control.py` with two
deliberate vulnerabilities chosen so **only** the SAST scanners react — the
file is `ruff`-, `ruff format`-, and `mypy --strict`-clean (verified locally),
and the flake8-bandit `S*` rules are not in this repo's selected ruff set.

**Result on PR #56 (run `37699506676`):**

| Check | Outcome |
|---|---|
| `SAST (semgrep)` | **fail** — exit 1 |
| `SAST (bandit)` | **fail** — exit 1 |
| Lint, Policy Compliance Check, Regression Tests, Repository Secret Pattern Scan, Terraform Format, Trivy Config Scan, Validate Repo Allow-List | all **pass** |

Exact detections:

- Semgrep: *"Ran 314 rules on 12 files: 2 findings"* —
  `python.lang.security.audit.subprocess-shell-true` (Blocking, line 34) and
  `python.lang.security.audit.eval-detected` (Blocking, line 41).
- Bandit: `B602 subprocess_popen_with_shell_equals_true` (Severity **High**,
  Confidence High, line 34) and `B307 blacklist` eval (Severity **Medium**,
  Confidence High, line 41); exit code 1. The run also reported *"1 potential
  issue skipped due to #nosec"*, which independently confirms the B108
  suppression from §3 is being honoured by the same job.

The isolation of the failure to exactly the two SAST contexts is the point: the
scanners detect, and nothing else spuriously fires.

**Honest status of "refused".** PR #56 was marked `MERGEABLE` /
`UNSTABLE`, not hard-blocked. Detection is proven, but GitHub only refuses the
merge outright once `SAST (semgrep)` is a **required** status check — which
lands after §5 (the gate-wiring declaration + the live branch-protection
PUT). Until then the red SAST check is advisory. This record does not claim
merge-blocking before it is verified live. The throwaway PR was closed
unmerged and its branch deleted; the vulnerable commit is unreachable in every
clone that pruned it.

---

## 5. Wiring and the two-phase bootstrap

Committing the workflow and declaring its context in the *same* PR cannot be
green, and the reason is itself a control working correctly:
`scripts/check_declared_contexts.py` (the `Context Parity` job) reads workflow
definitions from **live `main`**, so a required context can only be declared
once the job that produces it exists on `main`. Declaring `SAST (semgrep)`
before `sast.yml` is merged is an unsatisfiable declaration — exactly the D-44
class bug that script exists to catch. The rollout therefore splits on the
AGENTS.md §8 two-phase bootstrap:

1. **PR #55 — workflow.** Adds `sast.yml`, removes the old non-required Bandit
   job from `compliance-scan.yml`, adds `.trivyignore.yaml` and the B108
   `# nosec`. **All green.** Does not touch `repos/**`, so Context Parity is
   correctly not triggered.
2. **Merge #55**, then confirm `SAST (semgrep)` reports green on `main`.
3. **Gate-wiring PR** — `scripts/compliance_check.py` gains
   `check_sast_gate_wiring()` (fails if the repo is in a tier where `sast` is
   mandatory but `SAST (semgrep)` is not in its declared required contexts),
   `repos/jolarca-control.yml` declares the context, `tests/test_compliance_check.py`
   covers it with positive *and* negative controls. Context Parity is green at
   this point because `sast.yml` is on `main`.
4. **Live branch-protection PUT** adds `SAST (semgrep)` as a required context —
   an operator action (it is a mutating, high-blast-radius change and, if it
   names a context the workflow does not emit, it deadlocks the repo).

`check_sast_gate_wiring` deliberately asserts the **declaration** (a static,
re-runnable property) rather than querying a live check-run status: a required
context that depends on another required context completing is a circular,
flaky gate. The runtime *enforcement* of "SAST must be green to merge" is the
branch-protection required-context, not this static cross-check. The two
together are what makes the paper mandate real.

---

## 6. Verification commands

```bash
# Local scanners (venv-pinned, matching CI):
.venv/bin/semgrep scan --config p/default --config p/python --error \
  --metrics=off --severity ERROR --severity WARNING scripts/ tests/   # → 0 findings, rc 0
.venv/bin/bandit -r scripts/ tests/ -ll -ii                           # → rc 0 after B108 nosec
trivy config --severity HIGH,CRITICAL --exit-code 1 \
  --ignorefile .trivyignore.yaml .                                    # → rc 0 (2 accepted)

# Gate wiring is exercised by the compliance gate:
.venv/bin/python scripts/compliance_check.py                          # sast_gate_wiring: pass
.venv/bin/python -m pytest tests/test_compliance_check.py -q          # positive + negative controls

# Negative control (throwaway, closed): see run 37699506676.
gh run view 37699506676 --json name,conclusion -q '{.name, .conclusion}'
```

---

## 7. Exit criteria / expiry

- **Phase 1 (workflow):** DONE — PR #55 green, ready to merge.
- **Phase 2 (declaration + wiring):** authored on branch `ci/sast-gate-wiring`;
  opens as a follow-up PR **after** #55 is on `main`.
- **Phase 3 (live required context):** pending operator PUT; when done, re-run a
  negative control and assert `mergeStateStatus: BLOCKED` with the SAST context
  listed under `required_status_checks.contexts`.
- **Accepted Trivy findings** inherit their exceptions' expiries
  (D-05 → 2026-12-24; fleet-public-2026-10 → 2026-12-29); removal of the
  corresponding exception re-fires `Trivy Config Scan` red by construction.
- **Scanner version pins** (semgrep 1.179.0, bandit 1.9.4, trivy 0.75.0) are
  reviewed on the same cadence as other pinned tools; a bump is a reviewed
  change, not a floating tag.
