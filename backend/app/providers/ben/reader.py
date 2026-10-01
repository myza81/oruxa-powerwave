"""Bounds-checked primitives for reading BEN configuration bytes.

Every read goes through ``ByteView`` so an out-of-range offset becomes a
``BenTruncatedError`` naming the offset, never an ``IndexError`` or a
silently short slice.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from app.providers.ben import layout
from app.providers.ben.errors import BenStructureError, BenTruncatedError

_TEXT_ENCODING = "latin-1"


@dataclass(frozen=True, slots=True)
class ByteView:
    """A window of the file; ``start`` is its absolute file offset."""

    data: bytes
    start: int
    end: int

    @classmethod
    def whole(cls, data: bytes) -> ByteView:
        return cls(data, 0, len(data))

    def _check(self, rel: int, size: int, what: str) -> int:
        pos = self.start + rel
        if rel < 0 or pos + size > self.end:
            raise BenTruncatedError(f"{what} ({size} bytes) lies outside its structure", offset=pos)
        return pos

    def u8(self, rel: int, what: str = "u8 field") -> int:
        return self.data[self._check(rel, 1, what)]

    def u16(self, rel: int, what: str = "u16 field") -> int:
        return struct.unpack_from("<H", self.data, self._check(rel, 2, what))[0]

    def u32(self, rel: int, what: str = "u32 field") -> int:
        return struct.unpack_from("<I", self.data, self._check(rel, 4, what))[0]

    def f32(self, rel: int, what: str = "f32 field") -> float:
        return struct.unpack_from("<f", self.data, self._check(rel, 4, what))[0]

    def raw(self, rel: int, size: int, what: str = "field") -> bytes:
        pos = self._check(rel, size, what)
        return self.data[pos : pos + size]

    def text(self, rel: int, size: int, what: str = "text field") -> str:
        """Fixed-size NUL-terminated text; bytes after the NUL are ignored."""
        return self.raw(rel, size, what).split(b"\0", 1)[0].decode(_TEXT_ENCODING).strip()

    def sub(self, rel: int, size: int, what: str = "structure") -> ByteView:
        pos = self._check(rel, size, what)
        return ByteView(self.data, pos, pos + size)

    @property
    def size(self) -> int:
        return self.end - self.start


@dataclass(frozen=True, slots=True)
class Section:
    type_code: int
    offset: int  # absolute offset of the section frame
    payload: ByteView


def read_section(view: ByteView, rel: int) -> Section:
    """Read one ``u16 type | u16 0xFFFF | u32 length | payload`` section."""
    type_code = view.u16(rel, "section type")
    marker = view.u16(rel + 2, "section marker")
    if marker != layout.SECTION_MARKER:
        raise BenStructureError(
            f"section type {type_code:#06x} has marker {marker:#06x}, expected {layout.SECTION_MARKER:#06x}",
            offset=view.start + rel,
        )
    length = view.u32(rel + 4, "section length")
    payload = view.sub(rel + layout.SECTION_FRAME_SIZE, length, f"section {type_code:#06x} payload")
    return Section(type_code, view.start + rel, payload)


def record_entries(section: Section, record_size: int) -> list[ByteView]:
    """Split a record section into its fixed-size records.

    The declared count, the marker and the declared payload length must
    all agree exactly -- a record section is never partially trusted.
    """
    payload = section.payload
    count = payload.u16(0, "record count")
    marker = payload.u16(2, "record marker")
    if marker != layout.SECTION_MARKER:
        raise BenStructureError(
            f"record section {section.type_code:#06x} has marker {marker:#06x}",
            offset=payload.start + 2,
        )
    expected = layout.RECORD_SECTION_PREFIX_SIZE + count * record_size
    if expected != payload.size:
        raise BenStructureError(
            f"record section {section.type_code:#06x} declares {count} x {record_size}-byte records "
            f"({expected} bytes) but its length is {payload.size}",
            offset=section.offset,
        )
    base = layout.RECORD_SECTION_PREFIX_SIZE
    return [payload.sub(base + i * record_size, record_size) for i in range(count)]


@dataclass(frozen=True, slots=True)
class StringTable:
    """NUL-terminated names addressed by byte offset within the table."""

    view: ByteView
    type_code: int

    def name(self, offset: int) -> str:
        data = self.view.data
        start = self.view.start + offset
        if offset < 0 or start >= self.view.end:
            raise BenStructureError(
                f"name offset {offset} is outside string table {self.type_code:#06x} "
                f"({self.view.size} bytes)",
                offset=self.view.start,
            )
        stop = data.find(b"\0", start, self.view.end)
        if stop < 0:
            raise BenStructureError(
                f"name at offset {offset} in string table {self.type_code:#06x} is not NUL-terminated",
                offset=start,
            )
        return data[start:stop].decode(_TEXT_ENCODING)
