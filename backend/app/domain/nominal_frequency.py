"""NF-1: the ONE resolver of a recording's effective nominal frequency (pure domain, no I/O).

A recording has exactly one nominal frequency, shared by every channel, Measurement Group and bay in it. It is decided
here from three inputs and nothing else:

* the IMPORTED value (`SourceMetadata.nominal_frequency`), which is never modified;
* the import PROVENANCE (`SourceMetadata.preparation_provenance`), which says whether the importer had to assume the
  default (`nominal_frequency_assumed`: True) or took the value from the upload (BEN);
* an optional MANUAL value an engineer entered for this recording.

Resolution:

* **Manual** (a valid value was stored): the effective frequency is the manual value. Returning to Auto removes it.
* **Auto**: recomputed on every read, never stored, so "return to Auto" restores the automatic value by construction:
    - an imported value that is missing (`None`) or flagged assumed -> the 50 Hz default, origin `assumed_default`;
    - an imported value that passes the validity predicate -> that value; origin `recording_metadata` (declared by the
      file) or `import_supplied` (BEN: the format declares none, the uploader supplied it);
    - an imported value that was DECLARED but fails the predicate (0, negative, NaN, +-inf, outside 1-1000 Hz) ->
      preserved as imported, **no usable frequency** (`unusable`): a frequency-dependent calculation must refuse it and
      the engineer can correct it manually. Native waveform viewing never depends on it.

The validity predicate is the existing `nominal_frequency_valid` (1-1000 Hz, finite, not a bool). Individual algorithms
keep their own additional prerequisites. This module reads no registry and changes no sample.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from app.domain.calculated_channel import nominal_frequency_valid
from app.domain.metadata import DEFAULT_NOMINAL_FREQUENCY_HZ

MODE_AUTO = "auto"
MODE_MANUAL = "manual"

#: Declared by the recording file (COMTRADE `lf`).
ORIGIN_RECORDING_METADATA = "recording_metadata"
#: Taken from the upload, because the format declares none (BEN). Part of the automatic baseline.
ORIGIN_IMPORT_SUPPLIED = "import_supplied"
#: The importer (or this resolver, for a missing value) had to use the 50 Hz default.
ORIGIN_ASSUMED_DEFAULT = "assumed_default"
#: An engineer's value for this recording.
ORIGIN_MANUAL = "manual"
#: Declared but not a usable frequency; no effective value.
ORIGIN_UNUSABLE = "unusable"

_BEN_SOURCE_FORMAT = "BEN"

#: The agreement tolerance the phasor family already applies to recordings declaring "the same" frequency
#: (`phasor_analysis_service`, `math.isclose(f, first, rel_tol=1e-9, abs_tol=1e-9)`). Reused, not invented.
AGREEMENT_REL_TOL = 1e-9
AGREEMENT_ABS_TOL = 1e-9


def frequencies_agree(values: Iterable[float]) -> bool:
    """The ONE multi-recording agreement rule (NF-3B N-5): every value is the smallest one within the tolerance. Order-independent.
    The central accessor (`NominalFrequencyAccess.for_sources`) and the oscillation cross-signal classifier (NF-3G) both apply exactly this."""
    values = list(values)
    low = min(values)
    return all(math.isclose(v, low, rel_tol=AGREEMENT_REL_TOL, abs_tol=AGREEMENT_ABS_TOL) for v in values)


def agreed_frequency(values: Iterable[float]) -> float | None:
    """The common frequency of values that agree (the smallest of them, so the answer cannot depend on order), else None. Never a
    representative chosen from values that disagree."""
    values = list(values)
    return min(values) if values and frequencies_agree(values) else None


@dataclass(frozen=True, slots=True)
class EffectiveNominalFrequency:
    """The decision, with everything that led to it. `effective_hz` is None only when no usable frequency exists."""

    effective_hz: float | None
    origin: str
    mode: str
    #: The importer's value, exactly as imported (None only when the recording carried no value at all).
    imported_hz: float | None
    #: What Auto resolves to now (None when the imported value is unusable) and why.
    auto_hz: float | None
    auto_origin: str
    #: The engineer's value when mode == "manual".
    manual_hz: float | None
    #: Incremented whenever the stored manual state changes; for cache keys and "computed at" provenance.
    revision: int

    @property
    def usable(self) -> bool:
        return self.effective_hz is not None


def valid_nominal_frequency(value: Any) -> bool:
    """The one recording-level validity predicate (the existing 1-1000 Hz definition)."""
    return nominal_frequency_valid(value)


def resolve_auto(imported_hz: Any, provenance: Mapping[str, Any] | None) -> tuple[float | None, str]:
    """(auto_hz, auto_origin) from the immutable imported value and the import provenance. Pure."""
    provenance = provenance or {}
    if imported_hz is None or provenance.get("nominal_frequency_assumed"):
        # No value at all, or the importer substituted the default: the default is the automatic value.
        return DEFAULT_NOMINAL_FREQUENCY_HZ, ORIGIN_ASSUMED_DEFAULT
    if not valid_nominal_frequency(imported_hz):
        return None, ORIGIN_UNUSABLE
    origin = ORIGIN_IMPORT_SUPPLIED if provenance.get("source_format") == _BEN_SOURCE_FORMAT else ORIGIN_RECORDING_METADATA
    return float(imported_hz), origin


def resolve_nominal_frequency(
    imported_hz: Any,
    provenance: Mapping[str, Any] | None,
    manual_hz: float | None = None,
    revision: int = 0,
) -> EffectiveNominalFrequency:
    """Combine the immutable imported value, its provenance and an optional manual value. A stored manual value that
    is not valid (it cannot be, when stored through the service) is ignored rather than trusted."""
    auto_hz, auto_origin = resolve_auto(imported_hz, provenance)
    # Preserved exactly as imported, including NaN/inf/0 (the API layer is responsible for serialising them safely).
    imported = float(imported_hz) if isinstance(imported_hz, (int, float)) and not isinstance(imported_hz, bool) else None
    if manual_hz is not None and valid_nominal_frequency(manual_hz):
        return EffectiveNominalFrequency(
            effective_hz=float(manual_hz), origin=ORIGIN_MANUAL, mode=MODE_MANUAL, imported_hz=imported,
            auto_hz=auto_hz, auto_origin=auto_origin, manual_hz=float(manual_hz), revision=revision,
        )
    return EffectiveNominalFrequency(
        effective_hz=auto_hz, origin=auto_origin, mode=MODE_AUTO, imported_hz=imported,
        auto_hz=auto_hz, auto_origin=auto_origin, manual_hz=None, revision=revision,
    )
