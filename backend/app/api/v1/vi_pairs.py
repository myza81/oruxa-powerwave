"""Read-only V-I pair discovery endpoint (Phase C, DEC-205).

GET /api/v1/workspaces/{workspace_id}/vi-pairs

Exposes the ``find_vi_pairs()`` domain resolver (app.domain.vi_pair_resolution,
DEC-204) through the workspace API.  All pairing logic lives in the domain
module -- this router is a thin adapter that:

1. Lists every analog channel in the workspace.
2. Passes them to ``find_vi_pairs()``.
3. Serialises the result, enriching each channel reference with its unit
   and engineering type from the source registry.

Read-only guarantees (same as the line-to-line-voltage readiness endpoint):
- No workspace state is mutated.
- No data is persisted.
- No Measurement Group changes.
- No per-unit or power-calculation changes.
- No waveform arrays are transferred.

An empty or unknown workspace returns ``{"automatic_pairs": [],
"candidates_needing_confirmation": [], "total_input_channel_count": 0}``
-- the same idempotent convention every other workspace-scoped GET uses
(a workspace is never explicitly "created" server-side; it simply may or
may not have sources uploaded under it at the time of the request).
"""

from __future__ import annotations

import hashlib
import json

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.domain.vi_pair_resolution import (
    REASON_CONFLICT,
    REASON_CROSS_SOURCE,
    REASON_MULTIPLE_CURRENT,
    REASON_MULTIPLE_VOLTAGE,
    ChannelPairingInput,
    MatchedVIPair,
    ThreePhaseAutomaticSet,
    ThreePhaseIncompleteSet,
    VIPairCandidate,
    find_three_phase_vi_sets,
)
from app.schemas.source import ErrorOut
from app.schemas.vi_pairs import (
    AutomaticVIPairOut,
    CandidateVIPairOut,
    ThreePhaseCompleteSetOut,
    ThreePhaseIncompletePhaseOut,
    ThreePhaseIncompleteSetOut,
    ThreePhasePairRefOut,
    VIPairChannelOut,
    VIPairMatchEvidenceOut,
    VIPairsOut,
)
from app.services.workspace_registry import WorkspaceRegistry

router = APIRouter(
    prefix="/api/v1/workspaces/{workspace_id}/vi-pairs",
    tags=["vi-pairs"],
)

_REASON_LABELS: dict[str, str] = {
    REASON_CONFLICT: "identity conflict",
    REASON_MULTIPLE_VOLTAGE: "multiple voltages",
    REASON_MULTIPLE_CURRENT: "multiple currents",
    REASON_CROSS_SOURCE: "cross-source",
}


def get_workspace_registry(request: Request) -> WorkspaceRegistry:
    return request.app.state.workspace_registry


def _validate_workspace_id(workspace_id: str) -> str:
    # Mirrors the same check in app.api.v1.workspaces and
    # app.api.v1.calculated_channels -- duplicated per-module to avoid a
    # circular import between routers (see app.api.v1.calculated_channels's
    # own module docstring for the same documented rationale).
    if not workspace_id or not workspace_id.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorOut(
                code="invalid_workspace",
                message="workspace_id must not be blank.",
            ).model_dump(),
        )
    return workspace_id


def _stable_id(parts: list) -> str:
    """Deterministic 12-character hex prefix, safe for use in pair_id strings."""
    payload = json.dumps(parts, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode()).hexdigest()[:12]


def _auto_display_label(pair: MatchedVIPair) -> str:
    label = f"{pair.voltage_channel_name} / {pair.current_channel_name}"
    if pair.context_hint:
        label += f" ({pair.context_hint})"
    return label


def _candidate_display_label(cand: VIPairCandidate) -> str:
    reason_text = _REASON_LABELS.get(cand.reason, cand.reason)
    if cand.context_hint:
        return f"Phase {cand.phase_token} ({cand.context_hint}) — {reason_text}"
    return f"Phase {cand.phase_token} — {reason_text}"


def _three_phase_complete_label(s: ThreePhaseAutomaticSet) -> str:
    v_names = "/".join(p.voltage_channel_name for p in (s.phase_1, s.phase_2, s.phase_3))
    i_names = "/".join(p.current_channel_name for p in (s.phase_1, s.phase_2, s.phase_3))
    label = f"{v_names} / {i_names}"
    if s.context_hint:
        label += f" ({s.context_hint})"
    return label


@router.get("", response_model=VIPairsOut)
def get_vi_pairs(
    workspace_id: str,
    source_registry: WorkspaceRegistry = Depends(get_workspace_registry),
) -> VIPairsOut:
    """Discover automatic and candidate V-I pairs for the workspace.

    Returns every V-I pair the domain resolver could identify across all
    currently-loaded sources.  Channels the resolver ignores (no role
    token, non-V/I type, line-to-line voltage) are invisible in the
    result but still counted in ``total_input_channel_count``.

    An empty or unknown workspace returns empty lists, not 404.
    """
    workspace_id = _validate_workspace_id(workspace_id)
    sources = source_registry.list_for_workspace(workspace_id)

    # Single pass: build both the unit-lookup dict and the input list.
    # Keyed by (source_id, channel_name) because channel names are unique
    # within a source but not across sources.
    unit_type_map: dict[tuple[str, str], tuple[str, str]] = {}
    pairing_inputs: list[ChannelPairingInput] = []
    for source in sources:
        sid = source.metadata.source_id
        for ch in source.metadata.analog_channels:
            unit_type_map[(sid, ch.name)] = (ch.unit, ch.engineering_type)
            pairing_inputs.append(
                ChannelPairingInput(
                    source_id=sid,
                    channel_name=ch.name,
                    engineering_type=ch.engineering_type,
                    unit=ch.unit,
                    phase_label=ch.phase,
                )
            )

    three_phase_resolution = find_three_phase_vi_sets(pairing_inputs)
    resolution = three_phase_resolution.single_phase_pairs

    # --- Automatic pairs ------------------------------------------------
    auto_out: list[AutomaticVIPairOut] = []
    for pair in resolution.automatic_pairs:
        v_unit, v_type = unit_type_map.get((pair.source_id, pair.voltage_channel_name), ("", "Voltage"))
        i_unit, i_type = unit_type_map.get((pair.source_id, pair.current_channel_name), ("", "Current"))
        auto_out.append(
            AutomaticVIPairOut(
                pair_id="auto:" + _stable_id(
                    [pair.source_id, pair.voltage_channel_name, pair.current_channel_name]
                ),
                display_label=_auto_display_label(pair),
                source_id=pair.source_id,
                voltage_channel=VIPairChannelOut(
                    source_id=pair.source_id,
                    channel_name=pair.voltage_channel_name,
                    engineering_type=v_type,
                    unit=v_unit,
                ),
                current_channel=VIPairChannelOut(
                    source_id=pair.source_id,
                    channel_name=pair.current_channel_name,
                    engineering_type=i_type,
                    unit=i_unit,
                ),
                matching_evidence=VIPairMatchEvidenceOut(
                    context_hint=pair.context_hint,
                    phase_token=pair.phase_token,
                    phase_token_kind=pair.phase_token_kind,
                ),
            )
        )

    # --- Candidates requiring confirmation ------------------------------
    cand_out: list[CandidateVIPairOut] = []
    for cand in resolution.candidates_needing_confirmation:
        v_refs = [
            VIPairChannelOut(
                source_id=r.source_id,
                channel_name=r.channel_name,
                engineering_type=unit_type_map.get((r.source_id, r.channel_name), ("", "Voltage"))[1],
                unit=unit_type_map.get((r.source_id, r.channel_name), ("", ""))[0],
            )
            for r in cand.voltage_refs
        ]
        i_refs = [
            VIPairChannelOut(
                source_id=r.source_id,
                channel_name=r.channel_name,
                engineering_type=unit_type_map.get((r.source_id, r.channel_name), ("", "Current"))[1],
                unit=unit_type_map.get((r.source_id, r.channel_name), ("", ""))[0],
            )
            for r in cand.current_refs
        ]
        cand_out.append(
            CandidateVIPairOut(
                pair_id="cand:" + _stable_id([
                    cand.context_hint,
                    cand.phase_token,
                    [(r.source_id, r.channel_name) for r in cand.voltage_refs],
                    [(r.source_id, r.channel_name) for r in cand.current_refs],
                ]),
                display_label=_candidate_display_label(cand),
                reason=cand.reason,
                voltage_refs=v_refs,
                current_refs=i_refs,
                matching_evidence=VIPairMatchEvidenceOut(
                    context_hint=cand.context_hint,
                    phase_token=cand.phase_token,
                    # phase_token_kind is not reported for candidates: a candidate
                    # may span voltages of mixed kinds, so no single authoritative
                    # value exists.
                    phase_token_kind=None,
                ),
            )
        )

    # --- Three-phase complete sets (Phase E-2C) ----------------------------
    complete_sets_out: list[ThreePhaseCompleteSetOut] = []
    for s in three_phase_resolution.complete_sets:
        pairs_out = [
            ThreePhasePairRefOut(
                phase=ph.phase_token,
                voltage_channel=VIPairChannelOut(
                    source_id=ph.source_id,
                    channel_name=ph.voltage_channel_name,
                    engineering_type=unit_type_map.get((ph.source_id, ph.voltage_channel_name), ("", "Voltage"))[1],
                    unit=unit_type_map.get((ph.source_id, ph.voltage_channel_name), ("", ""))[0],
                ),
                current_channel=VIPairChannelOut(
                    source_id=ph.source_id,
                    channel_name=ph.current_channel_name,
                    engineering_type=unit_type_map.get((ph.source_id, ph.current_channel_name), ("", "Current"))[1],
                    unit=unit_type_map.get((ph.source_id, ph.current_channel_name), ("", ""))[0],
                ),
            )
            for ph in (s.phase_1, s.phase_2, s.phase_3)
        ]
        label = _three_phase_complete_label(s)
        complete_sets_out.append(
            ThreePhaseCompleteSetOut(
                set_id=s.set_id,
                display_label=label,
                source_id=s.source_id,
                context_hint=s.context_hint,
                phase_convention=s.phase_convention,
                pairs=pairs_out,
                voltage_reference=s.voltage_reference,
                voltage_reference_reason=s.voltage_reference_reason,
                voltage_reference_evidence_names=list(s.voltage_reference_evidence_names),
                voltage_reference_confirmation_required=(
                    s.voltage_reference != "line_to_ground"
                ),
            )
        )

    # --- Three-phase incomplete sets (Phase E-2C) --------------------------
    incomplete_sets_out: list[ThreePhaseIncompleteSetOut] = []
    for s in three_phase_resolution.incomplete_sets:
        present_out = [
            ThreePhasePairRefOut(
                phase=ph.phase_token,
                voltage_channel=VIPairChannelOut(
                    source_id=ph.source_id,
                    channel_name=ph.voltage_channel_name,
                    engineering_type=unit_type_map.get((ph.source_id, ph.voltage_channel_name), ("", "Voltage"))[1],
                    unit=unit_type_map.get((ph.source_id, ph.voltage_channel_name), ("", ""))[0],
                ),
                current_channel=VIPairChannelOut(
                    source_id=ph.source_id,
                    channel_name=ph.current_channel_name,
                    engineering_type=unit_type_map.get((ph.source_id, ph.current_channel_name), ("", "Current"))[1],
                    unit=unit_type_map.get((ph.source_id, ph.current_channel_name), ("", ""))[0],
                ),
            )
            for ph in s.present_pairs
        ]
        missing_out = [
            ThreePhaseIncompletePhaseOut(phase=mp.phase_token, reason=mp.reason)
            for mp in s.missing_phases
        ]
        incomplete_sets_out.append(
            ThreePhaseIncompleteSetOut(
                source_id=s.source_id,
                context_hint=s.context_hint,
                phase_convention=s.phase_convention,
                incomplete_reason=s.incomplete_reason,
                present_pairs=present_out,
                missing_phases=missing_out,
            )
        )

    return VIPairsOut(
        automatic_pairs=auto_out,
        candidates_needing_confirmation=cand_out,
        total_input_channel_count=len(pairing_inputs),
        three_phase_complete_sets=complete_sets_out,
        three_phase_incomplete_sets=incomplete_sets_out,
    )
