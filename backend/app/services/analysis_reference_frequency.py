"""NF-3D: the ONE place the phasor family and overcurrent decide which reference frequency an analysis uses, and why it may be refused.

Before NF-3D the same block was written six times (three in the phasor service, three in the overcurrent service). Each read the recording's
IMPORTED value directly and handed it, unvalidated, to `1/f` and to the form detector, so a declared 0 Hz or infinity was an HTTP 500, a
declared NaN a "frequency conflict" or a 500, and a declared -50, 0.5 or 1001 Hz a "waveform form not eligible" that names the wrong cause.

The decision (O-5, O-6, owner 2026-11-25):

1. An explicit `reference_frequency_hz` override wins, as it always has. It must pass the recording-level validity predicate or the answer is
   `invalid_reference_frequency` with the existing sentence. A valid override carries NO provenance (it is the caller's own value).
2. Otherwise the frequency comes from the central accessor for every recording that supplied a channel. Three distinct outcomes:
   * some recording has NO usable frequency (0, negative, NaN, infinite, outside 1-1000 Hz): `invalid_reference_frequency`, with a sentence that
     names the recording's DECLARED value as unusable. That is an unusable AUTHORITY. Nothing is substituted: in particular never 50 Hz.
   * all usable but different: `reference_frequency_conflict`, as before (same tolerance, the one the phasor family already used).
   * all usable and equal: that frequency, with the provenance of the recordings that supplied it.
3. A frequency that is VALID but that the algorithm cannot support (the sampling holds too few samples per cycle) is a different condition with its
   own, already existing reason, `insufficient_sampling_density`; it is decided by `sampling_supports()` below and never reported as an invalid
   frequency or as a waveform-form problem.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable

import numpy as np

from app.domain.calculated_channel import nominal_frequency_valid
from app.domain.frequency_provenance import FrequencyProvenance, RecordingFrequencyUse, provenance_of
from app.domain.phasor import (
    PHASOR_MIN_SAMPLES_PER_CYCLE,
    REASON_INSUFFICIENT_SAMPLING_DENSITY,
    REASON_INVALID_REFERENCE_FREQUENCY,
    REASON_REFERENCE_FREQUENCY_CONFLICT,
)
from app.services.nominal_frequency_access import (
    AGREEMENT_AGREED, AGREEMENT_MIXED, AGREEMENT_UNAVAILABLE, SourceFrequency, combine,
)

#: Round-off allowance when counting samples per cycle (an exact integer such as 100.00000000000001 must not count as 101).
_SPC_TOLERANCE = 1e-9

#: The existing sentence for an invalid explicit override (unchanged).
INVALID_OVERRIDE_MESSAGE = "The supplied reference_frequency_hz is outside the plausible range."

#: Form-eligibility verdicts (replace a bare bool): the third one is what makes "valid but unsupported" distinguishable.
FORM_ELIGIBLE = "eligible"
FORM_NOT_ELIGIBLE = "not_eligible"
SAMPLING_UNSUPPORTED = "sampling_unsupported"


@dataclass(frozen=True, slots=True)
class ReferenceFrequencyDecision:
    hz: float | None
    reason_code: str | None
    message: str | None
    #: None for an explicit override and for a refusal.
    provenance: FrequencyProvenance | None

    @property
    def usable(self) -> bool:
        return self.hz is not None


def _declared_text(frequency: SourceFrequency) -> str:
    value = frequency.imported_hz
    if value is None:
        return "missing"
    if math.isnan(value):
        return "not a number"
    if math.isinf(value):
        return "infinite" if value > 0 else "negative infinity"
    return f"{value:g}"


def unusable_message(unusable: list[SourceFrequency]) -> str:
    """The sentence for an unusable AUTHORITY: it names the declared value(s), says they are not usable, and offers only remedies that exist."""
    declared = ", ".join(dict.fromkeys(_declared_text(f) for f in unusable))
    gate_open = any(f.manual_override_enabled for f in unusable)
    remedy = ("supply a valid reference_frequency_hz, or set a nominal frequency in Recording Details"
              if gate_open else "supply a valid reference_frequency_hz")
    noun = "recording declares" if len(unusable) == 1 else "recordings declare"
    return f"The {noun} a nominal frequency that is not usable ({declared}), so no reference frequency can be taken from it; {remedy}."


def decide_reference_frequency(
    *, override: float | None, frequencies: Iterable[SourceFrequency], conflict_message: str,
) -> ReferenceFrequencyDecision:
    if override is not None:
        if not nominal_frequency_valid(override):
            return ReferenceFrequencyDecision(None, REASON_INVALID_REFERENCE_FREQUENCY, INVALID_OVERRIDE_MESSAGE, None)
        return ReferenceFrequencyDecision(float(override), None, None, None)

    unique: dict[str, SourceFrequency] = {}
    for f in frequencies:
        unique.setdefault(f.source_id, f)
    combined = combine(unique.values())
    if combined.status == AGREEMENT_UNAVAILABLE:
        return ReferenceFrequencyDecision(
            None, REASON_INVALID_REFERENCE_FREQUENCY, unusable_message([m for m in combined.members if not m.usable]), None)
    if combined.status == AGREEMENT_MIXED:
        return ReferenceFrequencyDecision(None, REASON_REFERENCE_FREQUENCY_CONFLICT, conflict_message, None)
    assert combined.status == AGREEMENT_AGREED and combined.common_hz is not None          # `empty` cannot occur: callers hold >= 1 candidate
    provenance = provenance_of(RecordingFrequencyUse(m.source_id, m.origin, m.revision) for m in combined.members)
    return ReferenceFrequencyDecision(combined.common_hz, None, None, provenance)


def sampling_supports(time: np.ndarray, frequency_hz: float, min_samples_per_cycle: int = PHASOR_MIN_SAMPLES_PER_CYCLE) -> bool:
    """Can a one-cycle window at `frequency_hz` EVER hold `min_samples_per_cycle` samples of this recording?

    The estimators (`estimate_phasor`, `estimate_trailing_rms_at_time`) refuse a half-open window `(t - 1/f, t]` holding fewer than
    `PHASOR_MIN_SAMPLES_PER_CYCLE` (8) / `OVERCURRENT_MIN_SAMPLES_PER_CYCLE` (4) samples (`insufficient_sampling_density`). Such a window holds
    `floor(spc)` or `ceil(spc)` samples (`spc` = samples per cycle, not an integer in general), depending on where it sits against the sample
    grid, so a recording is only certainly unsupported when even `ceil(spc)` falls short. This is that rule, evaluated up front and never
    stricter than the estimator: a frequency whose window can reach the minimum at some analysis times goes on to the detector and the
    estimator exactly as before. No threshold is invented: the caller passes the algorithm's own constant. It is consulted only where the
    waveform-form DETECTOR would otherwise be asked to classify a signal it cannot resolve (it answers "uncertain", which used to be reported as
    a form problem). NF-1's 1-1000 Hz range is therefore never taken as proof that an algorithm supports a frequency. Fewer than two samples:
    nothing to judge, the estimators report it.
    """
    if time.shape[0] < 2:
        return True
    median_dt = float(np.median(np.diff(time)))
    if not median_dt > 0:
        return True
    return math.ceil((1.0 / frequency_hz) / median_dt - _SPC_TOLERANCE) >= min_samples_per_cycle


def sampling_reason_message(frequency_hz: float, min_samples_per_cycle: int) -> str:
    return (f"The recording's sampling holds fewer than {min_samples_per_cycle} samples per cycle at {frequency_hz:g} Hz, "
            "so it cannot be analysed at that frequency.")
