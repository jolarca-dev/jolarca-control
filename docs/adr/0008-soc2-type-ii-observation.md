# ADR-0008: SOC 2 Type II Observation Window Decision

**Date:** 2026-09-28
**Status:** Proposed — requires owner decision
**Deciders:** Gintaras Kazlauskas (organization owner)

---

## Context

The jolarca-dev marketplace currently self-declares SOC 2 posture as "Aligned"
in various governance documents. An auditor treating "Aligned" as a claim to
test would require evidence that controls operated effectively over a period
of time (Type II), not just that they exist on paper (Type I).

The pre-deployment compliance checklist (B7) flags this:

> SOC2 posture is self-declared 'Aligned' — no Type II report period exists
> yet. Decide: pursue Type II observation window now (controls must operate
> effectively 3-12 months) or re-label honestly as 'In progress'. Auditors
> treat 'Aligned' as a claim to test.

## Options

### Option A: Begin Type II observation window now

- **What:** Declare the observation period start date (e.g., 2026-10-01).
  Controls must operate effectively for 3-12 months before a Type II report
  can be issued.
- **Pros:** The clock starts now. If the marketplace launches in 6 months,
  the Type II report could be ready at launch.
- **Cons:** Controls must actually operate for the entire period. Any gap
  (missed access review, lapsed exception, untested backup) breaks the
  observation window and resets the clock.

### Option B: Re-label as "In progress"

- **What:** Change all references from "Aligned" to "In progress" or
  "Type I only — controls designed, not yet tested for operating effectiveness."
- **Pros:** Honest. No risk of an auditor discovering a gap in a claimed
  observation period.
- **Cons:** Delays the Type II report. Marketplace launches without a
  Type II report, which some enterprise customers may require.

### Option C: Pursue Type I now, Type II later

- **What:** Engage an auditor for a Type I report (controls suitably designed
  as of a point in time). Begin Type II observation after Type I is issued.
- **Pros:** Type I is achievable now. Provides a report for enterprise
  customers. Type II observation starts with a clean baseline.
- **Cons:** Two audit engagements (cost). Type I alone does not prove
  operating effectiveness.

## Decision

**[OWNER DECISION REQUIRED]**

The organization owner must select one of the three options above. The
selection determines:
1. Whether "Aligned" claims in governance documents are accurate or must be
   changed.
2. Whether the observation period clock starts now or later.
3. The audit engagement timeline and budget.

## Consequences

- **If Option A:** Every control in policy/compliance-gates.yml must operate
  without gap for 3-12 months. The exceptions register must be reviewed
  quarterly without lapse. Access reviews must be executed on schedule.
  Backups must be taken and tested. Any lapse resets the clock.

- **If Option B:** All "Aligned" references change to "In progress." No
  audit engagement is needed now. The marketplace can still operate under
  self-attested controls, but enterprise customers requiring a SOC 2 report
  will need to wait.

- **If Option C:** Engage auditor for Type I within 30 days. Remediate any
  design deficiencies found. Begin Type II observation after Type I issuance.

---

## Professional Opinion

**Recommendation: Option C (Type I now, Type II later).**

Rationale: The control design is strong — the gates, policies, and exception
register are well-structured. But several controls are newly implemented
(compliance-scan.yml, first-commit pipeline, gitleaks config) and have not
yet operated for any meaningful period. A Type I report validates the design
now, identifies any design gaps, and provides a report for enterprise
customers. The Type II observation period should begin AFTER the control
suite has stabilised (estimated 2-3 months of steady-state operation).

Option A is risky because any lapse in the next 3-12 months (and there WILL
be lapses during the solo-era transition) would reset the clock. Option B
is honest but delays market access. Option C threads the needle: get the
design validated now, then prove it operates over time.
