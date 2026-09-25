# Contributing to jolarca-control

## Governance Model

All changes to `jolarca-control` follow the change management policy in
[`docs/change-management.md`](docs/change-management.md). This is a governance
repository: a one-line edit here can change branch protection, visibility or
Dependabot settings on **all six** `jolarca-dev` repositories, which sit inside
a PCI-DSS scope.

> **Not yet authoritative.** Until `docs/state-migration-runbook.md` completes,
> nothing in this repository is applied to GitHub. PRs are still reviewed and
> merged normally; `apply.yml` refuses to run. See the banner in `main.tf`.

## Before you open a PR

```bash
make setup         # creates .venv, installs the PINNED runtime + dev dependencies
. .venv/bin/activate
make lint          # terraform fmt + validate, allow-list validation, ruff,
                   # mypy --strict, shellcheck, plan-gate regression tests
make compliance    # full policy report — DECLARED config only, see the scope note in the JSON
make drift         # live comparison against jolarca-dev (read-only; needs gh auth)
```

If `make lint` fails locally it will fail in CI. There is no fast path around it.

Dependencies are pinned in `requirements.txt` / `requirements-dev.txt`, and the
ruff and mypy rule sets are pinned in `pyproject.toml`. Do not install tooling ad
hoc: ruff's default rule selection changes between releases, so an unpinned ruff
makes "lint passes" mean something different on your machine than it does in CI.
`requests` is deliberately absent from `requirements.txt` — no script imports it,
and an unused dependency is supply-chain surface for nothing.

## Adding a New Repository

Full procedure: [`docs/runbooks.md`](docs/runbooks.md) **RB-01**.

1. File the **repository lifecycle request** issue
   (`.github/ISSUE_TEMPLATE/repo-request.yml`) first. It is the approval record
   that must exist *before* the repo does; a PR alone does not show who asked for
   the repository or why. Deletion, rename and visibility changes use the same
   form.
2. The name must match `jolarca` or `jolarca-<suffix>`. This is enforced three
   independent times (Terraform precondition, `validate_repos.py`,
   `check_fleet_separation.sh`) because ADR-0004 mission/marketplace separation
   is the control that keeps PCI scope away from the mission platform. If your
   repo does not fit the name, it does not belong in this org.
3. Copy the closest existing entry in `repos/` and edit it.
4. Set `compliance.data_classification`. `confidential` or `restricted` forces
   `visibility: private` — validation fails otherwise.
5. Set `criticality` and `launch_status` against the rubric in
   `policy/repo-defaults.yml#asset_inventory`. These are the asset-inventory
   attributes an auditor uses (ISO 27001 A.5.9); `criticality` is **not** the
   same axis as the functional `tier`, and `confidential`/`restricted` data may
   not be `tier-3` because tier-3 is defined as holding no regulated data.
6. Set `required_status_checks.contexts` to contexts the repo's workflows
   **actually report**. A context that never reports blocks every PR forever.
7. PR → read the posted plan → merge.

## Modifying Policy

1. Edit `policy/repo-defaults.yml` or `policy/compliance-gates.yml`.
2. State the rationale in the PR description and link the ADR in `docs/adr/`.
3. If the change weakens a control, add it to `exceptions.active` in
   `compliance-gates.yml` with a compensating control and an expiry date, and
   to the risk acceptance register in `docs/threat-model.md`. An undocumented
   weakening is an audit finding; a documented one with an expiry is a
   decision.
4. `validate_repos.py` reads the signed-commit expectation from
   `repo-defaults.yml`, so changing it there changes what the validator
   enforces. That is intentional — do not hardcode the expectation back into
   the script.

## Updating Compliance Gates

1. Edit the gate in `policy/compliance-gates.yml`.
2. Update `enforcement_matrix`. Tiers here are `governance`, `platform`,
   `devops` only.
3. Update `required_status_checks` in the affected `repos/*.yml`.
4. Land the workflow that produces a new context **first**, confirm it reports
   green, and only then make it required — otherwise every open PR blocks.

## Code Standards

Marked ✅ where a machine actually enforces it. A standard nothing checks is a
hope, so the gaps are stated rather than left implied (the same doctrine
`policy/compliance-gates.yml` applies to D-07).

- ✅ Terraform must pass `terraform fmt -check` and `terraform validate` —
  `make fmt-check`, `make tf-validate`, and CI.
- ✅ Python must pass `ruff check` and `mypy --strict` — `make py-lint`,
  `make py-type`, and the **Static Analysis & Gate Tests** CI job. Rule
  selection and strictness are pinned in `pyproject.toml`; do not rely on ruff's
  defaults, which change between releases.
- ✅ Shell must pass `shellcheck` — `make sh-lint` and the same CI job.
- ✅ Plan-inspection gates must have regression tests — `make test`
  (`tests/test_check_plan_safety.sh`). An untested regex gate is a hypothesis,
  not a control; that is exactly how D-22 shipped inert.
- ✅ YAML must pass `yamllint -c .yamllint .` — `make yaml-lint` and the same CI
  job. There was no project config before, so "the project defaults" meant
  yamllint's built-in 80-column limit, which produced 345 findings on
  prose-heavy compliance text. `.yamllint` sets 160 columns (matching
  `jolarca-infrastructure`) and downgrades line length to a **warning**, so
  errors fail and long rationale prose does not. Do not run it with `--strict`.
- GitHub Actions must be **pinned to a full commit SHA**, never a tag or
  branch, with the version in a trailing comment. Every action in
  `.github/workflows/` follows this; a new unpinned action is a supply-chain
  regression (threat model T-12).
- Commits must be signed (`git commit -S`). Branch protection does not enforce
  signatures — deviation D-05 — because provider automation commits cannot be
  signed. The obligation on humans is unchanged and it is the compensating
  control for the zero-review deviation.

## Review and Approval

`jolarca-dev` has one member and no teams, so `required_approving_review_count`
is **0** (deviation **D-04**). Be clear about what that means in practice:
CODEOWNERS review is *configured* but **does not fire** (deviation **D-20**) —
the teams it names do not exist in this org. So changes still arrive through a
PR and still pass required status checks, but **no human approves them**. The
automated gates are the control, not a stand-in for one. Do not describe this
repository as having human review until D-20 and D-04 are both closed.

Do not write "two-person rule" or "N approvals" in a PR description or in audit
evidence. It would be false. See `docs/change-management.md` → *Solo-operator
reality* for the accurate wording.

## Emergency Changes

For incident response requiring immediate change:

1. Make the change. The org owner is the approver; there is no second approver
   to obtain, so do not claim one.
2. Document in `jolarca-compliance` **within 24 hours**: what changed, why,
   what the compensating controls were, and what was verified afterwards.
3. Retroactive review by the same operator, recorded as a self-review. Say so
   plainly — an auditor who discovers an unlabelled self-review treats it as a
   control failure, whereas a labelled one is a documented limitation.
4. If branch protection was removed, restore it in the same session (RB-03
   step 4).
