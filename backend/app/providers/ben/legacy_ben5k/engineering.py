"""Bounded P1 legacy Fast AC projection, independently evidenced by BPHE.

The shared SubBen record keeps its full-int16 contract. Original packed words,
descriptor coefficients and diagnostics remain available on the legacy record.
No physical-calibration status is upgraded by this numerical interpretation.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math

import numpy as np

from app.providers.ben import layout
from app.providers.ben.model import BenChannelKind, BenRecord, BenValueChannel
from app.providers.ben.legacy_ben5k.reader import Ben5kAnalogChannel, Ben5kHeader

FAST_AC_TRANSFORM_ID = "ben5k_v2_fast_ac_s12_gain_sqrt2_zero_offset"

# Owner-approved LOCAL P1 applicability: complete embedded configurations from
# BPHE 2022, GPTH October 2026 and Permas October 2026, respectively. Hash only
# bytes [fixed header end, payload start): event clock/sample words are excluded.
# These are evidence identities, never names/paths or a physical-verification
# assertion. A changed/unidentified configuration cannot acquire an AC convention
# merely because its descriptor says Voltage/Current. No proven AC/DC selector
# has been decoded for the general legacy family yet.
_SUPPORTED_AC_CONFIGURATIONS = frozenset({
    "2fc25dfff1207c0a411c533a88adb96661e6c503ab89c430074bca43c05569fe",
    "56c4c52597ccb28fd3f266b6aac5ba7dd2e7723adf75b5b8a53cac33237f6543",
    "550ad948004d29c2210ad352939c2b37599c41c24c0ec3b7632a8cd26a69db77",
})


def has_supported_fast_ac_configuration(data: bytes, header: Ben5kHeader) -> bool:
    """Recognize only reviewed legacy Fast configurations, independently of time."""
    if (len(data) < layout.HEADER_SIZE
            or data[:4] != layout.BEN_FAMILY_SIGNATURE
            or data[4:12] != layout.BEN5K_LAYOUT_SIGNATURE
            or data[14:16] != layout.BEN5K_GENERATION_MARKER
            or data[layout.RECORD_CLASS_FLAG_OFFSET] != 0):
        return False
    payload_offset = len(data) - header.sample_count * header.words_per_sample * 2
    if payload_offset <= layout.HEADER_SIZE:
        return False
    digest = hashlib.sha256(data[layout.HEADER_SIZE:payload_offset]).hexdigest()
    return digest in _SUPPORTED_AC_CONFIGURATIONS


def is_supported_fast_ac_descriptor(data: bytes, channel: Ben5kAnalogChannel) -> bool:
    """Additional channel guards; source configuration must also be recognized."""
    expected_unit = {0: b"KV", 4: b"KA"}.get(channel.type_byte)
    start = channel.descriptor_offset
    return (
        expected_unit is not None
        and channel.phase_seq in (1, 2, 3, 4)
        and channel.offset == 0.0
        and math.isfinite(channel.scale)
        and data[start + 20:start + 22] == expected_unit
    )


def fast_ac_engineering_values(raw_signed: np.ndarray, gain: float, offset: float = 0.0) -> np.ndarray:
    """Signed upper 12 bits -> instantaneous engineering values, exactly once.

    This explicit AC function is also usable for BPHE's independently identified
    physical columns without claiming the unresolved BPHE adapter mapping works.
    Caller supplies signed int16 words and established AC applicability.
    """
    if offset != 0.0 or not math.isfinite(gain):
        raise ValueError("BEN5K Fast AC P1 requires zero offset and a finite gain")
    raw = np.asarray(raw_signed)
    if not np.issubdtype(raw.dtype, np.signedinteger):
        raise ValueError("BEN5K Fast AC P1 requires signed integer sample words")
    if np.any(raw < -32768) or np.any(raw > 32767):
        raise ValueError("BEN5K Fast AC P1 sample word is outside signed int16")
    # Arithmetic shift preserves negatives; division would retain the low nibble.
    measurement = raw.astype(np.int32) >> 4
    return measurement.astype(np.float64) * gain * math.sqrt(2)


@dataclass(frozen=True, slots=True, eq=False)
class Ben5kRecord(BenRecord):
    """Legacy-only projection; inherited raw_values/sample_words stay untouched."""

    fast_ac_channel_ids: frozenset[int] = frozenset()

    def uses_fast_ac_contract(self, channel: BenValueChannel) -> bool:
        return (
            channel.channel_id in self.fast_ac_channel_ids
            and channel.kind == BenChannelKind.ANALOG
            and (channel.measurement, channel.quantity_code, channel.unit, channel.unit_code)
                in (("voltage", 0, "kV", 29), ("current", 4, "kA", 5))
            and channel.unit_multiplier_exponent == 3
            and channel.phase_code in (1, 2, 3, 4)
            and channel.offset == 0.0
            and math.isfinite(channel.scale)
            and channel.invalid_raw_value is None
        )

    def engineering_values(self, channel: BenValueChannel) -> np.ndarray:
        if self.uses_fast_ac_contract(channel):
            return fast_ac_engineering_values(self.raw_values(channel), channel.scale, channel.offset)
        # Explicit class call avoids dataclass(slots=True)'s zero-argument super
        # class-replacement pitfall. SubBen's implementation itself is unchanged.
        return BenRecord.engineering_values(self, channel)
