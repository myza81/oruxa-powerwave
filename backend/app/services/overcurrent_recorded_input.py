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
from app.domain.measurement_group import KIND_CURRENT
from app.domain.measurement_side_config import SIDE_PRIMARY, ChannelSideResolution
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
from app.services.recorded_side_authority import (
    PROBLEM_CALCULATED,
    PROBLEM_GROUP_CONFLICT,
    PROBLEM_INFERRED,
    PROBLEM_UNRESOLVED,
    ChannelSideAuthority,
    RecordedAuthority,
    channel_label,
    evaluate_channel_side,
)
from app.services.protection_instrument_context import (
    CONSUMABLE_AUTHORITIES,
    QUANTITY_CURRENT,
    RATIO_NO_GROUP,
    TransformerContext,
    resolve_transformer_context,
)

_RATIO_REL_TOL = 1e-6


#: The registries the recorded Overcurrent authority reads (shared with Impedance and Distance).
OvercurrentAuthority = RecordedAuthority


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


_channel_label = channel_label


def _where_to_set(group_name: str | None) -> str:
    return (f"Set it in Recording Details (the recording, or the Current Measurement Group '{group_name}')."
            if group_name else "Set it in Recording Details (the recording, or the channel's Current Measurement Group).")


def _side_blocker(ref: ChannelRef, chan: ChannelSideAuthority) -> AuthorityBlocker | None:
    label = _channel_label(ref)
    side, group_name = chan.side, chan.group_name
    if chan.problem is None:
        return None
    if chan.problem == PROBLEM_UNRESOLVED:
        return AuthorityBlocker(
            REASON_SIDE_UNRESOLVED,
            f"The measurement side of '{label}' (Primary or Secondary) is not defined by the recording or by "
            f"Recording Details, so the recorded current cannot be interpreted. {_where_to_set(group_name)}",
        )
    if chan.problem == PROBLEM_INFERRED:
        return AuthorityBlocker(
            REASON_SIDE_INFERRED,
            f"The measurement side of '{label}' is only inferred from other channels of the recording ({side.side}); "
            f"a recorded calculation needs the channel's own declaration or an engineer's setting. "
            f"{_where_to_set(group_name)}",
        )
    return AuthorityBlocker(
        REASON_SIDE_CONFLICT,
        f"The channels of the Current Measurement Group '{group_name}' declare different measurement sides, so "
        f"its side is contradictory. Choose Primary or Secondary for the group in Recording Details.",
    )


def _other_group_with_ct(workspace_id: str, ref: ChannelRef, own_group_id: str | None,
                         authority: "OvercurrentAuthority") -> tuple[str, float, float] | None:
    """(group name, CT primary, CT secondary) of ANOTHER Current group of the same recording that holds a usable CT.
    Only used to explain a missing CT -- never to supply one: a CT is never borrowed from another group."""
    for group in authority.side.group_registry.list_for_workspace(workspace_id):
        if group.kind != KIND_CURRENT or group.source_id != ref.source_id or group.id == own_group_id:
            continue
        config = authority.current_config_registry.get(workspace_id, group.id)
        if config is None or config.ct_authority not in CONSUMABLE_AUTHORITIES:
            continue
        primary, secondary = config.ct_primary_a, config.ct_secondary_a
        if primary is not None and secondary is not None and ct_values_valid(primary, secondary):
            return group.display_name, float(primary), float(secondary)
    return None


def _ct_blocker(ref: ChannelRef, ct: TransformerContext, group_name: str | None,
                other: tuple[str, float, float] | None = None) -> AuthorityBlocker | None:
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
    if other is not None:
        text += (f" A CT of {other[1]:g} A / {other[2]:g} A is configured on '{other[0]}', but '{label}' belongs to "
                 f"'{group_name or 'no group'}' and a CT is never borrowed from another group.")
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
    chan = evaluate_channel_side(workspace_id, channel_ref, authority=authority)
    if chan.problem == PROBLEM_CALCULATED:
        return RecordedCurrentAuthority(
            channel_ref, None, None, None, None,
            AuthorityBlocker(
                REASON_CALCULATED_SIDE,
                f"Measurement-side support for calculated channels is not available yet: the side of the calculated "
                f"current channel '{_channel_label(channel_ref)}' is derived from its inputs, and Recording Details does "
                f"not resolve it, so there is nothing to set there. A recorded Overcurrent calculation cannot use it "
                f"until that support is added; use a recorded (source) current channel or Manual input.",
            ),
        )
    side, group_name = chan.side, chan.group_name
    ct = resolve_transformer_context(
        workspace_id, [channel_ref], QUANTITY_CURRENT,
        group_registry=authority.side.group_registry, voltage_config_registry=authority.voltage_config_registry,
        current_config_registry=authority.current_config_registry, source_registry=authority.side.source_registry,
    )

    blocker = _side_blocker(channel_ref, chan)
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
        other = None if ct.ratio_consumable else _other_group_with_ct(workspace_id, channel_ref, chan.group_id, authority)
        blocker = _ct_blocker(channel_ref, ct, group_name, other) or _request_ct_blocker(ct, request_ct)
    return RecordedCurrentAuthority(channel_ref, chan.group_id, group_name, side, ct, blocker)
