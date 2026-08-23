"""Fetch and cache official UniHack CSVs. Never invent headers or rows."""

from __future__ import annotations

import logging
import urllib.request
from pathlib import Path

from backend.app.config import DATA_DIR
from backend.app.unihack.constants import (
    OFFICIAL_EXPECTED_OUTPUT_CSV,
    OFFICIAL_SAMPLE_INPUT_CSV,
)

logger = logging.getLogger(__name__)

UNIHACK_DATA = DATA_DIR / "unihack"
EXPECTED_OUTPUT_CACHE = UNIHACK_DATA / "official_expected_output.csv"
SAMPLE_INPUT_CACHE = UNIHACK_DATA / "official_sample_input.csv"


def _download(url: str, dest: Path, timeout: int = 45) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "ProductIntelligenceCopilot/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read()
    if not data or len(data) < 20:
        raise RuntimeError(f"Official download was empty: {url}")
    dest.write_bytes(data)
    logger.info("Cached official UniHack file %s (%s bytes)", dest.name, len(data))
    return dest


def ensure_expected_output() -> Path:
    from backend.app.unihack.discover import find_delivery_schema

    found = find_delivery_schema()
    if found and found.exists() and found.stat().st_size > 20:
        return found
    if EXPECTED_OUTPUT_CACHE.exists() and EXPECTED_OUTPUT_CACHE.stat().st_size > 20:
        return EXPECTED_OUTPUT_CACHE
    return _download(OFFICIAL_EXPECTED_OUTPUT_CSV, EXPECTED_OUTPUT_CACHE)


def ensure_sample_input() -> Path:
    from backend.app.unihack.discover import find_file

    found = find_file("input_1000")
    if found and found.exists() and found.stat().st_size > 20:
        return found
    if SAMPLE_INPUT_CACHE.exists() and SAMPLE_INPUT_CACHE.stat().st_size > 20:
        return SAMPLE_INPUT_CACHE
    return _download(OFFICIAL_SAMPLE_INPUT_CSV, SAMPLE_INPUT_CACHE)
