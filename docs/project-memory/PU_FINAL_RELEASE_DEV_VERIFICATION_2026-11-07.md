# Final PU release preparation and DEV verification - 2026-11-07

## Authorization and current status

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
