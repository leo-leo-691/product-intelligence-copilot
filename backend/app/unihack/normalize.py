"""Placeholder stripping, casing, and light string cleanup."""

from __future__ import annotations

import re
import unicodedata

from backend.app.unihack.constants import PLACEHOLDERS

_WS = re.compile(r"\s+")


def fold(text: str) -> str:
    n = unicodedata.normalize("NFKC", text or "")
    return _WS.sub(" ", n).strip()


def is_placeholder(text: str) -> bool:
    key = fold(text).lower()
    if not key:
        return True
    return key in PLACEHOLDERS


def clean_input(text: str | None) -> str:
    value = fold(str(text) if text is not None else "")
    if is_placeholder(value):
        return ""
    return value


def norm_key(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", fold(text).lower())
