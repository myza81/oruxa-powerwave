"""DEC-195: the parameter catalog is the primary mapping path for the targets it maps.

P441 and RED670 are interpreted by their *active* catalogs; the hand-written profile only supplies what
the catalog schema cannot yet express. These tests hold the three promises of that arrangement:

* nothing the user sees changes (review table + Apply payload equal the hand-written-only behaviour);
* every catalog-owned value is the catalog's -- never the extension's, never a fallback to it;
* everything else is kept: unmapped settings are retained "not interpreted" and never reach the engine.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import replace
from pathlib import Path

import pytest

from app.domain.parameter_catalog.catalog_first import overlay
from app.domain.parameter_catalog.interpreter import CatalogInterpreter
from app.domain.parameter_catalog.loader import (
    CATALOG_ROOT,
    CatalogLoadError,
    REGISTRY_FILE,
    default_store,
    load_store,
    verify_shipped_catalogs,
)
from app.domain.parameter_catalog.profile import CatalogProfile
from app.domain.relay_import.canonical_codec import encode_model
from app.domain.relay_import.canonical_distance import CanonicalDistanceProtectionModel
from app.domain.relay_import.provenance import MappingStatus, UnresolvedCause
from app.domain.relay_import.raw_document import RawSetting, SourceLocation
from app.domain.relay_import.review_state import ReviewDecisions
from app.relay_profiles.identification_catalogue import build_registry
from app.services.relay_apply_settings import apply_reviewed_settings
from tests.relay_review_tokens import apply_model
from app.services.relay_interpretation_summary import summarize_interpretation
from tests.parameter_catalog_equivalence import review_path, sourced_map
from tests.relay_p441_fixtures import make_doc as p441_doc
from tests.relay_red670_fixtures import default_sections, make_doc as red670_doc, zone_rows

STORE = default_store()
P441_CATALOG = STORE.get("schneider-micom-p44x-catalog")
RED670_CATALOG = STORE.get("hitachi-red670-catalog")


@pytest.fixture(scope="module")
def legacy(tmp_path_factory):
    """The registry as it behaved before catalogs were active: hand-written profiles only."""
    root = tmp_path_factory.mktemp("no_catalogs")
    (root / "canonical").mkdir()
    shutil.copy(CATALOG_ROOT / REGISTRY_FILE, root / REGISTRY_FILE)
    registry = build_registry(load_store(root))
    assert not any(isinstance(p, CatalogProfile) for p in registry._profiles)               # noqa: SLF001
    return registry


@pytest.fixture(scope="module")
def production():
    return build_registry()


def summary(registry, document):
    return summarize_interpretation(registry, document, registry.identify(document))


def review_core(s):
    """What the user sees, without the provenance bookkeeping that legitimately changes."""
    review = s.review
    rows = sorted(
        (g.id, i.item_id or "", i.primary, i.label, i.value_text, i.status, i.category, i.review_status, i.blocking)
        for g in review.groups for i in g.items
    )
    return {
        "rows": rows,
        "readiness": review.readiness.status,
        "blocking": sorted((b.message, b.item_ids) for b in review.blocking_issues),
        "counts": (review.mapped_count, review.assumption_count, review.missing_count, review.conflict_count,
                   review.unsupported_count, review.unreadable_count, review.not_interpreted_count),
        "not_interpreted": sorted((r.code, r.name, r.raw_value) for r in review.not_interpreted),
        "out_of_scope": sorted((r.code, r.name, r.raw_value) for r in review.out_of_scope),
        "zones": review.zone_count,
    }


def red670_sections_with(**per_zone):
    out = []
    for label, rows in default_sections():
        for n, kw in per_zone.items():
            if label.endswith(f"ZMQPDIS:{n[1:]}"):
                rows = zone_rows(int(n[1:]), **kw)
        out.append((label, rows))
    return out


P441_SHEETS = {
    "clean": {},
    "ct dropped": dict(drop=("0A07",)),
    "r1g unreadable": dict(overrides={"300C": ("R1G", "n/a", "0-400 /I1")}),
}
RED670_SHEETS = {
    "clean": {},
    "zone 1 off": dict(sections=red670_sections_with(z1=dict(operation="OFF"))),
    "rfpe unreadable": dict(overrides={"ZM02-:RFPE": ("many", "0.1-9000")}),
    "tpp dropped": dict(drop=("ZM03-:tPP", "ZM03-:Timer tPP")),
    "ct channels disagree": dict(overrides={"CTprim2": ("1500", "1-99999")}),
}


class TestNothingTheUserSeesChanges:
    @pytest.mark.parametrize("name", list(P441_SHEETS))
    def test_p441_review_table_is_the_accepted_one(self, name, production, legacy):
        document = p441_doc(**P441_SHEETS[name])
        assert review_core(summary(production, document)) == review_core(summary(legacy, document))

    @pytest.mark.parametrize("name", list(RED670_SHEETS))
    def test_red670_review_table_is_the_accepted_one(self, name, production, legacy):
        document = red670_doc(**RED670_SHEETS[name])
        assert review_core(summary(production, document)) == review_core(summary(legacy, document))

    def test_the_p441_apply_payload_is_unchanged(self, production, legacy):
        payloads = []
        for registry in (production, legacy):
            s = summary(registry, p441_doc())
            confirm = frozenset(i.item_id for g in s.review.groups for i in g.items if i.review_status == "to_confirm" and i.item_id)
            suggested = frozenset(f"zones[{z}].resistive_reach.reverse" for z in ("Z1", "Z2", "Z3"))     # the left reach
            decisions = ReviewDecisions(confirmed=confirm, suggested=suggested)
            plan = apply_model(s.model, decisions)
            payloads.append(plan)
        assert payloads[0] == payloads[1] and payloads[0].zones

    def test_the_red670_engine_view_and_readiness_are_unchanged(self, production, legacy):
        a, b = (summary(r, red670_doc()) for r in (production, legacy))
        assert a.review.engine == b.review.engine and a.review.readiness == b.review.readiness
        assert a.warnings == b.warnings

    def test_the_one_approved_divergence_disagreeing_bases_are_a_conflict(self, production, legacy):
        document = red670_doc(overrides={"ZM02-:IBase": ("1000", "1-99999")})
        base = {r: next(i for g in summary(r, document).review.groups for i in g.items if i.item_id == "transformers.current_base_a")
                for r in (production, legacy)}
        assert base[production].category == "conflict" and base[legacy].category == "missing"


class TestTheCatalogOwnsItsTargets:
    @pytest.mark.parametrize("sheets,make,catalog", [
        (P441_SHEETS, p441_doc, P441_CATALOG), (RED670_SHEETS, red670_doc, RED670_CATALOG)], ids=["p441", "red670"])
    def test_every_catalog_target_in_the_result_is_the_catalogs_even_when_it_does_not_resolve(self, sheets, make, catalog, production):
        profile = next(p for p in production._profiles if getattr(p, "catalog_id", None) == catalog.catalog_id)        # noqa: SLF001
        reg = STORE.registry
        for name, kwargs in sheets.items():
            document = make(**kwargs)
            model = profile.interpret(document)
            owned = sourced_map(model)
            for canonical in dict.fromkeys(m.canonical for m in catalog.mappings):
                param = reg.get(canonical)
                if param.plain:
                    continue
                zones = {z for m in catalog.mappings if m.canonical == canonical for z in m.zones}
                for zid in ([None] if param.scope == "document" else [z.zone_id for z in model.zones if "*" in zones or z.zone_id in zones]):
                    sourced = owned.get(review_path(param, zid))
                    if sourced is None:
                        continue
                    prov = sourced.provenance
                    assert prov.catalog_id == catalog.catalog_id and prov.catalog_version == catalog.version, (name, canonical, zid)
                    assert prov.canonical_id == canonical, (name, canonical, zid)
                    if sourced.is_resolved:
                        assert prov.profile_version == catalog.profile_version, (name, canonical, zid)

    def test_values_the_catalog_does_not_map_stay_with_the_extension(self, production):
        profile = next(p for p in production._profiles if getattr(p, "catalog_id", None) == P441_CATALOG.catalog_id)   # noqa: SLF001
        model = profile.interpret(p441_doc())
        assert model.line.length.provenance.catalog_id is None
        assert model.line.length.provenance.profile_version == "micom-p441-v1"
        assert model.metadata.profile_version == "micom-p441-v1"

    def test_a_catalog_target_that_does_not_resolve_is_never_rescued_by_the_extension(self):
        """Precedence rule 1: catalog mapping is authoritative -- also when it is Missing."""
        extension = _FixedExtension(x_reach=99.0)
        document = _doc(("Z1 Enable", "ON"))                    # the catalog finds no X Reach in this sheet
        profile = CatalogProfile(_acme(), STORE, extension)
        model = profile.interpret(document)
        z1 = model.zone("Z1")
        assert not z1.x_reach_ohm.is_resolved and z1.x_reach_ohm.provenance.catalog_id == "acme-x1"      # catalog says Missing
        assert z1.x_reach_ohm.provenance.cause in (None, UnresolvedCause.MISSING)

    def test_a_catalog_value_replaces_the_extensions_and_the_extension_keeps_the_rest(self):
        extension = _FixedExtension(x_reach=99.0, tilt=7.0)
        profile = CatalogProfile(_acme(), STORE, extension)
        model = profile.interpret(_doc(("Z1 X Reach", "6", "0.1-100")))
        z1 = model.zone("Z1")
        assert z1.x_reach_ohm.value == 6.0 and z1.x_reach_ohm.provenance.catalog_id == "acme-x1"
        assert z1.tilt_deg.value == 7.0 and z1.tilt_deg.provenance.catalog_id is None      # not in the catalog: the extension's
        assert profile.version == "acme-ext-v1" and profile.catalog_version == "1.0.0"

    def test_an_extension_of_another_relay_is_refused(self):
        other = _FixedExtension()
        other.profile_id = "someone-else"
        with pytest.raises(ValueError):
            CatalogProfile(_acme(), STORE, other)


class TestRfppIsDividedByTwoAndRfpeIsNot:
    def test_the_raw_oem_value_the_transformation_and_the_canonical_value_are_all_visible(self, production):
        s = summary(production, red670_doc())
        by_id = {i.item_id: i for g in s.review.groups for i in g.items if i.item_id}
        pp, pe = by_id["zones[Z2].resistive_reach.phase_phase"], by_id["zones[Z2].resistive_reach.phase_earth"]
        assert (pp.raw_value, pp.value_text) == ("10", "5 Ω")                      # Ω/loop in, Ω/phase out
        assert pp.transformation == "RFPP 10 ohm/loop ÷ 2 = 5 ohm (phase-phase boundary)"
        assert (pp.catalog_id, pp.catalog_version, pp.canonical_id) == ("hitachi-red670-catalog", "1.0.0", "distance.zone.r_right")
        assert (pp.sources[0].name, pp.sources[0].raw_value) == ("ZM02-:RFPP", "10")
        assert pp.label == "Phase-Phase Resistive Reach" or pp.label == "Right Resistive Reach (+R)"
        assert (pe.raw_value, pe.value_text, pe.transformation) == ("20", "20 Ω", None)       # no /2 by analogy
        assert pe.canonical_id == "distance.zone.r_phase_earth"


class TestUnknownParametersAreNeverLost:
    @pytest.mark.parametrize("make,extra,family", [
        (p441_doc, (("9999", "Mystery Setting", "42", None),), "p441"),
    ], ids=["p441"])
    def test_p441(self, make, extra, family, production):
        document = make(extra=extra)
        s = summary(production, document)
        self._assert_retained(s, document, "Mystery Setting", "42")

    def test_red670(self, production):
        document = red670_doc(extra=(("ZM01-:MysteryKnob", "13", "0-99"),))
        self._assert_retained(summary(production, document), document, "ZM01-:MysteryKnob", "13")

    @staticmethod
    def _assert_retained(s, document, name, raw):
        rows = [*s.review.not_interpreted, *s.review.out_of_scope]
        row = next(r for r in rows if r.name == name)
        assert row.raw_value is not None and raw in row.raw_value and row.page and row.line
        assert "not interpreted" in row.reason
        # nothing in the engine payload comes from it: no canonical value cites it
        profile = next(p for p in build_registry()._profiles if p.profile_id == s.profile_id)       # noqa: SLF001
        model = profile.interpret(document)
        raw_id = next(x.setting_id for x in document.settings if x.name == name)
        assert all(raw_id not in {r.setting_id for r in v.provenance.sources} for _, v in model.iter_sourced())
        assert raw_id in {u.setting_id for u in model.unmapped_settings}

    def test_no_raw_setting_is_discarded_by_the_merge(self, production):
        for make, sheets in ((p441_doc, P441_SHEETS), (red670_doc, RED670_SHEETS)):
            for kwargs in sheets.values():
                document = make(**kwargs)
                s = summary(production, document)
                profile = next(p for p in production._profiles if p.profile_id == s.profile_id)       # noqa: SLF001
                model = profile.interpret(document)
                assert model.referenced_setting_ids() >= {x.setting_id for x in document.settings if x.raw_value is not None or x.parameter_id}


class TestCoverage:
    @pytest.mark.parametrize("make,catalog_id", [(p441_doc, "schneider-micom-p44x-catalog"), (red670_doc, "hitachi-red670-catalog")])
    def test_the_buckets_account_for_every_extracted_setting(self, make, catalog_id, production):
        document = make()
        s = summary(production, document)
        c = s.catalog_coverage
        assert (s.catalog_id, s.catalog_version, c["catalog_id"], c["catalog_version"]) == (catalog_id, "1.0.0", catalog_id, "1.0.0")
        assert c["extracted_settings"] == len(document.settings)
        assert (c["catalog_recognised_settings"] + c["extension_interpreted_settings"] + c["unmapped_settings"]
                == c["extracted_settings"])
        assert c["catalog_recognised_settings"] > 0 and c["canonical_values_mapped"] > 0
        assert c["unmapped_settings"] == c["not_interpreted_settings"] + c["outside_distance_settings"]
        assert s.review.catalog_coverage == c and s.review.catalog_id == catalog_id

    def test_red670_reports_the_directional_boundary_as_a_known_unsupported_value(self, production):
        c = summary(production, red670_doc()).catalog_coverage
        assert c["canonical_values_unsupported"] >= 1                     # the left boundary (ZDRDIR) has no representation

    def test_review_rows_are_not_the_raw_setting_count(self, production):
        document = p441_doc()
        s = summary(production, document)
        rows = sum(len(g.items) for g in s.review.groups)
        assert s.catalog_coverage["extracted_settings"] == len(document.settings) and rows != len(document.settings)


class TestVendorsWithoutACatalogAreUntouched:
    def test_7sa511_has_no_catalog_and_no_catalog_identity(self, production):
        profile = next(p for p in production._profiles if p.profile_id == "siemens-7sa511")        # noqa: SLF001
        assert not isinstance(profile, CatalogProfile) and profile.version == "siemens-7sa511-v2"


class TestRedirectionDirectionalBoundaryIsStillAGap:
    def test_the_zdrdir_left_boundary_is_unsupported_with_its_angles_preserved(self, production):
        s = summary(production, red670_doc())
        left = next(i for g in s.review.groups if g.id == "zone-Z1" for i in g.items if i.item_id == "zones[Z1].resistive_reach.reverse")
        assert left.category == "unsupported" and left.catalog_id == "hitachi-red670-catalog"
        assert {src.name for src in left.sources} == {"ZD01-:ArgDir", "ZD01-:ArgNegRes"}


class TestPresentationIsDrivenByCanonicalMetadata:
    def test_every_catalog_owned_primary_row_is_labelled_from_the_registry_never_the_oem(self, production):
        reg = STORE.registry
        for make in (p441_doc, red670_doc):
            s = summary(production, make())
            for g in s.review.groups:
                for i in g.items:
                    if i.catalog_id and i.primary:
                        param = reg.get(i.canonical_id)
                        assert any(i.label.startswith(t) for t in (param.label, *param.label_variants.values())), (i.item_id, i.label)
                        assert i.sources and all(src.name != i.label for src in i.sources)

    def test_a_catalog_may_declare_a_value_an_assumption_and_the_review_shows_it(self, production):
        s = summary(production, red670_doc())
        vt = next(i for g in s.review.groups for i in g.items if i.item_id == "transformers.vt_primary_v")
        assert vt.authority == "assumption" and vt.category == "assumption" and vt.status == "inferred"


class TestTheCatalogIsEditableData:
    def _tree(self, tmp_path: Path) -> Path:
        shutil.copytree(CATALOG_ROOT, tmp_path / "catalogs")
        return tmp_path / "catalogs"

    def _registry(self, root: Path):
        store = load_store(root)
        assert not store.rejected, [str(r) for r in store.rejected]
        return build_registry(store)

    def test_editing_a_transformation_changes_the_result_with_no_python_change(self, tmp_path):
        root = self._tree(tmp_path)
        path = root / "hitachi_energy" / "red670.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        step = next(m for m in data["mappings"] if m["id"] == "red670.r_right")["transform"]
        assert step["by"] == 2
        step["by"] = 4
        step["describe"] = "RFPP {input} ohm/loop ÷ 4 = {result} ohm (edited)"
        data["version"] = "1.0.1"
        path.write_text(json.dumps(data), encoding="utf-8")
        s = summary(self._registry(root), red670_doc())
        pp = next(i for g in s.review.groups for i in g.items if i.item_id == "zones[Z2].resistive_reach.phase_phase")
        assert (pp.value_text, pp.raw_value, pp.transformation) == ("2.5 Ω", "10", "RFPP 10 ohm/loop ÷ 4 = 2.5 ohm (edited)")
        assert pp.catalog_version == "1.0.1"                                       # v1 and v2 imports are distinguishable

    def test_editing_an_enum_changes_the_result_with_no_python_change(self, tmp_path):
        root = self._tree(tmp_path)
        path = root / "schneider" / "p44x.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        direction = next(m for m in data["mappings"] if m["id"] == "p441.direction.zp")["transform"]
        assert direction["type"] == "enum"
        flipped = {k: ("reverse" if v == "forward" else "forward" if v == "reverse" else v) for k, v in direction["map"].items()}
        direction["map"] = flipped
        data["version"] = "1.0.1"
        path.write_text(json.dumps(data), encoding="utf-8")
        edited = summary(self._registry(root), p441_doc())
        shipped = summary(build_registry(), p441_doc())
        pick = lambda s: next(i for g in s.review.groups for i in g.items if i.item_id == "zones[ZP].direction")      # noqa: E731
        assert pick(edited).value_text != pick(shipped).value_text and pick(edited).catalog_version == "1.0.1"

    def test_a_catalog_edited_into_an_invalid_one_is_rejected_whole_and_stops_the_service(self, tmp_path, monkeypatch):
        root = self._tree(tmp_path)
        path = root / "hitachi_energy" / "red670.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["mappings"][0]["canonical"] = "ct_vt.not_a_parameter"
        path.write_text(json.dumps(data), encoding="utf-8")
        store = load_store(root)
        assert [r.path for r in store.rejected] == ["hitachi_energy/red670.json"] and store.get("hitachi-red670-catalog") is None
        import app.domain.parameter_catalog.loader as loader

        monkeypatch.setattr(loader, "default_store", lambda: store)
        with pytest.raises(CatalogLoadError, match="hitachi_energy/red670.json"):
            verify_shipped_catalogs()

    def test_the_shipped_catalogs_verify(self):
        assert verify_shipped_catalogs().active()


# --- helpers for the extension-precedence tests -------------------------------------------------------

from tests.test_parameter_catalog_new_relay_by_json import acme_catalog                    # noqa: E402
from app.domain.parameter_catalog.catalog_validation import parse_catalog                  # noqa: E402
from app.domain.relay_import.canonical_distance import DistanceZone, RelayMetadata          # noqa: E402
from app.domain.relay_import.provenance import SourceRef, mapped, unresolved                          # noqa: E402
from app.domain.relay_import.raw_document import RawRelayDocument, SourceFormat             # noqa: E402


def _acme():
    return parse_catalog(acme_catalog(), STORE.registry, source="test")


def _doc(*rows):
    settings = tuple(
        RawSetting(setting_id=f"s{i}", name=n, parameter_id=None, raw_value=v, setting_range=None, section_path=(),
                   location=SourceLocation(page=1, line=i))
        for i, (n, v, *_rest) in enumerate(rows, start=1)
    )
    return RawRelayDocument(SourceFormat.PDF, settings)


class _FixedExtension:
    """A stand-in for a hand-written profile of the synthetic relay: it reads fixed values."""

    profile_id = "acme-x1"
    version = "acme-ext-v1"

    def __init__(self, x_reach: float | None = None, tilt: float | None = None, **_):
        self._x, self._tilt = x_reach, tilt

    def match(self, document):
        raise AssertionError("not used")

    def interpret(self, document) -> CanonicalDistanceProtectionModel:
        def val(v):
            return (mapped(v, sources=(SourceRef("ext"),), profile_id=self.profile_id, profile_version=self.version)
                    if v is not None else unresolved())
        zone = DistanceZone(zone_id="Z1", name="Zone 1")
        zone = replace(zone, x_reach_ohm=val(self._x), tilt_deg=val(self._tilt))
        return CanonicalDistanceProtectionModel(metadata=RelayMetadata(source_format=document.source_format), zones=(zone,))
