import re
from dataclasses import dataclass
from pathlib import Path

from backend.app.config import settings
from backend.app.llm import get_llm_service
from backend.app.llm.compare import values_equivalent
from backend.app.llm.dual import merge_conflicts
from backend.app.schemas.categories import CategorySchema
from backend.app.schemas.fields import (
    ConflictCandidate,
    DualLLMMeta,
    ExtractionMethod,
    FieldConflict,
    FieldProvenance,
    SourceType,
)
from backend.app.services.retrieval import retrieve_relevant_chunks

FIELD_KEYWORDS: dict[str, dict[str, list[str]]] = {
    "industrial_valve": {
        "manufacturer": ["manufacturer", "mfr"],
        "model_number": ["model", "catalog"],
        "valve_type": ["valve type", "type:"],
        "nominal_size_in": ["nominal size", "size", "nps"],
        "pressure_class": ["class", "ansi", "pressure class"],
        "body_material": ["body", "material", "wcb"],
        "max_operating_pressure_psi": ["pressure", "psi", "wp"],
        "temperature_range_f": ["temperature", "temp"],
        "end_connection": ["connection", "flanged", "threaded"],
    },
    "bearing": {
        "manufacturer": ["manufacturer"],
        "part_number": ["part", "pn", "bearing no"],
        "bearing_type": ["type", "deep groove", "roller"],
        "bore_mm": ["bore", "id", "inner"],
        "outer_diameter_mm": ["od", "outer"],
        "width_mm": ["width", "b"],
        "dynamic_load_kn": ["dynamic", "load", "kn"],
        "max_rpm": ["rpm", "speed"],
    },
    "sensor": {
        "manufacturer": ["manufacturer"],
        "model_number": ["model"],
        "sensor_type": ["sensor", "type"],
        "measurement_range": ["range", "measuring"],
        "output_signal": ["output", "4-20", "signal"],
        "supply_voltage_v": ["supply", "voltage", "v dc"],
        "accuracy_percent": ["accuracy", "%"],
        "operating_temp_c": ["temperature", "operating"],
        "ip_rating": ["ip", "ingress"],
    },
    "motor": {
        "manufacturer": ["manufacturer"],
        "model_number": ["model"],
        "motor_type": ["motor type", "induction", "type"],
        "power_kw": ["power", "kw", "kW"],
        "voltage_v": ["voltage", "v"],
        "rpm": ["rpm", "speed"],
        "frame_size": ["frame"],
        "efficiency_class": ["efficiency", "ie2", "ie3"],
        "enclosure": ["enclosure", "ip", "tefc"],
    },
    "fastener": {
        "manufacturer": ["manufacturer"],
        "part_number": ["part", "pn"],
        "fastener_type": ["bolt", "screw", "type"],
        "thread_size": ["thread", "m8", "unc"],
        "length_mm": ["length", "mm"],
        "material": ["material", "steel", "stainless"],
        "grade": ["grade"],
        "finish": ["finish", "zinc"],
        "head_style": ["head", "hex"],
    },
}


@dataclass
class ExtractionBundle:
    fields: dict[str, FieldProvenance]
    dual_llm: DualLLMMeta | None = None
    llm_conflicts: list[FieldConflict] | None = None


def _parse_labeled_text(text: str, schema: CategorySchema) -> dict[str, FieldProvenance]:
    """Deterministic parser for demo text with Label: value lines."""
    fields: dict[str, FieldProvenance] = {}
    lines = text.splitlines()
    for fdef in schema.fields:
        fp = FieldProvenance(not_found=True)
        patterns = [
            re.compile(rf"^{re.escape(fdef.name.replace('_', ' '))}\s*:\s*(.+)$", re.I),
            re.compile(rf"^{re.escape(fdef.name)}\s*:\s*(.+)$", re.I),
        ]
        label_map = {
            "nominal_size_in": r"nominal size\s*\(in\)\s*:\s*(.+)",
            "max_operating_pressure_psi": r"max(?:imum)? operating pressure\s*\(psi\)\s*:\s*(.+)",
            "part_number": r"part number\s*:\s*(.+)",
            "model_number": r"model(?: number)?\s*:\s*(.+)",
        }
        if fdef.name in label_map:
            patterns.append(re.compile(label_map[fdef.name], re.I))

        for line in lines:
            line = line.strip()
            for pat in patterns:
                m = pat.match(line)
                if m:
                    val = m.group(1).strip()
                    if val.lower() in ("n/a", "not found", "-", ""):
                        continue
                    if fdef.type == "number":
                        num_m = re.search(r"[\d.]+", val.replace(",", ""))
                        val = float(num_m.group()) if num_m else val
                    fp = FieldProvenance(
                        value=val,
                        source_type=SourceType.DOCUMENT,
                        source_snippet=line[:200],
                        source_location="document text",
                        extraction_method=(
                            ExtractionMethod.TABLE_PARSE
                            if "|" in line or ":" in line
                            else ExtractionMethod.TEXT_LLM
                        ),
                        not_found=False,
                    )
                    break
            if not fp.not_found:
                break
        fields[fdef.name] = fp
    return fields


def _mock_from_sku(sku: str, schema: CategorySchema) -> dict[str, FieldProvenance]:
    seed = {
        "industrial_valve": {
            "manufacturer": "AcmeFlow",
            "model_number": sku,
            "valve_type": "Ball",
            "nominal_size_in": 2.0,
            "pressure_class": "ANSI 150",
            "body_material": "WCB",
        },
        "bearing": {
            "manufacturer": "PrecisionRoll",
            "part_number": sku,
            "bearing_type": "Deep Groove Ball",
            "bore_mm": 25.0,
        },
        "sensor": {
            "manufacturer": "SenseTek",
            "model_number": sku,
            "sensor_type": "Pressure",
            "measurement_range": "0-100 bar",
            "output_signal": "4-20 mA",
        },
        "motor": {
            "manufacturer": "DriveMax",
            "model_number": sku,
            "motor_type": "Induction",
            "power_kw": 5.5,
            "voltage_v": 400,
        },
        "fastener": {
            "manufacturer": "BoltPro",
            "part_number": sku,
            "fastener_type": "Hex Bolt",
            "thread_size": "M10",
            "length_mm": 40.0,
            "material": "Steel",
        },
    }
    base = seed.get(schema.category_id, {})
    out: dict[str, FieldProvenance] = {}
    for fdef in schema.fields:
        if fdef.name in base:
            out[fdef.name] = FieldProvenance(
                value=base[fdef.name],
                source_type=SourceType.DOCUMENT,
                source_snippet=f"Demo default for {fdef.name}",
                source_location="mock",
                extraction_method=ExtractionMethod.MOCK,
                not_found=False,
            )
        else:
            out[fdef.name] = FieldProvenance(not_found=True)
    return out


def extract_with_llm(text: str, schema: CategorySchema, sku: str) -> dict[str, FieldProvenance] | None:
    """Extract via configured LLM provider (Gemini or Claude). Never invents values."""
    bundle = extract_with_llm_bundle(text, schema, sku)
    if bundle is None or not bundle.fields:
        return None
    return bundle.fields


def extract_with_llm_bundle(text: str, schema: CategorySchema, sku: str) -> ExtractionBundle | None:
    """LLM extraction; dual mode runs Gemini and Claude independently."""
    context = retrieve_relevant_chunks(
        text,
        [f.name for f in schema.fields],
        FIELD_KEYWORDS.get(schema.category_id, {}),
    )
    if settings.dual_llm_enabled:
        from backend.app.llm.dual import DualLLMService

        outcome = DualLLMService().extract_fields_from_text(context, schema, sku)
        if outcome.fields is None:
            return ExtractionBundle(fields={}, dual_llm=outcome.meta, llm_conflicts=outcome.llm_conflicts)
        return ExtractionBundle(
            fields=outcome.fields,
            dual_llm=outcome.meta,
            llm_conflicts=outcome.llm_conflicts,
        )
    fields = get_llm_service().extract_fields_from_text(context, schema, sku)
    if fields is None:
        return None
    return ExtractionBundle(fields=fields)


def extract_fields(text: str, schema: CategorySchema, sku: str) -> dict[str, FieldProvenance]:
    return extract_bundle(text, schema, sku).fields


def _merge_labeled_and_dual(
    parsed: dict[str, FieldProvenance],
    llm: ExtractionBundle | None,
) -> ExtractionBundle:
    """Keep labeled-text provenance; attach dual-LLM evidence without overwriting."""
    dual_fields = (llm.fields if llm else None) or {}
    comparisons = {
        row.field_name: row
        for row in ((llm.dual_llm.comparisons if llm and llm.dual_llm else []) or [])
    }
    conflicts = merge_conflicts([], list(llm.llm_conflicts or []) if llm else [])
    merged: dict[str, FieldProvenance] = {}
    for name, labeled in parsed.items():
        if labeled.not_found:
            merged[name] = dual_fields.get(name, labeled)
            continue
        merged[name] = labeled
        row = comparisons.get(name)
        if not row:
            continue
        extra: list[ConflictCandidate] = []
        if row.gemini_value is not None and not values_equivalent(labeled.value, row.gemini_value):
            extra.append(
                ConflictCandidate(
                    value=row.gemini_value,
                    source_type=SourceType.DOCUMENT,
                    source_snippet=row.gemini_source_snippet,
                    source_location=row.gemini_source_location,
                    extraction_method=ExtractionMethod.TEXT_LLM,
                    provider="gemini",
                )
            )
        if row.claude_value is not None and not values_equivalent(labeled.value, row.claude_value):
            extra.append(
                ConflictCandidate(
                    value=row.claude_value,
                    source_type=SourceType.DOCUMENT,
                    source_snippet=row.claude_source_snippet,
                    source_location=row.claude_source_location,
                    extraction_method=ExtractionMethod.TEXT_LLM,
                    provider="anthropic",
                )
            )
        if extra:
            merged[name] = labeled.model_copy(update={"needs_review": True})
            doc_candidate = ConflictCandidate(
                value=labeled.value,
                source_type=labeled.source_type or SourceType.DOCUMENT,
                source_snippet=labeled.source_snippet,
                source_location=labeled.source_location,
                extraction_method=labeled.extraction_method,
            )
            conflicts = merge_conflicts(
                conflicts,
                [FieldConflict(field_name=name, kind="source", candidates=[doc_candidate, *extra])],
            )
    return ExtractionBundle(
        fields=merged,
        dual_llm=llm.dual_llm if llm else None,
        llm_conflicts=conflicts,
    )


def extract_bundle(text: str, schema: CategorySchema, sku: str) -> ExtractionBundle:
    parsed: dict[str, FieldProvenance] = {}
    labeled_hits = 0
    if text.strip():
        parsed = _parse_labeled_text(text, schema)
        labeled_hits = sum(1 for v in parsed.values() if not v.not_found)

    if not settings.dual_llm_enabled:
        if labeled_hits >= 2:
            return ExtractionBundle(fields=parsed)
        llm = extract_with_llm_bundle(text, schema, sku)
        if llm and llm.fields:
            return llm
        if labeled_hits:
            return ExtractionBundle(fields=parsed, dual_llm=llm.dual_llm if llm else None)
        return ExtractionBundle(
            fields=_mock_from_sku(sku, schema),
            dual_llm=llm.dual_llm if llm else None,
            llm_conflicts=llm.llm_conflicts if llm else None,
        )

    llm = extract_with_llm_bundle(text, schema, sku)
    if parsed:
        return _merge_labeled_and_dual(parsed, llm)
    if llm and llm.fields:
        return llm
    return ExtractionBundle(
        fields=_mock_from_sku(sku, schema),
        dual_llm=llm.dual_llm if llm else None,
        llm_conflicts=llm.llm_conflicts if llm else None,
    )


def load_seed_text(root: Path, relative: str) -> str:
    p = root / relative
    return p.read_text(encoding="utf-8") if p.exists() else ""
