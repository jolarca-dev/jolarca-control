"""SAST negative-control fixture — DELIBERATELY vulnerable. Throwaway PR only.

This file exists solely to prove that the `SAST (semgrep)` and `SAST (bandit)`
jobs in `.github/workflows/sast.yml` actually *detect* rather than merely run
green (AGENTS.md §7 / D-22: "a detection no one has watched fire is a
hypothesis"). It must never be merged to `main`; the PR that carries it is
closed and its branch deleted once the red is captured.

Two independent signals so the control is not engine-specific:

* `subprocess.call(..., shell=True)` on externally-supplied input —
  Bandit **B602** (`subprocess_popen_with_shell_equals_true`, severity
  MEDIUM / confidence HIGH) and the Semgrep `p/python`
  `subprocess-shell-true` rule (severity WARNING). Both clear the thresholds
  configured in sast.yml (`-ll -ii`, `--severity ERROR/WARNING`).
* `eval(...)` of attacker-controllable input — Bandit **B307** (eval usage,
  severity MEDIUM / confidence HIGH) and the Semgrep eval-detected rule
  (severity ERROR).

The code is intentionally `ruff`- and `mypy --strict`-clean (the flake8-bandit
`S*` rules are not in the selected ruff set; every local is used; returns are
typed) so the ONLY required jobs that go red are the two SAST scanners — a
crisp attribution of the failure to the gate under test. No `# nosec` is
present on purpose: suppressing Bandit here would defeat the whole point.
"""

from __future__ import annotations

import subprocess


def negative_control_shell(user_input: str) -> int:
    """B602 (bandit) + subprocess-shell-true (semgrep): shell=True on input."""
    return subprocess.call(f"echo {user_input}", shell=True)


def negative_control_eval(user_input: str) -> int:
    """B307 (bandit) + eval-detected (semgrep): eval of input."""
    # The result is consumed by int() so the local is "used" for ruff F841,
    # while the underlying eval() stays exactly as a scanner must find it.
    return int(bool(eval(user_input)))
