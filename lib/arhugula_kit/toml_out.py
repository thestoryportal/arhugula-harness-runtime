"""Write a configuration mapping as TOML.

The standard library reads TOML (`tomllib`) and does not write it. This writer covers the
value shapes the runtime's configuration uses: strings, integers, floats, booleans, lists,
and string-keyed mappings nested to any depth, including lists of mappings.

[LAW:verifiable-goals] `dumps` re-reads its own output with `tomllib` and refuses to return
text that does not parse back to the input, so a generated file is correct or absent.
"""

from __future__ import annotations

import json
import re
import tomllib
from collections.abc import Mapping, Sequence
from typing import Any

__all__ = ["dumps"]

_BARE_KEY = re.compile(r"[A-Za-z0-9_-]+")


def _key(name: str) -> str:
    return name if _BARE_KEY.fullmatch(name) else json.dumps(name, ensure_ascii=False)


def _is_table(value: object) -> bool:
    return isinstance(value, Mapping)


def _is_table_array(value: object) -> bool:
    return (
        isinstance(value, Sequence)
        and not isinstance(value, str)
        and len(value) > 0
        and all(isinstance(item, Mapping) for item in value)
    )


def _inline(value: object) -> str:
    """A value that fits on one line: a scalar, a list of scalars, or an empty mapping."""
    match value:
        case bool():
            return "true" if value else "false"
        case str():
            return json.dumps(value, ensure_ascii=False)
        case int() | float():
            return repr(value)
        case Mapping():
            items = ", ".join(f"{_key(str(k))} = {_inline(v)}" for k, v in value.items())
            return "{ " + items + " }" if items else "{}"
        case Sequence():
            return "[" + ", ".join(_inline(item) for item in value) + "]"
        case _:
            raise TypeError(f"TOML cannot carry a value of type {type(value).__name__}: {value!r}")


def _emit(path: tuple[str, ...], table: Mapping[str, Any], out: list[str]) -> None:
    """Emit one table: its own keys first, then sub-tables, then arrays of tables."""
    for name, value in table.items():
        if not (_is_table(value) and value) and not _is_table_array(value):
            out.append(f"{_key(name)} = {_inline(value)}")
    for name, value in table.items():
        if _is_table(value) and value:
            child = (*path, name)
            out.append("")
            out.append("[" + ".".join(_key(part) for part in child) + "]")
            _emit(child, value, out)
    for name, value in table.items():
        if _is_table_array(value):
            child = (*path, name)
            for item in value:
                out.append("")
                out.append("[[" + ".".join(_key(part) for part in child) + "]]")
                _emit(child, item, out)


def dumps(document: Mapping[str, Any], *, header: str = "") -> str:
    """The document as TOML text, preceded by `header` as comment lines."""
    out: list[str] = [f"# {line}".rstrip() for line in header.splitlines()]
    if out:
        out.append("")
    _emit((), document, out)
    text = "\n".join(out) + "\n"
    parsed = tomllib.loads(text)
    if parsed != _plain(document):
        raise ValueError("generated TOML does not read back to the document it was written from")
    return text


def _plain(value: Any) -> Any:
    """The value as the plain dict/list/scalar tree `tomllib` returns."""
    match value:
        case Mapping():
            return {str(k): _plain(v) for k, v in value.items()}
        case str():
            return value
        case Sequence():
            return [_plain(item) for item in value]
        case _:
            return value
