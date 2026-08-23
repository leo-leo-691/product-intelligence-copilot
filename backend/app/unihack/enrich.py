"""Catalog enrichment orchestrator: identify → discover → retrieve → extract → map."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from backend.app.config import settings
from backend.app.unihack.attribute_map import map_to_delivery, verified_facts
from backend.app.unihack.extract_attrs import extract_from_page, merge_extractions
from backend.app.unihack.identify import ProductIdentity, identify_product
from backend.app.unihack.retrieve import PageRetriever, is_pdf_url
from backend.app.unihack.sources import SourceDiscoveryResult, discover_sources

logger = logging.getLogger(__name__)


@dataclass
class EnrichmentResult:
    delivery: dict[str, str] = field(default_factory=dict)
    provenance: dict[str, dict[str, Any]] = field(default_factory=dict)
    identity: ProductIdentity | None = None
    discovery: SourceDiscoveryResult | None = None
    source_url: str = ""
    attributes_extracted: int = 0
    images_found: int = 0
    spec_sheet_found: bool = False
    verified_facts: list[str] = field(default_factory=list)
    error: str | None = None
    skipped: bool = False


def enrich_product(
    raw: dict[str, str],
    headers: list[str],
    *,
    input_delivery: dict[str, str] | None = None,
    retriever: PageRetriever | None = None,
    search_fn: Callable | None = None,
    enrichment_enabled: bool | None = None,
) -> EnrichmentResult:
    """Run full enrichment pipeline for one row. Failures return partial/blank fields."""
    enabled = settings.unihack_enrichment_enabled if enrichment_enabled is None else enrichment_enabled
    result = EnrichmentResult()
    input_delivery = input_delivery or {}

    identity = identify_product(raw)
    result.identity = identity

    if not enabled:
        result.skipped = True
        return result

    if not identity.mfg_part_num and not identity.part_desc:
        result.error = "missing product identifier"
        return result

    row_num = raw.get("row_number", "?")
    try:
        discovery = discover_sources(
            identity,
            **({"search_fn": search_fn} if search_fn is not None else {}),
        )
        result.discovery = discovery

        if not discovery.sources:
            logger.info(
                "[row %s] product: %s | manufacturer: %s | source discovery: none",
                row_num,
                identity.mfg_part_num or identity.part_desc,
                identity.manufacturer_query or "unknown",
            )
            result.error = discovery.error or "no sources discovered"
            return result

        retriever = retriever or PageRetriever()
        extractions = []
        pages_fetched = 0
        max_pages = settings.unihack_max_source_pages

        for src in discovery.sources:
            if pages_fetched >= max_pages:
                break
            if src.score < 30:
                continue
            page = retriever.get(
                src.url,
                manufacturer=identity.manufacturer_query,
                part_number=identity.mfg_part_num,
            )
            if not page:
                continue
            pages_fetched += 1
            extracted = extract_from_page(page, identity)
            if extracted.attributes or extracted.images:
                extractions.append(extracted)
                if not result.source_url:
                    result.source_url = page.url

        if not extractions:
            top = discovery.sources[0]
            logger.info(
                "[row %s] product: %s | manufacturer: %s | source discovery: partial | source: %s | retrieve: failed",
                row_num,
                identity.mfg_part_num,
                identity.manufacturer_query or "unknown",
                top.url,
            )
            result.error = "sources found but pages not retrieved"
            return result

        merged = merge_extractions(extractions)
        delivery, provenance = map_to_delivery(
            merged,
            headers,
            identity,
            input_values=input_delivery,
        )
        result.delivery = delivery
        result.provenance = provenance
        result.attributes_extracted = len(merged.attributes)
        result.images_found = len(merged.images)
        result.spec_sheet_found = bool(merged.spec_sheet_url)
        result.verified_facts = verified_facts(merged)

        logger.info(
            "[row %s] product: %s | manufacturer: %s | source discovery: success | source: %s | "
            "attributes extracted: %s | images found: %s | spec sheet: %s",
            row_num,
            identity.mfg_part_num,
            identity.manufacturer_query or delivery.get("MANUFACTURER_NAME") or "unknown",
            result.source_url,
            result.attributes_extracted,
            result.images_found,
            "found" if result.spec_sheet_found else "none",
        )
    except Exception as exc:  # noqa: BLE001 — row isolation
        logger.warning(
            "[row %s] enrichment failed for %s: %s",
            row_num,
            identity.mfg_part_num,
            exc,
            exc_info=True,
        )
        result.error = str(exc)

    return result
