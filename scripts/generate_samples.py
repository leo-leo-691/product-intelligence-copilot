#!/usr/bin/env python3
"""Generate synthetic datasheet text + simple PDF samples for the demo corpus."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEXT = ROOT / "data" / "samples" / "text"
PDF = ROOT / "data" / "samples" / "pdf"
TEXT.mkdir(parents=True, exist_ok=True)
PDF.mkdir(parents=True, exist_ok=True)

VALVE_TEMPLATE = """SOURCE_TEMPLATE: acmeflow_valve_series_a
AcmeFlow Valve Series A — Datasheet
SKU: {sku}
Manufacturer: AcmeFlow Industries
Model Number: {sku}
Valve Type: Ball
Nominal Size (in): {size}
Pressure Class: ANSI 150
Body Material: WCB
Max Operating Pressure (psi): 250
Temperature Range F: -20 to 400
End Connection: RF Flanged
"""

VALVE_CONFLICT = """SOURCE_TEMPLATE: acmeflow_valve_series_a
AcmeFlow Valve Series A — Datasheet
SKU: VALVE-CONFLICT-001
Manufacturer: AcmeFlow Industries
Model Number: VALVE-CONFLICT-001
Valve Type: Gate
Nominal Size (in): 3
Pressure Class: ANSI 300
Body Material: CF8M
Max Operating Pressure (psi): 250
"""

VALVE_SPARSE = """SOURCE_TEMPLATE: acmeflow_valve_series_a
AcmeFlow Valve Series A — partial listing
SKU: VALVE-SPARSE-001
Manufacturer: AcmeFlow Industries
Model Number: VALVE-SPARSE-001
Valve Type: Check
Nominal Size (in): 1.5
"""

BEARING_TEMPLATE = """SOURCE_TEMPLATE: precisionroll_bearing_std
PrecisionRoll Bearing — Catalog excerpt
Part Number: {sku}
Manufacturer: PrecisionRoll
Bearing Type: Deep Groove Ball
Bore mm: {bore}
Outer Diameter mm: {od}
Width mm: {width}
Dynamic Load kN: {load}
Max rpm: {rpm}
"""

SENSOR_TEMPLATE = """SenseTek Pressure Transmitter
Model Number: {sku}
Manufacturer: SenseTek
Sensor Type: Pressure
Measurement Range: 0-100 bar
Output Signal: 4-20 mA
Supply Voltage V: 24
Accuracy Percent: 0.25
Operating Temp C: -40 to 85
IP Rating: IP67
"""


def write_pdf(path: Path, text: str) -> None:
    """Minimal PDF writer without external deps (ASCII text pages)."""
    # Escape PDF string specials
    safe = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    lines = safe.splitlines()[:45]
    content_lines = ["BT", "/F1 10 Tf", "50 780 Td", "12 TL"]
    first = True
    for line in lines:
        if not first:
            content_lines.append("T*")
        content_lines.append(f"({line[:110]}) Tj")
        first = False
    content_lines.append("ET")
    stream = "\n".join(content_lines).encode("latin-1", errors="replace")

    objects: list[bytes] = []
    objects.append(b"1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj\n")
    objects.append(b"2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1 >>endobj\n")
    objects.append(
        b"3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>endobj\n"
    )
    objects.append(
        f"4 0 obj<< /Length {len(stream)} >>stream\n".encode("ascii")
        + stream
        + b"\nendstream\nendobj\n"
    )
    objects.append(b"5 0 obj<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>endobj\n")

    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objects:
        offsets.append(len(out))
        out.extend(obj)
    xref_pos = len(out)
    out.extend(f"xref\n0 {len(objects)+1}\n".encode("ascii"))
    out.extend(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        out.extend(f"{off:010d} 00000 n \n".encode("ascii"))
    out.extend(
        f"trailer<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode(
            "ascii"
        )
    )
    path.write_bytes(bytes(out))


sizes = [1, 1.5, 2, 2.5, 3, 4, 6, 8]
for i, sku in enumerate([f"VALVE-A-{n:03d}" for n in range(1, 9)], start=0):
    body = VALVE_TEMPLATE.format(sku=sku, size=sizes[i % len(sizes)])
    (TEXT / f"valve_acmeflow_{i+1:03d}.txt").write_text(body, encoding="utf-8")
    if i == 0:
        write_pdf(PDF / "valve_acmeflow_001.pdf", body)

(TEXT / "valve_conflict_001.txt").write_text(VALVE_CONFLICT, encoding="utf-8")
write_pdf(PDF / "valve_conflict_001.pdf", VALVE_CONFLICT)
(TEXT / "valve_sparse_001.txt").write_text(VALVE_SPARSE, encoding="utf-8")

for i, sku in enumerate([f"BEAR-P-{n}" for n in range(101, 106)], start=1):
    bore = 20 + i * 5
    body = BEARING_TEMPLATE.format(
        sku=sku, bore=bore, od=bore + 15, width=12 + i, load=10 + i, rpm=8000 - i * 200
    )
    (TEXT / f"bearing_{100+i}.txt").write_text(body, encoding="utf-8")

for i, sku in enumerate([f"SENS-T-{n}" for n in range(201, 206)], start=1):
    (TEXT / f"sensor_{200+i}.txt").write_text(SENSOR_TEMPLATE.format(sku=sku), encoding="utf-8")

print(f"Wrote sample texts to {TEXT}")
print(f"Wrote sample PDFs to {PDF}")
