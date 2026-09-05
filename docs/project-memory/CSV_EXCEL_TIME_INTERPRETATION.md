# CSV/Excel Time Interpretation Framework — Design Specification

Status: **Slice 7 (framework) is `[DONE, 2026-09-01]`. Slice 8A — the
first two of §19's five initial interpreters (single-column absolute
datetime, Date + Time) — is `[DONE, 2026-09-01]`. Slice 8B — the next
two (elapsed numeric time, sample index) — is `[DONE, 2026-09-02]`.
Slice 8C — the fifth and final §19 interpreter (repeated-timestamp /
precision-loss detection and user-approved reconstruction) — is
`[DONE, 2026-09-02]`, all implemented as real, deterministic
(non-fuzzy) interpreters (see
[CSV_EXCEL_INGESTION_ARCHITECTURE.md item 8](CSV_EXCEL_INGESTION_ARCHITECTURE.md#14-recommended-implementation-slices--owner-revised-sequence-dec-072-not-yet-authorized-to-begin)
for the full implementation summaries). §19's own five-interpreter list
is now fully implemented; segmented/variable-cadence reconstruction
(§7's own scope boundary) remains explicitly deferred, not a Slice 8C
gap. Slice 8D — Time Irregularity Diagnostics, a diagnostic-only
normalization layer over §11's own irregular-timing table (never a new
interpreter, never readiness policy) — is `[DONE, 2026-09-02]`. Slice 9
— the Full Powerwave Readiness Validator, the REAL `blocking`/
`warning`/`info` policy this document's own §13 always deferred — is
ALSO `[DONE, 2026-09-02]`; see
[CSV_EXCEL_INGESTION_ARCHITECTURE.md item 9](CSV_EXCEL_INGESTION_ARCHITECTURE.md#14-recommended-implementation-slices--owner-revised-sequence-dec-072-not-yet-authorized-to-begin)
for its own full implementation summary. Canonical `DisturbanceRecord`
conversion — Slice 10 — is ALSO `[DONE, 2026-09-03]`; see
[CSV_EXCEL_INGESTION_ARCHITECTURE.md item 10](CSV_EXCEL_INGESTION_ARCHITECTURE.md#14-recommended-implementation-slices--owner-revised-sequence-dec-072-not-yet-authorized-to-begin)
for its own full implementation summary, and §14 below for the specific
family→`timing_reference` mapping table this document proposed and
Slice 10 implemented verbatim.**

Date: 2026-09-01
Source: owner-requested design checkpoint, preceding Slice 7. This
document is the authoritative design reference for Slice 7 (framework)
and Slice 8 (initial interpreters) of the owner-revised CSV/Excel
ingestion sequence recorded in
[CSV_EXCEL_INGESTION_ARCHITECTURE.md §14](CSV_EXCEL_INGESTION_ARCHITECTURE.md#14-recommended-implementation-slices--owner-revised-sequence-dec-072-not-yet-authorized-to-begin).

This document does not reproduce `CSV_EXCEL_INGESTION_ARCHITECTURE.md`'s
own content — it assumes Slices 1–6 plus the two owner-UAT refinements
(progressive-disclosure UX; data-region end-selection) already exist
exactly as documented there and in `CURRENT_STATE.md`. Where this
document's design touches existing code, it cites the actual current
file/line, not an assumed shape.

---

## 1. Purpose and scope

**Purpose**: settle, before any implementation begins, how Powerwave
will interpret time information found in a CSV/Excel preparation
source — what semantic categories exist, who has final authority over
interpretation, how uncertain or degraded timing evidence is handled,
how the result is presented, and exactly where this stage's
responsibility ends and the next stage's begins.

**In scope**: the design of the time-interpretation domain model,
provenance model, fallback hierarchy, confidence model, UI/UX
organization, and the Slice 7/Slice 8 boundary.

**Out of scope (design only, nothing built here)**: any actual
timestamp parser, reconstruction algorithm, sampling-rate inference,
readiness validation logic, new production preparation-issue codes,
`DisturbanceRecord` conversion, waveform plotting, export, or automatic
row/data repair. See §20 for the complete explicit non-goals list.

**Architecture this design must fit inside, unchanged**:

```text
Immutable raw source (PreparationSession.raw_bytes)
        +
Sparse non-destructive Working Overlay (app.domain.working_overlay)
        +
Header row / dataset-wide Data Region / Column Roles (Slice 5)
        +
Preparation Readiness Issue model (Slice 6 — info-only today)
        +
Progressive-disclosure Data Preparation Workspace UI (owner UAT)
        ↓  [Slice 7/8 — THIS DOCUMENT'S subject]
Time Axis interpretation (candidate interpreted time, never canonical)
        ↓  [Slice 9 — NOT this document's subject]
Readiness Validator (decides acceptability, including time validity)
        ↓  [Slice 10 — NOT this document's subject, now DONE]
Canonical DisturbanceRecord conversion
        ↓
Existing Powerwave waveform/Time-Group/synchronization behavior — UNCHANGED
```

This document proposes nothing that requires modifying
`app/domain/disturbance_record.py`, `app/domain/timing.py`,
`app/domain/time_grouping.py`, `app/services/synchronization_service.py`,
or any waveform-rendering code — a claim scoped to Slices 7-9 (this
document's own subject), verified directly against the current content
of each file before writing this design (see §17). Slice 10 (a LATER
document's scope, not this one) did minimally widen
`app/domain/timing.py`'s `TimingInformation.start_time`/`.trigger_time`
to `datetime | None` — see
[CSV_EXCEL_INGESTION_ARCHITECTURE.md item 10](CSV_EXCEL_INGESTION_ARCHITECTURE.md#14-recommended-implementation-slices--owner-revised-sequence-dec-072-not-yet-authorized-to-begin)
for why that one change was necessary and why `time_grouping.py`/
`synchronization_service.py` needed none.

---

## 2. Core principles

These formalize the owner's own stated rules for this design. Every
later section is subordinate to these.

**Principle 1 — Preserve data first, interpret second.** Never
automatically discard a non-empty source value. Only a genuinely empty
cell (raw `None`, or a working edit to `""` — the exact same "blank"
concept `app.services.preparation_preview_service` already uses for
column labels, see that module's own `_build_column_labels()`) may be
treated as missing. An ambiguous or suspicious non-empty value
(`"N/A"`, `"ERR"`, `"#VALUE!"`, `"12.4?"`, unexpected text in a
Time-Axis or Waveform-Channel column) is preserved byte-for-byte and
surfaced as a diagnostic — never converted to zero, dropped, replaced
with `NaN` in a way that loses the original value, interpolated,
overwritten, merged, or silently coerced.

**Principle 2 — Never discard samples because timestamps repeat.**
Five rows sharing the literal timestamp `13:14:01` are five distinct
samples. They are never collapsed to one, never deduplicated, never
reduced to "keep the first," and never silently reordered or merged.
Repetition is *evidence about the time axis's own precision*, not a
data-quality defect to repair by removing rows.

**Principle 3 — Never reorder source rows.** Row order may itself
carry engineering meaning (this is already the exact rule Slice 4/5
enforce for row exclusion/data-region narrowing — see
`app.domain.working_overlay`'s own module docstring: "None of these
ever renumber"). Time interpretation extends this rule to itself: even
when timestamps appear out of order, rows are never reordered to make
them monotonic. Non-monotonic time is a *diagnostic*, handled at the
Readiness Validator stage (§13), never silently repaired here.

**Principle 4 — Backend is authoritative; the frontend never
manufactures a time interpretation.** Identical to the rule already
established for Slice 5 structure state and Slice 6 issues: the
frontend renders what the backend already decided/suggested/detected;
it never independently classifies a time family or computes a
reconstructed value client-side.

**Principle 5 — Never fabricate an absolute anchor.** Directly
reaffirms **DEC-072 point 5**, already binding: a source with no
defensible absolute timestamp must never receive a fabricated
`start_time` merely to satisfy `TimingInformation`'s non-`None` field —
no `powerwave`-style `2000-01-01` sentinel (see
[POWERWAVE_DISCOVERY.md — The 2000-01-01 sentinel](POWERWAVE_DISCOVERY.md#the-2000-01-01-sentinel--the-load-bearing-detail-behind-anchored-sources)),
ever. This is the single most load-bearing constraint on the entire
design below.

**Principle 6 — The format list stays permanently open-ended.**
Directly reaffirms **DEC-072 point 6**. Every semantic family, every
interpreter, and every provenance state below is illustrative, not
exhaustive. The interpreter-registry model (§17) exists specifically so
a new format never requires touching `time_grouping.py`,
`synchronization.py`, or waveform-rendering code — exactly the
extensibility already proven for the existing two-value
`timing_reference` signal (§4/§15 of the architecture document).

**Principle 7 — Detect, suggest, preview, warn — never decide
silently.** Formalized fully in §5.

**Principle 8 — Progressive disclosure, always.** A compact summary is
the default view; full interpreter mechanics are never permanently
visible. Formalized fully in §15.

---

## 3. Time semantic families

An open-ended set of conceptual categories a Time-Axis column (or
column combination) can belong to. New families may be added later
without changing this document's own model — only the registry's
contents grow.

| Family | Meaning | Example | Requires |
|---|---|---|---|
| `absolute` | A real calendar date+time exists or can be assembled from the selected column(s) | `2026-08-31 13:09:44.305` | A parseable date component (native or assembled from a multi-column combination, §10) |
| `elapsed` | A relative/duration axis — "seconds/ms/µs since some reference," reference itself not necessarily known | `0.000, 0.001, 0.002` | An explicit unit (§9) |
| `sample_index` | A plain integer sequence with no time semantics of its own | `1, 2, 3, 4` | Nothing to interpret time from directly; a rate may optionally be supplied to derive elapsed time (§9) |
| `partial` | A real time-of-day (or other partial calendar component) with a REQUIRED piece missing — most commonly time-of-day with no date | `13:09:44.305` | Must NOT be silently promoted to `absolute`; promotion requires the user to explicitly supply or confirm the missing component (a date, a base day boundary, etc.) |
| `unknown` | Powerwave cannot safely classify the column(s) at all | arbitrary/unrecognized text, or a plausible-looking but unparseable pattern | Nothing — must remain representable without destroying the source value (Principle 1) |

Two structural notes:

- **A family is a classification of the SOURCE representation, not a
  claim about the resulting quality.** An `absolute` family with
  precision-loss (repeated timestamps) is still `absolute` — its
  *provenance* (§4) is what changes (`native` → `reconstructed`), not
  its family.
- **`partial` is deliberately its own family, not a sub-case of
  `absolute` or `unknown`.** A time-only column is neither "a full
  absolute timestamp" (it structurally cannot be, per Principle 5) nor
  "meaningless" (it may carry real, useful ordering/interval
  information once the missing piece is supplied). Collapsing it into
  either neighbor would either violate Principle 5 or discard usable
  evidence.

---

## 4. Time provenance / quality

Every *resulting interpreted time value* (not the family classification
itself — see §3's second note) carries how it was obtained. Four
states, deliberately not more (see the reasoning after the table for
why "inferred" was considered and folded in rather than added):

| Provenance | Meaning |
|---|---|
| `native` | The value is exactly what a family-appropriate parse of the source cell(s) produced — no gap-filling, no user-supplied assumption |
| `reconstructed` | Powerwave synthesized/adjusted the value (e.g. distributing repeated timestamps across a suggested interval) — ALWAYS shown alongside the original native value it was derived from, and ALWAYS requires the user's explicit acceptance before it becomes the active interpretation (§5, §7) |
| `user_specified` | The user directly supplied the deciding piece of information (an interval, a sampling rate, a unit, an explicit override value) that produced this interpretation |
| `index_only` | The fallback: no time semantics were established at all; the active plotting basis is the row's own sequential position, not a time value (§9) |

**Why not a separate `inferred` state**: the task material raises this
as a candidate. On inspection, everything "inferred" in this framework
either (a) becomes a concrete `reconstructed` value once the user
accepts a suggestion, or (b) is a *confidence label on a suggestion
that has not yet been accepted at all* — which is not a provenance of
an actual value, since no value is active yet. Confidence (§6) already
carries that second meaning cleanly. Adding a fifth provenance state
here would create two different words for the same "not yet real"
concept. Kept to four, per the task's own "do not overcomplicate unless
necessary" instruction.

**Binding display rule** (directly from the task's own example):
a reconstructed timestamp must never be presented as though it came
natively from the source. Concretely: any UI or API surface showing a
`reconstructed` time value must show it paired with its own source
evidence and its own provenance label — never as a bare value
indistinguishable from `native`.

---

## 5. User authority model

Powerwave (the interpreter/detection layer) may only ever:

```text
detect       — classify a column/combination into a family, or fail to
suggest      — propose a reconstructed value or a family/unit choice
preview      — show a bounded before/after sample (§16)
warn         — surface a diagnostic (§11)
```

The engineer alone may:

```text
accept        — confirm a suggestion, making it the active interpretation
adjust        — change family, unit, columns, or a suggested value
keep original — decline a suggestion; the native/partial value stands as-is
use sample index — explicitly fall back, abandoning time semantics
```

**No silent engineering decision when ambiguity materially affects time
interpretation.** This is the direct extension of the same principle
already governing column roles (`app.domain.working_overlay`'s own "do
NOT automatically classify columns" rule, Slice 5) and Slice 6's own
issue model ("do NOT silently decide a header is mandatory"). Time
interpretation is simply the highest-stakes instance of a rule this
codebase already lives by everywhere else in preparation.

A *non-ambiguous* detection (§7's "clean case," e.g. a single column of
unambiguous ISO-8601 absolute timestamps with a strictly increasing,
non-repeating sequence) may be shown as already `Ready` without
requiring an explicit click — there is nothing to decide. The line is:
**if two people could reasonably disagree about the correct
interpretation, or if any information had to be invented to produce
one, the engineer must be asked.** If not, showing a confirmed default
is not a violation of this principle — it is simply reporting a fact.

---

## 6. Interpretation fallback hierarchy

The owner-approved hierarchy, formalized:

```text
1. Use valid native time
        ↓ (only if step 1 cannot produce a trustworthy result)
2. Detect precision loss / repeated-timestamp pattern
        ↓
3. Suggest a reconstructed interval, IF cadence confidence supports it
        ↓ (always available, at any point in this chain)
4. Allow the user to enter an interval / sampling rate manually
        ↓ (only if nothing above produced an accepted result)
5. Preserve all rows; fall back to Sample Index
```

Two properties this hierarchy is designed to guarantee:

- **Monotonic degradation of TRUST, never of DATA.** Every step down
  this chain reduces how much Powerwave claims to know about real time
  — it never reduces how many rows exist or what their original values
  were.
- **The user may enter at any rung, at any time, in either direction.**
  A source that starts at step 5 (index fallback, because detection
  found nothing usable) can move to step 4 the moment the user supplies
  a rate. A source sitting at step 3 (an unaccepted suggestion) can be
  overridden straight to step 4 (the user's own number) or abandoned
  straight to step 5. This is not a one-way pipeline; it is a
  configuration the user can revisit, matching the same
  edit-anytime/undo-anytime posture already established for header,
  data-region, and column-role state (Slice 5).

**Confidence model** (step 3's own gate, kept deliberately simple per
the task's own "do not make confidence mathematically elaborate unless
justified" instruction):

| Level | Informal meaning | Example evidence |
|---|---|---|
| High | The repeated-bucket pattern is stable across many consecutive transitions, with no irregular gaps | `5, 5, 5, 5, 5, 5, ...` rows per second-bucket, sustained |
| Medium | The pattern is mostly stable but has some irregularity, or the sample size is small | `5, 5, 4, 5, 6, 5, 5` — close, not perfectly uniform |
| Low | The pattern is inconsistent enough that automatic reconstruction should not be offered as a one-click action | `5, 4, 7, 3, 8, 2` |

A `Low` confidence result is still SHOWN as a diagnostic (§11) — it is
never hidden — but the UI does not present a one-click "Accept
Suggestion" affordance for it; the user is directed toward manual entry
(step 4) or Sample Index (step 5) instead. This is a UI-presentation
distinction, not a data-visibility one — consistent with Principle 1.

This confidence model is explicitly a *qualitative bucket*, not a
numeric score with fixed thresholds — deferring the exact
evidence-to-bucket rule to whichever interpreter implements it in
Slice 8, since that rule is properly an *interpreter's own concern*
(§17), not part of the framework contract itself.

---

## 7. Repeated timestamp / precision-loss handling

This is the scenario the owner's own example walks through in detail,
formalized as the framework's own worked case.

**Detection concept**: group consecutive rows by identical native
timestamp value, forming buckets. A bucket size greater than 1
indicates the source's own recorded precision is coarser than its true
sampling interval. This is computed only over the CURRENT bounded
preview page/window (never a full-dataset scan) for the compact-panel
summary and the review preview (§16); a wider (but still explicitly
bounded, never whole-file) sample may be used by an interpreter to
raise its own confidence level, at that interpreter's own discretion —
the framework contract does not mandate a specific scan size, only that
it must stay bounded (§18's own performance requirement).

**Reconstruction suggestion**: when a stable bucket-count pattern
supports it (§6's confidence model), the interpreter may propose
distributing each bucket's own rows evenly across the interval implied
by the transition to the NEXT distinct native timestamp. Example
(directly from the task):

```text
Native            Suggested (reconstructed)
13:14:01          13:14:01.000
13:14:01          13:14:01.200
13:14:01          13:14:01.400
13:14:01          13:14:01.600
13:14:01          13:14:01.800
13:14:02          13:14:02.000
```

**Phase ambiguity is explicitly acknowledged, not hidden.** The
evidence above supports a 200 ms SPACING; it does not by itself prove
whether the first sample within the `13:14:01` bucket truly occurred at
`.000` rather than, say, `.100` (a half-interval phase shift). The
design's own response to this is definitional, not algorithmic: this
output is called **reconstruction**, never **recovery** — the word
"recovery" would imply the original value was found, when it was in
fact synthesized under a stated assumption (even-spacing across the
bucket, anchored at the bucket's own start). The UI (§15) must always
show:

1. the original native values, unmodified, alongside the suggestion;
2. an explicit confidence level;
3. a required user confirmation before this becomes the active
   interpretation (never auto-applied, regardless of confidence level);
4. the phase-anchoring assumption in plain language when the user
   requests more detail (progressive disclosure — not in the compact
   summary).

**Sample-index fallback** for this exact scenario: if the user declines
the suggestion, or confidence is too low to offer one, or the user
simply prefers not to guess, Sample Index (§9) remains fully available
and preserves every row without alteration.

---

## 8. Manual interval / sampling-rate handling

The user may directly supply either:

```text
Sampling rate     (e.g. 20 Hz)
Sample interval   (e.g. 50 ms)
```

**Canonical internal value**: sample interval, in seconds, as a
floating-point value. Rationale: `TimingInformation`/`SamplingInformation`
(`app/domain/timing.py`) already express rate in Hz for
`SamplingInformation.sampling_rates`, but the actual per-sample
placement math downstream (`elapsed_start_seconds`/`elapsed_end_seconds`,
`disturbance_record.py:83-101`) is seconds-based throughout — storing
the user's own input as seconds-per-sample avoids a repeated Hz→seconds
conversion at every read site, while a rate is still trivially derived
for display or for populating `SamplingInformation` later (Slice 10's
own concern, not this one). Whichever unit the user actually types is
preserved as `user_specified` provenance metadata (so the UI can echo
back "20 Hz" rather than a converted "0.05 s" if that is what the user
typed) — only the INTERNAL working value is canonicalized, never the
user's own displayed input.

**Units are never silently inferred.** A bare numeric column (§9) always
requires an explicit unit choice from the user or a specific interpreter
decision recorded with `user_specified`/`reconstructed` provenance —
never a default assumption baked into the framework itself.

---

## 9. Sample-index fallback

Available at all times, not merely as a last resort — the user may
choose it directly even when a native/reconstructed interpretation
exists, if they prefer not to rely on it.

**Numeric elapsed-time units**: a plain numeric elapsed-time column is
ambiguous without an explicit unit. The framework defines an
open-ended (Principle 6) but presently-illustrated unit set:

```text
seconds
milliseconds
microseconds
nanoseconds
```

matching `TimingInformation.time_axis_unit`'s own existing (currently
dead — `app/domain/timing.py:44`, confirmed unused anywhere in
`backend/app` by direct inspection) field, which this framework is the
first real producer for. No default unit is ever assumed; the field
stays required whenever family `elapsed` is selected, until the user
picks one.

**Sample Index semantics** (directly from the task): when index
fallback is active, the ORIGINAL time column (if one existed at all —
some sources may have no time-like column whatsoever) is preserved as
source/provenance information, inspectable in the working preview
exactly like any other column (nothing about it changes — it simply
does not supply the active plotting basis). The active plotting basis
becomes the row's own sequential position: `1, 2, 3, 4, ...`.

**Consequences that must be documented to the user, not silently
implied**:

- No trustworthy real-time duration exists for this source.
- No trustworthy absolute or relative-seconds axis exists.
- No absolute synchronization with another source is possible (this is
  not a new limitation — it is exactly the existing, already-tested
  `elapsed_only` singleton-group behavior in
  `app.domain.time_grouping.derive_time_groups()`, confirmed by direct
  reading of that module: "every source whose `timing_reference !=
  "absolute"` always gets its own singleton, unaligned group").
- Any later feature that depends on a known, real sample interval
  (e.g. an accurate RMS window in physical units) may be unavailable or
  degraded for this source until real timing information is supplied —
  this framework never pretends index spacing equals seconds.

---

## 10. Multiple Time Axis columns

The `Time Axis` column role (Slice 5,
`app.domain.working_overlay.ROLE_TIME_AXIS`) already explicitly permits
more than one column to carry it simultaneously — verified directly:
Slice 5's own service layer performs no uniqueness check across
columns for this role (`app/services/working_overlay_service.py`'s
`set_column_role()` validates only role-set membership, never
cross-column exclusivity), and this was a deliberate Slice 5 design
choice ("do not assume the future time basis must always come from
exactly one physical column").

This design treats a **Time Axis Input Set** — the ordered tuple of
currently-selected `Time Axis` columns for one worksheet/source — as
the unit an interpreter actually receives, rather than a single column.
An interpreter declares which INPUT SHAPES it knows how to combine
(§17); the framework itself does not hard-code combination rules.

Illustrative (not exhaustive, per Principle 6) combinations:

```text
1 column   → a single absolute/elapsed/partial/index column
2 columns  → Date + Time (assembling one absolute value from two cells)
2 columns  → seconds + microseconds (assembling one elapsed value)
N columns  → any future split-field convention a later interpreter defines
```

**Selecting more Time Axis columns than any known interpreter can
combine is not an error.** It simply means no interpreter currently
claims that input shape, and the interpretation family for that
worksheet/source falls to `unknown` until either the user narrows the
selection or a future interpreter is added (Principle 6) that
understands it. This is never silently resolved by guessing which
column "really" matters.

---

## 11. Ambiguous / irregular timing cases

Represented as **diagnostics** — read-only findings surfaced to the
user — never silently repaired. This mirrors exactly how Slice 6's own
`PreparationIssue` model already works (informational findings about
current state, never auto-fixes, never raised as an exception) and is
expected to REUSE that same model rather than invent a second one (see
§13 for the precise boundary and why these are not YET issued as real
Slice 6 issues today).

At minimum, the framework must be able to represent all of the
following as distinct diagnostic conditions:

| Condition | What it means | What Powerwave does |
|---|---|---|
| Time goes backward | A later row's native time precedes an earlier row's | Flag; never reorder (Principle 3) |
| Timestamp reset | Time drops back to near-zero/near-start mid-file | Flag; never split into multiple sources automatically |
| Midnight rollover | A time-only column wraps past `23:59:59` back to `00:00:00` | Flag as a `partial`-family concern; never silently add a day without user confirmation |
| Large time gap | A much longer-than-typical interval between consecutive rows | Flag as a possible missing-sample region (§12); never insert a row |
| Non-uniform sampling | Intervals vary beyond what confidence (§6) supports | Lowers confidence; never forces a reconstruction |
| Repeated timestamps | Covered fully in §7 | — |
| Mixed time formats | Different rows appear to use different representations in the same column | Flag as `unknown`/needs-attention for the affected rows; never silently normalize |
| Ambiguous date locale | e.g. `03/04/2026` — DD/MM or MM/DD unclear | Flag; require explicit user confirmation of locale before treating as `absolute` |
| Missing timestamp | A blank cell in an otherwise time-bearing column | Governed by Principle 1 (a genuinely blank cell is fine as "missing," per the exact same blank-handling convention already used for column labels) — never fabricated |
| Time-only with no date | Covered fully as the `partial` family (§3) | — |

None of these conditions are validated or acted upon automatically.
They exist so a later Readiness Validator (§13) has something concrete
to consume, and so the compact Time Axis panel (§15) has something
honest to summarize ("Interpretation: repeated timestamps detected" is
literally this table's own first row, worded for the user).

**`[DONE, 2026-09-02]` Slice 8D implementation note**: every row of this
table now has a real, structured `TimeAxisDiagnostic` producer. Final
code, per row, and which interpreter(s) produce it:

| Table row | Final diagnostic code | Producer(s) |
|---|---|---|
| Time goes backward | `time_goes_backward` (new) / `elapsed_time_goes_backward` / `sample_index_goes_backward` (pre-existing) | `absolute_datetime`/`split_date_time` (new); `elapsed_numeric`/`sample_index` (Slice 8B, unchanged) |
| Timestamp reset | `timestamp_reset_suspected` (new) | `absolute_datetime`/`split_date_time` |
| Midnight rollover | `partial_midnight_rollover_suspected` (new) | `absolute_datetime`/`split_date_time`, `partial` family only |
| Large time gap | `large_time_gap` (new) | `absolute_datetime`/`split_date_time` |
| Non-uniform sampling | `non_uniform_interval` (new) / `non_uniform_elapsed_interval` (pre-existing) | `absolute_datetime`/`split_date_time` (new); `elapsed_numeric` (Slice 8B, unchanged) |
| Repeated timestamps | `repeated_timestamp_detected` (pre-existing, §7) | `repeated_timestamp_precision_loss` (Slice 8C, unchanged) |
| Mixed time formats | `mixed_datetime_format` (pre-existing) | `absolute_datetime`/`split_date_time` (Slice 8A, unchanged) |
| Ambiguous date locale | `ambiguous_date_order` (pre-existing) | `absolute_datetime`/`split_date_time` (Slice 8A, unchanged) |
| Missing timestamp | `missing_datetime_value` / `missing_elapsed_value` / `missing_sample_index` (pre-existing, one per family) | every interpreter (unchanged) |
| Time-only with no date | `time_only_not_absolute` (pre-existing) | `absolute_datetime` (Slice 8A, unchanged) |

Only FIVE codes were genuinely new — `absolute_datetime`/`split_date_time`
were this framework's one real gap (Slice 8B's elapsed/sample-index and
Slice 8C's own bucket cadence already checked backward/gap/non-uniform
conditions for their own families). Every other row already had an
established code from an earlier slice, reused verbatim per this
slice's own "prefer consolidation... do not rename existing public
codes unnecessarily" instruction.

**The exact detection rule** (deliberately simple, per this slice's own
"do not overengineer statistical detection" instruction): a resolved
row-to-row sequence (only ever computed once a format is ALREADY
resolved — never for a still-ambiguous or still-unparseable reading) is
walked once. The reference "expected local interval" is the SMALLEST
positive consecutive delta observed anywhere in the bounded sample —
deliberately the minimum, not the mean or median, since a large outlier
delta can never inflate its own comparison point this way, without a
second statistical pass. A transition at least 5× that reference is
"large" in either direction (`large_time_gap` forward,
`timestamp_reset_suspected` backward); anything smaller but still
negative is the plain `time_goes_backward`; a `partial`-family
transition from within 2 seconds of the end of the day to within 2
seconds of the start of the day is checked FIRST and reported as
`partial_midnight_rollover_suspected` instead, taking priority over
both — the exact "distinguish a likely reset from a small ordinary
irregularity" and "must NOT automatically be treated as generic
backward-time corruption" requirements this section's own table already
named. `non_uniform_interval` is a single, dataset-level finding (never
per-transition) for the softer case where the remaining ordinary
forward steps still vary by more than a ±20% tolerance of their own
median.

**Exact repeats (`delta == 0`) are deliberately never flagged by this
new logic** — `repeated_timestamp_precision_loss` (§7) already owns
that condition in full; duplicating even a bare presence check here
would be exactly the "duplicate the detection algorithm" this slice's
own task said not to do.

**All five new codes are `SEVERITY_WARNING`/`AMBIGUITY_UNAMBIGUOUS`** —
attention-worthy once present (via the existing `needs_attention`
path), never blocking `confirmed=true` (only `AMBIGUITY_AMBIGUOUS`
does that). No new `resolve_status()` precedence rule was needed for
this slice at all — "flag; never force a decision," this table's own
recurring wording, was already exactly what the framework's existing
severity/ambiguity axes express.

**Bounded, sample-based, never a full scan.** Every diagnostic this
slice adds is computed over the SAME already-bounded (≤50-row) sample
every interpreter here already receives — never a second, wider read of
the source. This means a genuinely large gap or a reset OUTSIDE the
sampled window is simply not seen; these are sample-based findings, not
full-dataset guarantees, exactly like every other diagnostic in this
framework since Slice 8A.

**A new, lightweight `category` axis** (`format`/`ordering`/`gap`/
`repeat`/`sampling`/`ambiguity`) is now available on every
`TimeAxisDiagnostic` — computed from `code` via
`app.domain.time_axis.diagnostic_category()`, never a stored field, so
no existing diagnostic construction anywhere needed to change.
Internal/UX grouping only; never mapped to `blocking`/`warning`/`info`
readiness severity (that mapping, if any, remains Slice 9's own
decision, per §13 below, untouched).

---

## 12. Non-empty ambiguous data-value preservation

This section formalizes Principle 1's own boundary with time
interpretation specifically, since the two interact directly (a
Waveform Channel column can contain `"ERR"` in the very row whose time
value is otherwise perfectly interpretable).

**The rule is column-role-agnostic.** Whether the ambiguous value sits
in a `Time Axis` column or a `Waveform Channel` column, the same
handling applies: preserve the exact original value, never coerce it,
and surface it as a diagnostic. A time interpreter that cannot parse
one cell in an otherwise-parseable Time-Axis column does not fail the
whole column — it flags that ONE row as unparseable/`unknown` for
timing purposes while leaving the value itself completely untouched
(consistent with `_apply_working_overlay`'s own existing per-row,
per-cell granularity, `app/services/preparation_preview_service.py`).

**The boundary this document draws explicitly** (directly requested by
the task):

```text
Time interpreter's own job:
    detect that a value is unparseable/ambiguous for time purposes
    record it as a diagnostic with its own location (row/column)
    NEVER decide whether this makes the dataset unacceptable

Readiness Validator's own future job (Slice 9, NOT this document):
    decide whether an ambiguous value is blocking for a given
    column role (e.g. "ERR" in a Waveform Channel may become a
    blocking finding once real severity policy exists;
    an occasional non-critical text value in a Metadata column
    may never be blocking at all)
```

No severity policy is decided here. This document only guarantees that
whatever the Readiness Validator eventually decides, it will have
complete, unmodified source values and complete diagnostic records to
decide from — never a version of the data that has already been
silently cleaned up on its behalf.

---

## 13. Diagnostics and readiness boundary

**Time-interpretation diagnostics are not yet Slice 6
`PreparationIssue`s.** This is a deliberate Slice 7 scope decision, not
an oversight: Slice 6's own production issue set
(`app/services/preparation_issue_service.py`) is currently a short,
closed, conservative list (`header_not_selected` /
`data_region_unconfigured`), all `info` severity, all derived from
CONFIGURATION state, never from data content. (A third code,
`column_roles_unassigned`, existed at the time this section was
written but was retired by a 2026-09-04 UAT fix — see
[DECISIONS.md — DEC-073](DECISIONS.md#dec-073--csvexcel-preparation-uses-only-three-column-roles-time-axis-waveform-and-not-assigned-not-assigned-is-the-default-and-is-omitted-from-cleaned-export) —
once the three-role column model made "Not Assigned" a normal,
intentional state rather than incomplete configuration.) A time-interpretation diagnostic (e.g. "repeated timestamps
detected," "possible missing sample") is derived from DATA CONTENT, a
qualitatively different and materially riskier thing to surface as a
severity-carrying finding before real readiness policy exists for it.

**Slice 7's own proposal**: time-interpretation diagnostics live in
their own result shape (`TimeAxisDiagnostics`, §17) returned alongside
the interpretation itself, consumed directly by the Time Axis panel
(§15). They are NOT injected into `GET .../issues`'s own
`PreparationIssueSummary` in Slice 7.

**Why this boundary, concretely**: `PreparationIssue.severity` already
has `blocking`/`warning` as real, modeled capabilities (Slice 6) that
this codebase has explicitly and repeatedly declined to exercise until
owner-approved validation semantics exist for them (Slice 6's own
module docstring: "never invents that something is blocking or a
warning without owner-approved validation semantics behind it"). A time
diagnostic is exactly the kind of finding a future Readiness Validator
will likely want to promote to `warning`/`blocking` — but deciding that
mapping now, inside a framework-only slice, would be scope creep this
document is specifically asked to avoid (see §19's own "no production
issue rules" non-goal). **When Slice 9 (Readiness Validator) is
actually scoped, whether/how time diagnostics feed into
`PreparationIssue` is exactly the kind of decision that document should
make explicitly** — flagged here as a genuinely open question (§21),
not resolved by this document.

**What IS shared today**: the transport shape. `TimeAxisDiagnostics`
should structurally resemble `PreparationIssue` closely enough
(severity-label, code, message, location, suggested action) that
promoting a subset of them into real `PreparationIssue`s later, once
Slice 9 policy exists, is a mechanical mapping rather than a redesign.

**`[DONE, 2026-09-02]` Slice 8D confirmation**: this boundary was
UNCHANGED by Slice 8D. Every new diagnostic (§11) was added to the SAME
`TimeAxisDiagnostic` list returned through the SAME existing
`GET`/`PUT .../time-axis` and dry-run `POST .../interpret` endpoints —
still never injected into `GET .../issues`'s own
`PreparationIssueSummary`, still never mapped to `blocking`/`warning`/
`info` AT THAT TIME. The new `category` field (§11's own implementation
note) added one more structurally-shared property (alongside severity-
label, code, message, location, suggested action) that a future
promotion mapping could reuse — it did not itself perform or authorize
any promotion.

**`[DONE, 2026-09-02]` Slice 9 resolution**: the promotion this section
(and §21's own open question 1) deferred is now real.
`app.services.readiness_service.collect_readiness_issues()` is the ONE
place a `TimeAxisDiagnostic.code` is mapped onto a real
`PreparationIssue` severity — reusing the diagnostic's OWN code,
message, location, `suggested_action`, and `details` VERBATIM (the
"structurally-shared property" this section always anticipated made
this a mechanical mapping, not a redesign, exactly as predicted).
Interpreters themselves still encode NO severity opinion of their own
-- `_BLOCKING_TIME_DIAGNOSTIC_CODES`/`_WARNING_TIME_DIAGNOSTIC_CODES`
in that module are the complete, explicit, reviewable POLICY table
(never scattered `if` statements inside a time interpreter). This
covers the DIAGNOSTIC-promotion half of readiness only; readiness also
independently validates full-active-region time-axis CELL values (a
different concern from any bounded-sample diagnostic) -- see
`docs/project-memory/CSV_EXCEL_INGESTION_ARCHITECTURE.md` item 9 for
the complete Slice 9 policy and implementation summary.

---

## 14. Absolute vs non-absolute semantics

Reuses `TimingInformation.timing_reference` (`app/domain/timing.py:43`)
**verbatim** — no new field, no parallel enum. This is not a
convenience choice; it is the ONLY way to satisfy Principle 6's own
explicit test ("new interpreters must be addable... without altering
`time_grouping.py`, `synchronization.py`, or any waveform-rendering
code" — `CSV_EXCEL_INGESTION_ARCHITECTURE.md §15`).

Mapping from this document's own semantic families (§3) to that
existing two-value signal, established as an explicit design table so
Slice 10 (canonical conversion, not this document's own scope) has an
unambiguous contract to implement against later:

| Family (§3) | Resulting `timing_reference` | Condition |
|---|---|---|
| `absolute` | `"absolute"` | ONLY when a real, defensible calendar date+time exists — never merely because the family label says "absolute"; see Principle 5 |
| `elapsed` | non-`"absolute"` (`"relative_elapsed"`, the value `time_grouping.py` already anticipates) | Always |
| `sample_index` | non-`"absolute"` | Always — an index has no calendar meaning regardless of any rate supplied |
| `partial` | non-`"absolute"` | Always, UNLESS the user explicitly supplies/confirms the missing component, at which point the result is reclassified as `absolute` going forward (a user action, never automatic — Principle 5's own "unless the engineer explicitly supplies a valid absolute anchor" clause) |
| `unknown` | non-`"absolute"` | Always |

**No fake anchor dates, ever** — restates Principle 5 in this specific
context: a `partial` (time-only) source is never silently promoted to
`absolute` by attaching today's date, the upload date, or any other
synthetic day boundary. The only path from `partial` to `absolute` is
an explicit user-supplied or user-confirmed date component, recorded
with `user_specified` (or `reconstructed`, if Powerwave suggested a
specific date and the user accepted it) provenance — never `native`,
since the date was never actually in the source.

**Reserved downstream vocabulary already exists and is honored, not
duplicated**: DEC-029 (`DECISIONS.md`) already reserves the names
**"Synthetic Elapsed Time"** and **"Sample Index"** in the waveform
workspace's own time-mode model, explicitly for "possible future
CSV/Excel timing work." This document's `elapsed`/`sample_index`
families are the producers those reserved waveform-side names are
waiting for — the actual wiring between them is Slice 10's own
canonical-conversion work, not this document's, but the naming is
confirmed consistent end-to-end today.

**`[DONE, 2026-09-03, Slice 10]`** the table above is now implemented
exactly as specified —
`app/services/preparation_conversion_service.py` produces
`timing_reference == "relative_elapsed"` for every `elapsed`/`partial`/
`sample_index` source, and `"absolute"` (with the real first
interpreted timestamp as `start_time`) only for a genuine `absolute`
source. One design point this document left open for Slice 10 to settle
is now decided: for `elapsed` family, **canonical waveform time
(`waveform_data["time"]`) is relative to the first ACTIVE sample**
(`canonical[i] = raw_elapsed[i] - raw_elapsed[0]`), never the raw
source offset verbatim — a source starting at elapsed `5.000s` produces
canonical `[0.0, 0.02, 0.04, ...]`, not `[5.0, 5.02, 5.04, ...]`. The
original non-zero source offset is NOT discarded — it is preserved
losslessly in `SourceMetadata.preparation_provenance
["source_time_offset_seconds"]`, so an engineer who needs the original
elapsed-time reference can still recover it, while every OTHER
canonical-time family (`absolute`, `partial`, `sample_index`) already
follows this exact same "relative to first active sample" convention
for consistency — a single uniform canonical-time rule across all four
convertible families, not a family-specific special case.

**`[DONE, 2026-09-03, Slice 11]`** integration finding directly
concerning this document's own §4/§14 "preserve timezone/offset
information when present" design intent: Slice 10 honestly preserving
a genuine timezone-aware `start_time` for an `absolute`-family source
(this document's own explicit requirement) exposed a PRE-EXISTING
downstream assumption in `app.domain.time_grouping`/`app.services.
calculated_channel_service` that every absolute source's `start_time`
shared the same naive/aware status — true only while COMTRADE (always
naive) was the sole absolute-time producer. Mixing a naive absolute
source with a genuinely timezone-aware one previously crashed Time
Group derivation (`TypeError`) and silently mis-computed cross-source
calculated-channel alignment (a server-timezone-dependent epoch). Fixed
in Slice 11 by normalizing awareness at the comparison boundary
(`app.domain.time_grouping.normalize_absolute_datetime()`) — never by
weakening this document's own "preserve the real offset" design intent,
and never by discarding or reinterpreting a genuinely declared
timezone. See
[CSV_EXCEL_INGESTION_ARCHITECTURE.md item 11](CSV_EXCEL_INGESTION_ARCHITECTURE.md#14-recommended-implementation-slices--owner-revised-sequence-dec-072-not-yet-authorized-to-begin)
for the full defect/fix account.

**`[DONE, 2026-09-03, Slice 12; SUPERSEDED 2026-09-04]`** cleaned data
export (`app.services.preparation_export_service`) originally did NOT
consume any of this document's own interpreted/reconstructed time
machinery for the exported table itself — a Time Axis column's CURRENT
WORKING value was exported verbatim, byte-for-byte identical to what
`preview_preparation_source()` already shows the user, never Slice 8's
own interpreted value and never Slice 8C's own reconstructed timestamp.
That was a deliberate Slice 12 scope limitation, not a permanent design
decision.

**`[DONE, 2026-09-04, DEC-074]`** A UAT enhancement ("Export the
Resolved/Configured Time Axis") supersedes the paragraph above: cleaned
export now DOES consume this document's own interpreted/reconstructed
time machinery directly — it re-calls the ALREADY-CONFIRMED
interpreter's own `build_preview_rows()` (the exact same Protocol
method Slice 10's own canonical conversion already calls) over the full
active region, and serializes exactly ONE standardized Time column from
the result: an ISO-8601 timestamp per row for `FAMILY_ABSOLUTE`
(`Time`), or fixed-precision seconds relative to the first active row
for every other resolved family (`Time (s)`) — including an ACCEPTED
Slice 8C reconstruction, which now exports its own resolved cadence,
never the original coarse timestamps. The original source Time Axis
column(s) no longer appear in the cleaned table at all (their values
are consumed to build the one configured column, not merely passed
through); the manifest's own new `exported_time` section records
`family`/`provenance`/`interpreter_id`/`date_order`/`interval_seconds`/
`export_representation`/`timezone_present`/`reconstructed` plus which
raw source column(s) it came from. Because there is now no honest
resolved Time column to build from an unconfigured/unresolved/`manual`
Time Axis, export gained the same "usable Time Axis + at least one
Waveform column" precondition Slice 10's own conversion already
enforces — see [DECISIONS.md — DEC-074](DECISIONS.md#dec-074--cleaned-export-serializes-the-resolvedconfigured-time-axis-a-standardized-timetime-s-column-not-the-original-source-time-axis-columns-a-usable-time-axis-plus-at-least-one-waveform-column-is-now-required-before-a-reusable-cleaned-export-can-be-produced)
for the full rationale. No new inference was introduced by this change
-- see `app.services.time_axis_normalization`'s own module docstring
for the shared parse/canonicalize helpers both this module and Slice 10
now use, so the two can never silently disagree about what a configured
Time Axis means.

---

## 15. UI/UX model

Follows the exact progressive-disclosure pattern already shipped for
Preparation Status and Structure (owner UAT refinement,
`frontend/index.html`'s own `wwDataPrepRenderIssues()`/
`wwDataPrepRenderStructureSummary()` + "Configure"/"View Issues" toggle
pattern) — summary first, full controls only on request, no new
interaction paradigm invented for this feature.

### 15.1 Compact default panel

A new "Time Axis" panel, positioned in the Data Preparation Workspace
alongside (not replacing) the existing Preparation Status and Structure
panels — same panel shell, same `.ww-data-prep-panel-header` pattern
already established.

Clean case (nothing to decide):

```text
TIME AXIS

Source           Column A
Interpretation   Absolute datetime
Status           Ready
```

Needs attention:

```text
TIME AXIS

Source           Column A
Interpretation   Repeated timestamps detected
Timing basis     Absolute, precision limited
Status           Review suggested

[Review]
```

Multi-column:

```text
TIME AXIS

Source           Columns A + B
Interpretation   Date + Time
Status           Ready
```

No Time Axis column selected at all (the common starting state):

```text
TIME AXIS

Source           Not selected
Status           Unconfigured

[Configure]
```

**Never exposed in this panel, at any disclosure level**: interpreter
IDs, registry names, parser class names, or any other internal
mechanism name. The user sees semantic families and plain-language
interpretation summaries only (§3's own family names, in Title Case,
e.g. "Absolute datetime," "Elapsed time," "Sample index" — never the
literal `ROLE_TIME_AXIS`/`absolute`/`elapsed` code-level strings).

### 15.2 Expanded review — context-specific only

The expanded view shows ONLY the controls relevant to the currently
detected/selected interpretation — never one large form covering every
possible family at once.

Repeated-timestamp review (§7's own worked case):

```text
TIME AXIS REVIEW

Detected pattern
5 samples per second (confidence: High)

Suggested interval
200 ms

Original        Suggested
13:14:01        13:14:01.000
13:14:01        13:14:01.200
...

[Accept Suggestion]   [Adjust]   [Use Sample Index]
```

Elapsed-time configuration:

```text
Interpret as:  Elapsed Time
Column:        [A]
Unit:          [milliseconds ▼]

[Apply]
```

Sample-index configuration:

```text
Interpret as:      Sample Index
Column:            [A]
Sampling rate:     [5000] Hz   (optional)

[Apply]
```

### 15.3 State model

A deliberately small user-facing state set (internal interpreter/
detection state may be richer, but the UI never exposes more than
this):

```text
Unconfigured      — no Time Axis column(s) selected yet
Detected          — Powerwave classified a family, no issue found
Review suggested  — a diagnostic exists and/or a reconstruction is offered
Confirmed         — the user has explicitly accepted the active interpretation
Needs attention   — a diagnostic exists that the user has not yet acted on
Index fallback    — Sample Index is the active basis
Unsupported       — the current column(s)/family combination has no interpreter (§10)
```

`Confirmed` and `Detected` may look identical when nothing was
ambiguous (§5's own "clean case" clause) — the state exists mainly to
let the compact panel say `Ready` truthfully once an explicit
acceptance has actually happened for anything that WAS ambiguous.

### 15.4 Visibility/collapse persistence

Identical policy to the existing Preparation Status/Structure panels:
frontend-only, session-scoped, reset to collapsed every time the Data
Preparation Workspace is (re)opened — never persisted server-side,
never a new backend field.

---

## 16. Preview model

Every reconstruction or user-entered conversion is shown against a
**bounded** sample before being applied — never a requirement to
materialize the whole dataset.

```text
Original            Interpreted
13:14:01             13:14:01.000
13:14:01             13:14:01.200
13:14:01             13:14:01.400
```

**Reuses the existing paged-preview mechanism, not a new one.** The
bounded window is exactly the CURRENTLY loaded preview page
(`app.services.preparation_preview_service`'s own `PreviewRow` list,
already capped at `PREVIEW_MAX_LIMIT` = 1000 rows) — the same rows
already on screen, with a parallel "interpreted" column computed
alongside them. This requires no new fetch, no new pagination model,
and no whole-file scan: if the interpretation-relevant rows (e.g. the
repeated-timestamp bucket) are not on the currently loaded page, the
existing "Go to Last Rows"-style navigation (owner-UAT refinement,
`wwDataPrepFetchPreview()`) is the same mechanism the user already
knows for moving to the region of interest before reviewing.

The preview computation itself is **read-only and disposable** — it
never mutates `PreparationSession.raw_bytes` or the Working Overlay
until the user explicitly clicks Accept/Apply (§5). Declining or
navigating away discards it with no residual state, matching the exact
same "cancel/Escape discards, never commits" convention already used
for cell click-to-edit (Slice 4, `wwDataPrepBeginCellEdit()`'s own
Escape handling).

**`[DONE, 2026-09-04, DEC-075]`** A SEPARATE, later enhancement ("Show
the Resolved/Configured Time Axis in Data Preview") adds a DIFFERENT
preview surface -- do not confuse the two. This §16 model is the Time
Axis PANEL's own bounded detect-preview ({original, interpreted} pairs,
shown only while reviewing a detection result before Save). DEC-075
instead adds a derived, read-only "Configured Time" COLUMN inside the
main Data Preparation Workspace TABLE itself (the raw/working row grid
Slice 3/4/5 already render), visible on every page once the Time Axis
is resolved -- not only during an active detect review. It answers a
different question ("what will Powerwave actually use for THIS row,
right now, on whichever page I'm looking at"), rather than "what would
this interpreter produce for a bounded sample I am currently
reviewing."

The two surfaces intentionally reuse the SAME underlying values where
they overlap (both are ultimately derived from the same confirmed
interpreter's own `build_preview_rows()` output, through the same
`app.services.time_axis_normalization` module), but compute them
differently: §16's own bounded-sample preview only ever looks at
`_TIME_AXIS_SAMPLE_LIMIT` (50) rows starting at the data region's own
start, while DEC-075's Data Preview column (`app.services.
time_axis_service.build_configured_time_values()`) processes the FULL
active region on every request -- required so a later preview PAGE's
own relative-seconds values stay anchored to the dataset's TRUE first
active row, never reset to zero merely because that page's own first
row is not the dataset's first row (a critical guardrail; see that
function's own docstring). See
[DECISIONS.md — DEC-075](DECISIONS.md#dec-075--data-preview-shows-a-read-only-derived-configured-time-column-once-the-time-axis-is-resolved-using-the-same-standardized-representation-and-normalization-semantics-as-cleaned-export-dec-074-and-canonical-conversion)
for the full decision.

---

## 17. Extensibility / interpreter registry concept

**Interpreter interface** (illustrative shape, not final code — Slice 7
will formalize the exact signatures):

```text
TimeAxisInterpreter
├── family: str                      — which semantic family (§3) this interpreter produces
├── accepts(input_columns_shape) -> bool
│                                     — does this interpreter know how to
│                                       combine the CURRENTLY selected Time
│                                       Axis Input Set (§10)?
├── detect(session, worksheet_index, sample_window) -> DetectionResult
│                                     — bounded-sample classification +
│                                       confidence (§6) + diagnostics (§11)
└── interpret(session, worksheet_index, config, page) -> list[InterpretedValue]
                                      — bounded-page interpretation only,
                                        never whole-dataset, mirroring every
                                        existing preview/preparation
                                        function's own paging discipline
```

**Registry**: a simple, explicit list of known interpreters (matching
`app.domain.working_overlay.KNOWN_COLUMN_ROLES`'s own "small, explicit
tuple, not a plugin-discovery mechanism" precedent) — no dynamic
plugin-loading infrastructure, no configuration file, no new
dependency. Adding an interpreter means adding one more entry to this
list plus its own module, exactly like adding a new column role would.

**Why this satisfies Principle 6/DEC-072 point 6 concretely**: every
interpreter communicates with the rest of the system through EXACTLY
two existing, already-stable surfaces —
`TimingInformation.timing_reference` (§14) and the bounded
`PreviewRow`/diagnostic shapes (§13/§16) this document defines once,
generically. Neither `time_grouping.py` nor `synchronization.py` nor
any waveform-rendering file needs to know an interpreter exists at all.

**Illustrative future interpreters (Principle 6 — not exhaustive, none
implemented here)**:

```text
Excel serial datetime (a numeric family requiring a specific epoch rule)
device-specific timestamp encodings
GPS week/seconds
epoch seconds / epoch milliseconds
custom split time fields beyond Date+Time (e.g. Day + Time-of-day + AM/PM flag)
new locale-specific date formats
```

Each would be added as one new interpreter registration, satisfying the
existing `family`/`accepts`/`detect`/`interpret` contract — no rewrite
of the Time Axis panel, the preview model, or the domain storage
location (§18) required.

---

## 18. Slice 7 scope — framework only

Proposed exact scope, consistent with
`CSV_EXCEL_INGESTION_ARCHITECTURE.md §14` item 7 ("Extensible time-axis
framework. Interpreter architecture; an explicit unknown/unsupported
path; no closed format list"):

**Included**:

1. **Domain model** — `app/domain/time_axis.py` (new module,
   mirroring `app/domain/working_overlay.py`'s own layering
   discipline: zero framework dependencies, pure dataclasses/functions
   only): the semantic-family constants (§3), provenance constants
   (§4), a `TimeAxisConfiguration` dataclass (family, the Time Axis
   Input Set of column indices, unit-or-rate, provenance, any
   user-confirmed override values), and a `TimeAxisDiagnostic`
   dataclass (§11/§13's own shape).
2. **Storage location**: `WorkingOverlay` gains
   `time_axis: dict[worksheet_index_or_None, TimeAxisConfiguration]`
   — the SAME sparse, per-worksheet-scoped dict pattern already used
   for `header_row`/`data_region` (Slice 5), participating in the
   exact same bounded undo/redo history and revision counter
   (`WorkingOperation`) with zero new mechanism, mirroring the
   data-region end-mode refinement's own proof that a new sub-state
   fits into the existing overlay for free.
3. **Interpreter interface + registry** (§17) — the contract only; no
   concrete interpreter beyond a minimal `unknown`/pass-through one
   needed to prove the registry mechanism works end-to-end.
4. **Interpretation result / diagnostics model** (§13) — computed live
   at preview-read time (matching Slice 6's own "derive live, no
   cache" convention, `app.services.preparation_issue_service`'s own
   module docstring reasoning applies identically here), never
   persisted beyond the overlay's own configuration.
5. **API**: extends the existing preparation-source API family the
   same minimal way Slice 5/6 each did — a
   `GET .../preparation-sources/{id}/time-axis` read endpoint
   (mirroring `GET .../issues`) plus `PUT`/`DELETE
   .../working/time-axis` mutation endpoints (mirroring
   `PUT`/`DELETE .../working/header`) — no new endpoint family, no new
   router.
6. **Compact Time Axis UI shell** (§15.1) plus the `Unconfigured` and
   `Unsupported` states fully working end-to-end — proving the
   progressive-disclosure shell and the "no interpreter claims this
   input shape" path, without yet having a real interpreter behind
   most of it.
7. **Explicit unknown/unsupported representation** — a Time Axis
   Input Set that no registered interpreter accepts must render as
   `Unsupported` cleanly (§15.3), never as an error, never as a crash,
   never as a silently-ignored selection.

**Explicitly excluded from Slice 7** (deferred to Slice 8 or later):
any concrete family-specific parsing/detection logic beyond the
minimal pass-through needed to prove the registry works; the
repeated-timestamp reconstruction algorithm and its confidence
computation (§6/§7); the expanded per-family review UI content (§15.2)
beyond a generic placeholder; promotion of diagnostics into
`PreparationIssue` (§13, deferred to Slice 9's own scope decision).

**`[DONE, 2026-09-01]` Implementation note**: built exactly as scoped
above, item-for-item, with two small naming/shape resolutions made
during implementation (both consistent with, not deviating from, this
section's own proposal): (a) item 3's "minimal `unknown`/pass-through"
interpreter became two concrete registry entries — `manual` (the
`pass_through` concept: stores whatever the user states, unconditional
`accepts()`) and `unsupported` (the universal fallback sentinel) —
since the task's own examples (`pass_through`/`unsupported`/`manual`)
read as alternative names for the same one non-parsing concept, not
three distinct interpreters; (b) the read endpoint
(`GET .../time-axis`) additionally echoes `unit`/`interval_seconds`/
`confirmed` verbatim from the stored `TimeAxisConfiguration` (not
listed explicitly above) so the frontend's own edit form can prefill
without a second, parallel "raw configuration" endpoint — a wire-level
convenience only, not a new calculated value. See
[CSV_EXCEL_INGESTION_ARCHITECTURE.md item 7](CSV_EXCEL_INGESTION_ARCHITECTURE.md#14-recommended-implementation-slices--owner-revised-sequence-dec-072-not-yet-authorized-to-begin)
for the full file-by-file/test-by-test implementation summary; this
document's own design content above is otherwise unchanged and remains
the authoritative reference for the shapes themselves.

---

## 19. Slice 8 scope — initial interpreters

Proposed exact scope, consistent with
`CSV_EXCEL_INGESTION_ARCHITECTURE.md §14` item 8 ("Initial time-axis
interpreters. The safest initial cases only"):

**Included** (the task's own "strong candidates," adopted as the
initial set):

1. **Single-column absolute datetime** — the most common, least
   ambiguous case; native `absolute` family, provenance `native` for
   the clean sub-case, feeding directly into `timing_reference =
   "absolute"` (§14).
2. **Date + Time (two columns)** — the first concrete multi-column
   Time Axis Input Set (§10), assembling one `absolute` value.
3. **Elapsed numeric time** — with the required explicit unit
   selection (§9), never a default unit.
4. **Sample index** — including the optional sampling-rate input
   (§8/§9).
5. **Repeated-timestamp / lost-precision detection** — the full §6/§7
   fallback hierarchy and confidence model, including the
   reconstruction suggestion, the required user confirmation, and the
   Sample Index fallback when declined.

**Deliberately NOT included in Slice 8** (later, illustrative-only per
Principle 6): Excel serial datetime, device-specific encodings, GPS
week/seconds, epoch seconds/milliseconds, custom multi-field splits
beyond Date+Time, additional locale formats — each remains a genuinely
future interpreter addition (§17), not a Slice 8 commitment.

**`[DONE, 2026-09-01]` Slice 8A implementation note**: items 1-2 above
(single-column absolute datetime, Date + Time) are implemented exactly
as scoped, as `absolute_datetime`/`split_date_time` in
`app.services.time_axis_interpreters`.

**`[DONE, 2026-09-04]` UAT fix — 2-digit years and actionable
parsing-failure wording**: owner UAT reported that a real source shape
(`3/6/26` + `18:04:00.000`, via Date + Time) produced a generic "50 of
50 sampled value(s) could not be parsed under a consistent format."
message with no actionable next step. Root cause, confirmed by direct
reproduction before any fix was written: `_DATE_PATTERNS_BY_ORDER` had
NO 2-digit-year (`%y`) candidate pattern at all for any order — only
4-digit-year (`%Y`) patterns, which `strptime` correctly refuses to
match against a bare 2-digit token like `"26"`. This was a missing-
format-family gap, not an ambiguity-detection bug and not a split-
date-time-specific bug -- every candidate order genuinely had zero
matches, so the case never even reached this section's own §6
ambiguity-by-elimination logic.

**Fix**: `_DATE_PATTERNS_BY_ORDER` gained `%d/%m/%y`/`%d-%m-%y`
(`dmy`) and `%m/%d/%y`/`%m-%d-%y` (`mdy`) candidates — deliberately
NOT added for `ymd` (a 2-digit-year-FIRST format is not among any
example this document or the owner ever gave, and would risk spurious
matches against unrelated short numeric sequences, e.g. a
`sample_index`-like column). The explicit, documented 2-digit-year
century rule for this application: **`00-69 -> 2000-2069`, `70-99 ->
1970-1999`** — Python's own native `%y` strptime inference is ALMOST
this rule (it pivots at 68/69: `00-68 -> 2000-2068`, `69-99 ->
1969-1999`, verified directly), differing at exactly one value (a
2-digit year of `69`); rather than silently defer to Python's own
slightly different pivot, `_parse_with_pattern()` applies one explicit
post-hoc correction (a parsed year of `1969` -- which `%y` only ever
produces from a literal `69` token -- is corrected to `2069`) so this
application's own stated boundary holds exactly. Every other 2-digit
value already agreed between the two conventions before this
correction.

With the fix, `3/6/26` + `18:04:00.000` now correctly reaches this
section's own existing `ambiguous_date_order` mechanism (BOTH `dmy` and
`mdy` are genuinely full matches for every sampled row) -- exactly the
outcome this document's own §6 already specifies for a genuinely
ambiguous non-ISO date, with ZERO new ambiguity mechanism introduced
(the EXISTING `date_order` resolution flow, already fully built in
Slice 8A/8B's own frontend UI, handles it automatically once the
backend produces the right diagnostic). Diagnostic wording was also
sharpened to distinguish the three user-facing states this task
introduced: a viable-but-undecided reading now reads "Date format needs
confirmation. The value \"X\" can be interpreted as Day/Month/Year or
Month/Day/Year. Choose the intended date order below." (never the
generic parse-failure wording); a genuinely unsupported reading now
reads "N of N sampled date/time value(s) could not be interpreted
using the supported formats. Review the examples below or choose a
different interpreter." and its own `TimeAxisDiagnostic.details`
gained a bounded (≤5) `examples` list of real `(row_number, value)`
pairs that failed to match the best-explaining candidate, so the UI can
show concrete failing rows rather than only a count — rendered by the
EXISTING diagnostics list in the Time Axis panel, purely additive, no
new panel. This fix stays entirely within Slice 8A's own already-
documented scope (no new interpreter, no new ambiguity mechanism, no
readiness-policy change), so `CSV_EXCEL_INGESTION_ARCHITECTURE.md` was
not touched. See `backend/tests/test_time_axis_interpreters.py::
TestTwoDigitYear` and `backend/tests/test_time_axis_service.py::
TestTwoDigitYearUatFixServiceLevel` for the regression coverage.

**`[DONE, 2026-09-04]` UAT fix — simplify the confirmation UX**: owner
UAT reported that a generic "☐ Confirmed" checkbox appeared under
EVERY sample-interpreter result -- including a plain, unambiguous
native reading such as `Detected: Absolute · Confidence: High ·
Format: DD/MM/YY` -- with no explanation of what was actually being
confirmed, and the checkbox was required even when nothing about the
interpretation was actually uncertain.

**Owner-approved policy**: `native + unambiguous -> no confirmation`;
`ambiguity resolved by an explicit user choice (date order, elapsed
unit, ...) -> that choice itself is sufficient confirmation, no second
checkbox`; `direct user-entered timing (manual interval/rate) -> the
input itself is sufficient confirmation`; `Powerwave-derived
reconstructed timing -> explicit acceptance is still required`, with
specific wording ("I confirm this reconstructed timing"), never the
generic word "Confirmed."

**Investigation finding (task's own explicit "inspect before changing
code" instruction)**: `app.domain.time_axis.resolve_status()` ALREADY
implements exactly this policy, verified directly against real
`set_time_axis_configuration()`/`build_issue_summary()` calls before
writing any code, not assumed:

- A native, unambiguous reading (`confirmed=False`) already reaches
  `STATUS_DETECTED` and `is_ready=True` -- confirmation was NEVER
  actually required for it at the backend level.
- An ambiguity resolved by an explicit `date_order` (or `unit`, for
  `elapsed_numeric`) that matches a genuinely valid candidate ALREADY
  drops the `ambiguous_date_order`/`missing_elapsed_unit` diagnostic
  entirely (see `detect_absolute_datetime()`'s own "the user's own
  explicit choice resolves what the data alone could not... no
  diagnostic is emitted for this outcome" branch) -- so
  `resolve_status()`'s rule 4 (which blocks ONLY while that diagnostic
  is present) never fires, and `confirmed=False` already reaches
  `is_ready=True`.
- Direct user-entered `sample_index`/`elapsed_numeric` timing
  (`provenance=user_specified`) is not gated on `confirmed` anywhere in
  `resolve_status()` at all -- it was already accepted immediately.
- `provenance == PROVENANCE_RECONSTRUCTED` (Slice 8C's own repeated-
  timestamp suggestion) is the ONLY route to `STATUS_REVIEW_REQUIRED`
  that `resolve_status()` actually gates on `confirmed` (its own rule
  5) -- confirmed by a direct before/after test:
  `confirmed=False` stays `review_required`/blocking,
  `confirmed=True` reaches `STATUS_CONFIRMED`/usable.

**Conclusion: this was a FRONTEND-ONLY defect.** Zero backend code was
changed -- the checkbox was simply shown unconditionally, regardless of
whether the backend's own already-correct policy actually needed it.
`frontend/index.html` gained one centralized rule,
`wwDataPrepTimeAxisRequiresExplicitConfirmation(detection)` (task's own
"one centralized semantic rule rather than scattered frontend
conditions" instruction), returning `detection.provenance ===
"reconstructed"` -- the SAME single condition `resolve_status()`'s own
rule 5 keys off of, mirrored rather than re-derived independently. The
confirmation control (`#wwDataPrepTimeAxisConfirmedField`) is hidden by
default and shown only when that rule is true, with its own label text
set to "I confirm this reconstructed timing" specifically for that
case; unchecked automatically whenever a NEW detection result no longer
needs it (never silently pre-accepting a suggestion the user has not
seen). The Manual interpreter (a separate, lower-level path where the
engineer can declare ANY provenance directly, including
`reconstructed`) deliberately keeps its own original, always-shown
generic "Confirmed" checkbox -- out of this fix's explicit scope (the
task concerns the 5 REAL/sample interpreters' own detection results),
and changing it was judged an unnecessary risk of a UX regression the
task never asked for.

Regression coverage locking in the (unchanged) backend policy:
`backend/tests/test_time_axis_service.py::TestConfirmationPolicy` (9
tests: native-unambiguous-without-confirmed, ambiguous-unresolved-
blocks, DMY/MDY-resolved-without-confirmed [parametrized], reconstructed-
without-confirmation-blocks, reconstructed-with-confirmation-usable,
user-entered-sample-index-interval-without-confirmed, user-entered-
elapsed-unit-without-confirmed, partial-family-native-without-
confirmed).

**`[DONE, 2026-09-02]` Slice 8B implementation note**: items 3-4 above
(elapsed numeric time, sample index) are ALSO implemented exactly as
scoped, as `elapsed_numeric`/`sample_index` in the SAME
`app.services.time_axis_interpreters` module, reusing the identical
interpreter contract Slice 8A established (no shape change beyond two
new optional `detect()`/`build_preview_rows()` parameters,
`requested_unit`/`requested_interval_seconds` — Slice 8A's own two
interpreters simply ignore both). Item 5 (repeated-timestamp/lost-
precision detection) remains NOT implemented — a future Slice 8C, per
this task's own explicit non-goals list (§20 below still applies to it
in full: no reconstruction algorithm, no confidence-gated suggestion,
no cadence inference exist anywhere in the current codebase).

Concrete choices made during the Slice 8B implementation, all
consistent with this section's own §8/§9 scope (none widen it):

- **No new top-level fields.** `TimeAxisConfiguration.unit`/
  `.interval_seconds` already existed since Slice 7 anticipating
  exactly this (§8's own "canonical internal value: sample interval, in
  seconds" and §9's own "the field stays required whenever family
  `elapsed` is selected" already named these two fields) — Slice 8B
  needed zero new `options` keys, zero new dataclass fields on
  `TimeAxisConfiguration` itself.
- **Missing unit reuses the SAME ambiguity mechanism as an unresolved
  date order.** An `elapsed_numeric` column with no unit chosen
  produces a NEW `missing_elapsed_unit` diagnostic with `ambiguity:
  "ambiguous"` — routing through `STATUS_REVIEW_REQUIRED` via the exact
  precedence rule Slice 8A already built for `ambiguous_date_order`, a
  second producer of one mechanism rather than a new status branch.
  `confirmed=true` is rejected server-side while it remains, exactly
  like an unresolved date order (§5's own "no silent engineering
  decision" rule, restated).
- **Sample index's own "no rate" state reuses Slice 7's own
  pre-existing `index_fallback` precedent verbatim.** `family=
  sample_index` + `provenance=index_only` already forced
  `STATUS_INDEX_FALLBACK` unconditionally since Slice 7 (built before
  any real interpreter existed to produce that combination) — Slice 8B
  needed no new domain-layer status logic at all for its own "approved
  fallback" case (§F).
- **Rate vs interval is a display choice, never a second stored value**
  (§I's own "do not maintain two conflicting authoritative values"
  instruction, taken literally): the frontend's own "Sampling rate
  (Hz)" input converts to `interval_seconds` client-side
  (`1 / rate_hz`) before ever reaching the backend; only
  `interval_seconds` is ever transmitted or stored. A stored
  configuration always redisplays as "Sample interval," never
  "Sampling rate" — the backend has no memory of which the user
  originally typed, by design.
- **Gap/backward/repeat detection compares only to the previous sampled
  value, in original row order** — never sorted, never a whole-column
  statistical pass. A gap is any consecutive positive delta `>1`; this
  is deliberately naive (no attempt to infer an expected step other
  than 1) since sample-index semantics (§E) never define a step other
  than "the next one."

**`[DONE, 2026-09-02]` Slice 8C implementation note**: item 5 above
(repeated-timestamp/precision-loss detection) is implemented exactly as
scoped in §7, as `repeated_timestamp_precision_loss` in the SAME
`app.services.time_axis_interpreters` module — the framework's fifth
and final §19 interpreter. No new top-level `TimeAxisConfiguration`/
`TimeAxisDetectionResult` fields were needed anywhere (`unit`/
`interval_seconds`/`options` already existed since Slice 7); the one
new interpreter-specific setting, `anchor_offset_seconds`, lives in the
pre-existing generic `options` bag.

Concrete choices made during the Slice 8C implementation, all
consistent with §7's own scope (none widen it):

- **Bucket analysis groups CONSECUTIVE identical native-timestamp rows
  only, in original row order** — never a full-dataset scan, never
  sorted (§7's own "computed only over the CURRENT bounded... window"
  rule, reused verbatim from the bounded-sampling architecture Slice
  8A/8B already built). Both `absolute` and `partial` (time-of-day)
  families are supported; `partial` never has a date invented for it.
- **First and last buckets never penalize confidence.** They may be
  truncated by the sample window's own edge, so only `interior_sizes =
  bucket_sizes[1:-1]` (excluding both ends) feeds the stability check —
  a sample that happens to start or end mid-bucket reads as no worse
  than one that doesn't.
- **The exact confidence rule** (§21's open question 2, now settled):
  HIGH requires at least 2 equal-sized interior buckets; MEDIUM covers
  either too few interior buckets to compare (but the buckets that do
  exist are fully consistent) or an interior spread of at most 1; LOW
  covers everything else, including fewer than 2 buckets total (no
  transition to measure at all). Confidence is always qualitative
  (High/Medium/Low) — never a percentage, per §6.
- **Interval estimation excludes the first bucket's own estimate.**
  Only the first bucket's row count can be a truncated undercount (the
  sample window may start mid-bucket); its own
  `span_to_next_bucket / bucket_size` estimate is excluded from the
  `statistics.median()` fed by every other transition, falling back to
  including it only when no other estimate exists at all.
- **Reconstruction offered is a genuinely SEPARATE `review_required`
  trigger from ambiguity, not a reuse of it.** Marking the "a
  reconstruction is offered" diagnostic as `ambiguity: "ambiguous"`
  (Slice 8A's own mechanism) would have made an accepted reconstruction
  permanently unconfirmable, since the diagnostic disclosing the
  suggestion is always present alongside it. Instead,
  `provenance == PROVENANCE_RECONSTRUCTED` is its own new
  `resolve_status()` precedence rule that ALSO routes to
  `STATUS_REVIEW_REQUIRED` while unconfirmed, but does not block
  `confirmed=true` from succeeding — directly implementing §15.3's "a
  diagnostic exists AND/OR a reconstruction is offered" wording as two
  independent triggers for the same status value.
- **A NEW diagnostic severity, `SEVERITY_INFO`, distinguishes always-
  true disclosure notes from real data-quality warnings.** Slice 8C is
  the first producer of purely informational diagnostics
  (`repeated_timestamp_detected`, `anchor_assumption_required` — the
  §7-mandated anchor disclosure); the framework's own pre-existing
  `if diagnostics: needs_attention` rule was unconditional on
  `confirmed`, which would have permanently prevented any confirmed
  reconstruction from ever reaching `STATUS_CONFIRMED`. Fixed by a
  `_has_attention_worthy_diagnostic()` filter
  (`severity_hint != SEVERITY_INFO`) — 100% backward compatible, since
  no diagnostic before Slice 8C ever used `SEVERITY_INFO`. A genuine
  `SEVERITY_WARNING` (e.g. `inconsistent_bucket_count`,
  `unexpected_bucket_sample_count`) still surfaces as
  `needs_attention` even after confirmation, exactly like every other
  interpreter's own "confirmed never suppresses a real warning" rule.
- **The anchor assumption is always disclosed, never implicit** (§7
  point 4): `anchor_assumption_required` names the default explicitly
  ("first sample in each bucket aligns with the displayed timestamp,
  unless adjusted") on every reconstruction, and `options.anchor_offset_seconds`
  (default 0) lets the user shift it — reusing the framework's existing
  generic `options` bag, never a new top-level field.
- **A manual interval/rate override is `provenance=user_specified`,
  never `reconstructed`** — the same provenance Slice 8B's own manual
  Sample Index interval uses, since a value the user typed in is
  decisive, not inferred. Missing/extra-sample diagnostics
  (`possible_missing_sample`, `unexpected_bucket_sample_count`) are
  still computed and attached even under a manual override, since they
  describe genuine facts about the underlying data independent of
  which interval the user chose to apply.
- **Missing/extra-sample bucket-count anomalies are diagnostics only**
  — never insert, delete, or reorder a row (the framework's own
  preservation guarantee, restated for this interpreter specifically).
- **Variable/unstable cadence is explicitly deferred, not silently
  guessed at.** A bucket-size pattern with no reliable transition
  (fewer than 2 comparable buckets, or an interior spread too wide to
  trust ANY suggestion) reports `cadence_not_reliable`
  (`ambiguity: "ambiguous"`) instead of a segmented/piecewise
  reconstruction — `confirmed=true` is rejected server-side while it
  remains, and Sample Index (§7's own documented fallback) stays fully
  available.
- **Midnight rollover for a `partial` family is left unaddressed, not
  misclassified.** A `23:59:59` → `00:00:00` transition is not treated
  as ordinary backward-time corruption and no date is fabricated to
  resolve it; full rollover inference is out of scope for this slice,
  matching §7's own "never invent a date for partial" rule taken to its
  logical edge case.

Concrete choices made during implementation, all consistent with this
section's own scope (none widen it):

- **Deterministic, not fuzzy.** A small, explicit `datetime.strptime`
  pattern table per date order (`dmy`/`mdy`/`ymd`) plus
  `datetime.fromisoformat`'s own ISO-8601 fast path (Python 3.13 --
  handles the space/`T` separator, fractional seconds, and a trailing
  `Z`/`±HH:MM` offset natively) -- no `dateutil`/free-form parsing
  anywhere, per §2's own "controlled parsing strategy" principle,
  restated explicitly by the Slice 8A task itself.
- **Ambiguity resolved by elimination first, by the user second.**
  Every known date order is tried against the WHOLE bounded sample;
  `strptime` already rejects an invalid calendar date, so a day value
  over 12 alone resolves `31/08/2026` to `dmy` with `native` provenance
  and no diagnostic at all -- only when 2+ orders validly parse the
  ENTIRE sample does the `ambiguous_date_order` diagnostic fire and
  `STATUS_REVIEW_REQUIRED` (§15.3, reserved since Slice 7, now real)
  apply. `set_time_axis_configuration()` rejects `confirmed=true`
  outright while that diagnostic is present -- §5's own "no silent
  engineering decision" rule enforced at the API boundary, not only in
  UI copy.
- **A NEW `ambiguity` axis, separate from confidence** (§6's own
  vocabulary untouched): `unambiguous`/`ambiguous`/`invalid` on
  `TimeAxisDiagnostic` answers "could a reasonable person read this
  differently," while `confidence` (§6) still answers "how much
  evidence supports this reading" -- the two were kept deliberately
  distinct rather than overloading confidence's own three-level bucket
  to also carry ambiguity.
- **Bare time-of-day stays `partial`.** A single-column interpreter
  given only time-of-day values (no date component at all) reports
  `family=partial` with a `time_only_not_absolute` diagnostic --
  §3's own "family is a classification of the SOURCE representation"
  rule applied literally: the interpreter reports the TRUE family even
  though its own name is "Absolute Datetime."
- **Preview reuses a fresh bounded sample, not the currently-loaded
  page.** §16 suggested reusing whatever preview page the frontend
  already has loaded; Slice 8A's own task spec explicitly listed "an
  explicit reasonable cap" as an equally acceptable alternative (its
  own §H) and this was chosen instead, for a preview/detection result
  that never depends on unrelated pagination state -- capped at 50
  sample rows for detection, 20 formatted rows in the dry-run preview
  response.

**`[DONE, 2026-09-05, DEC-081]` Enhancement — minute-resolution
24-hour time, explicit AM/PM hour-only time, and fixed-duration
elapsed units**: an investigation task ("CSV/Excel Absolute Datetime
Format Coverage") found `_TIME_PATTERNS` had no `%H:%M` (24-hour,
minute-resolution) candidate at all -- an asymmetry, since the 12-hour
minute-only form (`%I:%M %p`) already worked -- reproducing a real
reported bug (`"3/6/2026 17:25"` unparseable). The same investigation
found `KNOWN_ELAPSED_UNITS` supported only seconds/milliseconds/
microseconds/nanoseconds, with no fixed-duration minutes/hours/days/
weeks, despite the conversion mechanism (`_ELAPSED_UNIT_SECONDS_
FACTOR`, a flat unit->seconds multiplier dict) trivially supporting
them.

**Owner-approved scope** (see DEC-081 for the full boundary): added
`%H:%M` and explicit AM/PM hour-only (`%I %p`/`%I%p`) to the SAME
shared `_TIME_PATTERNS` table this section's own "one table, two
interpreters" design already established (§10's split Date+Time reuses
it unchanged); added `minutes`/`hours`/`days`/`weeks` to
`KNOWN_ELAPSED_UNITS` and their fixed multipliers (60/3600/86400/
604800) to `_ELAPSED_UNIT_SECONDS_FACTOR`. Explicitly NOT added: bare
24-hour hour-only (a lone `%H` pattern, judged too permissive without
further design), absolute date-only/day-only/week-only/month-only/
year-only support, and elapsed `months`/`years` (structurally excluded
-- no fixed-seconds factor exists for a calendar-variable unit, and
this interpreter's own "never invent an anchor date" contract means it
has no calendar reference such a unit could be resolved against
anyway). The existing ISO-8601 reduced-precision fast-path gap (§6's
own `_parse_iso()` accepting date-only/week-only/hour-only ISO strings
via Python 3.13's `datetime.fromisoformat()` with no diagnostic) was
confirmed still present and UNCHANGED -- only the DMY/MDY/YMD pattern
tables were touched, never that separate ISO fast-path.

**Safety proof**: `strptime`'s full-string-match strictness (verified
directly -- `strptime("17:25:30", "%H:%M")` and `strptime("1:00 pm",
"%I%p")` both raise `ValueError`) means the new, less-specific patterns
can never shadow a string that should match a more-specific existing
pattern; full-second, fractional-second, and 12-hour-with-minutes
values are provably unaffected. §6's own ambiguity-by-elimination
`date_order` policy is completely unchanged -- confirmed empirically
that which TIME pattern matches is orthogonal to date-order resolution
(a minute-resolution `"3/6/2026 17:25"` still requires an explicit
`date_order` choice exactly as a full-second value would).

55 new tests added (backend: 3039 -> 3094 passed). See DEC-081 for the
full files-changed/validation summary.

---

## 20. Explicit non-goals

Confirmed NOT part of this document, and not to be implemented as a
side effect of any future slice claiming to merely "follow this
design":

```text
time interpreters (concrete parsing/detection code)
timestamp parsing
reconstruction algorithm implementation
sampling-rate inference implementation
readiness validator
new production preparation-issue rules
DisturbanceRecord conversion
CSV/Excel waveform plotting
export
automatic row repair
data interpolation
synthetic waveform values
sample insertion
```

This document is design and documentation only. No source file under
`backend/app/` or `frontend/` is modified by this task.

---

## 21. Open questions / future decisions

Genuinely unresolved matters this document deliberately does NOT
settle, each requiring its own future owner decision at the point the
relevant slice is actually scoped:

1. **`[RESOLVED, 2026-09-02, Slice 9]`** ~~Whether/how time-
   interpretation diagnostics eventually feed into `PreparationIssue`~~
   — see §13's own Slice 9 resolution note above:
   `app.services.readiness_service`'s explicit
   `_BLOCKING_TIME_DIAGNOSTIC_CODES`/`_WARNING_TIME_DIAGNOSTIC_CODES`
   mapping table, and `docs/project-memory/CSV_EXCEL_INGESTION_
   ARCHITECTURE.md` item 9 for the complete policy.
2. **`[RESOLVED, 2026-09-02, Slice 8C]`** ~~The exact confidence-bucket
   computation (§6) is left to whichever interpreter implements
   repeated-timestamp detection in Slice 8~~ — see the Slice 8C
   implementation note above (§19) for the final HIGH/MEDIUM/LOW rule
   (interior-bucket stability, first/last buckets excluded).
3. **Whether a `partial`-family time-only column, once a date is
   user-confirmed, should be stored as a NEW `TimeAxisConfiguration`
   entry or as an evolution of the existing one** (i.e. does
   reclassifying `partial → absolute` count as the "same" time-axis
   configuration for undo/redo purposes, or a distinct operation?) —
   an implementation-level modeling question best resolved once Slice 7
   is actually being written against real code, not abstractly here.
4. **Exact API request/response field names** for
   `TimeAxisConfiguration`/`TimeAxisDiagnostic` (§18) — this document
   fixes the CONCEPTS and the storage/undo-redo/API-shape PATTERN
   (mirroring Slice 5 exactly), not final JSON field names, consistent
   with how prior slices' own exact schemas were only finalized during
   their own implementation, not during the architecture audit that
   preceded them.
5. **Whether the interpreter registry ever needs to become genuinely
   pluggable** (vs. the explicit small-list approach proposed in §17)
   — deferred until a real need for third-party/runtime-configurable
   interpreters materializes; no evidence for that need exists today.

This registry follows the exact same `[DECISION MODE: ...]` convention
already used in `CSV_EXCEL_INGESTION_ARCHITECTURE.md §18` — items above
are `[DECISION MODE: ANALYSIS]` (item 1, once Slice 9 is scoped),
`[DECISION MODE: ANALYSIS]` (items 2–4, once Slice 7/8 implementation
actually begins), and `[DECISION MODE: DEFER]` (item 5).
