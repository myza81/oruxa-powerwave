"""D5A-2B2C-1B: read-only report of what one recorded Impedance Locus / Distance Protection calculation consumes from Recording
Details -- the effective Voltage and Current measurement sides with provenance, the VT/CT of the Measurement Groups that own the
consumed channels, and whether the calculation is blocked. Nothing is computed or stored; the calculation endpoints evaluate the
identical authority (`independent_side_service.evaluate_recorded_input`), so the page and the calculation cannot disagree."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.calculated_channel import ChannelRefOut
from app.schemas.measurement_side import ChannelMeasurementSideOut
from app.services.independent_side_service import QuantityAuthority, RecordedInputEvaluation
from app.domain.side_conversion import SideBlock, SidePlan


class RecordedTransformerOut(BaseModel):
    """The VT (voltage) or CT (current) of the Measurement Group(s) that own the consumed channels (never another group's)."""

    status: str
    consumable: bool
    primary: float | None
    secondary: float | None
    ratio: float | None
    authority: str
    reason: str | None
    group_ids: list[str]
    nominal_ll_kv: float | None = None


class RecordedConfigureTargetOut(BaseModel):
    """Where Recording Details can resolve a problem: the recording and (when the channel is in one) its Measurement Group."""

    source_id: str
    group_id: str | None


class RecordedQuantityOut(BaseModel):
    quantity: str
    channels: list[ChannelRefOut]
    #: Per consumed channel: the effective side, its authority, the ORIGINAL declaration and any override warning.
    channel_sides: list[ChannelMeasurementSideOut]
    effective_side: str | None
    authority: str | None
    declared_sides: list[str]
    group_ids: list[str]
    group_names: list[str]
    #: Whether the requested output side needs this quantity's VT/CT.
    ratio_required: bool
    transformer: RecordedTransformerOut | None
    configure_target: RecordedConfigureTargetOut | None
    problem_code: str | None
    problem_message: str | None

    @classmethod
    def from_domain(cls, qa: QuantityAuthority) -> "RecordedQuantityOut":
        ctx = qa.transformer
        target = None
        for chan in qa.channels:
            if chan.ref.kind == "source" and chan.ref.source_id:
                target = RecordedConfigureTargetOut(source_id=chan.ref.source_id, group_id=chan.group_id)
                if chan.group_id and (qa.problem_code is None or chan.problem is not None):
                    break
        return cls(
            quantity=qa.quantity, channels=[ChannelRefOut.from_domain(r) for r in qa.refs],
            channel_sides=[ChannelMeasurementSideOut.from_domain(c.side) for c in qa.channels if c.side is not None],
            effective_side=qa.side, authority=qa.authority, declared_sides=list(qa.declared_sides),
            group_ids=list(qa.group_ids), group_names=list(qa.group_names), ratio_required=qa.ratio_required,
            transformer=None if ctx is None else RecordedTransformerOut(
                status=ctx.ratio_status, consumable=ctx.ratio_consumable, primary=ctx.primary, secondary=ctx.secondary,
                ratio=ctx.ratio, authority=ctx.authority, reason=ctx.reason, group_ids=list(ctx.group_ids),
                nominal_ll_kv=ctx.nominal_ll_kv,
            ),
            configure_target=target, problem_code=qa.problem_code, problem_message=qa.problem_message,
        )


class ProtectionRecordedInputOut(BaseModel):
    status: str = Field(description="`ready`, or the status the calculation would report (needs_configuration / ambiguous / ...).")
    analysis: str
    engineering_context_id: str
    phase: str | None
    loop: str | None
    output_side: str
    voltage: RecordedQuantityOut | None
    current: RecordedQuantityOut | None
    #: How each quantity is converted to the output side when ready: `none` (already there), `secondary_to_primary`
    #: (multiplied by its ratio) or `primary_to_secondary` (divided by it). Null while blocked.
    voltage_conversion: str | None
    current_conversion: str | None
    reason_code: str | None
    message: str

    @classmethod
    def from_evaluation(cls, ev: RecordedInputEvaluation, engineering_context_id: str) -> "ProtectionRecordedInputOut":
        outcome = ev.outcome
        status, reason, message = "ready", None, "The recorded input is ready."
        if ev.unresolved_roles:
            role, role_status, role_reason = ev.unresolved_roles[0]
            status, reason, message = role_status, role_reason, f"Role '{role}' did not resolve to a channel in this Engineering Context."
        elif isinstance(outcome, SideBlock):
            status, reason, message = "needs_configuration", outcome.code, outcome.message

        def conversion(source: str | None) -> str | None:
            if status != "ready" or source is None:
                return None
            if source == ev.output_side:
                return "none"
            return "secondary_to_primary" if source == "secondary" else "primary_to_secondary"

        plan_ready = isinstance(outcome, SidePlan) and status == "ready"
        return cls(
            status=status, analysis=ev.analysis, engineering_context_id=engineering_context_id, phase=ev.phase, loop=ev.loop,
            output_side=ev.output_side,
            voltage=RecordedQuantityOut.from_domain(ev.voltage) if ev.voltage is not None else None,
            current=RecordedQuantityOut.from_domain(ev.current) if ev.current is not None else None,
            voltage_conversion=conversion(outcome.voltage_side) if plan_ready else None,
            current_conversion=conversion(outcome.current_side) if plan_ready else None,
            reason_code=reason, message=message,
        )
