"""Disk cache + in-memory LRU for retrieved product pages and search results."""

from __future__ import annotations

import hashlib
import json
import threading
import time
from collections import OrderedDict
from pathlib import Path

from backend.app.config import STORAGE_DIR

CACHE_DIR = STORAGE_DIR / "unihack" / "page_cache"
DEFAULT_TTL_SECONDS = 86_400  # 24 hours

# In-memory LRU cache (bounded)
_MAX_MEMORY_ENTRIES = 200
_mem_cache: OrderedDict[str, dict] = OrderedDict()
_mem_lock = threading.Lock()

# Search result cache (bounded)
_MAX_SEARCH_ENTRIES = 500
_search_cache: OrderedDict[str, list[tuple[str, str, str]]] = OrderedDict()
_search_lock = threading.Lock()


def _cache_key(manufacturer: str, part_number: str, url: str) -> str:
    blob = f"{manufacturer}|{part_number}|{url}".lower().strip()
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _entry_path(key: str) -> Path:
    return CACHE_DIR / f"{key}.json"


def get_cached(
    manufacturer: str,
    part_number: str,
    url: str,
    *,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> dict | None:
    key = _cache_key(manufacturer, part_number, url)

    # Check in-memory first
    with _mem_lock:
        if key in _mem_cache:
            data = _mem_cache[key]
            if time.time() - data.get("cached_at", 0) <= ttl_seconds:
                _mem_cache.move_to_end(key)
                return data
            else:
                del _mem_cache[key]

    # Fall back to disk
    path = _entry_path(key)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if time.time() - data.get("cached_at", 0) > ttl_seconds:
            return None
        # Promote to memory
        with _mem_lock:
            _mem_cache[key] = data
            if len(_mem_cache) > _MAX_MEMORY_ENTRIES:
                _mem_cache.popitem(last=False)
        return data
    except (json.JSONDecodeError, OSError):
        return None


def set_cached(
    manufacturer: str,
    part_number: str,
    url: str,
    payload: dict,
) -> None:
    key = _cache_key(manufacturer, part_number, url)
    payload = {**payload, "cached_at": time.time(), "cache_key": key}

    # Store in memory
    with _mem_lock:
        _mem_cache[key] = payload
        if len(_mem_cache) > _MAX_MEMORY_ENTRIES:
            _mem_cache.popitem(last=False)

    # Store on disk
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _entry_path(key).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------------------
# Search result caching
# ---------------------------------------------------------------------------
def _search_key(query: str) -> str:
    return hashlib.sha256(query.lower().strip().encode("utf-8")).hexdigest()


def get_search_cached(query: str, *, ttl_seconds: int = 3600) -> list[tuple[str, str, str]] | None:
    """Get cached search results for a query."""
    key = _search_key(query)
    with _search_lock:
        if key in _search_cache:
            _search_cache.move_to_end(key)
            return _search_cache[key]
    return None


def set_search_cached(query: str, results: list[tuple[str, str, str]]) -> None:
    """Cache search results for a query."""
    key = _search_key(query)
    with _search_lock:
        _search_cache[key] = results
        if len(_search_cache) > _MAX_SEARCH_ENTRIES:
            _search_cache.popitem(last=False)
