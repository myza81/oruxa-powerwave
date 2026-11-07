# PU audit: DEV readiness review — 2026-11-04

**[DECISION] Owner approved the six-commit PU contents, existing ephemeral
workspace lifetime and the feature-branch-to-DEV UAT route. The owner additionally
authorized the narrow Peak/PU-modal fix, browser coverage and committing these
five readiness/UAT deliverables. Stop for confirmation before pushing or
deploying; do not merge main.** The only production change in this preparation
pass is the dialog-specific CSS rule documented below. No workflow,
infrastructure, numerical calculation or persistence change is included.
No push, merge or deployment was performed. This is not the consolidated audit.

## Verified release boundary

Read AGENTS.md, CLAUDE.md, project-memory README/current state/handoff,
DEC-015/036/050/051/209 and applicable PU model/implementation reports,
the architecture reference and existing development/deployment procedures.
Fetched `origin`; the following facts describe the reviewed snapshot:

| Item | Verified value |
|---|---|
| Working directory | `D:\Programming\oruxa-powerwave` |
| Branch | `feature/calculator-vi-phasors` |
| Approved six-commit PU HEAD, before release preparation | `bddebd507d40ab5d4d92a95f1e1917c130ac8e6d` |
| Upstream branch | `origin/feature/calculator-vi-phasors`, `9e5d829ef619f5485ac7a20c6955f785060e6fce` |
| Upstream comparison before preparation | Six ahead, zero behind |
| `origin/main` | `d8ade8f04dde5df2654082a784adbebb064a7336` |
| Main comparison before preparation | Six ahead, one behind; the extra main commit is PR #6's merge commit |
| Baseline tree | `origin/main` and `origin/feature/calculator-vi-phasors` have identical trees |
| Actual DEV API | `/health`: development, `git_sha=d8ade8f04dde5df2654082a784adbebb064a7336` |
| Actual DEV frontend | `/config.js`: development, same full `buildVersion`, correct DEV API URL |

The intended release baseline is **the verified live DEV `d8ade8f`**, not the
historical audit baseline `944e98f` or the earlier DEV UAT `3c5df3a` mentioned
in older project notes. GitHub confirms successful [main CI](https://github.com/myza81/oruxa-powerwave/actions/runs/41405107927)
and [automatic DEV deployment](https://github.com/myza81/oruxa-powerwave/actions/runs/41405824637)
for `d8ade8f`. Both live public version endpoints independently agree.

### Owner-approved six pending commits, oldest first

| Full commit | Contents and scope |
|---|---|
| `cc72cc72ceea6c5ed9152480a74bc691459159ea` | Approved **test maintenance outside PU implementation**: compact P/Q/\|S\| identity/expression/type/unit expectations in `calculated-channel-power.spec.js`; compact RMS summary in `line-to-line-voltage.spec.js`. No production change. |
| `0eea55c3dd28dcff4096b1b615f97cb6dc8a8ae7` | Slice 2, PU-005/008: unit-mode publication, stale-response fencing, waveform/cursor/annotation refresh; tests and memory. |
| `b5d824e7dfb0db5f33ae4ba55f8084479652cd6d` | Slice 3, PU-003/004: measured-unit eligibility and consistent Compliance reference selection; tests and memory. Compliance changes belong to this PU slice. |
| `2114a714f43a00fe40b1d293bd1852e1a3e92ad7` | Slice 4, PU-006/007: safe SI/derived bases and normalization, pre-coercion boolean rejection; tests and memory. |
| `e2427b652bafcb9e366cc84d79258e28c15dcc8b` | Stage 5A/PC-001: independent measurement/base sides, live compatible Current bases across authorities, existing group/default editors and provenance; tests, approved decision and memory. COMTRADE change only adds side metadata, without sample rescaling. |
| `bddebd507d40ab5d4d92a95f1e1917c130ac8e6d` | Stage 5B: result-owned manual Current configuration/API/existing-modal editor and synchronized display; tests and memory. Also includes separately owner-approved **test-only maintenance** in `channel-presentation-propagation.spec.js` and `text-spacing.spec.js`, preserving exact expression/identity/unit/spacing coverage. |

These six commits are not yet in `origin/main`. Their aggregate delta: **61 files,
5,983 insertions, 164 deletions**. Per-commit file lists are captured in
`release-commits.json` in the review evidence directory below.

The additional **release-preparation commit containing this document** has
`bddebd5` as parent. Its scope is exactly seven files: the PU-dialog CSS rule,
two browser regression cases in the existing manual-Current file, and these
five deliverables: this report, CURRENT_STATE, HANDOFF, the UAT checklist and
its fixture generator. It adds three files to the original 61-file release
delta. After the local commit the branch is seven ahead of upstream, with
nothing staged and only the five original protected untracked paths remaining.
The final full release SHA is reported to the owner after committing; it must
be approved before external actions. Resolve it locally with `git rev-parse HEAD`
and compare the seven-file commit before a future push.

Slice 1 `498e8cd` and maintenance `0f751b2` are already ancestors of
`origin/main` and remain intact. The completed Power Calculator, single/three-phase
Power operations and DEC-208 UI are already in the live baseline through
[PR #6](https://github.com/myza81/oruxa-powerwave/pull/6) and its predecessors.
They remain part of the deployed application, but are not new production Power
changes in these six commits. Review of the pending source diff finds no new
Power algorithm, sliding-phasor algorithm, Calculator behavior, CSS, dependency,
deployment or infrastructure change. Shared PU display/readout changes in the
frontend are intentional. Do not describe this release as six PU-only commits.

## Stage 5B readiness and test applicability

| Acceptance area | Evidence and current behavior |
|---|---|
| Automatic / Manual / Unassigned | Explicit result modes, successful transitions and separate Return to Automatic; no automatic fallback after a manual choice becomes inapplicable. |
| Result ownership | Canonical SI amperes and independent base side on the existing calculated assignment; input groups, defaults, linked bases and physical arrays are preserved. |
| References | Primary/Primary eligible subject to all gates; same-authority Secondary/Secondary supported; different secondary authorities and unknown/conflicting physical sides fail closed. No CT/VT scaling. |
| Rejected saves | Complete candidate validation before one locked assignment replacement. Tests compare full prior state/timestamp, inputs/indices/bases, provenance and effective arrays/scalars, including injected publication failure and deletion races. |
| Nested channels | Automatic children resolve original source leaves, without inheriting a parent's Manual/Unassigned mode. Each child can own its own manual base. |
| Display consumers | Shared backend normalization; refreshed waveform arrays, list units, legends, cursors, callouts and peaks. Stale responses cannot restore an old base. ER uses its own unit mode and live readiness. |
| Labels and compatibility | Shared identity/notation rendering; definitions/preview remain ENG. Existing Voltage restrictions and Source Default behavior remain, except explicitly approved PC-001 Current policy changes. Historical manual bases are not silently given a side. |

At the initial readiness review, all 861 code/test files matched the final
Stage 5B manifest. This preparation changes only `frontend/index.html` (CSS)
and `calculated-current-manual-pu.spec.js` (two new tests); all other 859 hashes
and every backend source/test hash remain unchanged. Historical evidence and
fresh preparation checks are distinguished below:

| Verification | Passed | Failed/errors | Skipped | Notes |
|---|---:|---:|---:|---|
| Stage 5B full backend, before the CSS fix | 11,315 | 0 | 320 | 11,635 collected; 21 existing warnings; exit 0. Includes all 62 Stage 5B cases and earlier slices. |
| Stage 5B selected browser, before the CSS fix | 431 | 0 | 0 | 37 explicit files, zero flaky cases/global errors/retries; exit 0. Includes PU, Power/Calculator, Compliance, ER, lifecycle and labels. Not the entire browser suite. |
| Complete approved maintenance files | 9 | 0 | 0 | Independent run; overlaps the 431. |
| Affected backend notation guard | 11 | 0 | 0 | After the two final browser-test edits. |
| Initial readiness probes, before the fix | 2 | 0 | 0 | Historical overlap/control recovery/numerics; reload/new-tab/reset/reimport lifetime. Zero retries. |
| Initial UAT fixture browser checks | 3 | 0 | 0 | Primary/Secondary/Unknown import, real group saves and Addition builder; expected values and manual acceptance/rejection. Zero retries. |
| Fresh backend selection after the fix | 3,578 | 0 | 17 | 111 complete files, all frontend static guards and relevant PU/group/annotation/Power checks. Three existing warnings; exit 0. |
| Fresh focused Peak/modal regressions | 2 | 0 | 0 | Maximum/Minimum Peak overlapping real controls; accepted/rejected saves and normal dragging after close. Zero retries; exit 0. |
| Fresh selected browser regression | 152 | 0 | 0 | 13 complete files, including both new cases; zero flaky cases/global errors/retries, exit 0, 11.4 minutes. The focused two cases overlap this count. |

The two new modal regressions first **failed 2/2** against the unchanged
frontend on Save hit-testing. After the targeted CSS rule, both pass with real
overlapping Peak boxes, accepted/rejected saves and normal post-modal dragging.
An intermediate fixed run exposed a test-setup error dragging a Peak header into
the toolbar. The setup now keeps header dragging within the waveform area,
retaining header-Close hit checks and actual header/ESC/backdrop closing. No
production change accommodated that correction. All initial evidence is preserved.

Fresh backend/selected-browser regression results are recorded in the
release-preparation evidence directory below. The prior full backend and broad
browser evidence is retained; neither entire suite was rerun for a three-line,
dialog-specific CSS change. Fresh checks include all frontend static tests and
relevant PU/group/annotation/Power backend cases, plus 13 complete browser files.
All 45 Slice 1 atomicity/publication, 185 Stage 5A and 62 Stage 5B backend cases
execute and pass in the fresh selection. All 12 cases in the complete manual
Current browser file pass, including the two new modal regressions. The source
hashes used for these runs match the final committed frontend/browser content.
The fresh 17 skips all require POSIX sh on this Windows host. The three warnings
are the existing Starlette/httpx deprecation and two relay-review regex warnings.
The historical 320 backend skips concern missing
owner relay PDFs (153), missing BEN reference data (49), POSIX-only checks (17)
and existing relay applicability/catalog cases (101). They are not passes.
The five initial readiness/fixture checks passed before release preparation. The
remaining standalone Calculator browser files, including the complete V-I
Phasors file, were not rerun here; their production code is unchanged and
their explicit smoke cases are included in owner UAT.
Candidate GitHub CI and actual DEV UAT are **pending**, since nothing was pushed.
No PROD validation or sustained load benchmark is claimed.

Independent Stage 5B proof retains 100,000 physical samples and agrees with
Decimal division: 8398 A / 4000 A = **2.0995 pu**; / 2000 A = **4.199 pu**.
ENG array identity/hash is unchanged. Earlier 5A checks also establish that an
unrelated ambient 1 kA default cannot repair incompatible 2/4 kA input groups.
See the [Stage 5B report](PER_UNIT_AUDIT_STAGE_5B.md) for original reproduction,
publication/refresh race tests, manifests and performance limitations.

## Live-workspace lifetime, precisely

| Action | Manual configuration |
|---|---|
| Close/reopen the PU dialog; navigate application pages; toggle ENG/PU/layout | Retained on the same calculated result in the live backend workspace. |
| Refresh the browser | Retained while the backend process and workspace still exist. UI display selections need not be restored; reselecting the result reads its stored mode/base. |
| Open another tab in the same browser profile and origin | Same `powerwave.workspaceId` in localStorage; same live backend configuration. Both tabs address the same workspace, not independent copies. |
| Close and reopen a tab/browser with localStorage retained | Can reconnect to the same workspace while its backend process survives; closing the tab itself has no workspace-delete handler. This is not a durability guarantee. |
| New browser profile/private context, cleared storage or different origin | Usually a new UUID; no configuration is transferred automatically. Having the same filename is not a workspace identity. |
| **Start New Workspace** | Confirms, deletes the old backend workspace/configurations, then rotates the UUID. Resetting in one shared tab invalidates the old workspace used by another. |
| Upload/reopen the same original files as a new source/workspace | New source/calculated identities. Manual calculated configurations are not embedded in the event files or reconstructed from their names. Recreate the calculation and configuration. |
| Delete a calculated result/source or its workspace | Corresponding assignment configuration is released by existing cleanup. |
| Restart backend, deploy/redeploy, DEV reload or rollback | Lost with all process-local workspace registries. No server-side durable restoration is implemented. |

The two new browser probes directly verified reload, same-origin tabs, explicit
reset and reimport. Registry construction/cleanup and localStorage code establish
the remaining lifecycle boundaries. These match **oruxa_powerwave's existing
ephemeral workspace design**, DEC-012/015/019 and DEC-209. This review does not
claim a new comparison with the separate desktop `powerwave` repository.
No permanent storage extension is proposed. Keep original files and a note of
accepted UAT bases/results outside the live workspace before any deployment.

## Peak annotation/modal overlap — reproduction and approved correction

Reproduced locally on unchanged candidate frontend at **1280 × 720**:

1. Display a calculated Current in Separate view with manual 4 kA Primary.
2. Add a Maximum Peak annotation, then reopen Per-unit configuration from the
   channel context menu. The default Peak box covers part of the Source/provenance
   area; base amount, side, Save, Return to Automatic and both Close buttons were
   reachable in this placement.
3. Close the dialog, drag the Peak box to the screen position occupied by Save,
   then reopen. **Save is obscured and its center pointer hit goes to Peak text.**
4. Drag the Peak by its header to the right of the dialog, even while the dialog
   is open. Save becomes reachable; an actual 2 kA save succeeds, updating the
   plot/cursors/annotations to 4.199 pu without moving data anchors.

Full configuration and PU waveform JSON were equal before/after overlay
repositioning. It does **not** change numerical results. The shared annotation
layer has computed z-index 15, the reused confirmation overlay 10; annotations
receive pointer events. Those stylesheet rules predate these six commits.

**[FACT] Corrected under the subsequent explicit owner authorization.**
`#wwChannelPerUnitOverlay { z-index: 16; }` places only the existing PU dialog
above the annotation layer at 15. Its opaque dialog/backdrop receives input;
Peak boxes can no longer obscure provenance/fields or intercept Save. No shared
annotation positioning, pointer policy, other modal layer, JavaScript or backend
behavior changes. Once the dialog closes, annotation dragging remains available.

Two regression cases cover Maximum and Minimum Peak boxes positioned over Save,
provenance, base/unit/side inputs, Return to Automatic and footer Close. Actual
Save, rejection, header Close, Escape and backdrop Close are exercised, with
header-Close hit testing at each placement. Dragging/reopening alone preserves
full configuration and PU waveform JSON, group state and annotation anchors;
an accepted 4-to-2 kA save updates 2.0995 to 4.199 pu. Physical ENG arrays remain
unchanged. A rejected zero base preserves the accepted configuration and PU.
Screenshots visually confirm unobscured controls. The old workaround and its
screenshots remain historical reproduction evidence, not the release behavior.

Other existing limits: CSV/BEN samples remain Unknown without an approved
sample-side contract; shared secondary-reference identity and CT/VT scaling are
deferred. The separately documented CSV post-conversion discovery-id issue is
not fixed by this release; use the supplied COMTRADE examples for the primary
UAT path. No new correction outside approved scope was made.

## DEV release procedure — feature branch selected, execution awaits confirmation

**Source:** the final local release-preparation commit, parent
`bddebd507d40ab5d4d92a95f1e1917c130ac8e6d`; use its full SHA from the final
owner handoff and `git rev-parse HEAD`. Do not deploy the pre-fix parent.
**Runtime target:** GitHub Environment **dev**, `/srv/oruxa/apps/powerwave-dev`,
Compose project `powerwave-dev`, backend/frontend ports 8200/8201, public
`https://api.dev.powerwave.oruxa.uk` / `https://dev.powerwave.oruxa.uk`.
Do not touch PROD, its environment or the shared infrastructure.

### A. Standard PR/main route — reference only; not selected or authorized

1. Obtain approval for these six commits, included maintenance and limitations.
   Re-fetch and compare refs/status; any code or remote drift requires review.
   Preserve all protected untracked evidence. Review/commit readiness documents
   separately only if requested; doing so creates a new SHA to approve.
2. With explicit push approval, push the feature branch normally, without force.
   Open a PR **head `feature/calculator-vi-phasors` → base `main`** describing the
   complete delta, test evidence and limitations. Do not squash/rebase away the
   reviewed history without separate agreement.
3. Require green **CI / Backend tests** (Ubuntu/Python 3.12/pinned dependencies)
   and **CI / Validate Compose overlays** for the reviewed head/PR. Local browser
   evidence is a separate gate: this workflow does not run Playwright.
   GitHub currently reports main `protected=false` and no rulesets; green status
   must be checked explicitly, not assumed to be enforced by branch protection.
4. Merge only with owner approval. Main has one extra merge commit but the same
   baseline tree, so a pure merge should preserve the candidate source tree.
   Record the resulting full merge SHA **M**; its value cannot be named before
   the merge. Verify the release code tree equals the reviewed candidate; any
   additional code change stops the release for review and appropriate tests.
5. **Merging main authorizes the automatic DEV effect:** once CI succeeds on M,
   `Deploy Powerwave (DEV, automatic)` uses that CI event's exact `head_sha=M`.
   A cancelled/failed CI does not deploy. Do not merge while expecting a later
   independent deploy button approval. No PROD deploy is triggered.

### B. Owner-selected route: exact feature-branch commit on DEV before merging

The existing **Deploy Powerwave** manual workflow supports selecting a branch
with `target=dev`; historical branch DEV runs demonstrate this. The owner has
selected this route, but explicitly requires another confirmation before push
or deployment. Main must not be merged. A PR is not required for this manual
branch deployment; create none without separate authorization.

After final SHA approval, an authorized normal push and green branch CI
(Backend tests and Validate Compose overlays), choose Actions →
**Deploy Powerwave** → Run workflow → branch `feature/calculator-vi-phasors` →
**target `dev`**. Verify that branch still points exactly to the approved SHA.
The workflow runs backend tests, then checks out `github.sha` on the VPS.
It has **no arbitrary SHA input**; the selected ref must resolve to the approved
commit. Record the run's actual head SHA before accepting its deployment.
This route needs no merge to deploy and lets DEV UAT exercise the exact final
release SHA, including the modal fix and readiness deliverables. A later PR
merge still requires separate approval and creates a new
main SHA requiring version verification/smoke checks.

Both workflows share the DEV deployment queue and use `TARGET=dev` explicitly.
They fetch and check out the exact commit, build and force-recreate the target
stack, then check backend health. A stale comment in manual `deploy.yml` saying
main merges deploy nowhere is superseded by DEC-036 and `deploy-dev.yml`.
Do not change a workflow or edit host source files to perform this release.

### Verification of the approved deployment

Record the GitHub test/deploy run URLs and expected full SHA (M for route A,
approved branch head for B). A successful deploy job alone is insufficient:

```powershell
Invoke-RestMethod https://api.dev.powerwave.oruxa.uk/health
(Invoke-WebRequest -UseBasicParsing https://dev.powerwave.oruxa.uk/config.js).Content
```

Require development environment and exact matching full API `git_sha` and
frontend `buildVersion`, plus the DEV API address. Hard-refresh the app to avoid
cached frontend assets; check its reported version and browser/API connectivity.
Then perform the [owner UAT checklist](../uat/pu-audit-2026-11-04/README.md).
Stop on mixed versions, a new failure or unexplained numerical differences.

### Rollback plan, only with owner authorization

Capture the pre-release baseline **d8ade8f04dde5df2654082a784adbebb064a7336**
and this report before deploying. Coordinate a deployment pause so queued/new
main CI deployments cannot immediately replace the rollback.

The smallest existing exact-commit rollback is to **re-run all jobs of the
previous successful automatic DEV deployment run 41405824637**. Its original
workflow event retains the validated `head_sha=d8ade8f...`; the workflow checks
out that SHA rather than current main. Verify the rerun log and both live full
versions afterward. Do not re-run the failed candidate deployment by mistake.

If GitHub no longer permits that rerun, use the existing manual workflow on an
owner-approved branch/tag resolving exactly to the baseline, target dev. Creating
that rollback ref needs approval. Do not pretend the workflow accepts a SHA input.
Never reset/rewrite the shared branch, edit VPS source, or delete storage.
There are no database/schema migrations in this candidate. Rollback/redeploy
does **not** restore ephemeral analysis workspaces; recreate from original files
and recorded engineering settings. Smoke-test health, Voltage PU and Calculator
after rollback and preserve the failed UAT evidence for a separately scoped fix.

## Evidence and review boundary

New review outputs are isolated at:
`C:/Users/fairizat/AppData/Local/Temp/oruxa-pu-dev-readiness-4952a4fb3d65445dac6272369262a230`.
They include release commit/file lists, rehashed test applicability, separate
focused browser JSON/logs, numerical/geometry evidence, screenshots and generated
synthetic UAT files. Original evidence is not reused as an output directory.

All original **2,250 protected files** retain hashes, sizes and modification
times: `.audit/`, `.slice1-evidence/`, `test-results/`,
`browser-tests/compact-label-screenshots.spec.js` and
`browser-tests/e3b-screenshots.spec.js`. They remain untracked and unstaged.
The five readiness/UAT deliverables are included in the scoped local
release-preparation commit. No protected path is included in that commit.

Release-preparation evidence, created without overwriting the initial review:
`C:/Users/fairizat/AppData/Local/Temp/oruxa-pu-modal-fix-c43300494509406ca36598544dcbacc6`.
It retains the failing baseline, corrected focused/browser reports, selected
backend JUnit/logs, exact selected file lists, source hashes, screenshots and
final Git/evidence preservation checks. Test output is not committed.

**[ASSESSMENT] Ready locally for the approved feature-branch DEV UAT route.**
The scoped Peak/modal defect is corrected and relevant fresh checks pass.
Remote CI and the manual DEV deployment remain gated by final owner confirmation;
owner UAT follows exact deployed-version verification. The existing ephemeral
workspace behavior is owner-accepted; the prior Peak obstruction is no longer
an accepted limitation or required workaround.

**Confirmation pending:** approve pushing/deploying the final reported local
release SHA through route B after local verification. The six PU commits,
ephemeral design, branch route and scoped local preparation are already approved.
No main merge, PROD deployment, permanent storage, further remediation or
consolidated audit is authorized. Stop here for the owner's final confirmation.
