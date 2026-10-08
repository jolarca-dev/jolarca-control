# F-01 / L-16 — Synthetic-fixture false-positive acceptance

**Record date:** 2026-10-07
**Prepared by:** sole operator (JourneyOfLife / Gintaras Kazlauskas)
**Status:** Accepted false positive; no history rewrite; reviewed under RB-04
**Frameworks:** SOC 2 CC7.2 · ISO 27001 A.8.24 · GDPR Art.32 · PCI-DSS 3.5
**Cross-references:** ADR-0009 F-01 · ADR-0009 F-04 · RB-03 · RB-04 · RB-08 step C · L-15 · L-16 · L-17

---

## What this record accepts

Running `scripts/repo_readiness_audit.py --repo jolarca-control --no-live`
on 2026-10-07 produces exactly one finding:

- `L-16 · severity S2 · category secrets · "secret-pattern match in git
  history"`. Two regex hits across the full blob history, both redacted in
  the report body. The audit's own note on the row says *"gitleaks ran and
  reported NO leak, so this is a regex-only match requiring human triage"*.

This record IS that triage. The two matches are documented false positives;
no action is required beyond retaining this file.

## Empirical basis (2026-10-07)

Verified by running the gates themselves, not by reading prior reports
(AGENTS.md §1).

| Check | Command | Result |
|---|---|---|
| Working tree clean | `gitleaks dir . --no-banner --redact` (default config) | `no leaks found`, exit 0 |
| Working tree clean, no allowlist | `gitleaks dir . --config <title-only>` | `no leaks found`, exit 0 |
| Git history, no allowlist | `gitleaks git . --config <title-only>` | `no leaks found`, exit 0 across 86 commits |
| Readiness regex sweep on tracked files | `python3 scripts/repo_readiness_audit.py --repo jolarca-control --no-live` | `secret_hits_head: []` |
| Readiness regex sweep on history | same command | `secret_hits_history: 2 matches` (AWS + Stripe), L-16 at **S2** not S0 |
| Full pytest | `.venv/bin/python -m pytest tests/ -q` | **217 passed** |
| Evidence integrity | `make evidence-check` | **36 files scanned, 0 mismatches** |

## Which blobs carry the historical literal shapes

Location only, never the string. The bodies are not reproduced here because
reproducing them would make this governance document itself match the
pattern and re-block the repository — the trap explicitly called out in
`docs/runbooks/first-commit-pipeline.md` §"Known issue" and the reason
prior fixtures were refactored to runtime assembly.

| Rule name | Commit(s) | Path | Line at the time |
|---|---|---|---|
| AWS access key ID (`AKIA[0-9A-Z]{16}`) | `0e17920`, `c4b6c5a` | `tests/test_repo_readiness_audit.py` | 515 (redacted) |
| Stripe live secret key (`sk_live_[0-9a-zA-Z]{24,}`) | `0e17920`, `c4b6c5a` | `tests/test_repo_readiness_audit.py` | 894 (redacted) |

Both fixtures were replaced in commit `ac0da96 feat: add readiness gate
improvements and first-commit pipeline (RB-08)` (2026-09-28) by runtime
assembly — the strings are now built as `"AKIA" + "<body>"` and
`"sk_live_" + "<body>"`, so no continuous credential-shaped sequence exists
in the current file. Verified by `grep -c 'AKIA[0-9A-Z]{16}' tests/test_repo_readiness_audit.py`
returning 0.

## Why this is a false positive

1. **Never issued by any provider.** Neither AWS nor Stripe has ever
   published these byte sequences. There is no issuer record, no bill, no
   audit trail behind them. They were typed into a fixture to exercise the
   gate's regex.
2. **The gate's own source says so.** `scripts/repo_readiness_audit.py`
   emits the L-16 evidence line *"The known benign class is a documented
   test fixture"*. This is that documented fixture.
3. **Rotation is not applicable and must not be faked.** The RB-08 runbook
   (step C, §"A synthetic fixture is not a credential") forbids inventing a
   rotation record — a fabricated rotation is worse than an unrecorded
   false positive because it corrupts the incident timeline an auditor
   reads.

## Why the history was not purged

Purging blobs from git history requires `git filter-repo` + force-push under
**RB-03**, on a repository that is already public and referenced by other
governance artefacts. RB-03 reserves that class of rewrite to an explicit
owner decision, and the risk-reward is negative here:

- The rewritten objects would still be reachable from any pre-existing fork
  or GitHub support-cache copy until a Support ticket detached them (an
  out-of-band step this repo cannot perform).
- GitHub's own secret scanning does not flag them — gitleaks reports
  `no leaks found` across all 86 commits even with no allowlist, because
  gitleaks' built-in AWS rule requires an accompanying secret-access-key
  or entropy signal that an isolated key-id does not meet.
- The residual that DOES fire — the repo's own regex sweep in the readiness
  audit — is already scoped to a governance document (this record) that
  the next auditor can consult instead of re-triaging.

If a future owner decides to purge anyway, RB-03 steps 3–5 govern; nothing
in this record precludes that. The decision here is only to accept the
current state, not to forbid a later change.

## What changed to make this acceptance safe

- `.gitleaks.toml` no longer allowlists `tests/**`. Empirically verified
  2026-10-07 that the exclusion was not load-bearing, and the task's
  explicit constraint "do not exclude tests/ from the sweep" matches
  RB-08 §"Known issue" step 4 and the AGENTS.md §5 principle that a real
  secret pasted into a test file is still a real secret.
- `.gitleaksignore` carries zero entries. The file remains because a future
  literal fixture must be dealt with via an explicit, dated, reviewed
  exclusion line rather than by re-widening `.gitleaks.toml`.
- The prior `.gitleaksignore` header asserted a "negative-control test"
  that fails if the file is emptied. No such test exists; the assertion was
  itself a D-40 class defect (a control described as enforced but not
  present) and is corrected in that file's header comment.

## Verification commands for the next auditor

All read-only. Reproduce every claim above:

```bash
# gitleaks against the working tree and history with NO allowlist of any kind
printf 'title = "bare"\n' > /tmp/bare.toml
gitleaks dir .  --config /tmp/bare.toml --no-banner --redact --exit-code 0
gitleaks git .  --config /tmp/bare.toml --no-banner --redact --exit-code 0

# the repo's own regex sweep, redacted output
.venv/bin/python scripts/repo_readiness_audit.py --repo jolarca-control --no-live \
  | python3 -c 'import sys, json; d = json.load(sys.stdin); \
      r = d["reports"][0]; \
      print("secret_hits_head:", r["facts"]["secret_hits_head"]); \
      print("secret_hits_history:", r["facts"]["secret_hits_history"]); \
      print("findings:", [(f["fid"], f["severity"]) for f in r["findings"]])'

# locate the exact blobs, WITHOUT printing their bodies
git cat-file -p 0e17920:tests/test_repo_readiness_audit.py \
  | grep -cE 'AKIA[0-9A-Z]{16}|sk_live_[0-9a-zA-Z]{24,}'
# expect: 2 (one per pattern family). Do not widen to a `-o` display — the
# point of this file is that nobody has to see the body to know what it is.

# confirm the current source uses runtime assembly, not literals
grep -nE '"AKIA" \+ |"sk_live_" \+ ' tests/test_repo_readiness_audit.py tests/test_first_commit_pipeline.py
```

## Exit criteria for this record

Rotate the classification from "accepted false positive" to "resolved" only
when **both** hold:

1. The pre-`ac0da96` blobs are unreachable from any branch or tag that is
   still meaningful to the fleet (either purged via RB-03 or superseded by
   a repository re-bootstrap that starts from a clean history).
2. `scripts/repo_readiness_audit.py` reports empty
   `secret_hits_history` on `main`.

Neither holds on 2026-10-07; the record stands.

## Related

- ADR-0009 §Bug F-01 — the original defect (source literals in test
  fixtures). Fixed by runtime assembly.
- ADR-0009 §Bug F-04 — the path-based allowlist that was applied as
  defense in depth while F-01 landed. Superseded by this record's
  `.gitleaks.toml` tightening.
- RB-03 — Respond to Secret Exposure. Not invoked: no real credential was
  ever exposed.
- RB-04 — Update a Compliance Gate. This record IS the change summary for
  the `.gitleaks.toml` and `.gitleaksignore` modifications in the same PR.
- RB-08 — Phase 3 first-commit pipeline gate, §"Known issue" at
  `docs/runbooks/first-commit-pipeline.md:268`. The runbook's S0 framing
  is out of date as of this change; it will be aligned separately.
- D-20's 2026-10-06 correction row is the closest relative in the D-series
  register — same class, "documentation asserts a control that is not
  there". D-20's enforcement gap and this acceptance record are separate
  findings.

---

**Decision owner:** Operator (single-member org, no teams; ADR-0004 R4).
**Reviewable as:** a dated artefact under `docs/security/`, hashed into
`docs/evidence-registry.csv`.
