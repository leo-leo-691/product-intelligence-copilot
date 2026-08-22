# Product Intelligence Copilot — Demo Script (5–7 min)

**Prep (before stage):**

```bash
python scripts/generate_samples.py
python scripts/run_batch.py
# API + UI running
```

Or click **Load 26-product demo batch** in the UI.

1. **Problem (10s)** — Industrial catalogs still depend on manual transcription from PDFs; generic LLM JSON has no provenance or trust layer.
2. **Clean ingest (60s)** — Open Review on `VALVE-A-001`. Show confidence badges; expand citation + confidence reasoning hover/JSON.
3. **Won’t hallucinate (30s)** — Open `VALVE-SPARSE-001`: `pressure_class` / `body_material` show **not found** / Low — no invented values.
4. **Conflict (30s)** — Open `VALVE-CONFLICT-001`: document **250 psi** vs web **285 psi** side by side; optionally click **Use this value** to resolve (human-in-the-loop).
5. **Propagation (60s)** — On `VALVE-A-001`, edit `body_material` from `WCB` → `WCC` → **Save edit**; accept propagation modal for sibling `acmeflow_valve_series_a` SKUs.
6. **HITL (20s)** — **Bulk-approve High** on a clean valve; optionally **Approve record**.
7. **Scale (30s)** — Dashboard: N products, % High/Medium/Low, conflicts, propagations, time saved, gold-label match rate.
8. **Architecture (30s)** — Ingest → RAG-lite chunks → extract (+ VLM) → computed confidence → validation/conflicts → scoped gap-fill → review → propagation.
9. **Close (20s)** — Roadmap: category inference, outliers, catalog knowledge graph.

**Backup:** Keep a screen recording of the above if live APIs flake. Offline mode (no API keys) still demos all signature moments via seeded fixtures.
