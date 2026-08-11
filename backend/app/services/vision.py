"""Vision-LLM fallback for product images / scanned pages."""
from __future__ import annotations

import base64
import json
import logging
from pathlib import Path

from backend.app.config import settings
from backend.app.schemas.categories import CategorySchema
from backend.app.schemas.fields import ExtractionMethod, FieldProvenance, SourceType

logger = logging.getLogger(__name__)


def _image_media_type(path: Path) -> str:
    suffix = path.suffix.lower()
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }.get(suffix, "image/png")


def extract_from_images(
    image_paths: list[str],
    schema: CategorySchema,
    existing: dict[str, FieldProvenance],
    sku: str,
) -> dict[str, FieldProvenance]:
    """Fill missing fields from images via Claude vision when API key is set."""
    if not image_paths:
        return existing
    if not settings.anthropic_api_key:
        # Soft note: images present but no VLM — leave fields as-is
        logger.info("Images attached for %s but ANTHROPIC_API_KEY not set; skipping VLM", sku)
        return existing

    paths = [Path(p) for p in image_paths if Path(p).exists()]
    if not paths:
        return existing

    missing = [f.name for f in schema.fields if existing.get(f.name, FieldProvenance(not_found=True)).not_found]
    if not missing:
        return existing

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        content: list[dict] = []
        for path in paths[:3]:
            data = base64.standard_b64encode(path.read_bytes()).decode("ascii")
            content.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": _image_media_type(path),
                        "data": data,
                    },
                }
            )
        content.append(
            {
                "type": "text",
                "text": (
                    f"Extract these missing product fields for SKU {sku} from the image(s). "
                    "Return ONLY JSON mapping field name to "
                    '{"value": ..., "source_snippet": "what you read", "source_location": "image region"}. '
                    "Use null if not visible — never invent.\n"
                    f"Missing fields: {json.dumps(missing)}"
                ),
            }
        )
        msg = client.messages.create(
            model=settings.anthropic_model,
            max_tokens=2048,
            messages=[{"role": "user", "content": content}],
        )
        raw = msg.content[0].text  # type: ignore[union-attr]
        start, end = raw.find("{"), raw.rfind("}") + 1
        data = json.loads(raw[start:end])
        out = dict(existing)
        for name in missing:
            item = data.get(name) or {}
            val = item.get("value") if isinstance(item, dict) else item
            if val is None:
                continue
            out[name] = FieldProvenance(
                value=val,
                source_type=SourceType.IMAGE,
                source_snippet=item.get("source_snippet") if isinstance(item, dict) else None,
                source_location=item.get("source_location", "image") if isinstance(item, dict) else "image",
                extraction_method=ExtractionMethod.VISION_LLM,
                needs_review=True,
                not_found=False,
            )
        return out
    except Exception:
        logger.exception("VLM extraction failed for %s", sku)
        return existing
