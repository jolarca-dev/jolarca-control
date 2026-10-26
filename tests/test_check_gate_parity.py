"""Negative controls for scripts/check_gate_parity.py — the gate that gates the gates.

Fleet convention (AGENTS.md §7): a gate that runs and reports green has not been shown to
detect anything. That rule was unenforced, and the enforcement gate is held to it first.

Each case builds a throwaway tree under tmp_path and points `check()` at it, so the rule is
exercised against input that MUST fail. The `prose-naming-is-not-an-invocation` case is the
regression this module exists for: the gate's first draft let a docstring that names a script
count as proof of liveness, which made the gate pass the exact defect it was written to find
(`check_secret_inventory.sh`, unwired since 2026-10-20, D-80). A meta-gate that can be fooled
by prose is worse than no meta-gate, because its green reads as systemic assurance.
"""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
GATE = ROOT / "scripts" / "check_gate_parity.py"


def _load() -> Any:
    spec = importlib.util.spec_from_file_location("check_gate_parity", GATE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _tree(
    tmp_path: Path, *, scripts: list[str], tests: list[str], makefile: str, workflows: str
) -> Path:
    """A minimal repository-shaped tree: the gate needs scripts/, tests/, Makefile, workflows.

    `on: pull_request` is added here rather than in each case because R2 only credits a
    workflow that can trigger on a pull request — without a trigger the gate must report a
    gap, and every fixture below would be testing the wrong property.
    """
    (tmp_path / "scripts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "tests").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".github" / "workflows").mkdir(parents=True, exist_ok=True)
    for name in scripts:
        (tmp_path / "scripts" / name).write_text(
            f"#!/usr/bin/env bash\necho {name}\n", encoding="utf-8"
        )
    for name in tests:
        # A placeholder fixture still has to reference its subject, or R1b (right-name,
        # no-substance stub) fires on every tree and the cases below test the wrong rule.
        subject = re.sub(r"^test_|\.(py|sh)$", "", name)
        if name.endswith(".py"):
            body = f'print("{subject} fixture")\n'
        else:
            body = f"#!/usr/bin/env bash\nbash scripts/{subject}\n"
        (tmp_path / "tests" / name).write_text(body, encoding="utf-8")
    (tmp_path / "Makefile").write_text(makefile, encoding="utf-8")
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text(
        f"on:\n  pull_request:\n{workflows}", encoding="utf-8"
    )
    return tmp_path


RUN = "run: bash scripts/thing_guard.sh\n"


def _clean(tmp_path: Path) -> Path:
    return _tree(
        tmp_path,
        scripts=["thing_guard.sh"],
        tests=["test_thing_guard.sh"],
        makefile="test:\n\tbash tests/test_thing_guard.sh\n",
        workflows=f"jobs:\n  v:\n    steps:\n      - {RUN}\n      - run: bash tests/test_thing_guard.sh\n",
    )


def test_clean_tree_passes(tmp_path: Path) -> None:
    """Positive control: parity actually holds when it holds, so the rules are not always-red."""
    mod = _load()
    findings, gaps = mod.check(_clean(tmp_path))
    assert gaps == [], gaps
    assert findings == [], findings


def test_script_without_fixture_is_r1(tmp_path: Path) -> None:
    mod = _load()
    tree = _tree(
        tmp_path,
        scripts=["thing_guard.sh"],
        tests=[],
        makefile="test:\n\techo\n",
        workflows=f"jobs:\n  v:\n    steps:\n      - {RUN}\n",
    )
    findings, _gaps = mod.check(tree)
    r1 = [f for f in findings if f["rule"] == "R1"]
    assert len(r1) == 1, findings
    assert "test_thing_guard" in r1[0]["what"]


def test_shell_fixture_missing_from_ci_is_r2(tmp_path: Path) -> None:
    """The `make test`-only case: it looks covered and protects no merge."""
    mod = _load()
    tree = _tree(
        tmp_path,
        scripts=["thing_guard.sh"],
        tests=["test_thing_guard.sh"],
        makefile="test:\n\tbash tests/test_thing_guard.sh\n",
        workflows=f"jobs:\n  v:\n    steps:\n      - {RUN}\n",  # fixture deliberately absent
    )
    findings, _gaps = mod.check(tree)
    r2 = [f for f in findings if f["rule"] == "R2"]
    assert len(r2) == 1, findings
    assert "only via `make test`" in r2[0]["what"], r2[0]


def test_shell_fixture_invoked_nowhere_is_r2(tmp_path: Path) -> None:
    mod = _load()
    tree = _tree(
        tmp_path,
        scripts=["thing_guard.sh"],
        tests=["test_thing_guard.sh"],
        makefile="test:\n\techo nothing\n",
        workflows=f"jobs:\n  v:\n    steps:\n      - {RUN}\n",
    )
    findings, _gaps = mod.check(tree)
    r2 = [f for f in findings if f["rule"] == "R2"]
    assert len(r2) == 1, findings
    assert "nothing at all" in r2[0]["what"], r2[0]


def test_shell_fixture_in_a_push_only_workflow_is_r2(tmp_path: Path) -> None:
    """CI that fires after the merge is a report, not a gate.

    Wiring a fixture into a schedule/push workflow satisfies naive "is it invoked anywhere?"
    checking while protecting nothing, so the corpus R2 reads must be PR-triggerable.
    """
    mod = _load()
    tree = _clean(tmp_path)
    (tree / ".github" / "workflows" / "ci.yml").write_text(
        f"on:\n  push:\njobs:\n  v:\n    steps:\n      - {RUN}\n"
        "      - run: bash tests/test_thing_guard.sh\n",
        encoding="utf-8",
    )
    findings, gaps = mod.check(tree)
    assert gaps == [], gaps
    r2 = [f for f in findings if f["rule"] == "R2"]
    assert len(r2) == 1, findings
    assert "cannot trigger on" in r2[0]["what"], r2[0]


def test_comment_inside_a_run_body_is_not_an_invocation(tmp_path: Path) -> None:
    """A `#` line inside a shell `run: |` block is prose, the same as a YAML comment.

    The gate strips comment lines from both corpora; without that, adding a commented-out
    invocation would silence R3 for a script nothing executes.
    """
    mod = _load()
    tree = _clean(tmp_path)
    (tree / "scripts" / "dead_gate.sh").write_text(
        "#!/usr/bin/env bash\necho x\n", encoding="utf-8"
    )
    (tree / ".github" / "workflows" / "ci.yml").write_text(
        "on:\n  pull_request:\njobs:\n  v:\n    steps:\n"
        f"      - {RUN}"
        "      - run: |\n"
        "          # bash scripts/dead_gate.sh  # kept for the day it is wired up\n"
        "          echo nothing runs the gate\n",
        encoding="utf-8",
    )
    findings, gaps = mod.check(tree)
    assert gaps == [], gaps
    r3 = [f for f in findings if f["rule"] == "R3"]
    assert len(r3) == 1, findings
    assert r3[0]["where"] == "scripts/dead_gate.sh", r3[0]


def test_baseline_entry_does_not_excuse_liveness(tmp_path: Path) -> None:
    """THE regression for the meta-gate itself: an exception must stay narrow.

    A NO_FIXTURE_BASELINE entry forgives the missing fixture. The first draft `continue`d
    instead, so a baselined script that was ALSO wired to nothing produced no finding at all —
    measured before the fix: `findings: []`. Listing a dead gate in the baseline would then
    have been a way to switch the gate off, which is §5's forbidden move (do not delete or
    weaken a gate).
    """
    mod = _load()
    mod.NO_FIXTURE_BASELINE = {"dead_unwired.sh": "baselined reason well over thirty chars"}
    mod.MAX_UNFIXTURED = 1
    tree = _tree(
        tmp_path,
        scripts=["dead_unwired.sh"],
        tests=[],
        makefile="test:\n\techo nothing\n",
        workflows="jobs:\n  v:\n    steps:\n      - run: echo unrelated\n",
    )
    findings, gaps = mod.check(tree)
    assert gaps == [], gaps
    # R1 is forgiven by the baseline; R3 is not.
    assert [f["rule"] for f in findings] == ["R3"], findings


def test_placeholder_fixture_is_r1b(tmp_path: Path) -> None:
    """A file with the right name and no subject reference is a stub, not a control."""
    mod = _load()
    tree = _clean(tmp_path)
    (tree / "tests" / "test_thing_guard.sh").write_text(
        "#!/usr/bin/env bash\necho placeholder\n", encoding="utf-8"
    )
    findings, gaps = mod.check(tree)
    assert gaps == [], gaps
    r1b = [f for f in findings if f["rule"] == "R1b"]
    assert len(r1b) == 1, findings
    assert r1b[0]["where"] == "tests/test_thing_guard.sh", r1b[0]


def test_workflow_without_trigger_is_cannot_verify(tmp_path: Path) -> None:
    """GitHub refuses a workflow with no `on:`; the gate must not read that as coverage."""
    mod = _load()
    tree = _clean(tmp_path)
    (tree / ".github" / "workflows" / "ci.yml").write_text(
        f"jobs:\n  v:\n    steps:\n      - {RUN}\n      - run: bash tests/test_thing_guard.sh\n",
        encoding="utf-8",
    )
    _findings, gaps = mod.check(tree)
    assert any("no `on:` trigger" in g for g in gaps), gaps
    code = subprocess.run([sys.executable, str(GATE), str(tree)], capture_output=True, text=True)
    assert code.returncode in (1, 2), (code.returncode, code.stdout, code.stderr)
    assert code.returncode != 0


def test_prose_naming_is_not_an_invocation(tmp_path: Path) -> None:
    """THE regression for D-80.

    A second script mentions the dead gate in a comment. Prose must not satisfy R3, or the
    gate reports green on a control that runs nowhere — which is precisely how the first
    draft behaved, because this very module's docstring names the script it indicts.
    """
    mod = _load()
    tree = _clean(tmp_path)
    (tree / "scripts" / "dead_gate.sh").write_text(
        "#!/usr/bin/env bash\n# mentioned dead_gate.sh in prose only\n", encoding="utf-8"
    )
    (tree / "scripts" / "thing_guard.sh").write_text(
        "#!/usr/bin/env bash\n# see dead_gate.sh for the same idea\n", encoding="utf-8"
    )
    (tree / "tests" / "test_dead_gate.sh").write_text(
        "#!/usr/bin/env bash\nbash scripts/dead_gate.sh\n", encoding="utf-8"
    )
    (tree / "Makefile").write_text(
        "test:\n\tbash tests/test_thing_guard.sh\n\tbash tests/test_dead_gate.sh\n",
        encoding="utf-8",
    )
    (tree / ".github" / "workflows" / "ci.yml").write_text(
        "on:\n  pull_request:\njobs:\n  v:\n    steps:\n"
        f"      - {RUN}\n"
        "      - run: bash tests/test_thing_guard.sh\n"
        "      - run: bash tests/test_dead_gate.sh\n"
        "      # dead_gate.sh is documented here and still never runs\n",
        encoding="utf-8",
    )
    findings, gaps = mod.check(tree)
    assert gaps == [], gaps
    r3 = [f for f in findings if f["rule"] == "R3"]
    assert len(r3) == 1, findings
    assert r3[0]["where"] == "scripts/dead_gate.sh", r3[0]


def test_stale_baseline_entry_is_r4(tmp_path: Path) -> None:
    """A baseline entry whose fixture now exists is a hiding place with nothing behind it."""
    mod = _load()
    mod.NO_FIXTURE_BASELINE = {"thing_guard.sh": "historic gap"}
    mod.MAX_UNFIXTURED = 1
    findings, _gaps = mod.check(_clean(tmp_path))
    r4 = [f for f in findings if f["rule"] == "R4"]
    assert len(r4) == 1, findings
    assert "stale baseline entry" in r4[0]["what"], r4[0]
    # And the same tree must NOT gain an R1: the baseline entry is why the fixture is checked
    # rather than required, so R1 and R4 must not both fire on one name.
    assert not [f for f in findings if f["rule"] == "R1"], findings


def test_baseline_growth_is_r4(tmp_path: Path) -> None:
    """The ratchet: two tolerated entries against a ceiling of one must fail."""
    mod = _load()
    mod.NO_FIXTURE_BASELINE = {
        "a_guard.sh": "reason a",
        "b_guard.sh": "reason b",
    }
    mod.MAX_UNFIXTURED = 1
    tree = _tree(
        tmp_path,
        scripts=["a_guard.sh", "b_guard.sh"],
        tests=[],
        makefile="test:\n\techo\n",
        workflows="jobs:\n  v:\n    steps:\n      - run: bash scripts/a_guard.sh\n      - run: bash scripts/b_guard.sh\n",
    )
    findings, _gaps = mod.check(tree)
    assert any("ceiling" in f["what"] for f in findings if f["rule"] == "R4"), findings


def test_missing_inputs_are_cannot_verify_not_clean(tmp_path: Path) -> None:
    mod = _load()
    findings, gaps = mod.check(tmp_path / "nope")
    assert findings == [] and gaps, (findings, gaps)
    code = subprocess.run(
        [sys.executable, str(GATE), str(tmp_path / "nope")], capture_output=True, text=True
    )
    assert code.returncode == 2, code.stderr


def test_empty_scripts_dir_is_cannot_verify(tmp_path: Path) -> None:
    """A gate over nothing must never report parity (§3)."""
    mod = _load()
    tree = _clean(tmp_path)
    for p in (tree / "scripts").iterdir():
        p.unlink()
    findings, gaps = mod.check(tree)
    assert findings == [] and gaps, (findings, gaps)


def test_unreadable_workflow_is_a_gap_not_a_pass(tmp_path: Path) -> None:
    """Corrupt workflow input must surface as CANNOT-VERIFY, whatever the failure stage.

    Asserted on the prefix rather than the exact phrase: the gate reports unreadable bytes at
    the parse step (`cannot parse`), and pinning the wording here would make the fixture break
    on a cosmetic message change while the property under test is simply `not silently fine`.
    """
    mod = _load()
    tree = _clean(tmp_path)
    wf = tree / ".github" / "workflows" / "ci.yml"
    wf.write_bytes(b"\xff\xfe not readable text at all \x00")
    _findings, gaps = mod.check(tree)
    assert any(g.startswith("cannot ") for g in gaps), gaps
    code = subprocess.run([sys.executable, str(GATE), str(tree)], capture_output=True, text=True)
    # Never 0. A tree with both a violation and an unreadable input reports the violation
    # (1); an unreadable-only tree reports 2. Asserting `!= 0` tests the property that matters
    # — an unparseable workflow can never be read as parity — without pinning which of the two
    # non-passing codes a fixture tree happens to also trigger.
    assert code.returncode in (1, 2), (code.returncode, code.stdout, code.stderr)
    assert "CANNOT-VERIFY" in code.stderr, code.stderr


# ── The real repository: the state this PR must leave behind ─────────────────
def test_real_repository_has_parity() -> None:
    mod = _load()
    findings, gaps = mod.check(ROOT)
    assert gaps == [], gaps
    assert findings == [], [f"{f['rule']} {f['where']}: {f['what']}" for f in findings]


def test_real_baseline_entries_are_still_true(tmp_path: Path) -> None:
    """Each baseline name must STILL lack a fixture, and the ceiling must equal the list.

    Without this, a baseline entry could outlive its gap or MAX_UNFIXTURED could be edited
    upward while the in-code check still reported the ratchet as armed.
    """
    mod = _load()
    assert len(mod.NO_FIXTURE_BASELINE) == mod.MAX_UNFIXTURED
    test_stems = {p.name[5:].split(".")[0] for p in (ROOT / "tests").glob("test_*")}
    for name, reason in mod.NO_FIXTURE_BASELINE.items():
        stem = name.rsplit(".", 1)[0]
        assert stem not in test_stems, f"{name} has a fixture now: remove the exception"
        assert len(reason) > 30, f"{name} is baselined without a real reason"


def test_gate_exit_codes_are_three_valued_on_the_real_tree() -> None:
    code = subprocess.run([sys.executable, str(GATE)], capture_output=True, text=True)
    assert code.returncode == 0, code.stdout + code.stderr
    assert "OK:" in code.stdout, code.stdout
