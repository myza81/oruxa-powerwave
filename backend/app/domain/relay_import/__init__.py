"""Relay-settings import foundation (Slice 1: contracts only).

    RawRelayDocument -> RelayProfile -> CanonicalDistanceProtectionModel
    RawRelayDocument -> RelayIdentifier -> RelayIdentification   (Slice 5)

No file reading, extraction, relay parsing, persistence or UI lives here.
Raw documents and models are ephemeral in-memory values; nothing in this
package may touch the database or storage layer.
"""

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
from app.domain.relay_import.identification import (
    DEFAULT_RULES,
    EvidenceKind,
    IdentificationCandidate,
    IdentificationConfidence,
    IdentificationEvidence,
    IdentificationStatus,
    ManufacturerAliases,
    ParameterSignature,
    RelayIdentification,
    RelayIdentificationDescriptor,
    RelayIdentifier,
    ScoringRules,
)
from app.domain.relay_import.profile import (
    GenericFallbackProfile,
    MatchLevel,
    ProfileMatch,
    RelayProfile,
    RelayProfileRegistry,
)
from app.domain.relay_import.provenance import (
    MappingStatus,
    Provenance,
    ProvenanceOrigin,
    Sourced,
    SourceRef,
    inferred,
    manual,
    manual_unresolved,
    mapped,
    unresolved,
)
from app.domain.relay_import.raw_document import (
    ExtractionProvenance,
    RawRelayDocument,
    RawSetting,
    SettingRange,
    SourceFormat,
    SourceLocation,
)
