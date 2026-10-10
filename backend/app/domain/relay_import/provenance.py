"""Interpretation provenance for relay-setting import.

Every engineering value the canonical distance model carries is wrapped in
`Sourced`, so the value is never separated from *how it was obtained*. The
value itself is OEM-neutral and independent of any user-facing wording; the
`Provenance` beside it records where it came from and how far to trust it.

Invariant (enforced): a `Sourced` value is present exactly when its status
is not UNRESOLVED. An unresolved item carries no electrical value -- only
the raw text, if any, in its provenance -- so an extracted-but-unexplained
parameter can never be mistaken for a known engineering quantity.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Generic, TypeVar

T = TypeVar("T")


class ProvenanceOrigin(StrEnum):
    #: Interpreted from an imported relay setting document.
    RELAY_DOCUMENT = "relay_document"
    #: Typed by the user in the manual Distance Protection form. Carries no
    #: document references or relay-profile metadata.
    MANUAL_ENTRY = "manual_entry"


class MappingStatus(StrEnum):
    #: A profile mapped the source deterministically; no confirmation needed.
    MAPPED = "mapped"
    #: Plausible but not proven (e.g. a unit or basis was assumed); the
    #: user should confirm before relying on it.
    INFERRED = "inferred"
    #: Meaning unknown; the value stays out of the model, raw text is kept.
    UNRESOLVED = "unresolved"


@dataclass(frozen=True)
class SourceRef:
    """Pointer back to the raw setting(s) a value was derived from."""

    setting_id: str
    parameter_id: str | None = None
    parameter_name: str | None = None
    page: int | None = None
    location: str | None = None


@dataclass(frozen=True)
class Provenance:
    status: MappingStatus
    sources: tuple[SourceRef, ...] = ()
    #: Profile that produced the interpretation (None for unresolved items
    #: no profile claimed).
    profile_id: str | None = None
    profile_version: str | None = None
    #: The value exactly as extracted, before any interpretation.
    raw_value: str | float | None = None
    notes: tuple[str, ...] = ()
    origin: ProvenanceOrigin = ProvenanceOrigin.RELAY_DOCUMENT

    def __post_init__(self) -> None:
        needs_source = self.origin is ProvenanceOrigin.RELAY_DOCUMENT
        if needs_source and self.status is not MappingStatus.UNRESOLVED and not self.sources:
            raise ValueError(f"a {self.status.value} value must cite at least one source setting")


@dataclass(frozen=True)
class Sourced(Generic[T]):
    value: T | None
    provenance: Provenance = field(default_factory=lambda: Provenance(MappingStatus.UNRESOLVED))

    def __post_init__(self) -> None:
        unresolved = self.provenance.status is MappingStatus.UNRESOLVED
        if unresolved and self.value is not None:
            raise ValueError("an unresolved value must not carry an engineering value")
        if not unresolved and self.value is None:
            raise ValueError(f"a {self.provenance.status.value} value must carry a value")

    @property
    def is_resolved(self) -> bool:
        return self.value is not None

    @property
    def needs_confirmation(self) -> bool:
        return self.provenance.status is MappingStatus.INFERRED


def unresolved(
    raw_value: str | float | None = None,
    *,
    sources: tuple[SourceRef, ...] = (),
    notes: tuple[str, ...] = (),
) -> Sourced:
    """A value the importer saw (or expected) but could not interpret."""
    return Sourced(None, Provenance(MappingStatus.UNRESOLVED, sources=sources, raw_value=raw_value, notes=notes))


def mapped(value: T, *, sources: tuple[SourceRef, ...], profile_id: str, profile_version: str,
           raw_value: str | float | None = None, notes: tuple[str, ...] = ()) -> Sourced[T]:
    return Sourced(value, Provenance(MappingStatus.MAPPED, sources, profile_id, profile_version, raw_value, notes))


def inferred(value: T, *, sources: tuple[SourceRef, ...], profile_id: str, profile_version: str,
             raw_value: str | float | None = None, notes: tuple[str, ...] = ()) -> Sourced[T]:
    return Sourced(value, Provenance(MappingStatus.INFERRED, sources, profile_id, profile_version, raw_value, notes))


def manual(value: T, *, raw_value: str | float | None = None) -> Sourced[T]:
    """A value the user entered by hand: status mapped, origin manual_entry,
    no document references and no profile (none exist for manual input)."""
    return Sourced(value, Provenance(MappingStatus.MAPPED, raw_value=raw_value, origin=ProvenanceOrigin.MANUAL_ENTRY))


def manual_unresolved(raw_value: str | float | None = None, *, notes: tuple[str, ...] = ()) -> Sourced:
    """A manual-form field left blank / not usable: absent, never defaulted."""
    return Sourced(
        None,
        Provenance(MappingStatus.UNRESOLVED, raw_value=raw_value, notes=notes, origin=ProvenanceOrigin.MANUAL_ENTRY),
    )
