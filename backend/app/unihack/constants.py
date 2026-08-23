"""Official UniHack spreadsheet URLs and known field aliases.

Delivery header *names* are never hardcoded here. They are loaded from the
official Expected Output sheet (cached locally after fetch).
"""

from __future__ import annotations

# Official published Google Sheets (CSV export).
OFFICIAL_SAMPLE_INPUT_CSV = (
    "https://docs.google.com/spreadsheets/d/1s17x6NWlsaTAMpjLgw1PeeGA2Iuq8unazUFAW4pkqsk/export?format=csv"
)
OFFICIAL_EXPECTED_OUTPUT_CSV = (
    "https://docs.google.com/spreadsheets/d/1llbNCJkwTrirP1Anzke9u3pQ_k7lCk52TXygUbfhSD8/export?format=csv"
)

# Placeholders from the official sample input and Expected Output examples.
# Matched after Unicode fold + lowercase. Never emit these as brand values.
PLACEHOLDERS = (
    "-- unbranded --",
    "-- no unilog brand --",
    "-- no dib brand --",
)

# Optional aliases for *input* columns when present. Extra columns are still ingested.
INPUT_ALIASES: dict[str, tuple[str, ...]] = {
    "Mfg_Part_Num": ("mfg_part_num", "mfg part num", "manufacturer part number", "mpn"),
    "Part_Desc": ("part_desc", "part desc", "description", "product description"),
    "E1_Brand": ("e1_brand", "e1 brand"),
    "Unilog_Brand": ("unilog_brand", "unilog brand"),
    "DIB_Brand": ("dib_brand", "dib brand"),
    "Part_Manuf": ("part_manuf", "part manuf", "manufacturer", "mfr"),
}

FILE_ALIASES: dict[str, tuple[str, ...]] = {
    "input_1000": (
        "sample_input.csv",
        "unihack__sample_dataset___input.csv",
        "unihack_sample_dataset_input.csv",
        "official_sample_input.csv",
        "sample-1000_items.xlsx",
        "sample-1000_items.csv",
        "sample_1000_items.xlsx",
    ),
    "expected_output": (
        "unihack__expected_output___delivery_format.csv",
        "unihack_expected_output_delivery_format.csv",
        "official_expected_output.csv",
        "expected_output.csv",
        "expected-output.csv",
    ),
    "ground_truth_200": (
        "unilog-sample_200_items-input-vs-output.xlsx",
        "unilog-sample_200_items-input-vs-output.csv",
        "unilog_sample_200_items_input_vs_output.xlsx",
    ),
    "uom": (
        "unilog_master_uom_standards_abbreviations_and_terms.xlsx",
    ),
    "fractions": ("decimal_fraction.xlsx",),
    "manufacturers": ("unicat_manufacturer_and_brand_list.xlsx",),
    "lov": ("unicat_lov_v1_0_updated_with_remarks.xlsx",),
    "lov_faucets": ("faucets_lov.xlsx",),
    "lov_fittings": ("fittings_lov.xlsx",),
    "guidelines": ("unilog_internal_content_guidelines.docx",),
}

MISSING_FILE_HINTS: dict[str, str] = {
    "input_1000": "MISSING INPUT: official sample input CSV (or upload an evaluation input file)",
    "expected_output": "MISSING INPUT: official Expected Output sheet (headers)",
    "ground_truth_200": "Ground-truth file not provided — evaluation metrics will be N/A",
    "delivery_schema": "MISSING INPUT: official Expected Output sheet (headers)",
}
