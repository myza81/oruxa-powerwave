"""Unified internal waveform contract.

Ported near-verbatim from powerwave's app/models/disturbance_record.py
(commit 3156392). This is the single normalized representation produced by
providers and consumed by downstream systems (analytics, visualization,
synchronization -- none of which exist in oruxa_powerwave yet).

waveform_data is stored by reference -- never copied on construction, and
never mutated in place anywhere in this codebase.

Correction (Phase 2A, DEC-019 -- see docs/project-memory/DECISIONS.md):
Phase 1's original note here said a DisturbanceRecord is "never cached or
shared across requests ... discarded at the end of that request." That is
no longer true by design: app.services.import_service now retains the
record (via app.domain.source.ActiveSource) in the active workspace's
WorkspaceRegistry entry, so later waveform range requests
(app.services.waveform_service) can read it without re-parsing the
COMTRADE file. It is still never mutated, never persisted to disk/DB/object
storage (DEC-015 is unaffected -- that decision is about the *uploaded
file*, not an already-parsed in-memory object), and is released exactly
when its owning source/workspace is removed (see
app.services.workspace_registry). See
docs/project-memory/MIGRATION_PLAN.md's Phase 2A implementation record.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from app.domain.channels import AnalogChannel, DigitalChannel
from app.domain.metadata import RecordingMetadata
from app.domain.timing import DisturbanceInformation, SamplingInformation, TimingInformation


@dataclass(slots=True)
class DisturbanceRecord:
    """Unified internal waveform contract."""

    metadata: RecordingMetadata
    waveform_data: pd.DataFrame
    analog_channels: list[AnalogChannel]
    digital_channels: list[DigitalChannel]
    sampling_info: SamplingInformation
    timing_info: TimingInformation
    disturbance_info: DisturbanceInformation | None = None

    def analog_channel_names(self) -> list[str]:
        return [ch.name for ch in self.analog_channels]

    def digital_channel_names(self) -> list[str]:
        return [ch.name for ch in self.digital_channels]

    def channel_names(self) -> list[str]:
        return self.analog_channel_names() + self.digital_channel_names()

    def has_channel(self, name: str) -> bool:
        return (
            any(ch.name == name for ch in self.analog_channels)
            or any(ch.name == name for ch in self.digital_channels)
        )

    def sample_count(self) -> int:
        return len(self.waveform_data)

    def duration_seconds(self) -> float:
        if self.waveform_data.empty:
            return 0.0

        if "time" in self.waveform_data.columns:
            return float(self.waveform_data["time"].iloc[-1]) - float(
                self.waveform_data["time"].iloc[0]
            )

        rates = self.sampling_info.sampling_rates
        counts = self.sampling_info.samples_per_rate
        if rates and all(r > 0 for r in rates):
            return sum(n / r for n, r in zip(counts, rates))

        return 0.0

    def validate(self) -> list[str]:
        """Run lightweight consistency checks. Never raises."""
        errors: list[str] = []

        if not isinstance(self.waveform_data, pd.DataFrame):
            errors.append("waveform_data must be a pandas DataFrame")
            return errors

        if self.waveform_data.empty:
            errors.append("waveform_data must not be empty")

        if not self.waveform_data.empty:
            df_cols = set(self.waveform_data.columns)
            for ch in self.analog_channels:
                if ch.name not in df_cols:
                    errors.append(
                        f"analog channel '{ch.name}' not found in waveform_data columns"
                    )
            for ch in self.digital_channels:
                if ch.name not in df_cols:
                    errors.append(
                        f"digital channel '{ch.name}' not found in waveform_data columns"
                    )

        if not self.sampling_info.sampling_rates:
            errors.append("sampling_info: sampling_rates must not be empty")
        elif len(self.sampling_info.sampling_rates) != len(
            self.sampling_info.samples_per_rate
        ):
            errors.append(
                "sampling_info: sampling_rates and samples_per_rate must have equal length"
            )

        if self.timing_info.trigger_time < self.timing_info.start_time:
            errors.append("timing_info: trigger_time cannot be before start_time")

        return errors
