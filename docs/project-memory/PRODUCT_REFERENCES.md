# Product Direction and Engineering Requirements — Oruxa-Powerwave

[DECISION] Owner direction, effective 2026-11-17.

Oruxa-Powerwave is an independent engineering waveform analysis platform. Product development is guided by owner-defined engineering requirements, numerical correctness, usability, performance, maintainability and professional software architecture.

This document records the active product direction. The earlier external
benchmarking framework in DEC-020 was retired by the owner on 2026-11-17.
Historical wording remains in Git history. Existing engineering requirements,
approved UI decisions and their acceptance evidence remain in force.
Development guidance must not introduce external product comparisons or goals
to imitate or surpass another product.

## Authority and evidence

Owner-defined requirements, approved decisions in
[DECISIONS.md](DECISIONS.md), and owner UAT determine product scope and acceptance.
Use the [project-memory labels and decision modes](README.md#decision-modes)
to distinguish facts, proposals, approved work and questions requiring UAT.
A design proposal does not authorize implementation or release.

Engineering claims require evidence: source-format documentation where available,
independent exports, pinned recording fixtures, full-resolution sample comparisons
and meaningful regression tests. Existing desktop `powerwave` parser/domain code
is read-only migration evidence; follow
[its startup rule](README.md#powerwave-specific-startup-rule) before inspecting it
and record verified findings in [POWERWAVE_DISCOVERY.md](POWERWAVE_DISCOVERY.md).
Existing behaviour alone does not establish numerical correctness or authorize
its adoption in Oruxa-Powerwave.

## Engineering requirements

- Preserve immutable original files, native sampling rates, sample identity,
  signed representation, scale/offset provenance, units and missing-data semantics.
- Keep full-resolution data authoritative for engineering calculations,
  cursor measurements and significant values. Display reduction must preserve
  peaks and must never become the numerical source of truth (DEC-019).
- Make elapsed time, source timestamps, event references and synchronization
  explicit. Avoid hidden resampling, interpolation or alignment assumptions.
- Keep analog, digital and calculated channel identities distinct, including
  duplicate source names and channels from multiple recordings.
- Preserve established numerical contracts and calibration gates. A plausible
  waveform or a successful import alone does not prove measurement validity.

## UI/UX and performance requirements

- Give the active analysis area visual priority, with compact controls and a
  readable channel browser. Preserve clear analog/digital/calculated organization,
  flexible grouping and user-controlled channel visibility.
- Maintain one shared waveform time viewport, synchronized zoom/pan, clear
  reset/autoscale actions and consistent cursor readouts with engineering units.
- Support understandable panel arrangement, resizing, labels and annotations
  while keeping the waveform usable and avoiding duplicate controls or state.
- Use the shared Light/Dark theme tokens and electrical-notation formatters.
  Oruxa's palette, typography and interaction standards define the presentation.
- Keep charts responsive and large-file interaction practical. Evaluate payload
  sizes, rendering cost, memory use and latency using representative recordings;
  choose implementation tools from measured evidence and owner UAT.

These requirements do not authorize deferred features. The approved decisions and
the current owner task determine which work may proceed.

## Architecture and maintainability

[Oruxa architecture](../architecture/oruxa-architecture.md) remains authoritative
and must be read at the source. Preserve frontend/backend separation, backend
engineering authority, portable configuration, API boundaries, provider
independence, source immutability and the approved ephemeral-event model
(DEC-015). Avoid hidden infrastructure and timing assumptions.

Use shared components and one authoritative state/calculation path where an
existing contract applies. Keep changes focused, dependencies pinned and tests
directed at meaningful behaviour and independent engineering evidence.

## Feature-design method

For a significant feature, document:

1. The owner's engineering task and applicable approved decisions.
2. Required data fidelity, numerical/time semantics and units.
3. The proposed interaction, layout and performance constraints.
4. Architecture boundaries, maintainability and relevant risks.
5. Acceptance evidence: independent numerical checks, regression tests and UAT
   where interaction quality requires hands-on evaluation.

Use [decision modes](README.md#decision-modes) to resolve open choices. Routine
internal engineering decisions need proportionate analysis; interaction questions
may need a bounded prototype and owner UAT. Do not promote a prototype or proposal
to an approved production design without an owner decision.

## Established examples and scope boundaries

**Waveform workspace:** DEC-019 preserves full-resolution authority and
peak-preserving display envelopes; DEC-021 establishes the shared time viewport.
Panel grouping, independent Y axes, zoom/pan and cursor semantics remain explicit
Oruxa engineering requirements. Preserve later approved refinements and UAT.

**Application shell (DEC-031, 2026-08-16):** the owner-approved layout has a
Global Header, full-height Main Sidebar Menu, contextual Workspace Sidebar,
dominant Main Workspace and Bottom Status Bar. The Status Bar does not run
beneath the Main Sidebar Menu. These structural requirements remain unchanged.

**Recordings page (DEC-032, 2026-08-16):** retain the compact table and Upload New
workflow, with a recording represented as one logical CFG+DAT event. Prefer the
real station/event name for display and preserve the session/workspace-backed
model; the page does not imply a persistent cloud recording library. Upload
design remains extensible to separately approved formats.

**Multi-source synchronization:** source-native sampling, exact/nearest timestamp
alignment, transparent synchronization and calculated channels across recordings
remain engineering considerations. Their implementation scope and timing rules
come from the relevant approved decisions, with no hidden resampling.

**Calculated signals:** retain reusable engineering calculations, explicit
expression semantics, units, provenance and validity limits. The owner determines
future expression capabilities and specialized grid/protection analysis scope;
these examples do not authorize new functionality.
