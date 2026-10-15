"""Negative controls for scripts/check_required_context_baseline.py (D-62).

The rule this suite exists to enforce is AGENTS.md §7: a gate that has never been
shown to fail is a hypothesis. Each case below asserts a specific refusal, and two
assert the gate does NOT fire where firing would make it noise (a no-op pass and a
null-valued `pull_request:` trigger, which is the repo's common shape).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import yaml

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "check_required_context_baseline.py"
REPO_ROOT = SCRIPT.parent.parent
REAL_NAMES = [
    "Validate Repo Allow-List",
    "Policy Compliance Check",
    "Repository Secret Pattern Scan",
    "SAST (semgrep)",
]


def _gate() -> Any:
    spec = importlib.util.spec_from_file_location("check_required_context_baseline", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _policy(contexts: list[str]) -> str:
    return yaml.safe_dump(
        {
            "required_checks": {
                "control_plane": [{"context": c, "description": "d"} for c in contexts]
            }
        }
    )


def _repo_file(contexts: list[str]) -> str:
    return yaml.safe_dump(
        {"branch_protection": {"main": {"required_status_checks": {"contexts": contexts}}}}
    )


def _workflows(tmp_path: Path, names: list[str], *, path_filtered: bool = False) -> Path:
    d = tmp_path / "workflows"
    d.mkdir(parents=True, exist_ok=True)
    trigger: Any = {"paths": ["repos/**"]} if path_filtered else None
    body = {"name": "CI", "on": {"pull_request": trigger}, "jobs": {}}
    for i, name in enumerate(names):
        body["jobs"][f"job{i}"] = {
            "name": name,
            "runs-on": "ubuntu-latest",
            "steps": [{"run": "true"}],
        }
    (d / "ci.yml").write_text(yaml.safe_dump(body), encoding="utf-8")
    return d


def _wire(
    monkeypatch: Any,
    mod: Any,
    tmp_path: Path,
    *,
    policy: list[str],
    declared: list[str],
    workflow_names: list[str],
    path_filtered: bool = False,
) -> None:
    (tmp_path / "policy").mkdir(exist_ok=True)
    (tmp_path / "repos").mkdir(exist_ok=True)
    policy_path = tmp_path / "policy" / "repo-defaults.yml"
    policy_path.write_text(_policy(policy), encoding="utf-8")
    repo_path = tmp_path / "repos" / "jolarca-control.yml"
    repo_path.write_text(_repo_file(declared), encoding="utf-8")
    monkeypatch.setattr(mod, "POLICY_PATH", policy_path)
    monkeypatch.setattr(mod, "REPO_PATH", repo_path)
    monkeypatch.setattr(
        mod, "WORKFLOW_DIR", _workflows(tmp_path, workflow_names, path_filtered=path_filtered)
    )


def test_real_repository_baseline_matches_its_declaration() -> None:
    """The regression D-62 was: this must stay true, not be assumed true."""
    mod = _gate()
    assert mod.baseline_contexts() == REAL_NAMES
    assert mod.declared_contexts() == REAL_NAMES
    problems, _ = mod.check()
    assert problems == [], problems


def test_missing_context_in_baseline_is_a_failure(monkeypatch: Any, tmp_path: Path) -> None:
    mod = _gate()
    _wire(
        monkeypatch,
        mod,
        tmp_path,
        policy=REAL_NAMES[:3],
        declared=REAL_NAMES,
        workflow_names=REAL_NAMES,
    )
    problems, _ = mod.check()
    assert any("omits" in p and "SAST (semgrep)" in p for p in problems), problems


def test_unreportable_context_name_is_a_failure(monkeypatch: Any, tmp_path: Path) -> None:
    """The exact D-62 defect: a baseline naming a job that no workflow reports."""
    mod = _gate()
    bad = [*REAL_NAMES[:3], "Fleet Separation Guard"]
    _wire(monkeypatch, mod, tmp_path, policy=bad, declared=REAL_NAMES, workflow_names=REAL_NAMES)
    problems, _ = mod.check()
    assert any("does not declare" in p for p in problems), problems
    assert any("Fleet Separation Guard" in p and "no pull_request event" in p for p in problems), (
        problems
    )


def test_empty_baseline_refuses_to_pass(monkeypatch: Any, tmp_path: Path) -> None:
    mod = _gate()
    _wire(monkeypatch, mod, tmp_path, policy=[], declared=REAL_NAMES, workflow_names=REAL_NAMES)
    problems, _ = mod.check()
    assert any("empty" in p for p in problems), problems


def test_path_filtered_workflow_cannot_back_a_required_context(
    monkeypatch: Any, tmp_path: Path
) -> None:
    """A name only produced under a paths filter cannot be required: under
    strict:true it deadlocks every PR that does not touch those paths (D-44)."""
    mod = _gate()
    _wire(
        monkeypatch,
        mod,
        tmp_path,
        policy=REAL_NAMES,
        declared=REAL_NAMES,
        workflow_names=REAL_NAMES,
        path_filtered=True,
    )
    problems, _ = mod.check()
    assert any("no pull_request event" in p for p in problems), problems


def test_null_pull_request_options_still_count_as_producible(
    monkeypatch: Any, tmp_path: Path
) -> None:
    """`pull_request:` with no value parses to None and means 'no options'.
    Reading it as absent made the gate invent four findings on a healthy repo."""
    mod = _gate()
    _wire(
        monkeypatch,
        mod,
        tmp_path,
        policy=REAL_NAMES,
        declared=REAL_NAMES,
        workflow_names=REAL_NAMES,
    )
    assert mod.pr_producible_names()[0] == set(REAL_NAMES)
    assert mod.check()[0] == []


def test_missing_input_is_cannot_verify_not_a_pass(monkeypatch: Any, tmp_path: Path) -> None:
    mod = _gate()
    monkeypatch.setattr(mod, "POLICY_PATH", tmp_path / "absent.yml")
    assert mod.main() == 2


def test_unparseable_yaml_is_cannot_verify(monkeypatch: Any, tmp_path: Path) -> None:
    mod = _gate()
    bad = tmp_path / "policy.yml"
    bad.write_text("required_checks: [unclosed", encoding="utf-8")
    monkeypatch.setattr(mod, "POLICY_PATH", bad)
    assert mod.main() == 2


def test_script_is_wired_into_a_workflow() -> None:
    """A gate nobody runs is folklore. It must be a step in a job that is itself
    a required context — 'Validate Repo Allow-List' in compliance-scan.yml."""
    text = (REPO_ROOT / ".github" / "workflows" / "compliance-scan.yml").read_text(encoding="utf-8")
    assert "check_required_context_baseline.py" in text, "the baseline gate is not wired into CI"
    doc = yaml.safe_load(text)
    steps = doc["jobs"]["validate"]["steps"]
    runs = [str(s.get("run", "")) for s in steps]
    assert any("check_required_context_baseline.py" in r for r in runs), runs
    assert doc["jobs"]["validate"]["name"] in REAL_NAMES
