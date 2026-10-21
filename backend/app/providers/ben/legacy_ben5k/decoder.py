"""Sample-matrix decoder for the BEN5K flat binary layout.

Extracts the sample payload, converts big-endian u16 words to signed int16,
applies per-channel scale/offset, and extracts digital bit states.

Critical: use .astype(np.int16) NOT .view(np.int16) on the big-endian array.
.view() reinterprets bytes without numeric conversion, producing byte-swapped
values on little-endian systems.
"""

from __future__ import annotations

import numpy as np

from app.providers.ben.errors import BenStructureError, BenTruncatedError
from app.providers.ben.legacy_ben5k.reader import Ben5kAnalogChannel, Ben5kDigitalChannel, Ben5kHeader

# Active-low digital convention (same as SubBen):
#   stored bit = 0 → channel is ACTIVE
#   stored bit = 1 → channel is INACTIVE
# This is ASSUMED for BEN5K based on payload observation (0xFFFF quiescent = all-inactive).
# Oracle confirmation required before treating this as authoritative.
_DIGITAL_ACTIVE_LOW = True


def decode_samples(
    data: bytes,
    header: Ben5kHeader,
    analog_channels: list[Ben5kAnalogChannel],
    digital_channels: list[Ben5kDigitalChannel],
) -> tuple[np.ndarray, np.ndarray]:
    """Decode the sample payload into engineering-value arrays.

    Returns:
        analog_eng: float32 array, shape (sample_count, len(analog_channels))
                    Engineering values: scale × raw_int16 + offset
        digital_states: bool array, shape (sample_count, len(digital_channels))
                    True = channel active (active-low assumed: stored 0 → True)

    Raises:
        BenTruncatedError: payload does not fit the declared dimensions
        BenStructureError: a channel word_index is out of bounds
    """
    payload_bytes = header.sample_count * header.words_per_sample * 2
    payload_offset = len(data) - payload_bytes

    if payload_offset <= 0:
        raise BenTruncatedError(
            f"BEN5K payload ({payload_bytes} bytes) exceeds file size ({len(data)})"
        )

    raw = np.frombuffer(
        data,
        dtype=">u2",
        count=header.sample_count * header.words_per_sample,
        offset=payload_offset,
    ).reshape(header.sample_count, header.words_per_sample)

    # ── Analog ────────────────────────────────────────────────────────────────
    if analog_channels:
        indices = [ch.word_index for ch in analog_channels]
        max_wi = max(indices)
        if max_wi >= header.words_per_sample:
            bad = [ch for ch in analog_channels if ch.word_index >= header.words_per_sample]
            raise BenStructureError(
                f"BEN5K analog channel word_index {max_wi} >= words_per_sample "
                f"({header.words_per_sample}); first offending: {bad[0].name!r} "
                f"at descriptor offset 0x{bad[0].descriptor_offset:X}"
            )

        # MUST use .astype(np.int16), NOT .view(np.int16).
        # .view() on a big-endian array reinterprets the raw bytes as LE → wrong values.
        raw_signed = raw[:, indices].astype(np.int16)

        scales = np.array([ch.scale for ch in analog_channels], dtype=np.float32)
        offsets = np.array([ch.offset for ch in analog_channels], dtype=np.float32)
        analog_eng = raw_signed.astype(np.float32) * scales + offsets
    else:
        analog_eng = np.empty((header.sample_count, 0), dtype=np.float32)

    # ── Digital ───────────────────────────────────────────────────────────────
    if digital_channels:
        # Build bool matrix from the confirmed word_group → sample_word formula.
        # sample_word = 37 + word_group (CONFIRMED by payload analysis).
        digital_states = np.empty(
            (header.sample_count, len(digital_channels)), dtype=bool
        )
        for col, ch in enumerate(digital_channels):
            sw = ch.sample_word_index
            if sw >= header.words_per_sample:
                raise BenStructureError(
                    f"BEN5K digital channel {ch.name!r} sample_word {sw} >= "
                    f"words_per_sample ({header.words_per_sample})"
                )
            word_vals = raw[:, sw]
            # Extract the bit at ch.bit_index from each sample word.
            # Big-endian u16: bit 0 is the LSB (bit 0 of the integer value).
            bits = (word_vals >> ch.bit_index) & 1
            if _DIGITAL_ACTIVE_LOW:
                digital_states[:, col] = bits == 0  # stored 0 → active
            else:
                digital_states[:, col] = bits == 1
    else:
        digital_states = np.empty((header.sample_count, 0), dtype=bool)

    return analog_eng, digital_states


def extract_raw_matrix(data: bytes, header: Ben5kHeader) -> np.ndarray:
    """Return the full raw sample matrix as unsigned big-endian u16.

    Shape: (sample_count, words_per_sample).  Useful for diagnostics and tests.
    """
    payload_bytes = header.sample_count * header.words_per_sample * 2
    payload_offset = len(data) - payload_bytes
    if payload_offset <= 0:
        raise BenTruncatedError(
            f"BEN5K payload ({payload_bytes} bytes) exceeds file size ({len(data)})"
        )
    return np.frombuffer(
        data,
        dtype=">u2",
        count=header.sample_count * header.words_per_sample,
        offset=payload_offset,
    ).reshape(header.sample_count, header.words_per_sample)
