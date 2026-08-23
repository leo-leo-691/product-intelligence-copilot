"""UniHack evaluation tests — dynamic rows/columns, exact headers, no invented values."""

from __future__ import annotations

from pathlib import Path

import pytest
from openpyxl import Workbook, load_workbook

from backend.app.unihack.constants import INPUT_ALIASES
from backend.app.unihack.evaluate import evaluate_predictions
from backend.app.unihack.export import write_csv, write_xlsx
from backend.app.unihack.ingest import ingest_input_workbook
from backend.app.unihack.jobs import create_job, run_job
from backend.app.unihack.normalize import clean_input
from backend.app.unihack.official import EXPECTED_OUTPUT_CACHE
from backend.app.unihack.pipeline import process_row
from backend.app.unihack.schema import empty_row, load_delivery_headers, validate_headers

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


def _xlsx(path: Path, headers: list[str], rows: list[list[object]], sheet: str = "Sheet1") -> Path:
    wb = Workbook()
    ws = wb.active
    ws.title = sheet
    ws.append(headers)
    for row in rows:
        ws.append(row)
    wb.save(path)
    return path


def _csv(path: Path, headers: list[str], rows: list[list[object]]) -> Path:
    import csv

    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(headers)
        w.writerows(rows)
    return path


def test_placeholders_are_empty():
    assert clean_input("-- Unbranded --") == ""
    assert clean_input("-- No Unilog Brand --") == ""
    assert clean_input("-- No DIB Brand --") == ""
    assert clean_input("Acme") == "Acme"


def test_ingest_dynamic_row_count(tmp_path: Path):
    headers = list(INPUT_ALIASES)
    rows = [[f"SKU-{i}", f"desc {i}", "Acme", "", "", "Acme"] for i in range(7)]
    data = ingest_input_workbook(_xlsx(tmp_path / "in.xlsx", headers, rows))
    assert data["row_count"] == 7


def test_ingest_dynamic_and_unknown_columns(tmp_path: Path):
    headers = ["Mfg_Part_Num", "Part_Desc", "Custom_Col", "E1_Brand"]
    data = ingest_input_workbook(
        _xlsx(tmp_path / "in.xlsx", headers, [["A1", "valve", "keep-me", "-- Unbranded --"]])
    )
    assert data["row_count"] == 1
    row = data["rows"][0]
    assert row["Custom_Col"] == "keep-me"
    assert row["E1_Brand"] == ""
    assert "Unilog_Brand" not in headers
    assert row.get("Unilog_Brand", "") == ""


def test_ingest_missing_input_values(tmp_path: Path):
    headers = ["Mfg_Part_Num", "Part_Desc"]
    data = ingest_input_workbook(_xlsx(tmp_path / "in.xlsx", headers, [["SKU", ""]]))
    assert data["rows"][0]["Part_Desc"] == ""
    assert data["rows"][0]["Mfg_Part_Num"] == "SKU"


def test_official_expected_output_headers_loaded():
    if not EXPECTED_OUTPUT_CACHE.exists():
        pytest.skip("official expected output CSV not cached")
    loaded = load_delivery_headers(EXPECTED_OUTPUT_CACHE)
    assert loaded["header_count"] > 0
    assert loaded["headers"][0] == "MFR URL"
    assert "Mfg_Part_Num" in loaded["headers"]
    check = validate_headers(loaded["headers"], loaded["headers"])
    assert check["valid"] is True


def test_process_row_emits_every_header_and_does_not_hallucinate(tmp_path: Path):
    headers = ["MFR URL", "Mfg_Part_Num", "Part_Desc", "Mystery_Spec", "Part_Manuf"]
    raw = {
        "row_number": 1,
        "Mfg_Part_Num": "ABC-9",
        "Part_Desc": "2 in steel elbow",
        "Part_Manuf": "UnknownMfrXYZ",
    }
    out = process_row(raw, headers, manufacturer_path=tmp_path / "missing.xlsx")
    assert list(out["delivery"].keys()) == headers
    assert out["delivery"]["Mfg_Part_Num"] == "ABC-9"
    assert out["delivery"]["Mystery_Spec"] == ""
    assert out["delivery"]["MFR URL"] == ""
    assert "titanium" not in str(out["delivery"]).lower()


def test_evaluation_exact_match_and_missing():
    headers = ["Mfg_Part_Num", "Color"]
    predicted = [{"Mfg_Part_Num": "A1", "Color": "Red"}]
    expected = [{"mfg_part_num": "A1", "expected": {"Mfg_Part_Num": "A1", "Color": "Red"}}]
    metrics = evaluate_predictions(predicted, expected, headers)
    assert metrics["fields_correct"] == 2
    assert metrics["field_level_accuracy_pct"] == 100.0
    predicted2 = [{"Mfg_Part_Num": "A1", "Color": ""}]
    metrics2 = evaluate_predictions(predicted2, expected, headers)
    assert metrics2["fields_missing"] >= 1


def test_csv_and_xlsx_preserve_exact_headers():
    headers = ["MFR URL", "Odd Header / 2", "Mfg_Part_Num"]
    rows = [empty_row(headers)]
    rows[0]["Mfg_Part_Num"] = "Z1"
    csv_text = write_csv(headers, rows).decode("utf-8-sig")
    assert csv_text.splitlines()[0] == "MFR URL,Odd Header / 2,Mfg_Part_Num"
    xlsx = write_xlsx(headers, rows)
    dest = Path("_tmp_unihack_hdr.xlsx")
    try:
        dest.write_bytes(xlsx)
        wb = load_workbook(dest)
        got = [c.value for c in next(wb.active.iter_rows(min_row=1, max_row=1))]
        assert got == headers
    finally:
        dest.unlink(missing_ok=True)


def test_job_row_failure_isolation(tmp_path: Path, monkeypatch):
    headers = ["Mfg_Part_Num", "Part_Desc"]
    schema = _csv(tmp_path / "schema.csv", headers, [])
    inp = _xlsx(
        tmp_path / "in.xlsx",
        ["Mfg_Part_Num", "Part_Desc"],
        [["OK-1", "valve"], ["OK-2", "sensor"]],
    )
    from backend.app.unihack import jobs as jobs_mod
    from backend.app.unihack.pipeline import process_row as real

    def flaky(raw, hdrs, **kwargs):
        if raw.get("Mfg_Part_Num") == "OK-1":
            raise RuntimeError("boom")
        return real(raw, hdrs, **kwargs)

    monkeypatch.setattr(jobs_mod, "process_row", flaky)
    monkeypatch.setattr(jobs_mod, "find_file", lambda kind: inp if kind == "input_1000" else None)
    monkeypatch.setattr(jobs_mod, "find_delivery_schema", lambda: schema)
    monkeypatch.setattr(jobs_mod, "ensure_expected_output", lambda: schema)
    monkeypatch.setattr(jobs_mod, "ensure_sample_input", lambda: inp)
    job = create_job(input_path=inp, evaluate=False)
    finished = run_job(job["id"])
    assert finished["status"] == "PARTIAL"
    assert finished["progress"]["successful"] == 1
    assert finished["progress"]["failed"] == 1
    from backend.app.unihack.store import list_rows

    rows = list_rows(finished["id"])
    failed = next(r for r in rows if r.get("status") == "error")
    assert list(failed["delivery"].keys()) == headers


def test_output_generation_blank_unknown(tmp_path: Path):
    headers = ["Mfg_Part_Num", "UPC", "Country Of Origin"]
    raw = {"row_number": 1, "Mfg_Part_Num": "N1", "Part_Desc": "nut"}
    out = process_row(raw, headers)
    assert out["delivery"]["UPC"] == ""
    assert out["delivery"]["Country Of Origin"] == ""
    assert out["delivery"]["Mfg_Part_Num"] == "N1"
