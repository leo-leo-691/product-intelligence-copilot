METHOD_RELIABILITY: dict[str, float] = {
    "table-parse": 1.0,
    "text-LLM": 0.75,
    "vision-LLM": 0.65,
    "web-agent": 0.50,
    "mock": 0.70,
}


def compute_band(raw: float, validation_failed: bool, not_found: bool) -> str:
    if validation_failed or not_found:
        return "Low"
    if raw >= 0.75:
        return "High"
    if raw >= 0.45:
        return "Medium"
    return "Low"


def compute_confidence(
    extraction_method: str,
    source_types: list[str],
    values_by_source: dict[str, str],
    validation_failed: bool,
    format_match: float,
    not_found: bool,
    llm_agreement: float | None = None,
) -> tuple[float, str, dict[str, float]]:
    method = METHOD_RELIABILITY.get(extraction_method, 0.5)

    unique_vals = {v.strip().lower() for v in values_by_source.values() if v}
    if len(values_by_source) >= 2 and len(unique_vals) == 1:
        agreement = 1.0
    elif len(values_by_source) >= 2 and len(unique_vals) > 1:
        agreement = 0.0
    elif len(values_by_source) == 1:
        agreement = 0.5
    else:
        agreement = 0.0

    validation_score = 0.3 if validation_failed else 1.0
    raw = 0.35 * method + 0.25 * agreement + 0.25 * validation_score + 0.15 * format_match
    if validation_failed:
        raw = min(raw, 0.44)
    # Optional dual-LLM signal: does not replace the four-factor formula.
    if llm_agreement is not None:
        if llm_agreement <= 0.0:
            raw = min(raw, 0.44)
        elif llm_agreement >= 1.0:
            raw = min(1.0, raw + 0.05)

    band = compute_band(raw, validation_failed, not_found)
    reasoning = {
        "method_reliability": round(method, 3),
        "cross_source_agreement": round(agreement, 3),
        "validation_score": round(validation_score, 3),
        "format_match": round(format_match, 3),
        "raw": round(raw, 3),
    }
    if llm_agreement is not None:
        reasoning["llm_agreement"] = round(llm_agreement, 3)
    return raw, band, reasoning
