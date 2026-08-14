# Powerwave Discovery

This is the cumulative technical discovery record for the existing desktop
`powerwave` application. It answers one question only:

> **What does the existing `powerwave` actually do?**

It does **not** decide what `oruxa_powerwave` should do — that belongs in
[DECISIONS.md](DECISIONS.md). A finding recorded here is evidence for a
future decision, not a design requirement by itself. See "Discovery vs.
design" in [README.md](README.md).

## Status

`[OPEN]` **This document is a skeleton.** No findings have been populated
yet. A first discovery pass across `powerwave`'s major subsystems was
partially run on 2026-08-14 (see [HANDOFF.md](HANDOFF.md) and the "Known
blockers" note in [CURRENT_STATE.md](CURRENT_STATE.md) for why it stopped
short), but per the instructions that created this framework, those raw
findings are deliberately **not** transcribed into this document during
framework setup — they belong to the dedicated discovery-audit task, so that
this document only ever contains findings that have actually been verified
and written down carefully, not a rushed dump.

## Locating `powerwave`

`[FACT]` The reference repository is at one of:

- Windows: `D:\Programming\powerwave\`
- macOS: `/Volumes/externalDrive/code-gym/powerwave/`

Detect which path exists on the current machine; do not assume the OS.
`powerwave` is a **reference system** — read for evidence, never the place
new project memory or migration planning gets written (see README.md).

## Finding format

Every finding in this document should use this shape:

```text
### <short finding title>

Finding:
<one or two sentences — what is true>

Evidence:
<file/module/class/function/test, with path and line number where practical>

Status:
Verified / Partially verified / Needs verification

Last verified:
YYYY-MM-DD
```

Distinguish observed facts from interpretation explicitly. If a finding is
partly inference (e.g. "this looks reusable"), label the inference clearly
rather than blending it into the observed fact.

## Sections (to be populated by the discovery audit)

Each section below is reserved structure only. Do not fill a section with
findings unless they have actually been inspected and verified in the
`powerwave` source.

### 1. Architecture overview

_(subsystem boundaries, dependency flow, entry points, GUI framework)_

### 2. Repository structure and canonical-vs-legacy status

_(`app/` vs `src/`, and any other duplicated/parallel implementations)_

### 3. Internal data model

_(`DisturbanceRecord` and related contracts: ownership, mutability,
lifetime, serializability, GUI coupling)_

### 4. Session and application state

_(current session/workspace concepts, ownership model, anything dangerous to
reuse directly inside a shared multi-user backend process)_

### 5. File import pipeline

_(COMTRADE / CSV / Excel: parser location, sync vs async, error handling,
large-file behaviour, provider pattern)_

### 6. Timestamp and timebase handling

_(supported timing models, detection/repair logic, multi-rate handling)_

### 7. Synchronization architecture

_(multi-source alignment, offsets, cursor sync, reversibility)_

### 8. Calculated signals

_(creation, identity, storage, display, lifecycle, cross-source support)_

### 9. Waveform visualization / rendering

_(plotting stack, panel/canvas architecture, decimation, performance
techniques actually implemented vs. only documented)_

### 10. Measurements and analytics catalog

_(per-capability purpose/input/output/module/GUI-dependency/reuse-potential)_

### 11. Background/worker processing

_(threading model, cancellation, progress reporting)_

### 12. Test coverage

_(what exists, what's a candidate migration-safety test, what's GUI-only and
won't translate)_

### 13. GUI / engineering-logic separation summary

_(cross-cutting summary of what's cleanly reusable vs. desktop-coupled vs.
mixed, referencing the sections above rather than repeating them)_

### 14. Documentation vs. implementation discrepancies

_(anywhere `powerwave`'s own `docs/*.md` disagrees with what the code
actually does — report both sides, do not silently resolve)_

### 15. Migration risk notes

_(engineering-integrity risks specifically — anywhere an apparently harmless
frontend/backend redesign could silently change numerical results)_

## Reuse candidates (populated after the sections above are verified)

`[OPEN]` Not yet populated. This will eventually categorize significant
`powerwave` modules as:

- **Category A** — reuse largely unchanged.
- **Category B** — reuse after controlled refactoring.
- **Category C** — reimplement for the web architecture.

Do not populate this categorization ahead of the underlying findings above.
