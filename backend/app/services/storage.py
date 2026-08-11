import json
import logging
import sqlite3
from pathlib import Path
from typing import Any

from backend.app.config import DB_PATH
from backend.app.models.product import BatchRun, DashboardStats, ProductRecord, PropagationSuggestion
from backend.app.schemas.fields import ConfidenceBand

logger = logging.getLogger(__name__)


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _ensure_products_schema(conn: sqlite3.Connection) -> None:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='products'"
    ).fetchone()
    if not row:
        conn.execute(
            """
            CREATE TABLE products (
                id TEXT PRIMARY KEY,
                sku TEXT,
                batch_id TEXT,
                data JSON NOT NULL
            )
            """
        )
        return
    cols = {r[1] for r in conn.execute("PRAGMA table_info(products)").fetchall()}
    if "sku" not in cols or "batch_id" not in cols:
        # Migrate from legacy (id, data) schema
        conn.executescript(
            """
            ALTER TABLE products RENAME TO products_legacy;
            CREATE TABLE products (
                id TEXT PRIMARY KEY,
                sku TEXT,
                batch_id TEXT,
                data JSON NOT NULL
            );
            INSERT INTO products (id, sku, batch_id, data)
            SELECT id, NULL, NULL, data FROM products_legacy;
            DROP TABLE products_legacy;
            """
        )


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _connect() as conn:
        _ensure_products_schema(conn)
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS batches (
                id TEXT PRIMARY KEY,
                data JSON NOT NULL
            );
            CREATE TABLE IF NOT EXISTS propagations (
                id TEXT PRIMARY KEY,
                data JSON NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_products_sku ON products(sku);
            CREATE INDEX IF NOT EXISTS idx_products_batch ON products(batch_id);
            """
        )
    logger.info("Database ready at %s", DB_PATH)


def clear_all() -> dict[str, int]:
    with _connect() as conn:
        pc = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        bc = conn.execute("SELECT COUNT(*) FROM batches").fetchone()[0]
        pr = conn.execute("SELECT COUNT(*) FROM propagations").fetchone()[0]
        conn.execute("DELETE FROM products")
        conn.execute("DELETE FROM batches")
        conn.execute("DELETE FROM propagations")
    return {"products": pc, "batches": bc, "propagations": pr}


def save_product(record: ProductRecord) -> ProductRecord:
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO products (id, sku, batch_id, data) VALUES (?, ?, ?, ?)",
            (record.id, record.sku, record.batch_id, record.model_dump_json()),
        )
    return record


def get_product(product_id: str) -> ProductRecord | None:
    with _connect() as conn:
        row = conn.execute("SELECT data FROM products WHERE id = ?", (product_id,)).fetchone()
    if not row:
        return None
    return ProductRecord.model_validate_json(row["data"])


def get_product_by_sku(sku: str) -> ProductRecord | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT data FROM products WHERE sku = ? ORDER BY rowid DESC LIMIT 1", (sku,)
        ).fetchone()
    if not row:
        return None
    return ProductRecord.model_validate_json(row["data"])


def list_products(batch_id: str | None = None) -> list[ProductRecord]:
    with _connect() as conn:
        if batch_id:
            rows = conn.execute(
                "SELECT data FROM products WHERE batch_id = ?", (batch_id,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT data FROM products").fetchall()
    records = [ProductRecord.model_validate_json(r["data"]) for r in rows]
    records.sort(key=lambda r: r.sku)
    return records


def save_batch(batch: BatchRun) -> BatchRun:
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO batches (id, data) VALUES (?, ?)",
            (batch.id, batch.model_dump_json()),
        )
    return batch


def list_batches() -> list[BatchRun]:
    with _connect() as conn:
        rows = conn.execute("SELECT data FROM batches").fetchall()
    batches = [BatchRun.model_validate_json(r["data"]) for r in rows]
    batches.sort(key=lambda b: b.created_at, reverse=True)
    return batches


def save_propagation(s: PropagationSuggestion) -> PropagationSuggestion:
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO propagations (id, data) VALUES (?, ?)",
            (s.id, s.model_dump_json()),
        )
    return s


def list_propagations(status: str | None = None) -> list[PropagationSuggestion]:
    with _connect() as conn:
        rows = conn.execute("SELECT data FROM propagations").fetchall()
    items = [PropagationSuggestion.model_validate_json(r["data"]) for r in rows]
    if status:
        items = [p for p in items if p.status == status]
    return items


def compute_dashboard(batch_id: str | None = None) -> DashboardStats:
    records = list_products(batch_id)
    stats = DashboardStats(total_products=len(records))
    high = med = low = 0
    approved = pending = 0
    conflicts = 0
    outliers = 0
    for r in records:
        conflicts += len([c for c in r.conflicts if not c.resolved])
        outliers += len(r.outliers or [])
        for fp in r.fields.values():
            stats.total_fields += 1
            if fp.confidence_score == ConfidenceBand.HIGH:
                high += 1
            elif fp.confidence_score == ConfidenceBand.MEDIUM:
                med += 1
            else:
                low += 1
            if fp.review_status in ("approved", "edited"):
                approved += 1
            else:
                pending += 1
    if stats.total_fields:
        stats.high_confidence_pct = round(100 * high / stats.total_fields, 1)
        stats.medium_confidence_pct = round(100 * med / stats.total_fields, 1)
        stats.low_confidence_pct = round(100 * low / stats.total_fields, 1)
    stats.fields_approved = approved
    stats.fields_pending = pending
    stats.conflicts_count = conflicts
    stats.propagations_applied = len([p for p in list_propagations("applied")])
    stats.estimated_minutes_saved = round(approved * 4.0 + high * 1.5, 1)
    stats.outliers_flagged = outliers
    try:
        from backend.app.services.knowledge_graph import kg_summary

        summary = kg_summary(limit=1)
        stats.kg_nodes = sum(summary.get("node_counts", {}).values())
    except Exception:
        stats.kg_nodes = 0
    return stats


def export_approved_json(path: Path) -> list[dict[str, Any]]:
    out = []
    for r in list_products():
        if r.status != "approved":
            continue
        row = {"sku": r.sku, "category_id": r.category_id}
        for k, v in r.fields.items():
            if v.review_status in ("approved", "edited"):
                row[k] = v.value
        out.append(row)
    path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    return out
