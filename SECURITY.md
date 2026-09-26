# Security Policy — jolarca-control

This repository is the governance control plane for `jolarca-dev`. It holds a
Terraform token capable of rewriting branch protection, visibility and
Dependabot settings on six PCI-DSS-scoped repositories. Treat it accordingly.

## Reporting a vulnerability

**Do not open a public issue.** This repository is private and the
organization has one member; a public report would disclose the control plane's
own weaknesses.

Report by either route:

1. GitHub private vulnerability reporting on this repository, or
2. The contact published in the org health repo
   ([`jolarca-dev/.github`](https://github.com/jolarca-dev/.github) →
   `SECURITY.md`), which GitHub serves org-wide.

Include: what you found, how to reproduce it, what you believe the impact is,
and whether you have already told anyone else.

**Response target: 4 hours** for anything affecting credential material or
branch protection. **GDPR Art. 33 notification: 72 hours** where personal data
is implicated.

## What counts as a security incident here

| Event | Severity | First action |
|---|---|---|
| `TF_GITHUB_TOKEN` or `GITHUB_TOKEN` exposed | P1 | Rotate immediately — `docs/runbooks/github-token-rotation.md`; then RB-03 |
| Terraform state file leaked or lost | P1 | RB-07; treat as loss of the sole ownership record (D-02) |
| Branch protection removed or weakened out-of-band | P1 | Restore from `repos/*.yml`; open a change record |
| A `jolarca*` repo appears that is not in the allow-list | P2 | RB-06 — ADR-0004 R2, 48 h import rule |
| A repo's visibility changed outside a PR | P1 | RB-02 / RB-06; check D-01 |
| A mission-platform (`jol-*`) resource in this state | P1 | ADR-0004 R3 violation; precedent already exists — see D-03 |
| `terraform apply` run from a root that does not own the state | P1 | Stop both roots; RB-07 |

## Known weaknesses

This control plane documents its own gaps rather than presenting an idealised
posture. The authoritative list is
[`docs/drift-findings.md`](docs/drift-findings.md), and the threat register
with its accepted risks is [`docs/threat-model.md`](docs/threat-model.md).

Open and **not accepted** as of 2026-09-25:

- **D-01** — `jolarca-compliance`, `jolarca-legal`, `jolarca-data` and
  `jolarca-infrastructure` are publicly readable while holding PCI-scope
  material. The allow-list declares them private; the live org disagrees.
- **D-02** — Terraform state is a single gitignored file on one host with no
  remote backend and no locking.
- **D-03** — the predecessor state holds a resource handle on
  `journeyoflife-org/.github`, a mission-platform repository.
- **D-13** — two Terraform roots currently declare the same real resources.
- **D-18** — org-wide two-factor authentication is **not** enforced.
- **D-19** — members may create repositories; default repository permission is
  `read`.

Accepted with compensating controls and an expiry: **D-04** (zero approving
reviews), **D-05** (signature enforcement off), **D-07** (tag protection
unenforced).

## Handling rules that apply to this repository

- **No secrets in git.** Not in `terraform.tfvars`, not in YAML, not in
  examples. Tokens come from the environment or from Actions secrets.
  `.gitignore` blocks `*.tfstate`, `.env*`, `*.pem`, `*.key`, `*.p12`.
- **No Terraform state in git.** It is gitignored and must stay that way; the
  policy copy of that rule is `policy/repo-defaults.yml` →
  `data_handling.terraform_state_in_git: prohibited`.
- **Signed commits** (`git commit -S`). Not enforced by branch protection
  (D-05) because provider automation commits cannot be signed — the obligation
  on humans is unchanged and it is the compensating control for D-04.
- **Every GitHub Action pinned to a full commit SHA**, never a tag or branch.
  See `CONTRIBUTING.md` → Code Standards.
- **No `--force` push to `main`**, ever. Branch protection blocks it; if you
  are in a position to remove that protection you are inside RB-03 and need a
  change record.

## Scope boundary

This policy covers `jolarca-dev` only. The mission platform
(`journeyoflife-org`, governed by `jol-control`) has its own control plane,
credentials and state, and the two must never be mixed — ADR-0004,
ISO 27001 A.8.13. A report about a mission-platform repository belongs with
`jol-control`, not here.
