"""D5A-2A: non-blocking diagnostics comparing a protection analysis request's CT/VT and
recording-basis assumptions with the authoritative Recording Details context.

Pure and read-only. Nothing here changes, overrides or rejects a request; every finding is
advisory, machine-readable (`code`) and carries the values it was derived from (`detail`).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Mapping

from app.services.protection_instrument_context import (
    RATIO_CONFIGURED,
    RATIO_NO_CHANNELS,
    SIDE_MIXED,
    SIDE_UNKNOWN,
    TransformerContext,
)

SEVERITY_WARNING = "warning"
SEVERITY_INFO = "info"

ANALYSIS_OVERCURRENT = "overcurrent"
ANALYSIS_IMPEDANCE = "impedance"
ANALYSIS_DISTANCE = "distance_protection"
KNOWN_ANALYSES = (ANALYSIS_OVERCURRENT, ANALYSIS_IMPEDANCE, ANALYSIS_DISTANCE)

# Reason codes (stable API contract).
CHANNEL_UNRESOLVED = "CHANNEL_UNRESOLVED"
CT_AUTHORITY_MISSING = "CT_AUTHORITY_MISSING"
VT_AUTHORITY_MISSING = "VT_AUTHORITY_MISSING"
VT_NOMINAL_NOT_USABLE = "VT_NOMINAL_NOT_USABLE"
REQUEST_CT_INCOMPLETE = "REQUEST_CT_INCOMPLETE"
REQUEST_VT_INCOMPLETE = "REQUEST_VT_INCOMPLETE"
REQUEST_CT_INVALID = "REQUEST_CT_INVALID"
REQUEST_VT_INVALID = "REQUEST_VT_INVALID"
REQUEST_CT_DIFFERS_FROM_AUTHORITY = "REQUEST_CT_DIFFERS_FROM_AUTHORITY"
REQUEST_VT_DIFFERS_FROM_AUTHORITY = "REQUEST_VT_DIFFERS_FROM_AUTHORITY"
REQUEST_CT_NOT_VERIFIED_BY_AUTHORITY = "REQUEST_CT_NOT_VERIFIED_BY_AUTHORITY"
REQUEST_VT_NOT_VERIFIED_BY_AUTHORITY = "REQUEST_VT_NOT_VERIFIED_BY_AUTHORITY"
VOLTAGE_SIDE_UNKNOWN = "VOLTAGE_SIDE_UNKNOWN"
CURRENT_SIDE_UNKNOWN = "CURRENT_SIDE_UNKNOWN"
VOLTAGE_SIDE_MIXED = "VOLTAGE_SIDE_MIXED"
CURRENT_SIDE_MIXED = "CURRENT_SIDE_MIXED"
VOLTAGE_CURRENT_SIDES_DIFFER = "VOLTAGE_CURRENT_SIDES_DIFFER"
REQUEST_RECORDING_BASIS_INVALID = "REQUEST_RECORDING_BASIS_INVALID"
REQUEST_RECORDING_BASIS_CONTRADICTS_VOLTAGE_SIDE = "REQUEST_RECORDING_BASIS_CONTRADICTS_VOLTAGE_SIDE"
REQUEST_RECORDING_BASIS_CONTRADICTS_CURRENT_SIDE = "REQUEST_RECORDING_BASIS_CONTRADICTS_CURRENT_SIDE"
REQUEST_RECORDING_BASIS_UNVERIFIABLE_VOLTAGE = "REQUEST_RECORDING_BASIS_UNVERIFIABLE_VOLTAGE"
REQUEST_RECORDING_BASIS_UNVERIFIABLE_CURRENT = "REQUEST_RECORDING_BASIS_UNVERIFIABLE_CURRENT"
CONVERSION_REQUESTED_WITHOUT_AUTHORITY = "CONVERSION_REQUESTED_WITHOUT_AUTHORITY"
CONVERSION_REQUESTED_WITH_UNKNOWN_SIDE = "CONVERSION_REQUESTED_WITH_UNKNOWN_SIDE"

_BASES = ("primary", "secondary")
_RATIO_REL_TOL = 1e-6


@dataclass(frozen=True, slots=True)
class RequestAssumptions:
    """The legacy request parameters, exactly as supplied. Never altered."""

    recording_basis: str | None = None
    impedance_basis: str | None = None
    vt_primary: float | None = None
    vt_secondary: float | None = None
    ct_primary: float | None = None
    ct_secondary: float | None = None


@dataclass(frozen=True, slots=True)
class Diagnostic:
    code: str
    severity: str
    message: str
    quantity: str | None = None
    detail: Mapping[str, str | float | None] = field(default_factory=dict)


def _finite_positive(value: float | None) -> bool:
    return value is not None and math.isfinite(value) and value > 0


def _label(quantity: str) -> tuple[str, str]:
    return ("VT", "VOLTAGE") if quantity == "voltage" else ("CT", "CURRENT")


def _request_ratio_findings(quantity: str, ctx: TransformerContext, primary, secondary) -> list[Diagnostic]:
    tag, _ = _label(quantity)
    if primary is None and secondary is None:
        return []
    if (primary is None) != (secondary is None):
        return [Diagnostic(
            f"REQUEST_{tag}_INCOMPLETE", SEVERITY_WARNING,
            f"Request supplied only one of {tag.lower()}_primary / {tag.lower()}_secondary.",
            quantity, {"primary": primary, "secondary": secondary},
        )]
    if not (_finite_positive(primary) and _finite_positive(secondary)):
        return [Diagnostic(
            f"REQUEST_{tag}_INVALID", SEVERITY_WARNING,
            f"Request {tag} values must be finite and positive.", quantity,
            {"primary": primary, "secondary": secondary},
        )]
    if ctx.ratio_consumable:
        request_ratio = primary / secondary
        if not math.isclose(request_ratio, ctx.ratio, rel_tol=_RATIO_REL_TOL):
            return [Diagnostic(
                f"REQUEST_{tag}_DIFFERS_FROM_AUTHORITY", SEVERITY_WARNING,
                f"Request {tag} ratio differs from the Recording Details Measurement Group ratio.", quantity,
                {"request_primary": primary, "request_secondary": secondary, "request_ratio": request_ratio,
                 "authoritative_primary": ctx.primary, "authoritative_secondary": ctx.secondary,
                 "authoritative_ratio": ctx.ratio, "authority": ctx.authority},
            )]
        return []
    return [Diagnostic(
        f"REQUEST_{tag}_NOT_VERIFIED_BY_AUTHORITY", SEVERITY_INFO,
        f"Request {tag} ratio has no authoritative Recording Details configuration to verify it.", quantity,
        {"request_primary": primary, "request_secondary": secondary, "authority_status": ctx.ratio_status},
    )]


def build_diagnostics(
    analysis: str,
    voltage: TransformerContext | None,
    current: TransformerContext | None,
    request: RequestAssumptions,
    *,
    unresolved_roles: tuple[tuple[str, str, str | None], ...] = (),
) -> list[Diagnostic]:
    """`voltage` is None when the analysis does not use voltage (Overcurrent).
    `unresolved_roles` is ((role_key, status, reason), ...) from channel resolution."""
    out: list[Diagnostic] = []
    for role_key, status, reason in unresolved_roles:
        out.append(Diagnostic(
            CHANNEL_UNRESOLVED, SEVERITY_WARNING, f"Role '{role_key}' did not resolve to a channel.",
            "voltage" if role_key.startswith("V") else "current", {"role_key": role_key, "status": status, "reason": reason},
        ))

    contexts = [(q, c) for q, c in (("voltage", voltage), ("current", current)) if c is not None]

    for quantity, ctx in contexts:
        tag, word = _label(quantity)
        if ctx.ratio_status not in (RATIO_CONFIGURED, RATIO_NO_CHANNELS):
            out.append(Diagnostic(
                f"{tag}_AUTHORITY_MISSING", SEVERITY_WARNING,
                f"No usable {tag} ratio is configured in Recording Details for the resolved channels.", quantity,
                {"ratio_status": ctx.ratio_status, "reason": ctx.reason, "authority": ctx.authority,
                 "group_ids": ",".join(ctx.group_ids) or None},
            ))
        if quantity == "voltage" and ctx.nominal_refused_reason is not None:
            out.append(Diagnostic(
                VT_NOMINAL_NOT_USABLE, SEVERITY_WARNING,
                "A nominal voltage is configured but no VT could be derived from it (the nominal is not an accepted value).",
                quantity, {"nominal_ll_kv": ctx.nominal_ll_kv, "reason": ctx.nominal_refused_reason},
            ))
        if ctx.ratio_status != RATIO_NO_CHANNELS:
            if ctx.side_status == SIDE_UNKNOWN:
                out.append(Diagnostic(f"{word}_SIDE_UNKNOWN", SEVERITY_WARNING,
                                      f"The recording does not declare the {quantity} measurement side.", quantity, {}))
            elif ctx.side_status == SIDE_MIXED:
                out.append(Diagnostic(f"{word}_SIDE_MIXED", SEVERITY_WARNING,
                                      f"The resolved {quantity} channels declare different measurement sides.", quantity, {}))
        primary, secondary = ((request.vt_primary, request.vt_secondary) if quantity == "voltage"
                              else (request.ct_primary, request.ct_secondary))
        out.extend(_request_ratio_findings(quantity, ctx, primary, secondary))

    if voltage is not None and current is not None:
        v, c = voltage.declared_basis, current.declared_basis
        if v is not None and c is not None and v != c:
            out.append(Diagnostic(
                VOLTAGE_CURRENT_SIDES_DIFFER, SEVERITY_WARNING,
                "Voltage and current are recorded on different sides; a single recording_basis cannot represent both.",
                None, {"voltage_side": v, "current_side": c},
            ))

    basis = request.recording_basis
    if basis is not None:
        if basis not in _BASES:
            out.append(Diagnostic(REQUEST_RECORDING_BASIS_INVALID, SEVERITY_WARNING,
                                  "recording_basis must be 'primary' or 'secondary'.", None, {"recording_basis": basis}))
        else:
            for quantity, ctx in contexts:
                if ctx.ratio_status == RATIO_NO_CHANNELS:
                    continue
                word = _label(quantity)[1]
                if ctx.declared_basis is not None and ctx.declared_basis != basis:
                    out.append(Diagnostic(
                        f"REQUEST_RECORDING_BASIS_CONTRADICTS_{word}_SIDE", SEVERITY_WARNING,
                        f"Request recording_basis contradicts the declared {quantity} measurement side.", quantity,
                        {"recording_basis": basis, "declared_side": ctx.declared_basis},
                    ))
                elif ctx.declared_basis is None:
                    out.append(Diagnostic(
                        f"REQUEST_RECORDING_BASIS_UNVERIFIABLE_{word}", SEVERITY_INFO,
                        f"Request recording_basis cannot be verified: the {quantity} side is {ctx.side_status}.", quantity,
                        {"recording_basis": basis, "side_status": ctx.side_status},
                    ))
            out.extend(_conversion_findings(analysis, contexts, request))
    return out


def _conversion_findings(analysis: str, contexts, request: RequestAssumptions) -> list[Diagnostic]:
    basis = request.recording_basis
    if analysis == ANALYSIS_OVERCURRENT:
        needs_conversion = basis == "primary"
        needed = {"current"}
    else:
        out_basis = request.impedance_basis
        needs_conversion = out_basis in _BASES and basis != out_basis
        needed = {"voltage", "current"}
    if not needs_conversion:
        return []
    findings: list[Diagnostic] = []
    for quantity, ctx in contexts:
        if quantity not in needed or ctx.ratio_status == RATIO_NO_CHANNELS:
            continue
        tag = _label(quantity)[0]
        if not ctx.ratio_consumable:
            findings.append(Diagnostic(
                CONVERSION_REQUESTED_WITHOUT_AUTHORITY, SEVERITY_WARNING,
                f"This request converts using a {tag} ratio, but Recording Details has no usable {tag} ratio.", quantity,
                {"recording_basis": basis, "impedance_basis": request.impedance_basis, "ratio_status": ctx.ratio_status},
            ))
        if ctx.side_status in (SIDE_UNKNOWN, SIDE_MIXED):
            findings.append(Diagnostic(
                CONVERSION_REQUESTED_WITH_UNKNOWN_SIDE, SEVERITY_WARNING,
                f"This request converts {quantity} samples, but their measurement side is {ctx.side_status}.", quantity,
                {"recording_basis": basis, "side_status": ctx.side_status},
            ))
    return findings
