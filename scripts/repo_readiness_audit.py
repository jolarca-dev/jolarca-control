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

# Directories that are never source, excluded from the pre-`git init` filesystem
# secret sweep so the scan spends its budget on content that could actually be
# committed. Excluding them here is about scan COST only — it is not permission
# to track them: .gitignore must still cover every one (the L-14 / A-04 class),
# and L-06a still reports any that reach the index.
SCAN_EXCLUDED_DIRS = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "env",
        "node_modules",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".idea",
        ".vscode",
        ".terraform",
        "dist",
        "build",
    }
)

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
    report.facts["local_path"] = str(root)

    is_git_repo = git(root, "rev-parse", "--git-dir")[0] == 0
    report.facts["is_git_repo"] = is_git_repo

    # ── Filesystem checks run UNCONDITIONALLY, ahead of the git guard ─────────
    # Not one of these six needs a .git directory: they read the working copy.
    # They used to sit at the END of this function, below an early `return` on
    # `git rev-parse` failure, so a directory that had not been `git init`'d yet
    # — precisely the pre-first-commit state this gate exists to inspect —
    # reported a single L-02 finding and silently skipped CODEOWNERS, license,
    # .gitignore, CI and the SECRET sweep. Verified on jolarca-consent
    # 2026-09-28: BLOCKED on 1 local finding where 7 were present, with no
    # secret scan performed at all. A gate that cannot read its subject must say
    # so; it must not stop looking.
    check_required_files(report, root)
    check_codeowners(report, root)
    check_ci_workflow(report, root, declared)
    check_license(report, root, declared)
    check_gitignore(report, root)
    check_secrets_local(report, root, patterns, is_git_repo)

    if not is_git_repo:
        report.add(
            Finding(
                "L-02",
                "S1",
                "local",
                "directory is not a git repository",
                f"{root} exists but `git rev-parse --git-dir` failed. The filesystem "
                "checks above still ran and their findings are real; only the "
                "git-dependent ones (remote identity, branch, cleanliness, index "
                "contents, pre-commit hook, signing) could not be performed.",
                f"cd {root} && git init -b main",
            )
        )
        report.note_unverified("git state", "not a git repository")
        return

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

    # NOTE: the filesystem checks (required files, CODEOWNERS, CI, license,
    # .gitignore, secrets) deliberately run ABOVE, before the git guard, so that
    # they also execute on a directory that has not been `git init`'d yet.
    # Do not move them back down here.


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


_ACTION_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
# A 40-hex pin that is really a placeholder. GitHub resolves a pin by looking the
# commit up, so a fabricated SHA does not fail review — it fails at RUNTIME, in
# CI, after the merge, with "unable to resolve action". Verified 2026-09-28:
# jolarca-consent pinned gitleaks-action@4f9a10b3c1d3b4e5e5e5e5e5e5e5e5e5e5e5e5e5,
# which GET /commits/<sha> answers with HTTP 422 "No commit found for SHA". A
# degenerate repeat run is the signature of a value written to LOOK like a hash
# rather than copied from one. This is a heuristic, so the finding points at the
# authoritative check instead of claiming to be it.
_DEGENERATE_SHA_RE = re.compile(r"(.)\1{7,}|(..)\2{4,}")
WORKFLOW_PR_TRIGGER = "pull_request"


def workflow_job_contexts(doc: dict[str, Any]) -> list[str]:
    """The status-check context names a workflow can actually report.

    GitHub names a required status check after the JOB's `name:` — falling back
    to the job key when `name:` is absent — and NOT after the workflow's own
    `name:`. Declaring a context that no job produces yields a protection rule
    that can never be satisfied, so every merge blocks forever. Reading the
    workflow name instead of the job name makes this check useless in exactly
    the way it exists to prevent.
    """
    jobs = doc.get("jobs")
    if not isinstance(jobs, dict):
        return []
    contexts: list[str] = []
    for job_id, body in jobs.items():
        if isinstance(body, dict) and isinstance(body.get("name"), str):
            contexts.append(str(body["name"]))
        else:
            contexts.append(str(job_id))
    return contexts


def _workflow_triggers(doc: dict[str, Any]) -> Any:
    """The workflow's `on:` block, accepting both spellings of the key.

    PyYAML implements YAML 1.1, where the bare key `on:` parses as the boolean
    True rather than the string "on" — the same trap that turns `no:` into
    False. The lookup goes through an Any-typed view because the declared key
    type cannot express a boolean key the parser genuinely produces, and
    `dict.get(True)` is a type error against `dict[str, Any]`.
    """
    raw: Any = doc
    return raw.get("on", raw.get(True))


def workflow_runs_on_pull_request(doc: dict[str, Any]) -> bool:
    """True when the workflow can fire on a pull request.

    Consulting only the string spelling of `on:` makes every workflow look
    trigger-less, which would report the whole fleet as unable to gate a merge.
    """
    triggers = _workflow_triggers(doc)
    if isinstance(triggers, str):
        return triggers == WORKFLOW_PR_TRIGGER
    if isinstance(triggers, list):
        return any(str(t) == WORKFLOW_PR_TRIGGER for t in triggers)
    if isinstance(triggers, dict):
        return WORKFLOW_PR_TRIGGER in triggers
    return False


def workflow_action_pins(doc: dict[str, Any]) -> list[tuple[str, str]]:
    """(job, action reference) for every step-level `uses:` in the workflow.

    A job-level `uses:` calls a REUSABLE workflow whose own pins cannot be
    resolved from this file, so those are skipped rather than guessed at.
    """
    jobs = doc.get("jobs")
    if not isinstance(jobs, dict):
        return []
    pins: list[tuple[str, str]] = []
    for job_id, body in jobs.items():
        if not isinstance(body, dict):
            continue
        steps = body.get("steps")
        if not isinstance(steps, list):
            continue
        for step in steps:
            if isinstance(step, dict) and isinstance(step.get("uses"), str):
                pins.append((str(job_id), str(step["uses"])))
    return pins


def _load_workflow(path: Path) -> dict[str, Any] | None:
    """Parse a workflow. None means it could not be parsed.

    Kept distinct from load_yaml, which propagates a parse error: a malformed
    workflow must be recorded as UNVERIFIABLE, not crash the gate, and must not
    be treated as a workflow with zero jobs — that would make every declared
    context look unsatisfiable for the wrong reason.
    """
    try:
        with open(path, encoding="utf-8") as handle:
            data = yaml.safe_load(handle)
    except (OSError, yaml.YAMLError):
        return None
    return data if isinstance(data, dict) else None


def check_ci_workflow(report: RepoReport, root: Path, declared: dict[str, Any]) -> None:
    """L-12 / L-19 / L-20 / L-21: declared status checks must be satisfiable.

    This is the D-22/D-27 failure class — a gate that exists in configuration
    and never fires. L-12 covers the coarse case (contexts declared, no workflow
    at all). It is NOT sufficient: a repo can ship three healthy workflows and
    still declare context names that no job produces, which is what
    jolarca-consent did (`ci` and `security` declared; jobs actually named
    "Lint (ruff)", "Gitleaks (secret scanning)" and so on — 0 of 2 satisfiable),
    and a workflow that never triggers on pull_request cannot gate a merge even
    when its job is named correctly.
    """
    contexts = (
        ((declared.get("branch_protection") or {}).get("main") or {}).get("required_status_checks")
        or {}
    ).get("contexts") or []
    declared_contexts = [str(c) for c in contexts]
    wf_dir = root / WORKFLOW_DIR
    workflow_paths = sorted(wf_dir.glob("*.y*ml")) if wf_dir.is_dir() else []
    workflows = [p.name for p in workflow_paths]
    report.facts["required_contexts"] = declared_contexts
    report.facts["workflows"] = workflows

    produced: set[str] = set()
    on_pr: set[str] = set()
    pins: list[tuple[str, str]] = []
    unparsable: list[str] = []
    for wf_path in workflow_paths:
        doc = _load_workflow(wf_path)
        if doc is None:
            unparsable.append(wf_path.name)
            continue
        names = workflow_job_contexts(doc)
        produced.update(names)
        if workflow_runs_on_pull_request(doc):
            on_pr.update(names)
        pins.extend(workflow_action_pins(doc))
    report.facts["workflow_contexts"] = sorted(produced)
    report.facts["workflow_pr_contexts"] = sorted(on_pr)

    if declared_contexts and not workflows:
        report.add(
            Finding(
                "L-12",
                "S1",
                "local",
                "registry requires status checks but the repo has NO CI workflow",
                f"repos/{report.repo}.yml declares required contexts {declared_contexts}; "
                f"{WORKFLOW_DIR}/ is {'absent' if not wf_dir.is_dir() else 'empty'}. "
                "Those checks can never report, so the protection rule they gate on "
                "is unsatisfiable — a control present in config that never fires (D-22, D-27).",
                f"cd {root} && mkdir -p {WORKFLOW_DIR} && $EDITOR {WORKFLOW_DIR}/ci.yml",
            )
        )
        return

    if unparsable:
        report.note_unverified(
            "CI workflow parse",
            f"could not parse {', '.join(unparsable)} — context satisfiability NOT assessed",
        )
        return

    if declared_contexts:
        unsatisfiable = sorted(set(declared_contexts) - produced)
        if unsatisfiable:
            report.add(
                Finding(
                    "L-19",
                    "S1",
                    "local",
                    "declared required status check cannot be produced by any workflow",
                    f"repos/{report.repo}.yml declares contexts {declared_contexts}, but the "
                    f"jobs in {WORKFLOW_DIR}/ report as {sorted(produced)}. "
                    f"{unsatisfiable} will therefore NEVER report. GitHub names a required "
                    "check after the job's `name:` (or its job key), not the workflow name, so "
                    "enabling protection as declared blocks every merge forever — the D-22/D-27 "
                    "failure class with the workflows present and healthy.",
                    f"cd {root} && grep -n 'name:' {WORKFLOW_DIR}/*.yml   # then set "
                    f"repos/{report.repo}.yml contexts to those exact strings",
                )
            )
        never_on_pr = sorted(c for c in declared_contexts if c in produced and c not in on_pr)
        if never_on_pr:
            report.add(
                Finding(
                    "L-20",
                    "S1",
                    "local",
                    "required status check never runs on a pull request",
                    f"{never_on_pr} are produced by a workflow whose `on:` does not include "
                    f"'{WORKFLOW_PR_TRIGGER}'. A check that only runs on schedule or manual "
                    "dispatch cannot gate a merge, so requiring it deadlocks every PR while "
                    "appearing fully configured.",
                    f"cd {root} && $EDITOR {WORKFLOW_DIR}/*.yml   # add "
                    f"'{WORKFLOW_PR_TRIGGER}:' under `on:`",
                )
            )

    # ── L-21: action pin integrity (supply chain, ISO 27001 A.8.19 / A.8.25)
    def _pin_ref(ref: str) -> str:
        return ref.rsplit("@", 1)[-1]

    degenerate = sorted(
        {
            ref
            for _, ref in pins
            if _ACTION_SHA_RE.match(_pin_ref(ref)) and _DEGENERATE_SHA_RE.search(_pin_ref(ref))
        }
    )
    if degenerate:
        report.add(
            Finding(
                "L-21a",
                "S1",
                "local",
                "action pinned to a SHA that looks fabricated — workflow will fail at runtime",
                f"{degenerate}. A 40-hex pin with a degenerate repeat run is a value written "
                "to resemble a commit hash, not one copied from it. GitHub resolves pins by "
                "lookup, so this passes review and fails in CI after the merge. Precedent: "
                "jolarca-consent security.yml, 2026-09-28 (HTTP 422, no such commit).",
                "for ref in " + " ".join(degenerate) + "; do "
                "owner_repo=${ref%@*}; sha=${ref##*@}; "
                'gh api "repos/$owner_repo/commits/$sha" -q .sha; done   # then repin to a real tag SHA',
            )
        )
    mutable = sorted(
        {ref for _, ref in pins if "@" in ref and not _ACTION_SHA_RE.match(_pin_ref(ref))}
    )
    if mutable:
        report.add(
            Finding(
                "L-21b",
                "S2",
                "local",
                "action pinned to a MUTABLE tag, not a commit SHA",
                f"{mutable}. policy/compliance-gates.yml SHA-pins every action it names, and "
                "the rest of this repo's workflows already do. A tag can be force-moved, so a "
                "green run yesterday does not describe the code that runs today.",
                "gh api repos/<owner>/<repo>/git/ref/tags/<tag> -q .object.sha   # then pin that SHA",
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
    # `license` records an explicit OWNER DECISION about licensing posture that
    # has no GitHub template — e.g. `proprietary`, meaning all rights reserved
    # with a committed LICENSE notice. It is deliberately NOT folded into
    # `license_template`: repositories.tf passes license_template straight to
    # github_repository and GitHub accepts only its own template keys, so
    # "proprietary" there would fail the apply. A separate field keeps L-13b
    # closable without breaking the provider, and makes the decision part of the
    # asset inventory instead of something an auditor has to infer from silence.
    posture = reg_settings.get("license") or declared.get("license")
    declared_posture = template or posture
    report.facts["has_license_file"] = has_license
    report.facts["license_template"] = template
    report.facts["license_posture"] = posture
    if declared_posture and not has_license:
        report.add(
            Finding(
                "L-13a",
                "S2",
                "local",
                "registry declares a license template but no LICENSE file exists",
                f"repos/{report.repo}.yml declares a licence posture "
                f"({template or posture}); {root} has no LICENSE to match it.",
                f"cd {root} && $EDITOR LICENSE   # {template or posture}",
            )
        )
    if not declared_posture and has_license:
        report.add(
            Finding(
                "L-13b",
                "S3",
                "local",
                "LICENSE present although policy declares none for this repo",
                f"{root} has a LICENSE file, but repos/{report.repo}.yml declares neither "
                "license_template nor license, and policy/repo-defaults.yml sets "
                "license: null. Confirm the licence is intended and record the decision "
                "in the registry so this finding is closable rather than permanent.",
                f"cd {root} && head -3 LICENSE   # then add `license: <posture>` under "
                f"settings in repos/{report.repo}.yml",
            )
        )
    if not declared_posture and not has_license and declared.get("visibility") == "public":
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


def run_gitleaks(report: RepoReport, root: Path, is_git_repo: bool = True) -> bool | None:
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
    # `gitleaks git` needs an object store. On a directory that has not been
    # `git init`'d it fails, and that failure would be recorded as "gitleaks
    # could not run" — which downgrades every regex hit to an UNCORROBORATED S0
    # and sends an operator to rotate credentials that do not exist. `gitleaks
    # dir` scans the same files without git. This is not a weaker check on a
    # pre-init directory: there is no history to scan yet either, so `dir` mode
    # is the COMPLETE scan, and the L-16 history sweep correctly reports itself
    # unverifiable.
    mode = "git" if is_git_repo else "dir"
    report.facts["gitleaks_mode"] = mode
    code, out, err = run_cmd(["gitleaks", mode, str(root), "--no-banner", "--redact"])
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
                f"`gitleaks {mode} {root}` exited 1 (leaks found). Its output is redacted "
                "by the tool; re-run locally to see the exact locations.",
                f"cd {root} && gitleaks {mode} . --no-banner   # then rotate every finding",
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


def _scan_targets(report: RepoReport, root: Path, is_git_repo: bool) -> list[str]:
    """Relative paths to sweep for secrets. Empty list only ever means "none found".

    With a repository the INDEX is authoritative: it is exactly what a commit
    would carry, so scanning the working tree instead would both miss staged
    deletions and waste effort on ignored files. Without one — the pre-`git init`
    state — fall back to a filesystem walk, because declining to enumerate would
    report an unscanned directory as clean.

    An unreadable index or tree is recorded as UNVERIFIABLE and yields no
    targets, never a silent pass (the D-23 lesson). Note that the fallback walk
    deliberately DOES scan files .gitignore would exclude, such as a local
    database: before the first commit nothing is excluded yet, and a SQLite file
    in a consent repository is exactly where residual PII would hide.
    """
    if is_git_repo:
        ls_rc, out, ls_err = git(root, "ls-files")
        if ls_rc != 0:
            report.note_unverified(
                "secret HEAD sweep", f"`git ls-files` exited {ls_rc}: {ls_err.strip()[:120]}"
            )
            return []
        return [line for line in out.splitlines() if line.strip()]

    found: list[str] = []
    errors: list[str] = []

    def _onerror(exc: OSError) -> None:
        errors.append(str(exc))

    for dirpath, dirnames, filenames in os.walk(root, onerror=_onerror):
        dirnames[:] = [d for d in dirnames if d not in SCAN_EXCLUDED_DIRS]
        current = Path(dirpath)
        for name in filenames:
            found.append(str((current / name).relative_to(root)))
    if errors:
        report.note_unverified(
            "secret filesystem sweep", f"{len(errors)} path(s) unreadable, e.g. {errors[0][:120]}"
        )
    return sorted(found)


def check_secrets_local(
    report: RepoReport,
    root: Path,
    patterns: list[tuple[str, str]],
    is_git_repo: bool = True,
) -> None:
    """L-15 / L-16: sweep tracked content AND history. Trust nothing.

    The brief is explicit that a secret in a brand-new repo "should be
    impossible" — verify anyway. History is scanned because a secret removed
    from HEAD is still in the packfile, still leaked, and still needs rotation.
    """
    corroborated = run_gitleaks(report, root, is_git_repo)
    compiled = [(re.compile(p), d) for p, d in patterns]

    hits_head: list[str] = []
    for rel in _scan_targets(report, root, is_git_repo):
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
    if not is_git_repo:
        # No object store, so no history exists to scan. This is a genuine
        # vacuous clean, not a skipped check — but it is recorded so the report
        # cannot be read as "history was swept and found clean".
        report.facts["secret_history_scanned"] = False
        report.facts["secret_hits_history"] = []
        return
    report.facts["secret_history_scanned"] = True
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
    check_protection(report, meta, policy, declared)


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


# Declared repos/<name>.yml branch_protection key -> where the same attribute
# lives in the live protection payload. `inverted` marks the two keys GitHub
# expresses as an ALLOWANCE (allow_force_pushes / allow_deletions) where the
# registry expresses a BLOCK (block_force_pushes / block_deletions).
#
# The live names are the REST API's, which do NOT always match the registry's
# (which follows the Terraform provider). `require_conversation_resolution` in
# repos/*.yml and branch-protection.tf is `required_conversation_resolution` in
# the REST payload. Verified against the live jolarca payload on 2026-09-28:
# using the Terraform spelling here returned None, was treated as unverifiable,
# and silently skipped a real declared=true/live=false drift.
_BP_BOOL_FIELDS: tuple[tuple[str, tuple[str, ...], bool], ...] = (
    ("enforce_admins", ("enforce_admins", "enabled"), False),
    ("require_linear_history", ("required_linear_history", "enabled"), False),
    (
        "require_conversation_resolution",
        ("required_conversation_resolution", "enabled"),
        False,
    ),
    ("require_signed_commits", ("required_signatures", "enabled"), False),
    ("block_force_pushes", ("allow_force_pushes", "enabled"), True),
    ("block_deletions", ("allow_deletions", "enabled"), True),
)

_BP_REVIEW_BOOLS: tuple[str, ...] = (
    "dismiss_stale_reviews",
    "require_code_owner_reviews",
    "require_last_push_approval",
)

# Attributes G-15 already compares against the FLEET baseline. When G-15 has
# actually fired for one of them, G-16 suppresses the same attribute so a single
# root cause does not appear twice under two IDs — an operator who fixes one and
# sees the other persist learns to distrust the register. G-16 still owns every
# attribute the fleet baseline does not mention.
_BP_G15_COVERED: dict[str, str] = {
    "enforce_admins": "enforce_admins=false",
    "block_force_pushes": "force pushes allowed",
    "block_deletions": "deletions allowed",
    "required_pull_request_reviews.require_code_owner_reviews": "code-owner review off",
    "required_pull_request_reviews.dismiss_stale_reviews": "stale-review dismissal off",
}


def _dig(payload: Any, path: tuple[str, ...]) -> Any:
    """Walk a nested payload, returning None when any level is absent.

    None is deliberately ambiguous between "absent" and "not a dict" — callers
    treat it as UNVERIFIABLE and skip the comparison rather than assume false.
    """
    current: Any = payload
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def live_required_contexts(prot_body: dict[str, Any]) -> list[str]:
    """Required status-check contexts, accepting both API shapes.

    The protection endpoint returns `contexts` (legacy list of strings) and/or
    `checks` (list of objects with a `context` key). Reading only one of them
    silently under-reports what is actually enforced.
    """
    checks = prot_body.get("required_status_checks") or {}
    if not isinstance(checks, dict):
        return []
    contexts = [str(c) for c in (checks.get("contexts") or [])]
    contexts.extend(
        str(c.get("context")) for c in (checks.get("checks") or []) if isinstance(c, dict)
    )
    return contexts


def compare_branch_protection(
    declared_bp: dict[str, Any], prot_body: dict[str, Any]
) -> list[tuple[str, Any, Any]]:
    """Pure: (attribute, declared, live) for every place LIVE IS WEAKER.

    Only the compliance-relevant direction is reported. A live rule that is
    STRICTER than the declaration is not a defect, and reporting it as one
    would train the operator to skim past the finding.
    """
    pairs: list[tuple[str, Any, Any]] = []

    for key, path, inverted in _BP_BOOL_FIELDS:
        if key not in declared_bp:
            continue
        want = bool(declared_bp[key])
        have_raw = _dig(prot_body, path)
        if have_raw is None:
            continue
        effective = (not bool(have_raw)) if inverted else bool(have_raw)
        if want and not effective:
            pairs.append((key, want, effective))

    declared_reviews = declared_bp.get("required_pull_request_reviews") or {}
    if isinstance(declared_reviews, dict):
        for key in _BP_REVIEW_BOOLS:
            if key not in declared_reviews:
                continue
            want = bool(declared_reviews[key])
            have = _dig(prot_body, ("required_pull_request_reviews", key))
            if have is None or not want or bool(have):
                continue
            pairs.append((f"required_pull_request_reviews.{key}", want, bool(have)))

        want_approvals = declared_reviews.get("required_approving_review_count")
        have_approvals = _dig(
            prot_body, ("required_pull_request_reviews", "required_approving_review_count")
        )
        if (
            isinstance(want_approvals, int)
            and isinstance(have_approvals, int)
            and have_approvals < want_approvals
        ):
            pairs.append(("required_approving_review_count", want_approvals, have_approvals))

    declared_checks = declared_bp.get("required_status_checks") or {}
    if isinstance(declared_checks, dict):
        live_checks = prot_body.get("required_status_checks")
        if (
            bool(declared_checks.get("strict"))
            and isinstance(live_checks, dict)
            and not bool(live_checks.get("strict"))
        ):
            pairs.append(("required_status_checks.strict", True, False))
        want_ctx = {str(c) for c in (declared_checks.get("contexts") or [])}
        live_ctx = set(live_required_contexts(prot_body))
        missing = sorted(want_ctx - live_ctx)
        if missing:
            pairs.append(("required_status_checks.contexts", sorted(want_ctx), missing))

    # `restrictions` absent vs null are different: absent means unverifiable.
    if (
        bool(declared_bp.get("restrict_pushes"))
        and "restrictions" in prot_body
        and prot_body.get("restrictions") is None
    ):
        pairs.append(("restrict_pushes", True, False))

    return pairs


def unverifiable_branch_protection(
    declared_bp: dict[str, Any], prot_body: dict[str, Any]
) -> list[str]:
    """Declared attributes whose live counterpart is ABSENT from the payload.

    D-23: "could not check" must never be reported as clean. A declared
    attribute the API did not return is not agreement — it is a hole in the
    auditor's own visibility, and it belongs in the report's unverified list.
    This exists because compare_branch_protection() deliberately skips such
    fields, so on its own a renamed API key would fail SILENTLY.

    `restrict_pushes` is intentionally excluded: the REST payload omits
    `restrictions` entirely rather than returning null, so absence there is
    ambiguous and would mark every declaring repo unverifiable.
    """
    missing: list[str] = []
    for key, path, _inverted in _BP_BOOL_FIELDS:
        if key in declared_bp and _dig(prot_body, path) is None:
            missing.append(key)

    declared_reviews = declared_bp.get("required_pull_request_reviews") or {}
    if isinstance(declared_reviews, dict):
        for key in (*_BP_REVIEW_BOOLS, "required_approving_review_count"):
            live = _dig(prot_body, ("required_pull_request_reviews", key))
            if key in declared_reviews and live is None:
                missing.append(f"required_pull_request_reviews.{key}")

    declared_checks = declared_bp.get("required_status_checks") or {}
    if isinstance(declared_checks, dict) and "strict" in declared_checks:
        live_checks = prot_body.get("required_status_checks")
        if not isinstance(live_checks, dict) or live_checks.get("strict") is None:
            missing.append("required_status_checks.strict")
    return missing


def branch_protection_remediation() -> str:
    """Terraform-first remediation for protection drift.

    A raw `gh api` PATCH is deliberately NOT offered. branch-protection.tf owns
    github_branch_protection for the fleet, so an out-of-band PATCH is reverted
    by the next apply and hides the drift from the plan — the operator would
    watch the finding they just "fixed" come back. That file also hardcodes
    strict / dismiss_stale_reviews / required_linear_history /
    require_conversation_resolution to FALSE and is disabled wholesale by
    var.enable_branch_protection=false, so the HCL itself is the defect.
    """
    return (
        "Terraform owns this rule (branch-protection.tf) — do NOT patch it out of band. "
        "Fix defect 1 in that file so each attribute reads "
        "each.value.branch_protection.main instead of a hardcoded false, set "
        "enable_branch_protection=true in terraform.tfvars, then: "
        "terraform plan -target github_branch_protection   # review before make apply"
    )


# Ruleset rule types that mean the protection actually gates a MERGE, not merely
# a deletion or a force-push. Stage 1 (deletion / non_fast_forward /
# required_linear_history) can and should be created before the first push; stage
# 2 must wait until a check has reported green at least once, or the required
# contexts are unsatisfiable and every merge deadlocks.
STAGE2_RULESET_RULE_TYPES = frozenset(
    {"pull_request", "required_pull_request_before_merging", "required_status_checks"}
)


def _active_branch_rulesets(body: Any) -> list[dict[str, Any]]:
    if not isinstance(body, list):
        return []
    return [
        entry
        for entry in body
        if isinstance(entry, dict)
        and entry.get("target") == "branch"
        and entry.get("enforcement") == "active"
    ]


def _ruleset_rule_types(detail: dict[str, Any]) -> set[str]:
    rules = detail.get("rules")
    if not isinstance(rules, list):
        return set()
    return {str(rule.get("type")) for rule in rules if isinstance(rule, dict)}


def _ruleset_targets_default_branch(detail: dict[str, Any], branch: str) -> bool:
    include = _dig(detail, ("conditions", "ref_name", "include"))
    if not isinstance(include, list):
        return False
    return any(str(ref) in ("~DEFAULT_BRANCH", branch) for ref in include)


def rulesets_covering_default_branch(
    body: Any, api_prefix: str, branch: str
) -> list[dict[str, Any]]:
    """Active branch rulesets that actually cover the default branch.

    GET /rulesets returns SUMMARIES that omit `conditions` and `rules` — verified
    2026-09-28 on jolarca-consent, where the list shape carries
    `"conditions": null` — so the per-ruleset detail endpoint must be read to
    know what a ruleset targets. A ruleset that exists but points at some other
    ref protects nothing here, and counting it as protection would repeat the
    original G-12 mistake in the opposite direction.
    """
    covering: list[dict[str, Any]] = []
    for summary in _active_branch_rulesets(body):
        ruleset_id = summary.get("id")
        if ruleset_id is None:
            continue
        status, detail = gh_api(f"{api_prefix}/rulesets/{ruleset_id}")
        if status != 200 or not isinstance(detail, dict):
            continue
        if _ruleset_targets_default_branch(detail, branch):
            detail.setdefault("name", summary.get("name"))
            covering.append(detail)
    return covering


def check_protection(
    report: RepoReport,
    meta: dict[str, Any],
    policy: dict[str, Any],
    declared: dict[str, Any] | None = None,
) -> None:
    """G-12..G-16: branch protection, read the Free-plan-readable way.

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
        # size == 0 means no commit has ever landed, so there is no branch object
        # and CLASSIC protection cannot be attached yet. What does NOT follow is
        # that the repo cannot be protected before the first push: a repository
        # RULESET matches a ref by NAME and can target ~DEFAULT_BRANCH before
        # that branch exists.
        #
        # Availability is a per-repo fact and must be PROBED, not inferred from
        # the plan tier. Verified 2026-09-28 on jolarca-consent: GET /rulesets
        # returns HTTP 200 on that PUBLIC repo and HTTP 403 "Upgrade to GitHub
        # Pro" on a private repo in the same org on the same Free plan. An
        # earlier revision of this finding asserted that protection "cannot be
        # attached before the first push"; telling an owner a control is
        # impossible when it is merely unimplemented causes risk to be accepted
        # that was never real — and it is never re-tested, because the finding
        # reads as closed.
        rs_status, rs_body = gh_api(f"repos/{ORG}/{report.repo}/rulesets")
        report.facts["ruleset_api_status"] = rs_status
        if rs_status == 200:
            api_prefix = f"repos/{ORG}/{report.repo}"
            covering = rulesets_covering_default_branch(rs_body, api_prefix, branch)
            names = [str(rule.get("name") or rule.get("id")) for rule in covering]
            report.facts["active_rulesets_on_default_branch"] = names
            if not covering:
                report.facts["protection"] = "absent-ruleset-available"
                report.add(
                    Finding(
                        "G-12a",
                        "S1",
                        "live",
                        "EMPTY and UNPROTECTED — a ruleset can and must precede the first push",
                        f"size={size}; GET branches/{branch} -> 404, so no classic rule can attach "
                        "yet. GET /rulesets -> HTTP 200 with no active rule covering the default "
                        "branch, so repository rulesets ARE available here and can protect "
                        "~DEFAULT_BRANCH before that branch exists. Pushing first and protecting "
                        "afterwards leaves the default branch unguarded for the entire bootstrap "
                        "window — which is when the largest single change in the repository's "
                        "life lands.",
                        f"gh api {api_prefix}/rulesets -X POST --input - <<'JSON'\n"
                        '{"name":"protect-main","target":"branch","enforcement":"active",'
                        '"conditions":{"ref_name":{"include":["~DEFAULT_BRANCH"],"exclude":[]}},'
                        '"rules":[{"type":"deletion"},{"type":"non_fast_forward"},'
                        '{"type":"required_linear_history"}],"bypass_actors":[]}\n'
                        "JSON\n"
                        "# Stage 2 — ONLY after the first PR reports green, or the contexts are\n"
                        "# unsatisfiable and every merge deadlocks: add pull_request and\n"
                        f"# required_status_checks via PATCH. Verify: gh api {api_prefix}/rulesets",
                    )
                )
            else:
                types: set[str] = set()
                for rule in covering:
                    types |= _ruleset_rule_types(rule)
                report.facts["ruleset_rule_types"] = sorted(types)
                stage2 = bool(types & STAGE2_RULESET_RULE_TYPES)
                report.facts["ruleset_stage2_present"] = stage2
                report.facts["protection"] = (
                    "ruleset-active" if stage2 else "ruleset-stage-1-active"
                )
                if not stage2:
                    report.add(
                        Finding(
                            "G-12c",
                            "S3",
                            "live",
                            "stage-1 ruleset ACTIVE on the empty repo — stage 2 still owed",
                            f"active ruleset(s) covering {branch}: {names}, enforcing "
                            f"{sorted(types)}. Deletion, force-push and non-linear history are "
                            "already blocked ahead of the first push, which is the part that "
                            "cannot be retrofitted safely. Merge gating is NOT yet enforced: "
                            "pull_request / required_status_checks are deliberately deferred "
                            "until a check has reported green once, because requiring a context "
                            "that has never reported blocks every merge.",
                            f"After the first green PR run: gh api {api_prefix}/rulesets/"
                            "<id> -X PUT --input - to add pull_request and "
                            "required_status_checks, then re-run this gate to confirm "
                            "ruleset_stage2_present=true.",
                        )
                    )
        elif rs_status == 403:
            report.facts["protection"] = "not-applicable-empty-repo"
            report.add(
                Finding(
                    "G-12b",
                    "S3",
                    "live",
                    "repository is EMPTY and the plan tier blocks protection",
                    f"size={size}; GET branches/{branch} -> 404 and GET /rulesets -> 403, so "
                    "neither classic protection nor a ruleset can be attached on this plan "
                    "until content exists or the repo is upgraded/made public. The repo has NO "
                    "change-control layer; this is recorded so the verdict is not read as clean.",
                    "Owner decision: upgrade the plan, or record a dated risk acceptance in "
                    "policy/compliance-gates.yml#exceptions.active in the D-07 pattern with "
                    "`blocked_by: plan tier`.",
                )
            )
        else:
            report.facts["protection"] = f"unverifiable-http-{rs_status}"
            report.note_unverified(
                "ruleset availability", f"GET /rulesets -> HTTP {rs_status} on an empty repo"
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
    contexts = live_required_contexts(prot_body)
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
                branch_protection_remediation(),
            )
        )
    approvals = reviews.get("required_approving_review_count")
    if approvals == 0:
        # NOT a defect: deviation D-04, accepted with a dated expiry in
        # policy/compliance-gates.yml exceptions.active. Reported so the audit
        # trail shows it explicitly instead of hiding or failing it.
        report.facts["deviation_D04_zero_reviews"] = True

    # ── G-16: live rule vs the PER-REPO declaration in repos/<name>.yml.
    # G-15 compares only against the fleet-wide baseline in
    # policy/repo-defaults.yml#organization_baseline.required_branch_protection,
    # which covers five attributes and a context COUNT. The registry entry is
    # both stricter and more specific (strict status checks, linear history,
    # conversation resolution, signed commits and the exact context list), and
    # nothing in the fleet compared any of it — a repo could satisfy the org
    # baseline while silently ignoring its own allow-list declaration. Same
    # D-22 failure class, one level down.
    declared_bp = ((declared or {}).get("branch_protection") or {}).get(branch) or {}
    if not isinstance(declared_bp, dict) or not declared_bp:
        report.note_unverified(
            "per-repo branch protection declaration",
            f"repos/{report.repo}.yml declares no branch_protection.{branch} block",
        )
        return
    bp_drift = compare_branch_protection(declared_bp, prot_body)
    bp_only = [pair for pair in bp_drift if _BP_G15_COVERED.get(pair[0]) not in weakened]
    bp_unverifiable = unverifiable_branch_protection(declared_bp, prot_body)
    if bp_unverifiable:
        report.note_unverified(
            "per-repo branch protection attributes",
            f"declared in repos/{report.repo}.yml but absent from the live protection "
            f"payload: {bp_unverifiable}",
        )
    report.facts["declared_branch_protection_drift"] = [
        {"field": k, "declared": w, "live": h} for k, w, h in bp_drift
    ]
    report.facts["declared_branch_protection_unverifiable"] = bp_unverifiable
    report.facts["declared_branch_protection_drift_not_in_G15"] = [
        {"field": k, "declared": w, "live": h} for k, w, h in bp_only
    ]
    if bp_only:
        report.add(
            Finding(
                "G-16",
                "S1",
                "live",
                f"live branch protection is weaker than repos/{report.repo}.yml declares",
                describe_drift(bp_only)
                + ". The allow-list entry is what an auditor reads as the declared "
                "control; where live is laxer, the documented control does not exist. "
                "Attributes already reported under G-15 are not repeated here.",
                branch_protection_remediation(),
            )
        )


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
