"""Normalize product identifiers for matching and source discovery."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from backend.app.unihack.excel import find_column
from backend.app.unihack.normalize import clean_input, fold, norm_key

# Preserve model-number characters; only collapse redundant whitespace.
_MPN_SAFE = re.compile(r"[^\w\-\./+#]", re.UNICODE)


@dataclass
class ProductIdentity:
    """Normalized identifiers for one catalog row."""

    mfg_part_num: str
    part_desc: str
    manufacturer_query: str
    brand_query: str
    mpn_normalized: str
    search_queries: list[str] = field(default_factory=list)
    tokens: list[str] = field(default_factory=list)


def normalize_mpn(mpn: str) -> str:
    """Normalize part number without destroying meaningful characters."""
    text = fold(mpn).upper()
    text = _MPN_SAFE.sub("", text)
    return text.strip("-. ")


def normalize_manufacturer_name(name: str) -> str:
    text = clean_input(name)
    if not text:
        return ""
    # Title-case words but preserve acronyms (2+ uppercase letters).
    parts: list[str] = []
    for word in text.split():
        if word.isupper() and len(word) > 1:
            parts.append(word)
        else:
            parts.append(word.capitalize())
    return " ".join(parts)


def _first(*values: str) -> str:
    for v in values:
        c = clean_input(v)
        if c:
            return c
    return ""


def identify_product(raw: dict[str, str]) -> ProductIdentity:
    """Build search/match identity from arbitrary input columns."""
    raw_keys = [k for k in raw if k != "row_number"]

    def col(*needles: str) -> str:
        for n in needles:
            if n in raw:
                return clean_input(str(raw.get(n, "")))
            hit = find_column(raw_keys, n)
            if hit:
                return clean_input(str(raw.get(hit, "")))
        return ""

    mpn = col("Mfg_Part_Num", "mpn", "manufacturer part number")
    desc = col("Part_Desc", "description", "product description")
    mfr = col("Part_Manuf", "manufacturer", "mfr")
    brand = _first(
        col("Unilog_Brand", "unilog brand"),
        col("E1_Brand", "e1 brand"),
        col("DIB_Brand", "dib brand"),
    )

    mpn_norm = normalize_mpn(mpn)
    mfr_norm = normalize_manufacturer_name(mfr)
    brand_norm = normalize_manufacturer_name(brand)

    queries: list[str] = []
    # Primary: manufacturer + MPN
    if mpn and mfr_norm:
        queries.append(f"{mfr_norm} {mpn}")
        queries.append(f"{mfr_norm} {mpn} specifications")
    # Brand + MPN (if brand differs from manufacturer)
    if mpn and brand_norm and brand_norm.lower() != mfr_norm.lower():
        queries.append(f"{brand_norm} {mpn}")
    # MPN + description (context-rich)
    if mpn and desc:
        queries.append(f"{mpn} {desc}")
    # MPN alone
    if mpn:
        queries.append(mpn)
    # Description only (fallback when no MPN)
    if desc and not mpn:
        queries.append(desc)

    # Site-specific query when manufacturer domain is known
    _domain_hints: dict[str, str] = {
        "frigidaire": "frigidaire.com",
        "whirlpool": "whirlpool.com",
        "kitchenaid": "kitchenaid.com",
        "ge": "geappliances.com",
        "bosch": "bosch-home.com",
        "samsung": "samsung.com",
        "lg": "lg.com",
        "maytag": "maytag.com",
        "electrolux": "electrolux.com",
        "moen": "moen.com",
        "kohler": "kohler.com",
        "delta": "deltafaucet.com",
        "rheem": "rheem.com",
        "honeywell": "honeywell.com",
        "watts": "watts.com",
        "rinnai": "rinnai.us",
        "navien": "navien.com",
    }
    if mpn and mfr_norm:
        mfr_key = norm_key(mfr_norm)
        for hint, domain in _domain_hints.items():
            if hint in mfr_key:
                queries.append(f"site:{domain} {mpn}")
                break

    # De-dupe while preserving order.
    seen: set[str] = set()
    unique_queries: list[str] = []
    for q in queries:
        key = q.lower()
        if key not in seen:
            seen.add(key)
            unique_queries.append(q)

    tokens = [t for t in (mpn_norm, norm_key(mfr_norm), norm_key(brand_norm)) if t]

    return ProductIdentity(
        mfg_part_num=mpn,
        part_desc=desc,
        manufacturer_query=mfr_norm or mfr,
        brand_query=brand_norm or brand,
        mpn_normalized=mpn_norm,
        search_queries=unique_queries,
        tokens=tokens,
    )
