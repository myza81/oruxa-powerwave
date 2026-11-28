# Controlled WUI-001–004 consolidation into shared DEV

2026-11-23. The original preparation-only brief was amended by the owner during
verification: **Codex may publish the dedicated candidate and proceed with DEV
deployment independently after verification.** The owner then selected the
authentication route: **the owner will dispatch DEV after Codex publishes the
verified branch**. No merge to `main`, production deployment or WUI-005 is
authorized. Execution results are recorded below.

## Authoritative checkpoint and concurrency

| Source | Verified checkpoint | Treatment |
|---|---|---|
| Remote shared DEV `origin/uat/dev-d5a-20261121` | `f24f1d72f49cf694ac5f843d03fd102e7754320a` | Integration parent and exact test baseline |
| Deployed frontend `buildVersion` and API `/health.git_sha` | Same `f24f1d7` | Confirmed independently by read-only requests |
| Owner-accepted WUI-004 | `d513fba7b221373070a97186955c107190f19003` | Approved UI delta, not the engineering baseline |
| Earlier engineering checkpoint inside WUI-004 | `ad1b6ede06519de3656c72abd41eccbc3c8761fa` | Common file-reconciliation ancestor only |
| Claude's active engineering worktree | `.local-data/d5a-2b2a` | Protected; newer unpublished work excluded |
| Primary checkout / `main` | Older, unrelated working checkpoints | Neither is the DEV authority; untouched |

DEV advanced from `ad1b6ed` while preparation was paused. A fresh fetch and
runtime checks identified published/deployed `f24f1d7`; the first isolated
`ad1b6ed` preparation was retained, then superseded by this fresh worktree.
GitHub CI run **45134215059** and successful DEV deployment **45136061375**
both identify `f24f1d7`. The deployment jobs explicitly say **Deploy to dev**.
The current DEV branch has no newer published-but-not-deployed tip at this check.

Claude's worktree had progressed to unpublished `3e9cc5f` with uncommitted
`backend/app/domain/side_conversion.py` and
`backend/app/services/independent_side_service.py`. No files, index, branch,
services or pending changes in that worktree were modified or incorporated.
Its latest unpublished work must be preserved in any later integration.
The primary checkout's existing untracked investigation files were also preserved.

Final candidate branch: **`integration/wui-001-004-dev-f24f1d7`**.
Worktree: **`.local-data/wui-001-004-current-dev`**.
The exact local candidate SHA is supplied with the delivery and exposed by its
isolated runtime configuration; this report accompanies the locally committed code.

## Accepted UI lineage

The owner has accepted all four slices, including WUI-004 `d513fba`.

| Slice | Accepted lineage preserved |
|---|---|
| WUI-001 | Pane Y controls `2c283d4`, painted-control correction `e161400`, final `5bce71a` |
| WUI-002 | Toolbar `39803f3`, exact SVGs `38e2f36`, pane ENG/PU `68786ac` / `bec5fcb`, final `9594a8a` |
| Earlier controlled integration | Owner-accepted `771dbf9`, preserving then-current engineering |
| Accepted WUI-002 refinements | Global Y readout removal `13b6caf`; Time Group metadata `b355e69` |
| WUI-003 | Modern panes / interactive adaptive legends `ec102706034cf7d28e96eeca0cda22ba4b53d46e` |
| WUI-004 | Per-axis resolved unit labels `d513fba7b221373070a97186955c107190f19003` |

WUI-003's intermediate `816750b` / `960e458` code checkpoints preserved later
engineering through `ad1b6ed`. They do not include DEV's subsequently released
Overcurrent integration, so the accepted WUI file was not used as a DEV replacement.

## Integration strategy and source preservation

The final branch starts directly at **`f24f1d7`**. Temporary-file three-way
reconciliation uses current DEV, common `ad1b6ed`, and accepted `d513fba`.
It found **zero source conflicts**. Its reviewed **47 frontend patch hunks**
were applied to the current DEV file with `git apply`; the file was not replaced
wholesale from the older UI worktree. Accepted icon assets and directly related
tests were applied separately. No Git branch merge or unrelated cleanup occurred.

The result preserves the released Overcurrent read-only side/CT UI, the shared
Recording Details authority, backend enforcement, blocked calculated-current
disclosure, Secondary-without-CT behavior, mixed-declaration safeguards, and
Recording Details tab-corner refinements from `f24f1d7`.

Source proof checks:

- **562 protected engineering/analyzer functions** match current DEV exactly.
- **1,777 existing functions are unchanged**; 25 accepted Waveform presentation
  hooks change, 23 presentation helpers are added, and no function is removed.
- All changed/added UI adapters match owner-accepted `d513fba` exactly.
- Inverting only the accepted UI delta in temporary files reproduces the exact
  `f24f1d7` frontend, proving newer engineering code was retained.
- Backend application, infrastructure, workflows, deployment scripts, theme and
  runtime configuration source files match `f24f1d7`.
- Core waveform trace/layout construction, unit-mode conversion, Y scaling,
  active-pane/Time Group targeting, cursor/time formatting and t0 handlers match
  current DEV. The grouping helper's optional layout argument preserves its
  default rule; it does not introduce engineering classification.

The detailed changed-file/function manifest and hashes are delivered as evidence.
Production edits are limited to `frontend/index.html`, the Waveform icon assets,
their registry manifest and provenance documentation. Backend changes are test
contracts only. No engineering calculation or API is modified.

All accepted interactions remain: local Y controls, synchronized local ENG/PU,
toolbar icons, absent global Y readout, two-line Time Group metadata, compact
panes, adaptive single-line `+N more`, canonical identity, sidebar/legend visibility
synchronization, and resolved per-axis units. Typography remains **0.65rem**
collapsed / `+N more`, **0.7rem** popover. Original eight mockup SVG geometries
and their provenance/attribution notice are retained; no dependency is added.

The approved lifecycle exception remains: surviving panes retain applicable
hidden legend members, but last-channel removal deletes a pane and restoration
uses the sidebar; Separate retains its one-channel lifecycle. Visibility derives
only from `ww.displayed`. A hidden channel with no known association in a newly
chosen PU partition is restored through the existing sidebar, without guessing
eligibility or pane identity. Missing angle units remain explicitly unavailable.

## Verification

Verification is performed on independent local source snapshots, API processes
and storage: exact `f24f1d7` baseline **30430/30431**, candidate **30440/30441**.
No shared DEV or other worker service participates. The full backend suites and
the same 417-case engineering/browser selection run on both checkpoints; the
candidate additionally runs the accepted WUI-specific suites and native zoom
checks. Final outcomes, individual failure reconciliation, screenshots and source
proof are recorded with this report after the jobs complete.

No historical failure total is presumed current. The paired results are:

| Suite | Baseline f24 | Candidate | Classification |
|---|---:|---:|---|
| Backend | 13,542 passed, 422 skipped, 0 failed | 13,567 passed, 422 skipped, 0 failed | No regressions; candidate includes accepted test coverage additions |
| Common browser matrix | 371 passed, 46 failed | 400 passed, 17 failed | Candidate-only failures: none after accepted WUI test renames are aligned |
| Dedicated WUI/browser/native checks | not run on baseline | 104 passed, 0 failed | All accepted WUI-001–004 checks pass |
| Projection/layout checks | 3 passed | 3 passed | Numeric/layout projection checks pass on both snapshots |

The 17 remaining candidate browser failures are the same known baseline
failures: Event Reconstruction isolation setup, delayed Per-Unit/editor race
contracts, and two retired Per-Unit entry-point contracts. The Event
Reconstruction missing-helper/setup issue is reported separately and is not a
WUI regression. The apparent collector “new failure” for the no-recordings
Y-zoom case was a renamed-test identity mismatch: the candidate pane-local
Y-zoom test passed, while its superseded global-toolbar counterpart is a
baseline-only name. No assertion was weakened or skipped.

The candidate WUI run captured Grouped, Separate and Custom layouts, light and
dark themes, native 100% and 125% zoom, axis-unit labels, pane controls,
interactive legends, toolbar/header states and calculated/mixed-channel cases.
Screenshots and raw logs are under
`docs/project-memory/evidence/wui-001-004-consolidation/`. `git diff --check`
is clean.

## Deployment readiness and risks

The owner clarified the initial “another deployment planned” answer: Claude is
implementing D5A-2B2C-1B in an isolated feature worktree, with **no scheduled DEV
deployment, confirmed final commit or timing**. The owner confirms
**`uat/dev-d5a-20261121` / `f24f1d7`** is the approved shared UAT baseline and
authorizes Codex to proceed independently. After Codex deployment/validation,
Claude must integrate against the exact new checkpoint, preserving both agents'
work. This supersedes the preparation-only stop point for DEV; `main` and PROD
remain excluded.

Current workflows, unchanged:

- `.github/workflows/ci.yml`: runs on pushes to every branch and pull requests;
  full backend tests and Compose-overlay validation are required.
- `.github/workflows/deploy.yml`: manual `workflow_dispatch`, explicit
  **`target=dev`**, full backend test job before the deploy job; deploys the
  dispatch ref's exact `github.sha`.
- `.github/workflows/deploy-dev.yml`: automatic DEV deployment only after
  successful **main** CI. Publishing this dedicated integration branch does not
  trigger that automatic path. `main` remains untouched.

Publishing only the dedicated integration branch is authorized by that follow-up.
Require green CI on its exact SHA before manually dispatching DEV. Publication
credentials/permissions have not been proved by a
write: no push was attempted. Read-only repository metadata confirms the connected
GitHub identity has `push` permission; this is capability, not owner authorization.
The local GitHub CLI is unauthenticated and no cached Git credential was found;
the owner selected manual DEV dispatch rather than CLI authentication. Publishing
uses the connected GitHub tools; workflow evidence is read through the same
connection. No credential is requested in chat, printed or stored by this task.

For the **separately authorized phase only**, freeze the approved branch, verify
its local and remote SHA equal the reviewed candidate, then use:

```powershell
git push origin integration/wui-001-004-dev-f24f1d7
gh workflow run deploy.yml --repo myza81/oruxa-powerwave --ref integration/wui-001-004-dev-f24f1d7 -f target=dev
```

The commands above describe the sequence for an authenticated owner environment;
the owner can instead use GitHub's **Run workflow** UI on `deploy.yml`, selecting
this exact integration branch and **target=dev** after green CI. Codex will not
dispatch or restart DEV through an alternate route. Execution details below
identify what actually ran. Verify CI, dispatch `head_sha` and
**Deploy to dev** before allowing service changes. After deployment verify both
API health SHA and frontend `buildVersion`, actual received HTML/assets and
owner DEV UAT. Re-fetch first: any newer engineering release requires safe
reconciliation and affected verification before publication/deployment.

`scripts/deploy.sh` builds and uses `up -d --force-recreate` for **both backend
and frontend**. There are no database/schema migrations in this change, but a
backend restart clears in-memory workspaces, source registrations, calculated
channels, Measurement Groups, configured CT/VT, PU/side decisions, synchronization
and reconstruction/session state. Stored original files are not deleted by the
UI patch; retaining files does not preserve the active registry/configuration.
Agree on preserving or recreating UAT setup before deployment. Rollback has the
same restart/state-loss consequence.

Rollback checkpoint: **`f24f1d72f49cf694ac5f843d03fd102e7754320a`**, successful
DEV deployment **45136061375**. After separate authorization, rerun that exact
recorded deployment (all jobs, preserving its original DEV input/SHA), or dispatch
a reviewed rollback ref pinned to that SHA with **target=dev**. Recheck the run
SHA/target and both runtime versions. Never edit code on the host or use `main`
as a rollback substitute.

Before execution, the remaining gates are completed local verification, exact-SHA
green CI and the final DEV checkpoint check. Report the actual deployed SHA after
validation so it becomes Claude's engineering integration checkpoint. No production
or WUI-005 work is included.
