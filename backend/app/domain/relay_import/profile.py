"""Relay-profile abstraction: RawRelayDocument -> CanonicalDistanceProtectionModel.

All relay-family knowledge (parameter codes, vocabularies, unit and basis
conventions, characteristic semantics) lives in profile implementations, not
in the generic domain or the distance characteristic engine. Concrete
profiles are future work (one per family, data-driven where possible).

Fail-safe rule: when no profile confidently claims a document, the generic
fallback is used. It reads nothing electrical -- every raw setting is
retained as unmapped -- so an unknown relay is never given invented meaning.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Protocol, runtime_checkable

from app.domain.relay_import.canonical_distance import (
    CanonicalDistanceProtectionModel,
    RelayMetadata,
    UnresolvedSetting,
)
from app.domain.relay_import.defeated_zone import infer_defeated_zones
from app.domain.relay_import.identification import (
    IdentificationStatus,
    ManufacturerAliases,
    RelayIdentification,
    RelayIdentificationDescriptor,
    RelayIdentifier,
)
from app.domain.relay_import.raw_document import RawRelayDocument


class MatchLevel(IntEnum):
    NONE = 0
    POSSIBLE = 1  # some evidence; not enough to interpret on its own
    CONFIRMED = 2  # the profile positively recognises this relay/format


@dataclass(frozen=True)
class ProfileMatch:
    level: MatchLevel
    notes: tuple[str, ...] = ()


@runtime_checkable
class RelayProfile(Protocol):
    profile_id: str
    version: str

    def match(self, document: RawRelayDocument) -> ProfileMatch: ...

    def interpret(self, document: RawRelayDocument) -> CanonicalDistanceProtectionModel: ...


class GenericFallbackProfile:
    """Retains the raw settings, interprets nothing."""

    profile_id = "generic-fallback"
    version = "1"

    def match(self, document: RawRelayDocument) -> ProfileMatch:
        return ProfileMatch(MatchLevel.POSSIBLE, ("generic fallback accepts any document",))

    def interpret(
        self, document: RawRelayDocument, *, notes: tuple[str, ...] = ()
    ) -> CanonicalDistanceProtectionModel:
        return CanonicalDistanceProtectionModel(
            metadata=RelayMetadata(source_format=document.source_format),
            unmapped_settings=tuple(
                UnresolvedSetting(
                    setting_id=s.setting_id,
                    name=s.name,
                    raw_value=s.raw_value,
                    unit=s.unit,
                    reason="no relay profile recognised this document",
                )
                for s in document.settings
            ),
            interpretation_notes=("relay not recognised; complete the settings manually",) + notes,
        )


class RelayProfileRegistry:
    """Holds interpretation profiles and, separately, identification
    descriptors. Identification (what relay is this?) and interpretation (what
    do its settings mean?) are different steps: a descriptor can be registered
    long before a profile exists, and ``identify()`` never calls a profile."""

    def __init__(
        self,
        profiles: tuple[RelayProfile, ...] = (),
        *,
        identification_descriptors: tuple[RelayIdentificationDescriptor, ...] = (),
        manufacturer_aliases: ManufacturerAliases | None = None,
    ) -> None:
        self._profiles: list[RelayProfile] = []
        self._descriptors: list[RelayIdentificationDescriptor] = []
        self._aliases = manufacturer_aliases or ManufacturerAliases()
        self._identifier: RelayIdentifier | None = None
        self._fallback = GenericFallbackProfile()
        for profile in profiles:
            self.register(profile)
        for descriptor in identification_descriptors:
            self.register_identification_descriptor(descriptor)

    def register(self, profile: RelayProfile) -> None:
        if any(p.profile_id == profile.profile_id for p in self._profiles):
            raise ValueError(f"profile {profile.profile_id!r} already registered")
        self._profiles.append(profile)
        self._identifier = None

    def profile(self, profile_id: str) -> RelayProfile | None:
        """The registered interpretation profile with exactly this id, or None."""
        return next((p for p in self._profiles if p.profile_id == profile_id), None)

    def register_identification_descriptor(self, descriptor: RelayIdentificationDescriptor) -> None:
        if any(d.profile_id == descriptor.profile_id for d in self.identification_descriptors()):
            raise ValueError(f"identification descriptor {descriptor.profile_id!r} already registered")
        self._descriptors.append(descriptor)
        self._identifier = None

    def identification_descriptors(self) -> tuple[RelayIdentificationDescriptor, ...]:
        """Standalone descriptors plus any a registered profile exposes through
        an optional ``identification`` attribute, in registration order."""
        from_profiles = tuple(
            d for p in self._profiles if isinstance(d := getattr(p, "identification", None), RelayIdentificationDescriptor)
        )
        return (*self._descriptors, *from_profiles)

    def identify(self, document: RawRelayDocument) -> RelayIdentification:
        """Which registered relay does the document most likely belong to?
        Pure identification: no profile ``match``/``interpret`` is called and
        nothing is read as an engineering value."""
        if self._identifier is None:
            self._identifier = RelayIdentifier(self.identification_descriptors(), self._aliases)
        return self._identifier.identify(document)

    def profile_for(self, identification: RelayIdentification) -> RelayProfile | None:
        """The registered interpretation profile for an *identified* relay, or
        None. Only an `identified` verdict routes to a profile -- an ambiguous
        or unknown document never does -- and the profile id must match
        exactly, so one relay family can never be read by another's profile."""
        if identification.status is not IdentificationStatus.IDENTIFIED or not identification.profile_id:
            return None
        return next((p for p in self._profiles if p.profile_id == identification.profile_id), None)

    def interpret(self, document: RawRelayDocument) -> CanonicalDistanceProtectionModel:
        """Interpret with the single profile that positively recognises the
        document. Zero or several confirmed matches -> generic fallback
        (several is ambiguity; picking one would be a guess)."""
        confirmed = [p for p in self._profiles if p.match(document).level is MatchLevel.CONFIRMED]
        if len(confirmed) == 1:
            return infer_defeated_zones(confirmed[0].interpret(document))
        if len(confirmed) > 1:
            ids = ", ".join(sorted(p.profile_id for p in confirmed))
            return self._fallback.interpret(document, notes=(f"ambiguous profile match: {ids}",))
        return self._fallback.interpret(document)
