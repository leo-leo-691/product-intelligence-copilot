"""Ingest evaluation input rows with a dynamic column set."""

from __future__ import annotations

from pathlib import Path

from backend.app.unihack.constants import INPUT_ALIASES
from backend.app.unihack.excel import SheetTable, find_column, read_tables
from backend.app.unihack.normalize import clean_input, norm_key


class IngestError(ValueError):
    pass


def _pick_input_sheet(tables: list[SheetTable]) -> SheetTable:
    if not tables:
        raise IngestError("Workbook has no sheets")
    # Prefer the sheet with the most populated rows.
    return max(tables, key=lambda t: len(t.rows))


def ingest_input_workbook(path: Path) -> dict:
    tables = read_tables(path)
    if not tables:
        raise IngestError(f"No sheets/rows in {path.name}")
    sheet = _pick_input_sheet(tables)
    if not sheet.headers:
        raise IngestError(f"No header row in {path.name}")

    alias_map = {canon: find_column(sheet.headers, canon) for canon in INPUT_ALIASES}
    for canon, aliases in INPUT_ALIASES.items():
        if alias_map.get(canon):
            continue
        for alias in aliases:
            hit = find_column(sheet.headers, alias)
            if hit:
                alias_map[canon] = hit
                break

    rows: list[dict] = []
    skipped_empty = 0
    for i, raw in enumerate(sheet.rows, start=1):
        record: dict = {"row_number": i}
        nonempty = False
        for header in sheet.headers:
            val = clean_input(raw.get(header, ""))
            record[header] = val
            if val:
                nonempty = True
        for canon, actual in alias_map.items():
            if actual and actual in record:
                record[canon] = record[actual]
        if not nonempty:
            skipped_empty += 1
            continue
        rows.append(record)

    extra = [
        h
        for h in sheet.headers
        if norm_key(h) not in {norm_key(c) for c in INPUT_ALIASES}
    ]
    return {
        "path": str(path),
        "sheet": sheet.sheet_name,
        "header_row_index": sheet.header_row_index,
        "input_headers": sheet.headers,
        "row_count": len(rows),
        "skipped_empty": skipped_empty,
        "alias_map": alias_map,
        "extra_columns": extra,
        "duplicate_headers": sheet.duplicates,
        "rows": rows,
        "warnings": ([f"Duplicate headers: {sheet.duplicates}"] if sheet.duplicates else []),
    }
