"""Vision-LLM fallback for product images / scanned pages."""
from __future__ import annotations

import logging

from backend.app.llm import get_llm_service
from backend.app.schemas.categories import CategorySchema
from backend.app.schemas.fields import FieldProvenance

logger = logging.getLogger(__name__)


def extract_from_images(
    image_paths: list[str],
    schema: CategorySchema,
    existing: dict[str, FieldProvenance],
    sku: str,
) -> dict[str, FieldProvenance]:
    """Fill missing fields from images via configured LLM vision provider."""
    return get_llm_service().extract_fields_from_images(
        image_paths, schema, existing, sku
    )
