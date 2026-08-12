"""Shared LLM types and provider protocol."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ExtractedFieldDraft:
    """Provider-agnostic field proposal (before app confidence/validation)."""

    name: str
    value: Any = None
    source_snippet: str | None = None
    source_location: str | None = None
    not_found: bool = False


@dataclass
class LLMExtractionResult:
    """Common extraction result consumed by the existing pipeline."""

    fields: list[ExtractedFieldDraft] = field(default_factory=list)
    provider: str = ""
    model: str = ""
    raw_text: str | None = None


@dataclass
class LLMJsonResult:
    """Generic JSON completion for translate / category-infer helpers."""

    data: dict[str, Any]
    provider: str = ""
    model: str = ""
    raw_text: str | None = None


class LLMProvider(ABC):
    """Interchangeable LLM backend."""

    name: str

    @abstractmethod
    def is_configured(self) -> bool:
        ...

    @abstractmethod
    def extract_product_fields(
        self,
        *,
        text: str,
        field_specs: list[dict[str, Any]],
        sku: str,
    ) -> LLMExtractionResult:
        """Extract fields from document text. Never invent missing values."""
        ...

    @abstractmethod
    def extract_product_fields_from_images(
        self,
        *,
        image_paths: list[str],
        missing_fields: list[str],
        sku: str,
    ) -> LLMExtractionResult:
        """Fill missing fields from images / rasterized pages."""
        ...

    @abstractmethod
    def complete_json(self, *, prompt: str, max_tokens: int = 2048) -> LLMJsonResult:
        """Return a JSON object for lightweight tasks (translate, infer)."""
        ...
