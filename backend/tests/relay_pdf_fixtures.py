"""Tiny hand-built PDFs for relay-import extraction tests (no PDF writer dep).

Text is placed at explicit x positions so the extractor's layout mode sees
real column gaps, like a settings table. Latin-1 text only (standard font).
"""

from __future__ import annotations

_COLUMN_X = (40, 230, 340, 450)


def _escape(text: str) -> bytes:
    raw = text.encode("latin-1")
    return raw.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


def rows_page(rows: list[list[str]]) -> list[tuple[int, int, str]]:
    """One page of text rows; each row's cells go into successive columns."""
    items: list[tuple[int, int, str]] = []
    y = 780
    for row in rows:
        for cell, x in zip(row, _COLUMN_X, strict=False):
            items.append((x, y, cell))
        y -= 16
    return items


def build_pdf(pages: list, *, pad: int = 0) -> bytes:
    """pages: each a list of (x, y, text) items, or the string "image" for a
    page whose only content is an image (no text layer). `pad` inserts a PDF
    comment of that many bytes (valid PDF, used for size tests)."""
    objects: list[bytes] = []

    def add(body: bytes) -> int:
        objects.append(body)
        return len(objects)

    add(b"<< /Type /Catalog /Pages 2 0 R >>")  # 1
    add(b"")  # 2 placeholder (pages tree)
    add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")  # 3
    image = add(
        b"<< /Type /XObject /Subtype /Image /Width 1 /Height 1 /ColorSpace /DeviceGray "
        b"/BitsPerComponent 8 /Length 1 >>\nstream\n\x80\nendstream"
    )  # 4
    kids = []
    for page in pages:
        if page == "image":
            content = b"q 100 0 0 100 50 600 cm /Im1 Do Q"
        else:
            parts = [b"BT /F1 10 Tf"]
            for x, y, text in page:
                parts.append(b"1 0 0 1 %d %d Tm (" % (x, y) + _escape(text) + b") Tj")
            parts.append(b"ET")
            content = b"\n".join(parts)
        stream = add(b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream")
        kids.append(
            add(
                b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 842] "
                b"/Resources << /Font << /F1 3 0 R >> /XObject << /Im1 %d 0 R >> >> /Contents %d 0 R >>"
                % (image, stream)
            )
        )
    objects[1] = b"<< /Type /Pages /Count %d /Kids [%s] >>" % (
        len(kids),
        b" ".join(b"%d 0 R" % k for k in kids),
    )
    out = bytearray(b"%PDF-1.4\n")
    if pad:
        out += b"%" + b"0" * pad + b"\n"
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    return bytes(out)


def simple_pdf(rows: list[list[str]] | None = None, **kwargs) -> bytes:
    return build_pdf([rows_page(rows or [["R1", "1.84", "0-655.35"]])], **kwargs)
