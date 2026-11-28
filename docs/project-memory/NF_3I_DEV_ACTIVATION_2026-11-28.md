# NF-3I — Nominal Frequency feature activation for DEV: implementation record

Date: 2026-11-28. Status: **implemented and verified locally; awaiting owner review and interactive owner UAT.** Not pushed, merged or deployed. PROD is untouched and out of scope.

## 1. Decisions applied

Recorded in [DEC-217 Amendment 2](DECISIONS.md#dec-217--a-recording-has-one-nominal-frequency-decided-by-one-shared-authority-nf-001--nf-1) (owner, 2026-11-28): NF-3F/G/H accepted (functional `194d8ba`) with the browser result's documented qualifications; the NF-3C native-oscillation behaviour **retained** (recording frequency is not propagated to native members; limitation recorded); the `invalid_nominal_frequency` refusal for Power, the sampling threshold, the agreement arithmetic, F-1 and O-3 unchanged; **O-12 approved** (documented browser failures keep their qualifications, no unexplained regression, **interactive owner UAT mandatory, activation restricted to DEV, PROD out of scope**). The 2.5 % instantaneous-error ceiling remains fixture-specific test evidence. Applied: AGENTS.md, DEC-217, DEC-218. No mathematical engine, RMS code, WUI or Per-Unit code was changed; F-1 and the RMS Waveform Toggle were not touched.

## 2. The actual gate changes

| Gate | Before | After (NF-3I) |
|---|---|---|
| Backend server gate (`NOMINAL_FREQUENCY_MANUAL_OVERRIDE_ENABLED`, O-1) | Accepted only for a non-deployed process; **refused in any deployed build, including DEV** (`config.py`) | Accepted **only when `ENVIRONMENT=development`** (a local process, a test process, the DEV deployment); refused at start for any other environment, PROD included. Default unchanged: closed |
| Frontend flag `featureFlags.nominalFrequencyOverride` | The container entrypoint could never emit it | The entrypoint emits it **only** when the same variable is an explicit affirmative (`1`, `true`, `yes`, case- and space-insensitive) **and** `ENVIRONMENT=development`; any other environment that carries the variable fails the container start. Unset or anything else: no flag, the original read-only row |
| Frontend constant `WW_NF_CONSUMERS_MIGRATED` | `false` ("Preview: calculations do not use this setting yet.") | `true`; the preview line is replaced, in every state, by: *Used by this recording's frequency-based calculations and analyses (RMS, power, phasor, overcurrent, compliance, event detection and RMS-based oscillation). Not used by automatic per-unit base evidence or by the nominal comparison for natively analysed oscillation signals.* (the O-3 exclusion and the NF-3C limitation). The unusable-recording hint now reads "choose Manual to enter a value for frequency-based calculations". The preview text survives only as the helper's unmigrated branch |

Unchanged and verified: the 50 Hz fallback (a recording that declares nothing is Auto = 50 Hz, flagged assumed); recording samples and imported metadata are never modified; provenance, revision and staleness; the existing layout and styling (the new note reuses the existing small-text rule `.ww-rd-nf-detail, .ww-rd-nf-preview`); no new control.

## 3. DEV configuration changes

| File | Change |
|---|---|
| `compose.dev.yaml` | `NOMINAL_FREQUENCY_MANUAL_OVERRIDE_ENABLED: "1"` on the **backend** (the enforcement) and the **frontend** (shows the control). One variable name, two services |
| `backend/app/config.py` | refusal rule: `environment != "development"` (was: deployed build) |
| `frontend/docker-entrypoint.d/10-powerwave-config.sh` | parses the variable, refuses a non-development environment, emits the page flag |
| `frontend/index.html` | the constant, the scope statement helper, one CSS selector |

**Not changed:** `compose.yaml`, `compose.prod.yaml`, `.env.example`, the workflows, `scripts/deploy.sh`, the Dockerfiles, the checked-in `frontend/config.js`. A static test now pins that exactly two files mention the variable (the DEV overlay and the entrypoint) and that no base, PROD, template, workflow, script or Dockerfile does.

## 4. Verification

| Check | Result |
|---|---|
| New acceptance module `test_nf3i_activation.py` (the UAT scenarios over HTTP, the app built through `load_settings` from the DEV overlay's environment) | 20 passed |
| Updated gate, entrypoint, compose and config tests (`test_nf3b_server_side_release_gate`, `test_frontend_nf2_release_gate`, `test_frontend_entrypoint` with its new flag tests, `test_compose_config`, `test_config`) | 190 passed |
| Mutations (the old "deployed" refusal; production not refused; staging not refused; gate defaults open; DEV overlay missing either service; PROD overlay carrying the variable; entrypoint not refusing; entrypoint emitting unconditionally; frontend flag closed; scope statement missing the O-3 exclusion) | **11 / 11 killed**, files restored |
| Browser, focused (Recording Details, per-unit, calculated channels, compliance, phasor, overcurrent, oscillation, NF-2, NF-3C labels, NF-3E staleness, text spacing), **UI flag off** (every non-DEV environment) | 597 passed, 1 skipped (the gated screenshot spec), 0 failed |
| Same set, **UI flag on** (DEV) | 596 passed, 1 skipped, 1 failed: only the NF-2 test "off by default: the original read-only row", which asserts the default config has no flag and fails by construction when the page is served WITH it (it passes in the flag-off run). No other failure: every per-unit, calculated-channel, compliance and Recording Details spec passes with the control visible |
| **Full backend, NF-3I tree** | **16,948 passed, 410 skipped, 0 failed** (35 min; the `194d8ba` baseline was 16,894 / 410 / 0; the 54 additional passes are the new NF-3I tests) |

The NF-2 browser spec was updated in the same commit: the "preview" assertions became assertions of the scope statement in every state (declared, assumed, unusable, editing, Manual) and of the O-3 wording.

**UAT scenarios and the test that proves each** (all in `test_nf3i_activation.py` unless noted): declared 50 and 60 Hz, assumed 50 Hz, unusable (`TestRecordingStates`); Auto, Manual, a Manual override that a consumer reads, return to Auto, out-of-range refusal (`TestAutoManualAndReturnToAuto`); staleness of an RMS and a power channel (`TestStalenessOfExistingCalculatedChannels`); Power across compatible, incompatible and reconciled recordings, 400 `nominal_frequency_mixed` with nothing written (`TestPowerAcrossRecordings`); per-unit configuration and the waveform unchanged by a frequency change, samples and imported metadata unchanged (`TestExistingFunctionalityIsPreserved`); the safe default without the variable and the PROD refusal (`TestTheDevConfigurationStartsAndOpensTheFeature`); the entrypoint behaviour (`test_frontend_entrypoint.py`).

**Why the full browser regression was not repeated:** the browser result on `194d8ba` (1,883 passed, 8 failed, 9 skipped) covers everything outside the changed code, and `index.html` differs from it only inside the Nominal Frequency block (a constant, one helper, two call sites, one CSS selector, a comment), which is reachable only behind the flag. The focused set above exercises that block in both flag states and every surface it neighbours; the full backend regression covers the static scanners of `index.html` and the settings change.

## 5. Final checks and DEV deployment readiness

The full backend regression passed (section 4). The NF-3F/G/H full regressions (backend 16,894, browser 1,883 / 8 / 9, BEN reference 1,015, 23 of 23 mutations) are reused unchanged for everything outside the changed code.

DEV picks the change up through the existing path: merge to `main` -> CI (including the Compose-overlay validation, unchanged) -> automatic `deploy-dev.yml`, which deploys `compose.yaml` + `compose.dev.yaml` with `ENVIRONMENT=development` on both services, so the new rule accepts the configuration; the frontend container regenerates `config.js` with the flag. PROD's overlay never sets the variable and both services would refuse it. Nothing was pushed, merged or deployed by this work.

## 6. Owner UAT checklist (DEV, interactive; mandatory under O-12)

1. Open Recording Details of a **declared 50 Hz** and a **declared 60 Hz** recording: the value, "Auto" selected, no status label; the scope statement under the row (including "Not used by automatic per-unit base evidence").
2. A recording with an **unreadable or missing `lf`** (CSV, `lf` text): "Assumed default" 50 Hz; a recording with `lf = 0`: the unusable notice and "choose Manual to enter a value for frequency-based calculations".
3. **Manual**: enter 60 on a 50 Hz recording; Apply; the value, "Manual", the Auto value shown in the detail; **Edit**; **return to Auto** restores the declared value. Out-of-range (0.5, 1001) is refused.
4. With RMS **and a power channel** already calculated, change the frequency: both show the stale marker and the one-line advisory with the reason; their values are unchanged; a new calculation on a stale channel is refused with the actionable message; returning the frequency clears it.
5. **Power from two recordings with different frequencies**: refused with the "different nominal frequencies" message naming each input; set the same frequency on both and it is accepted.
6. A power channel created on a **60 Hz** recording stores a frequency of 60 Hz (not the former fixed 50 Hz) and its steady-state value agrees with P = ½·V·I·cos φ from the recording's own peak values (the §5.5 check, done by hand on a clean load); a phasor analysis and the RMS builder default follow the effective value.
7. **Per-unit** (voltage base, PU display, cursors) and the **waveform** are unchanged by any of the above.
8. Confirm the scope statement wording is acceptable (it is the one piece of new text).

## 7. Remaining limitations

1. **Native oscillation members** do not carry the recording's frequency (NF-3C behaviour retained by decision); stated in the page text. `nominal_frequency_mixed` evidence arises only for RMS-magnitude members.
2. **Auto Base evidence (C-17)** is excluded (O-3); stated in the page text.
3. The documented browser qualifications carry unchanged (six CSV/Excel specs; the intermittent legend-visibility tests).
4. In-memory registry: a Manual value is cleared by a backend restart (back to Auto), by design since NF-1.
5. DEV only: PROD has neither gate and refuses the variable; releasing it to PROD would be a separate owner decision and a separate change.

## 8. Governance compliance (DEC-218)

Documents consulted: AGENTS.md, CLAUDE.md, the project-memory README, DEC-217 (Amendments 1 and 2), DEC-218/219, NF-3A section 8 and 10, NF-2 and NF-3B gate records, the NF-3F/G/H record, `compose*.yaml`, the workflows and `scripts/deploy.sh`. Decisions preserved: DEC-217, O-1, O-3, DEC-219, the PU authorities, the NF-3E staleness policy. The only amendment is DEC-217 Amendment 2 (the owner's instructions). No unresolved policy conflict. Scope deviation: none.
