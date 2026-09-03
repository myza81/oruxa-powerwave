# CSV/Excel Ingestion Architecture — Audit & Design Validation

Status: **AUDIT COMPLETE; SIX ARCHITECTURAL CLARIFICATIONS OWNER-APPROVED
(DEC-072); IMPLEMENTATION NOT YET AUTHORIZED**. This document records what
was found by inspecting the current `oruxa_powerwave` codebase and the
legacy `powerwave` reference against the owner-approved high-level
principles for a future CSV/Excel Data Preparation + Validation ingestion
layer, plus the six follow-up architectural decisions the owner has since
approved to close this audit's own open items (see §2A). It is a
discovery/design-validation record plus a decision cross-reference, not
itself an implementation specification — see [README.md — How facts,
decisions, and proposals are
distinguished](README.md#how-facts-decisions-and-proposals-are-distinguished).
Nothing in this document authorizes a code change. Cross-references:
[CURRENT_STATE.md — Current next workstream](CURRENT_STATE.md#current-next-workstream),
[DECISIONS.md — DEC-014](DECISIONS.md#dec-014--phase-1-is-comtrade-only-csvexcel-and-import-wizard-grade-timestamp-handling-are-deferred-to-phase-15),
[DECISIONS.md — DEC-057](DECISIONS.md#dec-057--timestamp-based-initial-alignment-and-time-groups-comtrade-sources-now-place-themselves-automatically-from-their-own-recorded-start-timestamps-and-a-waveform-panel-only-ever-mixes-sources-that-share-a-defensible-time-relationship),
[DECISIONS.md — DEC-072](DECISIONS.md#dec-072--csv-excel-ingestion-six-architectural-clarifications-approved--temporary-preparation-state-retention-preparation-scoped-severity-model-hybrid-rawworking-overlay-architecture-deferred-disturbancerecord-hardening-honest-non-absolute-time-preservation-and-an-open-ended-time-axis-format-list),
[POWERWAVE_DISCOVERY.md](POWERWAVE_DISCOVERY.md),
[PER_UNIT_MEASUREMENT_MODEL.md](PER_UNIT_MEASUREMENT_MODEL.md).

Audit date: 2026-08-30. Governance note: `git fetch origin` failed in the
auditing environment (no SSH publickey configured there) — the local
`main` clone's currency with GitHub could not be re-verified live during
this audit; the local tree was clean and consistent with its own last
recorded sync. This is disclosed per
[README.md's fetch/verify convention](README.md#before-relying-on-local-project-memory-documents),
not silently worked around.

---

## 1. Owner-approved principles this audit was asked to validate

Recorded here for reference, not reproduced in full — see the original
audit task for verbatim wording. Summarized:

1. Original source (CSV/XLSX) is immutable.
2. Three distinct states: Raw Data → Working Dataset (non-destructive,
   user-editable) → Powerwave Dataset (post-normalization/validation).
3. Non-destructive preparation — corrections are represented as an
   overlay/operation, not a mutation of raw values.
4. A Data Preparation Workspace sits between upload and the normal
   waveform workspace; CSV/Excel is not plotted immediately on upload.
5. Existing Powerwave waveform/synchronization/calculated-channel/PU
   behavior is not redesigned to accommodate malformed CSV/Excel — the
   ingestion layer adapts to Powerwave, never the reverse.
6. A strict Powerwave Readiness Gate blocks non-compliant data, with an
   eventual blocking/warning/informational distinction.
7. No silent engineering-data repair — ambiguous/invalid data is
   surfaced, never silently invented.
8. Excel sheets remain independent (no automatic merging) initially.
9. Column roles are broader than waveform/no-waveform (Time Axis /
   Waveform Channel / Metadata / Quality-Status / Ignore / Unknown).
10. Time-axis formats are treated as an open, extensible set, not a
    closed enumeration.

**`[FACT]`, verified this session**: none of principles 1–10 conflict
with the current codebase. §4 below explains why.

---

## 2. Executive conclusion

**`[FACT]`** Compatible with minor, well-defined additions. No existing
architecture must be redesigned. The current codebase already has:

- a provider abstraction (`app.providers.base.BaseProvider`) that is
  already format-agnostic and already produces one normalized contract
  (`DisturbanceRecord`) regardless of source format;
- a Time Group model (`app.domain.time_grouping`) that was *already
  built* anticipating a non-absolute-timestamp source (an "elapsed-only"
  source always gets its own solo, unaligned group — never guessed at)
  and is simply not reachable yet because no importer other than
  COMTRADE (always `timing_reference="absolute"`) exists;
- dormant, explicitly-reserved forward-compatibility fields on the
  analog-channel model (`parameter_type`, `waveform_form`) that a CSV/
  Excel importer is the intended first consumer of;
- an in-memory "one sibling registry per lifecycle stage" pattern
  (seven such registries already exist) that a new raw/working-dataset
  stage would extend unchanged.

**`[FACT]`** Two genuine architectural gaps exist, not merely unbuilt
features:

1. **No severity concept anywhere in validation.** Every current
   validation outcome is a hard-blocking `ImportServiceError` subclass
   (`app/services/errors.py`) mapped to an HTTP status. A "Powerwave
   Readiness Validator" that must distinguish blocking/warning/
   informational issues (principle 6) is new architecture to design, not
   an extension of an existing mechanism.
2. **`time`-column monotonicity/finiteness is required everywhere
   downstream but enforced nowhere.** This has never mattered before
   because COMTRADE's own parser guarantees it by construction. A CSV/
   Excel importer is the first thing in this codebase that could
   actually violate it, and nothing currently guards against that (see
   §5).

---

## 2A. Owner decisions recorded (2026-08-30) — see DEC-072

**`[OWNER DECISION]`** The three items this audit originally raised as
requiring owner input (§12, original items 1–3), plus three further
principles the owner chose to formalize explicitly, are now approved —
see [DECISIONS.md — DEC-072](DECISIONS.md#dec-072--csv-excel-ingestion-six-architectural-clarifications-approved--temporary-preparation-state-retention-preparation-scoped-severity-model-hybrid-rawworking-overlay-architecture-deferred-disturbancerecord-hardening-honest-non-absolute-time-preservation-and-an-open-ended-time-axis-format-list)
for the full text. Summarized (not duplicated in full — DEC-072 is
authoritative):

1. **Temporary preparation-state retention is permitted; durable
   retention is not.** Does not reopen DEC-015 — see the addendum added
   to DEC-015 itself.
2. **A preparation-scoped severity model is approved, not a redesign of
   the application's error taxonomy.** `ImportServiceError` is unchanged;
   a new, separate "preparation/readiness issue" concept
   (blocking/warning/info) applies only within the CSV/Excel
   preparation/readiness domain. Exact shape not yet approved.
3. **Raw/working architecture is a hybrid, reference-holding
   "preparation session," never full raw+working duplication.** The
   concrete storage mechanism remains open.
4. **`DisturbanceRecord.validate()` hardening is deferred, not the first
   CSV/Excel production change.** Time validity is enforced first by the
   preparation/readiness gate.
5. **Non-absolute time must be preserved honestly, never fabricated** —
   no sentinel-anchor fallback, ever.
6. **The time-axis format list stays permanently open-ended** — no
   closed enumeration may be introduced by future work.

This resolves this document's original §12 items 1–3 and formalizes
§15/§16/§17's existing findings as binding guardrails rather than
proposals. Every section below that these decisions touch has been
annotated accordingly, in place, without deleting the original
audit-time analysis — see [README.md's conflict-resolution
rules](README.md#conflict-resolution-rules) on why the historical record
is preserved rather than rewritten.

---

## 3. Current ingestion flow (COMTRADE) — the seam a CSV/Excel provider reuses

```
Frontend upload modal (RECORDING_FORMATS-driven)
  frontend/index.html:4887-4903  -- csv/excel already listed, enabled:false
  frontend/index.html:5465-5541  -- submit handler hardcoded to
                                     format.id === "comtrade" at :5481
        |  POST multipart (cfg_file, dat_file)
        v
backend/app/api/v1/sources.py:138            upload_comtrade_source()
        v
backend/app/services/import_service.py:101   import_comtrade_source()
  -- bytes written to a throwaway tempdir, provider called, tempdir
     always removed (context manager) -- DEC-015 unaffected
        v
backend/app/providers/comtrade.py            ComtradeProvider(BaseProvider).load()
  -- parse-or-raise only; zero repair layer for any malformed value
        v
backend/app/domain/disturbance_record.py     DisturbanceRecord (format-agnostic)
        v
import_service._build_source_metadata()  ->  app/domain/source.py
                                              SourceMetadata + ActiveSource
        v
backend/app/services/workspace_registry.py   WorkspaceRegistry
  -- in-memory only, keyed (workspace_id, source_id), no TTL
        v
backend/app/services/waveform_service.py     per-channel, per-range,
                                              adaptively-resolved extraction
        v
frontend wwFetchChannelRange() (index.html:9906)
  -> GET .../sources/{id}/waveform?channel_name=...&start_time=...&
         end_time=...&point_budget=...&unit_mode=...
        v
Plotly, one instance per panel (frontend/index.html:7216-7295)
```

`app.providers.base.BaseProvider` (`backend/app/providers/base.py:34`) is
an already-generalized two-method contract:

```python
class BaseProvider(ABC):
    def can_load(self, path: Path) -> bool: ...
    def load(self, path: Path) -> DisturbanceRecord: ...
```

**`[FACT]`** A `CsvProvider`/`ExcelProvider` would register into the same
`ProviderRegistry` (`providers/base.py:52`) and must produce the same
`DisturbanceRecord` — no change to this abstraction is required.

---

## 4. Current Powerwave waveform contract

`DisturbanceRecord` (`backend/app/domain/disturbance_record.py:37`) is
the single format-agnostic contract every provider must satisfy.

| Field / assumption | Status | Evidence |
|---|---|---|
| `waveform_data["time"]` — finite, ascending float seconds | **Mandatory in practice, unenforced in code** | `validate()` (line 103) never checks it. `waveform_service.py:183-187`'s own comment: *"searchsorted requires ascending order, which every COMTRADE record's time column satisfies by construction... not re-validated here."* Every `np.searchsorted` call site (`event_detection.py`, `rms_detector.py`, `calculated_channel.py`, `synchronization_service.py`, `waveform_service.py`) trusts this silently. |
| One DataFrame column per declared channel name | Mandatory, checked | `validate()` lines 114–125 |
| `sampling_info.sampling_rates`/`samples_per_rate` non-empty, equal length | Mandatory, checked | `validate()` lines 127–134 |
| `timing_info.start_time`/`trigger_time`, `trigger_time >= start_time` | Mandatory, checked | `validate()` line 136; both fields are non-`None` `datetime` on `TimingInformation` (`domain/timing.py:29`) — an importer with no real timestamp must still supply *some* concrete `datetime` |
| `timing_reference` | Effectively mandatory | Only the literal `"absolute"` is treated specially by Time Group derivation (`domain/time_grouping.py:141`); any other value (not necessarily the literal string `"relative_elapsed"`) is treated as elapsed-only |
| Analog channel `unit`, `parameter_type`, `waveform_form` | Optional, explicitly reserved for CSV/Excel | `domain/source.py:39-45`, `domain/channel_classification.py:16-18,66-73` — comments state COMTRADE never sets these |
| `timing_info.time_axis_unit` | **Dead field** | Declared (`domain/timing.py:44`) but never read anywhere in `backend/app`, and not even copied onto `SourceMetadata`/`TimebaseOut` — unlike `parameter_type`/`waveform_form`, this is not a live reserved hook today |
| Sample-index time axis | **Not represented at all** | No concept anywhere in `TimingInformation`/`SamplingInformation`. A sample-index-only source would need its `"time"` column synthesized as `index / assumed_rate` before it can even enter this contract — an engineering judgment call the Data Preparation Workspace must make explicit to the user, never silently. |
| Digital channel values | Mandatory 0/1 ints | `extract_digital_waveform` (`waveform_service.py:829`) does `int(values_full[i])` |
| Multi-input calculated-channel timebase | Mandatory, strictly enforced, **no resampling ever** | `domain/calculated_channel.py:412` `timebases_aligned()`: two channels combine only if they share one `reference_source_id`, or their absolute instants (`start_time + elapsed`) match within 1e-9s |

**`[PROPOSAL]`, not approved**: the concrete answer to this audit's key
question — *what canonical dataset must the CSV/Excel preparation system
produce* — is: a valid `DisturbanceRecord` satisfying every row of the
table above, with an honest (not fabricated) `timing_reference` and
`start_time`. Once produced, it needs zero special-casing anywhere
downstream — `import_service`, `WorkspaceRegistry`, `waveform_service`,
Time Groups, measurement groups, and calculated channels all already
operate on `DisturbanceRecord`/`SourceMetadata`, not on `provider_type`.

---

## 5. Current time-axis model

```
source native "time" (never altered)
   |
timestamp_placement_offset_s   (domain/time_grouping.py -- derived from
   |                             each source's own recorded start_time)
   |
manual_alignment_offset_s      (domain/synchronization.py -- the
   |                             engineer's Synchronise Sources correction)
   v
effective_alignment_offset_s = the two composed, never stored combined
   |
workspace_time
   |  - t0_workspace_time
   v
event_time
```

**`[FACT]`**:

- **Time Groups** (`domain/time_grouping.py:205` `derive_time_groups()`):
  every `recorded_absolute` source's interval
  `[start_time, start_time+duration]` groups by transitive overlap
  (union-find over pairwise overlap edges). Every source whose
  `timing_reference != "absolute"` **always** gets its own singleton,
  unaligned group — never auto-merged with anything, even another
  elapsed-only source (lines 70–73 of that module). This rule already
  exists, is tested, and is exactly what a real-timestamp-free CSV file
  needs; it is simply unreachable today because no importer other than
  COMTRADE exists (`CURRENT_STATE.md` confirms this directly).
- **No sample-index or elapsed-unit-labeling concept exists** in the
  current contract (see §4).
- **RMS/event-detection is already sampling-rate-agnostic**:
  `domain/event_detection.py`'s own docstring (lines 20–23) states its
  RMS engine is "already proven correct for both uniformly-sampled AND
  genuinely irregular/multi-rate time arrays" — favorable for irregular
  CSV timestamps, provided the `time` column itself is valid.
- **The one hard rule genuinely in tension with CSV data**: multi-input
  calculated channels (§4's last row) will routinely reject a CSV
  channel combined with a channel from a different source/file, because
  irregular/approximate timestamps essentially never satisfy the
  1e-9s absolute-instant-match requirement. **This is architecture
  working as intended (principle 5 — never weaken it to admit CSV),
  not a defect** — but it needs clear user-facing explanation in the
  eventual UI, not a silent rejection.

---

## 6. Existing validation model

**`[FACT]`** Centralized, structured, but strictly binary — no severity
levels exist anywhere in the backend. Every validation outcome is a
subclass of `ImportServiceError` (`backend/app/services/errors.py`, ~50
subclasses across every feature area — imports, waveform extraction,
calculated channels, per-unit, measurement groups, synchronization),
mapped 1:1 to an HTTP status via `_STATUS_BY_ERROR_CODE`
(`api/v1/sources.py:64-78`). There is no `warning`/`info` concept, no
partial-success response shape, and no accumulating "list of issues"
pattern anywhere in a live code path.

`DisturbanceRecord.validate()` (`domain/disturbance_record.py:103`) is
the one place with an accumulating `list[str]` of problems and a
"never raises" contract — but it is a dormant utility: COMTRADE
construction cannot violate its own invariants, so no live code path
calls it today.

**`[OWNER DECISION]` (DEC-072 point 2, 2026-08-30)**: a future Powerwave
Readiness Validator (principle 6) will use a genuinely new, preparation-
scoped "issue" concept (blocking/warning/info) — it will not be built by
relabeling the existing `ImportServiceError` taxonomy, which keeps its
current, unchanged binary-and-blocking shape for every existing
application/runtime error. The two concepts are decided to be
conceptually distinct:

```text
Application / request / runtime failure  -> existing ImportServiceError model (unchanged)
Dataset preparation / readiness finding  -> new preparation/readiness issue model
```

A candidate shape (`PreparationIssue{severity, code, message, location,
suggested_action}`) was discussed but is **not yet approved** — only the
principle above is decided; the exact shape remains open (§18, slice 6).

---

## 7. Existing CSV/Excel capability — `oruxa_powerwave` vs. legacy `powerwave`

**`[FACT]`** `oruxa_powerwave`: zero CSV/Excel parsing exists.
`backend/app/providers/` contains only `base.py` and `comtrade.py`. The
frontend lists CSV/Excel only as disabled placeholders
(`RECORDING_FORMATS`, `frontend/index.html:4897-4902`), and the upload
submit handler is hardcoded to bail unless `format.id === "comtrade"`
(`index.html:5481`).

**`[FACT]`, per [POWERWAVE_DISCOVERY.md](POWERWAVE_DISCOVERY.md)** (an
independent full audit from 2026-08-14; not re-verified live this
session — treated per project governance as the authoritative discovery
record for `powerwave`): legacy `powerwave` has a mature two-tier
system —

1. **Direct providers** (`csv_provider.py`/`excel_provider.py`) — single
   unchunked `pd.read_csv`/`pd.read_excel`, no repair, no longer
   reachable from interactive upload (manifest-reload only).
2. **Import Wizard backend** (`app/import_wizard/*.py`, 27 files,
   Qt-free) — a "never raises" `ValidationMessage(severity, code,
   message)` pipeline; sampled profiling (~200-row scan); a
   `NormalizedDataset` intermediate (an auditable, still-tabular
   representation before final conversion — directly analogous to this
   project's proposed "Working Dataset"); a 12-strategy timestamp-repair
   executor; genuinely severity-aware diagnostics (duplicate/
   non-monotonic/gap counts, *reported, not auto-corrected*).

**What must NOT be copied** (`[FACT]`, from that discovery record):

- Raw original timestamp *values* are discarded after normalization
  (only a strategy-name label survives) — conflicts directly with this
  project's principle 1 (immutable, always-recoverable original) and
  principle 7 (no silent repair without traceability).
- Two non-communicating column-classification systems
  (`RuleManager`/YAML rules vs. the wizard's own detectors) — unresolved
  technical debt in `powerwave`, not a pattern to inherit.
- The `2000-01-01` sentinel-timestamp fallback (used when no usable date
  exists, while still leaving `timing_reference="absolute"`) is fragile.
  `oruxa_powerwave`'s own `time_grouping.py` is already more principled
  here: it treats "no real timestamp" as its own honest elapsed-only
  Time Group rather than inventing a fake absolute anchor.

**What is a useful engineering/design reference** (concept, not code —
`powerwave`'s implementation is Qt-adjacent pandas): the
sampled-profiling/full-execution split; the severity-tagged
`ValidationMessage` shape as a model for §6's missing severity concept;
the conservative, name-gated + monotonicity-gated elapsed-time detector;
and the discontinuity/gap diagnostic (`interval_inference.infer_interval()`)
— a capability COMTRADE itself still lacks in `oruxa_powerwave` today.

---

## 8. Data Preparation Workspace feasibility

**`[FACT]`, frontend routing/dialogs**: no router exists — `shell`
(`frontend/index.html:4933`) is a plain state object toggling
`.hidden` on DOM sections. A third top-level page
(`"calculated-channels"`) was already added this exact way
(`index.html:5140-5143`), so a `"data-preparation"` page fits the same
mechanism with no new pattern needed. Nine-plus modals already share one
`.confirm-overlay`/`.group-editor-box` shell (`index.html:1874-1930`),
including a working-copy-then-commit pattern (Edit Channel Groups stages
edits in `groupEditorState`, committing only on explicit Apply) —
directly reusable for a staged column-mapping dialog.

**`[FACT]`, non-destructive-edit precedent**: the recently-shipped
channel presentation override feature
(`ww.channelPresentationOverrides` Map, `index.html:7454-7467`,
read-merge-at-render via `wwChannelDisplayName()`/`wwColorForChannel()`,
full reset-to-canonical when both fields clear) is a proven,
already-shipped example of exactly this project's principle 3
(non-destructive correction as an overlay over immutable canonical data)
— the same shape (`Map<"id::field", override>` merged at read time,
never mutating the canonical source) is a strong starting reference for
the Working Dataset's own correction model.

**`[FACT]`, the real gap — table/grid rendering**: zero table/grid
library exists anywhere (`frontend/vendor/` contains only Plotly). The
Recordings table and the annotation review drawer both do naive
`innerHTML`/`createElement` full-DOM rendering with no pagination or
virtualization; a CSS comment (`index.html:3184-3196`) explicitly
records that virtualization was *considered and deliberately deferred*
even for "hundreds of digital channels." **A raw preview table for a
10k–1M-row CSV/Excel file cannot reuse any existing frontend pattern
as-is** — this is new frontend engineering.

**`[FACT]`, payload discipline**: the plotted-waveform payload problem
is already solved — per-channel, per-visible-range fetches capped at
≤20,000 points (`WW_POINT_BUDGET_MIN/MAX`, `index.html:7314-7316`),
resolved backend-side (`waveform_service.py`). This does **not**
directly solve the *raw preparation table* problem (showing raw rows for
editing, not plotted samples), but a paginated/windowed raw-data-preview
endpoint should follow the same "backend decides what's sent, frontend
never receives the whole file" principle.

**`[FACT]`**: no browser-memory-ceiling awareness exists anywhere in the
frontend. The only size check is an advisory 100 MB upload-size hint
(`CLIENT_SIZE_GUIDANCE_MB`, `index.html:4870`), not a decoded-array
memory bound.

---

## 9. Recommended raw/working-data architecture — analysis only, not implemented

**`[OWNER DECISION]` (DEC-072 point 3, 2026-08-30)**: a naive
architecture duplicating the entire raw dataset AND an entire working
copy in browser and/or backend memory is explicitly rejected. The
approved direction is a hybrid, reference-holding `PreparationSession`
(identity, references, and metadata — not full duplicated datasets) sitting
in front of paged/windowed backend access, matching the general shape
sketched below. This decision approved the boundary/principle only —
Slice 1 has since chosen and built the concrete mechanism within that
boundary; see the `[FACT]` note below.

**`[PROPOSAL]`, original analysis retained below**: the existing backend
already has the template —
**one new sibling in-memory registry per lifecycle stage**, wired via
`app.state.*` inside `main.py`'s `lifespan()` (seven such registries
already exist: workspace, calculated-channel, per-unit,
measurement-group, voltage-group-config, current-group-config,
synchronization — `main.py:52-80`). A `RawDatasetRegistry`/
`WorkingDatasetRegistry` keyed by `(workspace_id, source_id)` fits this
pattern exactly, inheriting the same disclosed limitations
`WorkspaceRegistry` already has (no TTL, single-process-only, released
on explicit removal or process restart — `workspace_registry.py:30-40`).

**`[FACT]`**: `storage.py` already declares `"working"`/`"exports"`/
`"temporary"` categories (`storage.py:18-25`) that are **currently
unused** — only `"original"` is ever written anywhere in the backend.
These read as purpose-built for this feature, but nothing exercises them
today.

**`[FACT]`, implemented in Slice 1 (2026-08-30)**: the mechanism is now
chosen and built, exactly as the `[PROPOSAL]` above anticipated —
`app.services.preparation_session_registry.PreparationSessionRegistry`,
an eighth in-memory sibling registry (`app.domain.preparation_session.PreparationSession`
holding a lightweight `PreparationSessionSummary` plus the raw CSV bytes
by reference), wired via `app.state.preparation_session_registry` in
`main.py`'s `lifespan()` exactly like the other seven. `StorageBackend`'s
dormant `"working"` category was considered and explicitly **not**
used for Slice 1: `StorageBackend` has no delete capability at all
(`write_text`/`write_bytes`/`read_text`/`read_bytes`/`exists`/`list`
only), so using it here would either require adding a new deletion
capability to that abstraction (bigger than this slice's scope) or leave
orphaned files with no cleanup path — see
`preparation_session_registry.py`'s own module docstring for the full
reasoning. This is an implementation choice within DEC-072 point 3's
already-decided boundary (hybrid, no full duplication), not a new
architectural decision requiring its own DEC entry — the boundary itself
was what DEC-072 approved; this is that boundary's first concrete
realization. Lifecycle: created on `POST .../preparation-sources`,
released on `DELETE .../preparation-sources/{id}` or whole-workspace
`DELETE /api/v1/workspaces/{id}` (now cascades into this registry too,
mirroring every other sibling), and — like every other sibling registry
— lost on process restart (no TTL, single-process only, same disclosed
limitation `WorkspaceRegistry` already carries).

---

## 10. Export architecture

**`[FACT]`**: zero export code exists anywhere in the backend (a
project-wide grep for "export" outside tests and the unused `"exports"`
storage category name returned nothing). Any future working-dataset
CSV/XLSX export is genuinely new work with no existing pattern to extend
or conflict with.

---

## 11. Risks and constraints

**High**

- No severity concept in the validation model (§6) — a Readiness
  Validator needs new architecture, not an extension of
  `ImportServiceError`. **Principle resolved (DEC-072 point 2)**: this
  remains a real, non-trivial implementation risk (new architecture
  still has to be designed and built) — only the "new concept, not a
  redesign of `ImportServiceError`" boundary is decided, not the work
  itself.
- `time`-column monotonicity/finiteness is unenforced everywhere
  downstream (§4/§5) — the first format able to actually violate an
  assumption every measurement/RMS/event-detection/synchronization code
  path silently relies on.
- No table/grid virtualization precedent anywhere in the frontend (§8)
  — a 100k–1M-row raw preview table is new engineering, not reuse.
- The backend already retains full-resolution parsed data in memory per
  source indefinitely, with no TTL (`MIGRATION_PLAN.md §16`, already an
  open/unmeasured risk before this feature). A Working Dataset stage
  sitting *before* normalization would add a second full in-memory copy
  per source during preparation, compounding an already-open risk.

**Medium**

- Multi-input calculated channels will routinely and correctly reject
  cross-source combinations involving CSV/Excel data (§5) — expected
  behavior, but needs clear user-facing explanation, not a workaround.
- DEC-015 ("uploaded event files are never persistently retained")
  versus a Working Dataset that may need to survive a page refresh or a
  multi-step preparation session. **Resolved (DEC-072 point 1)**:
  temporary, session-scoped preparation retention is explicitly
  permitted and does not reopen DEC-015 (see the addendum on DEC-015
  itself); the residual risk is choosing the right temporary-retention
  *mechanism* (§9, §18), not the principle.
- `time_axis_unit` and sample-index time representation do not exist in
  the current contract at all (§4) — genuinely new domain modeling, not
  merely activating an existing dormant hook the way `parameter_type`/
  `waveform_form` already are.

**Low**

- The provider abstraction, the `DisturbanceRecord` contract, the
  elapsed-only Time Group path, and the sibling-in-memory-registry
  pattern all already generalize cleanly — no risk found in any of
  these.
- The frontend page/modal architecture already has a working precedent
  for both a new top-level page and new staged-edit dialogs.

---

## 12. Architecture conflicts / owner decisions required

Original audit findings retained for the historical record (not deleted
— see [README.md's conflict-resolution
rules](README.md#conflict-resolution-rules)); all three items below are
now **`[RESOLVED — see DEC-072]`** as of 2026-08-30.

1. **DEC-015 vs. Working Dataset persistence.** `[RESOLVED — DEC-072
   point 1]` — a multi-step Data Preparation Workspace plausibly needs
   raw uploaded bytes, or at least a parsed raw table, to survive across
   requests/a page refresh before any canonical dataset exists. ~~Whether
   that in-progress state falls under DEC-015's "uploaded event files
   are never persistently retained," or is a distinct category DEC-015
   does not govern, needs an explicit owner decision.~~ **Resolved**:
   temporary, session-scoped preparation retention is explicitly
   permitted and does not reopen DEC-015; durable/permanent retention
   remains out of scope. The eventual *mechanism* for temporary
   retention remains open (§9, §18).
2. **Severity-tiered validation is new architecture.** `[RESOLVED —
   DEC-072 point 2]` — ~~introducing warning/blocking/info into a
   codebase where every current error is binary-and-blocking is a real
   API/error-model design decision~~. **Resolved**: approved, but scoped
   to a new, separate preparation/readiness issue model — `ImportServiceError`
   itself is explicitly unchanged. The exact shape remains open (§18).
3. **Where raw/working state physically lives.** `[RESOLVED (principle)
   — DEC-072 point 3; mechanism remains OPEN]` — the *principle* (hybrid,
   reference-holding `PreparationSession`, no full raw+working
   duplication) is decided; the *concrete mechanism* (in-memory sibling
   registry vs. `StorageBackend` `"working"` category vs. another shape)
   remains genuinely open, deliberately left for the implementation
   slices (§18).

---

## 13. Proposed implementation boundaries

**`[PROPOSAL]`**:

- New provider seam, unchanged abstraction: `CsvProvider`/
  `ExcelProvider(BaseProvider)` alongside `ComtradeProvider`, registered
  in the same `ProviderRegistry` — no change to `providers/base.py`.
- Canonical output stays `DisturbanceRecord` (§4) — everything
  downstream of that boundary (import orchestration, `WorkspaceRegistry`,
  `waveform_service`, Time Groups, measurement groups, calculated
  channels) is reused completely unmodified.
- The new work sits strictly *before* that boundary:

  ```
  Upload -> Raw ingestion -> Data Preparation Workspace (new) ->
  Normalization / Readiness Validation (new) ->
  DisturbanceRecord (existing contract, unchanged) ->
  everything that exists today
  ```

- Frontend: a new `shell.currentPage` value following the
  `"calculated-channels"` precedent; staged edits following the
  `groupEditorState`/channel-presentation-override precedent; a
  genuinely new virtualized/paginated raw-table component (no existing
  analog to reuse).

---

## 14. Recommended implementation slices — owner-revised sequence (DEC-072), not yet authorized to begin

**`[OWNER DECISION]` (DEC-072, 2026-08-30)**: this section supersedes the
audit's original draft sequence (which began with an abstract severity
primitive and `DisturbanceRecord.validate()` hardening — see this
document's own git history for that original text). The owner prefers a
workflow-driven sequence, starting from preparation-session foundation
and raw ingestion. **Being recorded here does not authorize starting any
slice** — each remains subject to this project's own
[change-governance rule](../../CLAUDE.md#change-governance) and explicit
owner go-ahead before implementation begins.

1. **`[DONE, 2026-08-30]` Preparation-session foundation + raw CSV
   ingestion.** Implemented: `PreparationSessionRegistry` (in-memory,
   mirrors `WorkspaceRegistry`), `import_csv_preparation_source()`
   (validate `.csv` suffix/non-empty/size-bound via the same shared
   `upload_utils.read_bounded`/`validate_suffix` helpers COMTRADE now
   also uses), `POST`/`GET`/`DELETE .../preparation-sources` endpoints,
   Recording Events table gains File Format/File Size/Status columns
   (COMTRADE `SourceMetadata`/`SourceSummaryOut` additively gained
   `file_size_bytes` the same way), Upload Recording modal's CSV option
   enabled with its own "Upload & Prepare" action, a "Needs Preparation"
   row is structurally excluded from `GET .../sources` (so it can never
   reach the Workspace Sidebar's channel-selection list) and its own row
   click/keydown handlers are gated on `status === "ready"` (defense in
   depth against opening it as a waveform). No `DisturbanceRecord`, no
   header/column/time-axis inference, no working-dataset overlay, no
   readiness validation — exactly this slice's own scope, nothing more.
   Verified: 1813 backend tests passing (36 new), zero regressions; the
   committed browser smoke test (COMTRADE) still passes unchanged; a
   live-browser manual UAT run confirmed both acceptance scenarios
   (COMTRADE unaffected; CSV upload → "Needs Preparation" row → correct
   File Format/File Size/Status/—/—/— → not openable as a waveform →
   removable) with zero console/page errors.
2. **`[DONE, 2026-08-30]` Excel ingestion + worksheet discovery.**
   Implemented: **`.xlsx` only** — legacy `.xls` is deliberately deferred
   (would need a separate, unmaintained `xlrd` dependency; `xlrd` 2.x
   dropped `.xlsx` support entirely and only reads legacy `.xls`, so it
   would not even cover both formats with one library). Library:
   `openpyxl==3.1.5` (newly declared in `backend/requirements.txt` — it
   was already present in the dev environment but undeclared; its own
   dependency footprint is just `et_xmlfile`, pure Python, no C
   extension, no GUI, no LibreOffice), used in `read_only=True` streaming
   mode — verified directly (not assumed) that opening an in-memory
   `BytesIO` this way creates zero temporary files, and worksheet
   discovery never materializes a sheet's cell grid.
   `import_excel_preparation_source()` reuses the SAME
   `PreparationSession`/`PreparationSessionSummary` shape Slice 1 already
   established (per DEC-072's own "one preparation-session concept, not
   one per format" architecture) — no `ExcelPreparationSession` type was
   created. A new `WorksheetInfo` descriptor
   (`index`/`name`/`visible`/`row_count`/`column_count`, the last two
   best-effort/`None`-able, from `Worksheet.max_row`/`max_column`, never
   a full-sheet scan) is discovered once at upload time and stored on
   the summary; hidden sheets are discovered and reported, never merged
   or dropped; sheets are never combined, concatenated, or cross-
   referenced (principle 8, reaffirmed). A one-worksheet workbook is
   auto-selected (`selected_worksheet_index=0`, deterministic, still
   visibly reported) — a workbook with two or more worksheets (even one
   visible + one hidden) requires an explicit selection. New
   `PATCH .../preparation-sources/{id}` endpoint
   (`WorksheetSelectionRequest`/`select_preparation_worksheet()`) stores
   only the stable `index` already discovered, never a header row/data
   region/column mapping. `POST .../preparation-sources` evolved from
   Slice 1's single required `csv_file` field to two OPTIONAL fields
   (`csv_file` xor `excel_file`, exactly one required) — chosen over a
   generic `format`+`file` pair or a second endpoint family because it
   mirrors this codebase's own existing `cfg_file`+`dat_file` convention
   (`app.api.v1.sources.upload_comtrade_source`); Slice 1's own frontend
   call sites and almost all of its own tests are unaffected (one Slice 1
   edge-case test — "no file field at all" — deliberately migrated from
   a generic 422 to an explicit `ambiguous_preparation_upload` 400,
   disclosed in that test's own updated comment). Frontend: Excel enabled
   in `RECORDING_FORMATS` (`.xlsx` accept only, label still reads
   "Excel"), `submitExcelUpload()` parallel to `submitCsvUpload()`, and a
   new minimal Worksheet Selection modal (`#wwWorksheetSelectOverlay`,
   reusing the same `.confirm-overlay`/`.group-editor-box` shell) opened
   by clicking a "Needs Preparation" Excel row — shows filename/size,
   lists worksheet names with a hidden badge and best-effort row/column
   counts, lets the user pick one via `PATCH`. Never renders cell
   contents (Slice 3's own scope). A "Needs Preparation" CSV row's click
   still does nothing at all (no worksheet concept) — only Excel rows get
   this new interaction; the row-click-to-open-as-waveform gate itself is
   unchanged (`status === "ready"`, still false for every preparation
   source regardless of format).
   Verified: 1848 backend tests passing (35 new on top of Slice 1's
   1813), zero regressions; the committed browser smoke test (COMTRADE)
   still passes unchanged; a live-browser manual UAT run confirmed all
   four acceptance scenarios (COMTRADE unaffected; CSV regression
   unaffected — click still does nothing, no worksheet modal; Excel
   single-sheet — correct File Format/File Size/Status/—/—/—, click
   opens the modal with the one sheet pre-selected, does not touch
   channel-selection state; Excel multi-sheet — all four sheet names
   discovered in order, none pre-selected, a chosen selection persists
   across reopening the modal) with zero console/page errors.
3. **`[DONE, 2026-08-31]` Paged raw-data preview + Data Preparation
   Workspace shell.** Implemented: a new `GET .../preparation-sources/{id}/rows`
   endpoint (`app.services.preparation_preview_service`) returning a
   bounded page of raw rows — default 200, server-enforced maximum
   1000, via `Query(ge=0)`/`Query(gt=0, le=1000)` (matching the existing
   `point_budget` precedent in `app.api.v1.sources.get_source_waveform`,
   so no separate range-validation error class was needed). CSV: streamed
   through `csv.reader` over the in-memory bytes (never `pandas.read_csv`,
   never a full DataFrame); a bounded dialect sniff (`csv.Sniffer`,
   restricted to `,;\t|`, falling back to comma) picks the delimiter once
   per request; exact row/column totals require one full pass over the
   in-memory text, memoized on the `PreparationSession` itself after the
   first request so later pages never re-derive them (still no index —
   reaching a given offset still means iterating from row 0, exactly the
   "acceptable initially if documented" allowance this task's own brief
   anticipated). Excel: reused Slice 2's `read_only=True` streaming
   approach, reopened fresh per request (never held open across
   requests), `iter_rows(min_row=, max_row=, values_only=True)` to avoid
   materializing rows outside the window; `data_only=False` so a formula
   cell shows its stored formula text, never a recalculated/cached
   value; row/column totals reuse Slice 2's own best-effort
   `WorksheetInfo.row_count`/`column_count` (no new Excel-side scan).
   Frontend: a new `shell.currentPage = "data-preparation"` fourth page
   (same "hide, don't destroy" mechanism, discovered and fixed the SAME
   `[hidden]` CSS-origin-specificity bug `#pageCalculatedChannels`
   already needed a fix for, applied proactively this time), a
   completely separate `wwDataPrep` state object (never touches `ww`),
   a plain server-paginated DOM table (no virtualization library — the
   task's own "a simple paged table is preferable to over-engineering
   virtualization at this stage" guidance, since each page is already
   bounded to ≤1000 rows server-side) with spreadsheet-style column
   letters (A, B, C, ...) and 1-based row numbers, sticky header row and
   sticky first column, and a title attribute on every non-blank cell
   for full-value-on-hover. A "Needs Preparation" CSV or Excel Recording
   Events row now opens this workspace (superseding Slice 2's own
   standalone Worksheet Selection modal, which is removed entirely — its
   sheet picker now lives inside this workspace as a `<select>`,
   switching sheets resets the preview to offset 0 and re-fetches).
   Verified: 1887 backend tests passing (39 new on top of Slice 2's
   1848), zero regressions; the committed browser smoke test (COMTRADE)
   still passes unchanged; a live-browser manual UAT run confirmed all
   four acceptance scenarios (COMTRADE unaffected, no Data Preparation
   page involved; CSV — correct spreadsheet column headers, row 1 shown
   as an ordinary raw row not a header, "Showing rows 1–200 of 250,"
   Next correctly advances to row 201, Back returns to Recording Events,
   still not waveform-openable; Excel single-sheet — worksheet field
   shows the one sheet, raw cells render correctly; Excel multi-sheet —
   prompts for an explicit selection rather than guessing, all four
   sheet names listed in order, switching sheets correctly changes the
   preview content) with zero console/page errors.
4. **`[DONE, 2026-08-31]` Working Dataset / non-destructive overlay.**
   Implemented: `app.domain.working_overlay.WorkingOverlay` — a sparse
   overlay (`cell_overrides: dict` keyed by
   `(worksheet_index_or_None, row_number, column_index)`,
   `excluded_rows: set` keyed by `(worksheet_index_or_None, row_number)`,
   `ignored_columns: set` keyed by `(worksheet_index_or_None,
   column_index)` — 1-based row/0-based column, matching the preview's
   own coordinate space exactly), created empty alongside each
   `PreparationSession` and
   mutated in place — proportional to edit COUNT, never to dataset size,
   confirming §17's own design reference (channel-presentation-override
   precedent) as the chosen mechanism, closing open item 1 from §18.
   `CellOverride{kind: edit|clear, value: str|None}` keeps an explicit
   CLEAR distinct from an EDIT to `""`; a working edit is always a plain
   string (no type inference, per DEC-072/principle 9). Undo/redo is
   supported (task's own "if it fits naturally" allowance) via a bounded
   (200-entry) operation history recording only each operation's own
   before/after state — O(1) per cell/row/column op, O(edit-count) for
   `reset_all` (a snapshot of the overlay's three collections, never of
   the dataset). A monotonic `revision` counter increments on every
   mutation (including undo/redo) for stale-page detection.
   `app.services.working_overlay_service` adds bounds validation (CSV:
   reuses the exact same full-scan function
   (`ensure_csv_totals_cached`, extracted from Slice 3's own preview
   logic) Slice 3 already proved correct, rather than a second,
   possibly-divergent implementation; Excel: the selected worksheet's
   own best-effort `WorksheetInfo.row_count`/`column_count`, never
   enforced when unknown) and a 10,000-character cell-value sanity bound
   (never an engineering-content check). Seven new endpoints under
   `.../preparation-sources/{id}/working/...`
   (`PUT`/`DELETE cells/{row}/{col}`, `PUT rows/{row}`,
   `PUT columns/{col}`, `DELETE` for reset-all, `POST undo`/`redo`),
   each returning a small `WorkingOverlaySummaryOut`
   (`working_revision`, `edited_cell_count`, `excluded_row_count`,
   `ignored_column_count`, `can_undo`, `can_redo`) — the same summary
   shape now also appended to the existing
   `GET .../preparation-sources` (list/detail) responses. The existing
   `GET .../rows` preview now returns the WORKING view by default: raw
   rows are merged with the overlay at read time only (never persisted,
   never a raw+working duplication per cell) — each `PreparationRowOut`
   gains `excluded: bool` and a sparse `modified_cells: [{column_index,
   raw_value}]` (only cells that actually differ from raw; the raw value
   is kept here purely for provenance/hover/reset, never duplicated as a
   second visible cell), and `PreparationSourcePreviewOut` gains
   `ignored_columns: [int]` and `working_revision: int`. Raw bytes and
   `cached_row_count`/`cached_column_count` are never mutated by an
   edit. Frontend: the Data Preparation workspace's preview table gained
   click-to-edit cells (a plain `<input>` swapped into one `<td>` — no
   spreadsheet-grid library), a small reset (↺) action on a modified
   cell, per-row Exclude/Include and per-column Ignore/Unignore toggle
   buttons, Undo/Redo buttons, and a "Reset All Changes" action reusing
   the existing `.confirm-overlay`/`.confirm-box` shell; the heading and
   hint text switch from "Raw Data Preview" to "Data Preview (Edited)"
   once any working change exists (task's own explicit "wording must not
   mislead" requirement), and a small change-count summary
   ("N cells edited · M rows excluded · K columns ignored") is always
   visible. Every control calls its own backend endpoint and re-renders
   from the response — the browser never applies an edit locally first
   (backend stays authoritative). No header/column-role inference, no
   time-axis interpretation, no readiness logic, and no database/
   permanent storage were introduced — exactly this slice's own scope.
   Verified: 1974 backend tests passing (87 new on top of Slice 3's
   1887), zero regressions; the committed browser smoke test (COMTRADE)
   still passes unchanged; two throwaway live-browser Playwright UAT
   scripts (deleted after verification, never committed) confirmed CSV
   cell edit → working value shown → reset restores the raw value; row
   exclude/include never renumbers surrounding rows; column ignore/
   unignore is reported page-independently; undo/redo round-trips a cell
   edit; Reset All (via its own confirm dialog) clears every kind of
   change and restores the "Raw Data Preview" heading; and an Excel
   two-worksheet workbook keeps edits made on one sheet completely
   invisible on the other, restored correctly on switching back — all
   with zero console/page errors.
5. **`[DONE, 2026-08-31]` Header/data-region + column-role mapping.**
   Implemented: the SAME `app.domain.working_overlay.WorkingOverlay`
   Slice 4 built (not a second, separate structure-mapping model) gains
   `header_row: dict[worksheet_index_or_None, int]`,
   `data_region: dict[worksheet_index_or_None, DataRegion(start_row,
   end_row)]`, and `column_roles: dict[ColumnKey, str]` -- all sparse
   (absence is the default: no header selected, entire source active,
   `unknown` role), all participating in the exact same bounded
   (200-entry) operation history / undo-redo / revision counter as
   Slice 4's own cell/row/column-ignore mutations (six new pure
   functions: `set_header_row`/`clear_header_row`/`set_data_region`/
   `reset_data_region`/`set_column_role`/`reset_column_role`). Role set:
   `unknown` (implicit default, never written explicitly) /
   `waveform` / `time_axis` / `metadata` / `quality_status` / `ignore` --
   multiple columns may carry `time_axis` simultaneously (task's own
   explicit "do not assume exactly one physical time column" guidance);
   no role is ever validated beyond membership in this closed set (no
   numeric/format/uniqueness checking -- purely a stated intent, per
   principle 9). Slice 4's own separate `ignored_columns` set was
   RETIRED in favor of `column_roles`'s `ignore` value as the single
   authoritative representation -- Slice 4's own
   `PUT .../working/columns/{column_index}` boolean endpoint (body
   `{ignored: bool}`) is preserved unchanged as a thin alias
   (`ignored=True` ⇔ role `ignore`; `ignored=False` resets the role to
   `unknown` ONLY if it is currently `ignore`, never silently
   reclassifying a column that already carries a different explicit
   role), verified permanently coherent with the new
   `PUT .../working/columns/{column_index}/role` endpoint by
   construction (one underlying store, never two that could drift).
   `app.services.working_overlay_service` adds bounds validation
   reusing the exact same `_check_row_bound`/`_check_column_bound`
   helpers Slice 4 built (no second bounds-checking implementation) plus
   two new errors: `InvalidDataRegionError` (`start_row > end_row`) and
   `InvalidColumnRoleError` (role outside the closed set). Six new
   endpoints (`PUT`/`DELETE .../working/header`, `PUT`/
   `DELETE .../working/data-region`, `PUT`/
   `DELETE .../working/columns/{column_index}/role`), each returning the
   same `WorkingOverlaySummaryOut` Slice 4 built, now extended with
   `header_row_number`/`data_start_row`/`data_end_row` (scoped to
   whichever worksheet the caller resolved -- `None` for CSV or an
   unselected multi-sheet Excel workbook, since Slice 5 mutations can
   only ever write under a real worksheet index for Excel). The existing
   `GET .../rows` preview gains `header_row_number`/`data_start_row`/
   `data_end_row`/`column_labels`/`column_roles` (each O(columns), never
   duplicated per row) and each row gains `is_header`/`in_active_region`
   flags -- independent of, and never conflated with, Slice 4's own
   `excluded` flag (task's own explicit "these are different concepts"
   distinction: a row can be inside the active region and excluded, or
   outside the region and not excluded). Column labels come from the
   header row's own WORKING cells (Slice 4 edits included, verified) via
   a new `_resolve_header_cells()` that reuses the current page when the
   header happens to be on it, or performs exactly one bounded
   single-row fetch (`_fetch_single_csv_row`/`_fetch_single_excel_row`)
   otherwise -- never a second full-page read. A blank header cell (raw
   `None` or a working edit to `""`) gets a distinct `"Column {letter}"`
   fallback; no header at all gets the plain spreadsheet letter; a
   header WITH duplicate text (e.g. three columns all labeled
   `"Voltage"`) is returned verbatim, deliberately not disambiguated
   (task's own "keep implementation simple and stable-index-based"
   guidance -- the frontend already shows each column's own stable
   letter alongside its label). Slice 4's own "Reset All Changes" now
   also clears header/region/role state (`app.domain.working_overlay.reset_all`'s
   own five-collection snapshot, still bounded by edit/mapping count,
   never dataset size) -- its own confirm-dialog copy was updated to
   say so. Frontend: a new "Structure" panel between the meta panel and
   the preview table -- a header-row number input + Set/Clear buttons, a
   data-region start/end pair + Set/Reset buttons, and a compact
   Column/Label/Role mapping table (one `<select>` per column, task's
   own "may be easier to manage than configuring roles directly in the
   grid" suggestion) — plus a per-row "Header" quick-select button in
   the preview table itself (for a header row already visible on the
   current page) and new `ww-data-prep-row-is-header`/
   `ww-data-prep-row-inactive` row styling, visually distinct from the
   existing excluded-row strike-through. No new framework; every control
   calls its own backend endpoint and re-renders from the response,
   matching Slice 4's own "backend is authoritative" pattern exactly.
   No header/data-region/column-role concept was retrofitted into
   `SourceMetadata`/`DisturbanceRecord`/waveform code anywhere.
   Verified: 2057 backend tests passing (83 new on top of Slice 4's
   1974), zero regressions; the committed browser smoke test (COMTRADE)
   still passes unchanged; two throwaway (not committed) live-browser
   Playwright UAT scripts confirmed: selecting row 3 as header on a CSV
   with two preamble rows correctly labels columns from row 3 while
   rows 1-2 stay visible; a blank + duplicate header row
   (`Time,VR,,VR`) produces `["Time","VR","Column C","VR"]`; clearing
   the header reverts to plain letters; a data region correctly flags
   rows outside it as inactive without removing them, and resetting the
   region reactivates the full source; assigning `time_axis` to two
   different columns is accepted with no error; resetting a role
   returns it to `unknown`; and an Excel two-worksheet workbook keeps
   header/region/role configuration on one sheet completely invisible
   on, and unaffected by, the other — all with zero console/page errors.
6. **`[DONE, 2026-08-31]` Readiness Issue model.** Implemented: the
   preparation-specific `blocking`/`warning`/`info` issue LANGUAGE AND
   TRANSPORT MODEL (DEC-072 point 2) -- explicitly NOT the full
   Powerwave Readiness Validator (slice 9), which alone will decide
   when a `blocking`/`warning` finding is actually produced. New
   `app.domain.preparation_issue`: `PreparationIssue{severity, code,
   message, location, suggested_action, details}`,
   `IssueLocation{worksheet_index, row_number, column_index, field}`
   (every field independently optional -- a dataset-level issue is
   valid with all four `None`), `PreparationIssueSummary{source_id,
   evaluated_revision, current_revision, is_stale, blocking_count,
   warning_count, info_count, issues}`. `ImportServiceError` itself was
   NOT touched -- a `PreparationIssue` is never raised, and a genuine
   runtime/request failure (source not found, worksheet not selected)
   is never represented as one; the two taxonomies stay fully parallel,
   confirmed by dedicated tests. Only three stable issue codes exist
   (`header_not_selected`, `data_region_unconfigured`,
   `column_roles_unassigned`), deliberately not a preemptive registry
   of every future validator finding. `app.services.preparation_issue_service`
   is a short, linear function (`collect_preparation_issues()`) checking
   already-known CONFIGURATION facts only -- no data interpretation, no
   time-axis parsing, no value validation -- and every issue it produces
   is `SEVERITY_INFO`, never implying invalidity (task's own explicit
   "do NOT silently decide a header is mandatory" /
   "do NOT silently decide multiple time-axis columns are invalid"
   guardrails honored: the column-roles-unassigned issue counts
   `unknown`-role columns without ever asserting that classifying them
   is required, and multiple `time_axis` columns raise nothing at all).
   Issues are derived LIVE on every request -- no cache, no new
   registry, no database; `evaluated_revision`/`current_revision` are
   therefore always equal and `is_stale` is always `False` today (the
   fields exist for a future caching layer's own wire-shape
   compatibility, per the task's own explicit design request, not
   because Slice 6 itself needs them to differ). New endpoint
   `GET .../preparation-sources/{source_id}/issues`, mirroring the
   existing `GET .../rows` endpoint's own worksheet-resolution rule
   (raises `WorksheetNotSelectedError` for an unselected multi-sheet
   Excel workbook, exactly like preview/working-overlay mutations
   already do -- no separate per-worksheet issues endpoint). Frontend: a
   new "Preparation Status" panel in the Data Preparation Workspace
   (severity counts + grouped Blocking/Warning/Info lists, each item
   showing its message/suggested action and, when the issue carries a
   worksheet, a "Go to worksheet" action reusing the existing worksheet
   `<select>`) -- refetched alongside every preview load, which already
   covers "refetch after every mutation" for free since every mutation
   already triggers a preview refetch. Recording Events status stays
   `Needs Preparation` throughout; no `Ready`/`Preparation Error`
   status, no "Open in Powerwave" action, and no readiness gate of any
   kind exist anywhere in this slice.
   Verified: 2101 backend tests passing (44 new on top of Slice 5's
   2057), zero regressions; the committed browser smoke test (COMTRADE)
   still passes unchanged; two throwaway (not committed) live-browser
   Playwright UAT scripts confirmed: a freshly uploaded CSV shows all
   three info issues with correct counts and no blocking/warning
   anywhere, with status still reading "Needs Preparation" and no
   "Open in Powerwave"/"Powerwave Ready" text anywhere on the page;
   setting then clearing a header row correctly removes then restores
   the `header_not_selected` issue; `evaluated_revision`/
   `current_revision` both track the session's own actual working
   revision after mutations, with `is_stale` always `false`; and a
   multi-sheet Excel workbook with no worksheet selected yet leaves the
   issue panel safely empty (no error, no corrupted state) until a
   sheet is chosen, after which each sheet's own issues render
   correctly and independently -- all with zero console/page errors.

   **`[DONE, 2026-08-31]` Post-Slice-6 UX refinement (owner UAT,
   presentation only).** Owner feedback: Slice 6's own fully-expanded
   default layout for Preparation Status, combined with Slice 5's own
   fully-expanded default Structure controls, made the Data Preparation
   Workspace feel overwhelming. Applied progressive disclosure ("show
   current state first; show detailed configuration only when the user
   chooses to change or inspect it") to BOTH panels, `frontend/index.html`
   only -- no preparation-issue semantics/codes/severity logic, no
   working-overlay/header/data-region/column-role backend model, and no
   API contract changed. Preparation Status: the counts line stays
   always visible; the detailed grouped issue list collapses behind a
   new "View Issues"/"Hide Issues" toggle (plus a presentation-only
   `blocking_count > 0` "Needs Attention" lead-in shell for a FUTURE
   readiness state -- unreachable today, since this slice's own issue
   production never emits `blocking`). Structure: a compact `Header: …
   / Data range: … / Columns: …` summary line replaces the
   permanently-visible controls as the default view, with a single
   "Configure"/"Hide" toggle revealing the exact same header-row input,
   data-region inputs, and column-role mapping table Slice 5 already
   built. Both expand states are frontend-only, session-scoped flags,
   reset to collapsed on every fresh workspace open -- never persisted,
   never sent to the backend. Every existing interaction (row-level
   "Set as Header," column-role selects, Set/Reset Region, Undo/Redo,
   Reset All, issue-driven worksheet navigation) is functionally
   unchanged. Verified: full backend suite re-run unmodified (2101
   passed, 0 regressions -- no backend file touched); the committed
   browser smoke test (COMTRADE) still passes unchanged; two throwaway
   (not committed) live-browser Playwright UAT scripts confirmed the
   collapsed-by-default state, correct expand/collapse toggling for
   both panels, a correctly updating Structure summary after
   configuring header/region/roles, preserved row-level quick actions
   and Undo, and correct per-worksheet summary isolation for a
   multi-sheet Excel workbook -- zero console/page errors.

   **`[DONE, 2026-09-01]` Data-region end-selection UX refinement
   (owner UAT, presentation + minimal model evolution).** Owner
   feedback: manually finding the true last data row of a large source
   was "unnecessarily burdensome." `app.domain.working_overlay.DataRegion`
   gains `end_mode` (`END_MODE_SOURCE_END` / `END_MODE_SPECIFIC`,
   defaulting to `END_MODE_SPECIFIC` so every pre-refinement call site
   keeps working completely unchanged) -- `end_row` is `None` for
   `END_MODE_SOURCE_END` (a genuinely floating boundary, deliberately
   NEVER resolved into a stored numeric guess, even though the actual
   total may already be known). This stays ONE dataset-wide boundary
   per worksheet/source, exactly as Slice 5 established -- no per-column
   end was introduced, and a source with columns of differing effective
   lengths still resolves to a single shared region (verified directly).
   `app.services.working_overlay_service.set_data_region()`/
   `WorkingOverlaySummary` and `app.services.preparation_preview_service`'s
   `PreviewResult`/`_apply_structure_mapping()` extend the same way
   (`data_end_mode` alongside the existing `data_end_row`); the actual
   RESOLVED upper bound used only to compute each row's own
   `in_active_region` flag (CSV: exact via the existing
   `ensure_csv_totals_cached()`; Excel: the existing best-effort
   `WorksheetInfo.row_count`, or unbounded when unknown) is an internal
   detail never itself exposed on the wire. `DataRegionRequest` gains
   `end_mode` (defaulting to `"specific"`, preserving the original
   `{start_row, end_row}` request shape verbatim). "Go to Last Rows" is
   frontend-only NAVIGATION -- computed from the existing
   `GET .../rows` response's own `total_row_count` and the existing
   paging state, reusing `wwDataPrepFetchPreview()` -- no new endpoint,
   no data-region mutation, no revision change. Undo/redo needed ZERO
   domain-code changes to support an end-mode change, since
   `WorkingOperation.before`/`after` already stores the whole frozen
   `DataRegion` object. The optional per-column "last populated row"
   diagnostic from this task's own spec was evaluated and DEFERRED --
   see this document's own "Genuinely unresolved" register below for
   why. Frontend: the "Data rows" controls became a Start row input plus
   an End radio group ("To end of file" for CSV / "To end of sheet" for
   Excel, or "Specific row" with its own input, disabled unless
   selected) and a "Go to Last Rows" button; the Structure summary's
   "Data range" line reads "Rows N–end" for a floating boundary,
   "Rows N–M" for a specific one, and "All rows" when no region is
   configured at all.
   Verified: full backend suite 2125 passed (24 new on top of the
   post-Slice-6 UX refinement's 2101), zero regressions; the committed
   browser smoke test (COMTRADE) still passes unchanged; two throwaway
   (not committed) live-browser Playwright UAT scripts confirmed: the
   default end mode is "To end of file" with the specific-row input
   correctly disabled; setting a region with only a start row produces
   "Rows N–end"; "Go to Last Rows" jumps to the true final page without
   changing the region, the working overlay, or the revision counter;
   switching to "Specific row" and entering a numeric end correctly
   trims the region to "Rows N–M," with rows beyond it flagged
   `in_active_region: false` but still fully visible; undo/redo
   correctly round-trips an end-mode change; and an Excel workbook
   shows "To end of sheet" wording with fully independent per-worksheet
   region configuration -- all with zero console/page errors.

   **Note on commit `db72885`** ("fix: resize the font-size", owner
   commit): this commit unintentionally contains BOTH the owner's own
   CSS font-size changes AND the completed `app/domain/working_overlay.py`
   portion of this refinement (the `end_mode`/`DataRegion` domain
   changes), because both were present in the shared working tree at
   the moment the owner's commit was created. This is a commit-history
   attribution/message mismatch only -- not a code defect, and not
   something this session created or committed itself. Per explicit
   owner direction, `db72885` is left exactly as-is (not amended,
   reverted, or rebased); the domain-layer portion of this refinement
   is treated as already delivered via that commit, while the remaining
   files (service/preview/schema/API layers, tests, frontend,
   documentation) remain normal uncommitted working-tree changes,
   pending a separate, explicit commit instruction.
7. **`[DONE, 2026-09-01]` Extensible time-axis framework (Slice 7).**
   Implemented the FRAMEWORK from
   [CSV_EXCEL_TIME_INTERPRETATION.md](CSV_EXCEL_TIME_INTERPRETATION.md)
   -- interpreter architecture, an explicit unknown/unsupported path, no
   closed format list (DEC-072 point 6, §15) -- with deliberately NO real
   datetime/elapsed/sample-index parsing, no reconstruction algorithm, no
   confidence calculation, and no readiness gating (all Slice 8+). New
   `app.domain.time_axis`: five open-ended semantic families
   (`absolute`/`elapsed`/`sample_index`/`partial`/`unknown`), four -- not
   five -- provenance states (`native`/`reconstructed`/`user_specified`/
   `index_only`; "inferred" deliberately excluded, folded into
   `confidence` instead per the design doc's own §4), qualitative
   confidence (`high`/`medium`/`low`/`unknown`, always `unknown` today),
   a seven-state status model (`unconfigured`/`detected`/
   `review_required`/`confirmed`/`needs_attention`/`index_fallback`/
   `unsupported` -- `review_required` is a currently-unreachable-by-
   `resolve_status()` but valid value, reserved for Slice 8), and a
   `TimeAxisDiagnostic` model that is a SEPARATE transport from
   `PreparationIssue` (borrows the `blocking`/`warning`/`info`
   vocabulary informally only, never counted into
   `PreparationIssueSummary`). `TimeAxisConfiguration{column_indices,
   family, provenance, interpreter_id, unit, interval_seconds, confirmed,
   options}` is stored per-worksheet/source in a new
   `WorkingOverlay.time_axis: dict[worksheet_index_or_None,
   TimeAxisConfiguration]` -- the exact same sparse-dict/frozen-
   replace-on-change/`None`-scoped-for-CSV pattern as `header_row`/
   `data_region`/`column_roles` before it, sharing the SAME bounded
   undo/redo history and revision counter (`set_time_axis_configuration`/
   `clear_time_axis_configuration` add one new `"time_axis"`
   `WorkingOperation` kind; `reset_all()` clears it too) -- no second
   history mechanism. Column-role relationship (task's own explicit
   requirement): a configuration may only be CREATED referencing columns
   currently carrying `ROLE_TIME_AXIS` (enforced at write time by
   `app.services.time_axis_service`); if a column's role later changes
   away from Time Axis, the stored configuration is deliberately left
   untouched (no auto-clearing, which was considered and rejected to
   avoid a compound, harder-to-undo mutation) -- staleness is instead
   detected LIVE on every read and reported as `unsupported`, never
   presented as valid. `app.services.time_axis_service` provides a
   small, explicit, hand-written interpreter registry (no plugin
   discovery, matching `KNOWN_COLUMN_ROLES`'s own precedent) with
   exactly two non-parsing interpreters: `manual` (stores whatever
   family/provenance/unit/interval the caller states, accepts any
   non-empty column set) and `unsupported` (the universal fallback
   sentinel, always `family=None, provenance=None`) --
   `resolve_interpreter()` falls back to `unsupported` when no real
   interpreter accepts a request, directly unit-tested via a synthetic
   fake interpreter (Slice 8 adds real interpreters to this same
   registry without changing its shape). `TimeAxisInterpretationResult`
   is derived LIVE on every call from stored state + current
   `column_roles` (never cached, mirroring
   `preparation_issue_service`'s own "derive live" choice) and echoes
   `unit`/`interval_seconds`/`confirmed` verbatim from the stored
   configuration (a presentation convenience for the frontend's own edit
   form, not a new calculation). New endpoints, extending the existing
   `.../preparation-sources/{source_id}/...` pattern: `GET .../time-axis`
   (the live interpretation result), `PUT .../working/time-axis` (create/
   replace; full schema validation -- non-empty/unique/in-bounds
   `column_indices`, all currently Time-Axis-role, known
   `family`/`provenance`, positive `interval_seconds` if given, known
   `interpreter_id` if given), `DELETE .../working/time-axis` (clear,
   safe no-op), `GET .../time-axis/interpreters` (registry metadata).
   Two new error codes: `invalid_time_axis_configuration`,
   `unknown_time_axis_interpreter`. `time_grouping.py` and
   `DisturbanceRecord` were NOT touched (task's own explicit
   requirement) -- absolute/non-absolute compatibility is fully
   preserved since nothing in this slice feeds `timing_reference` yet.
   Frontend: a new compact, progressive-disclosure "Time Axis" panel in
   the Data Preparation Workspace (same shell as Preparation Status/
   Structure: an always-visible Columns/Interpretation/Status summary, a
   "Configure"/"Hide" toggle revealing a form) that CONSUMES -- never
   duplicates -- the Structure panel's own `column_roles` state: eligible
   columns are always exactly the current `time_axis`-role columns,
   rendered as checkboxes (supporting multiple Time Axis columns in one
   configuration); an explicit "No Time Axis columns selected" hint
   replaces the form when none exist; family selection toggles
   unit/interval field visibility (elapsed → unit, sample_index →
   interval, never both). `preview_supported` is always `false` on the
   wire -- the frontend never renders a fabricated reconstructed-
   timestamp preview (a seam only, per this slice's own explicit
   guardrail).
   Verified: full backend suite 2206 passed (81 new on top of the
   data-region end-selection refinement's 2125), zero regressions (new
   domain/WorkingOverlay/service/API test files/classes added for
   families/provenance/statuses, `resolve_status()` precedence, registry
   resolution and fallback, column-role staleness, worksheet isolation,
   and undo/redo); the committed browser smoke test (COMTRADE) still
   passes unchanged; two throwaway (not committed) live-browser
   Playwright UAT scripts confirmed: the panel is collapsed by default;
   expanding with no Time Axis columns shows the Structure-first hint;
   assigning the Time Axis role in Structure immediately makes a column
   eligible here; configuring one and then multiple columns updates the
   compact summary correctly (`"A"` then `"A, B"`); `sample_index`+
   `index_only` reports `index_fallback`; Undo/Redo correctly round-trips
   a configuration change; changing a configured column's role away from
   Time Axis reports `unsupported` without touching the stored
   configuration; Clear reverts to `unconfigured`; and a multi-sheet
   Excel workbook keeps one sheet's configuration completely invisible
   on, and unaffected by, another -- all with zero console/page errors.
8. **`[DONE, 2026-09-02]` Initial time-axis interpreters.** The safest
   initial cases only — do not attempt every possible time-axis format
   at once. Full proposed initial interpreter set (single-column
   absolute datetime; Date + Time; elapsed numeric time; sample index;
   repeated-timestamp/lost-precision detection) recorded in
   [CSV_EXCEL_TIME_INTERPRETATION.md §19](CSV_EXCEL_TIME_INTERPRETATION.md#19-slice-8-scope--initial-interpreters)
   — all five now implemented (Slices 8A/8B/8C below); segmented/
   variable-cadence reconstruction remains explicitly deferred (see the
   Slice 8C entry's own scope note), not a gap in this item.

   **`[DONE, 2026-09-01]` Slice 8A — the two deterministic absolute-time
   cases.** Implemented exactly the first two items of that set —
   single-column absolute datetime and Date + Time — as REAL,
   deterministic (non-fuzzy) interpreters on top of the Slice 7
   framework.

   **`[DONE, 2026-09-02]` Slice 8B — elapsed numeric time + sample
   index.** Implemented items 3-4 of that set (see this document's own
   Slice 8B entry below for the full implementation summary).

   **`[DONE, 2026-09-02]` Slice 8C — repeated-timestamp / precision-loss
   detection and reconstruction.** Implemented item 5, the fifth and
   final item of that set (see this document's own Slice 8C entry below
   for the full implementation summary). Powerwave may detect, analyse,
   suggest, and preview a reconstructed timing — it never silently
   applies one.

   **`[DONE, 2026-09-02]` Slice 8D — Time Irregularity Diagnostics.** A
   diagnostic-only normalization layer over the irregular-timing
   conditions §19's own five interpreters already encounter (see this
   document's own Slice 8D entry below for the full implementation
   summary) — never a new interpreter, never readiness gating.

   New interpreter ids registered in `app.services.time_axis_service`'s
   own registry: `absolute_datetime` (accepts exactly 1 column) and
   `split_date_time` (accepts exactly 2 columns, `column_indices`
   documented as `(date_column_index, time_column_index)` in that
   order) — both implemented in new
   `app/services/time_axis_interpreters.py`, a small, explicit,
   deterministic `datetime.strptime`/`datetime.fromisoformat` pattern
   table (`%d/%m/%Y`, `%m/%d/%Y`, `%Y/%m/%d` × a bounded time-pattern
   set with fractional seconds and AM/PM) — no `dateutil`/fuzzy parsing
   anywhere. `manual` stays the default when `interpreter_id` is
   omitted (explicitly checked by id, not by registry iteration order
   -- a real fragility was found and fixed here: a test's own
   `monkeypatch.delitem`/re-add of `manual` silently reordered the
   dict, which an order-dependent auto-select would have gotten wrong).

   **Ambiguity by elimination, never by guessing.** For `01/02/2026`-
   style input, every known date order (`dmy`/`mdy`/`ymd`) is tried
   against the WHOLE bounded sample; `strptime` itself already rejects
   an invalid calendar date (day=31 rules out `mdy`), so a single
   surviving order is reported `native`/`unambiguous` with `high`
   confidence, while two or more surviving orders produce an
   `ambiguous_date_order` diagnostic (`ambiguity: "ambiguous"`) and the
   NEW `review_required` status (Slice 7's own reserved-but-unreachable
   status is now real) — never auto-confirmed. The user's own explicit
   `options.date_order` choice resolves it (`provenance` becomes
   `user_specified`); `set_time_axis_configuration()` outright REJECTS
   `confirmed=true` while an `ambiguous_date_order` diagnostic remains,
   enforced server-side, not only in UI copy. A bare time-of-day column
   (no date component) is reported `family=partial`, never silently
   promoted to `absolute` (a `time_only_not_absolute` diagnostic). ISO-
   8601 timestamps preserve a trailing `Z`/`±HH:MM` offset verbatim
   (via `datetime.fromisoformat`, Python 3.13's own native support) --
   a value with NO timezone stays naive, never defaulted to the
   server's or browser's own local timezone.

   New domain vocabulary (`app/domain/time_axis.py`): `DATE_ORDER_DMY`/
   `MDY`/`YMD`/`AUTO`, `AMBIGUITY_UNAMBIGUOUS`/`AMBIGUOUS`/`INVALID`
   (a SEPARATE axis from `confidence` -- ambiguity is "could a
   reasonable person read this differently," confidence is "how much
   evidence supports this reading"), six diagnostic codes
   (`ambiguous_date_order`, `unparseable_datetime`,
   `mixed_datetime_format`, `missing_datetime_value`,
   `timezone_inconsistent` reserved for a future interpreter,
   `time_only_not_absolute`), and a new `TimeAxisDetectionResult`/
   `TimeAxisSampleRow`/`TimeAxisPreviewRow` shape set feeding the
   interpreter contract's own two-method split the design doc's §17
   already anticipated (`detect()` for classification, a bounded
   `build_preview_rows()` for the {original, interpreted} preview).
   `TimeAxisDiagnostic` gained `ambiguity`/`details` fields (both
   optional, defaulting to backward-compatible values);
   `TimeAxisInterpretationResult` gained an `options` echo field.

   **Bounded sampling, never a full scan** (task §H/§U): a NEW
   `_fetch_time_axis_samples()` in `time_axis_service.py` reuses
   `preparation_preview_service.preview_preparation_source()` verbatim
   (never a second raw-reading implementation), capped at 50 rows
   starting at the configured data region's own start row, with
   excluded/out-of-region/header rows dropped before an interpreter
   ever sees them. A dry-run preview response caps its own formatted
   {original, interpreted} rows at 20 (a second, smaller bound purely
   for response size) — detection itself still considers the full
   50-row sample regardless.

   New API: `POST .../working/time-axis/interpret` (task's own
   suggested route, kept verbatim) — a read-only, disposable dry-run
   action returning family/provenance/confidence/diagnostics/
   resolved_options/a bounded preview, storing nothing, never touching
   the revision counter or undo/redo. `PUT .../working/time-axis`
   extended: `family`/`provenance` are now OPTIONAL (required only for
   `manual`; a SAMPLE interpreter's own `detect()` always overrides
   whatever hint was supplied, since the interpreter's own identity
   already IS the family it produces) and a new `options` field is
   accepted and echoed back.

   Frontend: the Time Axis panel's expanded form gained an "Interpreter"
   `<select>` (Manual / Absolute Datetime / Date + Time) switching
   between Slice 7's own plain family/provenance fields and a new
   Detect → review ambiguity (a date-order radio group, shown ONLY when
   genuinely ambiguous) → bounded preview table → Confirm flow; `split_
   date_time` additionally shows two small "Date column"/"Time column"
   selects populated from whichever Time Axis columns are currently
   checked (task §Q's own "without duplicating the full Structure role
   table"). No internal parser/class names are ever exposed to the
   user.
   Verified: full backend suite 2284 passed (78 new on top of Slice 7's
   2206), zero regressions; the committed browser smoke test
   (COMTRADE) still passes unchanged; three throwaway (not committed)
   live-browser Playwright UAT scripts confirmed: an unambiguous ISO
   column detects cleanly with a correct preview and Save→Confirm works;
   an ambiguous `01/02/2026`-style column shows the date-order radios,
   blocks `confirmed=true` server-side with the rejection message
   surfaced in the panel's own status line, and resolves cleanly once an
   explicit order is chosen; `split_date_time` correctly combines two
   columns via its own Date/Time selects; and Excel worksheet isolation
   and the COMTRADE regression both remain intact -- all with zero
   console/page errors.

   **`[DONE, 2026-09-02]` Slice 8B — elapsed numeric time + sample
   index, full implementation summary.** New interpreter ids in the
   SAME `app.services.time_axis_service` registry: `elapsed_numeric`
   (accepts exactly 1 column) and `sample_index` (accepts exactly 1
   column) -- both implemented in `app/services/time_axis_interpreters.py`
   alongside Slice 8A's own two, reusing the identical `detect()`/
   `build_preview_rows()` interpreter contract (extended with two new
   optional parameters, `requested_unit`/`requested_interval_seconds`,
   accepted and ignored by `absolute_datetime`/`split_date_time`).

   **No new top-level fields needed.** `TimeAxisConfiguration.unit`/
   `.interval_seconds` already existed since Slice 7, anticipating
   exactly this -- `elapsed_numeric` resolves `unit` only,
   `sample_index` resolves `interval_seconds` only; neither needed a new
   `options` key. `TimeAxisDetectionResult` gained matching
   `resolved_unit`/`resolved_interval_seconds` fields (both default
   `None`, backward-compatible with Slice 8A's own two interpreters).

   **Elapsed numeric time** (task §A/§B/§C/§D): `family` is always
   `FAMILY_ELAPSED`, `provenance` is always `PROVENANCE_USER_SPECIFIED`
   once a unit is set (units are never silently inferred, per
   CSV_EXCEL_TIME_INTERPRETATION.md §8/§9's own pre-existing rule) --
   supports `seconds`/`milliseconds`/`microseconds`/`nanoseconds`
   (`app.domain.time_axis.KNOWN_ELAPSED_UNITS`), validated at the
   service layer SCOPED TO `elapsed_numeric` specifically (never
   narrowing `manual`'s own deliberately open-ended `unit` field, per
   DEC-072 point 6). An absent unit produces a NEW `missing_elapsed_unit`
   diagnostic with `ambiguity: "ambiguous"` -- reusing Slice 8A's own
   `review_required`-via-ambiguity precedence verbatim (a second
   producer of a mechanism already built, not a new status branch).
   `set_time_axis_configuration()` rejects `confirmed=true` while that
   diagnostic remains, exactly like an unresolved date order. Detected
   once a unit exists: `non_numeric_elapsed_value`,
   `missing_elapsed_value`, `elapsed_time_goes_backward`,
   `repeated_elapsed_time`, `non_uniform_elapsed_interval` (a ±1%
   relative-tolerance check against the first observed delta) -- all
   informational (`ambiguity: "unambiguous"`, except the non-numeric
   case which is `"invalid"`), routing through the existing generic
   `needs_attention` precedence. Preview values are always canonical
   SECONDS (`"0.010000 s"`), converted via one fixed per-unit factor
   table -- never the original unit re-displayed.

   **Sample index** (task §E-§L/§F/§G/§H): `family` is always
   `FAMILY_SAMPLE_INDEX`. Absent `interval_seconds` is
   `provenance=index_only` -- a COMPLETE, valid, non-diagnostic state
   (task's own explicit "not an error... the approved fallback"),
   reusing Slice 7's own pre-existing `STATUS_INDEX_FALLBACK` precedent
   verbatim (`family=sample_index` + `provenance=index_only` already
   forced this status unconditionally, even before Slice 8B existed).
   A present `interval_seconds` (already validated positive by the
   SAME generic top-level check every other interpreter's `interval_seconds`
   already used) is `provenance=user_specified`, `confidence=high`, and
   status falls through to the ordinary detected/confirmed/
   needs_attention rules. Detected regardless: `non_numeric_sample_index`,
   `missing_sample_index`, `sample_index_goes_backward`,
   `repeated_sample_index`, `sample_index_gap` (any consecutive delta
   `>1`) -- comparing each sampled value only to the PREVIOUS one, in
   original row order, never sorted or renumbered. A rate/interval
   choice is a FRONTEND-ONLY display toggle -- only `interval_seconds`
   (seconds-per-sample) is ever stored; a "Sampling rate (Hz)" input is
   converted client-side (`interval_seconds = 1/rate_hz`) before
   submission, never a second stored representation (task §I's own
   "do not maintain two conflicting authoritative values" instruction).
   Preview `relative_seconds = (index - first_valid_index_in_sample) *
   interval_seconds` (task §G's own recommended rule, generalized to
   interval form) -- `first_valid_index` is the first non-missing,
   numeric value in the bounded sample itself, never assumed `0`, never
   a whole-dataset scan.

   New API: `POST .../working/time-axis/interpret` and
   `PUT .../working/time-axis` both extended with the pre-existing
   `unit`/`interval_seconds` fields already accepted by the schema
   since Slice 7 (no new schema fields for the request bodies) --
   `TimeAxisInterpretPreviewOut`/`TimeAxisInterpretRequest` gained
   `resolved_unit`/`resolved_interval_seconds` (response) and `unit`/
   `interval_seconds` (request) respectively.

   Frontend: the Interpreter `<select>` gained "Elapsed Time (1 column)"
   and "Sample Index (1 column)"; Elapsed Time shows a required Unit
   `<select>` (no unit pre-selected); Sample Index shows a progressive-
   disclosure Timing radio group (Unknown / Sampling rate Hz / Sample
   interval ms, task §N) that converts to `interval_seconds` client-side
   before every Detect/Save call and always redisplays a stored
   configuration as "Sample interval" (the backend never remembers which
   input mode the user originally used). The shared Detect → diagnostics
   → preview → Confirm flow (Slice 8A) is reused verbatim; the date-order
   review UI is shown ONLY for the specific `ambiguous_date_order`
   diagnostic, never for `missing_elapsed_unit` (whose own resolution
   control is the Unit select, already visible).
   Verified: full backend suite 2362 passed (78 new on top of Slice 8A's
   2284), zero regressions; the committed browser smoke test (COMTRADE)
   still passes unchanged; three throwaway (not committed) live-browser
   Playwright UAT scripts confirmed: an elapsed column with no unit shows
   "Review Required" and a `missing_elapsed_unit` diagnostic, resolves
   cleanly to "Detected"/"Confirmed" once Milliseconds is chosen, with a
   correct canonical-seconds preview; a sample-index column with a gap
   shows the gap diagnostic while still reporting Index Fallback with no
   fabricated seconds column, accepts `confirmed=true` immediately (not
   an error), and correctly resolves a real-time interval once a
   Sampling rate is entered (surfacing the gap as "Needs Attention" once
   provenance is no longer `index_only`); and Excel worksheet isolation
   plus the COMTRADE regression both remain intact -- all with zero
   console/page errors.

   **`[DONE, 2026-09-02]` Slice 8C — repeated-timestamp / precision-loss
   detection and reconstruction, full implementation summary.** New
   interpreter id in the SAME `app.services.time_axis_service` registry:
   `repeated_timestamp_precision_loss` (accepts exactly 1 column) --
   implemented in `app/services/time_axis_interpreters.py` alongside
   Slice 8A/8B's own four, reusing the identical `detect()`/
   `build_preview_rows()` interpreter contract with no signature change
   at all (the same `requested_interval_seconds`/`requested_options`
   Slice 8B already added cover this interpreter's own manual-override
   and anchor-offset needs).

   **No new top-level fields needed anywhere.** `TimeAxisConfiguration.
   unit`/`.interval_seconds`/`.options` and `TimeAxisDetectionResult`'s
   own `resolved_interval_seconds`/`resolved_options` all already
   existed since Slice 7/8B, anticipating exactly this. The one new
   interpreter-specific setting, `anchor_offset_seconds` (seconds,
   default 0), lives in the pre-existing generic `options` bag -- zero
   new dataclass fields anywhere.

   **Bucket analysis** (CSV_EXCEL_TIME_INTERPRETATION.md §7): consecutive
   rows sharing an identical native timestamp string form one bucket, in
   original row order, over the SAME bounded ≤50-row sample every other
   interpreter already uses -- never a full-dataset scan, never sorted.
   Both `absolute` and `partial` (time-of-day, no date ever invented)
   families are supported via one family-agnostic `seconds_from_first:
   list[float]` representation computed once after parsing, so every
   downstream statistic (confidence, interval estimation) is written
   once regardless of family. First and last buckets never penalize
   confidence (they may be sample-window-truncated) -- only
   `interior_sizes = bucket_sizes[1:-1]` feeds the stability check.

   **Confidence rule** (qualitative only, per
   CSV_EXCEL_TIME_INTERPRETATION.md §6, no percentages): HIGH requires
   at least 2 equal-sized interior buckets; MEDIUM covers either too few
   interior buckets to compare (but fully consistent) or an interior
   spread of at most 1; LOW covers everything else, including fewer
   than 2 total buckets. Suggested `interval_seconds` is
   `statistics.median()` of `span_to_next_bucket / bucket_size` across
   every transition EXCEPT the first (the first bucket's own count may
   be a truncated undercount), falling back to including it only when no
   other estimate exists.

   **Reconstruction is offered, never silently applied** (the task's own
   governing rule, restated in code): a NEW `resolve_status()`
   precedence rule -- `provenance == PROVENANCE_RECONSTRUCTED and not
   confirmed` routes to `STATUS_REVIEW_REQUIRED` -- is GENUINELY SEPARATE
   from the ambiguity mechanism Slice 8A built (`ambiguous_date_order`/
   `missing_elapsed_unit`). Marking the "a suggestion exists" diagnostic
   as `ambiguity: "ambiguous"` would have made an accepted reconstruction
   permanently unconfirmable (the diagnostic disclosing it never
   disappears); the new rule instead lets `confirmed=true` succeed once
   the user accepts. A genuinely unreliable case
   (`cadence_not_reliable`, `ambiguity: "ambiguous"`) still uses the
   EXISTING ambiguity mechanism and correctly blocks confirmation --
   segmented/variable-cadence reconstruction is deferred, returning this
   review/low-confidence state instead of guessing.

   **A new diagnostic severity, `SEVERITY_INFO`, was required.** Slice
   8C is the first interpreter to attach always-true disclosure notes
   (`repeated_timestamp_detected`, `anchor_assumption_required` -- the
   design doc's own mandatory anchor disclosure) that never resolve away.
   The framework's pre-existing `if diagnostics: needs_attention` check
   was unconditional on `confirmed`, which would have permanently capped
   every confirmed reconstruction at `needs_attention`. Fixed with a
   `_has_attention_worthy_diagnostic()` filter excluding `SEVERITY_INFO`
   -- verified 100% backward compatible (no diagnostic before Slice 8C
   ever used it). A genuine `SEVERITY_WARNING`
   (`inconsistent_bucket_count`, `unexpected_bucket_sample_count` --
   missing/extra-sample bucket-count anomalies, diagnostics only, never
   inserted/deleted rows) still surfaces as `needs_attention` post-
   confirmation, matching every other interpreter's existing precedent.

   **Manual override and Sample Index fallback** (task §J/§N): an
   explicit `interval_seconds` is `provenance=user_specified` (never
   `reconstructed`) and `confidence=high`, with missing/extra-sample
   diagnostics still computed and attached regardless (they describe the
   underlying data, independent of which interval the user applied).
   Switching `interpreter_id` to `sample_index` remains the always-
   available, honest fallback that never fabricates a real-time
   interval -- unchanged from Slice 8B, needing no new code.

   New API: no new endpoints -- `POST .../working/time-axis/interpret`
   and `PUT .../working/time-axis` are reused verbatim, exactly like
   Slice 8B, with `options.anchor_offset_seconds` traveling through the
   already-generic `options` field.

   Frontend: the Interpreter `<select>` gained "Repeated Timestamp
   (Precision Loss) (1 column)"; the shared Detect → diagnostics →
   preview → Confirm flow (Slice 8A) is reused verbatim, with the
   compact summary line extended to show the Suggested interval and the
   anchor assumption in plain language whenever this interpreter is
   active. A collapsed-by-default "Adjust" panel (progressive
   disclosure) reveals a Timing-source radio (Suggested interval /
   Manual interval / Manual rate, converting to `interval_seconds`
   client-side exactly like Sample Index's own Hz/ms toggle) plus a
   "First sample offset" (ms) input feeding `options.anchor_offset_seconds`;
   a "Use Sample Index" button switches the Interpreter select directly.
   Verified: full backend suite 2439 passed (44 new on top of Slice 8B's
   2395), zero regressions; the committed browser smoke test (COMTRADE)
   still passes unchanged; a throwaway (not committed) live-browser
   Playwright UAT script confirmed: a stable-cadence column shows "High"
   confidence with the correct suggested interval and anchor disclosure
   in the compact summary and the diagnostics list; Accept Suggestion
   (Confirmed + Save) reaches "Confirmed"/"Reconstructed"; the Adjust
   flow's manual-interval override correctly switches provenance to
   "User Specified"; "Use Sample Index" switches the interpreter select;
   and an unstable-cadence column shows "Low" confidence with no
   fabricated interval, a `cadence_not_reliable`-driven diagnostic, and a
   server-rejected confirm attempt -- all with zero unexpected console/
   page errors.

   **`[DONE, 2026-09-02]` Slice 8D — Time Irregularity Diagnostics, full
   implementation summary.** A DIAGNOSTIC-ONLY normalization layer over
   the irregular-timing conditions
   CSV_EXCEL_TIME_INTERPRETATION.md §11's own table already named --
   never a new interpreter (no new `interpreter_id`, no new
   `TimeAxisConfiguration`/`TimeAxisDetectionResult` field), never
   readiness policy (no `blocking`/`warning`/`info` mapping, no
   `PreparationIssue` promotion -- both remain Slice 9's own decision).

   **The one real gap this slice fills**: `absolute_datetime`/
   `split_date_time` (Slice 8A) never checked row-to-row timing QUALITY
   at all -- only `elapsed_numeric`/`sample_index` (Slice 8B) and
   `repeated_timestamp_precision_loss`'s own bucket cadence (Slice 8C)
   ever did. A new shared, family-agnostic `_analyze_time_sequence()` in
   `app/services/time_axis_interpreters.py` fills that gap, called only
   once `absolute_datetime`/`split_date_time` already has a RESOLVED
   (non-ambiguous, non-unparseable) reading -- never for a still-open
   case, where no single trustworthy sequence exists to walk. For
   `split_date_time` specifically, the sequence analyzed is the COMBINED
   per-row date+time value, never the date-only column's own sequence
   (always midnight-anchored, not a meaningful timing signal by itself)
   -- a new `include_sequence_diagnostics` parameter on
   `detect_absolute_datetime()` suppresses its own analysis when reused
   internally as `split_date_time`'s date-only sub-detection, so the two
   never double-report the same finding.

   **Five genuinely new diagnostic codes**
   (`app/domain/time_axis.py`): `time_goes_backward`, `large_time_gap`,
   `timestamp_reset_suspected`, `partial_midnight_rollover_suspected`,
   `non_uniform_interval`. Every OTHER condition in §11's table already
   had an established code from an earlier slice (missing/unparseable/
   mixed-format/ambiguous-date-order from 8A; elapsed/sample-index's own
   repeat/backward/gap/non-uniform from 8B; repeated-timestamp/possible-
   missing-sample/cadence-not-reliable from 8C) -- reused verbatim, per
   this slice's own "prefer consolidation... do not rename existing
   public codes unnecessarily" instruction. All five new codes are
   `SEVERITY_WARNING`/`AMBIGUITY_UNAMBIGUOUS` -- the exact combination
   `elapsed_time_goes_backward`/`sample_index_gap` already use -- so
   `resolve_status()` needed ZERO new precedence rules for this slice.

   **The exact detection rule** (deliberately simple, per the task's own
   "do not overengineer statistical detection" instruction): the
   reference "expected local interval" is the MINIMUM positive
   consecutive delta observed in the bounded sample -- robust to a large
   outlier inflating its own comparison point, without a second
   statistical pass. A transition at least 5x that reference is "large"
   in either direction (`large_time_gap` forward,
   `timestamp_reset_suspected` backward); a smaller negative delta is
   the plain `time_goes_backward`; a `partial`-family transition from
   within 2 seconds of the end of the day to within 2 seconds of the
   start of the day is checked FIRST, taking priority over both, and
   reported as `partial_midnight_rollover_suspected` instead -- never a
   fabricated date, never an automatic day increment, never treated as
   ordinary backward-time corruption. `non_uniform_interval` is a
   single, dataset-level finding (never per-transition, mirroring
   `non_uniform_elapsed_interval`'s own shape) for the softer case where
   the remaining ordinary forward steps still vary by more than a ±20%
   tolerance of their own median. Exact repeats (`delta == 0`) are
   deliberately never flagged by this new logic at all --
   `repeated_timestamp_precision_loss` (Slice 8C) already owns that
   condition in full; duplicating even a bare presence check here would
   be exactly the "duplicate the detection algorithm" the task said not
   to do.

   **Bounded, sample-based, never a full scan** -- every new diagnostic
   is computed over the SAME already-bounded (≤50-row) sample every
   interpreter here already receives; a gap or reset outside the sampled
   window is simply not seen. This is documented explicitly as a
   sample-based finding, not a full-dataset guarantee, matching every
   other diagnostic in this framework since Slice 8A.

   **A new `category` axis** (`format`/`ordering`/`gap`/`repeat`/
   `sampling`/`ambiguity`) is available on every `TimeAxisDiagnostic` --
   a COMPUTED property (`app.domain.time_axis.diagnostic_category()`),
   never a stored field, so every diagnostic construction anywhere in
   the codebase (Slices 7/8A/8B/8C included) already has a correct
   category with ZERO call-site changes. Internal/UX grouping only,
   never mapped to readiness severity. `TimeAxisDiagnosticOut.category`
   (schema) echoes it, optional/`None` for any code that predates the
   concept.

   New API: NONE -- `GET`/`PUT .../time-axis` and dry-run
   `POST .../interpret` are reused verbatim; the only schema change is
   the additive `category` field above.

   Frontend: the compact Time Axis summary gained one new row,
   "Diagnostics" ("2 findings"), hidden entirely when there are none --
   the findings THEMSELVES stay inside the existing expanded-review
   diagnostics list (`#wwDataPrepTimeAxisDiagnostics`, already generic
   across every interpreter), never a new permanently-expanded panel.
   Message text already embeds a row-level "near row N" reference
   (e.g. "Interpreted time decreases at 1 point(s)... near row 3"), so
   no frontend string duplication was needed for that.
   Verified: full backend suite 2469 passed (30 new on top of Slice 8C's
   2439), zero regressions (three existing test fixtures across
   `test_time_axis_interpreters.py`/`test_time_axis_service.py`/
   `test_preparation_sources_api.py` needed a chronological-order fixup
   -- each was an artificial day-elimination example that happened to
   also be backward in time, now genuinely ascending); the committed
   browser smoke test (COMTRADE) still passes unchanged; a throwaway
   (not committed) live-browser Playwright UAT script confirmed: a
   backward-time column shows a "2 findings" compact count and the
   correct "near row 3" finding in the expanded review; a midnight-
   rollover column is distinguished from generic backward time with
   neutral wording ("consistent with an ordinary midnight rollover");
   a large-gap column shows neutral wording (never "missing data"); and
   no second top-level panel was introduced anywhere -- all with zero
   console/page errors.
9. **`[DONE, 2026-09-02]` Full Powerwave Readiness Validator.**
   Structural validity; data validity; time-axis validity;
   compatibility with canonical Powerwave requirements (§4/§16).
   Answers exactly one question -- **is the current prepared dataset
   ready to be converted into Powerwave?** -- using the SAME
   `blocking`/`warning`/`info` severity model Slice 6 already
   established, never a second, parallel readiness model:
   **Blocking** = Powerwave cannot safely build or trust the canonical
   waveform dataset; **Warning** = the dataset may proceed, but timing/
   data quality is degraded or imperfect; **Info** = setup/context
   only. Does NOT perform `DisturbanceRecord` conversion, canonical
   waveform creation, plotting, or export -- all explicitly Slice 10+.

   **Extends, never replaces, Slice 6's own transport.** New module
   `app/services/readiness_service.py` -- `collect_readiness_issues()`
   is called ADDITIONALLY by `preparation_issue_service.build_issue_
   summary()` (the SAME function `GET .../issues` already called),
   merged with Slice 6's own unchanged, still-`info`-only
   `collect_preparation_issues()` output into ONE
   `PreparationIssueSummary` via the SAME `summarize_issues()`. No new
   endpoint, no new request/response shape beyond one additive field:
   `PreparationIssueSummary.is_ready` (`blocking_count == 0`, computed
   once so it can never drift out of sync with the counts).

   **Live, never cached** -- exactly Slice 6's own precedent, extended:
   every mutation (cell edit, row exclude/include, header/data-region/
   column-role change, time-axis reconfiguration, undo, redo, reset)
   already bumps `WorkingOverlay.revision`, and `get_time_axis_
   summary()`/`collect_readiness_issues()` both recompute fresh on
   every call -- `evaluated_revision` always equals `current_revision`,
   `is_stale` is always `False`. One frontend gap was found and fixed:
   the Time Axis panel's own Save/Clear handlers previously only called
   a lightweight toolbar-only refresh, never `wwDataPrepFetchIssues()`
   -- now both explicitly re-fetch readiness immediately after a
   time-axis mutation, matching every other mutation path (which
   already refreshes issues via the shared `wwDataPrepFetchPreview()`
   flow).

   **Structure rules** (§C/§D/§E): no Time Axis columns configured at
   all (`time_axis_unconfigured`), a stale/no-longer-Time-Axis column
   reference (`time_axis_unsupported`), or zero columns currently
   carrying the Waveform Channel role (`waveform_channel_missing`) are
   all BLOCKING -- checked directly against `working_overlay.column_
   roles`'s own sparse dict, needing no column-count/dimension lookup
   at all for the waveform-presence check specifically. `header_not_
   selected`/`data_region_unconfigured`/`column_roles_unassigned`
   (Slice 6) are UNCHANGED, still `info` -- `DataRegion`'s own "absent
   means the entire source is active" is a valid, complete semantic,
   never relabeled as a problem (§AG).

   **Time-axis policy is a REUSE, not a re-derivation**: `get_time_axis_
   summary()` (Slice 7-8D, unchanged) is called once per readiness
   check; `UNCONFIGURED`/`UNSUPPORTED`/`REVIEW_REQUIRED` status is its
   own BLOCKING issue (`time_axis_unconfigured`/`_unsupported`/
   `_unresolved`) with no further inspection. For a resolved
   (`CONFIRMED`/`NEEDS_ATTENTION`/`INDEX_FALLBACK`) reading, EVERY
   diagnostic on it is promoted into a `PreparationIssue` reusing that
   diagnostic's OWN code/message/location/`suggested_action`/`details`
   VERBATIM, through one explicit, reviewable policy table:
   `_BLOCKING_TIME_DIAGNOSTIC_CODES` (`unparseable_datetime`,
   `mixed_datetime_format`, `non_numeric_elapsed_value`, `non_numeric_
   sample_index`, `missing_datetime_value`/`_elapsed_value`/`_sample_
   index`, `time_goes_backward`, `elapsed_time_goes_backward`,
   `sample_index_goes_backward`, `timestamp_reset_suspected`) vs
   `_WARNING_TIME_DIAGNOSTIC_CODES` (`large_time_gap`, `non_uniform_
   interval`, `non_uniform_elapsed_interval`, `possible_missing_
   sample`, `unexpected_bucket_sample_count`, `precision_loss_
   suspected`, `partial_midnight_rollover_suspected`, `inconsistent_
   bucket_count`, `repeated_timestamp_detected`, `sample_index_gap`,
   `repeated_elapsed_time`, `repeated_sample_index`, `anchor_
   assumption_required`, `time_only_not_absolute`). Plus one WARNING
   per resolved state that is degraded-but-usable: `sample_index_
   fallback` (§AC), `reconstructed_time` (§AE), `user_specified_time`
   (§AF), `partial_time_reference` (§AD) -- an accepted reconstruction,
   a manual rate/interval/date-order, an index-only fallback, or a
   bare time-of-day reading can all reach `is_ready=True`. Interpreters
   themselves encode NO severity opinion at all -- readiness OWNS
   policy (§W), never the interpreter.

   **Two DELIBERATELY different validation scopes** (§S, the slice's
   own most important rule): the diagnostic promotion above is
   necessarily SAMPLE-based (whatever `get_time_axis_summary()`'s own
   bounded ≤50-row window already saw) -- reused as-is, documented as
   such, never claimed as a full-dataset guarantee. On top of that,
   readiness independently BLOCKS on two full-active-region scans a
   bounded sample cannot cover: `time_value_missing`/`time_value_
   invalid` (every Time Axis cell in the ENTIRE active region, under
   the already-resolved family/date_order) and `waveform_value_
   missing`/`waveform_value_invalid` (every CURRENT Waveform Channel
   cell). A single new streaming generator,
   `app.services.preparation_preview_service.iterate_active_region_
   rows()`, powers both -- ONE single pass per readiness check (never
   two), yielding one row at a time with the SAME working-overlay
   application/`is_header`/`in_active_region` flags the bounded preview
   already computes, never a second materialized copy of the dataset
   and never repeated re-scans-per-page the way chunked `preview_
   preparation_source()` calls would cause for CSV. Excluded rows, the
   header row, and out-of-region rows are all skipped, matching every
   other row-level check in this codebase. `ERR`/`N/A`/`#VALUE!`/
   `12.3?`/arbitrary text in a Waveform Channel cell is preserved
   byte-for-byte and reported (never coerced to zero/null) -- reusing
   `_to_float()` verbatim, the exact same numeric-parse function Slice
   8B's own elapsed/sample-index diagnostics already use.

   **Digital channels are explicitly deferred** (§N) -- the column-role
   model has no dedicated digital role today; `digital_value_invalid`
   exists in the controlled vocabulary for when one does, but is never
   produced this slice. A digital-style column today is classified
   `waveform` (or left `unknown`/`metadata`) and gets the SAME numeric
   policy as any other column of that role -- no invented `TRUE`/
   `FALSE`/`ON`/`OFF` mapping.

   **Never repairs anything** -- no row is ever deleted, inserted,
   sorted, or reordered; no timestamp is ever synthesized; no waveform
   value is ever interpolated or coerced. Readiness only ever APPENDS
   `PreparationIssue` entries and returns them; the engineer resolves
   every finding by editing, excluding, or reconfiguring.

   Frontend: the EXISTING Preparation Status panel (Slice 6's own
   shell, which already had a documented "shell for a future Needs
   Attention readiness state" comment anticipating exactly this) gained
   a real two-state headline -- "Needs Attention" (`N issue(s) must be
   fixed · M warnings`) or "Ready for Powerwave" (`N Blocking · M
   Warnings · K Info`), colored via `--ok`/`--error` -- with NO
   "Continue to Powerwave" button anywhere (task's own "prefer not to
   expose a working action that cannot yet complete... choose the least
   misleading UX" instruction, taken literally: the headline text alone
   communicates the state). The detailed grouped issue list stays
   collapsed by default, unchanged; a new "Go to row" jump (alongside
   the existing "Go to worksheet" one) reuses the SAME paged-preview
   offset mechanism "Go to Last Rows" already established -- no second
   navigation framework.
   Verified: full backend suite 2515 passed (46 new on top of Slice
   8D's 2469), zero regressions (four pre-existing Slice 6/8D tests
   updated for the new, correctly-blocking default state of a totally
   unconfigured source); the committed browser smoke test (COMTRADE)
   still passes unchanged; a throwaway (not committed) live-browser
   Playwright UAT script confirmed: an unconfigured source shows "Needs
   Attention" with both new blocking findings listed in the (initially
   collapsed) detail view; configuring Time Axis + Waveform Channel
   reaches "Ready for Powerwave" (with a `timezone_unspecified` warning
   for the naive-datetime fixture used); editing a bad waveform cell
   (or excluding its row) immediately clears readiness back to Ready,
   with NO extra manual refresh needed; a Sample Index fallback source
   reaches Ready with its own warning, never blocking -- all with zero
   console/page errors.
10. **`[DONE, 2026-09-03]` Canonical `DisturbanceRecord` conversion.**
    The third and final stage of "Slice 8 → interpret; Slice 9 →
    validate; Slice 10 → convert" -- no new inference occurs here; the
    conversion adapts an already-Ready prepared dataset to Powerwave's
    existing waveform contract, never weakens that contract.

    **Three owner-approved rules governed this slice, all enforced by
    `app/services/preparation_conversion_service.py`
    (`convert_preparation_source()`)**: (1) readiness is RE-CHECKED
    against the current working revision at conversion time -- never
    trusts stale frontend state -- by calling the SAME `build_issue_
    summary()` Slice 9 already built, raising `ConversionNotReadyError`
    if `is_ready` is now `False`; (2) index-only is NOT canonical-
    seconds-ready -- a `sample_index` family with `interval_seconds is
    None` (Sample Index fallback, still only a Slice 9 WARNING, still
    `is_ready=True`) is REFUSED with `ConversionRequiresIntervalError`,
    a conversion-capability constraint, never a readiness-policy change;
    (3) no fake dates or trigger timestamps -- an unknown absolute start
    or trigger is represented as `None`, never a `2000-01-01`/
    `1970-01-01`/`trigger_time = start_time` sentinel.

    **Time-axis conversion is a REUSE, not a re-derivation** (mirroring
    Slice 9's own precedent): the SAME `TimeAxisInterpreter.build_
    preview_rows()` the Time Axis review UI already calls is invoked
    over the FULL active region (never the bounded ≤50-row sample) to
    get each row's already-interpreted string, which conversion then
    parses into a raw float and maps to canonical seconds via ONE
    uniform rule across every convertible family:
    `canonical[i] = raw[i] - raw[0]` (relative to the first active
    sample). `absolute` additionally preserves the real first absolute
    timestamp (with timezone/offset, when present) in `TimingInformation.
    start_time`; `elapsed`/`partial` preserve the true relative values
    with no fabricated calendar time, `start_time=None`; `sample_index`
    with a known `interval_seconds` computes
    `time_seconds = (index - first_active_index) * interval_seconds`,
    never assuming the first index is 0 or 1; `sample_index` with an
    unknown interval is refused per rule (2) above; a Manual-family
    configuration (which implements no `build_preview_rows()` at all) is
    refused with `ConversionUnsupportedInterpreterError`. Reconstructed
    (`repeated_timestamp_precision_loss`) and user-specified
    (manually-entered rate/interval) timing are consumed as already
    confirmed -- conversion never recalculates cadence or reinterprets
    date order.

    **Canonical-model hardening, deliberately minimal** (§Q/§F of the
    owner task spec): the ONLY required change turned out to be
    widening `TimingInformation.start_time`/`.trigger_time` from
    required `datetime` to `datetime | None` -- discovered, not assumed,
    by tracing every consumer of `.start_time`/`.trigger_time`
    (`time_grouping.derive_time_groups()`, `timestamp_placement_
    offset_s()`, `synchronization_service.py`,
    `calculated_channel_service.py`): every one of them ALREADY branches
    on `is None`, because `SourceMetadata.start_time`/`.trigger_time`
    were already `Optional` since Phase 5B/DEC-048 -- "existing waveform
    integration" needed zero changes, a major scope de-risking finding.
    `nominal_frequency` was deliberately NOT widened (unlike `start_
    time`/`trigger_time`) because `synchronization_service.py` consumes
    it as a required float for event-detection sensitivity -- widening
    it would be exactly the "redesign existing waveform integration"
    the task forbade. A converted source instead gets a documented
    conventional default (`_DEFAULT_NOMINAL_FREQUENCY_HZ = 50.0`) plus
    an explicit `nominal_frequency_assumed: true` flag in provenance.
    New additive `SamplingInformation.is_uniform` (defaults `True`,
    matching COMTRADE's unchanged existing behavior) flags genuinely
    irregular canonical timing honestly, using a ±1% relative interval
    tolerance (matching Slice 8B's own `non_uniform_elapsed_interval`
    precedent) -- an irregular source keeps its true per-sample
    `waveform_data["time"]` array (always authoritative, per
    `DisturbanceRecord.duration_seconds()`'s own pre-existing "prefer
    the time column" behavior) and never claims one fabricated average
    rate. `DisturbanceRecord.validate()` itself gained the finite/
    non-decreasing time-column check and a `samples_per_rate` row-count
    consistency check the "deliberately not part of this sequence" note
    below used to defer -- both needed directly to satisfy this slice's
    own §Q requirement ("after construction, run `validate()`... time
    finite; time ordering valid; sampling metadata internally
    consistent") and both verified to be a no-op for every real COMTRADE
    record (`TestComtradeRegressionUnaffected`,
    `test_disturbance_record_domain.py`).

    **Waveform channels**: exactly `active data region - excluded rows +
    current working cell overrides`, in source column order (never
    reordered); Metadata/Quality-Status/Ignore/Unknown-role columns
    never become channels. Channel names use the configured header
    label when available, else a deterministic neutral name (the
    spreadsheet column letter, e.g. `"B"`); a duplicate label never
    loses a channel -- the first occurrence keeps its label verbatim,
    every later occurrence gets a `__<spreadsheet-column-letter>` suffix
    (e.g. `Voltage`, `Voltage__C`, `Voltage__D`), with the original
    label preserved as each channel's own `description`.

    **Provenance**: a new, purely additive `SourceMetadata.preparation_
    provenance: dict | None` field (following the same "additive,
    defaulted, no existing provider sets it away from `None`" precedent
    `waveform_form`/DEC-048 already established) retains source format,
    original filename, worksheet name/index, preparation revision, time
    family/provenance, interpreter id, header row, data region, and
    excluded-row count -- enough to answer "where did this waveform come
    from and how was its time axis established?" without hard-coding a
    single CSV/Excel-specific field into any core waveform schema.

    **Idempotency needed zero new code**: a successful conversion
    removes the `PreparationSession` from its registry (mirroring
    COMTRADE's own upload flow, which never leaves a "Needs Preparation"
    ghost row behind either), so a repeated `POST .../convert` against
    the same, now-gone source naturally 404s via the ALREADY-EXISTING
    `SourceNotFoundError` path.

    **Revision-race protection**: readiness is re-evaluated and the
    canonical record is built from the SAME resolved session/revision;
    since this backend has no separate "commit" step and the in-memory
    registries are not concurrently mutated mid-request, no observed
    revision-changed race was reproducible in testing -- the
    `ConversionRevisionChangedError` class exists in the taxonomy for a
    future concurrent-mutation scenario but is not yet a reachable path.

    **API**: `POST .../preparation-sources/{source_id}/convert`, returning
    the SAME `SourceSummaryOut` shape a COMTRADE upload's `POST
    .../sources` already returns -- no bespoke response shape. New
    `Conversion*Error` taxonomy in `app/services/errors.py`
    (`ConversionNotReadyError`/`ConversionRequiresIntervalError`/
    `ConversionUnsupportedInterpreterError`/
    `ConversionRevisionChangedError`/`ConversionValidationError`), mapped
    to HTTP 409 (state conflict) except `ConversionValidationError`
    (HTTP 500, an unexpected internal contradiction) -- readiness issues
    stay `PreparationIssue`s, runtime conversion failures stay these
    distinct exception types, never blurred together.

    **Frontend**: the EXISTING Preparation Status panel (Slice 6/9's own
    shell) gained the actual "Continue to Powerwave" action, shown only
    when `is_ready` AND conversion-capable; the index-only-without-
    interval case instead shows a "Ready with limitations" notice
    ("Sample Index is currently used without a real-time interval. Add a
    sampling rate or interval before continuing to Powerwave.") plus a
    "Configure Time Axis" shortcut that expands the existing Time Axis
    panel -- never an enabled Continue action that would silently
    pretend `sample N == N seconds`. On success, the new source is
    registered via the SAME `refreshAllSourceViews()` every other
    upload path already calls, then the user is navigated into the
    EXISTING waveform workflow via `openRecordingForAnalysis()` -- the
    SAME entry point a COMTRADE "Open / Analyse" row uses -- never a
    CSV/Excel-specific plotting page (this slice's own explicit
    architectural goal). On failure, the user stays in Data Preparation
    with every existing preparation control intact; no partial
    registration.

    Verified: full backend suite 2583 passed (68 new: 21 domain-hardening
    + 39 conversion-service + 8 API), zero regressions; the committed
    browser smoke test (COMTRADE) still passes unchanged with zero
    console/page errors; a throwaway (not committed) live-browser
    Playwright UAT confirmed: a Ready source shows "Continue to
    Powerwave" and converting it opens the existing waveform workflow
    with a plottable channel; an index-only Ready source shows the
    "Ready with limitations" notice with NO enabled Continue action
    (a real CSS bug -- an unguarded `display: flex` on the action
    container beating the `[hidden]` attribute by author-vs-UA-
    stylesheet origin, the SAME class of bug already fixed elsewhere in
    this file for `#workspaceRow[hidden]` -- was caught and fixed by
    this exact UAT run); a not-ready source's failed conversion attempt
    leaves the preparation source fully intact afterward.
11. **Existing waveform integration.** Normal existing Powerwave
    behavior — plotting, source handling, Time Groups, synchronization,
    calculated-channel compatibility, measurement/per-unit compatibility
    where applicable. No weakening of existing rules (principle 5).
12. **Cleaned-data export.** Export working/prepared data as CSV/XLSX;
    original source remains unchanged (§10).
13. **Progressive automation and hardening** (future scope, illustrative
    not exhaustive): header suggestions; time-column suggestions; column
    classification suggestions; saved import profiles; vendor-specific
    interpreters; additional time formats; additional diagnostics;
    performance hardening. Automation remains a convenience layer over a
    correct manual workflow, never a replacement for it.

**Per DEC-072 point 4**: hardening `DisturbanceRecord.validate()` itself
with a monotonicity/finiteness check was deliberately deferred out of
slice 1 and every slice through Slice 9 — not independent, freestanding
canonical-contract work, but Slice 10's own conversion-time defensive
check (§Q of that slice's task spec: "conversion must still fail
defensively if canonical construction encounters contradiction"). Time
validity for CSV/Excel data is enforced FIRST by Slice 9's Readiness
Validator (`Working Dataset → Readiness Validator → finite/valid/
monotonic time confirmed → Slice 10's conversion service →
DisturbanceRecord.validate()` as a final defensive check, not the
primary gate) — see Slice 10 above for the exact minimal check added
(finite + non-decreasing time column, `samples_per_rate` row-count
consistency) and its zero-impact COMTRADE regression verification.

---

## 15. Time-axis extensibility — explicit statement

**See [CSV_EXCEL_TIME_INTERPRETATION.md](CSV_EXCEL_TIME_INTERPRETATION.md)
(2026-09-01) for the full design specification this section's own
finding was later formalized into** — semantic families, provenance,
fallback hierarchy, confidence model, the interpreter registry concept,
and the exact proposed Slice 7/Slice 8 scope. That document is now the
authoritative reference for time-axis design; this section is retained
for historical/audit continuity, not duplicated.

**`[OWNER DECISION]` (DEC-072 point 6, 2026-08-30)**: the time-axis
format list stays permanently open-ended; no future CSV/Excel work may
introduce a closed enumeration. The `[FACT]` finding below (already
consistent with this) is retained as its supporting evidence.

**`[FACT]`, restated from §4/§5 for emphasis per this audit's own
requirement**: the current codebase enumerates exactly one time
reference type in production (`timing_reference == "absolute"`, always
true for COMTRADE) plus one implicit fallback bucket (anything else,
currently unreachable). It does **not** hard-code a closed list of
supported time-axis formats anywhere — `time_grouping.py`'s own
`time_reference_type_for_source()` treats every non-`"absolute"` value
identically today, which is a permissive default, not a whitelist. A
future CSV/Excel importer introducing elapsed time, sample-index time,
Excel serial dates, separate date+time columns, or a format not yet
encountered can each become its own concrete interpreter feeding the
same two-value `timing_reference` signal (or, if finer distinctions ever
prove necessary downstream, extending it) without altering
`time_grouping.py`, `synchronization.py`, or any waveform-rendering
code. **This document does not propose a closed list of supported
time-axis formats, consistent with the owner's own instruction that this
list must remain open-ended.**

---

## 16. Powerwave readiness philosophy — explicit statement

**`[OWNER DECISION]` (DEC-072 points 4 and 5, 2026-08-30)**: time
validity is enforced first by the CSV/Excel preparation/readiness gate,
not by hardening `DisturbanceRecord.validate()` as a first step (point
4); and a source with no defensible absolute timestamp must never
receive a fabricated absolute anchor — no sentinel-timestamp fallback,
ever (point 5). The `[PROPOSAL]` reasoning below, already consistent
with both, is retained as supporting analysis.

**`[PROPOSAL]`, restated for emphasis**: nothing found in this audit
suggests weakening any existing Powerwave behavior would ever be
necessary to accommodate CSV/Excel. The `DisturbanceRecord` contract
(§4) is already the one canonical representation every provider must
satisfy; a CSV/Excel-specific branch anywhere downstream of that
boundary (in Time Groups, synchronization, calculated channels,
measurement groups, or waveform rendering) would be a new architectural
problem this codebase does not have today, not a necessity forced by the
current design. The strict Readiness Gate the owner has asked for
(principle 6) is therefore best understood as *the same
`DisturbanceRecord.validate()`-shaped check COMTRADE already trivially
satisfies by construction*, made real, severity-aware, and actually
wired into the upload flow — not a parallel, format-specific
correctness model.

---

## 17. Non-destructive preparation — explicit statement

**`[FACT]`, cross-reference**: DEC-072 point 3's approved
`PreparationSession` sketch (§9) already names an "edit/correction
overlay" as one of its own fields, consistent with the design reference
below — the exact overlay mechanism itself remains undecided (§18).

**`[PROPOSAL]`, restated for emphasis**: the channel-presentation-
override mechanism (§8) is the strongest existing precedent in this
codebase for principle 3 (corrections as an overlay, never a mutation of
raw values) and should be the starting design reference for the Working
Dataset's own correction model — an overlay map keyed by stable identity
(row/column reference, analogous to `sourceId::channelName`), merged
with canonical raw data only at read time, fully reversible by clearing
the overlay entry, never touching the immutable raw representation
underneath it. This is offered as a design reference, not an approved
implementation — the exact mechanism remains undecided per this audit's
own scope (introduction to the task: "the implementation mechanism is
NOT yet decided").

---

## 18. Open questions register

**Resolved as of DEC-072 (2026-08-30)** — retained here for traceability,
not as open items any more:

| # | Original question | Resolution |
|---|---|---|
| 1 | Does in-progress Working Dataset state fall under DEC-015? | Resolved — DEC-072 point 1: temporary session-scoped retention is permitted and does not reopen DEC-015 |
| 2 | What shape does severity-tiered validation take? | Resolved (principle) — DEC-072 point 2: a new, separate preparation-scoped issue model, `ImportServiceError` unchanged. Exact shape stays open — see item 2 below |
| 3 | Where does raw/working state physically live? | Resolved (principle) — DEC-072 point 3: a hybrid, reference-holding `PreparationSession`, never full raw+working duplication. Exact mechanism stays open — see item 1 below |
| 5 (orig.) | Should `DisturbanceRecord.validate()` hardening be scoped ahead of CSV/Excel work? | Resolved — DEC-072 point 4: explicitly deferred, independent future work; not part of the CSV/Excel critical path (§14) |

**Resolved by Slice 1 implementation (2026-08-30)**:

| # | Original question | Resolution |
|---|---|---|
| 1 (raw storage) | Exact temporary-storage mechanism for RAW CSV bytes | Resolved for Slice 1's own scope — `PreparationSessionRegistry`, an in-memory sibling registry (see §9's own `[FACT]` note). **Not yet resolved** for a future Working Dataset's own overlay/edit state (Slice 4) or paged/windowed large-file access (Slice 3) — those are separate storage questions this slice's raw-bytes-only registry does not answer. |

**Resolved by Slice 2 implementation (2026-08-30)**:

| # | Question | Resolution |
|---|---|---|
| 1 | Which Excel library/tooling, and does it extend to raw-bytes storage for Excel too? | `openpyxl==3.1.5`, `read_only=True` streaming discovery, zero temp files for an in-memory `BytesIO` source (verified directly). Raw workbook bytes reuse the SAME `PreparationSessionRegistry` Slice 1 already built for CSV — no second storage mechanism needed for the second format. |
| 2 | Should `.xls` be supported alongside `.xlsx`? | No — deferred. `.xls` would need `xlrd`, a separate, unmaintained dependency (its 2.x line dropped `.xlsx` support entirely), not currently justified. `.xlsx` only, per the task's own pre-authorized fallback. |
| 3 | Worksheet descriptor shape? | `WorksheetInfo{index, name, visible, row_count, column_count}` — the last two best-effort/`None`-able from `max_row`/`max_column`, never a full-sheet scan. |
| 4 | Single-sheet auto-selection behavior? | Auto-selected (`selected_worksheet_index=0`) only when the workbook has exactly one worksheet total (visible or hidden); two or more (even one visible + one hidden) requires explicit selection — per the task's own pre-authorized convenience option. |

**Resolved by Slice 3 implementation (2026-08-31)**:

| # | Question | Resolution |
|---|---|---|
| 1 | Exact frontend grid/virtualization technology | None — a plain server-paginated DOM `<table>`, no library. Justified directly by the task's own guidance ("a simple paged table is preferable to over-engineering virtualization at this stage") and by the server-side bound itself (≤1000 rows/page) making naive rendering safe. Remains compatible with introducing real virtualization later if a future slice's own UX needs it. |
| 2 | Exact preview API shape | `GET .../preparation-sources/{id}/rows?offset=&limit=` → `{source_id, selected_worksheet_index, offset, limit, returned_row_count, total_row_count, total_row_count_basis, column_count, column_count_basis, rows: [{row_number, cells}]}`. `offset`/`limit` bounds enforced via `Query(...)` constraints (0/1000 default/max), matching the existing `point_budget` precedent — no new range-validation error class needed. |
| 3 | Whether/how a large raw CSV/Excel file needs paging at the *storage* layer | Resolved for Slice 3's own scope: CSV needs one full in-memory-text pass to get exact totals (memoized after the first request per session); Excel needs no extra scan at all (reuses Slice 2's own upload-time `WorksheetInfo` totals). Neither format's raw bytes are ever loaded a second, larger way — the existing Slice 1/2 in-memory registry already holds everything needed. **Still not resolved**: whether the registry's own "hold the whole file's raw bytes in memory" model itself needs to change for very large files — that remains a storage-layer question, not a preview-algorithm one (see the still-open items below). |

**Resolved by Slice 4 implementation (2026-08-31)**:

| # | Question | Resolution |
|---|---|---|
| 1 | Exact overlay/delta implementation for non-destructive edits | `app.domain.working_overlay.WorkingOverlay` — a sparse, edit-count-proportional overlay (dict/set keyed by stable `(worksheet_index_or_None, row_number, column_index)`-shaped identity), merged with raw data only at preview-read time, exactly the §17 design reference's own "overlay map... merged with canonical raw data only at read time, fully reversible" shape. Undo/redo included (bounded 200-entry operation history). |

**Genuinely unresolved — must not be resolved prematurely** (owner's own
explicit list; do not pick a mechanism ahead of the implementation
slices without further owner input):

| # | Question | Decision mode | Needed before |
|---|---|---|---|
| 2 | Exact API shapes for readiness beyond what Slices 1-5 already established for preparation-source identity/upload/worksheet selection/raw+working preview/working-overlay mutation/header-data-region-column-role mapping | `[DECISION MODE: ANALYSIS]`, once slice work actually starts | Slice 6 |
| 3 | Exact timestamp-interpreter list to build first | `[DECISION MODE: ANALYSIS]` — the *list itself* stays open per DEC-072 point 6; only the first-slice subset needs choosing | Slice 8 |
| 4 | Exact saved-profile design (import-profile reuse across files) | `[DECISION MODE: DEFER]` | Slice 13 |
| 5 | Whether the underlying in-memory "hold the whole raw file" registry model itself needs to change for a genuinely huge CSV/Excel file (Slice 3's own preview algorithm is bounded per-request, but the registry still holds the entire original upload in memory regardless of size — a separate storage-layer question from anything Slice 3 itself needed to solve) | `[DECISION MODE: DEFER]` | Not currently scheduled |
| 6 | Permanent persistence of uploaded CSV/XLSX (beyond an active preparation session) | `[DECISION MODE: DEFER]` — explicitly out of scope unless a future, separate decision introduces it (DEC-072 point 1) | Not currently scheduled |
| 7 | Exact future `DisturbanceRecord.validate()` hardening (monotonicity/finiteness check) | `[DECISION MODE: DEFER]` — independent canonical-contract work, deliberately outside CSV/Excel scope (DEC-072 point 4) | Not currently scheduled |
| 8 | Whether `.xls` legacy support is ever added later (would require an explicit owner decision to accept the `xlrd` dependency, since Slice 2 deliberately did not) | `[DECISION MODE: DEFER]` | Not currently scheduled |
| 9 | Encoding detection for CSV decoding (Slice 3 uses a fixed UTF-8-with-replacement decode, disclosed as a simplification, not a solved problem) | `[DECISION MODE: DEFER]` | Not currently scheduled |
| 10 | Optional per-column "last populated row" diagnostic (data-region end-selection UX refinement's own explicitly optional scope item) — deferred because computing it correctly requires a genuinely NEW, more expensive scan than anything already cached: CSV would need an O(rows × columns) per-cell blankness pass (today's `ensure_csv_totals_cached()` only counts rows/max-width, never inspects individual cell content), and Excel would need a full-sheet materialization, contradicting that format's own established "never a full-sheet scan" principle (§ Excel strategy) | `[DECISION MODE: DEFER]` — revisit only if a future slice's own scope already requires a comparable scan for an unrelated reason | Not currently scheduled |

**`[FACT]`**: how a sample-index-only time axis is represented in the
canonical contract (original item 4 — no field exists for it today, see
§4) remains unresolved and is folded into open item 5 above (it is a
concrete instance of "which timestamp interpreters to build first," not
a separate question) — needed before slice 8, not slice 6 as originally
estimated (slice numbering shifted under the owner's revised sequence,
§14).

If any of the eight genuinely-open items above turns out to require a
decision *before* Slice 1 can safely begin (i.e. the current code
imposes a hard constraint this document did not anticipate), that must
be reported explicitly when Slice 1 is actually scoped — not resolved
silently in advance.
