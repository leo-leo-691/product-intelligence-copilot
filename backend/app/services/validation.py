import re
from typing import Any

from backend.app.schemas.categories import CategorySchema, FieldDef
from backend.app.schemas.fields import FieldProvenance


def _format_match(value: Any, field_def: FieldDef) -> tuple[float, list[str]]:
    errors: list[str] = []
    if value is None or value == "":
        if field_def.required:
            errors.append("required field missing")
        return 0.0, errors

    if field_def.type == "number":
        try:
            num = float(value)
        except (TypeError, ValueError):
            errors.append("expected numeric value")
            return 0.2, errors
        if field_def.min_value is not None and num < field_def.min_value:
            errors.append(f"below minimum {field_def.min_value}")
        if field_def.max_value is not None and num > field_def.max_value:
            errors.append(f"above maximum {field_def.max_value}")
        if errors:
            return 0.3, errors
        return 1.0, errors

    if field_def.type == "string":
        s = str(value)
        if field_def.pattern and not re.match(field_def.pattern, s):
            errors.append("pattern mismatch")
            return 0.4, errors
        return 1.0, errors

    return 1.0, errors


def validate_field(
    field_def: FieldDef, fp: FieldProvenance
) -> tuple[FieldProvenance, float, bool]:
    # Preserve explicit not_found when value is empty; do not invent presence
    if fp.value is None or fp.value == "":
        fp.not_found = True
        errors = ["required field missing"] if field_def.required else []
        fp.validation_errors = errors
        return fp, 0.0, bool(errors)

    fmt, errors = _format_match(fp.value, field_def)
    fp.validation_errors = errors
    fp.not_found = False
    return fp, fmt, bool(errors)


def validate_record(schema: CategorySchema, fields: dict[str, FieldProvenance]) -> dict[str, FieldProvenance]:
    out = {}
    for fdef in schema.fields:
        fp = fields.get(fdef.name, FieldProvenance(not_found=True))
        fp, _, _ = validate_field(fdef, fp)
        out[fdef.name] = fp
    return out
