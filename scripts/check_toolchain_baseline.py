#!/usr/bin/env python3
"""toolchain_baseline.py — one approved toolchain answer, and a check for who diverges.

jolarca-control — marketplace (jolarca-dev) governance control plane.
SOC 2 CC8.1 / CC7.1 · ISO/IEC 27001 A.8.19, A.8.32, A.5.20 · GDPR Art. 32(1)(b)

WHY THIS EXISTS (ADR-0010 M-06, measured 2026-11-03)
---------------------------------------------------------------------------
Per-repository mise configuration is the right decision, and it has a cost this
repository could not previously see: seventeen independent lockfiles with no single
answer to "which Python is approved, and who disagrees". Measured on default
branches the same day, the divergence is not hypothetical — 1 of 17 repositories
carries any mise configuration at all, and the other 16 carry none. Nothing
detected that; the state was assembled by hand from `gh api` output in a chat.

A centralised catalogue alone would be documentation, not a control. This script is
the part that makes it one.

RULES
---------------------------------------------------------------------------
Catalogue self-check, always run, offline and deterministic:
  C1  every approved tool names version, backend, upstream, verification,
      reviewed_by, reviewed_on and review_due. An approval without an owner and a
      deadline is a preference.
  C2  `exact: true` requires a full release, at least three dot-separated numeric
      components. "3.12" and "22" are version REQUESTS: mise resolves them against
      whatever the index offers at install time, which is the moving target the
      whole exercise exists to remove.
  C3  review_due must be in the future. An expired approval is a finding, not a
      hint — this is the same reasoning docs/security/key-custody.md applies to
      credential expiry.
  C4  the mise action pin is a full 40-hex commit and the binary digest is 64 hex.
      These are three different objects (action, release, artifact) and each needs
      its own pin.
  C5  supported_platforms is non-empty, and every binary_sha256 key is one of them.
      A lockfile for linux-x64 says nothing about Apple Silicon (M-05).
  C6  every exception names a repo, a reason, and an expiry in the future, and its
      `covers` list names the rules it actually excuses.
  C7  a duplicated YAML key is a finding. yaml.safe_load silently keeps the LAST
      duplicate, so `python:` twice does not error — it quietly deletes an approval.
  C8  every `workflow_exceptions` entry names a file, a reason, an expiry and the
      rules it covers.

Runtime check, always run, offline and deterministic (M-10):
  R8  every `actions/setup-python` step must declare `python-version` equal to the
      approved release, and every `hashicorp/setup-terraform` step must declare
      `terraform_version` equal to it. A prefix such as `"3.12"` is a request: the
      hosted runner answers it with whatever its image ships. Measured 2026-11-03 —
      the same unchanged declarations produced 3.12.15 on one run and 3.12.16 an
      hour later. Absent is worse: the version is then whatever the action defaults
      to, which is announced nowhere.

Fleet check, run against a real source (--live or --from-dir):
  L1  a declared tool absent from the catalogue and not overridden for that repo
  L2  a declared version that differs from the approved one
  L3  a declared version that is a prefix rather than a release
  L4  mise.toml present with no mise.lock — the pin is unverified
  L5  mise.toml present with no .miserc.toml — config discovery is unbounded, so a
      stray parent mise.toml merges tools into that repository and into no CI
      runner (M-01). Reported here because M-01's fix is a file, and only a gate
      makes its absence visible.
  L6  an exception whose expiry has passed
  L7  a repository in scope that could not be read

EXIT CODES (AGENTS.md §3 — never a silent pass)
  0  catalogue is coherent, and (when a source is given) no divergence
  1  findings — a real refusal
  2  could not verify — unreadable catalogue, unreadable repository, empty scope,
     or a live run with no `gh`. An unreachable API is 2, not 0.

The live mode is deliberately NOT wired into a required status check. It cannot go
green today, and a required context that cannot be satisfied wedges every pull
request in the repository including the ones that would fix it (D-90). Run it with
`make toolchain-baseline`.
"""

from __future__ import annotations

import argparse
import base64
import datetime
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CATALOGUE = REPO_ROOT / "docs" / "security" / "toolchain-catalogue.yml"
ORG = "jolarca-dev"

# A release, not a request: three or more dot-separated numeric components.
EXACT_VERSION = re.compile(r"^\d+\.\d+\.\d+(?:\.\d+)*$")
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
TOOLS_SECTION = re.compile(r"^\[tools\]\s*(?:#.*)?$")
NEXT_SECTION = re.compile(r"^\s*\[")
DECLARED_LINE = re.compile(r'^\s*(?P<name>[A-Za-z_][\w.-]*)\s*=\s*"(?P<version>[^"]*)"')


def duplicate_keys(text: str) -> list[str]:
    """Find mapping keys written twice in the catalogue.

    yaml keeps the LAST duplicate and does not warn, so a catalogue with `python:`
    twice reads as one approval rather than two, and the second silently deletes the
    first — an approval record that can be overwritten by appending to it. Detection
    is a separate pass over the composed node tree because the constructor subclass
    that would catch it fights the types-PyYAML stubs, and a gate whose own typing is
    hand-waved is not a gate.
    """
    root = yaml.compose(text)
    if root is None:
        return []
    found: list[str] = []
    stack: list[Any] = [root]
    while stack:
        node = stack.pop()
        if isinstance(node, yaml.MappingNode):
            seen: set[str] = set()
            for key_node, value_node in node.value:
                name = str(key_node.value)
                if name in seen:
                    found.append(f"{name!r} at line {key_node.start_mark.line + 1}")
                seen.add(name)
                stack.extend([key_node, value_node])
        elif isinstance(node, yaml.SequenceNode):
            stack.extend(node.value)
    return found


def isodate(value: Any) -> datetime.date | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.date.fromisoformat(value)
    except ValueError:
        return None


def parse_declared_tools(text: str) -> dict[str, str]:
    """Read the [tools] table out of a mise.toml.

    Deliberately not a TOML parse: the live path feeds remote text that may be
    anything, and the only question is which name/version pairs the [tools] section
    requests. A real parser would also accept [tools] written after [tasks], which
    mise itself would not.
    """
    declared: dict[str, str] = {}
    inside = False
    for line in text.splitlines():
        if TOOLS_SECTION.match(line):
            inside = True
            continue
        if inside and NEXT_SECTION.match(line):
            break
        if not inside:
            continue
        match = DECLARED_LINE.match(line)
        if match:
            declared[match.group("name")] = match.group("version")
    return declared


def catalogue_errors(cat: dict[str, Any], today: datetime.date) -> list[str]:
    errors: list[str] = []
    mise_raw = cat.get("mise")
    mise: dict[str, Any] = mise_raw if isinstance(mise_raw, dict) else {}
    if not isinstance(mise_raw, dict):
        errors.append("C1: no `mise:` block — the trust root is unrecorded")
    else:
        commit = mise.get("action_commit")
        if not isinstance(commit, str) or not FULL_SHA.match(commit):
            errors.append(f"C4: mise.action_commit is not a full 40-hex SHA: {commit!r}")
        digests = mise.get("binary_sha256")
        if not isinstance(digests, dict) or not digests:
            errors.append("C4: mise.binary_sha256 names no artifact digest")
        else:
            for platform, digest in sorted(digests.items()):
                if not isinstance(digest, str) or not SHA256.match(digest):
                    errors.append(f"C4: mise.binary_sha256[{platform!r}] is not 64 hex")
    platforms = cat.get("supported_platforms")
    if not isinstance(platforms, list) or not platforms:
        errors.append("C5: supported_platforms is empty — portability is unclaimed")
    else:
        digests_raw = mise.get("binary_sha256")
        if isinstance(digests_raw, dict):
            digest_platforms = {str(key) for key in digests_raw}
            for platform in sorted(digest_platforms - {str(p) for p in platforms}):
                errors.append(f"C5: binary_sha256[{platform!r}] is not a supported platform")
    due = isodate(cat.get("review_due"))
    if due is None:
        errors.append("C3: catalogue has no parseable review_due")
    elif due <= today:
        errors.append(f"C3: catalogue approval expired {due.isoformat()} — re-review required")
    tools_raw = cat.get("tools")
    tools: dict[str, Any] = tools_raw if isinstance(tools_raw, dict) else {}
    if not isinstance(tools_raw, dict) or not tools:
        errors.append("C1: no approved tools — the catalogue answers nothing")
    else:
        for name, entry in sorted(tools.items()):
            if not isinstance(entry, dict):
                errors.append(f"C1: tools.{name} is not a mapping")
                continue
            for field in (
                "version",
                "backend",
                "upstream",
                "verification",
                "reviewed_by",
                "reviewed_on",
                "review_due",
            ):
                if not entry.get(field):
                    errors.append(f"C1: tools.{name} omits {field}")
            version = entry.get("version")
            if entry.get("exact") and (
                not isinstance(version, str) or not EXACT_VERSION.match(version)
            ):
                errors.append(f"C2: tools.{name} claims exact but is a request: {version!r}")
            entry_due = isodate(entry.get("review_due"))
            if entry_due is not None and entry_due <= today:
                errors.append(f"C3: tools.{name} approval expired {entry_due.isoformat()}")
    for index, exception in enumerate(cat.get("exceptions") or []):
        if not isinstance(exception, dict):
            errors.append(f"C6: exceptions[{index}] is not a mapping")
            continue
        for field in ("repo", "reason", "expires"):
            if not exception.get(field):
                errors.append(f"C6: exceptions[{index}] omits {field}")
        if not isinstance(exception.get("covers"), list):
            errors.append(
                f"C6: exceptions[{index}] omits covers — an exception must name the rules "
                "it excuses, or it pardons every rule"
            )
        expires = isodate(exception.get("expires"))
        if expires is not None and expires <= today:
            errors.append(
                f"C6: exceptions[{index}] ({exception.get('repo')!r}) expired {expires.isoformat()}"
            )
    for index, exception in enumerate(cat.get("workflow_exceptions") or []):
        if not isinstance(exception, dict):
            errors.append(f"C8: workflow_exceptions[{index}] is not a mapping")
            continue
        for field in ("file", "reason", "expires"):
            if not exception.get(field):
                errors.append(f"C8: workflow_exceptions[{index}] omits {field}")
        if not isinstance(exception.get("covers"), list):
            errors.append(
                f"C8: workflow_exceptions[{index}] omits covers — an exception must name the "
                "rules it excuses, or it pardons every rule"
            )
        expires = isodate(exception.get("expires"))
        if expires is not None and expires <= today:
            errors.append(
                f"C8: workflow_exceptions[{index}] ({exception.get('file')!r}) expired "
                f"{expires.isoformat()}"
            )
    return errors


RUNTIME_ACTIONS = {
    "actions/setup-python": ("python-version", "python"),
    "hashicorp/setup-terraform": ("terraform_version", "terraform"),
}


def runtime_errors(cat: dict[str, Any], workflows_dir: Path, repo: str) -> tuple[list[str], int]:
    """R8: the interpreter a required check runs on must be the approved release.

    Returns (findings, steps_examined). The count is the non-vacuity guard: a glob
    that matched nothing would otherwise report a clean pass over zero files, and
    this repository has been fooled by that shape three times already.
    """
    findings: list[str] = []
    tools_raw = cat.get("tools")
    tools: dict[str, Any] = tools_raw if isinstance(tools_raw, dict) else {}
    approved: dict[str, str] = {}
    for name, entry in tools.items():
        if not isinstance(entry, dict):
            continue
        approved[name] = str(entry.get("version", ""))
        per = entry.get("per_repository_overrides")
        if isinstance(per, dict) and repo in per:
            approved[name] = str(per[repo])

    exc: dict[str, set[str]] = {}
    for item in cat.get("workflow_exceptions") or []:
        if isinstance(item, dict) and isinstance(item.get("covers"), list):
            exc[str(item.get("file"))] = {str(rule) for rule in item["covers"]}

    examined = 0
    for path in sorted(workflows_dir.glob("*.yml")):
        covered = exc.get(f".github/workflows/{path.name}", set())
        try:
            doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as parse_error:
            findings.append(f"R8: {path.name}: could not be parsed ({parse_error})")
            continue
        if not isinstance(doc, dict):
            continue
        jobs = doc.get("jobs")
        if not isinstance(jobs, dict):
            continue
        for job_id, job in jobs.items():
            if not isinstance(job, dict):
                continue
            for step in job.get("steps") or []:
                if not isinstance(step, dict) or not isinstance(step.get("uses"), str):
                    continue
                ref = step["uses"].split("@", 1)[0]
                spec = RUNTIME_ACTIONS.get(ref)
                if spec is None:
                    continue
                field, tool = spec
                examined += 1
                if "R8" in covered:
                    continue
                with_block = step.get("with")
                value = with_block.get(field) if isinstance(with_block, dict) else None
                want = approved.get(tool)
                if value is None:
                    findings.append(
                        f"R8: {path.name}:{job_id} runs {ref} with no {field}; the version "
                        "is whatever the action defaults to and is announced nowhere"
                    )
                elif not want or str(value) != want:
                    findings.append(
                        f"R8: {path.name}:{job_id} declares {tool} {value!r}, approved is "
                        f"{want!r}; a prefix is a request, not a release"
                    )
    return findings, examined


def declared_scope() -> list[str]:
    """The fleet this catalogue governs: every declared repo plus the org defaults repo.

    `.github` is absent from repos/*.yml — it sits outside the allow-list entirely —
    but it is a real repository with real workflows, so it is in scope here. That gap
    is recorded rather than smoothed over.
    """
    repos_dir = REPO_ROOT / "repos"
    if not repos_dir.is_dir():
        return []
    names = sorted(path.stem for path in repos_dir.glob("*.yml"))
    if ".github" not in names:
        names.append(".github")
    return names


def fetch_live(repo: str) -> dict[str, str | None]:
    """Read one repository's default-branch toolchain files through `gh`."""
    branch = subprocess.run(
        ["gh", "api", f"repos/{ORG}/{repo}", "--jq", ".default_branch"],
        capture_output=True,
        text=True,
    )
    if branch.returncode != 0:
        return {"error": f"cannot read default branch for {repo}"}
    ref = branch.stdout.strip()
    out: dict[str, str | None] = {"error": None}
    for key, path in (
        ("mise.toml", "mise.toml"),
        ("mise.lock", "mise.lock"),
        (".miserc.toml", ".miserc.toml"),
    ):
        read = subprocess.run(
            ["gh", "api", f"repos/{ORG}/{repo}/contents/{path}?ref={ref}", "--jq", ".content"],
            capture_output=True,
            text=True,
        )
        if read.returncode != 0 or not read.stdout.strip():
            out[key] = None
            continue
        out[key] = base64.b64decode(read.stdout.strip()).decode("utf-8", "replace")
    return out


def fetch_from_dir(root: Path, repo: str) -> dict[str, str | None]:
    """Same shape as fetch_live, from a local fixture directory. No network, no gh."""
    base = root / repo
    out: dict[str, str | None] = {"error": None}
    for key in ("mise.toml", "mise.lock", ".miserc.toml"):
        candidate = base / key
        out[key] = candidate.read_text(encoding="utf-8") if candidate.is_file() else None
    if out["mise.toml"] is None and not base.is_dir():
        out["error"] = f"{repo}: fixture directory absent"
    return out


def fleet_errors(
    states: dict[str, dict[str, str | None]], cat: dict[str, Any], today: datetime.date
) -> tuple[list[str], list[str]]:
    """Return (findings, unverifiable).

    The split is the point. A repository whose API call failed is not a finding — it
    is the absence of evidence, and reporting it as a finding would let a run where
    every read failed look like a run with an explained verdict. AGENTS.md §3 makes
    that exit 2.
    """
    errors: list[str] = []
    unverifiable: list[str] = []
    tools_raw = cat.get("tools")
    tools: dict[str, Any] = tools_raw if isinstance(tools_raw, dict) else {}
    approved = {
        name: str(entry.get("version")) for name, entry in tools.items() if isinstance(entry, dict)
    }
    overrides: dict[str, dict[str, str]] = {}
    for name, entry in tools.items():
        if isinstance(entry, dict):
            per = entry.get("per_repository_overrides")
            if isinstance(per, dict):
                for repo, version in per.items():
                    overrides.setdefault(str(repo), {})[name] = str(version)
    exception_rules: dict[str, set[str]] = {}
    for item in cat.get("exceptions") or []:
        if not isinstance(item, dict):
            continue
        repo = str(item.get("repo"))
        covers = item.get("covers")
        # An exception without `covers` excuses nothing. The alternative — treating a
        # bare repo name as a blanket pardon — is the off-switch defect this register
        # already documents elsewhere (an exception that also silences an unrelated
        # rule is not an exception, it is a blindfold). jolarca-security is the live
        # example: its recorded reason explains why the CI PROOF cannot run, and says
        # nothing about why the configuration is absent from its default branch.
        if isinstance(covers, list) and repo:
            exception_rules[repo] = {str(rule) for rule in covers}
    for repo, state in sorted(states.items()):
        if state.get("error"):
            unverifiable.append(f"L7: {repo}: {state['error']}")
            continue
        config = state.get("mise.toml")
        if config is None:
            if "L1" not in exception_rules.get(repo, set()):
                errors.append(f"L1: {repo}: no mise.toml on its default branch — not adopted")
            continue
        declared = parse_declared_tools(config)
        if not declared and "L1" not in exception_rules.get(repo, set()):
            errors.append(f"L1: {repo}: mise.toml declares no tools")
        for name, version in sorted(declared.items()):
            allowed = overrides.get(repo, {}).get(name, approved.get(name))
            if allowed is None:
                if "L1" not in exception_rules.get(repo, set()):
                    errors.append(
                        f"L1: {repo}: declares {name} {version}, which the catalogue does not approve"
                    )
                continue
            if version != allowed and "L2" not in exception_rules.get(repo, set()):
                errors.append(f"L2: {repo}: declares {name} {version}, approved is {allowed}")
            if not EXACT_VERSION.match(version) and "L3" not in exception_rules.get(repo, set()):
                errors.append(f"L3: {repo}: {name} {version} is a request, not a release")
        if state.get("mise.lock") is None and "L4" not in exception_rules.get(repo, set()):
            errors.append(f"L4: {repo}: mise.toml with no mise.lock — the pin is unverified")
        if state.get(".miserc.toml") is None and "L5" not in exception_rules.get(repo, set()):
            errors.append(
                f"L5: {repo}: mise.toml with no .miserc.toml — config discovery is unbounded (M-01)"
            )
    return errors, unverifiable


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    parser.add_argument("--catalogue", type=Path, default=DEFAULT_CATALOGUE)
    parser.add_argument(
        "--live", action="store_true", help="read the fleet through gh (needs a token)"
    )
    parser.add_argument(
        "--from-dir", type=Path, default=None, help="read the fleet from local fixtures"
    )
    parser.add_argument(
        "--scope",
        default=None,
        help="comma-separated repository names, overriding the repos/ allow-list (for tests)",
    )
    parser.add_argument(
        "--workflows-dir",
        type=Path,
        default=REPO_ROOT / ".github" / "workflows",
        help="workflow directory to apply R8 to (for tests)",
    )
    parser.add_argument(
        "--repo",
        default=REPO_ROOT.name,
        help="repository name whose per-repo overrides apply (for tests)",
    )
    parser.add_argument("--today", default=None, help="override the clock (ISO date, for tests)")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)

    today = datetime.date.fromisoformat(args.today) if args.today else datetime.date.today()

    try:
        raw = args.catalogue.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"CANNOT VERIFY: catalogue unreadable at {args.catalogue}: {exc}", file=sys.stderr)
        return 2
    try:
        cat = yaml.load(raw, Loader=yaml.SafeLoader)
    except yaml.YAMLError as exc:
        print(f"CANNOT VERIFY: catalogue is not well-formed YAML: {exc}", file=sys.stderr)
        return 2
    if not isinstance(cat, dict):
        print("CANNOT VERIFY: catalogue did not parse to a mapping", file=sys.stderr)
        return 2
    dupes = duplicate_keys(raw)
    if dupes:
        print(
            "CANNOT VERIFY: duplicate mapping key(s) in the catalogue — yaml keeps the last "
            f"and silently drops the earlier: {', '.join(dupes)}",
            file=sys.stderr,
        )
        return 2

    errors = catalogue_errors(cat, today)
    unverifiable: list[str] = []

    runtime_findings, examined = runtime_errors(cat, args.workflows_dir, args.repo)
    errors.extend(runtime_findings)

    # Non-vacuity: the catalogue approves runtimes, so if no step that consumes them
    # was found, R8 graded nothing and its silence is not a pass. A zero from a probe
    # that cannot return non-zero is the failure mode AGENTS.md §3 exists to forbid.
    approved_tools_raw = cat.get("tools")
    approved_tools: dict[str, Any] = (
        approved_tools_raw if isinstance(approved_tools_raw, dict) else {}
    )
    approved_runtimes = [name for name in ("python", "terraform") if name in approved_tools]
    if approved_runtimes and examined == 0:
        print(
            f"CANNOT VERIFY: catalogue approves {', '.join(approved_runtimes)} but no "
            f"setup-python or setup-terraform step was found under {args.workflows_dir}; "
            "R8 examined nothing, so its silence is not evidence",
            file=sys.stderr,
        )
        return 2

    if args.live or args.from_dir is not None:
        scope = [name.strip() for name in args.scope.split(",")] if args.scope else declared_scope()
        if not scope:
            print("CANNOT VERIFY: repos/ allow-list produced no scope", file=sys.stderr)
            return 2
        if args.live and shutil.which("gh") is None:
            print("CANNOT VERIFY: --live needs the gh CLI and it is not installed", file=sys.stderr)
            return 2
        states: dict[str, dict[str, str | None]] = {}
        for repo in scope:
            states[repo] = (
                fetch_live(repo) if args.live else fetch_from_dir(args.from_dir or Path("."), repo)
            )
        if len(states) < len(scope):
            print("CANNOT VERIFY: scope shrank between listing and reading", file=sys.stderr)
            return 2
        fleet_findings, fleet_unverifiable = fleet_errors(states, cat, today)
        errors.extend(fleet_findings)
        unverifiable.extend(fleet_unverifiable)

    if args.as_json:
        print(
            json.dumps(
                {
                    "catalogue": str(args.catalogue),
                    "runtime_steps_examined": examined,
                    "findings": errors,
                    "unverifiable": unverifiable,
                },
                indent=2,
            )
        )
    else:
        for line in errors:
            print(line)
        for line in unverifiable:
            print(line, file=sys.stderr)

    if unverifiable:
        print(
            f"CANNOT VERIFY: {len(unverifiable)} repository(s) could not be read; "
            f"{len(errors)} finding(s) are reported but the scope is not complete",
            file=sys.stderr,
        )
        return 2
    if errors:
        print(f"FAIL: {len(errors)} finding(s)", file=sys.stderr)
        return 1
    print(
        f"OK: catalogue coherent ({args.catalogue.name}); {len(cat.get('tools') or {})} "
        f"approved tool(s); {examined} workflow runtime step(s) examined against the "
        "approved releases"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
