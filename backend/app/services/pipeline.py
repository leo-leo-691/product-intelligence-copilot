from backend.app.config import ROOT, settings
from backend.app.models.product import ProductInput, ProductRecord
from backend.app.schemas.categories import CATEGORIES
from backend.app.schemas.fields import ConfidenceBand, FieldProvenance
from backend.app.services.category_infer import infer_category
from backend.app.services.confidence import compute_confidence
from backend.app.services.conflicts import detect_conflicts
from backend.app.services.crawl import capped_crawl
from backend.app.services.extraction import extract_fields
from backend.app.services.gap_fill import collect_web_alternates, gap_fill_missing
from backend.app.services.ingestion import guess_source_template, ingest_product_input
from backend.app.services.knowledge_graph import upsert_product_graph
from backend.app.services.language import detect_language, maybe_normalize_to_english
from backend.app.services.outliers import detect_outliers
from backend.app.services.storage import list_products
from backend.app.services.validation import validate_field, validate_record
from backend.app.services.vision import extract_from_images


def _apply_confidence(
    schema,
    fields: dict[str, FieldProvenance],
    web_alts: dict[str, list[FieldProvenance]],
):
    for fdef in schema.fields:
        fp = fields.get(fdef.name, FieldProvenance(not_found=True))
        fp, fmt, val_failed = validate_field(fdef, fp)
        values_by_source: dict[str, str] = {}
        if fp.source_type and fp.value is not None and not fp.not_found:
            values_by_source[fp.source_type.value] = str(fp.value)
        for alt in web_alts.get(fdef.name, []):
            if alt.source_type and alt.value is not None:
                values_by_source[alt.source_type.value] = str(alt.value)
        raw, band, reasoning = compute_confidence(
            fp.extraction_method.value,
            list(values_by_source.keys()),
            values_by_source,
            val_failed,
            fmt,
            fp.not_found,
        )
        fp.confidence_raw = raw
        fp.confidence_score = ConfidenceBand(band)
        fp.confidence_reasoning = reasoning
        if band == "High" and not val_failed and not fp.not_found:
            fp.needs_review = False
        else:
            fp.needs_review = True
        fields[fdef.name] = fp
    return fields


async def run_pipeline(inp: ProductInput, batch_id: str | None = None) -> ProductRecord:
    parsed = ingest_product_input(inp, ROOT)

    if inp.url and settings.crawl_enabled:
        try:
            pages = await capped_crawl(inp.url)
            extra = "\n\n".join(p["text"] for p in pages[1:])
            if extra.strip():
                parsed.text = (parsed.text or "") + "\n\n[CRAWL]\n" + extra[:12000]
        except Exception:
            pass

    lang_meta = detect_language(parsed.text)
    work_text, lang_meta = maybe_normalize_to_english(parsed.text, lang_meta)

    category_id = inp.category_id
    inference_meta = None
    if not category_id or category_id in ("auto", "infer"):
        cid, reason, conf = infer_category(work_text, title=inp.title, sku=inp.sku)
        category_id = cid
        inference_meta = {"category_id": cid, "reasoning": reason, "confidence": conf}

    if category_id not in CATEGORIES:
        raise ValueError(f"Unknown category: {category_id}")

    schema = CATEGORIES[category_id]
    template = inp.source_template_id or guess_source_template(work_text)

    fields = extract_fields(work_text, schema, inp.sku)

    if parsed.images:
        fields = extract_from_images(parsed.images, schema, fields, inp.sku)

    fields = await gap_fill_missing(inp.sku, schema, fields, inp.seed_web_overrides)
    web_alts = collect_web_alternates(inp.sku, fields, inp.seed_web_overrides)

    fields = _apply_confidence(schema, fields, web_alts)
    fields = validate_record(schema, fields)
    conflicts = detect_conflicts(fields, web_alts)

    peers = [p for p in list_products() if p.category_id == category_id]
    outliers = detect_outliers(category_id, fields, peers, inp.sku)

    record = ProductRecord(
        sku=inp.sku,
        category_id=category_id,
        source_template_id=template,
        fields=fields,
        conflicts=conflicts,
        batch_id=batch_id,
        category_inference=inference_meta,
        language=lang_meta,
        outliers=outliers,
    )

    if settings.kg_enabled:
        try:
            record.kg = upsert_product_graph(record)
        except Exception:
            record.kg = {"enabled": True, "error": "kg upsert failed"}

    return record
