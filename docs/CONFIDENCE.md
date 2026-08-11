# Confidence scoring

**One sentence:** Confidence is a weighted blend of extraction-method reliability, cross-source agreement, validation outcome, and format match — never a raw LLM self-score.

## Formula

```
raw = 0.35 * method_reliability
    + 0.25 * cross_source_agreement
    + 0.25 * validation_score
    + 0.15 * format_match
```

If validation fails, `raw` is capped at `0.44` (cannot be High).

| Band | Rule |
|------|------|
| High | `raw >= 0.75` and not failed / not missing |
| Medium | `raw >= 0.45` |
| Low | otherwise, or not found / validation fail |

## Method reliability baselines

| Method | Weight |
|--------|--------|
| table-parse | 1.00 |
| text-LLM | 0.75 |
| mock / labeled demo parse | 0.70 |
| vision-LLM | 0.65 |
| web-agent | 0.50 |

## Agreement

- Same value in 2+ independent sources → agreement `1.0` (boost)
- Disagreeing sources → agreement `0.0` (and conflict UI)
- Single source → `0.5`

Reasoning components are stored per field as `confidence_reasoning` and shown in the Review UI.
