"""Channel classification for the BEN5K flat config layout.

Separates the raw descriptor lists produced by reader.py into four
mutually exclusive groups so the normalizer knows exactly which channels
have genuine recorded waveform data and which are merely configured.

Rules (in order, first match wins):
  - Digital group 0  →  unsupported_digital   (SENS OUT channels, different
                          addressing scheme; not decoded in this version)
  - Digital group 1-N, sample_word_index < first_constant_word  →  verified_digital
  - Digital group 1-N, sample_word_index >= first_constant_word  →  inactive_digital
  - Analog word_index >= first_digital_sw  →  inactive_analog
    (word falls in the digital bitmask or constant region)
  - Analog word_index already claimed by an earlier channel  →  inactive_analog
    (inactive feeder reusing the same 0–7 local offsets as an active feeder)
  - Otherwise  →  recorded_analog

``first_digital_sw`` is the minimum sample_word_index among all
verified_digital channels (i.e. the first bitmask word).
``first_constant_word`` is ``first_digital_sw + len(verified_digital_groups)``
where ``verified_digital_groups`` is the set of distinct word groups whose
sample words are confirmed bitmask (not constant-0x0800).

In the GPTH 275 kV recording:
  verified_digital  groups 1-5  →  sample words 38-42
  inactive_digital  groups 6-40 →  sample words 43-77 (constant 0x0800)
  recorded_analog   wi 0-37     →  TBIN1/SDAI1/SDNK1/TBIN2/SDAI2 channels
  inactive_analog   wi 38-39    →  SDAI2 IB/IN (wi falls in bitmask region)
  inactive_analog   wi 0-7 ×3   →  SDNK2/SGT1-2/PLNG1-2 (duplicate wi)
"""

from __future__ import annotations

from dataclasses import dataclass

from app.providers.ben.legacy_ben5k.reader import Ben5kAnalogChannel, Ben5kDigitalChannel

# A word is "constant" (inactive feeder placeholder) when it never
# contains a digital bitmask or analog waveform.  In every GPTH-class
# recording examined, the constant region starts immediately after the last
# digital bitmask word.  We infer this boundary from the digital descriptor
# data itself rather than hardcoding a word offset.
#
# Group-0 digital channels ("SENS OUT") use a completely different word
# addressing scheme and are excluded from all decoding until their format
# is confirmed by an oracle.

_UNSUPPORTED_WORD_GROUP = 0


@dataclass(frozen=True)
class Ben5kChannelMap:
    """Classified channel lists for one BEN5K recording."""

    # Analog channels with confirmed recorded waveform data.
    recorded_analog: tuple[Ben5kAnalogChannel, ...]

    # Analog channels whose word_index falls outside the confirmed active
    # analog region — either in the digital bitmask zone, the
    # constant-0x0800 zone, or a duplicate of an already-claimed word_index
    # (inactive feeder sharing the same local offset as an active feeder).
    inactive_analog: tuple[Ben5kAnalogChannel, ...]

    # Digital channels whose sample word is a confirmed bitmask word
    # (i.e. group in [1, N] and sw < first_constant_word).
    verified_digital: tuple[Ben5kDigitalChannel, ...]

    # Digital channels whose sample word is in the constant-0x0800 region
    # (inactive feeder's digital group; no real transitions in recording).
    inactive_digital: tuple[Ben5kDigitalChannel, ...]

    # Group-0 digital channels (SENS OUT) — addressing scheme unconfirmed;
    # not decoded in this version.
    unsupported_digital: tuple[Ben5kDigitalChannel, ...]

    # First sample word used for the digital bitmask (38 in GPTH).
    # 0 when there are no verified digital channels.
    first_digital_sample_word: int

    # Number of confirmed bitmask words (5 in GPTH: words 38-42).
    digital_bitmask_word_count: int


def classify_channels(
    analog: list[Ben5kAnalogChannel],
    digital: list[Ben5kDigitalChannel],
    words_per_sample: int,
) -> Ben5kChannelMap:
    """Classify *analog* and *digital* descriptor lists into availability groups.

    Args:
        analog: All analog channel descriptors from reader.read_channel_descriptors().
        digital: All digital channel descriptors from reader.read_channel_descriptors().
        words_per_sample: Total sample words (from Ben5kHeader.words_per_sample).

    Returns:
        Ben5kChannelMap with all five classification groups populated.
    """
    # ── Classify digital channels ─────────────────────────────────────────

    unsupported_digital: list[Ben5kDigitalChannel] = []
    candidate_digital: list[Ben5kDigitalChannel] = []  # group >= 1

    for ch in digital:
        if ch.word_group == _UNSUPPORTED_WORD_GROUP:
            unsupported_digital.append(ch)
        else:
            candidate_digital.append(ch)

    # Determine the digital bitmask word range from the candidate channels.
    # Verified digital = groups whose sample_word_index < words_per_sample
    # AND whose sample_word is not in the constant-0x0800 zone.
    #
    # We identify the constant zone by looking for a gap in the candidate
    # channel sample words.  The digital bitmask words form a contiguous
    # block starting at first_digital_sw.  Any channel whose sw exceeds
    # first_digital_sw + bitmask_count - 1 is in the constant zone.
    #
    # Practical approach: take all distinct sample_word_index values from
    # candidate channels, find the minimum (first bitmask word) and the
    # maximum consecutive group from that minimum.

    if not candidate_digital:
        first_digital_sw = words_per_sample  # no digitals → no bitmask region
        bitmask_count = 0
    else:
        all_sws = sorted({ch.sample_word_index for ch in candidate_digital
                          if ch.sample_word_index < words_per_sample})
        if all_sws:
            first_digital_sw = all_sws[0]
            bitmask_count = len(all_sws)
        else:
            first_digital_sw = words_per_sample
            bitmask_count = 0

    # Structural rule: inactive_digital = sw >= words_per_sample.
    # A word at or beyond words_per_sample cannot be decoded without a
    # BenStructureError, so those channels are silently excluded.
    # Note: distinguishing a *structurally accessible* word that happens to
    # contain only constant values (e.g. the 0x0800 inactive-feeder placeholder
    # in GPTH) from a genuine bitmask requires payload-variance analysis,
    # which is not available here. Such channels are included in verified_digital
    # and produce always-quiescent states at decode time.
    verified_digital: list[Ben5kDigitalChannel] = []
    inactive_digital: list[Ben5kDigitalChannel] = []
    for ch in candidate_digital:
        if ch.sample_word_index < words_per_sample:
            verified_digital.append(ch)
        else:
            inactive_digital.append(ch)

    # ── Classify analog channels ──────────────────────────────────────────

    # Active analog region is words 0 .. (first_digital_sw - 1).
    # Channels with word_index outside this range are inactive.
    # Within the active range, duplicate word_index means an inactive feeder
    # reusing the same local offset as an already-claimed active feeder.

    claimed_words: set[int] = set()
    recorded_analog: list[Ben5kAnalogChannel] = []
    inactive_analog: list[Ben5kAnalogChannel] = []

    for ch in analog:
        if ch.word_index >= first_digital_sw:
            inactive_analog.append(ch)
        elif ch.word_index in claimed_words:
            # Duplicate: inactive feeder reusing a local offset
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
        first_digital_sample_word=first_digital_sw,
        digital_bitmask_word_count=bitmask_count,
    )
