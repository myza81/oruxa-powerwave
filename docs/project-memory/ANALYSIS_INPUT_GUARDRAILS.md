# Analysis Input Guardrails, Engineering Context & Automatic Role Resolver

**Status: Slice 1 (Engineering Context + durable phase identity) is
implemented — see [DECISIONS.md — DEC-086](DECISIONS.md#dec-086--analysis-guardrail-slice-1-engineering-context-physicallogical-bay-identity-and-durable-canonical-phase-are-established-as-a-new-additive-metadata-layer-kept-fully-independent-of-measurement-groupsper-unit-and-of-no-fixed-value-until-a-later-slices-automatic-analysis-input-resolver-reads-it).
Everything below marked "not yet implemented" is future-slice scope,
recorded here so a later slice does not need to re-derive the
architecture from scratch.**

## Why this document exists

Future protection/engineering analyses (Distance/Impedance, Overcurrent,
Phasors, Differential, Sequence Components, Frequency/RoCoF) all need the
same underlying capability: given an engineer's selection of **which
physical bay/equipment** and **which analysis mode**, automatically
resolve the concrete channels (e.g. Va, Ia) that analysis needs —
without the engineer manually picking raw channel pairs, *except* when
automatic resolution is genuinely ambiguous or impossible.

```text
Engineer selects: Engineering Context (Bay) + Analysis Mode
                              ↓
                  Powerwave resolves: required channels
```

This is a different axis from Playback (`docs/project-memory/DECISIONS.md`
— DEC-085): **Playback answers WHEN** (a time coordinate, engineering-
meaning-agnostic); **this layer answers WHAT** (which channels
correctly represent a given engineering role). Playback must remain
independent of bay/phase/analysis logic; this layer must remain
independent of animation-frame timing.

## Core product principle

> The engineer should select the engineering context and analysis mode.
> Powerwave should resolve the required channels automatically whenever
> the metadata is sufficient and unambiguous. Do NOT make the engineer
> manually choose raw channel pairs unless automatic resolution is
> ambiguous or impossible.

> Detection may suggest. Persisted metadata and explicit engineer
> confirmation decide. The engine must NEVER silently guess among
> ambiguous candidates.

## Implemented (Slice 1): Engineering Context + durable phase identity

### Engineering Context vs. Measurement Group

Two independent concepts that answer different questions and coexist —
neither replaces the other, and a channel may belong to both at once:

| | Measurement Group (`app.domain.measurement_group`) | Engineering Context (`app.domain.engineering_context`) |
|---|---|---|
| Answers | "Which channels form one kind-specific measurement bank?" | "Which channels represent one physical piece of equipment/bay?" |
| Scope | One source, one kind (Voltage XOR Current) | Workspace-wide, any kind, may span sources |
| Used for | Per-Unit base configuration | Future automatic analysis-input resolution |
| Phase identity | None (never needed one) | `EngineeringContextMember.phase`, durable |

### Domain model

```text
EngineeringContext
├── id                  ("ec-" + uuid4().hex)
├── workspace_id
├── display_name
├── status              suggested | confirmed | needs_review | manual
│                       (reused verbatim from MeasurementGroup's own
│                       vocabulary — see app.domain.measurement_group)
└── members: list[EngineeringContextMember]
        ├── channel_ref: ChannelRef        (source OR calculated; unchanged shape)
        ├── phase: str                     (canonical — see below)
        ├── phase_source: str              (provenance — see below)
        └── original_phase_label: str|None (engineer-facing raw label, display only)
```

Deliberately **no `source_id` field** on `EngineeringContext` — a
physical bay may legitimately span more than one uploaded source/file
(e.g. Voltage channels in one COMTRADE file, Current channels in a
second file for the same event). Each member's own `ChannelRef` already
carries whatever source identity it needs.

No completeness requirement: a context with only `Va` (or `Va`+`Ia`) is
exactly as valid as a full six-channel three-phase bay. Completeness is
a resolver-slice (not-yet-implemented) concern, evaluated per analysis
requirement, never enforced by the context model itself.

Membership is **not** restricted by engineering type (unlike a
Measurement Group's kind restriction) — a context identifies equipment,
not a measurement kind. A calculated-channel member is allowed; no
automatic phase inheritance is derived for one (manual/deferred only,
per explicit owner instruction).

### Canonical phase identity (`app.domain.phase_identity`)

One closed internal vocabulary: `A`, `B`, `C`, `N`, `AB`, `BC`, `CA`,
`unknown`, `not_applicable`. Every source-native convention (A/B/C,
R/Y/B, L1/L2/L3) normalizes into this set; the original engineer-facing
label (e.g. `"R"`) is preserved separately (`original_phase_label`) for
display only — resolver/matching logic must only ever compare the
canonical value.

**Convention-aware normalization guardrail**: the raw token `"B"` is
genuinely ambiguous alone — canonical `B` under A/B/C, canonical `C`
under R/Y/B (R→A, Y→B, B→C). `infer_phase_convention()` resolves this
from the *other* phase evidence present in the same context ("A"/"C" is
A/B/C-exclusive evidence; "R"/"Y" is R/Y/B-exclusive evidence); with no
evidence, or conflicting evidence, the convention stays unresolved and
every such token normalizes to `unknown` — never guessed.

**Phase provenance** (not a numerical confidence score, by explicit
owner instruction): `engineer_confirmed` / `manual` (top, equal
authority) > `structured_metadata` > `detected_from_name` > `unknown`.
`phase_identity.may_overwrite_phase_assignment()` enforces that an
`engineer_confirmed`/`manual` assignment is never overwritten by
anything automatic — the sole write path that IS allowed to set that
tier is the explicit per-member phase-correction service function
(`update_member_phase()`), never automatic re-detection.

### Automatic detection (`app.domain.engineering_context_detection`)

Deterministic, name-suffix-based clustering — the same deliberate
restraint `app.domain.measurement_group_detection` already established
(never probabilistic, never waveform analysis). The one structural
difference from Measurement Group detection: this module strips ONE
further trailing kind-marker letter (`V`/`I`) off the phase-stripped
base name to get a **cross-kind** clustering root, so `ALPHA1_VA`/
`ALPHA1_VB`/`ALPHA1_VC`/`ALPHA1_IA`/`ALPHA1_IB`/`ALPHA1_IC` cluster into
ONE candidate context (unlike Measurement Group detection's own
kind-scoped `(base_name, kind)` clustering, which keeps Voltage and
Current separate).

**Single-source only, deliberately.** Detection never looks at more
than one source's channels at once — the safest way to guarantee it
never silently merges two different physical bays across files on
name-prefix evidence alone (per the owner's own explicit "be
conservative about automatically merging across sources" instruction).
A genuinely multi-source bay is fully representable by the domain model
and constructible through `update_context_membership()` — just never
produced automatically.

Status: `suggested` when every member's phase resolves confidently and
no two members resolve to the same `(engineering_type, phase)` pair;
`needs_review` otherwise (unresolved convention, or a suspicious
duplicate role) — mirrors Measurement Group detection's own
`STATUS_NEEDS_REVIEW` guard. Never `confirmed`/`manual` — reserved for
an engineer's own review action.

`generate_suggested_contexts_for_source()` (the service-layer wrapper)
is additive-only and idempotent: a channel already claimed by ANY
existing context (any status) is skipped entirely on a re-run — this is
the structural mechanism that makes re-running detection safe against
ever silently overwriting a confirmed/manual assignment, without the
detector itself needing to know about locking.

### API surface (workspace-scoped metadata CRUD only)

```text
GET    /api/v1/workspaces/{workspace_id}/engineering-contexts
POST   /api/v1/workspaces/{workspace_id}/engineering-contexts
GET    /api/v1/workspaces/{workspace_id}/engineering-contexts/{id}
PATCH  /api/v1/workspaces/{workspace_id}/engineering-contexts/{id}
PATCH  /api/v1/workspaces/{workspace_id}/engineering-contexts/{id}/member-phase
DELETE /api/v1/workspaces/{workspace_id}/engineering-contexts/{id}
POST   /api/v1/workspaces/{workspace_id}/sources/{source_id}/engineering-contexts/suggest
```

**No `/analysis/...` resolver endpoint exists yet** — explicitly out of
scope for Slice 1.

### Lifecycle

In-memory, workspace-scoped `EngineeringContextRegistry` (mirrors
`MeasurementGroupRegistry`'s own shape/locking/defensive-copy
discipline exactly), released on "Start New Workspace". Removing ONE
source **prunes only the affected members** — a context may still have
valid members referencing other sources — rather than deleting the
whole context (unlike a Measurement Group's own source-scoped 1:1
removal-on-source-delete behavior).

## Not yet implemented (future slices — architecture recorded here so a later slice can build on it without redesign)

These were part of the original audit's recommendation but are
explicitly out of scope for Slice 1. Recording the intended shape here
so a later slice's design conversation starts from an agreed foundation
rather than re-deriving it:

- **Engineering Role model** — `(engineering_type, phase, representation)`
  triple; `representation` a closed, extensible enum starting with just
  `single_ended`, reserving room for `phase_to_phase`/sequence-component
  representations later without a role-shape redesign.
- **Analysis requirement definitions** — small typed constants (e.g.
  `DistancePhaseA requires {Voltage:A, Current:A}`), not a
  general-purpose rules engine.
- **Automatic resolver** — pure domain function matching required roles
  against one Engineering Context's own membership, subject to Time
  Group/`timebases_aligned()` compatibility (reused unchanged, never a
  parallel timebase rule); statuses `resolved`/`needs_configuration`/
  `ambiguous`/`not_applicable`; never silently picks among ambiguous
  candidates.
- **Frontend UX** — Bay + Analysis Mode selectors driving an
  auto-resolved Inputs list (✓/⚠/ambiguous-with-Resolve-link), reusing
  the same `suggested`/`confirmed`/`needs_review` badge vocabulary
  already established for Measurement Groups. Manual raw-channel picking
  remains an exception path, never the normal path. Not built in Slice 1
  at all (deferred by explicit owner allowance).
- **Digital-channel roles** (e.g. Trip/Pickup/Breaker-Open) — the model
  must extend to represent these later without a redesign; not
  implemented now. A digital channel cannot satisfy an analog role
  (Va/Ia) today, and the service layer's own channel-existence check
  (`_validate_member_channel_ref`) only resolves against
  `analog_channels`, so a digital channel name is rejected the same way
  an unrecognized name is.
- **Voltage↔Current association** — `linked_voltage_group_id` (Per-Unit
  Ibase derivation) must NOT become the analysis-association mechanism;
  bay/context identity + phase identity is expected to be sufficient for
  automatic Va/Ia resolution without a new generic association
  primitive, unless a later resolver slice genuinely proves otherwise.

## Related documents

- [DECISIONS.md — DEC-086](DECISIONS.md#dec-086--analysis-guardrail-slice-1-engineering-context-physicallogical-bay-identity-and-durable-canonical-phase-are-established-as-a-new-additive-metadata-layer-kept-fully-independent-of-measurement-groupsper-unit-and-of-no-fixed-value-until-a-later-slices-automatic-analysis-input-resolver-reads-it) — this slice's full approval record.
- [PER_UNIT_MEASUREMENT_MODEL.md](PER_UNIT_MEASUREMENT_MODEL.md) — the
  Measurement Group model this document's own Engineering Context
  concept is deliberately kept independent of.
- [DECISIONS.md — DEC-085](DECISIONS.md#dec-085--event-playback-is-a-top-level-capability-with-one-authoritative-frontend-only-playback-controller-owning-workspace-time-for-at-most-one-active-time-group-at-a-time-future-analysis-overlays-must-consume-it-never-build-an-independent-playback-clock) —
  Playback (the WHEN axis this document's WHAT axis stays independent of).
