"""Relay Import Slice 4: generic, relay-neutral PDF extraction.

Nothing here asserts engineering meaning: only structure, provenance,
syntactic splitting and failure handling.
"""

from __future__ import annotations

import io
import os
import re
from pathlib import Path

import pytest

import app.services.relay_pdf_extractor as extractor
from app.domain.relay_import.raw_document import SourceFormat
from app.services.relay_pdf_extractor import PdfExtractionStatus, extract_pdf
from tests.relay_pdf_fixtures import build_pdf, rows_page, simple_pdf


def _doc(rows):
    result = extract_pdf(simple_pdf(rows))
    assert result.status is PdfExtractionStatus.TEXT_EXTRACTED
    return result.document


def _encrypted(algorithm: str = "RC4-128", **kwargs) -> bytes:
    from pypdf import PdfReader, PdfWriter

    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(simple_pdf())))
    writer.encrypt(algorithm=algorithm, **kwargs)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


class TestRawDocumentPopulation:
    def test_one_page_key_value_row(self):
        doc = _doc([["R1", "1.84", "0-655.35"]])
        assert doc.source_format is SourceFormat.PDF
        (s,) = doc.settings
        assert (s.name, s.raw_value, s.normalized_value) == ("R1", "1.84", 1.84)
        assert s.setting_range.text == "0-655.35"
        assert (s.setting_range.minimum, s.setting_range.maximum) == (0.0, 655.35)
        assert s.location.page == 1 and s.location.line == 1
        assert re.search(r"R1\s+1\.84\s+0-655\.35", s.source_text)
        assert s.extraction.extractor_id == "generic_pdf_text"
        assert s.parameter_id is None and s.unit is None

    def test_table_like_row_keeps_every_cell_without_guessing_columns(self):
        (s,) = _doc([["Zone 2", "Forward", "2.4"]]).settings
        assert s.name == "Zone 2" and s.raw_value == "Forward"
        assert s.extraction.notes == ("row:table",)
        assert s.notes == ("cells: Zone 2 | Forward | 2.4",)

    def test_leading_code_token_becomes_parameter_id(self):
        (s,) = _doc([["1412 X1L", "130", "0.05-130 ohms"]]).settings
        assert (s.parameter_id, s.name, s.raw_value) == ("1412", "X1L", "130")

    def test_letter_led_names_are_never_split_into_codes(self):
        for name in ("R1", "Z2", "K0"):
            (s,) = _doc([[name, "5"]]).settings
            assert s.parameter_id is None and s.name == name

    def test_label_only_row_has_no_value(self):
        (s,) = _doc([["OP Mode ID38"]]).settings
        assert s.raw_value is None and s.extraction.notes == ("row:label",)

    def test_code_like_values_are_not_numerically_normalized(self):
        (s,) = _doc([["CfgBO_X", "0000"]]).settings
        assert s.raw_value == "0000" and s.normalized_value is None

    def test_pages_ids_and_order(self):
        pdf = build_pdf([rows_page([["A", "1"], ["B", "2"]]), rows_page([["C", "3"]])])
        doc = extract_pdf(pdf).document
        assert [s.name for s in doc.settings] == ["A", "B", "C"]
        assert [s.location.page for s in doc.settings] == [1, 1, 2]
        assert len({s.setting_id for s in doc.settings}) == 3


class TestSyntacticRules:
    @pytest.mark.parametrize(
        "text, name, raw, unit, norm",
        [
            ("R1 = 1.84 \u03a9", "R1", "1.84", "\u03a9", 1.84),
            ("Delay: 20 ms", "Delay", "20", "ms", 20.0),
            ("Name = Forward", "Name", "Forward", None, None),
            ("X = 5 furlongs", "X", "5 furlongs", None, None),  # not a known unit: left raw
        ],
    )
    def test_separator_rows_and_explicit_units(self, text, name, raw, unit, norm):
        row = extractor._parse_row(text)
        assert (row.name, row.raw_value, row.unit, row.normalized) == (name, raw, unit, norm)

    def test_times_are_not_key_value(self):
        assert extractor._parse_row("12:30").raw_value is None

    def test_no_unit_conversion(self):
        row = extractor._parse_row("Reach = 2 kV")
        assert (row.raw_value, row.unit, row.normalized) == ("2", "kV", 2.0)

    def test_numbered_heading_sets_section_path(self):
        doc = _doc([["21 Distance protection zones"], ["R1", "1"], ["22 Other things"], ["R2", "2"]])
        assert [s.section_path for s in doc.settings] == [("21 Distance protection zones",), ("22 Other things",)]

    def test_dotted_numbering_nests_but_does_not_invent_parents(self):
        doc = _doc([["2.1 Child only"], ["A", "1"], ["3 Top"], ["3.1 Sub"], ["B", "2"]])
        assert doc.settings[0].section_path == ("2.1 Child only",)
        assert doc.settings[1].section_path == ("3 Top", "3.1 Sub")

    def test_caps_heading_requires_following_line(self):
        doc = _doc([["GENERAL"], ["A", "1"], ["TRAILING"]])
        assert doc.settings[0].section_path == ("GENERAL",)
        assert doc.settings[-1].name == "TRAILING"  # last line: a label, not a heading

    def test_no_heading_means_flat(self):
        assert _doc([["A", "1"]]).settings[0].section_path == ()


class TestPageFurniture:
    def test_repeated_header_is_a_hint_not_an_entry(self):
        def page(n, extra):
            return rows_page([["RELAY SETTING SHEET"], [f"Sheet No. {n}/3"], [extra, "1"]])

        doc = extract_pdf(build_pdf([page(1, "A"), page(2, "B"), page(3, "C")])).document
        assert [s.name for s in doc.settings] == ["A", "B", "C"]
        assert doc.identification_hints[0] == "RELAY SETTING SHEET"
        assert all(s.section_path == () for s in doc.settings)


class TestTextVsScannedVsBrokenVsEncrypted:
    def test_image_only_pdf_is_valid_but_has_no_text(self):
        r = extract_pdf(build_pdf(["image", "image"]))
        assert r.status is PdfExtractionStatus.NO_EXTRACTABLE_TEXT
        assert r.document is None and r.page_count == 2 and r.pages_with_text == 0
        assert any("images but no text layer" in w for w in r.warnings)

    def test_blank_page_has_no_text(self):
        assert extract_pdf(build_pdf([[]])).status is PdfExtractionStatus.NO_EXTRACTABLE_TEXT

    def test_mixed_pdf_counts_pages_with_text(self):
        r = extract_pdf(build_pdf([rows_page([["A", "1"]]), "image"]))
        assert (r.status, r.page_count, r.pages_with_text) == (PdfExtractionStatus.TEXT_EXTRACTED, 2, 1)

    @pytest.mark.parametrize(
        "data",
        [b"", b"junk", b"%PDF-1.4\n1 0 obj\n<< >>\nendobj\n" + b"x" * 500 + b"\n%%EOF\n"],
    )
    def test_malformed_pdf_is_unreadable_without_raising(self, data):
        r = extract_pdf(data)
        assert r.status is PdfExtractionStatus.UNREADABLE and r.document is None

    def test_user_password_encrypted_pdf(self):
        r = extract_pdf(_encrypted(user_password="secret"))
        assert r.status is PdfExtractionStatus.ENCRYPTED and r.document is None

    def test_owner_only_encryption_is_readable_with_a_warning(self):
        r = extract_pdf(_encrypted(user_password="", owner_password="owner"))
        assert r.status is PdfExtractionStatus.TEXT_EXTRACTED
        assert any("owner password" in w for w in r.warnings)

    def test_unavailable_decryption_backend_reports_encrypted(self, monkeypatch):
        from pypdf import PdfReader
        from pypdf.errors import DependencyError

        data = _encrypted(user_password="secret")

        def boom(self, password):
            raise DependencyError("cryptography is required")

        monkeypatch.setattr(PdfReader, "decrypt", boom)
        assert extract_pdf(data).status is PdfExtractionStatus.ENCRYPTED


class TestLimitsAndSafety:
    def test_page_limit(self, monkeypatch):
        monkeypatch.setattr(extractor, "MAX_PAGES", 2)
        r = extract_pdf(build_pdf([rows_page([[f"P{i}", "1"]]) for i in range(4)]))
        assert r.page_count == 4
        assert {s.location.page for s in r.document.settings} == {1, 2}
        assert any("first 2 of 4 pages" in w for w in r.warnings)

    def test_entry_limit(self, monkeypatch):
        monkeypatch.setattr(extractor, "MAX_ENTRIES", 3)
        r = extract_pdf(simple_pdf([[f"K{i}", "1"] for i in range(6)]))
        assert len(r.document.settings) == 3
        assert any("Entry limit" in w for w in r.warnings)

    def test_page_text_failure_is_isolated_and_content_free(self, monkeypatch):
        from pypdf import PageObject

        original = PageObject.extract_text
        calls = {"n": 0}

        def flaky(self, *a, **k):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("secret-content C:\\leak")
            return original(self, *a, **k)

        monkeypatch.setattr(PageObject, "extract_text", flaky)
        r = extract_pdf(build_pdf([rows_page([["A", "1"]]), rows_page([["B", "2"]])]))
        assert r.status is PdfExtractionStatus.TEXT_EXTRACTED
        assert [s.name for s in r.document.settings] == ["B"]
        assert r.warnings == ("Page 1: text could not be extracted.",)

    def test_control_characters_are_stripped(self):
        row = extractor._parse_row(extractor._clean_line("A\x00B   5"))
        assert row.name == "AB"

    def test_extractor_is_relay_neutral(self):
        text = Path(extractor.__file__).read_text(encoding="utf-8").lower()
        for word in ("p441", "siemens", "abb", "toshiba", "micom", "7sa", "red670", "zone 1", "distance"):
            assert word not in text, word

    def test_extractor_does_not_persist(self):
        text = Path(extractor.__file__).read_text(encoding="utf-8")
        for forbidden in ("open(", "write_bytes", "mkdir", "tempfile", "psycopg", "app.storage"):
            assert forbidden not in text


class TestDeterminism:
    def test_repeat_extraction_is_identical(self):
        pdf = build_pdf([rows_page([["21 Heading"], ["R1 = 1.84 ohm"], ["A", "2", "0/1"]]), rows_page([["B", "3"]])])
        first, second = extract_pdf(pdf), extract_pdf(pdf)
        assert first == second
        assert first.document.settings == second.document.settings


SAMPLE_DIR = os.environ.get("RELAY_SAMPLE_PDF_DIR")
SAMPLES = ["p441", "7sa511", "7sa613", "7sl87", "grl200", "grz100", "rcs", "red670", "rel511", "rel670", "lfzp", "relz100"]


@pytest.mark.skipif(not SAMPLE_DIR, reason="owner sample PDFs are not committed; set RELAY_SAMPLE_PDF_DIR to run")
@pytest.mark.parametrize("name", SAMPLES)
def test_real_sample_regression(name):
    """Structure and provenance only: no engineering meaning is asserted."""
    from pypdf import PdfReader

    path = Path(SAMPLE_DIR) / f"{name}.pdf"
    if not path.exists():
        pytest.skip(f"{path.name} not available")
    data = path.read_bytes()
    r = extract_pdf(data)
    assert r.status is PdfExtractionStatus.TEXT_EXTRACTED
    assert r.page_count == len(PdfReader(io.BytesIO(data)).pages) == r.pages_with_text
    settings = r.document.settings
    assert settings and len({s.setting_id for s in settings}) == len(settings)
    for s in settings:
        assert 1 <= s.location.page <= r.page_count and s.source_text
        assert s.extraction.extractor_id == "generic_pdf_text"
    pages = [s.location.page for s in settings]
    assert pages == sorted(pages)
    assert extract_pdf(data) == r  # deterministic
