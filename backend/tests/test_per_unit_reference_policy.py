"""The one physical reference classifier: no samples, ratios or mutation."""
from dataclasses import asdict
from itertools import product

import pytest

from app.domain.per_unit import PerUnitResolution
from app.domain.per_unit_reference import apply_current_reference


@pytest.mark.parametrize("measurement,base", list(product(["primary", "secondary", "unknown"], repeat=2)))
@pytest.mark.parametrize("strict,cross", [(False, False), (True, False), (True, True)])
def test_reference_matrix(measurement, base, strict, cross):
    prior = PerUnitResolution("configured", "authority", 2000., "A", None)
    before = asdict(prior)
    result = apply_current_reference(prior, [measurement], [base], strict=strict, cross_authority=cross)
    unknown = "unknown" in (measurement, base)
    conflict = not unknown and measurement != base
    secondary_cross = measurement == base == "secondary" and cross
    assert result.reference_compatibility == ("incompatible" if conflict else "unverified" if unknown or secondary_cross else "compatible")
    assert result.status == ("base_required" if conflict or secondary_cross or (unknown and strict) else "configured")
    assert result.measurement_side == measurement and result.base_reference_side == base
    assert result.base_amount == 2000 and result.profile_id == "authority"
    assert asdict(prior) == before


@pytest.mark.parametrize("measured,bases", [
    (["primary", "secondary", "unknown"], ["unknown"]),
    (["unknown"], ["primary", "secondary"]),
    (["primary", "unknown"], ["secondary", "unknown"]),
])
def test_known_conflict_survives_unknown_aggregation(measured, bases):
    for strict in (False, True):
        result = apply_current_reference(PerUnitResolution("configured", None, 1., "A", None), measured, bases, strict=strict)
        assert result.status == "base_required" and result.reference_compatibility == "incompatible"
        assert result.reason == "current_reference_side_incompatible"


def test_other_unavailability_and_reference_meaning_are_independent():
    result = apply_current_reference(PerUnitResolution("base_required", "g", None, None, "group_not_confirmed"),
                                     ["secondary"], ["primary"])
    assert result.reason == "group_not_confirmed" and result.reference_compatibility == "incompatible"
