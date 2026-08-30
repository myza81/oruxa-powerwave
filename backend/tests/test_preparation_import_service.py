"""Service-level tests for CSV preparation-source import (Slice 1, DEC-072).

Mirrors the "Upload tests" character of tests/test_sources_api.py's own
TestUpload class, but at the service layer, plus a set of guardrail
assertions specific to this slice's own explicit scope limits (no
DisturbanceRecord, no waveform-ready registry entry).

`import_csv_preparation_source` is async (matches
`import_comtrade_source`'s own signature) -- driven here via
`asyncio.run()` rather than `async def test_...`, since this project has
no pytest-asyncio/anyio pytest plugin installed and no existing
precedent for testing an async service function directly (COMTRADE's
own async import service is exercised only through the synchronous
`TestClient` in tests/test_sources_api.py). See
tests/test_preparation_sources_api.py for the equivalent API-level
coverage through that same TestClient pattern.
"""

from __future__ import annotations

import asyncio
import io

import pytest
from fastapi import UploadFile
from starlette.datastructures import Headers

from app.domain.preparation_session import FORMAT_CSV, STATUS_NEEDS_PREPARATION
from app.services.errors import InvalidFileError, UnsupportedFileTypeError, UploadTooLargeError
from app.services.preparation_import_service import import_csv_preparation_source
from app.services.preparation_session_registry import PreparationSessionRegistry


def _upload(content: bytes, filename: str | None = "event.csv") -> UploadFile:
    return UploadFile(
        file=io.BytesIO(content),
        filename=filename,
        headers=Headers({"content-type": "text/csv"}),
    )


def _import(**kwargs):
    return asyncio.run(import_csv_preparation_source(**kwargs))


def test_valid_csv_is_accepted_and_returns_expected_summary():
    registry = PreparationSessionRegistry()
    content = b"time,VA\n0.0,1.0\n0.001,2.0\n"

    summary = _import(
        workspace_id="ws-1",
        csv_upload=_upload(content, "GPTH disturbance.csv"),
        max_total_bytes=100 * 1024 * 1024,
        registry=registry,
    )

    assert summary.workspace_id == "ws-1"
    assert summary.original_filename == "GPTH disturbance.csv"
    assert summary.source_format == FORMAT_CSV
    assert summary.status == STATUS_NEEDS_PREPARATION
    assert summary.original_byte_size == len(content)
    assert summary.source_id  # non-empty, opaque id


def test_accepted_session_is_stored_in_the_registry_with_raw_bytes_preserved():
    registry = PreparationSessionRegistry()
    content = b"time,VA\n0.0,1.0\n"

    summary = _import(
        workspace_id="ws-1", csv_upload=_upload(content), max_total_bytes=1_000_000, registry=registry,
    )

    stored = registry.get("ws-1", summary.source_id)
    assert stored is not None
    assert stored.raw_bytes == content
    assert stored.summary == summary


def test_unsupported_extension_is_rejected():
    registry = PreparationSessionRegistry()

    with pytest.raises(UnsupportedFileTypeError):
        _import(
            workspace_id="ws-1",
            csv_upload=_upload(b"not a csv", "event.txt"),
            max_total_bytes=1_000_000,
            registry=registry,
        )
    assert registry.count() == 0


def test_missing_filename_is_rejected():
    registry = PreparationSessionRegistry()

    with pytest.raises(UnsupportedFileTypeError):
        _import(
            workspace_id="ws-1",
            csv_upload=_upload(b"a,b\n1,2\n", filename=None),
            max_total_bytes=1_000_000,
            registry=registry,
        )
    assert registry.count() == 0


def test_empty_csv_is_rejected():
    registry = PreparationSessionRegistry()

    with pytest.raises(InvalidFileError):
        _import(
            workspace_id="ws-1", csv_upload=_upload(b"", "empty.csv"), max_total_bytes=1_000_000, registry=registry,
        )
    assert registry.count() == 0


def test_oversized_csv_is_rejected():
    registry = PreparationSessionRegistry()
    content = b"x" * 2000

    with pytest.raises(UploadTooLargeError):
        _import(
            workspace_id="ws-1", csv_upload=_upload(content, "big.csv"), max_total_bytes=1000, registry=registry,
        )
    assert registry.count() == 0


def test_two_uploads_in_the_same_workspace_get_distinct_source_ids():
    registry = PreparationSessionRegistry()

    first = _import(
        workspace_id="ws-1", csv_upload=_upload(b"a,b\n1,2\n", "a.csv"), max_total_bytes=1_000_000, registry=registry,
    )
    second = _import(
        workspace_id="ws-1", csv_upload=_upload(b"c,d\n3,4\n", "b.csv"), max_total_bytes=1_000_000, registry=registry,
    )

    assert first.source_id != second.source_id
    assert {s.summary.source_id for s in registry.list_for_workspace("ws-1")} == {
        first.source_id,
        second.source_id,
    }
