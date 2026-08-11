import re
from pathlib import Path
from urllib.parse import urlparse

import httpx
import pdfplumber
from bs4 import BeautifulSoup

from backend.app.models.product import ProductInput


class ParsedDocument:
    def __init__(self):
        self.text: str = ""
        self.tables: list[list[list[str]]] = []
        self.source_locations: dict[str, str] = {}
        self.images: list[str] = []


def parse_pdf(path: Path) -> ParsedDocument:
    doc = ParsedDocument()
    parts: list[str] = []
    with pdfplumber.open(path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            t = page.extract_text() or ""
            if t.strip():
                parts.append(f"--- Page {i} ---\n{t}")
            tables = page.extract_tables() or []
            for ti, table in enumerate(tables):
                doc.tables.append(table)
                row_text = " | ".join(" ".join(cell or "" for cell in row) for row in table)
                parts.append(f"[Table p{i} #{ti}] {row_text}")
    doc.text = "\n\n".join(parts)
    return doc


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
    return doc


def guess_source_template(text: str) -> str | None:
    m = re.search(r"SOURCE_TEMPLATE:\s*(\S+)", text, re.I)
    if m:
        return m.group(1)
    if "AcmeFlow Valve Series A" in text:
        return "acmeflow_valve_series_a"
    if "PrecisionRoll Bearing" in text:
        return "precisionroll_bearing_std"
    return None
