# Change Management Policy

## Scope
This policy governs all changes to the `jolarca-control` Terraform
configuration, policy baselines, and repository allow-list definitions — i.e.
every change that can alter the six `jolarca-dev` repositories.

SOC 2 CC8.1 · ISO 27001 A.8.32 · PCI-DSS Req 6.5.1.

## Solo-operator reality

`jolarca-dev` has one member and no teams (D-10). Approving-review counts are
therefore **0** fleet-wide (D-04) and cannot serve as the approval control.
What replaces them:

- **CODEOWNERS review is configured but INERT** on all five `jolarca*` repos —
  see **D-20**. `require_code_owner_reviews = true`, yet the referenced teams do
  not exist in `jolarca-dev` (zero teams) and in several cases name the *mission*
  org. Verified consequence: `jolarca-infrastructure` PR #26 merged with zero
  reviews and zero requested reviewers. Do **not** describe this as a human
  gate. Changes arrive through a PR, but no human approves them.
- **Non-empty required status checks** — the automated gate that actually
  decides, and currently the only real gate.
- **The `production` environment's manual approval prompt** in `apply.yml` —
  a deliberate human pause before any apply.
- **The plan-refusal gate** — `apply.yml` aborts on any destroy, replace, or
  visibility change.
- **Signed operator commits** — attribution, since review is self-review.

Do not describe any of this as "two-person rule" in audit evidence. It is not.
The compensating controls above are what should be written down.

## Change Categories

### Standard Changes (pre-approved pattern, still via PR)
- Adding a new repository to the allow-list (RB-01)
- Updating a repository description or topics
- Adding a required status-check context that already reports green

### Normal Changes (require explicit decision + change record)
- Changing repository visibility (RB-02) — **always** blocked by CI until run manually
- Adding or removing a compliance gate
- Changing reviewer counts or CODEOWNERS enforcement
- Reclassifying data (`docs/data-classification.md`)
- Anything that alters `terraform.tfvars`

### Emergency Changes (break-glass)
- Incident response requiring immediate access changes
- Secret exposure (RB-03)
- Must be documented retroactively **within 24 hours** in `jolarca-compliance`
- A break-glass change that removed branch protection must restore it in the
  same session — never leave a repo unprotected overnight

## Change Process

```
┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
│  Define  │──▶│ Validate │──▶│   Plan   │──▶│  Approve │──▶│  Apply   │
│  (PR)    │   │  (CI)    │   │(PR cmt)  │   │(env gate)│   │ (1 stage)│
└──────────┘   └──────────┘   └──────────┘   └──────────┘   └──────────┘
```

1. **Define** — feature branch; edit `repos/*.yml`, `policy/`, or `*.tf`.
2. **Validate** — `validate_repos.py`, `compliance_check.py`,
   `terraform fmt -check`, `terraform validate`, fleet separation guard.
3. **Plan** — gated on `STATE_MIGRATION_COMPLETE`; posted as a sticky PR
   comment. Until the state migration completes, plan is skipped and the PR
   says so explicitly rather than showing a misleading empty diff.
4. **Approve** — the `production` environment's manual approval prompt. This is
   the **only** human gate: CODEOWNERS review does not fire (D-20), and with one
   member nobody but the author can review. Confirm the environment prompt is
   actually enforceable on this plan before relying on it — see
   `docs/security/key-custody.md` deviation 2.
5. **Apply** — merge to `main` triggers a **single** production apply. There
   is no dev → staging → prod promotion: a GitHub organization control plane
   has exactly one target, so promoting the same plan three times would apply
   identical changes to the same real repositories three times.

## Approval Matrix

| Change | Automated gate that must pass | Human gate |
|---|---|---|
| Add repo | validate + compliance + fleet-separation + plan | `production` env approval — see caveat below |
| Edit repo settings | validate + compliance + plan | `production` env approval — see caveat below |
| Remove repo | — | `prevent_destroy` blocks it; requires deleting the lifecycle guard in a reviewed PR, then manual apply |
| Change visibility | validate + plan | **CI refuses**; manual apply per RB-02 with the plan transcript archived |
| Policy change | validate + compliance | `production` env approval — see caveat below |
| State migration | — | `docs/state-migration-runbook.md`, change record, off-host backup verified |
| Emergency | none | Org owner; documented within 24 h |

**Caveat on the human-gate column — read this.** There is currently **no
effective human review** in this organization. `require_code_owner_reviews` is
inert (D-20, proven by PR #26 merging with zero reviews), `required_approving_
review_count` is 0 (D-04), the org has one member who cannot approve their own
PR, and the `production` environment's required-reviewer rule could not be
confirmed as enforceable on the plan in force (key-custody deviation 2). The
gates that genuinely decide are automated: the required status checks, the
plan-refusal gate in `apply.yml`, `prevent_destroy`, and the
`STATE_MIGRATION_COMPLETE` hard gate. Do not represent this matrix to an auditor
as human segregation of duties. Restoring one requires the second operator
(D-10 trigger) plus the CODEOWNERS remediation in D-20.

## Rollback Procedure

1. Revert the PR that caused the issue — `git revert`, never a force-push.
2. Merge; the apply reverts the GitHub state.
3. Verify with `python3 scripts/drift_detect.py` and
   `bash scripts/org_delivery_audit.sh`.
4. If the change touched Terraform **state** rather than config, reverting the
   PR is not enough — follow `docs/runbooks.md` RB-07 and restore from the
   verified off-host backup.
5. Record the rollback in the original change record; a change record without
   its rollback outcome is incomplete evidence.
