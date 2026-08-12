"""Shared JSON parsing helpers for LLM providers."""
from __future__ import annotations

import json
import re
from typing import Any

from backend.app.llm.base import ExtractedFieldDraft, LLMExtractionResult


def parse_json_object(raw: str) -> dict[str, Any]:
    text = (raw or "").strip()
    if not text:
        raise ValueError("Empty model response")
    # Strip markdown fences if present
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, re.I)
    if fence:
        text = fence.group(1).strip()
    start, end = text.find("{"), text.rfind("}") + 1
    if start < 0 or end <= start:
        raise ValueError("No JSON object found in model response")
    data = json.loads(text[start:end])
    if not isinstance(data, dict):
        raise ValueError("Expected a JSON object")
    return data


def drafts_from_field_map(
    data: dict[str, Any],
    field_names: list[str],
    *,
    provider: str,
    model: str,
    raw_text: str | None = None,
) -> LLMExtractionResult:
    drafts: list[ExtractedFieldDraft] = []
    for name in field_names:
        item = data.get(name)
        if item is None:
            drafts.append(ExtractedFieldDraft(name=name, not_found=True))
            continue
        if isinstance(item, dict):
            val = item.get("value")
            if val is None:
                drafts.append(ExtractedFieldDraft(name=name, not_found=True))
            else:
                drafts.append(
                    ExtractedFieldDraft(
                        name=name,
                        value=val,
                        source_snippet=item.get("source_snippet"),
                        source_location=item.get("source_location"),
                        not_found=False,
                    )
                )
        else:
            drafts.append(
                ExtractedFieldDraft(name=name, value=item, not_found=False)
            )
    return LLMExtractionResult(
        fields=drafts, provider=provider, model=model, raw_text=raw_text
    )


def field_extraction_schema(field_names: list[str]) -> dict[str, Any]:
    """JSON schema for structured field extraction responses."""
    props: dict[str, Any] = {}
    for name in field_names:
        props[name] = {
            "type": "object",
            "properties": {
                "value": {},
                "source_snippet": {"type": "string"},
                "source_location": {"type": "string"},
            },
        }
    return {"type": "object", "properties": props}
