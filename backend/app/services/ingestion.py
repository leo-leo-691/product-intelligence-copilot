"""PDF / URL / image ingestion with page rasterization fallback."""
from __future__ import annotations

import logging
import re
from pathlib import Path

import httpx
import pdfplumber
from bs4 import BeautifulSoup

from backend.app.config import RASTER_DIR, settings
from backend.app.models.product import ProductInput

logger = logging.getLogger(__name__)


class ParsedDocument:
    def __init__(self):
        self.text: str = ""
        self.tables: list[list[list[str]]] = []
        self.source_locations: dict[str, str] = {}
        self.images: list[str] = []
        self.pdf_path: str | None = None
        self.was_sparse: bool = False


def parse_pdf(path: Path) -> ParsedDocument:
    doc = ParsedDocument()
    doc.pdf_path = str(path)
    parts: list[str] = []
    try:
        with pdfplumber.open(path) as pdf:
            for i, page in enumerate(pdf.pages, start=1):
                t = page.extract_text() or ""
                if t.strip():
                    parts.append(f"--- Page {i} ---\n{t}")
                tables = page.extract_tables() or []
                for ti, table in enumerate(tables):
                    doc.tables.append(table)
                    row_text = " | ".join(
                        " ".join(cell or "" for cell in row) for row in table
                    )
                    parts.append(f"[Table p{i} #{ti}] {row_text}")
    except Exception:
        logger.exception("pdfplumber failed for %s", path)
    doc.text = "\n\n".join(parts)
    return doc


def rasterize_pdf_pages(pdf_path: Path, sku: str, max_pages: int | None = None) -> list[str]:
    """Render PDF pages to PNG via pypdfium2 (no Poppler required)."""
    max_pages = max_pages or settings.pdf_raster_max_pages
    out_paths: list[str] = []
    try:
        import pypdfium2 as pdfium

        dest = RASTER_DIR / sku
        dest.mkdir(parents=True, exist_ok=True)
        pdf = pdfium.PdfDocument(str(pdf_path))
        n = min(len(pdf), max_pages)
        for i in range(n):
            page = pdf[i]
            bitmap = page.render(scale=2)
            pil = bitmap.to_pil()
            out = dest / f"page_{i + 1}.png"
            pil.save(out, format="PNG")
            out_paths.append(str(out))
            page.close()
        pdf.close()
        logger.info("Rasterized %s pages for %s", len(out_paths), sku)
    except Exception:
        logger.exception("PDF rasterization failed for %s", pdf_path)
    return out_paths


def parse_url(url: str) -> ParsedDocument:
    doc = ParsedDocument()
    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        r = client.get(url, headers={"User-Agent": "ProductIntelligenceCopilot/1.0"})
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "lxml")
        for tag in soup(["script", "style", "nav", "footer"]):
            tag.decompose()
        doc.text = soup.get_text(separator="\n", strip=True)
        doc.source_locations["url"] = url
    return doc


def ingest_product_input(inp: ProductInput, root: Path) -> ParsedDocument:
    doc = ParsedDocument()
    chunks: list[str] = []

    if inp.text:
        chunks.append(inp.text)
        doc.source_locations["text"] = "pasted"

    if inp.pdf_path:
        p = Path(inp.pdf_path)
        if not p.is_absolute():
            p = root / p
        if p.exists():
            pdf_doc = parse_pdf(p)
            chunks.append(pdf_doc.text)
            doc.tables.extend(pdf_doc.tables)
            doc.pdf_path = str(p)
            text_len = len((pdf_doc.text or "").strip())
            if text_len < settings.pdf_sparse_char_threshold:
                doc.was_sparse = True
                rasters = rasterize_pdf_pages(p, inp.sku)
                doc.images.extend(rasters)
                if rasters:
                    chunks.append(
                        f"[PDF sparse text ({text_len} chars); rasterized {len(rasters)} page(s) for VLM]"
                    )

    if inp.url:
        try:
            url_doc = parse_url(inp.url)
            chunks.append(url_doc.text)
            doc.source_locations.update(url_doc.source_locations)
        except Exception as e:
            chunks.append(f"[URL fetch failed: {e}]")

    if inp.image_path:
        p = Path(inp.image_path)
        if not p.is_absolute():
            p = root / p
        if p.exists():
            doc.images.append(str(p))
            chunks.append(f"[Image attached: {p.name}]")

    doc.text = "\n\n".join(chunks)
    if not doc.text.strip() and inp.text:
        doc.text = inp.text
    # Deduplicate images
    seen = set()
    uniq = []
    for img in doc.images:
        if img not in seen:
            seen.add(img)
            uniq.append(img)
    doc.images = uniq
    return doc


def guess_source_template(text: str) -> str | None:
    m = re.search(r"SOURCE_TEMPLATE:\s*(\S+)", text, re.I)
    if m:
        return m.group(1)
    if "AcmeFlow Valve Series A" in text:
        return "acmeflow_valve_series_a"
    if "PrecisionRoll Bearing" in text:
        return "precisionroll_bearing_std"
    if "DriveMax Motor" in text:
        return "drivemax_motor_std"
    if "BoltPro Fastener" in text:
        return "boltpro_fastener_std"
    return None
