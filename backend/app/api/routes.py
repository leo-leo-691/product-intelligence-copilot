import csv
import io
import json
import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from backend.app.config import ROOT, UPLOAD_DIR, settings
from backend.app.logging_config import setup_logging
from backend.app.middleware.auth import ApiKeyMiddleware
from backend.app.models.product import BatchRun, ProductInput, ProductRecord, utc_now
from backend.app.schemas.categories import CATEGORIES, record_to_export_dict
from backend.app.services.knowledge_graph import init_kg, kg_neighbors, kg_summary
from backend.app.services.learning import init_learning, log_correction, recent_corrections
from backend.app.services.pipeline import run_pipeline
from backend.app.services.propagation import apply_propagation, find_propagation_candidates
from backend.app.services.storage import (
    clear_all,
    compute_dashboard,
    get_product,
    init_db,
    list_batches,
    list_products,
    list_propagations,
    save_batch,
    save_product,
    save_propagation,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    setup_logging(settings.log_level)
    init_db()
    init_kg()
    init_learning()
    origins = settings.cors_origin_list()
    if settings.app_env == "production" and all(
        o.startswith("http://localhost") or o.startswith("http://127.0.0.1") for o in origins
    ):
        logger.warning(
            "CORS_ORIGINS still points at localhost in production — set your Vercel URL on Render"
        )
    logger.info(
        "Product Intelligence Copilot API ready (env=%s, cors_origins=%d)",
        settings.app_env,
        len(origins),
    )
    yield


app = FastAPI(
    title="Product Intelligence Copilot",
    version="1.1.0",
    description="Schema-validated product intelligence with computed confidence, conflicts, correction propagation, KG, and deploy-ready API auth.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(ApiKeyMiddleware)


@app.exception_handler(Exception)
async def unhandled_exception(request: Request, exc: Exception):
    if isinstance(exc, HTTPException):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "error": str(exc) if settings.app_env != "production" else "unexpected",
        },
    )


@app.get("/health")
def health():
    from backend.app.llm import get_llm_provider

    provider = get_llm_provider()
    llm_configured = provider.is_configured()
    return {
        "status": "ok",
        "version": "1.2.0",
        "llm_provider": provider.name,
        "llm_configured": llm_configured,
        # Backward-compatible alias (true when selected provider has a key)
        "anthropic_configured": llm_configured,
        "web_search_configured": bool(settings.tavily_api_key or settings.serpapi_api_key),
        "api_auth_required": bool(settings.api_key),
        "kg_enabled": settings.kg_enabled,
        "dual_llm_enabled": bool(settings.dual_llm_enabled),
        "env": settings.app_env,
    }


@app.get("/api/categories")
def get_categories():
    return [
        {"id": s.category_id, "name": s.display_name, "fields": [f.model_dump() for f in s.fields]}
        for s in CATEGORIES.values()
    ]


class IngestBody(BaseModel):
    sku: str = Field(min_length=1, max_length=128)
    category_id: str | None = "auto"
    text: str | None = None
    url: str | None = None
    source_template_id: str | None = None
    seed_web_overrides: dict[str, Any] | None = None
    batch_id: str | None = None
    title: str | None = None


async def _save_upload(sku: str, upload: UploadFile, subdir: str) -> str:
    if not upload.filename:
        raise HTTPException(400, "Empty filename")
    data = await upload.read()
    max_bytes = settings.max_upload_mb * 1024 * 1024
    if len(data) > max_bytes:
        raise HTTPException(413, f"File exceeds {settings.max_upload_mb}MB limit")
    dest = UPLOAD_DIR / subdir
    dest.mkdir(parents=True, exist_ok=True)
    safe_name = "".join(c for c in upload.filename if c.isalnum() or c in "._-") or "upload.bin"
    dest_file = dest / f"{sku}_{safe_name}"
    dest_file.write_bytes(data)
    return str(dest_file.relative_to(ROOT)).replace("\\", "/")


@app.post("/api/ingest", response_model=ProductRecord)
async def ingest_json(body: IngestBody):
    cat = body.category_id or "auto"
    if cat not in CATEGORIES and cat not in ("auto", "infer"):
        raise HTTPException(400, "Unknown category")
    if not body.text and not body.url:
        raise HTTPException(400, "Provide text and/or url")
    inp = ProductInput(
        sku=body.sku.strip(),
        category_id=None if cat in ("auto", "infer") else cat,
        text=body.text,
        url=body.url,
        source_template_id=body.source_template_id,
        seed_web_overrides=body.seed_web_overrides,
        title=body.title,
    )
    try:
        record = await run_pipeline(inp, batch_id=body.batch_id)
    except Exception as e:
        logger.exception("Pipeline failed for %s", body.sku)
        raise HTTPException(422, f"Pipeline failed: {e}") from e
    return save_product(record)


@app.post("/api/ingest/upload", response_model=ProductRecord)
async def ingest_upload(
    sku: str = Form(...),
    category_id: str = Form("auto"),
    text: str | None = Form(None),
    url: str | None = Form(None),
    source_template_id: str | None = Form(None),
    batch_id: str | None = Form(None),
    title: str | None = Form(None),
    pdf: UploadFile | None = File(None),
    image: UploadFile | None = File(None),
):
    if category_id not in CATEGORIES and category_id not in ("auto", "infer"):
        raise HTTPException(400, "Unknown category")

    pdf_path = None
    image_path = None
    try:
        if pdf and pdf.filename:
            pdf_path = await _save_upload(sku, pdf, "pdf")
        if image and image.filename:
            image_path = await _save_upload(sku, image, "images")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, f"Upload failed: {e}") from e

    if not any([text, url, pdf_path, image_path]):
        raise HTTPException(400, "Provide text, url, pdf, and/or image")

    inp = ProductInput(
        sku=sku.strip(),
        category_id=None if category_id in ("auto", "infer") else category_id,
        text=text,
        url=url,
        pdf_path=pdf_path,
        image_path=image_path,
        source_template_id=source_template_id,
        title=title,
    )
    try:
        record = await run_pipeline(inp, batch_id=batch_id)
    except Exception as e:
        logger.exception("Upload pipeline failed for %s", sku)
        raise HTTPException(422, f"Pipeline failed: {e}") from e
    return save_product(record)


@app.get("/api/products", response_model=list[ProductRecord])
def products(batch_id: str | None = None):
    return list_products(batch_id)


@app.get("/api/products/{product_id}", response_model=ProductRecord)
def product_detail(product_id: str):
    r = get_product(product_id)
    if not r:
        raise HTTPException(404, "Not found")
    return r


class FieldReview(BaseModel):
    review_status: str
    value: Any | None = None


@app.patch("/api/products/{product_id}/fields/{field_name}")
def review_field(product_id: str, field_name: str, body: FieldReview):
    r = get_product(product_id)
    if not r:
        raise HTTPException(404, "Not found")
    if field_name not in r.fields:
        raise HTTPException(400, "Unknown field")
    if body.review_status not in ("approved", "rejected", "edited", "pending"):
        raise HTTPException(400, "Invalid review_status")

    fp = r.fields[field_name]
    old_value = fp.value
    if body.review_status == "edited" and body.value is not None:
        # Coerce numbers when field looks numeric
        val = body.value
        try:
            if isinstance(old_value, (int, float)) or (
                isinstance(val, str) and val.replace(".", "", 1).isdigit()
            ):
                val = float(val) if "." in str(val) else int(float(val))
        except (TypeError, ValueError):
            pass
        fp.value = val
        fp.not_found = False
    fp.review_status = body.review_status
    if body.review_status == "approved":
        fp.needs_review = False
    r.fields[field_name] = fp
    r.updated_at = utc_now()

    # Auto-bump record status
    statuses = [f.review_status for f in r.fields.values()]
    if all(s in ("approved", "edited") for s in statuses):
        r.status = "approved"
    elif any(s in ("approved", "edited") for s in statuses):
        r.status = "partially_approved"

    save_product(r)

    suggestion = None
    if body.review_status == "edited" and body.value is not None:
        try:
            log_correction(
                sku=r.sku,
                category_id=r.category_id,
                source_template_id=r.source_template_id,
                field_name=field_name,
                old_value=old_value,
                new_value=fp.value,
            )
        except Exception:
            logger.exception("correction log failed")
        suggestion = find_propagation_candidates(
            list_products(), product_id, field_name, old_value, fp.value
        )
        if suggestion:
            save_propagation(suggestion)
    return {"product": r, "propagation_suggestion": suggestion}


class ResolveConflictBody(BaseModel):
    chosen_value: Any
    source_note: str | None = None


@app.post("/api/products/{product_id}/conflicts/{field_name}/resolve")
def resolve_conflict(product_id: str, field_name: str, body: ResolveConflictBody):
    r = get_product(product_id)
    if not r:
        raise HTTPException(404, "Not found")
    if field_name not in r.fields:
        raise HTTPException(400, "Unknown field")

    fp = r.fields[field_name]
    fp.value = body.chosen_value
    fp.not_found = False
    fp.review_status = "edited"
    fp.needs_review = False
    if body.source_note:
        fp.source_snippet = (fp.source_snippet or "") + f" | resolved: {body.source_note}"
    r.fields[field_name] = fp

    for c in r.conflicts:
        if c.field_name == field_name:
            c.resolved = True
    r.updated_at = utc_now()
    save_product(r)
    return r


@app.post("/api/products/{product_id}/bulk-approve-high")
def bulk_approve_high(product_id: str):
    r = get_product(product_id)
    if not r:
        raise HTTPException(404, "Not found")
    conflict_fields = {c.field_name for c in r.conflicts if not c.resolved}
    for name, fp in r.fields.items():
        if fp.confidence_score.value == "High" and not fp.not_found and name not in conflict_fields:
            fp.review_status = "approved"
            fp.needs_review = False
    approved_like = sum(1 for f in r.fields.values() if f.review_status in ("approved", "edited"))
    if approved_like == len(r.fields) and r.fields:
        r.status = "approved"
    elif approved_like:
        r.status = "partially_approved"
    r.updated_at = utc_now()
    save_product(r)
    return r


@app.post("/api/products/{product_id}/approve-record")
def approve_record(product_id: str):
    r = get_product(product_id)
    if not r:
        raise HTTPException(404, "Not found")
    for fp in r.fields.values():
        if not fp.not_found and fp.review_status == "pending":
            fp.review_status = "approved"
            fp.needs_review = False
    r.status = "approved"
    r.updated_at = utc_now()
    save_product(r)
    return r


@app.get("/api/propagations")
def propagations(status: str | None = None):
    return list_propagations(status)


class PropagationAction(BaseModel):
    action: str  # apply | dismiss


@app.post("/api/propagations/{propagation_id}")
def propagation_action(propagation_id: str, body: PropagationAction):
    items = list_propagations()
    s = next((p for p in items if p.id == propagation_id), None)
    if not s:
        raise HTTPException(404, "Not found")
    if body.action == "dismiss":
        s.status = "dismissed"
        save_propagation(s)
        return s
    if body.action == "apply":
        records = list_products()
        updated = apply_propagation(records, s)
        for rec in updated:
            if rec.id in s.candidate_product_ids or rec.id == s.source_product_id:
                save_product(rec)
        s.status = "applied"
        save_propagation(s)
        return s
    raise HTTPException(400, "Unknown action")


class BatchRequest(BaseModel):
    name: str = "demo-batch"
    items: list[IngestBody] = Field(default_factory=list)
    reset: bool = False


@app.post("/api/batch", response_model=BatchRun)
async def run_batch(body: BatchRequest):
    if body.reset:
        clear_all()
        init_db()
    batch = BatchRun(name=body.name)
    save_batch(batch)
    for item in body.items:
        text = item.text
        if text and str(text).endswith(".txt"):
            p = ROOT / text
            if p.exists():
                text = p.read_text(encoding="utf-8")
        inp = ProductInput(
            sku=item.sku,
            category_id=item.category_id,
            text=text,
            url=item.url,
            source_template_id=item.source_template_id,
            seed_web_overrides=item.seed_web_overrides,
        )
        record = await run_pipeline(inp, batch_id=batch.id)
        save_product(record)
        batch.product_ids.append(record.id)
    save_batch(batch)
    return batch


@app.post("/api/batch/from-manifest", response_model=BatchRun)
async def batch_from_manifest(reset: bool = True, name: str = "demo-batch"):
    """Load data/samples/manifest.json and run the full demo batch."""
    manifest_path = ROOT / "data" / "samples" / "manifest.json"
    if not manifest_path.exists():
        raise HTTPException(404, "manifest.json not found")
    if reset:
        clear_all()
        init_db()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    batch = BatchRun(name=name)
    save_batch(batch)
    for item in manifest.get("products", []):
        text_path = ROOT / "data" / "samples" / item["text_file"]
        text = text_path.read_text(encoding="utf-8") if text_path.exists() else ""
        pdf_path = None
        if item.get("pdf_file"):
            pdf_path = str((ROOT / "data" / "samples" / item["pdf_file"]).relative_to(ROOT)).replace("\\", "/")
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
        logger.info("Batch processed %s conflicts=%s", item["sku"], len(record.conflicts))
    save_batch(batch)
    return batch


@app.delete("/api/reset")
def reset_store():
    counts = clear_all()
    init_db()
    return {"cleared": counts, "status": "ok"}


@app.get("/api/batches", response_model=list[BatchRun])
def batches():
    return list_batches()


@app.get("/api/dashboard")
def dashboard(batch_id: str | None = None):
    return compute_dashboard(batch_id)


@app.get("/api/export/json")
def export_json(approved_only: bool = True):
    records = list_products()
    if approved_only:
        records = [r for r in records if r.status == "approved"]
    if not records:
        records = list_products()
    if not records:
        raise HTTPException(404, "No records to export")
    payload = [
        {"sku": r.sku, "category_id": r.category_id, "status": r.status, **record_to_export_dict(r.fields)}
        for r in records
    ]
    body = json.dumps(payload, indent=2, default=str)
    return StreamingResponse(
        iter([body]),
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=products.json"},
    )


@app.get("/api/export/csv")
def export_csv(approved_only: bool = True):
    records = list_products()
    if approved_only:
        records = [r for r in records if r.status == "approved"]
    if not records:
        # Fall back to all products for demo convenience
        records = list_products()
    if not records:
        raise HTTPException(404, "No records to export")

    # Union of fields across categories (valve/bearing/sensor differ)
    field_keys: list[str] = []
    seen: set[str] = set()
    for r in records:
        for k in r.fields.keys():
            if k not in seen:
                seen.add(k)
                field_keys.append(k)

    fieldnames = ["sku", "category_id", "status"] + field_keys
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
    w.writeheader()
    for r in records:
        row: dict[str, Any] = {"sku": r.sku, "category_id": r.category_id, "status": r.status}
        for k in field_keys:
            fp = r.fields.get(k)
            if fp is None or fp.not_found:
                row[k] = ""
            else:
                row[k] = fp.value
        w.writerow(row)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=products.csv"},
    )


@app.get("/api/eval/match-rate")
def eval_match_rate():
    path = ROOT / "data" / "eval" / "gold_labels.json"
    if not path.exists():
        return {"error": "gold_labels.json not found", "fields_compared": 0, "match_rate": 0}
    gold = json.loads(path.read_text(encoding="utf-8"))
    products = {r.sku: r for r in list_products()}
    total = matched = matched_high = 0
    details = []
    for entry in gold:
        rec = products.get(entry["sku"])
        if not rec:
            continue
        for field, expected in entry.get("fields", {}).items():
            total += 1
            fp = rec.fields.get(field)
            if not fp or fp.not_found:
                details.append({"sku": entry["sku"], "field": field, "ok": False, "reason": "missing"})
                continue
            ok = str(fp.value).strip().lower() == str(expected).strip().lower()
            if ok:
                matched += 1
                if fp.confidence_score.value == "High":
                    matched_high += 1
            details.append(
                {
                    "sku": entry["sku"],
                    "field": field,
                    "ok": ok,
                    "value": fp.value,
                    "expected": expected,
                    "confidence": fp.confidence_score.value,
                }
            )
    return {
        "fields_compared": total,
        "exact_matches": matched,
        "high_band_matches": matched_high,
        "match_rate": round(matched / total, 3) if total else 0,
        "high_precision_proxy": round(matched_high / total, 3) if total else 0,
        "details": details[:50],
    }


@app.get("/api/kg")
def api_kg_summary():
    try:
        return kg_summary()
    except Exception as e:
        logger.exception("KG summary failed")
        raise HTTPException(500, str(e)) from e


@app.get("/api/kg/node/{node_id:path}")
def api_kg_node(node_id: str):
    try:
        return kg_neighbors(node_id)
    except Exception as e:
        raise HTTPException(500, str(e)) from e


@app.get("/api/learning/corrections")
def api_corrections(limit: int = 50):
    try:
        return recent_corrections(min(limit, 200))
    except Exception as e:
        raise HTTPException(500, str(e)) from e
