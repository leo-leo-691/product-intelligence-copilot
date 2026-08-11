# Product Intelligence Copilot

Turn messy industrial product inputs (PDF, image, text, URL) into schema-validated catalog records with **computed confidence**, **conflicts**, **HITL review**, **correction propagation**, **outliers**, **multi-language**, and a **lightweight catalog knowledge graph**.

## Deploy in 3 steps

1. Copy env template and fill secrets:

```bash
cp .env.example .env
# Edit .env — at minimum for production:
# API_KEY=<strong-random>
# APP_ENV=production
# CORS_ORIGINS=https://your-frontend.example
# ANTHROPIC_API_KEY=...   (optional but enables LLM/VLM/translate)
# TAVILY_API_KEY=...      (optional live gap-fill)
```

2. Run with Docker:

```bash
docker compose up --build -d
```

- API: `http://localhost:8000/health`
- UI: `http://localhost:5173`

3. Or run locally:

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
pip install -r requirements.txt
python scripts/generate_samples.py
python scripts/run_batch.py
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
```

```bash
cd frontend && npm install && npm run dev
```

When `API_KEY` is set, send header `X-API-Key: <value>` on `/api/*` (health stays public).

## Feature coverage (Tiers 1–3)

| Area | Status |
|------|--------|
| PDF / image / text / URL ingest | Yes — PDF tables + **page rasterization → VLM** when text is sparse |
| 5 category schemas | Valve, Bearing, Sensor, **Motor**, **Fastener** |
| Provenance + computed confidence | Yes |
| Gap-fill (capped) + conflicts | Yes |
| HITL + bulk-approve + export CSV/JSON | Yes |
| Batch dashboard (26 sample SKUs) | Yes |
| Category auto-infer | Yes (`auto` on ingest) |
| Outlier consistency check | Yes |
| Correction log + propagation | Yes (no model fine-tune — corrections logged for learning) |
| Multi-language detect + optional translate | Yes |
| Lightweight knowledge graph | Yes (`GET /api/kg`) |
| Capped same-host crawl | Yes (max pages via env) |
| API key auth for deploy | Yes (`API_KEY`) |
| Model fine-tuning | **Not included** — use correction log + prompts instead |

## Env reference

See [`.env.example`](.env.example) for every knob (`PDF_RASTER_MAX_PAGES`, `GAP_FILL_MAX_CALLS`, `CRAWL_MAX_PAGES`, `KG_ENABLED`, etc.).

## Demo

See [docs/DEMO.md](docs/DEMO.md). Signature moments: sparse not-found, conflict 250 vs 285 psi, propagation WCB→WCC, dashboard aggregates.

## Verify

```bash
python scripts/smoke_test.py
python scripts/run_batch.py
```
