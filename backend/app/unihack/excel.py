"""Compatibility exports for UniHack workbook readers."""

from backend.app.unihack.excel_io import (
    SheetTable,
    cell_str,
    find_column,
    normalize_header_key,
    read_csv_table,
    read_tables,
    read_xlsx_tables,
)

SheetTable = SheetTable
SheetTable = SheetTable
cell_str = cell_str
find_column = find_column
read_tables = read_tables
read_csv_table = read_csv_table
read_xlsx_tables = read_xlsx_tables

__all__ = [
    "SheetTable",
    "SheetTable",
    "cell_str",
    "cell_str",
    "find_column",
    "find_column",
    "normalize_header_key",
    "read_csv_table",
    "read_csv_table",
    "read_tables",
    "read_tables",
    "read_xlsx_tables",
    "read_xlsx_tables",
]
