"""Manufacturer / brand resolution against UniCat master list when present."""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path

from backend.app.unihack.excel import find_column, read_tables
from backend.app.unihack.normalize import clean_input, norm_key

AUTO_THRESHOLD = 0.92
REVIEW_THRESHOLD = 0.80


@dataclass
class CatalogMatch:
    query: str
    matched_name: str = ""
    matched_code: str = ""
    kind: str = ""  # manufacturer | brand
    score: float = 0.0
    method: str = "none"  # exact | normalized | fuzzy | none
    needs_review: bool = False


def _col(headers: list[str], *names: str) -> str | None:
    for n in names:
        hit = find_column(headers, n)
        if hit:
            return hit
    lowered = [(h, h.lower()) for h in headers]
    for n in names:
        nlow = n.lower()
        for h, hl in lowered:
            if nlow in hl:
                return h
    return None


@lru_cache(maxsize=4)
def load_catalog(path: str) -> tuple[list[dict], list[dict]]:
    manufacturers: list[dict] = []
    brands: list[dict] = []
    for table in read_tables(Path(path)):
        mfr_name = _col(table.headers, "MANUFACTURER_NAME", "manufacturer name", "manufacturer")
        mfr_code = _col(table.headers, "MANUFACTURER_CODE", "manufacturer code", "mfr code")
        brand_name = _col(table.headers, "BRAND_NAME", "brand name", "brand")
        brand_code = _col(table.headers, "BRAND_CODE", "brand code")
        for row in table.rows:
            if mfr_name and row.get(mfr_name):
                manufacturers.append(
                    {
                        "name": clean_input(row.get(mfr_name, "")),
                        "code": clean_input(row.get(mfr_code or "", "")),
                        "key": norm_key(row.get(mfr_name, "")),
                    }
                )
            if brand_name and row.get(brand_name):
                brands.append(
                    {
                        "name": clean_input(row.get(brand_name, "")),
                        "code": clean_input(row.get(brand_code or "", "")),
                        "key": norm_key(row.get(brand_name, "")),
                    }
                )
    # de-dupe
    def uniq(items: list[dict]) -> list[dict]:
        seen: set[str] = set()
        out: list[dict] = []
        for it in items:
            if not it["key"] or it["key"] in seen:
                continue
            seen.add(it["key"])
            out.append(it)
        return out

    return uniq(manufacturers), uniq(brands)


def _match(query: str, items: list[dict], kind: str) -> CatalogMatch:
    q = clean_input(query)
    result = CatalogMatch(query=q, kind=kind)
    if not q:
        return result
    qk = norm_key(q)
    for it in items:
        if it["name"] == q:
            return CatalogMatch(q, it["name"], it["code"], kind, 1.0, "exact", False)
    for it in items:
        if it["key"] == qk:
            return CatalogMatch(q, it["name"], it["code"], kind, 0.99, "normalized", False)
    best: dict | None = None
    best_s = 0.0
    for it in items:
        s = SequenceMatcher(None, qk, it["key"]).ratio()
        if s > best_s:
            best_s, best = s, it
    if best and best_s >= AUTO_THRESHOLD:
        return CatalogMatch(q, best["name"], best["code"], kind, best_s, "fuzzy", False)
    if best and best_s >= REVIEW_THRESHOLD:
        return CatalogMatch(q, best["name"], best["code"], kind, best_s, "fuzzy", True)
    return result


def resolve_manufacturer(query: str, catalog_path: Path | None) -> CatalogMatch:
    if not catalog_path or not catalog_path.exists():
        q = clean_input(query)
        return CatalogMatch(query=q, matched_name="", method="unresolved", needs_review=bool(q))
    mfrs, _ = load_catalog(str(catalog_path))
    return _match(query, mfrs, "manufacturer")


def resolve_brand(query: str, catalog_path: Path | None) -> CatalogMatch:
    if not catalog_path or not catalog_path.exists():
        q = clean_input(query)
        return CatalogMatch(query=q, matched_name="", method="unresolved", needs_review=bool(q))
    _, brands = load_catalog(str(catalog_path))
    return _match(query, brands, "brand")
