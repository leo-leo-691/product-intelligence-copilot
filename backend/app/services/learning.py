"""Log human corrections for active-learning style prompt hints (no model fine-tune)."""
from __future__ import annotations

import json
import sqlite3
from typing import Any
from uuid import uuid4

from backend.app.config import DB_PATH


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def init_learning() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS correction_log (
                id TEXT PRIMARY KEY,
                sku TEXT,
                category_id TEXT,
                source_template_id TEXT,
                field_name TEXT,
                old_value TEXT,
                new_value TEXT,
                created_at TEXT
            )
            """
        )


def log_correction(
    *,
    sku: str,
    category_id: str,
    source_template_id: str | None,
    field_name: str,
    old_value: Any,
    new_value: Any,
) -> None:
    init_learning()
    from backend.app.models.product import utc_now

    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO correction_log
            (id, sku, category_id, source_template_id, field_name, old_value, new_value, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid4()),
                sku,
                category_id,
                source_template_id,
                field_name,
                json.dumps(old_value, default=str),
                json.dumps(new_value, default=str),
                utc_now(),
            ),
        )


def recent_corrections(limit: int = 50) -> list[dict[str, Any]]:
    init_learning()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM correction_log ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


def hints_for_template(source_template_id: str | None, field_name: str) -> list[str]:
    """Return past corrections as extraction hints for similar templates."""
    if not source_template_id:
        return []
    init_learning()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT old_value, new_value FROM correction_log
            WHERE source_template_id = ? AND field_name = ?
            ORDER BY created_at DESC LIMIT 5
            """,
            (source_template_id, field_name),
        ).fetchall()
    hints = []
    for r in rows:
        hints.append(f"Previously corrected {field_name}: {r['old_value']} → {r['new_value']}")
    return hints
