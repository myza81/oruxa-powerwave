"""Reference meaning only; never scales samples or infers a manual base side."""
from typing import Literal

ReferenceSide = Literal["primary", "secondary", "unknown"]
REFERENCE_SIDES = ("primary", "secondary", "unknown")


def comtrade_measurement_side(marker: str | None) -> ReferenceSide:
    return {"P": "primary", "S": "secondary"}.get((marker or "").strip().upper(), "unknown")


def configured_base_side(method: str, declared: str = "unknown") -> ReferenceSide:
    if method in ("equipment_rating", "derived"):
        return "primary"
    if method in ("manual", "direct") and declared in REFERENCE_SIDES:
        return declared
    return "unknown"


def candidate_base_side(method: str, requested: str | None, previous_method: str,
                        previous_side: str) -> ReferenceSide:
    """Omission preserves only an existing manual/direct declaration of the same method."""
    if requested is not None and (not isinstance(requested, str) or requested not in REFERENCE_SIDES):
        raise ValueError("Base reference side must be primary, secondary or unknown.")
    if method in ("equipment_rating", "derived"):
        if requested not in (None, "primary"):
            raise ValueError("Equipment-derived current bases represent the primary side.")
        return "primary"
    if method == "none":
        if requested not in (None, "unknown"):
            raise ValueError("An unconfigured current base has unknown reference side.")
        return "unknown"
    return requested if requested is not None else (
        configured_base_side(method, previous_side) if previous_method == method else "unknown"
    )
