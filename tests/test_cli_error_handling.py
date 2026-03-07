from __future__ import annotations

from pathlib import Path

from tests.helpers import run_cli


def test_cli_debug_env_keeps_traceback_for_diagnostics(tmp_path: Path) -> None:
    missing = tmp_path / "missing_run"
    other = tmp_path / "other"
    other.mkdir(parents=True, exist_ok=True)

    result = run_cli(
        ["diff", str(missing), str(other), "--out", str(tmp_path / "diff")],
        env_extra={"SITE_INSPECTOR_DEBUG": "1"},
    )

    assert result.returncode == 2
    assert "Traceback" in result.stderr
    assert "run.json not found for" in result.stderr
