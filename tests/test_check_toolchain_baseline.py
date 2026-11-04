"""Negative controls for scripts/check_toolchain_baseline.py (ADR-0010 M-06).

AGENTS.md §7 requires every gate to carry a fixture that can fail, and gate-parity
R1b requires this file to name the gate it controls rather than merely matching its
filename. A placeholder test with the right name satisfies R1 and can never catch
anything — that is the exact defect check_gate_parity.py was written to find.

check_toolchain_baseline.py answers one question: does the fleet's toolchain match
the one approved answer in docs/security/toolchain-catalogue.yml. Its rules are
labelled C1-C7 (is the catalogue itself coherent) and L1-L7 (does the fleet
diverge). Each rule below is shown firing on a synthetic fixture, and each exit
code is shown reaching the right value — including 2, which is what makes this a
gate rather than a report.

The three exit codes are the point of the whole file. A run that could not read a
repository must not be able to report "no findings", because the fleet state that
motivated M-06 was assembled by hand precisely because nothing could report it.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import check_toolchain_baseline as tb  # noqa: E402

TODAY = "2026-11-03"

CATALOGUE: dict[str, Any] = {
    "version": 1,
    "owner": "jolarca-control",
    "reviewed_by": "JourneyOfLife",
    "reviewed_on": "2026-11-03",
    "review_due": "2027-05-03",
    "supported_platforms": ["linux-x64"],
    "mise": {
        "version": "2026.10.25",
        "action": "jdx/mise-action",
        "action_commit": "5228313ee0372e111a38da051671ca30fc5a96db",
        "binary_sha256": {
            "linux-x64": "5d362ecc578dc7c146679b841dda949d6472cbf86ff5635db7afdca1b6b3fd87"
        },
    },
    "tools": {
        "python": {
            "version": "3.12.16",
            "exact": True,
            "backend": "core:python",
            "upstream": "https://example.invalid/python",
            "verification": "lockfile checksum",
            "reviewed_by": "JourneyOfLife",
            "reviewed_on": "2026-11-03",
            "review_due": "2027-05-03",
        },
        "terraform": {
            "version": "1.16.1",
            "exact": True,
            "backend": "aqua:hashicorp/terraform",
            "upstream": "https://example.invalid/tf",
            "verification": "lockfile checksum",
            "reviewed_by": "JourneyOfLife",
            "reviewed_on": "2026-11-03",
            "review_due": "2027-05-03",
            "per_repository_overrides": {"other-repo": "1.9.8", "jolarca-infrastructure": "1.9.8"},
        },
    },
    "not_yet_approved": ["gitleaks"],
    "exceptions": [],
    # Mirrors the shipped catalogue. Without it every test that leaves --workflows-dir
    # at its default would also grade this repository's real apply.yml, whose
    # python-version stays a request under a dated exception.
    "workflow_exceptions": [
        {
            "file": ".github/workflows/apply.yml",
            "reason": "apply trigger path; pinning it is a deploy decision",
            "expires": "2027-05-03",
            "covers": ["R8"],
        }
    ],
}


def write_catalogue(tmp_path: Path, mutate=None) -> Path:
    data = copy.deepcopy(CATALOGUE)
    if mutate is not None:
        mutate(data)
    path = tmp_path / "catalogue.yml"
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path


def run(tmp_path: Path, *args: str) -> int:
    return tb.main([str(a) for a in args])


def repo_fixture(
    root: Path, name: str, mise_toml: str | None = None, mise_lock: bool = True, miserc: bool = True
) -> None:
    base = root / name
    base.mkdir(parents=True, exist_ok=True)
    if mise_toml is not None:
        (base / "mise.toml").write_text(mise_toml, encoding="utf-8")
    if mise_lock:
        (base / "mise.lock").write_text("lockfile_version = 3\n", encoding="utf-8")
    if miserc:
        (base / ".miserc.toml").write_text('ceiling_paths = ["x"]\n', encoding="utf-8")


GOOD_TOML = '[tools]\npython = "3.12.16"\n'

# ── positive controls: the gate must be capable of saying OK ────────────────────


def test_the_real_committed_catalogue_passes(tmp_path: Path, capsys) -> None:
    """The shipped catalogue is coherent. Without this, every red below could be
    the gate being broken rather than the fixture being wrong."""
    assert run(tmp_path, "--today", TODAY) == 0
    assert "OK: catalogue coherent" in capsys.readouterr().out


def test_a_conforming_repository_produces_no_finding(tmp_path: Path) -> None:
    fixtures = tmp_path / "fleet"
    repo_fixture(fixtures, "good-repo", GOOD_TOML)
    cat = write_catalogue(tmp_path)
    assert (
        run(
            tmp_path,
            "--catalogue",
            str(cat),
            "--from-dir",
            fixtures,
            "--scope",
            "good-repo",
            "--today",
            TODAY,
        )
        == 0
    )


def test_per_repository_override_is_not_reported_as_divergence(tmp_path: Path) -> None:
    fixtures = tmp_path / "fleet"
    repo_fixture(fixtures, "other-repo", '[tools]\nterraform = "1.9.8"\n')
    cat = write_catalogue(tmp_path)
    assert (
        run(
            tmp_path,
            "--catalogue",
            str(cat),
            "--from-dir",
            fixtures,
            "--scope",
            "other-repo",
            "--today",
            TODAY,
        )
        == 0
    )


# ── C-rules: the catalogue itself ───────────────────────────────────────────────


@pytest.mark.parametrize(
    "field",
    ["version", "backend", "upstream", "verification", "reviewed_by", "reviewed_on", "review_due"],
)
def test_c1_missing_approval_metadata_is_a_finding(tmp_path: Path, field: str, capsys) -> None:
    def mutate(data: dict) -> None:
        data["tools"]["python"].pop(field)

    cat = write_catalogue(tmp_path, mutate)
    assert run(tmp_path, "--catalogue", str(cat), "--today", TODAY) == 1
    # Findings go to stdout; only the verdict line and CANNOT VERIFY go to stderr.
    # Asserting on the wrong stream is how a gate can look tested and be untested.
    assert f"C1: tools.python omits {field}" in capsys.readouterr().out


def test_c2_a_prefix_version_claimed_exact_is_a_finding(tmp_path: Path, capsys) -> None:
    """`3.12` is a version REQUEST. This is the rule that would have flagged the
    ten `python-version: "3.12"` declarations in this repository's own workflows."""

    def mutate(data: dict) -> None:
        data["tools"]["python"]["version"] = "3.12"

    cat = write_catalogue(tmp_path, mutate)
    assert run(tmp_path, "--catalogue", str(cat), "--today", TODAY) == 1
    assert "C2: tools.python claims exact but is a request" in capsys.readouterr().out


def test_c3_an_expired_catalogue_approval_is_a_finding(tmp_path: Path, capsys) -> None:
    cat = write_catalogue(tmp_path)
    assert tb.main(["--catalogue", str(cat), "--today", "2028-01-01"]) == 1
    assert "C3: catalogue approval expired" in capsys.readouterr().out


def test_c3_an_expired_tool_approval_is_a_finding(tmp_path: Path, capsys) -> None:
    def mutate(data: dict) -> None:
        data["tools"]["node"] = dict(data["tools"]["python"], version="22.23.4")
        data["tools"]["node"]["review_due"] = "2026-01-01"

    cat = write_catalogue(tmp_path, mutate)
    assert run(tmp_path, "--catalogue", str(cat), "--today", TODAY) == 1
    assert "C3: tools.node approval expired" in capsys.readouterr().out


def test_c4_an_abbreviated_action_pin_is_a_finding(tmp_path: Path, capsys) -> None:
    def mutate(data: dict) -> None:
        data["mise"]["action_commit"] = "08c6903"

    cat = write_catalogue(tmp_path, mutate)
    assert run(tmp_path, "--catalogue", str(cat), "--today", TODAY) == 1
    assert "C4: mise.action_commit is not a full 40-hex SHA" in capsys.readouterr().out


def test_c4_a_short_binary_digest_is_a_finding(tmp_path: Path, capsys) -> None:
    def mutate(data: dict) -> None:
        data["mise"]["binary_sha256"]["linux-x64"] = "deadbeef"

    cat = write_catalogue(tmp_path, mutate)
    assert run(tmp_path, "--catalogue", str(cat), "--today", TODAY) == 1
    assert "is not 64 hex" in capsys.readouterr().out


def test_c5_a_digest_for_an_unsupported_platform_is_a_finding(tmp_path: Path, capsys) -> None:
    def mutate(data: dict) -> None:
        data["mise"]["binary_sha256"]["darwin-arm64"] = "a" * 64

    cat = write_catalogue(tmp_path, mutate)
    assert run(tmp_path, "--catalogue", str(cat), "--today", TODAY) == 1
    assert (
        "C5: binary_sha256['darwin-arm64'] is not a supported platform" in capsys.readouterr().out
    )


def test_c5_empty_supported_platforms_is_a_finding(tmp_path: Path, capsys) -> None:
    def mutate(data: dict) -> None:
        data["supported_platforms"] = []

    cat = write_catalogue(tmp_path, mutate)
    assert run(tmp_path, "--catalogue", str(cat), "--today", TODAY) == 1
    assert "C5: supported_platforms is empty" in capsys.readouterr().out


def test_c6_an_exception_without_an_expiry_is_a_finding(tmp_path: Path, capsys) -> None:
    def mutate(data: dict) -> None:
        data["exceptions"] = [{"repo": "x", "reason": "because", "covers": ["L1"]}]

    cat = write_catalogue(tmp_path, mutate)
    assert run(tmp_path, "--catalogue", str(cat), "--today", TODAY) == 1
    captured = capsys.readouterr()
    assert "C6: exceptions[0] omits expires" in captured.out
    assert "FAIL: 1 finding(s)" in captured.err


def test_c6_an_exception_without_covers_is_a_finding(tmp_path: Path, capsys) -> None:
    """`covers` is what separates an exception from a pardon. Without the field the
    entry would excuse every rule for that repository, silently."""

    def mutate(data: dict) -> None:
        data["exceptions"] = [{"repo": "x", "reason": "because", "expires": "2027-05-03"}]

    cat = write_catalogue(tmp_path, mutate)
    assert run(tmp_path, "--catalogue", str(cat), "--today", TODAY) == 1
    assert "C6: exceptions[0] omits covers" in capsys.readouterr().out


def test_an_exception_does_not_silence_a_rule_it_does_not_cover(tmp_path: Path, capsys) -> None:
    """The off-switch control, and the reason this mechanism was built.

    jolarca-security's real exception explains why the CI PROOF cannot run. It says
    nothing about why the configuration is missing from its default branch. An
    exception keyed on repository name alone would have hidden that second gap: the
    first live run of this gate reported 15 findings where the correct count was 16,
    and the missing one was exactly that repository."""
    fixtures = tmp_path / "fleet"
    fixtures.mkdir()
    (fixtures / "x-repo").mkdir()

    def mutate(data: dict) -> None:
        data["exceptions"] = [
            {
                "repo": "x-repo",
                "reason": "CI proof unavailable, adoption status unaffected",
                "expires": "2027-05-03",
                "covers": ["L4"],
            }
        ]

    cat = write_catalogue(tmp_path, mutate)
    assert (
        run(
            tmp_path,
            "--catalogue",
            str(cat),
            "--from-dir",
            fixtures,
            "--scope",
            "x-repo",
            "--today",
            TODAY,
        )
        == 1
    )
    captured = capsys.readouterr()
    assert "L1: x-repo: no mise.toml" in captured.out
    assert "not adopted" in captured.out


def test_c7_a_duplicate_yaml_key_cannot_silently_delete_an_approval(tmp_path: Path) -> None:
    """yaml.safe_load keeps the LAST duplicate, so writing `python:` twice looks
    like two approvals and is one. The gate must refuse the file, not grade it."""
    path = tmp_path / "dupe.yml"
    path.write_text(
        "version: 1\nreviewed_by: x\nreviewed_on: '2026-11-03'\nreview_due: '2027-05-03'\n"
        "supported_platforms: [linux-x64]\n"
        "mise: {version: '2026.10.25', action: jdx/mise-action, action_commit: "
        "'5228313ee0372e111a38da051671ca30fc5a96db', binary_sha256: {linux-x64: '"
        + "a"
        * 64
        + "'}}\n"
        "tools:\n"
        "  python: {version: '3.12.16', exact: true, backend: core:python, upstream: u, "
        "verification: v, reviewed_by: r, reviewed_on: '2026-11-03', review_due: '2027-05-03'}\n"
        "  python: {version: '3.11.0', exact: true, backend: core:python, upstream: u, "
        "verification: v, reviewed_by: r, reviewed_on: '2026-11-03', review_due: '2027-05-03'}\n",
        encoding="utf-8",
    )
    assert tb.main(["--catalogue", str(path), "--today", TODAY]) == 2


# ── L-rules: the fleet ──────────────────────────────────────────────────────────


def test_l1_an_unapproved_tool_is_a_finding(tmp_path: Path, capsys) -> None:
    fixtures = tmp_path / "fleet"
    repo_fixture(fixtures, "odd-repo", '[tools]\nnode = "22.23.4"\n')
    cat = write_catalogue(tmp_path)
    assert (
        run(
            tmp_path,
            "--catalogue",
            str(cat),
            "--from-dir",
            fixtures,
            "--scope",
            "odd-repo",
            "--today",
            TODAY,
        )
        == 1
    )
    assert (
        "L1: odd-repo: declares node 22.23.4, which the catalogue does not approve"
        in capsys.readouterr().out
    )


def test_l1_a_repo_with_no_mise_toml_at_all_is_a_finding(tmp_path: Path, capsys) -> None:
    """This is the measured state of 16 of 17 default branches. If the gate cannot
    say so, it cannot detect the divergence it was written for."""
    fixtures = tmp_path / "fleet"
    (fixtures / "bare-repo").mkdir(parents=True)
    cat = write_catalogue(tmp_path)
    assert (
        run(
            tmp_path,
            "--catalogue",
            str(cat),
            "--from-dir",
            fixtures,
            "--scope",
            "bare-repo",
            "--today",
            TODAY,
        )
        == 1
    )
    assert "no mise.toml on its default branch" in capsys.readouterr().out


def test_l2_a_different_patch_is_a_finding(tmp_path: Path, capsys) -> None:
    fixtures = tmp_path / "fleet"
    repo_fixture(fixtures, "drift-repo", '[tools]\npython = "3.12.15"\n')
    cat = write_catalogue(tmp_path)
    assert (
        run(
            tmp_path,
            "--catalogue",
            str(cat),
            "--from-dir",
            fixtures,
            "--scope",
            "drift-repo",
            "--today",
            TODAY,
        )
        == 1
    )
    assert "L2: drift-repo: declares python 3.12.15, approved is 3.12.16" in capsys.readouterr().out


def test_l3_a_floating_request_in_a_repo_is_a_finding(tmp_path: Path, capsys) -> None:
    fixtures = tmp_path / "fleet"
    repo_fixture(fixtures, "float-repo", '[tools]\npython = "3.12"\n')
    cat = write_catalogue(tmp_path)
    # The version differs from the approved one too, so L2 fires; L3 must fire as
    # well rather than being masked by it.
    assert (
        run(
            tmp_path,
            "--catalogue",
            str(cat),
            "--from-dir",
            fixtures,
            "--scope",
            "float-repo",
            "--today",
            TODAY,
        )
        == 1
    )
    err = capsys.readouterr()
    assert "L3: float-repo: python 3.12 is a request, not a release" in err.out
    assert "L2:" in err.out


def test_l4_a_config_with_no_lockfile_is_a_finding(tmp_path: Path, capsys) -> None:
    fixtures = tmp_path / "fleet"
    repo_fixture(fixtures, "unlocked-repo", GOOD_TOML, mise_lock=False)
    cat = write_catalogue(tmp_path)
    assert (
        run(
            tmp_path,
            "--catalogue",
            str(cat),
            "--from-dir",
            fixtures,
            "--scope",
            "unlocked-repo",
            "--today",
            TODAY,
        )
        == 1
    )
    assert "L4: unlocked-repo: mise.toml with no mise.lock" in capsys.readouterr().out


def test_l5_a_config_with_no_miserc_is_a_finding(tmp_path: Path, capsys) -> None:
    """M-01: without a bound on config discovery a stray parent mise.toml merges
    tools into the repository that CI never sees. The file is cheap to add, so the
    absence is a finding rather than a note."""
    fixtures = tmp_path / "fleet"
    repo_fixture(fixtures, "unbounded-repo", GOOD_TOML, miserc=False)
    cat = write_catalogue(tmp_path)
    assert (
        run(
            tmp_path,
            "--catalogue",
            str(cat),
            "--from-dir",
            fixtures,
            "--scope",
            "unbounded-repo",
            "--today",
            TODAY,
        )
        == 1
    )
    assert "L5: unbounded-repo: mise.toml with no .miserc.toml" in capsys.readouterr().out


def test_l7_an_unreadable_repository_is_cannot_verify_not_a_pass(tmp_path: Path) -> None:
    """AGENTS.md §3. A scope entry with no fixture is the offline stand-in for an API
    that did not answer: exit 2, never 0, and never a mere finding."""
    fixtures = tmp_path / "fleet"
    fixtures.mkdir()
    cat = write_catalogue(tmp_path)
    assert (
        run(
            tmp_path,
            "--catalogue",
            str(cat),
            "--from-dir",
            fixtures,
            "--scope",
            "gone-repo",
            "--today",
            TODAY,
        )
        == 2
    )


def test_findings_and_unreadable_together_still_exit_2(tmp_path: Path, capsys) -> None:
    """The ordering matters: if a run has both, an operator must not read the
    finding count as a complete verdict over a scope that was not fully read."""
    fixtures = tmp_path / "fleet"
    repo_fixture(fixtures, "drift-repo", '[tools]\npython = "3.12.15"\n')
    cat = write_catalogue(tmp_path)
    assert (
        run(
            tmp_path,
            "--catalogue",
            str(cat),
            "--from-dir",
            fixtures,
            "--scope",
            "drift-repo,gone-repo",
            "--today",
            TODAY,
        )
        == 2
    )
    assert "could not be read" in capsys.readouterr().err


def test_a_missing_catalogue_is_cannot_verify(tmp_path: Path) -> None:
    assert run(tmp_path, "--catalogue", tmp_path / "nope.yml", "--today", TODAY) == 2


def test_malformed_catalogue_is_cannot_verify(tmp_path: Path) -> None:
    path = tmp_path / "bad.yml"
    path.write_text("tools: [unclosed\n", encoding="utf-8")
    assert run(tmp_path, "--catalogue", str(path), "--today", TODAY) == 2


def test_a_catalogue_that_is_a_list_is_cannot_verify(tmp_path: Path) -> None:
    path = tmp_path / "list.yml"
    path.write_text("- a\n- b\n", encoding="utf-8")
    assert run(tmp_path, "--catalogue", str(path), "--today", TODAY) == 2


# ── the parser, since every rule above depends on it ────────────────────────────


def test_parse_ignores_sections_after_tools() -> None:
    text = '[tool_config]\nlocked = true\n\n[tools]\npython = "3.12.16"\n\n[tasks.toolchain]\nrun = "x"\n'
    assert tb.parse_declared_tools(text) == {"python": "3.12.16"}


def test_parse_ignores_commented_and_unquoted_lines() -> None:
    text = '# python = "9.9.9"\n[tools]\npython = "3.12.16"\n# node = "22"\n'
    assert tb.parse_declared_tools(text) == {"python": "3.12.16"}


def test_parse_is_empty_when_there_is_no_tools_section() -> None:
    assert tb.parse_declared_tools('[tasks.x]\nrun = "y"\n') == {}


def test_scope_includes_the_org_defaults_repo() -> None:
    """`.github` is absent from repos/*.yml and therefore outside the allow-list,
    but it is a real repository with real workflows. If this ever returns a list
    without it, the fleet count in ADR-0010 is wrong by one."""
    scope = tb.declared_scope()
    assert ".github" in scope
    assert "jolarca-control" in scope


# ── R8: the interpreter a required check actually runs on (ADR-0010 M-10) ───────
#
# M-10 was measured, not theorised: the same unchanged `python-version: "3.12"`
# declarations produced 3.12.15 on one hosted-runner job and 3.12.16 on the next, an
# hour apart. These cases exist so the rule that closes it can be shown firing.


def workflow_dir(tmp_path: Path, body: str) -> Path:
    d = tmp_path / "workflows"
    d.mkdir(exist_ok=True)
    (d / "sample.yml").write_text(body, encoding="utf-8")
    return d


SP_TEMPLATE = """name: sample
on: push
jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2
{steps}
"""


def with_setup_python(version: str | None) -> str:
    if version is None:
        return (
            "      - uses: actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97 # v7.0.0"
        )
    return (
        "      - uses: actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97 # v7.0.0\n"
        f'        with:\n          python-version: "{version}"'
    )


def run_r8(tmp_path: Path, body: str, mutate=None, *extra: str) -> int:
    cat = write_catalogue(tmp_path, mutate)
    d = workflow_dir(tmp_path, body)
    return tb.main(["--catalogue", str(cat), "--workflows-dir", str(d), "--today", TODAY, *extra])


def test_r8_fires_on_a_floating_request(tmp_path: Path, capsys) -> None:
    body = SP_TEMPLATE.format(steps=with_setup_python("3.12"))
    assert run_r8(tmp_path, body) == 1
    captured = capsys.readouterr().out
    assert "declares python '3.12'" in captured
    assert "approved is '3.12.16'" in captured
    assert "via sample.yml" in captured


def test_r8_fires_on_a_wrong_exact_release(tmp_path: Path, capsys) -> None:
    """An exact but unapproved version is the more dangerous case: it looks pinned."""
    body = SP_TEMPLATE.format(steps=with_setup_python("3.11.9"))
    assert run_r8(tmp_path, body) == 1
    assert "declares python '3.11.9'" in capsys.readouterr().out


def test_r8_fires_when_the_version_is_not_declared_at_all(tmp_path: Path, capsys) -> None:
    """Absent is worse than floating: the action's own default now decides."""
    body = SP_TEMPLATE.format(steps=with_setup_python(None))
    assert run_r8(tmp_path, body) == 1
    assert "with no python-version" in capsys.readouterr().out


def test_r8_fires_on_setup_terraform_without_a_version(tmp_path: Path, capsys) -> None:
    """This is the skew ADR-0010's Context table row 3 measured: fmt unpinned while
    plan and apply pinned 1.16.1."""
    body = SP_TEMPLATE.format(
        steps=(
            "      - uses: hashicorp/setup-terraform@dfe3c3f87815947d99a8997f908cb6525fc44e9e"
            " # v4.0.1\n      - run: terraform fmt -check -recursive"
        )
    )
    assert run_r8(tmp_path, body) == 1
    assert "with no terraform_version" in capsys.readouterr().out


def test_r8_accepts_the_approved_release(tmp_path: Path) -> None:
    body = SP_TEMPLATE.format(steps=with_setup_python("3.12.16"))
    assert run_r8(tmp_path, body) == 0


def test_r8_honours_a_per_repository_override(tmp_path: Path) -> None:
    body = SP_TEMPLATE.format(
        steps=(
            "      - uses: hashicorp/setup-terraform@dfe3c3f87815947d99a8997f908cb6525fc44e9e"
            ' # v4.0.1\n        with:\n          terraform_version: "1.9.8"'
        )
    )
    cat = write_catalogue(tmp_path)
    d = workflow_dir(tmp_path, body)
    assert (
        tb.main(
            [
                "--catalogue",
                str(cat),
                "--workflows-dir",
                str(d),
                "--repo",
                "other-repo",
                "--today",
                TODAY,
            ]
        )
        == 0
    )


def test_r8_is_suppressed_only_by_an_exception_that_covers_it(tmp_path: Path, capsys) -> None:
    """The M-09 lesson applied to the new rule: an exception must not become an off
    switch for something it was not written to excuse."""
    body = SP_TEMPLATE.format(steps=with_setup_python("3.12"))

    def covering(data: dict) -> None:
        data["workflow_exceptions"] = [
            {
                "file": ".github/workflows/sample.yml",
                "reason": "apply trigger path",
                "expires": "2027-05-03",
                "covers": ["R8"],
            }
        ]

    def unrelated(data: dict) -> None:
        data["workflow_exceptions"] = [
            {
                "file": ".github/workflows/sample.yml",
                "reason": "apply trigger path",
                "expires": "2027-05-03",
                "covers": ["L4"],
            }
        ]

    assert run_r8(tmp_path, body, covering) == 0
    assert run_r8(tmp_path, body, unrelated) == 1
    assert "R8:" in capsys.readouterr().out


def test_c8_requires_file_reason_expiry_and_covers(tmp_path: Path, capsys) -> None:
    def mutate(data: dict) -> None:
        data["workflow_exceptions"] = [{"file": "workflows/x.yml", "covers": ["R8"]}]

    assert run_r8(tmp_path, SP_TEMPLATE.format(steps=with_setup_python("3.12.16")), mutate) == 1
    out = capsys.readouterr().out
    assert "C8: workflow_exceptions[0] omits reason" in out
    assert "C8: workflow_exceptions[0] omits expires" in out


def test_c8_an_expired_workflow_exception_is_a_finding(tmp_path: Path, capsys) -> None:
    def mutate(data: dict) -> None:
        data["workflow_exceptions"] = [
            {"file": "workflows/x.yml", "reason": "r", "expires": "2026-01-01", "covers": ["R8"]}
        ]

    assert run_r8(tmp_path, SP_TEMPLATE.format(steps=with_setup_python("3.12.16")), mutate) == 1
    assert "C8: workflow_exceptions[0]" in capsys.readouterr().out


def test_r8_refuses_to_pass_over_zero_examined_steps(tmp_path: Path, capsys) -> None:
    """Non-vacuity. An empty workflows directory would otherwise report a clean pass
    over nothing, which is the failure mode AGENTS.md §3 exists to forbid."""
    empty = tmp_path / "workflows"
    empty.mkdir()
    cat = write_catalogue(tmp_path)
    assert tb.main(["--catalogue", str(cat), "--workflows-dir", str(empty), "--today", TODAY]) == 2
    assert "examined nothing" in capsys.readouterr().err


def test_this_repositorys_own_workflows_pass_r8_and_are_actually_counted(
    tmp_path: Path, capsys
) -> None:
    """The shipped-artifact positive control, and the non-vacuity assertion for the
    default invocation: M-10's whole claim is that these files were unpinned, so the
    rule must be shown reading the real ones and finding the real count."""
    rc = tb.main(["--today", TODAY])
    out = capsys.readouterr().out
    assert rc == 0, out
    assert "13 workflow runtime step(s) examined" in out, out


def test_apply_yml_is_still_unpinned_and_that_is_excused_not_invisible(tmp_path: Path) -> None:
    """apply.yml is an apply trigger path, so its python-version stays a request under
    a dated exception. This test fails the moment someone pins it without removing the
    exception, or removes the exception without pinning it."""
    text = (REPO_ROOT / ".github" / "workflows" / "apply.yml").read_text(encoding="utf-8")
    # safe_load, not load: bandit runs `-ll -ii` and flagged B506 on the first draft of
    # this line. The Loader argument I passed was provably safe and bandit still
    # refused it, because a conditional expression naming a class that no longer exists
    # is not something a static checker can resolve — a dead fallback is not only dead,
    # it blinded the scanner.
    cat = yaml.safe_load(
        (REPO_ROOT / "docs" / "security" / "toolchain-catalogue.yml").read_text(encoding="utf-8")
    )
    exc = {
        str(e.get("file")): [str(c) for c in (e.get("covers") or [])]
        for e in cat.get("workflow_exceptions") or []
    }
    assert 'python-version: "3.12"\n' in text, "apply.yml was pinned; remove its exception too"
    assert exc.get(".github/workflows/apply.yml") == ["R8"], exc


# ── R8 composite-action resolution (the jolarca-infrastructure blind spot) ──────
#
# Measured before this rule existed: running main's committed gate against the REAL
# .github/workflows/terraform.yml plus .github/actions/terraform-setup/action.yml
# fetched from jolarca-dev/jolarca-infrastructure returned
#   CANNOT VERIFY: ... R8 examined nothing, so its silence is not evidence
# i.e. exit 2. The non-vacuity guard correctly refused to pass, but coverage was zero:
# infrastructure's only Terraform pin lives in a composite input default, not in a
# workflow. These fixtures reproduce that shape offline so the gap cannot return.


COMPOSITE_CALLER = """name: terraform
on:
  pull_request:
jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2
      - uses: ./.github/actions/terraform-setup
{extra}
"""

COMPOSITE_BODY = """name: terraform setup
description: pin the terraform binary
inputs:
  terraform_version:
    description: version
    default: "{version}"
runs:
  using: composite
  steps:
    - uses: hashicorp/setup-terraform@dfe3c3f87815947d99a8997f908cb6525fc44e9e # v4.0.1
      with:
        terraform_version: ${{{{ inputs.terraform_version }}}}
"""


def composite_tree(tmp_path: Path, version: str, extra: str = "") -> tuple[Path, Path, Path]:
    root = tmp_path / "tree"
    wf = root / ".github" / "workflows"
    actions_root = root / ".github" / "actions"
    act = actions_root / "terraform-setup"
    wf.mkdir(parents=True, exist_ok=True)
    act.mkdir(parents=True, exist_ok=True)
    (wf / "terraform.yml").write_text(COMPOSITE_CALLER.format(extra=extra), encoding="utf-8")
    (act / "action.yml").write_text(COMPOSITE_BODY.format(version=version), encoding="utf-8")
    # The actions ROOT is what --actions-dir means; returning the composite's own
    # directory here is what made the first fixture miss the sweep entirely.
    return root, wf, actions_root


def run_composite(
    tmp_path: Path, mutate=None, repo: str = "jolarca-infrastructure", *extra: str
) -> int:
    cat = write_catalogue(tmp_path, mutate)
    root, wf, act = composite_tree(tmp_path, "1.9.8")
    return tb.main(
        [
            "--catalogue",
            str(cat),
            "--root",
            str(root),
            "--workflows-dir",
            str(wf),
            "--actions-dir",
            str(act),
            "--repo",
            repo,
            "--today",
            TODAY,
            *extra,
        ]
    )


def test_composite_input_default_is_honoured_through_the_per_repo_override(tmp_path: Path) -> None:
    """The real infrastructure shape: caller passes nothing, the composite's input
    default is 1.9.8, and the catalogue approves 1.9.8 for that repository."""
    assert run_composite(tmp_path) == 0


def test_composite_default_is_refused_when_it_is_not_the_approved_release(
    tmp_path: Path, capsys
) -> None:
    """Same tree, a repo with no override. Before the fix this returned exit 2 with
    'R8 examined nothing' — the pin was invisible, not merely wrong."""
    assert run_composite(tmp_path, repo="some-other-repo") == 1
    out = capsys.readouterr().out
    assert "declares terraform '1.9.8'" in out
    assert "default in .github/actions/terraform-setup/action.yml" in out


def test_a_template_value_is_not_mistaken_for_the_pin(tmp_path: Path, capsys) -> None:
    """The composite step carries `${{ inputs.terraform_version }}`, not a version.

    Comparing that string against the approved release would raise a false finding on
    every correctly written composite, and the fleet response to a gate that cries wolf
    is an exception, not a fix. So a template must fall through to the input default.
    """
    assert run_composite(tmp_path, repo="some-other-repo") == 1
    out = capsys.readouterr().out
    assert "${{" not in out, "the template was graded as if it were a version"


def test_the_caller_with_wins_over_the_composite_default(tmp_path: Path, capsys) -> None:
    """GitHub applies the caller's value; the gate must judge that one instead."""
    cat = write_catalogue(tmp_path)
    root, wf, act = composite_tree(tmp_path, "1.9.8", extra="")
    caller = (
        "      - uses: ./.github/actions/terraform-setup\n"
        "        with:\n"
        '          terraform_version: "1.2.3"\n'
    )
    (wf / "terraform.yml").write_text(COMPOSITE_CALLER.format(extra=caller), encoding="utf-8")
    assert (
        tb.main(
            [
                "--catalogue",
                str(cat),
                "--root",
                str(root),
                "--workflows-dir",
                str(wf),
                "--actions-dir",
                str(act),
                "--repo",
                "jolarca-infrastructure",
                "--today",
                TODAY,
            ]
        )
        == 1
    )
    assert "declares terraform '1.2.3'" in capsys.readouterr().out


def test_an_unreferenced_composite_is_still_swept(tmp_path: Path, capsys) -> None:
    """A floating pin must not hide by having no caller today."""
    cat = write_catalogue(tmp_path)
    root, wf, act = composite_tree(tmp_path, "9.9.9")
    (wf / "terraform.yml").write_text(
        "name: nothing\non: push\njobs:\n  x:\n    runs-on: ubuntu-latest\n    steps:\n"
        "      - run: echo hi\n",
        encoding="utf-8",
    )
    assert (
        tb.main(
            [
                "--catalogue",
                str(cat),
                "--root",
                str(root),
                "--workflows-dir",
                str(wf),
                "--actions-dir",
                str(act),
                "--repo",
                "jolarca-infrastructure",
                "--today",
                TODAY,
            ]
        )
        == 1
    )
    out = capsys.readouterr().out
    assert "(unreferenced)" in out
    assert "9.9.9" in out


def test_a_local_uses_that_resolves_to_nothing_is_a_finding_not_silence(
    tmp_path: Path, capsys
) -> None:
    cat = write_catalogue(tmp_path)
    root, wf, act = composite_tree(tmp_path, "1.9.8")
    (wf / "broken.yml").write_text(
        "name: broken\non: push\njobs:\n  x:\n    runs-on: ubuntu-latest\n    steps:\n"
        "      - uses: ./.github/actions/does-not-exist\n",
        encoding="utf-8",
    )
    assert (
        tb.main(
            [
                "--catalogue",
                str(cat),
                "--root",
                str(root),
                "--workflows-dir",
                str(wf),
                "--actions-dir",
                str(act),
                "--repo",
                "jolarca-infrastructure",
                "--today",
                TODAY,
            ]
        )
        == 1
    )
    assert "resolves to no action.yml" in capsys.readouterr().out


def test_composite_only_tree_counts_steps_instead_of_exiting_2(tmp_path: Path, capsys) -> None:
    """Non-vacuity for the new object class. Before the fix this tree produced
    'R8 examined nothing' and exit 2; now it must report the three call sites."""
    cat = write_catalogue(tmp_path)
    root, wf, act = composite_tree(tmp_path, "1.9.8")
    rc = tb.main(
        [
            "--catalogue",
            str(cat),
            "--root",
            str(root),
            "--workflows-dir",
            str(wf),
            "--actions-dir",
            str(act),
            "--repo",
            "jolarca-infrastructure",
            "--today",
            TODAY,
            "--json",
        ]
    )
    assert rc == 0
    import json

    payload = json.loads(capsys.readouterr().out)
    assert payload["runtime_steps_examined"] >= 1, payload
