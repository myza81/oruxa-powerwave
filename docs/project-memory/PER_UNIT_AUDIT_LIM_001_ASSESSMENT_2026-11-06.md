# LIM-001 — Current reference safety: implementation-impact assessment

Date: 2026-11-06. Reviewed runtime: local
`384a55fafbbecf7e304aa9ea8cfc663554177fd1`, whose parent is the approved DEV
release `265f1906d4a6c30568309dd45ffa5e41cbb236ce`.
Part B of the owner-approved final PU audit follow-up.

**Assessment complete; LIM-001 runtime behavior is unchanged.** The owner has
approved the physical principle, not the Unknown-side policy or implementation.
This document is a proposal for review, not a new engineering decision or final
PU acceptance. No push, merge, deployment, CT/VT scaling or persistence change.

## 1. Finding and engineering risk

[FACT] Raw Current channels and historical single-authority Automatic calculated
Current results can still be `configured` with known incompatible measurement
and base sides. Waveform, both cursors, callout anchors, peaks, provenance and
raw-source coverage consistently follow that same historical omission. Consistency
does not make the physical reference correct. A numerical base being finite,
positive and equal to another base does not prove compatible reference meaning.

The supplied example is reproduced with an actual imported COMTRADE fixture:
`a=0.5`, `b=0`, raw sample 1, CT ratings 2000:1, marker `S`. The stored physical
sample remains **0.5 A Secondary**. A manual group base of **2 kA Primary**
currently produces **0.00025 pu**. A same-group absolute-value result and nested
Automatic results retain that omission. Equipment-derived Primary bases and
ungrouped Source Defaults have the same raw-channel applicability gap.

The engineering danger is a plausible finite PU value on the wrong physical
reference, potentially off by the CT ratio. The equivalent 1000 A Primary would
be 0.5 pu against 2000 A Primary, but **this assessment does not perform or
authorize that conversion**. A separately justified 1 A Secondary result base
can legitimately normalize the unchanged 0.5 A Secondary result to 0.5 pu using
the existing Stage 5B workflow. Declaring a Primary result base cannot repair
Secondary samples.

[FACT] Cross-authority Automatic and result-owned Manual already enforce the
Stage 5A/5B side contract. This follow-up must extend protection to historical
paths without weakening those checks or preventing a valid independent Manual
result override. Original PU-001–PU-008 closure and FA-001 preview remediation
do not certify LIM-001 reference applicability.

## 2. Existing contract and metadata

DEC-050/051 establish group authority and supported Source Default fallback;
DEC-209 and its Stage 5B addendum define independent reference sides and manual
override. Historical single-authority behavior was deliberately preserved by
those bounded scopes. The new owner instruction approves blocking known P/S
mixing in principle; changing that historical behavior still awaits review of
this impact assessment. The authoritative measurement model remains unchanged.

| Meaning | Existing authority and treatment |
|---|---|
| Measurement side | `AnalogChannel.measurement_side` and `AnalogChannelSummary.measurement_side`: `primary`, `secondary`, `unknown` |
| COMTRADE | Recognized, case-normalized P/S marker supplies measurement side. Missing/unrecognized marker, including the synthetic fixture's historical `C`, is Unknown. Ratios do not establish side. Conflicting contributing markers remain distinct known sides, not an inferred convention. |
| CSV/Excel | Preparation conversion creates analog metadata without a side declaration: Unknown. Measured-unit selection is independent. |
| BEN, including legacy BEN5K | Normalization supplies engineering values/ratings without an established measurement-side contract: Unknown. Ratings must not be used to guess it. |
| Current Group equipment rating | Base side is Primary, using linked or explicitly supplied nominal L-L voltage. |
| Current Group manual | Independent `base_reference_side`, default Unknown. |
| Source Default derived | Base side is Primary; nominal L-L current-base mathematics is unchanged. |
| Source Default direct | Independent `current_base_reference_side`, default Unknown. |
| Result-specific Manual | Immutable SI amperes and independent `base_reference_side` in the existing calculated assignment lifetime. Unknown cannot qualify a new Manual save. |

`reference_side.candidate_base_side()` preserves an omitted declaration only
within the same manual/direct method. A method transition does not inherit
derived Primary; explicit Unknown clears the declaration. Historical manual
bases are not backfilled. These semantics must remain intact.

COMTRADE still applies only `a * raw + b` to samples; the marker and CT ratios
are metadata. A provider marker's truth is assumed as supplied, not certified
against instrument wiring. Even matching known sides do not certify recorder
calibration or establish a common Secondary reference across distinct authorities.

## 3. Traced paths and affected consumers

Line references are for `384a55f`; links point to the actual implementation.

| Code path | Observed behavior / necessary future seam |
|---|---|
| [reference_side.py](../../backend/app/domain/reference_side.py), [COMTRADE provider](../../backend/app/providers/comtrade.py) `comtrade_measurement_side`, `_apply_analog_scaling` (652), `_build_record` (746) | Independent metadata; no ratio scaling. Preserve. |
| [preparation conversion](../../backend/app/services/preparation_conversion_service.py) (471, 610), [BEN normalization](../../backend/app/providers/ben/normalize.py) (89) | Side remains Unknown by domain defaults. No new provider inference is needed or authorized. |
| [group base adapter](../../backend/app/services/group_aware_per_unit.py) `resolve_per_unit_for_group` (72), [Current domain resolver](../../backend/app/domain/current_group_config.py) (215) | Validate group/review/method/numeric/link availability, then adapt Ibase to SI. No measurement-side argument. Group base availability is not channel reference eligibility. |
| [legacy/Source Default domain](../../backend/app/domain/per_unit.py) `resolve_per_unit` (259), `resolve_conversion_eligibility` (352) | Resolve base, units and full-channel numerical bounds, but no side comparison. `PerUnitResolution` (242) carries no reference proof. Conversion helpers cannot reconstruct it from scalar values. |
| [raw shared dispatcher](../../backend/app/services/waveform_service.py) `_resolve_effective_per_unit` (94) | Group first, own Source Default only when ungrouped. Metadata is available here, but side is unused. Its four consumers are waveform (269), cursors (478), annotation anchor (641), peak (783). Known mismatches currently configure in all four. |
| [calculated Current resolver](../../backend/app/services/calculated_current_per_unit.py) (43) | Walks/deduplicates live source leaves; validates dependencies, review, units, bases, tolerance and final range. Side checks at 146 apply only to multiple authorities or result Manual. One-authority Automatic skips them, including nested and mixed-P/S inputs. |
| [calculated display dispatcher](../../backend/app/services/calculated_channel_service.py) (1398) | Four public value consumers at 1511, 1581, 1641, 1704 supply full registry context and use the new Current resolver. A historical internal-manual graph returns `None` from that resolver, then falls back to group/legacy assignment resolution without reference proof. |
| [provenance service](../../backend/app/services/per_unit_provenance_service.py) (311, 355, 359) | Raw path repeats base/unit resolution; `measurement_side` is attached afterward. Calculated path uses the Current resolver when supplied, then the same legacy fallback. Side fields are exposed, but raw/single-authority status can still say Configured for P/S mismatch. |
| [coverage](../../backend/app/services/per_unit_coverage_service.py) `_classify_channel` (84) | Counts raw grouped/default coverage using base/unit/numerical readiness without side proof. Must agree with channel conversion; do not redefine it as calculated-result coverage. |
| [source API](../../backend/app/api/v1/sources.py) (300, 432, 554, 600, 652), [calculated API](../../backend/app/api/v1/calculated_channels.py) (341, 379, 415, 431, 488, 528, 580) | Public value/provenance/configuration surfaces. Existing `configured` / `base_required` / `not_applicable` vocabulary is sufficient for blocked normalization. |
| [frontend](../../frontend/index.html) `wwErChannelUnitDisplay` (18550), `wwRenderChannelPerUnitResolution` (32498), waveform status/axis/unit paths (32785–33680) | Backend status drives plots, list units, legends, cursors and annotations. Waveform retains ENG with Base required; ER retains selection but marks PU unavailable and omits the PU trace. Existing stale-response fences must prevent old PU values reappearing after a reference change. No frontend reference math should be added. |

### Internal legacy assignment and additional shared-helper boundary

The old `PerUnitRegistry.set_manual_assignment_for_calculated_channel()` (178)
is not Stage 5B Manual. A repository search finds its definition but **no
production call site or public endpoint**. Tests/internal integrations can still
create such records. The Current resolver detects an old manual record on any
ancestor and preserves the historical fallback. A temporary probe creates two
incompatible groups: ordinary cross-authority Automatic correctly blocks, but
an internal legacy assignment and its Automatic descendant can configure via
the assigned Source Default. Future physical eligibility must cover that
fallback too; do not silently delete or reinterpret the assignment.

[compliance_series.py](../../backend/app/services/compliance_series.py) `_raw`
(78–120) has one additional calculated dispatcher call (91) that supplies neither
`source_registry` nor `per_unit_registry`; it uses the old fallback. An isolated
direct Current-helper call returns 0.0005 pu even for an explicitly Unassigned
calculated Current whose public value endpoints correctly report unavailable.
This is a **latent internal reuse boundary**, not a demonstrated Current
Compliance UI defect: current Compliance measurement/readiness requires a
Voltage Group (`compliance_readiness_service.py:572`,
`compliance_measurement_service.py:376`) and exposes Voltage quantities. Keep
Voltage behavior unchanged. A future centralized Current gate must either
provide complete context to this helper or explicitly disallow unsupported
Current reuse; extending public Compliance to Current is outside scope.

## 4. Fresh characterization and concrete reproductions

An isolated local TestClient application imports real COMTRADE files into new
temporary storage. No existing workspace, DEV state or protected evidence is
used for mutation. **56/56 characterization probes confirmed**, exit 0. These
are observations of current behavior, including unsafe results, **not 56
passing LIM-001 acceptance tests**. No repository test expectations were changed
to bless known incompatible conversion.

| Probe set | Count | Observations |
|---|---:|---|
| Group manual and own Source Default direct: full 3×3 measurement/base side matrices | 18 | Raw, same-authority sum and nested result all configure, even P/S, S/P and Unknown. All four value consumers and provenance agree; read snapshots remain unchanged. |
| Group equipment and Source Default derived, each measurement side | 6 | Primary base; historical raw/same-authority/nested outputs remain configured for P, S and Unknown. |
| Distinct groups: full 3×3 side matrices | 9 | Only known P/P with matching bases qualifies. Known mismatch, Unknown and unestablished cross-authority S/S block. |
| Distinct Source Defaults and mixed group/default authorities | 8 | P/P accepts; S/P, S/S and Unknown/P block, including value/provenance parity. |
| Result Manual single authority: full 3×3 matrix | 9 | Only P/P and established same-authority S/S accept. Seven rejected saves leave full authoritative snapshot unchanged. |
| Manual replacement of incompatible input bases; cross-authority unequal Primary bases; cross-authority Secondary rejection | 3 | Valid result Manual supersedes input normalization bases without mutating them. Distinct Secondary remains blocked; rejected snapshot unchanged. |
| Mixed known P/S in one group | 1 | A sum currently configures despite conflicting leaves; aggregate provenance says Unknown. Future proof must retain the known conflict rather than collapse it into unverified metadata. |
| Internal legacy assignment and nested descendant | 1 | Historical fallback can bypass the new cross-authority reference guard; no public setter exists. |
| Additional internal Compliance Current-helper boundary | 1 | Demonstrates the missing context described above; no public Current Compliance behavior is claimed. |

For these fixtures each raw physical input is 0.5 A. A 2 kA accepted base yields
the historical 0.00025 pu; a two-input physical sum is 1 A, yielding 0.0005 pu.
An explicit compatible 1 A result base gives 1 pu for the sum. No probe applies
the 2000:1 ratio. Group/default/side/link/index/sample snapshots and physical
calculated arrays are compared around rejected saves and read-only operations.

Minimal engineer reproduction of known incompatibility: import the original
synthetic measurement fixture with `IBT_HV_IR` gain 0.5 and its final CT fields
`2000,1,S`; create/confirm a Current Group for that channel; select Manual 2 kA,
Base reference side Primary. Raw PU and an Automatic Abs result currently show
0.00025 pu. Under the proposed known-conflict rule both would be unavailable,
retaining the physical 0.5 A. Use the existing result Manual workflow with an
independently justified 1 A Secondary base for a compatible 0.5 pu result.

For Unknown, change the marker to `C` or leave it absent, or use CSV/BEN without
side metadata. With a valid base, historical raw/single-authority PU remains
available; cross-authority Automatic and result Manual remain unavailable.
Changing the **base** selector cannot establish missing **measurement** side.

Evidence, including complete response bodies and before/after assertions:

```text
C:/Users/fairizat/AppData/Local/Temp/oruxa-pu-followup-20261105-0c938079ecc74c33a4025c18138a7666/
  lim001_characterization_v2.py
  lim001-characterization-v2.json
  lim001-characterization-v2-summary.json
  lim001-characterization-v2.log
```

The first diagnostic attempt confirmed 31/56; 25 nested cases stopped because
the probe reused a calculated-channel name. Unique fixture names corrected the
probe, not the application. The first script/log/results remain preserved.

## 5. Proposed compatibility matrix — owner review required

Other existing gates always apply: Current quantity, measured A/kA units,
confirmed/manual groups, valid dependencies, positive representable base,
full-result numerical bounds and, for Automatic, equivalent effective bases
using the existing global relative tolerance. Matching side does not bypass them.

| Measurement / effective result base | Reference classification | Single established authority | Distinct authorities, Automatic or Manual |
|---|---|---|---|
| Primary / Primary | Known compatible | Eligible | Eligible; Automatic additionally requires equivalent input bases |
| Secondary / Secondary | Known compatible only within the existing authority contract | Eligible under established same-authority semantics | Unavailable: `current_secondary_reference_unestablished` |
| Primary / Secondary | Known incompatible | Unavailable: `current_reference_side_incompatible` | Unavailable |
| Secondary / Primary | Known incompatible | Unavailable: `current_reference_side_incompatible` | Unavailable |
| Primary / Unknown | Unknown/unverified | Owner policy choice below | Unavailable: `current_reference_side_unknown` |
| Secondary / Unknown | Unknown/unverified | Owner policy choice below | Unavailable |
| Unknown / Primary | Unknown/unverified | Owner policy choice below | Unavailable |
| Unknown / Secondary | Unknown/unverified | Owner policy choice below | Unavailable |
| Unknown / Unknown | Unknown/unverified | Owner policy choice below | Unavailable |
| Mixed known Primary and Secondary contributing samples | Known incompatible common-reference proof | Unavailable even when aggregate side or base side is Unknown | Unavailable |

Result Manual uses its **own** independently declared base side and amount in
this matrix. Input normalization-base amounts/sides may be missing, unequal or
incompatible without invalidating a physically compatible result Manual. Input
sample sides, units, review/dependency state and result safety still apply.
Unknown sample side cannot be repaired by a declared Manual base. Automatic
children continue resolving source leaves rather than inheriting a parent's
Manual or Unassigned choice.

Known conflicts should be detected before aggregating Unknown. Preserve the
set of contributing sides and authorities until proof is complete; a group ID,
same numeric denominator, cancellation to zero, or an Unknown aggregate does
not erase an explicit physical conflict. A known-conflict reason must not be
hidden by a second contributor with missing metadata.

Unavailable conversion should use `base_required` and existing Current reasons;
physical engineering arrays/scalars and units remain available. Retain accepted
configuration and explicit Manual mode when later inapplicable. A valid numeric
group/default base may remain saved/configured as a **base configuration** even
when a particular member cannot use it; do not reject every group member or
silently fall through to Source Default. A result Manual candidate continues to
reject before publication if that result cannot qualify.

## 6. Unknown policy options and backward compatibility

| Option | Engineering treatment | Compatibility / user impact |
|---|---|---|
| **A — block known conflicts; explicitly identify historical unverified PU** | Known mismatch blocks everywhere. Unknown never counts as compatible. Historical raw/single-authority Automatic remains numerically available with an explicit Unverified reference indication. Cross-authority Automatic and result Manual stay strict. | Smallest bounded change; preserves existing CSV/BEN and historical manual/direct workflows. Retains a disclosed risk where reference meaning cannot be proved; cannot claim universal physical-reference certification. Requires owner acceptance of that residual risk. |
| **B — require known compatible sides for every Current normalization** | Known mismatch and Unknown both make PU unavailable, with distinct explanations. | Strongest reference assurance without scaling. Existing valid-in-practice CSV/BEN, unmarked/nonstandard COMTRADE and historical Unknown manual/direct bases lose PU. Existing UI cannot declare recorded sample side, so many users cannot restore PU through current base editors. Could ship as an explicit limitation, or a separately approved measurement-metadata workflow would be needed. |

Neither option infers Primary from equipment type or Secondary from magnitude,
ratios, source format or selected base. Neither backfills historical declarations
or rescales samples. No date-based grandfather flag, new storage model or
automatic migration is necessary.

Known P/P remains eligible under either option. Raw/single-authority known P/S
or S/P recordings intentionally change from configured PU to unavailable.
Same-authority known S/S retains the approved contract; distinct S/S is still
deferred. Unknown base declarations can already be corrected independently by
the engineer where their meaning is known. Unknown **samples** cannot be
corrected through a base-side control. Manual override remains available when
the samples and explicitly selected result base establish compatible meaning.

[PROPOSAL] **Recommend Option A as the bounded compatibility-preserving follow-up,
conditional on explicit owner acceptance of Unverified reference risk.** It
enforces the approved known-mixing principle without silently expanding the
sample-metadata workflow. If the owner requires verified reference meaning for
every displayed Current PU, choose B and explicitly accept the loss of Unknown
workflows or separately approve the missing measurement-side design. This is
an analysis-based policy choice; the evidence does not authorize either option.

## 7. Smallest implementation, API and UI implications

[PROPOSAL] Introduce one pure Current reference-eligibility classifier returning
compatible/incompatible/unverified plus an existing reason. Inputs are the
selected effective base side, contributing measurement sides, authority set and
the approved mode/Unknown policy. Collect reference context at the existing
group/default selection seams; do not modify stored configuration or physical
calculation. Keep base availability separate from conversion readiness.

Apply the classifier **after the final normalization base is selected** in raw,
calculated, legacy-fallback, provenance and coverage paths. Reuse its outcome
rather than adding endpoint-specific checks. Do not run an input-base side gate
that poisons valid result Manual before its independent base replaces those
normalization bases. Preserve dependency/unit/review checks. Address the
context-free internal helper boundary deliberately, with Voltage regressions;
do not turn this into a new public Compliance feature.

No new persisted side fields, database, migration, transaction framework,
workspace lifetime, CT identity or scaling workflow is needed for known
mismatch protection. Existing side fields are sufficient. A small transient
reference-context/result type is an implementation detail, not new storage.
Preserve existing per-registry locking; do not claim a global snapshot across
separately accepted concurrent edits. Avoid permanently caching eligibility;
existing live resolution and asynchronous response fences remain authoritative.

Existing statuses and reason codes suffice for unavailable conversion. Raw and
legacy provenance reason translation must explicitly recognize Current side
reasons rather than return a generic incomplete-base message. Existing
measurement/base side fields remain independent. For A, propose an **additive**
provenance field `reference_compatibility` with compatible/incompatible/unverified
(nullable for other quantities), displayed as a clear reference warning for
available historical Unknown PU. Review strict-client/schema impact before
adding it. Do not label unverified reference Configured without qualification.
For B, existing unavailable reason/side rows can carry the distinction without
a required new API status.

Reuse Current Group manual, Source Default direct and result Manual base-side
selectors; derived base side remains read-only Primary. Add no sample-side
selector in this task. Base editor feedback should explain that saving a valid
base does not guarantee every channel is reference-compatible. Update shared
provenance/status rendering, Waveform row readiness and ER readiness/warnings
consistently. Existing data anchoring, legends, channel identity, units and
manual provenance remain intact; unavailable ENG must never be labeled pu.
Warning presentation is bounded UI work requiring approval with the policy,
not an authorization to redesign layout or annotations.

Expected implementation footprint: shared Current reference/domain helper;
raw and calculated dispatch; provenance/reason/schema and coverage; explicit
internal-helper handling; existing shared frontend status surfaces; relevant
backend/browser tests and documentation. Approximately 8–12 existing backend
modules plus a small helper, the existing frontend and tests, subject to final
design. No provider sample conversion, Power/phasor algorithm, Voltage math,
legacy assignment storage or deployment change is required. This is broader
than deleting the single-authority conditional alone.

## 8. Required regression and acceptance plan

1. Test the nine side pairs independently for raw Group manual/equipment (linked
   and manual voltage), Source Default direct/derived, single-authority unary/
   multi/nested Automatic, cross groups, cross sources and group/default mixes.
   Distinguish known mismatch from missing metadata. Include mixed P/S plus
   Unknown leaves so aggregation cannot hide a known conflict.
2. Reproduce the real 0.5 A Secondary / 2 kA Primary case. Known mismatch must
   report `base_required`, retain 0.5 A ENG and never return 0.00025 labeled pu.
   Verify known P/P and established single-authority S/S independently; keep
   distinct S/S blocked. No ratio application, even when ratings are present.
3. Cover actual COMTRADE P/S/missing/unrecognized markers and actual CSV/BEN
   imports with Unknown. Assert the owner-selected Unknown policy explicitly;
   do not change fixture sides merely to recover old expected results.
4. Preserve Manual / Unassigned / Return to Automatic, nesting, automatic child
   leaf resolution, provenance and stale-response fencing. Manual Primary with
   Primary samples must still replace missing/unequal/Secondary input bases.
   Secondary samples plus Primary result base reject atomically; established
   Secondary result base can work. Missing sample side still rejects Manual.
5. Cover legacy internal assignments, manual ancestors and context-free shared
   service callers; no fallback may bypass known physical incompatibility.
   Keep existing Voltage Compliance/DEC-052/115/116 behavior unchanged.
6. Compare every raw/calculated waveform, both cursors, anchor, max/min peak,
   provenance and applicable coverage/readiness outcome. Check full-resolution
   and reduced arrays, viewport-independent eligibility, units, list, plot,
   legend, ER, annotations and exact reference warning/reason in a real browser.
7. After accepted base/side/group/default/link/source changes, update all affected
   consumers without changing physical values, identities or anchor times.
   After rejected changes, compare complete configs, sides, group status/name/
   membership, reverse indices, assignments, stored samples and ENG/PU outputs.
8. Retain measured-unit, review, zero/nonfinite samples, empty windows, numeric
   overflow/subnormal, cancellation and dependency failure tests. A scalar-zero
   probe cannot certify reference compatibility. Do not weaken valid result
   numerical cancellation behavior by normalizing input arrays first.
9. Run relevant backend and complete browser files, then full backend and the
   agreed PU/Power browser suite. Preserve Voltage references, fallback,
   physical Power/phasor calculations, manual override and workspace lifetime.

## 9. Review gate and current delivery state

[OPEN — DECISION MODE: ANALYSIS] Owner must select A or B, approve the precise
Unknown warning/unavailable behavior and the bounded API/UI scope, then
authorize LIM-001 implementation. Strict B with continued Unknown-source PU
support would require separate approval of measurement-side metadata workflow;
it cannot be achieved by a base declaration or hidden sample inference.

FA-001 is locally fixed in `384a55fafbbecf7e304aa9ea8cfc663554177fd1`; its
[separate implementation record](PER_UNIT_AUDIT_FA_001_2026-11-05.md) gives
before/after and numerical/regression evidence. This assessment and living
memory/final-audit follow-up are left uncommitted for owner review, separate
from that focused fix. The original final audit at `265f1906` remains historical
evidence; its original content is preserved before an append-only addendum.

**Stop here. No LIM-001 runtime implementation or final PU acceptance is claimed.**
