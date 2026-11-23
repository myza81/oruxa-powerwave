"""D5A-2B2C-1A: the Recording Details authority a recorded Overcurrent calculation consumes.

Recording Details is the single source of truth for the Primary/Secondary side of a recorded channel (DEC-216). For the
ONE Current channel an Overcurrent phase consumes, this module asks the shared resolver for its effective side
(`measurement_side_service.resolve_effective_measurement_side`) and reads the CT of the Measurement Group that owns
THAT channel -- never another group, phase or recording. It owns no side interpretation of its own:

  * the side is never inferred from a magnitude or a CT ratio;
  * an unresolved side, a side that is only inferred from sibling channels, or a Current group whose own channels
    declare different sides blocks the calculation with a configuration reason -- nothing is guessed;
  * a legacy request `recording_basis` is only an assertion: it is validated against the authority and a
    contradiction blocks (it can never override Recording Details);
  * a legacy request CT is likewise only an assertion, and is looked at only when a conversion is needed;
  * the CT conversion itself stays in `app.domain.overcurrent` (the caller applies it once, to a Primary side only).

The same evaluation feeds both the calculation and the read-only input report, so the page and the backend cannot
disagree about what is consumed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from app.domain.calculated_channel import ChannelRef
from app.domain.measurement_side_config import SIDE_PRIMARY, STATUS_CONFLICT, ChannelSideResolution
from app.domain.overcurrent import (
    KNOWN_RECORDING_BASES,
    REASON_BASIS_CONTRADICTS_SIDE,
    REASON_CALCULATED_SIDE,
    REASON_INVALID_CT_VALUES,
    REASON_INVALID_RECORDING_BASIS,
    REASON_REQUEST_CT_DIFFERS,
    REASON_SIDE_CONFLICT,
    REASON_SIDE_INFERRED,
    REASON_SIDE_UNRESOLVED,
    ct_values_valid,
)
from app.services.current_group_config_registry import CurrentGroupConfigRegistry
from app.services.measurement_side_service import SideAuthority, build_group_view, resolve_effective_measurement_side
from app.services.protection_instrument_context import (
    QUANTITY_CURRENT,
    RATIO_NO_GROUP,
    TransformerContext,
    resolve_transformer_context,
)
from app.services.voltage_group_config_registry import VoltageGroupConfigRegistry

_RATIO_REL_TOL = 1e-6


@dataclass(frozen=True, slots=True)
class OvercurrentAuthority:
    """The registries the recorded Overcurrent authority reads. Build once per request with `from_app_state`."""

    side: SideAuthority
    current_config_registry: CurrentGroupConfigRegistry
    voltage_config_registry: VoltageGroupConfigRegistry

    @classmethod
    def from_app_state(cls, state) -> "OvercurrentAuthority":
        return cls(
            side=SideAuthority.from_app_state(state),
            current_config_registry=state.current_group_config_registry,
            voltage_config_registry=state.voltage_group_config_registry,
        )


@dataclass(frozen=True, slots=True)
class AuthorityBlocker:
    reason_code: str
    message: str


@dataclass(frozen=True, slots=True)
class RecordedCurrentAuthority:
    """What Recording Details says about the one consumed Current channel, and whether it may be consumed."""

    channel_ref: ChannelRef
    group_id: str | None
    group_name: str | None
    side: ChannelSideResolution | None
    #: The CT of the channel's OWN Measurement Group (read even for a Secondary side, where it is not needed).
    ct: TransformerContext | None
    blocker: AuthorityBlocker | None

    @property
    def basis(self) -> str | None:
        """The effective side the recorded current is expressed on; None while the calculation is blocked."""
        return self.side.side if self.blocker is None and self.side is not None else None

    @property
    def conversion_required(self) -> bool:
        return self.basis == SIDE_PRIMARY

    @property
    def ct_pair(self) -> tuple[float, float] | None:
        """(primary, secondary) of the CT to apply: only for a Primary side, only a consumable ratio of the group."""
        if self.blocker is None and self.conversion_required and self.ct is not None and self.ct.ratio_consumable:
            return float(self.ct.primary), float(self.ct.secondary)
        return None


def _channel_label(ref: ChannelRef) -> str:
    return ref.channel_name if ref.kind == "source" else f"calculated:{ref.calculated_channel_id}"


def _where_to_set(group_name: str | None) -> str:
    return (f"Set it in Recording Details (the recording, or the Current Measurement Group '{group_name}')."
            if group_name else "Set it in Recording Details (the recording, or the channel's Current Measurement Group).")


def _side_blocker(ref: ChannelRef, side: ChannelSideResolution, group_name: str | None,
                  group_in_conflict: bool) -> AuthorityBlocker | None:
    label = _channel_label(ref)
    if not side.usable:
        return AuthorityBlocker(
            REASON_SIDE_UNRESOLVED,
            f"The measurement side of '{label}' (Primary or Secondary) is not defined by the recording or by "
            f"Recording Details, so the recorded current cannot be interpreted. {_where_to_set(group_name)}",
        )
    if side.inferred:
        return AuthorityBlocker(
            REASON_SIDE_INFERRED,
            f"The measurement side of '{label}' is only inferred from other channels of the recording ({side.side}); "
            f"a recorded calculation needs the channel's own declaration or an engineer's setting. "
            f"{_where_to_set(group_name)}",
        )
    if group_in_conflict:
        return AuthorityBlocker(
            REASON_SIDE_CONFLICT,
            f"The channels of the Current Measurement Group '{group_name}' declare different measurement sides, so "
            f"its side is contradictory. Choose Primary or Secondary for the group in Recording Details.",
        )
    return None


def _ct_blocker(ref: ChannelRef, ct: TransformerContext, group_name: str | None) -> AuthorityBlocker | None:
    """The reason the CT of the consumed channel's own group cannot be applied (None when it can)."""
    if ct.ratio_consumable:
        return None
    label = _channel_label(ref)
    if ct.ratio_status == RATIO_NO_GROUP:
        text = (f"'{label}' is not in a Current Measurement Group, so no CT applies to it. Add it to a Current "
                f"Measurement Group in Recording Details and configure the CT.")
    elif ct.ratio_status in ("invalid", "untrusted_authority"):
        text = (f"The CT of the Current Measurement Group '{group_name}' is not usable"
                f"{' (' + ct.reason + ')' if ct.reason else ''}. Correct it in Recording Details.")
    else:
        text = (f"CT is not configured for the Current Measurement Group '{group_name}'. Set primary and secondary A "
                f"in Recording Details.")
    return AuthorityBlocker(REASON_INVALID_CT_VALUES, text)


def _request_ct_blocker(ct: TransformerContext, request_ct: tuple[float | None, float | None]) -> AuthorityBlocker | None:
    primary, secondary = request_ct
    if primary is None and secondary is None:
        return None
    if primary is None or secondary is None or not ct_values_valid(primary, secondary):
        return AuthorityBlocker(
            REASON_INVALID_CT_VALUES,
            "CT primary and CT secondary current must both be finite numbers greater than zero.",
        )
    if ct.ratio is None or not math.isclose(primary / secondary, ct.ratio, rel_tol=_RATIO_REL_TOL):
        return AuthorityBlocker(
            REASON_REQUEST_CT_DIFFERS,
            f"The supplied CT ({primary:g} A / {secondary:g} A) differs from the CT configured in Recording Details "
            f"({ct.primary:g} A / {ct.secondary:g} A). Recording Details is authoritative; change the CT there.",
        )
    return None


def evaluate_recorded_current_authority(
    workspace_id: str,
    channel_ref: ChannelRef,
    *,
    authority: OvercurrentAuthority,
    requested_basis: str | None = None,
    request_ct: tuple[float | None, float | None] = (None, None),
) -> RecordedCurrentAuthority:
    """Decide whether the recorded current of `channel_ref` may be consumed, and on which side, with which CT.

    `requested_basis` / `request_ct` are the legacy request assertions (None when the caller supplied none)."""
    if channel_ref.kind != "source":
        return RecordedCurrentAuthority(
            channel_ref, None, None, None, None,
            AuthorityBlocker(
                REASON_CALCULATED_SIDE,
                "The measurement side of a calculated current channel is derived from its inputs and is not "
                "resolved by Recording Details yet, so a recorded Overcurrent calculation cannot consume it.",
            ),
        )
    side = resolve_effective_measurement_side(
        workspace_id, channel_ref.source_id, channel_ref.channel_name, deps=authority.side,
    )
    group = authority.side.group_registry.get(workspace_id, side.group_id) if side.group_id else None
    group_name = group.display_name if group is not None else None
    ct = resolve_transformer_context(
        workspace_id, [channel_ref], QUANTITY_CURRENT,
        group_registry=authority.side.group_registry, voltage_config_registry=authority.voltage_config_registry,
        current_config_registry=authority.current_config_registry, source_registry=authority.side.source_registry,
    )
    group_in_conflict = False
    if group is not None:
        view = build_group_view(workspace_id, channel_ref.source_id, group.id, deps=authority.side)
        group_in_conflict = view.resolution.status == STATUS_CONFLICT

    blocker = _side_blocker(channel_ref, side, group_name, group_in_conflict)
    if blocker is None and requested_basis is not None:
        if requested_basis not in KNOWN_RECORDING_BASES:
            blocker = AuthorityBlocker(REASON_INVALID_RECORDING_BASIS, "Recording current basis must be 'primary' or 'secondary'.")
        elif requested_basis != side.side:
            blocker = AuthorityBlocker(
                REASON_BASIS_CONTRADICTS_SIDE,
                f"The requested recording basis ({requested_basis}) contradicts the measurement side defined in "
                f"Recording Details ({side.side}). Recording Details is authoritative; change the side there.",
            )
    if blocker is None and side.side == SIDE_PRIMARY:
        blocker = _ct_blocker(channel_ref, ct, group_name) or _request_ct_blocker(ct, request_ct)
    return RecordedCurrentAuthority(channel_ref, group.id if group else None, group_name, side, ct, blocker)
