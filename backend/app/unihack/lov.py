"""Controlled-vocabulary (LOV) loading and validation."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from backend.app.unihack.excel import find_column, read_tables
from backend.app.unihack.normalize import clean_input, norm_key


def _pick(headers: list[str], *names: str) -> str | None:
    for n in names:
        hit = find_column(headers, n)
        if hit:
            return hit
    for h in headers:
        hl = h.lower()
        for n in names:
            if n.lower() in hl:
                return h
    return None


@lru_cache(maxsize=8)
def load_lov(path: str) -> dict[str, dict[str, set[str]]]:
    """classpath -> attribute -> allowed values (normalized key + original)."""
    catalog: dict[str, dict[str, set[str]]] = {}
    originals: dict[str, dict[str, dict[str, str]]] = {}
    for table in read_tables(Path(path)):
        classpath = _pick(table.headers, "classpath", "class path", "category", "node")
        attr = _pick(table.headers, "attribute", "attribute_name", "field", "property")
        value = _pick(table.headers, "value", "lov", "allowed_value", "valid_value")
        if not attr or not value:
            continue
        for row in table.rows:
            a = clean_input(row.get(attr, ""))
            v = clean_input(row.get(value, ""))
            if not a or not v:
                continue
            cp = clean_input(row.get(classpath, "")) if classpath else "*"
            catalog.setdefault(cp, {}).setdefault(a, set()).add(norm_key(v))
            originals.setdefault(cp, {}).setdefault(a, {})[norm_key(v)] = v
    load_lov._originals = originals  # type: ignore[attr-defined]
    return catalog


def allowed_values(path: Path | None, attribute: str, classpath: str = "*") -> set[str]:
    if not path or not path.exists():
        return set()
    cat = load_lov(str(path))
    keys = cat.get(classpath) or cat.get("*") or {}
    # attribute name fuzzy: exact then contained
    if attribute in keys:
        return keys[attribute]
    nk = norm_key(attribute)
    for name, vals in keys.items():
        if norm_key(name) == nk:
            return vals
    return set()


def validate_value(path: Path | None, attribute: str, value: str, classpath: str = "*") -> dict:
    raw = clean_input(value)
    if not path or not path.exists():
        return {
            "applicable": False,
            "value": raw,
            "normalized": raw,
            "compliant": None,
            "reason": "LOV master not loaded",
        }
    allowed = allowed_values(path, attribute, classpath)
    if not allowed:
        return {
            "applicable": False,
            "value": raw,
            "normalized": raw,
            "compliant": None,
            "reason": "attribute not in LOV",
        }
    if not raw:
        return {
            "applicable": True,
            "value": raw,
            "normalized": "",
            "compliant": False,
            "reason": "empty",
        }
    ok = norm_key(raw) in allowed
    originals = getattr(load_lov, "_originals", {})
    canon = (
        originals.get(classpath, {}).get(attribute, {}).get(norm_key(raw))
        or originals.get("*", {}).get(attribute, {}).get(norm_key(raw))
        or raw
    )
    return {
        "applicable": True,
        "value": raw,
        "normalized": canon if ok else raw,
        "compliant": ok,
        "reason": "in_lov" if ok else "not_in_lov",
    }
