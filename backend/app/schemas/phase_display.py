"""Wire shape for a DEC-118 phase display convention -- shared by the
Engineering Context, Line-to-Line readiness and Compliance responses, so
every consumer reads the same shape. See
`app.domain.phase_identity.PhaseDisplayConvention`."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from app.domain.phase_identity import PhaseDisplayConvention


class PhaseDisplayOut(BaseModel):
    """DEC-118 phase display convention of one Measurement Group /
    Engineering Context: how its canonical members (A/B/C/AB/BC/CA) are
    spelled in user-facing notation. `symbols` is always complete;
    `convention` is `None` whenever `status` is `canonical_fallback`.
    Display metadata only -- canonical values are never replaced by it."""

    convention: str | None
    status: Literal["established", "canonical_fallback"]
    symbols: dict[str, str]
    reason: str | None = None

    @classmethod
    def from_domain(cls, display: PhaseDisplayConvention) -> "PhaseDisplayOut":
        return cls(**display.to_dict())
