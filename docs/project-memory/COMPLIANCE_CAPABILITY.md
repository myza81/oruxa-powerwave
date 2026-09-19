# Compliance & Capability

**Status: Slice 1 (workspace shell only) implemented, 2026-09-19.** No
engineering calculation, profile management, normalization, alignment
logic, or persistence exists yet — this document records the product
shape as it currently stands, deliberately provisional, and the explicit
scope boundary of what has NOT been built yet.

## Compliance is a top-level function, independent of Analysis

`Compliance` is its own first-class application page (`shell.currentPage
=== "compliance"`, `#pageCompliance`), reached from its own main-sidebar
entry — **not** another Analysis-menu analyzer. It does not register as
an Engineering Context consumer, does not mount the shared Playback
control surface, has no Analysis Input Source (Recording/Manual), and
carries no analyzer-specific state of any kind (no Phasor/Overcurrent/
Impedance/Sequence/Distance coupling). Opening Compliance does not
initialize, reset, or alter Playback, Analysis Input Source, Engineering
Context analyzer state, Sequence state, or Distance state — verified
directly (`browser-tests/compliance.spec.js`, "opening Compliance does
not touch Playback, Analysis Input Source, or any analyzer state").

Why independent rather than a sixth analyzer: compliance/capability
assessment is a genuinely different engineering question from the
existing Analysis-menu family (Phasor/Overcurrent/Impedance/Sequence/
Distance all answer "what did this event's signals actually do,"
Compliance answers "does a measured quantity satisfy an external
requirement/capability curve") and does not naturally share the
Analysis shell's own Engineering Context/Playback/Related-Waveforms
infrastructure (Compliance's own Event Alignment step, for one, is
expected to need a DIFFERENT, standalone time-reference model, not the
shared workspace clock every Analysis analyzer already consumes). Kept
as its own top-level page rather than forcing an awkward fit into the
existing shared shell.

Final main-menu order (implemented):

```text
Recordings
Waveform
Table
Calculated Channels
Analysis
Compliance
```

## Slice 1 supports only the Voltage workspace shell

```text
Compliance
└── Voltage
```

One Compliance function exists today (`wwComplianceActiveType ===
"voltage"`, `#wwComplianceTypeVoltageBtn`), reusing the exact
`.ww-analysis-type-nav`/`.ww-analysis-type-item` sub-nav component the
Analysis page already established (same visual language — task's own
explicit "do not introduce a separate visual design language"
instruction) so a future second function (e.g. Current) slots in the
same way a sixth analyzer would. The page heading currently reads
**"Voltage Compliance & Capability"** — intentionally provisional
wording, explicitly subject to change through owner UAT.

## Current workflow hypothesis

```text
Measurement
→ Reference Layers
→ Event Alignment
→ Comparison Chart
→ Results
```

Rendered top-to-bottom so the intended engineering workflow reads
directly off the screen without needing an explanation: Measurement/
Reference Layers/Event Alignment are three short, compact configuration
cards side by side (`.ww-compliance-config-row`), followed by the
Comparison Chart (`.ww-compliance-chart-panel`, deliberately the
single largest section on the page — sized via `aspect-ratio: 16/7`
with `min-height: 320px`/`max-height: 520px`, never a tiny fixed
height), followed by Results.

Every section shows a neutral empty state only — no fabricated
engineering values, no fake LVRT/HVRT curves, no fabricated
Compliant/Boundary Breached/Within Capability verdict:

| Section | Empty state |
|---|---|
| Measurement | "No assessment quantity selected" |
| Reference Layers | "No reference layers added" |
| Event Alignment | "No event reference set" |
| Comparison Chart | "No voltage assessment configured" |
| Results | "Results will appear after a measurement, reference layer and event alignment are configured." |

A few controls exist as visibly **disabled** placeholders purely for
layout UAT (task's own explicit allowance) — an "Assessment quantity"
select, a "+ Add Reference" button, and Shift-left/t0/Shift-right
alignment buttons — none of them wired to any real behavior.

## UI/UX is intentionally subject to owner UAT and may change

Workflow order, section placement, chart prominence, terminology,
density, and spacing are all explicitly UAT-subject per the task that
built this slice — not treated as settled product decisions. No
DECISIONS.md architectural entry was needed for the layout/terminology
choices themselves (see below for the one architectural point that WAS
recorded).

## No calculation/profile/persistence logic exists yet

Explicitly out of scope for Slice 1 (and not implemented anywhere in
this slice):

```text
Malaysian Grid Code profile
OEM profiles
profile JSON / profile import/export
instantaneous-to-RMS conversion
L-G/L-L normalization
per-unit conversion
positive-sequence calculation
t0 alignment logic
reference curves
multiple layer rendering
compliance evaluation / breach calculation / margin calculation / tolerance
backend endpoints
database/storage
localStorage
```

`#pageCompliance` is static markup with a single, no-op render hook
(`wwRenderCompliancePage()`) — there is no state to bootstrap, fetch,
reset, or persist. `backend/tests/test_frontend_compliance.py`'s
`TestComplianceOutOfScopeSlice1` class guards this boundary directly
(no profile/evaluation identifiers, no `/api/v1/compliance` endpoint, no
`localStorage` usage anywhere inside the Compliance page).

## Files

- `frontend/index.html` — `#mainNavComplianceBtn` (main sidebar),
  `#pageCompliance` (page markup), `shellSetCurrentPage()` (page
  lifecycle), `wwRenderCompliancePage()`/`wwComplianceSyncTypeNav()`
  (JS), `.ww-compliance-*` CSS.
- `backend/tests/test_frontend_compliance.py` — structural regression
  (nav registration/order, panel existence, Voltage sub-nav, the five
  section identifiers in order, empty-state wording, out-of-scope
  guards).
- `browser-tests/compliance.spec.js` — real-browser coverage (menu
  order, page open/close, sub-nav, all five sections, chart dominance,
  navigation lifecycle/isolation from Analysis, 1366px/1024px
  responsive/no-overflow checks).

## Related documents

- [DECISIONS.md](DECISIONS.md) (top-level/independent-from-Analysis
  architectural decision, if recorded there).
- [CURRENT_STATE.md](CURRENT_STATE.md), [HANDOFF.md](HANDOFF.md).
