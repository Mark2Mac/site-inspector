from __future__ import annotations

import subprocess
import sys

from site_inspector import __version__
from tests.helpers import repo_root


def test_module_entrypoint_prints_version() -> None:
    result = subprocess.run(
        [sys.executable, '-m', 'site_inspector', '--version'],
        cwd=str(repo_root()),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding='utf-8',
        errors='replace',
    )
    assert result.returncode == 0, result.stderr
    assert __version__ in result.stdout
