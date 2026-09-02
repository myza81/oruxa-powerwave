"""Full Powerwave Readiness Validator (CSV/Excel ingestion Slice 9, DEC-072).

Answers exactly one question: **is the current prepared dataset ready
to be converted into Powerwave?** Nothing here performs that
conversion -- no `DisturbanceRecord`, no canonical waveform, no
plotting, no export (all explicitly a later slice). This module only
DECIDES `blocking`/`warning`/`info` and reports why, through the SAME
`app.domain.preparation_issue.PreparationIssue`/`PreparationIssueSummary`
shapes Slice 6 already established -- there is no second, parallel
"readiness issue" model (task's own explicit instruction).

Fits into the architecture exactly as documented:

    Preparation state (raw + WorkingOverlay, Slices 1-5)
            +
    Time-axis interpretation + diagnostics (Slices 7-8D)
            |
    THIS MODULE -- Readiness Validator (Slice 9)
            |
    blocking / warning / info -> is_ready
            ↓ [a LATER slice -- not this one]
    Canonical DisturbanceRecord conversion

**Readiness owns policy; interpreters stay diagnostic producers**
(task section W). `app.services.time_axis_interpreters` never encodes
a blocking/warning decision of its own -- every `TimeAxisDiagnostic` it
produces carries only `severity_hint` (a borrowed, INFORMAL vocabulary,
see `app.domain.time_axis`'s own docstring) and `ambiguity` (whether
`confirmed=true` is even allowed to succeed). This module is the ONE
place a diagnostic CODE is mapped onto a real readiness severity --
`_BLOCKING_TIME_DIAGNOSTIC_CODES`/`_WARNING_TIME_DIAGNOSTIC_CODES`
below are that mapping table, deliberately explicit and reviewable in
one place rather than scattered `if` statements across five
interpreters.

**Live, always current-revision** (task section B): every function
here reads `session.working_overlay`'s CURRENT state directly, and
`get_time_axis_summary()` (reused verbatim) already recomputes its own
diagnostics fresh on every call. Nothing is cached, so nothing can go
stale -- any mutation (cell edit, row exclude, header/data-region/
column-role change, time-axis reconfiguration, undo, redo, reset) is
reflected on the very next call, automatically, with zero explicit
invalidation code needed (matches Slice 6's own established "recompute
live" precedent, extended rather than replaced).

**Two different validation SCOPES, deliberately** (task section S,
important): the time-axis framework's OWN diagnostics (`_time_axis_
readiness_issues` below) are computed from `get_time_axis_summary()`,
which is itself SAMPLE-BASED (a bounded ≤50-row window -- see
`app.services.time_axis_service`'s own docstring) -- reused as-is here,
never re-derived. But the two checks THIS module adds on top --
missing/unparseable TIME-AXIS cell values, and missing/invalid
WAVEFORM cell values -- are BLOCKING, data-content findings that must
hold for the WHOLE canonical dataset, not just whatever 50 rows an
interpreter happened to sample. `_scan_full_active_region()` below
therefore walks the COMPLETE active data region via
`app.services.preparation_preview_service.iterate_active_region_rows()`
-- a single-pass GENERATOR, never a second bounded sample, and never a
full materialized copy of the dataset (task section T: no duplicate
DataFrame, no huge intermediate array -- one row in memory at a time).

**No caching layer** (task section T): re-derived on every call,
exactly like Slice 6. A `source + worksheet + working_revision` cache
key was considered and deliberately NOT built -- the full-region scan
already only runs when the time-axis configuration is otherwise usable
(never for an already-blocking UNCONFIGURED/UNSUPPORTED/REVIEW_REQUIRED
state), and every `GET .../issues` call today already triggers at most
one streaming pass per configured column family; adding a cache before
a real performance problem is observed would be exactly the
"over-engineer caching" this task explicitly warns against.

**Never repairs anything** (task section R, restated here for this
module specifically): no row is ever deleted, inserted, sorted, or
reordered by anything in this file; no timestamp is ever synthesized;
no waveform value is ever interpolated or coerced. This module only
ever APPENDS `PreparationIssue` entries to a plain list and returns
them -- the engineer resolves every finding by editing, excluding, or
reconfiguring, exactly like every earlier slice's own working-overlay
mutations already require.

**Digital channels are explicitly deferred** (task section N): the
CURRENT column-role model (`app.domain.working_overlay.KNOWN_COLUMN_
ROLES`) has no dedicated digital role at all -- only `waveform`/
`time_axis`/`metadata`/`quality_status`/`ignore`/`unknown`. Inventing
one, or inventing a broad `TRUE`/`FALSE`/`ON`/`OFF` mapping table
without an owner-approved role to attach it to, is exactly the kind of
scope creep this task explicitly forbids ("do not invent broad mapping
behavior"). `ISSUE_DIGITAL_VALUE_INVALID` exists in the controlled
vocabulary (`app.domain.preparation_issue`) for when that role
eventually exists, but is never produced by this module today -- a
column holding digital-style text today is classified `waveform` (or
left `unknown`/`metadata`) like anything else, and gets exactly the
SAME numeric-value policy as any other column of that role, never a
silent special case.

**Header/data-region "unconfigured" info findings are unchanged**
(task section AG): `data_region_unconfigured` stays `SEVERITY_INFO`
-- `app.domain.working_overlay.DataRegion`'s own docstring already
establishes "absent key means the entire source is active" as a VALID,
complete semantic, not a defect; Slice 9 does not relabel it. The real
NEW requirements this slice enforces (a configured, coherent time
axis; at least one Waveform Channel) are their own new BLOCKING issues
below, never a severity bump to the old Slice 6 info findings.
"""

from __future__ import annotations

from app.domain.preparation_issue import (
    ISSUE_PARTIAL_TIME_REFERENCE,
    ISSUE_RECONSTRUCTED_TIME,
    ISSUE_SAMPLE_INDEX_FALLBACK,
    ISSUE_TIME_AXIS_UNCONFIGURED,
    ISSUE_TIME_AXIS_UNRESOLVED,
    ISSUE_TIME_AXIS_UNSUPPORTED,
    ISSUE_TIME_VALUE_INVALID,
    ISSUE_TIME_VALUE_MISSING,
    ISSUE_TIMEZONE_UNSPECIFIED,
    ISSUE_USER_SPECIFIED_TIME,
    ISSUE_WAVEFORM_CHANNEL_MISSING,
    ISSUE_WAVEFORM_VALUE_INVALID,
    ISSUE_WAVEFORM_VALUE_MISSING,
    SEVERITY_BLOCKING,
    SEVERITY_WARNING,
    IssueLocation,
    PreparationIssue,
)
from app.domain.preparation_session import PreparationSession
from app.domain.time_axis import (
    DATE_ORDER_AUTO,
    FAMILY_ABSOLUTE,
    FAMILY_ELAPSED,
    FAMILY_PARTIAL,
    FAMILY_SAMPLE_INDEX,
    INTERPRETER_ID_SPLIT_DATE_TIME,
    PROVENANCE_RECONSTRUCTED,
    PROVENANCE_USER_SPECIFIED,
    STATUS_INDEX_FALLBACK,
    STATUS_REVIEW_REQUIRED,
    STATUS_UNCONFIGURED,
    STATUS_UNSUPPORTED,
    TimeAxisInterpretationResult,
)
from app.domain.working_overlay import ROLE_WAVEFORM
from app.services.preparation_preview_service import iterate_active_region_rows
from app.services.preparation_session_registry import PreparationSessionRegistry
from app.services.time_axis_interpreters import _combine_date_and_time, _parse_time_only, _to_float, parse_absolute_datetime
from app.services.time_axis_service import get_time_axis_summary

#: (task section F/G, W) the readiness POLICY mapping from an already-
#: produced `TimeAxisDiagnostic.code` to a real severity -- see this
#: module's own docstring for why this table, not interpreter code,
#: owns the decision. A genuine data-quality/coherence problem with the
#: ACTIVE reading (missing/unparseable/mixed values, or ordering that
#: makes canonical timing unsafe) blocks; everything else that reaches
#: here is a disclosed, still-usable degradation.
_BLOCKING_TIME_DIAGNOSTIC_CODES = frozenset({
    "unparseable_datetime",
    "mixed_datetime_format",
    "non_numeric_elapsed_value",
    "non_numeric_sample_index",
    "missing_datetime_value",
    "missing_elapsed_value",
    "missing_sample_index",
    "time_goes_backward",
    "elapsed_time_goes_backward",
    "sample_index_goes_backward",
    "timestamp_reset_suspected",
})

#: (task section G/H/I/AC-AF) degraded-but-usable findings -- reused
#: verbatim from whichever interpreter produced them (never re-derived
#: here), promoted into a `PreparationIssue` at `SEVERITY_WARNING`.
_WARNING_TIME_DIAGNOSTIC_CODES = frozenset({
    "large_time_gap",
    "non_uniform_interval",
    "non_uniform_elapsed_interval",
    "possible_missing_sample",
    "unexpected_bucket_sample_count",
    "precision_loss_suspected",
    "partial_midnight_rollover_suspected",
    "inconsistent_bucket_count",
    "repeated_timestamp_detected",
    "sample_index_gap",
    "repeated_elapsed_time",
    "repeated_sample_index",
    "anchor_assumption_required",
    "time_only_not_absolute",
})


def _diagnostic_location(worksheet_index: int | None, diagnostic_location) -> IssueLocation:
    row_number = diagnostic_location.row_number if diagnostic_location is not None else None
    return IssueLocation(worksheet_index=worksheet_index, row_number=row_number, field="time_axis")


def _time_axis_readiness_issues(
    *, workspace_id: str, source_id: str, registry: PreparationSessionRegistry, worksheet_index: int | None,
) -> tuple[list[PreparationIssue], TimeAxisInterpretationResult | None, bool]:
    """(task sections C, F, G, H, I, AC-AF) The time-axis half of
    readiness. Returns `(issues, summary, usable)`: `summary` is the
    already-computed `TimeAxisInterpretationResult` the caller reuses
    for the full-region cell-value scan below (never re-fetched a
    second time); `usable` is `False` ONLY for `UNCONFIGURED`/
    `UNSUPPORTED`/`REVIEW_REQUIRED` status (task's own "evaluate the
    active FINAL CONFIGURATION" instruction: there is no coherent
    family/date_order to check individual cell values against yet). A
    resolved reading that ALSO happens to carry a blocking diagnostic
    from its own bounded sample (e.g. `missing_datetime_value`) is
    still `usable=True` -- that diagnostic and the full-region scan
    below are two independent, complementary checks over two different
    scopes (task section S), not a reason to skip one because the
    other already found something."""
    summary = get_time_axis_summary(workspace_id=workspace_id, source_id=source_id, registry=registry)
    issues: list[PreparationIssue] = []

    if summary.status == STATUS_UNCONFIGURED:
        issues.append(PreparationIssue(
            severity=SEVERITY_BLOCKING, code=ISSUE_TIME_AXIS_UNCONFIGURED,
            message="No Time Axis configuration is active -- Powerwave cannot build a canonical waveform dataset without one.",
            location=IssueLocation(worksheet_index=worksheet_index, field="time_axis"),
            suggested_action="Assign the Time Axis role to a column and configure how it should be interpreted.",
        ))
        return issues, summary, False

    if summary.status == STATUS_UNSUPPORTED:
        issues.append(PreparationIssue(
            severity=SEVERITY_BLOCKING, code=ISSUE_TIME_AXIS_UNSUPPORTED,
            message="The stored Time Axis configuration no longer references columns that carry the Time Axis role.",
            location=IssueLocation(worksheet_index=worksheet_index, field="time_axis"),
            suggested_action="Reassign the Time Axis role to the intended column(s), or reconfigure the time axis.",
        ))
        return issues, summary, False

    if summary.status == STATUS_REVIEW_REQUIRED:
        issues.append(PreparationIssue(
            severity=SEVERITY_BLOCKING, code=ISSUE_TIME_AXIS_UNRESOLVED,
            message="The Time Axis configuration is not yet resolved -- an ambiguity or a suggested reconstruction still needs an explicit choice.",
            location=IssueLocation(worksheet_index=worksheet_index, field="time_axis"),
            suggested_action="Open Time Axis review and resolve the pending ambiguity, or accept/adjust the suggested timing.",
        ))
        return issues, summary, False

    # CONFIRMED / NEEDS_ATTENTION / INDEX_FALLBACK -- a resolved, usable
    # reading exists. Inspect its OWN diagnostics for the specific
    # blocking-vs-warning conditions (never the coarse status alone).
    # Note this does NOT affect `usable` below -- a blocking diagnostic
    # here (e.g. a missing/mixed-format value the bounded SAMPLE already
    # caught) still leaves the resolved family/date_order coherent
    # enough to be worth walking cell-by-cell over the FULL region too
    # (task section S's own two-scope model); only a still-open
    # ambiguity/unresolved status (handled above, with its own early
    # `return`) skips that scan entirely.
    for diagnostic in summary.diagnostics:
        location = _diagnostic_location(worksheet_index, diagnostic.location)
        if diagnostic.code in _BLOCKING_TIME_DIAGNOSTIC_CODES:
            issues.append(PreparationIssue(
                severity=SEVERITY_BLOCKING, code=diagnostic.code, message=diagnostic.message,
                location=location, suggested_action=diagnostic.suggested_action, details=diagnostic.details,
            ))
        elif diagnostic.code in _WARNING_TIME_DIAGNOSTIC_CODES:
            issues.append(PreparationIssue(
                severity=SEVERITY_WARNING, code=diagnostic.code, message=diagnostic.message,
                location=location, suggested_action=diagnostic.suggested_action, details=diagnostic.details,
            ))

    if summary.status == STATUS_INDEX_FALLBACK:
        issues.append(PreparationIssue(
            severity=SEVERITY_WARNING, code=ISSUE_SAMPLE_INDEX_FALLBACK,
            message="Time is tracked by sample index only -- all samples are preserved, but real-time duration and synchronization are unavailable.",
            location=IssueLocation(worksheet_index=worksheet_index, field="time_axis"),
        ))
    elif summary.provenance == PROVENANCE_RECONSTRUCTED:
        issues.append(PreparationIssue(
            severity=SEVERITY_WARNING, code=ISSUE_RECONSTRUCTED_TIME,
            message="Timing was reconstructed from repeated timestamps under a stated anchor assumption -- not native precision.",
            location=IssueLocation(worksheet_index=worksheet_index, field="time_axis"),
        ))
    elif summary.provenance == PROVENANCE_USER_SPECIFIED:
        issues.append(PreparationIssue(
            severity=SEVERITY_WARNING, code=ISSUE_USER_SPECIFIED_TIME,
            message="Timing was supplied manually (an explicit rate, interval, or date order) rather than read natively from the source.",
            location=IssueLocation(worksheet_index=worksheet_index, field="time_axis"),
        ))

    if summary.family == FAMILY_PARTIAL:
        issues.append(PreparationIssue(
            severity=SEVERITY_WARNING, code=ISSUE_PARTIAL_TIME_REFERENCE,
            message="Timing is time-of-day only, with no date component -- absolute calendar alignment is unavailable.",
            location=IssueLocation(worksheet_index=worksheet_index, field="time_axis"),
        ))

    return issues, summary, True


def _classify_time_cell(value, *, family: str, date_order: str | None) -> str:
    """`"missing"` / `"ok"` / `"invalid"` for one ALREADY-non-header,
    ALREADY-in-region, ALREADY-non-excluded cell, under the family this
    configuration already resolved to (task section F). Never called
    for `split_date_time` (see `_scan_full_active_region`'s own
    per-interpreter branch below -- that one needs BOTH cells)."""
    if value in (None, ""):
        return "missing"
    if family == FAMILY_PARTIAL:
        return "ok" if _parse_time_only(str(value)) is not None else "invalid"
    if family == FAMILY_ABSOLUTE:
        return "ok" if parse_absolute_datetime(str(value), date_order=date_order or DATE_ORDER_AUTO) is not None else "invalid"
    if family in (FAMILY_ELAPSED, FAMILY_SAMPLE_INDEX):
        return "ok" if _to_float(value) is not None else "invalid"
    return "ok"


def _scan_full_active_region(
    session: PreparationSession, *, worksheet_index: int | None, summary: TimeAxisInterpretationResult,
) -> list[PreparationIssue]:
    """(task sections J, K, L, S) ONE single-pass streaming scan over
    the ENTIRE active data region -- never the bounded sample
    `get_time_axis_summary()` itself uses -- checking BOTH the
    configured Time Axis column(s) AND every CURRENT Waveform Channel
    column in the same pass (never two separate full scans). Excluded
    rows, the header row, and rows outside the active region are all
    skipped, matching every other row-level check in this codebase.
    """
    time_axis_family = summary.family
    time_axis_date_order = (summary.options or {}).get("date_order")
    time_axis_columns = summary.column_indices
    is_split_date_time = summary.interpreter_id == INTERPRETER_ID_SPLIT_DATE_TIME

    # A still-`auto` date order means the ABSOLUTE reading itself is not
    # actually resolved (an edge case only reachable when the interpreter
    # forced-allowed confirm despite `unparseable_datetime`/`mixed_
    # datetime_format` -- already reported as its own BLOCKING issue by
    # `_time_axis_readiness_issues` above) -- skip the redundant,
    # meaningless per-cell re-check rather than re-deriving the same
    # finding a second time under a different code.
    skip_time_axis_scan = time_axis_family == FAMILY_ABSOLUTE and time_axis_date_order in (None, DATE_ORDER_AUTO)

    waveform_columns = sorted(
        c for (ws, c), role in session.working_overlay.column_roles.items()
        if ws == worksheet_index and role == ROLE_WAVEFORM
    )

    time_missing_count = 0
    time_invalid_rows: list[int] = []
    saw_naive_absolute = False
    saw_aware_absolute = False
    waveform_missing: list[tuple[int, int]] = []
    waveform_invalid: list[tuple[int, int, object]] = []

    if (time_axis_columns and not skip_time_axis_scan) or waveform_columns:
        for row in iterate_active_region_rows(session, worksheet_index=worksheet_index):
            if row.excluded or row.is_header or not row.in_active_region:
                continue

            if time_axis_columns and not skip_time_axis_scan:
                if is_split_date_time and len(time_axis_columns) == 2:
                    date_col, time_col = time_axis_columns
                    date_value = row.cells[date_col] if date_col < len(row.cells) else None
                    time_value = row.cells[time_col] if time_col < len(row.cells) else None
                    if date_value in (None, "") or time_value in (None, ""):
                        time_missing_count += 1
                    else:
                        combined = _combine_date_and_time(str(date_value), str(time_value), date_order=time_axis_date_order or DATE_ORDER_AUTO)
                        if combined is None:
                            time_invalid_rows.append(row.row_number)
                        elif combined.tzinfo is None:
                            saw_naive_absolute = True
                        else:
                            saw_aware_absolute = True
                else:
                    col = time_axis_columns[0]
                    value = row.cells[col] if col < len(row.cells) else None
                    status = _classify_time_cell(value, family=time_axis_family, date_order=time_axis_date_order)
                    if status == "missing":
                        time_missing_count += 1
                    elif status == "invalid":
                        time_invalid_rows.append(row.row_number)
                    elif time_axis_family == FAMILY_ABSOLUTE:
                        parsed = parse_absolute_datetime(str(value), date_order=time_axis_date_order or DATE_ORDER_AUTO)
                        if parsed is not None and parsed.tzinfo is None:
                            saw_naive_absolute = True
                        elif parsed is not None:
                            saw_aware_absolute = True

            for col in waveform_columns:
                value = row.cells[col] if col < len(row.cells) else None
                if value in (None, ""):
                    waveform_missing.append((row.row_number, col))
                elif _to_float(value) is None:
                    waveform_invalid.append((row.row_number, col, value))

    issues: list[PreparationIssue] = []
    if time_missing_count:
        issues.append(PreparationIssue(
            severity=SEVERITY_BLOCKING, code=ISSUE_TIME_VALUE_MISSING,
            message=f"{time_missing_count} row(s) in the active data region have no Time Axis value.",
            location=IssueLocation(worksheet_index=worksheet_index, field="time_axis"),
            suggested_action="Fill in, correct, or exclude the affected row(s).",
            details={"missing_count": time_missing_count},
        ))
    if time_invalid_rows:
        issues.append(PreparationIssue(
            severity=SEVERITY_BLOCKING, code=ISSUE_TIME_VALUE_INVALID,
            message=f"{len(time_invalid_rows)} row(s) in the active data region have a Time Axis value that cannot be interpreted under the resolved format.",
            location=IssueLocation(worksheet_index=worksheet_index, row_number=time_invalid_rows[0], field="time_axis"),
            suggested_action="Correct or exclude the affected row(s) -- the original value is preserved.",
            details={"invalid_count": len(time_invalid_rows)},
        ))
    if time_axis_family == FAMILY_ABSOLUTE and saw_naive_absolute and not saw_aware_absolute and not skip_time_axis_scan:
        issues.append(PreparationIssue(
            severity=SEVERITY_WARNING, code=ISSUE_TIMEZONE_UNSPECIFIED,
            message="This absolute timestamp source carries no explicit timezone offset -- values are treated as naive local time.",
            location=IssueLocation(worksheet_index=worksheet_index, field="time_axis"),
        ))
    if waveform_missing:
        first_row, first_col = waveform_missing[0]
        issues.append(PreparationIssue(
            severity=SEVERITY_BLOCKING, code=ISSUE_WAVEFORM_VALUE_MISSING,
            message=f"{len(waveform_missing)} Waveform Channel cell(s) in the active data region are empty.",
            location=IssueLocation(worksheet_index=worksheet_index, row_number=first_row, column_index=first_col),
            suggested_action="Fill in, correct, or exclude the affected row(s) -- missing samples are never synthesized.",
            details={"missing_count": len(waveform_missing)},
        ))
    if waveform_invalid:
        first_row, first_col, first_value = waveform_invalid[0]
        issues.append(PreparationIssue(
            severity=SEVERITY_BLOCKING, code=ISSUE_WAVEFORM_VALUE_INVALID,
            message=f"{len(waveform_invalid)} Waveform Channel cell(s) in the active data region cannot be interpreted as numeric.",
            location=IssueLocation(worksheet_index=worksheet_index, row_number=first_row, column_index=first_col),
            suggested_action="Correct, exclude, or reclassify the affected row(s)/column -- the original value is preserved, never coerced to zero.",
            details={"invalid_count": len(waveform_invalid), "sample_value": str(first_value)},
        ))
    return issues


def collect_readiness_issues(
    session: PreparationSession, worksheet_index: int | None, *, workspace_id: str, source_id: str,
    registry: PreparationSessionRegistry,
) -> list[PreparationIssue]:
    """(Slice 9) The full readiness rule set -- structure (task section
    C/D/E), time-axis coherence (F/G/H/I), and full-active-region
    value validation (J-N). Combined with Slice 6's own unchanged
    configuration-only issues by `app.services.preparation_issue_
    service.build_issue_summary()`, never computed a second, competing
    way there."""
    issues: list[PreparationIssue] = []

    has_waveform_column = any(
        role == ROLE_WAVEFORM
        for (ws, _c), role in session.working_overlay.column_roles.items()
        if ws == worksheet_index
    )
    if not has_waveform_column:
        issues.append(PreparationIssue(
            severity=SEVERITY_BLOCKING, code=ISSUE_WAVEFORM_CHANNEL_MISSING,
            message="No column currently carries the Waveform Channel role -- Powerwave cannot build a canonical dataset with zero channels.",
            location=IssueLocation(worksheet_index=worksheet_index, field="column_roles"),
            suggested_action="Assign the Waveform Channel role to at least one column in the Structure panel.",
        ))

    time_axis_issues, summary, time_axis_usable = _time_axis_readiness_issues(
        workspace_id=workspace_id, source_id=source_id, registry=registry, worksheet_index=worksheet_index,
    )
    issues.extend(time_axis_issues)

    if time_axis_usable or has_waveform_column:
        issues.extend(_scan_full_active_region(
            session, worksheet_index=worksheet_index,
            summary=summary if time_axis_usable else _EMPTY_TIME_AXIS_SUMMARY,
        ))

    return issues


#: A configuration-free stand-in passed to `_scan_full_active_region()`
#: when the time-axis reading itself is not usable (already reported as
#: its own blocking issue above) but a waveform-only scan should still
#: run -- `column_indices=()` means the function's own time-axis branch
#: does nothing at all, exactly as if no Time Axis were configured.
_EMPTY_TIME_AXIS_SUMMARY = TimeAxisInterpretationResult(
    status=STATUS_UNCONFIGURED, family=None, provenance=None, interpreter_id=None, column_indices=(),
)
