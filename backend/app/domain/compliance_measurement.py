"""Compliance & Capability -- Voltage Measurement normalization (Slice 2;
see docs/project-memory/COMPLIANCE_CAPABILITY.md and
docs/project-memory/PER_UNIT_MEASUREMENT_MODEL.md).

Pure, framework-free domain layer -- no registry access, no waveform
fetch, matching this codebase's established `app.domain` layer contract
(see `app.domain.phasor`/`app.domain.sequence_components`). This module
owns exactly two things:

1. The Voltage assessment-quantity catalogue (Slice 2's fixed v1 list --
   task's own explicit "adapt naming to existing project conventions").
2. `compute_voltage_quantity_value()` -- the one pure transform from
   already-resolved per-phase RMS phasors (magnitude + optional angle)
   to the requested quantity's own normalized value. It never touches a
   waveform, a registry, or a specific `analysis_time`; producing the
   phasors it consumes is the SERVICE layer's job
   (`app.services.compliance_measurement_service`), which is also the
   only place allowed to call `app.domain.phasor.estimate_phasor()` or
   `app.domain.sequence_components.compute_symmetrical_components()`.
   This split keeps this module's own golden tests (docs task section
   22) simple, deterministic, and independent of any waveform fixture.

**Governing rule (task section 8, owner/architecture instruction): never
a blind `VLL = sqrt(3) * VLN` shortcut.** A derived line-line quantity
(no direct Vab/Vbc/Vca channel available) is only ever computed from two
genuine complex phase phasors (`Vab = Va - Vb`), which requires BOTH
phases' own angle to be known -- i.e. both must have been estimated from
an instantaneous waveform. An already-RMS-only input (magnitude with no
angle) can never be combined this way; see `compute_voltage_quantity_
value()`'s own `STATUS_UNSUPPORTED_REPRESENTATION` branch. The identical
angle requirement applies to Positive Sequence (the Fortescue transform
is meaningless without genuine phase-angle relationships between the
three phases).

**This module does not implement Reference Layers, Event Alignment, or
compliance evaluation** -- it only establishes the canonical assessment
quantity and its normalized value, which a later slice's reference
profiles will consume (task section 3/17). It does not decide, and has
no opinion on, per-unit basis -- that stays entirely inside
`app.domain.per_unit`/`app.domain.voltage_group_config`, applied by the
service layer on top of this module's own engineering-unit result
(task section 12's "normalization order").
"""

from __future__ import annotations

import cmath
import math
from dataclasses import dataclass

from app.domain.sequence_components import compute_symmetrical_components

#: Canonical single-phase-or-pair role keys this module understands --
#: deliberately the exact same vocabulary `app.domain.phase_identity`
#: already established (`PHASE_A`/`PHASE_B`/`PHASE_C`/`PHASE_AB`/
#: `PHASE_BC`/`PHASE_CA`), re-declared here as plain string constants
#: rather than imported, so this pure domain module has zero dependency
#: on the Engineering Context feature area at all (see this module's own
#: sibling, `app.services.compliance_measurement_service`, for why
#: Compliance deliberately never becomes an Engineering Context consumer
#: -- DEC-100 -- even though it reuses that feature's own detection
#: ALGORITHM).
ROLE_A = "A"
ROLE_B = "B"
ROLE_C = "C"
ROLE_AB = "AB"
ROLE_BC = "BC"
ROLE_CA = "CA"

#: Voltage representation -- what ELECTRICAL quantity the assessment
#: value actually is (PER_UNIT_MEASUREMENT_MODEL.md section 6/7: L-G and
#: L-L are first-class and must never be conflated).
VOLTAGE_REPRESENTATION_LINE_TO_GROUND = "line_to_ground"
VOLTAGE_REPRESENTATION_LINE_TO_LINE = "line_to_line"
VOLTAGE_REPRESENTATION_MIN_PHASE = "min_phase"
VOLTAGE_REPRESENTATION_MAX_PHASE = "max_phase"
VOLTAGE_REPRESENTATION_POSITIVE_SEQUENCE = "positive_sequence"

#: How the assessment value was arrived at from the raw recording (task
#: section 5/6). `direct_rms` means the recording is already an RMS/
#: magnitude channel -- the method that produced it is source-defined
#: and NOT claimed to be a fundamental-frequency estimate (task section
#: 6's own explicit "RMS method: Source-defined / unspecified" wording).
VALUE_REPRESENTATION_FUNDAMENTAL_RMS = "fundamental_rms"
VALUE_REPRESENTATION_DIRECT_RMS = "direct_rms"

#: Guardrail states (task section 16) -- deliberately the exact five the
#: task enumerates, never a generic "error".
STATUS_AVAILABLE = "available"
STATUS_MISSING_INPUTS = "missing_inputs"
STATUS_AMBIGUOUS_METADATA = "ambiguous_measurement_metadata"
STATUS_UNSUPPORTED_REPRESENTATION = "unsupported_representation"
STATUS_INVALID_BASE = "invalid_base"
KNOWN_STATUSES = (
    STATUS_AVAILABLE,
    STATUS_MISSING_INPUTS,
    STATUS_AMBIGUOUS_METADATA,
    STATUS_UNSUPPORTED_REPRESENTATION,
    STATUS_INVALID_BASE,
)


@dataclass(frozen=True, slots=True)
class ComplianceVoltageQuantity:
    """One entry of the fixed v1 catalogue (task section 2). `required_
    single_phase_roles` are the canonical phase roles that must resolve
    for this quantity to be computable; `direct_pair_role` (line-line
    quantities only) is the SINGLE paired-channel role (e.g. `"AB"`)
    that, if directly present as its own recorded/identified channel,
    satisfies this quantity WITHOUT needing to derive it from two
    single-phase roles at all (task section 11 -- "preserve actual
    measurement identity... do not derive arbitrary L-G quantities from
    L-L measurements" implies the converse too: prefer a genuine direct
    L-L reading over a derived one when both exist)."""

    id: str
    display_label: str
    voltage_representation: str
    required_single_phase_roles: tuple[str, ...]
    direct_pair_role: str | None = None


QUANTITY_PHASE_A_LG_RMS = "phase_a_lg_rms"
QUANTITY_PHASE_B_LG_RMS = "phase_b_lg_rms"
QUANTITY_PHASE_C_LG_RMS = "phase_c_lg_rms"
QUANTITY_PHASE_AB_LL_RMS = "phase_ab_ll_rms"
QUANTITY_PHASE_BC_LL_RMS = "phase_bc_ll_rms"
QUANTITY_PHASE_CA_LL_RMS = "phase_ca_ll_rms"
QUANTITY_MIN_PHASE_LG_RMS = "min_phase_lg_rms"
QUANTITY_MAX_PHASE_LG_RMS = "max_phase_lg_rms"
QUANTITY_POSITIVE_SEQUENCE_RMS = "positive_sequence_rms"

#: Display order == dropdown order == task section 2's own catalogue
#: order.
VOLTAGE_QUANTITIES: tuple[ComplianceVoltageQuantity, ...] = (
    ComplianceVoltageQuantity(
        id=QUANTITY_PHASE_A_LG_RMS, display_label="Phase A Voltage",
        voltage_representation=VOLTAGE_REPRESENTATION_LINE_TO_GROUND,
        required_single_phase_roles=(ROLE_A,),
    ),
    ComplianceVoltageQuantity(
        id=QUANTITY_PHASE_B_LG_RMS, display_label="Phase B Voltage",
        voltage_representation=VOLTAGE_REPRESENTATION_LINE_TO_GROUND,
        required_single_phase_roles=(ROLE_B,),
    ),
    ComplianceVoltageQuantity(
        id=QUANTITY_PHASE_C_LG_RMS, display_label="Phase C Voltage",
        voltage_representation=VOLTAGE_REPRESENTATION_LINE_TO_GROUND,
        required_single_phase_roles=(ROLE_C,),
    ),
    ComplianceVoltageQuantity(
        id=QUANTITY_PHASE_AB_LL_RMS, display_label="Line-Line AB Voltage",
        voltage_representation=VOLTAGE_REPRESENTATION_LINE_TO_LINE,
        required_single_phase_roles=(ROLE_A, ROLE_B), direct_pair_role=ROLE_AB,
    ),
    ComplianceVoltageQuantity(
        id=QUANTITY_PHASE_BC_LL_RMS, display_label="Line-Line BC Voltage",
        voltage_representation=VOLTAGE_REPRESENTATION_LINE_TO_LINE,
        required_single_phase_roles=(ROLE_B, ROLE_C), direct_pair_role=ROLE_BC,
    ),
    ComplianceVoltageQuantity(
        id=QUANTITY_PHASE_CA_LL_RMS, display_label="Line-Line CA Voltage",
        voltage_representation=VOLTAGE_REPRESENTATION_LINE_TO_LINE,
        required_single_phase_roles=(ROLE_C, ROLE_A), direct_pair_role=ROLE_CA,
    ),
    ComplianceVoltageQuantity(
        id=QUANTITY_MIN_PHASE_LG_RMS, display_label="Minimum Three-Phase Voltage",
        voltage_representation=VOLTAGE_REPRESENTATION_MIN_PHASE,
        required_single_phase_roles=(ROLE_A, ROLE_B, ROLE_C),
    ),
    ComplianceVoltageQuantity(
        id=QUANTITY_MAX_PHASE_LG_RMS, display_label="Maximum Three-Phase Voltage",
        voltage_representation=VOLTAGE_REPRESENTATION_MAX_PHASE,
        required_single_phase_roles=(ROLE_A, ROLE_B, ROLE_C),
    ),
    ComplianceVoltageQuantity(
        id=QUANTITY_POSITIVE_SEQUENCE_RMS, display_label="Positive Sequence Voltage",
        voltage_representation=VOLTAGE_REPRESENTATION_POSITIVE_SEQUENCE,
        required_single_phase_roles=(ROLE_A, ROLE_B, ROLE_C),
    ),
)

_QUANTITIES_BY_ID: dict[str, ComplianceVoltageQuantity] = {q.id: q for q in VOLTAGE_QUANTITIES}


def get_voltage_quantity(quantity_id: str) -> ComplianceVoltageQuantity | None:
    return _QUANTITIES_BY_ID.get(quantity_id)


@dataclass(frozen=True, slots=True)
class RolePhasor:
    """One resolved role's own already-computed engineering-unit RMS
    value. `angle_deg` is `None` when the source channel is already-RMS
    (no angle information exists to derive) -- present only when the
    value was itself produced by `app.domain.phasor.estimate_phasor()`
    from an instantaneous waveform."""

    magnitude: float
    angle_deg: float | None = None


@dataclass(frozen=True, slots=True)
class QuantityValueResult:
    status: str  # STATUS_AVAILABLE | STATUS_UNSUPPORTED_REPRESENTATION
    magnitude: float | None
    angle_deg: float | None
    reason_code: str | None = None
    message: str | None = None


def _to_complex(magnitude: float, angle_deg: float) -> complex:
    return cmath.rect(magnitude, math.radians(angle_deg))


def _to_magnitude_angle(value: complex) -> tuple[float, float]:
    magnitude, angle_rad = cmath.polar(value)
    return magnitude, math.degrees(angle_rad)


def compute_voltage_quantity_value(
    quantity: ComplianceVoltageQuantity,
    role_phasors: dict[str, RolePhasor],
    *,
    used_direct_pair: bool,
) -> QuantityValueResult:
    """Computes the requested quantity's own normalized magnitude (+
    angle, where the quantity has one meaningful single value) from
    already-resolved role phasors. Callers (the service layer) are
    responsible for having already confirmed every required role is
    present in `role_phasors` -- this function assumes availability, it
    only decides HOW to combine what it is given, and whether that
    combination is representationally valid (angle-dependent derivations
    reject an angle-less, already-RMS input rather than guess).

    `used_direct_pair` is `True` only for a line-line quantity whose
    `direct_pair_role` channel was itself found and resolved -- in that
    case `role_phasors` is expected to carry exactly that one pair role,
    used verbatim, never re-derived from two single-phase roles even if
    they also happen to be available (task section 11: preserve actual
    measurement identity).
    """
    rep = quantity.voltage_representation

    if rep == VOLTAGE_REPRESENTATION_LINE_TO_GROUND:
        role = quantity.required_single_phase_roles[0]
        value = role_phasors[role]
        return QuantityValueResult(status=STATUS_AVAILABLE, magnitude=value.magnitude, angle_deg=value.angle_deg)

    if rep == VOLTAGE_REPRESENTATION_LINE_TO_LINE:
        if used_direct_pair:
            value = role_phasors[quantity.direct_pair_role]
            return QuantityValueResult(status=STATUS_AVAILABLE, magnitude=value.magnitude, angle_deg=value.angle_deg)
        role_a, role_b = quantity.required_single_phase_roles
        phasor_a, phasor_b = role_phasors[role_a], role_phasors[role_b]
        if phasor_a.angle_deg is None or phasor_b.angle_deg is None:
            return QuantityValueResult(
                status=STATUS_UNSUPPORTED_REPRESENTATION, magnitude=None, angle_deg=None,
                reason_code="line_line_requires_phasor_angle",
                message=(
                    f"{quantity.display_label} must be derived from simultaneous complex phase phasors "
                    f"(V{role_a}{role_b} = V{role_a} - V{role_b}), which requires phase-angle information. "
                    f"At least one of Phase {role_a}/Phase {role_b} is an already-RMS magnitude-only input with "
                    "no angle -- deriving line-line voltage from it would require assuming a balanced system "
                    "(e.g. VLL = sqrt(3) x VLN), which is not valid during a disturbance."
                ),
            )
        derived = _to_complex(phasor_a.magnitude, phasor_a.angle_deg) - _to_complex(phasor_b.magnitude, phasor_b.angle_deg)
        magnitude, angle_deg = _to_magnitude_angle(derived)
        return QuantityValueResult(status=STATUS_AVAILABLE, magnitude=magnitude, angle_deg=angle_deg)

    if rep in (VOLTAGE_REPRESENTATION_MIN_PHASE, VOLTAGE_REPRESENTATION_MAX_PHASE):
        magnitudes = [role_phasors[role].magnitude for role in (ROLE_A, ROLE_B, ROLE_C)]
        magnitude = min(magnitudes) if rep == VOLTAGE_REPRESENTATION_MIN_PHASE else max(magnitudes)
        return QuantityValueResult(status=STATUS_AVAILABLE, magnitude=magnitude, angle_deg=None)

    if rep == VOLTAGE_REPRESENTATION_POSITIVE_SEQUENCE:
        phasor_a, phasor_b, phasor_c = role_phasors[ROLE_A], role_phasors[ROLE_B], role_phasors[ROLE_C]
        if phasor_a.angle_deg is None or phasor_b.angle_deg is None or phasor_c.angle_deg is None:
            return QuantityValueResult(
                status=STATUS_UNSUPPORTED_REPRESENTATION, magnitude=None, angle_deg=None,
                reason_code="positive_sequence_requires_phasor_angle",
                message=(
                    "Positive Sequence Voltage requires simultaneous complex phase phasors for A, B and C "
                    "(the Fortescue transform is meaningless without genuine phase-angle relationships). "
                    "At least one phase is an already-RMS magnitude-only input with no angle."
                ),
            )
        triplet = compute_symmetrical_components(
            phasor_a.magnitude, phasor_a.angle_deg,
            phasor_b.magnitude, phasor_b.angle_deg,
            phasor_c.magnitude, phasor_c.angle_deg,
        )
        return QuantityValueResult(
            status=STATUS_AVAILABLE, magnitude=triplet.positive_magnitude, angle_deg=triplet.positive_angle_deg,
        )

    raise ValueError(f"Unknown voltage_representation: {rep!r}")
