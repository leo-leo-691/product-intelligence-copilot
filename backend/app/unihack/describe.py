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
    verified_facts: list[str] | None = None,
) -> dict[str, str]:
    desc = clean_input(part_desc)
    brand_s = clean_input(brand)
    mfr_s = clean_input(manufacturer)
    sku = clean_input(mfg_part_num)
    facts = [clean_input(f) for f in (verified_facts or []) if clean_input(f)]
    fact_phrase = ", ".join(facts[:5]) if facts else ""
    lead = " ".join(p for p in (brand_s or mfr_s, desc) if p).strip() or desc
    if facts and desc:
        lead = f"{lead} with {fact_phrase}" if fact_phrase else lead
    elif facts and not desc:
        lead = " ".join(facts[:4])
    invoice = _clip(lead or sku, 40)
    mobile = _clip(lead or sku, 60)
    title = _clip(" ".join(p for p in (brand_s, desc, sku) if p), 128)
    long_parts = [p for p in (mfr_s, brand_s, sku, desc, fact_phrase) if p]
    long = fold(" | ".join(long_parts))
    return {
        "invoice": invoice,
        "mobile": mobile,
        "title": title,
        "long": long,
        "source_desc": desc,
    }
