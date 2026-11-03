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


def test_service_retries_a_transient_failure() -> None:
    """A backfilled run fires at the instant of resume, before the network is usable.

    Measured 2026-10-29: `Persistent=true` started the unit at 12:16:50 on resume while NetworkManager
    was still linking (8 connect/up events in that window); the fetch exited 2 and no archive was
    written, while the identical unit at 22:12 succeeded. Without a retry, every suspend-through-04:17
    costs a night that nobody notices.
    """
    text = _read(SERVICE)
    assert re.search(r"^Restart=on-failure$", text, re.M), "the unit lost its retry policy"
    assert re.search(r"^RestartSec=\d+\s*(s|sec|min|h)?$", text, re.M), (
        "RestartSec is missing or malformed"
    )


def test_start_limit_directives_are_in_the_section_that_reads_them() -> None:
    """`StartLimit*` belong to [Unit]. Under [Service] systemd warns and ignores them, so the retry
    bound silently stops existing -- a guard that is not applied is worse than no guard, because it
    reads like one. Assert placement by section, not mere presence in the file."""
    text = _read(SERVICE)
    unit_section = re.search(r"^\[Unit\](.*?)(?=^\[)", text, re.S | re.M)
    service_section = re.search(r"^\[Service\](.*?)(?=^\[|$)", text, re.S | re.M)
    assert unit_section and service_section, "the unit is missing [Unit] or [Service]"
    body = unit_section.group(1)
    assert re.search(r"^StartLimitBurst=\d+$", body, re.M), (
        "StartLimitBurst is not in [Unit] -- retries are unbounded or the limit is being ignored"
    )
    # Burst alone is not a bound: without an explicit interval the count runs over systemd's default
    # window, so "10 attempts per hour" in the comment would be a claim the unit does not implement.
    assert re.search(r"^StartLimitIntervalSec=\d+\s*(s|sec|min|h)?$", body, re.M), (
        "StartLimitIntervalSec is missing or malformed -- StartLimitBurst without an explicit interval "
        "counts over the default window, which is not the bound the comments describe"
    )
    assert "StartLimit" not in service_section.group(1), (
        "StartLimit* under [Service] is ignored by systemd with a warning; move it to [Unit]"
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
