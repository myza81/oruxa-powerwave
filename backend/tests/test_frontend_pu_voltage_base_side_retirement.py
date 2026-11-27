"""DEC-219 static guards -- the separate Voltage Base Reference Side input is retired from Recording Details.

Nominal system voltage is always the Primary PU base; the effective denominator is the backend's (side-denominator authority), never computed
in the frontend. These checks pin what the frontend may and may not send, because a stored declaration (a legacy Secondary base, a historical
Unknown) must never be overwritten as a side effect of an unrelated save:

  * the selector, its option list and its draft state are gone;
  * the three non-Apply Voltage writers (clear nominal, set VT, clear VT) do not send `base_reference_side` at all;
  * Apply sends it only through `wwRdVoltageNominalSave`, which declares "primary" and only when a nominal base is established;
  * no denominator arithmetic appears in the Voltage configuration code;
  * the Calculated Current manual base-side control (Stage 5B, D-2) is untouched.

Same source-text substring-assertion pattern every other `test_frontend_*.py` file uses. The behaviour is proven at the API in
`test_pu_voltage_base_side_retirement.py` and in the browser by `pu-voltage-base-side-retirement.spec.js`.
"""

from __future__ import annotations

from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "index.html"


def _source() -> str:
    return FRONTEND.read_text(encoding="utf-8")


def _between(source: str, start_marker: str, end_marker: str) -> str:
    start = source.index(start_marker)
    return source[start:source.index(end_marker, start)]


def test_the_selector_and_its_draft_state_are_gone():
    source = _source()
    assert "wwRdVltRefSide" not in source
    assert "draftRefSide" not in source
    assert "const sideOptions" not in source
    assert "Controls which voltage level is used as the PU denominator" not in source


def test_the_voltage_writers_never_echo_or_default_the_side():
    source = _source()
    apply_writer = _between(source, "async function wwRdVoltageApply()", "async function wwRdVoltageRevert()")
    other_writers = _between(source, "async function wwRdVoltageRevert()", "async function wwRdVtRemove()")
    other_writers += source[source.index("async function wwRdVtRemove()"):source.index("async function wwRdVtRemove()") + 1800]
    assert "base_reference_side" not in other_writers          # clear nominal, set VT, clear VT: the stored declaration is preserved
    # the old echo, which wrote Unknown whenever a group had no stored configuration, exists nowhere
    assert 'base_reference_side: (vc && vc.base_reference_side) || "unknown"' not in source
    assert "base_reference_side: ed.draftRefSide" not in source
    # Apply sends the side only from the helper's decision
    assert "body.base_reference_side = nominalSave.side" in apply_writer
    assert apply_writer.count("base_reference_side") == 1


def test_a_primary_side_is_declared_only_when_a_nominal_base_is_established():
    helper = _between(_source(), "function wwRdVoltageNominalSave(vc, rawKv)", "function wwRdLegacySecondaryBaseNoteHtml")
    assert 'side: send ? "primary" : null' in helper
    assert "stored === null || stored !== rawKv" in helper                       # new or changed nominal
    assert 'vc.base_authority === "legacy_manual"' in helper                     # a reviewed (confirmed) nominal
    assert '"secondary"' not in helper and '"unknown"' not in helper             # nothing else is ever declared here


def test_a_legacy_secondary_base_stays_identifiable_read_only():
    source = _source()
    note = _between(source, "function wwRdLegacySecondaryBaseNoteHtml(vc, editing)", "async function wwRdVoltageApply()")
    assert 'vc.base_reference_side !== "secondary" || vc.secondary_voltage_ll_v == null' in note     # the D-5 criterion
    assert "Legacy Secondary base" in note and "kept as stored" in note
    assert "<select" not in note and "<input" not in note                        # read-only: management awaits owner approval
    assert source.count("configHtml += wwRdLegacySecondaryBaseNoteHtml(vc,") == 2   # shown in read mode and in edit mode


def test_the_frontend_does_no_denominator_arithmetic_in_the_voltage_configuration_code():
    code = _between(_source(), "function wwRdVoltageNominalSave(vc, rawKv)", "// D2: Revert the manual kV")
    for forbidden in ("Math.sqrt", "/ ratio", "* ratio", "vt_primary_v /", "Math.SQRT"):
        assert forbidden not in code


def test_the_calculated_current_manual_base_side_control_remains():
    source = _source()
    assert "function wwPerUnitBaseSideFieldHtml(id, side)" in source
    assert 'wwPerUnitBaseSideFieldHtml("wwCalculatedPuSide", state.side)' in source
    assert "base_reference_side: state.side" in source                           # Stage 5B / D-2: independent side semantics kept
