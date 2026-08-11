#!/usr/bin/env python3
"""Smoke tests for hackathon demo pipeline."""
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.models.product import ProductInput
from backend.app.services.pipeline import run_pipeline
from backend.app.services.propagation import apply_propagation, find_propagation_candidates
from backend.app.services.storage import clear_all, init_db, save_product


async def test_text_e2e():
    text = (ROOT / "data/samples/text/valve_acmeflow_001.txt").read_text(encoding="utf-8")
    inp = ProductInput(sku="VALVE-A-001", category_id="industrial_valve", text=text)
    rec = await run_pipeline(inp)
    assert rec.fields["manufacturer"].value == "AcmeFlow Industries"
    assert rec.fields["manufacturer"].not_found is False
    assert rec.fields["manufacturer"].source_snippet
    assert rec.fields["manufacturer"].confidence_score.value in ("High", "Medium", "Low")
    assert rec.source_template_id == "acmeflow_valve_series_a"


async def test_conflict():
    text = (ROOT / "data/samples/text/valve_conflict_001.txt").read_text(encoding="utf-8")
    inp = ProductInput(sku="VALVE-CONFLICT-001", category_id="industrial_valve", text=text)
    rec = await run_pipeline(inp)
    assert len(rec.conflicts) >= 1
    assert any(c.field_name == "max_operating_pressure_psi" for c in rec.conflicts)


async def test_sparse_no_hallucination():
    text = (ROOT / "data/samples/text/valve_sparse_001.txt").read_text(encoding="utf-8")
    inp = ProductInput(sku="VALVE-SPARSE-001", category_id="industrial_valve", text=text)
    rec = await run_pipeline(inp)
    assert rec.fields["pressure_class"].not_found is True
    assert rec.fields["body_material"].not_found is True


async def test_propagation():
    init_db()
    clear_all()
    init_db()
    records = []
    for sku, fname in [
        ("VALVE-A-001", "valve_acmeflow_001.txt"),
        ("VALVE-A-002", "valve_acmeflow_002.txt"),
        ("VALVE-A-003", "valve_acmeflow_003.txt"),
    ]:
        text = (ROOT / "data/samples/text" / fname).read_text(encoding="utf-8")
        rec = await run_pipeline(
            ProductInput(
                sku=sku,
                category_id="industrial_valve",
                text=text,
                source_template_id="acmeflow_valve_series_a",
            )
        )
        save_product(rec)
        records.append(rec)

    source = records[0]
    suggestion = find_propagation_candidates(
        records, source.id, "body_material", source.fields["body_material"].value, "WCC"
    )
    assert suggestion is not None
    assert len(suggestion.candidate_product_ids) >= 2
    updated = apply_propagation(records, suggestion)
    for r in updated:
        if r.id in suggestion.candidate_product_ids:
            assert r.fields["body_material"].value == "WCC"


async def test_pdf_if_present():
    pdf = ROOT / "data/samples/pdf/valve_acmeflow_001.pdf"
    if not pdf.exists():
        print("skip pdf (generate_samples first)")
        return
    inp = ProductInput(
        sku="VALVE-PDF-001",
        category_id="industrial_valve",
        pdf_path=str(pdf.relative_to(ROOT)).replace("\\", "/"),
    )
    rec = await run_pipeline(inp)
    assert any(not f.not_found for f in rec.fields.values())


if __name__ == "__main__":
    asyncio.run(test_text_e2e())
    asyncio.run(test_conflict())
    asyncio.run(test_sparse_no_hallucination())
    asyncio.run(test_propagation())
    asyncio.run(test_pdf_if_present())
    print("smoke ok")
