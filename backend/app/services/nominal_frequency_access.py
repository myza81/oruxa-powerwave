"""NF-3B: the controlled access point to a recording's effective nominal frequency (NF-001 / DEC-217).

This is the ONLY way an engineering consumer is allowed to ask "what nominal frequency does this recording have?". It resolves
through the NF-1 authority (`app.services.nominal_frequency_service`) with the release gate applied, and returns a typed
outcome that says whether a usable frequency exists, where it came from and which revision of the engineer's setting it
reflects. It never reads a Manual value while the gate is closed, never substitutes a default for an unusable declared value
(the 50 Hz default exists in exactly one place, the NF-1 resolver, and only for a MISSING or importer-ASSUMED value), and never
modifies a recording, its metadata or its provenance.

STATUS: foundation only. In NF-3B no engineering consumer calls this module; the consumers are migrated slice by slice
(NF-3C onward) and `test_nf3b_frequency_call_path_guard.py` freezes both that and the rule that, once migrated, none of them
may read the imported value directly or hard-code a fundamental frequency.

Contract for a single recording (`for_source`, `for_channel_ref`)
-----------------------------------------------------------------
`SourceFrequency.usable` is True exactly when `hz` is a float that passes the recording-level validity predicate (1-1000 Hz,
finite). When it is False `hz` is None and the consumer MUST refuse with its own typed reason; it must not pick a number.
`origin` is one of the NF-1 origins (`recording_metadata`, `import_supplied`, `assumed_default`, `manual`, `unusable`);
`assumed` is True for `assumed_default`; `revision` moves whenever the engineer's setting for the recording changes (cache keys,
"computed at" provenance). `imported_hz` is the value the recording was imported with, exactly as imported.

A calculated channel has no frequency of its own: it inherits that of the recording that grounds its time base
(`reference_source_id`), exactly as it inherits its sample times. `for_channel_ref` applies that rule.

Contract for several recordings (`for_sources`)
-----------------------------------------------
A calculation that combines recordings never takes "the first recording's" frequency. `MultiSourceFrequency.status` is:

* `empty`        no recording was asked about;
* `unavailable`  at least one recording has no usable frequency (`unusable_source_ids` lists them);
* `agreed`       every recording is usable and they agree within the tolerance the phasor family already uses
                 (`math.isclose`, rel 1e-9, abs 1e-9); `common_hz` is then set (the smallest of the agreeing values, so the
                 result never depends on the order the recordings were listed in);
* `mixed`        every recording is usable but they differ; `common_hz` is None and `distinct_hz` lists the values. The consumer
                 either needs an explicit, engineer-supplied override or reports limiting evidence; it never chooses one.

Lifecycle and isolation: the answer is keyed by `(workspace_id, source_id)`. A recording that was removed, a workspace that was
reset, or a recording that belongs to another workspace is "not found" (`SourceNotFoundError`), never a fallback value.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from app.domain.calculated_channel import ChannelRef
from app.domain.nominal_frequency import (
    ORIGIN_ASSUMED_DEFAULT,
    ORIGIN_MANUAL,
    EffectiveNominalFrequency,
)
from app.services import nominal_frequency_service as _authority
from app.services.calculated_channel_registry import CalculatedChannelRegistry
from app.services.errors import CalculatedChannelNotFoundError, SourceNotFoundError
from app.services.nominal_frequency_registry import NominalFrequencyRegistry
from app.services.workspace_registry import WorkspaceRegistry

STATUS_USABLE = "usable"
STATUS_UNUSABLE = "unusable"

AGREEMENT_EMPTY = "empty"
AGREEMENT_UNAVAILABLE = "unavailable"
AGREEMENT_AGREED = "agreed"
AGREEMENT_MIXED = "mixed"

#: The agreement tolerance the phasor family already applies to recordings declaring "the same" frequency
#: (`phasor_analysis_service`, `math.isclose(f, first, rel_tol=1e-9, abs_tol=1e-9)`). Reused, not invented.
AGREEMENT_REL_TOL = 1e-9
AGREEMENT_ABS_TOL = 1e-9


@dataclass(frozen=True, slots=True)
class SourceFrequency:
    """What one recording's nominal frequency is for an engineering consumer, and why."""

    source_id: str
    #: The effective frequency, or None when no usable frequency exists (then `usable` is False and the consumer must refuse).
    hz: float | None
    origin: str
    mode: str
    revision: int
    #: The value the recording was imported with, exactly as imported (may be 0, negative, NaN, infinite or None).
    imported_hz: float | None
    #: Whether the release gate was open when this was resolved (False: a stored Manual value, if any, was ignored).
    manual_override_enabled: bool

    @property
    def usable(self) -> bool:
        return self.hz is not None

    @property
    def status(self) -> str:
        return STATUS_USABLE if self.usable else STATUS_UNUSABLE

    @property
    def assumed(self) -> bool:
        """True when the frequency is the 50 Hz default (the recording declared none, or the importer substituted it)."""
        return self.origin == ORIGIN_ASSUMED_DEFAULT

    @property
    def manual(self) -> bool:
        return self.origin == ORIGIN_MANUAL


@dataclass(frozen=True, slots=True)
class MultiSourceFrequency:
    """The frequency of a calculation that combines several recordings. Never a representative chosen from them."""

    members: tuple[SourceFrequency, ...]
    status: str
    #: Set only when `status == "agreed"`.
    common_hz: float | None
    #: The distinct usable values (sorted), whatever the status.
    distinct_hz: tuple[float, ...]
    unusable_source_ids: tuple[str, ...]

    @property
    def any_assumed(self) -> bool:
        return any(m.assumed for m in self.members)

    @property
    def any_manual(self) -> bool:
        return any(m.manual for m in self.members)

    @property
    def revisions(self) -> tuple[tuple[str, int], ...]:
        return tuple((m.source_id, m.revision) for m in self.members)


def _source_frequency(source_id: str, r: EffectiveNominalFrequency, manual_override_enabled: bool) -> SourceFrequency:
    return SourceFrequency(
        source_id=source_id, hz=r.effective_hz, origin=r.origin, mode=r.mode, revision=r.revision,
        imported_hz=r.imported_hz, manual_override_enabled=manual_override_enabled,
    )


def _agree(values: list[float]) -> bool:
    low = min(values)
    return all(math.isclose(v, low, rel_tol=AGREEMENT_REL_TOL, abs_tol=AGREEMENT_ABS_TOL) for v in values)


def combine(members: Iterable[SourceFrequency]) -> MultiSourceFrequency:
    """Apply the multi-recording contract to already-resolved members (pure; order-independent apart from `members` itself)."""
    members = tuple(members)
    unusable = tuple(m.source_id for m in members if not m.usable)
    usable = [m.hz for m in members if m.hz is not None]
    distinct = tuple(sorted(set(usable)))
    if not members:
        return MultiSourceFrequency(members, AGREEMENT_EMPTY, None, (), ())
    if unusable:
        return MultiSourceFrequency(members, AGREEMENT_UNAVAILABLE, None, distinct, unusable)
    if _agree(usable):
        return MultiSourceFrequency(members, AGREEMENT_AGREED, min(usable), distinct, ())
    return MultiSourceFrequency(members, AGREEMENT_MIXED, None, distinct, ())


class NominalFrequencyAccess:
    """The release-gated accessor, bound to the process's registries and policy at application start."""

    def __init__(
        self, source_registry: WorkspaceRegistry, registry: NominalFrequencyRegistry, *, manual_override_enabled: bool,
    ) -> None:
        self._sources = source_registry
        self._registry = registry
        self._enabled = bool(manual_override_enabled)

    @property
    def manual_override_enabled(self) -> bool:
        return self._enabled

    # ---- reading ----
    def effective(self, workspace_id: str, source_id: str) -> EffectiveNominalFrequency:
        """The full NF-1 resolution with the gate applied (what the NF-1 endpoint reports). Raises `SourceNotFoundError`."""
        return _authority.effective_nominal_frequency(
            workspace_id, source_id, source_registry=self._sources, registry=self._registry,
            manual_override_enabled=self._enabled)

    def for_source(self, workspace_id: str, source_id: str) -> SourceFrequency:
        """The typed outcome for one recording. Raises `SourceNotFoundError` for an unknown recording or workspace."""
        return _source_frequency(source_id, self.effective(workspace_id, source_id), self._enabled)

    def for_channel_ref(
        self, workspace_id: str, ref: ChannelRef, *, calc_registry: CalculatedChannelRegistry,
    ) -> SourceFrequency:
        """The frequency of the recording that grounds a channel: the source itself, or a calculated channel's
        `reference_source_id`. Raises `SourceNotFoundError` / `CalculatedChannelNotFoundError`."""
        if ref.kind == "source":
            return self.for_source(workspace_id, ref.source_id)
        channel = calc_registry.get(workspace_id, ref.calculated_channel_id)
        if channel is None:
            raise CalculatedChannelNotFoundError(
                f"Calculated channel {ref.calculated_channel_id!r} was not found in workspace {workspace_id!r}.")
        return self.for_source(workspace_id, channel.reference_source_id)

    def for_sources(self, workspace_id: str, source_ids: Iterable[str]) -> MultiSourceFrequency:
        """The combined outcome for several recordings of one workspace (duplicates collapse, order of first mention kept)."""
        unique = list(dict.fromkeys(source_ids))
        return combine(self.for_source(workspace_id, sid) for sid in unique)

    # ---- writing (policy-enforced at the service layer) ----
    def set_manual(
        self, workspace_id: str, source_id: str, value_hz: float, *, now: datetime | None = None,
    ) -> EffectiveNominalFrequency:
        """Store an engineer's value. Raises `ManualNominalFrequencyDisabledError` while the gate is closed,
        `InvalidNominalFrequencyError` for a value outside the recording-level range."""
        return _authority.set_manual_nominal_frequency(
            workspace_id, source_id, value_hz, source_registry=self._sources, registry=self._registry,
            manual_override_enabled=self._enabled, now=now)

    def reset_to_auto(self, workspace_id: str, source_id: str) -> EffectiveNominalFrequency:
        return _authority.reset_nominal_frequency_to_auto(
            workspace_id, source_id, source_registry=self._sources, registry=self._registry,
            manual_override_enabled=self._enabled)


__all__ = [
    "AGREEMENT_AGREED", "AGREEMENT_EMPTY", "AGREEMENT_MIXED", "AGREEMENT_UNAVAILABLE", "MultiSourceFrequency",
    "NominalFrequencyAccess", "SourceFrequency", "SourceNotFoundError", "STATUS_UNUSABLE", "STATUS_USABLE", "combine",
]
