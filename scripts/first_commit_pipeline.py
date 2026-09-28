#!/usr/bin/env python3
"""Phase 3 first-commit pipeline gate for jolarca-dev fleet repositories.

jolarca-control — marketplace (jolarca-dev) governance control plane.

WHY THIS EXISTS
---------------
scripts/repo_readiness_audit.py answers "may this repository receive its first
real commit?" — Phases 1 and 2 of the new-repository audit. It stops there.
Nothing in the fleet governs what happens NEXT: the six-step delivery pipeline
that carries a repository from a clean working tree to a verified commit on the
default branch.

  VERIFY FIRST → COMMIT → PUSH → REVIEW → MERGE → VERIFY AGAIN

That sequence is documented in prose and enforced nowhere, which is the D-22
failure class in its purest form: a control that exists in a document and never
fires. docs/drift-findings.md D-33 records the consequence — jolarca-security
took 14 commits directly onto main with zero pull requests, because on the Free
plan nothing could stop it and no tool was looking.

This script is that tool. It walks an operator through the pipeline one step at
a time, verifies every precondition it can read, prints the exact command for
the human to run, and refuses to advance until the previous step passed.

DESIGN CONSTRAINTS
------------------
  * READ-ONLY IS STRUCTURAL, NOT A PROMISE. Every subprocess call passes through
    _assert_read_only(), which rejects anything not on an explicit allowlist.
    `git commit`, `git push`, `gh pr merge` and any mutating `gh api` verb are
    unreachable from this module. A test asserts it by scanning this file's own
    source. The operator runs the write commands; this script only ever reads.
  * Step A CONSUMES repo_readiness_audit.py rather than re-implementing it.
    org_delivery_audit.sh hardcodes 7 of 16 repositories and silently
    under-audits the rest; two gates that each implement a check are two gates
    that eventually disagree. There is one readiness gate and this calls it.
  * PLAN-AWARE. Where the Free plan cannot enforce a control, the check
    degrades to a TRACKED EXCEPTION that names the finding (D-04 / D-05 / D-33),
    its compensating control, and its expiry date read live from
    policy/compliance-gates.yml `exceptions.active`. Never a silent pass.
  * EXPIRY IS ENFORCED. An exception whose `expires` date has passed is LAPSED
    and blocks in every mode, including the default one. The D-25 lesson: an
    event-only expiry has no deadline and stays open forever. When the org
    upgrades to GitHub Team, `--strict` becomes the default and nothing here
    needs rewriting.
  * EVIDENCE. Each step appends to a markdown record — timestamp, status, the
    command printed, exceptions cited, operator attestation. That file is the
    SOC 2 CC8.1 / ISO 27001 A.8.32 artifact proving a human confirmed the
    compensating controls, rather than a script waving them through.
  * SECRETS ARE NEVER ECHOED. A hit reports file:line and the pattern name only.
    The evidence file is committed as audit material; it must not become the leak.

Exit codes (same trichotomy as the readiness gate — the D-23 lesson: a control
that cannot read its subject must never report success)
----------
  0  every requested step PASSED
  1  at least one step is BLOCKED or carries a TRACKED EXCEPTION
  2  at least one check could not be verified (missing gh, auth failure, API error)

Usage
-----
  python3 scripts/first_commit_pipeline.py --repo jolarca-payments --step A
  python3 scripts/first_commit_pipeline.py --repo jolarca-payments --step all
  python3 scripts/first_commit_pipeline.py --repo r --step B --message "feat: add x"
  python3 scripts/first_commit_pipeline.py --repo r --step all --strict
  python3 scripts/first_commit_pipeline.py --repo r --step F --attest "G. Kazlauskas"
  make first-commit REPO=jolarca-payments STEP=A

Environment
-----------
  JOLARCA_CONTROL_ORG   organization to audit           (default: jolarca-dev)
  JOLARCA_REPOS_ROOT    parent dir holding local clones (default: this repo's parent)
  GITHUB_TOKEN/GH_TOKEN passed through to gh
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import repo_readiness_audit as rra

# ── Step vocabulary ──────────────────────────────────────────────────────────

STEP_A = "A"
STEP_B = "B"
STEP_C = "C"
STEP_D = "D"
STEP_E = "E"
STEP_F = "F"
STEP_ORDER = (STEP_A, STEP_B, STEP_C, STEP_D, STEP_E, STEP_F)

STEP_TITLES = {
    STEP_A: "VERIFY FIRST",
    STEP_B: "COMMIT",
    STEP_C: "PUSH",
    STEP_D: "REVIEW",
    STEP_E: "MERGE",
    STEP_F: "VERIFY AGAIN",
}

# A step may not be entered until every step before it has passed. Without this
# an operator can run --step E on a repository that never cleared Step A, which
# is exactly how an unaudited commit reaches the default branch.
PREREQUISITES: dict[str, tuple[str, ...]] = {
    STEP_A: (),
    STEP_B: (STEP_A,),
    STEP_C: (STEP_A, STEP_B),
    STEP_D: (STEP_A, STEP_B, STEP_C),
    STEP_E: (STEP_A, STEP_B, STEP_C, STEP_D),
    STEP_F: (STEP_A, STEP_B, STEP_C, STEP_D, STEP_E),
}

# ── Check statuses ───────────────────────────────────────────────────────────

STATUS_PASS = "PASS"
STATUS_EXCEPTION = "TRACKED-EXCEPTION"
STATUS_BLOCKED = "BLOCKED"
STATUS_UNVERIFIABLE = "UNVERIFIABLE"

# ── Read-only enforcement ────────────────────────────────────────────────────
# The allowlist is the control. Anything not listed here cannot be executed by
# this module, so "the gate is read-only" is a property of the code rather than
# a claim in its docstring.

_ALLOWED_GIT_SUBCOMMANDS = frozenset(
    {
        "status",
        "log",
        "diff",
        "rev-parse",
        "branch",
        "config",
        "remote",
        "ls-files",
        "show",
        "rev-list",
        "symbolic-ref",
    }
)
_ALLOWED_GH_SUBCOMMANDS = frozenset({"pr", "run", "repo", "api", "auth", "--version"})
_ALLOWED_GH_PR_VERBS = frozenset({"view", "list", "checks", "diff", "status"})
_ALLOWED_GH_RUN_VERBS = frozenset({"list", "view"})
_ALLOWED_GH_REPO_VERBS = frozenset({"view"})
_ALLOWED_TOOLS = frozenset({"git", "gh", "gitleaks"})

# Mutating flags. `gh api -X PUT` and `gh pr merge` are the two ways a read-only
# tool could still write to GitHub; both are refused here rather than by
# convention. gh's -f/-F/--input build a request BODY, which only a mutating
# verb can send, so their presence is treated as an attempted write.
_MUTATING_FLAGS = frozenset({"-X", "--method", "-f", "--field", "-F", "--raw-field", "--input"})

# `git config` is allowlisted because Step B must READ commit.gpgsign — but its
# write form (`git config [--global] name value`) mutates the operator's
# environment. Allowing the bare subcommand therefore allowed a write through a
# gate whose whole guarantee is that it cannot write. Permit only the explicit
# read flags; anything else is refused.
_READ_ONLY_GIT_CONFIG_FLAGS = frozenset(
    {"--get", "--get-all", "--get-regexp", "--get-urlmatch", "--list", "-l"}
)


class ReadOnlyViolation(RuntimeError):
    """Raised when a command outside the read-only allowlist is attempted."""


def _assert_read_only(cmd: list[str]) -> None:
    """Refuse any command that could write to git or to GitHub.

    Raises ReadOnlyViolation rather than returning a status: a caller must not be
    able to ignore the result. This is the single chokepoint every subprocess
    call in this module goes through.
    """
    if not cmd:
        raise ReadOnlyViolation("empty command")
    tool = cmd[0]
    if tool not in _ALLOWED_TOOLS:
        raise ReadOnlyViolation(f"tool not allowlisted: {tool}")

    if tool == "git":
        if len(cmd) < 2 or cmd[1] not in _ALLOWED_GIT_SUBCOMMANDS:
            raise ReadOnlyViolation(f"git subcommand not allowlisted: {cmd[1:2]}")
        if cmd[1] == "config" and not any(a in _READ_ONLY_GIT_CONFIG_FLAGS for a in cmd[2:]):
            raise ReadOnlyViolation(
                "git config is allowlisted for READING only; `git config [--global] "
                "name value` writes. Pass --get or --list."
            )
        return

    if tool == "gitleaks":
        # `detect` only reads. `protect` also only reads but implies push intent;
        # neither writes to the repository, and detect is what the gate needs.
        if len(cmd) < 2 or cmd[1] not in {"detect"}:
            raise ReadOnlyViolation(f"gitleaks subcommand not allowlisted: {cmd[1:2]}")
        return

    # gh
    if len(cmd) < 2 or cmd[1] not in _ALLOWED_GH_SUBCOMMANDS:
        raise ReadOnlyViolation(f"gh subcommand not allowlisted: {cmd[1:2]}")
    verb = cmd[1]
    if verb in {"pr", "run", "repo"}:
        allowed = {
            "pr": _ALLOWED_GH_PR_VERBS,
            "run": _ALLOWED_GH_RUN_VERBS,
            "repo": _ALLOWED_GH_REPO_VERBS,
        }[verb]
        if len(cmd) < 3 or cmd[2] not in allowed:
            raise ReadOnlyViolation(f"gh {verb} verb not allowlisted: {cmd[2:3]}")
    if any(arg in _MUTATING_FLAGS for arg in cmd[2:]):
        raise ReadOnlyViolation(f"mutating flag in read-only command: {cmd}")


def run_read_only(cmd: list[str], cwd: Path | None = None) -> tuple[int, str, str]:
    """run_cmd with the read-only allowlist enforced first."""
    _assert_read_only(cmd)
    return rra.run_cmd(cmd, cwd=cwd)


def gh_json(args: list[str]) -> tuple[int, Any]:
    """Run a read-only gh command that emits JSON. Returns (status, payload)."""
    status, out, _err = run_read_only(["gh", *args])
    if status != 0:
        return status, None
    try:
        return status, json.loads(out)
    except json.JSONDecodeError:
        return status, None


# ── Conventional Commits ─────────────────────────────────────────────────────

# CONTRIBUTING.md and the repository's own history use Conventional Commits.
# The type set is closed on purpose: an open regex accepts "update: stuff",
# which is the shape of a commit message an auditor cannot classify.
CONVENTIONAL_COMMIT_RE = re.compile(
    r"^(?P<type>feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)"
    r"(?:\((?P<scope>[A-Za-z0-9._/\-]+)\))?"
    r"(?P<breaking>!)?: (?P<subject>\S.{0,98})$"
)


def conventional_commit_subject(message: str) -> str | None:
    """Return the subject line if it is Conventional Commits, else None."""
    first = message.strip().splitlines()[0] if message.strip() else ""
    match = CONVENTIONAL_COMMIT_RE.match(first)
    return match.group("subject") if match else None


# ── Data model ───────────────────────────────────────────────────────────────


@dataclass
class Check:
    """One verification inside a step."""

    name: str
    status: str
    detail: str
    command: str = ""


@dataclass
class StepResult:
    """Outcome of one pipeline step, including the command the human must run."""

    step: str
    title: str
    checks: list[Check] = field(default_factory=list)
    command: str = ""

    def add(self, name: str, status: str, detail: str, command: str = "") -> None:
        self.checks.append(Check(name, status, detail, command))

    @property
    def status(self) -> str:
        """Worst status wins. UNVERIFIABLE outranks BLOCKED: a control that
        could not read its subject must not be reported as a mere failure."""
        seen = {c.status for c in self.checks}
        if STATUS_UNVERIFIABLE in seen:
            return STATUS_UNVERIFIABLE
        if STATUS_BLOCKED in seen:
            return STATUS_BLOCKED
        if STATUS_EXCEPTION in seen:
            return STATUS_EXCEPTION
        return STATUS_PASS

    @property
    def passed(self) -> bool:
        """Only an unqualified PASS advances the pipeline. A TRACKED EXCEPTION
        does not: it is recorded, and a human decides whether to proceed."""
        return self.status == STATUS_PASS


@dataclass
class PipelineReport:
    """Aggregated result for one repository's pipeline run."""

    repo: str
    steps: list[StepResult] = field(default_factory=list)
    snapshot: dict[str, Any] = field(default_factory=dict)

    def step(self, step: str) -> StepResult:
        result = StepResult(step, STEP_TITLES[step])
        self.steps.append(result)
        return result

    def get(self, step: str) -> StepResult | None:
        return next((s for s in self.steps if s.step == step), None)

    @property
    def status(self) -> str:
        seen = {s.status for s in self.steps}
        if STATUS_UNVERIFIABLE in seen:
            return STATUS_UNVERIFIABLE
        if STATUS_BLOCKED in seen:
            return STATUS_BLOCKED
        if STATUS_EXCEPTION in seen:
            return STATUS_EXCEPTION
        return STATUS_PASS


# ── Tracked exceptions (plan-tier reality) ───────────────────────────────────


def load_exceptions(gates: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Index policy/compliance-gates.yml `exceptions.active` by finding id."""
    active = (gates.get("exceptions") or {}).get("active") or []
    indexed: dict[str, dict[str, Any]] = {}
    if isinstance(active, list):
        for entry in active:
            if isinstance(entry, dict) and entry.get("id"):
                indexed[str(entry["id"])] = entry
    return indexed


def load_open_blocking(gates: dict[str, Any]) -> frozenset[str]:
    """Index policy/compliance-gates.yml `exceptions.open_blocking`.

    These are findings the owner has NOT accepted — they are listed precisely so
    the policy file cannot be read as a clean bill of health. Keeping them apart
    from `active` is the whole point: an open blocking finding must never be
    reported as a tracked exception, or this gate would launder an undecided risk
    into an accepted one and the audit trail would show a decision nobody made.
    """
    section = (gates.get("exceptions") or {}).get("open_blocking") or []
    if not isinstance(section, list):
        return frozenset()
    return frozenset(str(e["id"]) for e in section if isinstance(e, dict) and e.get("id"))


@dataclass(frozen=True)
class ExceptionRegister:
    """The policy's exception state, read live from policy/compliance-gates.yml.

    Read rather than hardcoded so that a lapsed or newly-recorded acceptance
    changes this gate's behaviour with no code change.
    """

    active: dict[str, dict[str, Any]]
    open_blocking: frozenset[str]


def load_register(gates: dict[str, Any]) -> ExceptionRegister:
    return ExceptionRegister(load_exceptions(gates), load_open_blocking(gates))


def _parse_expiry(raw: Any) -> date | None:
    if not isinstance(raw, str):
        return None
    try:
        return date.fromisoformat(raw.strip())
    except ValueError:
        return None


# Ceiling on how much of a policy compensating_control string is echoed into a
# check detail. See exception_state().
_MAX_CONTROL_CHARS = 400


def exception_state(register: ExceptionRegister, finding_id: str, today: date) -> tuple[str, str]:
    """Resolve a deviation to (status, reason).

    Four outcomes, none of them silent:
      * registered and unexpired  → TRACKED-EXCEPTION, naming the compensating
        control and the expiry date
      * registered but LAPSED     → BLOCKED, because an acceptance with no
        current signature is not an acceptance (D-25)
      * recorded as open_blocking → BLOCKED, naming that an OWNER DECISION is
        required; an open finding is not an accepted one
      * not registered at all     → BLOCKED, because the gate will not invent an
        exception that the policy owner never approved
    """
    entry = register.active.get(finding_id)
    if entry is None:
        if finding_id in register.open_blocking:
            return (
                STATUS_BLOCKED,
                (
                    f"{finding_id} is recorded in policy/compliance-gates.yml "
                    "exceptions.OPEN_BLOCKING — an unresolved finding, not an accepted "
                    "deviation. An owner decision is required: enforce the control, or "
                    "move it to exceptions.active with an ISO-8601 `expires` date and a "
                    "named compensating control. This gate will not treat an open "
                    "finding as accepted."
                ),
            )
        return (
            STATUS_BLOCKED,
            (
                f"{finding_id} is not registered in policy/compliance-gates.yml "
                "exceptions.active — this gate does not invent unapproved exceptions. "
                "Either the control must be enforced, or the owner must record a dated "
                "acceptance."
            ),
        )
    expires = _parse_expiry(entry.get("expires"))
    if expires is None:
        return (
            STATUS_BLOCKED,
            (
                f"{finding_id} carries no ISO-8601 `expires` date, so the acceptance has "
                "no deadline and can stay open indefinitely (the D-25 defect). Add an "
                "expiry, or enforce the control."
            ),
        )
    if expires < today:
        return (
            STATUS_BLOCKED,
            (
                f"{finding_id} LAPSED on {expires.isoformat()}. A lapsed acceptance is "
                "closed by a PR that restates the compensating controls — not by "
                "silence. Re-approve with a new date, or enforce the control."
            ),
        )
    control = str(entry.get("compensating_control") or "(none recorded)")
    if len(control) > _MAX_CONTROL_CHARS:
        # The evidence file is an audit record, not a wall of text. D-33's
        # compensating_control runs to ~1000 characters; a cell that long is
        # unreadable and the authoritative copy stays in the policy file.
        control = control[:_MAX_CONTROL_CHARS].rstrip() + " […]"
    reason = (
        f"{finding_id} accepted until {expires.isoformat()}. Compensating control: "
        f"{control}. Exit trigger: {entry.get('exit_trigger') or '(none recorded)'}. "
        f"Full text: policy/compliance-gates.yml exceptions.active"
    )
    if finding_id in register.open_blocking:
        # A finding in BOTH sections is not a contradiction to resolve silently —
        # the owner uses the open_blocking row to mark a CONDITIONAL acceptance
        # whose compensating controls are not fully stood up (D-33, recorded
        # 2026-09-28). The dated acceptance governs, so this is not BLOCKED; but
        # the conditionality must be visible to whoever relies on it.
        reason += (
            f" — CONDITIONAL: {finding_id} is ALSO listed in exceptions.open_blocking, "
            "which marks an acceptance whose compensating controls are NOT yet fully in "
            "place. Read the outstanding items in the policy file and verify them before "
            "relying on this exception."
        )
    return (STATUS_EXCEPTION, reason)


# ── Local git readers (all read-only) ────────────────────────────────────────


def _git_out(repo: Path, *args: str) -> str:
    status, out, _err = run_read_only(["git", *args], cwd=repo)
    return out.strip() if status == 0 else ""


def current_branch(repo: Path) -> str:
    return _git_out(repo, "rev-parse", "--abbrev-ref", "HEAD")


def default_branch(repo: Path) -> str:
    """Origin's HEAD, falling back to `main`.

    Read from the remote rather than assumed: a repository whose default branch
    is `master` would otherwise be checked against the wrong ref and every
    "am I on the default branch?" test would silently pass.
    """
    ref = _git_out(repo, "symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD")
    if ref and "/" in ref:
        return ref.split("/", 1)[1]
    return "main"


def remote_url(repo: Path) -> str:
    return _git_out(repo, "remote", "get-url", "origin")


def staged_files(repo: Path) -> list[str]:
    out = _git_out(repo, "diff", "--cached", "--name-only")
    return [line for line in out.splitlines() if line.strip()]


def head_sha(repo: Path) -> str:
    return _git_out(repo, "rev-parse", "HEAD")


def gpgsign_enabled(repo: Path) -> bool:
    return _git_out(repo, "config", "--get", "commit.gpgsign").lower() == "true"


def forbidden_staged(staged: list[str]) -> list[str]:
    """Staged paths matching the readiness gate's forbidden-pattern list.

    Reuses rra.FORBIDDEN_TRACKED_PATTERNS so the two gates can never disagree
    about what must never be tracked. D-28 is the precedent: .idea/ and a PyCharm
    scaffold were the only things in the index while every real file was untracked.
    """
    hits: list[str] = []
    for path in staged:
        for pattern in rra.FORBIDDEN_TRACKED_PATTERNS:
            if re.search(pattern, path):
                hits.append(f"{path} ({pattern})")
                break
    return hits


# ── Step implementations ─────────────────────────────────────────────────────


def step_a_verify_first(
    result: StepResult,
    repo_name: str,
    repo: Path,
    readiness: rra.RepoReport,
    snapshot_path: Path,
) -> None:
    """Step A — consume the readiness verdict, then check pipeline-only preconditions.

    Everything structural (governance files, hooks, signing, cleanliness, secrets,
    live settings, protection) is already decided by repo_readiness_audit.py and
    is deliberately NOT re-checked here. This step adds only what the pipeline
    needs and the readiness gate has no opinion about: that the operator is on a
    feature branch, and that a settings snapshot exists for Step F to diff against.
    """
    in_allow_list = not any(f.fid == "R-01" for f in readiness.findings)
    allow_detail = (
        f"repos/{repo_name}.yml present"
        if in_allow_list
        else (
            f"repos/{repo_name}.yml ABSENT — an org repo named jolarca* with no allow-list "
            "entry is an out-of-band creation INCIDENT under ADR-0004 R2 (import within 48h)"
        )
    )
    result.add(
        "allow-list entry",
        STATUS_PASS if in_allow_list else STATUS_BLOCKED,
        allow_detail,
        f"make readiness REPO={repo_name} REPORT=/tmp/{repo_name}-readiness.md",
    )

    if readiness.verdict == rra.VERDICT_READY:
        result.add(
            "readiness verdict",
            STATUS_PASS,
            "READY — no blocking and no non-blocking findings",
        )
    elif readiness.verdict == rra.VERDICT_FIXES:
        blocking = [f.fid for f in readiness.blocking()]
        result.add(
            "readiness verdict",
            STATUS_BLOCKED if blocking else STATUS_EXCEPTION,
            f"READY-WITH-FIXES. Findings: "
            f"{', '.join(f.fid + '/' + f.severity for f in readiness.findings) or '(none)'}",
            f"make readiness REPO={repo_name}",
        )
    else:
        result.add(
            "readiness verdict",
            STATUS_BLOCKED,
            f"{readiness.verdict}. Blocking findings: "
            f"{', '.join(f.fid + '/' + f.severity for f in readiness.blocking()) or '(none)'}; "
            f"unverified: {', '.join(readiness.unverified) or '(none)'}",
            f"make readiness REPO={repo_name}",
        )

    if readiness.unverified:
        result.add(
            "readiness completeness",
            STATUS_UNVERIFIABLE,
            "the readiness gate could not verify: " + "; ".join(readiness.unverified),
        )

    branch = current_branch(repo)
    default = default_branch(repo)
    on_default = branch == default
    result.add(
        "feature branch",
        STATUS_BLOCKED if on_default else STATUS_PASS,
        f"current branch `{branch}`, default branch `{default}`. "
        + (
            "You are ON the default branch. Never commit or push directly to it — "
            "create a feature branch first."
            if on_default
            else "Not the default branch, as required."
        ),
        f"git switch -c feat/{repo_name}-bootstrap" if on_default else "",
    )

    if snapshot_path.exists():
        result.add(
            "settings snapshot",
            STATUS_PASS,
            f"{snapshot_path} present — Step F will diff against it",
        )
    else:
        result.add(
            "settings snapshot",
            STATUS_EXCEPTION,
            f"no snapshot at {snapshot_path}; Step F cannot prove settings were "
            "unchanged. Pass --snapshot on a Step A run to create one.",
        )

    result.command = f"make readiness REPO={repo_name}"


def step_b_commit(
    result: StepResult,
    repo: Path,
    message: str | None,
    register: ExceptionRegister,
    today: date,
) -> None:
    """Step B — verify the commit is safe to make, then print the command."""
    branch = current_branch(repo)
    default = default_branch(repo)
    result.add(
        "not on default branch",
        STATUS_BLOCKED if branch == default else STATUS_PASS,
        f"branch `{branch}` vs default `{default}`",
        "git switch -c feat/bootstrap" if branch == default else "",
    )

    staged = staged_files(repo)
    result.add(
        "staged changes present",
        STATUS_PASS if staged else STATUS_BLOCKED,
        f"{len(staged)} file(s) staged" if staged else "nothing staged — `git add` first",
        "git add -A && git status" if not staged else "",
    )

    forbidden = forbidden_staged(staged)
    result.add(
        "no forbidden paths staged",
        STATUS_BLOCKED if forbidden else STATUS_PASS,
        "; ".join(forbidden) if forbidden else f"none of {len(staged)} staged path(s) forbidden",
        "git restore --staged <path>" if forbidden else "",
    )

    if message:
        subject = conventional_commit_subject(message)
        result.add(
            "Conventional Commits subject",
            STATUS_PASS if subject else STATUS_BLOCKED,
            f"accepted: `{message.splitlines()[0]}`"
            if subject
            else f"rejected: `{message.splitlines()[0]}` — expected "
            "`<type>(<scope>)?: <subject>` with type in "
            "feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert",
        )
    else:
        result.add(
            "Conventional Commits subject",
            STATUS_UNVERIFIABLE,
            "no --message supplied; the commit message was not checked. Pass "
            "--message so the gate can verify the format before you commit.",
        )

    if gpgsign_enabled(repo):
        result.add("commit signing configured", STATUS_PASS, "commit.gpgsign=true")
    else:
        status, reason = exception_state(register, "D-05", today)
        result.add(
            "commit signing configured",
            status,
            f"commit.gpgsign is not true. {reason}",
            "git config --global commit.gpgsign true",
        )

    result.command = (
        f'git commit -S -m "{message.splitlines()[0] if message else "<type>: <subject>"}"'
    )


def step_c_push(
    result: StepResult,
    repo_name: str,
    repo: Path,
    readiness: rra.RepoReport,
    register: ExceptionRegister,
    today: date,
) -> None:
    """Step C — verify the destination, then print the push command."""
    branch = current_branch(repo)
    default = default_branch(repo)
    result.add(
        "not pushing to default branch",
        STATUS_BLOCKED if branch == default else STATUS_PASS,
        f"would push `{branch}`; default is `{default}`",
    )

    url = remote_url(repo)
    expected_suffix = f"{rra.ORG}/{repo_name}.git"
    result.add(
        "remote identity",
        STATUS_PASS if url.endswith(expected_suffix) else STATUS_BLOCKED,
        f"origin = `{url}`"
        + ("" if url.endswith(expected_suffix) else f"; expected *{expected_suffix}"),
        f"git remote set-url origin git@github.com:{expected_suffix}"
        if not url.endswith(expected_suffix)
        else "",
    )

    ahead = _git_out(repo, "rev-list", "--count", f"origin/{default}..HEAD")
    result.add(
        "commits to push",
        STATUS_PASS if ahead and ahead != "0" else STATUS_UNVERIFIABLE,
        f"{ahead} commit(s) ahead of origin/{default}"
        if ahead
        else f"could not compare against origin/{default} — has it been fetched?",
        f"git fetch origin {default}" if not ahead else "",
    )

    # Push protection is the brief's Step C requirement. On the Free plan it is
    # not enforceable on a private repo, so it becomes a tracked exception with
    # its compensating control named — never a silent pass.
    push_protection = (
        readiness.facts.get("live_security", {}).get("secret_scanning_push_protection")
        if isinstance(readiness.facts.get("live_security"), dict)
        else None
    )
    if push_protection is True:
        result.add(
            "push protection",
            STATUS_PASS,
            "secret_scanning_push_protection is enabled — GitHub will reject a "
            "push containing a recognised secret",
        )
    else:
        status, reason = exception_state(register, "D-33", today)
        result.add(
            "push protection",
            status,
            f"push protection is not confirmed enabled (live={push_protection}). "
            f"{reason}. Compensating control for THIS push: gitleaks ran clean in "
            "Step B and the pre-push hook must be installed.",
            "gitleaks detect --source . --log-opts --no-banner",
        )

    result.command = f"git push -u origin {branch}"


def step_d_review(
    result: StepResult,
    repo_name: str,
    branch: str,
    declared: dict[str, Any],
) -> None:
    """Step D — verify the pull request is reviewable."""
    status, pr = gh_json(
        [
            "pr",
            "view",
            branch,
            "--repo",
            f"{rra.ORG}/{repo_name}",
            "--json",
            "number,body,state,mergeable,files,statusCheckRollup,reviewThreads,url",
        ]
    )
    if status != 0 or not isinstance(pr, dict):
        result.add(
            "pull request exists",
            STATUS_UNVERIFIABLE,
            f"`gh pr view {branch}` returned HTTP/exit {status}. No PR, or gh is "
            "not authenticated. Create the PR, then re-run this step.",
            f"gh pr create --repo {rra.ORG}/{repo_name} --base main --head {branch} "
            '--title "<type>: <subject>" --body "<what and why>"',
        )
        result.command = f"gh pr create --repo {rra.ORG}/{repo_name} --base main --head {branch}"
        return

    number = pr.get("number")
    result.add("pull request exists", STATUS_PASS, f"#{number} {pr.get('url')}")

    body = (pr.get("body") or "").strip()
    result.add(
        "description present",
        STATUS_PASS if body else STATUS_BLOCKED,
        f"{len(body)} character(s) of description"
        if body
        else "PR body is empty — a change with no recorded rationale cannot be audited",
        f"gh pr edit {number} --repo {rra.ORG}/{repo_name} --body '<what and why>'"
        if not body
        else "",
    )

    declared_bp = (declared.get("branch_protection") or {}).get("main") or {}
    contexts = (declared_bp.get("required_status_checks") or {}).get("contexts") or []
    rollup = pr.get("statusCheckRollup") or []
    reported = {}
    for check in rollup if isinstance(rollup, list) else []:
        if isinstance(check, dict):
            name = check.get("name") or check.get("context")
            if name:
                reported[str(name)] = check
    if contexts:
        missing = [c for c in contexts if c not in reported]
        failing = [
            name
            for name, check in reported.items()
            if str(check.get("conclusion") or check.get("state") or "").lower()
            not in {"success", "neutral", "skipped", ""}
        ]
        result.add(
            "declared required contexts reported",
            STATUS_BLOCKED if missing else STATUS_PASS,
            f"{len(contexts)} declared; missing: {', '.join(missing) or 'none'}",
        )
        result.add(
            "status checks green",
            STATUS_BLOCKED if failing else STATUS_PASS,
            f"failing: {', '.join(failing) or 'none'}",
        )
    else:
        result.add(
            "declared required contexts reported",
            STATUS_UNVERIFIABLE,
            f"repos/{repo_name}.yml declares no required_status_checks.contexts, so "
            "there is nothing to compare the rollup against. A protected branch with "
            "zero required contexts enforces nothing.",
        )

    files = [f.get("path") for f in (pr.get("files") or []) if isinstance(f, dict)]
    bad = [p for p in files if p and forbidden_staged([str(p)])]
    result.add(
        "no unrelated or forbidden files",
        STATUS_BLOCKED if bad else STATUS_PASS,
        f"{len(files)} file(s) in the diff; forbidden: {', '.join(str(b) for b in bad) or 'none'}",
    )

    result.command = f"gh pr view {number} --repo {rra.ORG}/{repo_name}"


def step_e_merge(
    result: StepResult,
    repo_name: str,
    branch: str,
    policy: dict[str, Any],
    register: ExceptionRegister,
    today: date,
) -> None:
    """Step E — verify the merge preconditions, then print the merge command."""
    status, pr = gh_json(
        [
            "pr",
            "view",
            branch,
            "--repo",
            f"{rra.ORG}/{repo_name}",
            "--json",
            "number,mergeable,mergeStateStatus,reviewDecision,reviewThreads,statusCheckRollup,url",
        ]
    )
    if status != 0 or not isinstance(pr, dict):
        result.add(
            "pull request readable",
            STATUS_UNVERIFIABLE,
            f"`gh pr view {branch}` returned exit {status}; cannot verify merge preconditions",
        )
        return

    number = pr.get("number")
    mergeable = str(pr.get("mergeable") or "").upper()
    result.add(
        "no conflicts",
        STATUS_BLOCKED if mergeable == "CONFLICTING" else STATUS_PASS,
        f"mergeable={pr.get('mergeable')} mergeStateStatus={pr.get('mergeStateStatus')}",
        "git fetch origin && git rebase origin/main" if mergeable == "CONFLICTING" else "",
    )

    rollup = pr.get("statusCheckRollup") or []
    failing = [
        str(check.get("name") or check.get("context"))
        for check in rollup
        if isinstance(check, dict)
        and str(check.get("conclusion") or check.get("state") or "").lower()
        not in {"success", "neutral", "skipped", ""}
    ]
    pending = [
        str(check.get("name") or check.get("context"))
        for check in rollup
        if isinstance(check, dict)
        and str(check.get("conclusion") or "").upper() in {"", "PENDING", "IN_PROGRESS", "QUEUED"}
    ]
    result.add(
        "all status checks green",
        STATUS_BLOCKED if failing else (STATUS_UNVERIFIABLE if pending else STATUS_PASS),
        f"failing: {', '.join(failing) or 'none'}; still running: {', '.join(pending) or 'none'}",
    )

    threads = pr.get("reviewThreads") or []
    unresolved = [t for t in threads if isinstance(t, dict) and not t.get("isResolved")]
    result.add(
        "no unresolved review threads",
        STATUS_BLOCKED if unresolved else STATUS_PASS,
        f"{len(unresolved)} unresolved of {len(threads)} thread(s)",
    )

    required = (
        ((policy.get("branch_protection") or {}).get("main") or {}).get(
            "required_pull_request_reviews"
        )
        or {}
    ).get("required_approving_review_count")
    if isinstance(required, int) and required >= 1:
        decision = str(pr.get("reviewDecision") or "")
        result.add(
            "approvals meet policy",
            STATUS_PASS if decision == "APPROVED" else STATUS_BLOCKED,
            f"policy requires {required} approval(s); reviewDecision={decision or '(none)'}",
        )
    else:
        exc_status, reason = exception_state(register, "D-04", today)
        result.add(
            "approvals meet policy",
            exc_status,
            f"policy requires {required} approvals — a solo-operator deviation. {reason}",
        )

    result.command = f"gh pr merge {number} --repo {rra.ORG}/{repo_name} --squash --delete-branch"


def step_f_verify_again(
    result: StepResult,
    repo_name: str,
    expected_sha: str | None,
    snapshot_path: Path,
    fresh: rra.RepoReport | None,
    attest: str | None,
) -> None:
    """Step F — prove the change landed and nothing else moved."""
    status, runs = gh_json(
        [
            "run",
            "list",
            "--repo",
            f"{rra.ORG}/{repo_name}",
            "--branch",
            "main",
            "--limit",
            "3",
            "--json",
            "databaseId,conclusion,displayTitle,status",
        ]
    )
    if status == 0 and isinstance(runs, list) and runs:
        bad = [
            str(r.get("displayTitle"))
            for r in runs
            if isinstance(r, dict) and str(r.get("conclusion") or "").lower() not in {"success", ""}
        ]
        result.add(
            "CI green on default branch",
            STATUS_BLOCKED if bad else STATUS_PASS,
            f"last {len(runs)} run(s); failing: {', '.join(bad) or 'none'}",
            f"gh run list --repo {rra.ORG}/{repo_name} --branch main",
        )
    else:
        result.add(
            "CI green on default branch",
            STATUS_UNVERIFIABLE,
            f"`gh run list` returned exit {status} with no runs. Either the default "
            "branch has no workflow runs yet or gh is not authenticated.",
        )

    if expected_sha:
        status2, view = gh_json(["api", f"repos/{rra.ORG}/{repo_name}/commits/main"])
        landed = isinstance(view, dict) and str(view.get("sha") or "").startswith(expected_sha[:7])
        result.add(
            "commit landed on default branch",
            STATUS_PASS if landed else STATUS_BLOCKED,
            f"expected {expected_sha[:12]}; main is at "
            f"{str(view.get('sha'))[:12] if isinstance(view, dict) else f'HTTP/exit {status2}'}",
        )
    else:
        result.add(
            "commit landed on default branch",
            STATUS_UNVERIFIABLE,
            "no --expected-sha supplied, so there is nothing to confirm landed",
        )

    if fresh is not None and snapshot_path.exists():
        try:
            before = json.loads(snapshot_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            before = None
        if isinstance(before, dict):
            before_facts = before.get("facts") or {}
            after_facts = fresh.facts
            drifted = sorted(
                key
                for key in set(before_facts) | set(after_facts)
                if before_facts.get(key) != after_facts.get(key)
            )
            result.add(
                "settings unchanged since Step A",
                STATUS_BLOCKED if drifted else STATUS_PASS,
                f"drifted fact(s): {', '.join(drifted) or 'none'}",
                f"make readiness REPO={repo_name}" if drifted else "",
            )
        else:
            result.add(
                "settings unchanged since Step A",
                STATUS_UNVERIFIABLE,
                f"{snapshot_path} is not valid JSON — cannot diff",
            )
    else:
        result.add(
            "settings unchanged since Step A",
            STATUS_UNVERIFIABLE,
            "no Step A snapshot or no fresh readiness report to diff against",
        )

    if attest:
        result.add("operator sign-off", STATUS_PASS, f"attested by: {attest}")
    else:
        result.add(
            "operator sign-off",
            STATUS_BLOCKED,
            "no --attest supplied. The sign-off line is the record that a human "
            "accepted the tracked exceptions in this run; it must not be skipped.",
            '--attest "Full Name"',
        )

    result.command = f"gh run list --repo {rra.ORG}/{repo_name} --branch main --limit 3"


# ── Evidence record ──────────────────────────────────────────────────────────


def render_evidence(report: PipelineReport, attest: str | None, generated: str) -> str:
    """Render the audit record. Committed as evidence, so it must never contain
    a secret value — every detail string in this module is built from counts,
    paths, finding ids and statuses only."""
    lines = [
        f"# First-commit pipeline evidence — {report.repo}",
        "",
        f"Generated: {generated}",
        f"Overall status: **{report.status}**",
        f"Attested by: {attest or '(NOT ATTESTED)'}",
        "",
    ]
    for step in report.steps:
        lines.append(f"## Step {step.step} — {step.title}: {step.status}")
        lines.append("")
        lines.append("| Check | Status | Detail |")
        lines.append("| --- | --- | --- |")
        for check in step.checks:
            detail = check.detail.replace("|", "\\|").replace("\n", " ")
            lines.append(f"| {check.name} | {check.status} | {detail} |")
        lines.append("")
        if step.command:
            lines.append("Command for the operator to run:")
            lines.append("")
            lines.append("```bash")
            lines.append(step.command)
            lines.append("```")
            lines.append("")
    lines.append("## Sign-off")
    lines.append("")
    if attest and report.status in {STATUS_PASS, STATUS_EXCEPTION}:
        lines.append(
            f"- [x] I, {attest}, confirm every step above reached PASS or a "
            "recorded TRACKED-EXCEPTION whose compensating control I verified."
        )
    else:
        lines.append(
            "- [ ] NOT SIGNED OFF — this run is not launch-ready. Resolve every "
            "BLOCKED and UNVERIFIABLE row above, then re-run."
        )
    lines.append("")
    return "\n".join(lines)


# ── Rendering ────────────────────────────────────────────────────────────────


def render_steps(report: PipelineReport) -> str:
    out: list[str] = [f"Pipeline {report.repo} — {report.status}", ""]
    for step in report.steps:
        out.append(f"Step {step.step} · {step.title}: {step.status}")
        for check in step.checks:
            out.append(f"    [{check.status}] {check.name}: {check.detail}")
            if check.command:
                out.append(f"        → {check.command}")
        if step.command:
            out.append(f"  RUN: {step.command}")
        out.append("")
    return "\n".join(out)


# ── Orchestration ────────────────────────────────────────────────────────────


def run_pipeline(
    repo_name: str,
    steps: tuple[str, ...],
    *,
    message: str | None = None,
    attest: str | None = None,
    strict: bool = False,
    live: bool = True,
    snapshot: bool = False,
    snapshot_path: Path | None = None,
    evidence_path: Path | None = None,
    expected_sha: str | None = None,
    readiness: rra.RepoReport | None = None,
    fresh: rra.RepoReport | None = None,
) -> tuple[PipelineReport, int]:
    """Execute the requested steps in order and return (report, exit code)."""
    policy = rra.load_yaml(rra.POLICY_DEFAULTS)
    gates = rra.load_yaml(rra.POLICY_GATES)
    register = load_register(gates)
    today = datetime.now(UTC).date()

    repo_root = rra.LOCAL_ROOT / repo_name
    report = PipelineReport(repo=repo_name)
    declared = rra.get_defined_repos().get(repo_name) or {}

    if readiness is None:
        org_findings: list[rra.Finding] = []
        if live:
            org_findings, _org_facts, _unverified = rra.check_org(policy)
        patterns = rra.secret_patterns(gates)
        defined = rra.get_defined_repos()
        readiness = rra.audit_repo(repo_name, defined, policy, patterns, org_findings, live)
        readiness.decide()

    snap_path = snapshot_path or Path(f"/tmp/{repo_name}-readiness-snapshot.json")

    for step_id in steps:
        result = report.step(step_id)

        # Prerequisite enforcement: a step cannot be entered on the strength of
        # an earlier step that did not pass in THIS run.
        missing = [p for p in PREREQUISITES[step_id] if p not in steps]
        blocked_by = [
            p
            for p in PREREQUISITES[step_id]
            if p in steps and (prior := report.get(p)) is not None and not prior.passed
        ]
        if missing:
            result.add(
                "prerequisites",
                STATUS_BLOCKED,
                f"step {step_id} requires {', '.join(missing)} to run first; "
                f"pass --step all or run them in order",
            )
            continue
        if blocked_by:
            for prior_id in blocked_by:
                prior = report.get(prior_id)
                assert prior is not None  # guaranteed by the comprehension above
                result.add(
                    "prerequisites",
                    STATUS_BLOCKED,
                    f"step {prior_id} ({prior.title}) did not pass — status {prior.status}. "
                    "STOP: fix it before continuing.",
                )
            continue

        if step_id == STEP_A:
            step_a_verify_first(result, repo_name, repo_root, readiness, snap_path)
            if snapshot:
                snap_path.write_text(
                    json.dumps(
                        {"repo": repo_name, "verdict": readiness.verdict, "facts": readiness.facts},
                        indent=2,
                    ),
                    encoding="utf-8",
                )
                result.add("snapshot written", STATUS_PASS, str(snap_path))
        elif step_id == STEP_B:
            step_b_commit(result, repo_root, message, register, today)
        elif step_id == STEP_C:
            step_c_push(result, repo_name, repo_root, readiness, register, today)
        elif step_id == STEP_D:
            step_d_review(result, repo_name, current_branch(repo_root), declared)
        elif step_id == STEP_E:
            step_e_merge(result, repo_name, current_branch(repo_root), policy, register, today)
        elif step_id == STEP_F:
            step_f_verify_again(result, repo_name, expected_sha, snap_path, fresh, attest)

    if strict:
        # --strict is the post-upgrade posture: a compensating control is no
        # longer an acceptable substitute for the real one.
        for step in report.steps:
            for check in step.checks:
                if check.status == STATUS_EXCEPTION:
                    check.status = STATUS_BLOCKED
                    check.detail += " [--strict: tracked exceptions are refused]"

    if evidence_path is not None:
        generated = datetime.now(UTC).isoformat(timespec="seconds")
        evidence_path.write_text(render_evidence(report, attest, generated), encoding="utf-8")

    status = report.status
    if status == STATUS_UNVERIFIABLE:
        return report, 2
    if status == STATUS_PASS:
        return report, 0
    return report, 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Phase 3 first-commit pipeline gate (read-only; prints commands)."
    )
    parser.add_argument("--repo", required=True, help="repository name as it appears in repos/")
    parser.add_argument(
        "--step",
        default="all",
        help="A|B|C|D|E|F or 'all' (default: all)",
    )
    parser.add_argument(
        "--message", help="proposed commit message, verified against Conventional Commits"
    )
    parser.add_argument("--attest", help="operator name for the Step F sign-off record")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="refuse tracked exceptions — the posture to adopt once GitHub Team lands",
    )
    parser.add_argument("--no-live", action="store_true", help="skip GitHub API checks")
    parser.add_argument(
        "--snapshot", action="store_true", help="write the Step A settings snapshot"
    )
    parser.add_argument("--snapshot-path", help="override the snapshot location")
    parser.add_argument("--evidence", help="write the markdown audit record to this path")
    parser.add_argument("--expected-sha", help="commit SHA Step F must confirm landed on main")
    parser.add_argument("--quiet", action="store_true", help="suppress the stderr summary")
    args = parser.parse_args()

    requested = STEP_ORDER if args.step.lower() == "all" else (args.step.upper(),)
    unknown = [s for s in requested if s not in STEP_ORDER]
    if unknown:
        print(f"ERROR: unknown step(s): {', '.join(unknown)}", file=sys.stderr)
        return 2

    snapshot_path = Path(args.snapshot_path) if args.snapshot_path else None
    evidence_path = Path(args.evidence) if args.evidence else None

    try:
        report, code = run_pipeline(
            args.repo,
            requested,
            message=args.message,
            attest=args.attest,
            strict=args.strict,
            live=not args.no_live,
            snapshot=args.snapshot,
            snapshot_path=snapshot_path,
            evidence_path=evidence_path,
            expected_sha=args.expected_sha,
        )
    except ReadOnlyViolation as exc:
        # Reaching this branch means the allowlist itself was bypassed by a code
        # change. Fail closed and loudly; never continue the pipeline.
        print(f"FATAL: read-only invariant violated: {exc}", file=sys.stderr)
        return 2

    if not args.quiet:
        print(render_steps(report), file=sys.stderr)
        if evidence_path is not None:
            print(f"evidence: {evidence_path}", file=sys.stderr)

    print(json.dumps({"repo": report.repo, "status": report.status, "exit": code}, indent=2))
    return code


if __name__ == "__main__":
    sys.exit(main())
