"""Evidence-based structured extraction from retrieved product pages."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from html import unescape
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag

from backend.app.unihack.identify import ProductIdentity, normalize_mpn
from backend.app.unihack.normalize import fold, norm_key
from backend.app.unihack.retrieve import RetrievedPage, is_pdf_url

logger = logging.getLogger(__name__)


@dataclass
class ExtractedAttribute:
    key: str
    value: str
    source_url: str
    evidence: str
    confidence: str = "High"
    uom: str = ""


@dataclass
class ExtractionResult:
    attributes: list[ExtractedAttribute] = field(default_factory=list)
    images: list[str] = field(default_factory=list)
    spec_sheet_url: str = ""
    mfr_url: str = ""
    ref_urls: list[str] = field(default_factory=list)
    documents: dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Regex patterns — only applied to source text; never invent values.
# ---------------------------------------------------------------------------
_PATTERNS: dict[str, re.Pattern[str]] = {
    "sound_level": re.compile(r"\b(\d+(?:\.\d+)?)\s*dBA\b", re.I),
    "voltage": re.compile(r"\b(\d+(?:\.\d+)?)\s*V(?:olts?)?\b(?!\s*[Aa])", re.I),
    "amperage": re.compile(r"\b(\d+(?:\.\d+)?)\s*(?:A(?:mps?)?|amps?)\b", re.I),
    "warranty": re.compile(r"\b(\d+)\s*[- ]?\s*year[s]?\s+(?:limited\s+)?warranty\b", re.I),
    "width": re.compile(r"\b(?:width|w)\s*[:.\-]?\s*(\d+(?:[./]\d+)?)\s*(?:in|inch|inches|\")\b", re.I),
    "height": re.compile(r"\b(?:height|h)\s*[:.\-]?\s*(\d+(?:[./]\d+)?)\s*(?:in|inch|inches|\")\b", re.I),
    "depth": re.compile(r"\b(?:depth|d)\s*[:.\-]?\s*(\d+(?:[./]\d+)?)\s*(?:in|inch|inches|\")\b", re.I),
    "weight": re.compile(r"\b(?:weight|wt|net\s+weight)\s*[:.\-]?\s*(\d+(?:\.\d+)?)\s*(?:lb|lbs|pounds?)\b", re.I),
    "wash_cycles": re.compile(r"\b(\d+)\s+wash\s+cycles?\b", re.I),
    "capacity": re.compile(r"\b(\d+(?:\.\d+)?)\s*(?:cu\.?\s*ft|place\s+settings)\b", re.I),
    "horsepower": re.compile(r"\b(\d+(?:[./]\d+)?)\s*(?:HP|horsepower)\b", re.I),
    "rpm": re.compile(r"\b(\d+)\s*RPM\b", re.I),
    "gpm": re.compile(r"\b(\d+(?:\.\d+)?)\s*GPM\b", re.I),
    "btu": re.compile(r"\b(\d[\d,]*)\s*BTU\b", re.I),
    "cfm": re.compile(r"\b(\d+(?:\.\d+)?)\s*CFM\b", re.I),
    "psi": re.compile(r"\b(\d+(?:\.\d+)?)\s*PSI\b", re.I),
    "frequency": re.compile(r"\b(\d+)\s*Hz\b", re.I),
    "flow_rate": re.compile(r"\b(?:flow\s*rate)\s*[:.\-]?\s*(\d+(?:\.\d+)?)\s*(?:GPM|LPM|gal/min)\b", re.I),
    "temperature": re.compile(r"\b(?:temp(?:erature)?)\s*[:.\-]?\s*(\d+(?:\.\d+)?)\s*°?\s*[FC]\b", re.I),
    "thread_size": re.compile(r"\b(\d+/\d+)\s*(?:inch|in|\")\s*(?:NPT|FPT|MIP|FIP|IPS)\b", re.I),
    "pipe_size": re.compile(r"\b(?:pipe\s*size)\s*[:.\-]?\s*(\d+(?:/\d+)?)\s*(?:in|inch|\")\b", re.I),
    "pressure_rating": re.compile(r"\b(?:pressure)\s*[:.\-]?\s*(\d+)\s*(?:PSI|psi|kPa)\b", re.I),
}

# ---------------------------------------------------------------------------
# Label normalization map — maps page labels to normalized attribute keys.
# ---------------------------------------------------------------------------
_LABEL_MAP: dict[str, str] = {
    # Identity
    "manufacturer": "manufacturer",
    "mfg": "manufacturer",
    "mfr": "manufacturer",
    "brand": "brand",
    "brand name": "brand",
    "model": "model",
    "model number": "model",
    "model no": "model",
    "model name": "model",
    "series": "series",
    "trade name": "trade_name",
    "collection": "series",
    "part number": "part_number",
    "part no": "part_number",
    "part #": "part_number",
    "manufacturer part number": "part_number",
    "manufacturer part #": "part_number",
    "mpn": "part_number",
    "mfg part number": "part_number",
    "alternate part number": "alternate_part_number",
    "alternate part #": "alternate_part_number",
    "replacement part": "alternate_part_number",
    "sku": "sku",
    "item number": "sku",
    "item #": "sku",
    "item no": "sku",
    "product id": "sku",
    # Codes
    "upc": "upc",
    "upc code": "upc",
    "universal product code": "upc",
    "ean": "ean",
    "gtin": "gtin",
    "gtin-13": "gtin",
    "gtin-14": "gtin",
    "unspsc": "unspsc",
    "unspsc code": "unspsc",
    # Descriptions
    "product name": "product_name",
    "product title": "product_name",
    "name": "product_name",
    "description": "description",
    "product description": "description",
    # Appearance
    "color": "color",
    "color/finish": "color",
    "colour": "color",
    "finish": "finish",
    "finish type": "finish",
    "material": "material",
    "primary material": "material",
    "body material": "material",
    "handle material": "material",
    "construction material": "material",
    # Electrical
    "voltage": "voltage",
    "voltage rating": "voltage",
    "operating voltage": "voltage",
    "rated voltage": "voltage",
    "amperage": "amperage",
    "amps": "amperage",
    "amp": "amperage",
    "rated amperage": "amperage",
    "current": "amperage",
    "wattage": "wattage",
    "watts": "wattage",
    "power": "wattage",
    "frequency": "frequency",
    "hertz": "frequency",
    "horsepower": "horsepower",
    "hp": "horsepower",
    # Sound
    "sound level": "sound_level",
    "noise level": "sound_level",
    "sound rating": "sound_level",
    "decibel": "sound_level",
    "dba": "sound_level",
    "sound level (dba)": "sound_level",
    "operating noise": "sound_level",
    "sound rating (dba)": "sound_level",
    # Dimensions
    "width": "width",
    "height": "height",
    "depth": "depth",
    "length": "depth",
    "overall width": "width",
    "overall height": "height",
    "overall depth": "depth",
    "overall length": "depth",
    "product width": "width",
    "product height": "height",
    "product depth": "depth",
    "weight": "weight",
    "product weight": "weight",
    "net weight": "weight",
    "shipping weight": "weight",
    "volume": "volume",
    # Performance
    "capacity": "capacity",
    "wash cycles": "wash_cycles",
    "number of wash cycles": "wash_cycles",
    "cycle options": "wash_cycles",
    "drying cycles": "drying_cycles",
    "rpm": "rpm",
    "speed": "rpm",
    "flow rate": "flow_rate",
    "gpm": "gpm",
    "btu": "btu",
    "btu/h": "btu",
    "btu output": "btu",
    "cfm": "cfm",
    "psi": "psi",
    "pressure rating": "pressure_rating",
    "max pressure": "pressure_rating",
    "temperature range": "temperature",
    "operating temperature": "temperature",
    # Connections
    "connection size": "connection_size",
    "connection type": "connection_type",
    "inlet size": "connection_size",
    "outlet size": "connection_size",
    "thread size": "thread_size",
    "pipe size": "pipe_size",
    "fitting size": "pipe_size",
    "mounting type": "mounting_type",
    "installation type": "mounting_type",
    "mount type": "mounting_type",
    # Certifications
    "certification": "certification",
    "certifications": "certification",
    "listings": "certification",
    "approvals": "certification",
    "standard": "certification",
    "standards": "certification",
    "standard/approvals": "certification",
    "agency approvals": "certification",
    "energy star": "energy_star",
    "energy star certified": "energy_star",
    "energy star qualified": "energy_star",
    "prop 65": "prop_65",
    "proposition 65": "prop_65",
    "prop65": "prop_65",
    "california prop 65": "prop_65",
    "rohs": "rohs",
    "rohs compliant": "rohs",
    "rohs compliance": "rohs",
    "ada compliant": "ada_compliant",
    "ada": "ada_compliant",
    # Provenance
    "country of origin": "country_of_origin",
    "country of manufacture": "country_of_origin",
    "made in": "country_of_origin",
    "origin": "country_of_origin",
    "discontinued": "discontinued",
    "availability": "availability",
    # Warranty / pricing
    "warranty": "warranty",
    "warranty information": "warranty",
    "limited warranty": "warranty",
    "warranty period": "warranty",
    "list price": "list_price",
    "msrp": "list_price",
    "price": "list_price",
    # Application
    "application": "application",
    "product type": "product_type",
    "type": "product_type",
    "category": "product_type",
    "sub-category": "product_type",
    "includes": "includes",
    "included accessories": "includes",
    "what's in the box": "includes",
    "accessories included": "includes",
    "package contents": "includes",
    "components included": "includes",
    # Packaging
    "selling qty": "selling_qty",
    "quantity": "selling_qty",
    "pack size": "selling_qty",
    "uom": "selling_uom",
    "unit of measure": "selling_uom",
    "selling uom": "selling_uom",
    "sold as": "selling_uom",
    "standard packaging": "standard_packaging",
    "packaging": "standard_packaging",
    "package type": "standard_packaging",
}


# ---------------------------------------------------------------------------
# Document link patterns (type → link text keywords)
# ---------------------------------------------------------------------------
_DOCUMENT_TYPES: dict[str, tuple[str, ...]] = {
    "spec_sheet": ("spec", "specification", "datasheet", "data sheet", "tech sheet"),
    "sds": ("sds", "safety data sheet", "msds", "material safety"),
    "warranty_doc": ("warranty",),
    "installation_manual": ("install", "installation"),
    "owners_manual": ("owner", "user manual", "user guide", "operating"),
    "service_manual": ("service manual",),
    "catalog": ("catalog", "catalogue", "brochure"),
    "submittal": ("submittal",),
    "technical_bulletin": ("technical bulletin", "tech bulletin"),
    "line_drawing": ("line drawing", "dimensional drawing", "cad drawing"),
    "engineering_drawing": ("engineering drawing", "full drawing"),
    "energy_guide": ("energy guide", "energy star", "energyguide"),
    "compatibility_chart": ("compatibility", "cross reference"),
    "size_chart": ("size chart", "sizing"),
    "product_label": ("product label", "label insert", "product insert"),
}


def _label_to_key(label: str) -> str | None:
    """Normalize a page label to a canonical attribute key."""
    lk = fold(label).lower().strip().rstrip(":")
    # Exact match first
    if lk in _LABEL_MAP:
        return _LABEL_MAP[lk]
    # Substring match
    for frag, key in _LABEL_MAP.items():
        if frag in lk:
            return key
    return None


def _add_attr(
    out: list[ExtractedAttribute],
    seen: set[tuple[str, str]],
    key: str,
    value: str,
    source_url: str,
    evidence: str,
    *,
    uom: str = "",
    confidence: str = "High",
) -> None:
    val = fold(value)
    if not val or len(val) > 500:
        return
    sig = (key, val.lower())
    if sig in seen:
        return
    seen.add(sig)
    out.append(
        ExtractedAttribute(
            key=key,
            value=val,
            source_url=source_url,
            evidence=evidence[:300],
            confidence=confidence,
            uom=uom,
        )
    )


def _page_relevant(page: RetrievedPage, identity: ProductIdentity) -> bool:
    blob = fold(f"{page.text} {page.html} {page.url}").upper()
    mpn = identity.mfg_part_num.upper()
    mpn_norm = normalize_mpn(identity.mfg_part_num)
    if mpn and mpn in blob:
        return True
    if mpn_norm and mpn_norm in blob.replace(" ", "").replace("-", ""):
        return True
    # Manufacturer + product category words from description.
    if identity.manufacturer_query and identity.manufacturer_query.lower() in blob.lower():
        if identity.part_desc and any(w in blob.lower() for w in identity.part_desc.lower().split()[:3]):
            return True
    return False


# ---------------------------------------------------------------------------
# JSON-LD extraction
# ---------------------------------------------------------------------------
def _parse_jsonld(soup: BeautifulSoup, base_url: str) -> tuple[list[tuple[str, str]], list[str], str]:
    attrs: list[tuple[str, str]] = []
    images: list[str] = []
    spec_url = ""

    def walk(node: object) -> None:
        nonlocal spec_url
        if isinstance(node, list):
            for item in node:
                walk(item)
            return
        if not isinstance(node, dict):
            return
        typ = node.get("@type", "")
        types = typ if isinstance(typ, list) else [typ]

        # Walk @graph arrays
        if "@graph" in node:
            walk(node["@graph"])

        # Walk mainEntity / mainEntityOfPage
        for entity_key in ("mainEntity", "mainEntityOfPage", "item"):
            if entity_key in node:
                walk(node[entity_key])

        if not any(t in ("Product", "IndividualProduct") for t in types):
            # Still walk nested graphs.
            for v in node.values():
                if isinstance(v, (dict, list)):
                    walk(v)
            return

        brand = node.get("brand")
        if isinstance(brand, dict):
            brand = brand.get("name", "")
        if brand:
            attrs.append(("brand", str(brand)))

        mfr = node.get("manufacturer")
        if isinstance(mfr, dict):
            mfr_url = mfr.get("url", "")
            mfr = mfr.get("name", "")
            if mfr_url:
                attrs.append(("mfr_url", str(mfr_url)))
        if mfr:
            attrs.append(("manufacturer", str(mfr)))

        for key, out_key in (
            ("name", "product_name"),
            ("sku", "sku"),
            ("mpn", "part_number"),
            ("model", "model"),
            ("color", "color"),
            ("material", "material"),
            ("description", "description"),
            ("category", "product_type"),
            ("productID", "sku"),
            ("url", "product_url"),
            ("countryOfOrigin", "country_of_origin"),
        ):
            val = node.get(key)
            if isinstance(val, dict):
                val = val.get("name", "") or val.get("@value", "")
            if val and isinstance(val, str):
                attrs.append((out_key, str(val)))

        # additionalProperty (Schema.org PropertyValue)
        add_props = node.get("additionalProperty") or []
        if isinstance(add_props, dict):
            add_props = [add_props]
        for prop in add_props:
            if isinstance(prop, dict):
                pname = prop.get("name", "")
                pval = prop.get("value", "")
                if pname and pval:
                    mapped = _label_to_key(str(pname))
                    if mapped:
                        attrs.append((mapped, str(pval)))

        # GTIN at Product level
        for gtin_key in ("gtin13", "gtin", "gtin14", "gtin12"):
            gtin = node.get(gtin_key)
            if gtin:
                attrs.append(("gtin", str(gtin)))
                break

        # Images
        img = node.get("image")
        if isinstance(img, str):
            images.append(urljoin(base_url, img))
        elif isinstance(img, list):
            for i in img:
                if isinstance(i, str):
                    images.append(urljoin(base_url, i))
                elif isinstance(i, dict) and i.get("url"):
                    images.append(urljoin(base_url, str(i["url"])))
        elif isinstance(img, dict) and img.get("url"):
            images.append(urljoin(base_url, str(img["url"])))

        # Offers
        offers = node.get("offers")
        if isinstance(offers, list):
            offers = offers[0] if offers else {}
        if isinstance(offers, dict):
            for gtin_key in ("gtin13", "gtin", "gtin14", "gtin12"):
                gtin = offers.get(gtin_key)
                if gtin:
                    attrs.append(("gtin", str(gtin)))
                    break
            price = offers.get("price")
            if price:
                attrs.append(("list_price", str(price)))

        # Walk remaining nested structures
        for v in node.values():
            if isinstance(v, (dict, list)):
                walk(v)

    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        walk(data)

    # Find spec sheet links
    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = a.get_text(strip=True).lower()
        if is_pdf_url(href) and any(x in text for x in ("spec", "specification", "datasheet", "data sheet")):
            spec_url = urljoin(base_url, href)
            break

    return attrs, images, spec_url


# ---------------------------------------------------------------------------
# Schema.org microdata extraction
# ---------------------------------------------------------------------------
def _parse_microdata(soup: BeautifulSoup, base_url: str) -> tuple[list[tuple[str, str]], list[str]]:
    """Extract Schema.org microdata (itemscope/itemprop) attributes."""
    attrs: list[tuple[str, str]] = []
    images: list[str] = []

    product_scopes = soup.find_all(
        attrs={"itemtype": re.compile(r"schema\.org/(Product|IndividualProduct)", re.I)}
    )
    if not product_scopes:
        return attrs, images

    _MICRO_MAP = {
        "name": "product_name",
        "brand": "brand",
        "manufacturer": "manufacturer",
        "model": "model",
        "sku": "sku",
        "mpn": "part_number",
        "gtin13": "gtin",
        "gtin14": "gtin",
        "gtin": "gtin",
        "color": "color",
        "material": "material",
        "description": "description",
        "url": "product_url",
    }

    for scope in product_scopes:
        for el in scope.find_all(attrs={"itemprop": True}):
            prop = el.get("itemprop", "").lower()
            if prop == "image":
                src = el.get("src") or el.get("href") or el.get("content", "")
                if src:
                    images.append(urljoin(base_url, src))
                continue
            if prop not in _MICRO_MAP:
                continue
            # Get value from content attr, href, or text
            val = el.get("content") or el.get("href") or el.get_text(strip=True)
            if val:
                attrs.append((_MICRO_MAP[prop], str(val)))

    return attrs, images


# ---------------------------------------------------------------------------
# OpenGraph / meta tag extraction
# ---------------------------------------------------------------------------
def _parse_meta_tags(soup: BeautifulSoup, base_url: str) -> tuple[list[tuple[str, str]], list[str]]:
    """Extract OpenGraph and meta tag data as supporting evidence."""
    attrs: list[tuple[str, str]] = []
    images: list[str] = []

    _OG_MAP = {
        "og:title": "product_name",
        "og:description": "description",
        "og:site_name": "manufacturer",
        "og:url": "product_url",
        "product:brand": "brand",
    }

    for meta in soup.find_all("meta"):
        prop = meta.get("property", "") or meta.get("name", "")
        content = meta.get("content", "")
        if not prop or not content:
            continue
        prop_lower = prop.lower()
        if prop_lower == "og:image":
            images.append(urljoin(base_url, content))
        elif prop_lower in _OG_MAP:
            attrs.append((_OG_MAP[prop_lower], content))
        elif prop_lower == "description":
            # Store as supporting description only
            if len(content) > 10:
                attrs.append(("meta_description", content[:300]))
        elif prop_lower == "keywords":
            # Don't use keywords as authoritative — just store for context
            pass

    return attrs, images


# ---------------------------------------------------------------------------
# Specification table parser
# ---------------------------------------------------------------------------
_SPEC_CONTAINER_PATTERNS = re.compile(
    r"spec|specification|technical|details|attribute|product-detail|product-spec|"
    r"productspec|techspec|tech-spec|features-specs|prod-spec",
    re.I,
)


def _parse_spec_tables(soup: BeautifulSoup) -> list[tuple[str, str]]:
    """Dedicated specification-table parser for structured product data."""
    pairs: list[tuple[str, str]] = []

    # Find spec-related containers
    containers = soup.find_all(
        ["div", "section", "article"],
        attrs={"class": _SPEC_CONTAINER_PATTERNS},
    )
    containers += soup.find_all(
        ["div", "section", "article"],
        attrs={"id": _SPEC_CONTAINER_PATTERNS},
    )

    # Also look at all tables
    all_tables = soup.find_all("table")

    # Tables inside spec containers get priority, but we process all
    spec_tables: list[Tag] = []
    for container in containers:
        spec_tables.extend(container.find_all("table"))
    # Add remaining tables not already found
    for table in all_tables:
        if table not in spec_tables:
            spec_tables.append(table)

    for table in spec_tables:
        for row in table.find_all("tr"):
            cells = row.find_all(["th", "td"])
            if len(cells) >= 2:
                label = cells[0].get_text(strip=True)
                value = cells[1].get_text(strip=True)
                if label and value and len(label) < 100 and len(value) < 500:
                    pairs.append((label, value))
            elif len(cells) == 1:
                # Single cell with colon-separated content
                text = cells[0].get_text(strip=True)
                if ":" in text and len(text) < 200:
                    lbl, _, val = text.partition(":")
                    if lbl.strip() and val.strip():
                        pairs.append((lbl.strip(), val.strip()))

    # Also extract from <dl> inside spec containers
    for container in containers:
        for dl in container.find_all("dl"):
            dts = dl.find_all("dt")
            dds = dl.find_all("dd")
            for dt, dd in zip(dts, dds):
                label = dt.get_text(strip=True)
                value = dd.get_text(strip=True)
                if label and value:
                    pairs.append((label, value))

    # Key-value divs inside spec containers (common pattern: label + value divs)
    for container in containers:
        for div in container.find_all("div", recursive=True):
            children = [c for c in div.children if isinstance(c, Tag)]
            if len(children) == 2:
                label = children[0].get_text(strip=True)
                value = children[1].get_text(strip=True)
                if label and value and len(label) < 80 and len(value) < 300:
                    # Avoid picking up navigation-like structures
                    if not children[0].find("a") or children[0].name in ("span", "dt", "th"):
                        pairs.append((label, value))

    return pairs


def _parse_labeled_blocks(soup: BeautifulSoup) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []

    for dl in soup.find_all("dl"):
        dts = dl.find_all("dt")
        dds = dl.find_all("dd")
        for dt, dd in zip(dts, dds):
            label = dt.get_text(strip=True)
            value = dd.get_text(strip=True)
            if label and value:
                pairs.append((label, value))

    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = row.find_all(["th", "td"])
            if len(cells) >= 2:
                label = cells[0].get_text(strip=True)
                value = cells[1].get_text(strip=True)
                if label and value and len(label) < 80:
                    pairs.append((label, value))

    for li in soup.find_all("li"):
        text = li.get_text(strip=True)
        if ":" in text and len(text) < 200:
            label, _, value = text.partition(":")
            if label.strip() and value.strip():
                pairs.append((label.strip(), value.strip()))

    return pairs


# ---------------------------------------------------------------------------
# Feature extraction
# ---------------------------------------------------------------------------
_FEATURE_CONTAINER_PATTERNS = re.compile(
    r"feature|benefit|highlight|product-detail|description|key-point|selling-point|"
    r"prod-feature|product-feature|pdp-feature|overview",
    re.I,
)


def _parse_features(soup: BeautifulSoup) -> list[str]:
    features: list[str] = []
    seen_texts: set[str] = set()

    def _add_feature(txt: str) -> None:
        if 5 < len(txt) < 200:
            sig = txt.lower().strip()
            if sig not in seen_texts:
                seen_texts.add(sig)
                features.append(txt)

    # Lists inside feature-related containers
    for container in soup.find_all(
        ["section", "div", "article"],
        attrs={"class": _FEATURE_CONTAINER_PATTERNS},
    ):
        for li in container.find_all("li", recursive=True):
            _add_feature(li.get_text(strip=True))

    for container in soup.find_all(
        ["section", "div", "article"],
        attrs={"id": _FEATURE_CONTAINER_PATTERNS},
    ):
        for li in container.find_all("li", recursive=True):
            _add_feature(li.get_text(strip=True))

    # Also look for <ul>/<ol> with feature-related parent text (existing approach)
    for ul in soup.find_all(["ul", "ol"]):
        cls = " ".join(ul.get("class") or []).lower()
        parent = ul.find_parent(["section", "div"])
        parent_text = ""
        if parent:
            parent_cls = " ".join(parent.get("class") or []).lower()
            parent_id = (parent.get("id") or "").lower()
            parent_text = f"{parent_cls} {parent_id}"
        if any(k in f"{parent_text} {cls}" for k in (
            "feature", "benefit", "highlight", "product-detail",
            "description", "key-point", "selling-point",
        )):
            for li in ul.find_all("li", recursive=False):
                _add_feature(li.get_text(strip=True))

    return features[:20]


# ---------------------------------------------------------------------------
# Document link extraction
# ---------------------------------------------------------------------------
def _parse_document_links(soup: BeautifulSoup, base_url: str) -> dict[str, str]:
    """Find links to product documents (PDFs, guides, manuals, etc.)."""
    documents: dict[str, str] = {}

    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = (a.get_text(strip=True) or "").lower()
        title = (a.get("title") or "").lower()
        combined = f"{text} {title}"

        if not href or href.startswith(("#", "javascript:", "mailto:")):
            continue

        full_url = urljoin(base_url, href)

        for doc_type, keywords in _DOCUMENT_TYPES.items():
            if doc_type in documents:
                continue
            if any(kw in combined for kw in keywords):
                # Prefer PDF links but accept any document link
                if is_pdf_url(full_url) or any(ext in full_url.lower() for ext in (".pdf", ".doc", ".docx")):
                    documents[doc_type] = full_url
                elif "pdf" in combined or "download" in combined:
                    documents[doc_type] = full_url

    return documents


# ---------------------------------------------------------------------------
# Image extraction
# ---------------------------------------------------------------------------
_GALLERY_PATTERNS = re.compile(
    r"gallery|product-image|product-photo|pdp-image|main-image|hero-image|"
    r"product-media|media-gallery|image-gallery|carousel|slider|product-img",
    re.I,
)

_REJECT_PATTERNS = re.compile(
    r"logo|icon|sprite|banner|placeholder|tracking|pixel|social|nav|menu|"
    r"footer|header|badge|rating|star|thumb-tiny|spacer|blank",
    re.I,
)


def _parse_images(soup: BeautifulSoup, base_url: str) -> list[str]:
    images: list[str] = []
    gallery_images: list[str] = []
    other_images: list[str] = []

    # Find images in product gallery containers first
    gallery_containers = soup.find_all(
        ["div", "section", "figure"],
        attrs={"class": _GALLERY_PATTERNS},
    )
    gallery_containers += soup.find_all(
        ["div", "section", "figure"],
        attrs={"id": _GALLERY_PATTERNS},
    )

    def _extract_img_url(img: Tag) -> str | None:
        src = img.get("src") or img.get("data-src") or img.get("data-lazy-src") or img.get("data-original")
        # Also check srcset for high-res
        if not src:
            srcset = img.get("srcset") or img.get("data-srcset", "")
            if srcset:
                # Take the first URL from srcset
                first = srcset.split(",")[0].strip().split(" ")[0]
                if first:
                    src = first
        if not src or src.startswith("data:"):
            return None
        alt = (img.get("alt") or "").lower()
        cls = " ".join(img.get("class") or []).lower()
        combined = f"{alt} {cls} {src}"
        if _REJECT_PATTERNS.search(combined):
            return None
        # Reject tiny images by checking width/height attrs
        for dim_attr in ("width", "height"):
            dim_val = img.get(dim_attr, "")
            try:
                if dim_val and int(dim_val) < 40:
                    return None
            except (ValueError, TypeError):
                pass
        return urljoin(base_url, src)

    for container in gallery_containers:
        for img in container.find_all("img"):
            url = _extract_img_url(img)
            if url and url not in gallery_images:
                gallery_images.append(url)

    # All other images
    for img in soup.find_all("img"):
        url = _extract_img_url(img)
        if url and url not in gallery_images and url not in other_images:
            other_images.append(url)

    # Gallery images first, then others
    images = gallery_images[:6] + other_images[:4]
    return images[:8]


# ---------------------------------------------------------------------------
# Regex extraction
# ---------------------------------------------------------------------------
def _regex_extract(text: str) -> list[tuple[str, str, str]]:
    found: list[tuple[str, str, str]] = []
    for key, pat in _PATTERNS.items():
        m = pat.search(text)
        if not m:
            continue
        if key == "warranty":
            val = f"{m.group(1)} year warranty"
        elif key == "sound_level":
            val = f"{m.group(1)} dBA"
        elif key in {"voltage", "frequency"}:
            unit = "V" if key == "voltage" else "Hz"
            val = f"{m.group(1)} {unit}"
        elif key == "amperage":
            val = f"{m.group(1)} A"
        elif key in {"width", "height", "depth"}:
            val = m.group(1)
            found.append((key, val, "in"))
            continue
        elif key == "weight":
            val = m.group(1)
            found.append((key, val, "lb"))
            continue
        elif key == "horsepower":
            val = f"{m.group(1)} HP"
        elif key == "rpm":
            val = f"{m.group(1)} RPM"
        elif key == "gpm":
            val = f"{m.group(1)} GPM"
        elif key == "btu":
            val = f"{m.group(1)} BTU"
        elif key == "cfm":
            val = f"{m.group(1)} CFM"
        elif key == "psi":
            val = f"{m.group(1)} PSI"
        else:
            val = m.group(0).strip()
        found.append((key, val, ""))
    return found


# ---------------------------------------------------------------------------
# Main extraction entry point
# ---------------------------------------------------------------------------
def extract_from_page(page: RetrievedPage, identity: ProductIdentity) -> ExtractionResult:
    """Extract facts from one retrieved page. Unknown fields are omitted."""
    result = ExtractionResult()
    if not page.html or not _page_relevant(page, identity):
        return result

    base = page.url
    soup = BeautifulSoup(page.html, "lxml")
    seen: set[tuple[str, str]] = set()
    attrs: list[ExtractedAttribute] = []

    # 1. JSON-LD / structured data (highest confidence)
    ld_attrs, ld_images, spec_url = _parse_jsonld(soup, base)
    for key, val in ld_attrs:
        _add_attr(attrs, seen, key, val, base, f"JSON-LD: {key}", confidence="High")
    result.images.extend(ld_images)
    if spec_url:
        result.spec_sheet_url = spec_url

    # 2. Schema.org microdata
    micro_attrs, micro_images = _parse_microdata(soup, base)
    for key, val in micro_attrs:
        _add_attr(attrs, seen, key, val, base, f"microdata: {key}", confidence="High")
    for img in micro_images:
        if img not in result.images:
            result.images.append(img)

    # 3. OpenGraph / meta tags (supporting evidence)
    meta_attrs, meta_images = _parse_meta_tags(soup, base)
    for key, val in meta_attrs:
        _add_attr(attrs, seen, key, val, base, f"meta: {key}", confidence="Medium")
    for img in meta_images:
        if img not in result.images:
            result.images.append(img)

    # 4. Dedicated specification tables
    for label, value in _parse_spec_tables(soup):
        key = _label_to_key(label)
        if key:
            _add_attr(attrs, seen, key, value, base, f"spec-table: {label}: {value}", confidence="High")

    # 5. Labeled specification blocks (dl, table, li)
    for label, value in _parse_labeled_blocks(soup):
        key = _label_to_key(label)
        if key:
            _add_attr(attrs, seen, key, value, base, f"{label}: {value}", confidence="High")

    # 6. Feature bullets
    for feat in _parse_features(soup):
        _add_attr(attrs, seen, "feature", feat, base, feat, confidence="Medium")

    # 7. Regex on visible text (evidence must exist in page)
    for key, val, uom in _regex_extract(page.text):
        evidence = val
        _add_attr(attrs, seen, key, val, base, evidence, uom=uom, confidence="High")

    # 8. Document links
    documents = _parse_document_links(soup, base)
    result.documents = documents
    if "spec_sheet" in documents and not result.spec_sheet_url:
        result.spec_sheet_url = documents["spec_sheet"]

    # 9. Images
    for img in _parse_images(soup, base):
        if img not in result.images:
            result.images.append(img)

    # Manufacturer URL heuristic
    host = urlparse(base).netloc
    if any(x in host for x in (".com", ".net", ".org")) and not is_pdf_url(base):
        if identity.manufacturer_query.lower() in page.text.lower() or identity.mpn_normalized in norm_key(page.text):
            result.mfr_url = base

    result.attributes = attrs
    result.ref_urls.append(base)
    return result


def merge_extractions(results: list[ExtractionResult]) -> ExtractionResult:
    """Merge multiple page extractions; first high-confidence wins per key."""
    merged = ExtractionResult()
    seen_keys: set[str] = set()
    seen_features: set[str] = set()

    for res in results:
        for attr in res.attributes:
            if attr.key == "feature":
                sig = attr.value.lower()
                if sig in seen_features:
                    continue
                seen_features.add(sig)
                merged.attributes.append(attr)
                continue
            if attr.key in seen_keys:
                continue
            seen_keys.add(attr.key)
            merged.attributes.append(attr)

        for img in res.images:
            if img not in merged.images:
                merged.images.append(img)
        for url in res.ref_urls:
            if url not in merged.ref_urls:
                merged.ref_urls.append(url)
        if not merged.spec_sheet_url and res.spec_sheet_url:
            merged.spec_sheet_url = res.spec_sheet_url
        if not merged.mfr_url and res.mfr_url:
            merged.mfr_url = res.mfr_url
        # Merge documents
        for doc_type, doc_url in res.documents.items():
            if doc_type not in merged.documents:
                merged.documents[doc_type] = doc_url

    return merged
