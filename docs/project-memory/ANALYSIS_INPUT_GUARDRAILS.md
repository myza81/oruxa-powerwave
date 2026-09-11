# Analysis Input Guardrails, Engineering Context & Automatic Role Resolver

**Status: Slice 1 (Engineering Context + durable phase identity) and
Slice 2 (Analysis Requirements + Automatic Input Resolver) are both
implemented** — see [DECISIONS.md — DEC-086](DECISIONS.md#dec-086--analysis-guardrail-slice-1-engineering-context-physicallogical-bay-identity-and-durable-canonical-phase-are-established-as-a-new-additive-metadata-layer-kept-fully-independent-of-measurement-groupsper-unit-and-of-no-fixed-value-until-a-later-slices-automatic-analysis-input-resolver-reads-it)
and [DECISIONS.md — DEC-087](DECISIONS.md#dec-087--analysis-guardrail-slice-2-a-small-typed-analysisrequirementrolespec-domain-plus-a-pure-backend-authoritative-resolver-automatically-match-an-analysis-modes-required-engineering-roles-against-one-engineering-contexts-own-membership-role-identity-and-numerical-readiness-are-kept-strictly-separate).
Everything below marked "not yet implemented" is future-slice scope,
recorded here so a later slice does not need to re-derive the
architecture from scratch.

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

Slice 2 added exactly one new, read-only endpoint (see below); no
calculation endpoint exists.

### Lifecycle

In-memory, workspace-scoped `EngineeringContextRegistry` (mirrors
`MeasurementGroupRegistry`'s own shape/locking/defensive-copy
discipline exactly), released on "Start New Workspace". Removing ONE
source **prunes only the affected members** — a context may still have
valid members referencing other sources — rather than deleting the
whole context (unlike a Measurement Group's own source-scoped 1:1
removal-on-source-delete behavior).

## Implemented (Slice 2): Analysis Requirements + Automatic Input Resolver

### Layering

```text
app/domain/analysis_requirements.py        → requirement definitions (pure)
app/domain/analysis_input_resolution.py    → pure role-matching resolver
app/services/analysis_input_resolution_service.py
        → fetches context/source/calculated-channel state,
          proves timebase compatibility, wraps the pure resolver
app/api/v1/engineering_contexts.py         → thin GET endpoint
```

Engineering rules stay entirely backend-authoritative at every layer —
a future analysis page (Phasor first) receives a fully-resolved (or
precisely-diagnosed) result and never reproduces role-matching,
ambiguity, or timebase logic of its own.

### Requirement model

Small, explicit typed constants — deliberately NOT a general-purpose
rules engine:

```text
AnalysisRequirement
├── analysis_kind        e.g. "phasor"
├── mode                 e.g. "voltage_three_phase"
└── required_roles: tuple[RoleSpec, ...]
        RoleSpec
        ├── role_key            e.g. "Va" (label only — never a matching criterion)
        ├── engineering_type    Voltage | Current
        ├── phase               canonical phase (app.domain.phase_identity)
        └── representation      "sampled" (the only value Slice 2 recognizes —
                                 NOT a claim the signal is already a phasor;
                                 reserved for a future phase_to_phase/
                                 sequence-component value without a shape change)
```

Eight representative Phasor input-role requirements are defined
(`PHASOR_VOLTAGE_PHASE_A/B/C`, `PHASOR_VOLTAGE_THREE_PHASE`,
`PHASOR_CURRENT_PHASE_A/B/C`, `PHASOR_CURRENT_THREE_PHASE`) — these
identify which waveform samples a future phasor engine needs; they do
NOT calculate a phasor.

### Role matching — never by channel name

For each required role, the resolver matches context members purely by
`engineering_type` + canonical `phase` — **channel names play no part in
resolution** (they may have helped an earlier detection pass; persisted
context/phase metadata is the sole authority at resolve time). A member
with `phase = unknown` never matches any concrete-phase role — this is
what makes "never guess an unconfirmed phase" fall out structurally
rather than needing a special case.

### Status semantics

- **`resolved`** — every required role matches exactly one candidate
  (and, for a multi-role match spanning more than one source, their
  timebases are proven compatible — see below).
- **`needs_configuration`** — one or more roles are missing or
  potentially-fixable. Per-role diagnostics
  (`missing_role_reasons[role_key]`) distinguish `role_missing`
  (nothing in the context matches at all) from
  `phase_identity_missing` (a same-`engineering_type` candidate exists
  but its own phase is unresolved) — an addition beyond the audit's own
  flat sketch, needed for genuinely actionable diagnostics.
  `timebase_incompatible` is a third reason, applied by the SERVICE
  layer after an otherwise-fully-resolved result fails timebase proof.
- **`ambiguous`** — more than one candidate matches the exact same role.
  **Never resolved by preference** (not by raw-vs-calculated, name
  length, detection confidence, or first-seen order) — both/all
  candidates are returned, unchanged, for the engineer to disambiguate
  via Slice 1's own `update_member_phase()`/membership-correction paths.
- **`not_applicable`** — reserved for a fundamentally invalid
  requirement (e.g. one declaring zero required roles); not reachable by
  any of the eight known Phasor requirements today. Deliberately not
  overused — an incomplete-but-legitimate context is always
  `needs_configuration`, never `not_applicable`.

### Timebase compatibility — reused, never reinvented

The pure resolver never touches sample arrays. Only after role matching
already narrows a multi-role requirement down to exactly one candidate
per role does the SERVICE layer prove cross-source compatibility, reusing
`app.domain.calculated_channel.timebases_aligned()` completely unchanged
— same-source roles short-circuit instantly (identical
`reference_source_id`); a genuinely different source requires proven
identical absolute sample instants. Never resamples, never
interpolates, never invents a new alignment rule. On failure, an
otherwise-`resolved` result is downgraded to `needs_configuration` /
`timebase_incompatible` — role identity was still correctly determined,
only simultaneous evaluation is blocked.

### Numerical readiness — separate from role identity

`numerically_ready: bool` (whole-resolution level) is `True` only when
`status == resolved` AND every resolved role's own channel carries a
non-blank unit. A blank-unit Voltage-Phase-A channel still resolves as
`Va` (Powerwave knows what signal it is) but reports
`numerically_ready = False` — role IDENTITY and numerical CALCULATION
readiness are never merged into one concept. Per-Unit display mode has
zero effect on either (the resolver never reads `ww.unitMode` or any
presentation state — Voltage stays Voltage, Current stays Current
regardless of display units).

### Calculated channels

A calculated `ChannelRef` context member is resolved by its own already-
known `engineering_type`/`unit` metadata, exactly like a raw channel —
no automatic phase inheritance (manual/deferred, per Slice 1). If a raw
and a calculated candidate both match one role, the result is
`ambiguous`, exactly like two raw candidates would be — kind is never a
tie-breaker.

### Manual override — none introduced

Slice 1's own `update_member_phase()` (correct a wrong/unknown phase)
and `update_context_membership()` (remove a genuinely duplicate/wrong
member) are sufficient to resolve every ambiguity this resolver can
produce — correcting the authoritative context/phase metadata makes the
NEXT resolution call deterministic. No separate, analysis-specific
override subsystem was introduced (would have been redundant machinery
the owner's own instruction explicitly warned against).

### API surface

```text
GET /api/v1/workspaces/{workspace_id}/engineering-contexts/{engineering_context_id}/input-resolution
    ?analysis_kind=phasor&mode=voltage_three_phase
```

Read-only, nested under one Engineering Context (not a new top-level
`/analysis/...` router) — mirrors how Measurement Groups already nest a
resource's derived views under its own id. Response: `status`,
`required_roles`/`required_role_specs`, `resolved_roles`,
`missing_roles`/`missing_role_reasons`, `ambiguous_roles`,
`numerically_ready`, `reason_code`, `message`. Never persisted — always
derived fresh from current context/channel state on every call.

## Not yet implemented (future slices — architecture recorded here so a later slice can build on it without redesign)

- **Frontend UX** — no generic Guardrail-Slice-3 selector UI was built
  (owner decision: the first resolver-driven UI will be Phasor Analysis
  itself, avoiding a placeholder that would be immediately replaced).
  When it is built: Bay + Analysis Mode selectors driving an
  auto-resolved Inputs list (✓/⚠/ambiguous-with-Resolve-link), reusing
  the same `suggested`/`confirmed`/`needs_review` badge vocabulary
  already established for Measurement Groups.
- **Playback integration** — a future analysis engine will evaluate a
  resolved role's own channel AT `wwPlayback.currentTime`; the resolver
  itself stays completely ignorant of Playback (no subscription, no
  animation-frame-frequency re-evaluation — input resolution is
  configuration/selection work, evaluated on demand).
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

- [DECISIONS.md — DEC-086](DECISIONS.md#dec-086--analysis-guardrail-slice-1-engineering-context-physicallogical-bay-identity-and-durable-canonical-phase-are-established-as-a-new-additive-metadata-layer-kept-fully-independent-of-measurement-groupsper-unit-and-of-no-fixed-value-until-a-later-slices-automatic-analysis-input-resolver-reads-it) — Slice 1's full approval record.
- [DECISIONS.md — DEC-087](DECISIONS.md#dec-087--analysis-guardrail-slice-2-a-small-typed-analysisrequirementrolespec-domain-plus-a-pure-backend-authoritative-resolver-automatically-match-an-analysis-modes-required-engineering-roles-against-one-engineering-contexts-own-membership-role-identity-and-numerical-readiness-are-kept-strictly-separate) — Slice 2's full approval record.
- [PER_UNIT_MEASUREMENT_MODEL.md](PER_UNIT_MEASUREMENT_MODEL.md) — the
  Measurement Group model this document's own Engineering Context
  concept is deliberately kept independent of.
- [DECISIONS.md — DEC-085](DECISIONS.md#dec-085--event-playback-is-a-top-level-capability-with-one-authoritative-frontend-only-playback-controller-owning-workspace-time-for-at-most-one-active-time-group-at-a-time-future-analysis-overlays-must-consume-it-never-build-an-independent-playback-clock) —
  Playback (the WHEN axis this document's WHAT axis stays independent of).
