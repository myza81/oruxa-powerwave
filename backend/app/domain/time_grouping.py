"""Timestamp-based initial alignment and Time Groups.

**Governing principle (task section 1): "One waveform panel = one
coherent time domain."** A waveform panel should contain sources only
when this app has a defensible shared time relationship between them --
never merely because they carry the same engineering type, both start
at elapsed `0`, share a duration, or share a sampling rate.

Time architecture (task section 3), kept as genuinely separate concepts
rather than one generic offset:

    source native time (waveform_data["time"], never altered)
          |
    timestamp_placement_offset_s  (derived, this module's own job --
    |                               "where does this source's recorded
    |                               start timestamp place it relative to
    |                               its time group's own origin source?")
    |
    manual_alignment_offset_s     (Slice 1's own existing engineer
    |                               correction, app.services.
    |                               synchronization_registry, UNCHANGED)
    v
    effective_alignment_offset_s = timestamp_placement_offset_s
                                  + manual_alignment_offset_s
          |
    time-group workspace time (source_time + effective_alignment_offset_s)
          |
    group t0   (Slice 2's own mechanism, now time-group-scoped --
    |            see app.services.synchronization_service)
    v
    event-relative time

This module owns ONLY the derivation of time groups and each member's
own `timestamp_placement_offset_s` -- it never reads/writes
`manual_alignment_offset_s` (that stays exactly where Slice 1 already
put it, `app.services.synchronization_registry`) and never touches `t0`.
Zero framework dependencies, matching every other `app.domain` module's
own convention.

**Time-reference type (task section 7)**: reuses the EXISTING
`app.domain.timing.TimingInformation.timing_reference` field verbatim
(`"absolute"` when start_time/trigger_time are real recording
timestamps, anything else treated as elapsed-only) -- already threaded
end-to-end through `SourceMetadata.timing_reference` since Phase 1, but
never actually consumed by any grouping logic before this module (every
current COMTRADE record sets it to `"absolute"` by provider
construction; a value of `"relative_elapsed"` is reserved for a future
elapsed-only importer, task section 6's own "for future CSV/Excel..."
scope note -- this module is already correct for that day without any
further change here).

**Grouping rule (task sections 10-15, a technically defensible,
DELIBERATELY CONSERVATIVE first implementation, task section 13's own
explicit instruction: "do not invent complex heuristics unless
necessary")**:

- Every `recorded_absolute` source's own ABSOLUTE INTERVAL is
  `[start_time, start_time + (elapsed_end_seconds - elapsed_start_seconds)]`
  -- i.e. the source's own recorded wall-clock start, plus however long
  its native elapsed axis actually spans (never assuming
  `elapsed_start_seconds == 0`; a pre-trigger-only capture can begin at
  a negative elapsed time). Two `recorded_absolute` sources share a time
  group exactly when their intervals OVERLAP (task section 10/13:
  "absolute-time sources share a group when their intervals overlap...
  keep non-overlapping sources separate by default") -- computed as the
  transitive closure (connected components) of pairwise overlap, so a
  long chain of sequentially-overlapping recordings (task section 12)
  still forms one group even where the first and last members do not
  directly overlap each other.
- Every `elapsed_only` source gets its OWN singleton time group, always
  (task section 14/15: "does not have a valid relationship to an
  absolute-time source unless another anchor exists... do not
  automatically group them together just because all begin at 0").
- A `recorded_absolute` singleton group that failed to overlap with any
  OTHER `recorded_absolute` source present in the same call carries a
  neutral `note` (task section 11: "flag that the recorded timestamps do
  not form a meaningful common event interval... do not permanently
  declare them unrelated events") -- never silently indistinguishable
  from an ordinary single-upload workspace with nothing to overlap with
  in the first place (that case gets no note).
- Each group's own ORIGIN source (task section 4's own worked example:
  "Group origin: <the earliest start>") is the EARLIEST-`start_time`
  member for an absolute group (ties broken by `source_id`, the same
  determinism convention `reference_source_id_for_workspace` already
  established for Slice 1), or the sole member for an elapsed-only
  singleton. The origin source's own `group_id` IS its `source_id` --
  no separate ID scheme (task section 23: "prefer derived/recomputable
  grouping relationships over hardcoded permanent assignment") -- groups
  are recomputed fresh from the CURRENT source set on every call, never
  cached/persisted, so group membership (and therefore which source_id
  is the current origin/group_id) can shift as sources are added or
  removed, exactly like Slice 1's own reference-source rule already
  does at workspace scope.

Sampling rate is never a grouping input (task section 16) -- two
sources at different native rates share a group exactly when their
timing relationship says so; nothing here ever resamples or reads a
sampling rate at all.

**CSV/Excel ingestion Slice 11 (DEC-072) integration finding**:
`start_time` comparison/arithmetic below (interval overlap,
`timestamp_placement_offset_s`) previously assumed every
`recorded_absolute` source's `start_time` shared the same tzinfo
awareness -- true by construction for COMTRADE alone (`app.providers.
comtrade` never attaches a timezone, always naive) but no longer true
once a CSV/Excel source can honestly carry a real, timezone-AWARE
`start_time` (Slice 10 preserves a genuine source-declared offset
rather than discarding it). Comparing (or subtracting) an aware
`datetime` against a naive one raises `TypeError` in Python -- a real,
demonstrated crash reproduced by mixing one naive COMTRADE-style source
with one timezone-aware CSV source in the same workspace. Root cause is
this module being unnecessarily COMTRADE-specific (implicitly "every
absolute source is naive"), not a Slice 10 conversion defect (preserving
a real declared offset is correct). Minimal fix: `normalize_absolute_
datetime()` below -- a naive value has no declared reference at all, so
it is treated as already being in this comparison's own reference frame
(UTC-labelled, not converted) purely so it becomes comparable; an
already-aware value is left completely untouched (its real declared
offset is honored). For the previously-only-reachable all-naive case
(pure COMTRADE, or COMTRADE + a timezone-unspecified CSV source), every
value gets the identical UTC label, so every comparison/subtraction
result is numerically IDENTICAL to before this fix -- zero behavior
change for that case, verified in
`tests/test_time_grouping_timezone_integration.py`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


def normalize_absolute_datetime(value: datetime) -> datetime:
    """Make an absolute `start_time` safe to compare/subtract against
    another one, regardless of which one (if either) carries a real
    declared timezone offset -- see this module's own docstring for the
    full "CSV/Excel ingestion Slice 11" rationale. A naive value (no
    declared offset at all, e.g. every COMTRADE recording today) is
    given the UTC label WITHOUT converting its wall-clock numbers --
    this is not a claim that the value truly IS UTC, only that "no
    declared offset" must resolve to SOME consistent reference so two
    such values remain directly comparable exactly as they always were
    (both get the same label, so their difference is unchanged). An
    already timezone-aware value is returned completely unmodified --
    its genuine declared offset is never overridden or reinterpreted.
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value

TIME_REFERENCE_RECORDED_ABSOLUTE = "recorded_absolute"
TIME_REFERENCE_ELAPSED_ONLY = "elapsed_only"
#: Time of Day (CSV/Excel ingestion, additive) -- a source whose own
#: time axis is genuine clock time with NO date component
#: (`app.domain.timing.TimingInformation.timing_reference ==
#: "time_of_day"`, set only for a converted `FAMILY_PARTIAL` source).
#: Kept as a THIRD, fully separate bucket from both
#: `TIME_REFERENCE_RECORDED_ABSOLUTE` and `TIME_REFERENCE_ELAPSED_ONLY`
#: -- never merged with either in `derive_time_groups()` below.
#: **The governing rule this bucket exists to enforce: Absolute DateTime
#: and Time of Day must never be automatically synchronized merely
#: because their clock portions look similar** -- a source recorded at
#: `2026-06-03 18:04:00` (recorded_absolute) and one recorded at
#: `18:04:00` with no date (time_of_day) share no defensible time
#: relationship this app is entitled to assume, so they are never even
#: compared for overlap against each other. Two `time_of_day` sources,
#: however, MAY share a group with EACH OTHER by ordinary clock-time
#: interval overlap (see `_TimeOfDaySource`/`_time_of_day_interval()`
#: below) -- exactly the same "intervals overlap -> one group" rule
#: `recorded_absolute` already uses, just in date-neutral
#: seconds-since-midnight coordinates instead of real calendar
#: `datetime`s, and never combined with one.
TIME_REFERENCE_TIME_OF_DAY = "time_of_day"

#: Task section 11's own suggested neutral wording -- never an
#: alarmist/definitive "different event" claim (the gap may be a wrong
#: recorder clock, a timezone mismatch, or a genuinely different event;
#: this module has no way to distinguish those, and section 11 is
#: explicit that it must not pretend to).
NON_OVERLAPPING_NOTE = "Large timestamp separation / no temporal overlap with other recorded-absolute sources in this workspace."


@dataclass(slots=True)
class TimeGroup:
    """One coherent time domain -- task section 9's own "Time Group."
    `group_id` is always the CURRENT `origin_source_id` (see this
    module's own docstring for why that is deliberately not a separate,
    hardcoded identifier). `source_ids` is ordered with `origin_source_id`
    first, then every other member sorted by `source_id` for a
    deterministic, stable rendering order."""

    group_id: str
    time_reference_type: str
    origin_source_id: str
    source_ids: list[str]
    note: str | None = None


def time_reference_type_for_source(timing_reference: str) -> str:
    """Task section 7's own minimum-required distinction: "source has a
    usable absolute recording start" vs. "source has only elapsed/native
    time." Reuses `SourceMetadata.timing_reference` verbatim (see this
    module's own docstring) -- the provider's own `"absolute"` literal
    maps to `recorded_absolute`, `"time_of_day"` (Time of Day, additive)
    maps to its own separate bucket, and anything else is treated as
    elapsed-only, never guessed at more finely than that (task section
    6: "do not introduce generic timestamp guessing into synchronization
    code")."""
    if timing_reference == "absolute":
        return TIME_REFERENCE_RECORDED_ABSOLUTE
    if timing_reference == "time_of_day":
        return TIME_REFERENCE_TIME_OF_DAY
    return TIME_REFERENCE_ELAPSED_ONLY


@dataclass(slots=True)
class _AbsoluteSource:
    source_id: str
    start_time: datetime
    interval_start: datetime
    interval_end: datetime


def _absolute_interval(*, start_time: datetime, elapsed_start_seconds: float, elapsed_end_seconds: float) -> tuple[datetime, datetime]:
    """Task section 4/17: `absolute_sample_time = start_timestamp +
    native_elapsed_time`, applied at BOTH ends of the source's own
    recorded native span -- never `sample_index / nominal_rate` (task
    section 17's own explicit anti-pattern; multi-rate sources are
    already handled correctly for free, since this reads the record's
    own true elapsed bounds, never a single assumed sample interval).
    `datetime + timedelta` is exact (no floating-point date-rollover
    edge case, task section 18) and preserves whatever sub-second
    precision `start_time` itself already carries (task section 4:
    "preserve sub-millisecond precision... do not rely on JavaScript
    Date millisecond precision")."""
    return (
        start_time + timedelta(seconds=elapsed_start_seconds),
        start_time + timedelta(seconds=elapsed_end_seconds),
    )


def _intervals_overlap(a: _AbsoluteSource, b: _AbsoluteSource) -> bool:
    """Inclusive overlap -- two intervals that merely touch at an
    endpoint are treated as overlapping (the conservative direction:
    task section 13 asks for non-overlap to be the DEFAULT for a genuine
    gap, not for two recordings that are contiguous down to the same
    instant to be split apart on a coin-flip boundary rule).

    Works unchanged for `_TimeOfDaySource` too (duck-typed on
    `.interval_start`/`.interval_end`) -- one shared overlap rule for
    both buckets, never a second copy."""
    return a.interval_start <= b.interval_end and b.interval_start <= a.interval_end


@dataclass(slots=True)
class _TimeOfDaySource:
    """Time of Day (additive) counterpart of `_AbsoluteSource` -- an
    interval in date-neutral seconds-since-midnight coordinates instead
    of real `datetime`s. `anchor_seconds` (always in `[0, 86400)`) is the
    source's own clock position at its elapsed=0 origin
    (`SourceMetadata.time_of_day_reference_seconds`); `interval_start`/
    `interval_end` add that source's own `elapsed_start_seconds`/
    `elapsed_end_seconds` on top -- exactly `_absolute_interval()`'s same
    `start_time + elapsed` composition, just in seconds rather than
    `timedelta`. `interval_end` may exceed `86400` when THIS source's
    own canonical time axis legitimately unwrapped a midnight rollover
    (see `app.services.time_axis_normalization`'s own unwrap logic) --
    that is what lets two sources which both genuinely cross the SAME
    midnight still compare correctly via plain numeric overlap below,
    with no cross-source day-shifting ever attempted."""

    source_id: str
    anchor_seconds: float
    interval_start: float
    interval_end: float


def _connected_components(nodes: list[str], edges: set[tuple[str, str]]) -> list[list[str]]:
    """Plain union-find -- task section 12's own "long overlapping
    chain" requirement (A overlaps B, B overlaps C, A does not overlap C
    directly) needs TRANSITIVE closure, not a single pairwise check."""
    parent: dict[str, str] = {n: n for n in nodes}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for a, b in edges:
        union(a, b)

    components: dict[str, list[str]] = {}
    for n in nodes:
        components.setdefault(find(n), []).append(n)
    return list(components.values())


def derive_time_groups(
    sources: list[tuple[str, str, datetime | None, float, float]],
    *,
    time_of_day_reference_seconds: dict[str, float] | None = None,
) -> list[TimeGroup]:
    """Derive every current Time Group from the workspace's current
    source set, recomputed fresh on every call (never cached/persisted --
    see this module's own docstring).

    `sources` is `[(source_id, timing_reference, start_time,
    elapsed_start_seconds, elapsed_end_seconds), ...]` -- deliberately a
    plain tuple list, not `SourceMetadata` itself, so this module stays
    a pure `app.domain` function with no dependency on `app.domain.source`
    (mirrors `reference_source_id_for_workspace()`'s own established
    `[(source_id, created_at), ...]` shape). `start_time` may be `None`
    for a `recorded_absolute`-typed source only in a defensively-handled
    edge case (a corrupt/missing field this module did not itself
    validate) -- such a source is demoted to its own `elapsed_only`-style
    singleton group rather than crashing.

    `time_of_day_reference_seconds` (Time of Day, additive) is an
    OPTIONAL `source_id -> seconds_since_midnight` lookup, needed only
    for sources whose own `timing_reference == "time_of_day"` (mirrors
    `SourceMetadata.time_of_day_reference_seconds`, kept as a SEPARATE
    parameter rather than widening the `sources` tuple itself, so every
    existing caller/test that already builds a plain 5-tuple keeps
    working completely unchanged). A `time_of_day`-typed source with no
    entry here (the same defensive "corrupt/missing field" edge case
    `start_time is None` already gets for `recorded_absolute`) is
    likewise demoted to its own `elapsed_only`-style singleton rather
    than crashing.

    Returns one `TimeGroup` per group, `source_ids` ordered
    origin-first. Order of the returned list itself is deterministic
    (sorted by `group_id`) but otherwise not meaningful.
    """
    time_of_day_reference_seconds = time_of_day_reference_seconds or {}
    absolute: list[_AbsoluteSource] = []
    time_of_day: list[_TimeOfDaySource] = []
    elapsed_only_ids: list[str] = []

    for source_id, timing_reference, start_time, elapsed_start_seconds, elapsed_end_seconds in sources:
        reference_type = time_reference_type_for_source(timing_reference)
        if reference_type == TIME_REFERENCE_RECORDED_ABSOLUTE and start_time is not None:
            # Slice 11 fix: normalize BEFORE any interval arithmetic/
            # comparison -- see this module's own docstring.
            start_time = normalize_absolute_datetime(start_time)
            interval_start, interval_end = _absolute_interval(
                start_time=start_time, elapsed_start_seconds=elapsed_start_seconds, elapsed_end_seconds=elapsed_end_seconds
            )
            absolute.append(_AbsoluteSource(source_id=source_id, start_time=start_time, interval_start=interval_start, interval_end=interval_end))
        elif reference_type == TIME_REFERENCE_TIME_OF_DAY and time_of_day_reference_seconds.get(source_id) is not None:
            anchor_seconds = time_of_day_reference_seconds[source_id]
            time_of_day.append(
                _TimeOfDaySource(
                    source_id=source_id,
                    anchor_seconds=anchor_seconds,
                    interval_start=anchor_seconds + elapsed_start_seconds,
                    interval_end=anchor_seconds + elapsed_end_seconds,
                )
            )
        else:
            elapsed_only_ids.append(source_id)

    groups: list[TimeGroup] = []

    if absolute:
        by_id = {a.source_id: a for a in absolute}
        node_ids = [a.source_id for a in absolute]
        edges = {
            (a.source_id, b.source_id)
            for i, a in enumerate(absolute)
            for b in absolute[i + 1 :]
            if _intervals_overlap(a, b)
        }
        components = _connected_components(node_ids, edges)
        multiple_absolute_groups = len(components) > 1

        for member_ids in components:
            members = sorted((by_id[sid] for sid in member_ids), key=lambda a: (a.start_time, a.source_id))
            origin = members[0]
            ordered_ids = [origin.source_id] + sorted(m.source_id for m in members[1:])
            note = NON_OVERLAPPING_NOTE if (len(members) == 1 and multiple_absolute_groups) else None
            groups.append(
                TimeGroup(
                    group_id=origin.source_id,
                    time_reference_type=TIME_REFERENCE_RECORDED_ABSOLUTE,
                    origin_source_id=origin.source_id,
                    source_ids=ordered_ids,
                    note=note,
                )
            )

    # Time of Day (additive): the SAME overlap/connected-components rule
    # as `recorded_absolute` above, in its own SEPARATE pass -- never
    # merged with the `absolute` list, so a Time of Day source and a
    # Recorded Absolute source can never end up sharing a group merely
    # because their clock portions happen to look similar (the
    # governing rule this whole bucket exists to enforce -- see
    # `TIME_REFERENCE_TIME_OF_DAY`'s own docstring).
    if time_of_day:
        tod_by_id = {t.source_id: t for t in time_of_day}
        tod_node_ids = [t.source_id for t in time_of_day]
        tod_edges = {
            (a.source_id, b.source_id)
            for i, a in enumerate(time_of_day)
            for b in time_of_day[i + 1 :]
            if _intervals_overlap(a, b)
        }
        tod_components = _connected_components(tod_node_ids, tod_edges)
        multiple_tod_groups = len(tod_components) > 1

        for member_ids in tod_components:
            members = sorted((tod_by_id[sid] for sid in member_ids), key=lambda t: (t.anchor_seconds, t.source_id))
            origin = members[0]
            ordered_ids = [origin.source_id] + sorted(m.source_id for m in members[1:])
            note = NON_OVERLAPPING_NOTE if (len(members) == 1 and multiple_tod_groups) else None
            groups.append(
                TimeGroup(
                    group_id=origin.source_id,
                    time_reference_type=TIME_REFERENCE_TIME_OF_DAY,
                    origin_source_id=origin.source_id,
                    source_ids=ordered_ids,
                    note=note,
                )
            )

    for source_id in elapsed_only_ids:
        groups.append(
            TimeGroup(
                group_id=source_id,
                time_reference_type=TIME_REFERENCE_ELAPSED_ONLY,
                origin_source_id=source_id,
                source_ids=[source_id],
                note=None,
            )
        )

    groups.sort(key=lambda g: g.group_id)
    return groups


def timestamp_placement_offset_s(*, source_start_time: datetime | None, origin_start_time: datetime | None) -> float:
    """Task section 4's own composition: the seconds a source's native
    elapsed-time array must be shifted by so that
    `origin_start_time + 0 == source_start_time + placement` -- i.e.
    `placement = source_start_time - origin_start_time`, computed via
    `datetime` subtraction (exact `timedelta`, never JS `Date`
    millisecond rounding -- task section 4's own explicit warning) and
    converted to a `float` of seconds only at the very end via
    `.total_seconds()` (double precision, far finer than millisecond
    resolution at the magnitudes real COMTRADE offsets take).

    `0.0` whenever either timestamp is unavailable (the source IS the
    origin, or this is an elapsed-only source with no absolute anchor at
    all) -- never a fabricated placement (task section 14: "do not
    assume elapsed 0 = absolute group start"). Slice 11 fix: both inputs
    are normalized (see `normalize_absolute_datetime()`) before
    subtraction -- mixing a naive and a timezone-aware `datetime`
    otherwise raises `TypeError`."""
    if source_start_time is None or origin_start_time is None:
        return 0.0
    source_start_time = normalize_absolute_datetime(source_start_time)
    origin_start_time = normalize_absolute_datetime(origin_start_time)
    return (source_start_time - origin_start_time).total_seconds()


def time_of_day_placement_offset_s(*, source_reference_seconds: float | None, origin_reference_seconds: float | None) -> float:
    """Time of Day (additive) counterpart of `timestamp_placement_offset_s()`
    above -- the SAME composition (`placement = source_anchor -
    origin_anchor`), in date-neutral seconds-since-midnight coordinates
    instead of `datetime` subtraction. `0.0` whenever either anchor is
    unavailable, mirroring that function's own same defensive default."""
    if source_reference_seconds is None or origin_reference_seconds is None:
        return 0.0
    return source_reference_seconds - origin_reference_seconds
