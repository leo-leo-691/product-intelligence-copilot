# Product Intelligence Copilot — Master Build Spec

## The Idea (One Line)

An AI system that turns messy, incomplete industrial product data (PDFs, images, raw text, URLs) into schema-validated, commerce-ready product records — where every field is traceable to a source, scored with a real (not cosmetic) confidence methodology, cross-checked for conflicts across sources, gap-filled by an agent when missing, reviewed by a human in one clean screen, and where corrections propagate automatically to similar products in the catalog.

**The single sentence that should be in every judge's head after your demo:**
"It doesn't just extract data — it knows what it doesn't know, tells you why, and gets smarter every time a human corrects it."

---

## Why This Wins (Not Just Passes)

Most teams will build: PDF → LLM → JSON. That's necessary but not sufficient. What makes this a winner:

1. **Real confidence scoring** — not `LLM says 0.85`, but a computed score from extraction method + cross-source agreement + validation pass/fail.
2. **Conflict detection** — when document and web disagree, the system surfaces both, doesn't silently pick one.
3. **Won't-hallucinate guarantee** — missing data is labeled "not found," never invented.
4. **The surprise moment: correction propagation** — when a human fixes one field, the system finds other products with the same source pattern and proactively suggests the same fix. This is the moment that separates you from every other "extraction pipeline" team.
5. **Batch scale proof** — not a single cherry-picked demo, a dashboard across 20-30 products with real aggregate stats.

---

## FULL FEATURE LIST

### TIER 1 — Core (must-build, non-negotiable)

**1. Multi-format ingestion**
- Accepts: PDF datasheet, product image(s), raw pasted text, URL
- PDF → text + table extraction (`unstructured` / `pdfplumber`)
- PDF page rasterization → image fallback for scanned/low-quality pages
- Basic web page fetch + text extraction for URL input

**2. Category-specific structured schemas**
- Fixed JSON schema per category (build 3-5: e.g. Industrial Valve, Bearing, Sensor, Motor, Fastener)
- Each field defined with: name, type, unit (if applicable), required/optional flag
- Pydantic (or JSON Schema) validation — every output must conform before being marked "complete"

**3. Extraction engine with per-field provenance**
- LLM structured/tool-use extraction from parsed text, constrained to the schema
- VLM pass on images/scanned tables to catch fields text extraction misses
- Every field carries:
  - `value`
  - `confidence_score` (see methodology below — not a raw LLM guess)
  - `source_type`: document | image | web
  - `source_snippet`: exact text/region the value came from
  - `source_location`: page number / section / image region
  - `extraction_method`: table-parse | text-LLM | vision-LLM | web-agent

**4. Real confidence scoring methodology (this is your credibility anchor)**
Confidence is computed, not guessed, from a weighted combination of:
- **Extraction method reliability**: table-parse (highest) > text-LLM > vision-LLM > web-agent (lowest baseline)
- **Cross-source agreement**: if the same value appears in 2+ independent sources (doc + web, or text + image), confidence increases
- **Validation rule pass/fail**: unit sanity, range checks, required-field presence — failing a rule caps confidence low regardless of extraction method
- **Format/pattern confidence**: does the extracted value match expected format (e.g., a number where a number is expected, a valid unit)?
- Output final score as High / Medium / Low with the computed reasoning shown on hover — be ready to explain this formula in one sentence in Q&A

**5. Gap-filling agent**
- Triggered only for required fields still missing after document + image extraction
- Performs 1-2 targeted web searches (manufacturer-site preferred)
- Tags result: `source: web`, `needs_review: true`, separate (typically lower) confidence
- Scoped tightly — not open-ended crawling

**6. Validation & conflict detection layer**
- Rule-based sanity checks: unit consistency, min<max ranges, required fields present
- Cross-source conflict detection: if document value ≠ web value, flag explicitly, show both with sources side-by-side, do NOT auto-resolve silently
- Outlier detection (Tier 2 stretch, see below)

**7. Human-in-the-loop review UI**
- One screen per product, field-by-field list
- Color-coded confidence badges (green/yellow/red)
- Click-to-expand source citation (snippet + location)
- Conflict fields shown prominently with both candidate values + sources
- Approve / Edit / Reject per field
- "Bulk-approve all High confidence" action

**8. Correction propagation ("the surprise moment")**
- When a human edits/corrects a field, log: `{source_document_pattern, field_name, old_value, new_value}`
- System scans other products in the current batch sharing the same source template/pattern
- Surfaces a suggestion: "This correction may apply to 4 other products from the same source — apply to all?"
- Human approves/rejects the batch suggestion — still human-in-the-loop, not silent auto-edit
- This does NOT require real ML retraining — pattern-matching on source template + field is enough to demo convincingly and it is genuinely useful

**9. Structured export**
- Approved record exports as JSON + CSV in catalog-ready schema format

**10. Batch mode + scale dashboard**
- Pre-run pipeline across 20-30 real sample products before the demo
- Dashboard shows: total products processed, % fields auto-approved at High confidence, % fields flagged for review, number of conflicts caught, number of corrections propagated, estimated time saved vs. manual entry

### TIER 2 — Stretch (build 1-2 if time allows, in priority order)

1. **Outlier/consistency detection**: compare new product's fields against category norms from already-processed products; flag statistical outliers (e.g., "this pressure rating is 10x typical for this category — verify")
2. **Category auto-inference**: given only a title + image, infer likely category and auto-select the right schema, with reasoning shown
3. **Multi-language source normalization**: extract from non-English datasheet, normalize to English, flag translation confidence separately

### TIER 3 — Explicitly cut (say this out loud to your team, do not build)

- Full knowledge graph across the whole catalog
- Open-ended arbitrary web crawling
- User auth / multi-tenancy / production deployment infra
- Model fine-tuning
- More than 5 product categories
- Real ML retraining for correction propagation (pattern-matching is enough)

---

## SYSTEM ARCHITECTURE / PIPELINE

```
┌─────────────────────────────────────────────────────────────┐
│ INPUT LAYER                                                   │
│  PDF datasheet | Product image(s) | Raw text | URL             │
└───────────────────────────┬────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ INGESTION & PARSING                                            │
│  - Text + table extraction (unstructured/pdfplumber)           │
│  - Page rasterization → images (VLM fallback path)             │
│  - URL fetch + text extraction                                 │
└───────────────────────────┬────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ EXTRACTION ENGINE                                               │
│  - Schema-constrained LLM structured extraction (tool use)      │
│  - VLM pass on images/tables for missed fields                 │
│  - Tag: value, source_snippet, source_location, method          │
└───────────────────────────┬────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ CONFIDENCE SCORING ENGINE                                       │
│  method_reliability + cross_source_agreement +                  │
│  validation_pass/fail + format_match → computed score           │
└───────────────────────────┬────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ VALIDATION & CONFLICT DETECTION                                 │
│  - Schema conformance (Pydantic)                                │
│  - Rule checks: units, ranges, required fields                  │
│  - Cross-source conflict flagging (doc vs web vs image)         │
└───────────────────────────┬────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ GAP-FILLING AGENT                                                │
│  Triggered only for missing required fields                     │
│  → targeted web search (1-2 calls) → tag source:web             │
└───────────────────────────┬────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ HUMAN REVIEW UI                                                  │
│  Field-by-field approve/edit/reject                              │
│  Conflict resolution view                                        │
│  Confidence-colored badges + source citations                    │
└───────────────────────────┬────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ CORRECTION PROPAGATION ENGINE                                    │
│  Human edit logged → scan batch for same source pattern +       │
│  field → suggest propagation → human approves                    │
└───────────────────────────┬────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ EXPORT + BATCH DASHBOARD                                         │
│  JSON + CSV export | Aggregate stats across catalog batch        │
└─────────────────────────────────────────────────────────────┘
```

---

## TECH STACK

- **LLM / VLM reasoning**: Claude (structured output/tool use for schema-constrained extraction, vision for scanned docs/tables)
- **PDF parsing**: `unstructured` or `pdfplumber` + `pdf2image` for rasterization
- **Backend**: FastAPI (Python)
- **Schema validation**: Pydantic
- **Frontend**: React + a simple component library (no custom design system — spend zero time here)
- **Storage**: SQLite or JSON files (no need for a real DB at this scale)
- **Web search**: any search API available, or direct fetch of 2-3 known manufacturer sites for reliability

---

## AUTOMATION / ORCHESTRATION LOGIC (pseudocode)

```
for each product_input in batch:
    parsed = ingest(product_input)  # text, tables, images, url_text

    schema = select_schema(product_input.category)  # or auto-infer (Tier 2)

    extraction = extract_fields(parsed, schema)  # LLM structured output
    extraction += vlm_extract_missed_fields(parsed.images, schema, extraction)

    for field in extraction:
        field.confidence = compute_confidence(
            method_reliability(field.extraction_method),
            cross_source_agreement(field, extraction),
            validate_rules(field, schema)
        )

    conflicts = detect_conflicts(extraction)  # doc vs web vs image disagreement
    missing_required = get_missing_required(extraction, schema)

    if missing_required:
        web_results = gap_fill_agent(missing_required, product_input)
        extraction += tag_source(web_results, source="web", needs_review=True)

    record = validate_against_schema(extraction, schema)
    queue_for_human_review(record, conflicts)

# On human correction event:
on_field_corrected(product_id, field_name, old_value, new_value):
    pattern = get_source_pattern(product_id)
    candidates = find_products_with_pattern(pattern, field_name, batch)
    suggest_propagation(candidates, field_name, new_value)  # human approves before applying

# Batch dashboard aggregation:
compute_batch_stats(all_records):
    - % fields High/Medium/Low confidence
    - % fields auto-approved
    - # conflicts detected and resolved
    - # corrections propagated
    - estimated time saved vs manual entry
```

---

## 10-14 DAY BUILD PLAN

| Days | Focus |
|---|---|
| 1-2 | Lock schemas for 3-5 categories. Collect 20-30 real test documents. Define exact JSON contract for a product record. Design the confidence formula precisely (write it down, get team agreement). |
| 3-4 | Ingestion + text extraction pipeline. Get ONE category fully working end-to-end before generalizing. |
| 5-6 | VLM fallback for images/scanned tables. Wire in source_snippet + source_location tracking. |
| 7 | Build confidence scoring engine (the real formula, not a placeholder). Schema validation + rule checks. |
| 8 | Conflict detection layer — doc vs web vs image disagreement handling. |
| 9 | Gap-filling web search agent, tightly scoped to 1-2 calls per missing field. |
| 10 | Human review UI — approve/edit/reject, confidence badges, conflict view. |
| 11 | Correction propagation engine — the surprise moment. Build and test this carefully. |
| 12 | Run full batch (20-30 products), build the aggregate stats dashboard. |
| 13 | Polish, fix edge cases, prepare deliberately messy demo input for the stress-test moment. Record a backup video of the full flow in case live demo fails. |
| 14 | Rehearse pitch + Q&A. Prepare crisp answers to "how is this different from just prompting an LLM with a template" and "how is confidence actually computed." |

---

## DEMO SCRIPT (5-7 minutes)

1. **Problem (10s)** — Manufacturers burn hours per product turning scattered docs into clean catalog entries, with no way to trust or trace AI output.
2. **Live demo, clean input (60s)** — Upload a real datasheet, watch structured record populate with confidence + citations.
3. **Signature moment #1 — won't hallucinate (30s)** — Feed a bad/incomplete input live, show missing fields labeled "not found," not invented.
4. **Signature moment #2 — conflict detection (30s)** — Show a case where document and web disagree; system flags both, doesn't silently pick.
5. **Signature moment #3 — correction propagation (60s, THE differentiator)** — Correct one field, watch the system suggest the same fix across 3-4 other products from the same source pattern, human approves the batch suggestion.
6. **Human review screen (20s)** — Bulk-approve high-confidence fields.
7. **Scale proof (30s)** — Batch dashboard: N products processed, % auto-approved, conflicts caught, time saved.
8. **Architecture (30s)** — Quick diagram walkthrough, explain *why* each technique was necessary.
9. **Close (20s)** — Roadmap: category auto-inference, outlier detection, cross-catalog knowledge graph.

---

## Q&A PREP (rehearse these exact answers)

- **"How is this different from just prompting an LLM with a template?"**
  → "A raw prompt gives you one number with no way to know if it's right. We compute confidence from extraction method reliability, cross-source agreement, and validation rule outcomes — so a judge can literally trace why a field is trusted or not, and the system refuses to invent missing data instead of guessing."

- **"How do you know your confidence scores are actually meaningful?"**
  → State the exact formula components (method reliability + cross-source agreement + validation pass/fail) and give one concrete example from your test set.

- **"Does this scale to a real catalog of 50,000 SKUs?"**
  → Point to the batch dashboard numbers, explain the gap-filling agent is scoped (not open crawling) specifically so it stays fast and cheap at scale.

- **"What happens when the correction propagation suggestion is wrong?"**
  → It's always human-approved before applying — the system suggests, it never silently bulk-edits.

---

## FINAL CHECKLIST BEFORE THE PITCH

- [ ] All Tier 1 features working end-to-end on real test data
- [ ] Confidence formula documented and explainable in one sentence
- [ ] At least one real conflict case in your test set (doc vs web disagreement)
- [ ] Correction propagation demoed successfully at least 5 times in rehearsal
- [ ] Batch dashboard pre-run with real numbers, not placeholders
- [ ] Backup recorded video of full flow in case of live demo failure
- [ ] Q&A answers rehearsed out loud, not just written down
- [ ] Team knows exactly what was explicitly cut (Tier 3) and why, in case asked
