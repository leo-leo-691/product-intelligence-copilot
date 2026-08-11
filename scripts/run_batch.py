#!/usr/bin/env python3
"""Pre-run batch ingestion from data/samples/manifest.json (clears prior demo data)."""
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.logging_config import setup_logging
from backend.app.models.product import BatchRun, ProductInput
from backend.app.services.pipeline import run_pipeline
from backend.app.services.storage import clear_all, compute_dashboard, init_db, save_batch, save_product


async def main():
    setup_logging()
    init_db()
    clear_all()
    init_db()

    manifest_path = ROOT / "data" / "samples" / "manifest.json"
    if not manifest_path.exists():
        print("manifest missing — run scripts/generate_samples.py first")
        sys.exit(1)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    batch = BatchRun(name="demo-batch")
    save_batch(batch)

    for item in manifest["products"]:
        text_path = ROOT / "data" / "samples" / item["text_file"]
        text = text_path.read_text(encoding="utf-8") if text_path.exists() else ""
        pdf_path = None
        if item.get("pdf_file"):
            pdf_path = str((ROOT / "data" / "samples" / item["pdf_file"]).relative_to(ROOT)).replace(
                "\\", "/"
            )
        inp = ProductInput(
            sku=item["sku"],
            category_id=item["category_id"],
            text=text,
            pdf_path=pdf_path,
            source_template_id=item.get("source_template_id"),
        )
        record = await run_pipeline(inp, batch_id=batch.id)
        save_product(record)
        batch.product_ids.append(record.id)
        print(f"Processed {item['sku']} -> conflicts={len(record.conflicts)}")

    save_batch(batch)
    stats = compute_dashboard(batch.id)
    print(f"Batch {batch.id} complete with {len(batch.product_ids)} products")
    print(
        f"Dashboard: high={stats.high_confidence_pct}% conflicts={stats.conflicts_count} "
        f"fields={stats.total_fields}"
    )


if __name__ == "__main__":
    asyncio.run(main())
