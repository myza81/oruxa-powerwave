"""The administrator workflow on the file system: edit JSON -> validate -> dry-run -> make available.

Neither command may change the catalog tree or any application state.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from app.domain.parameter_catalog.dry_run import dry_run, render_text, to_dict
from app.domain.parameter_catalog.loader import CATALOG_ROOT, default_store
from app.tools.catalog_cli import main
from tests.relay_p441_fixtures import make_doc as p441_doc
from tests.relay_red670_fixtures import make_doc as red670_doc
from tests.test_parameter_catalog_new_relay_by_json import acme_catalog, acme_pdf

STORE = default_store()


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    shutil.copytree(CATALOG_ROOT, tmp_path / "catalogs")
    return tmp_path / "catalogs"


def snapshot(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.rglob("*")) if p.is_file()}


def write(root: Path, rel: str, data) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")
    return path


def run(capsys, *argv: str):
    code = main(list(argv))
    out = capsys.readouterr()
    return code, out.out, out.err


class TestValidateCatalog:
    def test_a_valid_catalog_is_reported_ok_and_nothing_changes(self, tree, capsys):
        before = snapshot(tree)
        code, out, _ = run(capsys, "validate-catalog", str(tree / "hitachi_energy" / "red670.json"), "--root", str(tree))
        assert code == 0 and out.startswith("OK: hitachi-red670-catalog 1.0.0 (active)")
        assert snapshot(tree) == before

    def test_a_new_catalog_file_is_validated_against_the_installed_ones(self, tree, capsys):
        path = write(tree, "acme/x1.json", acme_catalog("tested"))
        code, out, _ = run(capsys, "validate-catalog", str(path), "--root", str(tree))
        assert code == 0 and "acme-x1 1.0.0 (tested)" in out and 'will not use it until "lifecycle" is "active"' in out

    def test_problems_are_listed_together_with_the_mapping_they_are_in(self, tree, capsys):
        data = acme_catalog("tested")
        data["mappings"][0]["canonical"] = "ct_vt.not_a_thing"                   # unknown canonical target
        data["mappings"][1]["transform"] = [{"type": "eval", "expr": "__import__('os').system('x')"}]   # code
        data["mappings"][2]["source"]["unit"] = "parsec"                          # invalid unit
        path = write(tree, "acme/x1.json", data)
        code, out, _ = run(capsys, "validate-catalog", str(path), "--root", str(tree))
        assert code == 1 and out.startswith("INVALID")
        first, second, third = (data["mappings"][i]["id"] for i in range(3))
        assert f"mappings[{first}].canonical: [unknown_canonical]" in out
        assert f"mappings[{second}].transform[0]: [unsupported_transform]" in out
        assert f"mappings[{third}].source.unit: [invalid_unit]" in out
        assert "The catalog was not used." in out

    def test_a_file_that_is_not_json_names_the_line(self, tree, capsys):
        path = write(tree, "acme/x1.json", '{\n  "catalog_id": \n}')
        code, out, _ = run(capsys, "validate-catalog", str(path), "--root", str(tree))
        assert code == 1 and "line 3" in out and "not valid JSON" in out

    def test_a_second_active_catalog_for_the_same_relay_is_refused(self, tree, capsys):
        clone = json.loads((tree / "hitachi_energy" / "red670.json").read_text(encoding="utf-8"))
        clone["catalog_id"] = "hitachi-red670-catalog-copy"
        path = write(tree, "hitachi_energy/red670_copy.json", clone)
        code, out, _ = run(capsys, "validate-catalog", str(path), "--root", str(tree))
        assert code == 1 and "already active for the same relay and firmware" in out

    def test_a_locked_version_whose_meaning_changed_is_refused(self, tree, capsys):
        path = tree / "hitachi_energy" / "red670.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["mappings"][0]["note"] = "edited without a new version"
        path.write_text(json.dumps(data), encoding="utf-8")
        code, out, _ = run(capsys, "validate-catalog", str(path), "--root", str(tree))
        assert code == 1 and "locked and its meaning changed" in out

    def test_a_missing_file_is_a_clear_error(self, tree, capsys):
        code, out, _ = run(capsys, "validate-catalog", str(tree / "nope.json"), "--root", str(tree))
        assert code == 1 and "cannot read the file" in out

    def test_list_shows_installed_and_rejected_catalogs(self, tree, capsys):
        write(tree, "acme/broken.json", '{"nope"')
        code, out, _ = run(capsys, "list", "--root", str(tree))
        assert code == 1 and "hitachi-red670-catalog 1.0.0  active" in out and "REJECTED acme/broken.json" in out


class TestDryRun:
    def test_a_real_pdf_is_read_through_a_draft_catalog_without_changing_anything(self, tree, tmp_path, capsys):
        catalog = write(tree, "acme/x1.json", acme_catalog("draft"))
        pdf = tmp_path / "acme.pdf"
        pdf.write_bytes(acme_pdf())
        before = snapshot(tree)
        code, out, _ = run(capsys, "dry-run", str(catalog), str(pdf), "--root", str(tree))
        assert code == 0 and "nothing was changed" in out
        assert "[mapped]" in out and "ct_vt.vt_primary" in out and "132 kV → 132000 V" in out
        assert "Hostname" in out                                           # unmapped, retained
        assert snapshot(tree) == before
        assert default_store().get("acme-x1") is None                      # the application's catalogs are untouched

    def test_json_output_is_machine_readable(self, tree, tmp_path, capsys):
        catalog = write(tree, "acme/x1.json", acme_catalog("draft"))
        pdf = tmp_path / "acme.pdf"
        pdf.write_bytes(acme_pdf())
        code, out, _ = run(capsys, "dry-run", str(catalog), str(pdf), "--root", str(tree), "--json")
        body = json.loads(out)
        assert code == 0 and body["catalog_id"] == "acme-x1" and body["counts"]["mapped"] > 0 and body["counts"]["transformed"] >= 1
        assert body["coverage"]["extracted_settings"] >= 20
        assert any(u["name"] == "Hostname" for u in body["unmapped"])

    def test_an_invalid_catalog_is_not_dry_run(self, tree, tmp_path, capsys):
        broken = acme_catalog("draft")
        broken["mappings"][0]["canonical"] = "ct_vt.not_a_thing"
        catalog = write(tree, "acme/x1.json", broken)
        pdf = tmp_path / "acme.pdf"
        pdf.write_bytes(acme_pdf())
        code, out, err = run(capsys, "dry-run", str(catalog), str(pdf), "--root", str(tree))
        assert code == 1 and "INVALID" in err and out == ""

    def test_a_document_that_is_not_a_pdf_is_a_usage_error(self, tree, tmp_path, capsys):
        catalog = write(tree, "acme/x1.json", acme_catalog("draft"))
        sheet = tmp_path / "sheet.xlsx"
        sheet.write_bytes(b"x")
        code, _, err = run(capsys, "dry-run", str(catalog), str(sheet), "--root", str(tree))
        assert code == 2 and "only PDF" in err


class TestDiagnostics:
    """recognised / mapped / transformed / unmapped / conflicting, for a relay that already has a catalog."""

    def report(self, catalog_id, document):
        return dry_run(STORE.get(catalog_id), STORE.registry, document)

    def test_red670_shows_mapped_transformed_unsupported_and_unmapped(self):
        document = red670_doc(extra=(("ZM01-:MysteryKnob", "13", "0-99"),))
        r = self.report("hitachi-red670-catalog", document)
        assert r.counts()["mapped"] > 30 and r.counts()["unsupported"] >= 1
        rfpp = next(e for e in r.transformed if e.canonical_id == "distance.zone.r_right" and e.zone == "Z2")
        assert (rfpp.raw_value, rfpp.value) == ("10", "5.0") and "÷ 2" in rfpp.transformation
        gap = next(e for e in r.of("unsupported"))
        assert gap.canonical_id == "distance.zone.r_left" and {s.name for s in gap.sources} == {"ZD01-:ArgDir", "ZD01-:ArgNegRes"}
        assert any(u.name == "ZM01-:MysteryKnob" for u in r.unmapped)
        assert r.coverage.extracted_settings == len(document.settings)

    def test_disagreeing_values_are_reported_as_conflicting(self):
        r = self.report("hitachi-red670-catalog", red670_doc(overrides={"ZM02-:IBase": ("1000", "1-99999")}))
        (conflict,) = [e for e in r.conflicting if e.canonical_id == "ct_vt.current_base"]
        assert {s.name for s in conflict.sources} == {"ZM01-:IBase", "ZM02-:IBase", "ZM03-:IBase"}
        assert r.coverage.canonical_values_conflicting >= 1
        assert "[conflict]" in render_text(r)

    def test_p441_shows_the_settings_the_catalog_leaves_to_the_extension_as_unmapped(self):
        r = self.report("schneider-micom-p44x-catalog", p441_doc())
        names = {u.name for u in r.unmapped}
        assert "Line Angle" in names and "kZ1 Res Comp" in names             # dry-run shows the catalog's own reading only
        assert r.counts()["mapped"] >= 20

    def test_a_dry_run_is_pure(self):
        document = p441_doc()
        a, b = (to_dict(self.report("schneider-micom-p44x-catalog", document)) for _ in range(2))
        assert a == b
