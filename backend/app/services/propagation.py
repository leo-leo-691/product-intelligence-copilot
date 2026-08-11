from backend.app.models.product import ProductRecord, PropagationSuggestion, utc_now
from backend.app.schemas.fields import FieldProvenance


def find_propagation_candidates(
    records: list[ProductRecord],
    source_product_id: str,
    field_name: str,
    old_value,
    new_value,
) -> PropagationSuggestion | None:
    source = next((r for r in records if r.id == source_product_id), None)
    if not source or not source.source_template_id:
        return None

    candidates: list[str] = []
    for r in records:
        if r.id == source_product_id:
            continue
        if r.source_template_id != source.source_template_id:
            continue
        fp = r.fields.get(field_name)
        if not fp:
            continue
        if fp.value == old_value or (fp.not_found and old_value is None):
            candidates.append(r.id)

    if not candidates:
        return None

    return PropagationSuggestion(
        source_template_id=source.source_template_id,
        field_name=field_name,
        old_value=old_value,
        new_value=new_value,
        source_product_id=source_product_id,
        candidate_product_ids=candidates,
    )


def apply_propagation(
    records: list[ProductRecord],
    suggestion: PropagationSuggestion,
) -> list[ProductRecord]:
    updated: list[ProductRecord] = []
    ids = set(suggestion.candidate_product_ids)
    for r in records:
        if r.id not in ids:
            updated.append(r)
            continue
        fp = r.fields.get(suggestion.field_name)
        if not fp:
            fp = FieldProvenance()
        fp.value = suggestion.new_value
        fp.not_found = False
        fp.review_status = "edited"
        fp.needs_review = False
        r.fields[suggestion.field_name] = fp
        r.updated_at = utc_now()
        updated.append(r)
    return updated
