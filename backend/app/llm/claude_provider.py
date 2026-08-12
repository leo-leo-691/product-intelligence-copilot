"""Anthropic Claude LLM provider."""
from __future__ import annotations

import base64
import json
import logging
from pathlib import Path
from typing import Any

from backend.app.config import settings
from backend.app.llm.base import LLMExtractionResult, LLMJsonResult, LLMProvider
from backend.app.llm.parsing import drafts_from_field_map, parse_json_object

logger = logging.getLogger(__name__)


def _image_media_type(path: Path) -> str:
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }.get(path.suffix.lower(), "image/png")


class ClaudeProvider(LLMProvider):
    name = "anthropic"

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key if api_key is not None else settings.anthropic_api_key
        self.model = model or settings.anthropic_model

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def _client(self):
        if not self.api_key:
            raise RuntimeError("Anthropic provider selected but ANTHROPIC_API_KEY is not configured.")
        import anthropic

        return anthropic.Anthropic(api_key=self.api_key)

    def extract_product_fields(
        self,
        *,
        text: str,
        field_specs: list[dict[str, Any]],
        sku: str,
    ) -> LLMExtractionResult:
        names = [f["name"] for f in field_specs]
        prompt = (
            f"Extract product fields for SKU {sku} from the context. "
            "Return ONLY valid JSON object mapping field names to "
            '{"value": ..., "source_snippet": "quote from text", "source_location": "page or section"}. '
            "Use null for missing values — never invent.\n"
            f"Fields: {json.dumps(field_specs)}\n"
            f"Context:\n{text[:12000]}"
        )
        client = self._client()
        msg = client.messages.create(
            model=self.model,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = msg.content[0].text  # type: ignore[union-attr]
        data = parse_json_object(raw)
        return drafts_from_field_map(
            data, names, provider=self.name, model=self.model, raw_text=raw
        )

    def extract_product_fields_from_images(
        self,
        *,
        image_paths: list[str],
        missing_fields: list[str],
        sku: str,
    ) -> LLMExtractionResult:
        client = self._client()
        content: list[dict[str, Any]] = []
        for path_str in image_paths[:3]:
            path = Path(path_str)
            if not path.exists():
                continue
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
                    f"Missing fields: {json.dumps(missing_fields)}"
                ),
            }
        )
        if len(content) == 1:
            return LLMExtractionResult(
                fields=[], provider=self.name, model=self.model
            )
        msg = client.messages.create(
            model=self.model,
            max_tokens=2048,
            messages=[{"role": "user", "content": content}],
        )
        raw = msg.content[0].text  # type: ignore[union-attr]
        data = parse_json_object(raw)
        return drafts_from_field_map(
            data, missing_fields, provider=self.name, model=self.model, raw_text=raw
        )

    def complete_json(self, *, prompt: str, max_tokens: int = 2048) -> LLMJsonResult:
        client = self._client()
        msg = client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = msg.content[0].text  # type: ignore[union-attr]
        data = parse_json_object(raw)
        return LLMJsonResult(
            data=data, provider=self.name, model=self.model, raw_text=raw
        )
