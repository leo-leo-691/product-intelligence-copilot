"""Application-facing LLM service used by extraction / vision / helpers."""
from __future__ import annotations

import logging
from typing import Any

from backend.app.config import settings
from backend.app.llm.base import LLMExtractionResult, LLMJsonResult, LLMProvider
from backend.app.llm.factory import get_llm_provider
from backend.app.schemas.categories import CategorySchema
from backend.app.schemas.fields import ExtractionMethod, FieldProvenance, SourceType

logger = logging.getLogger(__name__)


class LLMService:
    def __init__(self, provider: LLMProvider | None = None):
        self.provider = provider or get_llm_provider()

    @property
    def provider_name(self) -> str:
        return self.provider.name

    def is_configured(self) -> bool:
        return self.provider.is_configured()

    def extract_fields_from_text(
        self, text: str, schema: CategorySchema, sku: str
    ) -> dict[str, FieldProvenance] | None:
        """LLM text extraction → FieldProvenance map. None = use offline fallback."""
        if not self.provider.is_configured():
            if self.provider.name == "anthropic":
                raise RuntimeError(
                    "Anthropic provider selected but ANTHROPIC_API_KEY is not configured."
                )
            # Gemini default: offline/demo path when key missing
            logger.info("LLM not configured (%s); skipping text LLM extraction", self.provider.name)
            return None
        try:
            field_specs = [
                {"name": f.name, "type": f.type, "required": f.required, "unit": f.unit}
                for f in schema.fields
            ]
            result = self.provider.extract_product_fields(
                text=text, field_specs=field_specs, sku=sku
            )
            return _to_provenance(result, source_type=SourceType.DOCUMENT, method=ExtractionMethod.TEXT_LLM)
        except RuntimeError:
            raise
        except Exception:
            logger.exception("LLM text extraction failed via %s", self.provider.name)
            return None

    def extract_fields_from_images(
        self,
        image_paths: list[str],
        schema: CategorySchema,
        existing: dict[str, FieldProvenance],
        sku: str,
    ) -> dict[str, FieldProvenance]:
        if not image_paths:
            return existing
        if not self.provider.is_configured():
            if self.provider.name == "anthropic":
                raise RuntimeError(
                    "Anthropic provider selected but ANTHROPIC_API_KEY is not configured."
                )
            logger.info(
                "Images attached for %s but LLM (%s) not configured; skipping VLM",
                sku,
                self.provider.name,
            )
            return existing

        missing = [
            f.name
            for f in schema.fields
            if existing.get(f.name, FieldProvenance(not_found=True)).not_found
        ]
        if not missing:
            return existing

        try:
            result = self.provider.extract_product_fields_from_images(
                image_paths=image_paths, missing_fields=missing, sku=sku
            )
            filled = _to_provenance(
                result, source_type=SourceType.IMAGE, method=ExtractionMethod.VISION_LLM, needs_review=True
            )
            out = dict(existing)
            for name, fp in filled.items():
                if not fp.not_found:
                    out[name] = fp
            return out
        except RuntimeError:
            raise
        except Exception:
            logger.exception("VLM extraction failed via %s for %s", self.provider.name, sku)
            return existing

    def complete_json(self, prompt: str, max_tokens: int = 2048) -> LLMJsonResult | None:
        if not self.provider.is_configured():
            if self.provider.name == "anthropic":
                raise RuntimeError(
                    "Anthropic provider selected but ANTHROPIC_API_KEY is not configured."
                )
            return None
        try:
            return self.provider.complete_json(prompt=prompt, max_tokens=max_tokens)
        except RuntimeError:
            raise
        except Exception:
            logger.exception("LLM complete_json failed via %s", self.provider.name)
            return None


def get_llm_service() -> LLMService:
    return LLMService()


def llm_is_available() -> bool:
    return get_llm_provider().is_configured()


def _to_provenance(
    result: LLMExtractionResult,
    *,
    source_type: SourceType,
    method: ExtractionMethod,
    needs_review: bool = False,
) -> dict[str, FieldProvenance]:
    out: dict[str, FieldProvenance] = {}
    for draft in result.fields:
        if draft.not_found or draft.value is None:
            out[draft.name] = FieldProvenance(not_found=True)
        else:
            out[draft.name] = FieldProvenance(
                value=draft.value,
                source_type=source_type,
                source_snippet=draft.source_snippet,
                source_location=draft.source_location,
                extraction_method=method,
                needs_review=needs_review,
                not_found=False,
            )
    return out
