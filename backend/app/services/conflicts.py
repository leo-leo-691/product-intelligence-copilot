from backend.app.schemas.fields import ConflictCandidate, FieldConflict, FieldProvenance, SourceType


def _norm(v) -> str:
    if v is None:
        return ""
    return str(v).strip().lower()


def detect_conflicts(
    fields: dict[str, FieldProvenance],
    alternate_sources: dict[str, list[FieldProvenance]] | None = None,
) -> list[FieldConflict]:
    """Flag when document vs web (or other) disagree."""
    conflicts: list[FieldConflict] = []
    alternate_sources = alternate_sources or {}

    for field_name, alts in alternate_sources.items():
        primary = fields.get(field_name)
        if not primary or primary.not_found:
            continue
        candidates: list[ConflictCandidate] = [
            ConflictCandidate(
                value=primary.value,
                source_type=primary.source_type or SourceType.DOCUMENT,
                source_snippet=primary.source_snippet,
                source_location=primary.source_location,
                extraction_method=primary.extraction_method,
            )
        ]
        for alt in alts:
            if _norm(alt.value) != _norm(primary.value) and alt.value is not None:
                candidates.append(
                    ConflictCandidate(
                        value=alt.value,
                        source_type=alt.source_type or SourceType.WEB,
                        source_snippet=alt.source_snippet,
                        source_location=alt.source_location,
                        extraction_method=alt.extraction_method,
                    )
                )
        if len(candidates) > 1:
            conflicts.append(FieldConflict(field_name=field_name, candidates=candidates))

    return conflicts
