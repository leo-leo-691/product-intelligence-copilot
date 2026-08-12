"""Google Gemini LLM provider (google-genai SDK)."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from backend.app.config import settings
from backend.app.llm.base import LLMExtractionResult, LLMJsonResult, LLMProvider
from backend.app.llm.parsing import (
    drafts_from_field_map,
    field_extraction_schema,
    parse_json_object,
)

logger = logging.getLogger(__name__)


def _image_mime(path: Path) -> str:
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
        ".pdf": "application/pdf",
    }.get(path.suffix.lower(), "image/png")


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key if api_key is not None else settings.gemini_api_key
        self.model = model or settings.gemini_model

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def _client(self):
        if not self.api_key:
            raise RuntimeError("Gemini provider selected but GEMINI_API_KEY is not configured.")
        from google import genai

        return genai.Client(api_key=self.api_key)

    def extract_product_fields(
        self,
        *,
        text: str,
        field_specs: list[dict[str, Any]],
        sku: str,
    ) -> LLMExtractionResult:
        from google.genai import types

        names = [f["name"] for f in field_specs]
        prompt = (
            f"Extract product fields for SKU {sku} from the context. "
            "For each field return value, source_snippet (exact quote), and source_location. "
            "Use null for missing values — never invent.\n"
            f"Fields: {json.dumps(field_specs)}\n"
            f"Context:\n{text[:12000]}"
        )
        client = self._client()
        response = client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_json_schema=field_extraction_schema(names),
            ),
        )
        raw = response.text or ""
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
        from google.genai import types

        client = self._client()
        parts: list[Any] = []
        for path_str in image_paths[:3]:
            path = Path(path_str)
            if not path.exists():
                continue
            parts.append(
                types.Part.from_bytes(data=path.read_bytes(), mime_type=_image_mime(path))
            )
        parts.append(
            types.Part.from_text(
                text=(
                    f"Extract these missing product fields for SKU {sku} from the image(s). "
                    "For each field return value, source_snippet, source_location. "
                    "Use null if not visible — never invent.\n"
                    f"Missing fields: {json.dumps(missing_fields)}"
                )
            )
        )
        if len(parts) == 1:
            return LLMExtractionResult(fields=[], provider=self.name, model=self.model)

        response = client.models.generate_content(
            model=self.model,
            contents=parts,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_json_schema=field_extraction_schema(missing_fields),
            ),
        )
        raw = response.text or ""
        data = parse_json_object(raw)
        return drafts_from_field_map(
            data, missing_fields, provider=self.name, model=self.model, raw_text=raw
        )

    def complete_json(self, *, prompt: str, max_tokens: int = 2048) -> LLMJsonResult:
        from google.genai import types

        client = self._client()
        response = client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                max_output_tokens=max_tokens,
            ),
        )
        raw = response.text or ""
        data = parse_json_object(raw)
        return LLMJsonResult(
            data=data, provider=self.name, model=self.model, raw_text=raw
        )
