"""D5A-2B2C-1A/1B: the ONE channel-level policy every recorded consumer applies to the side of a channel it consumes.

Recording Details is the single source of truth for whether a recorded Voltage/Current channel is Primary or Secondary
(DEC-216). The shared resolver (`measurement_side_service.resolve_effective_measurement_side`) decides the side; this module
decides whether that answer may be CONSUMED by a numerical calculation, identically for Overcurrent, Impedance Locus and
Distance Protection (consistent strict-blocking policy):

  * a calculated channel has no resolved side yet (calculated-channel lineage is a later slice)  -> `calculated`;
  * a channel whose side is not defined by the recording or by Recording Details                 -> `unresolved`;
  * a channel whose side is only INFERRED from sibling channels (not strict-usable)              -> `inferred`;
  * a channel whose own Measurement Group declares mixed sides and no engineer has chosen one    -> `group_conflict`;
  * otherwise the effective side is consumable, with its provenance.

Group membership -- never a name, a bay or an Engineering Context -- is the authority boundary. Nothing is inferred from a
magnitude or a CT/VT ratio, and no request parameter can change the answer; the consumers only validate assertions against it.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.calculated_channel import ChannelRef
from app.domain.measurement_side_config import STATUS_CONFLICT, ChannelSideResolution
from app.services.current_group_config_registry import CurrentGroupConfigRegistry
from app.services.measurement_side_service import SideAuthority, build_group_view, resolve_effective_measurement_side
from app.services.voltage_group_config_registry import VoltageGroupConfigRegistry

PROBLEM_CALCULATED = "calculated"
PROBLEM_UNRESOLVED = "unresolved"
PROBLEM_INFERRED = "inferred"
PROBLEM_GROUP_CONFLICT = "group_conflict"


@dataclass(frozen=True, slots=True)
class RecordedAuthority:
    """The registries the recorded authority reads. Build once per request with `from_app_state`."""

    side: SideAuthority
    current_config_registry: CurrentGroupConfigRegistry
    voltage_config_registry: VoltageGroupConfigRegistry

    @classmethod
    def from_app_state(cls, state) -> "RecordedAuthority":
        return cls(
            side=SideAuthority.from_app_state(state),
            current_config_registry=state.current_group_config_registry,
            voltage_config_registry=state.voltage_group_config_registry,
        )


@dataclass(frozen=True, slots=True)
class ChannelSideAuthority:
    """What Recording Details says about ONE consumed channel's side, and whether it may be consumed."""

    ref: ChannelRef
    side: ChannelSideResolution | None
    group_id: str | None
    group_name: str | None
    #: One of the PROBLEM_* values, or None when the effective side is strict-usable and consistent.
    problem: str | None

    @property
    def usable_side(self) -> str | None:
        """The effective 'primary'/'secondary' side to consume; None whenever there is a problem."""
        return self.side.side if self.problem is None and self.side is not None else None


def channel_label(ref: ChannelRef) -> str:
    return ref.channel_name if ref.kind == "source" else f"calculated:{ref.calculated_channel_id}"


def evaluate_channel_side(
    workspace_id: str, ref: ChannelRef, *, authority: RecordedAuthority,
    group_status_cache: dict[tuple[str, str], bool] | None = None,
) -> ChannelSideAuthority:
    """Evaluate one consumed channel. `group_status_cache` is an optional request-scoped memo of "is this Measurement
    Group in conflict", so a calculation that consumes several channels of one group asks the shared service once."""
    if ref.kind != "source":
        return ChannelSideAuthority(ref, None, None, None, PROBLEM_CALCULATED)
    side = resolve_effective_measurement_side(workspace_id, ref.source_id, ref.channel_name, deps=authority.side)
    group = authority.side.group_registry.get(workspace_id, side.group_id) if side.group_id else None
    group_name = group.display_name if group is not None else None
    in_conflict = False
    if group is not None:
        key = (ref.source_id, group.id)
        if group_status_cache is not None and key in group_status_cache:
            in_conflict = group_status_cache[key]
        else:
            in_conflict = build_group_view(workspace_id, ref.source_id, group.id, deps=authority.side).resolution.status == STATUS_CONFLICT
            if group_status_cache is not None:
                group_status_cache[key] = in_conflict
    if not side.usable:
        problem = PROBLEM_UNRESOLVED
    elif side.inferred:
        problem = PROBLEM_INFERRED
    elif in_conflict:
        problem = PROBLEM_GROUP_CONFLICT
    else:
        problem = None
    return ChannelSideAuthority(ref, side, group.id if group else None, group_name, problem)
