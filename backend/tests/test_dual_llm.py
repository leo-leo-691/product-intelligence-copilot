"""Tests for optional dual-LLM extraction (mocked providers, no real API calls)."""
from __future__ import annotations

from typing import Any

import pytest

from backend.app.config import settings
from backend.app.llm.base import ExtractedFieldDraft, LLMExtractionResult, LLMJsonResult, LLMProvider
from backend.app.llm.compare import classify_pair, values_equivalent
from backend.app.llm.dual import DualLLMService
from backend.app.schemas.categories import CATEGORIES
from backend.app.schemas.fields import FieldProvenance
from backend.app.services.confidence import compute_confidence
from backend.app.services.validation import validate_field


class FakeProvider(LLMProvider):
    def __init__(
        self,
        name: str,
        *,
        values: dict[str, Any] | None = None,
        fail: bool = False,
        configured: bool = True,
        model: str = "fake",
        snippets: dict[str, str] | None = None,
    ):
        self.name = name
        self.model = model
        self._values = values or {}
        self._fail = fail
        self._configured = configured
        self._snippets = snippets or {}
        self.calls = 0

    def is_configured(self) -> bool:
        return self._configured

    def extract_product_fields(self, *, text: str, field_specs: list[dict[str, Any]], sku: str) -> LLMExtractionResult:
        self.calls += 1
        if self._fail:
            raise RuntimeError(f"{self.name} simulated failure")
        fields = []
        for spec in field_specs:
            name = spec["name"]
            if name not in self._values:
                fields.append(ExtractedFieldDraft(name=name, not_found=True))
            else:
                fields.append(
                    ExtractedFieldDraft(
                        name=name,
                        value=self._values[name],
                        source_snippet=self._snippets.get(name, f"{self.name}:{name}"),
                        source_location=f"{self.name}-loc",
                    )
                )
        return LLMExtractionResult(fields=fields, provider=self.name, model=self.model)

    def extract_product_fields_from_images(self, **kwargs) -> LLMExtractionResult:
        raise NotImplementedError

    def complete_json(self, *, prompt: str, max_tokens: int = 2048) -> LLMJsonResult:
        raise NotImplementedError


SCHEMA = CATEGORIES["industrial_valve"]


def _service(g: FakeProvider, c: FakeProvider, primary: str = "gemini") -> DualLLMService:
    return DualLLMService(gemini=g, claude=c, primary_name=primary)


def test_dual_disabled_only_selected_provider(monkeypatch):
    monkeypatch.setattr(settings, "dual_llm_enabled", False)
    monkeypatch.setattr(settings, "llm_provider", "gemini")
    gemini = FakeProvider("gemini", values={"manufacturer": "Acme"}, model="gemini-3.1-flash-lite")
    claude = FakeProvider("anthropic", values={"manufacturer": "Acme"}, model="claude-sonnet-4-20250514")

    from backend.app.llm import LLMService
    from backend.app.services.extraction import extract_with_llm_bundle

    monkeypatch.setattr("backend.app.services.extraction.get_llm_service", lambda: LLMService(provider=gemini))

    bundle = extract_with_llm_bundle("unlabeled blob that will not parse as labels", SCHEMA, "SKU-1")
    assert bundle is not None
    assert bundle.fields["manufacturer"].value == "Acme"
    assert gemini.calls == 1
    assert claude.calls == 0
    assert bundle.dual_llm is None


def test_dual_enabled_both_providers_run():
    g = FakeProvider("gemini", values={"manufacturer": "Acme"}, model="gemini-3.1-flash-lite")
    c = FakeProvider("anthropic", values={"manufacturer": "Acme"}, model="claude-sonnet-4-20250514")
    out = _service(g, c).extract_fields_from_text("ctx", SCHEMA, "SKU-1")
    assert g.calls == 1
    assert c.calls == 1
    assert out.meta.gemini_status == "success"
    assert out.meta.claude_status == "success"
    mfr = next(x for x in out.meta.comparisons if x.field_name == "manufacturer")
    assert mfr.status == "AGREEMENT"


def test_both_agree():
    g = FakeProvider("gemini", values={"manufacturer": "AcmeFlow", "body_material": "WCB"})
    c = FakeProvider("anthropic", values={"manufacturer": "acmeflow", "body_material": "wcb"})
    out = _service(g, c).extract_fields_from_text("ctx", SCHEMA, "SKU-1")
    row = next(x for x in out.meta.comparisons if x.field_name == "manufacturer")
    assert row.status == "AGREEMENT"
    assert out.fields["manufacturer"].value in ("AcmeFlow", "acmeflow")
    assert out.fields["manufacturer"].needs_review is False
    assert not any(cf.field_name == "manufacturer" for cf in out.llm_conflicts)


def test_both_disagree_conflict_review():
    g = FakeProvider("gemini", values={"max_operating_pressure_psi": "10 bar"})
    c = FakeProvider("anthropic", values={"max_operating_pressure_psi": "16 bar"})
    out = _service(g, c).extract_fields_from_text("ctx", SCHEMA, "SKU-1")
    row = next(x for x in out.meta.comparisons if x.field_name == "max_operating_pressure_psi")
    assert row.status == "DISAGREEMENT"
    assert row.requires_review is True
    assert out.fields["max_operating_pressure_psi"].needs_review is True
    assert any(cf.field_name == "max_operating_pressure_psi" and cf.kind == "llm" for cf in out.llm_conflicts)
    conflict = next(cf for cf in out.llm_conflicts if cf.field_name == "max_operating_pressure_psi")
    providers = {cand.provider for cand in conflict.candidates}
    assert providers == {"gemini", "anthropic"}


def test_gemini_missing_field():
    g = FakeProvider("gemini", values={"valve_type": "Ball"})
    c = FakeProvider("anthropic", values={"manufacturer": "Acme", "valve_type": "Ball"})
    out = _service(g, c).extract_fields_from_text("ctx", SCHEMA, "SKU-1")
    row = next(x for x in out.meta.comparisons if x.field_name == "manufacturer")
    assert row.status == "MISSING_FROM_GEMINI"
    assert out.fields["manufacturer"].value == "Acme"
    assert out.fields["manufacturer"].llm_provider == "anthropic"
    assert out.fields["manufacturer"].needs_review is True


def test_claude_missing_field():
    g = FakeProvider("gemini", values={"manufacturer": "Acme"})
    c = FakeProvider("anthropic", values={"valve_type": "Ball"})
    out = _service(g, c).extract_fields_from_text("ctx", SCHEMA, "SKU-1")
    row = next(x for x in out.meta.comparisons if x.field_name == "manufacturer")
    assert row.status == "MISSING_FROM_CLAUDE"
    assert out.fields["manufacturer"].value == "Acme"
    assert out.fields["manufacturer"].llm_provider == "gemini"


def test_gemini_failure_claude_still_used():
    g = FakeProvider("gemini", fail=True)
    c = FakeProvider("anthropic", values={"manufacturer": "Acme"}, snippets={"manufacturer": "claude-snip"})
    out = _service(g, c).extract_fields_from_text("ctx", SCHEMA, "SKU-1")
    assert out.fields is not None
    assert out.meta.gemini_status == "provider_unavailable"
    assert out.meta.claude_status == "success"
    assert out.fields["manufacturer"].value == "Acme"
    assert out.fields["manufacturer"].source_snippet == "claude-snip"
    assert out.llm_conflicts == []
    row = next(x for x in out.meta.comparisons if x.field_name == "manufacturer")
    assert row.status == "PROVIDER_UNAVAILABLE"
    assert row.requires_review is False
    assert out.fields["manufacturer"].needs_review is False
    from backend.app.llm.dual import llm_agreement_scores

    scores = llm_agreement_scores(out.meta)
    assert "manufacturer" not in scores


def test_claude_failure_gemini_still_used():
    g = FakeProvider("gemini", values={"manufacturer": "Acme"}, snippets={"manufacturer": "gemini-snip"})
    c = FakeProvider("anthropic", fail=True)
    out = _service(g, c).extract_fields_from_text("ctx", SCHEMA, "SKU-1")
    assert out.fields is not None
    assert out.meta.claude_status == "provider_unavailable"
    assert out.meta.gemini_status == "success"
    assert out.fields["manufacturer"].source_snippet == "gemini-snip"
    assert out.llm_conflicts == []
    assert all(row.status == "PROVIDER_UNAVAILABLE" for row in out.meta.comparisons)
    assert not any(row.requires_review for row in out.meta.comparisons if row.gemini_value is not None)
    from backend.app.llm.dual import llm_agreement_scores

    assert llm_agreement_scores(out.meta) == {}


def test_both_fail_returns_no_fields():
    g = FakeProvider("gemini", fail=True)
    c = FakeProvider("anthropic", fail=True)
    out = _service(g, c).extract_fields_from_text("ctx", SCHEMA, "SKU-1")
    assert out.fields is None
    assert out.meta.gemini_status == "provider_unavailable"
    assert out.meta.claude_status == "provider_unavailable"


def test_unit_normalized_equivalent_agreement():
    assert values_equivalent("10 bar", "10 BAR")
    assert values_equivalent("10 bar", "145 psi")
    assert not values_equivalent("10 bar", "16 bar")
    assert classify_pair("10 bar", "145 psi", gemini_missing=False, claude_missing=False) == "AGREEMENT"
    g = FakeProvider("gemini", values={"max_operating_pressure_psi": "10 bar"})
    c = FakeProvider("anthropic", values={"max_operating_pressure_psi": "145 psi"})
    out = _service(g, c).extract_fields_from_text("ctx", SCHEMA, "SKU-1")
    row = next(x for x in out.meta.comparisons if x.field_name == "max_operating_pressure_psi")
    assert row.status == "AGREEMENT"


def test_existing_validation_still_works():
    from backend.app.schemas.categories import INDUSTRIAL_VALVE

    fdef = next(f for f in INDUSTRIAL_VALVE.fields if f.name == "nominal_size_in")
    fp, fmt, failed = validate_field(fdef, FieldProvenance(value=2.0, not_found=False))
    assert failed is False
    assert fmt == 1.0
    _fp2, _, failed2 = validate_field(fdef, FieldProvenance(value=None, not_found=True))
    assert failed2 is True


def test_existing_provenance_not_overwritten():
    g = FakeProvider(
        "gemini",
        values={"manufacturer": "Acme"},
        snippets={"manufacturer": "from-gemini-only"},
    )
    c = FakeProvider(
        "anthropic",
        values={"manufacturer": "OtherCo"},
        snippets={"manufacturer": "from-claude-only"},
    )
    out = _service(g, c).extract_fields_from_text("ctx", SCHEMA, "SKU-1")
    row = next(x for x in out.meta.comparisons if x.field_name == "manufacturer")
    assert row.gemini_source_snippet == "from-gemini-only"
    assert row.claude_source_snippet == "from-claude-only"
    conflict = next(cf for cf in out.llm_conflicts if cf.field_name == "manufacturer")
    by_p = {cand.provider: cand for cand in conflict.candidates}
    assert by_p["gemini"].source_snippet == "from-gemini-only"
    assert by_p["anthropic"].source_snippet == "from-claude-only"


def test_existing_confidence_formula_unchanged_without_dual():
    raw_a, band_a, reason_a = compute_confidence(
        "text-LLM", ["document"], {"document": "Acme"}, False, 1.0, False
    )
    raw_b, band_b, reason_b = compute_confidence(
        "text-LLM", ["document"], {"document": "Acme"}, False, 1.0, False, llm_agreement=None
    )
    assert raw_a == raw_b
    assert band_a == band_b
    assert "llm_agreement" not in reason_a
    assert "llm_agreement" not in reason_b
    expected = 0.35 * 0.75 + 0.25 * 0.5 + 0.25 * 1.0 + 0.15 * 1.0
    assert abs(raw_a - expected) < 1e-9

    raw_d, band_d, reason_d = compute_confidence(
        "text-LLM", ["document"], {"document": "Acme"}, False, 1.0, False, llm_agreement=0.0
    )
    assert reason_d["llm_agreement"] == 0.0
    assert raw_d <= 0.44
    assert band_d == "Low"

    raw_ok, _, reason_ok = compute_confidence(
        "text-LLM", ["document"], {"document": "Acme"}, False, 1.0, False, llm_agreement=1.0
    )
    assert reason_ok["llm_agreement"] == 1.0
    assert raw_ok == pytest.approx(min(1.0, expected + 0.05))


def test_dual_not_configured_does_not_call_api():
    g = FakeProvider("gemini", configured=False, values={"manufacturer": "X"})
    c = FakeProvider("anthropic", values={"manufacturer": "Acme"})
    out = _service(g, c).extract_fields_from_text("ctx", SCHEMA, "SKU-1")
    assert g.calls == 0
    assert c.calls == 1
    assert out.meta.gemini_status == "provider_unavailable"
    assert out.fields["manufacturer"].value == "Acme"
    row = next(x for x in out.meta.comparisons if x.field_name == "manufacturer")
    assert row.status == "PROVIDER_UNAVAILABLE"
    assert row.requires_review is False


def test_config_dual_default_false():
    from backend.app.config import Settings

    assert Settings.model_fields["dual_llm_enabled"].default is False
    assert Settings.model_fields["llm_provider"].default == "gemini"


LABELED_TWO_FIELDS = "manufacturer: AcmeFlow\nmodel number: V-100\n"


def test_labeled_two_fields_dual_disabled_skips_llm(monkeypatch):
    monkeypatch.setattr(settings, "dual_llm_enabled", False)
    from backend.app.services.extraction import extract_bundle

    called = {"n": 0}

    def boom(*_a, **_k):
        called["n"] += 1
        raise AssertionError("LLM must not run when dual is off and labeled parse has >=2 fields")

    monkeypatch.setattr("backend.app.services.extraction.extract_with_llm_bundle", boom)
    bundle = extract_bundle(LABELED_TWO_FIELDS, SCHEMA, "VALVE-A-001")
    assert called["n"] == 0
    assert bundle.dual_llm is None
    found = [name for name, fp in bundle.fields.items() if not fp.not_found]
    assert len(found) >= 2
    assert bundle.fields["manufacturer"].value == "AcmeFlow"
    assert bundle.fields["manufacturer"].extraction_method.value in ("table-parse", "text-LLM")


def test_labeled_two_fields_dual_enabled_runs_both_providers(monkeypatch):
    monkeypatch.setattr(settings, "dual_llm_enabled", True)
    from backend.app.llm.dual import DualLLMService as RealDual
    from backend.app.services.extraction import extract_bundle

    g = FakeProvider(
        "gemini",
        values={"manufacturer": "OtherCo", "model_number": "V-100"},
        model="gemini-3.1-flash-lite",
        snippets={"manufacturer": "gemini-mfr"},
    )
    c = FakeProvider(
        "anthropic",
        values={"manufacturer": "AcmeFlow", "model_number": "V-100"},
        model="claude-sonnet-4-20250514",
        snippets={"manufacturer": "claude-mfr"},
    )

    monkeypatch.setattr(
        "backend.app.llm.dual.DualLLMService",
        lambda *a, **k: RealDual(gemini=g, claude=c),
    )
    bundle = extract_bundle(LABELED_TWO_FIELDS, SCHEMA, "VALVE-A-001")
    assert g.calls == 1
    assert c.calls == 1
    assert bundle.dual_llm is not None
    assert bundle.dual_llm.gemini_status == "success"
    assert bundle.dual_llm.claude_status == "success"
    assert bundle.fields["manufacturer"].value == "AcmeFlow"
    assert bundle.fields["manufacturer"].source_location == "document text"
    compared = {row.field_name: row.status for row in bundle.dual_llm.comparisons}
    assert compared["manufacturer"] in ("AGREEMENT", "DISAGREEMENT")
    assert compared["model_number"] == "AGREEMENT"
    assert any(row.field_name == "manufacturer" for row in bundle.dual_llm.comparisons)
    mfr_conflicts = [cf for cf in (bundle.llm_conflicts or []) if cf.field_name == "manufacturer"]
    assert mfr_conflicts, "labeled vs Gemini disagreement should surface as a conflict"
    providers = {cand.provider for cand in mfr_conflicts[0].candidates}
    assert "gemini" in providers

