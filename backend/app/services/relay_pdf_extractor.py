"""Generic, relay/OEM-neutral PDF text extraction into a `RawRelayDocument`.

Relay Import Slice 4. Responsibility: turn the text layer of a PDF into
neutral raw entries with page provenance. It knows nothing about relays: it
never decides what a label *means*, which manufacturer wrote the document,
or which protection function a row belongs to. Every detection below is
*syntactic* (layout, punctuation, a closed table of unit symbols) -- relay
knowledge belongs to profiles in later slices.

Library: pypdf (pure Python, BSD, maintained; no rendering/OCR stack). The
layout extraction mode keeps horizontal gaps, which is what lets a
"label ........ value" row be split into cells without guessing.

Inputs are bytes in memory; nothing is written anywhere and document
content is never logged. Output is deterministic for a given file.
"""

from __future__ import annotations

import io
import logging
import math
import re
from collections import Counter
from dataclasses import dataclass
from enum import StrEnum

from app.domain.relay_import.raw_document import (
    ExtractionProvenance,
    RawRelayDocument,
    RawSetting,
    SettingRange,
    SourceFormat,
    SourceLocation,
)

logger = logging.getLogger(__name__)

EXTRACTOR_ID = "generic_pdf_text"
EXTRACTOR_VERSION = "2"

#: Defensive bounds (pathological documents). Reaching one is reported as a
#: warning; the entries extracted so far are kept.
MAX_PAGES = 400
MAX_ENTRIES = 50_000
MAX_LINE_CHARS = 2_000
#: Page furniture (repeated header/footer text) is only searched near the
#: page edges.
_FURNITURE_TOP_LINES = 6
_FURNITURE_BOTTOM_LINES = 3
_MAX_HINTS = 10


class PdfExtractionStatus(StrEnum):
    TEXT_EXTRACTED = "text_extracted"
    #: Structurally valid PDF, but its text layer is empty (typically scanned
    #: / image-only). No OCR is attempted.
    NO_EXTRACTABLE_TEXT = "no_extractable_text"
    ENCRYPTED = "encrypted"
    #: Not parseable as a PDF at all.
    UNREADABLE = "unreadable"


@dataclass(frozen=True)
class PdfExtractionResult:
    status: PdfExtractionStatus
    document: RawRelayDocument | None
    page_count: int = 0
    pages_with_text: int = 0
    heading_count: int = 0
    warnings: tuple[str, ...] = ()


# --------------------------------------------------------------------------
# Syntactic line parsing
# --------------------------------------------------------------------------

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_CELL_SPLIT = re.compile(r"\s{2,}|\t")
#: A leading code-like token: starts with a digit, 3-8 chars,
#: alphanumeric/dot, and is not a decimal number ("2.4", "1.84"); see _is_code.
_CODE_TOKEN = re.compile(r"^[0-9][0-9A-Za-z.]{2,7}$")
_PLAIN_NUMBER = re.compile(r"^[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?$")
_RANGE_NUM = r"[-+]?\d+(?:\.\d+)?"
_RANGE_TAIL = r"(?:\s*[%A-Za-zΩ°µ/]{1,10})?"
#: "a-b", optionally followed by a short unit-like tail ("0.05-130 ohms"), or
#: a compact enumeration of options ("0/1", "OFF/ON", "FWD,RVS,N/DIR").
_RANGE_CELL = re.compile(
    rf"^{_RANGE_NUM}\s*(?:-|~|\.\.|to)\s*{_RANGE_NUM}{_RANGE_TAIL}$"
    r"|^[\w.+*-]{1,16}(?:[/,][\w.+*-]{1,16}){1,8}$"
)
#: The value and range columns of a table are at least this many characters apart (a lone cell
#: counts as sitting in the range column when it is within a quarter of that gap of it).
_COLUMN_GAP = 16
_RANGE_BOUNDS = re.compile(rf"^({_RANGE_NUM})\s*(?:-|~|\.\.|to)\s*({_RANGE_NUM}){_RANGE_TAIL}$")
#: "name = value" or "name: value"; the name must start with a letter.
_SEPARATOR_ROW = re.compile(r"^(?P<name>[A-Za-z_][^=:]{0,59}?)\s*(?:=\s*|:\s+)(?P<value>\S.*)$")
_NUMBERED_HEADING = re.compile(r"^(?P<num>\d{1,2}(?:\.\d{1,2}){0,3})\.?\s+(?P<title>[A-Za-z][^\d]{1,78})$")
_CAPS_HEADING = re.compile(r"^[A-Z][A-Z &/,'()\-]{2,78}$")
#: Closed table of explicit unit symbols recognised when written directly
#: after a number. Purely lexical -- nothing is converted or interpreted.
_UNITS = (
    "ohm/km", "Ω/km", "Ω/m", "ohms", "ohm", "Ohm", "kΩ", "mΩ", "MΩ", "Ω", "Ω",
    "kvar", "Mvar", "var", "kVA", "MVA", "VA", "kW", "MW", "W",
    "kHz", "Hz", "mA", "kA", "A", "mV", "kV", "V",
    "µs", "μs", "us", "ms", "min", "s", "h", "p.u.", "pu", "deg", "°", "%",
    "km", "mm", "m",
)
_VALUE_WITH_UNIT = re.compile(
    r"^(?P<num>[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)\s*(?P<unit>"
    + "|".join(re.escape(u) for u in sorted(set(_UNITS), key=len, reverse=True))
    + r")$"
)


def _clean_line(line: str) -> str:
    return _CONTROL_CHARS.sub("", line).rstrip()


def _split_value(text: str) -> tuple[str, str | None, float | None]:
    """(raw_value, unit, normalized) for a value cell. The raw value excludes
    an explicitly adjacent unit symbol only; the full row stays in source_text."""
    m = _VALUE_WITH_UNIT.match(text)
    if m:
        raw, unit = m.group("num"), m.group("unit")
    else:
        raw, unit = text, None
    return raw, unit, _normalize_number(raw)


def _normalize_number(raw: str) -> float | None:
    if not _PLAIN_NUMBER.match(raw):
        return None
    # "0000" / "007" are code-like strings: leading zeros without a decimal
    # point would lose information as a float, so leave them raw-only.
    digits = raw.lstrip("+-")
    if len(digits) > 1 and digits[0] == "0" and not digits.startswith("0."):
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def _parse_range(text: str) -> SettingRange:
    m = _RANGE_BOUNDS.match(text)
    if m:
        return SettingRange(text=text, minimum=float(m.group(1)), maximum=float(m.group(2)))
    return SettingRange(text=text)


@dataclass(frozen=True)
class _Row:
    name: str | None
    parameter_id: str | None
    raw_value: str | None
    unit: str | None
    normalized: float | None
    setting_range: SettingRange | None
    notes: tuple[str, ...]
    rule: str


def _is_code(token: str) -> bool:
    return bool(_CODE_TOKEN.match(token)) and not re.fullmatch(r"\d+\.\d+", token)


def _split_code(name: str) -> tuple[str | None, str]:
    head, _, tail = name.partition(" ")
    tail = tail.strip()
    if tail and _is_code(head) and re.search(r"[A-Za-z]", tail):
        return head, tail
    return None, name


def _cells_with_offsets(line: str) -> list[tuple[str, int]]:
    """The row's cells and the character column each starts at in the layout text."""
    out: list[tuple[str, int]] = []
    pos = 0
    for m in [*_CELL_SPLIT.finditer(line), None]:
        end = m.start() if m else len(line)
        segment = line[pos:end]
        if segment.strip():
            out.append((segment.strip(), pos + len(segment) - len(segment.lstrip())))
        pos = m.end() if m else end
    return out


def _median(values: list[int]) -> float:
    ordered = sorted(values)
    mid = len(ordered) // 2
    return float(ordered[mid]) if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2


def _table_columns(rows: list[list[tuple[str, int]]]) -> tuple[float, float] | None:
    """(value column, range column) of a page's settings table, from the rows that show both
    a value cell and a range cell. ``None`` unless the evidence is clear: at least two such
    rows, columns well apart, and most rows sitting close to both. The layout text drifts by
    a few characters from row to row, so the columns are medians, not exact positions."""
    ranged = [r for r in rows if len(r) >= 3 and _RANGE_CELL.match(r[-1][0])]
    # Numeric ranges ("0.05-65 ohms") are the evidence when there are enough: option lists
    # ("FWD,RVS") are as wide as they are long and do not mark a column edge as reliably.
    numeric = [r for r in ranged if _RANGE_BOUNDS.match(r[-1][0])]
    pairs = [(r[-2][1], r[-1][1]) for r in (numeric if len(numeric) >= 2 else ranged)]
    if len(pairs) < 2:
        return None
    value_col, range_col = _median([p[0] for p in pairs]), _median([p[1] for p in pairs])
    gap = range_col - value_col
    if gap < _COLUMN_GAP:
        return None
    near = sum(1 for v, r in pairs if abs(v - value_col) <= gap / 4 and abs(r - range_col) <= gap / 4)
    return (value_col, range_col) if near >= max(2, math.ceil(len(pairs) * 0.6)) else None


def _parse_row(
    text: str, *, offsets: list[tuple[str, int]] | None = None, columns: tuple[float, float] | None = None
) -> _Row:
    """``offsets`` / ``columns`` (layout text only) let a label followed by one lone cell
    be told apart: a cell sitting in the table's range column, with the value column
    empty, is a range -- not the value (a blank setting must not borrow its allowed values)."""
    cells = [c.strip() for c in _CELL_SPLIT.split(text) if c.strip()]
    if len(cells) >= 3 and _is_code(cells[0]) and re.search(r"[A-Za-z]", cells[1]):
        parameter_id, name, rest = cells[0], cells[1], cells[2:]
    elif len(cells) >= 2:
        parameter_id, name = _split_code(cells[0])
        rest = cells[1:]
    else:
        m = _SEPARATOR_ROW.match(text)
        if m:
            parameter_id, name = _split_code(m.group("name").strip())
            raw, unit, norm = _split_value(m.group("value").strip())
            return _Row(name, parameter_id, raw, unit, norm, None, (), "row:separator")
        parameter_id, name = _split_code(text)
        return _Row(name, parameter_id, None, None, None, None, (), "row:label")

    name = name.rstrip(":").strip() or None
    setting_range = None
    notes: list[str] = []
    if (
        columns is not None and offsets is not None and len(offsets) == len(cells) == 2 and len(rest) == 1
        and abs(offsets[1][1] - columns[1]) <= (columns[1] - columns[0]) / 4
    ):
        return _Row(
            name, parameter_id, None, None, None, _parse_range(rest[0]),
            ("the value cell is blank; the cell found sits in the range column",), "row:blank_value_range",
        )
    if len(rest) >= 2 and _RANGE_CELL.match(rest[-1]):
        setting_range = _parse_range(rest[-1])
        rest = rest[:-1]
    raw, unit, norm = _split_value(rest[0])
    rule = "row:key_value_range" if setting_range else "row:key_value"
    if len(rest) > 1:
        # A genuine table row: keep every cell visible; do not guess columns.
        notes.append("cells: " + " | ".join(([parameter_id] if parameter_id else []) + [name or ""] + rest))
        rule = "row:table"
    return _Row(name, parameter_id, raw, unit, norm, setting_range, tuple(notes), rule)


def _heading(text: str, *, has_next_line: bool) -> tuple[int, str] | None:
    """(depth, title) if the line is a conservative heading, else None."""
    if len(text) > 80 or _CELL_SPLIT.search(text) or _SEPARATOR_ROW.match(text):
        return None
    m = _NUMBERED_HEADING.match(text)
    if m:
        return m.group("num").count(".") + 1, text
    if has_next_line and _CAPS_HEADING.match(text) and len(text.split()) <= 8:
        return 1, text
    return None


_PAGE_COUNTER = re.compile(r"\b\d+\s*(?:/|of)\s*\d+\b|\bpage\s+\d+\b", re.IGNORECASE)


def _signature(text: str) -> str:
    """Whitespace-normalised text with only page counters ("2/5", "Page 2")
    masked, so a repeated header matches across pages but rows that merely
    differ in a number never do."""
    return _PAGE_COUNTER.sub("#", " ".join(text.split()))


# --------------------------------------------------------------------------
# PDF handling
# --------------------------------------------------------------------------


def _page_has_images(page) -> bool:
    try:
        xobjects = page["/Resources"]["/XObject"].get_object()
        return any(xobjects[k].get_object().get("/Subtype") == "/Image" for k in xobjects)
    except Exception:  # noqa: BLE001 - purely advisory
        return False


def extract_pdf(data: bytes) -> PdfExtractionResult:
    """Extract generic raw entries from PDF bytes. Never raises for bad input."""
    from pypdf import PdfReader  # imported lazily: heavy module, PDF-only path

    try:
        reader = PdfReader(io.BytesIO(data), strict=False)
        encrypted = bool(reader.is_encrypted)
    except Exception as exc:  # noqa: BLE001 - parser failures are all "unreadable"
        logger.info("PDF could not be parsed (%s)", type(exc).__name__)
        return PdfExtractionResult(PdfExtractionStatus.UNREADABLE, None)

    warnings: list[str] = []
    if encrypted:
        try:
            decrypted = int(reader.decrypt("")) != 0
        except Exception as exc:  # noqa: BLE001 - e.g. missing AES backend
            logger.info("PDF decryption unavailable (%s)", type(exc).__name__)
            decrypted = False
        if not decrypted:
            return PdfExtractionResult(PdfExtractionStatus.ENCRYPTED, None)
        warnings.append("PDF has an owner password with an empty user password; read without a password.")

    try:
        total_pages = len(reader.pages)
    except Exception as exc:  # noqa: BLE001
        logger.info("PDF page tree unreadable (%s)", type(exc).__name__)
        return PdfExtractionResult(PdfExtractionStatus.UNREADABLE, None)

    pages_read = min(total_pages, MAX_PAGES)
    if total_pages > MAX_PAGES:
        warnings.append(f"Only the first {MAX_PAGES} of {total_pages} pages were read.")

    page_lines: list[list[str]] = []
    pages_with_text = 0
    image_only_pages = 0
    for index in range(pages_read):
        page = reader.pages[index]
        try:
            text = page.extract_text(extraction_mode="layout") or ""
        except Exception as exc:  # noqa: BLE001
            logger.info("PDF page text extraction failed (%s)", type(exc).__name__)
            warnings.append(f"Page {index + 1}: text could not be extracted.")
            text = ""
        lines = [ln for ln in (_clean_line(raw) for raw in text.splitlines()) if ln.strip()]
        page_lines.append(lines)
        if any(ch.isalnum() for ch in text):
            pages_with_text += 1
        elif _page_has_images(page):
            image_only_pages += 1

    if pages_with_text == 0:
        if image_only_pages:
            warnings.append(f"{image_only_pages} page(s) contain images but no text layer (possibly scanned).")
        return PdfExtractionResult(
            PdfExtractionStatus.NO_EXTRACTABLE_TEXT, None, page_count=total_pages, warnings=tuple(warnings)
        )

    furniture = _find_furniture(page_lines)
    settings: list[RawSetting] = []
    hints: list[str] = []
    seen_hints: set[str] = set()
    heading_stack: list[tuple[int, str]] = []
    heading_count = 0
    truncated = False

    for page_no, lines in enumerate(page_lines, start=1):
        kept: list[tuple[int, str, list[tuple[str, int]]]] = []
        for line_no, line in enumerate(lines, start=1):
            text = line.strip()
            if _signature(text) in furniture and _is_edge(line_no, len(lines)):
                if text not in seen_hints and len(hints) < _MAX_HINTS:
                    seen_hints.add(text)
                    hints.append(" ".join(text.split()))
                continue
            kept.append((line_no, text, _cells_with_offsets(line)))
        columns = _table_columns([cells for _, _, cells in kept])
        for pos, (line_no, text, offsets) in enumerate(kept):
            note_truncated = len(text) > MAX_LINE_CHARS
            if note_truncated:
                text = text[:MAX_LINE_CHARS]
            head = _heading(text, has_next_line=pos + 1 < len(kept))
            if head:
                depth, title = head
                while heading_stack and heading_stack[-1][0] >= depth:
                    heading_stack.pop()
                heading_stack.append((depth, title))
                heading_count += 1
                continue
            if len(settings) >= MAX_ENTRIES:
                truncated = True
                break
            row = _parse_row(text, offsets=offsets, columns=columns)
            notes = row.notes + (("line truncated",) if note_truncated else ())
            settings.append(
                RawSetting(
                    setting_id=f"p{page_no}-e{len(settings) + 1}",
                    name=row.name,
                    parameter_id=row.parameter_id,
                    section_path=tuple(title for _, title in heading_stack),
                    raw_value=row.raw_value,
                    normalized_value=row.normalized,
                    unit=row.unit,
                    setting_range=row.setting_range,
                    location=SourceLocation(page=page_no, line=line_no),
                    source_text=text,
                    notes=notes,
                    extraction=ExtractionProvenance(
                        extractor_id=EXTRACTOR_ID,
                        extractor_version=EXTRACTOR_VERSION,
                        notes=(row.rule,),
                    ),
                )
            )
        if truncated:
            warnings.append(f"Entry limit ({MAX_ENTRIES}) reached; remaining content was not extracted.")
            break

    if not settings:
        warnings.append("Text was found but no raw entries could be formed.")
    document = RawRelayDocument(
        source_format=SourceFormat.PDF,
        settings=tuple(settings),
        identification_hints=tuple(hints),
        extractor_id=EXTRACTOR_ID,
        warnings=tuple(warnings),
    )
    return PdfExtractionResult(
        PdfExtractionStatus.TEXT_EXTRACTED,
        document,
        page_count=total_pages,
        pages_with_text=pages_with_text,
        heading_count=heading_count,
        warnings=tuple(warnings),
    )


def _is_edge(line_no: int, line_count: int) -> bool:
    return line_no <= _FURNITURE_TOP_LINES or line_no > line_count - _FURNITURE_BOTTOM_LINES


def _find_furniture(page_lines: list[list[str]]) -> frozenset[str]:
    """Signatures of header/footer lines repeated on at least half the pages
    (and at least two). Only page counters are masked ("Sheet No. 2/5")."""
    if len(page_lines) < 2:
        return frozenset()
    counts: Counter[str] = Counter()
    for lines in page_lines:
        edge = {
            _signature(line.strip())
            for n, line in enumerate(lines, start=1)
            if _is_edge(n, len(lines))
        }
        counts.update(edge)
    threshold = max(2, math.ceil(len(page_lines) / 2))
    return frozenset(sig for sig, n in counts.items() if n >= threshold)
