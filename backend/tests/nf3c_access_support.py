"""Test helper (not a test module): a gate-aware nominal-frequency accessor over the registries a test already built.

NF-3C moves the migrated consumers from reading a recording's imported frequency to asking the central accessor, so a test that calls a
consumer's service function directly passes one. `manual_override_enabled` is False unless the test is specifically about Manual mode.
"""

from __future__ import annotations

from app.services.nominal_frequency_access import NominalFrequencyAccess
from app.services.nominal_frequency_registry import NominalFrequencyRegistry


def access_for(source_registry, *, manual_override_enabled: bool = False, registry: NominalFrequencyRegistry | None = None) -> NominalFrequencyAccess:
    return NominalFrequencyAccess(
        source_registry, registry if registry is not None else NominalFrequencyRegistry(), manual_override_enabled=manual_override_enabled)
