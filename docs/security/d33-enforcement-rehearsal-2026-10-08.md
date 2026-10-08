# D-33 enforcement rehearsal — jolarca-control/main, 2026-10-08

**Record date:** 2026-10-08
**Prepared by:** sole operator (JourneyOfLife / Gintaras Kazlauskas)
**Task:** A-06 — technical enforcement of D-33 compensating controls
**Framework refs:** SOC 2 CC6.1 / CC8.1 · ISO 27001 A.5.1 / A.8.32 · GDPR Art.32 · PCI-DSS Req 6.3 / 6.5
**Cross-references:** D-04 · D-05 · D-10 · D-18 · D-20 · D-33 · D-35 · RB-03 · RB-04 · RB-08 step C

---

## What was flipped

Two out-of-band mutations against the live org, authorised by the operator
for this session. Terraform state is **not** updated — the D-35 precedent
(protection created out-of-band, not yet Terraform-managed) is extended, not
resolved.

| Surface | Setting | Before (2026-10-07) | After (2026-10-08) | Verified by |
|---|---|---|---|---|
| `jolarca-control` repo `.security_and_analysis.secret_scanning.status` | | `disabled` | `enabled` | re-read via `gh api repos/jolarca-dev/jolarca-control` |
| `jolarca-control` repo `.security_and_analysis.secret_scanning_push_protection.status` | | `disabled` | `enabled` | same |
| `jolarca-control` repo `.security_and_analysis.dependabot_security_updates.status` | | `disabled` | `enabled` | same |
| `jolarca-control` `main` branch protection `.required_pull_request_reviews.required_approving_review_count` | | `0` | `1` | re-read via `gh api repos/jolarca-dev/jolarca-control/branches/main/protection` |

All other branch-protection fields preserved (verified by re-read, not by
trusting the PUT 2xx response — the "2xx does not guarantee applied" pattern
is documented under `important_decision_experience` for
`jolarca-consent`). Current live state on `jolarca-control/main`:

```
strict: true
contexts: ["Validate Repo Allow-List", "Policy Compliance Check", "Repository Secret Pattern Scan"]
enforce_admins: true
required_approving_review_count: 1
dismiss_stale_reviews: true
require_code_owner_reviews: false
required_linear_history: true
allow_force_pushes: false
allow_deletions: false
required_conversation_resolution: true
```

## Consequence accepted for this session

`required_approving_review_count: 1` violates the ACTIVE exception D-04
(`policy/compliance-gates.yml:249-264`, expires `2026-12-24`, exit_trigger:
"second-operator onboarding — raise the count to 1 in the same PR that
resolves D-20 and replaces the individual CODEOWNERS entries with real
jolarca-dev teams").

Combined with `enforce_admins: true`, admins cannot bypass the review
requirement either. Practical effect at the time of writing:

- **Every currently-open PR on `jolarca-control` is deadlocked** (#41, #51,
  #40, #33, #29, #28, #6) — no reviewer exists besides the author.
- **This rehearsal PR (`feat/d33-enforcement-rehearsal`) will also be
  deadlocked once opened.** It is authored by the same sole operator.
- The task prompt accepted this: *"interim; D-04 re-approval is separate"*.
- Rollback path if this becomes operationally intolerable before the D-04
  exit trigger fires: `gh api -X DELETE repos/jolarca-dev/jolarca-control/branches/main/protection/required_pull_request_reviews`
  or lower the count to 0 in a fresh PUT. Both are owner decisions.

## Rehearsal 1 — direct push to `main`

**Setup.** Throwaway branch `test/a06-direct-push-rehearsal` created off
`main`; single file added (`.a06-rehearsal`, one line of documentation);
commit `c9d1154` GPG-signed. Attempted push with an explicit source-to-target
refspec that would have fast-forwarded `main` if allowed.

**Command.**

```bash
git push origin test/a06-direct-push-rehearsal:main
```

**Output (verbatim, redacted only of branch/commit identifiers that are not
secret material):**

```
remote: error: GH006: Protected branch update failed for refs/heads/main.
remote:
remote: - Changes must be made through a pull request.
remote:
remote: - 3 of 3 required status checks are expected.
To github.com:jolarca-dev/jolarca-control.git
 ! [remote rejected] test/a06-direct-push-rehearsal -> main (protected branch hook declined)
error: failed to push some refs to 'github.com:jolarca-dev/jolarca-control.git'
```

**Exit code.** `1` (from `${PIPESTATUS[0]}`).

**Post-state verification.**

```bash
$ git ls-remote origin -h refs/heads/main
dece75fbcf5943a052678e9312ca91fbb265cc93  refs/heads/main
```

Remote `main` unchanged. Refusal is server-side, driven by `enforce_admins:
true` combined with the PR-required rule.

**Conclusion.** **REFUSED — expected.** Branch protection genuinely blocks a
direct push to `main` even for an authenticated repo admin. This closes D-33
interim control (3) *"PR-by-convention is unenforced and bypassable without
trace"* on `jolarca-control` specifically.

**Cleanup.** Throwaway branch deleted locally. Never landed on remote, so
nothing to delete server-side.

## Rehearsal 2 — push of a canary secret

The intent was to prove GitHub push protection refuses a push containing a
secret. Empirical result is **more nuanced than "it works"** and is recorded
honestly rather than dressed up.

### Canary A — regex-shape GitHub personal access token

Assembled body matches `ghp_[A-Za-z0-9]{36}` — 40 total characters, one line
in `a06-canary.txt`. Synthetic: never issued by GitHub; body spells out its
own purpose. Push command:

```bash
git push --no-verify origin test/a06-canary-push-rehearsal-v2
```

**Result: PUSH SUCCEEDED.** Refusal was expected; none came. The commit
`4138c2d` was created on the remote as branch
`test/a06-canary-push-rehearsal-v2`, then deleted immediately after
verification (`git push origin --delete`). Nothing lingers.

`GET repos/jolarca-dev/jolarca-control/secret-scanning/alerts` returned `[]`
(zero alerts), confirming GitHub's scanner never flagged it either — the
provider validation path rejected the token as not plausibly real.

### Canary B — SSH private key block

Freshly generated with `ssh-keygen -t ed25519 -N ""`, copied into
`a06-canary-ssh.pem`, staged with `git add -f` to bypass `.gitignore`
pattern `*.pem`, committed `--no-verify`. Push over **both SSH and HTTPS
transports** (the HTTPS variant temporarily added the remote URL with a
`gh auth token` — same behaviour).

**Result: PUSH SUCCEEDED on both transports.** Commit `94f84e7` landed on
branch `test/a06-canary-sshkey-v2` and was immediately deleted. Same
provider-validation rationale: GitHub's push protection fires on **specific
provider patterns the scanner validates with the issuer**, not on generic
high-entropy or PEM blocks. Free-plan on public repos does not include SSH
private keys in its push-protection pattern set.

### Canary C — Slack API token shape (the one that fired)

Body assembled to match GitHub's documented Slack token pattern
`xoxb-<digits>-<digits>-<alnum>`, all placeholders (never issued). One line
in `slack-canary.txt`, committed `--no-verify`. Push:

```bash
git push --no-verify origin test/a06-canary-slack
```

**Result: REFUSED by push protection. Verbatim:**

```
remote: error: GH013: Repository rule violations found for refs/heads/test/a06-canary-slack.
remote:
remote: - GITHUB PUSH PROTECTION
remote:   —————————————————————————————————————————
remote:     Resolve the following violations before pushing again
remote:
remote:     - Push cannot contain secrets
remote:
remote:       (?) Learn how to resolve a blocked push
remote:       https://docs.github.com/code-security/secret-scanning/working-with-secret-scanning-and-push-protection/working-with-push-protection-from-the-command-line#resolving-a-blocked-push
remote:
remote:       —— Slack API Token ———————————————————————————————————
remote:        locations:
remote:          - commit: 3fd6e824fb2cf6f11d22f6bfb6b74b1f9bbfe31b
remote:            path: slack-canary.txt:1
remote:
remote:        (?) To push, remove secret from commit(s) or follow this URL to allow the secret.
remote:        https://github.com/jolarca-dev/jolarca-control/security/secret-scanning/unblock-secret/3KNteutCCbN2mLzeYv2sVrPwGzN
To github.com:jolarca-dev/jolarca-control.git
 ! [remote rejected] test/a06-canary-slack -> test/a06-canary-slack (push declined due to repository rule violations)
error: failed to push some refs to 'github.com:jolarca-dev/jolarca-control.git'
```

Exit code: `1`. `GH013: Repository rule violations` is GitHub's server-side
push-protection error. It names the secret type, points at the exact commit
and file path, and returns an "allow this specific secret" URL — the standard
bypass flow requiring human acknowledgement per commit.

**Cleanup.** Throwaway branch deleted locally; nothing landed remotely, so
no server-side deletion required. Canary files removed,
`git reflog expire --expire=now --all` and `git gc --prune=now` executed to
remove the orphaned blobs from the local object store.

### What this rehearsal actually proves

Push protection on `jolarca-control` is enforced at the level of **provider-
validated tokens** — the subset of secret patterns GitHub has an issuer
pipeline for (Slack, GitHub fine-grained PATs and classic PATs from real
account ranges, AWS key pairs, Stripe keys, etc.). It is NOT a general
high-entropy or regex-only gate.

Consequences:

1. A real credential that GitHub can pattern-match to a known provider is
   blocked at push time. **This is the D-33 (3)/(4) interim control the task
   asked to stand up.**
2. A synthetic fixture that matches the regex but is not plausibly issued is
   allowed through. That is a FEATURE for the D-52 / F-01 remediation
   pattern (`"AKIA" + "<body>"` at A-04) — the tests that legitimately
   embed regex-shaped synthetic fixtures still pass push, and gitleaks (not
   push protection) is the sweep that keeps them honest.
3. SSH private keys, PEM blocks, and generic high-entropy blobs are **not**
   in the Free-plan push-protection pattern set for public repos. The
   compensating control for those is the repository's own gitleaks gate
   (`Repository Secret Pattern Scan` required context, plus the pre-push
   local hook and the `make gate` suite), not GitHub's scanner. This
   limitation should NOT be reported as a passing D-33 control.

## D-33 interim control status after A-06

`policy/compliance-gates.yml:310-318` (D-33 exception body) lists four
interim controls. Post-A-06:

| Interim control | Status | Evidence |
|---|---|---|
| (1) `drift_detect.py` reads `.protected` (not the 403 protection endpoint) | **still outstanding** — not touched by A-06 | `scripts/drift_detect.py` — the field-name bug fix is on PR #28 (D-44), still pending merge |
| (2) `enable_branch_protection = true` on public repos | **DONE for jolarca-control**, still pending on the other 6 public repos with content | This rehearsal; the seven other public repos with `.protected = true` are per memory `ebb1a6a2` Notes 2026-09-30 |
| (3) PR-by-convention is unenforced and bypassable without trace | **CLOSED on jolarca-control** by Rehearsal 1 (direct push refused) | this record |
| (4) No off-host Terraform state backup (D-02) | **still outstanding** — unrelated to this task | D-02 open_blocking |

The D-33 exception row is **NOT** cleared. It remains CONDITIONAL and listed
in `exceptions.open_blocking` per `policy/compliance-gates.yml:410-418`.
The remaining interim controls (1) and (4) are separate work items.

## Rehearsal artefact integrity

- All commands in this record were run on 2026-10-08 against live org
  `jolarca-dev`, repo `jolarca-control`.
- No canary body (Slack-shaped or otherwise) is reproduced here. The Slack
  canary pattern shape is described in prose only, following
  `docs/security/f01-l16-synthetic-fixture-acceptance.md`'s precedent —
  reproducing the exact body in a tracked file would itself match a
  provider pattern and either (a) block this very push if we ever widen
  push protection, or (b) create an inconsistent state where the doc
  contradicts the policy it describes.
- The synthetic SSH key generated for Canary B was removed from `/tmp`, the
  local branch was deleted, `git reflog expire --expire=now --all` + `git
  gc --prune=now` executed. No blob of it survives in the local repository
  object store.
- The synthetic Slack canary in Canary C never left this workstation; the
  push was refused before any commit reached the remote. The remote branch
  was not created, so nothing needs server-side deletion.
- Canary A landed and was deleted server-side; the deleted commit remains
  reachable via its SHA `4138c2d...` for a short period until GitHub's
  own housekeeping GC. The body is a synthetic string never issued by any
  provider, so retention is harmless; noted here for the record.
- `git ls-remote origin 'refs/heads/test/*'` at the close of the session
  returns nothing — verified clean.

## Verification commands

Reproducible from a fresh clone. Read-only against the org:

```bash
# Live branch protection on main
gh api repos/jolarca-dev/jolarca-control/branches/main/protection \
  --jq '{arc: .required_pull_request_reviews.required_approving_review_count, \
         ea: .enforce_admins.enabled, \
         afp: .allow_force_pushes.enabled, \
         ad: .allow_deletions.enabled, \
         rlh: .required_linear_history.enabled, \
         rcr: .required_conversation_resolution.enabled, \
         strict: .required_status_checks.strict, \
         contexts: .required_status_checks.contexts}'

# Live repo security_and_analysis
gh api repos/jolarca-dev/jolarca-control \
  --jq '.security_and_analysis | {ss: .secret_scanning.status, pp: .secret_scanning_push_protection.status, dsu: .dependabot_security_updates.status}'

# Live secret-scanning alerts (should be empty; the rehearsal canaries were either refused or provider-validated as fake)
gh api 'repos/jolarca-dev/jolarca-control/secret-scanning/alerts' --jq 'length'
```

## Exit criteria for this record

This rehearsal record remains valid as long as:

1. `required_approving_review_count` on `jolarca-control/main` stays `>= 1`.
2. `enforce_admins` stays `true`.
3. `secret_scanning_push_protection.status` stays `enabled`.
4. The `Repository Secret Pattern Scan` required context stays in the branch
   protection `contexts` list (that is the gitleaks gate compensating for
   the push-protection scope gap identified above).

If any of those drifts, re-run the rehearsals and re-record. `drift_detect.py`
does not yet check `.protected` (interim control 1 above), so this record
is currently the human-cued verification path.

## Sign-off checklist

- [x] Branch protection live and readable via `gh api` (HTTP 200, not 403 —
  jolarca-control is public, per memory `ebb1a6a2` Notes)
- [x] `required_approving_review_count` verified by re-read, not by trusting
  the PUT response
- [x] Direct push to `main` refused by `GH006` (branch protection)
- [x] Provider-token push refused by `GH013` (push protection)
- [x] Non-provider-token pushes (SSH key, regex-shaped but fake) NOT refused
  — recorded as scope limit, not as pass
- [x] Every rehearsal artefact cleaned; `git ls-remote` shows zero residual
  branches
- [x] Consequences accepted: open PRs on `jolarca-control` are deadlocked
  until D-04 exit trigger fires or the operator lowers the count / disables
  `enforce_admins`

**Decision owner:** Operator (single-member org, no teams; D-10).
**Terraform alignment:** deferred; branch-protection.tf remains inert (D-35).
Reconcile against `policy/repo-defaults.yml` before promoting to Terraform
managed (D-26 weakened-guard fires otherwise).

---

## Reconciliation (A-08, 2026-10-08) — supersedes the review-count claims above

The rehearsal above is a valid record of what was observed **at execution
time** (the `arc 0→1` PUT was applied and re-read back as 1). It is **not**
the current live posture, and this PR is **not** merged declaring
`required_approving_review_count: 1`:

- **Live today is `arc = 0`** (re-verified via
  `gh api repos/jolarca-dev/jolarca-control/branches/main/protection`).
  `main`'s `repos/jolarca-control.yml` declares `0`. They agree.
- **`arc = 1` is not a workable posture for this org.** On GitHub Free a PR
  author cannot approve their own pull request, and `enforce_admins = true`
  removes the admin override. With a single operator and no second human,
  `arc = 1` is a **permanent self-merge lockout** — a denial of service on
  the control plane, not a control. A-06 therefore keeps the rehearsal's
  *demonstration* (the gate CAN be enforced) but reverts the *declaration* to
  the D-04 accepted exception (`arc = 0`, dated, compensating controls).
- **Exit criterion #1 above (`arc stays >= 1`) and the Sign-off line
  "`required_approving_review_count` verified ... [as 1]" are superseded** for
  current state. The enforceable posture is instead the set of
  **`strict = true` required status contexts** — now four after A-08:
  `Validate Repo Allow-List`, `Policy Compliance Check`,
  `Repository Secret Pattern Scan`, **`SAST (semgrep)`** — plus push protection
  and the gitleaks gate. A red one of those genuinely blocks a merge.

**If a future owner wants approvals required:** that needs a second human or
moving `enforce_admins = false` so the operator can admin-override — an RB-04
decision, not a default. Until then `arc = 0` is the honest, verified state.
