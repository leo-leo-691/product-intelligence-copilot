"""Optional dual extraction: Gemini and Claude independently, then compare."""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from dataclasses import dataclass, field
from typing import Any

from backend.app.config import settings
from backend.app.llm.base import LLMExtractionResult, LLMProvider
from backend.app.llm.compare import classify_pair
from backend.app.llm.factory import get_llm_provider
from backend.app.schemas.categories import CategorySchema
from backend.app.schemas.fields import (
    ConflictCandidate,
    DualLLMFieldComparison,
    DualLLMMeta,
    ExtractionMethod,
    FieldConflict,
    FieldProvenance,
    SourceType,
)

logger = logging.getLogger(__name__)

EXTRACT_TIMEOUT_S = 45


@dataclass
class DualExtractOutcome:
    fields: dict[str, FieldProvenance] | None
    meta: DualLLMMeta
    llm_conflicts: list[FieldConflict] = field(default_factory=list)


def _is_missing(fp: FieldProvenance | None) -> bool:
    if fp is None:
        return True
    return bool(fp.not_found or fp.value is None or fp.value == "")


def _drafts_to_fields(result: LLMExtractionResult) -> dict[str, FieldProvenance]:
    out: dict[str, FieldProvenance] = {}
    for draft in result.fields:
        if draft.not_found or draft.value is None:
            out[draft.name] = FieldProvenance(not_found=True)
        else:
            out[draft.name] = FieldProvenance(
                value=draft.value,
                source_type=SourceType.DOCUMENT,
                source_snippet=draft.source_snippet,
                source_location=draft.source_location,
                extraction_method=ExtractionMethod.TEXT_LLM,
                not_found=False,
            )
    return out


def _safe_extract(
    provider: LLMProvider,
    *,
    text: str,
    field_specs: list[dict[str, Any]],
    sku: str,
) -> tuple[str, LLMExtractionResult | None, str | None]:
    if not provider.is_configured():
        return "provider_unavailable", None, provider.model if hasattr(provider, "model") else None
    try:
        result = provider.extract_product_fields(text=text, field_specs=field_specs, sku=sku)
        return "success", result, result.model
    except Exception:
        logger.exception("Dual extraction failed for %s", provider.name)
        model = getattr(provider, "model", None)
        return "provider_unavailable", None, model


class DualLLMService:
    """Run Gemini and Claude independently on the same extraction request."""

    def __init__(
        self,
        gemini: LLMProvider | None = None,
        claude: LLMProvider | None = None,
        primary_name: str | None = None,
    ):
        self.gemini = gemini or get_llm_provider("gemini")
        self.claude = claude or get_llm_provider("anthropic")
        self.primary_name = (primary_name or settings.llm_provider or "gemini").strip().lower()

    def extract_fields_from_text(
        self, text: str, schema: CategorySchema, sku: str
    ) -> DualExtractOutcome:
        field_specs = [
            {"name": f.name, "type": f.type, "required": f.required, "unit": f.unit}
            for f in schema.fields
        ]
        names = [f.name for f in schema.fields]

        with ThreadPoolExecutor(max_workers=2) as pool:
            fut_g = pool.submit(
                _safe_extract, self.gemini, text=text, field_specs=field_specs, sku=sku
            )
            fut_c = pool.submit(
                _safe_extract, self.claude, text=text, field_specs=field_specs, sku=sku
            )
            try:
                g_status, g_result, g_model = fut_g.result(timeout=EXTRACT_TIMEOUT_S)
            except FuturesTimeout:
                g_status, g_result, g_model = "provider_unavailable", None, getattr(self.gemini, "model", None)
            try:
                c_status, c_result, c_model = fut_c.result(timeout=EXTRACT_TIMEOUT_S)
            except FuturesTimeout:
                c_status, c_result, c_model = "provider_unavailable", None, getattr(self.claude, "model", None)

        g_fields = _drafts_to_fields(g_result) if g_result else {}
        c_fields = _drafts_to_fields(c_result) if c_result else {}
        for fp in g_fields.values():
            fp.llm_provider = "gemini"
        for fp in c_fields.values():
            fp.llm_provider = "anthropic"

        meta = DualLLMMeta(
            enabled=True,
            gemini_status=g_status,
            claude_status=c_status,
            gemini_model=g_model or getattr(self.gemini, "model", None),
            claude_model=c_model or getattr(self.claude, "model", None),
        )

        if g_status != "success" and c_status != "success":
            return DualExtractOutcome(fields=None, meta=meta)

        g_ok = g_status == "success"
        c_ok = c_status == "success"

        merged: dict[str, FieldProvenance] = {}
        conflicts: list[FieldConflict] = []
        comparisons: list[DualLLMFieldComparison] = []

        for name in names:
            g_fp = g_fields.get(name)
            c_fp = c_fields.get(name)
            g_miss = g_ok and _is_missing(g_fp)
            c_miss = c_ok and _is_missing(c_fp)
            g_val = None if (not g_ok or g_miss) else g_fp.value  # type: ignore[union-attr]
            c_val = None if (not c_ok or c_miss) else c_fp.value  # type: ignore[union-attr]
            status = classify_pair(
                g_val,
                c_val,
                gemini_missing=g_miss,
                claude_missing=c_miss,
                gemini_unavailable=not g_ok,
                claude_unavailable=not c_ok,
            )
            requires_review = status in (
                "DISAGREEMENT",
                "MISSING_FROM_GEMINI",
                "MISSING_FROM_CLAUDE",
            )
            comparisons.append(
                DualLLMFieldComparison(
                    field_name=name,
                    gemini_value=g_val,
                    claude_value=c_val,
                    gemini_source_snippet=None if (not g_ok or g_miss) else (g_fp.source_snippet if g_fp else None),
                    gemini_source_location=None if (not g_ok or g_miss) else (g_fp.source_location if g_fp else None),
                    claude_source_snippet=None if (not c_ok or c_miss) else (c_fp.source_snippet if c_fp else None),
                    claude_source_location=None if (not c_ok or c_miss) else (c_fp.source_location if c_fp else None),
                    status=status,
                    requires_review=requires_review,
                )
            )
            merged[name] = _pick_field(
                status=status,
                g_fp=g_fp,
                c_fp=c_fp,
                primary=self.primary_name,
                requires_review=requires_review,
            )
            if status == "DISAGREEMENT" and g_fp and c_fp and g_ok and c_ok:
                conflicts.append(
                    FieldConflict(
                        field_name=name,
                        kind="llm",
                        candidates=[
                            ConflictCandidate(
                                value=g_fp.value,
                                source_type=g_fp.source_type or SourceType.DOCUMENT,
                                source_snippet=g_fp.source_snippet,
                                source_location=g_fp.source_location,
                                extraction_method=g_fp.extraction_method,
                                provider="gemini",
                            ),
                            ConflictCandidate(
                                value=c_fp.value,
                                source_type=c_fp.source_type or SourceType.DOCUMENT,
                                source_snippet=c_fp.source_snippet,
                                source_location=c_fp.source_location,
                                extraction_method=c_fp.extraction_method,
                                provider="anthropic",
                            ),
                        ],
                    )
                )

        meta.comparisons = comparisons
        return DualExtractOutcome(fields=merged, meta=meta, llm_conflicts=conflicts)


def _pick_field(
    *,
    status: str,
    g_fp: FieldProvenance | None,
    c_fp: FieldProvenance | None,
    primary: str,
    requires_review: bool,
) -> FieldProvenance:
    if status == "BOTH_MISSING":
        return FieldProvenance(not_found=True, needs_review=True)
    if status == "PROVIDER_UNAVAILABLE":
        chosen = g_fp if not _is_missing(g_fp) else c_fp
        if chosen is None or _is_missing(chosen):
            return FieldProvenance(not_found=True, needs_review=True)
        out = chosen.model_copy()
        out.needs_review = False
        return out
    if status == "AGREEMENT":
        chosen = g_fp if primary != "anthropic" else c_fp
        chosen = chosen or g_fp or c_fp
        assert chosen is not None
        out = chosen.model_copy()
        out.needs_review = False
        return out
    if status == "MISSING_FROM_GEMINI":
        out = (c_fp or FieldProvenance(not_found=True)).model_copy()
        out.needs_review = True
        return out
    if status == "MISSING_FROM_CLAUDE":
        out = (g_fp or FieldProvenance(not_found=True)).model_copy()
        out.needs_review = True
        return out
    # DISAGREEMENT — keep a candidate for the form, never treat as resolved.
    preferred = g_fp if primary != "anthropic" else c_fp
    preferred = preferred or g_fp or c_fp or FieldProvenance(not_found=True)
    out = preferred.model_copy()
    out.needs_review = True
    return out


def llm_agreement_scores(meta: DualLLMMeta | None) -> dict[str, float]:
    if not meta or not meta.enabled:
        return {}
    scores: dict[str, float] = {}
    for row in meta.comparisons:
        if row.status == "AGREEMENT":
            scores[row.field_name] = 1.0
        elif row.status == "DISAGREEMENT":
            scores[row.field_name] = 0.0
        elif row.status in ("MISSING_FROM_GEMINI", "MISSING_FROM_CLAUDE"):
            scores[row.field_name] = 0.5
        # PROVIDER_UNAVAILABLE: omit — do not treat as disagreement or missing-field evidence.
    return scores


def merge_conflicts(
    source_conflicts: list[FieldConflict],
    llm_conflicts: list[FieldConflict],
) -> list[FieldConflict]:
    """Keep document/web conflicts independent; append LLM disagreements."""
    by_name = {c.field_name: c for c in source_conflicts}
    out = list(source_conflicts)
    for extra in llm_conflicts:
        existing = by_name.get(extra.field_name)
        if not existing:
            out.append(extra)
            by_name[extra.field_name] = extra
            continue
        seen = {(str(c.value), c.provider) for c in existing.candidates}
        for cand in extra.candidates:
            key = (str(cand.value), cand.provider)
            if key not in seen:
                existing.candidates.append(cand)
                seen.add(key)
    return out
