"""Relay Import Slice 3: ephemeral relay-setting upload endpoint."""

from __future__ import annotations

import io
import logging
import tempfile
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.relay_pdf_fixtures import build_pdf, simple_pdf

URL = "/api/v1/relay-import/upload"
BACKEND_APP = Path(__file__).resolve().parents[1] / "app"

PDF_BYTES = simple_pdf([["R1", "1.84", "0-655.35"], ["Zone 2", "Forward", "2.4"]])
MIB = 1024 * 1024


def _files(content: bytes = PDF_BYTES, name: str = "P441 settings.pdf", ctype: str = "application/pdf"):
    return {"file": (name, io.BytesIO(content), ctype)}


@pytest.fixture
def small_settings(settings):
    return replace(settings, max_relay_import_upload_size_mb=1)


@pytest.fixture
def client(small_settings):
    with TestClient(create_app(small_settings)) as c:
        yield c


class TestAccepted:
    def test_valid_pdf_returns_safe_metadata_only(self, client):
        r = client.post(URL, files=_files())
        assert r.status_code == 200
        assert r.json() == {
            "filename": "P441 settings.pdf",
            "source_format": "pdf",
            "size_bytes": len(PDF_BYTES),
            "status": "accepted",
            "extraction_status": "text_extracted",
            "page_count": 1,
            "pages_with_text": 1,
            "raw_entry_count": 2,
            "section_count": 0,
            "extraction_warnings": [],
        }

    def test_response_carries_counts_never_document_content(self, client):
        body = client.post(URL, files=_files()).text
        for content in ("1.84", "Zone 2", "Forward"):
            assert content not in body

    def test_scanned_like_pdf_is_accepted_with_a_clear_status(self, client):
        r = client.post(URL, files=_files(content=build_pdf(["image"])))
        assert r.status_code == 200
        body = r.json()
        assert body["extraction_status"] == "no_extractable_text"
        assert (body["page_count"], body["pages_with_text"], body["raw_entry_count"]) == (1, 0, 0)

    def test_encrypted_pdf_is_accepted_but_reported(self, client):
        from pypdf import PdfReader, PdfWriter

        writer = PdfWriter(clone_from=PdfReader(io.BytesIO(PDF_BYTES)))
        writer.encrypt("secret", algorithm="RC4-128")
        buf = io.BytesIO()
        writer.write(buf)
        r = client.post(URL, files=_files(content=buf.getvalue()))
        assert r.status_code == 200
        assert r.json()["extraction_status"] == "encrypted"

    def test_extraction_is_repeatable_through_the_api(self, client):
        assert client.post(URL, files=_files()).json() == client.post(URL, files=_files()).json()

    def test_extension_is_case_insensitive(self, client):
        assert client.post(URL, files=_files(name="SETTINGS.PDF")).status_code == 200

    def test_client_path_is_reduced_to_base_name(self, client):
        for raw in ("C:\\Users\\someone\\secret\\a.pdf", "/home/someone/a.pdf"):
            r = client.post(URL, files=_files(name=raw))
            assert r.status_code == 200
            assert r.json()["filename"] == "a.pdf"


class TestRejected:
    @pytest.mark.parametrize("name", ["settings.xlsx", "settings.csv", "settings.txt", "settings", "settings.pdf.exe"])
    def test_unsupported_extension(self, client, name):
        r = client.post(URL, files=_files(name=name))
        assert r.status_code == 400
        assert r.json()["detail"]["code"] == "unsupported_file_type"

    def test_pdf_content_type_with_wrong_extension_is_rejected(self, client):
        assert client.post(URL, files=_files(name="x.docx", ctype="application/pdf")).status_code == 400

    def test_empty_file(self, client):
        r = client.post(URL, files=_files(content=b""))
        assert r.status_code == 400
        assert r.json()["detail"]["code"] == "empty_file"

    def test_oversized_file(self, client):
        r = client.post(URL, files=_files(content=PDF_BYTES + b"0" * MIB))
        assert r.status_code == 413
        assert r.json()["detail"]["code"] == "upload_too_large"

    @pytest.mark.parametrize(
        "content",
        [
            b"not a pdf at all",
            b"%PDF-1.4\n1 0 obj\n<< >>\nendobj\n" + b"x" * 5000,
            b"PK\x03\x04zip" + b"%%EOF",
            # passes the cheap header/EOF check but is not parseable
            b"%PDF-1.4\n1 0 obj\n<< >>\nendobj\n" + b"x" * 500 + b"\n%%EOF\n",
        ],
    )
    def test_malformed_pdf(self, client, content):
        r = client.post(URL, files=_files(content=content))
        assert r.status_code == 400
        assert r.json()["detail"]["code"] == "invalid_file"

    def test_errors_do_not_expose_paths_or_stack_traces(self, client, small_settings):
        bodies = [
            client.post(URL, files=_files(name="C:\\secret\\dir\\a.txt")).text,
            client.post(URL, files=_files(content=b"")).text,
            client.post(URL, files=_files(content=b"garbage")).text,
            client.post(URL, files=_files(content=b"%PDF-1.4\n" + b"x" * 500 + b"\n%%EOF\n")).text,
        ]
        for text in bodies:
            assert "secret" not in text
            assert small_settings.storage_path not in text
            assert tempfile.gettempdir() not in text
            assert "Traceback" not in text

    def test_unexpected_failure_is_generic(self, client, monkeypatch):
        import app.api.v1.relay_import as module

        async def boom(*args, **kwargs):
            raise RuntimeError("C:\\internal\\path\\leak")

        monkeypatch.setattr(module, "inspect_relay_setting_upload", boom)
        r = client.post(URL, files=_files())
        assert r.status_code == 500
        assert "leak" not in r.text
        assert r.json()["detail"]["code"] == "internal_error"

    def test_failure_does_not_log_filename(self, client, caplog):
        with caplog.at_level(logging.DEBUG):
            client.post(URL, files=_files(content=b"garbage", name="very-private-name.pdf"))
        assert "very-private-name" not in caplog.text


class TestNoPersistence:
    @staticmethod
    def _snapshot(root: Path) -> set[str]:
        return {str(p.relative_to(root)) for p in root.rglob("*")}

    def test_large_upload_leaves_no_temp_files(self, small_settings, tmp_path, monkeypatch):
        """A body past Starlette's 1 MiB spool threshold uses an OS temp
        file; point the temp dir at an observable folder and require it
        empty after success, malformed and oversized requests."""
        scratch = tmp_path / "scratch"
        scratch.mkdir()
        monkeypatch.setattr(tempfile, "tempdir", str(scratch))
        settings = replace(small_settings, max_relay_import_upload_size_mb=5)
        ok = simple_pdf(pad=2 * MIB)
        bad = b"garbage" + b"0" * (2 * MIB)
        with TestClient(create_app(settings)) as c:
            assert c.post(URL, files=_files(content=ok)).status_code == 200
            assert list(scratch.iterdir()) == []
            assert c.post(URL, files=_files(content=bad)).status_code == 400
            assert list(scratch.iterdir()) == []
            assert c.post(URL, files=_files(content=b"x" * (6 * MIB))).status_code == 413
            assert list(scratch.iterdir()) == []

    def test_upload_handle_closed_on_success_and_failure(self):
        import asyncio

        from starlette.datastructures import UploadFile

        from app.services.errors import InvalidFileError
        from app.services.relay_import_upload_service import inspect_relay_setting_upload

        ok = UploadFile(file=io.BytesIO(PDF_BYTES), filename="a.pdf")
        asyncio.run(inspect_relay_setting_upload(ok, max_bytes=len(PDF_BYTES) + 1))
        assert ok.file.closed

        bad = UploadFile(file=io.BytesIO(b"junk"), filename="a.pdf")
        with pytest.raises(InvalidFileError):
            asyncio.run(inspect_relay_setting_upload(bad, max_bytes=1024))
        assert bad.file.closed

    def test_no_storage_or_working_directory_writes(self, client, small_settings, tmp_path, monkeypatch):
        storage_root = Path(small_settings.storage_path)
        cwd = tmp_path / "cwd"
        cwd.mkdir()
        monkeypatch.chdir(cwd)
        before = self._snapshot(storage_root)
        client.post(URL, files=_files())
        client.post(URL, files=_files(content=b"junk"))
        assert self._snapshot(storage_root) == before
        assert list(cwd.iterdir()) == []

    def test_no_app_state_added_by_upload(self, client):
        before = set(vars(client.app.state))
        client.post(URL, files=_files())
        assert set(vars(client.app.state)) == before

    def test_upload_modules_have_no_persistence_code(self):
        for path in (
            BACKEND_APP / "api" / "v1" / "relay_import.py",
            BACKEND_APP / "services" / "relay_import_upload_service.py",
            BACKEND_APP / "services" / "relay_pdf_extractor.py",
            BACKEND_APP / "schemas" / "relay_import.py",
        ):
            text = path.read_text(encoding="utf-8")
            for forbidden in (
                "psycopg", "sqlalchemy", "app.storage", "get_storage", "import tempfile",
                "open(", "write_bytes", "mkdir", "STORAGE_PATH",
            ):
                assert forbidden not in text, (path.name, forbidden)

    def test_middleware_fast_rejects_oversized_declared_length(self, client):
        r = client.post(
            URL,
            content=b"x",
            headers={"content-length": str(50 * MIB), "content-type": "multipart/form-data; boundary=x"},
        )
        assert r.status_code == 413
        assert r.json()["detail"]["code"] == "upload_too_large"
        assert "1 MB" in r.json()["detail"]["message"]


class TestConfig:
    def test_default_and_env_override(self):
        from app.config import DEFAULT_MAX_RELAY_IMPORT_UPLOAD_SIZE_MB, ConfigurationError, load_settings

        base = {"STORAGE_PATH": "x"}
        assert load_settings(base).max_relay_import_upload_size_mb == DEFAULT_MAX_RELAY_IMPORT_UPLOAD_SIZE_MB == 20
        overridden = load_settings({**base, "MAX_RELAY_IMPORT_UPLOAD_SIZE_MB": "5"})
        assert overridden.max_relay_import_upload_size_bytes == 5 * MIB
        for bad in ("0", "-1", "abc"):
            with pytest.raises(ConfigurationError):
                load_settings({**base, "MAX_RELAY_IMPORT_UPLOAD_SIZE_MB": bad})
