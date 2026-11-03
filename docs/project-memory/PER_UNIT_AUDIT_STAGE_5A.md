# Per-Unit audit Stage 5A - automatic Current common bases

Date: 2026-11-03. Baseline `2114a714f43a00fe40b1d293bd1852e1a3e92ad7`,
branch `feature/calculator-vi-phasors`, four ahead / zero behind fetched origin.
Authority: owner-approved Stage 5A task; DEC-209. **Implemented and verified
locally. Stage 5A acceptance criteria are met. No push, merge or deployment.**

## Implementation and reference contract

PC-001 automatic Current resolution now walks live calculated dependencies to
contributing source channels. Group membership makes that group's base
authoritative, even if it is missing, unconfirmed or otherwise unavailable.
Only genuinely ungrouped channels consult their own Source Default. An ambient
calculated assignment cannot repair incompatible grouped inputs.

The shared reference vocabulary is primary/secondary/unknown. Unknown never
means an inferred primary value. Fields are additive:

- AnalogChannel, AnalogChannelSummary and channel responses: measurement_side.
- Current Group configuration/request/view: base_reference_side.
- Source Default configuration/request/view: current_base_reference_side.
- PU provenance: measurement_side, base_reference_side and nullable
  resolution_origin=automatic_common_base for multi-authority Current results.

Recognized COMTRADE P/S markers populate structured measurement side directly;
missing, unrecognized or conflicting markers become Unknown. The a*x+b path,
ratios, waveform arrays and physical engineering units are unchanged. CSV/BEN
remain Unknown; no provider-type, phase/name, magnitude or ratio inference.

Equipment/Source Default derived bases represent Primary. Manual Group/direct
Source Default bases require an independent declaration or remain Unknown.
Omitting side preserves an existing declaration only within the same manual/
direct method; creation or method transition starts Unknown. Explicit Unknown
resets it. Derived requests may omit side or declare Primary; contradictory
declarations reject. None clears side to Unknown. Invalid enum/null/boolean
values reject before publication. Existing numeric PUT semantics are unchanged.

Both existing editors expose the independent manual/direct selector. Derived
bases show Primary read-only; toggling to manual does not copy that declaration.
Current calculated channels use the existing read-only provenance modal and
calculated provenance endpoint, without adding a configuration workflow.

## Compatibility and numerical behavior

This matrix applies to distinct group/default authorities, after all existing
quantity, unit, dependency, confirmation, valid-base and result-safety checks:

| Measurement side | Base side | Stage 5A cross-authority outcome |
|---|---|---|
| Primary | Primary | Candidate eligible if every effective base agrees |
| Primary | Secondary | Unavailable |
| Secondary | Primary | Unavailable |
| Secondary | Secondary | Unavailable pending a shared secondary-reference definition |
| Unknown | Any | Unavailable |
| Any | Unknown | Unavailable |

Historical same-group/shared-Source-Default normalization remains supported when
metadata is missing. This does not certify the historical secondary applicability
limitation. Secondary compatibility is deferred, not permanently prohibited.

The resolver deduplicates source references, visits shared ancestors once, and
rejects missing/cyclic/incompatible dependencies. It collects all effective SI
ampere bases across the complete graph, rather than comparing representative
intermediate results. Numerical agreement uses (max-min)/max <= 1e-12 with zero
absolute tolerance. Division avoids underflow of tolerance*max for tiny bases.
The minimum equivalent SI base is deterministic and independent of traversal;
no averaging or arbitrary group attribution is used.

Existing project comparisons use context-specific tolerances (for example,
sampling alignment); none defines Current base equivalence. The chosen 1e-12
relative threshold accommodates floating-point derivation rounding while
rejecting engineering-scale changes and avoids absolute epsilon acceptance of
unrelated tiny bases. Boundary, ULP, nested-extrema and subnormal tests cover it.

Arithmetic remains in ENG. Inputs are not normalized before calculation; the
final physical result is divided once. Existing unit checks apply to contributors
and result; Slice 4 numerical bounds apply to the actual output. Large opposing
physical inputs may therefore legitimately produce a representable zero result.
No inherited numeric base is persisted or permanently cached. Later base/link/
side/default/group/source changes are read live. Existing Slice 2 source-scoped
refresh and stale-response fences refresh affected Waveform/ER values.

## Provenance, integrity and compatibility

The source_kind enum is unchanged: measurement_group/source_default/null. A
cross-authority result uses null group identity and source_kind, plus explicit
automatic_common_base origin, actual common kA base and independent sides.
Unavailable results give an honest reason. A single authority retains its
existing group/default provenance. Conversion and provenance call the same
Current resolver. Raw-source coverage retains its existing scope and is not
presented as calculated readiness.

New side values are validated with the complete candidate before publication.
Current config registries already copy on read/write; side and numeric fields
are published in one configuration replacement. A publication fault preserves
the old config. Source Default constructs a new candidate. Rejected API saves
preserve groups/status/membership, reverse indices, bases/sides, assignments and
effective values. No database or cross-registry transaction framework is added.
Live reads retain the existing per-registry concurrency model; separately
accepted edits are not one global multi-registry snapshot.

API consumers were reviewed: channel response mapping, group view/output,
Source Default view/output, both existing editors, provenance mapping/renderer,
Waveform/scalar calculated endpoints, ER and raw coverage. Additive fields do not
change existing status/source_kind values or numeric field meanings. External
strict response validators may need to accept the documented new fields.

DEC-050 identity/ownership and DEC-052/115/116 Voltage restrictions remain.
Source Default, equipment-current derivation, calculated math, physical samples,
Power and Voltage-only Compliance scope are unchanged. Existing internal manual
assignment graphs retain their legacy resolution path; no engineer-facing
result-specific manual override is introduced.

## Files changed

| File | Purpose |
|---|---|
| `backend/app/api/v1/calculated_channels.py` | Pass live source/default context to conversion and provenance. |
| `backend/app/api/v1/measurement_groups.py` | Map side request omission and group response metadata. |
| `backend/app/api/v1/per_unit.py` | Pass explicit/omitted Source Default side. |
| `backend/app/api/v1/sources.py` | Pass raw-channel sample side to provenance. |
| `backend/app/domain/channels.py` | Structured sample-side descriptor. |
| `backend/app/domain/current_group_config.py` | Independent Current Group base side. |
| `backend/app/domain/per_unit.py` | Independent Source Default current-base side; math unchanged. |
| `backend/app/domain/reference_side.py` | Shared vocabulary, marker decoding and candidate-side semantics. |
| `backend/app/domain/source.py` | Sample-side source summary. |
| `backend/app/providers/comtrade.py` | Carry the parsed P/S marker without changing analog scaling. |
| `backend/app/schemas/measurement_group.py` | Validated additive group request/response field. |
| `backend/app/schemas/per_unit.py` | Validated additive default/provenance fields; source_kind unchanged. |
| `backend/app/schemas/source.py` | Additive channel measurement-side field. |
| `backend/app/services/calculated_channel_service.py` | Shared Current resolution for all four conversion functions. |
| `backend/app/services/calculated_current_per_unit.py` | Live common-base graph proof and unavailable reasons. |
| `backend/app/services/current_group_config_service.py` | Validate side with each complete method candidate. |
| `backend/app/services/import_service.py` | Propagate structured measurement side to source metadata. |
| `backend/app/services/measurement_group_view_service.py` | Expose effective base-reference side. |
| `backend/app/services/per_unit_provenance_service.py` | Shared Current proof, origin and independent side provenance. |
| `backend/app/services/per_unit_service.py` | Source Default side candidate/omission semantics and read model. |
| `backend/tests/test_current_effective_base_graphs.py` | Live dependencies, global tolerance, mixed authorities and safety. |
| `backend/tests/test_current_effective_base_inheritance.py` | Original PC-001 reproduction, full endpoint/depth/reference matrix. |
| `backend/tests/test_reference_side_configuration.py` | Providers, omission, transitions, atomic rejection/publication fault. |
| `browser-tests/current-common-base.spec.js` | Real editor rejection/success, Waveform, read-only provenance and ER. |
| `docs/project-memory/CURRENT_STATE.md` | Operational Stage 5A status and deferred scope. |
| `docs/project-memory/DECISIONS.md` | Owner Stage 5A approval and compatibility/metadata policy. |
| `docs/project-memory/HANDOFF.md` | Continuation, verification evidence and Stage 5B stop boundary. |
| `docs/project-memory/MIGRATION_PLAN.md` | Stage 5A sequence and Stage 5B deferral. |
| `docs/project-memory/PER_UNIT_AUDIT_SLICE_5_DESIGN.md` | Preserved historical assessment with approval-scope addendum. |
| `docs/project-memory/PER_UNIT_AUDIT_SLICE_5_MANUAL_OVERRIDE_ASSESSMENT.md` | Preserved historical manual gap; Stage 5B remains deferred. |
| `docs/project-memory/PER_UNIT_AUDIT_STAGE_5A.md` | Implementation, per-file scope, compatibility and verification report. |
| `docs/project-memory/PER_UNIT_MEASUREMENT_MODEL.md` | Authoritative Current common-base/reference-side contract. |
| `frontend/index.html` | Existing base-side selectors, derived display and Current provenance. |

## Regression evidence and delivery status

- Baseline: 132 new cases, **108 failures / 24 passes**, zero errors/skips,
  three existing warnings, exit 1. All failures concern the intended compatibility
  or ambient-default behavior; no fixture/setup errors.
- Initial corrected selection: **173 passed**, zero failures/errors/skips,
  three existing warnings, exit 0.
- Broader focused selection: **494 passed**, zero failures/errors/skips,
  three existing warnings, exit 0. Additional subnormal/cancellation cases are
  included in the full backend run.
- Full backend: **11,573 collected: 11,253 passed, 320 skipped, zero failures/
  errors, 21 existing warnings, exit 0**. This includes all **185** new cases:
  132 inheritance cases, 22 graph cases and 31 reference-side/configuration cases.
  Existing Slice 1 atomicity (45), Slice 3 eligibility (69), Slice 4 numerical
  integrity (164), group/configuration, calculated inheritance, Waveform,
  cursor, ER, Compliance and Power suites remain green.
- Backend skips: 153 owner sample PDFs absent, 49 BEN reference cases without
  the configured reference directory, 17 POSIX-shell cases unavailable on
  Windows, and 101 existing relay/catalog/geometry non-applicability cases.
  These conditional/platform skips remain unexecuted; no pass is claimed for
  them. The detailed skip reasons are retained in backend-summary.json.
- New complete browser file rerun: **3/3 passed**, zero failures/global errors/
  skips/flaky cases, exit 0. Full relevant browser selection: **392/392 passed**
  across **32 explicit files**, zero failures/global errors/skips/flaky cases,
  exit 0. Selection includes PU atomicity/synchronization/eligibility/numerics,
  Current common bases, calculated presentation/preview/null/ROCOF/Power,
  three-phase Power, Waveform/cursors, ER, Compliance and lifecycle paths.
  The two pre-existing untracked screenshot specs were not selected. Browser
  results supply no separate warning count; none is inferred from pass status.
- First new browser attempt: three test-selector timeouts, corrected in the new
  test without changing production behavior or weakening assertions. Failure
  artifacts remain. Test-managed server teardown hung; only verified owned test
  processes were stopped. Fresh hidden local servers use isolated TEMP logs.

Independent electrical checks: 4199 A + 4199 A stays 8398 A in ENG. Distinct
2 kA/4 kA groups with ambient 1 kA default must be unavailable, rather than
8.398 pu. Compatible Primary 2 kA/2 kA groups yield 4.199 pu. Linked equipment
bases use S/(sqrt(3)*VLL), and an accepted Voltage change reevaluates agreement.
Rejected Voltage/side saves preserve configurations and resulting values.

Full-state comparisons cover group identity/status/metadata/membership, reverse
membership indices, base values/sides, Source Defaults and calculated assignments,
as well as complete ENG/PU arrays. A response status alone is not used as proof.
The real browser workflows cover accepted side/base saves, rejected combined
side/base saves, live Waveform/provenance refresh and retained ER selection with
safe ENG fallback. A linked equipment base is independently checked using
S/(sqrt(3)*VLL) before and after accepted or rejected Voltage changes.

Independent numerical proof: **1,800** Decimal comparisons across exponents
-1074 through 1023 and near-tolerance boundary factors have zero classification
mismatches. AST comparison against the baseline confirms **78** reviewed domain
functions and COMTRADE analog scaling are unchanged, including Voltage/Current
formulas, calculated arithmetic, numerical safety, phasor and sliding-phasor
functions. Production source hashes match the implementation used throughout
the full tests. Engineering arrays are compared independently of PU availability;
no stored sample rescaling or input-group mutation is introduced.

Evidence is isolated under
`C:/Users/fairizat/AppData/Local/Temp/oruxa-pu-stage5a-20261103-a64oug4y`.
Original audit/evidence and all five pre-existing untracked paths are preserved.
Final comparison confirms **2,250 files**, no additions/removals/changes to their
hashes, sizes or modification times. Audit SHA-256 remains
`e98310e2d3618d22b2468df3c878904e6e2009bf94ba4f338c1603c740ec256b`.
The five paths are .audit/, .slice1-evidence/, test-results/,
browser-tests/compact-label-screenshots.spec.js and browser-tests/e3b-screenshots.spec.js.
They remain outside the scoped local Stage 5A revision. Its containing Git commit
records the delivery hash; the implementation parent is 2114a71. The fetched
upstream had no incoming commits. No push, merge or deployment is authorized.

## Scope boundary and remaining limitations

Stage 5B is deferred: no result-owned manual base storage, write API/editor,
explicit calculated-result unassignment or new manual descendant policy. The
owner's manual-override principle remains required; see the separate historical
[manual assessment](PER_UNIT_AUDIT_SLICE_5_MANUAL_OVERRIDE_ASSESSMENT.md).
CSV/BEN declaration UI, CT/VT scaling, secondary identity model, CSV discovery-id
correction and unrelated Power changes are excluded. The original audit remains
historical evidence. Stop after Stage 5A verification and owner reporting.
