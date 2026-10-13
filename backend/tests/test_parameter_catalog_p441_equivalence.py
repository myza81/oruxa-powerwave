"""The MiCOM P44x catalog reproduces the hand-written P441 profile on every field it migrates.

The hand-written profile (`micom-p441-v1`) is not removed: it stays the production path. These tests
run both on the same documents -- a clean sheet and many degraded ones -- and require identical
canonical values, interpretation status and unresolved cause for every canonical parameter the
catalog maps, and identical cited source settings on the clean sheet.
"""

from __future__ import annotations

import pytest

from app.domain.parameter_catalog.interpreter import CatalogInterpreter
from app.domain.parameter_catalog.loader import load_store
from app.domain.relay_import.provenance import MappingStatus, UnresolvedCause
from app.relay_profiles.micom_p441 import MicomP441Profile
from tests.parameter_catalog_equivalence import differences
from tests.relay_p441_fixtures import make_doc

STORE = load_store()
CATALOG = STORE.get("schneider-micom-p44x-catalog")
PROFILE = MicomP441Profile()


def both(**kw):
    document = make_doc(**kw)
    return PROFILE.interpret(document), CatalogInterpreter(CATALOG, STORE.registry).interpret(document)


def check(**kw):
    profile_model, catalog_model = both(**kw)
    diffs, compared = differences(profile_model, catalog_model, CATALOG)
    assert not diffs, "\n".join(str(d) for d in diffs)
    return profile_model, catalog_model, compared


class TestTheCatalog:
    def test_the_p44x_catalog_is_valid_tested_and_not_yet_the_production_path(self):
        assert CATALOG is not None and not STORE.rejected
        assert CATALOG.lifecycle == "tested" and CATALOG.applicability.model == "P441"
        assert CATALOG not in STORE.active()

    def test_the_migrated_subset_covers_ct_vt_basis_timers_and_resistive_reaches(self):
        canonicals = {m.canonical for m in CATALOG.mappings}
        assert canonicals == {
            "ct_vt.ct_primary", "ct_vt.ct_secondary", "ct_vt.vt_primary", "ct_vt.vt_secondary", "ct_vt.impedance_basis",
            "distance.zone.common_delay", "distance.zone.r_right", "distance.zone.r_phase_earth", "distance.zone.direction",
        }

    def test_the_catalog_identification_matches_the_registered_descriptor(self):
        from app.relay_profiles.identification_catalogue import IDENTIFICATION_DESCRIPTORS

        descriptor = next(d for d in IDENTIFICATION_DESCRIPTORS if d.profile_id == CATALOG.profile_id)
        ident = CATALOG.identification
        assert (descriptor.manufacturer, descriptor.relay_family, descriptor.model) == (
            CATALOG.applicability.manufacturer, CATALOG.applicability.family, CATALOG.applicability.model)
        assert descriptor.model_patterns == ident.model_patterns and descriptor.family_markers == ident.family_markers
        assert [(s.signature_id, s.pattern, s.min_matches) for s in descriptor.parameter_signatures] == [
            (s["name"], s["pattern"], s["min_matches"]) for s in ident.parameter_signatures]


class TestCleanSheet:
    def test_every_migrated_field_is_identical_including_its_cited_sources_and_raw_text(self):
        profile_model, catalog_model = both()
        diffs, compared = differences(profile_model, catalog_model, CATALOG, sources=True, raw=True)
        assert not diffs, "\n".join(str(d) for d in diffs)
        # 5 document values + (5 delays + 5 right + 5 earth + 1 direction) over the five zones' fields
        assert compared >= 20

    def test_the_values_are_the_sheets(self):
        _, model, _ = check()
        t = model.transformers
        assert (t.ct_primary_a.value, t.ct_secondary_a.value, t.vt_primary_v.value, t.vt_secondary_v.value) == (1200.0, 1.0, 132000.0, 110.0)
        assert t.setting_basis.value.value == "secondary"
        z1, z3, z4, zp = (model.zone(i) for i in ("Z1", "Z3", "Z4", "ZP"))
        assert (z1.common_timer_s.value, z1.resistive_reach.phase_phase.value, z1.resistive_reach.phase_earth.value) == (0.0, 2.11, 7.02)
        # Zones 3 and 4 share one pair of resistive reaches and cite the same settings
        assert z3.resistive_reach.phase_phase.value == z4.resistive_reach.phase_phase.value == 6.34
        assert {s.setting_id for s in z3.resistive_reach.phase_phase.provenance.sources} == {s.setting_id for s in z4.resistive_reach.phase_phase.provenance.sources}
        assert zp.direction.value.value == "forward"

    def test_the_catalog_records_where_the_value_came_from(self):
        _, model, _ = check()
        p = model.zone("Z2").resistive_reach.phase_phase.provenance
        assert (p.catalog_id, p.catalog_version, p.canonical_id) == ("schneider-micom-p44x-catalog", "1.0.0", "distance.zone.r_right")
        assert p.sources[0].parameter_id == "3013" and p.sources[0].parameter_name == "R2Ph"
        assert p.status is MappingStatus.MAPPED

    def test_the_ohm_values_follow_the_ct_secondary(self):
        # '/I1' is secondary ohms only with a 1 A CT secondary: with 5 A it is not established
        _, model, _ = check(overrides={"0A08": ("Phase CT Sec'y", "5", "1A/5A")})
        assert not model.zone("Z1").resistive_reach.phase_phase.is_resolved


class TestDegradedSheetsAgree:
    @pytest.mark.parametrize("label,kwargs", [
        ("secondary CT 5 A", dict(overrides={"0A08": ("Phase CT Sec'y", "5", "1A/5A")})),
        ("CT secondary outside 1/5", dict(overrides={"0A08": ("Phase CT Sec'y", "2", "1A/5A")})),
        ("CT secondary printed range wrong", dict(overrides={"0A08": ("Phase CT Sec'y", "1", "0-10")})),
        ("CT primary dropped", dict(drop=("0A07",))),
        ("CT primary renamed", dict(overrides={"0A07": ("Something Else", "1200", "1-30000A")})),
        ("CT primary non-numeric", dict(overrides={"0A07": ("Phase CT Primary", "twelve", "1-30000A")})),
        ("CT primary out of range", dict(overrides={"0A07": ("Phase CT Primary", "99999", "1-30000A")})),
        ("CT primary wrong unit", dict(overrides={"0A07": ("Phase CT Primary", "1200", "1-30000kA")})),
        ("CT primary no unit", dict(overrides={"0A07": ("Phase CT Primary", "1200", "1-30000")})),
        ("VT primary dropped", dict(drop=("0A01",))),
        ("VT secondary wrong unit", dict(overrides={"0A02": ("Main VT Sec'y", "110", "80-140kV")})),
        ("basis primary", dict(overrides={"092E": ("Setting Values", "Primary", "Sec'y/Primary")})),
        ("basis unknown", dict(overrides={"092E": ("Setting Values", "Per Unit", "Sec'y/Primary")})),
        ("basis dropped", dict(drop=("092E",))),
        ("R1Ph out of range", dict(overrides={"300D": ("R1Ph", "999", "0-400 /I1")})),
        ("R1Ph explicit ohm", dict(overrides={"300D": ("R1Ph", "2.11", "0-400 ohm")})),
        ("R1Ph unprinted unit", dict(overrides={"300D": ("R1Ph", "2.11", "0-400")})),
        ("R1Ph wrong unit", dict(overrides={"300D": ("R1Ph", "2.11", "0-400 s")})),
        ("R1Ph no range at all", dict(overrides={"300D": ("R1Ph", "2.11", None)})),
        ("R2G dropped", dict(drop=("3012",))),
        ("R3G shared reach dropped", dict(drop=("3018",))),
        ("tZ1 wrong unit", dict(overrides={"300E": ("tZ1", "0", "0-10.0 ms")})),
        ("tZ2 non-numeric", dict(overrides={"3014": ("tZ2", "fast", "0-10.0 s")})),
        ("tZ4 dropped", dict(drop=("301C",))),
        ("Zone P direction reverse", dict(overrides={"301D": ("ZoneP - Direct", "Directional Rev", "Directional FWD/REV")})),
        ("Zone P direction unknown", dict(overrides={"301D": ("ZoneP - Direct", "Both", "Directional FWD/REV")})),
        ("Zone P absent", dict(drop=("301D", "3020", "3021", "3022", "3023", "301E", "301F"))),
        ("duplicate identical", dict(extra=((("300D"), "R1Ph", "2.11", "0-400 /I1"),))),
        ("duplicate conflicting", dict(extra=((("300D"), "R1Ph", "3.99", "0-400 /I1"),))),
    ])
    def test_the_catalog_and_the_profile_agree(self, label, kwargs):
        check(**kwargs)

    def test_a_code_under_another_name_is_a_conflict_in_both(self):
        profile_model, catalog_model, _ = check(overrides={"0A07": ("Something Else", "1200", "1-30000A")})
        for model in (profile_model, catalog_model):
            ct = model.transformers.ct_primary_a
            assert not ct.is_resolved and ct.provenance.cause is UnresolvedCause.CONFLICT

    def test_the_whole_document_is_still_accounted_for_by_the_catalog(self):
        document = make_doc()
        model = CatalogInterpreter(CATALOG, STORE.registry).interpret(document)
        accounted = model.referenced_setting_ids()
        assert {s.setting_id for s in document.settings} == set(accounted)
        distance_unmapped = [u for u in model.unmapped_settings if not u.out_of_scope]
        assert {u.name for u in distance_unmapped} >= {"Z1", "kZ1 Res Comp", "Line Length"}      # not migrated: left raw
        assert next(u for u in model.unmapped_settings if u.name == "VTS Time Delay").out_of_scope is True
