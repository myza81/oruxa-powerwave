# Per-Unit audit Slice 5 - reference-side design assessment

> Historical assessment prepared before Stage 5A approval. The owner has since
> authorized the automatic-only metadata/common-base scope in
> [Stage 5A](PER_UNIT_AUDIT_STAGE_5A.md). That task governs implementation;
> result-specific manual configuration remains deferred to Stage 5B. The
> earlier proposals and pause below describe the assessment stage.

Date: 2026-11-03. Based on `2114a714f43a00fe40b1d293bd1852e1a3e92ad7`,
`feature/calculator-vi-phasors`, four ahead / zero behind fetched origin.
Scope: bounded assessment of the owner-approved PC-001 policy and subsequent
owner direction to define explicit base-side metadata first. **No metadata
contract, eligibility correction, API or UI change is implemented.**

The additional owner requirement to preserve an explicit manual base for the
intended calculated Current result is assessed separately in
[PER_UNIT_AUDIT_SLICE_5_MANUAL_OVERRIDE_ASSESSMENT.md](PER_UNIT_AUDIT_SLICE_5_MANUAL_OVERRIDE_ASSESSMENT.md).
Its UI/storage extension remains a proposal requiring owner approval.

## Authority and current evidence

The owner approved effective-base rather than group-id eligibility for
calculated Current, then explicitly selected a design assessment before
implementation. Measurement side and configured base reference side must remain
independent. Neither CT/VT scaling nor interpretation of existing sample values
is authorized. See DEC-209 for approved principles; all field names, omission
rules, numerical tolerance and release boundaries below are **proposals**.

Verified current code:

- `domain/channels.py:AnalogChannel` and `domain/source.py:AnalogChannelSummary`
  contain ratios but no structured measurement-side field.
- `providers/comtrade.py:_analog_description()` retains the parsed P/S marker
  as `ps=...` in a description. `_apply_analog_scaling()` applies a*x+b, not
  CT/VT ratio conversion. `services/import_service.py:_build_metadata()` does
  not carry that marker into channel summaries. The Current audit fixture uses
  marker `C`, which must not be guessed to mean primary or secondary.
- `CurrentBaseConfiguration` and `PerUnitBaseProfile` have numeric bases/methods
  but no manual/direct base-side declaration. CSV conversion and the inspected
  BEN normalization path supply no explicit measurement side. Ratios, channel
  names, A/kA units or provider type alone cannot establish one.
- `calculated_group_aware_per_unit.resolve_inherited_measurement_group_id()`
  requires one group id; the dispatcher then permits Source Default fallback.
  Provenance mirrors this route. That is the PC-001 policy conflict.
- `PerUnitResolutionOut.source_kind` currently admits measurement_group,
  source_default or null. The existing provenance UI only displays effective
  Current bases for the first two cases.

## Proposed minimal data contract

One shared reference-side vocabulary: `primary`, `secondary`, `unknown`.
Unknown means undeclared/unestablished, never an inferred primary value.

| Location | Proposed field / behavior |
|---|---|
| AnalogChannel and AnalogChannelSummary | `measurement_side`, default unknown; describes stored engineering samples |
| Channel-list response | Additive `measurement_side`, default unknown |
| CurrentBaseConfiguration / Current config request and view | `base_reference_side`; manual is explicitly declared or unknown; equipment_rating resolves primary; none is unknown |
| PerUnitBaseProfile / Source Default request and view | `current_base_reference_side`; direct is declared or unknown; derived resolves primary; none is unknown |
| Channel PU provenance | Additive `measurement_side` and `base_reference_side`, independently reported |

Use validated values, not free text. Do not store an automatically derived base
or inherited side on calculated channels: derive the proof from live input
references/configurations on each request. A genuinely engineer-specified
result base is a separate proposed extension, not an automatic-base cache.
Do not change Voltage-base semantics.

For COMTRADE, pass a structured side directly from the parser's existing marker:
P -> primary, S -> secondary, absent/unrecognized/conflicting -> unknown.
Do not parse arbitrary descriptions or infer side from ratios, phase, magnitude,
unit or names. Old files with nonstandard markers still import; only the new
metadata is unknown. Do not change a*x+b, sample arrays or existing ratio fields.
CSV/BEN remain unknown unless an explicit, independently validated provider
contract already establishes side. A new CSV/BEN side-declaration workflow is
not required for this minimal increment and is not proposed as approved work.

Equipment MVA / nominal L-L derivation remains primary, whether voltage is linked
or manually entered. Manual/direct Ibase never inherits sample side, a previous
equipment-derived primary flag, or a guessed CT interpretation.

## Proposed compatibility matrix and release boundary

This matrix applies to **new automatic combinations across distinct base
authorities**: different groups, group plus Source Default, or different source
defaults. It is not a redesign of existing single-authority normalization.

| Sample side | Base side | Cross-authority outcome proposed |
|---|---|---|
| Primary | Primary | Candidate eligible; all contributors must pass the full common-base proof |
| Primary | Secondary | Unavailable: side mismatch |
| Secondary | Primary | Unavailable: side mismatch; no ratio conversion |
| Secondary | Secondary | Side labels agree, but secondary-reference compatibility still needs an explicit owner rule; conservatively unavailable in the first increment |
| Unknown | Any | Unavailable: measurement reference unestablished |
| Any | Unknown | Unavailable: base reference undeclared |

For the full proof, every contributing sample/base pair must qualify and all
contributors must agree on the same reference meaning. A mix of individually
matching P/P and S/S pairs is not one common reference. Missing/invalid bases,
review status, unresolved links, unsupported units and numerical failures remain
unavailable, never an ambient Source Default override.

**Secondary issue for owner review:** secondary currents from distinct CT
contexts can have different primary meanings despite equal secondary amperes.
The three-state vocabulary does not identify a shared secondary reference frame.
Recommended bounded release: enable new cross-authority primary/primary cases;
retain secondary metadata for truthful reporting but fail closed for new
secondary/secondary combinations until the owner defines whether an expressly
declared secondary calculation is sufficient, or a shared reference identity is
also required. This does not authorize ratio scaling or a new CT model.

Existing shared-group/shared-Source-Default behavior remains unchanged, including
manual bases with unknown sides. This preserves the owner's explicit scope
restriction, not a claim that historical secondary applicability is certified.
The original audit's LIM-001 remains a separate limitation.

## Proposed live effective-base algorithm

1. Keep DEC-052/115/116 Voltage representation restrictions unchanged. Scope
   the new algorithm to automatic calculated Current eligibility.
2. Walk the stored dependency graph to its contributing source channels,
   deduplicating references and guarding missing nodes/cycles. Resolve base
   configuration and units from the current owning source/group on every read.
3. For each leaf, group membership makes its group authoritative even when
   incomplete. Only genuinely ungrouped leaves consult their own Source Default.
   Never use a calculated result's ambient default to repair an input failure.
4. Preserve existing single-authority behavior. Across authorities, apply the
   approved side contract and final owner-approved compatibility matrix.
5. Validate finite positive SI ampere bases using Slice 4 helpers. Proposed
   numerical equivalence: compare overall minimum/maximum with relative
   tolerance 1e-12 and absolute tolerance zero. This accommodates insignificant
   derivation rounding while rejecting materially different bases; no fixed
   ampere allowance makes tiny/subnormal bases accidentally equivalent.
6. Compare all leaf bounds, not adjacent pairs or only an intermediate node's
   representative, to prevent tolerance accumulation through nesting. Use the
   minimum of already equivalent SI bases as an order-independent representative;
   do not average bases or select an unrelated group/default.
7. Evaluate arithmetic only in engineering units, as today. Normalize the final
   physical result once. Do not add differently based PU input arrays. Keep
   Slice 4 result-representability checks on the actual calculated output.
8. Return a final Current result: configured common base, or base_required with
   reason. The latter must stop fallback. Request-local memoization is sufficient;
   do not cache inherited bases/sides on calculated channels.

The existing arithmetic compatibility/alignment rules still govern A/kA and
cross-source creation; this design adds no resampling or automatic engineering
unit conversion. This algorithm covers automatic eligibility. A valid explicit
manual base must take precedence for its intended calculated result under the
owner's additional requirement, without mutating contributing inputs. The
existing internal manual profile pointer has no production API/UI caller and
does not override group resolution. The separate assessment documents that gap,
the proposed minimum extension and tests. An ambient automatic assignment must
never masquerade as an explicit override of incompatible grouped inputs.

## Backward compatibility and atomic updates

Proposed input rules, requiring owner approval:

- Append defaulted domain fields; existing manual/direct objects and requests
  mean unknown. Do not backfill primary from a P sample marker.
- Existing numeric PUT semantics stay unchanged. For the new side field only,
  omission during manual->manual/direct->direct editing preserves an already
  explicit stored declaration. Creation, deletion or transition from another
  method yields unknown unless a side is explicitly supplied. Explicit unknown
  clears the declaration. This avoids older clients erasing an engineer's
  explicit metadata. It is an intentional additive omission rule to review.
- Derived/equipment requests may omit side or supply primary; reject explicit
  secondary/unknown contradictions. None mode clears side to unknown. Proposed
  new enum fields reject null/booleans/unrecognized strings; existing numeric
  omission/null/type contracts are unaffected.
- Validate numeric fields, method/link and side together before publishing one
  configuration. A rejected save preserves registries, indices, confirmation,
  dependent eligibility and ENG/PU values (Slice 1).
- Reuse source-scoped successful-save refresh and stale-response guards
  (Slice 2), including side-only edits. Reevaluate descendants dynamically after
  side/base/link/default changes and group/source deletion. Do not add a second
  refresh system or persistent eligibility cache.

The current registries are ephemeral/in-memory; no database migration is needed.
New dataclass defaults and additive wire fields can preserve existing values and
clients that omit them. This is still an API extension: strict response consumers
and fixtures must be checked; do not claim every external client automatically
accepts new fields. No deployment or stored-file rewrite is part of this proposal.

## Minimal provenance and UI implications

Retain configured/base_required/not_applicable. Report both independent sides,
including unknown. Use existing reason text for missing metadata, side conflict,
base mismatch, unresolved dependencies and numerical unavailability.

For a compatible common Current base, preserve the current source_kind enum:
use null when no single authority exists, group id/name and equipment-rating
fields null, and the actual effective kA base plus a reason explaining common
input agreement. Never label the result Source Default or assign the first
group's identity. This needs a small provenance renderer branch that displays
the common Current base even with source_kind=null. A future per-contributor
details array is optional, not necessary to introduce the minimal contract.

Manual Current Group and direct Source Default editors need a reference-side
selector defaulting to Unknown; equipment/derived mode shows Primary read-only.
Sample side is separately displayed as provider metadata. Do not copy a sample
side into the base selector automatically. Existing manual saves remain allowed
with Unknown; explain that this does not establish new cross-group eligibility.
No calculated-channel editor is implemented or authorized by this metadata
proposal. A separate result-specific manual workflow now needs owner review as
documented in the manual-override assessment. No CT ratio input, sample-side
override workflow, unrelated layout/CSS or Power Calculator change is included.

Waveform/ER consume the same eligibility/provenance; ER preserves unavailable
selection and existing ENG restoration. Coverage is currently a raw-source
read model: keep its existing counts and precedence, and do not claim that raw
coverage counts automatically certify a calculated cross-group result.
Compliance is Voltage-focused; preserve its guardrails and test adjacent shared
conversion paths without adding Current Compliance functionality.

## Required implementation verification after approval

- Domain: every side pairing, unknown and malformed markers; manual versus
  derived semantics; no inferred manual side; historical objects/defaults;
  method transitions; relative-tolerance boundary/ULP/subnormal cases and
  whole-graph rather than pairwise equivalence.
- Provider/API: P/S/absent/C markers reach structured metadata without changing
  arrays; CSV/BEN unknown; legacy request omissions preserve declared metadata
  as approved; explicit unknown reset; enum/null/type rejection; numeric+side
  atomicity snapshots, linked Current and reverse-index invariance.
- Service/API: all 18 original Slice 5 scenarios, both valid and rejected base
  edits, mixed group/default authorities, nested unary/multi-input graphs,
  missing units/dependencies, source/group deletion, cross-source cases where
  existing alignment supports them, linked Voltage/default/side-only changes.
- Cross-feature: identical status/base/results across waveform, cursors,
  anchors, peaks and provenance; ENG array invariance; actual ER availability,
  rejection and restoration; primary common-base and nested browser workflows;
  all prior PU slices, Voltage restrictions and Power regression suites.
- Run focused regressions, complete affected browser files, relevant PU/Power
  browser selection and full backend in new TEMP outputs. Report actual counts,
  warnings, skips and exits before a scoped implementation commit.

## Reproduction and current delivery status

Before production edits, a 48-case prototype reproduced PC-001 across all four
calculated display/measurement endpoints and depth 0/1/2 graphs: **24 expected
failures, 24 passes, zero errors/skips, three pre-existing warnings, exit 1**.
All failures report configured instead of required base_required for different
or missing group bases with ambient 1 kA Source Default. The two 4199 A inputs
remain an 8398 A engineering sum; existing implementation reports 8.398 pu.
Passing cases cover shared-group and genuinely ungrouped legacy behavior.
Every case verifies engineering arrays/configuration snapshots before the
eligibility assertion. This is baseline evidence, not a fixed implementation.

The exact prototype, XML/log/exit and baseline summary are preserved under
`C:/Users/fairizat/AppData/Local/Temp/oruxa-pu-slice5-20261103-r9iy6a_2`.
The new expected-failing prototype was moved out of the normal test tree to
that fresh evidence directory after the owner switched to design-only work;
no pre-existing file was moved. Production and existing tests are unchanged.
No full backend/browser rerun is claimed for this documentation-only assessment.

The manual-override follow-up ran 61 existing registry/group-calculated/API cases:
all passed, zero failures/errors/skips, three existing warnings, exit 0. Its
isolated probe confirms the legacy manual pointer cannot supply group-overriding
result-specific behavior; this does not fix PC-001. See the separate report.

Owner review is required for the proposed fields/omission rules, minimal UI and
provenance treatment, numerical tolerance, secondary/secondary release rule and
the separate manual result configuration/descendant-scope extension.
**Pause before implementation. PC-001 remains unresolved at runtime.** No new
commit, staging, push, merge or deployment. The original audit and all 2,250
protected evidence files remain unchanged. See HANDOFF for continuation scope.
