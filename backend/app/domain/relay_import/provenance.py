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
    #: Slice 8: set by the user while reviewing an import (a confirmation or a
    #: manual resolution). Session-only; never a statement about the profile.
    SESSION_REVIEW = "session_review"
    #: Oruxa assumed a value because the source states nothing about it (e.g. an optional
    #: zone that is absent from a reliably read document). Not read from the source, so
    #: it cites none; an Assumption that needs no confirmation and never blocks.
    DEFAULT_ASSUMPTION = "default_assumption"


class MappingStatus(StrEnum):
    #: A profile mapped the source deterministically; no confirmation needed.
    MAPPED = "mapped"
    #: Plausible but not proven (e.g. a unit or basis was assumed); the
    #: user should confirm before relying on it.
    INFERRED = "inferred"
    #: Meaning unknown; the value stays out of the model, raw text is kept.
    UNRESOLVED = "unresolved"
    #: Slice 8: the user supplied the value during review for this session. It
    #: is neither a deterministic mapping nor evidence about the profile.
    RESOLVED_MANUALLY = "resolved_manually"


class MappingAuthority(StrEnum):
    """What kind of evidence put a value into the canonical model, strongest first (the
    precedence the parameter catalog applies when more than one source could supply it).
    Separate from `MappingStatus`: it says *why* a value was accepted, not how far to trust it."""

    #: The value is a setting the document states for this very parameter.
    CONFIGURED_SETTING = "configured_setting"
    #: A structured engineering instruction in the document (not a free-text note).
    ENGINEERING_INSTRUCTION = "engineering_instruction"
    #: Derived deterministically from documented relay semantics (a function-block identity,
    #: a documented unit/loop convention) applied to configured settings.
    DOCUMENTED_DERIVATION = "documented_derivation"
    #: An assumption or inference the document does not support on its own.
    ASSUMPTION = "assumption"
    #: Supplied by the user during review.
    MANUAL = "manual"


class UnresolvedCause(StrEnum):
    """Why an unresolved value is unresolved: the *source / extraction* side of the
    uncertainty, kept apart from the interpretation status (`MappingStatus`) and
    from engine capability (decided later by the engine adapter). The review
    presents these as Missing / Conflict / Unreadable / Unsupported."""

    #: The source does not state the value (absent, or not established).
    MISSING = "missing"
    #: Source values or statements disagree, or contradict the printed range/unit.
    CONFLICT = "conflict"
    #: The text was found but could not be read reliably (empty cell, not a number).
    UNREADABLE = "unreadable"
    #: The value was read but the profile has no meaning for it.
    UNSUPPORTED = "unsupported"


class ReviewStatus(StrEnum):
    """What the user did with an item during review (Slice 8). Separate from
    `MappingStatus`: an inferred value that was confirmed is still inferred."""

    CONFIRMED = "confirmed"
    RESOLVED_MANUALLY = "resolved_manually"
    #: The user looked at an unresolved item and chose to leave it unresolved.
    LEFT_UNRESOLVED = "left_unresolved"
    #: The user explicitly accepted an Oruxa suggestion for a missing value. Not a
    #: source value, a profile mapping or the relay's setting: kept apart from
    #: `RESOLVED_MANUALLY` (a value the user typed) so the two stay distinguishable.
    SUGGESTION_ACCEPTED = "suggestion_accepted"


@dataclass(frozen=True)
class ReviewRecord:
    """Session-review annotation on a `Provenance`: what the user decided and
    what the item was before that. The original interpretation is never
    rewritten -- it stays in the provenance fields beside this record."""

    status: ReviewStatus
    #: The `MappingStatus` the profile gave the item before review.
    original_status: MappingStatus
    #: The value as the user typed/chose it with its unit (manual resolution).
    user_value_text: str | None = None
    origin: ProvenanceOrigin = ProvenanceOrigin.SESSION_REVIEW


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
    #: Slice 8 session-review annotation; ``None`` until the user acts.
    review: ReviewRecord | None = None
    #: Why an unresolved value is unresolved; ``None`` for a resolved value and for
    #: an unresolved one nobody classified (presented as missing).
    cause: UnresolvedCause | None = None
    #: The transformation that turned the raw source value into the canonical value, in words
    #: (``None`` when the value is used exactly as printed). The raw value stays in ``raw_value``.
    transformation: str | None = None
    #: What kind of evidence supports the value (see `MappingAuthority`); ``None`` when not stated.
    authority: MappingAuthority | None = None
    #: The parameter catalog that produced the value (``None`` for a hand-written profile).
    catalog_id: str | None = None
    catalog_version: str | None = None
    #: The canonical parameter id the value was written to (``None`` for a hand-written profile).
    canonical_id: str | None = None

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
        """Inferred and not yet confirmed by the user in this session."""
        p = self.provenance
        if p.origin is ProvenanceOrigin.DEFAULT_ASSUMPTION:
            return False
        confirmed = p.review is not None and p.review.status is ReviewStatus.CONFIRMED
        return p.status is MappingStatus.INFERRED and not confirmed


def unresolved(
    raw_value: str | float | None = None,
    *,
    sources: tuple[SourceRef, ...] = (),
    notes: tuple[str, ...] = (),
    cause: UnresolvedCause | None = None,
    catalog_id: str | None = None,
    catalog_version: str | None = None,
    canonical_id: str | None = None,
) -> Sourced:
    """A value the importer saw (or expected) but could not interpret."""
    return Sourced(
        None,
        Provenance(
            MappingStatus.UNRESOLVED, sources=sources, raw_value=raw_value, notes=notes, cause=cause,
            catalog_id=catalog_id, catalog_version=catalog_version, canonical_id=canonical_id,
        ),
    )


def mapped(value: T, *, sources: tuple[SourceRef, ...], profile_id: str, profile_version: str,
           raw_value: str | float | None = None, notes: tuple[str, ...] = (),
           transformation: str | None = None, authority: MappingAuthority | None = None,
           catalog_id: str | None = None, catalog_version: str | None = None,
           canonical_id: str | None = None) -> Sourced[T]:
    return Sourced(value, Provenance(
        MappingStatus.MAPPED, sources, profile_id, profile_version, raw_value, notes, transformation=transformation,
        authority=authority, catalog_id=catalog_id, catalog_version=catalog_version, canonical_id=canonical_id,
    ))


def inferred(value: T, *, sources: tuple[SourceRef, ...], profile_id: str, profile_version: str,
             raw_value: str | float | None = None, notes: tuple[str, ...] = (),
             transformation: str | None = None, authority: MappingAuthority | None = None,
             catalog_id: str | None = None, catalog_version: str | None = None,
             canonical_id: str | None = None) -> Sourced[T]:
    return Sourced(value, Provenance(
        MappingStatus.INFERRED, sources, profile_id, profile_version, raw_value, notes, transformation=transformation,
        authority=authority, catalog_id=catalog_id, catalog_version=catalog_version, canonical_id=canonical_id,
    ))


def assumed_default(value: T, *, profile_id: str, profile_version: str, reason: str) -> Sourced[T]:
    """A value Oruxa assumes because the source is silent about it: status inferred
    (never mapped), origin ``default_assumption``, no source setting cited. It is
    shown as an Assumption but needs no confirmation (see `Sourced.needs_confirmation`)."""
    return Sourced(
        value,
        Provenance(
            MappingStatus.INFERRED,
            profile_id=profile_id,
            profile_version=profile_version,
            notes=(reason,),
            origin=ProvenanceOrigin.DEFAULT_ASSUMPTION,
        ),
    )


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
