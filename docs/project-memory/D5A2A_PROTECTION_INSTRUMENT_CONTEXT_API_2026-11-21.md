# D5A-2A — Protection Instrument Context API and Authority Diagnostics

> **Superseded in part (DEC-215, 2026-11-21):** a nominal-derived (`auto_nominal`) VT is now valid, consumable engineering configuration. Statements below that call it display-only / not consumable describe the earlier D5A rule. See [D5A_AUTO_NOMINAL_VT_POLICY_2026-11-21.md](D5A_AUTO_NOMINAL_VT_POLICY_2026-11-21.md).

**Branch:** `feature/d5a-1-ctvt-authority` · Read-only. No conversion, persistence, override, frontend or PU change.

## 1. Endpoint

`GET /api/v1/workspaces/{workspace_id}/engineering-contexts/{engineering_context_id}/protection-instrument-context`

| Query parameter | Required | Meaning |
|---|---|---|
| `analysis` | yes | `overcurrent` \| `impedance` \| `distance_protection` |
| `phase` | overcurrent, impedance | `A` \| `B` \| `C` |
| `loop` | distance_protection | `AB` \| `BC` \| `CA` |
| `recording_basis`, `impedance_basis`, `vt_primary`, `vt_secondary`, `ct_primary`, `ct_secondary` | no | The **legacy request assumptions**, exactly as the compute endpoints take them. Accepted only to be compared with Recording Details; echoed back verbatim; never applied. |

Status codes: `200`; `404 engineering_context_not_found`; `422` (unknown `analysis`/`phase`/`loop`, or the phase/loop the analysis needs is missing); `400 invalid_workspace`.

Channels are resolved through the **same requirement and role mappings the compute paths use** (Overcurrent `OVERCURRENT_CURRENT_PHASE_*`; Impedance and Distance the phasor-diagram roles `Va…Ic`, Distance via `LOOP_ROLE_KEYS`). A parity test asserts the endpoint and `/impedance` pick the same channels.

## 2. Response

```
read_only: true                       always
analysis, engineering_context_id, phase, loop
channels[]:   one per RESOLVED role
  role_key            "Va" | "Ia" | …
  quantity            "voltage" | "current"
  channel             { kind, source_id, channel_name, calculated_channel_id }
  measurement_group_id / measurement_group_kind   (null if ungrouped)
  declared_side       "primary" | "secondary" | "unknown"      per channel, never shared
  side_evidence       "recording_declared" | "none"
  provider_type       e.g. "COMTRADE"
voltage | current:                    null when the analysis does not use that quantity
  ratio_status        configured | no_channels | no_group | not_configured | untrusted_authority | invalid | conflict
  ratio_consumable    true only when ratio_status == configured
  group_ids[], primary, secondary, ratio (= primary/secondary), authority
  ratio_origin        "recording_details_measurement_group" when configured, else null
  provenance_note     the group's CT/VT provenance note
  reason              why a ratio is unavailable
  side, side_status   aggregated over the resolved channels of that quantity: recording_declared | unknown | mixed
  declared_basis      "primary"/"secondary" only when side_status == recording_declared
  ignored_nominal_kv  voltage only: a nominal kV exists but is display-only and was NOT used
request:      the legacy parameters as supplied
diagnostics[] { code, severity: "warning"|"info", quantity, message, detail{} }
```

## 3. Authority and provenance rules

1. Ratio authority is the **Recording Details Measurement Group** that owns the channel (Current group → CT, Voltage group → VT), looked up by workspace and `ChannelRef` (source id + channel name). Different recordings, sources and workspaces never share configuration.
2. Consumable ratio authorities: `manual`, `recording_metadata`. Anything else is `untrusted_authority`.
3. `auto_nominal` VT (nominal kV ÷ assumed 110 V) is display-only: never a ratio, never leaked into `primary`/`secondary`/`ratio`; reported only as `ignored_nominal_kv` plus `VT_NOMINAL_DISPLAY_ONLY`.
4. COMTRADE channel primary/secondary scaling is evidence of scaling, not a CT/VT nameplate; it is not read here.
5. Measurement side comes **only** from the recording's own per-channel declaration. Voltage and current are resolved independently; a configured ratio never implies a side; unknown/mixed never yields a `declared_basis`.
6. Calculated channels have no group and an unknown side.

## 4. Diagnostic reason codes (all non-blocking)

| Code | Severity | Raised when |
|---|---|---|
| `CHANNEL_UNRESOLVED` | warning | a required role did not resolve (detail: role_key, status, reason) |
| `CT_AUTHORITY_MISSING` / `VT_AUTHORITY_MISSING` | warning | no usable group ratio (detail: ratio_status, reason, authority, group_ids) |
| `VT_NOMINAL_DISPLAY_ONLY` | info | nominal kV present, no VT; nominal not used |
| `REQUEST_CT_INCOMPLETE` / `REQUEST_VT_INCOMPLETE` | warning | only one of primary/secondary supplied |
| `REQUEST_CT_INVALID` / `REQUEST_VT_INVALID` | warning | non-finite or non-positive request values |
| `REQUEST_CT_DIFFERS_FROM_AUTHORITY` / `REQUEST_VT_DIFFERS_FROM_AUTHORITY` | warning | request ratio ≠ group ratio (rel. tol 1e-6; detail has both) |
| `REQUEST_CT_NOT_VERIFIED_BY_AUTHORITY` / `REQUEST_VT_NOT_VERIFIED_BY_AUTHORITY` | info | request ratio supplied but no authoritative ratio exists to verify it |
| `VOLTAGE_SIDE_UNKNOWN` / `CURRENT_SIDE_UNKNOWN` | warning | recording does not declare the side |
| `VOLTAGE_SIDE_MIXED` / `CURRENT_SIDE_MIXED` | warning | resolved channels of that quantity declare different sides |
| `VOLTAGE_CURRENT_SIDES_DIFFER` | warning | both sides declared and different (detail: both) — one `recording_basis` cannot represent this |
| `REQUEST_RECORDING_BASIS_INVALID` | warning | not `primary`/`secondary` |
| `REQUEST_RECORDING_BASIS_CONTRADICTS_VOLTAGE_SIDE` / `…_CURRENT_SIDE` | warning | request basis ≠ declared side of that quantity |
| `REQUEST_RECORDING_BASIS_UNVERIFIABLE_VOLTAGE` / `…_CURRENT` | info | basis supplied but that quantity's side is unknown/mixed |
| `CONVERSION_REQUESTED_WITHOUT_AUTHORITY` | warning | request converts (Overcurrent: basis `primary`; Impedance/Distance: `recording_basis ≠ impedance_basis`) but that quantity has no consumable ratio |
| `CONVERSION_REQUESTED_WITH_UNKNOWN_SIDE` | warning | the same conversion, but that quantity's side is unknown/mixed |

Legacy request parameters are never overwritten; a test proves the compute endpoint returns identical results, with the request's own ratios, before and after this endpoint is called.

## 5. Tests

`test_d5a2a_protection_instrument_context_api.py` (22, real COMTRADE uploads) and `test_d5a2a_protection_instrument_diagnostics.py` (17, one per rule): group/channel association, multi-recording isolation, no synthetic VT, per-channel/independent/mixed/unknown sides, every request-vs-authority diagnostic, errors, legacy-unchanged and channel-parity.
