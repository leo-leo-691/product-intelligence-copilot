# Product Intelligence Copilot

**Turn messy industrial product inputs into schema-validated, traceable, commerce-ready catalog records.**

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-green.svg)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-18-61dafb.svg)](https://react.dev/)

> Built for **Unihack 2026** — AI-powered product intelligence for industrial B2B commerce.

---

## The problem

Industrial distributors and manufacturers still rely on manual transcription from PDF datasheets, scanned spec sheets, and supplier portals. Generic LLM prompts return JSON with no provenance, no confidence layer, and a tendency to **invent** missing values. Catalog teams cannot trust or audit those outputs at scale.

## Our solution

**Product Intelligence Copilot** ingests PDFs, images, raw text, and URLs, then runs them through a structured extraction pipeline that produces:

- **Category-specific schemas** (Valve, Bearing, Sensor, Motor, Fastener)
- **Per-field provenance** — value, source snippet, source location, extraction method
- **Computed confidence** — application-side scoring, not raw LLM self-certainty
- **Conflict detection** when document and web sources disagree
- **Human-in-the-loop review** with bulk-approve, edit, and propagation
- **Export-ready CSV/JSON** for PIM / ERP import

The system **does not hallucinate missing required fields**. Gap-fill via Tavily or SerpAPI only runs for genuinely missing required fields and tags results `source: web` with review required.

---

## Why judges should care

| Differentiator | What it means |
|----------------|---------------|
| **Trust layer** | Every field has provenance + computed confidence reasoning — not just model output |
| **Won't invent** | `VALVE-SPARSE-001` demo: missing fields stay **not found** / Low confidence |
| **Conflict surfacing** | `VALVE-CONFLICT-001`: document **250 psi** vs web **285 psi** shown side-by-side |
| **Correction propagation** | Edit `body_material` WCB → WCC on one SKU; siblings in same template get suggestions |
| **Offline demo** | Full pipeline works without API keys via labeled-text parser + seeded fixtures |
| **Interchangeable LLMs** | Gemini 3.1 Flash-Lite (default) or Claude Sonnet 4 behind one abstraction |
| **Scale signal** | 26-sample batch dashboard with aggregates, match rate, and export |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Ingest (UI / API)                        │
│              PDF · Image · Text · URL · File upload             │
└────────────────────────────┬────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────┐
│                     Ingestion & preprocessing                   │
│   PDF tables · sparse-page rasterization · URL crawl (capped)   │
│         Multi-language detect · optional LLM translate          │
└────────────────────────────┬────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────┐
│                    Category inference (auto)                    │
│              Keyword heuristics → optional LLM refine           │
└────────────────────────────┬────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────┐
│                      Extraction engine                          │
│   RAG-lite chunk retrieval → LLM structured extract (+ VLM)     │
│              Same Pydantic schemas regardless of provider       │
└────────────────────────────┬────────────────────────────────────┘
                             │
          ┌──────────────────┼──────────────────┐
          │                  │                  │
┌─────────▼────────┐ ┌───────▼───────┐ ┌───────▼────────┐
│  LLM layer       │ │  Search layer │ │  Validation    │
│  Gemini / Claude │ │  Tavily       │ │  Pydantic +    │
│  (LLMService)    │ │  SerpAPI      │ │  rules/units   │
└─────────┬────────┘ └───────┬───────┘ └───────┬────────┘
          │                  │                  │
          └──────────────────┼──────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────┐
│   Confidence · Conflicts · Outliers · Knowledge graph · HITL    │
│              Review UI · Propagation · CSV/JSON export          │
└─────────────────────────────────────────────────────────────────┘
```

**LLM abstraction** — business logic never instantiates provider SDKs directly:

```
LLMService → get_llm_provider() → GeminiProvider | ClaudeProvider
                                         ↓
                              LLMExtractionResult → FieldProvenance
```

Tavily and SerpAPI remain a separate search layer for web gap-fill only.

---

## Tech stack

| Layer | Technologies |
|-------|--------------|
| **Backend** | Python 3.12, FastAPI, Pydantic v2, SQLite |
| **Frontend** | React 18, TypeScript, Vite, Tailwind CSS |
| **LLM** | Google Gemini (`google-genai`) · Anthropic Claude (`anthropic`) |
| **Search** | Tavily, SerpAPI (optional gap-fill) |
| **Ingest** | pdfplumber, pypdfium2, BeautifulSoup |
| **Deploy** | Docker Compose, optional `API_KEY` auth |

---

## Quick start (judges — ~5 minutes)

### Option A: Offline demo (no API keys required)

```bash
git clone https://github.com/leo-leo-691/product-intelligence-copilot.git
cd Unihack

python -m venv .venv
# Windows:  .venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate

pip install -r requirements.txt
python scripts/generate_samples.py
python scripts/run_batch.py

# Terminal 1 — API (use 8001 if 8000 is busy on Windows)
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000

# Terminal 2 — UI
cd frontend && npm install && npm run dev
```

Open **http://localhost:5173** → go to **Review** or **Dashboard**.

Click **Load 20-product demo batch** in the UI, or use the pre-seeded batch from `run_batch.py`.

### Option B: Docker

```bash
cp .env.example .env   # leave keys blank for offline mode
docker compose up --build -d
```

- API health: `http://localhost:8000/health`
- UI: `http://localhost:5173`

### Option C: With live LLM + search

```bash
cp .env.example .env
```

Edit `.env` (never commit this file):

```env
LLM_PROVIDER=gemini
GEMINI_API_KEY=<your-key>
GEMINI_MODEL=gemini-3.1-flash-lite

# Optional — web gap-fill for missing required fields
TAVILY_API_KEY=<your-key>
# or SERPAPI_API_KEY=<your-key>
```

Restart the API after changing env vars.

---

## Demo script for judges (5–7 min)

Full walkthrough: [`docs/DEMO.md`](docs/DEMO.md)

| Step | SKU / action | What to show |
|------|--------------|--------------|
| 1 | `VALVE-A-001` | Clean ingest — confidence badges, provenance snippets |
| 2 | `VALVE-SPARSE-001` | Missing fields stay **not found** — no hallucination |
| 3 | `VALVE-CONFLICT-001` | Document vs web pressure conflict — pick a value (HITL) |
| 4 | `VALVE-A-001` edit | Change `body_material` WCB → WCC → accept propagation |
| 5 | Review | Bulk-approve High-confidence fields |
| 6 | Dashboard | Batch stats, conflict count, export CSV/JSON |

**Signature moments:** sparse not-found · conflict 250 vs 285 psi · propagation WCB→WCC · dashboard aggregates.

---

## Feature coverage

| Area | Status |
|------|--------|
| PDF / image / text / URL ingest | PDF tables + page rasterization → VLM when text is sparse |
| 5 category schemas | Valve, Bearing, Sensor, Motor, Fastener |
| Provenance + computed confidence | Per-field value, snippet, location, method, reasoning |
| Gap-fill (capped) + conflicts | Tavily/SerpAPI; conflicts never auto-resolved |
| HITL + bulk-approve + export | CSV and JSON export for approved records |
| Batch dashboard | 26 sample SKUs in `data/samples/manifest.json` |
| Category auto-infer | Set `category_id=auto` on ingest |
| Outlier consistency check | Z-score vs category peers |
| Correction log + propagation | Template-scoped sibling suggestions |
| Multi-language detect + translate | Heuristic detect; optional LLM translate |
| Lightweight knowledge graph | `GET /api/kg` |
| Capped same-host crawl | Configurable via `CRAWL_MAX_PAGES` |
| API key auth | Optional `API_KEY` header for `/api/*` |
| Interchangeable LLM providers | Gemini (default) or Anthropic via `LLM_PROVIDER` |

---

## LLM providers

| Provider | `LLM_PROVIDER` | Model env | Default model |
|----------|----------------|-----------|---------------|
| **Google Gemini** (default) | `gemini` | `GEMINI_MODEL` | `gemini-3.1-flash-lite` |
| **Anthropic Claude** | `anthropic` | `ANTHROPIC_MODEL` | `claude-sonnet-4-20250514` |

```env
LLM_PROVIDER=gemini          # or anthropic
GEMINI_API_KEY=
GEMINI_MODEL=gemini-3.1-flash-lite
ANTHROPIC_API_KEY=
ANTHROPIC_MODEL=claude-sonnet-4-20250514
```

- **No Gemini key:** falls back to labeled-text / offline demo extraction (judges can run without keys).
- **Anthropic selected without key:** clear configuration error (no silent fallback).
- **Confidence:** always computed by the application — never taken from model self-scores.

---

## Confidence scoring

Confidence is a weighted blend of extraction-method reliability, cross-source agreement, validation outcome, and format match.

```
raw = 0.35 × method_reliability
    + 0.25 × cross_source_agreement
    + 0.25 × validation_score
    + 0.15 × format_match
```

| Band | Rule |
|------|------|
| **High** | `raw ≥ 0.75` and validation passed and field found |
| **Medium** | `raw ≥ 0.45` |
| **Low** | otherwise, or not found / validation failed |

Details: [`docs/CONFIDENCE.md`](docs/CONFIDENCE.md)

---

## Project structure

```
Unihack/
├── backend/
│   ├── app/
│   │   ├── api/           # FastAPI routes
│   │   ├── llm/           # Gemini + Claude provider abstraction
│   │   ├── models/        # ProductRecord, ProductInput
│   │   ├── schemas/       # Category schemas + FieldProvenance
│   │   └── services/      # Pipeline, ingest, extract, gap-fill, etc.
│   └── tests/             # Provider unit tests (mocked APIs)
├── frontend/
│   └── src/
│       ├── pages/         # Upload, Review, Dashboard
│       └── components/    # ConfidenceStamp, RoutingTag
├── data/
│   └── samples/           # 26 demo SKUs (text + PDF fixtures)
├── docs/
│   ├── DEMO.md            # Judge demo script
│   ├── CONFIDENCE.md      # Scoring methodology
│   └── QA.md              # Anticipated judge Q&A
├── scripts/
│   ├── generate_samples.py
│   ├── run_batch.py
│   └── smoke_test.py
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── .env.example           # Template only — copy to .env locally
```

---

## API overview

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Service status, LLM provider, search config |
| `GET` | `/api/categories` | List category schemas |
| `POST` | `/api/ingest` | Ingest from JSON body (text, URL, metadata) |
| `POST` | `/api/ingest/upload` | Upload PDF / image / text file |
| `GET` | `/api/products` | List processed products |
| `GET` | `/api/products/{id}` | Single product with fields + conflicts |
| `PATCH` | `/api/products/{id}/fields/{name}` | Human edit + propagation trigger |
| `POST` | `/api/products/{id}/conflicts/{name}/resolve` | Resolve a conflict |
| `POST` | `/api/products/{id}/bulk-approve-high` | Approve all High-confidence fields |
| `POST` | `/api/batch/from-manifest` | Run demo batch from manifest |
| `GET` | `/api/dashboard` | Batch aggregates |
| `GET` | `/api/export/json` | Export approved records (JSON) |
| `GET` | `/api/export/csv` | Export approved records (CSV) |
| `GET` | `/api/kg` | Knowledge graph summary |
| `GET` | `/api/eval/match-rate` | Gold-label match rate (demo eval) |

When `API_KEY` is set, send header `X-API-Key: <value>` on `/api/*` routes. `/health` stays public.

Interactive docs (when API is running): `http://localhost:8000/docs`

---

## Environment variables

Copy [`.env.example`](.env.example) to `.env` locally. **Never commit `.env`.**

| Variable | Purpose | Default |
|----------|---------|---------|
| `LLM_PROVIDER` | `gemini` or `anthropic` | `gemini` |
| `GEMINI_API_KEY` | Google Gemini API key | *(empty)* |
| `GEMINI_MODEL` | Gemini model ID | `gemini-3.1-flash-lite` |
| `ANTHROPIC_API_KEY` | Anthropic API key | *(empty)* |
| `ANTHROPIC_MODEL` | Claude model ID | `claude-sonnet-4-20250514` |
| `TAVILY_API_KEY` | Tavily search (gap-fill) | *(empty)* |
| `SERPAPI_API_KEY` | SerpAPI search (gap-fill) | *(empty)* |
| `API_KEY` | Optional deploy auth | *(empty)* |
| `GAP_FILL_MAX_CALLS` | Max web searches per product | `2` |
| `CRAWL_MAX_PAGES` | Max pages crawled per URL | `3` |
| `PDF_RASTER_MAX_PAGES` | Max PDF pages rasterized for VLM | `3` |

Full list: [`.env.example`](.env.example)

---

## Testing & verification

```bash
# End-to-end smoke tests (offline, no API keys)
python scripts/smoke_test.py

# Load 26-sample demo batch
python scripts/run_batch.py

# LLM provider unit tests (mocked — no real API calls)
python -m pytest backend/tests/test_llm_providers.py -v

# Frontend production build
cd frontend && npm run build
```

Smoke tests cover: clean extraction, conflict detection, sparse no-hallucination, propagation, and dashboard export.

---

## Documentation

| Doc | Contents |
|-----|----------|
| [`docs/DEMO.md`](docs/DEMO.md) | Step-by-step judge demo script |
| [`docs/CONFIDENCE.md`](docs/CONFIDENCE.md) | Confidence formula and method weights |
| [`docs/QA.md`](docs/QA.md) | Anticipated judge questions and answers |

---

## Team

<!-- Update with your team details before submission -->

| Name | Role |
|------|------|
| *Your name* | *Role* |
| *Teammate* | *Role* |

**Event:** Unihack 2026  
**Repository:** `<your-github-repo-url>`

---

## Security notes

- API keys are read from environment variables only — never hard-coded or logged.
- `.env` is gitignored; `.env.example` contains placeholders only.
- Do not commit real credentials to this repository.

---

## License

Copyright (c) 2026 Product Intelligence Copilot Team

This project is licensed under the MIT License.