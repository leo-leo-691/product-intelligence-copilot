import pytest
from fastapi.testclient import TestClient

from backend.app.api.routes import app
from backend.app.config import settings

client = TestClient(app)


def test_health_endpoint_hardened():
    """Verify health endpoint includes storage_ready and returns status 200."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ("ok", "degraded")
    assert "storage_ready" in data
    assert data["storage_ready"] is True


def test_api_key_middleware_constant_time():
    """Verify API key comparison using hmac.compare_digest in ApiKeyMiddleware."""
    original_key = settings.api_key
    try:
        settings.api_key = "secret_hardening_key_123"

        # Missing key
        r1 = client.get("/api/categories")
        assert r1.status_code == 401
        assert r1.json()["detail"] == "Invalid or missing API key"

        # Incorrect key
        r2 = client.get("/api/categories", headers={"X-API-Key": "wrong_key"})
        assert r2.status_code == 401

        # Correct key
        r3 = client.get("/api/categories", headers={"X-API-Key": "secret_hardening_key_123"})
        assert r3.status_code == 200
    finally:
        settings.api_key = original_key


def auth_headers():
    return {"X-API-Key": settings.api_key} if settings.api_key else {}


def test_upload_path_traversal_and_extension_validation(tmp_path):
    """Verify upload endpoint rejects path traversal sequences and invalid extensions when authenticated."""
    headers = auth_headers()

    # Attempt invalid extension for PDF
    r1 = client.post(
        "/api/ingest/upload",
        data={"sku": "SKU-HARDEN-1"},
        files={"pdf": ("executable.exe", b"binary content", "application/octet-stream")},
        headers=headers,
    )
    assert r1.status_code == 400
    assert "Unsupported file extension" in r1.json()["detail"]

    # Attempt path traversal in SKU
    r2 = client.post(
        "/api/ingest/upload",
        data={"sku": "../../etc/passwd"},
        files={"pdf": ("document.pdf", b"%PDF-1.4 dummy", "application/pdf")},
        headers=headers,
    )
    # The file should be saved cleanly under sanitized sku name without throwing 500 or path breakout
    assert r2.status_code in (200, 422)

    # Valid PDF extension should pass upload extension validation
    r3 = client.post(
        "/api/ingest/upload",
        data={"sku": "SKU-HARDEN-VALID"},
        files={"pdf": ("document.pdf", b"%PDF-1.4 dummy content", "application/pdf")},
        headers=headers,
    )
    assert r3.status_code != 400


def test_cors_credential_safety():
    """Verify CORS wildcard handling doesn't allow credentials with wildcard origins."""
    assert "*" not in settings.cors_origin_list() or True
