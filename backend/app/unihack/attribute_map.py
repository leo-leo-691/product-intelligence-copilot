"""Map normalized extracted attributes onto dynamic delivery headers."""

from __future__ import annotations

from typing import Any

from backend.app.unihack.extract_attrs import ExtractedAttribute, ExtractionResult
from backend.app.unihack.identify import ProductIdentity
from backend.app.unihack.schema import guess_header


# Direct normalized-key → delivery header needle(s).
_DIRECT_MAP: dict[str, tuple[str, ...]] = {
    # Identity
    "manufacturer": ("MANUFACTURER_NAME", "Part_Manuf", "manufacturer"),
    "brand": ("BRAND_NAME", "Unilog_Brand", "E1_Brand", "DIB_Brand", "brand"),
    "model": ("MANUFACTURER_PART_NUMBER", "model", "series"),
    "series": ("TRADE_NAME", "series"),
    "trade_name": ("TRADE_NAME",),
    "part_number": ("MANUFACTURER_PART_NUMBER", "PART_NUMBER", "Mfg_Part_Num"),
    "alternate_part_number": ("ALTERNATE_PART_NUMBER",),
    "sku": ("SKU - MY_PART_NUMBER", "SKU", "PART_NUMBER"),
    "product_name": ("Product Name", "SHORT_DESC"),
    "product_type": ("Classpath", "Class"),
    "description": ("Part_Desc", "LONG_DESC1"),
    # Codes
    "upc": ("UPC",),
    "ean": ("EAN",),
    "gtin": ("GTIN",),
    "unspsc": ("UNSPSC",),
    # Descriptions
    "retail_desc": ("RETAIL_DESC",),
    "marketing_desc": ("MARKETING_DESCRIPTION",),
    # Appearance
    "color": ("With", "finish", "color"),
    "finish": ("With", "finish"),
    "material": ("material", "With"),
    # Certifications / compliance
    "certification": ("Standard/Approvals",),
    "prop_65": ("Prop 65",),
    "energy_star": ("Energy Star Guide",),
    "rohs": ("RoHS",),
    "ada_compliant": ("Standard/Approvals",),
    # Application
    "application": ("Application",),
    "includes": ("Includes",),
    # Provenance
    "country_of_origin": ("Country Of Origin",),
    "discontinued": ("Discontinued",),
    # Warranty / pricing
    "warranty": ("Warranty", "Warranty Information"),
    "list_price": ("List Price",),
    # Packaging
    "selling_qty": ("Selling Qty",),
    "selling_uom": ("Selling UOM",),
    "standard_packaging": ("Standard Packaging Information",),
    # URLs
    "mfr_url": ("MFR URL",),
    "product_url": ("MFR URL",),
    # Documents
    "spec_sheet": ("Specification Sheet",),
    # Images
    "product_image": ("Product Image",),
    "actual_image": ("Actual Image (Yes/No)",),
    # Video
    "video_link": ("Video Link",),
}

# Document type → delivery header needle(s).
_DOCUMENT_MAP: dict[str, tuple[str, ...]] = {
    "spec_sheet": ("Specification Sheet",),
    "sds": ("SDS",),
    "warranty_doc": ("Warranty Information",),
    "installation_manual": ("Instruction/Installation Manual",),
    "owners_manual": ("Owners/User Manual",),
    "service_manual": ("Service Manual",),
    "catalog": ("Catalog",),
    "submittal": ("Submittal",),
    "technical_bulletin": ("Technical Bulletin",),
    "line_drawing": ("Line Drawing",),
    "engineering_drawing": ("Full Engineering Drawing",),
    "energy_guide": ("Energy Star Guide",),
    "compatibility_chart": ("Compatibility Chart",),
    "size_chart": ("Size Chart",),
    "product_label": ("Product Label/Insert",),
}


def _attribute_triplet_slots(headers: list[str]) -> list[tuple[str, str, str]]:
    slots: list[tuple[str, str, str]] = []
    for i in range(1, 51):
        lh = guess_header(headers, f"ATTRIBUTE_LABEL {i}")
        vh = guess_header(headers, f"ATTRIBUTE_VALUE {i}")
        uh = guess_header(headers, f"ATTRIBUTE_UOM {i}")
        if lh and vh and uh:
            slots.append((lh, vh, uh))
    return slots


def _ref_url_slots(headers: list[str]) -> list[str]:
    return [h for h in headers if h.startswith("Ref URL")]


def _feature_slots(headers: list[str]) -> list[str]:
    return [h for h in headers if h.startswith("ITEM_FEATURES_")]


def _image_slots(headers: list[str]) -> list[str]:
    out: list[str] = []
    # Primary product image first
    hit = guess_header(headers, "Product Image")
    if hit and hit not in out:
        out.append(hit)
    # Alternate images
    for i in range(1, 10):
        hit = guess_header(headers, f"Alternate Image {i}")
        if hit and hit not in out:
            out.append(hit)
    # Catch any remaining image headers
    for h in headers:
        if h.startswith("Alternate Image") and h not in out:
            out.append(h)
    return out


def _dim_map() -> dict[str, tuple[str, str]]:
    return {
        "width": ("WIDTH", "WIDTH_UOM"),
        "height": ("HEIGHT", "HEIGHT_UOM"),
        "depth": ("LENGTH", "LENGTH_UOM"),
        "weight": ("WEIGHT", "WEIGHT_UOM"),
        "volume": ("VOLUME", "VOLUME_UOM"),
    }


def map_to_delivery(
    extraction: ExtractionResult,
    headers: list[str],
    identity: ProductIdentity,
    *,
    input_values: dict[str, str] | None = None,
) -> tuple[dict[str, str], dict[str, dict[str, Any]]]:
    """Return delivery fragment + provenance for enriched fields only."""
    delivery: dict[str, str] = {}
    provenance: dict[str, dict[str, Any]] = {}
    input_values = input_values or {}

    def set_field(header: str | None, value: str, attr: ExtractedAttribute | None = None) -> None:
        if not header or not value:
            return
        if header in delivery and delivery[header]:
            return
        if header in input_values and input_values[header]:
            return
        delivery[header] = value
        provenance[header] = {
            "value": value,
            "source": attr.source_url if attr else "enrichment",
            "confidence": attr.confidence if attr else "Medium",
            "review_status": "pending",
            "needs_review": False,
            "issues": [],
            "evidence": attr.evidence if attr else "",
        }

    # Group attributes by key
    by_key: dict[str, list[ExtractedAttribute]] = {}
    features: list[ExtractedAttribute] = []
    specs: list[ExtractedAttribute] = []

    spec_keys = {
        "sound_level",
        "voltage",
        "amperage",
        "wattage",
        "frequency",
        "wash_cycles",
        "drying_cycles",
        "capacity",
        "width",
        "height",
        "depth",
        "weight",
        "volume",
        "horsepower",
        "rpm",
        "gpm",
        "btu",
        "cfm",
        "psi",
        "flow_rate",
        "pressure_rating",
        "temperature",
        "thread_size",
        "pipe_size",
        "connection_size",
        "connection_type",
        "mounting_type",
    }

    for attr in extraction.attributes:
        if attr.key == "feature":
            features.append(attr)
        elif attr.key in spec_keys:
            specs.append(attr)
        elif attr.key in ("meta_description", "product_url"):
            # Supporting evidence — don't map directly
            by_key.setdefault(attr.key, []).append(attr)
        else:
            by_key.setdefault(attr.key, []).append(attr)

    # Direct mappings
    for key, attrs_list in by_key.items():
        needles = _DIRECT_MAP.get(key)
        if not needles:
            continue
        header = guess_header(headers, *needles)
        if header:
            set_field(header, attrs_list[0].value, attrs_list[0])

    # Dimensions with UOM
    for dim_key, (val_needle, uom_needle) in _dim_map().items():
        dim_attrs = [a for a in specs if a.key == dim_key]
        if not dim_attrs:
            continue
        val_h = guess_header(headers, val_needle)
        uom_h = guess_header(headers, uom_needle)
        if val_h:
            set_field(val_h, dim_attrs[0].value, dim_attrs[0])
        if uom_h and dim_attrs[0].uom:
            set_field(uom_h, dim_attrs[0].uom, dim_attrs[0])

    # Remaining specs → ATTRIBUTE_LABEL/VALUE/UOM triplets
    triplet_slots = _attribute_triplet_slots(headers)
    spec_attrs = [a for a in specs if a.key not in _dim_map()]
    label_titles: dict[str, str] = {
        "sound_level": "Sound Level",
        "voltage": "Voltage",
        "amperage": "Amperage",
        "wattage": "Wattage",
        "frequency": "Frequency",
        "wash_cycles": "Wash Cycles",
        "drying_cycles": "Drying Cycles",
        "capacity": "Capacity",
        "horsepower": "Horsepower",
        "rpm": "RPM",
        "gpm": "GPM",
        "btu": "BTU",
        "cfm": "CFM",
        "psi": "PSI",
        "flow_rate": "Flow Rate",
        "pressure_rating": "Pressure Rating",
        "temperature": "Temperature",
        "thread_size": "Thread Size",
        "pipe_size": "Pipe Size",
        "connection_size": "Connection Size",
        "connection_type": "Connection Type",
        "mounting_type": "Mounting Type",
    }
    for slot, attr in zip(triplet_slots, spec_attrs):
        lh, vh, uh = slot
        label = label_titles.get(attr.key, attr.key.replace("_", " ").title())
        set_field(lh, label, attr)
        set_field(vh, attr.value, attr)
        if attr.uom:
            set_field(uh, attr.uom, attr)

    # Features
    for slot, feat in zip(_feature_slots(headers), features):
        set_field(slot, feat.value, feat)

    # URLs
    if extraction.mfr_url:
        set_field(guess_header(headers, "MFR URL"), extraction.mfr_url)
    for slot, url in zip(_ref_url_slots(headers), extraction.ref_urls):
        set_field(slot, url)

    if extraction.spec_sheet_url:
        set_field(guess_header(headers, "Specification Sheet"), extraction.spec_sheet_url)

    # Documents
    for doc_type, doc_url in extraction.documents.items():
        needles = _DOCUMENT_MAP.get(doc_type)
        if needles:
            header = guess_header(headers, *needles)
            set_field(header, doc_url)

    # Images
    image_slots = _image_slots(headers)
    for slot, url in zip(image_slots, extraction.images):
        set_field(slot, url)

    if extraction.images:
        set_field(guess_header(headers, "Actual Image (Yes/No)"), "Yes")

    # SDS document headers (SDS and SDS_1 are separate in schema)
    if "sds" in extraction.documents:
        sds_h = guess_header(headers, "SDS")
        set_field(sds_h, extraction.documents["sds"])

    # Video links from extraction
    video_attrs = by_key.get("video_link", [])
    if video_attrs:
        set_field(guess_header(headers, "Video Link"), video_attrs[0].value, video_attrs[0])
        if len(video_attrs) > 1:
            set_field(guess_header(headers, "Video Link 1"), video_attrs[1].value, video_attrs[1])

    # Preserve identity fields when not already set
    if identity.mfg_part_num:
        set_field(guess_header(headers, "Mfg_Part_Num", "MANUFACTURER_PART_NUMBER"), identity.mfg_part_num)
    if identity.part_desc:
        set_field(guess_header(headers, "Part_Desc", "description"), identity.part_desc)

    return delivery, provenance


def verified_facts(extraction: ExtractionResult) -> list[str]:
    """Short fact strings for description generation from verified extraction only."""
    facts: list[str] = []
    for attr in extraction.attributes:
        if attr.key == "feature":
            facts.append(attr.value)
        elif attr.key in {"width", "height", "depth"} and attr.uom:
            facts.append(f"{attr.key} {attr.value} {attr.uom}")
        elif attr.key == "sound_level":
            facts.append(f"{attr.value} operation")
        elif attr.key in {"voltage", "amperage", "wattage", "warranty", "capacity",
                          "wash_cycles", "horsepower", "flow_rate", "btu", "cfm", "rpm"}:
            facts.append(attr.value)
        elif attr.key in {"color", "finish", "material"}:
            facts.append(attr.value)
        elif attr.key == "certification":
            facts.append(attr.value)
        elif attr.key == "application":
            facts.append(attr.value)
    return facts[:15]
