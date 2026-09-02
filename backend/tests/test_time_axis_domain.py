"""Domain-level tests for the Time-Axis interpretation FRAMEWORK
(Slice 7, DEC-072). Pure data-structure/pure-function tests only -- no
registry, no CSV/Excel I/O, no HTTP. Production detection/parsing logic
does not exist yet (Slice 8's own scope), so every test here exercises
the FRAMEWORK'S OWN shapes and `resolve_status()`/
`build_interpretation_result()` directly, not any real interpretation.
"""

from __future__ import annotations

from app.domain.time_axis import (
    AMBIGUITY_AMBIGUOUS,
    AMBIGUITY_INVALID,
    AMBIGUITY_UNAMBIGUOUS,
    CONFIDENCE_HIGH,
    CONFIDENCE_UNKNOWN,
    FAMILY_ABSOLUTE,
    FAMILY_ELAPSED,
    FAMILY_PARTIAL,
    FAMILY_SAMPLE_INDEX,
    FAMILY_UNKNOWN,
    INTERPRETER_ID_ABSOLUTE_DATETIME,
    INTERPRETER_ID_MANUAL,
    INTERPRETER_ID_REPEATED_TIMESTAMP,
    INTERPRETER_ID_UNSUPPORTED,
    KNOWN_AMBIGUITY_LEVELS,
    KNOWN_CONFIDENCE_LEVELS,
    KNOWN_DATE_ORDERS,
    KNOWN_PROVENANCES,
    KNOWN_TIME_AXIS_STATUSES,
    KNOWN_TIME_FAMILIES,
    PROVENANCE_INDEX_ONLY,
    PROVENANCE_NATIVE,
    PROVENANCE_RECONSTRUCTED,
    PROVENANCE_USER_SPECIFIED,
    STATUS_CONFIRMED,
    STATUS_DETECTED,
    STATUS_INDEX_FALLBACK,
    STATUS_NEEDS_ATTENTION,
    STATUS_REVIEW_REQUIRED,
    STATUS_UNCONFIGURED,
    STATUS_UNSUPPORTED,
    TimeAxisConfiguration,
    TimeAxisDiagnostic,
    build_interpretation_result,
    resolve_status,
)


class TestSemanticFamilies:
    def test_five_known_families(self):
        assert KNOWN_TIME_FAMILIES == (
            FAMILY_ABSOLUTE, FAMILY_ELAPSED, FAMILY_SAMPLE_INDEX, FAMILY_PARTIAL, FAMILY_UNKNOWN,
        )

    def test_families_are_stable_strings(self):
        assert all(isinstance(f, str) and f for f in KNOWN_TIME_FAMILIES)


class TestProvenance:
    def test_four_known_provenances_not_five(self):
        # "inferred" was deliberately not added as a fifth state -- see
        # this module's own module docstring for why.
        assert KNOWN_PROVENANCES == (
            PROVENANCE_NATIVE, PROVENANCE_RECONSTRUCTED, PROVENANCE_USER_SPECIFIED, PROVENANCE_INDEX_ONLY,
        )
        assert "inferred" not in KNOWN_PROVENANCES


class TestConfidence:
    def test_four_known_confidence_levels(self):
        assert KNOWN_CONFIDENCE_LEVELS == ("high", "medium", "low", CONFIDENCE_UNKNOWN)


class TestStatusModel:
    def test_seven_known_statuses(self):
        assert len(KNOWN_TIME_AXIS_STATUSES) == 7
        assert STATUS_UNCONFIGURED in KNOWN_TIME_AXIS_STATUSES
        assert STATUS_UNSUPPORTED in KNOWN_TIME_AXIS_STATUSES


class TestTimeAxisConfigurationConstruction:
    def test_one_time_axis_column(self):
        config = TimeAxisConfiguration(
            column_indices=(0,), family=FAMILY_ABSOLUTE, provenance=PROVENANCE_NATIVE,
            interpreter_id=INTERPRETER_ID_MANUAL,
        )

        assert config.column_indices == (0,)
        assert config.family == FAMILY_ABSOLUTE

    def test_multiple_time_axis_columns(self):
        config = TimeAxisConfiguration(
            column_indices=(0, 1), family=FAMILY_ABSOLUTE, provenance=PROVENANCE_USER_SPECIFIED,
            interpreter_id=INTERPRETER_ID_MANUAL,
        )

        assert config.column_indices == (0, 1)

    def test_sample_index_with_null_rate_is_valid(self):
        config = TimeAxisConfiguration(
            column_indices=(0,), family=FAMILY_SAMPLE_INDEX, provenance=PROVENANCE_INDEX_ONLY,
            interpreter_id=INTERPRETER_ID_MANUAL, interval_seconds=None,
        )

        assert config.interval_seconds is None
        assert config.family == FAMILY_SAMPLE_INDEX

    def test_partial_family_representable_without_a_date(self):
        config = TimeAxisConfiguration(
            column_indices=(0,), family=FAMILY_PARTIAL, provenance=PROVENANCE_NATIVE,
            interpreter_id=INTERPRETER_ID_MANUAL,
        )

        assert config.family == FAMILY_PARTIAL

    def test_unsupported_sentinel_has_null_family_and_provenance(self):
        config = TimeAxisConfiguration(
            column_indices=(0, 1, 2), family=None, provenance=None, interpreter_id=INTERPRETER_ID_UNSUPPORTED,
        )

        assert config.family is None
        assert config.provenance is None

    def test_elapsed_family_carries_a_unit(self):
        config = TimeAxisConfiguration(
            column_indices=(0,), family=FAMILY_ELAPSED, provenance=PROVENANCE_USER_SPECIFIED,
            interpreter_id=INTERPRETER_ID_MANUAL, unit="milliseconds",
        )

        assert config.unit == "milliseconds"

    def test_interval_seconds_is_the_canonical_internal_value(self):
        config = TimeAxisConfiguration(
            column_indices=(0,), family=FAMILY_SAMPLE_INDEX, provenance=PROVENANCE_USER_SPECIFIED,
            interpreter_id=INTERPRETER_ID_MANUAL, interval_seconds=0.05,
        )

        assert config.interval_seconds == 0.05

    def test_confirmed_defaults_false(self):
        config = TimeAxisConfiguration(
            column_indices=(0,), family=FAMILY_ABSOLUTE, provenance=PROVENANCE_NATIVE,
            interpreter_id=INTERPRETER_ID_MANUAL,
        )

        assert config.confirmed is False

    def test_options_bag_is_generic_and_empty_by_default(self):
        config = TimeAxisConfiguration(
            column_indices=(0,), family=FAMILY_ABSOLUTE, provenance=PROVENANCE_NATIVE,
            interpreter_id=INTERPRETER_ID_MANUAL,
        )

        assert config.options == {}


class TestTimeAxisDiagnostic:
    def test_minimal_diagnostic_has_no_location_or_action(self):
        diagnostic = TimeAxisDiagnostic(severity_hint="info", code="x", message="msg")

        assert diagnostic.location is None
        assert diagnostic.suggested_action is None

    def test_diagnostic_reuses_issue_location_shape(self):
        from app.domain.preparation_issue import IssueLocation

        diagnostic = TimeAxisDiagnostic(
            severity_hint="warning", code="repeated_timestamps", message="msg",
            location=IssueLocation(worksheet_index=0, column_index=1),
        )

        assert diagnostic.location.worksheet_index == 0
        assert diagnostic.location.column_index == 1


class TestResolveStatus:
    def test_no_configuration_is_unconfigured(self):
        status = resolve_status(None, columns_still_time_axis=True, diagnostics=[])

        assert status == STATUS_UNCONFIGURED

    def test_unsupported_interpreter_id_is_unsupported(self):
        config = TimeAxisConfiguration(
            column_indices=(0, 1), family=None, provenance=None, interpreter_id=INTERPRETER_ID_UNSUPPORTED,
        )

        status = resolve_status(config, columns_still_time_axis=True, diagnostics=[])

        assert status == STATUS_UNSUPPORTED

    def test_stale_columns_are_unsupported_even_with_a_real_interpreter(self):
        # The column role was changed away from Time Axis after this
        # configuration was created -- the config itself is untouched,
        # but the COMPUTED status must never present it as valid.
        config = TimeAxisConfiguration(
            column_indices=(0,), family=FAMILY_ABSOLUTE, provenance=PROVENANCE_NATIVE,
            interpreter_id=INTERPRETER_ID_MANUAL, confirmed=True,
        )

        status = resolve_status(config, columns_still_time_axis=False, diagnostics=[])

        assert status == STATUS_UNSUPPORTED

    def test_sample_index_with_index_only_provenance_is_index_fallback(self):
        config = TimeAxisConfiguration(
            column_indices=(0,), family=FAMILY_SAMPLE_INDEX, provenance=PROVENANCE_INDEX_ONLY,
            interpreter_id=INTERPRETER_ID_MANUAL,
        )

        status = resolve_status(config, columns_still_time_axis=True, diagnostics=[])

        assert status == STATUS_INDEX_FALLBACK

    def test_diagnostics_present_and_unconfirmed_is_needs_attention(self):
        config = TimeAxisConfiguration(
            column_indices=(0,), family=FAMILY_ABSOLUTE, provenance=PROVENANCE_NATIVE,
            interpreter_id=INTERPRETER_ID_MANUAL, confirmed=False,
        )
        diagnostic = TimeAxisDiagnostic(severity_hint="warning", code="mixed_formats", message="msg")

        status = resolve_status(config, columns_still_time_axis=True, diagnostics=[diagnostic])

        assert status == STATUS_NEEDS_ATTENTION

    def test_confirmed_with_no_diagnostics_is_confirmed(self):
        config = TimeAxisConfiguration(
            column_indices=(0,), family=FAMILY_ABSOLUTE, provenance=PROVENANCE_NATIVE,
            interpreter_id=INTERPRETER_ID_MANUAL, confirmed=True,
        )

        status = resolve_status(config, columns_still_time_axis=True, diagnostics=[])

        assert status == STATUS_CONFIRMED

    def test_unconfirmed_with_no_diagnostics_is_detected(self):
        config = TimeAxisConfiguration(
            column_indices=(0,), family=FAMILY_ABSOLUTE, provenance=PROVENANCE_NATIVE,
            interpreter_id=INTERPRETER_ID_MANUAL, confirmed=False,
        )

        status = resolve_status(config, columns_still_time_axis=True, diagnostics=[])

        assert status == STATUS_DETECTED

    def test_ambiguous_diagnostic_and_unconfirmed_is_review_required(self):
        # Slice 8A: the first production path that actually reaches
        # STATUS_REVIEW_REQUIRED -- an `ambiguous_date_order`-class
        # diagnostic, distinct from a plain data-quality finding.
        config = TimeAxisConfiguration(
            column_indices=(0,), family=FAMILY_ABSOLUTE, provenance=PROVENANCE_USER_SPECIFIED,
            interpreter_id=INTERPRETER_ID_ABSOLUTE_DATETIME, confirmed=False,
        )
        diagnostic = TimeAxisDiagnostic(
            severity_hint="warning", code="ambiguous_date_order", message="msg", ambiguity=AMBIGUITY_AMBIGUOUS,
        )

        status = resolve_status(config, columns_still_time_axis=True, diagnostics=[diagnostic])

        assert status == STATUS_REVIEW_REQUIRED

    def test_ambiguous_diagnostic_with_confirmed_true_falls_through_to_needs_attention(self):
        # Confirming while genuinely ambiguous is rejected by the
        # SERVICE layer (see test_time_axis_service.py), so this
        # combination should not arise from real stored state -- but
        # this pure function still has a defined, non-crashing answer
        # for it: `review_required` specifically requires `not
        # confirmed` (a resolved/accepted ambiguity is no longer "needs
        # a choice"), so a confirmed config with a lingering ambiguous
        # diagnostic falls through to the SAME generic "diagnostics
        # present -> needs_attention" rule every other diagnostic
        # already uses, exactly like `test_diagnostics_present_and_
        # unconfirmed_is_needs_attention` above -- `confirmed` alone
        # never suppresses a non-empty diagnostics list.
        config = TimeAxisConfiguration(
            column_indices=(0,), family=FAMILY_ABSOLUTE, provenance=PROVENANCE_USER_SPECIFIED,
            interpreter_id=INTERPRETER_ID_ABSOLUTE_DATETIME, confirmed=True,
        )
        diagnostic = TimeAxisDiagnostic(
            severity_hint="warning", code="ambiguous_date_order", message="msg", ambiguity=AMBIGUITY_AMBIGUOUS,
        )

        status = resolve_status(config, columns_still_time_axis=True, diagnostics=[diagnostic])

        assert status == STATUS_NEEDS_ATTENTION

    def test_non_ambiguous_diagnostic_still_falls_through_to_needs_attention(self):
        # An `invalid`/plain diagnostic must NOT trigger review_required
        # -- only AMBIGUITY_AMBIGUOUS does.
        config = TimeAxisConfiguration(
            column_indices=(0,), family=FAMILY_ABSOLUTE, provenance=PROVENANCE_NATIVE,
            interpreter_id=INTERPRETER_ID_ABSOLUTE_DATETIME, confirmed=False,
        )
        diagnostic = TimeAxisDiagnostic(
            severity_hint="warning", code="unparseable_datetime", message="msg", ambiguity=AMBIGUITY_INVALID,
        )

        status = resolve_status(config, columns_still_time_axis=True, diagnostics=[diagnostic])

        assert status == STATUS_NEEDS_ATTENTION


class TestBuildInterpretationResult:
    def test_unconfigured_result_shape(self):
        result = build_interpretation_result(None, columns_still_time_axis=True)

        assert result.status == STATUS_UNCONFIGURED
        assert result.family is None
        assert result.provenance is None
        assert result.interpreter_id is None
        assert result.column_indices == ()
        assert result.confidence == CONFIDENCE_UNKNOWN
        assert result.diagnostics == []
        assert result.preview_supported is False
        assert result.confirmation_required is False

    def test_configured_unconfirmed_requires_confirmation(self):
        config = TimeAxisConfiguration(
            column_indices=(0,), family=FAMILY_ABSOLUTE, provenance=PROVENANCE_NATIVE,
            interpreter_id=INTERPRETER_ID_MANUAL, confirmed=False,
        )

        result = build_interpretation_result(config, columns_still_time_axis=True)

        assert result.confirmation_required is True
        assert result.status == STATUS_DETECTED

    def test_confirmed_does_not_require_confirmation(self):
        config = TimeAxisConfiguration(
            column_indices=(0,), family=FAMILY_ABSOLUTE, provenance=PROVENANCE_NATIVE,
            interpreter_id=INTERPRETER_ID_MANUAL, confirmed=True,
        )

        result = build_interpretation_result(config, columns_still_time_axis=True)

        assert result.confirmation_required is False
        assert result.status == STATUS_CONFIRMED

    def test_multi_column_configuration_echoed_in_result(self):
        config = TimeAxisConfiguration(
            column_indices=(0, 1), family=FAMILY_ABSOLUTE, provenance=PROVENANCE_USER_SPECIFIED,
            interpreter_id=INTERPRETER_ID_MANUAL,
        )

        result = build_interpretation_result(config, columns_still_time_axis=True)

        assert result.column_indices == (0, 1)

    def test_confidence_always_unknown_in_slice_7(self):
        config = TimeAxisConfiguration(
            column_indices=(0,), family=FAMILY_ABSOLUTE, provenance=PROVENANCE_NATIVE,
            interpreter_id=INTERPRETER_ID_MANUAL,
        )

        result = build_interpretation_result(config, columns_still_time_axis=True)

        assert result.confidence == CONFIDENCE_UNKNOWN

    def test_preview_never_claimed_supported_in_slice_7(self):
        config = TimeAxisConfiguration(
            column_indices=(0,), family=FAMILY_ABSOLUTE, provenance=PROVENANCE_NATIVE,
            interpreter_id=INTERPRETER_ID_MANUAL,
        )

        result = build_interpretation_result(config, columns_still_time_axis=True)

        assert result.preview_supported is False

    def test_unit_interval_confirmed_are_echoed_verbatim(self):
        config = TimeAxisConfiguration(
            column_indices=(0,), family=FAMILY_SAMPLE_INDEX, provenance=PROVENANCE_USER_SPECIFIED,
            interpreter_id=INTERPRETER_ID_MANUAL, unit="milliseconds", interval_seconds=0.02, confirmed=True,
        )

        result = build_interpretation_result(config, columns_still_time_axis=True)

        assert result.unit == "milliseconds"
        assert result.interval_seconds == 0.02
        assert result.confirmed is True

    def test_unit_interval_confirmed_default_when_unconfigured(self):
        result = build_interpretation_result(None, columns_still_time_axis=True)

        assert result.unit is None
        assert result.interval_seconds is None
        assert result.confirmed is False

    def test_options_echoed_verbatim(self):
        config = TimeAxisConfiguration(
            column_indices=(0,), family=FAMILY_ABSOLUTE, provenance=PROVENANCE_NATIVE,
            interpreter_id=INTERPRETER_ID_ABSOLUTE_DATETIME, options={"date_order": "dmy"},
        )

        result = build_interpretation_result(config, columns_still_time_axis=True)

        assert result.options == {"date_order": "dmy"}

    def test_options_default_empty_when_unconfigured(self):
        result = build_interpretation_result(None, columns_still_time_axis=True)

        assert result.options == {}

    def test_confidence_and_preview_supported_are_caller_supplied(self):
        # Slice 8A: the caller (time_axis_service) supplies real values
        # for a sample interpreter -- this module never looks up the
        # registry itself to decide.
        config = TimeAxisConfiguration(
            column_indices=(0,), family=FAMILY_ABSOLUTE, provenance=PROVENANCE_NATIVE,
            interpreter_id=INTERPRETER_ID_ABSOLUTE_DATETIME,
        )

        result = build_interpretation_result(
            config, columns_still_time_axis=True, confidence=CONFIDENCE_HIGH, preview_supported=True,
        )

        assert result.confidence == CONFIDENCE_HIGH
        assert result.preview_supported is True


class TestSlice8AVocabulary:
    def test_four_ambiguity_levels_not_more(self):
        assert KNOWN_AMBIGUITY_LEVELS == (AMBIGUITY_UNAMBIGUOUS, AMBIGUITY_AMBIGUOUS, AMBIGUITY_INVALID)

    def test_four_date_orders_including_auto(self):
        assert KNOWN_DATE_ORDERS == ("dmy", "mdy", "ymd", "auto")

    def test_diagnostic_ambiguity_defaults_to_unambiguous(self):
        diagnostic = TimeAxisDiagnostic(severity_hint="info", code="x", message="msg")

        assert diagnostic.ambiguity == AMBIGUITY_UNAMBIGUOUS
        assert diagnostic.details is None

    def test_diagnostic_details_bag_is_optional_and_structured(self):
        diagnostic = TimeAxisDiagnostic(
            severity_hint="warning", code="unparseable_datetime", message="msg",
            ambiguity=AMBIGUITY_INVALID, details={"matched": 1, "sample_size": 3},
        )

        assert diagnostic.details == {"matched": 1, "sample_size": 3}


class TestResolveStatusReconstructionOffered:
    """(Slice 8C) `provenance == PROVENANCE_RECONSTRUCTED` is a SEPARATE
    `review_required` trigger from the ambiguity mechanism -- unlike an
    ambiguous diagnostic, it must never block `confirmed=true` from
    succeeding."""

    def test_reconstructed_unconfirmed_is_review_required(self):
        config = TimeAxisConfiguration(
            column_indices=(0,), family=FAMILY_PARTIAL, provenance=PROVENANCE_RECONSTRUCTED,
            interpreter_id=INTERPRETER_ID_REPEATED_TIMESTAMP, interval_seconds=0.2, confirmed=False,
        )
        diagnostic = TimeAxisDiagnostic(severity_hint="info", code="anchor_assumption_required", message="msg")

        status = resolve_status(config, columns_still_time_axis=True, diagnostics=[diagnostic])

        assert status == STATUS_REVIEW_REQUIRED

    def test_reconstructed_confirmed_reaches_confirmed_despite_info_diagnostics(self):
        config = TimeAxisConfiguration(
            column_indices=(0,), family=FAMILY_PARTIAL, provenance=PROVENANCE_RECONSTRUCTED,
            interpreter_id=INTERPRETER_ID_REPEATED_TIMESTAMP, interval_seconds=0.2, confirmed=True,
        )
        diagnostics = [
            TimeAxisDiagnostic(severity_hint="info", code="repeated_timestamp_detected", message="msg"),
            TimeAxisDiagnostic(severity_hint="info", code="anchor_assumption_required", message="msg"),
        ]

        status = resolve_status(config, columns_still_time_axis=True, diagnostics=diagnostics)

        assert status == STATUS_CONFIRMED

    def test_reconstructed_confirmed_still_shows_needs_attention_for_a_real_warning(self):
        # An INFO-only diagnostic never blocks reaching `confirmed`, but
        # a genuine WARNING (e.g. inconsistent_bucket_count) still does
        # -- exactly like every other interpreter's own warnings.
        config = TimeAxisConfiguration(
            column_indices=(0,), family=FAMILY_PARTIAL, provenance=PROVENANCE_RECONSTRUCTED,
            interpreter_id=INTERPRETER_ID_REPEATED_TIMESTAMP, interval_seconds=0.2, confirmed=True,
        )
        diagnostics = [
            TimeAxisDiagnostic(severity_hint="info", code="repeated_timestamp_detected", message="msg"),
            TimeAxisDiagnostic(severity_hint="warning", code="inconsistent_bucket_count", message="msg"),
        ]

        status = resolve_status(config, columns_still_time_axis=True, diagnostics=diagnostics)

        assert status == STATUS_NEEDS_ATTENTION

    def test_user_specified_does_not_trigger_the_reconstructed_rule(self):
        config = TimeAxisConfiguration(
            column_indices=(0,), family=FAMILY_PARTIAL, provenance=PROVENANCE_USER_SPECIFIED,
            interpreter_id=INTERPRETER_ID_REPEATED_TIMESTAMP, interval_seconds=0.2, confirmed=False,
        )

        status = resolve_status(config, columns_still_time_axis=True, diagnostics=[])

        assert status == STATUS_DETECTED


class TestResolveStatusAttentionWorthyFilter:
    def test_info_only_diagnostics_reach_detected_when_unconfirmed(self):
        config = TimeAxisConfiguration(
            column_indices=(0,), family=FAMILY_PARTIAL, provenance=PROVENANCE_NATIVE,
            interpreter_id=INTERPRETER_ID_REPEATED_TIMESTAMP, confirmed=False,
        )
        diagnostic = TimeAxisDiagnostic(severity_hint="info", code="repeated_timestamp_detected", message="msg")

        status = resolve_status(config, columns_still_time_axis=True, diagnostics=[diagnostic])

        assert status == STATUS_DETECTED

    def test_warning_diagnostic_still_reaches_needs_attention(self):
        config = TimeAxisConfiguration(
            column_indices=(0,), family=FAMILY_ABSOLUTE, provenance=PROVENANCE_NATIVE,
            interpreter_id=INTERPRETER_ID_ABSOLUTE_DATETIME, confirmed=False,
        )
        diagnostic = TimeAxisDiagnostic(severity_hint="warning", code="mixed_datetime_format", message="msg")

        status = resolve_status(config, columns_still_time_axis=True, diagnostics=[diagnostic])

        assert status == STATUS_NEEDS_ATTENTION
