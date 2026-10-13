"""The Hitachi Energy RED670 catalog reproduces the corrected hand-written RED670 profile.

RFPP is the test of the whole idea: its meaning (a phase-phase *loop* value, halved for the R-X
plane) lives in the catalog as data -- a ``divide`` primitive with a description -- and the generic
matcher produces the same canonical value, status and provenance as the profile's Python.
"""

from __future__ import annotations

import pytest

from app.domain.parameter_catalog.interpreter import CatalogInterpreter
from app.domain.parameter_catalog.loader import load_store
from app.domain.relay_import.canonical_distance import CharacteristicType, GeometryMode, SettingBasis, ZoneDirection, ZoneStatus
from app.domain.relay_import.provenance import MappingAuthority, MappingStatus, UnresolvedCause
from app.relay_profiles.hitachi_red670 import HitachiRed670Profile
from tests.parameter_catalog_equivalence import differences
from tests.relay_red670_fixtures import default_sections, make_doc, zone_rows

STORE = load_store()
CATALOG = STORE.get("hitachi-red670-catalog")
PROFILE = HitachiRed670Profile()


def both(**kw):
    document = make_doc(**kw)
    return PROFILE.interpret(document), CatalogInterpreter(CATALOG, STORE.registry).interpret(document)


def sections_with(zone_kwargs: dict[int, dict]):
    out = []
    for label, rows in default_sections():
        for n, kw in zone_kwargs.items():
            if label.endswith(f"ZMQPDIS:{n}"):
                rows = zone_rows(n, **kw)
        out.append((label, rows))
    return out


def check(*, sources=False, raw=False, **kw):
    profile_model, catalog_model = both(**kw)
    diffs, compared = differences(profile_model, catalog_model, CATALOG, sources=sources, raw=raw)
    assert not diffs, "\n".join(str(d) for d in diffs)
    return profile_model, catalog_model, compared


class TestTheCatalog:
    def test_the_red670_catalog_is_valid_tested_and_not_yet_the_production_path(self):
        assert CATALOG is not None and not STORE.rejected
        assert CATALOG.lifecycle == "tested" and CATALOG.applicability.model == "RED670" and CATALOG not in STORE.active()

    def test_the_migrated_subset_includes_the_requested_parameters(self):
        sources = {s.name for m in CATALOG.mappings for _, s in ((("value", m.source),) if m.source else ()) + m.sources if s.name}
        for needed in ("ZM{nn}-:Operation", "ZM{nn}-:OperationDir", "ZM{nn}-:OperationPP", "ZM{nn}-:OperationPE", "ZM{nn}-:X1",
                       "ZM{nn}-:RFPP", "ZM{nn}-:RFPE", "ZM{nn}-:tPP", "ZM{nn}-:tPE"):
            assert needed in sources, needed
        families = {s.family.member for m in CATALOG.mappings if m.source and (s := m.source).family}
        assert {"ZM{nn}-:IBase", "ZM{nn}-:UBase", "CTprim{n}", "CTsec{n}", "VTprim{n}", "VTsec{n}"} <= families

    def test_the_catalog_identification_matches_the_registered_descriptor(self):
        from app.relay_profiles.identification_catalogue import IDENTIFICATION_DESCRIPTORS

        descriptor = next(d for d in IDENTIFICATION_DESCRIPTORS if d.profile_id == CATALOG.profile_id)
        ident = CATALOG.identification
        assert (descriptor.manufacturer, descriptor.relay_family, descriptor.model) == (
            CATALOG.applicability.manufacturer, CATALOG.applicability.family, CATALOG.applicability.model)
        assert descriptor.model_patterns == ident.model_patterns
        assert [(s.signature_id, s.pattern, s.min_matches) for s in descriptor.parameter_signatures] == [
            (s["name"], s["pattern"], s["min_matches"]) for s in ident.parameter_signatures]


class TestCleanSheet:
    def test_every_migrated_field_is_identical_with_its_cited_sources_and_raw_text(self):
        profile_model, catalog_model = both()
        diffs, compared = differences(profile_model, catalog_model, CATALOG, sources=True, raw=True)
        assert not diffs, "\n".join(str(d) for d in diffs)
        assert compared >= 70

    def test_the_catalog_model_carries_the_corrected_semantics(self):
        _, model, _ = check()
        z2 = model.zone("Z2")
        rr = z2.resistive_reach
        assert (rr.phase_phase.value, rr.phase_earth.value) == (5.0, 20.0)          # RFPP 10 / 2 ; RFPE 20 as printed
        assert z2.characteristic.type.value is CharacteristicType.QUADRILATERAL
        assert z2.characteristic.type.provenance.status is MappingStatus.MAPPED
        assert z2.characteristic.geometry_mode is GeometryMode.EXPLICIT_RX
        assert model.transformers.setting_basis.value is SettingBasis.PRIMARY
        assert model.transformers.setting_basis.provenance.status is MappingStatus.MAPPED
        assert (z2.status.value, z2.direction.value) == (ZoneStatus.ENABLED, ZoneDirection.FORWARD)
        assert model.zone("Z4").status.value is ZoneStatus.DISABLED

    def test_the_left_resistive_reach_is_a_capability_gap_with_the_directional_angles_preserved(self):
        _, model, _ = check(sources=True)
        z1 = model.zone("Z1")
        left = z1.resistive_reach.reverse
        assert not left.is_resolved and left.provenance.cause is UnresolvedCause.UNSUPPORTED
        assert {s.parameter_name for s in left.provenance.sources} == {"ZD01-:ArgDir", "ZD01-:ArgNegRes"}
        assert "capability gap" in " ".join(left.provenance.notes) and "ArgDir = 15" in " ".join(left.provenance.notes)
        params = {p.name: p.value.value for p in z1.characteristic.parameters}
        assert params["directional_arg_dir"] == 15.0 and params["directional_arg_neg_res"] == 115.0

    def test_the_catalog_and_the_profile_account_for_the_same_distance_settings(self):
        profile_model, catalog_model = both()
        ids = lambda m: {u.setting_id for u in m.unmapped_settings if not u.out_of_scope}          # noqa: E731
        assert ids(catalog_model) >= ids(profile_model)
        out = lambda m: {u.setting_id for u in m.unmapped_settings if u.out_of_scope}              # noqa: E731
        assert out(catalog_model) >= out(profile_model)
        assert catalog_model.referenced_setting_ids() == {s.setting_id for s in make_doc().settings}


class TestRfppIsDefinedByMetadata:
    def test_the_catalog_holds_rfpp_as_a_declared_transformation_not_code(self):
        (mapping,) = [m for m in CATALOG.mappings if m.canonical == "distance.zone.r_right"]
        assert [s.type for s in mapping.steps] == ["divide"] and mapping.steps[0].params == {"by": 2}
        assert mapping.source.name == "ZM{nn}-:RFPP" and mapping.authority == "documented_derivation" and mapping.confidence == "inferred"

    @pytest.mark.parametrize("rfpp", ["7", "10", "0.1", "21.91", "3000"])
    def test_the_oem_value_is_preserved_and_the_canonical_value_is_half(self, rfpp):
        profile_model, catalog_model = both(overrides={"ZM01-:RFPP": (rfpp, "0.1-3000")})
        for model in (profile_model, catalog_model):
            pp = model.zone("Z1").resistive_reach.phase_phase
            assert pp.value == float(rfpp) / 2.0 and pp.provenance.raw_value == rfpp
            assert pp.provenance.sources[0].parameter_name == "ZM01-:RFPP"
        a, b = (m.zone("Z1").resistive_reach.phase_phase.provenance for m in (profile_model, catalog_model))
        assert a.transformation == b.transformation and f"RFPP {rfpp} ohm/loop ÷ 2" in b.transformation
        assert a.authority == b.authority == MappingAuthority.DOCUMENTED_DERIVATION
        assert a.status == b.status == MappingStatus.INFERRED

    def test_rfpe_is_never_transformed(self):
        _, catalog_model = both(overrides={"ZM01-:RFPE": ("15", "0.1-9000")})
        pe = catalog_model.zone("Z1").resistive_reach.phase_earth
        assert pe.value == 15.0 and pe.provenance.transformation is None and pe.provenance.status is MappingStatus.MAPPED

    def test_catalog_provenance_names_the_catalog_version_and_the_canonical_target(self):
        _, catalog_model = both()
        p = catalog_model.zone("Z3").resistive_reach.phase_phase.provenance
        assert (p.catalog_id, p.catalog_version, p.canonical_id) == ("hitachi-red670-catalog", "1.0.0", "distance.zone.r_right")
        assert p.profile_version == "hitachi-red670-catalog-v1.0.0"


class TestDegradedSheetsAgree:
    @pytest.mark.parametrize("label,kwargs", [
        ("X1 dropped", dict(drop=("ZM01-:X1",))),
        ("X1 outside range", dict(overrides={"ZM01-:X1": ("5000", "0.1-3000")})),
        ("X1 non-numeric", dict(overrides={"ZM02-:X1": ("far", "0.1-3000")})),
        ("X1 wrong printed unit", dict(overrides={"ZM02-:X1": ("11", "0.1-3000 A")})),
        ("RFPP dropped", dict(drop=("ZM01-:RFPP",))),
        ("RFPP non-numeric", dict(overrides={"ZM03-:RFPP": ("n/a", "0.1-3000")})),
        ("RFPE dropped", dict(drop=("ZM02-:RFPE",))),
        ("RFPE out of range", dict(overrides={"ZM02-:RFPE": ("99999", "0.1-9000")})),
        ("Operation OFF", dict(sections=sections_with({1: dict(operation="OFF")}))),
        ("OperationDir Off", dict(sections=sections_with({2: dict(direction="Off")}))),
        ("OperationDir reverse and non-dir", dict(sections=sections_with({1: dict(direction="Reverse"), 2: dict(direction="Non-dir")}))),
        ("Operation unrecognised", dict(overrides={"ZM01-:Operation": ("MAYBE", "OFF/ON")})),
        ("OperationDir unrecognised", dict(overrides={"ZM01-:OperationDir": ("Sideways", "Off/Non-dir/Forw/Rev")})),
        ("Operation dropped", dict(drop=("ZM01-:Operation",))),
        ("OperationDir dropped", dict(drop=("ZM02-:OperationDir",))),
        ("Operation and direction dropped", dict(drop=("ZM01-:Operation", "ZM01-:OperationDir"))),
        ("OperationPE OFF", dict(sections=sections_with({2: dict(pe="OFF")}))),
        ("OperationPP unrecognised", dict(overrides={"ZM03-:OperationPP": ("??", "OFF/ON")})),
        ("OperationPE dropped", dict(drop=("ZM01-:OperationPE",))),
        ("timer gate OFF", dict(sections=sections_with({1: dict(timer_gate="OFF")}))),
        ("timer gate dropped", dict(drop=("ZM03-:Timer tPP",))),
        ("timer gate unrecognised", dict(overrides={"ZM01-:Timer tPE": ("MAYBE", "OFF/ON")})),
        ("tPP dropped", dict(drop=("ZM03-:tPP", "ZM03-:Timer tPP"))),
        ("tPE non-numeric", dict(overrides={"ZM01-:tPE": ("soon", "0-60")})),
        ("tPP out of range", dict(overrides={"ZM01-:tPP": ("900", "0-60")})),
        ("IBase dropped", dict(drop=("ZM01-:IBase", "ZM02-:IBase", "ZM03-:IBase"))),
        ("UBase unreadable", dict(overrides={"ZM01-:UBase": ("kV", "0.05-2000")})),
        ("UBase dropped everywhere", dict(drop=("ZM01-:UBase", "ZM02-:UBase", "ZM03-:UBase"))),
        ("no zone in service", dict(sections=sections_with({n: dict(operation="OFF") for n in (1, 2, 3)}))),
        ("CT primary channels disagree", dict(overrides={"CTprim2": ("1500", "1-99999")})),
        ("CT secondary channel missing", dict(drop=("NAMECH3", "ChannelType3", "CTsec3", "CTprim3"))),
        ("CT primary unreadable", dict(overrides={"CTprim1": ("lots", "1-99999")})),
        ("VT primary channels disagree", dict(overrides={"VTprim8": ("110", "0.05-2000")})),
        ("VT secondary dropped", dict(drop=("VTsec7", "VTsec8", "VTsec9"))),
        ("VT channel type changed", dict(overrides={"ChannelType9": ("CurrentProtection", None)})),
        ("heading renamed", dict(sections=[(l.replace("ZMQPDIS:1", "SOMETHING:1"), r) for l, r in default_sections()])),
        ("fault locator values", dict(overrides={"FLO1-:R1L": ("x", "0.001-1500")})),
        ("duplicate conflicting X1", dict(extra=(("ZM01-:X1", "7", "0.1-3000"),))),
        ("duplicate identical X1", dict(extra=(("ZM01-:X1", "6", "0.1-3000"),))),
    ])
    def test_the_catalog_and_the_profile_agree(self, label, kwargs):
        check(**kwargs)

    def test_bases_that_disagree_are_a_conflict_in_the_catalog_where_the_profile_says_missing(self):
        """The one deliberate divergence: the profile reports disagreeing IBase rows as merely Missing
        (an unresolved value with no recorded cause), the catalog classifies the disagreement as a
        Conflict -- as the CT/VT channels already are. Same value (unresolved), same status."""
        profile_model, catalog_model = both(overrides={"ZM02-:IBase": ("1000", "1-99999")})
        p, c = profile_model.transformers.current_base_a, catalog_model.transformers.current_base_a
        assert not p.is_resolved and not c.is_resolved
        assert (p.provenance.cause, c.provenance.cause) == (UnresolvedCause.MISSING, UnresolvedCause.CONFLICT)
        assert {s.parameter_name for s in c.provenance.sources} == {"ZM01-:IBase", "ZM02-:IBase", "ZM03-:IBase"}

    def test_any_number_of_zone_instances_is_found(self):
        sections = default_sections()
        sections.insert(5, ("IMP_PROT/DistanceZones/ZMQPDIS:5", zone_rows(5, x1="30", direction="Reverse")))
        _, model, _ = check(sections=sections)
        assert [z.zone_id for z in model.zones] == ["Z1", "Z2", "Z3", "Z4", "Z5"]
        assert model.zone("Z5").direction.value is ZoneDirection.REVERSE

    def test_the_scheme_notes_never_decide_a_state_through_the_catalog_either(self):
        _, model, _ = check(drop=("ZM04-:Operation", "ZM04-:OperationDir"))
        assert not model.zone("Z4").status.is_resolved


class TestMetadata:
    def test_identity_comes_from_the_catalog_and_the_documents_scheme_field(self):
        _, model = both()
        m = model.metadata
        assert (m.manufacturer.value, m.family.value, m.model.value, m.version.value) == ("Hitachi Energy", "Relion 670", "RED670", "V1.2")
        assert m.scheme_name.value == "RED670_V1.2_21_F11L"
        assert (m.profile_id, m.profile_version) == ("hitachi-red670", "hitachi-red670-catalog-v1.0.0")
        assert m.model.provenance.catalog_version == "1.0.0"

    def test_a_scheme_naming_another_relay_does_not_claim_a_red670(self):
        header = (("LZOP: 275kV", "Scheme: REL670_V1.2"), ("Utility ID: 1", "Active Group: X"), ("TAP NAME", "TAP SETTING", "TAP RANGE"))
        _, model = both(header=header)
        assert not model.metadata.model.is_resolved and model.metadata.scheme_name.value == "REL670_V1.2"
