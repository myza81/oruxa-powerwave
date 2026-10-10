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
    def __init__(self, profiles: tuple[RelayProfile, ...] = ()) -> None:
        self._profiles: list[RelayProfile] = []
        self._fallback = GenericFallbackProfile()
        for profile in profiles:
            self.register(profile)

    def register(self, profile: RelayProfile) -> None:
        if any(p.profile_id == profile.profile_id for p in self._profiles):
            raise ValueError(f"profile {profile.profile_id!r} already registered")
        self._profiles.append(profile)

    def interpret(self, document: RawRelayDocument) -> CanonicalDistanceProtectionModel:
        """Interpret with the single profile that positively recognises the
        document. Zero or several confirmed matches -> generic fallback
        (several is ambiguity; picking one would be a guess)."""
        confirmed = [p for p in self._profiles if p.match(document).level is MatchLevel.CONFIRMED]
        if len(confirmed) == 1:
            return confirmed[0].interpret(document)
        if len(confirmed) > 1:
            ids = ", ".join(sorted(p.profile_id for p in confirmed))
            return self._fallback.interpret(document, notes=(f"ambiguous profile match: {ids}",))
        return self._fallback.interpret(document)
