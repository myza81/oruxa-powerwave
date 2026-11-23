"""D5A-2B1 wire shape for the independent-side conversion echo (additive, null on the legacy path)."""

from __future__ import annotations

from pydantic import BaseModel

from app.domain.side_conversion import SideConversionInfo


class SideConversionOut(BaseModel):
    mode: str
    voltage_side: str | None
    current_side: str | None
    output_side: str | None
    vt_ratio_applied: float | None
    ct_ratio_applied: float | None
    voltage_group_ids: list[str]
    current_group_ids: list[str]
    block_code: str | None
    block_quantity: str | None
    block_detail: dict[str, str | float | None]
    #: D5A-2B2C-1B: provenance of each effective side (e.g. `engineer_group_override`) and the owning group names.
    voltage_side_authority: str | None = None
    current_side_authority: str | None = None
    voltage_group_names: list[str] = []
    current_group_names: list[str] = []

    @classmethod
    def from_domain(cls, info: SideConversionInfo | None) -> "SideConversionOut | None":
        if info is None:
            return None
        return cls(
            mode=info.mode, voltage_side=info.voltage_side, current_side=info.current_side, output_side=info.output_side,
            vt_ratio_applied=info.vt_ratio_applied, ct_ratio_applied=info.ct_ratio_applied,
            voltage_group_ids=list(info.voltage_group_ids), current_group_ids=list(info.current_group_ids),
            block_code=info.block_code, block_quantity=info.block_quantity, block_detail=dict(info.block_detail),
            voltage_side_authority=info.voltage_side_authority, current_side_authority=info.current_side_authority,
            voltage_group_names=list(info.voltage_group_names), current_group_names=list(info.current_group_names),
        )
