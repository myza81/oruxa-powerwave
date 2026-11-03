# Per-Unit audit remediation - Slice 3

Date: 2026-11-03. Scope: PU-003 / PU-004. Based on local 0eea55c,
feature/calculator-vi-phasors, two commits ahead and zero behind the fetched
upstream. No tracked pre-existing edits; original audit baseline 944e98f and
all protected untracked evidence retained. Owner explicitly authorized this
slice; no new engineering decision is needed.

## Shared eligibility contract and compatibility

PU-003: coverage and provenance previously stopped at base availability.
The numerical conversion functions already refused missing/incompatible units.
resolve_conversion_eligibility() now provides that measured-unit check to all
four scalar/array conversion helpers and both read models. It uses the existing
case-insensitive V/kV and A/kA tables, performs no waveform calculation, and
returns an independent resolution on rejection. Existing base/representation/
quantity/review/inheritance restrictions run first and keep their own reason.

Configuration availability remains separate from conversion readiness. A
resolved base and its group/source ownership remain available as metadata even
when a missing/unsupported unit means status=base_required. Provenance retains
nominal voltage, reference, effective base and equipment metadata where actually
resolved; it explains the missing/unsupported measured unit. These metadata
fields must not be treated as readiness booleans. Status is authoritative.
Coverage counts these channels under needs_configuration, not group/default
conversion coverage. Source/group configuration views continue to describe
configuration availability; no base is erased merely because a unit is absent.

No response fields, field types or status vocabulary change. Existing configured,
base_required and not_applicable statuses remain. New internal measured-unit
reason codes are mapped to human-readable text in the existing reason field.
The source provenance builder now requires measured_unit; its sole production
caller passes canonical channel.unit. Its existing service-test factory supplies
explicit units, preserving every previous assertion. No unit is inferred in
production.

PU-004: Compliance raw-series resolution now obtains names through the same
voltage_channel_names_for_source() accessor as its calculated branch, replacing
the noncanonical lowercase comparison. Shared automatic L-G/L-L evidence,
manual overrides, group precedence, angle exclusion and RMS readiness remain.
No physical processing, denominator selection or arithmetic is changed.

## Consumers reviewed

- Waveform arrays and source/calculated scalar cursors, anchors and peaks already
  use apply_per_unit_to_value/array; their fallback output is unchanged.
- Event Reconstruction consumes the same endpoints and provenance status:
  unavailable channels remain selected but unplotted in PU; ENG restores them.
- Compliance readiness and real traces share compliance_series and refuse
  conversions that do not return configured/pu. Valid V/kV base resolution now
  agrees with Waveform on the raw Source Default branch.
- Calculated unary/group/default channels use their actual output unit. DEC-052
  and DEC-116 guard generic Voltage arithmetic before unit checking. Declared
  L-L metadata and Current inheritance rules are not changed.
- Configuration views, engineering-axis schemas and the older group-specific
  conversion helpers are not separate readiness claims: the helpers already
  reject unsupported units, and the schemas only describe potential axes.
  No additional active conversion consumer requiring a correction was found.

## Numerical reference

For a 132 kV nominal line-line base, a phase RMS denominator is
132/sqrt(3) = 76.21023553303061 kV = 76210.23553303061 V. Matching raw RMS
measurements in V and kV yield 1.0 pu in both Waveform and Compliance (1e-12
relative tolerance). A raw L-L RMS measurement of 132 kV / 132000 V also yields
1.0 pu. Manual overrides select the explicitly requested reference.
The real shared 50 Hz RMS operation over an instantaneous phase sine of peak
132*sqrt(2/3) kV produces 1.0 pu after its warm-up; its NaN warm-up samples are
preserved. No instantaneous sample is compared as if it were an RMS magnitude.
Manual Current base 2 kA normalizes 2000 A / 2 kA to 1.0 pu.

## Regression evidence

Initial test authoring found four invalid None-valued source metadata fixtures
and one incorrect conversion HTTP expectation; source metadata uses blank units
and the domain separately accepts None. After those fixture corrections, the
unmodified implementation produced 27 failures / 25 passes / no skips or errors
in 52 cases: 18 raw-unit read-model mismatches, four calculated mismatches, the
original missing-unit CSV case and four automatic-reference Compliance cases.
No production edit preceded this counted reproduction.

Initial corrected targeted suite: 205 passed, no failures/errors/skips, exit 0.
Expanded dedicated file: 69 passed, no failures/errors/skips, exit 0.
Coverage includes Voltage V/kV/blank/None/unsupported/current units, Current
A/kA/blank/None/unsupported/voltage units, both configuration scopes, incomplete
groups without Source Default borrowing, scalar/array consistency, immutable
resolution/arrays, calculated units, angle exclusions, manual/ambiguous auto
references, actual readiness/trace production, and shared real RMS conversion.

New real-browser file: three final focused cases passed, zero failures/errors/
skips/retries, exit 0. CSV is explicitly classified Voltage, unit remains blank
or explicit kV, absolute timestamps make it eligible for reconstruction. Tests
check coverage/provenance, actual arrays/units/status, accepted base edit with no
stale invented PU, ER unavailable selection and exact ENG restoration, valid
Waveform/ER numerical agreement. Initial browser run had two assertions reading
the wrong object field and an elapsed-only ER fixture; these were test defects,
corrected without production UI changes. The raw Source Default Compliance
adapter is tested directly: the current Compliance UI requires a Measurement
Group and is not redesigned to admit ungrouped recordings.

| Verification | Passed | Failed | Errors | Skipped | Exit |
|---|---:|---:|---:|---:|---:|
| Counted original-defect reproduction (52 cases) | 25 | 27 | 0 | 0 | 1 |
| Initial corrected targeted backend selection | 205 | 0 | 0 | 0 | 0 |
| Expanded dedicated regression file | 69 | 0 | 0 | 0 | 0 |
| Final focused new browser file | 3 | 0 | 0 | 0 | 0 |
| Final relevant browser selection (30 explicit files) | 385 | 0 | 0 | 0 | 0 |
| Full backend (11,224 collected) | 10,904 | 0 | 0 | 320 | 0 |

The full backend run took 1,804.822 seconds and reported 21 warnings. Its 320
skips comprise 153 unavailable owner-PDF references, 49 unavailable BEN
references, 17 POSIX-only cases and 101 relay applicability/metadata conditions.
All 69 new cases and all 45 Slice 1 atomicity cases pass within that run.
The browser selection took 1,068.764 seconds, two configured workers, zero
retries, including all 26 Slice 2 synchronization cases. Both untracked
screenshot scripts were excluded. The initial new-browser authoring run had
two assertion failures and one timeout error (exit 1); the final corrected
file passes both alone and in the complete selection. Windows Playwright
server teardown required stopping only each completed run's two verified
server descendants after test workers exited; no test was interrupted.

Local evidence: isolated OS TEMP directory
`oruxa-pu-slice3-20261102-t1ek42sv`: baseline/targeted/expanded/full-backend and
browser JUnit XML, logs and actual exit-code files; `numerical-proof.json`
records actual Waveform/Compliance values, provenance and coverage. Valid raw
L-G/L-L RMS examples in both V and kV return exactly 1.0 pu in both consumers;
missing-unit input remains unchanged and unavailable. Source hashes, exact
selected browser files, skip reasons and protected snapshots are retained.
Counts overlap and must not be added as unique tests.

## Remaining limitations / separate issue

Existing CSV post-conversion discovery uses the preparation source id after
convert_preparation_source creates a new canonical UUID. Code: API
preparation_sources.py post_convert_preparation_source passes its source_id to
prepare_workspace_source rather than returned metadata.source_id; conversion
service deliberately generates new_source_id. The browser logs show the old-id
SourceNotFoundError; the canonical source exists and remains usable. Both files
are unchanged from HEAD. This issue affects automatic group/context discovery,
not measured-unit eligibility. Proposed separate correction: pass the canonical
id, with real CSV discovery regression coverage. Benefit: normal discovery can
run. Risk/impact: previously absent suggested groups would become available and
could affect normal membership precedence, so it needs separately scoped owner
review. No fix or workaround in production is included here.

PC-001 cross-group Current policy, PU-006/007 numeric-input findings, unknown
metadata policies, and remaining audit work are unchanged. No unit guessing,
CT/VT scaling, base-policy change, generic transaction framework, caching system,
new service layer or backend request is introduced. No full-record calculation
is added to metadata readiness. Full repository browser coverage and sustained
load/latency benchmarking are not claimed.

## Delivery

Only the five production files, directly relevant tests, and project memory
belong to the local Slice 3 commit. Preserve the original audit and all 2250
protected files; final SHA-256/size/modification-time comparison confirms all are unchanged. No push, merge or
deployment. Stop after Slice 3 for owner review; do not start Slice 4.


## Files in this remediation

| File | Purpose |
|---|---|
| `backend/app/domain/per_unit.py` | Shared measured-unit eligibility used by scalar/array conversion |
| `backend/app/services/per_unit_coverage_service.py` | Count only conversion-ready channels as covered |
| `backend/app/services/per_unit_provenance_service.py` | Honest readiness/reason while retaining resolved base metadata |
| `backend/app/api/v1/sources.py` | Pass the channel's declared measured unit into provenance |
| `backend/app/services/compliance_series.py` | Canonical shared voltage-name accessor for raw Source Default resolution |
| `backend/tests/test_per_unit_eligibility_integration.py` | 69 metadata, conversion, waveform, Compliance and RMS cases |
| `backend/tests/test_per_unit_provenance_service.py` | Supply explicit units in the existing test factory; all assertions retained |
| `browser-tests/per-unit-eligibility.spec.js` | Three real CSV/Waveform/ER eligibility workflows |
| `docs/project-memory/CURRENT_STATE.md` | Verified implementation status and separate issue |
| `docs/project-memory/HANDOFF.md` | Continuation state and owner-review stop boundary |
| `docs/project-memory/MIGRATION_PLAN.md` | Distinguish this audit slice from original DEC-050 sequencing |
| `docs/project-memory/PER_UNIT_AUDIT_SLICE_3.md` | Mechanism, compatibility, evidence and remaining limitations |
