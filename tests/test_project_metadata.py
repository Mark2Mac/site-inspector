from __future__ import annotations

import tomllib
from pathlib import Path

from site_inspector import __version__


def test_pyproject_metadata_is_aligned_for_public_packaging() -> None:
    root = Path(__file__).resolve().parent.parent
    data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))

    project = data["project"]
    urls = project["urls"]

    assert project["name"] == "site-inspector"
    assert project["version"] == __version__
    assert isinstance(project["license"], str)
    assert project["license"] == "MIT"
    assert project["scripts"]["site-inspector"] == "site_inspector.cli:main"

    assert project["authors"][0]["name"] != "OpenAI / User project"
    assert "example.invalid" not in urls["Homepage"]
    assert "example.invalid" not in urls["Documentation"]
    assert "example.invalid" not in urls["Changelog"]
    assert "Operating System :: OS Independent" in project["classifiers"]
