# Powerwave icon assets

DEC-143 (see `docs/project-memory/DECISIONS.md` and
`docs/project-memory/POWERWAVE_ICON_SYSTEM.md`): Powerwave icons are
maintained as **owner-approved local SVG assets** under this directory.
Application code references these physical files through the
semantic registry (`WW_TOOL_ICONS` in `frontend/index.html`), never a
second hand-copied inline `<svg>` for a function an asset already
covers.

## Rules

- **Search this directory (and `manifest.json`) before adding any new
  icon.** A function that already has a file here reuses that file --
  it is never redrawn, even if a new request phrases it differently.
- **Coding agents must not independently draw, redraw, simplify,
  recolour or reinterpret an icon.** These files are owner-supplied,
  approved design assets, not placeholders. If a semantic slot has no
  matching owner file yet, say so and leave it on its existing
  (usually inline `<svg>`) fallback -- never substitute a generated or
  library (e.g. Lucide) icon for it without being told to.
- **Same semantic function, same file, on every page.** `PAN` is one
  path; Waveform's Pan button and Event Reconstruction's both read it.
- **The registry maps a semantic ID to an asset path**
  (`SEMANTIC_KEY: "/assets/icons/<folder>/<file>.svg"`); `manifest.json`
  records each one's provenance. A registry value that is inline
  markup instead of a path means no owner asset exists for that key
  yet -- check the manifest's own `"source": "inline-fallback"` entries
  before assuming one does.
- **Adding a future icon:** the owner supplies the file first (placed
  in the matching folder below), then it is registered. Code never
  invents the artwork to "fill a gap" -- an unfilled gap stays
  reported, not guessed at.

## Folders

- `common/` -- generic, reusable application controls (e.g. Annotate,
  Annotations, Search) used across more than one feature area.
- `navigation/` -- the main sidebar's per-page icons.
- `waveform/` -- waveform display, time, units, layout, zoom, cursor
  and fit/reset icons (Waveform and Event Reconstruction alike).
- `analysis/` -- the Analysis page's own analyzer-type nav icons
  (Overcurrent, Impedance Locus, Distance Protection, Phasor, Sequence
  Components).

See `frontend/assets/branding/README.md` for logo/favicon assets,
which are a separate, not-yet-supplied set.

## Rendering

Icons render via a CSS `mask-image` (the `.ww-icon-asset` class,
`frontend/index.html`), not `<img>` or fetch+inject -- see that CSS
rule's own comment for why: the supplied files are not colour-uniform
(some use `stroke="currentColor"`, most use a hardcoded fill/stroke),
so a mask (which reads only each file's silhouette and paints it with
the control's own `currentColor`) is the one technique that themes
correctly for every file without touching any artwork.

## WUI-002 owner-approved scoped artwork

The owner explicitly authorized exact SVG reuse from `oruxa_waveform_mockup.html`
for the Waveform Analysis **global toolbar only**, and selected: **"Reuse exact
SVGs; retain existing icons for gaps."** This is a scoped exception to the
same-function/same-file guidance above. Existing shared semantic keys, other
pages, WUI-001 pane-local controls, and the renderer remain unchanged.

Eight `WUI002_*` entries in the existing registry resolve to local assets under
`waveform/wui-002/`. No second registry, copied inline geometry or external icon
library is introduced. Time, unit, layout-mode, annotation-manager, t0 and
annotation-menu gaps retain their existing artwork. Do not infer approval for
redrawing those gaps.

See [provenance](waveform/wui-002/provenance.json) and
[artwork notice](waveform/wui-002/NOTICE.md) for source hashes and reuse notes.

The later owner refinement (2026-11-22) moves Voltage Display into pane headers
as text ENG/PU pills following the supplied pane reference. Shared unit SVGs stay
unchanged for other pages. See the
[relocation report](../../../docs/project-memory/WUI_002_VOLTAGE_DISPLAY_RELOCATION.md).
