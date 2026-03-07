from __future__ import annotations

from site_inspector import __version__
from tests.helpers import run_cli


def test_cli_version_flag_prints_package_version() -> None:
    result = run_cli(["--version"])
    assert result.returncode == 0
    assert __version__ in (result.stdout or result.stderr)
