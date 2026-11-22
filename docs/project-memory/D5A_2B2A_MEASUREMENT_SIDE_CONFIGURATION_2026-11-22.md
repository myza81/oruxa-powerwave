# D5A-2B2A — Unified measurement-side configuration and shared resolver

**Branch:** `feature/d5a-2b2a-measurement-side-config`, from the accepted D5A UAT baseline `a2b55eb`
(`origin/uat/dev-d5a-20261121`). **Not pushed, merged or deployed.** Backend only.
**Supersedes:** [D5A2B2_MEASUREMENT_SIDE_DATA_MODEL_PROPOSAL_2026-11-21.md](D5A2B2_MEASUREMENT_SIDE_DATA_MODEL_PROPOSAL_2026-11-21.md)
(group-level fields on the Voltage/Current base configurations). That proposal is **not** implemented; see
[DEC-216](DECISIONS.md#dec-216--recording-details-is-the-single-authority-for-recorded-measurement-side-d5a-2b2-unified-model).

## 1. What this slice delivers

One authoritative, stateless resolver — `resolve_effective_measurement_side(workspace_id, source_id, channel_name, deps=…)` in
[measurement_side_service.py](../../backend/app/services/measurement_side_service.py) — plus the configuration and read/write API behind it.
It changes **no** PU, Overcurrent, Impedance or Distance behaviour and adds **no** UI. Every later consumer must call the resolver
(or `resolve_consumed_side()` for the set of channels one calculation consumes); none may interpret a P/S marker or a request
parameter itself.

## 2. Data model and precedence

| Level | Key | Stored (engineer decision only) |
|---|---|---|
| 1 — Recording | `(workspace_id, source_id)` | optional correction `{side, note, set_at}` |
| 2 — Bay (Engineering Context) **within one recording** | `(workspace_id, engineering_context_id, source_id)` | optional override `{side, set_at}` |

Evidence is **never stored here**: the recording's per-channel P/S marker stays on the source's channels, untouched. A bay with no
override stores nothing (no duplicated per-bay default). Registry: `MeasurementSideRegistry`; in memory only; same lifetime as the
other sibling registries.

Effective side of one Voltage/Current channel — first match wins:

| # | Source | `authority` |
|---|---|---|
| 1 | bay override (bay membership `confirmed`/`manual` only) | `engineer_bay_override` |
| 2 | recording correction | `engineer_recording_correction` |
| 3 | the channel's own original P/S declaration | `recording_channel_declared` |
| 4 | recording default: the consistent declaration of the recording's *other* channels — **inferred** (`inferred: true`, not `strict_usable`) | `recording_default` |
| 5 | nothing | `unresolved` (`effective_side: "unknown"`, `usable: false`) |

Recording-derived (Level 1) evidence is `consistent` (every declaring channel agrees), `mixed` (declarations differ → **no** default), or
`none`. Level 1 effective = engineer correction, else the consistent evidence, else unresolved.

Behaviour rules (all tested):

1. Changing Level 1 updates every bay without an override (nothing is copied into them).
2. A manually overridden bay keeps its value when Level 1 changes.
3. Selecting the side a bay currently inherits clears its override; there is no Reset. (Level 1 mirrors this: selecting the value the
   recording already declares consistently stores no correction; `side: null` removes one.)
4. An engineer value that disagrees with a channel's declaration wins, and the declaration stays visible (`declared_side`, plus
   `ENGINEER_CORRECTION_OVERRIDES_DECLARATION` / `BAY_OVERRIDE_OVERRIDES_DECLARATION`).

## 3. Bay ownership

A bay is an **Engineering Context**. A channel belongs to exactly one source (its `ChannelRef`) and, by the existing registry invariant,
to at most one bay. Nothing is parsed from channel names. A bay setting applies only while the context's status is `confirmed` or
`manual`; a `suggested`/`needs_review` context is ambiguous ownership: no bay setting is applied to its channels
(`BAY_MEMBERSHIP_UNCONFIRMED`), a stored override is inactive (`BAY_OVERRIDE_INACTIVE_UNCONFIRMED_MEMBERSHIP`), and setting one is refused
(`409 bay_membership_unconfirmed`). A channel in no bay follows its recording. The CT/VT Measurement Groups of a bay's members are
reported (`voltage_group_ids`, `current_group_ids`); they never change the side and no ratio is read or applied here.

## 4. Conflicts and diagnostics (stable codes)

`RECORDING_SIDE_EVIDENCE_MISSING`, `RECORDING_MIXED_SIDE_EVIDENCE`, `RECORDING_PARTIAL_SIDE_EVIDENCE`,
`ENGINEER_CORRECTION_OVERRIDES_DECLARATION`, `BAY_OVERRIDE_OVERRIDES_DECLARATION`, `BAY_MIXED_SIDES_WITHIN_QUANTITY`,
`BAY_VOLTAGE_CURRENT_SIDES_DIFFER`, `BAY_SIDE_UNRESOLVED`, `BAY_MEMBERSHIP_UNCONFIRMED`, `BAY_OVERRIDE_INACTIVE_UNCONFIRMED_MEMBERSHIP`,
`BAY_HAS_NO_VOLTAGE_CURRENT_MEMBERS`, `BAY_RECORDINGS_DISAGREE`, `CONSUMED_CHANNELS_SIDES_DIFFER`, `CONSUMED_CHANNEL_SIDE_UNRESOLVED`,
`SOURCE_NOT_FOUND`, `CHANNEL_NOT_FOUND`, `CHANNEL_NOT_VOLTAGE_OR_CURRENT`, `CALCULATED_CHANNEL_NOT_RESOLVED`.
Severity is `info` / `warning` / `conflict`. A set of channels (a bay, or what a calculation consumes) resolves to one side only when
**every** channel agrees. Channels that disagree **within one quantity** give `status: conflict`; any unresolved channel gives `unresolved` — never a
manufactured single interpretation, and per-channel sides remain available. **Voltage on one side and current on the other is not a conflict
(owner decision B2A-1)**: the set is `resolved`, `side` is null, `voltage_side`/`current_side` are set, `reference_sides` is `voltage_current_differ`
and `BAY_VOLTAGE_CURRENT_SIDES_DIFFER` / `CONSUMED_VOLTAGE_CURRENT_SIDES_DIFFER` are `info`.
`usable` means every channel has a concrete side; `strict_usable` additionally requires that none is merely inferred (B2A-2).

## 5. API (additive; `/api/v1/workspaces/{workspace_id}`)

| Method / path | Purpose |
|---|---|
| `GET /measurement-side` | every recording's Level 1 state and every bay's Level 2 state (no channel detail) |
| `GET /sources/{source_id}/measurement-side` | Level 1: `recording_derived` evidence, `engineer_correction`, `effective_side`, `authority`, `bay_ids`, diagnostics, per-channel resolution |
| `PUT /sources/{source_id}/measurement-side` | body `{side: "primary"\|"secondary"\|null, note?}` |
| `GET /engineering-contexts/{id}/measurement-side` | the bay with **one association per recording** that contributes voltage/current channels (each as below); nothing is shared or inherited across recordings |
| `GET /sources/{source_id}/engineering-contexts/{id}/measurement-side` | Level 2 for the bay **within that recording**: `inherited_recording_side` (that recording's own Level 1), `override {side,set_at,active}`, `status`, `effective_side`, `voltage_side`, `current_side`, `reference_sides`, `strict_usable`, `group_ownership`, diagnostics, per-channel resolution |
| `PUT /sources/{source_id}/engineering-contexts/{id}/measurement-side` | body `{side: "primary"\|"secondary"}` (null rejected: no reset); never touches another recording's channels of the same bay |
| `GET /measurement-side/channel?source_id=&channel_name=` | the shared resolver for one channel; never an error for an unresolvable channel |

Errors: `404 source_not_found` / `engineering_context_not_found`, `409 bay_membership_unconfirmed` / `bay_has_no_measurement_channels`, `422` for an invalid side.
Existing endpoints are unchanged (no field added, removed or re-typed).

## 6. Lifecycle and isolation

Cleared with: the workspace (`DELETE /workspaces/{id}`), the source (`DELETE …/sources/{id}` removes its Level 1 correction and every bay
override scoped to that recording), the bay (`DELETE …/engineering-contexts/{id}` removes every recording's override of it), or the membership
(a `PATCH` that removes a recording's channels from the bay releases that recording's override). A bay that spans several sources survives a
source removal, keeping the other recordings' overrides. A re-upload gets a new `source_id` and therefore starts with no correction. Everything is keyed by
`workspace_id`; ids never resolve across workspaces. No persistence of any kind.

## 7. Verification

`tests/test_d5a2b2a_measurement_side_config.py` — 66 tests, expected sides/authorities stated by hand from the owner's rules.
Mutation checks (each fails the suite): removing clear-on-equal (2), dropping the Level 1 correction tier (8), dropping the channel-declaration
tier (13), a fabricated recording default (4), treating mixed evidence as consistent (4), applying an unconfirmed bay override (2).
The "existing results unchanged" test snapshots Overcurrent, Impedance (legacy and strict), the protection-instrument context, PU coverage, the
source channel list and the Measurement Group list before and after every Level 1 / Level 2 change and requires identical responses.

Full backend regression: 13,448 passed / 405 skipped / 0 failed / 0 errors (13,853 collected, 1,148 s). The D5A-OC baseline was 13,386 passed / 405 skipped, so the delta is exactly the 62 new tests; no existing test changed.

## 8. Plan after this slice (owner decisions of 2026-11-22; see DEC-216)

| Slice | Scope |
|---|---|
| **D5A-2B2A** (this) | Shared backend authority, configuration, API contract, lifecycle, tests |
| **D5A-2B2B** | Recording Details frontend: recording-level and per-bay Primary/Secondary control, read-only provenance/diagnostics (engineer-task-first, DEC-214) |
| **PU migration** (own slice; sequencing to be confirmed) | Retire the separate PU Base Reference Side input; derive a compatible denominator from the effective side and the authoritative CT/VT; preserve nominal L-L, L-L/L-N, derived Ibase, DEC-211, DEC-213, calculated-channel policies and DEC-215. Review the manual Current base's reference-side contract first |
| **D5A-2B2C** | Consumer migration and removal of duplicate recorded-mode selectors: Overcurrent "Recording current basis", Impedance/Distance recorded voltage/current-side selectors. Backend enforcement: a recorded request cannot silently override Recording Details; unresolved/contradictory side blocks. One consistent safety policy replaces today's Overcurrent strict-block vs Impedance/Distance warning-only inconsistency. Cross-consumer regression of one recording through PU, Overcurrent, Impedance and Distance. Output-side (primary/secondary impedance) controls and Manual mode stay |
| **D5A-2B2D** | Legacy retirement |

## 9. Limitations (original nine; owner answers of 2026-11-22 in the right-hand column)

1. **Voltage and current on different sides in one bay** — *ANSWERED (B2A-1):* not a conflict; `info` diagnostic, `reference_sides: voltage_current_differ`,
   each quantity normalised independently. Only disagreement within one quantity is a conflict.
2. **Partial evidence** — *ANSWERED (B2A-2):* `recording_default` is inferred (`inferred`, not `strict_usable`); strict consumers need reliable evidence or an
   engineer-confirmed Recording/Bay setting.
3. **Bay spanning recordings with different Level 1 sides** — *RESOLVED in D5A-2B2B (owner safety refinement):* a Level 2 setting belongs to the bay within one
   recording; each recording is interpreted separately and nothing is inherited across them.
4. **Unconfirmed bays** — *ANSWERED (B2A-3):* approved; Level 1 and inheritance continue to work without confirming bays.
5. **Providers without P/S evidence (BEN, CSV/Excel)** — *ANSWERED (B2A-4):* approved; never inferred from ratios or magnitude.
6. **Calculated channels** are not resolved by this slice (`CALCULATED_CHANNEL_NOT_RESOLVED`); deferred to D5A-2B2C — the open lineage questions are listed in the D5A-2B2B document §7.
7. **A CT/VT group spanning two bays with different sides** — *RESOLVED in D5A-2B2B:* diagnosed (`GroupOwnership`, see the D5A-2B2B document); the future consumer blocks.
8. An engineer value winning over a declaration — *ANSWERED (B2A-5):* approved; warning + `overridden_declarations`, consumable, UI must disclose.
9. The old D5A-2B2 rule "a confirmed side never feeds PU" (proposal §6/Q4) is superseded: PU is a planned consumer of the effective side.
