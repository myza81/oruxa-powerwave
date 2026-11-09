"""Pure-domain engineering evidence resolver (DEC-050 Slice 5A).

Accepts channel-level metadata for one candidate measurement group and
returns candidate engineering quantities with provenance. No I/O, no
registry access, no configuration mutations, no recorded-sample access.

Design constraints from Stage 1A Final Engineering Contract:
  C1  ``nominal_voltage_ll_kv`` represents the nominal primary-system L-L
      voltage. Secondary-side measured voltage is kept separate and is not
      automatically stored in that field without a compatible redesign of
      ``VoltageBaseConfiguration``.
  C2  CT/VT winding ratings (``primary_ratio``, ``secondary_ratio``) are
      transformation information. They produce candidates, not authoritative
      nominal values.
  C3  Voltage reference geometry is determined from channel names via
      ``detect_voltage_reference()``, not from VT winding topology.
  C4  Voltage-level name tokens (e.g. ``275KV``) do not establish whether
      samples are Primary or Secondary side.
  C5  CT primary winding rating is never an Ibase candidate (DEC-050 §11).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from app.domain.reference_side import ReferenceSide

if TYPE_CHECKING:
    from app.domain.voltage_hypothesis import VoltageHypothesisResolution
    from app.domain.waveform_evidence import WaveformEvidence
from app.domain.voltage_reference import (
    LINE_TO_GROUND,
    LINE_TO_LINE,
    REASON_CONFLICTING,
    REASON_NO_CHANNELS,
    detect_voltage_reference,
)

# ---------------------------------------------------------------------------
# Public type aliases
# ---------------------------------------------------------------------------

Confidence = Literal["high", "medium", "low"]

# ---------------------------------------------------------------------------
# Machine-readable reason constants
# ---------------------------------------------------------------------------

REASON_NO_NOMINAL_EVIDENCE = "no_nominal_evidence"
REASON_CONTRADICTORY_NOMINAL = "contradictory_nominal_candidates"
REASON_MIXED_SIDES = "mixed_measurement_sides"
REASON_REFERENCE_UNDETERMINED = "voltage_reference_undetermined"
REASON_REFERENCE_CONFLICTED = "voltage_reference_conflicted"
REASON_UNIT_UNRECOGNIZED = "unit_not_recognized"
REASON_CT_PRIMARY_EXCLUDED = "ct_primary_excluded_dec050_s11"
REASON_NO_EQUIPMENT_CURRENT = "no_equipment_nominal_current_in_channel_data"
REASON_SIDE_UNKNOWN = "measurement_side_unknown"
REASON_SECONDARY_REQUIRES_REDESIGN = "secondary_nominal_requires_vbc_redesign_c1"
REASON_NO_VOLTAGE_CHANNELS = "no_voltage_channels_in_group"
REASON_NO_CURRENT_CHANNELS = "no_current_channels_in_group"
REASON_NOMINAL_BELOW_MINIMUM = "nominal_below_minimum_voltage"
REASON_HYPOTHESIS_AMBIGUOUS = "hypothesis_ambiguous_needs_confirmation"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SQRT_3 = 1.7320508075688772

# Minimum realistic nominal L-L voltage (kV) accepted for automatic PU
# configuration.  primary_ratio=1.0 for a kV-unit channel (the COMTRADE
# field default meaning "not set") gives 1.73 kV L-L — below any real
# power-system voltage used in protection relay recordings and therefore
# excluded.  The threshold is set to 2.0 kV to exclude the 1.73 kV case
# while accepting all standard distribution and transmission voltages
# (11 kV and above).
_MIN_NOMINAL_LL_KV = 2.0

# Name-level kV token: matches "275KV", "132KV", "11KV", "275 KV", etc.
# Deliberately conservative — only explicit kV suffixes, word boundary on
# the left.  Does not match "kV" appearing inside a quoted unit annotation.
_NAME_KV_RE = re.compile(r"\b(\d+(?:\.\d+)?)\s*KV\b", re.IGNORECASE)

# Voltage unit normalization: how many kV is one unit of voltage
_V_UNIT_TO_KV: dict[str, float] = {"v": 1e-3, "kv": 1.0}

# Current unit normalization: how many kA is one unit of current
_I_UNIT_TO_KA: dict[str, float] = {"a": 1e-3, "ka": 1.0}

# Nominal-candidate consistency: maximum relative spread across candidates
_CONSISTENCY_TOLERANCE = 0.05  # 5 %

# ---------------------------------------------------------------------------
# Standard nominal voltage levels for L-G winding-reference disambiguation
# ---------------------------------------------------------------------------

# Power-system nominal L-L voltage levels (kV) used to determine whether a
# COMTRADE VT ``primary_ratio`` for a Line-to-Ground channel represents the
# nominal system L-L voltage directly (Convention A — the dominant encoding in
# IEC protection relay COMTRADE files) or a phase-winding voltage that needs
# × √3 correction (Convention B).  Covers IEC/EN, IEEE/ANSI and additional
# common regional levels.
_STANDARD_NOMINAL_KV: tuple[float, ...] = (
    # IEC/EN standard nominal voltages
    3.3, 6.6, 11.0, 22.0, 33.0, 66.0, 110.0, 132.0, 220.0, 275.0, 400.0, 500.0, 765.0,
    # IEEE/ANSI nominal voltages
    4.16, 13.8, 34.5, 69.0, 115.0, 138.0, 161.0, 230.0, 345.0,
    # Additional common levels (European, Asian, Australian)
    6.0, 10.0, 12.0, 15.0, 20.0, 30.0, 35.0, 60.0, 90.0, 150.0, 380.0,
)
# 2 % relative tolerance: handles minor rounding (e.g. 76.2 kV → 131.98 kV ≈ 132 kV).
_STANDARD_NOMINAL_KV_TOL = 0.02


def _is_near_standard_nominal_kv(kv: float) -> bool:
    """True when ``kv`` is within ``_STANDARD_NOMINAL_KV_TOL`` (relative) of any
    recognised power-system nominal voltage level.

    Used in Step 3b of ``resolve_voltage_group_evidence`` to disambiguate the
    winding-reference geometry of a Line-to-Ground COMTRADE channel:

    * Convention A — primary_ratio IS the nominal system L-L voltage (275 kV on a
      275 kV system).  Most common in IEC protection relay COMTRADE files.
    * Convention B — primary_ratio is a phase-winding voltage (76.2 kV for a
      132 kV system); nominal L-L = primary_ratio × √3.
    """
    for std in _STANDARD_NOMINAL_KV:
        if abs(kv - std) / std <= _STANDARD_NOMINAL_KV_TOL:
            return True
    return False


# ---------------------------------------------------------------------------
# Input type
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class ChannelAutoMetadata:
    """Format-agnostic channel descriptor for evidence resolution.

    ``primary_ratio`` and ``secondary_ratio`` are in the channel's own
    engineering unit, matching ``AnalogChannel`` convention:

    * COMTRADE 1999: CFG primary/secondary fields (same unit as channel).
    * BEN: ``primary_rating`` and ``secondary_rating_in_channel_unit``.

    ``measurement_side``:

    * ``"primary"`` / ``"secondary"`` when COMTRADE PS flag is present.
    * ``"unknown"`` for BEN, COMTRADE 1991, or absent/blank PS flag.

    These are instrument-transformer winding quantities, not authoritative
    nominal-system values (C2).
    """

    name: str
    engineering_type: str | None          # "voltage" / "current"
    unit: str | None                      # "V", "kV", "A", "kA"
    measurement_side: ReferenceSide       # "primary" / "secondary" / "unknown"
    primary_ratio: float | None           # VT/CT primary winding rating, channel unit
    secondary_ratio: float | None         # VT/CT secondary winding rating, channel unit


# ---------------------------------------------------------------------------
# Output types — Voltage
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class NominalVoltageCandidate:
    """One candidate for the nominal PRIMARY-SYSTEM L-L voltage (kV).

    Always expresses the primary power-system quantity.  Secondary-side
    measured voltage is NOT placed here (C1).  The ``derivation`` field
    describes the electrical interpretation path for transparency.
    """

    value_kv: float
    confidence: Confidence
    source: str                            # machine-readable source tag
    supporting_channels: tuple[str, ...]
    derivation: str                        # human-readable derivation path


@dataclass(frozen=True, slots=True)
class MeasuredSecondaryVoltage:
    """The measured voltage at VT secondary terminals.

    This is the VT output quantity — the voltage present at the secondary
    (measurement) side.  It is NOT a primary-system nominal and is kept
    separate from ``NominalVoltageCandidate`` per C1.

    ``primary_ll_kv_from_ratio`` is a LOW-confidence estimate of the
    primary-system nominal derived from the VT primary winding field (C2).
    A compatible redesign of ``VoltageBaseConfiguration`` is required
    before ``value_kv`` can be used for automatic secondary-side PU
    configuration.
    """

    value_kv: float                        # Normalized to kV from channel unit
    channel_reference: str | None         # "line_to_line" / "line_to_ground"
    primary_ll_kv_from_ratio: float | None  # Primary nominal from winding ratio; low confidence
    supporting_channels: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class VoltageGroupEvidence:
    """Complete engineering evidence for one candidate voltage measurement group.

    The resolver produces candidates with provenance; it does not set
    configuration values or assert automatic authority.
    """

    # Input summary
    channel_names: tuple[str, ...]

    # Measurement-side from PS flags
    measurement_side: ReferenceSide     # common side; "unknown" when mixed/absent
    side_declared: bool                 # True when ALL channels share the same non-unknown side
    side_note: str | None               # Explanation when partial or mixed

    # Channel reference geometry (from channel names, not winding topology — C3)
    channel_reference: str | None       # "line_to_line" / "line_to_ground" / None
    reference_note: str | None          # Reason when undetermined or conflicted

    # Primary-system nominal L-L voltage candidates
    primary_nominal_candidates: tuple[NominalVoltageCandidate, ...]
    primary_nominal_consistent: bool    # All candidates agree within 5 % relative tolerance

    # Secondary-side measured voltage (separate from nominal — C1)
    secondary_measured: MeasuredSecondaryVoltage | None

    # Contradiction / ambiguity flags
    has_contradictions: bool
    contradiction_reasons: tuple[str, ...]

    # Can a primary-side PU denominator be determined from available evidence?
    # True when: >= 1 primary nominal candidate, consistent, reference resolved,
    # no contradictions.
    primary_denominator_determinable: bool

    # Is evidence sufficient for automatic configuration?
    sufficient_for_auto_nominal: bool    # Can auto-configure nominal_voltage_ll_kv?
    sufficient_for_auto_side: bool       # Can auto-configure base_reference_side?
    insufficient_reasons: tuple[str, ...]

    # Multi-hypothesis resolution detail (populated for L-G groups, Slice 6B)
    hypothesis_resolution: VoltageHypothesisResolution | None = None


# ---------------------------------------------------------------------------
# Output types — Current
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class CurrentGroupEvidence:
    """Complete engineering evidence for one candidate current measurement group.

    In Slice 5A no Ibase can be automatically determined from channel
    descriptor data: CT primary winding rating is excluded per DEC-050 §11
    (C5); no other equipment-nominal current source exists in COMTRADE/BEN
    channel descriptors.
    """

    channel_names: tuple[str, ...]

    measurement_side: ReferenceSide
    side_declared: bool
    side_note: str | None

    # CT winding ratings — present in data, excluded from Ibase use (C5)
    ct_primary_ratings_ka: tuple[float, ...]   # Excluded values, retained for transparency
    ct_primary_excluded: bool                  # True when any ratings are present

    # Always False in Slice 5A — no auto-Ibase from channel descriptors
    sufficient_for_auto_ibase: bool
    insufficient_reasons: tuple[str, ...]

    has_contradictions: bool
    contradiction_reasons: tuple[str, ...]


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _to_kv(value: float | None, unit: str | None) -> float | None:
    """Normalize a voltage value to kV.  Returns None for unrecognized units."""
    if value is None or not math.isfinite(value) or value <= 0:
        return None
    key = (unit or "").strip().lower()
    scale = _V_UNIT_TO_KV.get(key)
    return value * scale if scale is not None else None


def _to_ka(value: float | None, unit: str | None) -> float | None:
    """Normalize a current value to kA.  Returns None for unrecognized units."""
    if value is None or not math.isfinite(value) or value <= 0:
        return None
    key = (unit or "").strip().lower()
    scale = _I_UNIT_TO_KA.get(key)
    return value * scale if scale is not None else None


def _extract_name_kv_tokens(names: tuple[str, ...]) -> list[tuple[float, str]]:
    """Find (kv_value, channel_name) pairs for channels with explicit kV tokens."""
    results = []
    for name in names:
        m = _NAME_KV_RE.search(name)
        if m:
            try:
                kv = float(m.group(1))
                if kv > 0 and math.isfinite(kv):
                    results.append((kv, name))
            except ValueError:
                pass
    return results


def _candidates_consistent(values_kv: list[float]) -> bool:
    """True when all values agree within _CONSISTENCY_TOLERANCE (relative)."""
    if len(values_kv) <= 1:
        return True
    low, high = min(values_kv), max(values_kv)
    if high <= 0:
        return False
    return (high - low) / high <= _CONSISTENCY_TOLERANCE


def _common_side(
    sides: list[ReferenceSide],
) -> tuple[ReferenceSide, bool, str | None]:
    """Return (common_side, side_declared, note).

    ``side_declared`` is True only when every channel in the group has
    the same non-unknown side (all carry consistent PS flags).  When some
    channels lack a PS flag (mix of known + unknown), the common known
    side is returned but ``side_declared`` is False.  When sides conflict
    (primary vs secondary), returns ``("unknown", False, REASON_MIXED_SIDES)``.
    """
    known = [s for s in sides if s != "unknown"]
    if not known:
        return "unknown", False, None
    unique_known = set(known)
    if len(unique_known) > 1:
        return "unknown", False, REASON_MIXED_SIDES
    common = unique_known.pop()
    all_declared = all(s != "unknown" for s in sides)
    note = None if all_declared else REASON_SIDE_UNKNOWN
    return common, all_declared, note


# ---------------------------------------------------------------------------
# Main resolvers
# ---------------------------------------------------------------------------

def resolve_voltage_group_evidence(
    channels: list[ChannelAutoMetadata],
    *,
    group_name: str | None = None,
    waveform_evidence: WaveformEvidence | None = None,
) -> VoltageGroupEvidence:
    """Resolve engineering evidence for a candidate voltage measurement group.

    Accepts ``ChannelAutoMetadata`` for every channel in the candidate group.
    Channels with ``engineering_type != "voltage"`` are silently excluded
    (a group may contain mixed types if the caller has not pre-filtered).

    Args:
        channels: Channel metadata list.
        group_name: Optional group/source name forwarded to the multi-hypothesis
            resolver for kV-token corroboration (Slice 6B).
        waveform_evidence: Optional waveform evidence forwarded to the resolver
            as a corroboration annotation (Slice 6B).  Waveform evidence does
            NOT change the nominal candidate selected; it is advisory only.

    Returns ``VoltageGroupEvidence`` with candidates, provenance, and
    sufficiency flags.  Does not modify configuration or assert authority.
    """
    voltage_chs = [c for c in channels if (c.engineering_type or "").lower() == "voltage"]

    if not voltage_chs:
        return VoltageGroupEvidence(
            channel_names=tuple(c.name for c in channels),
            measurement_side="unknown", side_declared=False, side_note=None,
            channel_reference=None, reference_note=REASON_NO_VOLTAGE_CHANNELS,
            primary_nominal_candidates=(),
            primary_nominal_consistent=True,
            secondary_measured=None,
            has_contradictions=False,
            contradiction_reasons=(REASON_NO_VOLTAGE_CHANNELS,),
            primary_denominator_determinable=False,
            sufficient_for_auto_nominal=False,
            sufficient_for_auto_side=False,
            insufficient_reasons=(REASON_NO_VOLTAGE_CHANNELS,),
        )

    channel_names = tuple(c.name for c in voltage_chs)

    # --- Step 1: measurement-side determination ---
    sides = [c.measurement_side for c in voltage_chs]
    measurement_side, side_declared, side_note = _common_side(sides)

    # --- Step 2: channel reference geometry (from names, not winding topology — C3) ---
    ref_det = detect_voltage_reference(list(channel_names))
    channel_reference = ref_det.reference
    if ref_det.reason == REASON_CONFLICTING:
        reference_note = REASON_REFERENCE_CONFLICTED
    elif channel_reference is None:
        reference_note = REASON_REFERENCE_UNDETERMINED
    else:
        reference_note = None

    # --- Step 3: primary-system nominal candidates ---
    primary_candidates: list[NominalVoltageCandidate] = []

    # 3a. Name tokens: medium confidence; do NOT establish measurement side (C4)
    name_tokens = _extract_name_kv_tokens(channel_names)
    if name_tokens:
        kv_vals_tok = [kv for kv, _ in name_tokens]
        supporting_tok = tuple(n for _, n in name_tokens)
        if _candidates_consistent(kv_vals_tok):
            primary_candidates.append(NominalVoltageCandidate(
                value_kv=kv_vals_tok[0],
                confidence="medium",
                source="name_token",
                supporting_channels=supporting_tok,
                derivation=(
                    f"Nominal voltage-level token extracted from channel name(s): "
                    f"{', '.join(supporting_tok)}.  "
                    f"Does not establish measurement side (C4)."
                ),
            ))

    # 3b. VT primary winding field (geometry-corrected) — C2: transformation data
    #
    # For L-L channels: primary_ratio is already the L-L voltage, used directly.
    #
    # For L-G channels: primary_ratio may encode the nominal system L-L voltage
    # directly (Convention A, IEC dominant) or a phase-winding voltage needing
    # × √3 correction (Convention B).  Disambiguation is delegated to the
    # multi-hypothesis resolver (Slice 6B), which evaluates both hypotheses
    # against standard-nominal tables, name tokens, group name tokens, and VT
    # winding ratio plausibility.  When both hypotheses remain plausible (e.g.
    # 132.0 kV on L-G channels, which matches both IEC 132 kV and ANSI 230 kV),
    # the resolver returns "ambiguous" and no winding candidate is generated —
    # ``REASON_HYPOTHESIS_AMBIGUOUS`` is added to insufficient_reasons.
    winding_cand_kvs: list[float] = []
    winding_cand_chs: list[str] = []
    unit_unrecognized_chs: list[str] = []
    _lg_convention: str | None = None  # "direct" (A) | "sqrt3" (B); for backward compat
    _hypothesis_resolution_result = None  # VoltageHypothesisResolution | None
    _hyp_ambiguous_reason = False        # True when resolver returns "ambiguous"

    for ch in voltage_chs:
        if ch.primary_ratio is None:
            continue
        kv = _to_kv(ch.primary_ratio, ch.unit)
        if kv is None:
            unit_unrecognized_chs.append(ch.name)
            continue
        if channel_reference == LINE_TO_LINE:
            winding_cand_kvs.append(kv)
            winding_cand_chs.append(ch.name)
        # L-G and None-reference cases handled by the hypothesis resolver below

    if channel_reference == LINE_TO_GROUND and voltage_chs:
        # Delegate L-G disambiguation to the multi-hypothesis resolver (Slice 6B).
        # Local import avoids a circular dependency (voltage_hypothesis imports from here).
        from app.domain.voltage_hypothesis import evaluate_voltage_hypotheses as _eval_hyp  # noqa: PLC0415
        _hypothesis_resolution_result = _eval_hyp(
            voltage_chs,
            group_name=group_name,
            waveform_evidence=waveform_evidence,
        )
        hyp_res = _hypothesis_resolution_result
        if hyp_res.selected in ("A", "B") and hyp_res.nominal_ll_kv is not None:
            nominal_kv_resolved = hyp_res.nominal_ll_kv
            if nominal_kv_resolved >= _MIN_NOMINAL_LL_KV:
                winding_cand_kvs.append(nominal_kv_resolved)
                winding_cand_chs.extend(list(channel_names))
                _lg_convention = "direct" if hyp_res.selected == "A" else "sqrt3"
        elif hyp_res.is_ambiguous:
            _hyp_ambiguous_reason = True

    winding_inconsistent = False
    if winding_cand_kvs and _candidates_consistent(winding_cand_kvs):
        # Build source tag and human-readable reference text based on geometry.
        if channel_reference == LINE_TO_LINE:
            ref_text = "L-L"
            source_tag = "comtrade_primary_ll"
        elif _lg_convention == "direct":
            # Convention A: the raw primary_ratio IS the nominal L-L voltage.
            ref_text = "L-L (nominal system voltage, Convention A via multi-hypothesis)"
            source_tag = "comtrade_primary_ll"
        elif _lg_convention == "sqrt3":
            # Convention B: phase-winding voltage corrected by × √3.
            ref_text = "L-G × √3 (Convention B via multi-hypothesis)"
            source_tag = "comtrade_primary_lg"
        else:
            ref_text = "L-L"
            source_tag = "comtrade_primary_ll"

        # Confidence from hypothesis resolver when available; fall back to measurement-side.
        if _hypothesis_resolution_result is not None and _hypothesis_resolution_result.confidence:
            hyp_conf = _hypothesis_resolution_result.confidence
            confidence: Confidence = hyp_conf if hyp_conf in ("high", "medium", "low") else "medium"
        elif measurement_side == "primary":
            confidence = "medium"
        else:
            confidence = "low"

        if measurement_side == "primary":
            deriv = (
                f"VT primary winding rating ({ref_text}), PS='P' — primary-side declaration "
                f"(C2: transformation data, treated as candidate)."
            )
        elif measurement_side == "secondary":
            confidence = "low"
            deriv = (
                f"VT primary winding rating ({ref_text}), PS='S' — primary-side winding "
                f"of a secondary-side recording.  Low confidence (C2).  "
                f"Note C1: for PU use secondary_measured, not this value."
            )
        else:
            confidence = "low"
            deriv = (
                f"VT primary winding rating ({ref_text}), no PS flag — measurement side "
                f"unknown (C4).  Low confidence (C2)."
            )
        primary_candidates.append(NominalVoltageCandidate(
            value_kv=winding_cand_kvs[0],
            confidence=confidence,
            source=source_tag,
            supporting_channels=tuple(winding_cand_chs),
            derivation=deriv,
        ))
    elif len(winding_cand_kvs) > 1 and not _candidates_consistent(winding_cand_kvs):
        # Channels in the same group declare contradictory primary winding ratings
        winding_inconsistent = True

    # --- Step 4: secondary measured voltage (separate from nominal — C1) ---
    secondary_measured: MeasuredSecondaryVoltage | None = None
    if measurement_side == "secondary":
        sec_kvs: list[tuple[float, str]] = []
        for ch in voltage_chs:
            if ch.measurement_side != "secondary":
                continue
            kv = _to_kv(ch.secondary_ratio, ch.unit)
            if kv is not None:
                sec_kvs.append((kv, ch.name))
        if sec_kvs and _candidates_consistent([kv for kv, _ in sec_kvs]):
            sec_kv = sec_kvs[0][0]
            # Primary nominal from winding ratio — same Convention A/B geometry as step 3b.
            pri_ll: float | None = None
            pri_kvs = [kv for kv, _ in [(
                _to_kv(ch.primary_ratio, ch.unit), ch.name
            ) for ch in voltage_chs if ch.measurement_side == "secondary"] if kv is not None]
            if pri_kvs and _candidates_consistent(pri_kvs):
                raw_pri = pri_kvs[0]
                if channel_reference == LINE_TO_LINE:
                    pri_ll = raw_pri
                elif channel_reference == LINE_TO_GROUND:
                    # Reuse the multi-hypothesis resolution from Step 3b when available;
                    # fall back to the standard-nominal heuristic for edge cases.
                    if (
                        _hypothesis_resolution_result is not None
                        and _hypothesis_resolution_result.selected in ("A", "B")
                        and _hypothesis_resolution_result.nominal_ll_kv is not None
                    ):
                        pri_ll = _hypothesis_resolution_result.nominal_ll_kv
                    else:
                        _near_direct = _is_near_standard_nominal_kv(raw_pri)
                        _near_sqrt3 = _is_near_standard_nominal_kv(raw_pri * SQRT_3)
                        if _near_direct:
                            pri_ll = raw_pri           # Convention A: L-L nominal directly
                        elif _near_sqrt3:
                            pri_ll = raw_pri * SQRT_3  # Convention B: phase-winding × √3
                        # else: ambiguous — pri_ll stays None
            secondary_measured = MeasuredSecondaryVoltage(
                value_kv=sec_kv,
                channel_reference=channel_reference,
                primary_ll_kv_from_ratio=pri_ll,
                supporting_channels=tuple(ch for _, ch in sec_kvs),
            )

    # --- Step 5: candidate consistency ---
    all_candidate_kvs = [c.value_kv for c in primary_candidates]
    primary_nominal_consistent = _candidates_consistent(all_candidate_kvs)

    # --- Step 6: contradiction detection ---
    contradiction_reasons: list[str] = []
    if side_note == REASON_MIXED_SIDES:
        contradiction_reasons.append(REASON_MIXED_SIDES)
    if reference_note == REASON_REFERENCE_CONFLICTED:
        contradiction_reasons.append(REASON_REFERENCE_CONFLICTED)
    if not primary_nominal_consistent and len(all_candidate_kvs) > 1:
        contradiction_reasons.append(REASON_CONTRADICTORY_NOMINAL)
    # Name tokens within the same group that disagree
    name_tok_kvs = [kv for kv, _ in name_tokens]
    if len(name_tok_kvs) > 1 and not _candidates_consistent(name_tok_kvs):
        if REASON_CONTRADICTORY_NOMINAL not in contradiction_reasons:
            contradiction_reasons.append(REASON_CONTRADICTORY_NOMINAL)
    # Winding ratios within the same group that disagree (computed but inconsistent)
    if winding_inconsistent and REASON_CONTRADICTORY_NOMINAL not in contradiction_reasons:
        contradiction_reasons.append(REASON_CONTRADICTORY_NOMINAL)
    has_contradictions = bool(contradiction_reasons)

    # --- Step 7: primary denominator determinability ---
    primary_denominator_determinable = (
        bool(primary_candidates)
        and primary_nominal_consistent
        and channel_reference is not None
        and not has_contradictions
    )

    # --- Step 8: sufficiency ---
    insufficient_reasons: list[str] = []
    if not primary_candidates:
        insufficient_reasons.append(REASON_NO_NOMINAL_EVIDENCE)
    elif not primary_nominal_consistent:
        insufficient_reasons.append(REASON_CONTRADICTORY_NOMINAL)
    if channel_reference is None:
        insufficient_reasons.append(reference_note or REASON_REFERENCE_UNDETERMINED)
    for r in contradiction_reasons:
        if r not in insufficient_reasons:
            insufficient_reasons.append(r)
    if unit_unrecognized_chs and not primary_candidates:
        # All winding data present but units unrecognized — no candidates from winding
        if REASON_UNIT_UNRECOGNIZED not in insufficient_reasons:
            insufficient_reasons.append(REASON_UNIT_UNRECOGNIZED)
    if measurement_side == "unknown" and REASON_SIDE_UNKNOWN not in insufficient_reasons:
        insufficient_reasons.append(REASON_SIDE_UNKNOWN)
    if measurement_side == "secondary" and secondary_measured is not None:
        if REASON_SECONDARY_REQUIRES_REDESIGN not in insufficient_reasons:
            insufficient_reasons.append(REASON_SECONDARY_REQUIRES_REDESIGN)
    if _hyp_ambiguous_reason and REASON_HYPOTHESIS_AMBIGUOUS not in insufficient_reasons:
        insufficient_reasons.append(REASON_HYPOTHESIS_AMBIGUOUS)

    # sufficient_for_auto_nominal: needs ≥ 1 medium/high candidate, consistent, reference
    # resolved, no contradictions, and nominal voltage >= _MIN_NOMINAL_LL_KV.
    # The minimum-voltage gate excludes primary_ratio=1.0 kV (COMTRADE default field
    # value meaning "not set"), which resolves to 1.73 kV L-L — not a real system voltage.
    _eligible = [
        c for c in primary_candidates
        if c.confidence in ("high", "medium") and c.value_kv >= _MIN_NOMINAL_LL_KV
    ]
    if not _eligible and any(c.confidence in ("high", "medium") for c in primary_candidates):
        insufficient_reasons.append(REASON_NOMINAL_BELOW_MINIMUM)
    sufficient_for_auto_nominal = (
        bool(primary_candidates)
        and primary_nominal_consistent
        and channel_reference is not None
        and not has_contradictions
        and bool(_eligible)
    )
    sufficient_for_auto_side = side_declared and measurement_side != "unknown"

    return VoltageGroupEvidence(
        channel_names=channel_names,
        measurement_side=measurement_side,
        side_declared=side_declared,
        side_note=side_note,
        channel_reference=channel_reference,
        reference_note=reference_note,
        primary_nominal_candidates=tuple(primary_candidates),
        primary_nominal_consistent=primary_nominal_consistent,
        secondary_measured=secondary_measured,
        has_contradictions=has_contradictions,
        contradiction_reasons=tuple(contradiction_reasons),
        primary_denominator_determinable=primary_denominator_determinable,
        sufficient_for_auto_nominal=sufficient_for_auto_nominal,
        sufficient_for_auto_side=sufficient_for_auto_side,
        insufficient_reasons=tuple(insufficient_reasons),
        hypothesis_resolution=_hypothesis_resolution_result,
    )


def resolve_current_group_evidence(
    channels: list[ChannelAutoMetadata],
) -> CurrentGroupEvidence:
    """Resolve engineering evidence for a candidate current measurement group.

    In Slice 5A, no Ibase can be automatically determined from channel
    descriptor data:

    * CT primary winding rating (``primary_ratio`` on a current channel) is
      explicitly excluded per DEC-050 §11 and C5.
    * No equipment nominal current source exists in COMTRADE/BEN channel
      descriptors.

    The CT winding ratings are retained in the output for transparency.
    Returns ``CurrentGroupEvidence`` with provenance and sufficiency flags.
    """
    current_chs = [c for c in channels if (c.engineering_type or "").lower() == "current"]

    if not current_chs:
        return CurrentGroupEvidence(
            channel_names=tuple(c.name for c in channels),
            measurement_side="unknown", side_declared=False, side_note=None,
            ct_primary_ratings_ka=(),
            ct_primary_excluded=False,
            sufficient_for_auto_ibase=False,
            insufficient_reasons=(REASON_NO_CURRENT_CHANNELS,),
            has_contradictions=False,
            contradiction_reasons=(REASON_NO_CURRENT_CHANNELS,),
        )

    channel_names = tuple(c.name for c in current_chs)

    # --- Measurement-side ---
    sides = [c.measurement_side for c in current_chs]
    measurement_side, side_declared, side_note = _common_side(sides)

    # --- CT winding ratings (excluded from Ibase per C5 / DEC-050 §11) ---
    ct_ka_values: list[float] = []
    for ch in current_chs:
        ka = _to_ka(ch.primary_ratio, ch.unit)
        if ka is not None:
            ct_ka_values.append(ka)

    ct_primary_excluded = bool(ct_ka_values)

    # --- Contradiction detection ---
    contradiction_reasons: list[str] = []
    if side_note == REASON_MIXED_SIDES:
        contradiction_reasons.append(REASON_MIXED_SIDES)
    has_contradictions = bool(contradiction_reasons)

    # --- Insufficient reasons ---
    insufficient_reasons: list[str] = [REASON_NO_EQUIPMENT_CURRENT]
    if ct_primary_excluded:
        insufficient_reasons.append(REASON_CT_PRIMARY_EXCLUDED)
    for r in contradiction_reasons:
        if r not in insufficient_reasons:
            insufficient_reasons.append(r)

    return CurrentGroupEvidence(
        channel_names=channel_names,
        measurement_side=measurement_side,
        side_declared=side_declared,
        side_note=side_note,
        ct_primary_ratings_ka=tuple(ct_ka_values),
        ct_primary_excluded=ct_primary_excluded,
        sufficient_for_auto_ibase=False,
        insufficient_reasons=tuple(insufficient_reasons),
        has_contradictions=has_contradictions,
        contradiction_reasons=tuple(contradiction_reasons),
    )
