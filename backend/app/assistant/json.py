"""Bounded JSON at the untrusted model boundary."""

import hashlib
import json

from pydantic import JsonValue


def _pairs(pairs: list[tuple[str, JsonValue]]) -> dict[str, JsonValue]:
    result: dict[str, JsonValue] = {}
    for key, value in pairs:
        if key in result or "\x00" in key:
            raise ValueError("Duplicate or invalid JSON key")
        key.encode("utf-8")
        result[key] = value
    return result


def _constant(value: str) -> JsonValue:
    raise ValueError("Non-finite JSON numbers are not supported")


def _check_text(value: JsonValue) -> None:
    if isinstance(value, str):
        if "\x00" in value:
            raise ValueError("NUL is not supported")
        value.encode("utf-8")
    if isinstance(value, dict):
        for item in value.values():
            _check_text(item)
    elif isinstance(value, list):
        for item in value:
            _check_text(item)


def json_object(value: str) -> dict[str, JsonValue]:
    result: JsonValue = json.loads(value, object_pairs_hook=_pairs, parse_constant=_constant)
    if not isinstance(result, dict):
        raise ValueError("Expected a JSON object")
    # Also reject exponent overflow and PostgreSQL-incompatible escaped NUL values.
    json.dumps(result, allow_nan=False)
    _check_text(result)
    return result


def call_hash(name: str, arguments: str) -> str:
    try:
        canonical = json.dumps(json_object(arguments), sort_keys=True, separators=(",", ":"))
    except (ValueError, RecursionError):
        canonical = arguments
    return hashlib.sha256(f"{name}\n{canonical}".encode()).hexdigest()
