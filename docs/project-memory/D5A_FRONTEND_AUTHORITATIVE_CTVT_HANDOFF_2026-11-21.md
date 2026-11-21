# D5A — Frontend hand-off: consume authoritative CT/VT in Impedance Locus and Distance Protection

> **Superseded in part (DEC-215, 2026-11-21):** a nominal-derived (`auto_nominal`) VT is now valid, consumable engineering configuration. Statements below that call it display-only / not consumable describe the earlier D5A rule. See [D5A_AUTO_NOMINAL_VT_POLICY_2026-11-21.md](D5A_AUTO_NOMINAL_VT_POLICY_2026-11-21.md).

**For:** Codex (Waveform Analysis redesign) and the owner · **From:** Claude (backend / API, and — per the §7 update — this Impedance/Distance frontend change) · **Status:** backend fix committed separately; frontend change implemented in its own commit, pending owner review.
**Approved direction (owner):** retrieve the authoritative Measurement Group CT/VT, display it **read-only**, and navigate to Recording Details for corrections. No competing CT/VT editor. `auto_nominal` is never an authoritative ratio.

## 1. Why (confirmed on a KPDN1 reproduction)

The Impedance Locus and Distance panels keep their own VT/CT fields (`wwImpedanceState.settings.vtPrimary…`, `wwDistanceState.settings…`), default `null`, filled only by typing. `wwImpedanceBasisParams` / `wwDistanceBasisParams` send ratios only when the two bases differ **and** all four panel fields are set, so a recording configured in Recording Details still gets `Valid VT and CT ratios are required…`. Recording Details shows a nominal-derived VT (`vt_effective_authority = auto_nominal`, "Based on nominal voltage") that is **not** a stored ratio. Related Waveforms said "No related waveform signals available" because blocked results carried no channel references — **fixed in the backend** (see §2).

## 2. What the backend already provides

- `GET /api/v1/workspaces/{ws}/engineering-contexts/{ctx}/protection-instrument-context?analysis=impedance|distance_protection&phase=A|B|C | loop=AB|BC|CA[&recording_basis=…&impedance_basis=…]` (D5A-2A, read-only). Per channel: `channel` (source/channel), `measurement_group_id`, `declared_side`. Per quantity (`voltage`, `current`): `ratio_status`, `ratio_consumable`, `primary`, `secondary`, `ratio`, `authority`, `group_ids`, `provenance_note`, `side`, `side_status`, `declared_basis`, `ignored_nominal_kv`. `diagnostics[]` with stable `code`s.
- Only `manual` / `recording_metadata` ratios are `ratio_consumable`; a nominal-only VT is `not_configured` with `ignored_nominal_kv` and the diagnostic `VT_NOMINAL_DISPLAY_ONLY`.
- Blocked `/impedance` and `/distance-protection` results (missing/invalid ratio, unsupported unit, strict side checks) now keep `voltage_channel_ref` / `current_channel_ref` (Distance: `v1/v2/i1/i2_channel_ref`) and `voltage_unit` / `current_unit` for the channels that resolved; an unresolved channel stays `null`. Status, `reason_code`, `message` and the absent impedance values are unchanged, so `wwImpedanceComputeActiveRelatedWaveformRoles()` / `wwDistanceComputeActiveRelatedWaveformRoles()` need no change.
- Legacy numerics are unchanged: the request still carries `recording_basis`, `impedance_basis` and, when a conversion is needed, `vt_primary/vt_secondary/ct_primary/ct_secondary`.

## 3. Proposed frontend change (Recording mode of Impedance Locus and Distance only)

1. On context / phase (loop) / basis change and on entering the page, fetch the context report; re-fetch after a Recording Details save.
2. Replace the four VT/CT inputs (Recording mode) with a **read-only** block: VT and CT value, authority, group name, and a **Configure in Recording Details** button that calls the existing `wwNavigateToRdForGroup(sourceId, groupId)` (ids come from `channels[]`). **Manual mode keeps its own inputs untouched.**
3. When the bases differ and the needed ratios are `ratio_consumable`, send those values through the existing legacy parameters (numbers unchanged). Never send the nominal-derived VT. Never send a partial set.
4. If a needed ratio is not consumable, do **not** request the calculation; show the specific message below.

## 4. Safety rules for measurement sides (must hold)

- If conversion is required and **voltage and current declare different sides** (`VOLTAGE_CURRENT_SIDES_DIFFER`) or a quantity is `mixed`: no request; message "Voltage and current are recorded on different sides; this single-basis analysis cannot convert them. Independent-side mode is required." Never choose a basis silently.
- If a needed side is **unknown**: do not default `recording_basis`; leave the control unset with "The recording does not declare whether the voltage/current channels are primary or secondary — choose the Recording basis explicitly." Once chosen, show a persistent "unverified" marker. A contradiction with a declared side (`REQUEST_RECORDING_BASIS_CONTRADICTS_*`) is shown, not overridden.
- If sides agree and are declared, pre-select `recording_basis` from `declared_basis`.
- Strict mode (`voltage_side` / `current_side`) is **not** adopted by the UI without separate owner authorisation.

## 5. Actionable messages (from `ratio_status` / diagnostics)

| Condition | Message |
|---|---|
| VT `not_configured`, `ignored_nominal_kv` present | "VT is not configured for '<group name>'. The <kV> kV / 110 V shown in Recording Details is derived from the nominal voltage and is display-only. Open Recording Details → VT → Edit → Save to confirm it." |
| VT `not_configured`, no nominal | "VT is not configured for '<group name>'. Set primary kV and secondary V in Recording Details." |
| CT `not_configured` | "CT is not configured for '<group name>'. Set primary and secondary A in Recording Details." |
| `no_group` | "<channel> is not in a <Voltage/Current> Measurement Group. Add it in Recording Details." |
| `invalid` / `untrusted_authority` | "The <VT/CT> in '<group name>' is not usable (<reason>). Correct it in Recording Details." |
| `conflict` | "Phases use groups with different <VT/CT> ratios (<groups>). Align them in Recording Details." |
| `CHANNEL_UNRESOLVED` | "Role <Va/Ia/…> did not resolve to a channel in this Engineering Context." |

Each message names the missing item and the group; each links to Recording Details.

## 6. Acceptance checks

- Static tests: no `wwImpedanceVtPrimaryInput` / `wwDistanceVtPrimaryInput` style editor in Recording mode; `wwNavigateToRdForGroup` is the only correction path; Manual-mode inputs unchanged; no use of `vt_effective_*`.
- Browser: KPDN1 with nominal-only VT → VT message + Configure button + Related Waveforms visible; after Edit → Save of VT → read-only VT/CT shown, calculation runs with no typing and matches the API; mixed/unknown sides never convert silently; Distance identical; Overcurrent, PU, Manual mode unchanged.

## 7. Ownership

**Update (owner clarification, 2026-11-21):** Codex's redesign is limited to the Waveform Analysis page, so Claude implements the Impedance Locus and Distance Protection change itself, in a separate commit from the backend work. The change is confined to the Impedance/Distance sections of `frontend/index.html` (markup host, one shared `wwCtVt*` helper block, the two `*BasisParams` functions, locus signatures, settings/reset/wiring) and adds `backend/tests/test_frontend_d5a_ctvt_authority.py`. It does not touch the Waveform Analysis page or any Codex-owned function. Because both agents may edit `frontend/index.html`, coordinate at the Git-file level: rebase/merge on the shared branch rather than overwriting. Overcurrent has the same per-panel CT pattern and is a separate follow-up after Impedance/Distance UAT.
