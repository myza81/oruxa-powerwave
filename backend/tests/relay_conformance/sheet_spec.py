"""Synthetic relay setting sheets from one structured description (``sheets/<id>.json``).

A sheet spec is the single source of a synthetic relay sheet for the backend tests and the browser tests (which call
``python -m tests.relay_conformance.sheet_cli``). The PDF is built only here, so text escaping and layout live in one
place and the output is deterministic (byte-identical for the same spec and overrides).

Spec (``"schema": "oruxa.relay-sheet/1"``)::

    id, relay, description
    layout     {"columns": [x...], "rows_per_page": n, "line_height": 16, "top": 780}
    value_index  the cell that holds the configured value (the key of a line is always its first cell)
    lines      [[cell, ...], ...]   header and setting rows, in order (null = no cell in that column)
    notes      [[cell, ...], ...]   scheme / document notes, appended after ``lines``
    variants   {name: overrides}    named sheets derived from the default one (data only)

Overrides (all optional, applied in this order)::

    variant     name of a variant whose overrides are applied first
    drop        [key, ...]                  remove lines
    set         {key: value}                replace the value cell ("" = a blank configured cell)
    set_range   {key: text | null}          replace (or remove) the cell after the value
    insert_after {key: [[cell, ...], ...]}  add lines after a line
    append      [[cell, ...], ...]          add lines after the setting rows (before the notes)
    notes       [[cell, ...], ...]          replace the notes

An override naming a key the sheet does not have is an error (a typo never silently tests the default sheet).
"""

from __future__ import annotations

import copy
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from tests.relay_pdf_fixtures import build_pdf

SHEETS_DIR = Path(__file__).resolve().parent / "sheets"
SCHEMA = "oruxa.relay-sheet/1"
_OVERRIDE_KEYS = {"variant", "drop", "set", "set_range", "insert_after", "append", "notes"}

Line = list  # [cell | None, ...]


class SheetSpecError(ValueError):
    pass


def sheet_ids() -> list[str]:
    return sorted(p.stem for p in SHEETS_DIR.glob("*.json"))


@lru_cache(maxsize=None)
def _load(sheet_id: str) -> str:
    path = SHEETS_DIR / f"{sheet_id}.json"
    if not path.exists():
        raise SheetSpecError(f"unknown sheet {sheet_id!r}")
    return path.read_text(encoding="utf-8")


def load_spec(sheet_id: str) -> dict[str, Any]:
    """A fresh copy of the spec (callers may not mutate the cached one)."""
    spec = json.loads(_load(sheet_id))
    if spec.get("schema") != SCHEMA or spec.get("id") != sheet_id:
        raise SheetSpecError(f"{sheet_id}: not a {SCHEMA} spec for this id")
    return spec


def _index(lines: list[Line], key: str, sheet_id: str) -> int:
    hits = [i for i, line in enumerate(lines) if line and line[0] == key]
    if len(hits) != 1:
        raise SheetSpecError(f"{sheet_id}: {'no' if not hits else 'more than one'} line keyed {key!r}")
    return hits[0]


def _apply(spec: dict[str, Any], lines: list[Line], notes: list[Line], ov: dict[str, Any]) -> tuple[list[Line], list[Line]]:
    unknown = set(ov) - _OVERRIDE_KEYS
    if unknown:
        raise SheetSpecError(f"{spec['id']}: unknown override keys {sorted(unknown)}")
    sid, vi = spec["id"], spec["value_index"]
    if ov.get("variant"):
        variants = spec.get("variants", {})
        if ov["variant"] not in variants:
            raise SheetSpecError(f"{sid}: unknown variant {ov['variant']!r}")
        lines, notes = _apply(spec, lines, notes, variants[ov["variant"]])
    for key in ov.get("drop", ()):
        del lines[_index(lines, key, sid)]
    for key, value in ov.get("set", {}).items():
        line = lines[_index(lines, key, sid)]
        while len(line) <= vi:
            line.append(None)
        line[vi] = value
    for key, rng in ov.get("set_range", {}).items():
        line = lines[_index(lines, key, sid)]
        del line[vi + 1:]
        if rng is not None:
            line.append(rng)
    for key, extra in ov.get("insert_after", {}).items():
        at = _index(lines, key, sid) + 1
        lines[at:at] = [list(x) for x in extra]
    lines = lines + [list(x) for x in ov.get("append", ())]
    if "notes" in ov:
        notes = [list(x) for x in ov["notes"]]
    return lines, notes


def sheet_lines(sheet_id: str, overrides: dict[str, Any] | None = None) -> list[Line]:
    """Every line of the sheet (setting rows, then notes) after the overrides."""
    spec = load_spec(sheet_id)
    lines, notes = _apply(spec, copy.deepcopy(spec["lines"]), copy.deepcopy(spec.get("notes", [])), overrides or {})
    return lines + notes


def note_lines(sheet_id: str, overrides: dict[str, Any] | None = None) -> list[Line]:
    spec = load_spec(sheet_id)
    return _apply(spec, copy.deepcopy(spec["lines"]), copy.deepcopy(spec.get("notes", [])), overrides or {})[1]


def sheet_pdf(sheet_id: str, overrides: dict[str, Any] | None = None) -> bytes:
    """The sheet as a real text PDF (read back through the real extractor by the tests)."""
    layout = load_spec(sheet_id)["layout"]
    columns, per_page = layout["columns"], layout["rows_per_page"]
    top, step = layout.get("top", 780), layout.get("line_height", 16)
    lines = sheet_lines(sheet_id, overrides)
    pages = []
    for start in range(0, len(lines), per_page):
        items, y = [], top
        for line in lines[start:start + per_page]:
            items += [(x, y, cell) for cell, x in zip(line, columns, strict=False) if cell is not None]
            y -= step
        pages.append(items)
    return build_pdf(pages)
