"""Review confirmation / resolution (Slice 8): a session review overlay.

    original interpretation (immutable)  +  ReviewDecisions
        -> apply_review() -> effective reviewed model

The user's decisions are an overlay, never an edit of the interpretation. The
original model is not touched; the effective model is a copy in which

* a **confirmed** inferred value keeps its value, its profile provenance and its
  ``inferred`` status, and gains a `ReviewRecord` saying the user confirmed it;
* a **manually resolved** value replaces an unresolved one, keeping the original
  unresolved provenance (sources, raw text, notes) beside a `ReviewRecord` that
  holds what the user entered;
* a **left unresolved** value stays unresolved, annotated as consciously left.

Nothing here is relay-specific, and nothing here persists: decisions are plain
values the caller supplies for one evaluation. Every resolved value comes from a
profile mapping, an explicit confirmation or an explicit manual entry -- never
from a form default, a zone default or an engine default.

Confirmation is session-specific. It does not validate the profile, change a
mapping rule or apply anything to the Distance Protection form.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field, fields, is_dataclass, replace
from enum import StrEnum

from app.domain.relay_import.canonical_distance import (
    CanonicalDistanceProtectionModel,
    ZoneDirection,
    ZoneStatus,
    item_label,
)
from app.domain.relay_import.engine_adapter import EngineAdaptation, UnsupportedCode, zone_active
from app.domain.relay_import.provenance import (
    MappingStatus,
    Provenance,
    ProvenanceOrigin,
    ReviewRecord,
    ReviewStatus,
    Sourced,
    UnresolvedCause,
)


class ReviewDecisionError(ValueError):
    """A review decision that cannot be applied (unknown item, wrong kind of
    item, invalid value, contradictory decisions). The message is safe to show."""


# ---------------------------------------------------------------------------
# What may be resolved by hand
# ---------------------------------------------------------------------------


class ResolutionKind(StrEnum):
    NUMBER = "number"
    CHOICE = "choice"


@dataclass(frozen=True)
class ResolutionSpec:
    """The canonical type of a value the user may supply for an unresolved item.

    Only a field with a known canonical target and a known type/unit has one;
    everything else (a compound reach, a raw OEM setting, a base value) stays
    unresolved."""

    kind: ResolutionKind
    #: ``ohm`` | ``s`` for a number; ``None`` for a choice.
    unit: str | None = None
    minimum: float | None = None
    maximum: float | None = None
    #: (value, label) pairs for a choice.
    options: tuple[tuple[str, str], ...] = ()


_ZONE = r"^zones\[[^\]]+\]\."
_OHM = ResolutionSpec(ResolutionKind.NUMBER, "ohm", 0.0, 1e5)
_SECONDS = ResolutionSpec(ResolutionKind.NUMBER, "s", 0.0, 1e4)
_STATUS = ResolutionSpec(
    ResolutionKind.CHOICE,
    options=((ZoneStatus.ENABLED.value, "Enabled"), (ZoneStatus.DISABLED.value, "Disabled")),
)
_DIRECTION = ResolutionSpec(
    ResolutionKind.CHOICE,
    options=(
        (ZoneDirection.FORWARD.value, "Forward"),
        (ZoneDirection.REVERSE.value, "Reverse"),
        (ZoneDirection.NON_DIRECTIONAL.value, "Non-directional"),
    ),
)
_ENUM_FOR_CHOICE = {_STATUS: ZoneStatus, _DIRECTION: ZoneDirection}

_RESOLUTION_SPECS: tuple[tuple[re.Pattern[str], ResolutionSpec], ...] = (
    (re.compile(_ZONE + r"status$"), _STATUS),
    (re.compile(_ZONE + r"direction$"), _DIRECTION),
    (re.compile(_ZONE + r"resistive_reach\.(common|phase_phase|phase_earth|reverse)$"), _OHM),
    (re.compile(_ZONE + r"x_reach_ohm$"), _OHM),
    (re.compile(_ZONE + r"(common|phase|earth)_timer_s$"), _SECONDS),
)

_UNIT_SYMBOLS = {"ohm": "Ω", "s": "s"}


def resolution_spec(path: str) -> ResolutionSpec | None:
    """How the value at ``path`` could be supplied manually, or ``None`` when its
    canonical type is not clear enough to let a user type it."""
    return next((spec for pattern, spec in _RESOLUTION_SPECS if pattern.match(path)), None)


def _number_text(value: float) -> str:
    return str(int(value)) if value == int(value) and abs(value) < 1e15 else f"{value:.10g}"


@dataclass(frozen=True)
class SuggestionSpec:
    """A neutral, non-authoritative value Oruxa may *offer* for a missing item.

    A suggestion is never applied on its own and is never a source or profile value:
    the user accepts it explicitly and it is recorded as such. Only the items listed
    in `_SUGGESTIONS` have one."""

    value: float
    unit: str
    #: Text shown as the effective value once accepted.
    value_text: str
    #: Why the value is offered (shown beside the offer).
    rationale: str
    #: Wording used instead when the item is *Unsupported* rather than Missing: the source does
    #: state something, but Oruxa cannot represent it, so the value is a visualization
    #: approximation of the relay's real geometry. ``None`` means no offer for an unsupported item.
    unsupported_rationale: str | None = None


#: The only suggestion: a missing quadrilateral left-hand resistive reach (-R) may
#: be placed at R = 0 for plotting/analysis. Not the relay's setting, not a
#: utility standard and not profile-derived.
_SUGGESTIONS: tuple[tuple[re.Pattern[str], SuggestionSpec], ...] = (
    (
        re.compile(_ZONE + r"resistive_reach\.reverse$"),
        SuggestionSpec(
            0.0,
            "ohm",
            "0.00 Ω",
            "Places the left-hand boundary at R = 0. A neutral starting point for plotting "
            "and analysis; it is not the relay's setting.",
            "Relay directional boundary is not yet representable. 0.00 Ω is an optional visualization "
            "approximation only and is not a mapped relay setting.",
        ),
    ),
)


def suggestion_text(spec: SuggestionSpec, cause: UnresolvedCause | None) -> str | None:
    """The rationale to show for ``spec`` when the item's unresolved ``cause`` is as given, or
    ``None`` when the suggestion is not offered for that cause (only a value missing from the
    source, or an unsupported one whose spec words an approximation, may take a suggestion)."""
    if cause in (None, UnresolvedCause.MISSING):
        return spec.rationale
    if cause is UnresolvedCause.UNSUPPORTED:
        return spec.unsupported_rationale
    return None


def suggestion_spec(path: str) -> SuggestionSpec | None:
    """The suggestion Oruxa may offer for the value at ``path`` (if it is missing),
    or ``None`` -- no other item has one."""
    return next((spec for pattern, spec in _SUGGESTIONS if pattern.match(path)), None)


def _manual_value(path: str, spec: ResolutionSpec, raw: object) -> tuple[object, str]:
    """(canonical value, text shown as the user's resolution) for ``raw``, or
    `ReviewDecisionError`. A blank is not a value and zero is."""
    if spec.kind is ResolutionKind.NUMBER:
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise ReviewDecisionError("A number is required.")
        value = float(raw)
        if not math.isfinite(value):
            raise ReviewDecisionError("A finite number is required.")
        if spec.minimum is not None and value < spec.minimum:
            raise ReviewDecisionError(f"The value must be at least {_number_text(spec.minimum)}.")
        if spec.maximum is not None and value > spec.maximum:
            raise ReviewDecisionError(f"The value must be at most {_number_text(spec.maximum)}.")
        symbol = _UNIT_SYMBOLS.get(spec.unit or "", spec.unit or "")
        return value, f"{_number_text(value)} {symbol}".strip()
    labels = dict(spec.options)
    if not isinstance(raw, str) or raw not in labels:
        raise ReviewDecisionError("Choose one of the offered values.")
    return _ENUM_FOR_CHOICE[spec](raw), labels[raw]


# ---------------------------------------------------------------------------
# Decisions and the effective model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReviewDecisions:
    """The user's session decisions, keyed by canonical value path."""

    #: Inferred values the user accepts for this session.
    confirmed: frozenset[str] = frozenset()
    #: path -> the value the user entered (float for a number, str for a choice).
    manual: dict[str, float | str] = field(default_factory=dict)
    #: Unresolved values the user consciously leaves unresolved.
    left_unresolved: frozenset[str] = frozenset()
    #: Missing values for which the user accepted Oruxa's suggestion (see
    #: `suggestion_spec`). Distinct from ``manual``: an explicit entry of the same
    #: number stays a manual resolution.
    suggested: frozenset[str] = frozenset()


_ZONE_STATUS_PATH = re.compile(r"^zones[[](?P<zone>[^]]+)[]]\.status$")


def is_overridable_assumption(path: str, sourced: Sourced) -> bool:
    """A zone status Oruxa merely assumed (absent optional zone, or a defeated delay) may be
    replaced by the user's own choice; a mapped or inferred profile value may not."""
    return (
        sourced.is_resolved
        and sourced.provenance.origin is ProvenanceOrigin.DEFAULT_ASSUMPTION
        and sourced.provenance.review is None
        and _ZONE_STATUS_PATH.match(path) is not None
    )


_ZONE_ID = re.compile(r"^zones[[](?P<zone>[^]]+)[]]")
_TOKEN = re.compile(r"\[[^\]]*\]|[^.\[\]]+")


def _replace_at(obj, tokens: list[str], new: Sourced):
    head, rest = tokens[0], tokens[1:]
    if isinstance(obj, tuple):
        label = head[1:-1]
        index = next((i for i, item in enumerate(obj) if item_label(item, i) == label), None)
        if index is None:
            raise ReviewDecisionError("Unknown review item.")
        child = new if not rest else _replace_at(obj[index], rest, new)
        return (*obj[:index], child, *obj[index + 1:])
    if is_dataclass(obj) and head in {f.name for f in fields(obj)}:
        child = new if not rest else _replace_at(getattr(obj, head), rest, new)
        return replace(obj, **{head: child})
    raise ReviewDecisionError("Unknown review item.")


def _confirmed(sourced: Sourced) -> Sourced:
    record = ReviewRecord(ReviewStatus.CONFIRMED, original_status=sourced.provenance.status)
    return Sourced(sourced.value, replace(sourced.provenance, review=record))


def _left_unresolved(sourced: Sourced) -> Sourced:
    record = ReviewRecord(ReviewStatus.LEFT_UNRESOLVED, original_status=sourced.provenance.status)
    return Sourced(None, replace(sourced.provenance, review=record))


def _resolved_manually(sourced: Sourced, value: object, text: str) -> Sourced:
    p = sourced.provenance
    return Sourced(
        value,
        Provenance(
            MappingStatus.RESOLVED_MANUALLY,
            sources=p.sources,
            profile_id=p.profile_id,
            profile_version=p.profile_version,
            raw_value=p.raw_value,
            notes=p.notes,
            origin=ProvenanceOrigin.SESSION_REVIEW,
            review=ReviewRecord(ReviewStatus.RESOLVED_MANUALLY, p.status, user_value_text=text),
            cause=p.cause,
            catalog_id=p.catalog_id,
            catalog_version=p.catalog_version,
            canonical_id=p.canonical_id,
            references=p.references,
        ),
    )


def _suggestion_accepted(sourced: Sourced, spec: SuggestionSpec) -> Sourced:
    """The suggested value as an effective value. The source interpretation stays
    unresolved (its cause, sources, raw text and notes are kept); the record says the
    value is Oruxa's suggestion accepted by the user."""
    p = sourced.provenance
    return Sourced(
        spec.value,
        Provenance(
            MappingStatus.RESOLVED_MANUALLY,
            sources=p.sources,
            profile_id=p.profile_id,
            profile_version=p.profile_version,
            raw_value=p.raw_value,
            notes=p.notes,
            origin=ProvenanceOrigin.SESSION_REVIEW,
            review=ReviewRecord(ReviewStatus.SUGGESTION_ACCEPTED, p.status, user_value_text=spec.value_text),
            cause=p.cause,
            catalog_id=p.catalog_id,
            catalog_version=p.catalog_version,
            canonical_id=p.canonical_id,
            references=p.references,
        ),
    )


def apply_review(
    model: CanonicalDistanceProtectionModel, decisions: ReviewDecisions
) -> CanonicalDistanceProtectionModel:
    """The effective reviewed model: ``model`` with the decisions overlaid.

    ``model`` is not modified. Raises `ReviewDecisionError` for a decision that
    names an unknown item, the wrong kind of item (only an inferred value can be
    confirmed; only an unresolved one can be resolved or left), an invalid value,
    or two contradictory decisions about one item."""
    index = dict(model.iter_sourced())
    overlay: dict[str, Sourced] = {}
    # A zone that is authoritatively disabled needs none of its own settings, so there is
    # nothing to suggest for it (the decisions are validated against the model as read).
    # A zone whose assumed status the user overrides is judged by the override instead.
    overridden = {m.group("zone") for p in decisions.manual if (m := _ZONE_STATUS_PATH.match(p))}
    inactive = {z.zone_id for z in model.zones if zone_active(z) is False and z.zone_id not in overridden}

    def claim(path: str) -> Sourced:
        if path not in index:
            raise ReviewDecisionError("Unknown review item.")
        if path in overlay:
            raise ReviewDecisionError("An item cannot have more than one review decision.")
        return index[path]

    for path in sorted(decisions.confirmed):
        sourced = claim(path)
        if sourced.provenance.status is not MappingStatus.INFERRED:
            raise ReviewDecisionError("Only an inferred value can be confirmed.")
        overlay[path] = _confirmed(sourced)
    for path in sorted(decisions.left_unresolved):
        sourced = claim(path)
        if sourced.is_resolved:
            raise ReviewDecisionError("Only an unresolved value can be left unresolved.")
        overlay[path] = _left_unresolved(sourced)
    for path in sorted(decisions.manual):
        sourced = claim(path)
        if sourced.is_resolved and not is_overridable_assumption(path, sourced):
            raise ReviewDecisionError("Only an unresolved value can be resolved manually.")
        spec = resolution_spec(path)
        if spec is None:
            raise ReviewDecisionError("This value cannot be entered manually.")
        value, text = _manual_value(path, spec, decisions.manual[path])
        overlay[path] = _resolved_manually(sourced, value, text)

    for path in sorted(decisions.suggested):
        sourced = claim(path)
        spec = suggestion_spec(path)
        if spec is None:
            raise ReviewDecisionError("No suggestion is available for this value.")
        if sourced.is_resolved:
            raise ReviewDecisionError("Only a missing value can take a suggestion.")
        zone = _ZONE_ID.match(path)
        if zone and zone["zone"] in inactive:
            raise ReviewDecisionError("This value is not required while its zone is disabled.")
        if suggestion_text(spec, sourced.provenance.cause) is None:
            raise ReviewDecisionError(
                "A suggestion is offered only for a value missing from the source, or one that is not representable."
            )
        overlay[path] = _suggestion_accepted(sourced, spec)

    effective = model
    for path, sourced in overlay.items():
        effective = _replace_at(effective, _TOKEN.findall(path), sourced)
    return effective


# ---------------------------------------------------------------------------
# Blocking issues and readiness
# ---------------------------------------------------------------------------


class Readiness(StrEnum):
    #: The current engine cannot take the model, or a blocking item is open.
    NOT_READY = "not_ready"
    #: Nothing blocks the engine, but inferred values are still unconfirmed.
    READY_AFTER_CONFIRMATION = "ready_after_confirmation"
    #: The engine accepts the model and every inferred value is confirmed.
    READY = "ready"
    #: DEC-198: as ``ready``, but the accepted model contains at least one automatic engine
    #: approximation of an approved rule (conservative or bounded). No import reaches it until
    #: such a rule is approved.
    READY_APPROXIMATE = "ready_approximate"


@dataclass(frozen=True)
class BlockingIssue:
    """Why the current engine cannot take the model, from the adapter's reasons
    (identical messages across zones merged). ``paths`` are the canonical values
    that would address it; an issue can persist after they are all resolved
    (e.g. a zone the engine cannot represent)."""

    message: str
    zone_ids: tuple[str, ...] = ()
    paths: tuple[str, ...] = ()


def blocking_issues(adaptation: EngineAdaptation) -> tuple[BlockingIssue, ...]:
    merged: dict[str, tuple[list[str], list[str]]] = {}
    for reason in adaptation.reasons:
        zones, paths = merged.setdefault(reason.message, ([], []))
        if reason.zone_id and reason.zone_id not in zones:
            zones.append(reason.zone_id)
        paths.extend(p for p in reason.paths if p not in paths)
    return tuple(BlockingIssue(message, tuple(zones), tuple(paths)) for message, (zones, paths) in merged.items())


def blocking_paths(adaptation: EngineAdaptation) -> frozenset[str]:
    return frozenset(path for reason in adaptation.reasons for path in reason.paths)


#: Adapter reasons that say the engine cannot represent / use a value it understands.
_CAPABILITY_CODES = frozenset({
    UnsupportedCode.BASIS_MISMATCH,
    UnsupportedCode.CHARACTERISTIC_UNSUPPORTED,
    UnsupportedCode.CHARACTERISTIC_MIXED,
    UnsupportedCode.DIRECTION_UNSUPPORTED,
    UnsupportedCode.GEOMETRY_UNSUPPORTED,
    UnsupportedCode.LOOP_TYPE_UNSUPPORTED,
    UnsupportedCode.REACH_REPRESENTATION,
    UnsupportedCode.TILT_UNSUPPORTED,
})
#: Adapter reasons that say two resolved values disagree.
_CONFLICT_CODES = frozenset({UnsupportedCode.RESISTIVE_REACH_CONFLICT, UnsupportedCode.TIMER_CONFLICT})


def engine_limits(adaptation: EngineAdaptation) -> dict[str, tuple[str, str]]:
    """``path -> (kind, message)`` for every canonical value the adapter refuses
    for a reason other than "it is not known yet": ``unsupported`` (the engine
    cannot represent or use it) or ``conflict`` (resolved values disagree). An
    engine limit is kept apart from source and interpretation certainty: it
    describes the engine, not the document. ``unsupported`` wins over ``conflict``
    when a value is named by both."""
    out: dict[str, tuple[str, str]] = {}
    for reason in adaptation.reasons:
        kind = "unsupported" if reason.code in _CAPABILITY_CODES else "conflict" if reason.code in _CONFLICT_CODES else None
        if kind is None:
            continue
        for path in reason.paths:
            if path not in out or (kind == "unsupported" and out[path][0] == "conflict"):
                out[path] = (kind, reason.message)
    return out


def compute_readiness(
    *, engine_supported: bool, pending_confirmations: int, blocking_unresolved: int, approximations: int = 0
) -> Readiness:
    """``Ready`` only when the engine adapter accepts the effective model, no
    blocking item is open and no inferred value awaits confirmation. A "required
    canonical field" is one the adapter needs, so an unresolved one always makes
    the adapter refuse the model. DEC-198: an accepted model that contains an
    automatic engine approximation is ``ready_approximate`` instead of ``ready``."""
    if not engine_supported or blocking_unresolved > 0:
        return Readiness.NOT_READY
    if pending_confirmations > 0:
        return Readiness.READY_AFTER_CONFIRMATION
    return Readiness.READY_APPROXIMATE if approximations > 0 else Readiness.READY


#: Readiness states that allow Apply (the model is accepted, nothing awaits the user).
APPLICABLE_READINESS = frozenset({Readiness.READY, Readiness.READY_APPROXIMATE})
