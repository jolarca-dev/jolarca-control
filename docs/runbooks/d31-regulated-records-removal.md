# Runbook: removing regulated records from public git (D-31 / option B1)

Status: **PROCEDURE ONLY — not executed.** Landing this runbook does **not**
remediate D-31. The exposure persists until an operator runs every step below
against `jolarca-dev/jolarca-compliance` and `jolarca-dev/jolarca-infrastructure`
and verifies the outcome. D-31 stays **S1, BLOCKING, OPEN** (see
`docs/drift-findings.md` D-31 and D-52) until Step 9 verification passes.

Framework scope: GDPR Art. 5(1)(f), Art. 30 (RoPA), Art. 32 (security of
processing), Art. 33 (breach notification); PCI-DSS Req 1.2 (scope);
ISO 27001 A.5.10 / A.8.10 / A.8.13; SOC 2 CC6.1 / CC6.3 / CC9.2.

Owner / blast radius: Steps 5–7 are **irreversible and cross-repo**
(`git filter-repo`, force-push, a GitHub Support request). Per AGENTS.md §5
those are executed by the sole operator, never by an agent or a PR from this
control plane. This repo's role is the governed destination design, the
regenerable inventory, and the verification evidence.

---

## 1. Why the visibility fix was rejected

Two options were on the table: (a) flip the repos private, (b) move the records
out of public git. **Option (a) was executed and reverted on 2026-10-06** — it
makes the control plane's required context *Context Parity* exit 2, because its
`GITHUB_TOKEN` (scoped to `jolarca-control`) cannot read a private sibling's
`.github/workflows`, so `scripts/check_declared_contexts.py` files those repos
`unverifiable`. Privating a governed fleet repo therefore blinds the control
plane to exactly what it must oversee, and on the Free plan also withdraws
branch protection, secret scanning, push protection and Dependabot security
updates from that repo (D-33). See D-52 for the measured evidence.

**Option B1 is chosen:** the regulated records are operational compliance
artifacts, not source — they belong in an **encrypted, access-controlled,
non-git destination**, and the public fleet repos keep only genuinely
publishable content.

---

## 2. Destination design (B1)

- **Mechanism:** an `age`-encrypted archive per repo per snapshot, stored in an
  object store with **versioning + retention lock** (align with the fleet's
  existing WORM / age backup conventions).
  - [OPERATOR SETS] destination bucket/prefix, e.g. `gs://<jolarca-compliance-archive>/d31/`.
  - [OPERATOR SETS] age recipient (X25519 public key). The **private** key lives
    in the operator's key custody, never in any repo. (Do not paste key material
    here or anywhere in git — push protection scans docs; see AGENTS §5.)
- **Access control:** sole operator key holder; every decrypt is an auditable
  event. Retention aligned to the RoPA's own `retention_class` values, not to
  git history.
- **Availability duty (non-negotiable):** the GDPR Art. 30 RoPA must remain
  *maintained and available to the controller and supervisory authority*.
  Therefore **stage + verify the destination before any deletion** — there must
  be no window where the record exists in neither the public repo (deleted) nor
  the destination (not yet written).
- **Integrity:** the destination index carries a `sha256` per file, recorded in
  the runbook's own verification (this file is evidence-hashed).

---

## 3. Authoritative inventory (regenerate, do not trust the snapshot counts)

Run read-only against live `main` of each repo before acting; the list below is
what a 2026-10-06 run matched and is **broader than the earlier D-52
spot-enumeration** (which used a narrower pattern and under-counted).

```bash
for r in jolarca-compliance jolarca-infrastructure; do
  echo "== $r =="
  gh api "repos/jolarca-dev/$r/git/trees/main?recursive=1" \
    --jq '.tree[]|select(.type=="blob")|"\(.size)\t\(.path)"' \
  | grep -iE 'ropa/|dpia/|risk-register/|vendor-assessments/|data-subject-requests/|incidents/|lawful-basis/|audits/|security/deviation-register\.md|payment'
done
```

Path prefixes to move out of **`jolarca-compliance`** (public repo keeps none of
these once remediated):

- `ropa/` (incl. `master-register.csv`, `by-system/*.md`)
- `dpia/` (incl. `003-payments-and-vat/dpia.md`, the largest)
- `risk-register/`
- `vendor-assessments/` (every `*/assessment.md` + `register.csv`/`register.md`)
- `data-subject-requests/`
- `incidents/` (register + breach-notification templates)
- `lawful-basis/` (consent versions + legitimate-interest assessments)
- `audits/gate-evidence/` and `audits/internal/` (payment-boundary audit reports
  and execution bundles)

Path prefixes / files to move out of **`jolarca-infrastructure`**:

- `security/deviation-register.md` — the acute item: a public list of the org's
  own control weaknesses (an attacker roadmap).
- `audits/internal/` (infra-audit report + gate-0 preflight)
- the payment-boundary design artifacts (`payment-api-contract.md`,
  `payment-boundary-enforcement.md`, `STEP10_PAYMENT_BOUNDARY.md`) —
  **operator decision**: some IaC/architecture is legitimately publishable
  (ADR-0007 posture); move only what reveals the CDE topology/weaknesses, keep
  the rest. This is the B3 split applied per-file.

Non-records that may stay: top-level `README.md` stubs, `.gitkeep`, and generic
`.markdownlint.json`. Replace a moved directory's content with a short
`README.md` that says the authoritative record now lives in the controlled
destination (pointer, not data).

---

## 4. Procedure (operator)

Preconditions (Step 0): age installed (`age --version`); destination bucket with
versioning + retention lock enabled; the recipient public key registered; an
up-to-date off-host state backup exists (D-02/D-13 make this urgent — with no
force-push block, recovery from a rewritten history depends on a copy that is
not on the pushing host).

1. **Enumerate** (Section 3 command) → freeze the exact file list + per-file
   `sha256` into a working manifest kept outside git.
2. **Stage**: export the enumerated files from `main` (blob contents), build a
   per-repo archive, `age --encrypt` it, upload to the destination, and record
   the archive's `sha256` in the destination index.
3. **Verify destination** BEFORE deleting anything:
   ```bash
   age --decrypt -i <private-key> <archive>.age | tar -x -C /tmp/verify
   sha256sum -c <per-file manifest>   # every record must match
   ```
   Do not proceed until this passes. This is the "stage before delete" rule.
4. **Remove from HEAD** in each repo: `git rm -r <prefix>` for the moved paths,
   add pointer `README.md`, commit, open a PR there. This alone does **not** end
   the exposure (history) — it only stops new readers of HEAD.
5. **Purge history** (irreversible — operator). **Never run whole-directory
   prefixes** (`--path audits/ --path docs/ --path security/`). A read-only
   dry-run on 2026-10-07 (Section 6) measured that those prefixes would remove
   **102 of 218** full-history paths in `jolarca-compliance` and **54 of 334** in
   `jolarca-infrastructure`, most of it *collateral*: every `README.md` /
   `.gitkeep` / `.markdownlint.json`, the generic breach-notification and consent
   templates, and on infrastructure the entire `docs/` ADR set (0001-0007) and
   the operational runbook set. That destroys governance and ops documentation,
   irreversibly. Use a **frozen exact-path manifest** and dry-run it first:
   ```bash
   # MANDATORY gate: apply the manifest to a throwaway clone and diff the
   # full-history path sets before -> after. removed must equal the manifest and
   # collateral must be empty. Nothing is pushed; the clone is discarded.
   c=$(mktemp -d); git clone --quiet https://github.com/jolarca-dev/<repo> "$c"
   ( cd "$c"
     git log --all --pretty=format: --name-only --diff-filter=AMR | sort -u > "$c/before.txt"
     git filter-repo --invert-paths --paths-from-file /abs/regulated-blobs.txt --force
     git log --all --pretty=format: --name-only --diff-filter=AMR | sort -u > "$c/after.txt"
     comm -23 "$c/before.txt" "$c/after.txt"   # removed paths == manifest, EXACTLY )
   rm -rf "$c"
   ```
   The manifest is in Section 6. `filter-repo` treats a trailing-`/` line as a
   directory and any other line as an exact path. Coordinate first: a rewrite
   breaks every fork, clone and open PR in those repos (measured `forks_count = 0`
   on both, so there are no third-party forks to re-contact).
6. **GitHub Support request** — HEAD-rewrite leaves the old commits reachable
   via cached/network objects and forks. Open a support ticket to **detach and
   purge the history**, and re-contact any forks. Until support confirms, the
   blobs may still be retrievable — **this is why Step 3 (stage) is mandatory
   and why the assessment in Step 8 cannot be skipped.**
7. **Verify blobs are gone** (negative control — must find nothing):
   ```bash
   d=$(mktemp -d); git clone --quiet https://github.com/jolarca-dev/jolarca-compliance "$d"
   cd "$d"
   git log --all --oneline -- ropa/ dpia/ vendor-assessments/   # expect empty
   git rev-list --all --objects | grep -E 'ropa|dpia|deviation-register' # expect empty
   gh api "repos/jolarca-dev/jolarca-compliance/git/trees/main?recursive=1" \
     --jq '.tree[].path' | grep -iE 'ropa/|dpia/|vendor-assessments/'       # expect empty
   ```
8. **Re-classify honestly** in `jolarca-control` `repos/*.yml`: once only
   publishable content remains, set each repo's `data_classification` to what
   the *remaining* content warrants. Do **not** keep `confidential` on a public
   repo that no longer has confidential content, and never use a downgrade to
   hide content that is still present — `scripts/validate_repos.py` hard-fails a
   `confidential`/`restricted` repo that is `public`, and the D-31 masking
   defect was precisely a `confidential`→`internal` downgrade that disabled that
   gate while the records stayed public.
9. **GDPR Art. 32/33 assessment** (parallel, owner, in `jolarca-compliance`):
   the disclosure already happened (records public since at least the
   2026-09-25 enumeration). Determine whether the exposure to date is
   notifiable and record the determination. This is independent of cleanup
   timing — the act occurred regardless of when the history is purged.

---

## 5. Limitations / risks

- A history rewrite is destructive and unrecoverable except from a pre-rewrite
  backup — Step 0's off-host backup is the only safety net.
- Forks and any GitHub-side caches can retain the old blobs after a force-push;
  only the Support purge (Step 6) addresses that, and only once confirmed.
- Until Steps 5–7 pass, "moved out of git" is not yet true in the forensic
  sense; treat D-31 as OPEN until Step 7 verification is clean.

## Related

D-31 (the finding), D-52 (option (a) attempted + reverted; (b) chosen; the
CI-coupling constraint), D-33 (private repos unprotected on Free — compounds
why privating is not a fix), D-02 / D-13 (state backup and frozen state),
D-37 (its "D-31 superseded" claim corrected in D-52), `scripts/validate_repos.py`
(public + confidential hard gate), `scripts/check_declared_contexts.py` (the
Context Parity coupling).

## 6. Dry-run verification and the curated manifest (2026-10-07)

A read-only dry-run reproduced `git filter-repo --invert-paths --path` semantics
over full git history (scratch HTTPS clones; blob bodies never read; nothing
pushed; clones deleted). Both repos measured `visibility: public`, `forks_count 0`.

| Repo | distinct full-history paths | broad Step-5 prefixes would remove | collateral vs a narrow manifest |
|---|---|---|---|
| jolarca-compliance | 218 | 102 | 75 |
| jolarca-infrastructure | 334 | 54 | 50 |

Collateral shrinks once the borderline records below are added to the manifest;
the Step-5 dry-run gate re-measures it exactly before anything runs.

Curated `regulated-blobs.txt` (one path per line; trailing `/` = a directory).
Posture for a *public* repo holding regulated content: move anything that reveals
CDE topology, control weaknesses, key management, network policy, or per-subject
records; keep generic governance/transparency, READMEs, and empty skeletons.
**Every line is an operator-reviewable judgment call - adjust with reason, then
re-run the Step-5 dry-run gate.**

```text
# jolarca-compliance
ropa/master-register.csv
ropa/by-system/
dpia/001-identity-and-consent/dpia.md
dpia/002-ai-processing/dpia.md
dpia/003-payments-and-vat/dpia.md
dpia/004-geolocation-search/dpia.md
dpia/register.md
risk-register/register.md
vendor-assessments/anthropic/assessment.md
vendor-assessments/dpd/assessment.md
vendor-assessments/google-cloud/assessment.md
vendor-assessments/hetzner/assessment.md
vendor-assessments/letsencrypt/assessment.md
vendor-assessments/omniva/assessment.md
vendor-assessments/openai/assessment.md
vendor-assessments/proxmox/assessment.md
vendor-assessments/stripe/assessment.md
vendor-assessments/register.csv
vendor-assessments/register.md
data-subject-requests/register.md
incidents/register.md
lawful-basis/consent-versions.md
audits/internal/2026-08-step17-payment-boundary-audit/AUDIT_REPORT.md
audits/internal/2026-08-step22-payment-boundary-reaudit/AUDIT_REPORT.md
audits/internal/2026-08-step22c-payment-boundary-reaudit/AUDIT_REPORT.md
audits/gate-evidence/G3-payments/G3_DECISION.md
audits/gate-evidence/G3-payments/reports/
# jolarca-infrastructure
security/deviation-register.md
security/network-policy.md
security/pci-dss-scope.md
security/key-custody.md
STEP10_PAYMENT_BOUNDARY.md
docs/payment-api-contract.md
docs/payment-boundary-enforcement.md
docs/runbooks/vault-sealed.md
docs/runbooks/wireguard-key-rotation.md
docs/runbooks/state-compromise.md
docs/runbooks/postgres-failover.md
docs/adr/0005-single-payment-boundary.md
docs/adr/0006-redis-co-located-on-app-host.md
```

Borderline calls made here, each overridable by the operator with reason:
- **Moved** the compliance payment-boundary audit reports and `G3-payments` - same
  control-weakness class as the deviation register; leaving them while removing
  the register would be inconsistent.
- **Moved** infra `security/{network-policy,pci-dss-scope,key-custody}.md` and the
  live-credential / compromise runbooks (`vault-sealed`, `wireguard-key-rotation`,
  `state-compromise`, `postgres-failover`) - a public attacker playbook for the
  highest-value targets.
- **Moved** `docs/adr/0005`, `0006` (CDE topology: single payment boundary, redis
  co-location).
- **Kept** all other ADRs, `docs/architecture.md`, `docs/threat-model.md`,
  `security/{isolation-model,cis-baseline,access-review}.md` (procedures, not
  populated records), every `README.md`, `.gitkeep`, `.markdownlint.json`, and the
  generic `incidents/templates/*` and `lawful-basis/consent-text/*` skeletons. If
  any kept file turns out to hold org-specific values, move it too - decide by
  reading it during Step 2 staging, not from this list.

Landing this section runs nothing. **D-31 remains S1/BLOCKING/OPEN** until the
operator provisions and verifies the destination (Steps 0-3), then executes
Steps 4-7 with the Step-5 dry-run gate clean.
