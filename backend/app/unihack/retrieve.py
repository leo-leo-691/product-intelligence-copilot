"""HTTP retrieval with caching, retries, timeouts, and rate limiting."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from backend.app.config import settings
from backend.app.unihack.cache import get_cached, set_cached

logger = logging.getLogger(__name__)

_USER_AGENT = "ProductIntelligenceCopilot/1.0 (catalog-enrichment)"

# Per-domain rate limiting
_domain_locks: dict[str, threading.Lock] = {}
_domain_last_request: dict[str, float] = {}
_domain_registry_lock = threading.Lock()


@dataclass
class RetrievedPage:
    url: str
    html: str
    text: str
    content_type: str
    status_code: int
    from_cache: bool = False


def _get_domain_lock(domain: str) -> threading.Lock:
    """Get or create a per-domain lock for rate limiting."""
    with _domain_registry_lock:
        if domain not in _domain_locks:
            _domain_locks[domain] = threading.Lock()
        return _domain_locks[domain]


def _throttle_domain(domain: str) -> None:
    """Per-domain rate limiting — allows concurrent requests to different domains."""
    delay = max(0.0, settings.unihack_request_delay)
    lock = _get_domain_lock(domain)
    with lock:
        last = _domain_last_request.get(domain, 0.0)
        elapsed = time.monotonic() - last
        if elapsed < delay:
            time.sleep(delay - elapsed)
        _domain_last_request[domain] = time.monotonic()


def _html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    return soup.get_text(separator="\n", strip=True)


class PageRetriever:
    """Fetch public product pages with cache + polite rate limiting."""

    def __init__(
        self,
        *,
        timeout: float | None = None,
        max_retries: int | None = None,
    ) -> None:
        self.timeout = timeout or settings.unihack_request_timeout
        self.max_retries = max_retries or settings.unihack_max_retries
        # Shared client for connection pooling
        self._client = httpx.Client(
            timeout=self.timeout,
            follow_redirects=True,
            headers={"User-Agent": _USER_AGENT},
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
        )

    def close(self) -> None:
        """Close the shared HTTP client."""
        try:
            self._client.close()
        except Exception:  # noqa: BLE001
            pass

    def get(
        self,
        url: str,
        *,
        manufacturer: str = "",
        part_number: str = "",
        use_cache: bool = True,
    ) -> RetrievedPage | None:
        if not url or not url.startswith(("http://", "https://")):
            return None

        if use_cache:
            cached = get_cached(manufacturer, part_number, url)
            if cached and cached.get("html"):
                return RetrievedPage(
                    url=url,
                    html=cached["html"],
                    text=cached.get("text") or _html_to_text(cached["html"]),
                    content_type=cached.get("content_type", "text/html"),
                    status_code=cached.get("status_code", 200),
                    from_cache=True,
                )

        domain = urlparse(url).netloc.lower()
        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                _throttle_domain(domain)
                resp = self._client.get(url)
                if resp.status_code >= 400:
                    logger.debug("HTTP %s for %s", resp.status_code, url)
                    if resp.status_code in {403, 429, 503} and attempt < self.max_retries:
                        time.sleep(1.5 * (attempt + 1))
                        continue
                    return None
                content_type = resp.headers.get("content-type", "")
                html = resp.text
                text = _html_to_text(html) if "html" in content_type.lower() else html[:12000]
                page = RetrievedPage(
                    url=str(resp.url),
                    html=html,
                    text=text[:40000],
                    content_type=content_type,
                    status_code=resp.status_code,
                )
                if use_cache and "html" in content_type.lower():
                    set_cached(
                        manufacturer,
                        part_number,
                        url,
                        {
                            "url": page.url,
                            "html": page.html[:500_000],
                            "text": page.text,
                            "content_type": page.content_type,
                            "status_code": page.status_code,
                        },
                    )
                return page
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                if attempt < self.max_retries:
                    time.sleep(1.0 * (attempt + 1))
        logger.debug("Failed to retrieve %s: %s", url, last_exc)
        return None


def is_pdf_url(url: str) -> bool:
    path = urlparse(url).path.lower()
    return path.endswith(".pdf") or "pdf" in path
