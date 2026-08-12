"""Multi-language detection + optional English normalization."""
from __future__ import annotations

import logging
import re
from typing import Any

from backend.app.config import settings

logger = logging.getLogger(__name__)

# Lightweight script / keyword heuristics (no heavy NLP deps)
NON_ENGLISH_HINTS = [
    (r"[äöüßÄÖÜ]", "de"),
    (r"[àâçéèêëîïôùûüÿœæ]", "fr"),
    (r"[áéíóúñ¿¡]", "es"),
    (r"[àèéìòù]", "it"),
    (r"[\u0400-\u04FF]", "ru"),
    (r"[\u4e00-\u9fff]", "zh"),
    (r"[\u3040-\u30ff]", "ja"),
    (r"[\uac00-\ud7af]", "ko"),
]


def detect_language(text: str) -> dict[str, Any]:
    sample = (text or "")[:5000]
    if not sample.strip():
        return {
            "source_language": "unknown",
            "normalized_to": "en",
            "translation_applied": False,
            "translation_confidence": None,
            "reasoning": "empty text",
        }

    for pattern, lang in NON_ENGLISH_HINTS:
        if re.search(pattern, sample):
            return {
                "source_language": lang,
                "normalized_to": "en",
                "translation_applied": False,
                "translation_confidence": None,
                "reasoning": f"Script/diacritic heuristic matched '{lang}'",
            }

    # Common non-English industrial words
    lower = sample.lower()
    if any(w in lower for w in ("druck", "nennweite", "werkstoff", "ventil")):
        return {
            "source_language": "de",
            "normalized_to": "en",
            "translation_applied": False,
            "translation_confidence": None,
            "reasoning": "German industrial keywords",
        }
    if any(w in lower for w in ("pression", "diamètre", "matériau", "vanne")):
        return {
            "source_language": "fr",
            "normalized_to": "en",
            "translation_applied": False,
            "translation_confidence": None,
            "reasoning": "French industrial keywords",
        }

    return {
        "source_language": "en",
        "normalized_to": "en",
        "translation_applied": False,
        "translation_confidence": 1.0,
        "reasoning": "No non-English signals",
    }


def maybe_normalize_to_english(text: str, lang_meta: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """If non-English and LLM configured, translate to English for extraction."""
    meta = dict(lang_meta)
    src = meta.get("source_language")
    if not settings.translate_enabled or src in (None, "en", "unknown"):
        return text, meta

    from backend.app.llm import get_llm_service

    service = get_llm_service()
    if not service.is_configured():
        meta["reasoning"] = (meta.get("reasoning") or "") + "; translation skipped (no API key)"
        return text, meta

    try:
        result = service.complete_json(
            prompt=(
                f"Translate the following industrial datasheet text from {src} to English. "
                "Preserve numbers, units, and part numbers exactly. "
                'Return ONLY JSON: {"english_text":"...","translation_confidence":0.0-1.0}\n\n'
                f"{text[:8000]}"
            ),
            max_tokens=4096,
        )
        if not result:
            meta["reasoning"] = (meta.get("reasoning") or "") + "; translation skipped"
            return text, meta
        english = result.data.get("english_text") or text
        meta["translation_applied"] = True
        meta["translation_confidence"] = float(result.data.get("translation_confidence") or 0.7)
        meta["normalized_to"] = "en"
        meta["reasoning"] = (meta.get("reasoning") or "") + "; LLM translation applied"
        return english, meta
    except Exception:
        logger.exception("Translation failed")
        meta["reasoning"] = (meta.get("reasoning") or "") + "; translation failed"
        return text, meta
