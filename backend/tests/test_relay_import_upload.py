"""Relay Import Slice 3: ephemeral relay-setting upload endpoint."""

from __future__ import annotations

import io
import json
import logging
import tempfile
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.relay_pdf_fixtures import build_pdf, rows_page, simple_pdf
from tests.relay_p441_fixtures import BASE, NOTES, SCHEME_ROW

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


def _sheet(scheme: str | None, *extra: list[str]) -> bytes:
    rows = [["Issued By:"]]
    if scheme is not None:
        rows.append(["LZOP: 132kV AAAA - BBBB", "Scheme: " + scheme])
    rows.extend(extra or [["R1", "1.84", "0-655.35"]])
    return simple_pdf(rows)


class TestIdentification:
    """Slice 5: the verdict is returned; evidence and document text are not."""

    def test_identified_relay_is_reported_without_document_content(self, client):
        data = _sheet("7SA6131_4AB02_3GA0", ["1313 X(Z2)", "3.6", "0.05-250 ohms"])
        r = client.post(URL, files=_files(data, name="document.pdf"))
        assert r.status_code == 200
        body = r.json()
        assert body["identification_status"] == "identified"
        assert (body["manufacturer"], body["relay_family"], body["model"]) == ("Siemens", "SIPROTEC 4 7SA6", "7SA613")
        assert (body["profile_id"], body["confidence"]) == ("siemens-7sa613", "high")
        assert body["identification_warnings"] == []
        # engineering values appear only inside ``review`` (Slice 7); the identification verdict carries none
        outside_review = json.dumps({k: v for k, v in body.items() if k != "review"})
        for content in ("3.6", "X(Z2)", "7SA6131_4AB02", "evidence", "score"):
            assert content not in outside_review

    def test_response_stays_concise(self, client):
        body = client.post(URL, files=_files(_sheet("GRL200_TNB"))).json()
        assert set(body) == {
            "filename", "source_format", "size_bytes", "status", "extraction_status", "page_count",
            "pages_with_text", "raw_entry_count", "section_count", "extraction_warnings",
            "identification_status", "manufacturer", "relay_family", "model", "profile_id", "confidence",
            "identification_warnings",
            "interpretation_status", "profile_version", "mapped_setting_count", "inferred_setting_count",
            "unresolved_setting_count", "not_interpreted_setting_count", "zone_count", "interpretation_warnings",
            "catalog_id", "catalog_version", "catalog_coverage", "review",
        }

    def test_unrecognised_relay_is_unknown_not_an_error(self, client):
        r = client.post(URL, files=_files(_sheet("XYZ9000_V1")))
        assert r.status_code == 200
        body = r.json()
        assert body["identification_status"] == "unknown"
        assert body["profile_id"] is None and body["model"] is None
        assert body["extraction_status"] == "text_extracted" and body["raw_entry_count"] >= 1

    def test_file_name_is_not_evidence(self, client):
        generic = client.post(URL, files=_files(_sheet(None), name="p441.pdf")).json()
        assert generic["identification_status"] == "unknown"
        renamed = client.post(URL, files=_files(_sheet("RELZ100_3.0"), name="p441.pdf")).json()
        assert renamed["profile_id"] == "relz100"

    def test_ambiguous_documents_select_nothing(self, client):
        body = client.post(URL, files=_files(_sheet("7SA511_V3.2_1A", ["Relay Type:", "7SA6131"]))).json()
        assert body["identification_status"] == "ambiguous"
        assert body["profile_id"] is None and body["model"] is None
        assert body["manufacturer"] == "Siemens" and body["confidence"] == "low"
        assert body["identification_warnings"]

    def test_unreadable_text_means_nothing_to_identify(self, client):
        body = client.post(URL, files=_files(build_pdf(["image"]))).json()
        assert body["identification_status"] is None
        assert (body["manufacturer"], body["model"], body["confidence"]) == (None, None, None)
        assert body["identification_warnings"] == []


def _p441_pdf(*, notes=NOTES, overrides=None) -> bytes:
    """A P441-shaped setting sheet built through the real PDF extractor path:
    code / name / value / printed range in four columns, notes as one cell."""
    rows = dict(BASE)
    rows.update(overrides or {})
    lines = [list(SCHEME_ROW)] + [[code, *cells] for code, cells in ((c, (n, v, r or "")) for c, (n, v, r) in rows.items())]
    lines += [[n] for n in notes]
    pages = [rows_page(lines[i : i + 40]) for i in range(0, len(lines), 40)]
    return build_pdf(pages)


class TestInterpretation:
    """Slice 6: upload -> extraction -> identification -> interpretation. A summary
    only (counts and fixed phrases); nothing is applied to the form."""

    def test_p441_is_interpreted_and_summarised(self, client):
        r = client.post(URL, files=_files(_p441_pdf(), name="document.pdf"))
        assert r.status_code == 200
        body = r.json()
        assert body["identification_status"] == "identified" and body["profile_id"] == "schneider-micom-p441"
        assert body["interpretation_status"] == "interpreted"
        assert body["profile_version"] == "micom-p441-v1"
        assert body["zone_count"] == 5
        assert body["mapped_setting_count"] >= 25 and body["inferred_setting_count"] > 0 and body["unresolved_setting_count"] > 0
        assert body["interpretation_warnings"]

    def test_the_api_summary_matches_the_profile_run_on_the_same_extraction(self, client):
        from app.relay_profiles.identification_catalogue import default_registry
        from app.services.relay_interpretation_summary import summarize_interpretation
        from app.services.relay_pdf_extractor import extract_pdf

        data = _p441_pdf()
        body = client.post(URL, files=_files(data)).json()
        doc = extract_pdf(data).document
        reg = default_registry()
        expected = summarize_interpretation(reg, doc, reg.identify(doc))
        assert (body["mapped_setting_count"], body["inferred_setting_count"], body["unresolved_setting_count"], body["zone_count"]) == (
            expected.mapped_setting_count, expected.inferred_setting_count, expected.unresolved_setting_count, expected.zone_count,
        )
        assert body["interpretation_warnings"] == list(expected.warnings)

    def test_summary_fields_never_carry_settings_or_document_text(self, client):
        # Slice 7: the engineering values travel only inside the dedicated
        # ``review`` payload; every summary field stays counts and fixed phrases.
        body = client.post(URL, files=_files(_p441_pdf())).json()
        body.pop("review")
        text = json.dumps(body)
        for content in ("1.43", "7.02", "17.19", "132000", "Defeated", "Directional", "R1Ph", "300A", "Kilometres"):
            assert content not in text

    def test_engine_limits_are_reported_as_warnings_not_errors(self, client):
        warnings = client.post(URL, files=_files(_p441_pdf())).json()["interpretation_warnings"]
        assert any(w.startswith("Engine: ") for w in warnings)

    def test_zone_4_defeat_survives_the_pdf_round_trip(self, client):
        defeated = client.post(URL, files=_files(_p441_pdf())).json()
        undeclared = client.post(URL, files=_files(_p441_pdf(notes=NOTES[:2]))).json()
        # Without the defeat statement Zone 4's status is unresolved, so one more item is open.
        assert undeclared["unresolved_setting_count"] > defeated["unresolved_setting_count"]
        assert undeclared["inferred_setting_count"] < defeated["inferred_setting_count"]

    def test_an_unrecognised_relay_stays_uninterpreted(self, client):
        body = client.post(URL, files=_files(_sheet("XYZ9000_V1"))).json()
        assert body["interpretation_status"] == "not_supported"
        assert body["profile_version"] is None and body["zone_count"] == 0
        assert (body["mapped_setting_count"], body["inferred_setting_count"], body["unresolved_setting_count"]) == (0, 0, 0)
        assert body["interpretation_warnings"] == []

    @pytest.mark.parametrize("scheme, profile_id, catalog_id, version", [
        ("7SA6131_4AB02_3GA0", "siemens-7sa613", "siemens-7sa613-catalog", "1.4.0"),   # DEC-198 Am. 6; DEC-199 Phase 2A/2D/2F boundaries
        ("GRL200_TNB", "toshiba-grl200", "toshiba-grl200-catalog", "1.0.0"),
        ("RELZ100_3.0", "relz100", "relz100-catalog", "1.0.0"),
    ])
    def test_a_catalogued_relay_is_interpreted_by_its_own_catalog(self, client, scheme, profile_id, catalog_id, version):
        body = client.post(URL, files=_files(_sheet(scheme))).json()
        assert body["profile_id"] == profile_id and body["catalog_id"] == catalog_id
        assert body["profile_version"] == f"{catalog_id}-v{version}"
        assert body["interpretation_status"] in ("interpreted", "incomplete")

    def test_p441_settings_under_another_relays_scheme_are_not_interpreted_as_a_p441(self, client):
        data = _p441_pdf().replace(b"SE_P441?A1???038?JE", b"7SA6131_4AB02_3GA0")
        body = client.post(URL, files=_files(data)).json()
        assert body["profile_id"] == "siemens-7sa613"                                # the scheme decides the relay
        assert not (body["profile_version"] or "").startswith(("micom", "schneider"))  # never the P441 profile / catalog

    def test_nothing_to_interpret_without_text(self, client):
        body = client.post(URL, files=_files(build_pdf(["image"]))).json()
        assert body["interpretation_status"] is None and body["zone_count"] == 0

    def test_a_profile_failure_does_not_fail_the_upload(self, client, monkeypatch):
        from app.relay_profiles.micom_p441 import MicomP441Profile

        def boom(self, document):
            raise RuntimeError("1.43 is not acceptable")

        monkeypatch.setattr(MicomP441Profile, "interpret", boom)
        r = client.post(URL, files=_files(_p441_pdf()))
        assert r.status_code == 200
        body = r.json()
        assert body["identification_status"] == "identified" and body["interpretation_status"] == "failed"
        assert "1.43" not in r.text and body["zone_count"] == 0

    def test_interpretation_keeps_the_upload_ephemeral(self, client, small_settings, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        before = sorted(p.name for p in tmp_path.iterdir())
        client.post(URL, files=_files(_p441_pdf()))
        assert sorted(p.name for p in tmp_path.iterdir()) == before


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
            "identification_status": "unknown",
            "manufacturer": None,
            "relay_family": None,
            "model": None,
            "profile_id": None,
            "confidence": "none",
            "identification_warnings": [],
            "interpretation_status": "not_supported",
            "profile_version": None,
            "mapped_setting_count": 0,
            "inferred_setting_count": 0,
            "unresolved_setting_count": 0,
            "not_interpreted_setting_count": 0,
            "zone_count": 0,
            "interpretation_warnings": [],
            "catalog_id": None,
            "catalog_version": None,
            "catalog_coverage": None,
            "review": None,
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
