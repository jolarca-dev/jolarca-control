"""Negative controls for the committed systemd units.

The nightly state backup is a control, and until 2026-10-28 its only definition was a file in
`~/.config/systemd/user` on one workstation: zero tracked files mentioned it, it sat on a third
device (`/home`, 66319) from both the repository (64513) and the backup disk (2065), and no archive
contained it. That is the D-85 shape -- a real fix that exists only on one machine -- so the units are
now committed and installed from the repo via `make backup-timer-install`.

Committing them creates the opposite risk: a reviewed file that no longer describes what runs. These
tests do not compare against the installed copy (CI has no such file, and a check that passes because
its input is absent is the vacuous-green pattern this repository keeps finding). They assert the
properties that make the unit *correct as a control*, each of which can fail.
"""

from __future__ import annotations

import pathlib
import re

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
UNIT_DIR = REPO_ROOT / "systemd"
SERVICE = UNIT_DIR / "jolarca-state-backup.service"
TIMER = UNIT_DIR / "jolarca-state-backup.timer"


def _read(path: pathlib.Path) -> str:
    assert path.is_file(), f"missing committed unit: {path}"
    return path.read_text(encoding="utf-8")


def test_service_runs_the_repo_script_that_exists() -> None:
    """An ExecStart pointing at a renamed or deleted script fails only at 04:17, silently."""
    text = _read(SERVICE)
    match = re.search(r"^ExecStart=\S*\s+bash\s+(\S+)\s*$", text, re.M)
    assert match, "ExecStart no longer invokes `bash <script>` (the unit uses /usr/bin/env bash)"
    script = REPO_ROOT / match.group(1)
    assert script.is_file(), f"ExecStart targets {match.group(1)}, which is not in the repository"


def test_service_sets_the_off_host_enforcement() -> None:
    """Without the flag, a remount or path typo sends backups to the same disk and still exits 0."""
    text = _read(SERVICE)
    assert re.search(r"^Environment=STATE_BACKUP_REQUIRE_OFF_HOST=1$", text, re.M), (
        "the committed unit must set STATE_BACKUP_REQUIRE_OFF_HOST=1; the refusal is the control"
    )
    dest = re.search(r"^Environment=BACKUP_DEST=(\S+)$", text, re.M)
    assert dest, "the unit must pin BACKUP_DEST; an unset destination makes the script exit 1"
    assert "jolarca/backups" not in dest.group(1), (
        f"BACKUP_DEST={dest.group(1)} is the volume holding the working copy, not a second disk"
    )


def test_timer_backfills_a_missed_window() -> None:
    """Persistent=true is the entire reason the timer replaced cron; without it, a suspend loses a run."""
    text = _read(TIMER)
    assert re.search(r"^Persistent=true$", text, re.M), (
        "the timer lost Persistent=true -- user crontabs and non-persistent timers do not backfill, "
        "which is how the 2026-10-27 install produced zero runs on 2026-10-28"
    )
    assert re.search(r"^OnCalendar=\S+\s+\d{2}:\d{2}:\d{2}$", text, re.M), "OnCalendar is malformed"


def test_timer_names_a_service_that_is_committed() -> None:
    """A typo in Unit= means the timer fires and starts nothing."""
    text = _read(TIMER)
    match = re.search(r"^Unit=(\S+)$", text, re.M)
    assert match, "the timer does not name its service"
    assert (UNIT_DIR / match.group(1)).is_file(), (
        f"Unit={match.group(1)} is not committed beside it"
    )


def test_units_carry_no_credential_shaped_values() -> None:
    """Section 5: push protection scans documentation and unit files alike; a real-looking token in a
    committed unit would S0-BLOCK the readiness gate permanently."""
    for path in (SERVICE, TIMER):
        text = _read(path)
        assert not re.search(
            r"(ghp_|github_pat_|xox[baprs]-|AKIA[0-9A-Z]{16}|BEGIN [A-Z ]*PRIVATE KEY)", text
        ), f"{path.name} contains a credential-shaped literal"
        assert "token" not in text.lower(), f"{path.name} must not embed a Terraform/cloud token"
