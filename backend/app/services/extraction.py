import re
from pathlib import Path

from backend.app.llm import get_llm_service
from backend.app.schemas.categories import CategorySchema
from backend.app.schemas.fields import (
    ExtractionMethod,
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
    context = retrieve_relevant_chunks(
        text,
        [f.name for f in schema.fields],
        FIELD_KEYWORDS.get(schema.category_id, {}),
    )
    return get_llm_service().extract_fields_from_text(context, schema, sku)


def extract_fields(text: str, schema: CategorySchema, sku: str) -> dict[str, FieldProvenance]:
    if text.strip():
        parsed = _parse_labeled_text(text, schema)
        if sum(1 for v in parsed.values() if not v.not_found) >= 2:
            return parsed
    llm = extract_with_llm(text, schema, sku)
    if llm:
        return llm
    if text.strip():
        parsed = _parse_labeled_text(text, schema)
        if any(not v.not_found for v in parsed.values()):
            return parsed
    return _mock_from_sku(sku, schema)


def load_seed_text(root: Path, relative: str) -> str:
    p = root / relative
    return p.read_text(encoding="utf-8") if p.exists() else ""
