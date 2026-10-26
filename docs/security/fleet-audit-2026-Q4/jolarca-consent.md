# Fleet Audit 2026-Q4 — `jolarca-dev/jolarca-consent`

**Verdict: NO-GO.** One S0, five S1, three S2.
Baseline `main` = `7e5f84045ae0ff0dc590aa5a60ce4639f26ae1a7`, manifest fingerprint `506723d8…9969`, 74 files, working tree clean.
Machine-readable register: [`jolarca-consent.yml`](jolarca-consent.yml). Measured 2026-10-26, read-only.

This is the GDPR consent store. Its job is to make consent **demonstrable** (Art. 7(1)) and
the demonstration **tamper-evident**. The code tries hard to do exactly that — and the audit
found that the mechanism proving it has never once run successfully.

---

## FA-consent-01 · S0 — changes reach `main` with no review and no gate

**What is wrong.** Protection exists in a form that does not gate merges. The active ruleset
`24087580` contains `deletion`, `non_fast_forward`, `required_linear_history` and nothing else.
There is no `pull_request` rule and no `required_status_checks` rule. The legacy endpoint answers
HTTP 404 "Branch not protected" while `branches/main.protected` says `true`.

**How it was identified.** `gh api repos/jolarca-dev/jolarca-consent/rulesets/24087580` for the
rule list; the rulesets *list* endpoint returns summaries without `rules`, which is why the
detail endpoint is mandatory — reading the list would have shown "one active ruleset" and looked fine.

**Reproduce.**
```bash
gh api repos/jolarca-dev/jolarca-consent/rulesets/24087580 \
  -q '{rules:[.rules[].type], updated_at, bypass_actors, current_user_can_bypass}'
gh api repos/jolarca-dev/jolarca-consent/branches/main        -q .protected
gh api repos/jolarca-dev/jolarca-consent/branches/main/protection   # HTTP 404
```

**Why it happens (root cause).** The ruleset was written on 2026-09-28 as a *bootstrap* rule —
stage 1 of the pattern documented in `repo_readiness_audit.py:1862-1870`, where `pull_request` and
`required_status_checks` are deliberately deferred "ONLY after the first PR reports green, or the
contexts are unsatisfiable and every merge deadlocks". PR #6 went green on 2026-10-15. Stage 2 was
never added. So this is an unfinished remediation, not a design choice — `jolarca-dr` and
`jolarca-vendor` both carry `pull_request` rules.

**Impact — measured, not assumed.** Eight CI jobs exist and run on PRs (`Lint (ruff)`,
`Type check (mypy)`, `Test (pytest)`, `Repository smoke-check`, `CodeQL (python)`,
`Gitleaks (secret scanning)`, `Dependency review`, plus `Verify Chain` off-schedule). **None can
block.** Two of them are red on every open PR right now (FA-consent-08), and that is survivable
only because nothing is required. History check: exactly one PR has ever merged here (#6 →
`7e5f84045`); commit `8e3a890bc` ("consent retention + expiry anonymization") has no PR with a
matching `mergeCommit` and its committer is the human, whereas the PR-merged commit's committer is
`GitHub`. So the ungated path has been used, not merely left open.

**Severity.** S0. Art. 7(1) + Art. 5(2) demonstrability cannot rest on a ledger whose integrity
controls are advisory; SOC 2 CC8.1 (change management) fails outright.

**What should change.** Add to ruleset `24087580`: a `pull_request` rule
(`required_approving_review_count: 0` is acceptable while D-04 stands; set
`required_review_thread_resolution: true` and `dismiss_stale_reviews_on_push: true`, as `jolarca-dr`
already does) and a `required_status_checks` rule naming the seven PR-producible contexts with
`strict_required_status_checks_policy: true`.

**How the fix is tested.** Re-read the ruleset detail and assert both rule types and a non-empty
context list; then prove a red check blocks a merge. Add the negative control that is currently
missing everywhere: a fixture asserting that a ruleset with `required_status_checks: []` is
**rejected** by `drift_detect.py` — the shape that fooled D-33.

**Sequence constraint (do not skip).** Do not add the required contexts before fixing
FA-consent-08: `Gitleaks` and `Dependency review` fail today, so making them required would wedge
every PR on the consent store. Fix the substrates, watch one green run, then require.

**What could go wrong during remediation.** A ruleset PUT replaces the whole document — omitting
`deletion`/`non_fast_forward` would silently drop them. Requiring a context name that no job
produces deadlocks all merges (A-01 precedent in `repos/jolarca-consent.yml:55-59`). An out-of-band
PATCH creates state drift that Terraform later reverts (AGENTS.md §5).

**Rollback.** Record the current document first, then restore verbatim:
```bash
gh api repos/jolarca-dev/jolarca-consent/rulesets/24087580 > /tmp/ruleset-24087580.before.json
# rollback:
gh api repos/jolarca-dev/jolarca-consent/rulesets/24087580 -X PUT \
  --input /tmp/ruleset-24087580.before.json
```

---

## FA-consent-02 · S1 — the hash-chain verifier has never run green

**What is wrong.** The `Integrity` workflow ("Verify Chain") is `failure` on all six most recent
scheduled runs (2026-10-21 through 2026-10-26 inclusive).

**How it was identified.** `gh run list -R jolarca-dev/jolarca-consent --workflow Integrity`, then
`gh run view 40286486523 --log-failed`. The step list shows `Run migrations=success` and
`Verify chain=failure`; the PostgreSQL log says
`ERROR: relation "consent_registry_consentrecord" does not exist` (plus `FATAL: role "root" does
not exist` twice).

**Reproduce.** Read `manage.py:10` and `project/settings/dev.py` next to `integrity.yml:47-57`.

**Why it happens (root cause).** The workflow exports `DATABASE_URL` pointing at the `postgres:16`
service and runs `python manage.py migrate` — but `manage.py` hardcodes
`DJANGO_SETTINGS_MODULE=project.settings.dev`, and `dev.py` overrides `DATABASES` to SQLite.
The schema is built in a throwaway file; the verifier then queries an empty PostgreSQL. The
migrate step "succeeds", which is what makes this invisible.

**Impact.** The control the repo cites for Art. 7(1) demonstrability (migration docstring:
"satisfies GDPR Art. 7(1) demonstrability and ISO 27001 A.8.12 integrity") has never been executed
against the engine it protects. Two consequences: the chain is unverified, **and** the DB-level
append-only triggers have never been created in any CI run — which is how FA-consent-03 stayed hidden.

**Severity.** S1. Not S0: it does not itself allow an unreviewed change (that is FA-consent-01),
but it removes the evidence that the ledger is intact.

**What should change.** Give the workflow a settings module that reads `DATABASE_URL` (or set
`DJANGO_SETTINGS_MODULE=project.settings.test` with a postgres override), assert the table exists
before verifying, and make the job fail **loudly** on an empty database rather than reporting
"valid, count=0" — `test_empty_chain_passes` shows empty is currently a pass.

**How the fix is tested.** The job must go green with a seeded chain *and* red when a record is
tampered on PostgreSQL. Today the tamper tests run on SQLite without triggers (FA-consent-03), so
porting them to postgres is the regression test this fix requires.

**What could go wrong.** Making this job required before it is green deadlocks merges (the exact
reason `repos/jolarca-consent.yml:60-62` excludes it). Seeding data must be synthetic — a realistic
fixture secret would S0-BLOCK the readiness gate.

**Rollback.** Revert the workflow commit; the schedule returns to its prior (failing) state, which
is why the pre-fix state must be recorded, not re-derived.

---

## FA-consent-03 · S1 — anonymization cannot execute on the engine that enforces append-only

**What is wrong.** `0002_add_append_only_triggers.py` installs `BEFORE UPDATE … RAISE EXCEPTION`
with no exception path. `retention.py:141-148` anonymizes by
`ConsentRecord.objects.filter(pk=…).update(subject_id=…, ip_address=None, user_agent="",
anonymized_at=…)`, and its own docstring states the purpose: *"Use QuerySet.update() to bypass the
ORM-level immutability guard."* It bypasses the ORM guard and hits the DB guard.

**How it was identified.** Reading the three files that must agree: `models.py:106-123` (ORM
guard), `migrations/0002…:23-52` (trigger), `retention.py:106-159` (UPDATE path).

**Impact.** On PostgreSQL — the engine `base.py:89` declares for production — the retention job
`anonymize_expired` raises instead of anonymizing. Withdrawn consent records past their TTL keep a
linkable `subject_id`, `ip_address` and `user_agent` forever. ADR-0003's resolution of the
Art. 7(1) vs Art. 17 conflict becomes non-operative, and Art. 5(1)(e) storage limitation is not met
by the mechanism the repo documents as meeting it.

**Severity.** S1, and explicitly **READ-VERIFIED, NOT RUN**. The SQL semantics are unambiguous, but
the run that proves it has never existed — CI cannot even create the trigger (FA-consent-02), and
there is no production settings module to point at postgres (FA-consent-06). This is stated as a
source-level contradiction, not a demonstrated runtime failure.

**What should change.** Pick one and test it on postgres:
(a) narrow the trigger to allow UPDATE only when the mutating columns are exactly the anonymization
set, verified inside the trigger body; or (b) perform anonymization through a `SECURITY DEFINER`
function that is the single authorized mutation path, and log its use; or (c) append a new
anonymized record and mark the old one superseded by an immutable pointer, keeping the table
strictly append-only. Option (c) fits ADR-0002's chain model best; option (a) is the smallest change.

**How the fix is tested.** A postgres-backed test asserting `anonymize_expired()` returns ≥1 and the
row is unlinkable, plus a test asserting an *unauthorized* UPDATE still raises. Both must run in CI.

**What could go wrong.** Weakening the trigger to let anonymization through also weakens it against
tampering — the adversarial suite's five paths use `.update()` and would start succeeding silently.
The fix must distinguish the two, and the tests must be ported to postgres or they prove nothing.

**Rollback.** This finding's fix is code-level: revert the migration plus its test. Never drop a
production trigger as a "rollback" — that removes integrity protection wholesale.

---

## FA-consent-04 · S1 — the API is uncallable, and the tests hide it

**What is wrong.** `base.py:139-151` sets `DEFAULT_PERMISSION_CLASSES=[IsAuthenticated]` together
with `DEFAULT_AUTHENTICATION_CLASSES=[]`. With no authenticator, every request resolves to
`AnonymousUser`, so `IsAuthenticated` denies all of it: the consent registry refuses every read and
every write. Meanwhile `test_api.py:21-33` and `test_adversarial.py:26-38` replace `REST_FRAMEWORK`
wholesale with `DEFAULT_PERMISSION_CLASSES=[]` — no auth — so the suite exercises a configuration
production does not have, and no test asserts the 401.

**How it was identified.** Comparing `base.py` against the two test class decorators; then checking
that CI's `Test (pytest)` job passes (`ci.yml:69`, `pytest --cov --cov-fail-under=80`) — green tests
on a service that cannot serve.

**Impact.** Two failure directions from one defect. Today: the service is dead on arrival for its
consumer (the marketplace app), so consent cannot be recorded at all — which makes Art. 7(1) moot
because there is no ledger being written. Tomorrow, if someone "fixes" it by leaving permissions
empty: the ledger becomes readable to any caller, including `GET /api/v1/consent-records/` with no
filter, returning every subject's `subject_id`, `ip_address`, `user_agent` and timestamps.

**Severity.** S1. It is fail-closed, so it is not a live exposure; it is a broken control plus a
test that cannot see the difference.

**What should change.** Choose the real trust model and express it once: service-to-service
authentication (e.g. a scoped OIDC/JWT or network mTLS at the gateway) with an authenticator class
configured, plus per-subject scoping (FA-consent-05). Then make the tests run against the **shipped**
settings module, injecting a test credential rather than deleting the permission requirement.

**How the fix is tested.** One test asserting `401/403` unauthenticated, one asserting `200` with a
valid credential, one asserting a *different* subject's records are not readable with a valid
credential. The `@override_settings` blocks must go.

**What could go wrong.** Adding authentication without scoping produces a false sense of closure
while FA-consent-05 stays open. Removing the overrides may fail many tests at once — that is the
intended signal, not a regression.

**Rollback.** Config-only revert (`base.py` + test decorators), redeploy.

---

## FA-consent-05 · S1 latent — no object-level authorization on personal-data reads

`views.py:38-61` filters by a client-supplied `subject_id` with no ownership check;
`views.py:122-141` (`DSRExportView`) returns all records for whatever `subject_id` is in the query
string; `models.py:40` stores `subject_id` as a bare UUID with no caller binding. The Art. 15/20
export is therefore a BOLA surface the moment traffic is permitted. Currently unexercisable —
FA-consent-04 blocks all traffic — so this is recorded as a **design defect**, not a demonstrated
vulnerability. Fix it in the same change as FA-consent-04, never after.

---

## FA-consent-06/07/08/09/10 — summary

| ID | Sev | One-line defect | Verified by |
|---|---|---|---|
| FA-consent-06 | S2 | No production settings module exists; `base.py` has `ALLOWED_HOSTS=[]` and empty DB password | `ls project/settings/`, grep for `settings.prod` → nothing |
| FA-consent-07 | S2 | `prev_hash` derived from `order_by("-timestamp").first()` with no lock/transaction → concurrent writes can fork the chain | source read; **NOT RUN** — no concurrency test exists |
| FA-consent-08 | S2 | `Gitleaks` fails for a missing `GITLEAKS_LICENSE`; `Dependency review` fails because the Dependency graph is off; declared config still reports coverage 16/16 | check-run annotations `121446022404`, `121446022514` |
| FA-consent-09 | S1 | Declared protection (`repos/jolarca-consent.yml:49-77`, strict + 7 contexts) is entirely unenforced, and the only Terraform path is refused by `check_plan_safety.sh` (D-61) → circular block needing an operator decision | file read + live 404/ruleset detail |
| FA-consent-10 | S2 | Red advisory signals accumulate: `CodeQL (python)` fails on #9/#10; six Dependabot PRs closed unmerged; 3.x majors stalled | `gh pr checks`, PR list |

---

## Method notes (what this pass refused to conclude)

1. `.protected=true` was not treated as protection. On this repo it coexists with zero merge gating.
2. "Direct push is possible" was **not** accepted from the ruleset shape alone. It was tested by
   exhaustively comparing every PR's `mergeCommit` against `main`'s history — and that changed the
   finding from capability to observed use.
3. `git log` committer identity (`Gintaras Kazlauskas` vs `GitHub`) was used as corroboration, not
   proof: a squash-merge message can be edited, so the PR-list comparison is the load-bearing evidence.
4. Every claim about PostgreSQL behaviour is labelled READ-VERIFIED because CI has never created the
   schema there (FA-consent-02). A contradiction you cannot run is a hypothesis with strong support.
5. `is_security_policy_enabled` returned `null` for all 17 repos, so no claim is made about which
   repos rely on the org-wide `SECURITY.md`. Unreadable ≠ absent.
6. Strengths are listed in the YAML register. An audit that only reports defects trains the reader to
   ignore severity.
