"""Conservative description fields — never invent attributes not in the source."""

from __future__ import annotations

from backend.app.unihack.normalize import clean_input, fold


def _clip(text: str, limit: int) -> str:
    text = fold(text)
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def build_descriptions(
    *,
    part_desc: str,
    manufacturer: str,
    brand: str,
    mfg_part_num: str,
) -> dict[str, str]:
    desc = clean_input(part_desc)
    brand_s = clean_input(brand)
    mfr_s = clean_input(manufacturer)
    sku = clean_input(mfg_part_num)
    lead = " ".join(p for p in (brand_s or mfr_s, desc) if p).strip() or desc
    invoice = _clip(lead or sku, 40)
    mobile = _clip(lead or sku, 60)
    title = _clip(" ".join(p for p in (brand_s, desc, sku) if p), 128)
    long = fold(" | ".join(p for p in (mfr_s, brand_s, sku, desc) if p))
    return {
        "invoice": invoice,
        "mobile": mobile,
        "title": title,
        "long": long,
        "source_desc": desc,
    }
