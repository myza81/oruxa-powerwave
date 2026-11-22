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
| 2 — Bay (Engineering Context) | `(workspace_id, engineering_context_id)` | optional override `{side, set_at}` |

Evidence is **never stored here**: the recording's per-channel P/S marker stays on the source's channels, untouched. A bay with no
override stores nothing (no duplicated per-bay default). Registry: `MeasurementSideRegistry`; in memory only; same lifetime as the
other sibling registries.

Effective side of one Voltage/Current channel — first match wins:

| # | Source | `authority` |
|---|---|---|
| 1 | bay override (bay membership `confirmed`/`manual` only) | `engineer_bay_override` |
| 2 | recording correction | `engineer_recording_correction` |
| 3 | the channel's own original P/S declaration | `recording_channel_declared` |
| 4 | recording default: the consistent declaration of the recording's *other* channels | `recording_default` |
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
**every** channel agrees; different sides give `status: conflict`, any unresolved channel gives `unresolved` — never a manufactured
single interpretation. Per-channel sides remain available in both cases.

## 5. API (additive; `/api/v1/workspaces/{workspace_id}`)

| Method / path | Purpose |
|---|---|
| `GET /measurement-side` | every recording's Level 1 state and every bay's Level 2 state (no channel detail) |
| `GET /sources/{source_id}/measurement-side` | Level 1: `recording_derived` evidence, `engineer_correction`, `effective_side`, `authority`, `bay_ids`, diagnostics, per-channel resolution |
| `PUT /sources/{source_id}/measurement-side` | body `{side: "primary"\|"secondary"\|null, note?}` |
| `GET /engineering-contexts/{id}/measurement-side` | Level 2: `inherited_recording_side`, `override {side,set_at,active}`, `status`, `effective_side`, `voltage_side`, `current_side`, group ids, diagnostics, per-channel resolution |
| `PUT /engineering-contexts/{id}/measurement-side` | body `{side: "primary"\|"secondary"}` (null rejected: no reset) |
| `GET /measurement-side/channel?source_id=&channel_name=` | the shared resolver for one channel; never an error for an unresolvable channel |

Errors: `404 source_not_found` / `engineering_context_not_found`, `409 bay_membership_unconfirmed` / `bay_has_no_measurement_channels`, `422` for an invalid side.
Existing endpoints are unchanged (no field added, removed or re-typed).

## 6. Lifecycle and isolation

Cleared with: the workspace (`DELETE /workspaces/{id}`), the source (`DELETE …/sources/{id}` removes its Level 1 correction and
prunes overrides of bays it emptied), the bay (`DELETE …/engineering-contexts/{id}`). A bay that spans several sources survives a
source removal with its override. A re-upload gets a new `source_id` and therefore starts with no correction. Everything is keyed by
`workspace_id`; ids never resolve across workspaces. No persistence of any kind.

## 7. Verification

`tests/test_d5a2b2a_measurement_side_config.py` — 62 tests, expected sides/authorities stated by hand from the owner's rules.
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

## 9. Limitations needing an owner decision before the frontend / PU stages

1. **Voltage and current on different sides in one bay is reported as a `conflict`** (per the owner's rule), yet Impedance/Distance legitimately
   normalise V and I independently. Decide whether, for those consumers, a bay-level V/I difference blocks or only warns when each channel's side
   is individually resolved (per-channel sides are available either way).
2. **Partial evidence**: an undeclared V/I channel takes the consistent default of its siblings (`recording_default`, with an info diagnostic). Decide
   whether strict consumers may accept `recording_default` or require `recording_channel_declared` / an engineer value.
3. **Bay spanning recordings with different Level 1 sides** has no single inherited value, so selecting a side is always a manual override (nothing to clear to).
4. **Unconfirmed bays** (`suggested`/`needs_review`) cannot take a bay setting. The UI must offer promotion to confirmed before the control is enabled.
5. **Providers without P/S evidence (BEN, CSV/Excel)** resolve `unresolved` until an engineer sets Level 1 — by design, nothing is guessed.
6. **Calculated channels** are not resolved by this slice (`CALCULATED_CHANNEL_NOT_RESOLVED`); their side follows their inputs and belongs to the PU / consumer slices.
7. **A CT/VT group spanning two bays with different sides** is not diagnosed here (groups never carry a side); decide whether the Recording Details UI should flag it.
8. An engineer value silently winning over a declaration is reported as a `warning` diagnostic, not a block. Confirm that is the intended strictness.
9. The old D5A-2B2 rule "a confirmed side never feeds PU" (proposal §6/Q4) is superseded: PU is a planned consumer of the effective side.
