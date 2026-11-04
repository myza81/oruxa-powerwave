"""Validate complete result-owned Current candidates before one publication."""
from datetime import datetime, timezone

from app.domain.calculated_current_config import CalculatedCurrentConfiguration
from app.domain.calculated_channel import MULTI_OPERATIONS, UNARY_OPERATIONS, OP_ROCOF
from app.domain.channel_classification import CURRENT
from app.domain.per_unit import STATUS_CONFIGURED
from app.domain.per_unit_numerics import scaled_base
from app.services.calculated_current_per_unit import resolve_calculated_current_per_unit, CURRENT_REASON_COPY
from app.services.errors import ImportServiceError


class InvalidCalculatedCurrentConfiguration(ImportServiceError):
    code = "invalid_calculated_current_configuration"


def require_current_result(channel):
    if channel.engineering_type != CURRENT or channel.operation not in (UNARY_OPERATIONS | MULTI_OPERATIONS) - {OP_ROCOF}:
        raise InvalidCalculatedCurrentConfiguration("PU result configuration supports calculated Current channels only.")


def update_current_configuration(*, workspace_id, channel, mode, current_base_value,
                                 current_base_unit, base_reference_side, per_unit_registry,
                                 source_registry, calc_registry, group_registry,
                                 voltage_config_registry, current_config_registry):
    require_current_result(channel)
    if mode not in ("automatic", "manual", "unassigned") or current_base_unit not in ("A", "kA"):
        raise InvalidCalculatedCurrentConfiguration("Invalid Current configuration mode or base unit.")
    if base_reference_side not in ("primary", "secondary", "unknown"):
        raise InvalidCalculatedCurrentConfiguration("Invalid base reference side.")
    amount = None
    if mode == "manual":
        amount = scaled_base(current_base_value, 1000. if current_base_unit == "kA" else 1.)
        if amount is None:
            raise InvalidCalculatedCurrentConfiguration("Current base must be numeric, finite, positive and representable in amperes.")
    elif current_base_value is not None or base_reference_side != "unknown":
        raise InvalidCalculatedCurrentConfiguration("Only Manual mode accepts a Current base and reference side.")
    candidate = CalculatedCurrentConfiguration(mode, amount, base_reference_side, datetime.now(timezone.utc))
    if mode == "manual":
        proof = resolve_calculated_current_per_unit(
            workspace_id=workspace_id, channel=channel, candidate_configuration=candidate,
            source_registry=source_registry, per_unit_registry=per_unit_registry,
            calc_registry=calc_registry, group_registry=group_registry,
            voltage_config_registry=voltage_config_registry, current_config_registry=current_config_registry)
        if proof is None or proof.resolution.status != STATUS_CONFIGURED:
            reason = proof.resolution.reason if proof else "current_dependency_unavailable"
            raise InvalidCalculatedCurrentConfiguration(CURRENT_REASON_COPY.get(reason,
                "Manual PU is unavailable: measured units or numerical result are incompatible (" + str(reason) + ")."))
    per_unit_registry.set_current_configuration_for_calculated_channel(workspace_id, channel.id, candidate)
    return candidate
