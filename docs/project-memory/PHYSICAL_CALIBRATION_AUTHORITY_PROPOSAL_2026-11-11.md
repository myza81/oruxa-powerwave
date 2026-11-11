# Physical calibration authority — bounded design proposal

Date: 2026-11-11. **[PROPOSAL] Not approved or implemented.** Owner requested
this separately from the BEN5K mapping / COMTRADE missing-data corrections.
No scaling factor, CT/VT conversion, PU mathematics or source-side authority
change is authorized by this document. No Slice 6D work is included.

## Problem and independent authorities

The accepted BEN-wide audit proves that a successfully decoded word, a correct
channel slot, a plausible unit label and a configured nominal base do not prove
physical calibration. BEN5K's existing packed-word/gain convention remains
unverified. Correcting its sample slots or an exported missing-data sentinel
does not resolve that uncertainty. An engineer selecting Primary or entering
a manual PU denominator cannot establish the calibration of the numerator.

Keep these independent:

| Authority | What it establishes | What it cannot establish |
|---|---|---|
| Structural decoding | File/sample boundaries, signed representation | Physical amplitude |
| Channel mapping | Descriptor refers to the right payload column | Calibration, wiring or nominal Voltage |
| Missing-data validity | A particular sample is absent/present | Calibration of present samples |
| Physical calibration | A declared numerical transform and representation have adequate independent evidence | Nominal network/base value or sample reference side |
| Measurement side | Primary / Secondary / Unknown | Numerical gain or configured base side |
| Nominal/base authority | Accepted denominator and reference interpretation | Physical validity of the measured numerator |
| Engineering eligibility | All required authorities and operation-specific checks pass | A substitute for any upstream proof |

Existing DEC-050/051 base precedence, DEC-084 gap handling, DEC-210/211 side
policy and DEC-212 raw-Current ENG behavior remain independent. The proposed
calibration gate must not be implemented by changing nominal detection,
inventing a CT/VT ratio, treating waveform disagreement as nominal authority,
or assigning Primary from units/ratings. Established behavior is changed only
at the explicitly approved calibration gate.

## Smallest proposed data contract

Add an immutable optional `PhysicalCalibrationAuthority` to each normalized
`AnalogChannel`; propagate it to the active channel summary and source/channel
API metadata. Proposed fields:

```text
status          verified | unverified | invalid
reason          stable machine-readable reason
transform_id    versioned interpretation of raw word -> engineering value
evidence_refs   immutable references identifying evidence, its scope and hashes
```

An absent object means **not assessed under this new contract**, not Verified.
This additive default preserves existing providers and stored/live records.
Initial enforcement is scoped to native legacy BEN5K channels explicitly
marked `unverified / ben5k_absolute_calibration_unverified` by their adapter.
For a source already identified as legacy BEN5K, an absent authority must also
fail closed as Unverified; it must not obtain the compatibility exemption by
losing metadata. This includes an existing live source with retained legacy
layout provenance. The exemption is for other, not-yet-assessed provider
contracts, never for a known BEN5K source or its derived dependencies.
This avoids silently reclassifying every historical COMTRADE, CSV or SubBen
record as either certified or blocked. Extending enforcement to other
providers is a separate owner decision after their contracts are assessed.

Verification concerns the numerical interpretation and stated representation,
with the evidence's limits recorded; it must not imply a current calibration
certificate for the physical instrument when none exists. Evidence should
identify original recording/configuration hashes, channel identities, hardware
and firmware where relevant, the gain/offset/bit convention, instantaneous vs
already calculated representation, validated units, and independent reference
method. A schema-valid CFG, matching raw export, unit label, steady RMS near
nominal, or absence of warnings is insufficient alone.

Do not create an editable “calibration verified” checkbox. In the first stage,
only a later owner-approved, evidence-backed adapter contract can publish
Verified. A file-specific observation must not promote all recorder families.
Future engineer attestations/evidence import need their own approved workflow;
they are not equivalent to an existing manual base save.

Raw files remain write-once. Keep the existing normalized arrays and raw
decoder inspection capability; the authority object describes their meaning
without applying another transform. Use existing ephemeral workspace lifetime,
not a new database, permanent server store, synchronization system or
environment setting. An evidence reference does not require copying private
recordings into GitHub.

## One policy, enforced at every engineering input boundary

Implement one pure domain evaluator taking contributing leaf-channel
authorities and the operation purpose. Return availability, reason and
evidence provenance. Consumers must use it before normalizing or computing an
authoritative engineering result. Avoid independent frontend eligibility
rules or checking only an immediate calculated parent.

| Input authority | Raw inspection | PU / recorded-input power / Compliance |
|---|---|---|
| Explicit Verified | Allowed | Allowed subject to units, side, base, confirmation, timing, representation and numerical checks |
| Explicit Unverified legacy BEN5K | Allowed with conspicuous calibration limitation | Unavailable: `physical_calibration_unverified` |
| Explicit Invalid | Diagnostic/raw inspection only, with reason | Unavailable: `physical_calibration_invalid` |
| Absent/not assessed | Existing compatibility behavior; never display a new Verified claim | Existing behavior preserved outside initial enforcement scope |

The strict initial BEN5K gate must apply to source-backed calculations in
engineering units as well as PU. Otherwise dividing by a manually chosen base,
using a configured Measurement Group or falling back to ENG simply bypasses
the protection. For nested calculations, any Invalid leaf dominates;
otherwise any explicitly Unverified leaf makes the engineering result
unavailable. All-Verified leaves are necessary, but operation validity is
still required. A mixed legacy-not-assessed path must not manufacture a
Verified claim. Validity masks remain per sample, independently of this
channel-level authority.

Raw diagnostic transformations such as displaying polarity may be retained
only with inherited Unverified provenance and without becoming an
authoritative engineering input. Whether to permit a separately labelled
exploratory RMS/shape analysis is an owner policy choice, not an implicit
exemption. The default proposed stage blocks physical-result creation from
explicitly Unverified leaves; it does not silently generate plausible numbers.

Recommended integration points, identified in the current code:

- `ben/legacy_ben5k/normalize.py` -> shared `AnalogChannel` normalization and
  channel summary/schema: publish/retain the calibration limitation.
- `waveform_service._resolve_effective_per_unit()` and shared PU provenance:
  evaluate before conversion, including cursor/peak/annotation paths. A valid
  base may remain configured while measured-result availability is blocked.
- `calculated_channel_service._resolve_input()` / creation and calculated
  dependency resolution: evaluate all original leaves for physical-result
  operations, including power, RMS, sequence and nested channels. Generic
  operation `override` must not bypass this gate.
- `phasor_analysis_service._fetch_role_candidate()` / readiness: block
  unverified recorded-input amplitudes before supplying phasors to power or
  other engineering consumers.
- `compliance_readiness_service` and `compliance_measurement_service`: fail
  readiness explicitly before auto-preparation, RMS/sequence calculation,
  base conversion or pass/fail evaluation. Do not emit a compliance verdict
  from unverified physical values.

Use dedicated availability reasons, not “enter a Voltage base.” Prefer an
additive `physical_calibration` field plus a domain availability result.
The exact wire representation for blocked PU requests needs approval: a new
`calibration_required` status is clearer than overloading `base_required`, but
requires updating all existing response consumers and frontend fallback
branches. If retaining current status values is chosen for compatibility,
the dedicated reason and calibration metadata must still distinguish a valid
base from unsafe measurement calibration. Do not implement either choice
implicitly in the missing-data correction.

## Power Calculator boundary and manual override

The current `POST /api/v1/calculator/power/single-phase` endpoint is stateless:
it accepts numeric RMS magnitudes/angles, with no workspace or ChannelRefs.
It cannot establish whether a caller typed independent values, pasted a BEN
value, or supplied a computed phasor. Adding a field that merely asserts
“verified” would not establish provenance.

Preserve the existing manual calculator and its numerical safety checks.
Manual input is explicitly engineer-supplied, not a new source-calibration
certificate. Source-backed power calculations must enforce the backend gate
while resolving their ChannelRefs; phasor/autofill paths must not pass
Unverified BEN5K values into the calculator as if they were verified manual
inputs. If the owner requires this stateless endpoint itself to verify
source-backed provenance, an additive source-reference request contract or
reuse of a source-scoped calculation route is necessary and needs approval.
No software can infer the origin of arbitrary pasted numbers from their
magnitude alone.

The same limitation applies if someone manually copies values into a fresh
CSV or an external export strips provenance. Application-generated exports
must preserve known calibration limitations where their format permits, and
known source-derived imports must not be promoted by filename or format
change. An untraceable external file remains not assessed, not Verified.
The proposed compatibility stage cannot guarantee the origin of every such
file; a strict policy blocking all unassessed providers would be a broader
owner decision, not part of this bounded BEN5K proposal.

An existing manual PU base remains an independent denominator. Its save must
not mutate original input groups, declare their calibration Verified, change
their measured side, or allow a blocked measured numerator into PU, power or
Compliance. Calibration authority is not a replacement for manual override;
it identifies what the override can actually establish.

## UI and lifecycle implications

Display an explicit “Physical calibration unverified” state wherever an
affected channel supplies engineering values: list/selection, plot/legend,
cursor/annotation and engineering readiness. Keep this separate from
“Unverified reference,” “Base required,” missing-data gaps and channel review
status. Unit strings and original channel names remain domain metadata;
decorate them with the limitation rather than silently rewriting kV/kA to
make numbers plausible. Use shared presentation helpers and the existing
electrical notation conventions if symbols are displayed.

Raw inspection may remain available, but blocked calculations need a precise
explanation and no misleading success/ready badge. No new calibration editor,
file uploader, persistence or automatic scaling UI is part of this proposal.
Backend enforcement remains mandatory even if a UI control is bypassed.

Bind authority to stable source/channel identity and transform version, not
editable names. Re-import creates a new evaluation; changing a group/base,
renaming a channel, changing units, confirming a group or reusing a calculated
result cannot upgrade it. Include the authority/transform fingerprint in
existing result-cache and stale-response invalidation paths. If later
verification is mutable, publish the replacement authority and invalidate
dependent readiness/results atomically; a failed verification update must
leave all prior authorities and results unchanged.

## Required regression and engineering acceptance

1. Decode/mapping/gap/unit/nominal/side/calibration states vary independently;
   fixing one never upgrades another. Fast/Slow raw/gain logic is unchanged.
2. Legacy BEN5K stays inspectable but cannot yield an authoritative PU,
   recorded-input power or Compliance result while explicitly Unverified,
   across direct APIs, annotations, cursors and UI.
3. Known units, Primary metadata, nominal matching, group confirmation,
   Source Default, manual PU bases and operation override do not bypass the
   gate. Existing allowed non-BEN5K provider behavior remains compatible.
4. Nested/mixed calculations inspect every contributing leaf. Rename, group
   reassignment, calculated presentation/type changes and cached parents do
   not launder authority. A later invalid/unverified replacement invalidates
   all dependent authoritative results consistently.
5. Verified synthetic cases preserve independent closed-form Vpu/Ipu,
   phasor and P/Q/S results. Missing samples remain gaps under the existing
   null policy, never zeros or fabricated measurements.
6. Verified is attainable only from owner-approved, independently justified
   calibration/representation evidence; no guessed √2/16, CT/VT factor or
   forced 1 pu acceptance. Preserve manual calculator semantics and separate
   explicit provenance for manual numbers versus source-backed measurements.

## Owner decisions needed before implementation

- Approve the scoped strict gate for explicitly Unverified legacy BEN5K and
  the additive default/not-assessed compatibility treatment for other data.
- Select blocked-result wire behavior and whether exploratory derived
  inspection is permitted with inherited limitations.
- Define the minimum evidence that can publish Verified; decide whether any
  future engineer attestation is allowed, with what scope and traceability.
- Decide whether the manual numeric Calculator needs a source-backed API
  extension, beyond gating existing recorded-input/phasor paths.

These are design/policy decisions. They are not implemented by the two
confirmed-defect corrections and must not be silently expanded into them.
