# AGENTS.md — operating rules for AI agents in this repository

Versioned source of truth for how changes are made here. If an agent's memory and
this file disagree, **this file wins** — memory is a cache, not a record. Changes
to this file go through the same PR flow as any other governed artifact.

Scope: `jolarca-control`, the marketplace (`jolarca-dev`) governance control
plane. Public repository. Sole operator, no teams (ADR-0004 R4).

---

## 1. Non-negotiable workflow

```
VERIFY FIRST → COMMIT → PUSH → REVIEW → MERGE → VERIFY AGAIN
```

- Verify empirically. A tool's summary, a prior report, or an agent's own claim
  ("file updated successfully") is **not** evidence. Command output is.
- Search results are claims too. A grep that returns "no matches" or a truncated
  result set has not proven absence — read the file before asserting a defect.
- Re-verify after merge. Live state, not the merge banner.
- Never infer approval from a previous conversation. Approval lives in a dated
  record (`policy/compliance-gates.yml` `exceptions.active`) or it does not exist.

## 2. Commands

Setup and gates (all offline unless marked live):

| Command | Purpose |
|---|---|
| `make setup` | Create `.venv`, install pinned deps |
| `make lint` | Everything CI runs: fmt-check, tf-validate, validate, ruff, mypy, shellcheck, yamllint, tests |
| `make test` | Plan-safety fixtures + `pytest` |
| `make validate` | Validate `repos/*.yml` against policy |
| `make readiness REPO=<name>` | Pre-first-commit verdict: READY / READY-WITH-FIXES / BLOCKED |
| `make first-commit REPO=<name> STEP=A..F` | Read-only pipeline gate; prints commands, never runs them |
| `make evidence-check` | Verify evidence hashes against the **committed** registry |
| `make evidence-register` | Regenerate `docs/evidence-registry.csv`, then commit the diff in a PR |
| `make drift` / `make fleet-audit` / `make org-audit` | Live, read-only (need `gh` / token) |

Run Python through the venv: `.venv/bin/python -m pytest tests/ -q`. The system
`python3 -m pytest` can exit 1 with no output, which reads as a mystery failure.

`make apply` is **REFUSED by design** (exit 1) and `make plan` prompts before an
offline `-refresh=false` plan. Do not "fix" either. Both are gated on
`STATE_MIGRATION_COMPLETE`; see `docs/state-migration-runbook.md`.

## 3. Exit-code convention

Every gate in this repo is three-valued. Preserve this in any new gate:

| Code | Meaning |
|---|---|
| `0` | Verified safe / passed |
| `1` | Findings — a real refusal |
| `2` | **Could not verify.** Never a silent pass. |

An unreadable input, a missing baseline, or an unreachable API is `2`, not `0`.

## 4. Change classification — route on blast radius, not diff size

A 3-line change here can be catastrophic; a 400-line docs change can be trivial.

**High blast radius** — requires a human-read plan and top-tier review, regardless
of size: `*.tf`, `*.tfvars`, `repos/**`, `policy/**`, `.github/workflows/**`,
`scripts/**`, `docs/evidence-registry.csv`.

**Lower blast radius:** `docs/**` (prose), `staging/**`, `audit/**` checklists.

Specific high-consequence edits:
- `repos/*.yml` `visibility` — a public/private flip is D-01 class: it changes
  what is publicly readable inside PCI-DSS/GDPR scope.
- `terraform.tfvars` `enable_branch_protection` — weakening fires D-26.
- Anything touching GitHub secret-scanning or push-protection configuration.

## 5. Hard boundaries

- **No `terraform apply` from this root.** State is owned by
  `jolarca-infrastructure` until the migration runbook completes.
- **No `terraform state rm` / `state mv` / `import` by an agent.** Operator runs
  these; they are irreversible against a single local state copy (D-02).
- **No `gh api -X PATCH` for branch protection or repo settings.** Terraform is
  the source of truth; out-of-band PATCHes are silently reverted and create drift.
- **No `jol-*` / mission-platform references** in fleet files. ADR-0004 separates
  the mission platform from the marketplace; `make fleet-audit` enforces it.
- **No literal secrets or credential-shaped fixtures in tests or docs.** Push
  protection scans documentation, and a real-looking fixture can permanently
  S0-BLOCK the readiness gate. Use runtime-assembled synthetic values.
- **No new dependency, action, or tool version unpinned.** Dependencies pin in
  `requirements*.txt`; GitHub Actions pin to a full commit SHA with a `# vX.Y.Z`
  comment; ruff's rule set is pinned in `pyproject.toml` because its defaults
  move between releases.
- **Do not delete or weaken a gate to make CI pass.** If a gate is wrong, fix the
  gate and its fixtures in the same PR, and say so in the description.

## 6. Conventions

- Comments and documentation in English.
- Conventional Commits with a body that states *why*, not just *what*.
- Squash-merge PRs; keep history linear. Delete the feature branch.
- Match surrounding style. These files carry dense rationale comments explaining
  the defect that motivated them — that is deliberate, keep doing it.
- yamllint line length is 160 at **warning** level; prose-heavy compliance YAML
  is expected to warn. Do not reflow it to silence warnings.
- Documentation must state actual implementation status. Never describe a control
  as enforced when it is configured-but-inert or convention-only.

## 7. Verification standards

- **Verify the verifier.** A gate that runs and reports green has not been shown
  to detect anything. Every gate needs a **negative control** — a fixture that
  must fail. `tests/test_check_plan_safety.sh` is the model (10 cases including
  empty and missing plan). An untested regex gate is a hypothesis: D-22 was an
  inline `visibility\s*:` pattern that never matched `terraform show` output, so
  the only control between an unattended apply and a fleet-wide visibility flip
  was inert.
- **Evidence must be retained to count.** Verification output that justified a
  merge is a deliverable, not a transient. Evidence files under `docs/adr/`,
  `audit/`, `policy/`, `repos/`, `docs/runbooks/`, `docs/security/` are hashed
  into the committed `docs/evidence-registry.csv`; edit one and re-register in
  the same PR or `make evidence-check` fails.
- **Do not trust a correct verdict.** A gate can report the right aggregate
  answer while silently skipping whole check families (an early `return` on a
  missing `.git` once skipped six filesystem checks and the entire secret sweep).
  Cross-check finding counts against an independent run.

## 8. Controls that are NOT currently enforced

Recorded so no agent assumes protection that does not exist. Verify live before
relying on any of these; details and expiries in `policy/compliance-gates.yml`.

- **Branch protection is not active on this repo's `main`.** Squash-merge-only and
  PR-only are **convention**, enforceable by nothing today (D-33; the org is on
  the GitHub Free plan, which blocks protection on private repos).
- **`required_approving_review_count = 0`** — the sole operator can merge their
  own change (D-04, dated acceptance).
- **Tag protection is unenforceable** — release tags can be moved or deleted (D-07).
- **Open blocking findings** D-01, D-02, D-18, D-20, D-33 all block the first
  `terraform apply`. They are listed in `exceptions.open_blocking`, not accepted.
- **There is no targeted-apply mechanism.** `apply.yml` runs a whole-state
  `terraform apply -auto-approve tfplan`; the safety comes from the pre-apply
  `check_plan_safety.sh` gate plus `prevent_destroy`. `terraform plan -target`
  appears only as printed advice in `scripts/repo_readiness_audit.py`.

## 9. Session discipline

One task per session; start fresh at completed task boundaries. Before ending a
session, persist to durable artifacts (spec, plan, or this file) — not to chat:
accepted scope, task status, files changed, exact verification commands and their
output, and open questions. A fresh session reads the artifacts and real
`git status`, and re-runs verification when the recorded baseline is stale.

Two failed attempts at the same step: **stop**. Capture `git status`, `git diff`
and the exact command output, confirm nothing out of scope was touched, then
escalate. Do not let a model loop — loops are where it starts "fixing" things
nobody asked it to touch.
