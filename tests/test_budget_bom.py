from __future__ import annotations

from pathlib import Path

from site_inspector.utils import load_json_if_exists


def test_load_json_if_exists_accepts_utf8_bom(tmp_path: Path) -> None:
    path = tmp_path / "budget.json"
    path.write_text('{"ok": true}', encoding="utf-8-sig")

    payload = load_json_if_exists(str(path))

    assert payload == {"ok": True}
