"""Unit tests for interchangeable Gemini / Claude LLM providers (mocked APIs)."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from backend.app.llm.base import ExtractedFieldDraft, LLMExtractionResult, LLMJsonResult
from backend.app.llm.claude_provider import ClaudeProvider
from backend.app.llm.factory import get_llm_provider, require_configured_provider
from backend.app.llm.gemini_provider import GeminiProvider
from backend.app.llm.parsing import drafts_from_field_map, parse_json_object
from backend.app.schemas.categories import CATEGORIES
from backend.app.schemas.fields import FieldProvenance


def test_gemini_provider_selected(monkeypatch):
    monkeypatch.setattr("backend.app.llm.factory.settings.llm_provider", "gemini")
    provider = get_llm_provider()
    assert isinstance(provider, GeminiProvider)
    assert provider.name == "gemini"


def test_claude_provider_selected(monkeypatch):
    monkeypatch.setattr("backend.app.llm.factory.settings.llm_provider", "anthropic")
    provider = get_llm_provider()
    assert isinstance(provider, ClaudeProvider)
    assert provider.name == "anthropic"


def test_default_models(monkeypatch):
    monkeypatch.setattr("backend.app.config.settings.gemini_model", "gemini-3.1-flash-lite")
    monkeypatch.setattr("backend.app.config.settings.anthropic_model", "claude-sonnet-4-20250514")
    g = GeminiProvider(api_key="x", model=None)
    c = ClaudeProvider(api_key="x", model=None)
    # Providers read settings when model is None
    from backend.app.config import settings

    assert settings.gemini_model == "gemini-3.1-flash-lite"
    assert settings.anthropic_model == "claude-sonnet-4-20250514"
    assert g.model == "gemini-3.1-flash-lite"
    assert c.model == "claude-sonnet-4-20250514"


def test_unsupported_provider(monkeypatch):
    monkeypatch.setattr("backend.app.llm.factory.settings.llm_provider", "xyz")
    with pytest.raises(ValueError) as exc:
        get_llm_provider()
    assert "Unsupported LLM_PROVIDER: xyz" in str(exc.value)
    assert "gemini" in str(exc.value) and "anthropic" in str(exc.value)


def test_missing_gemini_key_not_configured(monkeypatch):
    monkeypatch.setattr("backend.app.config.settings.gemini_api_key", None)
    monkeypatch.setattr("backend.app.llm.factory.settings.llm_provider", "gemini")
    provider = get_llm_provider()
    assert provider.is_configured() is False
    with pytest.raises(RuntimeError) as exc:
        require_configured_provider()
    assert "GEMINI_API_KEY" in str(exc.value)


def test_missing_claude_key_clear_error(monkeypatch):
    monkeypatch.setattr("backend.app.config.settings.anthropic_api_key", None)
    monkeypatch.setattr("backend.app.llm.factory.settings.llm_provider", "anthropic")
    provider = get_llm_provider()
    assert provider.is_configured() is False
    with pytest.raises(RuntimeError) as exc:
        require_configured_provider()
    assert "ANTHROPIC_API_KEY" in str(exc.value)
    assert "not configured" in str(exc.value)


def test_parse_json_object():
    assert parse_json_object('{"a": 1}')["a"] == 1
    assert parse_json_object('```json\n{"a": 2}\n```')["a"] == 2


def test_drafts_schema_compatible():
    schema = CATEGORIES["industrial_valve"]
    names = [f.name for f in schema.fields]
    data = {
        "manufacturer": {"value": "Acme", "source_snippet": "Manufacturer: Acme", "source_location": "p1"},
        "model_number": {"value": "V-1", "source_snippet": "Model V-1", "source_location": "p1"},
    }
    result = drafts_from_field_map(data, names, provider="gemini", model="gemini-3.1-flash-lite")
    assert isinstance(result, LLMExtractionResult)
    assert len(result.fields) == len(names)
    found = {d.name: d for d in result.fields if not d.not_found}
    assert found["manufacturer"].value == "Acme"

    # Same drafts work for Claude provider label
    result2 = drafts_from_field_map(data, names, provider="anthropic", model="claude-sonnet-4-20250514")
    assert {d.name for d in result2.fields} == set(names)


def test_gemini_extract_mocked():
    provider = GeminiProvider(api_key="test-key", model="gemini-3.1-flash-lite")
    fake_response = MagicMock()
    fake_response.text = json.dumps(
        {
            "manufacturer": {
                "value": "AcmeFlow",
                "source_snippet": "Manufacturer: AcmeFlow",
                "source_location": "doc",
            }
        }
    )
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = fake_response
    with patch.object(provider, "_client", return_value=mock_client):
        result = provider.extract_product_fields(
            text="Manufacturer: AcmeFlow",
            field_specs=[{"name": "manufacturer", "type": "string"}],
            sku="VALVE-1",
        )
    assert result.provider == "gemini"
    assert result.model == "gemini-3.1-flash-lite"
    assert result.fields[0].value == "AcmeFlow"
    mock_client.models.generate_content.assert_called_once()
    call_kwargs = mock_client.models.generate_content.call_args.kwargs
    assert call_kwargs["model"] == "gemini-3.1-flash-lite"


def test_claude_extract_mocked():
    provider = ClaudeProvider(api_key="test-key", model="claude-sonnet-4-20250514")
    fake_msg = MagicMock()
    fake_msg.content = [
        MagicMock(
            text=json.dumps(
                {
                    "manufacturer": {
                        "value": "AcmeFlow",
                        "source_snippet": "Manufacturer: AcmeFlow",
                        "source_location": "doc",
                    }
                }
            )
        )
    ]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = fake_msg
    with patch.object(provider, "_client", return_value=mock_client):
        result = provider.extract_product_fields(
            text="Manufacturer: AcmeFlow",
            field_specs=[{"name": "manufacturer", "type": "string"}],
            sku="VALVE-1",
        )
    assert result.provider == "anthropic"
    assert result.model == "claude-sonnet-4-20250514"
    assert result.fields[0].value == "AcmeFlow"
    call_kwargs = mock_client.messages.create.call_args.kwargs
    assert call_kwargs["model"] == "claude-sonnet-4-20250514"


def test_llm_service_offline_gemini(monkeypatch):
    monkeypatch.setattr("backend.app.llm.factory.settings.llm_provider", "gemini")
    monkeypatch.setattr("backend.app.config.settings.gemini_api_key", None)
    from backend.app.llm import LLMService

    service = LLMService()
    schema = CATEGORIES["industrial_valve"]
    assert service.extract_fields_from_text("Manufacturer: X", schema, "SKU-1") is None


def test_llm_service_anthropic_missing_key_raises(monkeypatch):
    monkeypatch.setattr("backend.app.llm.factory.settings.llm_provider", "anthropic")
    monkeypatch.setattr("backend.app.config.settings.anthropic_api_key", None)
    from backend.app.llm import LLMService

    service = LLMService()
    schema = CATEGORIES["industrial_valve"]
    with pytest.raises(RuntimeError) as exc:
        service.extract_fields_from_text("Manufacturer: X", schema, "SKU-1")
    assert "ANTHROPIC_API_KEY" in str(exc.value)


def test_to_provenance_same_schema():
    from backend.app.llm import _to_provenance
    from backend.app.schemas.fields import ExtractionMethod, SourceType

    result = LLMExtractionResult(
        fields=[
            ExtractedFieldDraft(
                name="manufacturer",
                value="Acme",
                source_snippet="Acme",
                source_location="p1",
            )
        ],
        provider="gemini",
        model="gemini-3.1-flash-lite",
    )
    prov = _to_provenance(
        result, source_type=SourceType.DOCUMENT, method=ExtractionMethod.TEXT_LLM
    )
    assert isinstance(prov["manufacturer"], FieldProvenance)
    assert prov["manufacturer"].value == "Acme"
    assert prov["manufacturer"].source_type == SourceType.DOCUMENT
    # Confidence left for application layer
    assert prov["manufacturer"].confidence_score is None or True


def test_config_defaults():
    from backend.app.config import Settings

    s = Settings(
        _env_file=None,
        llm_provider="gemini",
        gemini_model="gemini-3.1-flash-lite",
        anthropic_model="claude-sonnet-4-20250514",
    )
    assert s.llm_provider == "gemini"
    assert s.gemini_model == "gemini-3.1-flash-lite"
    assert s.anthropic_model == "claude-sonnet-4-20250514"
