# Sample corpus

- `manifest.json` — 20 demo SKUs for batch ingest
- `text/` — labeled datasheet text (deterministic extract without API keys)
- `pdf/` — generated sample PDFs (`valve_acmeflow_001.pdf`, `valve_conflict_001.pdf`)

Regenerate with:

```bash
python scripts/generate_samples.py
```

Drop real manufacturer PDFs into `pdf/` and add `pdf_file` entries in the manifest for live PDF demos.
