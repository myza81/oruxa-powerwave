# Powerwave Waveform Tool Icon System

Status: AUTHORITATIVE DESIGN-SYSTEM REFERENCE

This document records the global Powerwave Waveform Tool Icon System
(DEC-140): the one shared icon registry every waveform-capable page draws
its common tool icons from, which icon each semantic function uses and
why, and the capability matrix that decides which tools a given page
enables. It exists so a future agent never needs to redraw a common tool
icon from scratch, or guess whether two pages' buttons are "close enough"
— they either name the same registry key, or there is a recorded reason
they don't.

Read this document before adding or changing any waveform-capable
toolbar icon. See [DECISIONS.md — DEC-140](DECISIONS.md#dec-140--the-global-powerwave-waveform-tool-icon-system-one-shared-icon-registrycapability-matrix-replaces-page-specific-duplicated-icon-markup)
for the durable rule this document implements.

---

## 1. The rule

> Powerwave waveform-capable pages use one global tool system. Shared
> tools reuse the same semantic icon, tooltip wording, compact control
> treatment and interaction language. Individual pages own their own
> state and enable only the capabilities valid for that page.

> Powerwave selects icons from the approved shared icon system; coding
> agents must not independently redraw common tool icons.

This is an **app-wide** rule, not an Event Reconstruction-only one. Today
it covers Waveform and Event Reconstruction (the only two waveform-capable
pages — see §3). Any future waveform-capable page reads this document
first and reuses what already exists here.

---

## 2. Architecture

- **`WW_TOOL_ICONS`** (`frontend/index.html`, defined immediately before
  the Phase 3B recording-format section, near the top of the script) is
  the one registry: `{ SEMANTIC_KEY: "<svg ...>...</svg>" }`.
- A control's markup carries `data-ww-icon="SEMANTIC_KEY"` on an empty
  `<span class="ww-icon">` — it never repeats the `<svg>` inline.
- **`wwApplyToolIcons(root = document)`** fills every `[data-ww-icon]`
  placeholder under `root` from the registry. Called once, synchronously,
  for the whole static page (before any other init-time wiring, so there
  is no flash of an empty icon), and again, scoped, by
  `wwCreateTimeGroupCanvasDom()` for each Time Group canvas it builds
  later (the one piece of toolbar markup that is itself built from a JS
  template, not static HTML).
- "The same function on two pages uses the same icon" is therefore a
  structural fact — both controls name the identical registry key — not
  two independently-typed `<svg>` blocks that happen to agree.

### Geometry contract (`[FACT]`)

Every icon in this codebase already renders through the one shared CSS
rule:

```css
.ww-icon svg {
    width: 18px; height: 18px;
    stroke: currentColor; fill: none;
    stroke-width: 1.5;
    stroke-linecap: round; stroke-linejoin: round;
}
```

— an **18-unit coordinate space**, not Lucide's native 24-unit one, with
**one house stroke weight**. Pasting a Lucide icon's own markup verbatim
(`viewBox="0 0 24 24"`, authored assuming `stroke-width: 2`) under this
rule renders it measurably **thinner relative to its own size** than an
18-unit-native icon — the same `stroke-width: 1.5` is a smaller fraction
of a wider path. That is a real, visible weight mismatch next to every
existing Powerwave icon, which is exactly what one global icon system
must not have.

**Every icon in the registry is therefore hand-adapted into this file's
own existing 18-unit grammar — never a raw Lucide paste.** Lucide is used
as a source of **shapes/metaphors** (§4), not as literal markup. This is
the one, intentional departure from the icon system's own general "prefer
24x24, Lucide verbatim" framing: the existing, already-shipped 18-unit/
1.5-stroke-weight contract is what this codebase actually has, and
matching it is what keeps every icon — old and new, library-sourced and
composite alike — visually consistent, which is the actual goal that
framing exists to serve.

### Icon-selection discipline

For every semantic function, in order:

1. An icon Powerwave already uses — reused verbatim.
2. Failing that, a recognised standard metaphor (Lucide, redrawn per the
   geometry contract above).
3. Failing that, a composite: an existing/standard base plus one small
   modifier, in the same family as its siblings.
4. A fully custom standalone shape — last resort.

No two icons for the same function. No per-icon arbitrary geometry/
weight/style.

---

## 3. Pages audited

- **Waveform** (`#wwToolbar` + each Time Group's own canvas toolbar,
  `wwCreateTimeGroupCanvasDom()`).
- **Event Reconstruction** (`#wwErToolbar`; its Reconstruction Timeline
  canvas no longer has its own toolbar at all — see §11).
- Every other page (Table, Calculated Channels, Analysis/Phasor/
  Overcurrent/Sequence Components/Impedance/Distance, Compliance) was
  checked and has **no** waveform-style Box Zoom/Pan/A-B-cursor/Annotate
  toolbar of its own — nothing else to migrate.

---

## 11. Toolbar composition (DEC-141)

DEC-140 established the icon registry and the per-function capability
matrix, but left Event Reconstruction's controls split across two DOM
locations: the global `#wwErToolbar` header (drag mode, View Mode, Time
Display, Unit Mode, Annotate/Annotations) and its Reconstruction
Timeline canvas's own `#wwErCanvasToolbar` (Zoom In/Out, Reset Time
View, Autoscale Y, A/B Cursors, Fit Record). Owner UAT found this an
unacceptable "split toolbar" experience. DEC-141 consolidates every
general waveform tool into the one global header, in seven ordered,
separator-divided families, and **removes** `#wwErCanvasToolbar`
entirely — the Reconstruction Timeline canvas now holds only its own
contextual content (title/meta header, the cursor VALUE readout, the
plotted panels).

### Family order (`#wwErToolbar`, left to right)

1. **View Mode** — Grouped, Combined, Separate (disabled), Custom
   (disabled), Split (disabled).
2. **Time Display** — Elapsed (disabled), Relative, Absolute.
3. **Units** — ENG / PU (text, unchanged, §9).
4. **Time Navigation** — Box Zoom, Pan, Zoom Out (X), Zoom In (X).
5. **Y-axis Scale** — Zoom Out (Y, disabled), Zoom In (Y, disabled),
   Autoscale Y.
6. **Fit / Reset** — Fit Selected Record, Reset Time View.
7. **Analysis** — A/B Cursors, Annotate, Annotations.

Every control keeps its **existing element id and handler** — only its
markup's DOM location, CSS class (text button → `.ww-icon-btn`) and icon
changed. `wwErSyncToolbar()`, `wwErStepZoomX()`, `wwErResetView()`,
`wwErAutoscaleY()`, `wwErFitRecord()` and the Annotate/Cursor wiring are
byte-for-byte unchanged.

### Reversed: Separate/Custom/Split now shown, disabled (§6 superseded)

§6 above (DEC-140) recorded a decision **not** to add disabled Separate/
Custom/Split stub buttons to Event Reconstruction. Owner UAT on DEC-141
explicitly reversed this, with the unambiguous instruction "do not omit
unsupported global slots — keep them visible but disabled with
explanatory tooltip." All three now exist on Event Reconstruction's own
View Mode family, reusing Waveform's own existing icons verbatim
(`VIEW_SEPARATE`/`VIEW_CUSTOM`/`VIEW_SPLIT`), permanently disabled, each
tooltipped `"<Name> — unavailable in Event Reconstruction"`. §6's own
finding (Separate is missing from the ticket's literal 4-slot list, the
true union is 5 slots) still stands and is now fully implemented, not
just documented.

### Zoom In/Out: now wired (§7 superseded)

§7 above (DEC-140) registered `ZOOM_X_IN`/`ZOOM_X_OUT`/`ZOOM_Y_IN`/
`ZOOM_Y_OUT` but deliberately left them unused. DEC-141's own owner
instruction is explicit: "the Y Zoom buttons must still be placed in the
global header now... preserve the current behavior and clearly report
that limitation." Both pages now use these composites live:

- **Event Reconstruction's Time Navigation** — Zoom In/Out (X) are the
  SAME `wwErZoomInBtn`/`wwErZoomOutBtn` ids and `wwErStepZoomX()`
  handler as before, now rendered with `ZOOM_X_IN`/`ZOOM_X_OUT` instead
  of text. Its own axis-chooser dropdown (`wwErZoomInAxisBtn`/
  `wwErZoomOutAxisBtn`) is **retired** — it was always permanently
  disabled and never wired to anything (Event Reconstruction has only
  ever zoomed the time axis), so removing it loses no real behaviour.
- **Event Reconstruction's Y-axis Scale** — two brand-new buttons,
  `wwErZoomYInBtn`/`wwErZoomYOutBtn`, using `ZOOM_Y_IN`/`ZOOM_Y_OUT`.
  At the time of this slice (DEC-141) no "active Y axis target" concept
  existed to drive a stepped Y zoom when a view may have several
  panels/axes at once (Grouped) or several axes on one panel (Combined),
  so they were permanently disabled with the tooltip `"Zoom In/Out —
  Selected Y Axis"` — the owner's own anticipated state ("if no valid Y
  target exists: disable Y Zoom In/Out, tooltip should explain why"),
  not a gap. **DEC-142 (the very next slice) built that targeting
  concept and wired these buttons live** — see
  [EVENT_RECONSTRUCTION_RENDERER_DESIGN.md](EVENT_RECONSTRUCTION_RENDERER_DESIGN.md)'s
  own DEC-142 entry for the full record; they now disable only when
  nothing is plotted or no target is set, with the tooltip "Select a Y
  axis to zoom".
- **Waveform's own Zoom In/Out** — the split-button's MAIN action icon
  now swaps between `ZOOM_X_IN`/`ZOOM_X_OUT` and `ZOOM_Y_IN`/
  `ZOOM_Y_OUT` live, exactly as its tooltip already dynamically swapped
  (`wwSyncTimeGroupZoomControls()`, one added `iconSpan.innerHTML`
  write keyed off the same `axis` variable the tooltip already reads).
  The split-button structure, its X/Y axis-chooser dropdown, and every
  interaction/zoom-amount behaviour are **completely unchanged** —
  Waveform already has a real, working "which axis" resolution
  mechanism (the dropdown), so retiring it (as Event Reconstruction's
  decorative copy safely was) would be a genuine functional regression,
  not a presentation change.
- **Waveform's own new Fit Selected Record stub** — `FIT_SELECTED_RECORD`
  (moved into the registry from Event Reconstruction's own pre-existing
  icon, reused verbatim), permanently disabled, tooltip "Fit selected
  record — unavailable in Waveform" (Waveform has no single "active
  record" concept — a Time Group may hold several independently-aligned
  sources, never one record to fit to).

### `RESET_TIME_VIEW` / `AUTOSCALE_Y`: new composites

Both were text-only before this slice (Waveform's own established
canvas-toolbar precedent, DEC-139). The owner's own explicit "do not
leave Reset Time View / Autoscale Y as a large text button" instruction
for the NOW-GLOBAL-HEADER context applies to both pages' consolidated
copies: `RESET_TIME_VIEW` (a counter-clockwise arc + arrowhead,
Lucide RotateCcw metaphor) and `AUTOSCALE_Y` (a vertical line with
outward arrowheads at both ends — "stretch to fit the full vertical
range"), both redrawn at the 18-unit house grammar (§2).

### Why Waveform's own per-Time-Group controls were not globalized

Waveform can have **multiple, independent, simultaneously-open Time
Groups** (DEC-057), each needing its own Reset/Autoscale/Zoom/Cursor
state — collapsing them into ONE set of global header buttons would need
an "active Time Group" targeting concept Waveform does not have today,
exactly the kind of interaction redesign this slice (and DEC-141's own
scope boundary) must not attempt. Event Reconstruction has exactly one
shared timeline, so its own consolidation is structurally sound without
inventing anything. Waveform's canvas-toolbar controls therefore stay in
their existing per-canvas location; what changed for them is icon/
registry conversion only (§7), never their placement.

### Deliberate mock deviations (reported, not silently applied)

- The attached mock's Units group appeared to show two icons rather than
  the existing ENG/PU text toggle. The ticket's own written §5
  ("Keep the current compact ENG/PU selector... concise state selectors
  only where icon semantics are genuinely weaker") is explicit and
  unambiguous, and is reaffirmed by §9 above (DEC-140); at the mock's
  rendered resolution, two bold uppercase glyphs in a compact pill are
  difficult to distinguish confidently from a true icon. ENG/PU stays
  text, per the written instruction.
- The mock's Y-axis Scale group showed a third element, a "Y target:
  <quantity> (<unit>)" text readout, alongside Zoom Out/In (Y). Populating
  that readout requires the same "active Y axis target" concept the
  owner's own instructions (both this ticket's §16 and the follow-up
  clarification) explicitly defer to a later ticket; it is not
  implemented. Autoscale Y (which already, unchanged, operates on every
  axis of the current view, never one "target") needed no such concept
  and is live.

---

## 4. The registry

**Note on `Source`:** rows below mostly still carry their original
DEC-140 "Powerwave (existing)"/composite description; many of these
(`ANNOTATE`, `ANNOTATIONS`, `CURSORS_AB`, `VIEW_SEPARATE`/`_CUSTOM`/
`_SPLIT`, etc.) have since become owner-supplied assets under DEC-143 —
see `frontend/assets/icons/manifest.json` (the manifest, not this
table, is kept current for provenance on every migration) and §12
below for the architecture that superseded this table's own original
"Source = how the artwork was drawn" framing.

| Key | Source | Pages | Notes |
|---|---|---|---|
| `PAN` | Owner-supplied (`pan.svg`) | no dedicated button on either page any more (DEC-144 — Pan is the only plot-area mode, communicated by cursor feedback instead); kept registered as a real, surviving concept | open hand |
| `CARET_DOWN` | Powerwave (existing) | Waveform (Zoom In/Out axis trigger, both Time-Group templates) | the one shared split-button caret, also used by Annotate/Unit Mode; ER's own equivalent decorative dropdown was retired (DEC-141 §11 — always disabled, never wired) |
| `ZOOM_X_IN` / `ZOOM_X_OUT` / `ZOOM_Y_IN` / `ZOOM_Y_OUT` | Owner-supplied (`zoom_in_x.svg`/`zoom_out_x.svg`/`zoom_in_y.svg`/`zoom_out_y.svg`, DEC-146) — each a dedicated, distinct file; the former shared plain `ZOOM_IN`/`ZOOM_OUT` aliasing (and the unwired `ZOOM_HORIZONTAL`/`ZOOM_VERTICAL` scope-only cues) is retired, both files deleted | Waveform, ER — wired live | see §7, DEC-142 and DEC-146 |
| `TIME_ELAPSED` | Composite: shared clock base (existing Powerwave clock, redrawn for a common base) + stopwatch-crown modifier | Waveform, ER | |
| `TIME_RELATIVE` | Composite: same clock base + reference-pin modifier | Waveform (new, disabled stub), ER | new icon this slice |
| `TIME_ABSOLUTE` | Composite: same clock base + calendar modifier (Lucide CalendarClock metaphor) | Waveform, ER | existing Absolute Time icon redrawn onto the shared base + given its calendar cue |
| `VIEW_GROUPED` | Owner-supplied (`grouped_view.svg`, DEC-143 §12 — the original inline composite it replaced was Powerwave's existing "Grouped Layout" shape) | Waveform, ER | gap resolved — see §6/§12 |
| `VIEW_SEPARATE` | Powerwave (existing) | Waveform (enabled), ER (disabled stub) | DEC-141 §11 reversed the original "no ER concept" finding — shown disabled, never omitted |
| `VIEW_CUSTOM` | Powerwave (existing) | Waveform (enabled), ER (disabled stub) | DEC-141 §11, same reversal |
| `VIEW_COMBINED` | Owner-supplied (`combine_view.svg`, DEC-143 §12 — originally a composite of `VIEW_GROUPED`'s own inline base + a dual-axis tick modifier; no shape relationship to Grouped is expected or enforced any more, both being independent owner files) | ER only | still no Waveform concept or stub (DEC-141 §11 only reversed the Separate/Custom/Split finding, not this one) — see §6 |
| `VIEW_SPLIT` | Powerwave (existing) | Waveform (enabled), ER (disabled stub) | DEC-141 §11, same reversal (no table to split with) |
| `CURSORS_AB` | Powerwave (existing) | Waveform, ER | |
| `ANNOTATE` | Powerwave (existing) | Waveform, ER | |
| `ANNOTATION_TEXT_NOTE` / `ANNOTATION_CALLOUT` / `ANNOTATION_PEAK_MAX` / `ANNOTATION_PEAK_MIN` | Powerwave (existing) | Waveform, ER | |
| `ANNOTATIONS` | Powerwave (existing) | Waveform, ER | |
| `AUTOSCALE_X` | Owner-supplied (`autoscale_x.svg`, DEC-144) | Waveform, ER | renamed from `RESET_TIME_VIEW` — same function; groups with `AUTOSCALE_Y` and `FIT_SELECTED_RECORD` (DEC-145, extended by DEC-147) |
| `AUTOSCALE_Y` | Owner-supplied (`autoscale_y.svg`, DEC-144 — gap open since DEC-143 now resolved) | Waveform, ER | groups with `AUTOSCALE_X` and `FIT_SELECTED_RECORD` (DEC-145, extended by DEC-147) |
| `FIT_SELECTED_RECORD` | Owner-supplied (`fit_selected_record.svg`) | ER (enabled), Waveform (disabled stub — no "active record" concept) | sits in the same group as `AUTOSCALE_X`/`AUTOSCALE_Y`, after Autoscale Y (DEC-147) |

**`UNIT_ENGINEERING`/`UNIT_PER_UNIT` now exist (DEC-143, §12)** —
`assets/icons/waveform/engineering_unit.svg`/`per_unit.svg`, Event
Reconstruction's own ENG/PU buttons; see §9 for the superseded
reasoning they originally didn't.

---

## 5. Capability matrix

A page enables a shared-family button by simply not marking it
`disabled`; it never hides a family member that exists on another page
(§9's rule). A disabled stub still carries the family's shared icon and
an explanatory `title`/`aria-label`.

| Control | Waveform | Event Reconstruction |
|---|---|---|
| Elapsed Time | **ON** | OFF — "Elapsed Time — unavailable in Event Reconstruction" |
| Relative Time | OFF — "Relative Time — unavailable in Waveform" | **ON** |
| Absolute Time | **ON** | **ON** |
| Grouped | **ON** (page-rule: default) | **ON** |
| Separate | **ON** (page-rule) | OFF — "Separate Layout — unavailable in Event Reconstruction" (DEC-141 §11; never omitted) |
| Custom Layout | **ON** (page-rule) | OFF — same treatment (DEC-141 §11) |
| Combined | *(no control — §6, unchanged by DEC-141)* | **ON** |
| Split View | **ON** (page-rule) | OFF — same treatment (DEC-141 §11) |
| Pan | **ON** (the only plot-area mode, DEC-144 — Box Zoom retired; no toggle button, cursor feedback only) | **ON**, same |
| Zoom In/Out (X) | **ON** | **ON** |
| Zoom In/Out (Y) | **ON** (its own axis-chooser dropdown) | **ON** when an active Y-axis target is set (DEC-142); disabled with "Select a Y axis to zoom" otherwise — direct individual-Y-axis drag zoom (DEC-134) is also still supported |
| Autoscale X (DEC-144, renamed from Reset Time View) | **ON** | **ON** |
| Autoscale Y | **ON** | **ON** |
| Fit Selected Record (groups with Autoscale X/Y, DEC-147) | *(no control — Waveform has no "active record" concept)* | **ON** |
| A/B Cursors | **ON** | **ON** |
| Annotate / Annotations | **ON** | **ON** |
| Unit Mode (ENG/PU) | **ON** | **ON** |

---

## 6. Why Event Reconstruction has no Separate/Custom/Split stubs (superseded by §11/DEC-141)

**This section's own decision not to add the stub buttons below was
reversed by owner UAT on the very next ticket (DEC-141, §11) — Event
Reconstruction now shows all three, permanently disabled. The finding
below (the ticket's own 4-slot framing omits Separate; the true union
is 5 slots) is still correct and unaffected; only the "do not invent a
button" conclusion built on it was overridden.**

Section 14 of the owner's own ticket lists the View Mode family as
"Grouped / Combined / Custom / Split" — four slots, omitting Separate
Layout entirely, even though Separate is a real, currently-used, default-
adjacent Waveform capability (`layoutModeSeparateBtn`, one panel per
channel). The true union of both pages' real view modes is **five**
slots: Grouped (shared), Separate (Waveform-only, one panel per
channel), Custom (Waveform-only, user-defined groups), Combined (Event
Reconstruction-only, every channel on one multi-axis panel), Split View
(Waveform-only, waveform+table side by side — Event Reconstruction has no
table to split with). `[FACT]`, confirmed by reading
`ww.layoutMode`'s own implementation comment (`frontend/index.html`,
near line 26100) and Event Reconstruction's own DEC-131/DEC-132 Grouped/
Combined design.

Per the ticket's own "do not invent functionality" rule (§12/§21), this
document originally recorded the decision **not** to add disabled
Separate/Custom/Split stub buttons to Event Reconstruction (nor a
disabled Combined stub to Waveform — that half stands unchanged): none
of these concepts has ever existed on the other page, unlike Time
Display (§9/§10's own explicit three-button-everywhere mandate, which
this document does implement in full). **DEC-141's own owner UAT
explicitly reversed the Event-Reconstruction half of this reasoning**
("never omit a global slot — keep it visible but disabled with an
explanatory tooltip" overrides the risk described below for this
family); Combined still has no Waveform stub, since that reversal was
never extended to it. The risk this section originally weighed —
inventing a greyed-out button for a capability never discussed as a
future feature risks misleading an engineer into thinking it is
planned — is recorded for context, not as the current rule.

Grouped **is** shared: Waveform's "Grouped Layout" groups channels by
`engineering_type`; Event Reconstruction's "Grouped" groups by the finer
`display_axis_key` (quantity + unit, DEC-131). Both are "channels that
belong together share one panel" at page-appropriate precision — the same
function, different state, exactly the architecture §19 of the ticket
describes — so `VIEW_GROUPED` is reused verbatim and both buttons'
tooltips name that single word.

---

## 7. Zoom X/Y composites: registered, not yet wired (superseded by §11/DEC-141, then §12/DEC-143, then §14/DEC-146)

**Triply superseded, recorded for context only.** §11/DEC-141 wired
these keys live (still as hand-drawn composites then). §12/DEC-143 went
further: the composites themselves were retired — `ZOOM_X_IN`/`ZOOM_Y_IN`
aliased the owner-supplied plain `ZOOM_IN` file (same for `_OUT`), per
the owner's own "do not invent compound icons" instruction at the time.
§14/DEC-146 (a later owner delivery) superseded that aliasing in turn:
each of the four keys now has its own dedicated owner file, and the
"icon swaps by axis" description below IS accurate again, just with
real per-axis artwork instead of a hand-drawn composite. The axis
distinction this section describes moving into tooltip wording is still
accurate throughout.

`ZOOM_X_IN`/`ZOOM_X_OUT`/`ZOOM_Y_IN`/`ZOOM_Y_OUT` exist in the registry
(one canonical definition each, satisfying the icon-selection rule) but
are **not** referenced by any `data-ww-icon` in the page today. The Zoom
In/Out split-buttons keep their current form — Waveform's own already-
aligned TEXT main button (DEC-139: Waveform itself has never had an icon
form of this function to reuse) plus the `CARET_DOWN` axis-chooser
trigger — unchanged by this slice.

Converting the split-button's own main action from text to one of these
composites, and deciding how it should present the engineer's X/Y choice,
is Y-axis interaction surface — explicitly deferred to the dedicated
Y-axis interaction ticket this slice's own owner instructions name, so as
not to mix toolbar architecture with interaction-behaviour redesign in
one change. What *did* change here, safely (pure wording, the same
`wwSyncTimeGroupZoomControls()` function, same disabling logic): the
tooltip's own axis phrase moved from generic "X axis"/"Y axis" to the
canonical "Time Axis"/"Selected Y Axis" (§8 below).

---

## 8. Tooltip wording

Same semantic tool ⇒ same tooltip text, on both pages, **except** where a
disabled stub names the page it is unavailable on (§5's own examples) —
the base mode name itself (`"Elapsed Time"`, `"Relative Time"`,
`"Absolute Time"`) is always identical.

| Function | Canonical tooltip |
|---|---|
| Pan | *(no dedicated button since DEC-144 — Box Zoom retired, Pan is the only plot-area mode; grab/grabbing cursor feedback instead)* |
| Zoom In (time axis) | `Zoom In — Time Axis` |
| Zoom Out (time axis) | `Zoom Out — Time Axis` |
| Zoom In/Out (selected Y axis, Waveform only) | `Zoom In — Selected Y Axis` / `Zoom Out — Selected Y Axis` |
| Autoscale X (DEC-144, renamed from Reset Time View) | `Autoscale X` (Waveform's own canvas-toolbar form additionally says "for this Time Group" — a real context qualifier Event Reconstruction has no Time Group to name; see DEC-139) |
| Autoscale Y | `Autoscale Y` (same qualifier note; groups with Autoscale X and Fit Selected Record, DEC-145/DEC-147) |
| A/B Time Cursors | `A/B Time Cursors` (same qualifier note) |
| Annotate | `Annotate` |
| Annotations | `Annotations` |
| Elapsed Time | `Elapsed Time` |
| Relative Time | `Relative Time` |
| Absolute Time | `Absolute Time` |
| Grouped | `Grouped Layout` (Waveform) / `Grouped Measurement View` (Event Reconstruction — see §6: related, page-appropriate, not forced identical) |
| Combined | `Combined Multi-Axis View` (Event Reconstruction only) |
| Fit Selected Record | `Fit selected record` (Event Reconstruction-specific; groups with Autoscale X/Y, after Autoscale Y, DEC-147) |

Event Reconstruction's own Relative/Absolute tooltips previously carried
additional explanatory clauses (e.g. "reconstructed recorded wall-clock
time, including timing corrections (display timezone)") from DEC-135.
This slice shortens them to the canonical form per the owner's own
explicit, repeated "do not create slightly different wording" instruction
— the detail is real and was a deliberate UAT-era choice, so it is
recorded here rather than silently discarded: if the owner wants it kept,
it belongs in a help affordance separate from the tooltip, not back in
the tooltip itself.

---

## 9. Unit Mode: deliberately not an icon (superseded by §12/DEC-143)

**This section's own decision was reversed by the owner on a later
ticket (DEC-143, §12 below) once dedicated `engineering_unit.svg`/
`per_unit.svg` assets existed — Event Reconstruction's ENG/PU is now an
icon pair, not text. The reasoning below is recorded for context (why
no icon existed at the time), not as the current rule.**

Engineering Units / Per Unit originally had no icon registry entry.
`[DECISION]` (DEC-140, per the ticket's own §13 hedge: "if icons become
too ambiguous, keep a compact labelled control only if necessary — do
not sacrifice usability merely to make everything icon-only"). An
electrical engineer's "Engineering vs Per Unit" distinction has no
widely-recognised pictogram, and a guessed one (a ruler? a fraction
symbol? a percent sign?) would be actively misleading rather than
merely unclear. That blocker no longer applies once the owner supplies
an approved pictogram — see §12.

---

## 10. State isolation

Shared icon/tooltip/button-class presentation never implies shared
**state**. Each page keeps its own:

- drag mode (`ww.dragMode` vs `wwErState.dragMode`);
- time display mode (`ww.timeMode` vs `wwErState.timeDisplay`);
- view/layout mode (`ww.layoutMode` vs `wwErState.plot.viewMode`);
- cursor state (`ww.timeGroupCursorState` vs `wwErState.plot.cursors`);
- annotation state (`ww.annotations` vs the backend-owned Event
  Reconstruction definition, DEC-136/137);
- unit mode (`ww.unitMode` vs `wwErState.unitMode`, DEC-138).

Event Reconstruction's own module never reads any of Waveform's `ww.*`
state or calls any of Waveform's own handler functions — enforced by a
static forbidden-substring test (see `test_frontend_event_reconstruction.py`'s
`TestEventReconstructionToolConsistency.test_shared_toolbar_primitives_never_introduce_shared_state`).

---

## 12. Owner-approved local SVG assets (DEC-143)

Full decision record: [DECISIONS.md — DEC-143](DECISIONS.md#dec-143--powerwave-icons-become-owner-approved-local-svg-assets-individually-bordered-tool-buttons-and-unit-mode-joins-the-icon-system).
This section records the architecture every future icon addition must
follow; the decision record carries the one-time migration's own detail.

### The rule

> Powerwave icons are maintained as owner-approved local SVG assets
> under `frontend/assets/icons`. Application code references these
> physical assets through semantic registry mappings. Coding agents
> must not independently redraw or reinterpret approved icon artwork.

### Where the files live

```
frontend/assets/
  icons/
    README.md        -- the rule above, in full, plus folder purposes
    manifest.json     -- { KEY: { file, source: "owner-supplied" | ... } }
    common/            -- generic reusable controls (Annotate, Annotations, Search)
    navigation/        -- #mainSidebarMenu's per-page icons
    waveform/          -- waveform display/time/units/layout/zoom/cursor/fit icons
  branding/
    README.md          -- reserved; favicon/logo not yet supplied
```

**Before adding any icon, search this directory and `manifest.json`.** A
function with a file here reuses that file; it is never redrawn. A
function with no file yet keeps its inline fallback (§2's own geometry
contract still governs that inline markup) until the owner supplies one
— never substitute a generated or library icon to "fill the gap."

### Registry value: path, or inline fallback

```js
KEY: "assets/icons/<folder>/<file>.svg"   // owner-supplied (most entries)
KEY: '<svg viewBox="0 0 18 18">...</svg>' // no owner asset yet (§2's rule governs this)
```

`wwSetToolIcon(el, key)` (`frontend/index.html`) is the one place that
tells the two apart (does the value start with `"<"`) and renders
either: a path becomes a CSS `mask-image` (`.ww-icon-asset`); inline
markup becomes `innerHTML`, as before DEC-143. `wwApplyToolIcons()` and
the one dynamic icon-swap site (`wwSyncTimeGroupZoomControls()`, the
Zoom In/Out split-button's own X/Y icon swap) both go through it.

### Rendering: CSS mask, not `<img>` or fetch+inject

The delivered files are **not colour-uniform**: a few use
`stroke="currentColor"` (Lucide-sourced), most use a hardcoded
fill/stroke colour and their own viewBox (SVG-Repo-sourced). `<img>`
cannot inherit `currentColor` at all, so it would show every
hardcoded-colour file wrong in at least one theme; fetch+inject would
need to parse and strip each file's own colour attributes to theme it,
which edits the artwork in spirit even without touching the file on
disk. `.ww-icon-asset` instead sets `background-color: currentColor`
plus `mask-image`/`-webkit-mask-image: url(...)` — the mask reads only
each file's silhouette (any opaque pixel) and paints it with the
control's own colour, correct in both themes for every file, exactly
as delivered.

### Individual-button geometry (owner correction, DEC-143)

Every action/mode tool group (Pan, Time Display, View Mode,
Unit Mode) is a row of **individual** compact buttons — the same
`.ww-toolbar .ww-icon-btn` geometry as A/B Cursors/Annotate (30px cell,
6px radius, its own full border) — never one shared-border/segmented
pill. `.ww-toolbar`'s own flex `gap` is **2px** (within one family); a
family boundary reads through the existing `.ww-toolbar-sep` hairline's
own margin, never a bigger uniform gap. `.ww-tg-toolbar` (Waveform's
own per-Time-Group canvas toolbar, §11's "why Waveform's own per-Time-
Group controls were not globalized") is a separate surface, not covered
by this spacing rule.

### Known gaps (no owner asset in this delivery)

`CARET_DOWN` and the four annotation TYPE icons
(`ANNOTATION_TEXT_NOTE`/`_CALLOUT`/`_PEAK_MAX`/`_PEAK_MIN`) stay on
their original inline markup. `BOX_ZOOM` is not a gap — the function
itself is retired (DEC-144), not pending an icon. `AUTOSCALE_Y`'s own
gap (open when this section was first written) is resolved — see §13.
`ZOOM_HORIZONTAL`/`ZOOM_VERTICAL` are no longer registered at all —
removed (DEC-146) once dedicated per-axis zoom icons made the
"how should these combine with Zoom In/Out" composition question moot;
see §14.

---

## 13. Box Zoom retired; Pan cursor feedback; Autoscale X/Y renamed, re-iconed and paired (DEC-144/DEC-145)

Full decision records: [DECISIONS.md — DEC-144](DECISIONS.md#dec-144--box-zoom-is-retired-pan-gets-cursor-feedback-grabgrabbing-reset-time-view-is-renamed-autoscale-x)
and [DEC-145](DECISIONS.md#dec-145--autoscale-x-and-autoscale-y-are-paired-adjacent-in-their-own-toolbar-group).

- **Box Zoom retired.** No toggle, no button, no `BOX_ZOOM` registry
  entry, on either page. Pan is the only plot-area interaction mode;
  `ww.dragMode`/`wwErState.dragMode` are fixed at `"pan"`.
- **Pan cursor feedback.** `.ww-panel .draglayer .nsewdrag` /
  `.ww-er-panel .draglayer .nsewdrag` get `cursor: grab`, switching to
  `grabbing` via a `.ww-panning` class toggled by the shared
  `wwWirePlotAreaGrabCursor()` on pointerdown/mouseup/touchend.
- **`AUTOSCALE_X`** (renamed from `RESET_TIME_VIEW`) and **`AUTOSCALE_Y`**
  are both owner-supplied (`autoscale_x.svg`/`autoscale_y.svg`) and sit
  paired, adjacent, in their own toolbar group — `[Autoscale X]
  [Autoscale Y]`, each its own individual button, 2px apart, never
  joined.

---

## 14. Dedicated zoom-axis icons, the fit/scale-view group, and an Engineering/Per-Unit artwork refresh (DEC-146/DEC-147/DEC-148)

Full decision records: [DECISIONS.md — DEC-146](DECISIONS.md#dec-146--zoom-xy-get-dedicated-owner-icons-the-plainscope-only-zoom-icons-are-removed),
[DEC-147](DECISIONS.md#dec-147--autoscale-x-autoscale-y-and-fit-selected-record-become-one-toolbar-group-amends-dec-145)
and [DEC-148](DECISIONS.md#dec-148--engineering-unit--per-unit-icon-artwork-refreshed-same-filenames-same-semantics).

- **`ZOOM_X_IN`/`ZOOM_X_OUT`/`ZOOM_Y_IN`/`ZOOM_Y_OUT`** each now have
  their own dedicated owner file (`zoom_in_x.svg`/`zoom_out_x.svg`/
  `zoom_in_y.svg`/`zoom_out_y.svg`) instead of aliasing a shared plain
  zoom-in/zoom-out pair. The former `ZOOM_IN`/`ZOOM_OUT` keys and files,
  and the never-wired `ZOOM_HORIZONTAL`/`ZOOM_VERTICAL` scope-only
  cues, are removed — both the registry entries and the on-disk `.svg`
  files. `waveform/reset_time_view.svg` (DEC-144's own, unrelated,
  pre-existing orphan) was left untouched — out of this ticket's scope.
- **Autoscale X, Autoscale Y and Fit Selected Record** now sit in one
  "fit/scale view" toolbar group (DEC-147, amending DEC-145's narrower
  Autoscale-X/Y-only pairing) — `[Autoscale X][Autoscale Y][Fit Selected
  Record]`, each its own individual button, 2px apart throughout, never
  joined into a segmented control. Pure DOM reorder; no id, class,
  handler or behaviour changed on any of the three.
- **`engineering_unit.svg`/`per_unit.svg` artwork refreshed (DEC-148).**
  Same filenames, same `UNIT_ENGINEERING`/`UNIT_PER_UNIT` registry
  mapping, same `.ww-icon-asset` mask rendering — an asset-only
  update, no semantic/behavioural change.
