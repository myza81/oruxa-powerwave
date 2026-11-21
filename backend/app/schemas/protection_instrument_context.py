"""D5A-2A response contract for `GET .../engineering-contexts/{id}/protection-instrument-context`."""

from __future__ import annotations

from pydantic import BaseModel

from app.schemas.calculated_channel import ChannelRefOut
from app.services.protection_context_report_service import ProtectionContextReport
from app.services.protection_instrument_context import TransformerContext


class ChannelFactOut(BaseModel):
    role_key: str
    quantity: str
    channel: ChannelRefOut
    measurement_group_id: str | None
    measurement_group_kind: str | None
    declared_side: str
    side_evidence: str
    provider_type: str | None


class TransformerContextOut(BaseModel):
    quantity: str
    ratio_status: str
    ratio_consumable: bool
    group_ids: list[str]
    primary: float | None
    secondary: float | None
    ratio: float | None
    authority: str
    ratio_origin: str | None
    provenance_note: str | None
    reason: str | None
    side: str
    side_status: str
    declared_basis: str | None
    ignored_nominal_kv: float | None

    @classmethod
    def from_domain(cls, ctx: TransformerContext) -> "TransformerContextOut":
        return cls(
            quantity=ctx.quantity, ratio_status=ctx.ratio_status, ratio_consumable=ctx.ratio_consumable,
            group_ids=list(ctx.group_ids), primary=ctx.primary, secondary=ctx.secondary, ratio=ctx.ratio,
            authority=ctx.authority,
            ratio_origin="recording_details_measurement_group" if ctx.ratio_consumable else None,
            provenance_note=ctx.provenance_note, reason=ctx.reason, side=ctx.side, side_status=ctx.side_status,
            declared_basis=ctx.declared_basis, ignored_nominal_kv=ctx.ignored_nominal_kv,
        )


class RequestAssumptionsOut(BaseModel):
    recording_basis: str | None
    impedance_basis: str | None
    vt_primary: float | None
    vt_secondary: float | None
    ct_primary: float | None
    ct_secondary: float | None


class DiagnosticOut(BaseModel):
    code: str
    severity: str
    quantity: str | None
    message: str
    detail: dict[str, str | float | None]


class ProtectionInstrumentContextOut(BaseModel):
    """Read-only. `read_only` is always true: nothing here converts, persists or overrides a request."""

    read_only: bool = True
    analysis: str
    engineering_context_id: str
    phase: str | None
    loop: str | None
    channels: list[ChannelFactOut]
    voltage: TransformerContextOut | None
    current: TransformerContextOut | None
    request: RequestAssumptionsOut
    diagnostics: list[DiagnosticOut]

    @classmethod
    def from_report(cls, report: ProtectionContextReport) -> "ProtectionInstrumentContextOut":
        return cls(
            analysis=report.analysis, engineering_context_id=report.engineering_context_id,
            phase=report.phase, loop=report.loop,
            channels=[
                ChannelFactOut(
                    role_key=r.role_key, quantity=r.facts.quantity, channel=ChannelRefOut.from_domain(r.facts.ref),
                    measurement_group_id=r.facts.group_id, measurement_group_kind=r.facts.group_kind,
                    declared_side=r.facts.declared_side,
                    side_evidence="recording_declared" if r.facts.declared_side != "unknown" else "none",
                    provider_type=r.facts.provider_type,
                )
                for r in report.channels
            ],
            voltage=TransformerContextOut.from_domain(report.voltage) if report.voltage else None,
            current=TransformerContextOut.from_domain(report.current) if report.current else None,
            request=RequestAssumptionsOut(
                recording_basis=report.request.recording_basis, impedance_basis=report.request.impedance_basis,
                vt_primary=report.request.vt_primary, vt_secondary=report.request.vt_secondary,
                ct_primary=report.request.ct_primary, ct_secondary=report.request.ct_secondary,
            ),
            diagnostics=[
                DiagnosticOut(code=d.code, severity=d.severity, quantity=d.quantity, message=d.message, detail=dict(d.detail))
                for d in report.diagnostics
            ],
        )
