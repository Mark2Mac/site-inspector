from __future__ import annotations

import tomllib
from pathlib import Path

from site_inspector import __version__


def test_pyproject_metadata_is_aligned_for_packaging_cleanup() -> None:
    root = Path(__file__).resolve().parent.parent
    data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))

    project = data["project"]
    assert project["name"] == "site-inspector"
    assert project["version"] == __version__
    assert isinstance(project["license"], str)
    assert project["license"] == "LicenseRef-Proprietary"
    assert project["scripts"]["site-inspector"] == "site_inspector.cli:main"
