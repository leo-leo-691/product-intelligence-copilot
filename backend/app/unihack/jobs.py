"""Batch job runner for UniHack evaluation. Isolated from the 26-product demo."""

from __future__ import annotations

import logging
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.app.config import settings
from backend.app.unihack.discover import find_delivery_schema, find_file, inventory, missing_hint
from backend.app.unihack.evaluate import evaluate_predictions, load_ground_truth
from backend.app.unihack.ingest import ingest_input_workbook
from backend.app.unihack.official import ensure_expected_output, ensure_sample_input
from backend.app.unihack.pipeline import process_row
from backend.app.unihack.schema import empty_row, load_delivery_headers, validate_headers
from backend.app.unihack.store import (
    get_eval,
    get_job,
    latest_job,
    list_rows,
    save_eval,
    save_job,
    save_row,
)

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _refs() -> dict[str, Any]:
    lov = [p for p in (find_file("lov"), find_file("lov_faucets"), find_file("lov_fittings")) if p]
    return {
        "manufacturers": find_file("manufacturers"),
        "lov": lov,
        "uom": find_file("uom"),
        "fractions": find_file("fractions"),
    }


def _schema_path() -> Path | None:
    local = find_delivery_schema()
    if local:
        return local
    try:
        return ensure_expected_output()
    except Exception as exc:
        logger.warning("Could not fetch official Expected Output: %s", exc)
        return None


def _input_path(explicit: Path | None) -> Path | None:
    if explicit:
        return explicit
    local = find_file("input_1000")
    if local:
        return local
    try:
        return ensure_sample_input()
    except Exception as exc:
        logger.warning("Could not fetch official sample input: %s", exc)
        return None


def create_job(*, input_path: Path | None = None, evaluate: bool = False) -> dict[str, Any]:
    src = _input_path(input_path)
    schema_path = _schema_path()
    job = {
        "id": str(uuid.uuid4()),
        "status": "QUEUED",
        "created_at": _now(),
        "completed_at": None,
        "evaluate": evaluate,
        "input_path": str(src) if src else None,
        "schema_path": str(schema_path) if schema_path else None,
        "missing": [],
        "progress": {"processed": 0, "successful": 0, "failed": 0, "total": 0},
        "headers": [],
        "header_count": 0,
        "error": None,
        "files": inventory(),
    }
    if not src:
        job["missing"].append(missing_hint("input_1000"))
    if not schema_path:
        job["missing"].append(missing_hint("expected_output"))
    if job["missing"]:
        job["status"] = "FAILED"
        job["error"] = " ; ".join(job["missing"])
        job["completed_at"] = _now()
    save_job(job)
    return job


def run_job(job_id: str) -> dict[str, Any]:
    job = get_job(job_id)
    if not job:
        raise KeyError(job_id)
    if job["status"] == "FAILED" and job.get("error"):
        return job
    job["status"] = "RUNNING"
    save_job(job)
    try:
        ingested = ingest_input_workbook(Path(job["input_path"]))
        schema = load_delivery_headers(Path(job["schema_path"]))
        headers: list[str] = schema["headers"]
        job["headers"] = headers
        job["header_count"] = len(headers)
        job["schema_compliance"] = validate_headers(headers, schema["headers"])
        job["input_row_count"] = ingested["row_count"]
        job["input_headers"] = ingested.get("input_headers") or []
        job["ingest_warnings"] = ingested.get("warnings") or []
        refs = _refs()
        total = ingested["row_count"]
        job["progress"]["total"] = total
        save_job(job)

        ok = fail = 0
        workers = max(1, settings.unihack_batch_workers)
        batch_size = max(1, settings.unihack_batch_size)

        def _process_one(raw: dict) -> dict:
            """Process a single row with full isolation."""
            try:
                row = process_row(
                    raw,
                    headers,
                    manufacturer_path=refs["manufacturers"],
                    lov_paths=refs["lov"],
                    uom_path=refs["uom"],
                )
                if row.get("error"):
                    row["status"] = "error"
                    row["delivery"] = row.get("delivery") or empty_row(headers)
                return row
            except Exception as exc:  # noqa: BLE001
                return {
                    "row_number": raw.get("row_number"),
                    "mfg_part_num": raw.get("Mfg_Part_Num") or raw.get("Mfg_Part_Num"),
                    "status": "error",
                    "error": str(exc),
                    "delivery": empty_row(headers),
                    "provenance": {},
                    "fields_generated": 0,
                    "fields_missing": len(headers),
                    "review_required": True,
                    "issues": [traceback.format_exc(limit=3)],
                    "confidence": "Low",
                }

        all_rows = ingested["rows"]

        # Process in batches using ThreadPoolExecutor
        for batch_start in range(0, len(all_rows), batch_size):
            batch = all_rows[batch_start : batch_start + batch_size]

            if workers > 1 and len(batch) > 1:
                from concurrent.futures import ThreadPoolExecutor, as_completed

                with ThreadPoolExecutor(max_workers=min(workers, len(batch))) as executor:
                    futures = {executor.submit(_process_one, raw): raw for raw in batch}
                    for future in as_completed(futures):
                        row = future.result()
                        if row.get("status") == "error":
                            fail += 1
                        else:
                            ok += 1
                        save_row(job_id, row)
            else:
                # Sequential fallback for single-worker or single-row batches
                for raw in batch:
                    row = _process_one(raw)
                    if row.get("status") == "error":
                        fail += 1
                    else:
                        ok += 1
                    save_row(job_id, row)

            job["progress"] = {
                "processed": ok + fail,
                "successful": ok,
                "failed": fail,
                "total": total,
            }
            save_job(job)

        job["progress"] = {
            "processed": ok + fail,
            "successful": ok,
            "failed": fail,
            "total": total,
        }
        probe = empty_row(headers)
        saved_rows = list_rows(job_id)
        if saved_rows:
            probe = saved_rows[0].get("delivery") or probe
        job["schema_compliance"] = validate_headers(list(probe.keys()), headers)
        if fail and ok:
            job["status"] = "PARTIAL"
        elif fail and not ok:
            job["status"] = "FAILED"
            job["error"] = f"All {fail} rows failed"
        else:
            job["status"] = "COMPLETED"
        job["completed_at"] = _now()
        save_job(job)
        if job.get("evaluate"):
            try:
                run_evaluation(job_id)
            except Exception as exc:  # noqa: BLE001
                job = get_job(job_id) or job
                job["eval_error"] = str(exc)
                save_job(job)
        return get_job(job_id) or job
    except Exception as exc:
        job["status"] = "FAILED"
        job["error"] = str(exc)
        job["completed_at"] = _now()
        save_job(job)
        logger.exception("UniHack job %s failed", job_id)
        return job


def run_evaluation(job_id: str) -> dict[str, Any]:
    job = get_job(job_id)
    if not job:
        raise KeyError(job_id)
    gt_path = find_file("ground_truth_200")
    if not gt_path:
        payload = {
            "available": False,
            "ground_truth": "NOT AVAILABLE",
            "evaluation": "NOT RUN",
            "error": missing_hint("ground_truth_200"),
            "message": "Official 200-row Input-vs-Output ground truth is not available. Accuracy is not calculated.",
        }
        save_eval(job_id, payload)
        return payload
    headers: list[str] = job.get("headers") or load_delivery_headers(Path(job["schema_path"]))["headers"]
    expected = load_ground_truth(gt_path, headers)
    rows = list_rows(job_id)
    predicted = [r.get("delivery") or empty_row(headers) for r in rows]
    for pred, r in zip(predicted, rows):
        if r.get("mfg_part_num"):
            pred.setdefault("Mfg_Part_Num", r["mfg_part_num"])
    refs = _refs()
    metrics = evaluate_predictions(
        predicted,
        expected,
        headers,
        lov_paths=refs["lov"],
        uom_path=refs["uom"],
    )
    metrics["available"] = True
    metrics["ground_truth_path"] = str(gt_path)
    save_eval(job_id, metrics)
    return metrics


def job_status(job_id: str | None = None) -> dict[str, Any]:
    job = get_job(job_id) if job_id else latest_job()
    if not job:
        return {"status": None, "message": "Evaluation has not been run yet"}
    rows = list_rows(job["id"])
    flagged = [r for r in rows if r.get("review_required") or r.get("status") == "error"]
    return {
        **job,
        "flagged_count": len(flagged),
        "evaluation": get_eval(job["id"]),
        "sample_errors": [
            {
                "row_number": r.get("row_number"),
                "mfg_part_num": r.get("mfg_part_num"),
                "error": r.get("error"),
            }
            for r in flagged[:25]
            if r.get("error")
        ],
    }
