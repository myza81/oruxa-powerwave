"""Builds small, structurally faithful BEN32 SubBen files for tests.

Written from the layout documented in docs/project-memory/BEN_FORMAT.md
with its own literal offsets -- deliberately NOT importing
app.providers.ben.layout -- so a regression in the parser's constants
cannot be masked by the builder sharing them.

Everything the parser must derive (rate, counts, stride, channel word
and bit positions, record class) is a free parameter here, so tests can
build layouts unlike any real reference file.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

import numpy as np


@dataclass
class SynthValue:
    channel_id: int
    name: str
    word: int
    unit_code: int = 29  # V
    multiplier: int = 3  # k
    phase_code: int = 1
    quantity_code: int = 0
    scale: float = 0.5
    offset: float = 0.0
    primary: float = 400.0
    secondary: float = 110.0
    bay: str | None = None


@dataclass
class SynthDigital:
    """``derived`` bits are carried by ``bit_id`` (a trigger id);
    ``physical`` bits by ``bit_id`` (a physical digital id)."""

    source: str  # "physical" | "derived"
    bit_id: int
    name: str
    word: int
    bit: int
    source_channel_id: int = 0  # derived: the value channel it watches
    event_name: str | None = None
    bay: str | None = None


@dataclass
class SynthBen:
    record_class: str = "fast"  # "fast" | "slow"
    rate_field: int = 1_200_000
    pre_trigger: int = 10
    words_per_sample: int = 7
    values: list[SynthValue] = field(default_factory=list)
    digitals: list[SynthDigital] = field(default_factory=list)
    samples: np.ndarray | None = None  # (n, words) uint16 word values
    trigger: tuple[int, ...] = (2024, 3, 5, 6, 7, 8, 12, 34, 56)  # y m d h m s + base-100 digits
    station: str = "SYNTH STATION"
    unit_id: int = 4321
    record_number: int = 777
    extra_sections: list[tuple[int, bytes]] = field(default_factory=list)
    #: Optional overrides (for malformed-file tests), keyed by field name.
    override: dict[str, int] = field(default_factory=dict)

    @property
    def is_fast(self) -> bool:
        return self.record_class == "fast"

    def build(self) -> tuple[bytes, dict[str, int]]:
        """Return (file bytes, absolute offsets of interesting structures)."""
        assert self.samples is not None
        n = self.samples.shape[0]
        offsets: dict[str, int] = {}
        ov = self.override

        header = bytearray(0xDC)
        header[0x00:0x0C] = b"\x01\x00\x04\x00\x2a\xff\x03\x00\x6e\x00\xca\x00"
        struct.pack_into("<H", header, 0x0C, self.unit_id)
        header[0x0E:0x10] = b"\x06\xff"
        header[0x10 : 0x10 + len(self.station)] = self.station.encode("latin-1")
        struct.pack_into("<I", header, 0x38, self.record_number)
        header[0x3C] = ov.get("class_flag", 0 if self.is_fast else 1)
        header[0x3D] = 0xFF
        header[0x42:0x4C] = b"New Record"
        struct.pack_into("<III", header, 0x54, self.rate_field, self.pre_trigger, ov.get("sample_count", n))
        struct.pack_into("<H", header, 0x60, ov.get("words", self.words_per_sample))
        year, month, day, hour, minute, second, *digits = self.trigger
        header[0x64:0x6D] = bytes([year - 1900, month, day, hour, minute, second, *digits])
        struct.pack_into("<I", header, 0x7A, ov.get("last_index", n - 1))

        body = bytearray(header)

        def section(type_code: int, payload: bytes) -> None:
            offsets[f"section_{type_code:04x}"] = len(body)
            body.extend(struct.pack("<HHI", type_code, 0xFFFF, len(payload)))
            body.extend(payload)

        def records(chunks: list[bytes]) -> bytes:
            return struct.pack("<HH", len(chunks), 0xFFFF) + b"".join(chunks)

        names = _Strings()
        event_names = _Strings()
        bay_names = _Strings()
        bays = sorted({c.bay for c in [*self.values, *self.digitals] if c.bay})
        bay_ids = {bay: 1_000_100 + i for i, bay in enumerate(bays)}

        section(0x0001, bytes(24))
        class_record = bytearray(84)
        struct.pack_into("<I", class_record, 0, ov.get("class_code", 1006 if self.is_fast else 1007))
        class_name = b"Fast SubBen" if self.is_fast else b"Slow SubBen"
        class_record[12 : 12 + len(class_name)] = class_name
        struct.pack_into("<I", class_record, 36, ov.get("class_rate", self.rate_field))
        struct.pack_into("<I", class_record, 52, self.pre_trigger)
        section(0x06A4, records([bytes(class_record)]))

        value_records = []
        trigger_of: dict[int, int] = {}
        for d in self.digitals:
            if d.source == "derived":
                trigger_of.setdefault(d.source_channel_id, d.bit_id)
        for v in self.values:
            if self.is_fast:
                rec = bytearray(52)
                struct.pack_into("<HHH", rec, 0, v.channel_id, trigger_of.get(v.channel_id, 0), 21_000 + v.channel_id % 1000)
                struct.pack_into("<H", rec, 8, names.add(v.name))
                rec[10:16] = bytes([1, 1, v.quantity_code, v.phase_code, v.unit_code, v.multiplier])
                struct.pack_into("<ff", rec, 16, v.scale, v.offset)
                struct.pack_into("<f", rec, 28, v.primary)
                struct.pack_into("<f", rec, 36, v.secondary)
                struct.pack_into("<H", rec, 44, 0x0100 + v.channel_id % 16)
                rec[46:52] = b"\xff" * 6
            else:
                rec = bytearray(164)
                struct.pack_into("<HH", rec, 0, v.channel_id, trigger_of.get(v.channel_id, 0))
                struct.pack_into("<H", rec, 6, 21_000 + v.channel_id % 1000)
                struct.pack_into("<H", rec, 8, names.add(v.name))
                rec[10:16] = bytes([1, 2, v.quantity_code, v.phase_code, v.unit_code, v.multiplier])
                struct.pack_into("<ff", rec, 16, v.scale, v.offset)
            value_records.append(bytes(rec))
        section(0x0514 if self.is_fast else 0x0516, records(value_records))

        physical = [d for d in self.digitals if d.source == "physical"]
        if physical:
            recs = []
            for d in physical:
                rec = bytearray(18)
                struct.pack_into("<HHH", rec, 0, d.bit_id, 0, 21_500 + d.bit_id % 500)
                struct.pack_into("<H", rec, 8, names.add(d.name))
                rec[10:12] = b"\x01\x01"
                struct.pack_into("<H", rec, 12, 0x80 + d.bit_id % 64)
                rec[16:18] = b"\xff\xff"
                recs.append(bytes(rec))
            section(0x0515, records(recs))

        section(0x0518, names.table())

        derived = [d for d in self.digitals if d.source == "derived"]
        section(0x0578, records([struct.pack("<H", d.bit_id) + bytes(208) for d in derived]))

        events = []
        for i, d in enumerate(self.digitals):
            rec = bytearray(86)
            struct.pack_into("<HH", rec, 0, 21_000 + i, event_names.add(d.event_name or d.name))
            if d.source == "derived":
                struct.pack_into("<HH", rec, 74, d.bit_id, d.source_channel_id)
            else:
                struct.pack_into("<HH", rec, 74, 0, d.bit_id)
            events.append(bytes(rec))
        section(0x0579, records(events))
        section(0x057A, event_names.table())

        for type_code, payload in self.extra_sections:
            section(type_code, payload)

        if bays:
            bay_recs = []
            for bay in bays:
                rec = bytearray(28)
                struct.pack_into("<II", rec, 0, bay_ids[bay], 1_000_000)
                struct.pack_into("<H", rec, 8, bay_names.add(f"{self.station} : {bay}"))
                bay_recs.append(bytes(rec))
            section(0x06A6, records(bay_recs))
            chan_recs = []
            for v in self.values:
                if v.bay:
                    rec = bytearray(36)
                    struct.pack_into("<II", rec, 0, 1_001_000 + v.channel_id % 1000, bay_ids[v.bay])
                    struct.pack_into("<H", rec, 16, v.channel_id)
                    chan_recs.append(bytes(rec))
            section(0x06A7, records(chan_recs))
            card_recs = []
            for bay in bays:
                members = [d.bit_id for d in self.digitals if d.bay == bay][:8]
                rec = bytearray(52)
                struct.pack_into("<II", rec, 0, 1_002_000 + bay_ids[bay] % 1000, bay_ids[bay])
                struct.pack_into(f"<{len(members)}I", rec, 20, *members)
                card_recs.append(bytes(rec))
            section(0x06A9, records(card_recs))
            section(0x06AA, bay_names.table())

        # Sample-layout container.
        summary = bytearray(60)
        struct.pack_into("<IHH", summary, 0, ov.get("summary_record_number", self.record_number), 1006 if self.is_fast else 1007, 0x0108)
        struct.pack_into("<H", summary, 24, ov.get("summary_words", self.words_per_sample))
        struct.pack_into("<III", summary, 28, self.rate_field, self.pre_trigger, ov.get("summary_sample_count", n))
        entries = [struct.pack("<HHBB", v.channel_id, v.word, ov.get("value_bit", 0), 0) for v in self.values]
        entries += [struct.pack("<HHBB", d.bit_id, d.word, d.bit, 3) for d in self.digitals]
        layout_payload = records(entries)
        blocks = b"".join(
            struct.pack("<HHI", t, 0xFFFF, len(p)) + p
            for t, p in ((0x4E20, bytes(96)), (0x4E21, bytes(summary)), (0x4E25, layout_payload))
        )
        offsets["container"] = len(body)
        body.extend(struct.pack("<HI", 0x03E8, len(blocks)))
        offsets["layout_entries"] = len(body) + 8 + 96 + 8 + 60 + 8 + 4
        body.extend(blocks)
        body.extend(struct.pack("<H", 0x07D0))
        offsets["data"] = len(body)
        body.extend(self.samples.astype(">u2").tobytes())
        return bytes(body), offsets


class _Strings:
    def __init__(self) -> None:
        self._data = bytearray(b"\0")

    def add(self, text: str) -> int:
        offset = len(self._data)
        self._data.extend(text.encode("latin-1") + b"\0")
        return offset

    def table(self) -> bytes:
        return bytes(self._data)


def active_low(active: np.ndarray) -> np.ndarray:
    """Stored bit values for the given active (1) / inactive (0) states."""
    return 1 - np.asarray(active, dtype=np.uint16)


def to_word(raw: np.ndarray) -> np.ndarray:
    """Signed raw values -> their 16-bit word pattern."""
    return np.asarray(raw, dtype=np.int16).astype(np.uint16)
