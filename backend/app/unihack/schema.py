"""Load Expected Output headers from the official sheet. Names are never invented."""

from __future__ import annotations

from pathlib import Path

from backend.app.unihack.excel import SheetTable, find_column, read_tables
from backend.app.unihack.normalize import norm_key


class SchemaError(ValueError):
    def __init__(self, message: str, report: dict | None = None):
        super().__init__(message)
        self.report = report or {}


def _header_row(table: SheetTable) -> list[str]:
    headers = [h.strip() for h in table.headers if str(h).strip() and not str(h).startswith("UNNAMED")]
    return headers


def load_delivery_headers(path: Path) -> dict:
    tables = read_tables(path)
    if not tables:
        raise SchemaError(f"No sheets in {path.name}")

    # Prefer the sheet with the most non-empty header cells (Expected Output is wide).
    ranked = sorted(tables, key=lambda t: len(_header_row(t)), reverse=True)
    chosen = _header_row(ranked[0])
    if not chosen:
        raise SchemaError(f"No headers found in {path.name}")

    keys = [norm_key(h) for h in chosen]
    duplicates = [h for i, h in enumerate(chosen) if keys[i] in keys[:i]]
    return {
        "path": str(path),
        "sheet": ranked[0].sheet_name,
        "headers": chosen,
        "header_count": len(chosen),
        "duplicates": duplicates,
        "valid": not duplicates,
    }


def validate_headers(headers: list[str], expected: list[str]) -> dict:
    missing = [h for h in expected if h not in headers]
    unexpected = [h for h in headers if h not in expected]
    order_ok = list(headers) == list(expected)
    report = {
        "expected_count": len(expected),
        "generated_count": len(headers),
        "actual_count": len(headers),
        "missing": missing,
        "missing_headers": missing,
        "unexpected": unexpected,
        "unexpected_headers": unexpected,
        "duplicate_headers": [h for i, h in enumerate(headers) if h in headers[:i]],
        "order": "PASS" if order_ok else "FAIL",
        "exact_match": order_ok,
        "valid": order_ok,
    }
    return report


def require_schema(headers: list[str], expected: list[str]) -> dict:
    report = validate_headers(headers, expected)
    if report["valid"]:
        return report
    raise SchemaError(
        "SCHEMA VALIDATION FAILED — "
        f"Expected headers: {report['expected_count']}; "
        f"Generated headers: {report['generated_count']}; "
        f"Missing: {len(report['missing'])}; "
        f"Unexpected: {len(report['unexpected'])}; "
        f"Order: {report['order']}",
        report,
    )




def empty_row(headers: list[str]) -> dict[str, str]:
    return {h: "" for h in headers}


def guess_header(headers: list[str], *needles: str) -> str | None:
    for needle in needles:
        hit = find_column(headers, needle)
        if hit:
            return hit
    nset = [norm_key(n) for n in needles if n]
    for h in headers:
        hk = norm_key(h)
        if any(n and n == hk for n in nset):
            return h
    return None
