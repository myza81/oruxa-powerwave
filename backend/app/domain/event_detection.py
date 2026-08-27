"""Slice 3 of waveform time synchronization: assisted event-origin
detection ("Detect Event Origin").

**Advisory only (task section 1's own governing principle: "an
assistant, not an automatic decision-maker")** -- this module only ever
answers "where does this ONE engineer-selected analog channel show a
sustained, statistically meaningful disturbance onset, if any?" It never
writes `t0`, never touches a source's own alignment offset, and never
mutates source data; the caller (app.services.synchronization_service)
returns a plain candidate for the frontend to preview, and `t0` is only
ever set through Slice 2's own existing, unmodified `set_t0()` service
function, on separate explicit engineer acceptance.

Deliberately does NOT threshold instantaneous AC waveform samples (task
section 3's own explicit anti-pattern: "if voltage_sample < threshold" on
a raw sinusoid crosses zero every cycle and is meaningless). Instead this
reuses `app.domain.calculated_channel.evaluate_rms()` verbatim -- the
SAME trailing one-cycle true-RMS engine DEC-048's RMS calculated channel
already uses, already proven correct for both uniformly-sampled AND
genuinely irregular/multi-rate `time` arrays (see that function's own
docstring) -- so this module needs no separate multi-rate special-casing;
the underlying disturbance indicator is already sampling-rate-independent
by construction, per task section 19/20.

Algorithm, adapted (concepts only, not code -- task section 4's own
"do not copy desktop code blindly, use its engineering concepts where
appropriate") from the existing desktop `powerwave` reference
(`app/analytics/events/event_detector.py`): establish a pre-event RMS
baseline from the leading portion of the record, compare every later RMS
sample against it as a RATIO (never an absolute/hard-coded threshold --
task section 21: "prefer change magnitude relative to baseline"), and
require the ratio to stay past a sensitivity-selected trigger band for a
minimum SUSTAINED duration (task section 9) before accepting it as a
candidate -- a single noisy sample can never trigger a candidate by
itself. `powerwave`'s OTHER detector
(`app/sessions/alignment_engine.detect_trigger_time`) was deliberately
NOT used as a reference: it thresholds raw instantaneous samples against
a baseline RMS, exactly the anti-pattern task section 3 forbids.

Zero framework dependencies, matching every other app.domain module's own
convention.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.domain.calculated_channel import (
    MIN_SAMPLES_PER_CYCLE,
    evaluate_rms,
    nominal_frequency_valid,
    rms_recording_long_enough,
    rms_sampling_dense_enough,
)

SENSITIVITY_CONSERVATIVE = "conservative"
SENSITIVITY_NORMAL = "normal"
SENSITIVITY_SENSITIVE = "sensitive"

#: Task section 8: three plain tiers, never raw tunable parameters
#: (sigma/window_samples/derivative_threshold) exposed to the engineer.
VALID_SENSITIVITIES = frozenset({SENSITIVITY_CONSERVATIVE, SENSITIVITY_NORMAL, SENSITIVITY_SENSITIVE})

DIRECTION_INCREASE = "increase"
DIRECTION_DECREASE = "decrease"

QUALITY_STRONG = "strong"
QUALITY_MODERATE = "moderate"
QUALITY_WEAK = "weak"

DETECTOR_METHOD_RMS_SUSTAINED_CHANGE = "rms_sustained_change"

#: Same "at least a few cycles before any indicator is meaningful"
#: precedent as app.domain.rms_detector.MIN_CYCLES_FOR_DETECTION -- a
#: baseline built from less than this is not trustworthy.
MIN_BASELINE_CYCLES = 3.0
#: Task section 24 (documented rule, not the frontend's current
#: viewport): the pre-event baseline -- and, symmetrically, this fraction
#: of the record used to build it when no explicit search range narrows
#: things further -- defaults to the record's own leading portion, the
#: SAME "first ~25%" fallback rule `powerwave`'s own event_detector.py
#: already uses when no trigger hint is available. Only ever a LOWER
#: bound is raised by MIN_BASELINE_CYCLES above, never lowered by it.
BASELINE_FRACTION = 0.25

#: (low_ratio, high_ratio, persistence_cycles) per sensitivity tier.
#: `powerwave`'s own event_detector.py DIP/SWELL thresholds (0.90/1.10,
#: 0.5-cycle minimum duration) are reused verbatim as this module's own
#: "normal" tier -- a validated existing choice, not a fresh guess;
#: conservative/sensitive scale outward/inward from it. Persistence is
#: intentionally MORE than one full RMS window (1.0 cycle) in every tier
#: except "sensitive": evaluate_rms() is already a trailing ONE-CYCLE
#: window, so a genuine single-sample spike only elevates the RMS for at
#: most one cycle as the window slides past it (task section 9/33: "avoid
#: triggering from one noisy sample" / "single-sample spike must not be
#: interpreted as sustained") -- requiring MORE than one cycle of
#: persistence structurally rejects it in the two stricter tiers.
_SENSITIVITY_PARAMS: dict[str, tuple[float, float, float]] = {
    SENSITIVITY_CONSERVATIVE: (0.80, 1.20, 2.0),
    SENSITIVITY_NORMAL: (0.90, 1.10, 1.5),
    SENSITIVITY_SENSITIVE: (0.95, 1.05, 1.0),
}

#: Merge two candidate segments separated by a gap no larger than this
#: many cycles -- a momentary dip back under threshold mid-disturbance
#: (e.g. one noisy RMS sample) must not fragment one real event into
#: several too-short segments that each individually fail the
#: persistence requirement. Deliberately smaller than any tier's own
#: persistence requirement above.
_MERGE_GAP_CYCLES = 0.5

#: Quality buckets are FIXED and sensitivity-independent (task section
#: 11: "Strong/Moderate/Weak" must mean the same real-world thing
#: regardless of which sensitivity tier triggered the candidate) --
#: keyed on the sustained segment's own peak |ratio - 1.0|, never on how
#: close the ratio came to whichever threshold happened to trigger it.
_QUALITY_STRONG_DELTA = 0.5
_QUALITY_MODERATE_DELTA = 0.2

#: A baseline RMS this close to zero cannot support a meaningful RATIO
#: (division would blow up on essentially any later noise) -- treated as
#: "no usable baseline," never a divide-by-near-zero candidate.
_MIN_BASELINE_RMS = 1e-9


@dataclass(slots=True)
class EventDetectionResult:
    """One channel's assisted event-origin analysis (task section 10).

    `found=False` is a first-class, expected outcome (task section 28:
    "must be allowed to return... not an arbitrary candidate") -- every
    field below `found`/`reason`/`detector_method` is `None` in that
    case. Never a fabricated numeric confidence (task section 11) --
    `quality` is always one of QUALITY_STRONG/MODERATE/WEAK, a
    qualitative engineering indicator, never a percentage.
    """

    found: bool
    reason: str
    detector_method: str
    candidate_index: int | None = None
    candidate_source_time: float | None = None
    baseline_rms: float | None = None
    changed_rms: float | None = None
    change_ratio: float | None = None
    direction: str | None = None
    quality: str | None = None


def _find_segments(mask: np.ndarray, time: np.ndarray, *, min_duration_s: float, merge_gap_s: float) -> list[tuple[int, int]]:
    """Contiguous `True` runs in `mask`, gap-merged then duration-filtered
    (concept adapted from `powerwave`'s own `event_detector._find_segments`,
    task section 4/9) -- but filtered by actual ELAPSED TIME
    (`time[end] - time[start]`), never a raw sample count, so this stays
    correct for a genuinely non-uniformly-sampled `time` array (task
    section 7/19's own "time-based, not fixed-N" requirement, matching
    `evaluate_rms()`'s own convention). Returns `(start_index,
    end_index)` pairs (both inclusive), earliest first.
    """
    if not np.any(mask):
        return []
    padded = np.concatenate(([False], mask, [False]))
    edges = np.diff(padded.astype(np.int8))
    starts = np.flatnonzero(edges == 1)
    ends = np.flatnonzero(edges == -1) - 1  # inclusive end index

    merged: list[list[int]] = [[int(starts[0]), int(ends[0])]]
    for s, e in zip(starts[1:], ends[1:]):
        gap_s = float(time[s] - time[merged[-1][1]])
        if gap_s <= merge_gap_s:
            merged[-1][1] = int(e)
        else:
            merged.append([int(s), int(e)])

    return [
        (s, e) for s, e in merged
        if float(time[e] - time[s]) >= min_duration_s
    ]


def detect_event_onset(
    time: np.ndarray,
    values: np.ndarray,
    *,
    nominal_frequency_hz: float,
    sensitivity: str = SENSITIVITY_NORMAL,
) -> EventDetectionResult:
    """Detect a sustained RMS change (task's own "disturbance onset") in
    one analog channel's full-resolution `(time, values)` pair.

    Pipeline (task section 6):
    `derive RMS indicator -> establish pre-event baseline -> measure
    deviation as a RATIO -> require it sustained for
    sensitivity-selected persistence -> report the FIRST such onset, or
    "no clear event"`.

    `time`/`values` are the caller's own already-selected slice -- this
    function has no concept of "viewport" or "whole record," matching
    `resolve_peak_value()`'s own established shape (the caller decides
    what range to pass in). Never mutates its inputs.

    Returns `found=False` (never raises) for every documented edge case
    (task section 29): too few samples, non-finite/constant signal,
    non-monotonic time, insufficient pre-event baseline, no sustained
    change -- `reason` always explains which one, in plain engineering
    language, never a stack trace or an internal exception.
    """
    if sensitivity not in VALID_SENSITIVITIES:
        sensitivity = SENSITIVITY_NORMAL  # caller (service layer) validates and rejects before this is ever reached

    if time.shape[0] == 0 or values.shape[0] == 0:
        return EventDetectionResult(found=False, reason="No samples available to analyse.", detector_method=DETECTOR_METHOD_RMS_SUSTAINED_CHANGE)
    if time.shape[0] != values.shape[0]:
        return EventDetectionResult(found=False, reason="Time and value arrays do not match.", detector_method=DETECTOR_METHOD_RMS_SUSTAINED_CHANGE)
    if not nominal_frequency_valid(nominal_frequency_hz):
        return EventDetectionResult(found=False, reason="No usable nominal frequency is available for this source.", detector_method=DETECTOR_METHOD_RMS_SUSTAINED_CHANGE)

    # Task section 29: "non-monotonic time array" -- COMTRADE's own
    # per-row timestamps are non-decreasing by provider construction
    # (duplicated timestamps at a multi-rate section boundary are
    # therefore fine -- `>=`, not `>`), but this is defended explicitly
    # rather than trusted blindly, since a corrupted/hand-edited record
    # is exactly the situation this check exists to catch safely instead
    # of producing a silently-wrong candidate.
    if time.shape[0] >= 2 and not bool(np.all(np.diff(time) >= 0)):
        return EventDetectionResult(found=False, reason="Time array is not monotonic; cannot analyse.", detector_method=DETECTOR_METHOD_RMS_SUSTAINED_CHANGE)

    if not rms_recording_long_enough(time, nominal_frequency_hz):
        return EventDetectionResult(found=False, reason="Recording is too short for RMS-based analysis.", detector_method=DETECTOR_METHOD_RMS_SUSTAINED_CHANGE)
    if not rms_sampling_dense_enough(time, nominal_frequency_hz):
        return EventDetectionResult(
            found=False,
            reason=f"Sample rate is too low for RMS-based analysis (fewer than {MIN_SAMPLES_PER_CYCLE} samples per cycle).",
            detector_method=DETECTOR_METHOD_RMS_SUSTAINED_CHANGE,
        )

    rms = evaluate_rms(time, values, nominal_frequency_hz)

    baseline_duration_s = max(MIN_BASELINE_CYCLES / nominal_frequency_hz, BASELINE_FRACTION * float(time[-1] - time[0]))
    baseline_end_time = time[0] + baseline_duration_s
    baseline_mask = np.isfinite(rms) & (time <= baseline_end_time)
    # Task section 29 ("insufficient pre-event baseline"): the SAME
    # minimum-cycles bar used above to size the baseline window is also
    # the bar for how much valid RMS it must actually contain -- a
    # record whose leading portion is mostly NaN (e.g. barely longer
    # than one RMS window) cannot support a trustworthy baseline.
    min_baseline_samples = max(2, int(round(MIN_BASELINE_CYCLES * MIN_SAMPLES_PER_CYCLE)))
    if int(np.count_nonzero(baseline_mask)) < min_baseline_samples:
        return EventDetectionResult(found=False, reason="Insufficient pre-event baseline to establish a reference RMS.", detector_method=DETECTOR_METHOD_RMS_SUSTAINED_CHANGE)

    baseline_rms = float(np.median(rms[baseline_mask]))
    if not np.isfinite(baseline_rms) or baseline_rms < _MIN_BASELINE_RMS:
        return EventDetectionResult(found=False, reason="Pre-event baseline is effectively zero; no reliable reference RMS.", detector_method=DETECTOR_METHOD_RMS_SUSTAINED_CHANGE)

    low_ratio, high_ratio, persistence_cycles = _SENSITIVITY_PARAMS[sensitivity]
    persistence_duration_s = persistence_cycles / nominal_frequency_hz
    merge_gap_s = _MERGE_GAP_CYCLES / nominal_frequency_hz

    # Search region: strictly AFTER the baseline window -- the baseline
    # itself is assumed quiet by definition and must never be able to
    # nominate itself as its own event (task section 6: "establish
    # pre-event baseline" is a distinct, earlier step from "measure
    # deviation," never the same window).
    search_mask = np.isfinite(rms) & (time > baseline_end_time)
    with np.errstate(invalid="ignore", divide="ignore"):
        ratio = rms / baseline_rms
    trigger_mask = search_mask & ((ratio <= low_ratio) | (ratio >= high_ratio))

    segments = _find_segments(trigger_mask, time, min_duration_s=persistence_duration_s, merge_gap_s=merge_gap_s)
    if not segments:
        return EventDetectionResult(found=False, reason="No clear disturbance onset detected.", detector_method=DETECTOR_METHOD_RMS_SUSTAINED_CHANGE)

    onset_index, segment_end_index = segments[0]
    segment_ratios = ratio[onset_index:segment_end_index + 1]
    # The segment's own most extreme point decides direction/quality --
    # the ONSET index (first crossing) is still what is reported as the
    # candidate time (task section 6: "identify first sustained
    # significant change" -- the moment it begins, not the moment the
    # persistence requirement is confirmed).
    peak_local_idx = int(np.argmax(np.abs(segment_ratios - 1.0)))
    peak_ratio = float(segment_ratios[peak_local_idx])
    peak_index = onset_index + peak_local_idx

    direction = DIRECTION_DECREASE if peak_ratio < 1.0 else DIRECTION_INCREASE
    delta = abs(peak_ratio - 1.0)
    if delta >= _QUALITY_STRONG_DELTA:
        quality = QUALITY_STRONG
    elif delta >= _QUALITY_MODERATE_DELTA:
        quality = QUALITY_MODERATE
    else:
        quality = QUALITY_WEAK

    reason = "Sustained RMS reduction detected." if direction == DIRECTION_DECREASE else "Sustained RMS increase detected."

    return EventDetectionResult(
        found=True,
        reason=reason,
        detector_method=DETECTOR_METHOD_RMS_SUSTAINED_CHANGE,
        candidate_index=onset_index,
        candidate_source_time=float(time[onset_index]),
        baseline_rms=baseline_rms,
        changed_rms=float(rms[peak_index]),
        change_ratio=peak_ratio,
        direction=direction,
        quality=quality,
    )
