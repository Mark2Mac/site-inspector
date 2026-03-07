from __future__ import annotations

import tomllib
from pathlib import Path


def test_pyproject_exposes_public_package_metadata() -> None:
    data = tomllib.loads(Path('pyproject.toml').read_text(encoding='utf-8'))
    project = data['project']

    assert project['name'] == 'site-inspector'
    assert project['readme'] == 'README.md'
    assert 'site-inspector' in project['scripts']
    assert project['scripts']['site-inspector'] == 'site_inspector.cli:main'
    assert 'urls' in project
    assert 'Homepage' in project['urls']
