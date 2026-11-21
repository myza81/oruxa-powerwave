# D5A-1 — CT/VT Engineering Authority and Protection-Analysis Data Flow

**Date:** 2026-11-21 · **Branch:** `feature/d5a-1-ctvt-authority` · **Start commit:** `77fc74a` (code identical to the verified PU baseline `229fba1`)

Final principle: **CT/VT ratios are configuration data, not proof of the physical measurement side.**
No PU code, CT/VT conversion, API, frontend or numerical behaviour was changed. This slice adds a read-only lookup contract and tests only.

## 1. Verified current data flow (code references on the start commit)

| | Overcurrent | Impedance Locus | Distance Protection |
|---|---|---|---|
| Where CT/VT originate | Request parameters `ct_primary`/`ct_secondary` — recorded route `GET /engineering-contexts/{id}/overcurrent` (`api/v1/engineering_contexts.py:812-868`), manual route `:722-757` | `vt_*`/`ct_*` request parameters — `/impedance` and `/impedance-locus` (`engineering_contexts.py:887-968`), manual `:996-` | `vt_*`/`ct_*` request parameters — `/distance-protection` and `-locus` (`engineering_contexts.py:1247-1377`), manual `:1413-` |
| Basis of incoming samples | Caller-asserted `recording_basis` (`services/overcurrent_analysis_service.py:180-183, 231-236`) | Caller-asserted single `recording_basis` for **both** V and I (`services/impedance_analysis_service.py:74-111`) | Same single `recording_basis` (`services/distance_protection_analysis_service.py:69-112`) |
| Where samples enter | Source channel via engineering-context role resolution (`_fetch_current_candidate`, `:107-138`) | Same, via the shared phasor preparation | Same |
| Where scaling happens | `convert_to_relay_secondary` / `convert_array_to_relay_secondary` (`domain/overcurrent.py:500-560`), once, only if basis is `primary` | `convert_impedance_basis` (`domain/impedance.py:163-209`), once, only if `recording_basis != impedance_basis` (`impedance_analysis_service.py:160,184`) | Same helper (`distance_protection_analysis_service.py:178,204`) |
| Output basis | Relay-secondary amperes | Caller-chosen `impedance_basis` (independent of recording basis) | Same |
| Reads Measurement Groups / `measurement_side` / group CT-VT? | **No** | **No** | **No** |
| Manual mode | Single `input_basis` (current only) | **Independent** `voltage_basis` and `current_basis`; each quantity normalised to secondary before dividing, then one output conversion (`domain/impedance.py:326-408`) | Same, four legs (`domain/distance_protection.py:716-809`) |

Evidence that no protection module consults the authority: no reference to the group registries, `measurement_side`, `ct_authority`/`vt_authority` exists in the three services, three domain modules or the `engineering_contexts` API. The competing authority is the **frontend per-panel state** (`s.ctPrimary`, `s.vtPrimary`, `s.recordingBasis`, `m.voltageRatioPrimary` …, e.g. `frontend/index.html` ≈51056, 52423, 52510, 52981, 53462, 53914) — Codex's territory, not touched.

Ratio application count: each engine converts **exactly once** (primary→secondary, or one output conversion). No double application inside the backend. Nothing, however, reconciles the caller's asserted basis/ratios with the recording or with Recording Details.

Test evidence: baseline on the start commit for all protection modules (incl. their frontend static tests) = **1,497 passed, 0 failed**; plus 22 new pins (`test_d5a1_protection_ratio_semantics.py`).

## 2. Findings

- **F1 — No authoritative consumption.** Ratios and bases are re-entered per analysis; Recording Details CT/VT (`CurrentBaseConfiguration.ct_primary_a/ct_secondary_a/ct_authority`, `VoltageBaseConfiguration.vt_primary_v/vt_secondary_v/vt_authority`, `domain/current_group_config.py:165-183`, `domain/voltage_group_config.py:173-186`) is stored but unused by analyses.
- **F2 — Recorded Impedance/Distance cannot represent mixed sides.** One `recording_basis` governs V and I. Worked example (VT 110000:110, CT 1000:5, true Z = 165 Ω primary / 33 Ω secondary): with V primary (66 000 V) and I secondary (2 A) and `recording_basis="primary"`, the engine divides raw V/I = 33 000 Ω and reports 33 000 Ω primary, or 6 600 Ω secondary (×ct/vt) — wrong by exactly the CT ratio (200×). Manual mode handles the same case correctly (pinned by tests). **Numerical policy decision required (D1).**
- **F3 — Caller-asserted basis is never checked against the channel's declared side** (`AnalogChannel.measurement_side`, COMTRADE `ps` P/S only: `domain/reference_side.py:8-9`, `providers/comtrade.py:806`). A wrong basis silently mis-scales.
- **F4 — Unknown side is never silently converted by the engines:** every entry point rejects a basis other than `primary`/`secondary` (`needs_configuration`, `invalid_basis`/`invalid_recording_basis`; pinned). The gap is upstream: something must choose the basis.
- **F5 — `auto_nominal` VT is an assumption.** `measurement_group_view_service.py:121-134` synthesises VT = nominal kV : **110 V** when none is configured. Display-only; must never be consumed as a ratio.
- **F6 — `recording_metadata` authority is reserved but never written.** Live writers store only `manual` or `not_configured` (`current_group_config_service.py:300-309`, `voltage_group_config_service.py:195-205`). COMTRADE channel `primary_ratio/secondary_ratio` are not promoted into group CT/VT.

## 3. Source → Measurement Group authority contract (implemented)

`app/services/protection_instrument_context.py` (read-only, no new storage):

1. Channel identity: `ChannelRef(source_id, channel_name)` resolved by the analysis (calculated channels → no group, side unknown).
2. Group: `MeasurementGroupRegistry.group_for_channel(workspace_id, ref)`; group `kind` must match the quantity (current→Current group, voltage→Voltage group).
3. Ratio: raw `ct_*`/`vt_*` from the group's own configuration registry keyed `(workspace_id, group_id)`. Consumable only when authority ∈ {`manual`, `recording_metadata`} and the pair is finite and positive. All channels of the role must agree (ratio within 1e-9) else `conflict`.
4. Ratio status vocabulary: `configured`, `no_channels`, `no_group`, `not_configured`, `untrusted_authority`, `invalid`, `conflict`. Ratio convention `primary/secondary`.
5. Isolation: keyed by workspace and source id; verified no leakage across sources or workspaces.

## 4. Treatment of measurement sides (implemented)

Side comes only from the recording's own `measurement_side` (P/S marker), resolved **separately for voltage and current**.

| Condition | `side_status` | `declared_basis` |
|---|---|---|
| All channels declare `primary` (or all `secondary`) | `recording_declared` | that side |
| Any channel `unknown`, source missing, or calculated | `unknown` | `None` |
| Channels declare both sides | `mixed` | `None` |

A configured ratio never changes the side. Unknown/mixed never yields a proposed basis and nothing is converted.

## 5. Implemented in D5A-1 (smallest safe slice)

- `app/services/protection_instrument_context.py` — lookup + side contract (not wired into any compute path).
- `tests/test_d5a1_instrument_context.py` — 30 tests: correct CT/VT group, multi-source/workspace isolation, missing/invalid/untrusted configuration, `auto_nominal` exclusion, side declared/unknown/mixed, V/I independence.
- `tests/test_d5a1_protection_ratio_semantics.py` — 22 pins with hand-derived values for Overcurrent (once-only, kA, secondary untouched, missing CT refused, unknown basis refused), Impedance/Distance (all four V/I side combinations give 165 Ω primary / 33 Ω secondary, no-op same basis, round trip, unknown basis refused, primary output without ratios refused).

## 6. Remaining engineering decisions (owner)

- **D1 — Recorded Impedance/Distance mixed-side policy.** Adopt the manual-mode rule (normalise V and I to secondary independently, divide, one output conversion) for recorded channels? Requires separate `voltage_basis`/`current_basis` on the recorded API — an interface change.
- **D2 — Basis reconciliation.** If the request basis disagrees with the declared side: reject, warn, or let Recording Details override?
- **D3 — Unknown side with configured ratios.** Where does an engineer-confirmed basis live? Any group field would be new configuration storage.
- **D4 — Confirm `auto_nominal` stays display-only.**
- **D5 — Populate `recording_metadata` from COMTRADE channel primary/secondary?** Those describe the channel's scaling, which is not necessarily the CT/VT nameplate ratio.
- **D6 — Frontend (Codex):** replace per-panel CT/VT inputs with group-sourced values.

## 7. Recommended D5A-2 scope

1. Additive read-only GET exposing `ProtectionInstrumentContext` for an engineering context's resolved roles (no new storage).
2. Advisory, non-blocking check comparing request-supplied basis/ratios with the authoritative context (diagnostic only; blocking needs D2).
3. After D1: recorded-path per-quantity normalisation for Impedance/Distance with the worked example as the regression oracle.
4. Codex: group-sourced CT/VT in the three panels.

## 8. Must not change

Accepted PU engine and contracts, DEC-049 compatibility exception, H2 legacy path, RD-0B, CT/VT conversion until D1–D3 are decided.
