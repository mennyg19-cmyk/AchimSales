"""Minimal PDF builder for Customer's Last Order (no third-party PDF deps).

Produces a one-page-ish multi-page text PDF with a simple item table. Enough for
a salesman to print/email; not a design system.
"""

from __future__ import annotations

from io import BytesIO


def last_order_pdf(
    *,
    customer_name: str,
    account: str,
    primary: dict,
    display_po: str,
    lines: list[dict],
    totals: dict,
) -> bytes:
    pages: list[list[str]] = []
    lines_out: list[str] = [
        f"Customer's Last Order — {customer_name or account}",
        f"Account: {account}",
        f"Order: {primary.get('order_number') or '—'}"
        f"    Date: {primary.get('order_date') or '—'}"
        + (f"    PO: {display_po}" if display_po else ""),
        "",
        f"{'Item #':<14} {'Description':<32} {'Ord':>7} {'Ship':>7} {'Can':>7} {'Price':>10} {'Total':>10}",
        "-" * 94,
    ]
    for row in lines:
        desc = str(row.get("description") or "")[:32]
        lines_out.append(
            f"{str(row.get('item') or ''):<14} {desc:<32} "
            f"{_g(row.get('qty_ordered')):>7} {_g(row.get('qty_shipped')):>7} "
            f"{_g(row.get('qty_cancelled')):>7} "
            f"{_money(row.get('sales_price')):>10} {_money(row.get('total')):>10}"
        )
    lines_out.append("-" * 94)
    lines_out.append(
        f"{'TOTALS':<47} {_g(totals.get('qty_ordered')):>7} "
        f"{_g(totals.get('qty_shipped')):>7} {_g(totals.get('qty_cancelled')):>7} "
        f"{'':>10} {_money(totals.get('total')):>10}"
    )

    # ~50 content lines per page
    chunk = 50
    for i in range(0, len(lines_out), chunk):
        pages.append(lines_out[i:i + chunk])
    return _write_pdf(pages)


def _g(v) -> str:
    try:
        n = float(v or 0)
        return f"{n:g}"
    except (TypeError, ValueError):
        return ""


def _money(v) -> str:
    try:
        return f"${float(v or 0):,.2f}"
    except (TypeError, ValueError):
        return ""


def _pdf_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _write_pdf(pages: list[list[str]]) -> bytes:
    """Very small PDF 1.4 writer: Helvetica text, one content stream per page."""
    out = BytesIO()
    offsets: list[int] = []

    def w(data: bytes | str) -> None:
        if isinstance(data, str):
            data = data.encode("latin-1", errors="replace")
        out.write(data)

    w("%PDF-1.4\n")
    # Object 1: catalog
    offsets.append(out.tell())
    w("1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj\n")

    kids = " ".join(f"{3 + i * 2} 0 R" for i in range(len(pages)))
    offsets.append(out.tell())
    w(f"2 0 obj<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>endobj\n")

    for i, page_lines in enumerate(pages):
        page_obj = 3 + i * 2
        content_obj = page_obj + 1
        # Build content stream
        y = 770
        parts = ["BT /F1 9 Tf 40 770 Td 12 TL"]
        first = True
        for line in page_lines:
            esc = _pdf_escape(line)
            if first:
                parts.append(f"({esc}) Tj")
                first = False
            else:
                parts.append(f"T* ({esc}) Tj")
        parts.append("ET")
        stream = "\n".join(parts).encode("latin-1", errors="replace")

        offsets.append(out.tell())
        w(
            f"{page_obj} 0 obj<< /Type /Page /Parent 2 0 R "
            f"/MediaBox [0 0 612 792] /Contents {content_obj} 0 R "
            f"/Resources << /Font << /F1 {3 + len(pages) * 2} 0 R >> >> >>endobj\n"
        )
        offsets.append(out.tell())
        w(f"{content_obj} 0 obj<< /Length {len(stream)} >>stream\n")
        w(stream)
        w("\nendstream\nendobj\n")

    font_obj = 3 + len(pages) * 2
    offsets.append(out.tell())
    w(f"{font_obj} 0 obj<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>endobj\n")

    xref = out.tell()
    w(f"xref\n0 {len(offsets) + 1}\n")
    w("0000000000 65535 f \n")
    for off in offsets:
        w(f"{off:010d} 00000 n \n")
    w(f"trailer<< /Size {len(offsets) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n")
    return out.getvalue()
