from typing import Any

import httpx

from backend.app.config import settings
from backend.app.schemas.categories import CategorySchema
from backend.app.schemas.fields import ExtractionMethod, FieldProvenance, SourceType

# Seeded web values for demo when no search API key.
# Used for gap-fill (missing required) AND cross-check alternates (conflict demos).
SEEDED_WEB: dict[str, dict[str, Any]] = {
    "VALVE-CONFLICT-001": {
        "max_operating_pressure_psi": {
            "value": 285,
            "snippet": "Manufacturer site lists 285 psi working pressure (conflicts with datasheet 250 psi).",
        }
    },
    "default_valve_gap": {
        "end_connection": {"value": "RF Flanged", "snippet": "RF flanged ends per catalog."},
    },
}

# SKUs that must never invent missing required fields via default gap seeds
SPARSE_NO_GAP_FILL = {"VALVE-SPARSE-001"}


def _seeded_fp(seeded: dict[str, Any]) -> FieldProvenance:
    return FieldProvenance(
        value=seeded["value"],
        source_type=SourceType.WEB,
        source_snippet=seeded.get("snippet"),
        source_location="seeded-web",
        extraction_method=ExtractionMethod.WEB_AGENT,
        needs_review=True,
        not_found=False,
    )


async def gap_fill_field(
    sku: str,
    field_name: str,
    manufacturer: str | None,
    model: str | None,
) -> FieldProvenance | None:
    seeded = SEEDED_WEB.get(sku, {}).get(field_name)
    if not seeded and sku not in SPARSE_NO_GAP_FILL:
        seeded = SEEDED_WEB.get("default_valve_gap", {}).get(field_name)
    if seeded:
        return _seeded_fp(seeded)

    query = f"{manufacturer or ''} {model or ''} {field_name.replace('_', ' ')}".strip()
    result = await _web_search(query)
    if result is None:
        return None
    return FieldProvenance(
        value=result["value"],
        source_type=SourceType.WEB,
        source_snippet=result.get("snippet"),
        source_location=result.get("url", "web"),
        extraction_method=ExtractionMethod.WEB_AGENT,
        needs_review=True,
        not_found=False,
    )


async def _web_search(query: str) -> dict[str, Any] | None:
    if settings.tavily_api_key:
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                r = await client.post(
                    "https://api.tavily.com/search",
                    json={"api_key": settings.tavily_api_key, "query": query, "max_results": 2},
                )
                r.raise_for_status()
                data = r.json()
                if data.get("results"):
                    hit = data["results"][0]
                    return {
                        "value": hit.get("content", "")[:80],
                        "snippet": hit.get("content"),
                        "url": hit.get("url"),
                    }
        except Exception:
            pass
    if settings.serpapi_api_key:
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                r = await client.get(
                    "https://serpapi.com/search",
                    params={"api_key": settings.serpapi_api_key, "q": query, "engine": "google"},
                )
                r.raise_for_status()
                data = r.json()
                organic = data.get("organic_results") or []
                if organic:
                    hit = organic[0]
                    return {
                        "value": hit.get("title"),
                        "snippet": hit.get("snippet"),
                        "url": hit.get("link"),
                    }
        except Exception:
            pass
    return None


def collect_web_alternates(
    sku: str,
    fields: dict[str, FieldProvenance],
    seed_overrides: dict[str, Any] | None = None,
) -> dict[str, list[FieldProvenance]]:
    """Build alternate web values for conflict detection without overwriting document fields."""
    alts: dict[str, list[FieldProvenance]] = {}

    seeded = dict(SEEDED_WEB.get(sku, {}))
    if seed_overrides:
        for fname, val in seed_overrides.items():
            seeded[fname] = {"value": val, "snippet": "seed override"}

    for fname, meta in seeded.items():
        primary = fields.get(fname)
        if not primary or primary.not_found:
            continue
        fp = _seeded_fp(meta if isinstance(meta, dict) else {"value": meta, "snippet": "seed"})
        if str(fp.value).strip().lower() != str(primary.value).strip().lower():
            alts.setdefault(fname, []).append(fp)

    return alts


async def gap_fill_missing(
    sku: str,
    schema: CategorySchema,
    fields: dict[str, FieldProvenance],
    seed_overrides: dict[str, Any] | None = None,
) -> dict[str, FieldProvenance]:
    out = dict(fields)
    manufacturer = out.get("manufacturer")
    model = out.get("model_number") or out.get("part_number")
    mfr = manufacturer.value if manufacturer and not manufacturer.not_found else None
    mdl = model.value if model and not model.not_found else None

    if seed_overrides:
        for fname, val in seed_overrides.items():
            if fname in out and out[fname].not_found:
                out[fname] = FieldProvenance(
                    value=val,
                    source_type=SourceType.WEB,
                    source_snippet="seed override",
                    source_location="fixture",
                    extraction_method=ExtractionMethod.WEB_AGENT,
                    needs_review=True,
                    not_found=False,
                )

    if sku in SPARSE_NO_GAP_FILL:
        return out

    filled_count = 0
    max_calls = max(1, min(settings.gap_fill_max_calls, 5))
    for fdef in schema.fields:
        if not fdef.required:
            continue
        fp = out.get(fdef.name)
        if fp and not fp.not_found:
            continue
        # Cap gap-fill calls for scale
        if filled_count >= max_calls:
            break
        filled = await gap_fill_field(
            sku, fdef.name, str(mfr) if mfr else None, str(mdl) if mdl else None
        )
        if filled:
            out[fdef.name] = filled
            filled_count += 1
    return out
