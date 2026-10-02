"""BenRecord -> DisturbanceRecord normalization.

Maps a parsed BEN record onto Powerwave's existing normalized contract
without changing that contract:

- Value channels become ``AnalogChannel`` columns of engineering values
  (``scale * raw + offset``). Calculated quantities (frequency, active
  power) use the ``parameter_type`` values the channel classifier
  already understands. An unavailable sample becomes ``NaN``, the
  established missing-sample representation (DEC-084), never a number.
- Exported binary channels become ``DigitalChannel`` columns of states
  with 1 = active (BEN stores them active-low).
- Times are BEN's own trigger instant and the start derived from the
  pre-trigger count, as timezone-aware UTC datetimes (``timezone`` also
  says ``"UTC"``). Presentation in a local timezone is never done here.

BEN does not declare the power-system nominal frequency anywhere that has
been decoded, so the caller must supply it -- nothing here assumes 50 Hz.

Channel names lose surrounding whitespace, as the COMTRADE provider's
CFG fields do (BenRecord keeps them byte-exact); a repeated name gets the
same ``_1``, ``_2`` suffix scheme the COMTRADE provider uses, so every
descriptor names its own column. The contract has no field for BEN's
richer channel identity (channel id, byte-exact source name, bay), so
``channel_identities()`` returns it keyed by the normalized name for the
caller to keep alongside the record; ``BenRecord`` keeps everything else
(raw codes, validity).
"""

from __future__ import annotations

import math

import pandas as pd

from app.domain import (
    AnalogChannel,
    DigitalChannel,
    DisturbanceRecord,
    RecordingMetadata,
    SamplingInformation,
    TimingInformation,
)
from app.providers.ben.model import BenRecord

PROVIDER_TYPE = "BEN"
TIMEZONE = "UTC"

#: BEN measurement kind -> AnalogChannel.parameter_type understood by
#: app.domain.channel_classification.
_PARAMETER_TYPES = {
    "voltage": "voltage",
    "current": "current",
    "frequency": "frequency",
    "active_power": "active power",
    "reactive_power": "reactive power",
}


def to_disturbance_record(
    record: BenRecord,
    *,
    source_file: str,
    nominal_frequency_hz: float,
) -> DisturbanceRecord:
    """Normalize *record* into Powerwave's ``DisturbanceRecord``."""
    if not math.isfinite(nominal_frequency_hz) or nominal_frequency_hz <= 0:
        raise ValueError(f"nominal_frequency_hz must be a positive number, got {nominal_frequency_hz!r}")

    header = record.header
    value_names, digital_names = normalized_names(record)
    columns: dict[str, object] = {"time": record.time_axis()}

    analog_channels: list[AnalogChannel] = []
    for channel, name in zip(record.value_channels, value_names):
        columns[name] = record.engineering_values(channel)
        analog_channels.append(
            AnalogChannel(
                name=name,
                unit=channel.unit or "",
                index=channel.index + 1,
                phase=channel.phase,
                scale=channel.scale,
                offset=channel.offset,
                primary_ratio=channel.primary_rating,
                secondary_ratio=channel.secondary_rating_in_channel_unit,
                parameter_type=_PARAMETER_TYPES.get(channel.measurement or ""),
            )
        )

    digital_channels: list[DigitalChannel] = []
    for position, (channel, name) in enumerate(zip(record.digital_channels, digital_names)):
        columns[name] = record.digital_states(channel)
        digital_channels.append(DigitalChannel(name=name, index=position + 1, normal_state=0))

    return DisturbanceRecord(
        metadata=RecordingMetadata(
            station_name=header.station_name,
            recorder_name=str(header.recorder_unit_id),
            source_file=source_file,
            provider_type=PROVIDER_TYPE,
            nominal_frequency=nominal_frequency_hz,
            timezone=TIMEZONE,
        ),
        waveform_data=pd.DataFrame(columns),
        analog_channels=analog_channels,
        digital_channels=digital_channels,
        sampling_info=SamplingInformation(
            sampling_rates=[header.sampling_rate_hz],
            samples_per_rate=[header.sample_count],
            nominal_frequency=nominal_frequency_hz,
        ),
        timing_info=TimingInformation(
            start_time=header.start_time_utc,
            trigger_time=header.trigger_time_utc,
            timezone=TIMEZONE,
        ),
        disturbance_info=None,
    )


def normalized_names(record: BenRecord) -> tuple[list[str], list[str]]:
    """The column names ``to_disturbance_record`` gives value and binary channels."""
    unique = _UniqueNames()
    values = [unique.take(c.name.strip()) for c in record.value_channels]
    digitals = [unique.take(c.name.strip()) for c in record.digital_channels]
    return values, digitals


def channel_identities(record: BenRecord) -> list[dict[str, object]]:
    """BEN source identity of every normalized channel (JSON-safe).

    Nothing here is renamed: ``source_name`` is the name exactly as BEN
    stores it, ``ben_channel_id`` the file's own id.
    """
    value_names, digital_names = normalized_names(record)
    identities: list[dict[str, object]] = []
    for channel, name in zip(record.value_channels, value_names):
        identities.append(
            {
                "name": name,
                "kind": channel.kind.value,
                "ben_channel_id": channel.channel_id,
                "source_name": channel.name,
                "bay": channel.bay_name,
            }
        )
    for channel, name in zip(record.digital_channels, digital_names):
        identities.append(
            {
                "name": name,
                "kind": "digital",
                "digital_source": channel.source.value,
                "ben_channel_id": channel.bit_channel_id,
                "source_name": channel.name,
                "bay": channel.bay_name,
            }
        )
    return identities


class _UniqueNames:
    """Column names unique across ``time``, analog and digital channels."""

    def __init__(self) -> None:
        self._seen: set[str] = {"time"}
        self._suffix: dict[str, int] = {}

    def take(self, name: str) -> str:
        candidate = name
        while candidate in self._seen:
            count = self._suffix.get(name, 0) + 1
            self._suffix[name] = count
            candidate = f"{name}_{count}"
        self._seen.add(candidate)
        return candidate
