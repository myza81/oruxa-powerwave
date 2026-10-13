"""Distance-zone interpretation rule: a 10.0 s operating delay marks a defeated zone.

Many distance relays let an engineer "defeat" a zone by setting its operating delay to
the top of the timer range. When a source states a zone's delay but no enabled/disabled
state can be established, Oruxa assumes such a zone is Disabled.

Scope (owner decision, DEC-187):

* vendor-neutral -- it reads only the canonical `DistanceZone`, never an OEM name or code;
* distance zones only -- it is not a generic relay-timer rule and is never applied to
  overcurrent, earth-fault, differential, breaker-failure, auto-reclose, voltage,
  frequency or any other protection function;
* an interpretation/readiness step, not engine maths -- the distance characteristic engine
  never sees the timer meaning, only the resulting enabled/disabled zone status.

Precedence: an established status (mapped, inferred, or set by the user) always wins; an
unresolved status with a 10.0 s delay becomes Disabled (an Assumption); any other delay
leaves the status unresolved. The zone's timer and every other extracted value are kept.
"""

from __future__ import annotations

from dataclasses import replace

from app.domain.relay_import.canonical_distance import (
    CanonicalDistanceProtectionModel,
    DistanceZone,
    ZoneStatus,
)
from app.domain.relay_import.provenance import (
    MappingStatus,
    Provenance,
    ProvenanceOrigin,
    Sourced,
)

#: The operating delay, in seconds, that marks a distance zone as defeated.
DEFEATED_ZONE_DELAY_S = 10.0

DEFEATED_ZONE_REASON = (
    "No explicit zone status was available. The 10.0 s operating delay is interpreted "
    "as a defeated/inactive distance zone."
)


def is_defeated_delay_assumption(status: Sourced) -> bool:
    """True for a zone status produced by this rule (so the review can word it)."""
    p = status.provenance
    return p.origin is ProvenanceOrigin.DEFAULT_ASSUMPTION and DEFEATED_ZONE_REASON in p.notes


def _stated_delays(zone: DistanceZone) -> tuple[Sourced, ...]:
    return tuple(t for t in (zone.common_timer_s, zone.phase_timer_s, zone.earth_timer_s) if t.is_resolved)


def infers_defeated(zone: DistanceZone) -> bool:
    """The zone's status is unresolved and every operating delay it states is exactly 10.0 s."""
    if zone.status.is_resolved:
        return False
    delays = _stated_delays(zone)
    return bool(delays) and all(
        isinstance(d.value, (int, float)) and not isinstance(d.value, bool) and d.value == DEFEATED_ZONE_DELAY_S
        for d in delays
    )


def _defeated_status(zone: DistanceZone) -> Sourced:
    delays = _stated_delays(zone)
    sources = tuple(ref for d in delays for ref in d.provenance.sources)
    carried = delays[0].provenance
    return Sourced(
        ZoneStatus.DISABLED,
        Provenance(
            MappingStatus.INFERRED,  # an Assumption, never Mapped
            sources=sources,
            profile_id=carried.profile_id,
            profile_version=carried.profile_version,
            raw_value=carried.raw_value,
            notes=(DEFEATED_ZONE_REASON,),
            origin=ProvenanceOrigin.DEFAULT_ASSUMPTION,
        ),
    )


def infer_defeated_zones(model: CanonicalDistanceProtectionModel) -> CanonicalDistanceProtectionModel:
    """A copy of ``model`` in which every zone with an unresolved status and a 10.0 s delay
    is Disabled (Assumption). Nothing else changes; a model with no such zone is returned as is."""
    if not any(infers_defeated(z) for z in model.zones):
        return model
    zones = tuple(replace(z, status=_defeated_status(z)) if infers_defeated(z) else z for z in model.zones)
    return replace(model, zones=zones)
