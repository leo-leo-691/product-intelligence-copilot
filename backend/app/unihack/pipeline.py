"""Turn one evaluation input row into a full Expected Output row + provenance.

Unknown output fields stay blank. Input is copied when headers match; enrichment
fills additional fields only from retrieved, evidence-based sources.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from backend.app.unihack.describe import build_descriptions
from backend.app.unihack.enrich import enrich_product
from backend.app.unihack.excel import find_column
from backend.app.unihack.lov import validate_value
from backend.app.unihack.manufacturer import resolve_brand, resolve_manufacturer
from backend.app.unihack.normalize import clean_input
from backend.app.unihack.schema import empty_row, guess_header
from backend.app.unihack.uom import apply_uom_in_text

logger = logging.getLogger(__name__)


def _set(
    delivery: dict[str, str],
    provenance: dict[str, dict[str, Any]],
    header: str | None,
    value: str,
    source: str,
    confidence: str,
    needs_review: bool = False,
    issues: list[str] | None = None,
    evidence: str = "",
) -> None:
    if not header or not value:
        return
    delivery[header] = value
    provenance[header] = {
        "value": value,
        "source": source,
        "confidence": confidence,
        "review_status": "pending",
        "needs_review": needs_review,
        "issues": issues or [],
        "evidence": evidence,
    }


def _merge_enrichment(
    delivery: dict[str, str],
    provenance: dict[str, dict[str, Any]],
    enriched_delivery: dict[str, str],
    enriched_provenance: dict[str, dict[str, Any]],
) -> None:
    for header, value in enriched_delivery.items():
        if not value or delivery.get(header):
            continue
        delivery[header] = value
        if header in enriched_provenance:
            provenance[header] = enriched_provenance[header]


def process_row(
    raw: dict[str, str],
    headers: list[str],
    *,
    manufacturer_path: Path | None = None,
    lov_paths: list[Path] | None = None,
    uom_path: Path | None = None,
    enrichment_enabled: bool | None = None,
) -> dict[str, Any]:
    delivery = empty_row(headers)
    provenance: dict[str, dict[str, Any]] = {}
    issues: list[str] = []
    review = False
    enrichment_stats: dict[str, Any] = {}

    raw_keys = [k for k in raw.keys() if k != "row_number"]

    # 1) Exact / normalized header match: copy input → output. Never invent.
    for header in headers:
        src = header if header in raw else find_column(raw_keys, header)
        if not src:
            continue
        val = clean_input(str(raw.get(src, "")))
        if val:
            _set(delivery, provenance, header, val, "input", "High")

    mfr_q = clean_input(str(raw.get("Part_Manuf") or raw.get("Part_Manuf") or ""))
    brand_q = clean_input(
        str(
            raw.get("Unilog_Brand")
            or raw.get("E1_Brand")
            or raw.get("DIB_Brand")
            or ""
        )
    )
    mpn = clean_input(str(raw.get("Mfg_Part_Num") or raw.get("Mfg_Part_Num") or ""))
    desc = clean_input(str(raw.get("Part_Desc") or raw.get("Part_Desc") or ""))

    if not mfr_q:
        src = find_column(raw_keys, "Part_Manuf") or find_column(raw_keys, "manufacturer")
        mfr_q = clean_input(str(raw.get(src, ""))) if src else ""
    if not mpn:
        src = find_column(raw_keys, "Mfg_Part_Num") or find_column(raw_keys, "mpn")
        mpn = clean_input(str(raw.get(src, ""))) if src else ""
    if not desc:
        src = find_column(raw_keys, "Part_Desc") or find_column(raw_keys, "description")
        desc = clean_input(str(raw.get(src, ""))) if src else ""

    mfr = resolve_manufacturer(mfr_q, manufacturer_path)
    brand = resolve_brand(brand_q, manufacturer_path)

    mfr_header = guess_header(headers, "MANUFACTURER_NAME", "Part_Manuf", "manufacturer")
    brand_header = guess_header(headers, "BRAND_NAME", "Unilog_Brand", "brand")

    if mfr.matched_name:
        _set(
            delivery,
            provenance,
            mfr_header,
            mfr.matched_name,
            "reference",
            "High" if not mfr.needs_review else "Medium",
            needs_review=mfr.needs_review,
            issues=["ambiguous manufacturer"] if mfr.needs_review else [],
        )
        if mfr.needs_review:
            review = True
            issues.append("Manufacturer match is ambiguous — human review required.")
    elif mfr_q and manufacturer_path:
        review = True
        issues.append("Manufacturer not found in catalog — value not invented.")

    if brand.matched_name:
        _set(
            delivery,
            provenance,
            brand_header,
            brand.matched_name,
            "reference",
            "High" if not brand.needs_review else "Medium",
            needs_review=brand.needs_review,
        )
        if brand.needs_review:
            review = True
    elif brand_q and manufacturer_path:
        review = True
        issues.append("Brand not found in catalog — value not invented.")

    # 2) Dynamic catalog enrichment from discovered sources.
    enrichment = enrich_product(
        raw,
        headers,
        input_delivery=delivery,
        enrichment_enabled=enrichment_enabled,
    )
    enrichment_stats = {
        "attributes_extracted": enrichment.attributes_extracted,
        "images_found": enrichment.images_found,
        "spec_sheet_found": enrichment.spec_sheet_found,
        "source_url": enrichment.source_url,
        "error": enrichment.error,
        "skipped": enrichment.skipped,
    }
    if enrichment.delivery:
        _merge_enrichment(delivery, provenance, enrichment.delivery, enrichment.provenance)
    if enrichment.error and not enrichment.skipped:
        issues.append(f"Enrichment partial: {enrichment.error}")

    # Prefer catalog-resolved names, then enriched, then raw input.
    effective_mfr = mfr.matched_name or delivery.get(mfr_header or "", "") or mfr_q
    effective_brand = brand.matched_name or delivery.get(brand_header or "", "") or brand_q

    desc_h = guess_header(headers, "Part_Desc", "description")
    if desc_h and uom_path:
        new, changed = apply_uom_in_text(delivery.get(desc_h, "") or desc, uom_path)
        if changed:
            _set(delivery, provenance, desc_h, new, "uom", "High")

    # Descriptions derived only from known input + verified enriched attributes.
    if desc or mpn or enrichment.verified_facts:
        texts = build_descriptions(
            part_desc=desc or delivery.get(desc_h or "", ""),
            manufacturer=effective_mfr,
            brand=effective_brand,
            mfg_part_num=mpn,
            verified_facts=enrichment.verified_facts,
        )
        for needles, key in (
            (("INVOICE_DESC", "invoice"), "invoice"),
            (("MOBILE_DESC", "mobile"), "mobile"),
            (("SHORT_DESC", "product title", "title"), "title"),
            (("LONG_DESC1", "long description"), "long"),
        ):
            target = guess_header(headers, *needles)
            if target and not delivery.get(target):
                _set(delivery, provenance, target, texts[key], "generated", "Medium")

    for path in lov_paths or []:
        for header, val in list(delivery.items()):
            if not val:
                continue
            result = validate_value(path, header, val)
            if not result.get("applicable"):
                continue
            if result.get("compliant") is False:
                review = True
                entry = provenance.setdefault(
                    header,
                    {
                        "value": val,
                        "source": "input",
                        "confidence": "Low",
                        "review_status": "pending",
                        "needs_review": True,
                        "issues": [],
                    },
                )
                entry["needs_review"] = True
                entry.setdefault("issues", []).append("LOV mismatch")
                entry["confidence"] = "Low"
            elif result.get("compliant") and result.get("normalized") and result["normalized"] != val:
                _set(delivery, provenance, header, result["normalized"], "lov", "High")

    filled = sum(1 for v in delivery.values() if str(v).strip())
    if not mpn:
        review = True
        issues.append("Missing manufacturer part number")

    return {
        "row_number": raw.get("row_number"),
        "mfg_part_num": mpn,
        "status": "ok",
        "error": None,
        "delivery": delivery,
        "provenance": provenance,
        "fields_generated": filled,
        "fields_missing": len(headers) - filled,
        "review_required": review or any(p.get("needs_review") for p in provenance.values()),
        "issues": issues,
        "confidence": "Low" if review else ("High" if filled >= 4 else "Medium"),
        "enrichment": enrichment_stats,
    }
