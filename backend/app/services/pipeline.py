from backend.app.config import ROOT
from backend.app.models.product import ProductInput, ProductRecord
from backend.app.schemas.categories import CATEGORIES
from backend.app.schemas.fields import ConfidenceBand, FieldProvenance
from backend.app.services.confidence import compute_confidence
from backend.app.services.conflicts import detect_conflicts
from backend.app.services.extraction import extract_fields
from backend.app.services.gap_fill import collect_web_alternates, gap_fill_missing
from backend.app.services.ingestion import guess_source_template, ingest_product_input
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
    if inp.category_id not in CATEGORIES:
        raise ValueError(f"Unknown category: {inp.category_id}")

    schema = CATEGORIES[inp.category_id]
    parsed = ingest_product_input(inp, ROOT)
    template = inp.source_template_id or guess_source_template(parsed.text)

    fields = extract_fields(parsed.text, schema, inp.sku)
    if parsed.images:
        fields = extract_from_images(parsed.images, schema, fields, inp.sku)

    fields = await gap_fill_missing(inp.sku, schema, fields, inp.seed_web_overrides)
    web_alts = collect_web_alternates(inp.sku, fields, inp.seed_web_overrides)

    fields = _apply_confidence(schema, fields, web_alts)
    fields = validate_record(schema, fields)
    conflicts = detect_conflicts(fields, web_alts)

    return ProductRecord(
        sku=inp.sku,
        category_id=inp.category_id,
        source_template_id=template,
        fields=fields,
        conflicts=conflicts,
        batch_id=batch_id,
    )
