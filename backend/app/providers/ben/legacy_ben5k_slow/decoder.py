"""Sample-matrix decoder for the BEN5K Slow flat binary layout.

Extracts the sample payload and returns:
  - The raw unsigned sample matrix for diagnostics
  - Per-channel signed int16 columns for TENTATIVE channels

BEN5K Slow stores calculated trend quantities (frequency, active power,
reactive power, voltage RMS) at 20 samples/s.  This is NOT instantaneous
waveform data -- do not confuse it with the 3 000-7 200 sps BEN5K Fast format.

Critical: use .astype(np.int16) NOT .view(np.int16) on the big-endian array.
.view() reinterprets bytes without numeric conversion, producing byte-swapped
values on little-endian systems.

Scale factors for BEN5K Slow channels are not yet confirmed from descriptor
bytes 24-27 (scale_ref_raw).  All values are returned as raw int16 with
unit 'raw' pending oracle validation.
"""

from __future__ import annotations

import numpy as np

from app.providers.ben.errors import BenStructureError, BenTruncatedError
from app.providers.ben.legacy_ben5k_slow.reader import (
    Ben5kSlowHeader,
    SlowChannelDescriptor,
    SlowChannelStatus,
)

_UNAVAILABLE_WORD = 0xFFFF    # same as BEN5K Fast: word value meaning inactive/unavailable


def extract_raw_matrix(data: bytes, header: Ben5kSlowHeader) -> np.ndarray:
    """Return the full raw sample matrix as unsigned big-endian u16.

    Shape: (sample_count, words_per_sample).
    Useful for diagnostics and for reading channel columns.
    """
    payload_bytes = header.sample_count * header.words_per_sample * 2
    payload_offset = len(data) - payload_bytes
    if payload_offset <= 0:
        raise BenTruncatedError(
            f"BEN5K Slow payload ({payload_bytes} bytes) exceeds file size ({len(data)})"
        )
    return np.frombuffer(
        data,
        dtype=">u2",
        count=header.sample_count * header.words_per_sample,
        offset=payload_offset,
    ).reshape(header.sample_count, header.words_per_sample)


def extract_channel_columns(
    data: bytes,
    header: Ben5kSlowHeader,
    channels: list[SlowChannelDescriptor],
) -> np.ndarray:
    """Extract signed int16 sample columns for a list of TENTATIVE channels.

    Args:
        data: full BEN5K Slow file bytes.
        header: decoded Ben5kSlowHeader.
        channels: list of TENTATIVE SlowChannelDescriptor objects whose
            word_index_tentative values are all in [1, words_per_sample).
            Non-TENTATIVE channels must not be passed.

    Returns:
        int16 array, shape (sample_count, len(channels)).
        Values are raw int16 (big-endian u16 reinterpreted as signed).
        0xFFFF (unavailable) becomes -1 in int16, not filtered out.

    Raises:
        BenStructureError: a channel's word_index_tentative is out of bounds
            or the channel has a non-TENTATIVE status.
        BenTruncatedError: payload does not fit the declared dimensions.
    """
    if not channels:
        return np.empty((header.sample_count, 0), dtype=np.int16)

    # Validate before allocating
    for ch in channels:
        if ch.status != SlowChannelStatus.TENTATIVE:
            raise BenStructureError(
                f"BEN5K Slow channel {ch.name!r} has status {ch.status.name}, "
                f"expected TENTATIVE; only TENTATIVE channels may be decoded"
            )
        if ch.word_index_tentative == 0 or ch.word_index_tentative >= header.words_per_sample:
            raise BenStructureError(
                f"BEN5K Slow channel {ch.name!r} word_index {ch.word_index_tentative} "
                f"is out of bounds [1, {header.words_per_sample})"
            )

    raw = extract_raw_matrix(data, header)
    indices = [ch.word_index_tentative for ch in channels]
    # MUST use .astype(np.int16), NOT .view(np.int16).
    return raw[:, indices].astype(np.int16)


def sample_word_inventory(raw: np.ndarray) -> list[dict]:
    """Produce a per-word diagnostic inventory from a raw sample matrix.

    Returns a list of dicts (one per word column) containing:
      word_index, min_unsigned, max_unsigned, min_signed, max_signed,
      count_unavailable (0xFFFF), count_zero, unique_count, is_constant.
    """
    n_samples, n_words = raw.shape
    inventory = []
    signed = raw.astype(np.int16)
    for w in range(n_words):
        col_u = raw[:, w]
        col_s = signed[:, w]
        inventory.append({
            "word_index": w,
            "min_unsigned": int(col_u.min()),
            "max_unsigned": int(col_u.max()),
            "min_signed": int(col_s.min()),
            "max_signed": int(col_s.max()),
            "count_unavailable": int(np.sum(col_u == _UNAVAILABLE_WORD)),
            "count_zero": int(np.sum(col_u == 0)),
            "unique_count": int(len(np.unique(col_u))),
            "is_constant": bool(col_u.min() == col_u.max()),
        })
    return inventory
