"""NF-3E closeout: mutation checks of the consumer guards (compliance execution + readiness, oscillation, phasor family, overcurrent) and of
the shared sentinel/reason vocabulary. Same method as `mutation_checks.py` (one production line mutated in a scratch copy; the focused test
files must fail):

    python mutation_checks_guards.py <python with backend requirements> [--out results.json] [--only G1,G2]
"""

from __future__ import annotations

import sys

import mutation_checks as base

base.TEST = "tests/test_nf3e_consumer_guards.py tests/test_frontend_nf3e_staleness.py"

SPEC = "app/services/oscillation_spectrum_service.py"
REPR = "app/services/oscillation_representation_service.py"
PHASOR = "app/services/phasor_analysis_service.py"
OC = "app/services/overcurrent_analysis_service.py"
READY = "app/services/compliance_readiness_service.py"
SERIES = "app/services/compliance_series.py"
STALE = "app/services/calculated_channel_staleness.py"

base.MUTATIONS = [
    ("G1", SERIES, "if reg.frequency_access is not None:\n        assert_inputs_not_stale([ref]", "if False:\n        assert_inputs_not_stale([ref]",
     "compliance execution never refuses a stale input"),
    ("G2", SERIES, "assert_inputs_not_stale([ref], workspace_id=workspace_id, calc_registry=reg.calc", "assert_inputs_not_stale([], workspace_id=workspace_id, calc_registry=reg.calc",
     "compliance execution checks no input"),
    ("G3", READY, "    members = _block_stale_members(ctx, members)\n", "    members = members\n", "readiness never blocks a stale member"),
    ("G4", READY, "refs = [m.channel_ref, m.step.input_ref if m.step is not None else None]", "refs = [m.channel_ref]",
     "readiness ignores the stale input of an RMS step"),
    ("G5", READY, "refs = [m.channel_ref, m.step.input_ref if m.step is not None else None]", "refs = [m.step.input_ref if m.step is not None else None]",
     "readiness ignores the member's own stale channel"),
    ("G6", READY, "            member=m.member, state=STATE_BLOCKED, channel_name=m.channel_name, calculated_channel_id=m.calculated_channel_id,",
     "            member=m.member, state=STATE_INCOMPATIBLE, channel_name=m.channel_name, calculated_channel_id=m.calculated_channel_id,",
     "a stale member is reported with the wrong state"),
    ("G7", "app/api/v1/compliance.py", '"stale_calculated_input": status.HTTP_409_CONFLICT,', '"stale_calculated_input": status.HTTP_400_BAD_REQUEST,',
     "compliance maps the refusal to the wrong HTTP status"),
    ("G8", "app/api/v1/compliance.py", "                frequency_access=state.nominal_frequency_access,\n", "", "the compliance router forgets the authority"),
    ("G9", READY, "current_config=current_config_registry, frequency_access=frequency_access,", "current_config=current_config_registry,",
     "readiness builds Registries without the authority"),
    ("G10", SPEC, "    assert_inputs_not_stale([input_ref], workspace_id=workspace_id, calc_registry=calc_registry, frequency_access=frequency_access)\n    resolved = _resolve_input(",
     "    resolved = _resolve_input(", "oscillation analysis entry no longer refuses (native representation accepts a stale RMS)"),
    ("G11", REPR, "    assert_inputs_not_stale([input_ref], workspace_id=workspace_id, calc_registry=calc_registry, frequency_access=frequency_access)\n    resolved = _resolve_input(",
     "    resolved = _resolve_input(", "the oscillation representation endpoint no longer refuses"),
    ("G12", "app/api/v1/oscillation.py", '"stale_calculated_input": status.HTTP_409_CONFLICT,', '"stale_calculated_input": status.HTTP_400_BAD_REQUEST,',
     "oscillation maps the refusal to the wrong HTTP status"),
    ("G13", PHASOR, "    if stale is not None:\n        return stale\n    calculated = get_calculated_result(", "    if False:\n        return stale\n    calculated = get_calculated_result(",
     "the phasor fetcher never blocks a stale channel"),
    ("G14", PHASOR, "        if isinstance(candidate, StaleInputBlocked):\n            return _short_circuit(", "        if False:\n            return _short_circuit(",
     "phasor compute does not handle the sentinel"),
    ("G15", PHASOR, "            role_reason_codes[role_key] = REASON_STALE_CALCULATED_INPUT\n", '            role_reason_codes[role_key] = "channel_unavailable"\n',
     "the phasor diagram reports the wrong reason"),
    ("G16", PHASOR, "status=STATUS_NEEDS_CONFIGURATION, reason_code=REASON_STALE_CALCULATED_INPUT, message=candidate.message,",
     'status=STATUS_NEEDS_CONFIGURATION, reason_code="channel_unavailable", message=candidate.message,', "phasor readiness reports the wrong reason"),
    ("G17", OC, "    if stale is not None:\n        return stale\n    calculated = get_calculated_result(", "    if False:\n        return stale\n    calculated = get_calculated_result(",
     "the overcurrent fetcher never blocks a stale channel"),
    ("G18", OC, "    if isinstance(candidate, StaleInputBlocked):\n        return _short_circuit(", "    if False:\n        return _short_circuit(",
     "overcurrent compute does not handle the sentinel"),
    ("G19", OC, "return OvercurrentReadiness(\n            status=STATUS_NEEDS_CONFIGURATION, reason_code=REASON_STALE_CALCULATED_INPUT,",
     'return OvercurrentReadiness(\n            status=STATUS_NEEDS_CONFIGURATION, reason_code="channel_unavailable",', "overcurrent readiness reports the wrong reason"),
    ("G20", OC, "        return RecordedCurrentInput(\n            status=STATUS_NEEDS_CONFIGURATION, engineering_context_id=engineering_context_id, phase=phase,\n            reason_code=REASON_STALE_CALCULATED_INPUT,",
     '        return RecordedCurrentInput(\n            status=STATUS_NEEDS_CONFIGURATION, engineering_context_id=engineering_context_id, phase=phase,\n            reason_code="channel_unavailable",',
     "the recorded current input reports the wrong reason"),
    ("G21", STALE, 'REASON_STALE_CALCULATED_INPUT = "stale_calculated_input"', 'REASON_STALE_CALCULATED_INPUT = "stale_input"', "the public reason value drifts"),
    ("G22", STALE, "return None if problem is None else StaleInputBlocked(problem)", 'return None if problem is None else StaleInputBlocked("")',
     "the refusal carries no actionable message"),
    ("G23", "../frontend/index.html", 'stale_calculated_input: "This calculated channel is stale', 'stale_calculated_input_x: "This calculated channel is stale',
     "the refused analysis shows no actionable sentence"),
    ("G24", "app/services/waveform_service.py", "from __future__ import annotations\n", "from __future__ import annotations\nfrom app.services import calculated_channel_staleness  # noqa\n",
     "the shared waveform fetcher is guarded (historical inspection would be blocked)"),
]

if __name__ == "__main__":
    raise SystemExit(base.main())
