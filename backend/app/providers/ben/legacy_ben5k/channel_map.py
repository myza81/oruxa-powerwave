"""Channel classification for the BEN5K flat config layout.

Separates the raw descriptor lists produced by reader.py into six
mutually exclusive groups so the normalizer knows exactly which channels
have genuine recorded waveform data and which are merely configured.

Rules (in order, first match wins):
  - Digital group 0  →  unsupported_digital   (SENS OUT channels, different
                          addressing scheme; not decoded in this version)
  - Digital group 1-N, sw >= words_per_sample  →  inactive_digital
    (structurally out of bounds; cannot be decoded safely)
  - Digital group 1-N, sw in bounds AND column is constant 0x0800
                       →  constant_placeholder_digital
    (confirmed inactive-feeder placeholder value; only classified when
    sample_words is provided; other constant values fall through to verified)
  - Digital group 1-N, sw in bounds AND (varying OR constant ≠ 0x0800)
                       →  verified_digital
    (genuine bitmask data, or legitimately constant signal during recording)
  - Analog word_index >= first_digital_sw  →  inactive_analog
    (word falls in the digital bitmask or constant region)
  - Analog word_index already claimed by an earlier channel  →  inactive_analog
    (inactive feeder reusing the same 0–7 local offsets as an active feeder)
  - Otherwise  →  recorded_analog

``first_digital_sample_word`` is the minimum sample_word_index among ALL
in-bounds candidate digital channels (verified + constant_placeholder
combined).  This is the boundary used to classify analog channels, so that
analog words that overlap the digital region are correctly excluded even when
those digital words happen to carry constant values.

``digital_bitmask_word_count`` counts only the distinct sample words whose
columns have confirmed variance (i.e. verified_digital words only).

In the GPTH 275 kV recording (sample_words provided):
  verified_digital             groups 1-5  →  sample words 38-42 (varying)
  constant_placeholder_digital groups 6-40 →  sample words 43-77 (constant 0x0800)
  recorded_analog              wi 0-37     →  TBIN1/SDAI1/SDNK1/TBIN2/SDAI2 channels
  inactive_analog              wi 38-39    →  SDAI2 IB/IN (wi in digital region)
  inactive_analog              wi 0-7 ×3   →  SDNK2/SGT1-2/PLNG1-2 (duplicate wi)
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.providers.ben.legacy_ben5k.reader import Ben5kAnalogChannel, Ben5kDigitalChannel

_UNSUPPORTED_WORD_GROUP = 0

# Confirmed inactive-feeder placeholder raw value in the GPTH 275 kV recording.
# Inactive feeder word slots carry exactly this value across all samples.
# This is the ONLY raw value that triggers constant_placeholder_digital; a
# constant column with any other value (e.g. 0xFFFF quiescent) is classified
# as verified_digital (legitimately constant signal, no transitions recorded).
_PLACEHOLDER_CONSTANT_VALUE: int = 0x0800


@dataclass(frozen=True)
class Ben5kChannelMap:
    """Classified channel lists for one BEN5K recording."""

    # Analog channels with confirmed recorded waveform data.
    recorded_analog: tuple[Ben5kAnalogChannel, ...]

    # Analog channels whose word_index falls outside the confirmed active
    # analog region — either in the digital bitmask zone, the
    # constant-placeholder zone, or a duplicate of an already-claimed
    # word_index (inactive feeder sharing the same local offset).
    inactive_analog: tuple[Ben5kAnalogChannel, ...]

    # Digital channels whose sample word is in bounds and has confirmed
    # variance across samples (genuine bitmask data).
    verified_digital: tuple[Ben5kDigitalChannel, ...]

    # Digital channels whose sample_word_index >= words_per_sample
    # (structurally out of bounds; cannot be safely decoded).
    inactive_digital: tuple[Ben5kDigitalChannel, ...]

    # Group-0 digital channels (SENS OUT) — addressing scheme unconfirmed;
    # not decoded in this version.
    unsupported_digital: tuple[Ben5kDigitalChannel, ...]

    # Digital channels whose sample word is in bounds and carries the constant
    # value 0x0800 across all samples (confirmed inactive-feeder placeholder).
    # Channels with a different constant value (e.g. 0xFFFF quiescent) stay in
    # verified_digital so legitimately-constant signals are not hidden.
    # Empty when classify_channels() is called without sample_words.
    constant_placeholder_digital: tuple[Ben5kDigitalChannel, ...]

    # First sample word in the digital region (38 in GPTH).
    # Equals words_per_sample when there are no in-bounds candidate channels.
    first_digital_sample_word: int

    # Number of distinct sample words with confirmed variance (verified only).
    digital_bitmask_word_count: int


def classify_channels(
    analog: list[Ben5kAnalogChannel],
    digital: list[Ben5kDigitalChannel],
    words_per_sample: int,
    *,
    sample_words: np.ndarray | None = None,
) -> Ben5kChannelMap:
    """Classify *analog* and *digital* descriptor lists into availability groups.

    Args:
        analog: All analog channel descriptors from reader.read_channel_descriptors().
        digital: All digital channel descriptors from reader.read_channel_descriptors().
        words_per_sample: Total sample words (from Ben5kHeader.words_per_sample).
        sample_words: Optional (n_samples × words_per_sample) uint16 array.
            When provided, in-bounds digital channels whose sample-word column
            carries the constant value 0x0800 across all samples are classified
            as constant_placeholder_digital rather than verified_digital.
            Other constant-value columns (e.g. 0xFFFF quiescent) stay in
            verified_digital — they represent real channels that did not
            transition during this recording.

    Returns:
        Ben5kChannelMap with all six classification groups populated.
    """
    # ── Classify digital channels ─────────────────────────────────────────

    unsupported_digital: list[Ben5kDigitalChannel] = []
    candidate_digital: list[Ben5kDigitalChannel] = []  # group >= 1

    for ch in digital:
        if ch.word_group == _UNSUPPORTED_WORD_GROUP:
            unsupported_digital.append(ch)
        else:
            candidate_digital.append(ch)

    # Structural split: out-of-bounds cannot be decoded at all.
    in_bounds: list[Ben5kDigitalChannel] = []
    inactive_digital: list[Ben5kDigitalChannel] = []
    for ch in candidate_digital:
        if ch.sample_word_index < words_per_sample:
            in_bounds.append(ch)
        else:
            inactive_digital.append(ch)

    # Placeholder split: when sample_words is available, in-bounds channels
    # whose column carries the constant 0x0800 value are inactive-feeder
    # placeholders.  A constant value other than 0x0800 (e.g. 0xFFFF
    # quiescent) means the channel is real but did not transition during
    # this recording — keep it in verified_digital so it is not hidden.
    # Without sample_words all in-bounds channels are treated as verified.
    verified_digital: list[Ben5kDigitalChannel] = []
    constant_placeholder_digital: list[Ben5kDigitalChannel] = []
    if sample_words is not None:
        for ch in in_bounds:
            col = sample_words[:, ch.sample_word_index]
            col_min = int(col.min())
            if col_min == int(col.max()) == _PLACEHOLDER_CONSTANT_VALUE:
                constant_placeholder_digital.append(ch)
            else:
                verified_digital.append(ch)
    else:
        verified_digital = list(in_bounds)

    # ── Compute boundary fields ───────────────────────────────────────────

    # first_digital_sw uses ALL in-bounds channels so that analog channels
    # at wi=38 are excluded even when those digital words carry constant values.
    all_in_bounds_sws = sorted({ch.sample_word_index for ch in in_bounds})
    first_digital_sw = all_in_bounds_sws[0] if all_in_bounds_sws else words_per_sample

    # bitmask_count counts only words with confirmed variance.
    verified_sws = sorted({ch.sample_word_index for ch in verified_digital})
    bitmask_count = len(verified_sws)

    # ── Classify analog channels ──────────────────────────────────────────

    claimed_words: set[int] = set()
    recorded_analog: list[Ben5kAnalogChannel] = []
    inactive_analog: list[Ben5kAnalogChannel] = []

    for ch in analog:
        if ch.word_index >= first_digital_sw:
            inactive_analog.append(ch)
        elif ch.word_index in claimed_words:
            inactive_analog.append(ch)
        else:
            claimed_words.add(ch.word_index)
            recorded_analog.append(ch)

    return Ben5kChannelMap(
        recorded_analog=tuple(recorded_analog),
        inactive_analog=tuple(inactive_analog),
        verified_digital=tuple(verified_digital),
        inactive_digital=tuple(inactive_digital),
        unsupported_digital=tuple(unsupported_digital),
        constant_placeholder_digital=tuple(constant_placeholder_digital),
        first_digital_sample_word=first_digital_sw,
        digital_bitmask_word_count=bitmask_count,
    )
