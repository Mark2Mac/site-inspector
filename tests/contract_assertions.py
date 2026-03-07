from __future__ import annotations

from typing import Any


def _typename(value: Any) -> str:
    if value is None:
        return 'null'
    if isinstance(value, bool):
        return 'boolean'
    if isinstance(value, int) and not isinstance(value, bool):
        return 'integer'
    if isinstance(value, float):
        return 'number'
    if isinstance(value, str):
        return 'string'
    if isinstance(value, list):
        return 'array'
    if isinstance(value, dict):
        return 'object'
    return type(value).__name__


def assert_contract(value: Any, contract: dict[str, Any], path: str = '$') -> None:
    expected = contract.get('type', 'any')
    actual = _typename(value)

    if expected == 'any':
        return
    if expected == 'number' and actual in {'integer', 'number'}:
        pass
    elif expected != actual:
        raise AssertionError(f"{path}: expected {expected}, got {actual}")

    if expected == 'object':
        assert isinstance(value, dict)
        for key in contract.get('required', []):
            if key not in value:
                raise AssertionError(f"{path}: missing required key '{key}'")
        props = contract.get('properties', {})
        for key, sub in props.items():
            if key in value:
                assert_contract(value[key], sub, f"{path}.{key}")
    elif expected == 'array':
        assert isinstance(value, list)
        item_contract = contract.get('items')
        if item_contract:
            for idx, item in enumerate(value[:3]):
                assert_contract(item, item_contract, f"{path}[{idx}]")
