import pytest
from fastapi.testclient import TestClient
from backend.app.api.routes import app
from backend.app.config import settings

client = TestClient(app)


def auth_headers():
    return {"X-API-Key": settings.api_key} if settings.api_key else {}


def test_import_csv_metadata_success(tmp_path):
    """Test that importing a valid CSV returns correct metadata (row count, columns, headers)."""
    csv_content = b"Mfg_Part_Num,Part_Desc,Part_Manuf,Extra_Col\nMPN001,Description 1,Manufacturer A,Extra 1\nMPN002,Description 2,Manufacturer B,Extra 2\n"

    headers = auth_headers()
    response = client.post(
        "/api/unihack/import",
        params={"kind": "input"},
        files={"file": ("test_catalog.csv", csv_content, "text/csv")},
        headers=headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert "metadata" in data
    meta = data["metadata"]
    assert meta["row_count"] == 2
    assert meta["column_count"] == 4
    assert meta["headers"] == ["Mfg_Part_Num", "Part_Desc", "Part_Manuf", "Extra_Col"]


def test_import_xlsx_metadata_success():
    """Test that importing a valid XLSX returns correct metadata (row count, columns, headers)."""
    from openpyxl import Workbook
    import io

    wb = Workbook()
    ws = wb.active
    ws.title = "Catalog"
    ws.append(["Mfg_Part_Num", "Part_Desc", "Part_Manuf", "Extra_Col"])
    ws.append(["MPN001", "Description 1", "Manufacturer A", "Extra 1"])
    ws.append(["MPN002", "Description 2", "Manufacturer B", "Extra 2"])

    buf = io.BytesIO()
    wb.save(buf)
    xlsx_content = buf.getvalue()

    headers = auth_headers()
    response = client.post(
        "/api/unihack/import",
        params={"kind": "input"},
        files={"file": ("test_catalog.xlsx", xlsx_content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert "metadata" in data
    meta = data["metadata"]
    assert meta["row_count"] == 2
    assert meta["column_count"] == 4
    assert meta["headers"] == ["Mfg_Part_Num", "Part_Desc", "Part_Manuf", "Extra_Col"]


def test_import_csv_metadata_reordered_and_extra_and_blank():
    """Test that reordered, extra, and blank columns are correctly parsed and returned."""
    # Column order: Extra_Col, Part_Manuf (empty in second row), Mfg_Part_Num, Part_Desc
    csv_content = b"Extra_Col,Part_Manuf,Mfg_Part_Num,Part_Desc\nExtra 1,Manufacturer A,MPN001,Description 1\nExtra 2,,MPN002,Description 2\n"

    headers = auth_headers()
    response = client.post(
        "/api/unihack/import",
        params={"kind": "input"},
        files={"file": ("test_catalog.csv", csv_content, "text/csv")},
        headers=headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert "metadata" in data
    meta = data["metadata"]
    assert meta["row_count"] == 2
    assert meta["column_count"] == 4
    assert meta["headers"] == ["Extra_Col", "Part_Manuf", "Mfg_Part_Num", "Part_Desc"]


def test_import_invalid_csv_handling():
    """Test that an invalid/unparseable file returns HTTP 400 and actionable error detail."""
    headers = auth_headers()
    # Sending a binary or corrupted payload that ingest_input_workbook won't parse properly
    response = client.post(
        "/api/unihack/import",
        params={"kind": "input"},
        files={"file": ("corrupted.xlsx", b"invalid excel signature content", "application/vnd.ms-excel")},
        headers=headers,
    )

    assert response.status_code == 400
    data = response.json()
    assert "detail" in data
    assert "Invalid catalog workbook" in data["detail"]


def test_import_auth_protection():
    """Verify that /api/unihack/import is protected by ApiKeyMiddleware when settings.api_key is active."""
    original_key = settings.api_key
    try:
        settings.api_key = "secure_test_key_unihack"

        # Unauthorized request
        response = client.post(
            "/api/unihack/import",
            params={"kind": "input"},
            files={"file": ("test.csv", b"col1,col2\n1,2", "text/csv")},
        )
        assert response.status_code == 401

        # Authorized request
        response = client.post(
            "/api/unihack/import",
            params={"kind": "input"},
            files={"file": ("test.csv", b"col1,col2\n1,2", "text/csv")},
            headers={"X-API-Key": "secure_test_key_unihack"},
        )
        assert response.status_code == 200
    finally:
        settings.api_key = original_key
