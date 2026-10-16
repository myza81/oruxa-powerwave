"""Relay Import response schema: safe metadata, extraction counts, the relay
identification verdict (Slice 5) and an interpretation summary (Slice 6).

No document content, no evidence text and no engineering values: the
interpretation summary is counts and fixed phrases only.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictInt, StrictStr

#: Mapped / To confirm / Confirmed / Unresolved / Resolved manually. Separate from
#: the interpretation ``status``, which a confirmation never rewrites.
#: ``assumed`` is an Assumption made because the source is silent (e.g. an absent
#: optional zone); it is shown as an Assumption but never awaits confirmation.
ReviewStatusName = Literal["mapped", "to_confirm", "assumed", "confirmed", "unresolved", "resolved_manually"]


#: Slice 8A presentation category: how an item's uncertainty is explained, kept apart
#: from the interpretation ``status`` (a profile's mapped / inferred / unresolved).
#: Assumption = the source was read but an engineering assumption was needed.
#: DEC-198: documented = documented relay behaviour (a documented derivation, not a stated setting);
#: approximate = an engine approximation of an approved rule; unverified = the meaning / conversion of
#: a stated value is not established; not_exposed = the relay has no such setting (never "missing").
CategoryName = Literal[
    "mapped", "documented", "approximate", "assumption", "missing", "conflict", "unsupported", "unverified",
    "not_exposed", "unreadable",
]
ApproximationClassName = Literal["conservative", "bounded"]
ReadinessName = Literal["not_ready", "ready_after_confirmation", "ready", "ready_approximate"]


class ReviewReferenceOut(BaseModel):
    """DEC-198: an authoritative reference behind a value (identification only)."""

    reference_id: str
    title: str
    verification: Literal["verified", "unverified"]
    document: str | None = None
    section: str | None = None
    page: str | None = None
    scope: str | None = None


class ApproximationOut(BaseModel):
    """DEC-198: an engine approximation of an approved, relay-neutral rule. ``unbounded`` never occurs:
    an unbounded approximation is never applied automatically."""

    rule_id: str
    rule_version: str
    #: The canonical path of the approximated value.
    field: str
    classification: ApproximationClassName
    description: str
    #: The verified error envelope, in words (always present for a bounded rule).
    envelope: str | None = None
    zone_id: str | None = None


class ReviewSourceOut(BaseModel):
    """Where one interpreted value came from (never a file path)."""

    code: str | None = None
    name: str | None = None
    raw_value: str | None = None
    page: int | None = None
    line: int | None = None
    source_text: str | None = None


class ReviewSuggestionOut(BaseModel):
    """A neutral value that is offered for a missing item. Never applied automatically."""

    value_text: str
    rationale: str


class ReviewResolutionOut(BaseModel):
    """How the user may supply a value for an unresolved item."""

    kind: Literal["number", "choice"]
    unit_symbol: str | None = None
    minimum: float | None = None
    maximum: float | None = None
    #: (value, label) pairs for a choice.
    options: list[tuple[str, str]] = []


class ReviewItemOut(BaseModel):
    key: str
    label: str
    full_label: str
    #: Formatted engineering value with unit; ``None`` when unresolved.
    value_text: str | None = None
    status: Literal["mapped", "inferred", "unresolved"]
    notes: list[str] = []
    raw_value: str | None = None
    profile_id: str | None = None
    profile_version: str | None = None
    sources: list[ReviewSourceOut] = []
    #: Slice 8. Canonical path the user's decisions refer to; ``None`` for a
    #: declined zone setting (never resolvable).
    item_id: str | None = None
    #: False on the second row of a value shown as two rows (reach + angle).
    primary: bool = True
    review_status: ReviewStatusName = "mapped"
    #: Unresolved and needed by the current engine adapter.
    blocking: bool = False
    left_unresolved: bool = False
    user_value_text: str | None = None
    resolution: ReviewResolutionOut | None = None
    suggestion: ReviewSuggestionOut | None = None
    #: manual | suggestion: who supplied the effective value of a user-resolved item.
    resolution_origin: Literal["manual", "suggestion"] | None = None
    category: CategoryName = "mapped"
    #: The engine adapter's message when it refuses or cannot use this value.
    engine_reason: str | None = None
    #: Unresolved, zone-local and in a disabled zone no enabled function needs: visible, not a blocker.
    not_required: bool = False
    not_required_reason: str | None = None
    #: How the raw source value became the shown canonical value (``None`` = used as printed).
    transformation: str | None = None
    authority: str | None = None
    #: Parameter catalog (id, version) and canonical parameter behind the value, if any.
    catalog_id: str | None = None
    catalog_version: str | None = None
    canonical_id: str | None = None
    #: DEC-198: the authoritative references the catalog cites for this value.
    references: list[ReviewReferenceOut] = []
    #: DEC-198: present when the value is an engine approximation.
    approximation: ApproximationOut | None = None


class ReviewSourceNoteOut(BaseModel):
    """A document statement about a zone that is not one of its settings (a requirement or
    design note). Shown beside the zone; never a value and never applied."""

    kind_label: str
    title: str
    text: str
    sources: list[ReviewSourceOut] = []


class ReviewGroupOut(BaseModel):
    id: str
    kind: Literal["relay", "transformers", "line", "zone", "compensation"]
    title: str
    state_label: str | None = None
    state_status: Literal["mapped", "inferred", "unresolved"] | None = None
    state_review_status: ReviewStatusName | None = None
    #: Helper text for a zone whose state was assumed.
    state_note: str | None = None
    items: list[ReviewItemOut] = []
    source_notes: list[ReviewSourceNoteOut] = []


class ReviewRawSettingOut(BaseModel):
    code: str | None = None
    name: str | None = None
    raw_value: str | None = None
    page: int | None = None
    line: int | None = None
    reason: str = ""


class ReviewEngineReasonOut(BaseModel):
    zone_ids: list[str] = []
    message: str


class ReviewEngineOut(BaseModel):
    status: Literal["ready", "not_ready"]
    reasons: list[ReviewEngineReasonOut] = []
    warnings: list[str] = []


class ReviewBlockingIssueOut(BaseModel):
    message: str
    zone_ids: list[str] = []
    #: Canonical values that would address the issue (it can outlive them all).
    item_ids: list[str] = []
    #: DEC-198: ``unverified`` -- a meaning that is not yet verified (not an engine limit); ``""`` otherwise.
    kind: Literal["", "unverified"] = ""


class ReviewReadinessOut(BaseModel):
    status: ReadinessName
    pending_confirmations: int
    blocking_unresolved: int


class ReviewStateFieldsOut(BaseModel):
    """The part of a review that changes with the user's decisions."""

    #: Counts are per canonical value (a reach and its angle are one).
    mapped_count: int
    #: Inferred values still awaiting confirmation.
    to_confirm_count: int
    confirmed_count: int
    resolved_manually_count: int
    #: Resolved by accepting a suggested value (not included in `resolved_manually_count`).
    suggested_count: int
    #: Unresolved values, blocking or not, including those left unresolved.
    unresolved_count: int
    #: Unresolved values the current engine adapter needs (a subset of the above).
    #: Blocking *settings*; `blocking_issues` are the adapter's *reasons*.
    blocking_count: int
    #: Unresolved values of a disabled zone that no enabled function needs; not in the
    #: Missing / Unreadable counts and never blocking.
    not_required_count: int
    #: Slice 8A presentation counts (see `CategoryName`).
    assumption_count: int
    missing_count: int
    conflict_count: int
    unsupported_count: int
    unreadable_count: int
    #: DEC-198 presentation counts: documented relay behaviour (not in `mapped_count`), engine
    #: approximations, values whose meaning is not verified, settings the relay does not expose.
    documented_count: int = 0
    approximate_count: int = 0
    unverified_count: int = 0
    not_exposed_count: int = 0
    readiness: ReviewReadinessOut
    blocking_issues: list[ReviewBlockingIssueOut] = []
    engine: ReviewEngineOut


class ExtractionReviewOut(ReviewStateFieldsOut):
    """Slice 7: Extraction Review, with the Slice 8 review state. Request-scoped
    and ephemeral: it rides in the upload response and is kept only in the browser
    tab's memory. Nothing here is applied to the Distance Protection form."""

    manufacturer: str | None = None
    relay_family: str | None = None
    model: str | None = None
    profile_id: str | None = None
    profile_version: str | None = None
    zone_count: int
    not_interpreted_count: int
    #: Interpretation quality, separate from engine compatibility.
    interpretation: Literal["reviewable", "incomplete"]
    notes: list[str] = []
    groups: list[ReviewGroupOut] = []
    not_interpreted: list[ReviewRawSettingOut] = []
    out_of_scope: list[ReviewRawSettingOut] = []
    #: DEC-198 Amendment 5. The signed, opaque validation token sealing the original interpretation,
    #: for stateless re-validation of the user's decisions (see ``POST /api/v1/relay-import/review/validate``
    #: and ``/review/apply``), and the backend-generated import identity it is bound to. Opaque to the
    #: browser: held in tab memory and sent back unchanged; never parsed or built by the page.
    validation_token: str | None = None
    import_id: str | None = None
    #: DEC-195. The parameter catalog that interpreted the relay and how much of the sheet it accounts for
    #: (counts only; ``None`` when no catalog describes the relay).
    catalog_id: str | None = None
    catalog_version: str | None = None
    catalog_coverage: dict | None = None


class ReviewManualResolutionIn(BaseModel):
    item_id: str = Field(max_length=300)
    #: A number for a numeric item, an offered option for a choice. Never coerced:
    #: a string is not a number and a boolean is neither.
    value: StrictFloat | StrictInt | StrictStr


class ReviewValidationIn(BaseModel):
    """The upload's signed validation token and import identity, plus the user's session decisions.

    DEC-198 Amendment 5: unknown fields are refused -- a raw ``validation_context`` (the former,
    unsigned interpretation JSON) is never accepted as authority, not even ignored silently."""

    model_config = ConfigDict(extra="forbid")

    validation_token: str = Field(min_length=1, max_length=4_000_000)
    import_id: str = Field(min_length=1, max_length=64)
    confirmed: list[Annotated[str, Field(max_length=300)]] = Field(default=[], max_length=2000)
    manual: list[ReviewManualResolutionIn] = Field(default=[], max_length=2000)
    left_unresolved: list[Annotated[str, Field(max_length=300)]] = Field(default=[], max_length=2000)
    #: Missing items whose suggested value the user explicitly accepted.
    suggested: list[Annotated[str, Field(max_length=300)]] = Field(default=[], max_length=2000)


class ReviewItemStateOut(BaseModel):
    item_id: str
    #: The interpretation status; a confirmation never rewrites it.
    status: Literal["mapped", "inferred", "unresolved"]
    review_status: ReviewStatusName
    value_text: str | None = None
    blocking: bool = False
    left_unresolved: bool = False
    user_value_text: str | None = None
    category: CategoryName = "mapped"
    engine_reason: str | None = None
    suggestion: ReviewSuggestionOut | None = None
    resolution_origin: Literal["manual", "suggestion"] | None = None
    not_required: bool = False
    not_required_reason: str | None = None
    approximation: ApproximationOut | None = None


class ReviewStateOut(ReviewStateFieldsOut):
    """The reviewed state after the decisions were applied: one entry per
    canonical value plus the counts, blocking issues, engine compatibility and
    readiness. Nothing is stored and nothing is applied to the form."""

    items: list[ReviewItemStateOut] = []


_Ohm = Annotated[float, Field(ge=0, allow_inf_nan=False)]


class ApplyZoneOut(BaseModel):
    """One zone of the applied collection. ``None`` = not configured. Only the fields
    the selected characteristic reads are filled."""

    #: The stable canonical zone id (e.g. ``Z1``, ``ZP``) -- the zone's identity. Never
    #: its position in the list.
    id: Annotated[str, Field(min_length=1)]
    #: The label to show for the zone (the source's own name for it).
    display_name: Annotated[str, Field(min_length=1)]
    enabled: bool
    #: ``None`` only for a *disabled* zone whose direction the source does not state.
    direction: Literal["forward", "reverse"] | None = None
    delay_s: _Ohm | None = None
    #: ``polar``: a reach at an angle. ``explicit_rx``: orthogonal X / +R / -R limits with no
    #: angle (``characteristic_angle_deg`` is then absent) -- never converted to a polar reach.
    geometry_mode: Literal["polar", "explicit_rx"] = "polar"
    #: Reach angle (°) -- distinct from every reach in ohms. Absent for an explicit R/X zone.
    characteristic_angle_deg: Annotated[float, Field(allow_inf_nan=False)] | None = None
    #: Mho |Z| reach (Ω).
    reach_ohm: _Ohm | None = None
    #: Quadrilateral reactive reach (Ω); the X limit of an explicit R/X zone.
    reactive_reach_ohm: _Ohm | None = None
    #: Right Resistive Reach (+R), Ω.
    resistive_reach_forward_ohm: _Ohm | None = None
    #: Left Resistive Reach (−R), Ω. ``0.0`` is a valid setting.
    resistive_reach_reverse_ohm: _Ohm | None = None


class ApplySettingsOut(BaseModel):
    """The controlled apply payload -- exactly what the Distance Protection analysis
    needs, nothing from the uploaded document or the canonical model. Slice 10: ``zones``
    is the complete zone collection of the reviewed model (any number, in the model's
    order, disabled zones included and flagged); it is never truncated to a fixed count."""

    characteristic: Literal["mho", "quadrilateral"]
    impedance_basis: Literal["primary", "secondary"]
    zones: Annotated[list[ApplyZoneOut], Field(min_length=1)]
    #: DEC-198: every engine approximation in the applied configuration (empty = exact). The R-X view
    #: uses it to say the plot is approximate. Empty for every relay today: no rule is approved.
    approximations: list[ApproximationOut] = []


class RelayImportUploadOut(BaseModel):
    filename: str
    source_format: str
    size_bytes: int
    status: Literal["accepted"]
    #: text_extracted | no_extractable_text | encrypted (unreadable is a 400)
    extraction_status: Literal["text_extracted", "no_extractable_text", "encrypted"]
    page_count: int
    pages_with_text: int
    raw_entry_count: int
    section_count: int
    extraction_warnings: list[str]
    #: Slice 5. ``None`` when no text could be read (nothing to identify).
    #: Identified != interpreted: no setting has been read as an engineering value.
    identification_status: Literal["identified", "ambiguous", "unknown"] | None = None
    manufacturer: str | None = None
    relay_family: str | None = None
    model: str | None = None
    profile_id: str | None = None
    #: Categorical, not a probability: high | medium | low | none.
    confidence: Literal["high", "medium", "low", "none"] | None = None
    identification_warnings: list[str] = []
    #: Slice 6. ``None`` when no text could be read. ``not_supported`` for every
    #: relay without an interpretation profile. Interpreted != applied: nothing
    #: is written to the Distance Protection form.
    interpretation_status: Literal["interpreted", "incomplete", "not_supported", "failed"] | None = None
    #: Version of the interpretation profile that ran (an explicit, per-relay-template id).
    profile_version: str | None = None
    mapped_setting_count: int = 0
    #: Rest on profile knowledge the sheet does not state; confirmation recommended.
    inferred_setting_count: int = 0
    unresolved_setting_count: int = 0
    #: Distance-related settings retained raw, not interpreted by this profile version.
    not_interpreted_setting_count: int = 0
    zone_count: int = 0
    interpretation_warnings: list[str] = []
    #: DEC-195. The catalog behind the interpretation (``None`` for a relay no catalog describes) and its
    #: coverage of the extracted settings.
    catalog_id: str | None = None
    catalog_version: str | None = None
    catalog_coverage: dict | None = None
    #: Slice 7. Present only for an ``interpreted`` relay; ``None`` otherwise.
    review: ExtractionReviewOut | None = None
