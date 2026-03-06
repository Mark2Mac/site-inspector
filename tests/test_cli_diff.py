from __future__ import annotations

import json
from pathlib import Path

from tests.helpers import run_cli, seed_resume_run


def test_diff_command_generates_outputs(tmp_path: Path, fixture_site_url: str) -> None:
    run_a = tmp_path / "runA"
    run_b = tmp_path / "runB"
    diff_out = tmp_path / "diff"

    seed_resume_run(run_a, fixture_site_url)
    seed_resume_run(run_b, fixture_site_url)

    for out_dir in (run_a, run_b):
        result = run_cli([
            "run",
            f"{fixture_site_url}/index.html",
            "--resume",
            "--skip-playwright",
            "--out",
            str(out_dir),
        ])
        assert result.returncode == 0, result.stderr or result.stdout

    diff_result = run_cli(["diff", str(run_a), str(run_b), "--out", str(diff_out)])
    assert diff_result.returncode == 0, diff_result.stderr or diff_result.stdout
    assert (diff_out / "diff.json").exists()
    assert (diff_out / "diff.md").exists()

    payload = json.loads((diff_out / "diff.json").read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
