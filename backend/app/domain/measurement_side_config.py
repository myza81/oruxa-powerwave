"""D5A-2B2A: unified measurement-side configuration (pure domain).

One authoritative interpretation of "is this recorded Voltage/Current channel on the Primary or the
Secondary side of its instrument transformer", shared by every consumer. Two levels of configuration:

* Level 1 -- the Recording (source): a recording-wide default, resolved automatically from the
  recording's own per-channel P/S evidence when that evidence is consistent, and correctable by an
  engineer. The engineer's value is stored SEPARATELY from the evidence; the evidence is never altered.
* Level 2 -- the Bay (Engineering Context): an optional engineer override of Level 1, one value for the
  whole bay (never per phase). A bay with no override simply follows Level 1; nothing is stored for it.

Channel precedence (first match wins):

    1. bay override            (engineer, confirmed bay membership only)    -> `engineer_bay_override`
    2. recording correction    (engineer)                                   -> `engineer_recording_correction`
    3. the channel's own P/S   (original recording evidence)                -> `recording_channel_declared`
    4. recording default       (consistent evidence of the OTHER channels)  -> `recording_default`
    5. nothing                                                              -> `unresolved`

Contradictory evidence is never hidden: a recording whose channels declare different sides has NO
recording-derived default (so it cannot be used to conceal the mix), each channel keeps its own
declaration, and a bay that ends up with different effective sides is reported as a conflict instead of
being given a single manufactured interpretation. An engineer value that disagrees with a channel's
declaration wins, and the declaration it overrides stays visible (`declared_side`, diagnostics).

No CT/VT ratio, no Per-Unit base and no conversion lives here, and nothing is inferred from channel
names. Per-phase settings are intentionally not modelled.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Mapping, Sequence

SIDE_PRIMARY = "primary"
SIDE_SECONDARY = "secondary"
SIDE_UNKNOWN = "unknown"
CONFIGURABLE_SIDES = (SIDE_PRIMARY, SIDE_SECONDARY)

QUANTITY_VOLTAGE = "voltage"
QUANTITY_CURRENT = "current"

# --- Channel / recording-level authority (what decided the effective side) ---
AUTH_BAY_OVERRIDE = "engineer_bay_override"
AUTH_RECORDING_CORRECTION = "engineer_recording_correction"
AUTH_CHANNEL_DECLARED = "recording_channel_declared"
AUTH_RECORDING_DEFAULT = "recording_default"
AUTH_UNRESOLVED = "unresolved"
AUTH_NOT_APPLICABLE = "not_applicable"

# --- Recording-derived evidence status ---
EVIDENCE_CONSISTENT = "consistent"
EVIDENCE_NONE = "none"
EVIDENCE_MIXED = "mixed"

# --- Aggregate resolution status (bay / consumed-channel set) ---
STATUS_RESOLVED = "resolved"
STATUS_CONFLICT = "conflict"
STATUS_UNRESOLVED = "unresolved"
STATUS_NOT_APPLICABLE = "not_applicable"

# --- Bay membership reliability ---
MEMBERSHIP_NONE = "none"
MEMBERSHIP_CONFIRMED = "confirmed"
MEMBERSHIP_UNCONFIRMED = "unconfirmed"

SEVERITY_INFO = "info"
SEVERITY_WARNING = "warning"
SEVERITY_CONFLICT = "conflict"

# Diagnostic codes (stable contract).
DIAG_RECORDING_EVIDENCE_MISSING = "RECORDING_SIDE_EVIDENCE_MISSING"
DIAG_RECORDING_EVIDENCE_MIXED = "RECORDING_MIXED_SIDE_EVIDENCE"
DIAG_RECORDING_EVIDENCE_PARTIAL = "RECORDING_PARTIAL_SIDE_EVIDENCE"
DIAG_RECORDING_CORRECTION_OVERRIDES = "ENGINEER_CORRECTION_OVERRIDES_DECLARATION"
DIAG_BAY_OVERRIDE_OVERRIDES = "BAY_OVERRIDE_OVERRIDES_DECLARATION"
DIAG_BAY_MIXED_WITHIN_QUANTITY = "BAY_MIXED_SIDES_WITHIN_QUANTITY"
DIAG_BAY_VOLTAGE_CURRENT_DIFFER = "BAY_VOLTAGE_CURRENT_SIDES_DIFFER"
DIAG_BAY_UNRESOLVED = "BAY_SIDE_UNRESOLVED"
DIAG_BAY_MEMBERSHIP_UNCONFIRMED = "BAY_MEMBERSHIP_UNCONFIRMED"
DIAG_BAY_OVERRIDE_INACTIVE = "BAY_OVERRIDE_INACTIVE_UNCONFIRMED_MEMBERSHIP"
DIAG_BAY_NO_MEASUREMENT_MEMBERS = "BAY_HAS_NO_VOLTAGE_CURRENT_MEMBERS"
DIAG_BAY_INHERITANCE_AMBIGUOUS = "BAY_RECORDINGS_DISAGREE"
DIAG_CHANNEL_NOT_FOUND = "CHANNEL_NOT_FOUND"
DIAG_CHANNEL_NOT_MEASUREMENT = "CHANNEL_NOT_VOLTAGE_OR_CURRENT"
DIAG_CALCULATED_CHANNEL = "CALCULATED_CHANNEL_NOT_RESOLVED"
DIAG_SOURCE_NOT_FOUND = "SOURCE_NOT_FOUND"
DIAG_CONSUMED_MIXED = "CONSUMED_CHANNELS_SIDES_DIFFER"
DIAG_CONSUMED_VI_DIFFER = "CONSUMED_VOLTAGE_CURRENT_SIDES_DIFFER"
DIAG_CHANNEL_INFERRED = "CHANNEL_SIDE_INFERRED"
DIAG_CONSUMED_UNRESOLVED = "CONSUMED_CHANNEL_SIDE_UNRESOLVED"


def side_configurable(side: object) -> bool:
    return isinstance(side, str) and side in CONFIGURABLE_SIDES


def normalise_declared_side(side: str | None) -> str:
    """A recording's own marker as `primary` / `secondary`; anything else is `unknown`."""
    return side if side in CONFIGURABLE_SIDES else SIDE_UNKNOWN


@dataclass(frozen=True, slots=True)
class SideDiagnostic:
    code: str
    severity: str
    message: str
    detail: Mapping[str, str | int | None] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ChannelSideEvidence:
    """The recording's original declaration for one Voltage/Current channel. Never mutated."""

    channel_name: str
    quantity: str
    declared_side: str
    source_id: str | None = None


@dataclass(frozen=True, slots=True)
class RecordingSideDerivation:
    """What the recording's own channel evidence says, with no engineer input applied."""

    status: str
    side: str | None
    primary_count: int = 0
    secondary_count: int = 0
    undeclared_count: int = 0
    evidence_channel_count: int = 0


def derive_recording_side(evidence: Iterable[ChannelSideEvidence]) -> RecordingSideDerivation:
    """Consistent only when every DECLARING channel agrees; mixed declarations yield no default."""
    items = list(evidence)
    primary = sum(1 for e in items if e.declared_side == SIDE_PRIMARY)
    secondary = sum(1 for e in items if e.declared_side == SIDE_SECONDARY)
    undeclared = len(items) - primary - secondary
    if primary and secondary:
        status, side = EVIDENCE_MIXED, None
    elif primary or secondary:
        status, side = EVIDENCE_CONSISTENT, SIDE_PRIMARY if primary else SIDE_SECONDARY
    else:
        status, side = EVIDENCE_NONE, None
    return RecordingSideDerivation(status, side, primary, secondary, undeclared, len(items))


@dataclass(frozen=True, slots=True)
class RecordingSideState:
    """Level 1 for one recording: derived evidence + the engineer's correction (if any) + the result."""

    derivation: RecordingSideDerivation
    engineer_side: str | None
    effective_side: str | None
    authority: str
    diagnostics: tuple[SideDiagnostic, ...] = ()


def resolve_recording_state(
    derivation: RecordingSideDerivation, engineer_side: str | None,
    evidence: Sequence[ChannelSideEvidence] = (),
) -> RecordingSideState:
    diags: list[SideDiagnostic] = []
    if derivation.status == EVIDENCE_MIXED:
        diags.append(SideDiagnostic(
            DIAG_RECORDING_EVIDENCE_MIXED, SEVERITY_CONFLICT,
            "The recording's voltage/current channels declare different measurement sides; no recording-wide "
            "default is derived. Each channel keeps its own declaration until an engineer sets the recording side.",
            {"primary_channels": derivation.primary_count, "secondary_channels": derivation.secondary_count},
        ))
    elif derivation.status == EVIDENCE_NONE:
        diags.append(SideDiagnostic(
            DIAG_RECORDING_EVIDENCE_MISSING, SEVERITY_WARNING,
            "The recording declares no Primary/Secondary side for its voltage/current channels.",
            {"evidence_channels": derivation.evidence_channel_count},
        ))
    elif derivation.undeclared_count:
        diags.append(SideDiagnostic(
            DIAG_RECORDING_EVIDENCE_PARTIAL, SEVERITY_INFO,
            "Some voltage/current channels declare no side; they take the recording default of the channels "
            "that do.", {"undeclared_channels": derivation.undeclared_count},
        ))
    if engineer_side is not None:
        contradicted = sorted(e.channel_name for e in evidence
                              if e.declared_side not in (SIDE_UNKNOWN, engineer_side))
        if contradicted:
            diags.append(SideDiagnostic(
                DIAG_RECORDING_CORRECTION_OVERRIDES, SEVERITY_WARNING,
                "The engineer's recording side overrides the side declared by these channels; the original "
                "declarations are retained.", {"channels": ",".join(contradicted), "count": len(contradicted)},
            ))
        return RecordingSideState(derivation, engineer_side, engineer_side, AUTH_RECORDING_CORRECTION, tuple(diags))
    if derivation.status == EVIDENCE_CONSISTENT:
        return RecordingSideState(derivation, None, derivation.side, AUTH_CHANNEL_DECLARED, tuple(diags))
    return RecordingSideState(derivation, None, None, AUTH_UNRESOLVED, tuple(diags))


def recording_correction_to_store(selected: str | None, derivation: RecordingSideDerivation) -> str | None:
    """The engineer's selection -> the correction to keep. `None` follows the recording. Selecting the value the
    recording already declares for EVERY channel stores nothing (nothing is redundant). When some channels declare
    nothing, the same selection is kept: it is the engineer's confirmation of what those channels would otherwise
    only inherit as an inferred default."""
    if selected is None:
        return None
    if not side_configurable(selected):
        raise ValueError("Measurement side must be 'primary' or 'secondary'.")
    if derivation.status == EVIDENCE_CONSISTENT and selected == derivation.side and not derivation.undeclared_count:
        return None
    return selected


def bay_override_to_store(selected: str, inherited_recording_side: str | None) -> str | None:
    """Selecting the side the bay already inherits from Level 1 clears the override (it follows Level 1 again);
    anything else is a manual override. With no single inherited value there is nothing to clear to."""
    if not side_configurable(selected):
        raise ValueError("Measurement side must be 'primary' or 'secondary'.")
    return None if inherited_recording_side is not None and selected == inherited_recording_side else selected


@dataclass(frozen=True, slots=True)
class BaySideState:
    """What applies to one channel from its bay. `override_side` is set only when the override is ACTIVE
    (confirmed membership); `membership` is `none` when the channel is in no bay."""

    context_id: str | None = None
    membership: str = MEMBERSHIP_NONE
    stored_override_side: str | None = None

    @property
    def override_side(self) -> str | None:
        return self.stored_override_side if self.membership == MEMBERSHIP_CONFIRMED else None


@dataclass(frozen=True, slots=True)
class ChannelSideResolution:
    channel_name: str | None
    quantity: str | None
    side: str
    authority: str
    declared_side: str
    recording_side: str | None
    recording_authority: str
    context_id: str | None = None
    membership: str = MEMBERSHIP_NONE
    bay_override_side: str | None = None
    diagnostics: tuple[SideDiagnostic, ...] = ()
    source_id: str | None = None

    @property
    def usable(self) -> bool:
        """True for any concrete Primary/Secondary side, including an inferred one (display / inheritance)."""
        return self.side in CONFIGURABLE_SIDES

    @property
    def inferred(self) -> bool:
        """The side comes only from the sibling-derived recording default, not from this channel's own evidence."""
        return self.authority == AUTH_RECORDING_DEFAULT

    @property
    def strict_usable(self) -> bool:
        """A side strict side-dependent calculations may act on: reliable evidence (the channel's own declaration)
        or an engineer-confirmed Recording / Bay setting. An inferred default is not enough."""
        return self.usable and not self.inferred


def resolve_channel_side(
    evidence: ChannelSideEvidence, recording: RecordingSideState, bay: BaySideState | None = None,
) -> ChannelSideResolution:
    bay = bay or BaySideState()
    diags: list[SideDiagnostic] = []
    if bay.membership == MEMBERSHIP_UNCONFIRMED:
        diags.append(SideDiagnostic(
            DIAG_BAY_MEMBERSHIP_UNCONFIRMED, SEVERITY_INFO,
            "This channel's bay membership is suggested or needs review, so no bay setting is applied to it; "
            "it follows its recording.",
            {"engineering_context_id": bay.context_id},
        ))
    declared = evidence.declared_side
    override = bay.override_side
    if override is not None:
        side, authority = override, AUTH_BAY_OVERRIDE
        if declared not in (SIDE_UNKNOWN, override):
            diags.append(SideDiagnostic(
                DIAG_BAY_OVERRIDE_OVERRIDES, SEVERITY_WARNING,
                "The bay setting overrides the side this channel declares; the declaration is retained.",
                {"declared_side": declared, "bay_side": override},
            ))
    elif recording.engineer_side is not None:
        side, authority = recording.engineer_side, AUTH_RECORDING_CORRECTION
        if declared not in (SIDE_UNKNOWN, side):
            diags.append(SideDiagnostic(
                DIAG_RECORDING_CORRECTION_OVERRIDES, SEVERITY_WARNING,
                "The engineer's recording side overrides the side this channel declares; the declaration is "
                "retained.", {"declared_side": declared, "recording_side": side},
            ))
    elif declared != SIDE_UNKNOWN:
        side, authority = declared, AUTH_CHANNEL_DECLARED
    elif recording.effective_side is not None:
        side, authority = recording.effective_side, AUTH_RECORDING_DEFAULT
        diags.append(SideDiagnostic(
            DIAG_CHANNEL_INFERRED, SEVERITY_INFO,
            "This channel declares no side; the side shown is inferred from the recording's other channels. Strict "
            "side-dependent calculations need reliable evidence or an engineer-confirmed recording/bay setting.",
            {"inferred_side": side},
        ))
    else:
        side, authority = SIDE_UNKNOWN, AUTH_UNRESOLVED
    return ChannelSideResolution(
        channel_name=evidence.channel_name, quantity=evidence.quantity, side=side, authority=authority,
        declared_side=declared, recording_side=recording.effective_side, recording_authority=recording.authority,
        context_id=bay.context_id, membership=bay.membership, bay_override_side=override,
        diagnostics=tuple(diags), source_id=evidence.source_id,
    )


@dataclass(frozen=True, slots=True)
class SideSetResolution:
    """Aggregate of several channels' effective sides (a bay, or the channels a calculation consumes)."""

    status: str
    side: str | None
    voltage_side: str | None
    current_side: str | None
    authority: str
    diagnostics: tuple[SideDiagnostic, ...] = ()
    inferred_channels: tuple[str, ...] = ()

    @property
    def usable(self) -> bool:
        """Every channel has a concrete side (possibly inferred, possibly Primary voltage with Secondary current)."""
        return self.status == STATUS_RESOLVED

    @property
    def strict_usable(self) -> bool:
        """`usable` and no side is merely inferred: safe for a strict side-dependent calculation."""
        return self.usable and not self.inferred_channels

    @property
    def reference_sides(self) -> str | None:
        """`uniform` when every channel shares one side; `voltage_current_differ` when each quantity is uniform
        but voltage and current sit on different sides (legitimate: each is normalised independently)."""
        if not self.usable:
            return None
        return "uniform" if self.side is not None else "voltage_current_differ"


def _uniform(resolutions: Sequence[ChannelSideResolution]) -> str | None:
    sides = {r.side for r in resolutions}
    return next(iter(sides)) if len(sides) == 1 and next(iter(sides)) in CONFIGURABLE_SIDES else None


def resolve_side_set(
    resolutions: Sequence[ChannelSideResolution], *,
    mixed_code: str = DIAG_BAY_MIXED_WITHIN_QUANTITY, vi_code: str = DIAG_BAY_VOLTAGE_CURRENT_DIFFER,
    unresolved_code: str = DIAG_BAY_UNRESOLVED,
) -> SideSetResolution:
    """A single side only when EVERY channel agrees; different sides are a conflict (never merged) and any
    unresolved channel keeps the set unresolved -- nothing is guessed."""
    items = [r for r in resolutions if r.authority != AUTH_NOT_APPLICABLE]
    if not items:
        return SideSetResolution(STATUS_NOT_APPLICABLE, None, None, None, AUTH_NOT_APPLICABLE)
    diags: list[SideDiagnostic] = []
    by_quantity = {q: [r for r in items if r.quantity == q] for q in (QUANTITY_VOLTAGE, QUANTITY_CURRENT)}
    voltage_side, current_side = (_uniform(by_quantity[q]) if by_quantity[q] else None
                                  for q in (QUANTITY_VOLTAGE, QUANTITY_CURRENT))
    conflict = False
    for quantity, group in by_quantity.items():
        concrete = {r.side for r in group if r.usable}
        if len(concrete) > 1:
            conflict = True
            diags.append(SideDiagnostic(
                mixed_code, SEVERITY_CONFLICT,
                f"The {quantity} channels have different effective measurement sides; no single interpretation "
                "is manufactured.", {"quantity": quantity, "channels": ",".join(
                    f"{r.channel_name}={r.side}" for r in group)},
            ))
    concrete_all = {r.side for r in items if r.usable}
    vi_differ = False
    if not conflict and voltage_side and current_side and voltage_side != current_side:
        # Not a conflict: each quantity is internally consistent, so each can be normalised independently. Only
        # a quantity whose channels disagree among themselves is (above).
        vi_differ = True
        diags.append(SideDiagnostic(
            vi_code, SEVERITY_INFO,
            "Voltage and current are on different measurement sides; each is normalised independently when a "
            "calculation needs it.", {"voltage_side": voltage_side, "current_side": current_side},
        ))
    unresolved = [r for r in items if not r.usable]
    if unresolved:
        diags.append(SideDiagnostic(
            unresolved_code, SEVERITY_WARNING if not conflict else SEVERITY_INFO,
            "These channels have no resolvable measurement side.",
            {"channels": ",".join(r.channel_name or "?" for r in unresolved), "count": len(unresolved)},
        ))
    for r in items:
        diags.extend(d for d in r.diagnostics if d not in diags)
    if conflict:
        return SideSetResolution(STATUS_CONFLICT, None, voltage_side, current_side, AUTH_UNRESOLVED, tuple(diags))
    if unresolved:
        return SideSetResolution(STATUS_UNRESOLVED, None, voltage_side, current_side, AUTH_UNRESOLVED, tuple(diags))
    inferred = tuple(r.channel_name or "?" for r in items if r.inferred)
    authorities = {r.authority for r in items}
    authority = next(iter(authorities)) if len(authorities) == 1 else "mixed"
    side = None if vi_differ else next(iter(concrete_all))
    return SideSetResolution(STATUS_RESOLVED, side, voltage_side, current_side, authority, tuple(diags), inferred)
