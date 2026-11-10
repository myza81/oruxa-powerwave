"""Automatic Per-Unit base configuration after COMTRADE/BEN import (DEC-050 Slice 5D-2).

After ``generate_suggested_groups_for_source()`` creates measurement groups,
this service analyses the channel-level evidence from COMTRADE PS flags and
VT/CT winding ratios, then writes ``VoltageBaseConfiguration`` when evidence
is sufficient.

Design constraints (from Slice 5D-2 Final Engineering Contract):
  C1  ``secondary_measured.value_kv`` goes to ``secondary_voltage_ll_v`` (in V),
      NEVER to ``nominal_voltage_ll_kv`` (design constraint from auto_base_evidence).
  C2  ``REASON_SECONDARY_REQUIRES_REDESIGN`` in ``insufficient_reasons`` is now
      obsolete for this service -- Slice 5D-1 added ``secondary_voltage_ll_v``
      to ``VoltageBaseConfiguration``.  The service handles secondary without
      modifying ``auto_base_evidence.py`` (preserves its Slice 5A tests).
  C3  CT primary winding rating is NEVER an Ibase candidate (DEC-050 §11 / C5).
      No current-group configuration is written by this service.
  C4  Manual and legacy-manual authority is NEVER overwritten.  Engineer-set
      values survive automatic re-runs.
  C5  ``base_authority="auto_resolved"`` is set directly via the registry
      (bypassing ``update_voltage_configuration()``'s manual-only gate), as
      explicitly anticipated by that function's own docstring.
  C6  Never raises -- all exceptions are caught, logged, and surfaced in the
      result only.  An auto-base failure NEVER turns an upload into an error.
  C7  Idempotent -- safe to call multiple times on the same source.
  C8  When an optional ``waveform_provider`` callable is supplied, waveform RMS
      evidence is used to annotate the hypothesis resolution (Slice 6B) for
      transparency and provenance only.  A ``magnitude_disagreement`` verdict
      does NOT downgrade automatic authority — a voltage sag, fault, or other
      non-nominal recording condition is physically valid and does not indicate
      an incorrect nominal reference.  Only independent metadata contradictions
      (conflicting primary_ratio, conflicting side declarations, missing channel
      reference) may block automatic authority.  All waveform code is wrapped in
      try/except (C6) — a provider failure never blocks primary/secondary
      configuration.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable, Sequence

import numpy as np

from app.domain.auto_base_evidence import (
    ChannelAutoMetadata,
    resolve_voltage_group_evidence,
)
from app.domain.base_authority import (
    BASE_AUTHORITY_AUTO,
    BASE_AUTHORITY_LEGACY,
    BASE_AUTHORITY_MANUAL,
    BASE_AUTHORITY_NEEDS_REVIEW,
)
from app.domain.measurement_group import KIND_VOLTAGE
from app.services.measurement_group_registry import MeasurementGroupRegistry
from app.services.voltage_group_config_registry import VoltageGroupConfigRegistry
from app.services.workspace_registry import WorkspaceRegistry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result types (observability only — no caller currently surfaces these)
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class VoltageGroupAutoResult:
    group_id: str
    action: str   # "configured_primary" | "configured_secondary" | "needs_review"
                  # | "skipped_manual" | "skipped_no_channels" | "error"
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class AutoBaseResult:
    voltage_groups_configured: int = 0
    voltage_groups_needs_review: int = 0
    voltage_groups_skipped: int = 0
    voltage_group_details: tuple[VoltageGroupAutoResult, ...] = field(default_factory=tuple)
    error: str | None = None


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def configure_auto_bases_for_source(
    *,
    workspace_id: str,
    source_id: str,
    source_registry: WorkspaceRegistry,
    group_registry: MeasurementGroupRegistry,
    voltage_config_registry: VoltageGroupConfigRegistry,
    waveform_provider: Callable[[str, str, Sequence[str]], dict[str, tuple[np.ndarray, np.ndarray]]] | None = None,
) -> AutoBaseResult:
    """Auto-configure PU bases for voltage measurement groups of one source.

    For each voltage measurement group that belongs to this source, runs
    evidence analysis and writes ``VoltageBaseConfiguration`` with
    ``base_authority="auto_resolved"`` when evidence is sufficient.

    Never raises (C6).  Idempotent (C7).  Never overwrites manual/legacy (C4).
    Current groups are skipped entirely (C3).

    ``waveform_provider`` is an optional callable ``(workspace_id, source_id,
    channel_names) → dict[str, (time_s, values_kv)]`` for Slice 6B waveform
    corroboration (C8).  Absent means no waveform annotation.
    """
    try:
        active = source_registry.get(workspace_id, source_id)
        if active is None:
            return AutoBaseResult(error="source_not_found")

        channel_map = {ch.name: ch for ch in active.metadata.analog_channels}
        groups = group_registry.list_for_source(workspace_id, source_id)

        details: list[VoltageGroupAutoResult] = []
        configured = 0
        needs_review = 0
        skipped = 0

        for group in groups:
            if group.kind != KIND_VOLTAGE:
                continue  # C3: current groups have no auto Ibase

            try:
                result = _configure_voltage_group(
                    workspace_id=workspace_id,
                    source_id=source_id,
                    group=group,
                    channel_map=channel_map,
                    voltage_config_registry=voltage_config_registry,
                    waveform_provider=waveform_provider,
                )
            except Exception:
                logger.exception(
                    "Auto-base: failed for voltage group %s workspace %s source %s",
                    group.id, workspace_id, source_id,
                )
                result = VoltageGroupAutoResult(
                    group_id=group.id,
                    action="error",
                    reason="auto_base_configuration_error",
                )

            details.append(result)
            if result.action.startswith("configured_"):
                configured += 1
            elif result.action == "needs_review":
                needs_review += 1
            else:
                skipped += 1

        return AutoBaseResult(
            voltage_groups_configured=configured,
            voltage_groups_needs_review=needs_review,
            voltage_groups_skipped=skipped,
            voltage_group_details=tuple(details),
        )

    except Exception:
        logger.exception(
            "Auto-base: unexpected error for workspace %s source %s", workspace_id, source_id
        )
        return AutoBaseResult(error="auto_base_unexpected_error")


# ---------------------------------------------------------------------------
# Per-group helper
# ---------------------------------------------------------------------------

def _configure_voltage_group(
    *,
    workspace_id,
    source_id,
    group,
    channel_map,
    voltage_config_registry,
    waveform_provider=None,
):
    group_id = group.id

    # C4: never overwrite engineer-set authority
    existing = voltage_config_registry.get(workspace_id, group_id)
    if existing is not None and existing.base_authority in (BASE_AUTHORITY_MANUAL, BASE_AUTHORITY_LEGACY):
        return VoltageGroupAutoResult(
            group_id=group_id,
            action="skipped_manual",
            reason=f"authority_{existing.base_authority}",
        )

    # Build ChannelAutoMetadata for this group's source channels
    metadata_list: list[ChannelAutoMetadata] = []
    for ref in group.channel_refs:
        if ref.kind != "source" or ref.source_id != source_id:
            continue
        ch = channel_map.get(ref.channel_name)
        if ch is None:
            continue
        # engineering_type from AnalogChannelSummary is title-cased ("Voltage"/"Current");
        # resolve_voltage_group_evidence() lowercases before filtering, so lower() is correct.
        metadata_list.append(ChannelAutoMetadata(
            name=ch.name,
            engineering_type=(ch.engineering_type or "").lower() or None,
            unit=ch.unit,
            measurement_side=ch.measurement_side,
            primary_ratio=ch.primary_ratio,
            secondary_ratio=ch.secondary_ratio,
        ))

    if not metadata_list:
        return VoltageGroupAutoResult(
            group_id=group_id,
            action="skipped_no_channels",
            reason="no_source_channels_in_group",
        )

    # Optionally build waveform evidence for Slice 6B corroboration (C8).
    waveform_evidence = None
    if waveform_provider is not None:
        try:
            channel_names = [m.name for m in metadata_list]
            raw_waveforms = waveform_provider(workspace_id, source_id, channel_names)
            if raw_waveforms:
                from app.domain.waveform_evidence import extract_waveform_evidence  # noqa: PLC0415
                waveform_evidence = extract_waveform_evidence(raw_waveforms)
        except Exception:
            logger.warning(
                "Auto-base: waveform evidence unavailable for group %s — skipping corroboration",
                group_id,
            )

    evidence = resolve_voltage_group_evidence(
        metadata_list,
        group_name=group.display_name,
        waveform_evidence=waveform_evidence,
    )

    # --- Secondary path ---
    # C2: REASON_SECONDARY_REQUIRES_REDESIGN is now resolved by Slice 5D-1.
    # Use sufficient_for_auto_side (not sufficient_for_auto_nominal) as the gate.
    if (evidence.measurement_side == "secondary"
            and evidence.sufficient_for_auto_side
            and evidence.secondary_measured is not None):
        secondary_v = evidence.secondary_measured.value_kv * 1000.0
        # C1: secondary value → secondary_voltage_ll_v, NOT nominal_voltage_ll_kv.
        # Also set nominal if primary evidence is sufficient and consistent (best-effort).
        nominal_kv: float | None = None
        if evidence.sufficient_for_auto_nominal:
            nominal_kv = _best_candidate_kv(evidence.primary_nominal_candidates)
        voltage_config_registry.update_fields(
            workspace_id, group_id,
            nominal_voltage_ll_kv=nominal_kv,
            base_reference_side="secondary",
            base_authority=BASE_AUTHORITY_AUTO,
            secondary_voltage_ll_v=secondary_v,
            update_secondary=True,
        )
        reason = f"secondary_v={secondary_v:.4g}V"
        if nominal_kv is not None:
            reason += f",nominal={nominal_kv}kV"
        return VoltageGroupAutoResult(group_id=group_id, action="configured_secondary", reason=reason)

    # --- Primary path ---
    if evidence.measurement_side == "primary" and evidence.sufficient_for_auto_nominal:
        nominal_kv = _best_candidate_kv(evidence.primary_nominal_candidates)
        # C8: waveform corroboration is attached to hypothesis_resolution for transparency
        # only — it does NOT change authority.  A magnitude_disagreement may reflect a
        # voltage sag, fault, or other non-nominal condition in the recorded event, which
        # is physically valid and does not indicate an incorrect nominal reference.
        voltage_config_registry.update_fields(
            workspace_id, group_id,
            nominal_voltage_ll_kv=nominal_kv,
            base_reference_side="primary",
            base_authority=BASE_AUTHORITY_AUTO,
            update_secondary=True,
            secondary_voltage_ll_v=None,
        )
        return VoltageGroupAutoResult(
            group_id=group_id, action="configured_primary",
            reason=f"nominal={nominal_kv}kV",
        )

    # --- Insufficient evidence: mark needs_review ---
    # Even when the nominal voltage cannot be auto-resolved, the measurement
    # side (primary/secondary) may still be unambiguously known from PS flags.
    # Writing base_reference_side here prevents the provenance layer from
    # returning reference_compatibility="unverified" solely because the side
    # field was never written — a false "Unverified reference" warning on a
    # channel whose measurement side is entirely unambiguous (PS=P/S declared).
    insufficient = ",".join(evidence.insufficient_reasons) or "evidence_insufficient"
    side_kwargs: dict = {}
    if (evidence.measurement_side == "primary" and evidence.sufficient_for_auto_side):
        side_kwargs["base_reference_side"] = "primary"
    elif (evidence.measurement_side == "secondary" and evidence.sufficient_for_auto_side):
        side_kwargs["base_reference_side"] = "secondary"
    voltage_config_registry.update_fields(
        workspace_id, group_id,
        base_authority=BASE_AUTHORITY_NEEDS_REVIEW,
        **side_kwargs,
    )
    return VoltageGroupAutoResult(group_id=group_id, action="needs_review", reason=insufficient)


def _best_candidate_kv(candidates) -> float:
    """Return the highest-confidence candidate's kV value."""
    _priority = {"high": 0, "medium": 1, "low": 2}
    return min(candidates, key=lambda c: _priority.get(c.confidence, 99)).value_kv
