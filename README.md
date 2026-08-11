# Product Intelligence Copilot

Turn messy industrial product inputs (PDF, image, text, URL) into schema-validated catalog records with **computed confidence**, **cross-source conflicts**, **human review**, and **correction propagation**.

## Quick start (Windows)

```bat
cd "E:\Hackathon 2026\Unihack"
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python scripts\generate_samples.py
python scripts\run_batch.py
uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

In a second terminal:

```bat
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 — click **Load 20-product demo batch** (or use pre-run data) → Review → Dashboard.

Or run `scripts\start-dev.bat` to launch both processes.

## Quick start (Docker)

```bash
cp .env.example .env
docker compose up --build
```

- API: http://localhost:8000/health  
- UI: http://localhost:5173  

## Environment

Copy `.env.example` → `.env`:

| Variable | Purpose |
|----------|---------|
| `ANTHROPIC_API_KEY` | Claude structured extract + vision for images |
| `ANTHROPIC_MODEL` | Default `claude-sonnet-4-20250514` |
| `TAVILY_API_KEY` / `SERPAPI_API_KEY` | Live gap-fill search |
| `CORS_ORIGINS` | Comma-separated allowed origins |
| `APP_ENV` | `development` or `production` |
| `LOG_LEVEL` | `INFO` / `DEBUG` |

**Without keys:** labeled-text parsing + seeded conflict/gap stubs still run the full demo.

## Demo path (judges)

See [docs/DEMO.md](docs/DEMO.md). Signature moments:

1. **Won’t hallucinate** — `VALVE-SPARSE-001` missing fields stay **not found**
2. **Conflict** — `VALVE-CONFLICT-001` doc **250 psi** vs web **285 psi**
3. **Propagation** — edit `body_material` on `VALVE-A-001` (`WCB` → `WCC`) → apply to sibling template SKUs
4. **Scale** — Dashboard aggregates + gold-label match rate

## Architecture

```
Ingest (PDF/text/URL/image)
  → RAG-lite chunk retrieval
  → Schema-constrained extraction (+ VLM for images when keyed)
  → Computed confidence (method + agreement + validation + format)
  → Conflict detection (no silent merge)
  → Scoped gap-fill (≤2 web calls, missing required only)
  → Human review / bulk-approve / conflict resolve
  → Correction propagation (human-approved)
  → JSON/CSV export + batch dashboard
```

Confidence formula: [docs/CONFIDENCE.md](docs/CONFIDENCE.md)  
Q&A prep: [docs/QA.md](docs/QA.md)

## API highlights

| Endpoint | Purpose |
|----------|---------|
| `POST /api/ingest` | JSON text/URL ingest |
| `POST /api/ingest/upload` | PDF + image upload |
| `POST /api/batch/from-manifest` | Demo batch (reset + 20 SKUs) |
| `PATCH /api/products/{id}/fields/{field}` | Approve / edit / reject |
| `POST /api/products/{id}/conflicts/{field}/resolve` | Pick a conflict value |
| `POST /api/propagations/{id}` | Apply / dismiss propagation |
| `GET /api/dashboard` | Aggregate stats |
| `GET /api/export/csv` · `/json` | Catalog export |
| `GET /api/eval/match-rate` | Gold-label mini eval |
| `DELETE /api/reset` | Clear SQLite store |

## Verification

```bash
python scripts/smoke_test.py
python scripts/run_batch.py
```

Smoke covers E2E extract, conflict, sparse no-hallucination, propagation, and PDF path.

## Layout

```
backend/app/     FastAPI pipeline + SQLite
frontend/        React + Vite + Tailwind
data/samples/    Manifest, text, PDF fixtures
data/seeds/      Conflict + propagation seeds
data/eval/       Gold labels
scripts/         generate_samples, run_batch, smoke_test, start-dev
docs/            CONFIDENCE, DEMO, QA
```

## Production notes (hackathon-ready)

- SQLite with WAL; uploads capped via `MAX_UPLOAD_MB`
- Structured logging + global exception handler
- Lifespan startup initializes DB
- Intentionally **not** included (Tier 3): auth, multi-tenancy, knowledge graph, fine-tuning, open crawling
