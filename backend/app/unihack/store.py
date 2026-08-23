"""SQLite persistence for UniHack jobs — separate from the 26-product demo tables."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from backend.app.config import DB_PATH

_DDL = """
CREATE TABLE IF NOT EXISTS unihack_jobs (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    created_at TEXT,
    completed_at TEXT,
    data JSON NOT NULL
);
CREATE TABLE IF NOT EXISTS unihack_rows (
    job_id TEXT NOT NULL,
    row_number INTEGER NOT NULL,
    mfg_part_num TEXT,
    status TEXT,
    data JSON NOT NULL,
    PRIMARY KEY (job_id, row_number)
);
CREATE TABLE IF NOT EXISTS unihack_evals (
    job_id TEXT PRIMARY KEY,
    data JSON NOT NULL
);
"""


def init_unihack_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.executescript(_DDL)


def save_job(job: dict[str, Any]) -> None:
    init_unihack_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO unihack_jobs (id, status, created_at, completed_at, data)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                job["id"],
                job.get("status", "QUEUED"),
                job.get("created_at"),
                job.get("completed_at"),
                json.dumps(job),
            ),
        )


def get_job(job_id: str) -> dict[str, Any] | None:
    init_unihack_db()
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute("SELECT data FROM unihack_jobs WHERE id = ?", (job_id,)).fetchone()
    return json.loads(row[0]) if row else None


def latest_job() -> dict[str, Any] | None:
    init_unihack_db()
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT data FROM unihack_jobs ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
    return json.loads(row[0]) if row else None


def save_row(job_id: str, row: dict[str, Any]) -> None:
    init_unihack_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO unihack_rows (job_id, row_number, mfg_part_num, status, data)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                job_id,
                int(row.get("row_number") or 0),
                row.get("mfg_part_num"),
                row.get("status"),
                json.dumps(row),
            ),
        )


def list_rows(job_id: str) -> list[dict[str, Any]]:
    init_unihack_db()
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT data FROM unihack_rows WHERE job_id = ? ORDER BY row_number",
            (job_id,),
        ).fetchall()
    return [json.loads(r[0]) for r in rows]


def save_eval(job_id: str, payload: dict[str, Any]) -> None:
    init_unihack_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO unihack_evals (job_id, data) VALUES (?, ?)",
            (job_id, json.dumps(payload)),
        )


def get_eval(job_id: str) -> dict[str, Any] | None:
    init_unihack_db()
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute("SELECT data FROM unihack_evals WHERE job_id = ?", (job_id,)).fetchone()
    return json.loads(row[0]) if row else None
