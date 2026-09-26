"""Canonical phase identity + provenance (Analysis Guardrail Slice 1; see
docs/project-memory/ANALYSIS_INPUT_GUARDRAILS.md, "Phase identity
representation" / "Canonical phase normalization" / "Phase provenance").

This module owns exactly two small, closed vocabularies:

1. **Canonical phase** -- one internal representation (`PHASE_A`/`PHASE_B`/
   `PHASE_C`/`PHASE_N`/`PHASE_AB`/`PHASE_BC`/`PHASE_CA`/`PHASE_UNKNOWN`/
   `PHASE_NOT_APPLICABLE`) that every raw source convention (A/B/C,
   R/Y/B, L1/L2/L3) normalizes into, so resolver logic (a later slice)
   only ever compares canonical values, never raw source-specific
   tokens.
2. **Phase provenance** -- where a phase assignment came from
   (`engineer_confirmed`/`manual`/`structured_metadata`/
   `detected_from_name`/`unknown`), used to decide whether a NEW
   candidate assignment is allowed to overwrite an EXISTING one. This is
   deliberately NOT a numerical confidence score -- the owner's own
   instruction: "Do NOT model phase confidence as a fake numerical
   percentage." Only a strict authority ordering is needed:
   engineer-confirmed/manual assignment > structured normalized source
   metadata > high-confidence name-suffix detection > unknown.

**The convention ambiguity guardrail**: the raw single-letter token "B"
is genuinely ambiguous on its own -- it means canonical B under the A/B/C
convention, but canonical C under the R/Y/B convention (R->A, Y->B,
B->C). `infer_phase_convention()` below resolves this the same way an
engineer would: by looking at the OTHER phase tokens present in the same
context. "R" or "Y" anywhere is exclusive R/Y/B evidence; "A" or "C"
anywhere is exclusive A/B/C evidence (R/Y/B never uses raw "A" or "C").
A context containing ONLY "B" (no other phase letters) has no
distinguishing evidence at all and must not guess -- convention stays
`None`, every such token normalizes to `PHASE_UNKNOWN`.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

PHASE_A = "A"
PHASE_B = "B"
PHASE_C = "C"
PHASE_N = "N"
PHASE_AB = "AB"
PHASE_BC = "BC"
PHASE_CA = "CA"
PHASE_UNKNOWN = "unknown"
#: Reserved for a future non-phase-bearing member (e.g. a Frequency or
#: Power channel admitted to a context) -- not produced by any detection
#: or normalization logic in this slice; a member's own default phase is
#: `PHASE_UNKNOWN`, never this. Exists now purely so the closed set is
#: complete and does not need a breaking addition later (canonical
#: document section 6).
PHASE_NOT_APPLICABLE = "not_applicable"

KNOWN_PHASES = (
    PHASE_A, PHASE_B, PHASE_C, PHASE_N, PHASE_AB, PHASE_BC, PHASE_CA,
    PHASE_UNKNOWN, PHASE_NOT_APPLICABLE,
)


def phase_valid(phase: str) -> bool:
    return phase in KNOWN_PHASES


#: Provenance vocabulary -- see module docstring. `engineer_confirmed` is
#: written when an engineer explicitly reviews/accepts a phase that
#: detection already suggested; `manual` is written when an engineer sets
#: a phase directly with no detection involved at all (mirrors
#: `app.domain.measurement_group`'s own `STATUS_CONFIRMED`/`STATUS_MANUAL`
#: distinction, applied one level down at the per-member phase field
#: rather than the whole context's status).
PHASE_SOURCE_ENGINEER_CONFIRMED = "engineer_confirmed"
PHASE_SOURCE_MANUAL = "manual"
PHASE_SOURCE_STRUCTURED_METADATA = "structured_metadata"
PHASE_SOURCE_DETECTED_FROM_NAME = "detected_from_name"
PHASE_SOURCE_UNKNOWN = "unknown"

KNOWN_PHASE_SOURCES = (
    PHASE_SOURCE_ENGINEER_CONFIRMED,
    PHASE_SOURCE_MANUAL,
    PHASE_SOURCE_STRUCTURED_METADATA,
    PHASE_SOURCE_DETECTED_FROM_NAME,
    PHASE_SOURCE_UNKNOWN,
)

#: Strict authority ranking -- higher wins. `engineer_confirmed` and
#: `manual` are equal, top authority (both mean "an engineer decided
#: this, not a detector"). This is an ORDERING, never a probability --
#: see module docstring's "not a fake numerical percentage" instruction;
#: the integer values themselves carry no meaning beyond relative order.
_PHASE_SOURCE_AUTHORITY: dict[str, int] = {
    PHASE_SOURCE_ENGINEER_CONFIRMED: 3,
    PHASE_SOURCE_MANUAL: 3,
    PHASE_SOURCE_STRUCTURED_METADATA: 2,
    PHASE_SOURCE_DETECTED_FROM_NAME: 1,
    PHASE_SOURCE_UNKNOWN: 0,
}

#: Provenance tiers an automatic process (detection, or any future
#: re-detection re-run) must never overwrite -- "Re-running detection
#: must never silently overwrite confirmed/manual context membership or
#: phase assignments" (owner instruction). An automatic candidate may
#: only ever replace a `structured_metadata`/`detected_from_name`/
#: `unknown` existing assignment.
LOCKED_PHASE_SOURCES = frozenset({PHASE_SOURCE_ENGINEER_CONFIRMED, PHASE_SOURCE_MANUAL})


def phase_source_valid(phase_source: str) -> bool:
    return phase_source in KNOWN_PHASE_SOURCES


def phase_source_authority(phase_source: str) -> int:
    return _PHASE_SOURCE_AUTHORITY.get(phase_source, 0)


def may_overwrite_phase_assignment(*, existing_source: str, candidate_source: str) -> bool:
    """True iff an automatic (non-engineer) candidate assignment is
    allowed to replace the existing one. A locked existing assignment
    (`engineer_confirmed`/`manual`) is NEVER replaced by this function,
    regardless of the candidate's own authority -- only an engineer's own
    explicit follow-up action may change a locked assignment (the service
    layer's `update_member_phase()`, not automatic re-detection). Among
    unlocked tiers, only a STRICTLY higher-authority candidate replaces
    the existing one; an equal-authority re-detection result (e.g. two
    consecutive `detected_from_name` runs) is allowed to refresh the
    stored token/label, since it carries no risk of downgrading trust."""
    if existing_source in LOCKED_PHASE_SOURCES:
        return False
    return phase_source_authority(candidate_source) >= phase_source_authority(existing_source)


# ---------------------------------------------------------------------------
# Convention-aware normalization
# ---------------------------------------------------------------------------

CONVENTION_ABC = "ABC"
CONVENTION_RYB = "RYB"
CONVENTION_L123 = "L123"
KNOWN_CONVENTIONS = (CONVENTION_ABC, CONVENTION_RYB, CONVENTION_L123)

#: Raw single-phase-letter tokens exclusive to one convention -- the
#: evidence `infer_phase_convention()` looks for. "B" is deliberately
#: absent from both: it is the one letter shared by A/B/C and R/Y/B, so
#: it can never, by itself, prove which convention is in use (module
#: docstring).
_ABC_EXCLUSIVE_LETTERS = frozenset({"A", "C"})
_RYB_EXCLUSIVE_LETTERS = frozenset({"R", "Y"})
_L123_TOKENS = frozenset({"L1", "L2", "L3"})

_SINGLE_MAP_BY_CONVENTION: dict[str, dict[str, str]] = {
    CONVENTION_ABC: {"A": PHASE_A, "B": PHASE_B, "C": PHASE_C},
    CONVENTION_RYB: {"R": PHASE_A, "Y": PHASE_B, "B": PHASE_C},
    CONVENTION_L123: {"L1": PHASE_A, "L2": PHASE_B, "L3": PHASE_C},
}

#: Phase-to-phase (pair) tokens per convention, both orderings mapping to
#: the same canonical pair (an "AB" and "BA" suffix mean the same pair
#: relationship for clustering purposes -- ordering is display-only, not
#: modeled here in Slice 1).
_PAIR_MAP_BY_CONVENTION: dict[str, dict[str, str]] = {
    CONVENTION_ABC: {
        "AB": PHASE_AB, "BA": PHASE_AB,
        "BC": PHASE_BC, "CB": PHASE_BC,
        "CA": PHASE_CA, "AC": PHASE_CA,
    },
    CONVENTION_RYB: {
        "RY": PHASE_AB, "YR": PHASE_AB,
        "YB": PHASE_BC, "BY": PHASE_BC,
        "BR": PHASE_CA, "RB": PHASE_CA,
    },
}


def infer_phase_convention(raw_tokens: list[str]) -> str | None:
    """Infers ONE shared naming convention from a batch of raw phase
    tokens (e.g. every member of one candidate Engineering Context),
    never per-token in isolation. Returns `None` -- convention unknown --
    when there is no exclusive evidence at all, or when evidence for more
    than one convention is present at once (a genuine conflict, e.g. both
    "R" and "A" appear); `None` must never be guessed away by a caller,
    per the "do not silently guess among ambiguous candidates" principle.
    A bare neutral suffix's own letter (the "N" in "AN"/"RN") is passed
    in as its underlying phase letter by the caller, exactly like a
    single-phase token would be -- this function only ever looks at
    A/B/C/R/Y/L1/L2/L3 evidence.
    """
    letters: set[str] = set()
    has_l123 = False
    for token in raw_tokens:
        if not token:
            continue
        upper = token.strip().upper()
        if upper in _L123_TOKENS:
            has_l123 = True
        elif len(upper) == 1:
            letters.add(upper)
    has_abc = bool(letters & _ABC_EXCLUSIVE_LETTERS)
    has_ryb = bool(letters & _RYB_EXCLUSIVE_LETTERS)
    evidence = [c for c, present in ((CONVENTION_ABC, has_abc), (CONVENTION_RYB, has_ryb), (CONVENTION_L123, has_l123)) if present]
    if len(evidence) == 1:
        return evidence[0]
    return None


def raw_token_matches_phase(raw_token: str | None, canonical_phase: str, convention: str) -> bool:
    """True iff `raw_token` is a valid spelling of `canonical_phase` under
    `convention`, in either pair order ("RY"/"YR" both mean AB under R/Y/B).
    Used to check that a convention explains every member's own label."""
    if not raw_token:
        return False
    return normalize_phase_token(raw_token, convention) == canonical_phase


def normalize_phase_token(raw_token: str, convention: str | None) -> str:
    """Normalizes one raw phase-suffix token (e.g. "A", "R", "L2", "AB",
    "N") to its canonical value under `convention`. Returns
    `PHASE_UNKNOWN` whenever the token cannot be confidently resolved:
    `convention` is `None`, the token is not recognized under that
    convention, or (for a bare neutral-conductor token) -- "N" is
    convention-independent and always normalizes to `PHASE_N` regardless
    of `convention` (every convention uses a bare "N" for the neutral
    conductor identically), including when `convention` itself is
    unknown. Never raises."""
    if not raw_token:
        return PHASE_UNKNOWN
    upper = raw_token.strip().upper()
    if upper == "N":
        return PHASE_N
    if convention is None:
        return PHASE_UNKNOWN
    single_map = _SINGLE_MAP_BY_CONVENTION.get(convention, {})
    if upper in single_map:
        return single_map[upper]
    pair_map = _PAIR_MAP_BY_CONVENTION.get(convention, {})
    if upper in pair_map:
        return pair_map[upper]
    return PHASE_UNKNOWN


# ---------------------------------------------------------------------------
# Phase DISPLAY convention (DEC-118; see docs/project-memory/
# ANALYSIS_INPUT_GUARDRAILS.md, "Phase display convention")
# ---------------------------------------------------------------------------
#
# Canonical A/B/C (and AB/BC/CA) stay the ONLY identities calculation,
# resolution and API values use. A context's display convention only says
# how Powerwave-generated engineering notation for that context should
# SPELL those canonical members: canonical A of an R/Y/B bay is shown as
# "R", so its phase voltage reads VR and its A-B line-to-line voltage VRY.
#
# The convention is never re-detected from a channel name. It is derived
# from what detection (or an engineer) already resolved: each member's
# canonical `phase` together with the `original_phase_label` it was
# normalized from.

PHASE_DISPLAY_ESTABLISHED = "established"
PHASE_DISPLAY_CANONICAL_FALLBACK = "canonical_fallback"

#: The canonical members a display map covers, in display order.
DISPLAY_MEMBERS = (PHASE_A, PHASE_B, PHASE_C, PHASE_AB, PHASE_BC, PHASE_CA)
_DISPLAY_PHASE_MEMBERS = frozenset(DISPLAY_MEMBERS)

#: canonical member -> display token, per convention whose display notation
#: is owner-approved. Pairs keep the cyclic canonical order (AB, BC, CA ->
#: RY, YB, BR). L1/L2/L3 is recognized for phase NORMALIZATION but has no
#: approved display notation yet (its line-to-line form is an open owner
#: question), so an L1/L2/L3 context falls back to canonical display.
#: Adding a convention here (and to the frontend's
#: WW_PHASE_DISPLAY_TOKENS) is all a new display convention needs.
PHASE_DISPLAY_SYMBOLS_BY_CONVENTION: dict[str, dict[str, str]] = {
    CONVENTION_ABC: {
        PHASE_A: "A", PHASE_B: "B", PHASE_C: "C",
        PHASE_AB: "AB", PHASE_BC: "BC", PHASE_CA: "CA",
    },
    CONVENTION_RYB: {
        PHASE_A: "R", PHASE_B: "Y", PHASE_C: "B",
        PHASE_AB: "RY", PHASE_BC: "YB", PHASE_CA: "BR",
    },
}
CANONICAL_DISPLAY_SYMBOLS = PHASE_DISPLAY_SYMBOLS_BY_CONVENTION[CONVENTION_ABC]


@dataclass(frozen=True, slots=True)
class PhaseDisplayConvention:
    """How one Measurement Group / Engineering Context spells its canonical
    members in user-facing notation.

    `symbols` is always complete (every member in `DISPLAY_MEMBERS`), so a
    caller never has to handle a gap. `convention` is the established
    convention, or `None` when `status` is `canonical_fallback`, in which
    case `symbols` is the canonical A/B/C spelling and `reason` says why.
    """

    convention: str | None
    status: str
    symbols: dict[str, str]
    reason: str | None = None

    def symbol(self, member: str) -> str:
        """Display token for a canonical member; anything outside the map
        (N, unknown) is returned unchanged."""
        return self.symbols.get(member, member)

    def to_dict(self) -> dict:
        return {
            "convention": self.convention,
            "status": self.status,
            "symbols": dict(self.symbols),
            "reason": self.reason,
        }


CANONICAL_PHASE_DISPLAY = PhaseDisplayConvention(
    convention=None,
    status=PHASE_DISPLAY_CANONICAL_FALLBACK,
    symbols=dict(CANONICAL_DISPLAY_SYMBOLS),
    reason="No phase convention could be established.",
)


def _fallback(reason: str) -> PhaseDisplayConvention:
    return PhaseDisplayConvention(
        convention=None,
        status=PHASE_DISPLAY_CANONICAL_FALLBACK,
        symbols=dict(CANONICAL_DISPLAY_SYMBOLS),
        reason=reason,
    )


def resolve_phase_display_convention(
    members: Iterable[tuple[str, str | None]],
) -> PhaseDisplayConvention:
    """Derives ONE display convention from a grouped measurement's own
    resolved members, each given as `(canonical phase, original phase
    label)`. Never guesses. A convention is established only when all of
    these hold:

    1. At least one member resolved to a canonical phase or pair
       (A/B/C/AB/BC/CA). Neutral/unknown members carry no evidence and are
       ignored.
    2. Every such member still has the source label it was resolved from.
       A member without one (e.g. a manually assigned phase with no label)
       cannot be checked, so the whole context falls back.
    3. The labels contain convention-exclusive evidence, judged by the same
       `infer_phase_convention()` detection uses. A lone "B" (A/B/C phase B,
       or R/Y/B phase C?) is not evidence, so it never decides.
    4. That convention explains EVERY member's (canonical phase, label)
       pair. One inconsistent member (a conflict, or a mixed-convention
       context spanning two sources) means no convention.

    The convention names a closed system, so once it is established the
    full A/B/C map follows from it, including a phase this context does not
    happen to record (a bay with only VR and VY still spells phase C "B").

    Anything else returns the canonical A/B/C spelling with
    `status = canonical_fallback`, which is exactly what the UI showed
    before this convention existed.
    """
    resolved = [
        (phase, (label or "").strip().upper())
        for phase, label in members
        if phase in _DISPLAY_PHASE_MEMBERS
    ]
    if not resolved:
        return _fallback("No member has a resolved phase.")
    if any(not label for _, label in resolved):
        return _fallback("A resolved phase has no source phase label to check its convention against.")

    evidence: list[str] = []
    for _, label in resolved:
        if label in _L123_TOKENS or len(label) == 1:
            evidence.append(label)
        elif len(label) == 2:
            evidence.extend(label)
    convention = infer_phase_convention(evidence)
    if convention is None:
        return _fallback("The phase labels do not identify exactly one convention.")
    if not all(raw_token_matches_phase(label, phase, convention) for phase, label in resolved):
        return _fallback(f"Not every phase label is consistent with the {convention} convention.")
    symbols = PHASE_DISPLAY_SYMBOLS_BY_CONVENTION.get(convention)
    if symbols is None:
        return _fallback(f"No display notation is defined for the {convention} convention yet.")
    return PhaseDisplayConvention(
        convention=convention, status=PHASE_DISPLAY_ESTABLISHED, symbols=dict(symbols), reason=None,
    )


def phase_symbol_text(quantity: str, member: str, display: PhaseDisplayConvention | None = None) -> str:
    """Plain-text engineering symbol for backend-supplied messages, following
    the DEC-117 plain fallback (concatenated, never underscore-joined):
    ("V", "A") -> "VA"; with an R/Y/B display -> "VR"; ("V", "AB") -> "VRY"."""
    return quantity + (display or CANONICAL_PHASE_DISPLAY).symbol(member)
