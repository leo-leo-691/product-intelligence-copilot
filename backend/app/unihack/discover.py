"""Locate official UniHack files without inventing datasets."""

from __future__ import annotations

from pathlib import Path

from backend.app.config import DATA_DIR, ROOT, STORAGE_DIR
from backend.app.unihack.constants import FILE_ALIASES, MISSING_FILE_HINTS

UNIHACK_DATA = DATA_DIR / "unihack"
UNIHACK_UPLOADS = STORAGE_DIR / "unihack"


def search_roots() -> list[Path]:
    return [
        UNIHACK_DATA,
        UNIHACK_UPLOADS,
        DATA_DIR,
        ROOT,
        ROOT / "challenge",
        ROOT / "datasets",
    ]


def _norm_name(path: Path) -> str:
    return path.name.lower().replace(" ", "_").replace("-", "_")


def _kind_match(kind: str, path: Path) -> bool:
    n = _norm_name(path)
    aliases = FILE_ALIASES.get(kind, ())
    if n in aliases:
        return True
    stem = path.stem.lower().replace(" ", "_").replace("-", "_")
    if any(stem == a.rsplit(".", 1)[0] for a in aliases):
        return True
    suffix = path.suffix.lower()
    if suffix not in {".csv", ".xlsx", ".xls"}:
        return False
    if kind == "input_1000":
        return "sample" in n and "input" in n and "vs" not in n and "output" not in n
    if kind == "expected_output":
        return ("expected" in n and "output" in n) or ("delivery" in n and "format" in n)
    if kind == "ground_truth_200":
        return "200" in n and ("input" in n and "output" in n or "ground" in n)
    return False


def find_file(kind: str) -> Path | None:
    hits: list[Path] = []
    for root in search_roots():
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file() and _kind_match(kind, path):
                hits.append(path)
    if not hits:
        return None

    def _rank(path: Path) -> tuple[int, int]:
        n = _norm_name(path)
        if path.is_relative_to(UNIHACK_UPLOADS):
            return (-1, len(path.name))
        if "delivery_format" in n or "sample_dataset" in n:
            return (0, len(path.name))
        if "expected_output" in n or "sample" in n and "input" in n:
            return (1, len(path.name))
        return (2, len(path.name))

    hits.sort(key=_rank)
    return hits[0]


def missing_hint(kind: str) -> str:
    return MISSING_FILE_HINTS.get(kind, f"MISSING INPUT: {kind}")


def find_delivery_schema() -> Path | None:
    return (
        find_file("expected_output")
        or find_file("ground_truth_200")
        or next(
            (
                p
                for root in search_roots()
                if root.exists()
                for p in root.rglob("*")
                if p.is_file()
                and "expected" in _norm_name(p)
                and p.suffix.lower() in {".csv", ".xlsx"}
            ),
            None,
        )
    )


def inventory() -> dict[str, dict[str, str | None | bool]]:
    out: dict[str, dict[str, str | None | bool]] = {}
    kinds = list(FILE_ALIASES) + ["delivery_schema"]
    for kind in kinds:
        path = find_file(kind) if kind != "delivery_schema" else find_delivery_schema()
        out[kind] = {
            "present": path is not None,
            "path": str(path) if path else None,
            "missing_hint": None if path else missing_hint(kind),
        }
    return out
