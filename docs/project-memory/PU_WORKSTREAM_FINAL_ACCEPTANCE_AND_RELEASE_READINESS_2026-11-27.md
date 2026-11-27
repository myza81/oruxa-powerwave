# Per-Unit workstream — final owner acceptance and release readiness (2026-11-27)

Status: **owner UAT passed; Per-Unit workstream accepted and frozen. Integration readiness reviewed; awaiting owner review.**
Nothing described here was merged, pushed to `main`, or deployed to PROD by this record.

This is the closeout record for the Per-Unit migration (PU-MIG S1–S6), DEC-219, the W-1 auto-base alignment and the final
Voltage-configuration UI simplification. It does not introduce policy: every rule it cites is recorded in
[DECISIONS.md](DECISIONS.md) (DEC-210…DEC-219). Detailed engineering records stay in their own files (section 9).

## 1. Formal acceptance

| Item | Record |
|---|---|
| Owner acceptance | DEV UAT passed (2026-11-27). PU S1–S6, DEC-219, W-1 and the final Voltage-configuration UI simplification are accepted. |
| Accepted functional baseline | **`4885ca2`** on `feature/pu-mig-s5-verification-presentation`. Frozen: no further PU feature work is authorised. |
| DEV release branch | `uat/dev-pu-mig-dec219-20261127` = `4885ca2` (verified equal at the time of this record). |
| DEV deployment evidence | CI run `45986951629` success; Deploy Powerwave run `45988779482` (workflow_dispatch, target=dev) success; `/health` and `/config.js` report `4885ca2`; served `index.html` byte-identical to the committed page (sha256 `30da8935f1195479…`); Voltage Base Reference Side selector and *Advanced reference settings* container absent; API smoke 14/14. |
| Outstanding owner-reported PU defects | **None.** |
| PROD | Not deployed. PROD `/health` unchanged; PROD OpenAPI contains none of the PU fields (section 6). |

## 2. Completed scope

**Engineering (backend).** One pure side-denominator resolver is the only place a Per-Unit denominator is computed
(`D = B·ρ` direct; `B·ρ/r` Primary base on Secondary samples; `B·ρ·r` Secondary base on Primary samples; `ρ = 1/√3` for L-G; `r` = the
VT/CT primary÷secondary ratio) and is checked by an independent 80-digit oracle. Raw Voltage (S2), calculated Voltage (S3) and Current
(S4) consume it; the historical gate never verifies; a conversion without a ratio authority is refused. S5 added the additive
`per_unit_verification_state` field (`verified_direct`, `verified_converted`, `unverified_historical`, `blocked`) to the waveform, calculated,
peak, cursor and anchor responses; S6 fixed the Source Default base-side presentation. DEC-219 made the nominal system voltage the
Primary Voltage PU base, retired the separate base-side input, and (W-1) aligned `auto_base_service` so it no longer creates a legacy
Secondary base.

**UI.** Recording Details has no Voltage Base Reference Side selector and no *Advanced reference settings* container; the Voltage
reference select and *Clear reference override* sit in the Voltage reference field and *Clear manual nominal voltage* under the Nominal
field; a legacy Secondary base is one read-only line. Verification state and provenance are shown with the S5 presentation.

**Behaviour fixed by the accepted fixture (nominal 275 kV L-L, Secondary peak 0.577345 kV).** Auto VT 275 kV : 110 V (ratio 2500) → 5.2486 pu,
numerically correct for the configured ratio; Manual VT 275 kV : 1000 V (ratio 275) → 0.577345 pu, equal to the Primary recording
(158.77 / 275), physically correct under the actual 275 : 1 ratio. DEC-215 VT policy is unchanged; no CFG or `recording_metadata` VT
authority is written anywhere.

## 3. Known accepted limitations (accepted by the owner; not defects)

1. A legacy Secondary base (stored `secondary` side plus a valid `secondary_voltage_ll_v`, D-5) is kept exactly as stored. Its nominal voltage
   is **not editable in Recording Details**, because changing it would be a transition to the Primary base and no transition mechanism is
   approved (DEC-219 Amendment 2). Reference and VT editing, and the API, remain available.
2. A **new** Secondary recording stays `needs_review` until the engineer enters the nominal voltage: the CFG winding rating is low-confidence
   evidence and never produces an automatic nominal (DEC-219 Amendment 1).
3. The Auto VT default (110 V L-L secondary) is a policy default, not a measurement. Where the physical ratio differs the engineer sets the
   Manual VT override (DEC-215).
4. Deploying or rolling back DEV clears the ephemeral workspace state (groups, CT/VT, uploads); UAT data must be re-created.
5. Browser UI smoke against DEV is not possible from the engineering laptop (corporate proxy redirects headless browsers to the identity
   provider); the UI evidence is the served-bytes equality plus the browser suite plus the owner's own UAT.
6. Six browser tests in the CSV/Excel export area fail in the full browser run (deferred, unrelated to Per-Unit; recorded in S6).

## 4. Deferred enhancements — none authorised, none required for release

These are **enhancements**, not incomplete release requirements. The release requirements of S1–S6 (resolver, verification, refusal
safeguards, presentation, DEC-219) are all met.

| Deferred enhancement | Why it is not a release requirement |
|---|---|
| Raw Current ENG/PU waveform display toggle | Raw Current stays in engineering units by default (DEC-212); the Current PU path exists for calculated Current. |
| Additional Current PU reference types | The accepted Current base methods are unchanged. |
| Creation-time Current PU configuration | Configuration after creation is accepted behaviour. |
| Stage 6D proposals | Proposals only. |
| Legacy Secondary base management UI (W-2) | Legacy bases are preserved and shown read-only (limitation 1). |
| Legacy API field deprecation (`*_base_reference_side`) | Fields retained by D-8; additive compatibility. |
| New CFG transformer-ratio authority | Not introduced; DEC-215 stands. |

## 5. Integration readiness (candidate vs latest `main`)

Facts measured on 2026-11-27 after `git fetch origin`; no ref other than the local feature branch was changed.

| # | Question | Finding |
|---|---|---|
| 1 | SHAs | `origin/main` = `b743a67` (PR #12, 2026-11-17). Candidate functional baseline `4885ca2`. |
| 2 | Merge base / divergence | Merge base = `b743a67` (= `main` tip). **198 ahead / 0 behind.** `main` is an ancestor: a fast-forward is possible and a merge commit's tree equals the candidate's tree. |
| 3 | Lineage required | All 198 commits, one linear stack: 152 from `main` up to `e9c621c` (the DEV UAT base: RD-0B/RD-1, D5A measurement-side work, PU-CORE-001, UX/PU-UI, and the WUI-001–004 consolidation), +40 from `e9c621c` to `9ec49d9` (PU-MIG S0–S6 and P0 remediation), +6 from `9ec49d9` to `4885ca2` (DEC-219, W-1, UI simplification). PU-MIG consumes the DEC-216 unified effective side, so the PU commits cannot be separated from the D5A base without rework. |
| 4 | Dependencies present | Yes. Every dependency is inside the 198 commits or already on `main`; the BEN5K fixes (PRs #9–#11) are ancestors of the candidate. |
| 5 | Unrelated NF/RMS/WUI changes | **NF and RMS: not included** — none of the local NF branches (`nf-1`, `nf-2`, `nf-3a`–`3e`), `rms-display-r0-shared-authority` or the R1A work is an ancestor; no NF-authority symbol exists in the candidate (the `nominal_frequency` mentions are the long-standing source display field from RD-1 Slice C-1). **WUI-001–004: included**, as part of the DEV base: PR #13 merged them into `uat/dev-d5a-20261121`, **not into `main`**, so integrating the candidate also brings the owner-accepted WUI-001–004 consolidation and D5A work to `main`. This enlarges the change beyond PU and should be confirmed (section 10, decision 1). |
| 6 | Merge conflicts | **None** against `main` (`git merge-tree --write-tree origin/main 4885ca2` exit 0; resulting tree identical to `4885ca2`'s tree). Future conflicts with unpublished branches are listed in section 8. |
| 7 | Numbering / project memory | `main` ends at DEC-213; the candidate adds DEC-214, 215, 216, 218, 219. DEC-217 is deliberately unused: it is reserved by NF-001 on the unpublished NF branches (DECISIONS.md states this at DEC-218 and DEC-219). No collision with `main`. |
| 8 | DB / API / config / deployment | No database, migration or persistent-storage change. No route or response field removed against `main`; the additive changes are new routes and fields (`per_unit_verification_state`, present eight times in the OpenAPI document, measurement-side and per-unit-config routes) and one request relaxation (`method` now defaults to `"none"`). No change to `config.py`, `.env.example`, Compose files, `scripts/` or workflows against `main` (the only `scripts/` change is one diagnostic file). |
| 9 | Rollback | Section 7. |
| 10 | Strategy | Section 8. |

Size against `main`: 667 files, +153,431 / −5,169; of these 353 are `docs/project-memory` (mostly evidence screenshots), 134 browser tests,
65 backend application files and 1 frontend page (`frontend/index.html`).

## 6. What PROD runs today (changes the shape of the release)

PROD currently runs only a **skeleton deployment**, not the application. The last PROD deploy through `deploy.yml` is run `31597729649`
(2026-08-12, `main` @ `947b72b`, "ci: isolate Powerwave dev and prod deployments"). The PROD OpenAPI exposes a single path, `/health`; there
is no workspace, upload or analysis API. `947b72b` is **678 commits behind `main`** and 876 behind the candidate. PROD `/health` reports no commit
SHA, so this identification is from the workflow history and the OpenAPI surface, and should be confirmed by the owner who operates the VPS.

Consequence: merging to `main` does not reach PROD (`deploy.yml`: "Merging to main does not reach any environment"), but the
first PROD release of this line is the **first production release of the whole application**, not an incremental PU update.
Requirements that were already on `main` and become PROD requirements:

- `RELAY_REVIEW_SIGNING_KEY` (at least 32 characters, different from DEV) must be set for PROD; `compose.prod.yaml` refuses to start without it and the backend refuses to start without it.
- `BEN5K_EXPERIMENTAL_ENABLED` stays unset in PROD unless the owner approves it (`.env.example`).
- `POWERWAVE_DATA_PATH`, `POWERWAVE_UID`, `POWERWAVE_GID`, `API_BASE_URL` and `CORS_ORIGINS` for PROD, as validated by CI's PROD overlay check.
- `deploy-dev.yml` (on `main`) **automatically deploys `main` to DEV after CI succeeds**. After the integration merge DEV will redeploy the merge commit; its tree equals the accepted `4885ca2` (plus documentation), so the visible effect is the build SHA only.

## 7. Production deployment and rollback plan (proposed; not authorised)

Deployment is a manual `workflow_dispatch` of `deploy.yml` with `target=prod`, from a ref the owner names. The `prod` environment has no
protection rules, so the dispatch itself is the control; it must not be run without the owner's explicit instruction.

1. Owner approves the integration (section 10) and the PROD configuration prerequisites in section 6 are in place on the VPS.
2. Merge to `main`; wait for CI and the automatic DEV deploy; re-run the DEV smoke (section 8, gate G5).
3. Before the first PROD dispatch, create a rollback ref for the current PROD state. `workflow_dispatch` accepts a branch or tag, so
   a tag at `947b72b` is required (a SHA alone cannot be dispatched). Creating it is an outward action and needs owner approval.
4. Dispatch `deploy.yml` `ref=main` (or the release ref the owner names), `target=prod`; verify `/health`, `/config.js`, and the OpenAPI path set (129 paths on DEV `4885ca2`).

**Rollback.** There is no database or migration, and workspace state is ephemeral, so rollback is a redeploy and needs no data restore:
PROD → dispatch `target=prod` with the rollback tag at `947b72b` (restores the `/health`-only state of run `31597729649`); DEV → dispatch `target=dev` with
`uat/dev-pu-mig-20261127` (= `9ec49d9`, run `45909322939`) or `uat/dev-d5a-20261121` (= `e9c621c`, run `45386596132`). Do not edit the VPS or reset branches.

## 8. Recommended integration strategy and final regression gate

**Strategy (recommended): one pull request, `feature/pu-mig-s5-verification-presentation` → `main`, merged with a merge commit.** This matches the repository
convention (PRs #3–#12 on `main` are merge commits), preserves all 198 accepted commits and their DEV-evidence lineage, needs no rebase or force-push, and
yields a tree identical to what the owner accepted. Do not squash. Describe the PR in three segments (152 D5A/WUI base, 40 PU-MIG, 6 DEC-219) so review can follow the
accepted history. The alternative — two PRs (the already DEV-accepted `e9c621c` base first, then PU-MIG) — gives smaller review units but the same final tree and two CI
and review cycles; it is not recommended unless the owner wants the WUI/D5A base reviewed separately. The feature branch is not on `origin` and must be
pushed (a new branch, no force) before the PR; pushing and opening the PR need the owner's approval.

**Unpublished branches (informational; none block this integration).**

| Local branch | Relation to the candidate |
|---|---|
| `feature/nf-1`, `nf-2` | built on `e9c621c`; merge conflict only in `DECISIONS.md` (each adds DEC-217) |
| `feature/nf-3d`, `nf-3e` | conflicts in `DECISIONS.md`, `compliance.py`, `compliance_readiness_service.py`, `browser-tests/playwright.config.js` |
| `feature/rms-display-r0-shared-authority` | merges cleanly |
| `docs/dec-217-governance` | carries a second copy of DEC-218 on a `main` base: conflicts in `DECISIONS.md` and `HANDOFF.md`; should be retired in favour of the candidate's DEC-218 (owner decision) |
| `feature/wui-001`…`wui-004`, `integration/wui-001-002-…` | superseded by the consolidated WUI integration already in the candidate; merging them again would conflict (`wui-004`: 7 files) and must not be done |

**Final regression gate for the integration candidate** (the candidate is the feature branch tip after this documentation commit, whose delta
from `4885ca2` is documentation only; section 1 baseline stays frozen).

| Gate | Requirement | Reuse of DEV evidence |
|---|---|---|
| G1 identity | `git diff 4885ca2..<candidate>` touches only `docs/` | If true, the functional code is identical to the DEV-accepted `4885ca2` and the DEV acceptance evidence applies. |
| G2 CI | CI green on the PR head: full backend `pytest` and the Compose overlay validation (DEV, PROD, isolation). | CI on `4885ca2` was green (run `45986951629`); it must be re-run on the PR head. |
| G3 mergeability | Re-fetch `origin/main` immediately before merging; re-run `git merge-tree --write-tree origin/main <candidate>`; any movement of `main` re-opens this record. | None. |
| G4 full browser | Full Playwright suite on the candidate with `BEN5K_EXPERIMENTAL_ENABLED=1`: no failures beyond the six recorded CSV/Excel failures and the eight owner-recording skips. **Not currently on record at `4885ca2`**: the last full browser run was at `7026f14` (1,808 passed, 6 failed, 8 skipped); after it, DEC-219 and W-1 ran targeted suites only (browser 30 specs, 327 passed). | Partial: acceptable for DEV UAT, recommended to close before PROD. |
| G5 post-merge DEV | After the automatic DEV deploy of `main`: `/health` and `/config.js` report the merge commit; served `index.html` equals the committed page; `dev_smoke3` API smoke 14/14; OpenAPI carries `per_unit_verification_state`. | Same smoke as the accepted deployment. |
| G6 PROD readiness | Section 6 prerequisites present; section 7 rollback ref created; owner approval recorded. | None. |

Backend evidence already on record: full backend at `7026f14` 15,624 tests, 0 failed, 410 skipped; DEC-219 static and backend 2,533, 0 failed;
W-1 targeted 5,482, 0 failed; BEN owner-reference backend 284 passed; independent oracle `--check` OK.

## 9. Related records

[PER_UNIT_MEASUREMENT_MODEL.md](PER_UNIT_MEASUREMENT_MODEL.md) (authoritative model) ·
[PU_MIG_S1_PURE_DENOMINATOR_RESOLVER_2026-11-24.md](PU_MIG_S1_PURE_DENOMINATOR_RESOLVER_2026-11-24.md) ·
[PU_MIG_S2_RAW_VOLTAGE_SIDE_2026-11-25.md](PU_MIG_S2_RAW_VOLTAGE_SIDE_2026-11-25.md) ·
[PU_MIG_S3_CALCULATED_VOLTAGE_SIDE_2026-11-26.md](PU_MIG_S3_CALCULATED_VOLTAGE_SIDE_2026-11-26.md) ·
[PU_MIG_S4_CURRENT_SIDE_2026-11-26.md](PU_MIG_S4_CURRENT_SIDE_2026-11-26.md) ·
[PU_MIG_S2_S4_RECONCILIATION_2026-11-26.md](PU_MIG_S2_S4_RECONCILIATION_2026-11-26.md) ·
[PU_MIG_S5_VERIFICATION_PRESENTATION_2026-11-26.md](PU_MIG_S5_VERIFICATION_PRESENTATION_2026-11-26.md) ·
[PU_MIG_S6_FINAL_ACCEPTANCE_2026-11-26.md](PU_MIG_S6_FINAL_ACCEPTANCE_2026-11-26.md) ·
[PU_VOLTAGE_BASE_SIDE_RETIREMENT_2026-11-27.md](PU_VOLTAGE_BASE_SIDE_RETIREMENT_2026-11-27.md) ·
[DEC-219](DECISIONS.md#dec-219--the-nominal-system-voltage-is-always-the-primary-voltage-pu-base-the-separate-voltage-base-reference-side-input-is-retired).

## 10. Outstanding owner decisions

1. Confirm that integrating the candidate to `main` should also bring the owner-accepted WUI-001–004 and D5A base (not only PU), as recommended in section 8, or request the two-PR split.
2. Approve pushing `feature/pu-mig-s5-verification-presentation` and opening the PR (neither has been done).
3. Decide whether a full browser run on the final candidate (gate G4) is required before the merge or only before PROD.
4. Retire `docs/dec-217-governance` (duplicate DEC-218) and the superseded individual WUI branches, or state how they are to be reconciled.
5. For the first PROD release: confirm the PROD state identified in section 6, provide or confirm the PROD secrets and configuration, approve the rollback tag, and give the explicit instruction to dispatch `target=prod`.
6. Deferred items in section 4 stay unscheduled until the owner asks for them.

## 11. Integration instruction and superseded branches (owner, 2026-11-27)

The owner accepted the readiness report above and authorised the integration steps below. This section records those instructions; it creates no engineering
policy.

**Resolved from section 10.** Decision 1: one merge-commit PR into `main` carrying the complete accepted lineage (D5A, RD-1, WUI-001–004 as already integrated, PU-MIG S1–S6,
DEC-218, DEC-219 and its amendments, this acceptance record); the dependency stack is not split. Decision 2: pushing the branch as a new remote branch and opening the PR are
authorised; the PR is **not** merged until the owner approves. Decision 3: the full browser run (gate G4) is mandatory **before** the merge, not only before PROD. Decision 4:
recorded below. Decisions 5 and 6 remain open.

Excluded: NF development, RMS development, any paused WUI work and every other unaccepted workstream. No squash, rebase or force-push; no existing branch history is rewritten.

**Superseded branches.** None of these is merged independently, deleted or removed from its worktree; cleanup is deferred until after a successful production release.

| Branch (local only unless stated) | Tip | Status |
|---|---|---|
| `docs/dec-217-governance` | `8affd9c` | **Superseded by DEC-218.** Two documentation commits on a `main` base (the governance decision first numbered DEC-217, then renumbered DEC-218); the same decision is already carried, with later amendments, by the candidate. DEC-217 stays reserved for NF-001. Merging it would conflict in `DECISIONS.md` and `HANDOFF.md`. |
| `feature/wui-001-pane-local-y-controls` | `5bce71a` | Superseded by the integrated lineage (WUI-001–004 consolidation, PR #13). |
| `feature/wui-002-global-toolbar-redesign` | `9594a8a` | Superseded by the integrated lineage. |
| `feature/wui-003-modern-pane-adaptive-legend` | `ec10270` | Superseded by the integrated lineage. |
| `feature/wui-004-compact-y-axis-units` | `d513fba` | Superseded by the integrated lineage (`d513fba` is the accepted final UI commit). |
| `integration/wui-001-002-into-dev-20261122` | `b355e69` | Superseded by the integrated lineage. |

`integration/wui-001-004-into-dev-20261123` (`ad1b6ed`) and `integration/wui-001-004-dev-f24f1d7` (`3ed200c`, on `origin`, merged by PR #13) are already ancestors of the candidate.
