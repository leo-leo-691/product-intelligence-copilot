"""Category deep-dive from real input evidence only. Never invent Faucets/Fittings coverage."""

from __future__ import annotations

from pathlib import Path

from backend.app.unihack.discover import find_file
from backend.app.unihack.ingest import ingest_input_workbook
from backend.app.unihack.normalize import fold
from backend.app.unihack.official import ensure_sample_input
from backend.app.unihack.pipeline import process_row
from backend.app.unihack.schema import load_delivery_headers
from backend.app.unihack.official import ensure_expected_output

_FAUCET_FITTING = ("faucet", "fitting", "elbow", "nipple", "coupling", "tee")


def _blob(row: dict) -> str:
    return fold(" ".join(str(v) for v in row.values() if v)).lower()


def category_hits(rows: list[dict]) -> dict[str, int]:
    counts = {"Faucets": 0, "Fittings": 0}
    for row in rows:
        text = _blob(row)
        if "faucet" in text:
            counts["Faucets"] += 1
        if any(t in text for t in ("fitting", "elbow", "nipple", "coupling")):
            counts["Fittings"] += 1
    return counts


def build_deep_dive() -> dict:
    lov_faucets = find_file("lov_faucets")
    lov_fittings = find_file("lov_fittings")
    try:
        src = find_file("input_1000") or ensure_sample_input()
        ingested = ingest_input_workbook(src)
    except Exception as exc:  # noqa: BLE001
        return {
            "supported": False,
            "preferred_categories": ["Faucets", "Fittings"],
            "reason": f"Sample input not loaded: {exc}",
            "example": None,
        }

    hits = category_hits(ingested["rows"])
    supported = (hits["Faucets"] > 0 or hits["Fittings"] > 0) and bool(lov_faucets or lov_fittings)
    example_row = ingested["rows"][0] if ingested["rows"] else None
    example: dict | None = None
    if example_row:
        raw_view = {k: v for k, v in example_row.items() if k != "row_number"}
        try:
            headers = load_delivery_headers(ensure_expected_output())["headers"]
            processed = process_row(example_row, headers)
            filled = {
                h: processed["delivery"][h]
                for h in headers
                if str(processed["delivery"].get(h, "")).strip()
            }
            example = {
                "raw_input": raw_view,
                "classification": "Not assigned — no category taxonomy in the sample input file.",
                "extracted_attributes": filled,
                "normalized_lov": "NOT RUN — Faucets/Fittings LOV workbooks are not loaded.",
                "generated_descriptions": {
                    k: filled[k]
                    for k in filled
                    if k in {"INVOICE_DESC", "MOBILE_DESC", "SHORT_DESC", "LONG_DESC1", "Part_Desc"}
                },
                "validation": processed.get("issues") or [],
                "provenance": processed.get("provenance") or {},
                "note": "Values are copied or derived only from this input row. Blank delivery fields stay blank.",
            }
        except Exception as exc:  # noqa: BLE001
            example = {"raw_input": raw_view, "error": str(exc)}

    reason = (
        "Sample input contains Faucet/Fitting evidence and LOV files are present."
        if supported
        else (
            "Faucets/Fittings deep dive is not available: the official sample input has "
            f"{hits['Faucets']} faucet-like row(s) and {hits['Fittings']} fitting-like row(s), "
            "and dedicated Faucets/Fittings LOV files are not loaded. Coverage is not fabricated."
        )
    )
    return {
        "supported": supported,
        "preferred_categories": ["Faucets", "Fittings"],
        "category_hits": hits,
        "lov_faucets_present": lov_faucets is not None,
        "lov_fittings_present": lov_fittings is not None,
        "reason": reason,
        "example": example,
        "input_row_count": ingested["row_count"],
        "input_columns": ingested.get("input_headers") or [],
    }
