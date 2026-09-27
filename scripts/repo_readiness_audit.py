#!/usr/bin/env python3
"""Pre-first-commit readiness gate for jolarca-dev fleet repositories.

jolarca-control — marketplace (jolarca-dev) governance control plane.

WHY THIS EXISTS
---------------
The fleet's other gates each answer a different question, and none of them
answers "may this repository receive its first real commit?":

  * scripts/validate_repos.py       — is repos/*.yml internally valid?   (offline)
  * scripts/compliance_check.py     — is the DECLARED config consistent?  (offline)
  * scripts/drift_detect.py         — does live GitHub match the allow-list? (live)
  * scripts/check_fleet_separation.sh — ADR-0004 R1/R2/R3 membership.     (live)
  * scripts/org_delivery_audit.sh   — capture delivery-chain evidence.    (live)

The gap is the moment BEFORE content exists. Seven of sixteen repositories are
empty on GitHub (size: 0) with their first commit sitting in a local clone. At
that instant drift_detect.py has nothing to compare, org_delivery_audit.sh has
no branch to read, and nothing at all inspects the local working copy — which is
where the D-28 failure class lives (an index holding .idea/ and a PyCharm
scaffold while every real file was untracked). This script closes that gap.

It answers four questions per repository, and emits a verdict:

  1. DECLARED  — is the repo in the allow-list, and is the entry complete?
  2. LOCAL     — is the working copy safe to commit and push? (remote, branch,
                 cleanliness, hooks, signing, governance files, CI, secrets)
  3. LIVE      — does the GitHub repository match the declaration and policy?
                 (visibility, settings, secret scanning, access, protection)
  4. ORG       — do org-level baselines hold? (2FA, default permission, plan)

Verdicts: READY · READY-WITH-FIXES · BLOCKED. "Probably fine" is not a verdict:
a check that could not be performed is reported as UNVERIFIABLE and blocks.

DESIGN CONSTRAINTS
------------------
  * Registry-driven. The fleet is read from repos/*.yml — NEVER a hardcoded
    list or count. org_delivery_audit.sh hardcodes 7 of 16 repositories and
    therefore silently under-audits the other nine; this script must not
    inherit that defect.
  * Policy-driven. Expected values come from policy/repo-defaults.yml and
    policy/compliance-gates.yml, so a documented deviation (D-04 zero reviews,
    D-05 unsigned automation commits) is reported as a TRACKED EXCEPTION rather
    than as a defect, and a policy change changes what this gate enforces.
  * Read-only. This script never writes to GitHub and never commits. It prints
    remediation commands; a human decides whether to run them.
  * Three-valued exit codes (the D-23 lesson): 0 ready, 1 findings, 2 could not
    verify. A control that cannot read its subject must never report success.

Exit codes
----------
  0  every audited repository is READY
  1  at least one repository is READY-WITH-FIXES or BLOCKED
  2  at least one check could not be verified (missing gh, auth failure, API error)

Usage
-----
  python3 scripts/repo_readiness_audit.py                     # whole allow-list
  python3 scripts/repo_readiness_audit.py --repo jolarca-payments
  python3 scripts/repo_readiness_audit.py --repo a --repo b --markdown /tmp/report.md
  python3 scripts/repo_readiness_audit.py --no-live           # offline: declared + local
  python3 scripts/repo_readiness_audit.py --output evidence.json

Environment
-----------
  JOLARCA_CONTROL_ORG   organization to audit           (default: jolarca-dev)
  JOLARCA_REPOS_ROOT    parent dir holding local clones (default: this repo's parent)
  GITHUB_TOKEN/GH_TOKEN passed through to gh
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

BASE_DIR = Path(__file__).resolve().parent.parent
REPOS_DIR = BASE_DIR / "repos"
POLICY_DEFAULTS = BASE_DIR / "policy" / "repo-defaults.yml"
POLICY_GATES = BASE_DIR / "policy" / "compliance-gates.yml"

ORG = os.environ.get("JOLARCA_CONTROL_ORG", "jolarca-dev")
# Derived from the control plane's own location rather than hardcoded, so the
# gate still works on another operator's checkout. Env override wins.
LOCAL_ROOT = Path(os.environ.get("JOLARCA_REPOS_ROOT", str(BASE_DIR.parent)))

# The community-health repo is declared in health-repo.tf, not in the allow-list.
HEALTH_REPO = ".github"

# Severity vocabulary matches docs/drift-findings.md exactly, so a finding here
# and a finding there are the same currency.
SEVERITIES = ("S0", "S1", "S2", "S3")
SEVERITY_MEANING = {
    "S0": "stop-work — do not commit, do not push",
    "S1": "fix before the first commit/push",
    "S2": "fix soon",
    "S3": "tracked hygiene / informational",
}
# A single S0 or S1 blocks. That is deliberate: the whole point of a pre-commit
# gate is that it cannot be talked past.
BLOCKING_SEVERITIES = frozenset({"S0", "S1"})

VERDICT_READY = "READY"
VERDICT_FIXES = "READY-WITH-FIXES"
VERDICT_BLOCKED = "BLOCKED"

_HTTP_RE = re.compile(r"HTTP\s+(\d{3})")

# Governance files every fleet repo must carry. CONTRIBUTING.md is graded one
# step lower than the rest: its absence weakens onboarding, not security.
REQUIRED_FILES_S1 = ("README.md", "SECURITY.md", ".gitignore")
REQUIRED_FILES_S2 = ("CONTRIBUTING.md",)
# CODEOWNERS is NOT at the repo root in this fleet (D-20) — check all three
# locations GitHub honours, or a root-only check reports a false absence.
CODEOWNERS_CANDIDATES = (".github/CODEOWNERS", "CODEOWNERS", "docs/CODEOWNERS")
WORKFLOW_DIR = Path(".github/workflows")

# ADR-0004 R4: no CODEOWNERS in a marketplace repo may name a mission-platform
# principal. This list MUST stay identical to drift_detect.check_codeowners()
# (`forbidden_orgs`), or the two gates contradict each other.
#
# There is deliberately NO bare "jol-" prefix here. The marketplace org is
# `jolarca-dev`, so prefix-matching "jol" flags every correctly-scoped
# CODEOWNERS entry as a cross-project violation — an earlier revision did exactly
# that and reported 6 of 15 repos as breaching ADR-0004 R4 when none were.
# Match the org segment of `org/team` for equality instead.
FORBIDDEN_CODEOWNERS_ORGS = frozenset({"journeyoflife-org", "jol-infrastructure"})

# Paths that must never be tracked. D-28 is the precedent: .idea/ and a
# PyCharm main.py scaffold were the ONLY things in the index, and every real
# file was untracked, so the bootstrap commit would have shipped IDE metadata
# and none of the control plane.
FORBIDDEN_TRACKED_PATTERNS = (
    r"(^|/)\.idea/",
    r"(^|/)\.venv/",
    r"(^|/)__pycache__/",
    r"\.tfstate(\.|$)",
    r"(^|/)\.env(\.|$)",
    r"\.pem$",
    r"\.p12$",
    r"(^|/)credentials\.json$",
    r"(^|/)secrets\.json$",
)

# Committed-by-design templates that happen to match a forbidden pattern. Graded
# S3 (confirm the contents are placeholders) rather than S1, so the gate does not
# block a repository for following normal practice.
TEMPLATE_SUFFIXES = (".example", ".sample", ".template", ".dist")

# High-signal secret patterns only. Deliberately narrow: a broad "password="
# heuristic floods the report with false positives, and an auditor who learns
# to ignore the secret check has lost the one check that matters. gitleaks
# remains the authoritative scanner and is used when installed.
BUILTIN_SECRET_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"AKIA[0-9A-Z]{16}", "AWS access key ID"),
    (r"gh[pousr]_[A-Za-z0-9]{36,}", "GitHub token (classic)"),
    (r"github_pat_[A-Za-z0-9_]{22,}", "GitHub fine-grained PAT"),
    (r"sk_live_[0-9a-zA-Z]{24,}", "Stripe live secret key"),
    (r"xox[baprs]-[0-9A-Za-z-]{10,}", "Slack token"),
    (r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----", "private key block"),
)


@dataclass(frozen=True)
class Finding:
    """One numbered audit finding.

    `status` keeps the VERIFIED / ASSUMED distinction the audit brief demands:
    a finding backed by evidence read in this run is VERIFIED; a check that
    could not be performed is UNVERIFIABLE and is never reported as clean.
    """

    fid: str
    severity: str
    category: str
    summary: str
    evidence: str
    remediation: str
    status: str = "VERIFIED"


@dataclass
class RepoReport:
    """Aggregated result for one repository."""

    repo: str
    verdict: str = VERDICT_READY
    findings: list[Finding] = field(default_factory=list)
    facts: dict[str, Any] = field(default_factory=dict)
    unverified: list[str] = field(default_factory=list)
    local_path: str | None = None

    def add(self, finding: Finding) -> None:
        self.findings.append(finding)

    def note_unverified(self, check: str, reason: str) -> None:
        self.unverified.append(f"{check}: {reason}")

    def blocking(self) -> list[Finding]:
        return [f for f in self.findings if f.severity in BLOCKING_SEVERITIES]

    def decide(self) -> None:
        """Set the verdict from the findings actually collected."""
        if self.unverified or any(f.severity in ("S0", "S1") for f in self.findings):
            self.verdict = VERDICT_BLOCKED
        elif self.findings:
            self.verdict = VERDICT_FIXES
        else:
            self.verdict = VERDICT_READY


# ── External command helpers ─────────────────────────────────────────────────


def run_cmd(cmd: list[str], cwd: Path | None = None) -> tuple[int, str, str]:
    """Run a command, never raising. (rc, stdout, stderr); rc=127 if unavailable."""
    try:
        proc = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, check=False, timeout=180
        )
    except FileNotFoundError as exc:
        return 127, "", f"command not found: {exc.filename}"
    except subprocess.TimeoutExpired:
        return 124, "", f"timed out: {' '.join(cmd)}"
    return proc.returncode, proc.stdout, proc.stderr


def gh_api(path: str) -> tuple[int, Any]:
    """Call the REST API via gh. Returns (http_status, parsed_body).

    Status 0 means the call could not be classified — callers must treat that
    as UNVERIFIABLE, never as "no finding" (D-23).
    """
    code, out, err = run_cmd(["gh", "api", path])
    if code == 127:
        return 0, {"error": "gh CLI not found"}
    if code == 0:
        try:
            return 200, json.loads(out or "null")
        except json.JSONDecodeError as exc:
            return 0, {"error": f"unparseable JSON: {exc}"}
    match = _HTTP_RE.search(err)
    status = int(match.group(1)) if match else 0
    return status, {"error": err.strip()[:400]}


def git(repo: Path, *args: str) -> tuple[int, str, str]:
    return run_cmd(["git", *args], cwd=repo)


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    with open(path, encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    return data if isinstance(data, dict) else {}


def get_defined_repos() -> dict[str, dict[str, Any]]:
    """The allow-list: repos/*.yml keyed by the declared `name` field."""
    defined: dict[str, dict[str, Any]] = {}
    for yml_file in sorted(REPOS_DIR.glob("*.yml")):
        data = load_yaml(yml_file)
        name = data.get("name")
        if isinstance(name, str) and name:
            defined[name] = data
    return defined


def secret_patterns(gates: dict[str, Any]) -> list[tuple[str, str]]:
    """Policy custom patterns first, then the built-in high-signal set.

    Read from policy/compliance-gates.yml#gates.secret_scan so the gate and the
    policy cannot disagree about what counts as a secret.
    """
    impl = ((gates.get("gates") or {}).get("secret_scan") or {}).get("implementation") or {}
    patterns: list[tuple[str, str]] = []
    for entry in impl.get("custom_patterns") or []:
        if isinstance(entry, dict) and entry.get("pattern"):
            patterns.append(
                (str(entry["pattern"]), str(entry.get("description", "policy pattern")))
            )
    patterns.extend(BUILTIN_SECRET_PATTERNS)
    return patterns


# ── Local working-copy checks ────────────────────────────────────────────────


def check_local(
    report: RepoReport, declared: dict[str, Any], patterns: list[tuple[str, str]]
) -> None:
    """Everything that can be wrong with the clone before it is ever pushed."""
    path = report.local_path
    if path is None:
        repo_dir = LOCAL_ROOT / report.repo
        path = str(repo_dir) if repo_dir.is_dir() else None
        report.local_path = path
    if path is None:
        report.add(
            Finding(
                "L-01",
                "S1",
                "local",
                "no local clone found — first-commit hygiene cannot be verified",
                f"expected a working copy at {LOCAL_ROOT / report.repo}; directory absent.",
                f"git clone git@github.com:{ORG}/{report.repo}.git {LOCAL_ROOT / report.repo}",
                "UNVERIFIABLE",
            )
        )
        report.note_unverified("local working copy", "clone not present under JOLARCA_REPOS_ROOT")
        return

    root = Path(path)
    rc, _, _ = git(root, "rev-parse", "--git-dir")
    if rc != 0:
        report.add(
            Finding(
                "L-02",
                "S1",
                "local",
                "directory is not a git repository",
                f"{root} exists but `git rev-parse --git-dir` failed.",
                f"cd {root} && git init -b main",
            )
        )
        report.note_unverified("git state", "not a git repository")
        return

    report.facts["local_path"] = str(root)

    # ── L-03 / L-04: remote identity. Pushing to the wrong destination is the
    # single most destructive mistake available at first-commit time, so an
    # absent remote and a WRONG remote are graded differently.
    rc, out, _ = git(root, "remote", "get-url", "origin")
    has_origin = rc == 0
    if rc != 0:
        report.add(
            Finding(
                "L-03",
                "S1",
                "local",
                "no `origin` remote configured — push has no destination",
                "`git remote get-url origin` failed; the clone is detached from GitHub. "
                "Commits made here are invisible to every live control (protection, "
                "scanning, CI) until a remote exists.",
                f"cd {root} && git remote add origin git@github.com:{ORG}/{report.repo}.git",
            )
        )
    else:
        url = out.strip()
        report.facts["remote_origin"] = url
        expected = re.compile(rf"[:/]({re.escape(ORG)})/({re.escape(report.repo)})(?:\.git)?$")
        if not expected.search(url):
            report.add(
                Finding(
                    "L-04",
                    "S0",
                    "local",
                    "origin points somewhere other than the audited repository",
                    f"origin is `{url}`; expected a URL ending {ORG}/{report.repo}. "
                    "A push here lands in a DIFFERENT repository — possibly a "
                    "mission-platform (jol-*) repo, breaching ADR-0004 R4.",
                    f"cd {root} && git remote set-url origin git@github.com:{ORG}/{report.repo}.git",
                )
            )

    # ── L-05: branch and cleanliness
    rc, out, _ = git(root, "rev-parse", "--abbrev-ref", "HEAD")
    branch = out.strip() if rc == 0 else "?"
    report.facts["local_branch"] = branch

    rc, out, _ = git(root, "status", "--porcelain")
    dirty = [line for line in out.splitlines() if line.strip()]
    report.facts["dirty_entries"] = len(dirty)
    if dirty:
        preview = ", ".join(d.strip()[:60] for d in dirty[:5])
        report.add(
            Finding(
                "L-05",
                "S2",
                "local",
                "working tree is not clean",
                f"{len(dirty)} uncommitted/untracked entr(ies): {preview}"
                + (" ..." if len(dirty) > 5 else ""),
                f"cd {root} && git status   # then commit deliberately or gitignore",
            )
        )

    # ── L-06: forbidden paths in the index (D-28 class)
    rc, out, _ = git(root, "ls-files")
    tracked = [line for line in out.splitlines() if line.strip()]
    report.facts["tracked_files"] = len(tracked)
    offenders = sorted(
        {t for t in tracked for pat in FORBIDDEN_TRACKED_PATTERNS if re.search(pat, t)}
    )
    # `.env.example` and friends are deliberate, committed templates: the
    # flagship ships three of them carrying `CHANGE_ME` placeholders and
    # "NEVER commit real values" headers. Calling those stop-work secrets would
    # block a repository for following good practice — and an operator who
    # learns the secret check cries wolf stops reading it. They are reported at
    # S3 for content confirmation instead. Note the tension this exposes:
    # policy/repo-defaults.yml lists `.env.*` as a mandatory gitignore pattern,
    # which read literally would ignore `.env.example` too.
    hard = [o for o in offenders if not o.endswith(TEMPLATE_SUFFIXES)]
    templates = [o for o in offenders if o.endswith(TEMPLATE_SUFFIXES)]
    report.facts["forbidden_tracked_hard"] = hard
    report.facts["forbidden_tracked_templates"] = templates
    if hard:
        report.add(
            Finding(
                "L-06a",
                "S1",
                "local",
                "policy-forbidden paths are TRACKED in git",
                f"{len(hard)} tracked path(s) match forbidden patterns: "
                f"{', '.join(hard[:8])}. Precedent D-28: the index held only "
                ".idea/ and a PyCharm scaffold while every real file was untracked.",
                f"cd {root} && git rm -r --cached {hard[0]}   # then extend .gitignore",
            )
        )
    if templates:
        report.add(
            Finding(
                "L-06b",
                "S3",
                "local",
                "tracked env TEMPLATE file(s) — confirm they hold no real values",
                f"{len(templates)} template(s) tracked: {', '.join(templates[:8])}. These "
                "are normally committed on purpose and are not secrets, but "
                "policy/repo-defaults.yml#data_handling lists `.env.*` as a mandatory "
                "gitignore pattern, which read literally would exclude them. Open each "
                "one, confirm every value is a placeholder, and record the owner "
                "decision on whether the policy pattern should be narrowed to exclude "
                "`.env.example`.",
                f"cd {root} && cat {templates[0]}   # every value must be a placeholder",
            )
        )

    # ── L-18: clone freshness. `origin/<branch>` is a LOCAL remote-tracking ref
    # that only moves on fetch, so comparing against it proves nothing — this
    # audit measured +0/-0 "in sync" on three clones that were in fact stale.
    # Ask the remote for its real head instead. This is how a remediated file
    # gets resurrected: jolarca-compliance's live tree has NO .github/CODEOWNERS,
    # yet the clone still carries the pre-D-20 version naming mission-org teams,
    # and committing it would re-introduce an ADR-0004 R4 violation that the
    # findings register records as fixed.
    ls_rc2, ls_out, ls_err2 = git(root, "ls-remote", "origin", f"refs/heads/{branch}")
    remote_head = ls_out.split("\t")[0].strip() if ls_out.strip() else ""
    head_rc, head_out, _ = git(root, "rev-parse", branch)
    local_head = head_out.strip() if head_rc == 0 else ""
    report.facts["remote_head"] = remote_head or None
    report.facts["local_head"] = local_head or None
    report.facts["remote_branch_exists"] = bool(remote_head)
    # Without an origin remote L-03 already blocks the repo, and `ls-remote`
    # cannot succeed — recording that as an independent verification gap would
    # double-count a consequence as a second problem.
    if has_origin and ls_rc2 != 0:
        report.note_unverified(
            "clone freshness", f"`git ls-remote` exited {ls_rc2}: {ls_err2.strip()[:120]}"
        )
    elif has_origin and remote_head and local_head and remote_head != local_head:
        reason: str | None
        if git(root, "cat-file", "-e", f"{remote_head}^{{commit}}")[0] != 0:
            reason = (
                "the local object store does not even contain the remote head — this "
                "clone has never fetched it"
            )
        elif git(root, "merge-base", "--is-ancestor", remote_head, branch)[0] == 0:
            # Remote head is an ancestor of local: the clone is simply AHEAD,
            # which is the normal pre-push state and not a finding.
            reason = None
        else:
            reason = (
                "the remote head is not an ancestor of the local branch — the two have diverged"
            )
        if reason:
            report.add(
                Finding(
                    "L-18",
                    "S1",
                    "local",
                    "local clone is STALE — it does not reflect the live repository",
                    f"local {branch}={local_head[:12]} but the remote's {branch}="
                    f"{remote_head[:12]}; {reason}. Committing on top of a stale clone "
                    "silently reverts whatever changed live and can resurrect files that "
                    "were deliberately deleted during remediation.",
                    f"cd {root} && git fetch origin && git log --oneline {branch}..origin/{branch}"
                    f"   # then rebase before committing anything",
                )
            )

    # ── L-07: pre-commit hook installed
    hook = root / ".git" / "hooks" / "pre-commit"
    report.facts["pre_commit_hook"] = hook.is_file()
    if not hook.is_file():
        report.add(
            Finding(
                "L-07",
                "S1",
                "local",
                "pre-commit hook is not installed",
                f"{hook} does not exist, so lint/secret/branch hooks declared in "
                ".pre-commit-config.yaml will NOT run before a commit.",
                f"cd {root} && pre-commit install",
            )
        )

    # ── L-08: commit signing (D-05 compensating control)
    rc, out, _ = git(root, "config", "--get", "commit.gpgsign")
    signed = out.strip().lower() == "true"
    report.facts["commit_gpgsign"] = signed
    if not signed:
        report.add(
            Finding(
                "L-08",
                "S2",
                "local",
                "commit.gpgsign is not enabled",
                "policy/repo-defaults.yml#commit_signing_policy requires signed commits "
                "for human operators. GitHub-side enforcement is OFF (deviation D-05), so "
                "local signing is the ONLY attribution control that exists.",
                f"cd {root} && git config commit.gpgsign true",
            )
        )

    check_required_files(report, root)
    check_codeowners(report, root)
    check_ci_workflow(report, root, declared)
    check_license(report, root, declared)
    check_gitignore(report, root)
    check_secrets_local(report, root, patterns)


def check_required_files(report: RepoReport, root: Path) -> None:
    """L-09: the governance files the audit brief requires, graded by impact."""
    missing_s1 = [f for f in REQUIRED_FILES_S1 if not (root / f).is_file()]
    missing_s2 = [f for f in REQUIRED_FILES_S2 if not (root / f).is_file()]
    report.facts["missing_required_files"] = missing_s1 + missing_s2
    if missing_s1:
        report.add(
            Finding(
                "L-09a",
                "S1",
                "local",
                "required governance file(s) missing",
                f"absent from {root}: {', '.join(missing_s1)}. SECURITY.md is the "
                "vulnerability-disclosure path (ISO 27001 A.5.24); .gitignore is the "
                "control that keeps secrets and state out of history.",
                f"cd {root} && cp ../jolarca-control/files/SECURITY.md . "
                f"# author the rest; do not paste placeholders",
            )
        )
    if missing_s2:
        report.add(
            Finding(
                "L-09b",
                "S2",
                "local",
                "onboarding file(s) missing",
                f"absent from {root}: {', '.join(missing_s2)}.",
                f"cd {root} && $EDITOR {missing_s2[0]}",
            )
        )


def check_codeowners(report: RepoReport, root: Path) -> None:
    """L-10 / L-11: CODEOWNERS presence and ADR-0004 R4 cross-project leakage."""
    found = next((c for c in CODEOWNERS_CANDIDATES if (root / c).is_file()), None)
    report.facts["codeowners"] = found
    if found is None:
        report.add(
            Finding(
                "L-10",
                "S1",
                "local",
                "no CODEOWNERS file",
                f"none of {', '.join(CODEOWNERS_CANDIDATES)} exists in {root}. "
                "require_code_owner_reviews has nothing to resolve against (D-20).",
                f"cd {root} && mkdir -p .github && "
                f"printf '* @JourneyOfLife\\n' > .github/CODEOWNERS",
            )
        )
        return
    text = (root / found).read_text(encoding="utf-8", errors="replace")
    refs = sorted(set(re.findall(r"@([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)", text)))
    report.facts["codeowners_team_refs"] = refs
    bad = sorted(r for r in refs if r.split("/", 1)[0] in FORBIDDEN_CODEOWNERS_ORGS)
    if bad:
        report.add(
            Finding(
                "L-11",
                "S1",
                "local",
                "CODEOWNERS references mission-platform principals (ADR-0004 R4)",
                f"{found} names {', '.join(bad)}. GitHub cannot grant review rights "
                "across organizations, so the rule is inert AND breaches the "
                "mission/marketplace separation. Precedent: D-20 / D-32.",
                f"cd {root} && sed -i 's|@[^ ]*/|@JourneyOfLife #|' {found}  # then review by hand",
            )
        )


def check_ci_workflow(report: RepoReport, root: Path, declared: dict[str, Any]) -> None:
    """L-12: a declared required status check with no workflow can never report.

    This is the D-22/D-27 failure class — a gate that exists in configuration
    and never fires. repos/*.yml declares required_status_checks.contexts; if no
    workflow exists, those contexts are unsatisfiable and branch protection
    would block every merge forever (or, on this plan, protect nothing at all).
    """
    contexts = (
        ((declared.get("branch_protection") or {}).get("main") or {}).get("required_status_checks")
        or {}
    ).get("contexts") or []
    workflows = (
        sorted(p.name for p in (root / WORKFLOW_DIR).glob("*.y*ml"))
        if (root / WORKFLOW_DIR).is_dir()
        else []
    )
    report.facts["required_contexts"] = list(contexts)
    report.facts["workflows"] = workflows
    if contexts and not workflows:
        report.add(
            Finding(
                "L-12",
                "S1",
                "local",
                "registry requires status checks but the repo has NO CI workflow",
                f"repos/{report.repo}.yml declares required contexts {list(contexts)}; "
                f"{WORKFLOW_DIR}/ is {'absent' if not (root / WORKFLOW_DIR).is_dir() else 'empty'}. "
                "Those checks can never report, so the protection rule they gate on "
                "is unsatisfiable — a control present in config that never fires (D-22, D-27).",
                f"cd {root} && mkdir -p {WORKFLOW_DIR} && $EDITOR {WORKFLOW_DIR}/ci.yml",
            )
        )


def check_license(report: RepoReport, root: Path, declared: dict[str, Any]) -> None:
    """L-13: license coherence with POLICY, not with a generic assumption.

    policy/repo-defaults.yml sets `license: null` on purpose: only the flagship
    `jolarca` carries one (AGPL-3.0, deliberate — repos/jolarca.yml
    `license_template: agpl-3.0`). compliance-gates.yml#license_check.scope_note
    restricts that gate to INBOUND DEPENDENCIES and explicitly warns against
    "remediating" an AGPL finding on jolarca's own LICENSE. So AGPL here is
    never reported as a violation.
    """
    has_license = (root / "LICENSE").is_file() or (root / "LICENSE.md").is_file()
    # `license_template` is declared under `settings` in this fleet's registry
    # (verified: repos/jolarca.yml), not at the top level. Reading the wrong
    # nesting made every repo look license-less and produced a false positive on
    # the flagship — the exact mistake compliance-gates.yml#license_check
    # scope_note warns against.
    reg_settings = declared.get("settings") or {}
    template = reg_settings.get("license_template") or declared.get("license_template")
    report.facts["has_license_file"] = has_license
    report.facts["license_template"] = template
    if template and not has_license:
        report.add(
            Finding(
                "L-13a",
                "S2",
                "local",
                "registry declares a license template but no LICENSE file exists",
                f"repos/{report.repo}.yml declares license_template: {template}; "
                f"{root} has no LICENSE.",
                f"cd {root} && $EDITOR LICENSE   # {template}",
            )
        )
    if not template and has_license:
        report.add(
            Finding(
                "L-13b",
                "S3",
                "local",
                "LICENSE present although policy declares none for this repo",
                f"{root} has a LICENSE file, but repos/{report.repo}.yml declares no "
                "license_template and policy/repo-defaults.yml sets license: null. "
                "Confirm the license is intended and record it in the registry.",
                f"cd {root} && head -3 LICENSE   # then add license_template to repos/{report.repo}.yml",
            )
        )
    if not template and not has_license and declared.get("visibility") == "public":
        report.add(
            Finding(
                "L-13c",
                "S3",
                "local",
                "public repository with no explicit license",
                f"{report.repo} is declared public and carries no LICENSE, so default "
                "copyright (all rights reserved) applies. That is the safe proprietary "
                "posture, but it is IMPLICIT. Policy intentionally declares license: null "
                "for governance repos — confirm that intent rather than assuming it.",
                "No action if the all-rights-reserved default is intended; otherwise add "
                f"license_template to repos/{report.repo}.yml and a LICENSE file.",
            )
        )


def check_gitignore(report: RepoReport, root: Path) -> None:
    """L-14: the policy's mandatory ignore patterns must actually be present."""
    gi = root / ".gitignore"
    if not gi.is_file():
        return  # already reported by L-09a; do not double-count
    text = gi.read_text(encoding="utf-8", errors="replace")
    policy = load_yaml(POLICY_DEFAULTS)
    wanted = [
        str(p) for p in (policy.get("data_handling") or {}).get("required_gitignore_patterns") or []
    ]
    missing: list[str] = []
    for pattern in wanted:
        needle = pattern.rstrip("/").lstrip("*")
        if needle and needle not in text:
            missing.append(pattern)
    report.facts["gitignore_missing_patterns"] = missing
    if missing:
        report.add(
            Finding(
                "L-14",
                "S2",
                "local",
                ".gitignore is missing policy-mandated patterns",
                f"policy/repo-defaults.yml#data_handling.required_gitignore_patterns "
                f"demands {missing}; .gitignore does not cover them. These are exactly "
                "the keys, certs and Terraform state files that must never be committed.",
                f"cd {root} && printf '%s\\n' {' '.join(repr(m) for m in missing)} >> .gitignore",
            )
        )


def _redact(token: str) -> str:
    """Never write a full credential into an evidence artifact.

    This report is meant to be committed as audit evidence, so echoing the
    matched value would turn the finding itself into the leak it reports.
    """
    prefix = token[:8] if len(token) > 8 else token[:2]
    return f"{prefix}...[redacted {len(token)} chars]"


def run_gitleaks(report: RepoReport, root: Path) -> bool | None:
    """True if gitleaks found leaks, False if it ran clean, None if it could not run.

    gitleaks is the authoritative scanner: it weighs entropy, keywords and
    known example fixtures. A bare regex cannot, so its hits are treated as
    SIGNALS to be corroborated, not as verdicts.
    """
    if run_cmd(["gitleaks", "version"])[0] != 0:
        report.facts["gitleaks_exit"] = None
        report.note_unverified(
            "gitleaks", "not installed — the regex sweep below is UNCORROBORATED"
        )
        return None
    code, out, err = run_cmd(["gitleaks", "git", str(root), "--no-banner", "--redact"])
    report.facts["gitleaks_exit"] = code
    if code == 0:
        return False
    if code == 1:
        report.add(
            Finding(
                "L-17",
                "S0",
                "secrets",
                "gitleaks reported leaks — STOP AND ROTATE",
                f"`gitleaks git {root}` exited 1 (leaks found). Its output is redacted "
                "by the tool; re-run locally to see the exact locations.",
                f"cd {root} && gitleaks git . --no-banner   # then rotate every finding",
            )
        )
        return True
    report.note_unverified("gitleaks", f"exit {code}: {(err or out).strip()[:200]}")
    return None


def _secret_finding(
    fid: str, where: str, hits: list[str], corroborated: bool | None, root: Path
) -> Finding:
    """Grade a regex hit by whether the authoritative scanner agrees.

    Both failure directions are expensive. A false S0 sends an operator to
    rotate a credential that does not exist and trains them to ignore the
    secret check; a false clean ships a real key to a public packfile. So an
    uncorroborated hit blocks, a confirmed hit blocks, and only "gitleaks ran
    and found nothing" downgrades to mandatory human triage.
    """
    preview = ", ".join(hits[:6]) + (" ..." if len(hits) > 6 else "")
    if corroborated is None:
        severity = "S0"
        stance = (
            "gitleaks could not run, so this regex hit is UNCORROBORATED — treat it as "
            "a live credential until a human confirms otherwise."
        )
    elif corroborated:
        severity = "S0"
        stance = "gitleaks independently confirms the leak."
    else:
        severity = "S2"
        stance = (
            "gitleaks ran and reported NO leak, so this is a regex-only match requiring "
            "human triage. The known benign class is a documented test fixture: "
            "jolarca-compliance's initial-build audit embeds a deliberately planted "
            "dummy AWS key to prove gitleaks fires, and a regex cannot tell that from "
            "a real credential. Read the line and record the decision — do not rotate "
            "a key that does not exist, and do not clear this without looking."
        )
    rotate = (
        "1) rotate the credential at its issuer (it is compromised even if brand new); "
        "2) docs/runbooks/github-token-rotation.md; "
        f"3) cd {root} && git rm --cached <file> and gitignore it; "
        "4) purge history with git-filter-repo or BFG; "
        "5) record the incident in jolarca-compliance."
    )
    triage = (
        f"cd {root} && grep -rn '<redacted-prefix>' .   # open each match, confirm it is "
        "a fixture or a placeholder, then record the triage decision and the date in "
        "docs/drift-findings.md so the next auditor does not repeat this work."
    )
    return Finding(
        fid,
        severity,
        "secrets",
        f"secret-pattern match in {where}" + ("" if severity == "S2" else " — STOP AND ROTATE"),
        f"{len(hits)} match(es): {preview}. {stance}",
        rotate if severity == "S0" else triage,
    )


def check_secrets_local(report: RepoReport, root: Path, patterns: list[tuple[str, str]]) -> None:
    """L-15 / L-16: sweep tracked content AND history. Trust nothing.

    The brief is explicit that a secret in a brand-new repo "should be
    impossible" — verify anyway. History is scanned because a secret removed
    from HEAD is still in the packfile, still leaked, and still needs rotation.
    """
    corroborated = run_gitleaks(report, root)
    compiled = [(re.compile(p), d) for p, d in patterns]

    hits_head: list[str] = []
    ls_rc, out, ls_err = git(root, "ls-files")
    if ls_rc != 0:
        # Never treat an unreadable index as "no secrets" (the D-23 lesson).
        report.note_unverified(
            "secret HEAD sweep", f"`git ls-files` exited {ls_rc}: {ls_err.strip()[:120]}"
        )
    for rel in (line for line in out.splitlines() if line.strip()):
        target = root / rel
        if not target.is_file() or target.stat().st_size > 2_000_000:
            continue
        try:
            text = target.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            for rx, desc in compiled:
                for match in rx.finditer(line):
                    hits_head.append(f"{rel}:{lineno} {desc} [{_redact(match.group(0))}]")
    report.facts["secret_hits_head"] = hits_head
    if hits_head:
        report.add(_secret_finding("L-15", "tracked files", hits_head, corroborated, root))

    history_hits: list[str] = []
    hist_rc, hist_out, hist_err = git(root, "log", "--all", "-p", "--no-color")
    if hist_rc == 0 and hist_out:
        for rx, desc in compiled:
            for match in rx.finditer(hist_out):
                history_hits.append(f"{desc} [{_redact(match.group(0))}]")
                break  # one instance per pattern is enough to require triage
    report.facts["secret_hits_history"] = history_hits
    if history_hits:
        report.add(_secret_finding("L-16", "git history", history_hits, corroborated, root))
    if hist_rc != 0:
        report.note_unverified(
            "secret history sweep",
            f"`git log --all -p` exited {hist_rc}: {hist_err.strip()[:120] or 'no stderr'}",
        )


# ── Live GitHub checks ───────────────────────────────────────────────────────

# Registry `settings` key -> live REST payload field. Anything in this map is
# compared declared-vs-live; a mismatch is drift the control plane cannot yet
# apply (apply is blocked by the state migration), so it is reported, not fixed.
LIVE_SETTINGS_MAP = {
    "has_issues": "has_issues",
    "has_wiki": "has_wiki",
    "has_projects": "has_projects",
    "delete_branch_on_merge": "delete_branch_on_merge",
    "allow_merge_commit": "allow_merge_commit",
    "allow_squash_merge": "allow_squash_merge",
    "allow_rebase_merge": "allow_rebase_merge",
    "archived": "archived",
    "is_template": "is_template",
    "web_commit_signoff_required": "web_commit_signoff_required",
}

# Security features read from the repo payload's security_and_analysis block.
SECURITY_FEATURES = (
    ("secret_scanning", "S1"),
    ("secret_scanning_push_protection", "S1"),
    ("dependabot_security_updates", "S2"),
)

# Per-feature impact, so a Dependabot finding never inherits the secret-scanning
# rationale. A finding that explains the wrong risk is worse than one that
# explains nothing, because it gets acted on for the wrong reason.
SECURITY_FEATURE_RATIONALE = {
    "secret_scanning": (
        "Without secret scanning a credential committed here is never detected. On a "
        "PUBLIC repository it is harvested by automated bots within minutes of the push."
    ),
    "secret_scanning_push_protection": (
        "Without push protection the FIRST COMMIT can carry a secret straight into the "
        "packfile with nothing to stop it, and removing it afterwards requires a history "
        "rewrite plus rotation of a value that must already be assumed public."
    ),
    "dependabot_security_updates": (
        "Without automated security updates a vulnerable dependency waits for a human to "
        "notice it (ISO 27001 A.8.8 / PCI-DSS 6.3.3)."
    ),
}

PLAN_TIER_HINT = (
    "jolarca-dev is on the GitHub Free plan: this control is unavailable for "
    "PRIVATE repositories and requires Team/Advanced Security. Recorded as "
    "`blocked_by: plan tier` (the D-07 / D-33 pattern) — it cannot be closed by "
    "configuration alone and must not be silently downgraded to a warning."
)


def compute_settings_drift(
    settings: dict[str, Any], defaults: dict[str, Any], meta: dict[str, Any]
) -> list[tuple[str, Any, Any]]:
    """Pure: (live_field, declared_value, live_value) for every mismatch.

    The per-repo registry entry takes precedence over the fleet-wide defaults in
    policy/repo-defaults.yml. Fields absent from the live payload are skipped
    rather than guessed at.
    """
    pairs: list[tuple[str, Any, Any]] = []
    for key, live_key in LIVE_SETTINGS_MAP.items():
        want = settings[key] if key in settings else defaults.get(key)
        if want is None or live_key not in meta:
            continue
        have = meta.get(live_key)
        if bool(want) != bool(have):
            pairs.append((live_key, want, have))
    return pairs


def describe_drift(pairs: list[tuple[str, Any, Any]]) -> str:
    """Human-readable form of a drift set."""
    return "; ".join(
        f"{live_field}: declared={want} live={have}" for live_field, want, have in pairs
    )


def drift_patch_command(repo: str, pairs: list[tuple[str, Any, Any]]) -> str:
    """The PATCH that moves live state to the DECLARED value — never the reverse.

    This exists as a named, testable unit because the first implementation built
    these flags by parsing describe_drift()'s own output and picked up the LIVE
    value instead of the DECLARED one, so the printed "remediation" re-applied
    the drift it had just reported. tests/test_repo_readiness_audit.py pins the
    direction. D-22 is the precedent: an untested generated command is a
    hypothesis, not a control.
    """
    flags = " ".join(
        f"-F {live_field}={'true' if bool(want) else 'false'}" for live_field, want, _ in pairs
    )
    return f"gh api repos/{ORG}/{repo} -X PATCH {flags}"


def security_feature_command(repo: str, feature: str) -> str:
    """PATCH enabling one security_and_analysis feature.

    Built with json.dumps rather than hand-escaped braces: a malformed payload
    fails at the moment a junior operator pastes it, which is the worst possible
    time to discover the tool that produced it was wrong.
    """
    payload = json.dumps({"security_and_analysis": {feature: {"status": "enabled"}}})
    return f"gh api repos/{ORG}/{repo} -X PATCH --input - <<<'{payload}'"


def check_live(report: RepoReport, declared: dict[str, Any], policy: dict[str, Any]) -> None:
    """Compare the live GitHub repository against the declaration and policy."""
    status, meta = gh_api(f"repos/{ORG}/{report.repo}")
    if status == 404:
        report.add(
            Finding(
                "G-01",
                "S0",
                "live",
                "allow-list repository does not exist in the org",
                f"GET repos/{ORG}/{report.repo} -> HTTP 404. A declared repo missing "
                "from the org is a possible deletion, not a bootstrap convenience "
                "(check_fleet_separation.sh check 4).",
                f"gh api orgs/{ORG}/repos -X POST -f name={report.repo} -F private="
                f"{'true' if declared.get('visibility') == 'private' else 'false'}"
                "   # or run the state-migration runbook step that creates it",
            )
        )
        return
    if status != 200:
        report.add(
            Finding(
                "G-02",
                "S1",
                "live",
                "live repository state could not be read",
                f"GET repos/{ORG}/{report.repo} -> HTTP {status}: "
                f"{str(meta.get('error', ''))[:200]}",
                "gh auth status   # confirm the token has `repo` + `admin:org` scope",
                "UNVERIFIABLE",
            )
        )
        report.note_unverified("live repository", f"HTTP {status}")
        return

    defaults = policy.get("repository_defaults") or {}
    settings = declared.get("settings") or {}
    report.facts["live_visibility"] = meta.get("visibility")
    report.facts["live_size"] = meta.get("size")
    report.facts["live_default_branch"] = meta.get("default_branch")
    report.facts["live_license"] = (meta.get("license") or {}).get("spdx_id")

    # ── G-03: visibility coherence (how D-01 was found)
    want_vis = str(declared.get("visibility", ""))
    have_vis = "private" if meta.get("private") else "public"
    if want_vis and want_vis != have_vis:
        exposure = "high" if want_vis == "private" and have_vis == "public" else "low"
        # The impact sentence must match the DIRECTION of the drift. Claiming
        # "regulated content is world-readable" about a repo that is live
        # PRIVATE and merely mis-declared would be a false statement in an
        # audit artifact — the kind of overclaim D-30 exists to prevent.
        impact = (
            "Regulated content is world-readable right now (precedent: D-01 / D-31)."
            if exposure == "high"
            else "Live is MORE restrictive than declared, so nothing is exposed; the "
            "registry entry is simply wrong, and an auditor scoping work from it "
            "would be misled about where the regulated content lives."
        )
        report.add(
            Finding(
                "G-03",
                "S1" if exposure == "high" else "S2",
                "live",
                f"visibility drift ({exposure} exposure)",
                f"repos/{report.repo}.yml declares `{want_vis}`; live is `{have_vis}`. {impact}",
                f"gh api repos/{ORG}/{report.repo} -X PATCH -F private="
                f"{'true' if want_vis == 'private' else 'false'}"
                "   # NOTE apply.yml refuses visibility-changing plans: run deliberately",
            )
        )

    # ── G-04: per-setting drift
    drift_pairs = compute_settings_drift(settings, defaults, meta)
    report.facts["settings_drift"] = [
        {"field": k, "declared": w, "live": h} for k, w, h in drift_pairs
    ]
    if drift_pairs:
        report.add(
            Finding(
                "G-04",
                "S2",
                "live",
                "repository settings drift from the declaration",
                describe_drift(drift_pairs)
                + ". Squash-only linear history is a compliance property (CC8.1), so "
                "allow_merge_commit/allow_rebase_merge drifting to true weakens the "
                "audit trail even where branch protection is unavailable.",
                drift_patch_command(report.repo, drift_pairs),
            )
        )

    # ── G-05..G-07: secret scanning / push protection / Dependabot
    analysis = meta.get("security_and_analysis") or {}
    for index, (feature, severity) in enumerate(SECURITY_FEATURES, start=5):
        block = analysis.get(feature) or {}
        enabled = block.get("status") == "enabled"
        want = bool(defaults.get(feature, True))
        report.facts[feature] = block.get("status")
        if want and not enabled:
            parts = (
                (
                    f"security_and_analysis.{feature}.status = "
                    f"{block.get('status') or 'absent'}; "
                    f"policy/repo-defaults.yml#repository_defaults requires {want}."
                ),
                SECURITY_FEATURE_RATIONALE.get(feature, ""),
                PLAN_TIER_HINT if meta.get("private") else "",
            )
            report.add(
                Finding(
                    f"G-{index:02d}",
                    severity,
                    "live",
                    f"{feature} is not enabled",
                    " ".join(p for p in parts if p),
                    security_feature_command(report.repo, feature),
                )
            )

    # ── G-08: Dependabot vulnerability alerts (separate endpoint, 204/404)
    want_alerts = bool(settings.get("vulnerability_alerts", defaults.get("vulnerability_alerts")))
    alert_status, _ = gh_api(f"repos/{ORG}/{report.repo}/vulnerability-alerts")
    report.facts["vulnerability_alerts_http"] = alert_status
    if alert_status == 0:
        report.note_unverified("dependabot alerts", "endpoint could not be classified")
    elif want_alerts and alert_status == 404:
        report.add(
            Finding(
                "G-08",
                "S2",
                "live",
                "Dependabot vulnerability alerts are OFF",
                f"GET .../vulnerability-alerts -> 404 (not enabled), but the registry "
                f"declares vulnerability_alerts: {want_alerts}.",
                f"gh api repos/{ORG}/{report.repo}/vulnerability-alerts -X PUT",
            )
        )

    check_access(report, policy)
    check_protection(report, meta, policy)


def check_access(report: RepoReport, policy: dict[str, Any]) -> None:
    """G-09..G-11: least privilege — admins, outside collaborators, deploy keys."""
    baseline = policy.get("organization_baseline") or {}
    allowed = {str(a) for a in baseline.get("allowed_admins") or []}

    status, collabs = gh_api(
        f"repos/{ORG}/{report.repo}/collaborators?affiliation=all&per_page=100"
    )
    if status == 200 and isinstance(collabs, list):
        admins = sorted(
            str(c.get("login"))
            for c in collabs
            if isinstance(c, dict) and (c.get("permissions") or {}).get("admin")
        )
        report.facts["admins"] = admins
        unexpected = sorted(set(admins) - allowed)
        if unexpected:
            report.add(
                Finding(
                    "G-09",
                    "S1",
                    "live",
                    "unexpected administrator(s)",
                    f"admin holders: {admins}; policy allowed_admins: {sorted(allowed)}. "
                    "Unexpected: "
                    f"{unexpected}. The control plane cannot tell a legitimate invitation "
                    "from a compromised one, so a human must.",
                    f"gh api repos/{ORG}/{report.repo}/collaborators/{unexpected[0]}/permission "
                    "-X PUT -f permission=push   # downgrade, or add to allowed_admins with rationale",
                )
            )
        writers = sorted(
            str(c.get("login"))
            for c in collabs
            if isinstance(c, dict)
            and (c.get("permissions") or {}).get("push")
            and str(c.get("login")) not in allowed
        )
        report.facts["non_allowed_writers"] = writers
        if writers:
            report.add(
                Finding(
                    "G-10",
                    "S1",
                    "live",
                    "write access held by a principal outside the allow-list",
                    f"{writers} hold push access but are not in allowed_admins. "
                    "PCI-DSS Req 7 least privilege; solo-operator era expects exactly one.",
                    f"gh api repos/{ORG}/{report.repo}/collaborators/{writers[0]} -X DELETE",
                )
            )
    elif status != 200:
        report.note_unverified("collaborators", f"HTTP {status}")

    status, keys = gh_api(f"repos/{ORG}/{report.repo}/keys")
    if status == 200 and isinstance(keys, list):
        writable = [
            str(k.get("title") or k.get("id"))
            for k in keys
            if isinstance(k, dict) and not k.get("read_only")
        ]
        report.facts["deploy_keys"] = len(keys)
        report.facts["writable_deploy_keys"] = writable
        if writable:
            report.add(
                Finding(
                    "G-11",
                    "S1",
                    "live",
                    "deploy key with WRITE access",
                    f"writable deploy key(s): {writable}. A write deploy key is an "
                    "unattributable push path that bypasses every human control.",
                    f"gh api repos/{ORG}/{report.repo}/keys -q '.[].id'   # then DELETE the key id",
                )
            )
    elif status != 200:
        report.note_unverified("deploy keys", f"HTTP {status}")


def check_protection(report: RepoReport, meta: dict[str, Any], policy: dict[str, Any]) -> None:
    """G-12..G-14: branch protection, read the Free-plan-readable way.

    D-33 is the reason this function is written like this. The dedicated
    protection endpoint returns HTTP 403 on a Free-plan PRIVATE repository, and
    drift_detect.py classifies that as `unverifiable` — which files a real,
    proven absence of control under "could not check". The `.protected` boolean
    on the branch object IS readable on Free, so read it first and treat a
    plan-tier 403 as a FINDING with `blocked_by: plan tier`, not as a gap in
    the auditor's own visibility.
    """
    branch = str(meta.get("default_branch") or "main")
    size = meta.get("size")

    if not size:
        # size == 0 means no commit has ever landed: there is no branch object,
        # so protection is not merely absent but not yet POSSIBLE. Reporting
        # this as a defect would be a false positive; reporting it as nothing
        # would hide that the repo is unprotected. Informational, explicitly.
        report.facts["protection"] = "not-applicable-empty-repo"
        report.add(
            Finding(
                "G-12",
                "S3",
                "live",
                "repository is EMPTY — no default branch exists yet",
                f"size={size}; GET branches/{branch} -> 404. Branch protection cannot "
                "be attached before the first push creates the branch, so this repo "
                "currently has NO change-control layer at all. This is the expected "
                "pre-first-commit state, recorded so the verdict is not read as clean.",
                f"After the first push: gh api repos/{ORG}/{report.repo}/branches/{branch} "
                "-q .protected   # must become true where the plan allows it",
            )
        )
        return

    status, branch_obj = gh_api(f"repos/{ORG}/{report.repo}/branches/{branch}")
    if status != 200:
        report.facts["protection"] = f"unverifiable-http-{status}"
        report.note_unverified("branch protection", f"GET branches/{branch} -> HTTP {status}")
        return

    protected = bool(branch_obj.get("protected"))
    report.facts["branch_protected"] = protected

    prot_status, prot_body = gh_api(f"repos/{ORG}/{report.repo}/branches/{branch}/protection")
    plan_blocked = prot_status == 403 and "pgrade" in str(prot_body.get("error", ""))

    if not protected:
        severity = "S1"
        report.facts["protection"] = "missing"
        detail = f"branches/{branch}.protected = false — no enforceable protection. "
        if plan_blocked:
            detail += (
                f"The protection endpoint also returns HTTP 403 ({str(prot_body.get('error', ''))[:120]}), "
                f"which is a PLAN-TIER refusal, not a token-scope failure. {PLAN_TIER_HINT}"
            )
        else:
            detail += (
                "Direct pushes, force-pushes and branch deletion all succeed. Precedent "
                "D-33: jolarca-security took 14 commits directly on main with zero PRs."
            )
        report.add(
            Finding(
                "G-14" if plan_blocked else "G-13",
                severity,
                "live",
                "default branch is NOT protected"
                + (" (blocked by plan tier)" if plan_blocked else ""),
                detail,
                (
                    "Owner decision required: upgrade jolarca-dev to GitHub Team, then set "
                    "enable_branch_protection=true in terraform.tfvars; or record a dated "
                    "acceptance in policy/compliance-gates.yml exceptions.active with "
                    "`blocked_by: plan tier`. Do NOT close this by making the repo public "
                    "(D-31 records why that is worse)."
                    if plan_blocked
                    else f"gh api repos/{ORG}/{report.repo}/branches/{branch}/protection -X PUT "
                    "--input - <<<'{}'   # or set enable_branch_protection=true and apply"
                ),
            )
        )
        return

    # Protected: compare the rule against the declared baseline.
    report.facts["protection"] = "present"
    if prot_status != 200 or not isinstance(prot_body, dict):
        report.note_unverified(
            "branch protection attributes",
            f"branch reports protected=true but the rule is unreadable (HTTP {prot_status})",
        )
        return
    required = (policy.get("organization_baseline") or {}).get("required_branch_protection") or {}
    weakened: list[str] = []
    reviews = prot_body.get("required_pull_request_reviews") or {}
    checks = prot_body.get("required_status_checks") or {}
    contexts = list(checks.get("contexts") or []) + [
        str(c.get("context")) for c in (checks.get("checks") or []) if isinstance(c, dict)
    ]
    if required.get("enforce_admins") and not (prot_body.get("enforce_admins") or {}).get(
        "enabled"
    ):
        weakened.append("enforce_admins=false")
    if required.get("allow_force_pushes") is False and (
        prot_body.get("allow_force_pushes") or {}
    ).get("enabled"):
        weakened.append("force pushes allowed")
    if required.get("allow_deletions") is False and (prot_body.get("allow_deletions") or {}).get(
        "enabled"
    ):
        weakened.append("deletions allowed")
    if required.get("require_code_owner_reviews") and not reviews.get("require_code_owner_reviews"):
        weakened.append("code-owner review off")
    if required.get("dismiss_stale_reviews") and not reviews.get("dismiss_stale_reviews"):
        weakened.append("stale-review dismissal off")
    min_ctx = int(required.get("minimum_required_contexts") or 1)
    if len(contexts) < min_ctx:
        weakened.append(f"only {len(contexts)} required status context(s), baseline is {min_ctx}")
    report.facts["required_contexts_live"] = contexts
    report.facts["protection_weakened"] = weakened
    if weakened:
        report.add(
            Finding(
                "G-15",
                "S1",
                "live",
                "branch protection is weaker than the declared baseline",
                "; ".join(weakened)
                + ". A protection rule that exists but enforces nothing is the D-22 "
                "failure class: the control is present in configuration and never fires.",
                f"gh api repos/{ORG}/{report.repo}/branches/{branch}/protection "
                "-q '.'   # then reconcile with policy/repo-defaults.yml and apply",
            )
        )
    approvals = reviews.get("required_approving_review_count")
    if approvals == 0:
        # NOT a defect: deviation D-04, accepted with a dated expiry in
        # policy/compliance-gates.yml exceptions.active. Reported so the audit
        # trail shows it explicitly instead of hiding or failing it.
        report.facts["deviation_D04_zero_reviews"] = True


# ── Organization-level checks ────────────────────────────────────────────────


def check_org(policy: dict[str, Any]) -> tuple[list[Finding], dict[str, Any], list[str]]:
    """Org baselines the provider cannot manage. Shared by every repo's verdict."""
    findings: list[Finding] = []
    facts: dict[str, Any] = {}
    unverified: list[str] = []

    status, org = gh_api(f"orgs/{ORG}")
    if status != 200:
        return (
            [
                Finding(
                    "O-00",
                    "S1",
                    "org",
                    "organization settings could not be read",
                    f"GET orgs/{ORG} -> HTTP {status}: {str(org.get('error', ''))[:200]}",
                    "gh auth status   # needs admin:org scope",
                    "UNVERIFIABLE",
                )
            ],
            facts,
            [f"org settings: HTTP {status}"],
        )

    baseline = policy.get("organization_baseline") or {}
    plan = ((org.get("plan") or {}).get("name")) or "unknown"
    facts["plan"] = plan
    facts["two_factor_requirement_enabled"] = org.get("two_factor_requirement_enabled")
    facts["default_repository_permission"] = org.get("default_repository_permission")

    if plan == "free":
        findings.append(
            Finding(
                "O-05",
                "S3",
                "org",
                "organization is on the GitHub Free plan",
                "plan.name = free. This is CONTEXT, not a defect in itself, but it "
                "determines which controls are even possible: branch protection and "
                "rulesets are unavailable for private repos, and secret scanning / "
                "CodeQL require Team or Advanced Security (D-07, D-33).",
                "Owner decision: fund GitHub Team, or maintain dated risk acceptances "
                "for every control the plan makes impossible.",
            )
        )

    for key in (
        "two_factor_requirement_enabled",
        "members_can_create_repositories",
        "members_can_create_public_repositories",
        "members_can_create_private_repositories",
        "members_can_fork_private_repositories",
        "default_repository_permission",
        "web_commit_signoff_required",
    ):
        if key not in baseline:
            continue
        want = baseline[key]
        have = org.get(key)
        facts[key] = have
        if have is None:
            unverified.append(f"org.{key}: field absent from API response")
            continue
        if have == want:
            continue
        # 2FA is graded highest: it is the one control that stops a
        # credential-stuffed account from owning every PCI-scoped repo.
        severity = "S1" if key == "two_factor_requirement_enabled" else "S2"
        findings.append(
            Finding(
                f"O-{key}",
                severity,
                "org",
                f"org baseline violation: {key}",
                f"policy/repo-defaults.yml#organization_baseline requires {key}={want!r}; "
                f"live is {have!r}. Not provider-manageable — drift_detect.py is the only "
                "control that sees it.",
                (
                    "GitHub UI -> Organization settings -> Authentication security -> "
                    "Require two-factor authentication (API cannot set this; enabling it "
                    "removes any member without 2FA)."
                    if key == "two_factor_requirement_enabled"
                    else f"gh api orgs/{ORG} -X PATCH -f {key}={str(want).lower()}"
                ),
            )
        )
    return findings, facts, unverified


# ── Per-repository orchestration ─────────────────────────────────────────────


def audit_repo(
    name: str,
    defined: dict[str, dict[str, Any]],
    policy: dict[str, Any],
    patterns: list[tuple[str, str]],
    org_findings: list[Finding],
    live: bool,
) -> RepoReport:
    report = RepoReport(repo=name)
    declared = defined.get(name) or {}

    if name not in defined:
        report.add(
            Finding(
                "R-01",
                "S0",
                "declared",
                "repository is not in the allow-list",
                f"no repos/{name}.yml. An org repo named jolarca* that is absent from the "
                "allow-list is an out-of-band creation INCIDENT under ADR-0004 R2 "
                "(import within 48h).",
                f"$EDITOR {REPOS_DIR / (name + '.yml')}   # then terraform import per the runbook",
            )
        )
    else:
        report.facts["declared_visibility"] = declared.get("visibility")
        report.facts["tier"] = declared.get("tier")
        report.facts["criticality"] = declared.get("criticality")
        report.facts["launch_status"] = declared.get("launch_status")
        report.facts["data_classification"] = (declared.get("compliance") or {}).get(
            "data_classification"
        )

    check_local(report, declared, patterns)
    if live:
        check_live(report, declared, policy)
    else:
        report.note_unverified("live GitHub state", "skipped via --no-live")

    # Org-level baselines gate every repo: a first push into an org without 2FA
    # is not "ready" however clean the repository itself is.
    for finding in org_findings:
        report.add(finding)
    report.decide()
    return report


# ── Rendering ────────────────────────────────────────────────────────────────


def render_table(reports: list[RepoReport]) -> str:
    head = f"{'REPOSITORY':<26}{'VIS':<9}{'CRIT':<8}{'EMPTY':<7}{'PROT':<10}{'S0':<4}{'S1':<4}{'S2':<4}{'S3':<4}  VERDICT"
    lines = [head, "-" * len(head)]
    for r in reports:
        counts = {s: sum(1 for f in r.findings if f.severity == s) for s in SEVERITIES}
        vis = str(r.facts.get("live_visibility") or r.facts.get("declared_visibility") or "?")
        size = r.facts.get("live_size")
        empty = "?" if size is None else ("yes" if not size else "no")
        prot = str(r.facts.get("protection") or r.facts.get("branch_protected") or "?")[:9]
        crit = str(r.facts.get("criticality") or "?")
        lines.append(
            f"{r.repo:<26}{vis:<9}{crit:<8}"
            f"{empty:<7}{prot:<10}{counts['S0']:<4}{counts['S1']:<4}"
            f"{counts['S2']:<4}{counts['S3']:<4}  {r.verdict}"
        )
    return "\n".join(lines)


def render_markdown(reports: list[RepoReport], org_facts: dict[str, Any], generated: str) -> str:
    out = [
        "# Repository Readiness Audit — jolarca-dev",
        "",
        f"**Generated:** {generated}  ",
        "**Tool:** `scripts/repo_readiness_audit.py` (read-only)  ",
        f"**Fleet source:** `repos/*.yml` allow-list — {len(reports)} repositories  ",
        (
            f"**Org plan:** {org_facts.get('plan', 'unknown')} · "
            f"**2FA enforced:** {org_facts.get('two_factor_requirement_enabled', 'unknown')}"
        ),
        "",
        "Severity vocabulary matches `docs/drift-findings.md`: "
        + " · ".join(f"**{s}** {SEVERITY_MEANING[s]}" for s in SEVERITIES),
        "",
        "```",
        render_table(reports),
        "```",
        "",
    ]
    for r in reports:
        out.append(f"## {r.repo} — {r.verdict}")
        out.append("")
        if r.local_path:
            out.append(f"Local clone: `{r.local_path}`")
            out.append("")
        if not r.findings and not r.unverified:
            out.append("No findings. Every check in scope returned evidence.")
            out.append("")
            continue
        if r.findings:
            out.append("| ID | Sev | Category | Finding | Remediation |")
            out.append("|---|---|---|---|---|")
            for f in sorted(r.findings, key=lambda x: (SEVERITIES.index(x.severity), x.fid)):
                summary = f.summary.replace("|", "\\|")
                evidence = f.evidence.replace("|", "\\|").replace("\n", " ")
                remedy = f.remediation.replace("|", "\\|").replace("\n", " ")
                flag = "" if f.status == "VERIFIED" else f" **[{f.status}]**"
                out.append(
                    f"| {f.fid} | {f.severity} | {f.category} | {summary}{flag}<br>{evidence} | `{remedy}` |"
                )
            out.append("")
        if r.unverified:
            out.append(
                "**UNVERIFIED — these checks could not be performed, so the repo is BLOCKED:**"
            )
            out.append("")
            out.extend(f"- {u}" for u in r.unverified)
            out.append("")
    return "\n".join(out)


def to_json(reports: list[RepoReport], org_facts: dict[str, Any], generated: str) -> dict[str, Any]:
    return {
        "timestamp": generated,
        "tool": "scripts/repo_readiness_audit.py",
        "organization": ORG,
        "fleet_source": "repos/*.yml allow-list (registry-driven, never hardcoded)",
        "scope": "DECLARED + LOCAL WORKING COPY + LIVE GITHUB + ORG BASELINE",
        "read_only": True,
        "org_facts": org_facts,
        "repositories": [
            {
                "repo": r.repo,
                "verdict": r.verdict,
                "local_path": r.local_path,
                "facts": r.facts,
                "findings": [asdict(f) for f in r.findings],
                "unverified": r.unverified,
            }
            for r in reports
        ],
        "verdict_counts": {
            v: sum(1 for r in reports if r.verdict == v)
            for v in (VERDICT_READY, VERDICT_FIXES, VERDICT_BLOCKED)
        },
    }


# ── Entry point ──────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Pre-first-commit readiness gate for jolarca-dev repositories (read-only)."
    )
    parser.add_argument(
        "--repo",
        action="append",
        default=None,
        help="audit a specific repository (repeatable); default is the whole allow-list",
    )
    parser.add_argument("--no-live", action="store_true", help="skip GitHub API checks (offline)")
    parser.add_argument("--output", help="write the JSON evidence bundle to this path")
    parser.add_argument("--markdown", help="write the human-readable audit report to this path")
    parser.add_argument("--quiet", action="store_true", help="suppress the stderr summary")
    args = parser.parse_args()

    if not REPOS_DIR.is_dir():
        print(f"ERROR: allow-list directory not found: {REPOS_DIR}", file=sys.stderr)
        return 2

    policy = load_yaml(POLICY_DEFAULTS)
    gates = load_yaml(POLICY_GATES)
    defined = get_defined_repos()
    if not defined:
        print(f"ERROR: no repositories parsed from {REPOS_DIR}/*.yml", file=sys.stderr)
        return 2

    patterns = secret_patterns(gates)
    live = not args.no_live

    if live and run_cmd(["gh", "--version"])[0] != 0:
        print(
            "ERROR: gh CLI is required for live checks. Install it, or pass --no-live "
            "and accept that live state will be reported as UNVERIFIABLE.",
            file=sys.stderr,
        )
        return 2

    org_findings: list[Finding] = []
    org_facts: dict[str, Any] = {}
    org_unverified: list[str] = []
    if live:
        org_findings, org_facts, org_unverified = check_org(policy)

    targets = args.repo if args.repo else sorted(defined)
    unknown = sorted(set(targets or []) - set(defined) - {HEALTH_REPO})
    if unknown:
        print(
            f"WARNING: not in the allow-list, auditing anyway: {', '.join(unknown)}",
            file=sys.stderr,
        )

    reports: list[RepoReport] = []
    for name in targets or []:
        report = audit_repo(name, defined, policy, patterns, org_findings, live)
        for item in org_unverified:
            report.note_unverified("org baseline", item)
        # --no-live is an explicit operator choice, not a silent gap: the repos
        # whose live state was skipped are recorded so the verdict cannot be
        # mistaken for a clean bill of health (the D-30 lesson).
        report.decide()
        reports.append(report)

    generated = datetime.now(UTC).isoformat(timespec="seconds")
    bundle = to_json(reports, org_facts, generated)

    if args.output:
        Path(args.output).write_text(json.dumps(bundle, indent=2), encoding="utf-8")
    if args.markdown:
        Path(args.markdown).write_text(
            render_markdown(reports, org_facts, generated), encoding="utf-8"
        )

    if not args.quiet:
        print(render_table(reports), file=sys.stderr)
        counts = bundle["verdict_counts"]
        print(
            f"\n{counts[VERDICT_READY]} READY · {counts[VERDICT_FIXES]} READY-WITH-FIXES · "
            f"{counts[VERDICT_BLOCKED]} BLOCKED  ({len(reports)} repositories)",
            file=sys.stderr,
        )
        if args.markdown:
            print(f"report:    {args.markdown}", file=sys.stderr)
        if args.output:
            print(f"evidence:  {args.output}", file=sys.stderr)

    print(json.dumps(bundle, indent=2) if not args.output else f'{{"written": "{args.output}"}}')

    if any(r.unverified for r in reports):
        return 2
    return 0 if all(r.verdict == VERDICT_READY for r in reports) else 1


if __name__ == "__main__":
    sys.exit(main())
