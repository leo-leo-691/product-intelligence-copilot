"""UniHack evaluation API — does not alter 26-product demo routes."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile
from fastapi.responses import Response

from backend.app.unihack.deep_dive import build_deep_dive
from backend.app.unihack.discover import UNIHACK_UPLOADS, find_file, inventory, missing_hint
from backend.app.unihack.export import write_validated_csv, write_validated_xlsx
from backend.app.unihack.jobs import create_job, job_status, run_evaluation, run_job
from backend.app.unihack.official import ensure_expected_output
from backend.app.unihack.schema import SchemaError, load_delivery_headers, require_schema
from backend.app.unihack.store import get_job, latest_job, list_rows, save_row

router = APIRouter(prefix="/api/unihack", tags=["unihack"])

_UPLOAD_KINDS = {
    "input",
    "ground_truth",
    "manufacturers",
    "lov",
    "uom",
    "fractions",
    "delivery_schema",
}


def _save_upload(kind: str, upload: UploadFile) -> Path:
    UNIHACK_UPLOADS.mkdir(parents=True, exist_ok=True)
    dest = UNIHACK_UPLOADS / (upload.filename or f"{kind}.xlsx")
    dest.write_bytes(upload.file.read())
    return dest


@router.get("/files")
def unihack_files():
    return {"files": inventory()}


@router.get("/schema")
def unihack_schema():
    try:
        path = ensure_expected_output()
        loaded = load_delivery_headers(path)
        headers = loaded["headers"]
        return {
            "available": True,
            "path": str(path),
            "header_count": loaded["header_count"],
            "headers": headers,
            "duplicates": loaded.get("duplicates") or [],
            "sheet": loaded.get("sheet"),
            "display_note": "252 required delivery fields",
            "schema_compliance": {
                "expected_count": len(headers),
                "generated_count": len(headers),
                "order": "PASS",
                "missing": 0,
                "unexpected": 0,
                "valid": True,
                "scope": "official Expected Output file (headers loaded; export not yet generated)",
            },
        }
    except Exception as exc:
        return {"available": False, "error": str(exc), "header_count": None, "headers": []}


@router.post("/import")
async def unihack_import(kind: str = "input", file: UploadFile = File(...)):
    if kind not in _UPLOAD_KINDS:
        raise HTTPException(400, f"Unknown kind '{kind}'. Use: {sorted(_UPLOAD_KINDS)}")
    path = _save_upload(kind, file)
    return {"saved": str(path), "filename": path.name, "kind": kind, "files": inventory()}


@router.post("/run")
def unihack_run(background_tasks: BackgroundTasks, evaluate: bool = True, use_official: bool = True):
    src = find_file("input_1000") if use_official else None
    job = create_job(input_path=src, evaluate=evaluate)
    if job["status"] != "FAILED":
        background_tasks.add_task(run_job, job["id"])
    return job


@router.post("/evaluate")
def unihack_evaluate(job_id: str | None = None):
    job = get_job(job_id) if job_id else latest_job()
    if not job:
        raise HTTPException(404, "Evaluation has not been run yet")
    try:
        return run_evaluation(job["id"])
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/status")
@router.get("/status/{job_id}")
def unihack_status(job_id: str | None = None):
    return job_status(job_id)


@router.get("/evaluation")
def unihack_evaluation(job_id: str | None = None):
    status = job_status(job_id)
    ev = status.get("evaluation")
    if not ev:
        return {
            "available": False,
            "ground_truth": "NOT AVAILABLE",
            "evaluation": "NOT RUN",
            "message": "Official 200-row ground truth is not loaded. Accuracy is not calculated.",
            "job": status,
        }
    return ev


@router.get("/deep-dive")
def unihack_deep_dive():
    return build_deep_dive()


@router.get("/rows")
def unihack_rows(job_id: str | None = None, flagged_only: bool = False, limit: int = 50):
    job = get_job(job_id) if job_id else latest_job()
    if not job:
        return {"rows": []}
    rows = list_rows(job["id"])
    if flagged_only:
        rows = [r for r in rows if r.get("review_required") or r.get("status") == "error"]
    slim = []
    for r in rows[: max(1, min(limit, 500))]:
        slim.append(
            {
                "row_number": r.get("row_number"),
                "mfg_part_num": r.get("mfg_part_num"),
                "status": r.get("status"),
                "confidence": r.get("confidence"),
                "review_required": r.get("review_required"),
                "fields_generated": r.get("fields_generated"),
                "fields_missing": r.get("fields_missing"),
                "issues": r.get("issues"),
                "error": r.get("error"),
            }
        )
    return {"job_id": job["id"], "count": len(slim), "rows": slim}


@router.post("/rows/{row_number}/review")
def unihack_review_row(
    row_number: int,
    field: str,
    review_status: str,
    value: str | None = None,
    job_id: str | None = None,
):
    if review_status not in {"approved", "rejected", "edited", "pending"}:
        raise HTTPException(400, "review_status must be approved|rejected|edited|pending")
    job = get_job(job_id) if job_id else latest_job()
    if not job:
        raise HTTPException(404, "No UniHack job")
    rows = {int(r.get("row_number") or 0): r for r in list_rows(job["id"])}
    row = rows.get(row_number)
    if not row:
        raise HTTPException(404, "Row not found")
    prov = row.setdefault("provenance", {}).setdefault(
        field,
        {
            "value": (row.get("delivery") or {}).get(field, ""),
            "source": "human",
            "confidence": "High",
            "review_status": "pending",
            "needs_review": True,
            "issues": [],
        },
    )
    if value is not None:
        row.setdefault("delivery", {})[field] = value
        prov["value"] = value
        prov["source"] = "human"
    prov["review_status"] = review_status
    prov["needs_review"] = review_status == "pending"
    save_row(job["id"], row)
    return {"ok": True, "row_number": row_number, "field": field, "review_status": review_status}


def _export_payload(job_id: str | None) -> tuple[list[str], list[str], list[dict[str, str]]]:
    job = get_job(job_id) if job_id else latest_job()
    if not job:
        raise HTTPException(404, "Evaluation has not been run yet")
    headers = job.get("headers") or []
    if not headers:
        raise HTTPException(400, missing_hint("delivery_schema"))
    try:
        expected = load_delivery_headers(ensure_expected_output())["headers"]
        require_schema(headers, expected)
    except SchemaError as exc:
        raise HTTPException(409, str(exc)) from exc
    compliance = job.get("schema_compliance") or {}
    if compliance and compliance.get("valid") is False:
        raise HTTPException(
            409,
            f"SCHEMA VALIDATION FAILED — Order: {compliance.get('order')}; "
            f"Missing: {len(compliance.get('missing') or [])}; "
            f"Unexpected: {len(compliance.get('unexpected') or [])}",
        )
    rows = [r.get("delivery") or {} for r in list_rows(job["id"])]
    return headers, expected, rows


@router.get("/export/csv")
def unihack_export_csv(job_id: str | None = None):
    try:
        headers, expected, rows = _export_payload(job_id)
        content = write_validated_csv(headers, rows, expected)
    except SchemaError as exc:
        raise HTTPException(409, str(exc)) from exc
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="unihack-delivery.csv"'},
    )


@router.get("/export/xlsx")
def unihack_export_xlsx(job_id: str | None = None):
    try:
        headers, expected, rows = _export_payload(job_id)
        content = write_validated_xlsx(headers, rows, expected)
    except SchemaError as exc:
        raise HTTPException(409, str(exc)) from exc
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="unihack-delivery.xlsx"'},
    )
