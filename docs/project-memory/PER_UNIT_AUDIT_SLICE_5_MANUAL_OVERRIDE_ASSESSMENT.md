# PC-001 manual override - bounded gap assessment

> Historical assessment prepared before Stage 5A approval. The owner has since
> authorized the automatic-only metadata/common-base scope in
> [Stage 5A](PER_UNIT_AUDIT_STAGE_5A.md). That task governs implementation;
> result-specific manual configuration remains deferred to Stage 5B. The
> earlier proposals and pause below describe the assessment stage.

Date: 2026-11-03. Verified against `2114a714f43a00fe40b1d293bd1852e1a3e92ad7`
on `feature/calculator-vi-phasors`, four ahead / zero behind fetched origin.
Status: **design only; owner review required before extending UI or storage**.
This supplements [the reference-side assessment](PER_UNIT_AUDIT_SLICE_5_DESIGN.md).
No production functionality, schema, UI or existing test has been changed.

## Approved requirement and existing contract

[DECISION] The owner's additional PC-001 requirement preserves manual override:
when automatic Current PU resolution fails because contributing bases differ or
are unknown, an engineer must be able to supply a valid explicit base for the
intended calculated result. That base takes precedence, has manual provenance,
and must not alter input groups/bases. Numerical safety, measured-unit validation
and physical compatibility still apply. The owner explicitly requires checking
existing mechanisms and obtaining approval for any new UI/storage extension.

DEC-050/model sections 10 and 16 preserve engineer-supplied Ibase and overrides.
DEC-049 decisions 6/7 establish a separate calculated-assignment contract:
automatic inheritance, explicit manual assignment, and explicit manual
unassignment are distinct states. Recompute must never overwrite a manual
choice; manual unassignment must not silently resume automatic inheritance.
The source-bound addendum retains this calculated-assignment lifecycle.
DEC-051 later makes inherited group resolution authoritative ahead of the legacy
profile path. The new owner requirement establishes the intended PC-001 Current
manual precedence; it does not authorize changing Voltage restrictions or
silently broadening historical assignment behavior.

## Verified implementation gap

| Mechanism | Current capability | Why it does not supply the requested workflow |
|---|---|---|
| Current Group manual Ibase | Engineer enters a group-scoped kA base | Editing it changes the input group's own configuration and all its eligible members |
| Source Default direct Ibase | Engineer enters one source-scoped kA base | Editing it changes shared source configuration; it is not an independent result base |
| `PerUnitRegistry.ChannelAssignment` | Stores `mode` and a source-profile pointer, including manual/None | Stores no independent numeric result base or base reference side |
| Internal manual-assignment setter | Changes only a calculated result's assignment record | No production caller or API/UI action reaches it; it cannot override authoritative inherited group resolution |
| Calculated-channel creation `override` flag | Acknowledges operation suitability checks for RMS/ROCOF | It is not a PU-base override or a physical-compatibility bypass |
| PU provenance | Reports group or Source Default resolution | Does not expose calculated assignment mode or a result-specific manual base origin |

Evidence in current code:

- `services/per_unit_registry.py:ChannelAssignment`,
  `set_manual_assignment_for_calculated_channel()` and
  `recompute_inherited_per_unit_assignments()` retain the internal two-axis
  lifecycle. An AST scan of `backend/app` finds zero calls to the manual setter.
  Its comment referring to a setup UI is not evidence of a current UI caller.
- `api/v1/per_unit.py` and the generated application OpenAPI expose source-scoped
  configuration writes and coverage reads. Calculated PU provenance is read-only;
  no calculated-base assignment/configuration write route exists.
- `frontend/index.html:wwApplyPerUnitProfileEditor()` writes
  `/per-unit/sources/{source_id}`. The Current Group drawer writes group config.
  Neither editor accepts a calculated-result target.
- `api/v1/calculated_channels.py:_resolve_profile_for_calculated_channel()`
  retrieves the pointer without passing assignment mode to the dispatcher.
  `calculated_channel_service._resolve_effective_per_unit_for_calculated_channel()`
  and `per_unit_provenance_service.build_calculated_channel_provenance()` resolve
  inherited groups first. Manual pointer presence is not a precedence switch.

Isolated characterization: two 4199 A inputs in one 2 kA group produce 8398 A,
or 4.199 pu. A source profile is separately configured at 1 kA. Directly invoking
the internal manual setter with that profile leaves **all four endpoints at
4.199 pu**, rather than 8.398 pu. Explicit internal manual unassignment also
leaves group conversion active. Provenance reports the 2 kA Measurement Group;
input group and Source Default response snapshots remain identical. This is
documented existing behavior, not a product correction made in this pass.

[FACT] The lifecycle foundation is reusable, but the complete engineer-facing,
calculated-result-specific override does not currently exist. Repointing the
internal pointer alone, editing a source/group, or reusing creation `override`
would not satisfy the new requirement. A small feature extension needs approval.

## Proposed minimal extension - not approved for implementation

[PROPOSAL] Extend the existing workspace/calculated-id assignment record with an
optional explicit manual Current base value object: canonical kA amount and an
independently declared `primary|secondary|unknown` reference side. Reuse existing
registry locking, calculated/workspace cleanup and dependency graph. Do not
create a new profile identity, database, persistent graph, CT model, or stored
automatically derived base. This **is a storage-model extension**, even though
the registry is ephemeral; it must not be implemented without owner approval.

Keep existing `mode` and legacy `profile_id` fields compatible. A new explicit
base and a legacy profile pointer must not compete in one record. Preserve the
legacy pointer path outside the approved scope; do not migrate historical manual
pointers or manual group/default bases into new result-specific configurations.

The minimal Current result contract proposed for review has three explicit
actions/states:

| Result selection | Resolution behavior proposed |
|---|---|
| Automatic | Resolve compatible live contributing bases; unresolved grouped inputs cannot borrow ambient Source Default |
| Explicit manual base | Validate this result's manual base and physical applicability first; use it when eligible, independently of automatic input-base agreement |
| Explicit manual unassignment | Keep PU unavailable until a later explicit assignment or explicit Return to Automatic action |

Clearing a value and returning to automatic must be different actions. A source,
group, linked Voltage base or automatic recompute cannot overwrite a manual
selection. If a saved override becomes inapplicable after a dependency change,
retain the engineer's choice and report base_required with a reason; do not
quietly select an automatic base. Any Return to Automatic action is an explicit
new workflow for owner review, not a reinterpretation of manual unassignment.

[PROPOSAL] Add a narrowly scoped calculated-result Current configuration read/
write action, following existing versioned workspace API conventions. Validate
the entire candidate and target identity/type before atomically replacing its
assignment. Do not add a PU field to generic math parameters or reuse the
operation-suitability `override` flag. Reuse the established base editor's fixed
kA input and refresh/stale-response conventions through a selected-result entry
point. Show Automatic / Manual and separate sample/base reference meaning.
This requires a **new API/UI workflow**; reuse of components does not make it an
existing workflow. Exact route, request fields and UI interaction remain pending
owner approval. No prototype UI is included in this assessment.

## Eligibility and compatibility boundaries

These are proposed checks for the new explicit override, within the separate
reference-side contract still awaiting review. They do not alter historical
single-authority normalization or existing manual Group/Source Default saves.

| Input situation | Automatic result | Explicit manual result proposed |
|---|---|---|
| Effective bases agree and physical references are proven compatible | Eligible under PC-001 automatic proof | Valid explicit result base takes precedence |
| Input base amounts differ, but physical result and reference side are compatible | base_required | May use explicit result base; input bases are not used for this normalization |
| Input base absent, or its reference side undeclared, but sample/result physical meaning is independently proven | base_required across authorities | May use a valid explicit result base; do not invent missing input-base metadata |
| Actual sample/result reference side is unknown or conflicting | New cross-authority proof fails closed | Manual numeric entry alone does not establish physical compatibility |
| Primary samples with secondary manual base, or the reverse | Incompatible | Incompatible; no ratio scaling |
| Secondary inputs/result and secondary manual base | Pending common-secondary-reference policy | Same unresolved policy applies; manual entry cannot bypass it |
| Unsupported/missing measured units, incompatible quantity, unresolved dependency, unsafe normalization, or required confirmation absent | Unavailable | Unavailable; no bypass |

The distinction between an unknown **input normalization base** and an unknown
**physical sample/result reference** is essential. Requiring all input bases to
agree before permitting a manual result base would defeat the override. Letting
a manual number assert an unknown sample side would violate the owner's
separate-side requirement. Any additional sample-side declaration workflow,
including for CSV/BEN, needs separate approval; this proposal does not add one.

Continue computing physical ENG arithmetic first; normalize the result once.
Use Slice 3 supported-unit checks and Slice 4 positive/finite/SI-denominator and
full-output representability checks. Reject booleans and invalid enum values
before coercion. No automatic CT/VT conversion, input rescaling, engineering
sample rewriting or Power calculation change.

## Provenance, dependency and compatibility treatment

[PROPOSAL] Add an explicit resolution mode/origin that distinguishes a manually
specified **calculated-result** base from automatic common-base resolution and
from a group's manual method. Report actual effective kA base, independently
declared base side, sample/result side and target calculated identity. Do not
label a result-owned manual base Source Default or attribute it to one input
group. Existing source_kind/status consumers need an additive compatibility
review; exact fields/enum handling are not approved here. Conversion and
provenance must share the same decision, including every unavailable reason.

Preserve automatic base lookup on live leaves, not stale stored inherited
numbers. Revalidate manual physical applicability after input/reference/unit/
timing changes. Input base-only changes do not rewrite the chosen result base.
Reuse source-scoped refresh guards; a result-only manual edit also needs a
refresh of that result and affected descendants, without changing source
configuration or treating raw-source coverage as calculated readiness.

[PROPOSAL/OPEN] Preserve DEC-049's inheritance shape when adapting it to a
result-owned base: an automatic unary child may inherit its parent's live
explicit base, while automatic multi-input children must prove their own
effective-input base agreement. A manually configured descendant retains its
own choice. Physical compatibility still requires inspecting contributing
samples; do not discard a parent's explicit base and substitute its unresolved
automatic input bases, or normalize an already normalized PU array again.
The new value object is not a source-profile identity, so its resolution
boundary, transitive tolerance handling and provenance need explicit review
with the reference-side contract. Do not silently change the existing legacy
pointer cascade or implement a different descendant policy in this assessment.

Benefits: engineer escape route for a known result base, honest provenance and
no input mutations; minimal reuse of existing lifecycle and safety mechanisms.
Risks: confusing manual unassignment with automatic reset, incorrect descendant
inheritance, stale result refresh, and falsely certifying unknown physical
reference sides. Impact is confined to a newly approved Current result workflow;
Voltage representation restrictions, original Group/Source Default workflows,
physical arrays and Power remain unchanged. No broader measurement-scaling
redesign or database migration is needed for this bounded extension.

## Required regression coverage after approval

1. Differing input bases and missing input bases: automatic base_required;
   compatible explicit result base works with independently calculated PU.
   Equal bases with a different explicit result base prove manual precedence.
2. Both successful and rejected manual requests compare all input groups,
   metadata/status, base configurations, reverse indices, Source Default and
   ENG/PU values. Rejected requests preserve the target override as well.
3. Manual amount/side validation, booleans, zero/negative/nonfinite values,
   SI/subnormal/overflow boundaries, missing/wrong units, quantity restrictions,
   unknown/conflicting sample side and unresolved/confirmation failures.
4. Manual/automatic provenance and actual base agree across waveform, cursors,
   anchors, peaks, ER and calculated provenance. No ambient fallback after an
   invalid or explicit-unassigned manual selection.
5. Dependency base/link/default/side changes do not overwrite manual choices;
   physical applicability is reevaluated. Test explicit unassign, distinct return
   to automatic, override replacement, deletion and workspace cleanup.
6. Nested unary/multi-input graphs, manual parent/automatic child and manual
   child/automatic parent under the approved descendant rule; cross-source cases
   only where existing alignment and physical compatibility permit them.
7. Real UI save/rejection, selected result identity, retained input settings,
   base/side/provenance, effective numerical values and stale-response fences.
   Retain all 18 original PC-001 scenarios, prior PU slices, Voltage and Power
   checks, relevant complete browser files and full backend regression suite.

## Assessment verification and approval boundary

Existing registry, group-aware calculated endpoint and Source Default API suites:
**61 passed, zero failures/errors/skips, three existing warnings, exit 0**.
An isolated probe made 12 endpoint observations plus provenance/configuration
checks; a separate generated-OpenAPI inventory and AST caller scan confirm the
workflow gap. New evidence is isolated under
`C:/Users/fairizat/AppData/Local/Temp/oruxa-pc001-manual-assessment-20261103-vh5oepnm`.
The earlier PC-001 reproduction remains **24 expected failures / 24 passes**;
this is not a claim that the defect or new manual workflow is implemented.
Full backend/browser reruns await an approved implementation.

**Owner review requested:** the separate reference-side proposal and this
minimal result-scoped storage/API/UI extension, manual lifecycle, provenance
and descendant scope. The owner's explicit instruction to obtain approval for
extensions is the reason implementation remains paused. No production change,
staging, commit, push, merge or deployment is included.
