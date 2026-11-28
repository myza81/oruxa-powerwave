"""Static regression tests for PU-UI-002: Recording Details → Waveform
Analysis Per-Unit synchronisation.

Root cause: ww.perUnitMode is an undefined property (never assigned anywhere
in the codebase). wwRdVoltageApply and wwRdVoltageRevert guarded their refresh
calls on `if (ww.perUnitMode)`, which is always falsy, so the refresh never
fired. wwRdCurrentApply, wwRdVtApply, wwRdVtRemove, wwRdCtApply, and
wwRdCtRemove had no refresh call at all.

Fix: replace `ww.perUnitMode` with `ww.unitMode === "per_unit"` and add the
same guard + call to the five functions that were missing it entirely.
"""

from __future__ import annotations

from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "index.html"


def _source() -> str:
    return FRONTEND.read_text(encoding="utf-8")


def _function_body(source: str, signature: str, next_signature: str) -> str:
    start = source.index(signature)
    end = source.index(next_signature, start)
    return source[start:end]


REFRESH_CALL = "wwRefreshDisplayedChannelsForPerUnitChange(sourceId)"
UNIT_MODE_GUARD = 'ww.unitMode === "per_unit"'
STALE_GUARD = "ww.perUnitMode"


class TestStalePropertyAbsent:
    """The undefined property ww.perUnitMode must not appear anywhere in the
    codebase.  It was the root cause of PU-UI-002: the refresh guard always
    evaluated as falsy because the property is never assigned."""

    def test_ww_per_unit_mode_property_not_used_anywhere(self):
        source = _source()
        assert STALE_GUARD not in source, (
            "ww.perUnitMode is undefined — use ww.unitMode === \"per_unit\""
        )


class TestVoltageApplyRefresh:
    """Test A: wwRdVoltageApply must call the WA refresh when PU mode is
    active.  This was the original confirmed UAT defect."""

    def test_voltage_apply_calls_refresh(self):
        source = _source()
        body = _function_body(source, "async function wwRdVoltageApply()", "async function wwRdVoltageRevert()")
        assert REFRESH_CALL in body

    def test_voltage_apply_uses_correct_unit_mode_guard(self):
        source = _source()
        body = _function_body(source, "async function wwRdVoltageApply()", "async function wwRdVoltageRevert()")
        assert UNIT_MODE_GUARD in body

    def test_voltage_apply_does_not_use_stale_guard(self):
        source = _source()
        body = _function_body(source, "async function wwRdVoltageApply()", "async function wwRdVoltageRevert()")
        assert STALE_GUARD not in body


class TestVoltageRevertRefresh:
    """Test B: wwRdVoltageRevert must also call the WA refresh — clearing a
    nominal voltage changes the effective PU base just as saving one does."""

    def test_voltage_revert_calls_refresh(self):
        source = _source()
        body = _function_body(source, "async function wwRdVoltageRevert()", "async function wwRdCurrentApply()")
        assert REFRESH_CALL in body

    def test_voltage_revert_uses_correct_unit_mode_guard(self):
        source = _source()
        body = _function_body(source, "async function wwRdVoltageRevert()", "async function wwRdCurrentApply()")
        assert UNIT_MODE_GUARD in body

    def test_voltage_revert_does_not_use_stale_guard(self):
        source = _source()
        body = _function_body(source, "async function wwRdVoltageRevert()", "async function wwRdCurrentApply()")
        assert STALE_GUARD not in body


class TestCurrentApplyRefresh:
    """Test C: wwRdCurrentApply must call the WA refresh — saving equipment
    MVA and linked voltage group changes the effective current PU base."""

    def test_current_apply_calls_refresh(self):
        source = _source()
        body = _function_body(source, "async function wwRdCurrentApply()", "function wwRdVtUpdateLiveRatio()")
        assert REFRESH_CALL in body

    def test_current_apply_uses_correct_unit_mode_guard(self):
        source = _source()
        body = _function_body(source, "async function wwRdCurrentApply()", "function wwRdVtUpdateLiveRatio()")
        assert UNIT_MODE_GUARD in body


class TestVtApplyRefresh:
    """Test D: wwRdVtApply must call the WA refresh — saving a VT ratio
    changes the effective scaling of the voltage channel group."""

    def test_vt_apply_calls_refresh(self):
        source = _source()
        body = _function_body(source, "async function wwRdVtApply()", "async function wwRdVtRemove()")
        assert REFRESH_CALL in body

    def test_vt_apply_uses_correct_unit_mode_guard(self):
        source = _source()
        body = _function_body(source, "async function wwRdVtApply()", "async function wwRdVtRemove()")
        assert UNIT_MODE_GUARD in body


class TestVtRemoveRefresh:
    """Test E: wwRdVtRemove must call the WA refresh — removing a VT ratio
    reverts the channel scaling and changes the displayed values."""

    def test_vt_remove_calls_refresh(self):
        source = _source()
        body = _function_body(source, "async function wwRdVtRemove()", "async function wwRdCtApply()")
        assert REFRESH_CALL in body

    def test_vt_remove_uses_correct_unit_mode_guard(self):
        source = _source()
        body = _function_body(source, "async function wwRdVtRemove()", "async function wwRdCtApply()")
        assert UNIT_MODE_GUARD in body


class TestCtApplyRefresh:
    """Test F: wwRdCtApply must call the WA refresh — saving a CT ratio
    changes the effective scaling of the current channel group."""

    def test_ct_apply_calls_refresh(self):
        source = _source()
        body = _function_body(source, "async function wwRdCtApply()", "async function wwRdCtRemove()")
        assert REFRESH_CALL in body

    def test_ct_apply_uses_correct_unit_mode_guard(self):
        source = _source()
        body = _function_body(source, "async function wwRdCtApply()", "async function wwRdCtRemove()")
        assert UNIT_MODE_GUARD in body


class TestCtRemoveRefresh:
    """Test G: wwRdCtRemove must call the WA refresh — removing a CT ratio
    reverts the channel scaling and changes the displayed values."""

    def test_ct_remove_calls_refresh(self):
        source = _source()
        body = _function_body(source, "async function wwRdCtRemove()", "function wwRdUpdateGroupInCache(")
        assert REFRESH_CALL in body

    def test_ct_remove_uses_correct_unit_mode_guard(self):
        source = _source()
        body = _function_body(source, "async function wwRdCtRemove()", "function wwRdUpdateGroupInCache(")
        assert UNIT_MODE_GUARD in body
