"""Category auto-inference from title/text/image context."""
from __future__ import annotations

import json
import logging
import re

from backend.app.config import settings
from backend.app.schemas.categories import CATEGORIES

logger = logging.getLogger(__name__)

KEYWORD_MAP: dict[str, list[str]] = {
    "industrial_valve": ["valve", "ball valve", "gate valve", "globe", "ansi", "flanged", "psi"],
    "bearing": ["bearing", "bore", "rpm", "deep groove", "roller", "skf", "od mm"],
    "sensor": ["sensor", "transmitter", "4-20", "transducer", "ip67", "mA"],
    "motor": ["motor", "kW", "horsepower", "induction", "frame iec", "rpm motor", "enclosure"],
    "fastener": ["bolt", "screw", "nut", "fastener", "thread", "hex head", "grade 8"],
}


def infer_category(
    text: str,
    title: str | None = None,
    sku: str | None = None,
) -> tuple[str, str, float]:
    """
    Returns (category_id, reasoning, confidence 0-1).
    Heuristic keyword scoring first; optional LLM refine when keyed.
    """
    blob = f"{title or ''} {sku or ''} {text or ''}".lower()
    scores: dict[str, float] = {cid: 0.0 for cid in CATEGORIES}
    hits: dict[str, list[str]] = {cid: [] for cid in CATEGORIES}

    for cid, kws in KEYWORD_MAP.items():
        for kw in kws:
            if kw.lower() in blob:
                scores[cid] += 1.0
                hits[cid].append(kw)

    # SKU prefix hints
    sku_u = (sku or "").upper()
    if sku_u.startswith("VALVE") or sku_u.startswith("VLV"):
        scores["industrial_valve"] += 2
        hits["industrial_valve"].append("sku-prefix")
    if sku_u.startswith("BEAR"):
        scores["bearing"] += 2
        hits["bearing"].append("sku-prefix")
    if sku_u.startswith("SENS"):
        scores["sensor"] += 2
        hits["sensor"].append("sku-prefix")
    if sku_u.startswith("MOT"):
        scores["motor"] += 2
        hits["motor"].append("sku-prefix")
    if sku_u.startswith("FAST") or sku_u.startswith("BOLT"):
        scores["fastener"] += 2
        hits["fastener"].append("sku-prefix")

    best = max(scores, key=lambda k: scores[k])
    best_score = scores[best]
    if best_score <= 0:
        # LLM fallback
        llm = _llm_infer(blob[:4000])
        if llm:
            return llm
        return "industrial_valve", "No strong signals; defaulted to industrial_valve", 0.35

    total = sum(scores.values()) or 1
    conf = min(0.95, 0.4 + best_score / max(total, 1) * 0.5)
    reason = f"Matched keywords for {CATEGORIES[best].display_name}: {', '.join(hits[best][:6]) or 'score'}"
    return best, reason, round(conf, 3)


def _llm_infer(text: str) -> tuple[str, str, float] | None:
    if not settings.anthropic_api_key or not text.strip():
        return None
    try:
        import anthropic

        cats = [{"id": c.category_id, "name": c.display_name} for c in CATEGORIES.values()]
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        msg = client.messages.create(
            model=settings.anthropic_model,
            max_tokens=400,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Infer the best product category. Return ONLY JSON: "
                        '{"category_id":"...","reasoning":"...","confidence":0.0-1.0}\n'
                        f"Categories: {json.dumps(cats)}\nText:\n{text[:3500]}"
                    ),
                }
            ],
        )
        raw = msg.content[0].text  # type: ignore[union-attr]
        start, end = raw.find("{"), raw.rfind("}") + 1
        data = json.loads(raw[start:end])
        cid = data.get("category_id")
        if cid in CATEGORIES:
            return cid, str(data.get("reasoning") or "LLM inference"), float(data.get("confidence") or 0.7)
    except Exception:
        logger.exception("LLM category inference failed")
    return None
