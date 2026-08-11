# Q&A rehearsal

## How is this different from prompting an LLM with a template?

A raw prompt returns a single guess. We compute confidence from extraction method reliability, cross-source agreement, validation outcomes, and format match (see `docs/CONFIDENCE.md`). Every field carries `source_snippet` and `source_location`. Missing values stay **not found** — the gap-fill agent only runs for required gaps and tags `source: web` with review required.

## How do you know confidence scores are meaningful?

They are **heuristic composition**, not ML calibration. Demo: (1) table-parse / labeled text → High when validation passes; (2) `VALVE-CONFLICT-001` — agreement drops when doc ≠ web; (3) optional `/api/eval/match-rate` against `data/eval/gold_labels.json` for High-band field match count.

## Does this scale to 50k SKUs?

Batch dashboard proves throughput on 20+ SKUs. Gap-fill is capped at 1–2 searches per missing **required** field — no open crawl. Storage is SQLite/JSON files; export is catalog-ready JSON/CSV for PIM import.

## What if propagation is wrong?

Suggestions require explicit **Apply** in the UI; dismiss leaves other SKUs unchanged. Pattern match is on `source_template_id` + field + old value only.

## What if the LLM API is down?

Deterministic labeled-text parser + mock extractor still produce a reviewable record; fields are marked with lower method reliability. Seeded conflict/gap fixtures keep demo moments working. Judges see partial pipeline + human review queue, not fabricated High scores.

## What about images / scanned pages?

With `ANTHROPIC_API_KEY`, missing fields are filled via vision-LLM (`backend/app/services/vision.py`) and tagged `source: image` / `vision-LLM`. Without a key, images are noted in ingest text and left for review.

## RAG?

Parsed document text is chunked; keyword retrieval selects top sections per field group before structured extraction (`backend/app/services/retrieval.py`) — constrains context without a vector DB.
