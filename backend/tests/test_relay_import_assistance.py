"""DEC-198 foundation -- Relay Import Assistance for Non-Expert Users.

The generic model only: catalog references and verified documented derivations, the
documented-relay-behaviour presentation, *not exposed* vs *missing*, *unverified* vs
*unsupported*, the approximation data model (conservative / bounded / unbounded), the
``ready_approximate`` readiness and the Apply ``approximations`` list. No relay is
approximated and no shipped catalog changes: every check here runs on the synthetic "Acme X1"
relay (it exists nowhere in the source tree) or on the shipped catalogs' lock.
"""

from __future__ import annotations

import math
import re
from dataclasses import asdict, replace
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.domain.parameter_catalog.catalog_validation import parse_catalog
from app.domain.parameter_catalog.errors import CatalogValidationError, IssueCode
from app.domain.parameter_catalog.loader import (
    canonical_registry,
    check_lock,
    default_store,
    load_lock,
    semantics_digest,
)
from app.domain.relay_import import approximation as approximation_module
from app.domain.relay_import.apply_settings import build_apply_plan, model_approximations
from app.domain.relay_import.approximation import (
    APPROVED_RULES,
    ApproximationClass,
    ApproximationRecord,
    ApproximationRule,
    ErrorEnvelope,
    approved_rule,
    rule_problems,
)
from app.domain.relay_import.canonical_codec import SnapshotError, decode_model, encode_model
from app.domain.relay_import.provenance import (
    DocumentReference,
    MappingAuthority,
    MappingStatus,
    Provenance,
    ProvenanceOrigin,
    Sourced,
    UnresolvedCause,
)
from app.domain.relay_import.review_state import APPLICABLE_READINESS, Readiness, compute_readiness
from app.schemas.relay_import import (
    ApplySettingsOut,
    ApproximationOut,
    ExtractionReviewOut,
    ReviewReadinessOut,
)
from app.services.relay_extraction_review import build_extraction_review
from app.services.relay_interpretation_summary import engine_adaptation
from tests.parameter_catalog_helpers import catalog_json, doc, interpret, mapping, parse
from tests.test_parameter_catalog_new_relay_by_json import ACME_ROWS, acme_catalog

VERIFIED_REF = {"id": "acme-manual-dist", "title": "Acme X-Series distance protection manual", "verification": "verified",
                "document": "AX-1000-EN", "section": "4.2 Zone characteristic", "page": 37}
UNVERIFIED_REF = {"id": "acme-app-note", "title": "Acme application note 12", "verification": "unverified"}


def acme_document():
    return doc(*[tuple(r) if len(r) == 3 else (r[0], r[1]) for r in ACME_ROWS[2:]])


def characteristic_mapping(zone: str = "*", **kw) -> dict:
    return mapping(
        f"char.{zone}", "distance.zone.characteristic", zone=zone, transform={"type": "constant", "value": "quadrilateral"},
        evidence=[{"name": "Head {zone}"}], authority="documented_derivation", **kw,
    )


def codes(exc: pytest.ExceptionInfo) -> set[str]:
    return set(exc.value.codes())


def review_of(model, document=None):
    document = document or acme_document()
    return build_extraction_review(model, document, engine_adaptation(model), not_interpreted=0)


def items(review):
    return {i.item_id: i for g in review.groups for i in g.items if i.item_id and i.primary}


# ---------------------------------------------------------------------------
# 1. References and verified documented derivations
# ---------------------------------------------------------------------------


class TestCatalogReferences:
    def test_a_verified_documented_derivation_requires_a_reference(self):
        data = catalog_json(characteristic_mapping(verification="verified"))
        with pytest.raises(CatalogValidationError) as exc:
            parse(data)
        assert IssueCode.UNVERIFIED_REFERENCE in codes(exc)

    def test_an_unverified_reference_is_not_enough_for_a_verified_derivation(self):
        data = catalog_json(characteristic_mapping(verification="verified", references=["acme-app-note"]),
                            references=[UNVERIFIED_REF])
        with pytest.raises(CatalogValidationError) as exc:
            parse(data)
        assert IssueCode.UNVERIFIED_REFERENCE in codes(exc)

    def test_a_verified_reference_carries_the_derivation_into_provenance(self):
        data = catalog_json(characteristic_mapping(verification="verified", references=["acme-manual-dist"]),
                            references=[VERIFIED_REF, UNVERIFIED_REF])
        catalog = parse(data)
        assert catalog.reference("acme-manual-dist").page == "37"           # an integer page is kept as text
        model = interpret(data, doc(("Head Z1", None)))
        prov = model.zone("Z1").characteristic.type.provenance
        assert prov.status is MappingStatus.MAPPED and prov.authority is MappingAuthority.DOCUMENTED_DERIVATION
        assert prov.references == (DocumentReference(
            "acme-manual-dist", "Acme X-Series distance protection manual", "verified", "AX-1000-EN",
            "4.2 Zone characteristic", "37", None),)
        # the references survive the stateless review context
        again = decode_model(encode_model(model))
        assert again.zone("Z1").characteristic.type.provenance.references == prov.references

    @pytest.mark.parametrize("kw", [{"authority": "assumption", "confidence": "inferred"},
                                    {"confidence": "inferred"}])
    def test_only_a_certain_documented_derivation_can_be_declared_verified(self, kw):
        m = characteristic_mapping(verification="verified", references=["acme-manual-dist"])
        m.update(kw)
        with pytest.raises(CatalogValidationError) as exc:
            parse(catalog_json(m, references=[VERIFIED_REF]))
        assert IssueCode.MALFORMED in codes(exc)

    def test_a_configured_setting_cannot_be_declared_a_verified_derivation(self):
        m = mapping("x", "distance.zone.x_reach", zone="*", source={"name": "X {zone}", "type": "number", "unit": "ohm"},
                    verification="verified", references=["acme-manual-dist"])
        with pytest.raises(CatalogValidationError) as exc:
            parse(catalog_json(m, references=[VERIFIED_REF]))
        assert IssueCode.MALFORMED in codes(exc)

    def test_an_undefined_reference_id_is_refused(self):
        with pytest.raises(CatalogValidationError) as exc:
            parse(catalog_json(characteristic_mapping(references=["nowhere"])))
        assert IssueCode.INVALID_REFERENCE in codes(exc)

    @pytest.mark.parametrize("bad,code", [
        ({**VERIFIED_REF, "text": "The quadrilateral characteristic is formed by ..."}, IssueCode.UNKNOWN_FIELD),
        ({**VERIFIED_REF, "title": "x" * 201}, IssueCode.MALFORMED),
        ({**VERIFIED_REF, "section": "s" * 161}, IssueCode.MALFORMED),
        ({**VERIFIED_REF, "verification": "probably"}, IssueCode.MALFORMED),
        ({**VERIFIED_REF, "id": "Not Kebab"}, IssueCode.MALFORMED),
        ({"id": "no-title", "verification": "verified"}, IssueCode.MISSING_METADATA),
    ])
    def test_a_reference_identifies_its_source_and_never_carries_its_text(self, bad, code):
        with pytest.raises(CatalogValidationError) as exc:
            parse(catalog_json(characteristic_mapping(), references=[bad]))
        assert code in codes(exc)

    def test_duplicate_reference_ids_are_refused(self):
        with pytest.raises(CatalogValidationError) as exc:
            parse(catalog_json(characteristic_mapping(), references=[VERIFIED_REF, dict(VERIFIED_REF)]))
        assert IssueCode.DUPLICATE in codes(exc)


# ---------------------------------------------------------------------------
# 2. Documented relay behaviour is presented as such
# ---------------------------------------------------------------------------


class TestDocumentedRelayBehaviour:
    def test_a_documented_derivation_is_not_presented_as_mapped(self):
        review = review_of(interpret(acme_catalog(), acme_document()))
        char = items(review)["zones[Z1].characteristic.type"]
        assert (char.status, char.category, char.authority) == ("mapped", "documented", "documented_derivation")
        assert review.documented_count == 2                                  # one characteristic per zone
        # Mapped means "a setting the document states": the derivations are not in it
        assert sum(1 for i in items(review).values() if i.category == "mapped" and i.review_status == "mapped") == review.mapped_count
        # and nothing about readiness changed: documented behaviour needs no confirmation
        assert review.readiness.status == Readiness.READY.value and review.readiness.pending_confirmations == 0

    def test_the_review_cites_the_reference_behind_a_documented_value(self):
        data = acme_catalog()
        data["references"] = [VERIFIED_REF]
        for m in data["mappings"]:
            if m["canonical"] == "distance.zone.characteristic":
                m.update(references=["acme-manual-dist"], verification="verified")
        review = review_of(interpret(data, acme_document()))
        refs = items(review)["zones[Z1].characteristic.type"].references
        assert [(r.reference_id, r.verification, r.document, r.section, r.page) for r in refs] == [
            ("acme-manual-dist", "verified", "AX-1000-EN", "4.2 Zone characteristic", "37")]
        out = ExtractionReviewOut(**asdict(review))
        item = next(i for g in out.groups for i in g.items if i.item_id == "zones[Z1].characteristic.type")
        assert item.category == "documented" and item.references[0].title.startswith("Acme X-Series")

    def test_an_inferred_documented_derivation_stays_an_assumption(self):
        # the confirmation gate is unchanged in this slice (e.g. RFPP / 2 is still confirmed by the user)
        data = catalog_json(mapping("d", "distance.zone.r_right", zone="*", source={"name": "R {zone}", "type": "number", "unit": "ohm"},
                                    transform={"type": "divide", "by": 2}, authority="documented_derivation", confidence="inferred"))
        model = interpret(data, doc(("R Z1", "7")))
        assert items(review_of(model, doc(("R Z1", "7"))))["zones[Z1].resistive_reach.phase_phase"].category == "assumption"


# ---------------------------------------------------------------------------
# 3. Not exposed is not Missing
# ---------------------------------------------------------------------------


def pp_not_exposed() -> dict:
    return mapping("pp.inherent", "distance.zone.pp_enabled", zone="*",
                   not_exposed={"note": "The relay always measures the phase-phase loops of every zone; there is no switch."})


def acme_without_pp(*extra: dict) -> dict:
    data = acme_catalog()
    data["mappings"] = [m for m in data["mappings"] if m["canonical"] != "distance.zone.pp_enabled"] + list(extra)
    return data


class TestNotExposed:
    def test_a_setting_the_relay_does_not_expose_is_not_missing_and_has_no_value(self):
        model = interpret(acme_without_pp(pp_not_exposed()), acme_document())
        pp = model.zone("Z1").phase_phase_enabled
        assert not pp.is_resolved and pp.provenance.cause is UnresolvedCause.NOT_EXPOSED
        assert "no switch" in " ".join(pp.provenance.notes)
        review = review_of(model)
        item = items(review)["zones[Z1].phase_phase_enabled"]
        assert item.category == "not_exposed" and item.resolution is None and item.suggestion is None
        assert review.not_exposed_count == 2
        missing = {i.item_id for i in items(review).values() if i.category == "missing"}
        assert not any("phase_phase_enabled" in m for m in missing)

    def test_it_never_supplies_a_value_so_the_engine_need_still_blocks(self):
        review = review_of(interpret(acme_without_pp(pp_not_exposed()), acme_document()))
        item = items(review)["zones[Z1].phase_phase_enabled"]
        assert item.blocking and review.readiness.status == Readiness.NOT_READY.value

    def test_a_documented_derivation_of_the_same_target_supplies_the_value(self):
        derived = mapping("pp.documented", "distance.zone.pp_enabled", zone="*", transform={"type": "constant", "value": True},
                          evidence=[{"name": "{zone} X Reach"}], authority="documented_derivation",
                          references=["acme-manual-dist"], verification="verified")
        data = acme_without_pp(pp_not_exposed(), derived)
        data["references"] = [VERIFIED_REF]
        model = interpret(data, acme_document())
        pp = model.zone("Z1").phase_phase_enabled
        assert pp.value is True and pp.provenance.authority is MappingAuthority.DOCUMENTED_DERIVATION
        review = review_of(model)
        assert items(review)["zones[Z1].phase_phase_enabled"].category == "documented"
        assert review.readiness.status == Readiness.READY.value

    def test_when_the_derivation_cannot_be_applied_the_setting_stays_not_exposed(self):
        derived = mapping("pp.documented", "distance.zone.pp_enabled", zone="*", transform={"type": "constant", "value": True},
                          evidence=[{"name": "{zone} Absent Heading"}], authority="documented_derivation")
        pp = interpret(acme_without_pp(pp_not_exposed(), derived), acme_document()).zone("Z1").phase_phase_enabled
        assert not pp.is_resolved and pp.provenance.cause is UnresolvedCause.NOT_EXPOSED

    @pytest.mark.parametrize("extra", [
        {"source": {"name": "PP {zone}"}},
        {"transform": {"type": "constant", "value": True}},
        {"authority": "documented_derivation"},
        {"gap": {"note": "x"}},
    ])
    def test_a_not_exposed_declaration_reads_and_asserts_nothing(self, extra):
        with pytest.raises(CatalogValidationError) as exc:
            parse(catalog_json({**pp_not_exposed(), **extra}))
        assert IssueCode.MALFORMED in codes(exc)

    def test_a_not_exposed_declaration_needs_a_note(self):
        with pytest.raises(CatalogValidationError) as exc:
            parse(catalog_json(mapping("pp", "distance.zone.pp_enabled", zone="*", not_exposed={})))
        assert IssueCode.MALFORMED in codes(exc)

    def test_a_relay_cannot_both_state_and_not_expose_a_setting(self):
        stated = mapping("pp.stated", "distance.zone.pp_enabled", zone="*", source={"name": "{zone} PP Loops"},
                         transform={"type": "boolean"})
        with pytest.raises(CatalogValidationError) as exc:
            parse(catalog_json(pp_not_exposed(), stated))
        assert IssueCode.CONFLICT in codes(exc)


# ---------------------------------------------------------------------------
# 4. Unverified (meaning not established) differs from Unsupported (engine limit)
# ---------------------------------------------------------------------------


def right_reach_gap(kind: str | None) -> dict:
    gap = {"note": "The relay states {evidence}.", "evidence": [{"name": "{zone} R Right"}]}
    if kind is not None:
        gap["kind"] = kind
    return mapping("r_right.gap", "distance.zone.r_right", zone="*", gap=gap)


def acme_with_right_reach_gap(kind: str | None) -> dict:
    data = acme_catalog()
    data["mappings"] = [m for m in data["mappings"] if m["canonical"] != "distance.zone.r_right"] + [right_reach_gap(kind)]
    return data


class TestUnverifiedVersusUnsupported:
    def test_an_unverified_gap_is_a_semantic_unknown(self):
        model = interpret(acme_with_right_reach_gap("unverified"), acme_document())
        rr = model.zone("Z1").resistive_reach.phase_phase
        assert not rr.is_resolved and rr.provenance.cause is UnresolvedCause.UNVERIFIED and rr.provenance.raw_value == "4"
        assert any("not yet verified for this relay" in n for n in model.interpretation_notes)
        review = review_of(model)
        item = items(review)["zones[Z1].resistive_reach.phase_phase"]
        assert item.category == "unverified" and item.blocking and item.resolution is None and item.suggestion is None
        assert (review.unverified_count, review.unsupported_count) == (2, 0)
        assert review.readiness.status == Readiness.NOT_READY.value

    @pytest.mark.parametrize("kind", [None, "unsupported"])
    def test_an_unsupported_gap_is_an_engine_limit_as_before(self, kind):
        model = interpret(acme_with_right_reach_gap(kind), acme_document())
        assert model.zone("Z1").resistive_reach.phase_phase.provenance.cause is UnresolvedCause.UNSUPPORTED
        review = review_of(model)
        assert items(review)["zones[Z1].resistive_reach.phase_phase"].category == "unsupported"
        assert (review.unverified_count, review.unsupported_count) == (0, 2)

    def test_a_gap_kind_must_be_known(self):
        with pytest.raises(CatalogValidationError) as exc:
            parse(catalog_json(right_reach_gap("maybe")))
        assert IssueCode.MALFORMED in codes(exc)

    def test_an_unverified_value_survives_the_review_context(self):
        model = interpret(acme_with_right_reach_gap("unverified"), acme_document())
        again = decode_model(encode_model(model))
        assert again.zone("Z1").resistive_reach.phase_phase.provenance.cause is UnresolvedCause.UNVERIFIED


# ---------------------------------------------------------------------------
# 5. The approximation data model
# ---------------------------------------------------------------------------


def bounded_envelope() -> ErrorEnvelope:
    return ErrorEnvelope("up to 0.5 × X at the upper-left corner", max_relative_deviation=0.5)


def record(classification=ApproximationClass.CONSERVATIVE, envelope=None, field="zones[Z1].resistive_reach.reverse"):
    return ApproximationRecord("test-left-boundary-at-zero", "1.0.0", field, classification,
                               "The left boundary is drawn at R = 0.", envelope, "Z1")


class TestApproximationModel:
    def test_classifications(self):
        assert [c.value for c in ApproximationClass] == ["conservative", "bounded", "unbounded"]
        assert ApproximationClass.CONSERVATIVE.permits_automatic_apply and ApproximationClass.BOUNDED.permits_automatic_apply
        assert not ApproximationClass.UNBOUNDED.permits_automatic_apply

    def test_an_unbounded_approximation_is_never_recorded_as_applied(self):
        with pytest.raises(ValueError):
            record(ApproximationClass.UNBOUNDED)

    def test_a_bounded_approximation_needs_its_error_envelope(self):
        with pytest.raises(ValueError):
            record(ApproximationClass.BOUNDED)
        assert record(ApproximationClass.BOUNDED, bounded_envelope()).envelope.max_relative_deviation == 0.5

    @pytest.mark.parametrize("kw", [{"max_deviation_ohm": -1.0}, {"max_relative_deviation": math.nan},
                                    {"max_deviation_ohm": math.inf}])
    def test_an_error_envelope_is_finite_and_non_negative(self, kw):
        with pytest.raises(ValueError):
            ErrorEnvelope("bound", **kw)
        with pytest.raises(ValueError):
            ErrorEnvelope("   ")

    def test_rule_validation(self):
        good = ApproximationRule("test-rule", "1.0.0", "distance.zone.r_left", ApproximationClass.CONSERVATIVE, "Drawn at R = 0.")
        assert rule_problems(good) == []
        assert rule_problems(replace(good, classification=ApproximationClass.BOUNDED)) == [
            "a bounded approximation needs a verified error envelope"]
        assert len(rule_problems(replace(good, rule_id="Bad Id", rule_version="1", field=" ", description=""))) == 4

    def test_no_rule_is_approved_yet(self):
        assert APPROVED_RULES == ()
        assert approved_rule("test-rule", "1.0.0") is None

    def test_only_an_approved_conservative_or_bounded_rule_can_be_applied(self):
        rules = (
            ApproximationRule("a", "1.0.0", "distance.zone.r_left", ApproximationClass.CONSERVATIVE, "Drawn at R = 0."),
            ApproximationRule("b", "1.0.0", "distance.zone.r_left", ApproximationClass.UNBOUNDED, "Unknown effect."),
            ApproximationRule("c", "1.0.0", "distance.zone.r_left", ApproximationClass.BOUNDED, "No envelope."),
        )
        assert approved_rule("a", "1.0.0", rules) is rules[0]
        assert approved_rule("a", "2.0.0", rules) is None
        assert approved_rule("b", "1.0.0", rules) is None and approved_rule("c", "1.0.0", rules) is None

    def test_provenance_carries_a_record_exactly_for_an_engine_approximation(self):
        ok = Provenance(MappingStatus.MAPPED, origin=ProvenanceOrigin.ENGINE_APPROXIMATION, approximation=record())
        assert ok.approximation.rule_id == "test-left-boundary-at-zero"
        with pytest.raises(ValueError):
            Provenance(MappingStatus.MAPPED, origin=ProvenanceOrigin.ENGINE_APPROXIMATION)
        with pytest.raises(ValueError):
            Provenance(MappingStatus.MAPPED, origin=ProvenanceOrigin.SESSION_REVIEW, approximation=record())
        with pytest.raises(ValueError):
            Provenance(MappingStatus.INFERRED, origin=ProvenanceOrigin.ENGINE_APPROXIMATION, approximation=record())

    def test_an_approximation_rule_names_no_relay(self):
        """Rules are relay-neutral: an OEM catalog may opt into one, the rule never names an OEM."""
        source = Path(approximation_module.__file__).read_text(encoding="utf-8")
        names = {c.applicability.model for c in default_store().catalogs} | {
            c.applicability.manufacturer for c in default_store().catalogs if c.applicability.manufacturer}
        names |= {"Siemens", "Toshiba", "Schneider", "MiCOM", "Hitachi", "ABB", "SIPROTEC", "Relion", "NR Electric"}
        assert not [n for n in names if re.search(rf"(?<![A-Za-z0-9]){re.escape(n)}(?![A-Za-z0-9])", source)]

    def test_a_review_context_can_never_carry_an_approximation(self):
        """Approximations are derived by the backend after decoding, never trusted from the browser."""
        with pytest.raises(SnapshotError):
            decode_model(encode_model(approximated_model()))


# ---------------------------------------------------------------------------
# 6. Readiness: READY_APPROXIMATE
# ---------------------------------------------------------------------------


def approximated_model(rec: ApproximationRecord | None = None):
    """The ready Acme model whose Zone 1 left boundary is replaced by an engine approximation (test-only rule)."""
    model = interpret(acme_catalog(), acme_document())
    z1 = model.zone("Z1")
    value = Sourced(0.0, Provenance(MappingStatus.MAPPED, origin=ProvenanceOrigin.ENGINE_APPROXIMATION,
                                    approximation=rec or record()))
    zone = replace(z1, resistive_reach=replace(z1.resistive_reach, reverse=value))
    return replace(model, zones=tuple(zone if z.zone_id == "Z1" else z for z in model.zones))


class TestReadinessApproximate:
    def test_compute_readiness(self):
        assert compute_readiness(engine_supported=True, pending_confirmations=0, blocking_unresolved=0) is Readiness.READY
        assert compute_readiness(engine_supported=True, pending_confirmations=0, blocking_unresolved=0,
                                 approximations=1) is Readiness.READY_APPROXIMATE
        assert compute_readiness(engine_supported=True, pending_confirmations=2, blocking_unresolved=0,
                                 approximations=1) is Readiness.READY_AFTER_CONFIRMATION
        assert compute_readiness(engine_supported=True, pending_confirmations=0, blocking_unresolved=1,
                                 approximations=1) is Readiness.NOT_READY
        assert compute_readiness(engine_supported=False, pending_confirmations=0, blocking_unresolved=0,
                                 approximations=1) is Readiness.NOT_READY
        assert APPLICABLE_READINESS == {Readiness.READY, Readiness.READY_APPROXIMATE}

    def test_an_accepted_model_with_an_approximation_is_ready_approximate(self):
        review = review_of(approximated_model(record(ApproximationClass.BOUNDED, bounded_envelope())))
        assert review.readiness.status == "ready_approximate" and review.approximate_count == 1
        item = items(review)["zones[Z1].resistive_reach.reverse"]
        assert item.category == "approximate" and item.value_text == "0 Ω"
        assert (item.approximation.rule_id, item.approximation.classification, item.approximation.envelope) == (
            "test-left-boundary-at-zero", "bounded", "up to 0.5 × X at the upper-left corner")

    def test_ready_approximate_serializes(self):
        assert ReviewReadinessOut(status="ready_approximate", pending_confirmations=0, blocking_unresolved=0).status == "ready_approximate"
        out = ExtractionReviewOut(**asdict(review_of(approximated_model())))
        assert out.readiness.status == "ready_approximate" and out.approximate_count == 1
        item = next(i for g in out.groups for i in g.items if i.item_id == "zones[Z1].resistive_reach.reverse")
        assert item.category == "approximate" and item.approximation.classification == "conservative"

    def test_the_state_exists_but_no_current_relay_reaches_it(self):
        review = review_of(interpret(acme_catalog(), acme_document()))
        assert review.readiness.status == "ready" and review.approximate_count == 0


# ---------------------------------------------------------------------------
# 7. Apply carries approximations[]
# ---------------------------------------------------------------------------


class TestApplyApproximations:
    def test_an_exact_model_applies_with_an_empty_list(self):
        model = interpret(acme_catalog(), acme_document())
        plan = build_apply_plan(model, engine_adaptation(model), impedance_basis="primary")
        assert plan.approximations == () and model_approximations(model) == ()
        assert ApplySettingsOut(characteristic=plan.characteristic, impedance_basis=plan.impedance_basis,
                                zones=[_zone_out(z) for z in plan.zones]).approximations == []

    def test_an_approximated_model_carries_each_record(self):
        model = approximated_model(record(ApproximationClass.BOUNDED, bounded_envelope()))
        plan = build_apply_plan(model, engine_adaptation(model), impedance_basis="primary")
        assert [(a.rule_id, a.field, a.classification, a.envelope, a.zone_id) for a in plan.approximations] == [(
            "test-left-boundary-at-zero", "zones[Z1].resistive_reach.reverse", "bounded",
            "up to 0.5 × X at the upper-left corner", "Z1")]
        out = ApplySettingsOut(characteristic=plan.characteristic, impedance_basis=plan.impedance_basis,
                               zones=[_zone_out(z) for z in plan.zones], approximations=[asdict(a) for a in plan.approximations])
        assert out.approximations[0].classification == "bounded"
        # the approximated boundary is what the engine receives -- the relay setting itself is not invented
        z1 = next(z for z in plan.zones if z.zone_id == "Z1")
        assert z1.resistive_reach_reverse_ohm == 0.0

    def test_an_unbounded_approximation_is_not_a_valid_payload(self):
        with pytest.raises(ValidationError):
            ApproximationOut(rule_id="r", rule_version="1.0.0", field="f", classification="unbounded", description="d")


def _zone_out(zone) -> dict:
    fields = asdict(zone)
    fields["id"] = fields.pop("zone_id")
    return fields


# ---------------------------------------------------------------------------
# 8. The shipped catalogs are unchanged
# ---------------------------------------------------------------------------


class TestShippedCatalogsUnchanged:
    def test_the_lock_is_consistent(self):
        store = default_store()
        assert not store.rejected and check_lock(store, load_lock()) == []

    def test_no_other_shipped_catalog_uses_the_new_declarations(self):
        # REL511 (1.1.0 / 1.2.0) and 7SL87 (1.1.0) are the only catalogs to use them (their own tests:
        # test_relay_rel511_documented_behaviour.py, test_relay_7sl87_documented_behaviour.py)
        for catalog in default_store().catalogs:
            if catalog.catalog_id in ("hitachi-rel511-catalog", "siemens-siprotec5-7sl87-catalog"):
                continue
            assert catalog.references == ()
            assert all(m.not_exposed is None and m.verification is None and not m.references for m in catalog.mappings)
            assert all(m.gap is None or m.gap.kind == "unsupported" for m in catalog.mappings)

    def test_references_count_in_the_digest_only_when_used(self):
        data = catalog_json(characteristic_mapping())
        before = semantics_digest(data)
        assert semantics_digest({**data}) == before
        assert semantics_digest({**data, "references": [VERIFIED_REF]}) != before

    def test_a_catalog_validates_against_the_shipped_registry(self):
        # the new keys are accepted by the same validator the service runs at start-up
        data = catalog_json(characteristic_mapping(verification="verified", references=["acme-manual-dist"]),
                            pp_not_exposed(), right_reach_gap("unverified"), references=[VERIFIED_REF])
        catalog = parse_catalog(data, canonical_registry(), source="test")
        assert {m.id for m in catalog.mappings} == {"char.*", "pp.inherent", "r_right.gap"}


# ---------------------------------------------------------------------------
# 9. REL511 knowledge-integration mechanisms, generic (DEC-198)
# ---------------------------------------------------------------------------


def acme_without(*canonicals: str, extra: tuple[dict, ...] = (), preserved: list | None = None) -> dict:
    data = acme_catalog()
    data["mappings"] = [m for m in data["mappings"] if m["canonical"] not in canonicals] + list(extra)
    if preserved is not None:
        data["zone_preserved"] = preserved
    return data


def reasons(model) -> set[tuple[str, str | None]]:
    return {(r.code.value, r.zone_id) for r in engine_adaptation(model).reasons}


class TestCompleteBlockerPicture:
    def test_a_missing_x_limit_no_longer_hides_the_missing_resistive_limits(self):
        rows = [tuple(r) if len(r) == 3 else (r[0], r[1]) for r in ACME_ROWS[2:]]
        document = doc(*[r for r in rows if r[0] not in ("Z1 X Reach", "Z1 R Right", "Z1 R Left")])
        messages = {r.message for r in engine_adaptation(interpret(acme_catalog(), document)).reasons if r.zone_id == "Z1"}
        assert {"The Reactive Reach (X) is unresolved.", "The Right Resistive Reach (+R) is unresolved.",
                "The Left Resistive Reach (−R) is unresolved."} <= messages

    def test_an_unnamed_characteristic_of_explicit_rx_limits_still_reports_their_gaps(self):
        model = interpret(acme_without("distance.zone.characteristic", "distance.zone.r_left"), acme_document())
        assert {("characteristic_unresolved", "Z1"), ("resistive_reach_unresolved", "Z1")} <= reasons(model)
        review = review_of(model)
        assert items(review)["zones[Z1].resistive_reach.reverse"].blocking              # the row exists to point at

    def test_an_unverified_fault_resistance_is_worded_as_such(self):
        model = interpret(acme_with_right_reach_gap("unverified"), acme_document())
        msgs = {r.message for r in engine_adaptation(model).reasons}
        assert ("A source fault-resistance setting is available, but its conversion to the plotted resistive "
                "boundary has not yet been verified.") in msgs
        assert not any("Only a phase-earth" in m for m in msgs)

    def documented_unsupported_right_reach(self, *, references: list[str] | None) -> dict:
        gap = right_reach_gap(None)                                                   # unsupported (default kind)
        if references is not None:
            gap["references"] = references
        earth = mapping("pe", "distance.zone.r_phase_earth", zone="*", source={"name": "{zone} R Left", "type": "number", "unit": "ohm"})
        data = acme_without("distance.zone.r_right", extra=(gap, earth))
        data["references"] = [VERIFIED_REF, UNVERIFIED_REF]
        return data

    def test_a_documented_boundary_the_engine_cannot_draw_is_worded_as_an_engine_limitation(self):
        # DEC-198 Amendment 2: a fault-resistance setting whose boundary a verified reference documents, but which
        # the engine cannot represent, is neither "not yet verified" nor "only a phase-earth reach is available".
        model = interpret(self.documented_unsupported_right_reach(references=["acme-manual-dist"]), acme_document())
        msgs = {r.message for r in engine_adaptation(model).reasons if r.zone_id == "Z1"}
        assert ("A source fault-resistance setting is available and its resistive boundary is documented, but the "
                "current engine cannot represent that boundary exactly.") in msgs
        assert not any("Only a phase-earth" in m or "not yet been verified" in m for m in msgs)
        assert ("resistive_reach_unresolved", "Z1") in reasons(model) and ("loop_type_unsupported", "Z1") not in reasons(model)

    @pytest.mark.parametrize("refs", [None, ["acme-app-note"]])
    def test_without_a_verified_reference_the_previous_wording_stays(self, refs):
        model = interpret(self.documented_unsupported_right_reach(references=refs), acme_document())
        msgs = {r.message for r in engine_adaptation(model).reasons if r.zone_id == "Z1"}
        assert "Only a phase-earth resistive reach is available; the engine evaluates phase-phase loops only." in msgs
        assert not any("resistive boundary is documented" in m for m in msgs)

    def test_an_unverified_basis_is_worded_as_such(self):
        gap = mapping("basis.gap", "ct_vt.impedance_basis", gap={"kind": "unverified", "note": "Not verified for this format."})
        model = interpret(acme_without("ct_vt.impedance_basis", extra=(gap,)), acme_document())
        assert any("has not yet been verified for this relay" in r.message for r in engine_adaptation(model).reasons)


class TestGatedDocumentedConstant:
    def gated(self) -> dict:
        derived = mapping("pp.doc", "distance.zone.pp_enabled", zone="*", transform={"type": "constant", "value": True},
                          evidence=[{"name": "{zone} X Reach"}], authority="documented_derivation",
                          requires=[{"source": {"name": "{zone} Enable", "allowed_text": ["yes", "no"]}, "equals": ["yes"]}])
        return acme_without_pp(pp_not_exposed(), derived)

    def test_the_constant_applies_only_while_its_gate_holds_and_cites_the_gate(self):
        model = interpret(self.gated(), acme_document())
        pp = model.zone("Z1").phase_phase_enabled
        assert pp.value is True and {s.parameter_name for s in pp.provenance.sources} == {"Z1 X Reach", "Z1 Enable"}

    def test_a_closed_gate_leaves_the_not_exposed_declaration(self):
        document = doc(*[(r[0], "No", *r[2:]) if r[0] == "Z2 Enable" else r for r in
                         (tuple(x) if len(x) == 3 else (x[0], x[1]) for x in ACME_ROWS[2:])])
        pp = interpret(self.gated(), document).zone("Z2").phase_phase_enabled
        assert not pp.is_resolved and pp.provenance.cause is UnresolvedCause.NOT_EXPOSED


class TestMaterialPreservedSetting:
    def preserved(self, values=("on",)) -> list:
        return [{"zone": ["Z1", "Z2"], "names": ["{zone} Lock"], "reason": "Effect not verified.", "unverified_when": list(values)}]

    def test_a_material_value_blocks_an_enabled_zone_as_unverified(self):
        document = doc(*[tuple(r) if len(r) == 3 else (r[0], r[1]) for r in ACME_ROWS[2:]], ("Z1 Lock", "On"), ("Z2 Lock", "Off"))
        model = interpret(acme_without(preserved=self.preserved()), document)
        lock1 = next(u for u in model.zone("Z1").unresolved_settings if u.name == "Z1 Lock")
        lock2 = next(u for u in model.zone("Z2").unresolved_settings if u.name == "Z2 Lock")
        assert (lock1.material, lock1.raw_value, lock2.material) == (True, "On", False)
        assert ("unverified_setting", "Z1") in reasons(model) and ("unverified_setting", "Z2") not in reasons(model)
        review = review_of(model, document)
        rows = {i.label: i for g in review.groups for i in g.items if i.item_id is None}
        assert (rows["Z1 Lock"].category, rows["Z1 Lock"].blocking) == ("unverified", True)
        assert (rows["Z2 Lock"].category, rows["Z2 Lock"].blocking) == ("unsupported", False)
        assert review.readiness.status == Readiness.NOT_READY.value
        issue = next(b for b in review.blocking_issues if b.kind == "unverified")
        assert issue.zone_ids == ("Z1",) and issue.item_ids == ()

    def test_unverified_when_must_list_raw_values(self):
        with pytest.raises(CatalogValidationError) as exc:
            parse(catalog_json(zone_preserved=[{"zone": "*", "names": ["{zone} Lock"], "reason": "x", "unverified_when": "on"}]))
        assert IssueCode.MALFORMED in codes(exc)
