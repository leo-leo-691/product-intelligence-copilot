"""Source discovery — find reliable product pages for arbitrary SKUs."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from html import unescape
from urllib.parse import parse_qs, unquote, urlparse

import httpx

from backend.app.config import settings
from backend.app.unihack.cache import get_search_cached, set_search_cached
from backend.app.unihack.identify import ProductIdentity, normalize_mpn
from backend.app.unihack.normalize import fold, norm_key
from backend.app.unihack.retrieve import is_pdf_url

logger = logging.getLogger(__name__)

_USER_AGENT = "ProductIntelligenceCopilot/1.0 (catalog-enrichment)"

# Known manufacturer domains (generic patterns, not product-specific).
_MFR_DOMAIN_HINTS: dict[str, tuple[str, ...]] = {
    "frigidaire": ("frigidaire.com", "electrolux.com"),
    "whirlpool": ("whirlpool.com",),
    "kitchenaid": ("kitchenaid.com", "whirlpool.com"),
    "ge": ("geappliances.com",),
    "bosch": ("bosch-home.com", "bosch.com"),
    "samsung": ("samsung.com",),
    "lg": ("lg.com",),
    "maytag": ("maytag.com", "whirlpool.com"),
    "amana": ("amana.com", "whirlpool.com"),
    "electrolux": ("electrolux.com", "frigidaire.com"),
    "moen": ("moen.com",),
    "delta": ("deltafaucet.com",),
    "kohler": ("kohler.com",),
    "rheem": ("rheem.com",),
    "ao smith": ("hotwater.com", "aosmith.com"),
    "honeywell": ("honeywell.com",),
    "emerson": ("emerson.com",),
    "watts": ("watts.com",),
    "navien": ("navien.com",),
    "rinnai": ("rinnai.us", "rinnai.com"),
    "bradford white": ("bradfordwhite.com",),
    "grundfos": ("grundfos.com",),
    "taco": ("tacocomfort.com",),
    "grohe": ("grohe.us", "grohe.com"),
    "american standard": ("americanstandard.com",),
    "pfister": ("pfisterfaucets.com",),
    "insinkerator": ("insinkerator.com",),
    "noritz": ("noritz.com",),
    "takagi": ("takagi-us.com",),
    "milwaukee": ("milwaukeetool.com",),
    "dewalt": ("dewalt.com",),
    "ridgid": ("ridgid.com",),
    "makita": ("makitatools.com",),
    "lennox": ("lennox.com",),
    "carrier": ("carrier.com",),
    "trane": ("trane.com",),
    "goodman": ("goodmanmfg.com",),
}

_DISTRIBUTOR_DOMAINS = (
    "homedepot.com",
    "lowes.com",
    "bestbuy.com",
    "ajmadison.com",
    "build.com",
    "ferguson.com",
    "grainger.com",
    "zoro.com",
    "supplyhouse.com",
    "appliancepartspros.com",
    "mcmaster.com",
    "globalindustrial.com",
    "mscdirect.com",
    "webstaurantstore.com",
    "plumbingsupply.com",
    "plumbersstock.com",
    "amazon.com",
)


@dataclass
class DiscoveredSource:
    url: str
    title: str
    snippet: str
    source_type: str  # manufacturer_page | spec_pdf | manufacturer_docs | distributor | other
    score: float
    manufacturer_match: bool = False
    part_match: bool = False
    query: str = ""


@dataclass
class SourceDiscoveryResult:
    sources: list[DiscoveredSource] = field(default_factory=list)
    queries_run: list[str] = field(default_factory=list)
    error: str | None = None


def _manufacturer_domains(manufacturer: str, brand: str) -> set[str]:
    domains: set[str] = set()
    for token in (manufacturer, brand):
        key = norm_key(token)
        for hint, doms in _MFR_DOMAIN_HINTS.items():
            if hint in key:
                domains.update(doms)
    return domains


def _part_in_text(mpn: str, mpn_norm: str, text: str) -> bool:
    if not mpn and not mpn_norm:
        return False
    blob = fold(text).upper()
    if mpn and mpn.upper() in blob:
        return True
    if mpn_norm and mpn_norm in blob.replace(" ", "").replace("-", ""):
        return True
    return False


def _manufacturer_in_text(manufacturer: str, brand: str, text: str) -> bool:
    blob = fold(text).lower()
    for token in (manufacturer, brand):
        if token and token.lower() in blob:
            return True
    return False


def _score_source(
    url: str,
    title: str,
    snippet: str,
    identity: ProductIdentity,
    mfr_domains: set[str],
) -> DiscoveredSource:
    host = urlparse(url).netloc.lower().replace("www.", "")
    text = f"{title} {snippet} {url}"
    part_match = _part_in_text(identity.mfg_part_num, identity.mpn_normalized, text)
    mfr_match = _manufacturer_in_text(identity.manufacturer_query, identity.brand_query, text)

    score = 0.0
    source_type = "other"

    if part_match:
        score += 50
    if mfr_match:
        score += 25
    if any(host.endswith(d) for d in mfr_domains):
        score += 40
        source_type = "manufacturer_page"
    elif is_pdf_url(url):
        score += 20
        source_type = "spec_pdf"
    elif any(host.endswith(d) for d in _DISTRIBUTOR_DOMAINS):
        score += 12
        source_type = "distributor"
    if "spec" in url.lower() or "specification" in text.lower():
        score += 8
        if source_type == "other":
            source_type = "manufacturer_docs"
    if "support" in host or "manual" in url.lower():
        score += 5
        if source_type in {"other", "manufacturer_page"}:
            source_type = "manufacturer_docs"
    # Boost for product-detail indicators in URL
    url_lower = url.lower()
    if any(seg in url_lower for seg in ("/product/", "/p/", "/products/", "/model/")):
        score += 8
    # Boost for structured data indicators in snippet
    snippet_lower = snippet.lower()
    if any(kw in snippet_lower for kw in ("specifications", "features", "product details")):
        score += 5

    # Penalize irrelevant search/aggregator pages.
    if any(x in host for x in (
        "facebook.com", "youtube.com", "reddit.com", "pinterest.com",
        "twitter.com", "instagram.com", "tiktok.com", "quora.com",
        "yelp.com", "wikipedia.org",
    )):
        score -= 30
    # Penalize generic category/search pages
    if any(x in url_lower for x in ("/search?", "/category/", "/browse/", "q=")):
        score -= 15

    return DiscoveredSource(
        url=url,
        title=title,
        snippet=snippet,
        source_type=source_type,
        score=score,
        manufacturer_match=mfr_match,
        part_match=part_match,
    )


def _parse_ddg_html(html: str) -> list[tuple[str, str, str]]:
    """Parse DuckDuckGo HTML results into (url, title, snippet)."""
    results: list[tuple[str, str, str]] = []
    for block in re.findall(
        r'<a[^>]+class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
        html,
        re.I | re.S,
    ):
        href, title_html = block
        url = href
        if "uddg=" in href:
            qs = parse_qs(urlparse(href).query)
            url = unquote(qs.get("uddg", [href])[0])
        title = unescape(re.sub(r"<[^>]+>", "", title_html)).strip()
        results.append((url, title, ""))

    # Snippets are in adjacent result__snippet blocks — pair by index.
    snippets = [
        unescape(re.sub(r"<[^>]+>", "", s)).strip()
        for s in re.findall(r'class="result__snippet"[^>]*>(.*?)</', html, re.I | re.S)
    ]
    out: list[tuple[str, str, str]] = []
    for i, (url, title, _) in enumerate(results):
        snip = snippets[i] if i < len(snippets) else ""
        out.append((url, title, snip))
    return out


def _search_tavily(query: str, max_results: int) -> list[tuple[str, str, str]]:
    if not settings.tavily_api_key:
        return []
    try:
        with httpx.Client(timeout=settings.unihack_request_timeout) as client:
            r = client.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": settings.tavily_api_key,
                    "query": query,
                    "max_results": max_results,
                    "search_depth": "basic",
                },
            )
            r.raise_for_status()
            data = r.json()
            return [
                (hit.get("url", ""), hit.get("title", ""), hit.get("content", "")[:400])
                for hit in data.get("results") or []
                if hit.get("url")
            ]
    except Exception as exc:  # noqa: BLE001
        logger.debug("Tavily search failed: %s", exc)
        return []


def _search_serpapi(query: str, max_results: int) -> list[tuple[str, str, str]]:
    if not settings.serpapi_api_key:
        return []
    try:
        with httpx.Client(timeout=settings.unihack_request_timeout) as client:
            r = client.get(
                "https://serpapi.com/search",
                params={
                    "api_key": settings.serpapi_api_key,
                    "q": query,
                    "engine": "google",
                    "num": max_results,
                },
            )
            r.raise_for_status()
            data = r.json()
            return [
                (hit.get("link", ""), hit.get("title", ""), hit.get("snippet", ""))
                for hit in data.get("organic_results") or []
                if hit.get("link")
            ]
    except Exception as exc:  # noqa: BLE001
        logger.debug("SerpAPI search failed: %s", exc)
        return []


def _search_ddg(query: str, max_results: int) -> list[tuple[str, str, str]]:
    try:
        with httpx.Client(timeout=settings.unihack_request_timeout, follow_redirects=True) as client:
            r = client.post(
                "https://html.duckduckgo.com/html/",
                data={"q": query, "b": "", "kl": "us-en"},
                headers={"User-Agent": _USER_AGENT},
            )
            r.raise_for_status()
            parsed = _parse_ddg_html(r.text)
            return parsed[:max_results]
    except Exception as exc:  # noqa: BLE001
        logger.debug("DuckDuckGo search failed: %s", exc)
        return []


def web_search(query: str, max_results: int | None = None) -> list[tuple[str, str, str]]:
    """Search web with API priority: Tavily → SerpAPI → DuckDuckGo HTML."""
    limit = max_results or settings.unihack_search_max_results
    # Check search cache first
    cached = get_search_cached(query)
    if cached is not None:
        return cached[:limit]
    for fn in (_search_tavily, _search_serpapi, _search_ddg):
        hits = fn(query, limit)
        if hits:
            set_search_cached(query, hits)
            return hits
    return []


def discover_sources(
    identity: ProductIdentity,
    *,
    search_fn=web_search,
    max_results: int | None = None,
) -> SourceDiscoveryResult:
    """Discover candidate sources for an arbitrary product row."""
    if not identity.search_queries:
        return SourceDiscoveryResult(error="no search queries")

    mfr_domains = _manufacturer_domains(identity.manufacturer_query, identity.brand_query)
    limit = max_results or settings.unihack_search_max_results
    seen_urls: set[str] = set()
    ranked: list[DiscoveredSource] = []
    queries_run: list[str] = []

    for query in identity.search_queries[:3]:
        queries_run.append(query)
        for url, title, snippet in search_fn(query, limit):
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            src = _score_source(url, title, snippet, identity, mfr_domains)
            src.query = query
            # Require part number match OR strong manufacturer domain match.
            if src.part_match or (src.manufacturer_match and src.score >= 40):
                ranked.append(src)
            elif src.score >= 55:
                ranked.append(src)

    ranked.sort(key=lambda s: -s.score)
    return SourceDiscoveryResult(sources=ranked[: limit + 2], queries_run=queries_run)
