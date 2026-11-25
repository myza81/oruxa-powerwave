"""NF-1: additive API contract for a recording's nominal frequency."""

from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, StrictFloat, StrictInt

from app.domain.nominal_frequency import EffectiveNominalFrequency


class NominalFrequencyOut(BaseModel):
    """What the recording's nominal frequency is, why, and what Auto would give.

    `imported_hz` is the value the recording was imported with, never changed; it is null when the recording carried
    none or the value is not a finite number, and `imported_text` always shows it exactly (for example `nan`, `inf`,
    `0.0`) so an unusable declared value stays visible. `effective_hz` is null only when `usable` is false.
    """

    source_id: str
    mode: Literal["auto", "manual"]
    effective_hz: float | None
    usable: bool
    #: recording_metadata | import_supplied | assumed_default | manual | unusable
    origin: str
    imported_hz: float | None
    imported_text: str | None
    auto_hz: float | None
    auto_origin: str
    manual_hz: float | None
    #: Moves forward whenever the stored manual state of this recording changes.
    revision: int
    #: NF-3B: whether the server-side release gate allows a Manual value (False by default; always False in a deployed build).
    #: When False a `PUT mode=manual` is refused with 409 and every field above is the Auto resolution.
    manual_override_enabled: bool = False

    @classmethod
    def from_domain(
        cls, source_id: str, r: EffectiveNominalFrequency, manual_override_enabled: bool = False,
    ) -> "NominalFrequencyOut":
        finite = r.imported_hz is not None and math.isfinite(r.imported_hz)
        return cls(
            source_id=source_id, mode=r.mode, effective_hz=r.effective_hz, usable=r.usable, origin=r.origin,
            imported_hz=r.imported_hz if finite else None,
            imported_text=None if r.imported_hz is None else repr(r.imported_hz),
            auto_hz=r.auto_hz, auto_origin=r.auto_origin, manual_hz=r.manual_hz, revision=r.revision,
            manual_override_enabled=manual_override_enabled,
        )


class NominalFrequencyUpdateRequest(BaseModel):
    """`{"mode": "manual", "value_hz": 60}` stores an engineer's value; `{"mode": "auto"}` returns to Auto.

    A value that is not a finite number from 1 to 1000 Hz is refused with `invalid_nominal_frequency`.
    """

    model_config = ConfigDict(extra="forbid")

    mode: Literal["auto", "manual"]
    value_hz: StrictInt | StrictFloat | None = None
