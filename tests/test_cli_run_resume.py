from __future__ import annotations

import json
from pathlib import Path

from tests.helpers import run_cli, seed_resume_run


def test_run_resume_generates_outputs_without_recollecting(tmp_path: Path, fixture_site_url: str) -> None:
    out_dir = tmp_path / "run"
    seed_resume_run(out_dir, fixture_site_url)

    result = run_cli(["run", f"{fixture_site_url}/index.html", "--resume", "--skip-playwright", "--out", str(out_dir)])
    assert result.returncode == 0, result.stderr or result.stdout
    payload = json.loads((out_dir / "run.json").read_text(encoding="utf-8"))
    assert payload["target_url"].endswith("/index.html")
    assert len((payload["crawl"] or {}).get("pages") or []) == 3
