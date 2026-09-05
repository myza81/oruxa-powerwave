"""Explicit interpreter authority (additive, 2026-09-05): "auto-detection
assists the user, explicit selection governs the interpretation." Once an
engineer explicitly selects (or restores a saved) sample interpreter, that
selection is authoritative -- detection may validate/challenge/recommend,
but must never silently substitute a different interpretation and let it
proceed as though nothing were wrong. These tests exercise EXPLICIT
selection through the real service-layer entry points (`set_time_axis_
configuration`, `get_time_axis_summary`, `interpret_time_axis`,
`build_issue_summary`, `convert_preparation_source`) -- never the raw
detector functions in isolation, since the guard is about the FRAMEWORK's
own central enforcement, not any one interpreter's own detect() body.
"""

from __future__ import annotations

import asyncio
import io

import pytest
from fastapi import UploadFile
from starlette.datastructures import Headers

from app.domain.time_axis import (
    DIAGNOSTIC_INTERPRETER_FAMILY_MISMATCH,
    FAMILY_ABSOLUTE,
    FAMILY_ELAPSED,
    FAMILY_PARTIAL,
    FAMILY_SAMPLE_INDEX,
    INTERPRETER_ID_ABSOLUTE_DATETIME,
    INTERPRETER_ID_ELAPSED_NUMERIC,
    INTERPRETER_ID_SAMPLE_INDEX,
    INTERPRETER_ID_SPLIT_DATE_TIME,
    INTERPRETER_ID_TIME_OF_DAY,
    STATUS_NEEDS_ATTENTION,
)
from app.services.errors import ConversionNotReadyError, InvalidTimeAxisConfigurationError
from app.services.preparation_conversion_service import convert_preparation_source
from app.services.preparation_import_service import import_csv_preparation_source
from app.services.preparation_issue_service import build_issue_summary
from app.services.preparation_session_registry import PreparationSessionRegistry
from app.services.time_axis_service import get_time_axis_summary, interpret_time_axis, set_time_axis_configuration
from app.services.working_overlay_service import set_column_role
from app.services.workspace_registry import WorkspaceRegistry

WS = "ws-1"


def _upload(content: bytes, filename: str = "e.csv") -> UploadFile:
    return UploadFile(file=io.BytesIO(content), filename=filename, headers=Headers({"content-type": "text/csv"}))


def _add_csv(registry: PreparationSessionRegistry, content: bytes) -> str:
    summary = asyncio.run(
        import_csv_preparation_source(workspace_id=WS, csv_upload=_upload(content), max_total_bytes=10_000_000, registry=registry)
    )
    return summary.source_id


def _mark_columns(registry: PreparationSessionRegistry, source_id: str) -> None:
    set_column_role(workspace_id=WS, source_id=source_id, column_index=0, role="time_axis", registry=registry)
    set_column_role(workspace_id=WS, source_id=source_id, column_index=1, role="waveform", registry=registry)


def _mismatch_codes(diagnostics) -> list[str]:
    return [d.code for d in diagnostics]


class TestExample1AbsoluteDateTimeSelectedTimeOfDayData:
    """Task's own Example 1: user selects Absolute DateTime; data is
    genuinely bare time-of-day. Expected: selected interpreter stays
    Absolute DateTime (never silently changed), mismatch flagged,
    Save/confirm/conversion blocked, no silent fallback."""

    def _configure(self, registry, source_id, *, confirmed):
        return set_time_axis_configuration(
            workspace_id=WS, source_id=source_id, column_indices=(0,),
            interpreter_id=INTERPRETER_ID_ABSOLUTE_DATETIME, confirmed=confirmed, registry=registry,
        )

    def test_selected_interpreter_never_silently_changes(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"18:04:00,1.0\n18:04:00.020000,2.0\n18:04:00.040000,3.0\n")
        _mark_columns(registry, source_id)

        result = self._configure(registry, source_id, confirmed=False)

        assert result.interpreter_id == INTERPRETER_ID_ABSOLUTE_DATETIME

    def test_mismatch_flagged_with_suggestion(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"18:04:00,1.0\n18:04:00.020000,2.0\n18:04:00.040000,3.0\n")
        _mark_columns(registry, source_id)

        result = self._configure(registry, source_id, confirmed=False)

        assert result.status == STATUS_NEEDS_ATTENTION
        codes = _mismatch_codes(result.diagnostics)
        assert DIAGNOSTIC_INTERPRETER_FAMILY_MISMATCH in codes
        mismatch = next(d for d in result.diagnostics if d.code == DIAGNOSTIC_INTERPRETER_FAMILY_MISMATCH)
        assert mismatch.details["detected_family"] == FAMILY_PARTIAL
        assert mismatch.details["suggested_interpreter_id"] == INTERPRETER_ID_TIME_OF_DAY

    def test_confirm_is_blocked(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"18:04:00,1.0\n18:04:00.020000,2.0\n18:04:00.040000,3.0\n")
        _mark_columns(registry, source_id)

        with pytest.raises(InvalidTimeAxisConfigurationError):
            self._configure(registry, source_id, confirmed=True)

    def test_save_still_persists_the_selection_for_inspection(self):
        # The configuration is NOT silently discarded on a non-confirmed
        # save -- it stays visible/inspectable as Needs Attention (task's
        # own "restored saved configuration should be treated as an
        # intentional interpretation" principle applies here too: the
        # engineer's OWN choice is what gets stored and shown back).
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"18:04:00,1.0\n18:04:00.020000,2.0\n18:04:00.040000,3.0\n")
        _mark_columns(registry, source_id)
        self._configure(registry, source_id, confirmed=False)

        summary = get_time_axis_summary(workspace_id=WS, source_id=source_id, registry=registry)

        assert summary.interpreter_id == INTERPRETER_ID_ABSOLUTE_DATETIME
        assert summary.status == STATUS_NEEDS_ATTENTION

    def test_readiness_blocks_and_conversion_blocks(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"18:04:00,1.0\n18:04:00.020000,2.0\n18:04:00.040000,3.0\n")
        _mark_columns(registry, source_id)
        self._configure(registry, source_id, confirmed=False)

        issues = build_issue_summary(workspace_id=WS, source_id=source_id, registry=registry)
        assert issues.is_ready is False
        assert DIAGNOSTIC_INTERPRETER_FAMILY_MISMATCH in [i.code for i in issues.issues]

        ws_registry = WorkspaceRegistry()
        with pytest.raises(ConversionNotReadyError):
            convert_preparation_source(workspace_id=WS, source_id=source_id, preparation_registry=registry, workspace_registry=ws_registry)

    def test_dry_run_detect_also_shows_the_mismatch(self):
        # The mismatch/recommendation UI is meant to surface via the
        # dry-run preview BEFORE a real Save is ever attempted.
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"18:04:00,1.0\n18:04:00.020000,2.0\n18:04:00.040000,3.0\n")
        _mark_columns(registry, source_id)

        preview = interpret_time_axis(
            workspace_id=WS, source_id=source_id, column_indices=(0,),
            interpreter_id=INTERPRETER_ID_ABSOLUTE_DATETIME, registry=registry,
        )

        assert preview.interpreter_id == INTERPRETER_ID_ABSOLUTE_DATETIME
        assert DIAGNOSTIC_INTERPRETER_FAMILY_MISMATCH in _mismatch_codes(preview.diagnostics)


class TestExample2TimeOfDaySelectedAbsoluteData:
    """Task's own Example 2: user selects Time of Day; data has a real
    calendar date. Expected: no silent date stripping, mismatch flagged,
    suggestion may point at Absolute DateTime, blocked."""

    def test_no_silent_date_stripping_and_mismatch_flagged(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"2026-06-03 18:04:00,1.0\n2026-06-03 18:04:00.020,2.0\n")
        _mark_columns(registry, source_id)

        result = set_time_axis_configuration(
            workspace_id=WS, source_id=source_id, column_indices=(0,),
            interpreter_id=INTERPRETER_ID_TIME_OF_DAY, confirmed=False, registry=registry,
        )

        assert result.interpreter_id == INTERPRETER_ID_TIME_OF_DAY
        assert result.status == STATUS_NEEDS_ATTENTION
        # The Time of Day interpreter itself already rejects a value that
        # carries a genuine date (never silently truncates it to a bare
        # time) -- this pre-existing per-value guard is what actually
        # produces the finding here, verified directly rather than assumed.
        issues = build_issue_summary(workspace_id=WS, source_id=source_id, registry=registry)
        assert issues.is_ready is False


class TestExample3ElapsedNumericSelectedClockTimeData:
    """Task's own Example 3: Elapsed Numeric selected; data is clock
    time. Expected: mismatch (via the interpreter's own existing
    non-numeric-value diagnostic), never silently reinterpreted as Time
    of Day."""

    def test_non_numeric_clock_values_block_readiness(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"18:04:00,1.0\n18:04:00.020,2.0\n")
        _mark_columns(registry, source_id)

        result = set_time_axis_configuration(
            workspace_id=WS, source_id=source_id, column_indices=(0,),
            interpreter_id=INTERPRETER_ID_ELAPSED_NUMERIC, unit="seconds", confirmed=False, registry=registry,
        )

        # Never silently continues as Time of Day: the reported family
        # stays FAMILY_ELAPSED (elapsed_numeric's own sole contract),
        # never promoted/reinterpreted to FAMILY_PARTIAL.
        assert result.family == FAMILY_ELAPSED
        assert result.interpreter_id == INTERPRETER_ID_ELAPSED_NUMERIC
        issues = build_issue_summary(workspace_id=WS, source_id=source_id, registry=registry)
        assert issues.is_ready is False


class TestExample4SampleIndexSelectedElapsedLookingData:
    """Task's own Example 4: Sample Index selected; data merely LOOKS
    like elapsed seconds (0.000/0.020/0.040). Expected: preserve
    existing detection logic -- these values are still structurally
    valid sample-index floats, so no NEW heuristic invents a mismatch
    here; no silent reinterpretation either way."""

    def test_numeric_values_are_accepted_as_sample_index_unchanged(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"0.000,1.0\n0.020,2.0\n0.040,3.0\n")
        _mark_columns(registry, source_id)

        result = set_time_axis_configuration(
            workspace_id=WS, source_id=source_id, column_indices=(0,),
            interpreter_id=INTERPRETER_ID_SAMPLE_INDEX, confirmed=False, registry=registry,
        )

        assert result.family == FAMILY_SAMPLE_INDEX
        assert result.interpreter_id == INTERPRETER_ID_SAMPLE_INDEX
        assert DIAGNOSTIC_INTERPRETER_FAMILY_MISMATCH not in _mismatch_codes(result.diagnostics)


class TestCorrectSelectionsRemainUnchanged:
    """Cases 3-7 of the required validation matrix: a CORRECTLY selected
    interpreter for genuinely matching data must show no mismatch and
    remain fully save/convert-able, exactly as before this task."""

    def test_correct_time_of_day(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"18:04:00,1.0\n18:04:00.020000,2.0\n18:04:00.040000,3.0\n")
        _mark_columns(registry, source_id)
        result = set_time_axis_configuration(
            workspace_id=WS, source_id=source_id, column_indices=(0,),
            interpreter_id=INTERPRETER_ID_TIME_OF_DAY, confirmed=True, registry=registry,
        )
        assert DIAGNOSTIC_INTERPRETER_FAMILY_MISMATCH not in _mismatch_codes(result.diagnostics)
        assert build_issue_summary(workspace_id=WS, source_id=source_id, registry=registry).is_ready is True

    def test_correct_absolute_datetime(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"2026-06-03 18:04:00,1.0\n2026-06-03 18:04:00.020,2.0\n")
        _mark_columns(registry, source_id)
        result = set_time_axis_configuration(
            workspace_id=WS, source_id=source_id, column_indices=(0,),
            interpreter_id=INTERPRETER_ID_ABSOLUTE_DATETIME, confirmed=True, registry=registry,
        )
        assert result.family == FAMILY_ABSOLUTE
        assert DIAGNOSTIC_INTERPRETER_FAMILY_MISMATCH not in _mismatch_codes(result.diagnostics)
        assert build_issue_summary(workspace_id=WS, source_id=source_id, registry=registry).is_ready is True

    def test_correct_date_plus_time(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"2026-06-03,18:04:00\n2026-06-03,18:04:00.020\n")
        set_column_role(workspace_id=WS, source_id=source_id, column_index=0, role="time_axis", registry=registry)
        set_column_role(workspace_id=WS, source_id=source_id, column_index=1, role="time_axis", registry=registry)
        result = set_time_axis_configuration(
            workspace_id=WS, source_id=source_id, column_indices=(0, 1),
            interpreter_id=INTERPRETER_ID_SPLIT_DATE_TIME, confirmed=True, registry=registry,
        )
        assert result.family == FAMILY_ABSOLUTE
        assert DIAGNOSTIC_INTERPRETER_FAMILY_MISMATCH not in _mismatch_codes(result.diagnostics)

    def test_correct_elapsed_numeric(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"5.000,1.0\n5.020,2.0\n5.040,3.0\n")
        _mark_columns(registry, source_id)
        result = set_time_axis_configuration(
            workspace_id=WS, source_id=source_id, column_indices=(0,),
            interpreter_id=INTERPRETER_ID_ELAPSED_NUMERIC, unit="seconds", confirmed=True, registry=registry,
        )
        assert result.family == FAMILY_ELAPSED
        assert DIAGNOSTIC_INTERPRETER_FAMILY_MISMATCH not in _mismatch_codes(result.diagnostics)
        assert build_issue_summary(workspace_id=WS, source_id=source_id, registry=registry).is_ready is True

    def test_correct_sample_index(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"100,1.0\n101,2.0\n102,3.0\n")
        _mark_columns(registry, source_id)
        result = set_time_axis_configuration(
            workspace_id=WS, source_id=source_id, column_indices=(0,),
            interpreter_id=INTERPRETER_ID_SAMPLE_INDEX, interval_seconds=0.02, confirmed=True, registry=registry,
        )
        assert result.family == FAMILY_SAMPLE_INDEX
        assert DIAGNOSTIC_INTERPRETER_FAMILY_MISMATCH not in _mismatch_codes(result.diagnostics)
        assert build_issue_summary(workspace_id=WS, source_id=source_id, registry=registry).is_ready is True


class TestUserAcceptsRecommendation:
    """Item 10 of the required validation matrix: the "Use X" quick
    accept is, at the backend/API-contract level, simply a SECOND
    explicit `set_time_axis_configuration()` call with the SUGGESTED
    interpreter_id substituted in by the (frontend) caller -- never a
    backend auto-switch. Re-detection against the corrected selection
    must pass cleanly and Save must become available."""

    def test_switching_to_the_suggested_interpreter_resolves_the_mismatch(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"18:04:00,1.0\n18:04:00.020000,2.0\n18:04:00.040000,3.0\n")
        _mark_columns(registry, source_id)
        mismatched = set_time_axis_configuration(
            workspace_id=WS, source_id=source_id, column_indices=(0,),
            interpreter_id=INTERPRETER_ID_ABSOLUTE_DATETIME, confirmed=False, registry=registry,
        )
        mismatch = next(d for d in mismatched.diagnostics if d.code == DIAGNOSTIC_INTERPRETER_FAMILY_MISMATCH)
        suggested_id = mismatch.details["suggested_interpreter_id"]

        accepted = set_time_axis_configuration(
            workspace_id=WS, source_id=source_id, column_indices=(0,),
            interpreter_id=suggested_id, confirmed=True, registry=registry,
        )

        assert accepted.interpreter_id == INTERPRETER_ID_TIME_OF_DAY
        assert DIAGNOSTIC_INTERPRETER_FAMILY_MISMATCH not in _mismatch_codes(accepted.diagnostics)
        assert build_issue_summary(workspace_id=WS, source_id=source_id, registry=registry).is_ready is True


class TestRestoredSavedConfiguration:
    """Item 11: a configuration saved earlier (e.g. before this data
    changed, or from a previous session/process) is re-evaluated live
    on every read -- the detector never silently replaces the STORED
    interpreter_id/selection, it only reports what it currently finds
    against that same, unchanged selection."""

    def test_get_time_axis_summary_never_changes_the_stored_interpreter(self):
        registry = PreparationSessionRegistry()
        source_id = _add_csv(registry, b"18:04:00,1.0\n18:04:00.020000,2.0\n18:04:00.040000,3.0\n")
        _mark_columns(registry, source_id)
        set_time_axis_configuration(
            workspace_id=WS, source_id=source_id, column_indices=(0,),
            interpreter_id=INTERPRETER_ID_ABSOLUTE_DATETIME, confirmed=False, registry=registry,
        )

        # Simulate a "restored session" -- a fresh read, independent of
        # whatever the original save call chain looked like.
        restored = get_time_axis_summary(workspace_id=WS, source_id=source_id, registry=registry)

        assert restored.interpreter_id == INTERPRETER_ID_ABSOLUTE_DATETIME
        assert restored.status == STATUS_NEEDS_ATTENTION
        assert DIAGNOSTIC_INTERPRETER_FAMILY_MISMATCH in _mismatch_codes(restored.diagnostics)
