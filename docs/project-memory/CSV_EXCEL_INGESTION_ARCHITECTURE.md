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
8. **`[DESIGN COMPLETE, 2026-09-01]` Initial time-axis interpreters.**
   The safest initial cases only — do not attempt every possible
   time-axis format at once. Exact proposed initial interpreter set
   (single-column absolute datetime; Date + Time; elapsed numeric time;
   sample index; repeated-timestamp/lost-precision detection) recorded
   in
   [CSV_EXCEL_TIME_INTERPRETATION.md §19](CSV_EXCEL_TIME_INTERPRETATION.md#19-slice-8-scope--initial-interpreters).
   Not yet implemented.
9. **Full Powerwave Readiness Validator.** Structural validity; data
   validity; time-axis validity; compatibility with canonical Powerwave
   requirements (§4/§16).
10. **Canonical `DisturbanceRecord` conversion.** Only Powerwave-ready
    working datasets may convert; no downstream CSV/Excel special-casing
    (§13).
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

**Deliberately not part of this sequence, per DEC-072 point 4**:
hardening `DisturbanceRecord.validate()` itself with the new
monotonicity/finiteness check is deferred, independent future canonical-
contract work — not slice 1, and not bundled into any slice above. Time
validity for CSV/Excel data is enforced first by slice 9's Readiness
Validator (`Working Dataset → Readiness Validator → finite/valid/
monotonic time confirmed → Normalizer → DisturbanceRecord`).

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
