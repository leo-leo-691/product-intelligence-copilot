"""Similar-product consistency / outlier checks within a category."""
from __future__ import annotations

import statistics
from typing import Any

from backend.app.config import settings
from backend.app.models.product import ProductRecord
from backend.app.schemas.categories import CATEGORIES
from backend.app.schemas.fields import FieldProvenance


def detect_outliers(
    category_id: str,
    fields: dict[str, FieldProvenance],
    peers: list[ProductRecord],
    sku: str,
) -> list[dict[str, Any]]:
    """Flag numeric fields that are statistical outliers vs category peers."""
    schema = CATEGORIES.get(category_id)
    if not schema or len(peers) < 3:
        return []

    outliers: list[dict[str, Any]] = []
    thr = settings.outlier_z_threshold

    for fdef in schema.fields:
        if fdef.type != "number":
            continue
        fp = fields.get(fdef.name)
        if not fp or fp.not_found or fp.value is None:
            continue
        try:
            val = float(fp.value)
        except (TypeError, ValueError):
            continue

        peer_vals: list[float] = []
        for p in peers:
            if p.sku == sku or p.category_id != category_id:
                continue
            pf = p.fields.get(fdef.name)
            if not pf or pf.not_found or pf.value is None:
                continue
            try:
                peer_vals.append(float(pf.value))
            except (TypeError, ValueError):
                continue

        if len(peer_vals) < 3:
            continue

        mean = statistics.mean(peer_vals)
        stdev = statistics.pstdev(peer_vals)
        if stdev <= 0:
            # Flag extreme multiples of mean
            if mean > 0 and (val > mean * 10 or val < mean / 10):
                outliers.append(
                    {
                        "field_name": fdef.name,
                        "value": val,
                        "peer_mean": round(mean, 4),
                        "peer_count": len(peer_vals),
                        "z_score": None,
                        "message": (
                            f"{fdef.name}={val} is ~{val / mean:.1f}x the category mean ({mean:.4g}) — verify"
                        ),
                    }
                )
            continue

        z = (val - mean) / stdev
        if abs(z) >= thr:
            outliers.append(
                {
                    "field_name": fdef.name,
                    "value": val,
                    "peer_mean": round(mean, 4),
                    "peer_stdev": round(stdev, 4),
                    "peer_count": len(peer_vals),
                    "z_score": round(z, 2),
                    "message": (
                        f"{fdef.name}={val} is {abs(z):.1f}σ from category mean {mean:.4g} — verify"
                    ),
                }
            )
    return outliers
