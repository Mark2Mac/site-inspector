from __future__ import annotations

from pathlib import Path

from tests.helpers import run_cli


def test_diff_missing_run_dir_has_human_error(tmp_path: Path) -> None:
    missing = tmp_path / "missing_run"
    other = tmp_path / "other"
    other.mkdir(parents=True, exist_ok=True)
    result = run_cli(["diff", str(missing), str(other), "--out", str(tmp_path / "diff")])
    assert result.returncode != 0
    assert "run.json not found for" in result.stderr
    assert "run directory" in result.stderr.lower()
