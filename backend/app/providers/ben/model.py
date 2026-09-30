"""Native BEN record model.

``BenRecord`` is what the BEN parser produces: everything decoded from
the file, before any Powerwave normalization. Sample data is NOT copied
into per-channel Python objects. The record keeps one read-only
``(sample_count, words_per_sample)`` big-endian view directly over the
file bytes; per-channel arrays are produced on demand, one channel at a
time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum

import numpy as np

from app.providers.ben import layout


class BenRecordClass(str, Enum):
    """BEN32 record classes validated so far (see layout.RECORD_CLASSES)."""

    FAST = "Fast SubBen"
    SLOW = "Slow SubBen"


class BenChannelKind(str, Enum):
    """Where a value channel comes from."""

    #: A sampled analog input (instantaneous waveform), Fast SubBen.
    ANALOG = "analog"
    #: A quantity the recorder calculates (frequency, power, ...), Slow SubBen.
    CALCULATED = "calculated"


class BenDigitalSource(str, Enum):
    """Origin of an exported binary channel."""

    #: A physical binary input of the recorder.
    PHYSICAL = "physical"
    #: An indication the recorder derives from a value channel
    #: (e.g. "OVER BUGL1 VR").
    DERIVED = "derived"


@dataclass(frozen=True, slots=True)
class BenDiagnostic:
    """Something the parser could not fully interpret, reported honestly."""

    code: str
    severity: str  # "info" | "warning"
    message: str


@dataclass(frozen=True, slots=True)
class BenTriggerTime:
    """The trigger instant as stored by BEN (UTC).

    ``fraction_digits`` are the raw base-100 digits (hundredths, 1e-4 s,
    1e-6 s). ``microsecond`` is ``None`` when those digits do not form a
    valid fraction -- the whole second is then still reported, and no
    sub-second value is invented.
    """

    utc_whole_second: datetime  # naive, UTC
    fraction_digits: tuple[int, int, int]
    microsecond: int | None

    def as_utc(self) -> datetime:
        """Naive UTC datetime (sub-second only when decoded)."""
        return self.utc_whole_second.replace(microsecond=self.microsecond or 0)


@dataclass(frozen=True, slots=True)
class BenHeader:
    """Record-level facts, each read from the file itself."""

    recorder_unit_id: int
    station_name: str
    record_label: str
    record_number: int
    record_class: BenRecordClass
    record_class_code: int
    rate_field: int
    sample_count: int
    pre_trigger_samples: int
    words_per_sample: int
    sample_data_offset: int
    trigger_time: BenTriggerTime
    #: Trigger-cause area (header bytes 0x80-0xDB), preserved uninterpreted.
    trigger_info_raw: bytes = field(repr=False)

    @property
    def sampling_rate_hz(self) -> float:
        return self.rate_field / layout.RATE_FIELD_PER_SAMPLE_PER_SECOND

    @property
    def sample_stride_bytes(self) -> int:
        return self.words_per_sample * layout.SAMPLE_WORD_BYTES

    @property
    def pre_trigger_seconds(self) -> float:
        return self.pre_trigger_samples / self.sampling_rate_hz

    @property
    def trigger_time_utc(self) -> datetime:
        return self.trigger_time.as_utc()

    @property
    def start_time_utc(self) -> datetime:
        """First-sample instant: trigger minus the pre-trigger duration."""
        offset_us = round(self.pre_trigger_samples * 1_000_000 / self.sampling_rate_hz)
        return self.trigger_time_utc - timedelta(microseconds=offset_us)


@dataclass(frozen=True, slots=True)
class BenSampleSlot:
    """Where one channel lives inside every sample (from the layout map)."""

    word_index: int
    bit: int
    slot_kind: int  # raw, uninterpreted

    @property
    def byte_offset(self) -> int:
        return self.word_index * layout.SAMPLE_WORD_BYTES


@dataclass(frozen=True, slots=True)
class BenValueChannel:
    """One analog input or calculated quantity (a 16-bit word per sample).

    ``unit`` is the decoded engineering unit (e.g. ``kV``, ``MW``) or
    ``None`` when the unit code has not been validated -- raw codes are
    always kept. Engineering value = ``scale * raw + offset``.
    ``invalid_raw_value`` is the raw value meaning "unavailable" for this
    channel, or ``None`` when no such rule is established for its kind.
    """

    index: int  # 0-based order within the descriptor section
    channel_id: int
    name: str
    kind: BenChannelKind
    measurement: str | None  # "voltage" | "current" | "frequency" | "active_power"
    unit: str | None
    unit_code: int
    unit_multiplier_exponent: int
    phase: str | None  # "A" | "B" | "C" | "N"
    phase_code: int
    quantity_code: int
    scale: float
    offset: float
    #: Primary rating in the channel's (prefixed) unit, e.g. 500 kV.
    primary_rating: float | None
    #: Secondary rating in the channel's BASE unit, e.g. 110 V.
    secondary_rating: float | None
    bay_name: str | None
    trigger_id: int
    event_id: int
    hardware_address: int | None
    slot: BenSampleSlot
    invalid_raw_value: int | None
    descriptor_raw: bytes = field(repr=False)

    @property
    def base_unit(self) -> str | None:
        entry = layout.UNIT_CODES.get(self.unit_code)
        return entry[0] if entry else None

    @property
    def secondary_rating_in_channel_unit(self) -> float | None:
        """Secondary rating expressed in the channel's own unit (kV/kA).

        This is the form BEN32 writes to the COMTRADE ``secondary`` field.
        """
        if self.secondary_rating is None:
            return None
        return self.secondary_rating / 10**self.unit_multiplier_exponent


@dataclass(frozen=True, slots=True)
class BenDigitalChannel:
    """One exported binary channel, resolved to its bit in every sample.

    ``bit_channel_id`` is the id whose layout slot carries the bit: the
    derived trigger for a DERIVED channel, the physical input for a
    PHYSICAL one. The resolution follows BEN's own descriptor links, never
    event-specific inference.
    """

    index: int  # 0-based order within BEN's exported list
    event_id: int
    name: str
    event_name: str
    source: BenDigitalSource
    bit_channel_id: int
    source_channel_id: int
    bay_name: str | None
    slot: BenSampleSlot
    active_low: bool = layout.DIGITAL_STORED_BIT_ACTIVE_LOW


@dataclass(frozen=True, slots=True, eq=False)
class BenRecord:
    """A fully parsed BEN record."""

    header: BenHeader
    value_channels: tuple[BenValueChannel, ...]
    digital_channels: tuple[BenDigitalChannel, ...]
    diagnostics: tuple[BenDiagnostic, ...]
    #: Read-only (sample_count, words_per_sample) view of the payload,
    #: big-endian unsigned words, sharing memory with the file bytes.
    sample_words: np.ndarray = field(repr=False)

    @property
    def sample_count(self) -> int:
        return self.header.sample_count

    def time_axis(self) -> np.ndarray:
        """Seconds from the first sample (float64)."""
        return np.arange(self.sample_count, dtype=np.float64) / self.header.sampling_rate_hz

    def raw_values(self, channel: BenValueChannel) -> np.ndarray:
        """Raw signed 16-bit samples of one value channel (native-endian copy)."""
        return self.sample_words[:, channel.slot.word_index].view(layout.SAMPLE_VALUE_DTYPE).astype(np.int16)

    def valid_mask(self, channel: BenValueChannel) -> np.ndarray:
        """True where the raw sample is a real measurement."""
        raw = self.raw_values(channel)
        if channel.invalid_raw_value is None:
            return np.ones(raw.shape, dtype=bool)
        return raw != channel.invalid_raw_value

    def engineering_values(self, channel: BenValueChannel) -> np.ndarray:
        """``scale * raw + offset`` as float64; NaN where the sample is invalid."""
        raw = self.raw_values(channel)
        values = raw.astype(np.float64) * channel.scale + channel.offset
        if channel.invalid_raw_value is not None:
            values[raw == channel.invalid_raw_value] = np.nan
        return values

    def stored_bits(self, channel: BenDigitalChannel) -> np.ndarray:
        """The bit exactly as stored (uint8 0/1), before polarity handling."""
        words = self.sample_words[:, channel.slot.word_index]
        return ((words >> channel.slot.bit) & 1).astype(np.uint8)

    def digital_states(self, channel: BenDigitalChannel) -> np.ndarray:
        """Indication state as int8: 1 = active, 0 = inactive."""
        bits = self.stored_bits(channel).astype(np.int8)
        return (1 - bits) if channel.active_low else bits

    def value_channel(self, name: str) -> BenValueChannel:
        for channel in self.value_channels:
            if channel.name == name:
                return channel
        raise KeyError(name)
