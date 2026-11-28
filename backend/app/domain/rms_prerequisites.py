"""Shared RMS prerequisites and input-form classification (RMS display R0).

Two pieces of *composition* that used to live inline in
`app.services.calculated_channel_service` and that every RMS consumer must
apply identically:

1. `check_rms_window_prerequisites` -- the two data-quality gates that decide
   whether a one-cycle RMS can be computed meaningfully at all (recording at
   least one window long; at least `MIN_SAMPLES_PER_CYCLE` samples per cycle).
2. `classify_input_form` -- the metadata-first classification of whether an
   input is an instantaneous waveform or already an RMS/magnitude signal:
   a *declared* `waveform_form` wins and the detector is not consulted;
   otherwise `app.domain.rms_detector.classify_waveform_form` decides.

What this module is NOT
-----------------------
* It contains no engineering mathematics. The RMS itself stays in
  `app.domain.calculated_channel.evaluate_rms` (unchanged, the single
  mathematical authority); the window and frequency predicates it applies stay
  in `app.domain.calculated_channel` and the detector stays in
  `app.domain.rms_detector`. This module only calls them, in the same order as
  before.
* It contains no policy. Whether a "not an instantaneous waveform" outcome is
  overridable (Calculated Channels: yes, with an explicit override; any other
  consumer: its own decision), the user-facing wording, the exception mapping
  and the null-policy handling belong to the caller. In particular, sharing
  this classification does NOT give any other feature an override capability.
* It does not validate the nominal frequency. `nominal_frequency_valid` is a
  separate, unchanged predicate and the callers keep their own ordering of it.

Provenance limitation (deliberately not hidden)
-----------------------------------------------
`InputFormClassification.basis` distinguishes only "a form was DECLARED" from
"the DETECTOR decided". A declared `waveform_form` may originate from
recording/importer metadata or from a calculated channel's own derivation
(`app.domain.channel_classification.derive_waveform_form`); the string alone
cannot tell which, so this interface does not claim to. A caller that needs
that distinction must carry it separately.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import numpy as np

from app.domain.calculated_channel import rms_recording_long_enough, rms_sampling_dense_enough
from app.domain.channel_classification import (
    WAVEFORM_FORM_INSTANTANEOUS,
    WAVEFORM_FORM_MAGNITUDE,
    WAVEFORM_FORM_RMS,
)
from app.domain.rms_detector import (
    LIKELY_INSTANTANEOUS,
    LIKELY_MAGNITUDE_OR_RMS,
    classify_waveform_form,
)


class RmsPrerequisiteFailure(StrEnum):
    """Which window prerequisite failed. The first failing one is reported, in this order."""

    RECORDING_TOO_SHORT = "recording_too_short"
    SAMPLING_TOO_SPARSE = "sampling_too_sparse"


def check_rms_window_prerequisites(time: np.ndarray, nominal_frequency_hz: float) -> RmsPrerequisiteFailure | None:
    """`None` when a one-cycle RMS can be computed meaningfully for `time` at `nominal_frequency_hz`, else the
    FIRST failing prerequisite: recording shorter than one window, then sampling too sparse. Same two
    predicates in the same order as before the extraction; the second is not evaluated when the first fails.

    `nominal_frequency_hz` is assumed already validated by the caller (`nominal_frequency_valid`)."""
    if not rms_recording_long_enough(time, nominal_frequency_hz):
        return RmsPrerequisiteFailure.RECORDING_TOO_SHORT
    if not rms_sampling_dense_enough(time, nominal_frequency_hz):
        return RmsPrerequisiteFailure.SAMPLING_TOO_SPARSE
    return None


class InputForm(StrEnum):
    """The classification OUTCOME: what the input is to be treated as for RMS purposes."""

    INSTANTANEOUS = "instantaneous"
    RMS_OR_MAGNITUDE = "rms_or_magnitude"
    UNCERTAIN = "uncertain"


class FormBasis(StrEnum):
    """What decided the outcome (see the module's provenance limitation)."""

    DECLARED_WAVEFORM_FORM = "declared_waveform_form"
    DETECTOR = "detector"


@dataclass(frozen=True, slots=True)
class InputFormClassification:
    outcome: InputForm
    basis: FormBasis
    #: The `waveform_form` string the caller supplied, verbatim.
    declared_waveform_form: str
    #: The raw detector result; `None` whenever a declared form decided and the detector was not run.
    detector_result: str | None


def classify_input_form(
    declared_waveform_form: str, time: np.ndarray, values: np.ndarray, nominal_frequency_hz: float
) -> InputFormClassification:
    """Metadata first, detector second.

    * declared `rms` or `magnitude`  -> `RMS_OR_MAGNITUDE` (detector NOT run);
    * declared `instantaneous`       -> `INSTANTANEOUS`    (detector NOT run);
    * anything else (`unknown`)      -> `classify_waveform_form(time, values, nominal_frequency_hz)`:
      `LIKELY_INSTANTANEOUS` -> `INSTANTANEOUS`, `LIKELY_MAGNITUDE_OR_RMS` -> `RMS_OR_MAGNITUDE`,
      otherwise `UNCERTAIN`.

    A detector result is never promoted to a declared form: the returned `basis` says which one decided."""
    if declared_waveform_form in (WAVEFORM_FORM_RMS, WAVEFORM_FORM_MAGNITUDE):
        return InputFormClassification(
            InputForm.RMS_OR_MAGNITUDE, FormBasis.DECLARED_WAVEFORM_FORM, declared_waveform_form, None
        )
    if declared_waveform_form == WAVEFORM_FORM_INSTANTANEOUS:
        return InputFormClassification(
            InputForm.INSTANTANEOUS, FormBasis.DECLARED_WAVEFORM_FORM, declared_waveform_form, None
        )
    detector_result = classify_waveform_form(time, values, nominal_frequency_hz)
    if detector_result == LIKELY_INSTANTANEOUS:
        outcome = InputForm.INSTANTANEOUS
    elif detector_result == LIKELY_MAGNITUDE_OR_RMS:
        outcome = InputForm.RMS_OR_MAGNITUDE
    else:
        outcome = InputForm.UNCERTAIN
    return InputFormClassification(outcome, FormBasis.DETECTOR, declared_waveform_form, detector_result)
