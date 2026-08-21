"""Deterministic field comparison for dual-LLM extraction."""
from __future__ import annotations

import re
from typing import Any

# Convert to a shared SI-ish quantity for equivalence checks.
_UNIT_TO_SI: dict[str, tuple[str, float]] = {
    "bar": ("pressure_pa", 100_000.0),
    "psi": ("pressure_pa", 6_894.757293168),
    "kpa": ("pressure_pa", 1_000.0),
    "mpa": ("pressure_pa", 1_000_000.0),
    "pa": ("pressure_pa", 1.0),
    "mm": ("length_m", 0.001),
    "cm": ("length_m", 0.01),
    "m": ("length_m", 1.0),
    "in": ("length_m", 0.0254),
    "inch": ("length_m", 0.0254),
    "inches": ("length_m", 0.0254),
    "kn": ("force_n", 1_000.0),
    "n": ("force_n", 1.0),
    "kw": ("power_w", 1_000.0),
    "w": ("power_w", 1.0),
    "v": ("voltage_v", 1.0),
    "rpm": ("rpm", 1.0),
}

_NUM_UNIT = re.compile(
    r"^\s*([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)\s*([a-zA-Z%°]+)?\s*$"
)


def _collapse(text: str) -> str:
    return re.sub(r"\s+", " ", str(text).strip()).casefold()


def _parse_quantity(value: Any) -> tuple[float, str | None] | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value), None
    raw = str(value).replace(",", "").strip()
    m = _NUM_UNIT.match(raw)
    if not m:
        return None
    num = float(m.group(1))
    unit = (m.group(2) or "").casefold() or None
    return num, unit


def values_equivalent(a: Any, b: Any, *, rel_tol: float = 0.02, abs_tol: float = 1e-6) -> bool:
    """True if values match after case/whitespace and optional unit conversion."""
    if a is None or b is None:
        return False
    if _collapse(a) == _collapse(b):
        return True

    qa, qb = _parse_quantity(a), _parse_quantity(b)
    if qa is None or qb is None:
        return False
    na, ua = qa
    nb, ub = qb

    if ua and ub:
        da = _UNIT_TO_SI.get(ua)
        db = _UNIT_TO_SI.get(ub)
        if da and db and da[0] == db[0]:
            sa, sb = na * da[1], nb * db[1]
            scale = max(abs(sa), abs(sb), abs_tol)
            return abs(sa - sb) <= max(abs_tol, rel_tol * scale)
        if ua == ub:
            scale = max(abs(na), abs(nb), abs_tol)
            return abs(na - nb) <= max(abs_tol, rel_tol * scale)
        return False

    if ua is None and ub is None:
        scale = max(abs(na), abs(nb), abs_tol)
        return abs(na - nb) <= max(abs_tol, rel_tol * scale)
    return False


def classify_pair(
    gemini_value: Any,
    claude_value: Any,
    *,
    gemini_missing: bool,
    claude_missing: bool,
    gemini_unavailable: bool = False,
    claude_unavailable: bool = False,
) -> str:
    """Compare one field. Provider-level failure is not a field omission."""
    if gemini_unavailable and claude_unavailable:
        return "PROVIDER_UNAVAILABLE"
    if gemini_unavailable or claude_unavailable:
        return "PROVIDER_UNAVAILABLE"
    if gemini_missing and claude_missing:
        return "BOTH_MISSING"
    if gemini_missing:
        return "MISSING_FROM_GEMINI"
    if claude_missing:
        return "MISSING_FROM_CLAUDE"
    if values_equivalent(gemini_value, claude_value):
        return "AGREEMENT"
    return "DISAGREEMENT"
