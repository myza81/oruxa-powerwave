# Final PU release preparation and DEV verification - 2026-11-07

## DEV execution outcome - 2026-11-07

**Recommendation: GO for final owner acceptance on DEV.** Final owner UAT and
overall PU acceptance remain the owner's decision. No main merge or PROD release.

- Deployed release: `82c8ebbe320b58113a71caeb1c2e4335ad7887a8` (documentation preparation commit, parent b6202fc).
- Normal feature-branch push succeeded; remote ref matched that exact SHA.
- [CI](https://github.com/myza81/oruxa-powerwave/actions/runs/42327370768): Backend tests and Validate Compose overlays both passed.
  Full Linux backend: **11,391 passed / 303 skipped / zero failures / 21 warnings**,
  307.31 seconds. The 17 additional passes versus Windows are its POSIX cases.
- [Manual deployment](https://github.com/myza81/oruxa-powerwave/actions/runs/42327935955): workflow_dispatch, target **dev**, exact recorded
  head SHA above; its own full backend gate passed **11,391 / 303 / 21**, zero
  failures, 553.94 seconds. Deploy to dev succeeded. No workflow changes/bypass.
- At `2026-11-07T02:45:59.307Z`, frontend buildVersion and backend git_sha both matched the full
  release SHA; backend status ok, both development, frontend API points to DEV.
  TLS 1.3, authorized chain and hostname checks passed on both hosts, including
  negative wrong-hostname checks. Node --use-system-ca used existing Windows
  trust. No ignoreHTTPSErrors, disabled verification, CA/key export or trust change.

### Executed smoke and honest first-run accounting

**140 unique selected cases have passing deployed evidence across nine files.**
The initial run was not clean: 101 passed / one temporary-harness assertion
failed / 38 not run after maxFailures=1. It incorrectly expected a raw source
row to become IA (pu); DEC-209 and Stage 5B explicitly preserve raw row ENG units.
Saved bases, every API sample and plotted values had already passed. Correcting
that assertion exposed a second harness setup error: a legend was queried in
Grouped view, where that element is absent (zero passes / one harness error /
38 not run). Neither was a production numerical or reference-policy defect.

Both attempts, original scripts, JSON, traces and screenshots are retained.
A separate frozen harness selected Separate view, asserted exact raw IA (A),
data-unit A, plot legend IA (pu), trace identity and all numerical comparisons.
The complete remaining **39/39 passed**, no failures/skips/flaky/global errors.
All runs used **zero automatic retries**. The two earlier max-failure controller
errors remain recorded; this is not claimed as one pristine 140-test run.
No repository test, production behavior or engineering expected result changed.
The isolated DEV runner used 120-second tests and 20-second default expectations
to allow network overhead; existing explicit timing assertions were retained.

| Explicit file | Passing cases |
|---|---:|
| `calculated-current-manual-pu.spec.js` | 12 |
| `calculator-power-current.spec.js` | 34 |
| `calculator-vi-phasors.spec.js` | 19 |
| `current-common-base.spec.js` | 3 |
| `per-unit-display-synchronization.spec.js` | 26 |
| `per-unit-reference-safety.spec.js` | 7 |
| `release-authoritative-values.spec.js` | 4 |
| `source-default-current-preview.spec.js` | 7 |
| `three-phase-power.spec.js` | 28 |

The added release-authoritative-values spec exists only in isolated TEMP. All
others reuse reviewed repository assertions with explicit DEV origins, real
config.js, synthetic fixtures and test-owned lifecycle handling. No substitute
frontend/backend or mocked deployment/version response. Controlled obsolete
responses use actual backend responses with timing held by the existing tests.

Manual/Unassigned/Automatic and Return to Automatic, independent Manual/nested
ownership, rejected saves, waveform arrays/plots/legends, A/B, callouts/peaks,
mode/base edits, async fences, group precedence/defaults and Voltage PU passed.
Power Calculator Current/P-Q-S/PF and backend V-I Phasors passed; single- and
three-phase calculated Power creation, units and confirmation gates passed.
Fresh Peak/modal and Unknown-reference screenshots were visually inspected.

### FA-001 actual deployed numerical evidence

Each row uses a 5 A peak synthetic Primary Current channel with no group base.
All 101 returned samples equal physical amperes divided by the independently
calculated base; physical arrays remain identical, plot arrays match the API.

| VLL kV | S MVA | Preview | Saved base A | Peak pu |
|---|---|---|---|---|
| 132 | 1000 | 4.3739 kA | 4373.865675678983 | 0.001143153532995459 |
| 275 | 1000 | 2.0995 kA | 2099.455524325912 | 0.002381569860407206 |
| 1e+300 | 1e+308 | 57735026.9190 kA | 57735026918.96258 | 8.660254037844386e-11 |

No Infinity preview or fabricated base. Existing subnormal and invalid-save
preview cases also passed; manual/automatic L-G/L-L interpretation is unchanged.

### LIM-001 and shared consumers

Primary/Primary and one-established-authority Secondary/Secondary remain usable.
Both known mismatch directions are unavailable, retain unchanged ENG arrays and
never scale CT/VT values. Historical Unknown raw/single-authority PU retains its
approved numbers with Unverified disclosure on rows, legends, cursors and
annotations; provenance/readiness distinguish it from verified compatibility.
Cross-authority Unknown samples remain unavailable; independently declared
Manual Primary is rejected when sample side is unknown, with exact before/after
group/configuration/resolution/waveform equality. Compatible independent Manual
remains valid; incompatible/unknown Manual saves retain accepted state. ER uses
its own mode. Obsolete compatible data cannot restore PU after an incompatible
accepted edit. Physical storage and PU/Power mathematics are unchanged.

### Evidence, Git identity and handoff boundary

All 871 application/test hashes still match final local acceptance. Existing
Windows backend 11,374/320 and complete local browser 1302/1302 remain applicable;
no fresh complete local run is claimed. The two fresh full Linux backend runs
and the deployed browser selection above were executed for this task.

All 142 attempted test contexts cleaned only their own 142 synthetic workspace
UUIDs after closing their browser contexts; every DELETE returned 204. Existing
owner resources were not selected for cleanup. All 2250 protected evidence files
retain SHA-256, size and nanosecond mtime, with zero additions/removals/changes.
The assessment remains byte-identical; all historical audit bytes are preserved
before append-only release evidence. The five protected paths remain untracked,
unstaged and outside both documentation commits.

The release preparation commit above contains six reviewed docs. This execution
record, CURRENT_STATE, HANDOFF and the final-audit addendum form a separate
**documentation-only closure commit**, whose identity is the commit containing
this outcome. Branch HEAD may therefore be newer than the deployed release;
application/test hashes and the intended running SHA stay explicit. Publishing
that record does not redeploy DEV or merge main. CI for the closure record is
separately checked; the runtime release gates above apply to the deployed SHA.

New evidence only:
C:\Users\fairizat\AppData\Local\Temp\oruxa-pu-final-dev-20261107-bf637a9452a64a33a85dc314d130b120

Known limits remain the approved ephemeral workspace lifetime, historical
Unknown as Unverified, no shared Secondary identity/CT-VT conversion, deferred
CSV/BEN side declaration and separate CSV discovery-ID work, and no broader
load/heap certification. Existing CI action-runtime/image migration notices and
21 warnings were nonblocking; no unrelated workflow correction was made.
Rollback remains prior manual DEV run 41831396862 for 265f1906, only with owner
direction; no rollback, main merge, production deploy or further feature work.
Owner UAT: [existing checklist](../uat/pu-audit-2026-11-04/README.md), interpreted
with the current DEC-210 matrix above. Stop for final owner acceptance.

## Authorization and preparation checkpoint (historical)

The owner's task "Final PU Release Preparation and DEV Verification" accepts
the LIM-001 engineering policy and authorizes reviewed documentation, a normal
feature-branch push, green CI, exact-commit manual DEV deployment and deployed
smoke checks. No main merge or production deployment. This supersedes earlier
release stop notes only within that explicit scope. Final owner acceptance
still follows DEV verification.

Status at this preparation commit: local acceptance and release-content review
pass; GitHub CI, new deployment and post-deployment smoke are **pending**.
This document does not claim those pending checks passed. Results will be
recorded after execution in a separate documentation-only closure revision;
the actual deployed release SHA remains explicit.

## Release contents

Before documentation preparation:
- Branch: `feature/calculator-vi-phasors`.
- HEAD: `b6202fcea18682dccd1b8ec41e080f9e9be953a7`.
- Upstream and previously approved DEV: `265f1906d4a6c30568309dd45ffa5e41cbb236ce`.
- `origin/main`: `d8ade8f04dde5df2654082a784adbebb064a7336`.
- Two ahead / zero behind upstream; tracked working tree and index clean.
- Seven existing untracked entries: five protected paths and two memory reports.

The proposed release is the documentation commit containing this preparation
record, with parent `b6202fc`. Its exact SHA is resolved after committing and
recorded in deployment evidence and the final owner handoff. No runtime or
repository test file is changed during release preparation.

| Commit above prior DEV/upstream | Scope |
|---|---|
| `384a55fafbbecf7e304aa9ea8cfc663554177fd1` | FA-001: overflow-safe Source Default Current preview, seven browser cases, two static guards and its report; five files |
| `b6202fcea18682dccd1b8ec41e080f9e9be953a7` | LIM-001: shared reference proof, response/provenance/readiness metadata and UI warnings; 59 backend/seven browser cases, scoped guards and policy/memory; 26 files |
| Commit containing this record | Reviewed documentation only: archival final audit/addenda and historical assessment, current state/handoff, release record and release-authorization note in DEC-210 |

The two implementation commits change 30 unique files relative to prior DEV
and upstream. Exact per-commit file sets match their reviewed allowlists.
Relative to main, there are nine prior commits and 79 changed files before this
documentation commit. They include the seven already-approved/deployed commits:

- `cc72cc72ceea6c5ed9152480a74bc691459159ea` - test: align Power labels and RMS browser expectations
- `0eea55c3dd28dcff4096b1b615f97cb6dc8a8ae7` - fix(pu): synchronize waveform display state for Slice 2
- `b5d824e7dfb0db5f33ae4ba55f8084479652cd6d` - fix(pu): align conversion readiness and Compliance references
- `2114a714f43a00fe40b1d293bd1852e1a3e92ad7` - fix(pu): guard numerical bases and reject boolean inputs
- `e2427b652bafcb9e366cc84d79258e28c15dcc8b` - fix: resolve automatic Current PU bases across authorities
- `bddebd507d40ab5d4d92a95f1e1917c130ac8e6d` - feat(pu): add manual bases for calculated Current results
- `265f1906d4a6c30568309dd45ffa5e41cbb236ce` - fix(ui): keep PU configuration above Peak annotations

The remaining two are FA-001 and LIM-001 above. The original seven include
owner-approved presentation-test maintenance and the earlier scoped modal fix;
they are not described as PU-only production changes. Power Calculator and
single-/three-phase calculated Power remain part of the baseline. No new Power,
phasor, dependency, workflow, deployment or infrastructure algorithm/configuration
change is present in the delta since prior DEV. The shared PU changes in LIM-001
are intentional and owner-approved.

## Evidence and documentation review

All 871 application/test files match the final LIM-001 acceptance manifest.
Existing local evidence therefore remains applicable: full backend **11,374
passed / 320 skipped / zero failures or errors / 21 existing warnings**, 2012.44
seconds; complete browser **1302/1302**, 92 files, four workers, zero failures/
skips/flaky cases/global errors/retries, 2449.365 seconds. This release task does
not claim a new complete local run. Both GitHub CI and the existing manual
deployment workflow still run their required full backend suite.

The historical [final audit](PER_UNIT_AUDIT_FINAL_2026-11-05.md), including its
original conditional verdict at 265f1906, remains intact before append-only
follow-up. Its later FA-001/LIM-001 addenda distinguish completed local fixes
from the original findings. The [assessment](PER_UNIT_AUDIT_LIM_001_ASSESSMENT_2026-11-06.md)
is archived byte-identically as a dated proposal at 384a55f, superseded by approved
DEC-210 and its implementation. Neither historical document claims current DEV
already contains those local fixes. The [FA-001](PER_UNIT_AUDIT_FA_001_2026-11-05.md)
and [LIM-001](PER_UNIT_AUDIT_LIM_001_IMPLEMENTATION.md) reports retain exact original
failures, later corrections, prerequisites and limitations. The original
`.audit/per-unit-2026-10-31/AUDIT_REPORT.md` is never rewritten or committed here.

Only six documentation paths are included in this preparation commit. All
protected evidence directories and both screenshot specs remain untracked,
unstaged and untouched. New release outputs only:
`C:\Users\fairizat\AppData\Local\Temp\oruxa-pu-final-dev-20261107-bf637a9452a64a33a85dc314d130b120`.

## Secure pre-deployment observation

At 2026-11-07T01:59:42.515Z, frontend `buildVersion` and backend
`git_sha` both matched `265f1906d4a6c30568309dd45ffa5e41cbb236ce`;
backend status was ok and both environments were development.
Strict TLS 1.3 and hostname verification passed on both DEV hosts, including
negative wrong-hostname checks. Node 24.15.0 `--use-system-ca` uses the existing
Windows-trusted Zscaler inspection CA. No TLS bypass, ignoreHTTPSErrors, trust-store
change, certificate/private-key export or application configuration change.

## Execution gates and exact-commit procedure

1. Review the staged documentation-only diff; commit only its allowlist.
2. Resolve release SHA R. Push `feature/calculator-vi-phasors` normally, without
   force; require the remote ref to equal R.
3. Require CI on R: both **Backend tests** and **Validate Compose overlays**
   succeed. Record exact run/job URLs. No Playwright CI claim.
4. Recheck the remote branch equals R. Dispatch the existing `deploy.yml`
   workflow on that branch, input **target=dev**. It has no arbitrary SHA input.
   Require its recorded head SHA to equal R; retain its own backend-test gate.
   Do not merge main, edit workflows, SSH from Windows or edit host files.
5. Require successful **Deploy to dev**; verify frontend `buildVersion`,
   backend `git_sha`, development environments and health all match R over
   validated HTTPS.
6. Run the focused real-DEV browser/API smoke selection below with zero retries.
   Recheck versions afterward. Stop on CI/deployment/version/numerical failure;
   do not bypass gates or perform unrelated corrections.
7. Record actual results in current memory and a documentation-only closure
   revision. Distinguish that record's identity from the deployed release R.

DEV target: GitHub Environment `dev`, checkout
`/srv/oruxa/apps/powerwave-dev`, Compose project `powerwave-dev`,
ports 8200/8201, frontend `https://dev.powerwave.oruxa.uk`,
API `https://api.dev.powerwave.oruxa.uk`. PROD is excluded.

## Planned deployed smoke checks - results pending

Use actual deployed frontend configuration and backend requests; no locally
served substitute app, mocked version/configuration or TLS bypass. Reuse reviewed
browser assertions with only explicit DEV-origin/fixture-path adaptation in an
isolated temporary harness. Use only synthetic COMTRADE recordings and fresh
test-owned workspace UUIDs; close browser contexts before deleting only those
workspaces, following the existing test cleanup policy.

- FA-001: real Source Default editor, 132/275 kV and 1e300 kV / 1e308 MVA,
  finite preview `57735026.9190 kA`, accepted base about
  `57735026918.96258 A`, actual ungrouped Current PU samples independently
  divided by that base; invalid saves retain state.
- LIM-001: Primary/Primary, same-authority Secondary/Secondary, both known
  mismatches, historical Unknown Unverified, cross-authority Unknown unavailable,
  compatible Manual and incompatible Manual rejection.
- Shared consumers: exact arrays and units, channel identity, rows/plots/legends,
  A/B cursors, callouts, max/min peaks, provenance/readiness and ER's own mode.
  Live base/mode changes and held obsolete responses must preserve newer intent.
- Regression: Voltage PU, group precedence, Source Default, independent Manual
  ownership, Unassigned/Return to Automatic, cross-group Current and Power
  Calculator / calculated Power.

## Remaining limitations and owner acceptance boundary

Historical raw/single-authority Unknown remains Unverified by explicit owner
policy. CSV/BEN recorded-side declaration, common Secondary reference identity,
CT/VT scaling, the separate CSV discovery-ID defect, durable workspace storage
and broader load/heap certification remain separate future work.
The live workspace is ephemeral: backend restart/deploy does not restore manual
settings. This existing design is owner-accepted. Matching declared sides is
not a calibration or wiring certificate.

DEV smoke proves the recorded cases on R, not permanent durability, arbitrary
CT conversion, unrestricted secondary mixing or final owner UAT acceptance.
Overall PU acceptance remains the owner's decision after this handoff.
No main merge or production release is authorized.

## Rollback boundary

Pre-release known DEV is 265f1906. If significant UAT failure occurs, stop and
request owner rollback direction. The existing exact-commit option is a rerun of
the prior successful manual DEV deployment for that SHA; capture its run ID
before releasing. Do not reset shared branches or edit the VPS. A rollback or
redeploy loses ephemeral workspace state as documented. Verify exact versions
and smoke after any separately authorized rollback.
