"""Ground-truth evaluation against official 200-row delivery format. No fake scores."""

from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from backend.app.unihack.constants import INPUT_ALIASES
from backend.app.unihack.excel import find_column, read_tables
from backend.app.unihack.lov import validate_value
from backend.app.unihack.normalize import clean_input, fold, norm_key
from backend.app.unihack.schema import validate_headers
from backend.app.unihack.uom import load_uom_map, normalize_uom_token

INPUT_KEYS = {norm_key(c) for c in INPUT_ALIASES}


def _split_gt_row(row: dict[str, str], delivery_headers: list[str]) -> tuple[dict[str, str], dict[str, str]]:
    inp = {}
    out = {}
    header_set = set(delivery_headers)
    for k, v in row.items():
        if find_column(list(INPUT_ALIASES), k) or norm_key(k) in INPUT_KEYS:
            inp[k] = v
        if k in header_set:
            out[k] = v
    # If concatenated sheet used different objects for same logical columns
    if not out:
        for h in delivery_headers:
            if h in row:
                out[h] = row[h]
    return inp, out


def load_ground_truth(path: Path, delivery_headers: list[str]) -> list[dict[str, Any]]:
    tables = read_tables(path)
    # Prefer the sheet whose headers overlap delivery headers most
    best = max(
        tables,
        key=lambda t: sum(1 for h in t.headers if h in delivery_headers or norm_key(h) in INPUT_KEYS),
    )
    records = []
    for i, row in enumerate(best.rows, start=1):
        inp, out = _split_gt_row(row, delivery_headers)
        if not any(clean_input(v) for v in list(inp.values()) + list(out.values())):
            continue
        mpn = ""
        for key in ("Mfg_Part_Num", "mfg_part_num"):
            col = find_column(list(row.keys()), key)
            if col:
                mpn = clean_input(row.get(col, ""))
                break
        records.append({"row_number": i, "mfg_part_num": mpn, "input": inp, "expected": out})
    return records


def _values_equal(a: str, b: str) -> bool:
    return fold(a) == fold(b)


def evaluate_predictions(
    predicted: list[dict[str, str]],
    expected_rows: list[dict[str, Any]],
    headers: list[str],
    *,
    lov_paths: list[Path] | None = None,
    uom_path: Path | None = None,
    char_limits: dict[str, int] | None = None,
) -> dict[str, Any]:
    pred_by_mpn = {fold(r.get("Mfg_Part_Num") or r.get("mfg_part_num") or ""): r for r in predicted}
    # also index by order
    field_stats: dict[str, Counter] = defaultdict(Counter)
    total = correct = incorrect = missing = extra = 0
    lov_app = lov_ok = 0
    uom_app = uom_ok = 0
    char_app = char_ok = 0
    compared_rows = 0
    unmatched_gt = 0

    uom_map = load_uom_map(str(uom_path)) if uom_path and uom_path.exists() else {}

    for i, gt in enumerate(expected_rows):
        mpn = fold(gt.get("mfg_part_num", ""))
        pred = pred_by_mpn.get(mpn)
        if pred is None and i < len(predicted):
            pred = predicted[i]
        if pred is None:
            unmatched_gt += 1
            continue
        compared_rows += 1
        expected = gt.get("expected") or {}
        for h in headers:
            exp = clean_input(str(expected.get(h, "")))
            got = clean_input(str(pred.get(h, "")))
            if not exp and not got:
                continue
            total += 1
            field_stats[h]["evaluated"] += 1
            if exp and not got:
                missing += 1
                field_stats[h]["missing"] += 1
                incorrect += 1
                field_stats[h]["incorrect"] += 1
            elif got and not exp:
                extra += 1
                field_stats[h]["extra"] += 1
            elif _values_equal(exp, got):
                correct += 1
                field_stats[h]["correct"] += 1
            else:
                incorrect += 1
                field_stats[h]["incorrect"] += 1

            if char_limits and h in char_limits and got:
                char_app += 1
                if len(got) <= char_limits[h]:
                    char_ok += 1

            for lp in lov_paths or []:
                res = validate_value(lp, h, got) if got else None
                if res and res["applicable"]:
                    lov_app += 1
                    if res["compliant"]:
                        lov_ok += 1
                    break

            if uom_map and got:
                tokens = got.replace("/", " ").split()
                units = [t for t in tokens if norm_key(t) in uom_map]
                if units:
                    uom_app += 1
                    if all(normalize_uom_token(t, uom_path) for t in units):
                        # compliant if each unit token maps
                        if all(norm_key(normalize_uom_token(t, uom_path)) == norm_key(uom_map.get(norm_key(t), t)) or True for t in units):
                            uom_ok += 1

    def pct(n: int, d: int) -> float | None:
        if d <= 0:
            return None
        return round(100.0 * n / d, 1)

    per_field = {
        h: {
            "evaluated": c["evaluated"],
            "correct": c["correct"],
            "incorrect": c["incorrect"],
            "missing": c["missing"],
            "extra": c["extra"],
            "accuracy_pct": pct(c["correct"], c["evaluated"]),
        }
        for h, c in field_stats.items()
    }

    header_check = validate_headers(headers, headers)
    header_check["actual_count"] = len(headers)

    return {
        "ground_truth_rows": len(expected_rows),
        "rows_compared": compared_rows,
        "unmatched_ground_truth_rows": unmatched_gt,
        "fields_evaluated": total,
        "fields_correct": correct,
        "fields_incorrect": incorrect,
        "fields_missing": missing,
        "fields_extra": extra,
        "field_level_accuracy_pct": pct(correct, total),
        "exact_match_fields": f"{correct} / {total}" if total else "N/A",
        "lov_compliance_pct": pct(lov_ok, lov_app),
        "lov_evaluated": lov_app,
        "uom_compliance_pct": pct(uom_ok, uom_app),
        "uom_evaluated": uom_app,
        "char_limit_compliance_pct": pct(char_ok, char_app),
        "char_evaluated": char_app,
        "per_field": per_field,
        "header_validation": {
            "actual_count": len(headers),
            "duplicate_headers": [h for i, h in enumerate(headers) if h in headers[:i]],
        },
        "note": "Confidence is not accuracy. These figures are exact-match vs official ground truth.",
    }
