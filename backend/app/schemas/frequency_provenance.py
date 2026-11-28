"""NF-3D (owner decision O-6): the provenance of the nominal frequency an analysis used, as a mixin for the phasor-family and overcurrent results.

`reference_frequency_hz` says WHICH frequency; these say WHERE IT CAME FROM, in the NF-1 vocabulary (`recording_metadata`, `import_supplied`,
`assumed_default`, `manual`, `unusable`; nothing is added). They describe the frequency the calculation actually used, not an imported or cached
value: `nominal_frequency_sources` lists every recording that supplied a channel, each with its own origin and the revision of the engineer's
setting it was resolved with; `nominal_frequency_origin` / `nominal_frequency_revision` summarise that when ONE recording (or several with one
shared origin; then the revision is null because revisions are per recording) supplied it. A result computed with an EXPLICIT
`reference_frequency_hz` supplied by the caller has no provenance (all null / empty): that value is the caller's own. A `manual` origin means an
engineer entered the value in Recording Details; it is never a measured or verified waveform frequency.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.domain.frequency_provenance import FrequencyProvenance


class NominalFrequencySourceOut(BaseModel):
    source_id: str
    origin: str
    revision: int


class NominalFrequencyProvenanceOut(BaseModel):
    nominal_frequency_origin: str | None = None
    nominal_frequency_revision: int | None = None
    nominal_frequency_sources: list[NominalFrequencySourceOut] = Field(default_factory=list)


def provenance_fields(provenance: FrequencyProvenance | None) -> dict:
    """The keyword arguments that fill the mixin from a domain result's `frequency_provenance`."""
    if provenance is None:
        return {"nominal_frequency_origin": None, "nominal_frequency_revision": None, "nominal_frequency_sources": []}
    return {
        "nominal_frequency_origin": provenance.origin, "nominal_frequency_revision": provenance.revision,
        "nominal_frequency_sources": [NominalFrequencySourceOut(source_id=r.source_id, origin=r.origin, revision=r.revision) for r in provenance.recordings],
    }
