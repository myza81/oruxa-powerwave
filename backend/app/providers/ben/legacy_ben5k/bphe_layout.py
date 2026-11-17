"""Bounded BPHE acquisition layout, established by the independent CFG/DAT.

The flat descriptors contain logical selectors, not a proven universal physical
address. Keep the exact descriptor/column matches rather than inventing a sparse
packing rule. Configuration identity excludes the event clock and sample payload.
"""
from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

from app.providers.ben import layout
from app.providers.ben.errors import BenStructureError

if TYPE_CHECKING:
    from app.providers.ben.legacy_ben5k.reader import Ben5kAnalogChannel

BPHE_CONFIGURATION_SHA256 = "2fc25dfff1207c0a411c533a88adb96661e6c503ab89c430074bca43c05569fe"

# (descriptor byte offset, original logical word, physical word, quantity, phase).
# Source: pinned BPHE independent export comparison, all 1,148 samples per column.
# Names are deliberately NOT keys: the two second-feeder VR names are distinct.
BPHE_ANALOG_POSITIONS = (
    (0x354, 0, 0, 0, 1), (0x4C0, 1, 1, 0, 2), (0x608, 2, 2, 0, 3),
    (0x826, 4, 4, 4, 1), (0x94A, 5, 5, 4, 2), (0xA6E, 6, 6, 4, 3),
    (0xBB6, 7, 7, 4, 4),
    (0xEB6, 16, 11, 0, 1), (0xFFE, 17, 12, 0, 2), (0x116A, 18, 13, 0, 3),
    (0x1388, 20, 15, 4, 1), (0x14AC, 21, 16, 4, 2),
    (0x15D0, 22, 17, 4, 3), (0x1718, 23, 18, 4, 4),
)


def is_reviewed_bphe_configuration(data: bytes, payload_offset: int) -> bool:
    return (
        len(data) >= layout.HEADER_SIZE
        and data[:4] == layout.BEN_FAMILY_SIGNATURE
        and data[4:12] == layout.BEN5K_LAYOUT_SIGNATURE
        and data[14:16] == layout.BEN5K_GENERATION_MARKER
        and data[layout.RECORD_CLASS_FLAG_OFFSET] == 0
        and payload_offset > layout.HEADER_SIZE
        and hashlib.sha256(data[layout.HEADER_SIZE:payload_offset]).hexdigest() == BPHE_CONFIGURATION_SHA256
    )


def bphe_physical_words(analog: list[Ben5kAnalogChannel], words_per_sample: int) -> dict[int, int]:
    """Validate the complete descriptor inventory before addressing any column.

    Caller must first establish the reviewed configuration identity. This function
    never estimates an address from sample amplitude or drops an unmatched input.
    """
    identities = tuple((c.descriptor_offset, c.word_index, c.type_byte, c.phase_seq) for c in analog)
    expected = tuple((off, logical, quantity, phase) for off, logical, _, quantity, phase in BPHE_ANALOG_POSITIONS)
    if words_per_sample != 24 or identities != expected:
        raise BenStructureError("BPHE reviewed analog descriptor inventory or acquisition width disagrees")
    return {off: physical for off, _, physical, _, _ in BPHE_ANALOG_POSITIONS}
