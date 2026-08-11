from typing import Any

from pydantic import BaseModel, Field

from backend.app.schemas.fields import FieldProvenance


class FieldDef(BaseModel):
    name: str
    type: str  # string, number, boolean
    unit: str | None = None
    required: bool = False
    min_value: float | None = None
    max_value: float | None = None
    pattern: str | None = None
    description: str = ""


class CategorySchema(BaseModel):
    category_id: str
    display_name: str
    fields: list[FieldDef]


INDUSTRIAL_VALVE = CategorySchema(
    category_id="industrial_valve",
    display_name="Industrial Valve",
    fields=[
        FieldDef(name="manufacturer", type="string", required=True),
        FieldDef(name="model_number", type="string", required=True),
        FieldDef(name="valve_type", type="string", required=True),
        FieldDef(name="nominal_size_in", type="number", unit="in", required=True, min_value=0.25, max_value=48),
        FieldDef(name="pressure_class", type="string", required=True),
        FieldDef(name="body_material", type="string", required=True),
        FieldDef(name="max_operating_pressure_psi", type="number", unit="psi", required=False, min_value=0, max_value=10000),
        FieldDef(name="temperature_range_f", type="string", required=False),
        FieldDef(name="end_connection", type="string", required=False),
    ],
)

BEARING = CategorySchema(
    category_id="bearing",
    display_name="Bearing",
    fields=[
        FieldDef(name="manufacturer", type="string", required=True),
        FieldDef(name="part_number", type="string", required=True),
        FieldDef(name="bearing_type", type="string", required=True),
        FieldDef(name="bore_mm", type="number", unit="mm", required=True, min_value=1, max_value=500),
        FieldDef(name="outer_diameter_mm", type="number", unit="mm", required=False, min_value=1, max_value=600),
        FieldDef(name="width_mm", type="number", unit="mm", required=False, min_value=1, max_value=200),
        FieldDef(name="dynamic_load_kn", type="number", unit="kN", required=False, min_value=0, max_value=5000),
        FieldDef(name="max_rpm", type="number", unit="rpm", required=False, min_value=0, max_value=500000),
    ],
)

SENSOR = CategorySchema(
    category_id="sensor",
    display_name="Sensor",
    fields=[
        FieldDef(name="manufacturer", type="string", required=True),
        FieldDef(name="model_number", type="string", required=True),
        FieldDef(name="sensor_type", type="string", required=True),
        FieldDef(name="measurement_range", type="string", required=True),
        FieldDef(name="output_signal", type="string", required=True),
        FieldDef(name="supply_voltage_v", type="number", unit="V", required=False, min_value=0, max_value=48),
        FieldDef(name="accuracy_percent", type="number", unit="%", required=False, min_value=0, max_value=10),
        FieldDef(name="operating_temp_c", type="string", required=False),
        FieldDef(name="ip_rating", type="string", required=False),
    ],
)

MOTOR = CategorySchema(
    category_id="motor",
    display_name="Motor",
    fields=[
        FieldDef(name="manufacturer", type="string", required=True),
        FieldDef(name="model_number", type="string", required=True),
        FieldDef(name="motor_type", type="string", required=True),
        FieldDef(name="power_kw", type="number", unit="kW", required=True, min_value=0.01, max_value=5000),
        FieldDef(name="voltage_v", type="number", unit="V", required=True, min_value=12, max_value=15000),
        FieldDef(name="rpm", type="number", unit="rpm", required=False, min_value=0, max_value=50000),
        FieldDef(name="frame_size", type="string", required=False),
        FieldDef(name="efficiency_class", type="string", required=False),
        FieldDef(name="enclosure", type="string", required=False),
    ],
)

FASTENER = CategorySchema(
    category_id="fastener",
    display_name="Fastener",
    fields=[
        FieldDef(name="manufacturer", type="string", required=True),
        FieldDef(name="part_number", type="string", required=True),
        FieldDef(name="fastener_type", type="string", required=True),
        FieldDef(name="thread_size", type="string", required=True),
        FieldDef(name="length_mm", type="number", unit="mm", required=True, min_value=1, max_value=2000),
        FieldDef(name="material", type="string", required=True),
        FieldDef(name="grade", type="string", required=False),
        FieldDef(name="finish", type="string", required=False),
        FieldDef(name="head_style", type="string", required=False),
    ],
)

CATEGORIES: dict[str, CategorySchema] = {
    "industrial_valve": INDUSTRIAL_VALVE,
    "bearing": BEARING,
    "sensor": SENSOR,
    "motor": MOTOR,
    "fastener": FASTENER,
}


def empty_record(category_id: str) -> dict[str, FieldProvenance]:
    schema = CATEGORIES[category_id]
    return {f.name: FieldProvenance(not_found=True) for f in schema.fields}


def record_to_export_dict(fields: dict[str, FieldProvenance]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for name, fp in fields.items():
        out[name] = fp.value
    return out
