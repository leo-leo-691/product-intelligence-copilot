"""UOM and decimal/fraction normalization from official workbooks."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from backend.app.unihack.excel import find_column, read_tables
from backend.app.unihack.normalize import clean_input, fold, norm_key

_NUM_UNIT = re.compile(
    r"(?P<num>\d+(?:\.\d+)?)(?:\s*)(?P<unit>[A-Za-z.\"]+)"
)


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


@lru_cache(maxsize=4)
def load_uom_map(path: str) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for table in read_tables(Path(path)):
        src = _pick(table.headers, "alias", "abbreviation", "from", "uom", "unit", "term")
        dst = _pick(table.headers, "standard", "canonical", "approved", "to", "preferred")
        if not src:
            continue
        # if only one unit column, treat values as already canonical
        for row in table.rows:
            a = clean_input(row.get(src, ""))
            b = clean_input(row.get(dst, "")) if dst else a
            if a:
                mapping[norm_key(a)] = b or a
            if b:
                mapping.setdefault(norm_key(b), b)
    return mapping


@lru_cache(maxsize=2)
def load_fraction_map(path: str) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for table in read_tables(Path(path)):
        dec = _pick(table.headers, "decimal", "dec", "value")
        frac = _pick(table.headers, "fraction", "frac")
        if not dec or not frac:
            continue
        for row in table.rows:
            d = clean_input(row.get(dec, ""))
            f = clean_input(row.get(frac, ""))
            if d and f:
                mapping[d] = f
                try:
                    mapping[str(float(d))] = f
                except ValueError:
                    pass
    return mapping


def normalize_uom_token(token: str, uom_path: Path | None) -> str:
    raw = fold(token)
    if not raw or not uom_path or not uom_path.exists():
        return raw
    mapped = load_uom_map(str(uom_path)).get(norm_key(raw))
    return mapped or raw


def apply_uom_in_text(text: str, uom_path: Path | None) -> tuple[str, bool]:
    """Replace unit tokens using the official map. Returns (text, changed)."""
    if not text or not uom_path or not uom_path.exists():
        return text, False
    mapping = load_uom_map(str(uom_path))
    if not mapping:
        return text, False

    def repl(match: re.Match[str]) -> str:
        num = match.group("num")
        unit = match.group("unit")
        canon = mapping.get(norm_key(unit), unit)
        # approved form: number, space, unit
        return f"{num} {canon}"

    new = _NUM_UNIT.sub(repl, text)
    return new, new != text


def decimal_to_fraction(value: str, fraction_path: Path | None) -> str:
    raw = clean_input(value)
    if not raw or not fraction_path or not fraction_path.exists():
        return raw
    fracs = load_fraction_map(str(fraction_path))
    if raw in fracs:
        return fracs[raw]
    try:
        return fracs.get(str(float(raw)), raw)
    except ValueError:
        return raw
