"""JSON-safe snapshot of a `CanonicalDistanceProtectionModel` (Slice 8).

The platform keeps no state between requests, and relay-import data must stay
ephemeral, so a review cannot be re-validated by looking an interpretation up on
the server. Instead the upload response carries a *validation context* -- this
snapshot -- which the browser holds in tab memory and sends back with the user's
decisions. The backend decodes it, applies the decisions and re-runs the engine
adapter: validation stays authoritative in the domain and no server session or
store exists.

The decoder is strict: it only builds the registered canonical dataclasses and
enums, rejects unknown types and fields, and goes through each class's own
constructor, so every domain invariant is re-checked. The snapshot is not
authenticated -- it is the user's own session data, and the next slice that acts
on it (Apply) must re-derive or re-verify rather than trust it.

The document-level ``unmapped_settings`` (hundreds of retained raw lines the
adapter never reads) are left out to keep the snapshot small.

DEC-198: catalog references (`DocumentReference`) travel with the snapshot, but an
engine approximation never does -- its record type is deliberately not decodable,
so a context that claims one is refused. Approximations are derived by the backend
from the original interpretation, never trusted from the browser.
"""

from __future__ import annotations

from dataclasses import fields, is_dataclass, replace
from enum import Enum
from typing import Any

from app.domain.relay_import.canonical_distance import (
    CanonicalDistanceProtectionModel,
    CharacteristicSpec,
    CharacteristicType,
    CompensationKind,
    DistanceZone,
    ExtraQuantity,
    GeometryMode,
    ImpedanceValue,
    InstrumentTransformers,
    ProtectedLine,
    RelayMetadata,
    ResidualCompensation,
    ResistiveReach,
    SettingBasis,
    SourceNote,
    SourceNoteKind,
    UnresolvedSetting,
    ZoneDirection,
    ZoneStatus,
)
from app.domain.relay_import.provenance import (
    DocumentReference,
    MappingAuthority,
    MappingStatus,
    Provenance,
    ProvenanceOrigin,
    ReviewRecord,
    ReviewStatus,
    Sourced,
    SourceRef,
    UnresolvedCause,
)
from app.domain.relay_import.raw_document import SourceFormat

_DATACLASSES = {
    cls.__name__: cls
    for cls in (
        CanonicalDistanceProtectionModel, RelayMetadata, InstrumentTransformers, ProtectedLine, DistanceZone,
        CharacteristicSpec, ResistiveReach, ResidualCompensation, ExtraQuantity, UnresolvedSetting,
        ImpedanceValue, Sourced, Provenance, SourceRef, ReviewRecord, SourceNote, DocumentReference,
    )
}
_ENUMS = {
    cls.__name__: cls
    for cls in (
        ZoneStatus, ZoneDirection, CharacteristicType, SettingBasis, CompensationKind, SourceFormat,
        MappingStatus, ProvenanceOrigin, ReviewStatus, UnresolvedCause, GeometryMode, SourceNoteKind, MappingAuthority,
    )
}

#: A real model has a few hundred values; this only stops a pathological payload.
MAX_NODES = 100_000


class SnapshotError(ValueError):
    """The validation context is not a valid canonical-model snapshot."""


def encode_model(model: CanonicalDistanceProtectionModel) -> dict[str, Any]:
    """The model as JSON-safe data (document-level unmapped settings omitted)."""
    return _encode(replace(model, unmapped_settings=()))


def _encode(obj: Any) -> Any:
    if isinstance(obj, Enum):
        return {"_e": type(obj).__name__, "v": obj.value}
    if is_dataclass(obj) and not isinstance(obj, type):
        out: dict[str, Any] = {"_t": type(obj).__name__}
        for f in fields(obj):
            out[f.name] = _encode(getattr(obj, f.name))
        return out
    if isinstance(obj, (tuple, list)):
        return [_encode(item) for item in obj]
    return obj


def decode_model(data: Any) -> CanonicalDistanceProtectionModel:
    """Rebuild a model from `encode_model` output, or raise `SnapshotError`."""
    budget = [MAX_NODES]
    try:
        model = _decode(data, budget)
    except SnapshotError:
        raise
    except (TypeError, ValueError, KeyError, AttributeError) as exc:
        raise SnapshotError("The review context is not valid.") from exc
    if not isinstance(model, CanonicalDistanceProtectionModel):
        raise SnapshotError("The review context is not a canonical model.")
    return model


def _decode(value: Any, budget: list[int]) -> Any:
    budget[0] -= 1
    if budget[0] < 0:
        raise SnapshotError("The review context is too large.")
    if isinstance(value, list):
        return tuple(_decode(item, budget) for item in value)
    if not isinstance(value, dict):
        return value
    if "_e" in value:
        enum_cls = _ENUMS.get(value["_e"])
        if enum_cls is None or set(value) != {"_e", "v"}:
            raise SnapshotError("The review context is not valid.")
        return enum_cls(value["v"])
    cls = _DATACLASSES.get(value.get("_t"))
    if cls is None:
        raise SnapshotError("The review context is not valid.")
    allowed = {f.name for f in fields(cls) if f.init}
    kwargs = {}
    for name, item in value.items():
        if name == "_t":
            continue
        if name not in allowed:
            raise SnapshotError("The review context is not valid.")
        kwargs[name] = _decode(item, budget)
    return cls(**kwargs)
