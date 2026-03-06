from __future__ import annotations

import json
from pathlib import Path

from tests.helpers import run_cli, seed_resume_run


def test_run_json_contains_duplicates_validation(tmp_path: Path, fixture_site_url: str) -> None:
    out_dir = tmp_path / "run"
    seed_resume_run(out_dir, fixture_site_url)
    result = run_cli(["run", f"{fixture_site_url}/index.html", "--resume", "--skip-playwright", "--out", str(out_dir)])
    assert result.returncode == 0, result.stderr or result.stdout
    payload = json.loads((out_dir / "run.json").read_text(encoding="utf-8"))
    dup = payload["duplicates"]
    assert "duplicate_groups" in dup
    assert "validation" in dup
    assert dup["validation"]["actionable_groups"] >= 1
