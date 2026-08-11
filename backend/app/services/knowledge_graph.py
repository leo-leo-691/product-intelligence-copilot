"""Lightweight catalog knowledge graph in SQLite (no Neo4j required)."""
from __future__ import annotations

import json
import sqlite3
from typing import Any
from uuid import uuid4

from backend.app.config import DB_PATH, settings
from backend.app.models.product import ProductRecord


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def init_kg() -> None:
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS kg_nodes (
                id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                label TEXT NOT NULL,
                props JSON NOT NULL
            );
            CREATE TABLE IF NOT EXISTS kg_edges (
                id TEXT PRIMARY KEY,
                src TEXT NOT NULL,
                dst TEXT NOT NULL,
                rel TEXT NOT NULL,
                props JSON NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_kg_edges_src ON kg_edges(src);
            CREATE INDEX IF NOT EXISTS idx_kg_edges_dst ON kg_edges(dst);
            """
        )


def _upsert_node(conn: sqlite3.Connection, node_id: str, kind: str, label: str, props: dict) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO kg_nodes (id, kind, label, props) VALUES (?, ?, ?, ?)",
        (node_id, kind, label, json.dumps(props)),
    )


def _add_edge(conn: sqlite3.Connection, src: str, dst: str, rel: str, props: dict | None = None) -> None:
    conn.execute(
        "INSERT INTO kg_edges (id, src, dst, rel, props) VALUES (?, ?, ?, ?, ?)",
        (str(uuid4()), src, dst, rel, json.dumps(props or {})),
    )


def upsert_product_graph(record: ProductRecord) -> dict[str, Any]:
    if not settings.kg_enabled:
        return {"enabled": False}
    init_kg()
    product_node = f"product:{record.sku}"
    cat_node = f"category:{record.category_id}"
    mfr_fp = record.fields.get("manufacturer")
    mfr = None if not mfr_fp or mfr_fp.not_found else str(mfr_fp.value)
    mfr_node = f"manufacturer:{mfr}" if mfr else None

    with _connect() as conn:
        _upsert_node(
            conn,
            product_node,
            "product",
            record.sku,
            {"category_id": record.category_id, "status": record.status, "id": record.id},
        )
        _upsert_node(conn, cat_node, "category", record.category_id, {})
        _add_edge(conn, product_node, cat_node, "IN_CATEGORY")
        if mfr_node and mfr:
            _upsert_node(conn, mfr_node, "manufacturer", mfr, {})
            _add_edge(conn, product_node, mfr_node, "MADE_BY")
        if record.source_template_id:
            tmpl = f"template:{record.source_template_id}"
            _upsert_node(conn, tmpl, "template", record.source_template_id, {})
            _add_edge(conn, product_node, tmpl, "USES_TEMPLATE")
        for fname, fp in record.fields.items():
            if fp.not_found or fp.value is None:
                continue
            field_node = f"field:{record.sku}:{fname}"
            _upsert_node(
                conn,
                field_node,
                "field",
                fname,
                {"value": fp.value, "confidence": fp.confidence_score.value},
            )
            _add_edge(conn, product_node, field_node, "HAS_FIELD")

    return {"enabled": True, "product_node": product_node, "manufacturer": mfr}


def kg_summary(limit: int = 50) -> dict[str, Any]:
    init_kg()
    with _connect() as conn:
        nodes = conn.execute(
            "SELECT kind, COUNT(*) AS c FROM kg_nodes GROUP BY kind"
        ).fetchall()
        edges = conn.execute(
            "SELECT rel, COUNT(*) AS c FROM kg_edges GROUP BY rel"
        ).fetchall()
        sample = conn.execute(
            "SELECT id, kind, label FROM kg_nodes LIMIT ?", (limit,)
        ).fetchall()
    return {
        "node_counts": {r["kind"]: r["c"] for r in nodes},
        "edge_counts": {r["rel"]: r["c"] for r in edges},
        "sample_nodes": [{"id": r["id"], "kind": r["kind"], "label": r["label"]} for r in sample],
    }


def kg_neighbors(node_id: str, limit: int = 40) -> dict[str, Any]:
    init_kg()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT e.rel, e.dst AS other, n.kind, n.label
            FROM kg_edges e
            JOIN kg_nodes n ON n.id = e.dst
            WHERE e.src = ?
            LIMIT ?
            """,
            (node_id, limit),
        ).fetchall()
        rows2 = conn.execute(
            """
            SELECT e.rel, e.src AS other, n.kind, n.label
            FROM kg_edges e
            JOIN kg_nodes n ON n.id = e.src
            WHERE e.dst = ?
            LIMIT ?
            """,
            (node_id, limit),
        ).fetchall()
    return {
        "node_id": node_id,
        "outgoing": [dict(r) for r in rows],
        "incoming": [dict(r) for r in rows2],
    }
