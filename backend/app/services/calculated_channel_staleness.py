"""NF-3E: derived nominal-frequency staleness of stored calculated channels (NF-001 / DEC-217, O-4, owner policy 2026-11-27).

A calculated channel is immutable and eagerly evaluated: its values are never recomputed when a recording's nominal frequency changes. What
can change is whether those stored values still reflect the recording's current frequency. This module answers that question; it stores
nothing, so the answer can never go out of date, and it never reads or writes a channel's values.

Rules
-----
* **Recording-following** RMS channel (`parameters.nominal_frequency_basis == "recording"`): stale while its stored `nominal_frequency_hz`
  differs (the accessor's agreement tolerance) from the effective frequency of the recording that grounds it (`reference_source_id`), or
  while that recording has no usable frequency. It is current again as soon as they agree (Manual set back to the stored value, or the
  return to Auto), with no separate clearing step.
* **Explicit** RMS channel (`"explicit"`, and any channel created before the basis existed): never stale on its own account. The intent is
  declared by the caller at creation; it is never inferred from the number being equal to the recording's.
* **Inherited**: a channel is stale if any calculated channel it depends on, directly or transitively, is stale. Inherited staleness clears
  only when every stale ancestor is current; unrelated causes are untouched.
* **Not assessed directly**: power channels (fixed 50 Hz, reserved for NF-3F) and every operation that stores no frequency. They only
  inherit; `assessment` says so.
* **Option B** (`assert_inputs_not_stale`): a NEW calculation on a stale input is refused with `StaleCalculatedInputError`. Raw source
  inputs are never stale. Viewing, inspecting and deleting a stale channel is unaffected.
* **Governing principle** (owner, 2026-11-27): a stale calculated channel stays available for HISTORICAL INSPECTION (waveform, cursors, peaks,
  list) but is not a valid input for a new engineering calculation or assessment. Every consumer that starts a new calculation reuses THIS
  module (never a private staleness rule): `assert_inputs_not_stale` where a typed error is the convention (creation, line-to-line,
  compliance execution, oscillation), `stale_input_block` where a result carries a reason code (phasor family, overcurrent), and
  `stale_input_problem` where readiness reports a blocked state (compliance). The shared array fetchers are never guarded.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable

from app.domain.calculated_channel import OP_RMS, ChannelRef
from app.domain.nominal_frequency import ORIGIN_ASSUMED_DEFAULT, ORIGIN_MANUAL
from app.services.calculated_channel_registry import CalculatedChannelRegistry
from app.services.errors import SourceNotFoundError, StaleCalculatedInputError
from app.services.nominal_frequency_access import AGREEMENT_ABS_TOL, AGREEMENT_REL_TOL, NominalFrequencyAccess

BASIS_RECORDING = "recording"
BASIS_EXPLICIT = "explicit"
KNOWN_BASES = (BASIS_RECORDING, BASIS_EXPLICIT)

STATE_CURRENT = "current"
STATE_STALE = "stale"

ASSESSMENT_FREQUENCY_AWARE = "frequency_aware"      # the channel's own frequency is compared with its recording's
ASSESSMENT_INHERITED_ONLY = "inherited_only"        # only upstream staleness can make it stale

REASON_CHANGED = "recording_frequency_changed"
REASON_UNUSABLE = "recording_frequency_unusable"

#: The result-level reason code of analyses that report refusals as a reason code (phasor family, overcurrent). One public value.
REASON_STALE_CALCULATED_INPUT = "stale_calculated_input"

_ORIGIN_TEXT = {
    "recording_metadata": "recording metadata", "import_supplied": "supplied at import", ORIGIN_ASSUMED_DEFAULT: "assumed default",
    ORIGIN_MANUAL: "Manual", "unusable": "unusable declaration",
}


@dataclass(frozen=True, slots=True)
class StaleCause:
    """One stale ancestor (or the channel itself): the root of the staleness, never an intermediate dependant."""

    channel_id: str
    channel_name: str
    reason: str
    stored_hz: float
    effective_hz: float | None
    stored_origin: str | None
    stored_revision: int | None
    effective_origin: str | None
    effective_revision: int | None


@dataclass(frozen=True, slots=True)
class FrequencyStaleness:
    state: str
    assessment: str
    causes: tuple[StaleCause, ...]

    @property
    def stale(self) -> bool:
        return self.state == STATE_STALE


def _agree(a: float, b: float) -> bool:
    return math.isclose(a, b, rel_tol=AGREEMENT_REL_TOL, abs_tol=AGREEMENT_ABS_TOL)


def _own_cause(channel, workspace_id: str, access: NominalFrequencyAccess) -> StaleCause | None:
    stored = channel.parameters.get("nominal_frequency_hz")
    if isinstance(stored, bool) or not isinstance(stored, (int, float)):
        return None
    try:
        effective = access.for_source(workspace_id, channel.reference_source_id)
    except SourceNotFoundError:
        return None                                      # the recording is gone: the existing `incompatible_time_base` signal covers it
    if effective.usable and _agree(float(stored), effective.hz):
        return None
    return StaleCause(
        channel_id=channel.id, channel_name=channel.name, reason=REASON_CHANGED if effective.usable else REASON_UNUSABLE,
        stored_hz=float(stored), effective_hz=effective.hz,
        stored_origin=channel.parameters.get("nominal_frequency_origin"), stored_revision=channel.parameters.get("nominal_frequency_revision"),
        effective_origin=effective.origin, effective_revision=effective.revision)


def frequency_staleness(
    channel, *, workspace_id: str, calc_registry: CalculatedChannelRegistry, frequency_access: NominalFrequencyAccess,
    _memo: dict | None = None,
) -> FrequencyStaleness:
    memo = {} if _memo is None else _memo
    cached = memo.get(channel.id)
    if cached is not None:
        return cached
    own_assessed = channel.operation == OP_RMS and channel.parameters.get("nominal_frequency_basis") == BASIS_RECORDING
    causes: list[StaleCause] = []
    if own_assessed:
        own = _own_cause(channel, workspace_id, frequency_access)
        if own is not None:
            causes.append(own)
    for dependency_id in channel.dependency_ids:
        dependency = calc_registry.get(workspace_id, dependency_id)
        if dependency is None:
            continue
        for cause in frequency_staleness(dependency, workspace_id=workspace_id, calc_registry=calc_registry,
                                         frequency_access=frequency_access, _memo=memo).causes:
            if all(cause.channel_id != c.channel_id for c in causes):
                causes.append(cause)
    result = FrequencyStaleness(
        state=STATE_STALE if causes else STATE_CURRENT,
        assessment=ASSESSMENT_FREQUENCY_AWARE if own_assessed else ASSESSMENT_INHERITED_ONLY, causes=tuple(causes))
    memo[channel.id] = result
    return result


def _hz_text(hz: float | None) -> str:
    return "not usable" if hz is None else f"{hz:g} Hz"


def _origin_text(origin: str | None, revision: int | None) -> str:
    if origin is None:
        return ""
    return f" ({_ORIGIN_TEXT.get(origin, origin)}" + (f", revision {revision}" if revision is not None else "") + ")"


def _cause_sentence(cause: StaleCause, *, inherited: bool) -> str:
    stored = f"{cause.stored_hz:g} Hz{_origin_text(cause.stored_origin, cause.stored_revision)}"
    if cause.reason == REASON_UNUSABLE:
        why = f"was calculated at {stored}, but its recording no longer has a usable nominal frequency"
    else:
        why = (f"was calculated at {stored}, but its recording's nominal frequency is now "
               f"{_hz_text(cause.effective_hz)}{_origin_text(cause.effective_origin, cause.effective_revision)}")
    return f"it depends on '{cause.channel_name}', which {why}" if inherited else f"it {why}"


def stale_input_message(input_name: str, staleness: FrequencyStaleness, input_id: str) -> str:
    sentences = [_cause_sentence(c, inherited=c.channel_id != input_id) for c in staleness.causes]
    first = staleness.causes[0]
    remedy = (f"Create a new RMS channel at the recording's current frequency and use that instead, or return the recording to "
              f"{first.stored_hz:g} Hz. The stale channel stays available to view; its values are not changed.")
    return f"'{input_name}' cannot be used as an input because " + "; ".join(sentences) + ". " + remedy


def first_stale_input(
    inputs: Iterable[ChannelRef], *, workspace_id: str, calc_registry: CalculatedChannelRegistry, frequency_access: NominalFrequencyAccess,
):
    """`(channel, staleness)` of the first stale calculated input (direct or transitive), or None. Raw source inputs are never stale."""
    memo: dict = {}
    for ref in inputs:
        if ref is None or ref.kind != "calculated":
            continue
        channel = calc_registry.get(workspace_id, ref.calculated_channel_id)
        if channel is None:
            continue
        staleness = frequency_staleness(channel, workspace_id=workspace_id, calc_registry=calc_registry,
                                        frequency_access=frequency_access, _memo=memo)
        if staleness.stale:
            return channel, staleness
    return None


def stale_input_problem(
    inputs: Iterable[ChannelRef], *, workspace_id: str, calc_registry: CalculatedChannelRegistry, frequency_access: NominalFrequencyAccess,
) -> str | None:
    """The actionable sentence for the first stale input, or None. For consumers that REPORT a refusal (readiness, reason codes)."""
    found = first_stale_input(inputs, workspace_id=workspace_id, calc_registry=calc_registry, frequency_access=frequency_access)
    return None if found is None else stale_input_message(found[0].name, found[1], found[0].id)


@dataclass(frozen=True, slots=True)
class StaleInputBlocked:
    """Sentinel an analysis candidate-fetcher returns for a stale calculated input (cf. the calibration-blocked sentinel): the caller
    turns it into its own result with `REASON_STALE_CALCULATED_INPUT` and this actionable message."""

    message: str


def stale_input_block(
    ref: ChannelRef, *, workspace_id: str, calc_registry: CalculatedChannelRegistry, frequency_access: NominalFrequencyAccess,
) -> StaleInputBlocked | None:
    problem = stale_input_problem([ref], workspace_id=workspace_id, calc_registry=calc_registry, frequency_access=frequency_access)
    return None if problem is None else StaleInputBlocked(problem)


def assert_inputs_not_stale(
    inputs: Iterable[ChannelRef], *, workspace_id: str, calc_registry: CalculatedChannelRegistry, frequency_access: NominalFrequencyAccess,
) -> None:
    """Option B: refuse a NEW calculation whose input (direct or transitive) is stale. Raw source inputs are never stale."""
    found = first_stale_input(inputs, workspace_id=workspace_id, calc_registry=calc_registry, frequency_access=frequency_access)
    if found is not None:
        channel, staleness = found
        raise StaleCalculatedInputError(stale_input_message(channel.name, staleness, channel.id))
