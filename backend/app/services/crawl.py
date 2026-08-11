"""Capped multi-page crawl for gap-fill enrichment (not open-ended scraping)."""
from __future__ import annotations

import logging
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from backend.app.config import settings

logger = logging.getLogger(__name__)


async def capped_crawl(start_url: str, max_pages: int | None = None) -> list[dict]:
    """Fetch start URL + up to N same-host links. Hard cap for safety/cost."""
    if not settings.crawl_enabled or not start_url:
        return []
    max_pages = max_pages or settings.crawl_max_pages
    max_pages = max(1, min(max_pages, 5))  # hard ceiling

    seen: set[str] = set()
    results: list[dict] = []
    host = urlparse(start_url).netloc
    queue = [start_url]

    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        while queue and len(results) < max_pages:
            url = queue.pop(0)
            if url in seen:
                continue
            seen.add(url)
            try:
                r = await client.get(url, headers={"User-Agent": "ProductIntelligenceCopilot/1.0"})
                r.raise_for_status()
                soup = BeautifulSoup(r.text, "lxml")
                for tag in soup(["script", "style", "nav", "footer"]):
                    tag.decompose()
                text = soup.get_text(separator="\n", strip=True)
                results.append({"url": url, "text": text[:8000]})
                if len(results) >= max_pages:
                    break
                for a in soup.find_all("a", href=True):
                    href = urljoin(url, a["href"])
                    if urlparse(href).netloc != host:
                        continue
                    if href.startswith("mailto:") or href.endswith((".pdf", ".zip", ".png", ".jpg")):
                        continue
                    if href not in seen and len(queue) + len(results) < max_pages * 2:
                        queue.append(href)
            except Exception:
                logger.warning("Crawl failed for %s", url, exc_info=True)
    return results
