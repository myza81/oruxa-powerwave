"""API response DTOs for the V-I pair discovery endpoint (Phase C, DEC-205).

Read-only workspace-scoped response only -- no request body.  All
serialisation happens in app.api.v1.vi_pairs; this module carries the
Pydantic models only, following the same schema/router split every other
endpoint in this API uses.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class VIPairChannelOut(BaseModel):
    """Identity of one channel participating in a V-I pairing result.

    ``engineering_type`` is the broad classification already computed at
    import time (``"Voltage"``, ``"Current"``, etc.) -- the same value
    carried by ``AnalogChannelOut``.  ``unit`` is the raw COMTRADE unit
    string (``"kV"``, ``"kA"``, etc.) before any scaling.
    """

    source_id: str
    channel_name: str
    engineering_type: str
    unit: str


class VIPairMatchEvidenceOut(BaseModel):
    """The matching key that caused two channels to be considered a pair.

    ``context_hint`` is the equipment-context prefix extracted by the
    role-grammar resolver (e.g. ``"IBT1 HV"`` from ``"IBT1 HV VA"``), or
    ``None`` for channels with no equipment prefix.

    ``phase_token`` is the phase identity token (e.g. ``"A"``, ``"R"``,
    ``"L1"``).

    ``phase_token_kind`` is the token-kind string from the voltage
    channel's own resolved identity (``"single"``, ``"neutral"``,
    ``"l123"``), or ``None`` for candidate entries that span multiple
    channels of potentially mixed kinds.
    """

    context_hint: str | None
    phase_token: str
    phase_token_kind: str | None


class AutomaticVIPairOut(BaseModel):
    """One V-I pair that met all five automatic-pairing criteria.

    ``pair_id`` is a stable, deterministic identifier for this pair within
    the current workspace state -- computed as a SHA-256 prefix over
    ``(source_id, voltage_channel_name, current_channel_name)``.  It is
    unambiguous even when different sources carry channels with the same
    name.

    ``display_label`` is a human-readable one-liner suitable for dropdown
    pre-fill, e.g. ``"VA / IA (IBT1 HV)"``.
    """

    pair_id: str
    status: Literal["automatic"] = "automatic"
    display_label: str
    source_id: str
    voltage_channel: VIPairChannelOut
    current_channel: VIPairChannelOut
    matching_evidence: VIPairMatchEvidenceOut


class CandidateVIPairOut(BaseModel):
    """A V-I pairing candidate that could not be automatically confirmed.

    ``reason`` is one of the REASON_* constants from
    ``app.domain.vi_pair_resolution``:

    - ``"conflict"``          — at least one channel has an identity conflict.
    - ``"multiple_voltage"``  — more than one Voltage candidate at the key.
    - ``"multiple_current"``  — more than one Current candidate at the key.
    - ``"cross_source"``      — the single V and single I are from different
                                recording sources.

    ``voltage_refs`` and ``current_refs`` carry the COMPLETE sets of
    matching candidates -- never a single arbitrarily selected entry.
    The engineer must explicitly choose one from each list before the
    frontend can create a power channel.
    """

    pair_id: str
    status: Literal["needs_confirmation"] = "needs_confirmation"
    display_label: str
    reason: str
    voltage_refs: list[VIPairChannelOut]
    current_refs: list[VIPairChannelOut]
    matching_evidence: VIPairMatchEvidenceOut


class ThreePhasePairRefOut(BaseModel):
    """One V-I pair slot within a three-phase set (Phase E-2C, DEC-208).

    ``phase`` is the phase token that belongs to this slot (e.g. ``"R"``,
    ``"Y"``, ``"B"``).  ``voltage_channel`` and ``current_channel`` carry the
    same wire shape as a single-phase automatic pair's channel fields --
    the frontend can build a six-channel create request directly from
    three consecutive ``ThreePhasePairRefOut`` entries.
    """

    phase: str
    voltage_channel: VIPairChannelOut
    current_channel: VIPairChannelOut


class ThreePhaseIncompletePhaseOut(BaseModel):
    """Why one expected phase token is absent from an incomplete set.

    ``reason`` is ``"not_found"`` when no channel with that phase token
    exists in the workspace at all, or ``"needs_confirmation"`` when a
    candidate exists but requires explicit user confirmation before it can
    be used.
    """

    phase: str
    reason: str  # "not_found" | "needs_confirmation"


class ThreePhaseCompleteSetOut(BaseModel):
    """A complete, automatically resolved three-phase V-I measurement set.

    The three pairs are listed in fixed phase order (phase_1/phase_2/
    phase_3 = R/Y/B, A/B/C, or L1/L2/L3 depending on ``phase_convention``).

    ``voltage_reference`` is the result of running ``detect_voltage_reference``
    over the three voltage channel names:

    - ``"line_to_ground"``  — confident phase-to-neutral; auto-proceed.
    - ``"line_to_line"``    — line-to-line voltages; set will be rejected.
    - ``None``              — no recognizable evidence; confirmation required.

    ``voltage_reference_confirmation_required`` is ``True`` whenever
    ``voltage_reference`` is not ``"line_to_ground"``, signalling that the
    frontend must show the confirmation checkbox before enabling Create.

    ``voltage_reference_evidence_names`` carries the channel name(s) the
    detector used as evidence, verbatim, for display in the UI.
    """

    set_id: str
    status: Literal["complete"] = "complete"
    display_label: str
    source_id: str
    context_hint: str | None
    phase_convention: str  # "RYB" | "ABC" | "L123"
    pairs: list[ThreePhasePairRefOut]
    voltage_reference: str | None
    voltage_reference_reason: str
    voltage_reference_evidence_names: list[str]
    voltage_reference_confirmation_required: bool


class ThreePhaseIncompleteSetOut(BaseModel):
    """A partial three-phase group — one or more phases are absent.

    ``phase_convention`` is ``None`` when the present tokens are ambiguous
    (e.g. only phase ``"B"`` is present, which belongs to both RYB and ABC).

    ``incomplete_reason`` is one of:

    - ``"missing_phases"``           — phases simply not found.
    - ``"phases_need_confirmation"`` — at least one absent phase has a
      candidate that requires confirmation.
    - ``"ambiguous_convention"``     — the present tokens do not uniquely
      identify a convention.
    """

    status: Literal["incomplete"] = "incomplete"
    source_id: str
    context_hint: str | None
    phase_convention: str | None
    incomplete_reason: str
    present_pairs: list[ThreePhasePairRefOut]
    missing_phases: list[ThreePhaseIncompletePhaseOut]


class VIPairsOut(BaseModel):
    """Top-level response for GET .../vi-pairs.

    ``total_input_channel_count`` is the number of analog channels across
    all sources that were passed to the resolver, for diagnostics.
    Channels silently excluded by the resolver (no role, non-V/I type,
    line-to-line voltage) are NOT subtracted -- this is the raw input
    count, so callers can sanity-check that the workspace has the channels
    they expect before acting on the pairing results.

    ``three_phase_complete_sets`` and ``three_phase_incomplete_sets`` are
    Phase E-2C additions (DEC-208).  Both default to empty lists -- existing
    callers that do not read these fields are unaffected.
    """

    automatic_pairs: list[AutomaticVIPairOut]
    candidates_needing_confirmation: list[CandidateVIPairOut]
    total_input_channel_count: int
    three_phase_complete_sets: list[ThreePhaseCompleteSetOut] = []
    three_phase_incomplete_sets: list[ThreePhaseIncompleteSetOut] = []
