from __future__ import annotations

import hashlib
import json
import platform
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .utils import _run, safe_write


# Dependencies installed into the inner-collector venv.
INNER_DEPS = [
    "requests>=2.31.0",
    "beautifulsoup4>=4.12.0",
    "lxml>=5.0.0",
    "python-Wappalyzer>=0.3.1",
    "builtwith>=1.3.4",
]


# -----------------------------
# Inner collector (runs in temp venv) — posture + link extraction
# -----------------------------

def _get_inner_script_text() -> str:
    return (Path(__file__).parent / "scripts" / "inner_collector.py").read_text(encoding="utf-8")




# -----------------------------
def get_or_create_inner_venv() -> Tuple[Path, Path, Path]:
    """Return (venv_dir, python_exe, pip_exe) for the inner-collector venv.

    Why this exists:
    - creating a brand new venv on every crawl is very slow on Windows
    - users may think the CLI is stuck and interrupt it mid-bootstrap

    We keep a stable per-Python-version venv in the system temp dir and
    never delete it after use, so the next invocation reuses it.
    """
    cache_root = Path(tempfile.gettempdir()) / "site_inspector_runtime"
    cache_root.mkdir(parents=True, exist_ok=True)
    version_tag = f"py{sys.version_info.major}{sys.version_info.minor}"
    venv_dir = cache_root / f"inner_{version_tag}"

    if not venv_dir.exists():
        rc, _, se = _run([sys.executable, "-m", "venv", str(venv_dir)], timeout=900)
        if rc != 0:
            raise RuntimeError(f"Failed to create venv: {se}")

    if platform.system().lower().startswith("win"):
        py = venv_dir / "Scripts" / "python.exe"
        pip = venv_dir / "Scripts" / "pip.exe"
    else:
        py = venv_dir / "bin" / "python"
        pip = venv_dir / "bin" / "pip"

    if not py.exists() or not pip.exists():
        shutil.rmtree(venv_dir, ignore_errors=True)
        rc, _, se = _run([sys.executable, "-m", "venv", str(venv_dir)], timeout=900)
        if rc != 0:
            raise RuntimeError(f"Failed to recreate venv: {se}")

    return venv_dir, py, pip


def ensure_inner_deps(pip: Path, venv_dir: Path, out_raw_dir: Path) -> None:
    """Install INNER_DEPS into the venv, skipping if already up-to-date.

    Uses a marker file (.deps_installed) whose content is a hash of the
    dependency list.  If the hash matches, pip install is skipped entirely.
    Raises RuntimeError if pip returns a non-zero exit code.
    """
    deps_hash = hashlib.sha1("|".join(INNER_DEPS).encode()).hexdigest()
    marker = venv_dir / ".deps_installed"

    if marker.exists() and marker.read_text(encoding="utf-8").strip() == deps_hash:
        return  # deps already installed for this exact spec

    rc, so, se = _run(
        [str(pip), "install", "--quiet", "--disable-pip-version-check"] + INNER_DEPS,
        timeout=900,
    )
    safe_write(out_raw_dir / "pip_install.stdout.txt", so)
    safe_write(out_raw_dir / "pip_install.stderr.txt", se)

    if rc != 0:
        raise RuntimeError(
            f"pip install failed (rc={rc}). See {out_raw_dir / 'pip_install.stderr.txt'}"
        )

    marker.write_text(deps_hash, encoding="utf-8")


def run_inner(py: Path, venv_dir: Path, mode: str, url: str, timeout_s: int, out_raw_dir: Path, tag: str) -> Dict[str, Any]:
    inner_path = venv_dir / "inner.py"
    if not inner_path.exists():
        inner_path.write_text(_get_inner_script_text(), encoding="utf-8")

    rc, so, se = _run([str(py), str(inner_path), mode, url, "--timeout", str(timeout_s)], timeout=max(60, timeout_s + 30))
    safe_write(out_raw_dir / f"{tag}.stdout.json", so)
    safe_write(out_raw_dir / f"{tag}.stderr.txt", se)

    try:
        return json.loads(so) if so.strip().startswith("{") else {"errors": ["inner returned non-json"], "raw": so, "rc": rc}
    except Exception:
        return {"errors": ["failed to parse inner json"], "raw": so, "stderr": se, "rc": rc}
