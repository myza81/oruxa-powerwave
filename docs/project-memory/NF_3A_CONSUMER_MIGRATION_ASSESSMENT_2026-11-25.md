# NF-3A — Nominal-frequency consumer migration: engineering contract (assessment only)

**Date:** 2026-11-25 · **Decision base:** [DEC-217](DECISIONS.md) · **Branch:** `assessment/nf-3a-consumer-migration`, worktree `.local-data/nf-3a`
**Baseline:** `2adf9db` (NF-2 closure) on `e3296a3` (NF-2 visual acceptance preparation) on the verified NF-1 candidate `0c4abba`, on the accepted R0/R1A integration `0aa3562`, on the published DEV `e9c621c`. All ancestry is local and unpublished.
**Status:** investigation and design only. **No production code, test, API or UI-gate change.** Not pushed, merged or deployed. NF-3B is not started. Owner review is required before any slice begins.

Earlier design input: `NOMINAL_FREQUENCY_SSOT_NF001_ASSESSMENT.md` (design-reports directory, outside the repository). Everything it says about consumers was re-checked against the current code; where this document differs, it says so (section 12).

---

## 1. Summary

1. **The inventory has 24 entries** (section 3). Nine direct `metadata.nominal_frequency` readers are frozen by the NF-1 tripwire; the others are indirect (analysis functions reached through them), hard-coded 50 Hz paths, a request parameter, and frontend displays. **18 entries require migration** (several only through another entry), **3 are governed by a different, justified authority**, **2 are constants unrelated to the recording's nominal frequency**, and **1 is deferred with justification** (Auto Base, PU-coupled).
2. **Auto mode can be made behaviour-neutral** for every consumer that reads a valid declared value today: the resolver returns the same number. Each slice must prove that with frozen golden outputs *before* the consumer is touched.
3. **Four existing defects were found** (section 11): three measured or verified by execution, one by code inspection. None is caused by NF-1/NF-2; NF-3 must not silently carry them forward, and each needs a decision because fixing it changes behaviour:
   * **Power calculated channels ignore the recording's frequency** and always use a 50 Hz window. On a 60 Hz recording that gives **P −11.8 %, Q −13.2 %, with 37 % peak-to-peak ripple** (measured).
   * **The RMS-eligibility endpoint returns HTTP 500** for a request frequency of 0 (verified through HTTP).
   * **The phasor family, overcurrent, compliance measurement and Auto Base pass the *declared* frequency to the engine unvalidated**; the raw engine functions raise `ZeroDivisionError`/`ValueError` or return silently wrong arrays for 0, negative, NaN and infinite values (measured at engine level; service-level exposure is by code inspection, not exercised through HTTP).
   * **Oscillation cross-signal takes the first member's frequency** (or a 50 Hz constant), which DEC-217 forbids.
4. **A value valid under NF-1 is not valid for every algorithm.** Measured example: the waveform-form detector returns `uncertain` for every nominal frequency below 3 Hz, because its analysis slice is capped at 1 s while it needs 3 cycles. Per-algorithm sampling and duration envelopes are in section 4.4.
5. **A calculated channel is stored, immutable and eager.** Frequency staleness can therefore be *derived at read time* by comparing the frequency recorded in a channel's parameters with the recording's current effective value, with no state to keep in step. The compliance-readiness service already works this way.
6. **There is a release-safety gap in the current design:** the NF-1 `PUT` endpoint is live on every deployment, and only the *UI* is gated. Once consumers honour the override, anyone with API access can change calculations with no UI trace, and turning the UI gate back off would leave a hidden effect. Decision **O-1** recommends a server-side enforcement setting.
7. **Recommended first implementation slice: NF-3B**, "frozen baselines and consumer accessor, no behaviour change" (section 9.1), because it makes every later slice provable and changes no output.

Twelve genuine owner decisions (O-1 to O-12) are listed in section 13; none was silently resolved here.

## 2. Method and evidence

* **Inventory:** every `nominal_frequency`/`nominalFrequency`/`reference_frequency` reference in `backend/app` (307 occurrences in 42 files) and `frontend/index.html` (46) was read; then a separate search for hard-coded 50/60 constants, default arguments, fundamental/window/cycle constants, and engine entry points (`evaluate_rms`, `compute_sliding_phasor`, `estimate_phasor`, `estimate_trailing_rms_at_time`, `classify_waveform_form`, `detect_event_onset`, `extract_waveform_evidence`). The NF-1 tripwire (`backend/tests/test_nf1_nominal_frequency_authority.py:454`, `ALLOWED_DIRECT_READERS`) was used as a cross-check, not as the definition of the inventory.
* **Numerical probes** (read-only calls of the existing code with exactly known signals): `scripts/diagnostics/nf3a_numerical_probes.py` → `evidence/nf-3a-2026-11-25/numerical_probes.json`.
* **HTTP probe** (existing API through `TestClient`, 50/60/0 Hz recordings): `scripts/diagnostics/nf3a_http_probe.py` → `evidence/nf-3a-2026-11-25/http_probe.json`.
* **Not done, stated plainly:** the phasor family, overcurrent and compliance paths were *not* driven end to end through HTTP with an unusable recording (they need an Engineering Context and Measurement Group set-up); their exposure is established from the call sites plus the engine-level probe. NF-3D must start with a failing test for each. No browser run was made in this assessment.
* **Line references** are to `2adf9db`. `frontend/index.html` line numbers move with every edit; function names are given with them.

## 3. Consumer inventory

Classes: **M** = requires migration to NF-1 · **D** = already governed by a different, justified authority · **K** = constant intentionally unrelated to the recording's nominal frequency · **X** = deferred, with justification. "Direct" = counted by the NF-1 tripwire.

### 3.1 Backend: readers of the imported value

| ID | Where | What it does with the frequency | Class |
|---|---|---|---|
| C-01 | `services/phasor_analysis_service.py:215,245` (`_fetch_role_candidate`), used at `:375,638,1037` | Each resolved role carries `active.metadata.nominal_frequency` (calculated channels: the reference source's). **Direct ×2.** The three selection sites (`compute_phasor_analysis`, `prepare_phasor_diagram`, `check_phasor_diagram_readiness`) take an explicit `reference_frequency_hz_override`, else require all roles' *declared* values to agree (`math.isclose`), else `reference_frequency_conflict`. The declared value is **not validated** before `1.0 / reference_frequency_hz` (`:418,708`) or the detector (`:283`) | **M** |
| C-02 | `services/overcurrent_analysis_service.py:134,145` (`_fetch_current_candidate`), used at `:303,492` | Same pattern, one role. **Direct ×2.** Override validated at `:295,485`; candidate value not validated before `1.0 / reference_frequency_hz` (`:334`) | **M** |
| C-03 | `services/synchronization_service.py:522,529` (`detect_event_onset` view) | Event-onset detection and the `nominal_frequency_hz` echoed in the view. **Direct ×2.** The domain function validates (`domain/event_detection.py:217`) and returns a typed refusal | **M** |
| C-04 | `services/compliance_readiness_service.py:240-253` (`_nominal_frequency_for`), `:302-326`, `:754` | Validates; `None` blocks the RMS preparation step; a valid value is carried into the proposed step and into the RMS channel it later creates. Identity: `find_equivalent_rms` (`:210-223`) reuses an RMS channel only when `parameters["nominal_frequency_hz"]` equals the needed value. **Direct ×1** | **M** |
| C-05 | `services/compliance_measurement_service.py:298` | Passes the declared value to `classify_waveform_form`. **Direct ×1. Not validated** | **M** |
| C-06 | `services/oscillation_representation_service.py:86-95,120,137-141,190-191` | `_nominal_frequency()` reads the declared value and labels its origin from the provenance flag; validates; derives the RMS magnitude and the roll-off bandwidth from it. **Direct ×1.** The best-behaved consumer today | **M** |
| C-07 | `services/oscillation_spectrum_service.py:274-330,425`; `services/oscillation_cross_signal_service.py:163-164`; `services/oscillation_damping_service.py:33` | Indirect: the representation's frequency, origin and `nominal_frequency_assumed` flag are carried through; the roll-off warning and `rms_nominal_frequency_hz=nominal` (`:425`) move with it | **M** (labels and origin mapping only) |
| C-08 | `domain/oscillation_classification.py:49,259-261,398-399` | Takes the **first** member that has a value (`next(...)`), else the constant `ASSUMED_NOMINAL_FREQUENCY_HZ = 50.0`, for the sub-synchronous comparison | **M** (multi-recording rule, section 7) |
| C-09 | `services/line_to_line_voltage_service.py:250-255` | Calls `check_phasor_diagram_readiness(... reference_frequency_hz_override=None ...)`: reaches C-01 | **M** (through C-01) |
| C-10 | `services/impedance_analysis_service.py:88-172`, `distance_protection_analysis_service.py:84-195`, `sequence_components_analysis_service.py:113-146` | Pass `reference_frequency_hz_override` into `prepare_phasor_diagram`; echo `reference_frequency_hz`/`window_seconds`. Protection calculations reach the frequency only through C-01 | **M** (through C-01) |

### 3.2 Backend: hard-coded 50 Hz and calculation parameters

| ID | Where | What | Class |
|---|---|---|---|
| C-11 | `services/calculated_channel_service.py:1071,1075` (single-phase power), `:1290,1294` (three-phase power) | `rms_recording_long_enough(time, 50.0)` / `rms_sampling_dense_enough(time, 50.0)`: the prerequisite gates assume 50 Hz | **M** |
| C-12 | `domain/calculated_channel.py:958-998` (`evaluate_power_channel`, default `nominal_frequency_hz=50.0` at `:965`) and `:1016-1076` (`evaluate_three_phase_power_channel`, default at `:1031`); called without a frequency at `calculated_channel_service.py:1493,1502` | **The power channel's DFT window is always 1/50 s**, whatever the recording | **M** (numerical change, **O-2**) |
| C-13 | `services/calculated_channel_service.py:1546-1555` | Stores `"nominal_frequency_hz": 50.0` in the parameters of power channels, a fact about the code, not about the recording | **M** |
| C-14 | `services/calculated_channel_service.py:1373-1403,1469,1531` (`OP_RMS`) | The explicit request parameter `parameters.nominal_frequency_hz`: validated (`nominal_frequency_valid`), used for eligibility, prerequisites and the window, **stored** in the channel (`:1531`) | **D**: an explicit calculation parameter (DEC-048) that stays. Its *default* comes from the frontend (C-22), which is the migration |
| C-15 | `api/v1/calculated_channels.py:505-535`; `schemas/calculated_channel.py:139-146` (`RmsEligibilityRequest.nominal_frequency_hz: float`) | Stateless eligibility pre-check; the request frequency goes **unvalidated** into `check_rms_eligibility` → detector | **M** (defect, section 11) |
| C-16 | `domain/sliding_phasor.py:166` (default `reference_frequency_hz=50.0`) and `domain/waveform_evidence.py:343` (default `nominal_frequency_hz=50.0`) | Default arguments. A caller that omits the frequency silently gets 50 Hz | **M** (remove the silent default once no caller relies on it; section 9, NF-3H) |
| C-17 | `services/auto_base_service.py:221-228` → `domain/waveform_evidence.py:341` | `extract_waveform_evidence(raw_waveforms)` is called **without** a frequency: the evidence RMS window is `round(sample_rate / 50)` samples. On a 60 Hz recording that is 1.2 cycles: **12.6 % peak-to-peak ripple in the evidence RMS** (measured, P7) | **X**: voltage-group Auto Base evidence belongs to the PU workstream (PU-MIG), which is outside NF-3. Deferral needs owner confirmation (**O-3**) |

### 3.3 Backend: importers, validators and constants that are not consumers

| ID | Where | Class |
|---|---|---|
| C-18 | `providers/comtrade.py:75,429-432,845-854,895-912` (default 50.0 on an unparseable `lf`, flagged `nominal_frequency_assumed`); `services/preparation_conversion_service.py:181-190,495,551,563` (CSV/Excel default, flagged); `providers/ben/provider.py:42-84`, `providers/ben/normalize.py:86-154`, `services/import_service.py:88-228,343`, `api/v1/sources.py:183-226` (BEN upload value) | **D**: producers of the *imported* value and its provenance. NF-1 already treats them as Auto input; unchanged |
| C-19 | `domain/calculated_channel.py:88-91,709-720` (`MIN/MAX_NOMINAL_FREQUENCY_HZ = 1/1000`, `nominal_frequency_valid`) | **D**: the single validity predicate, reused by NF-1 (`valid_nominal_frequency`) |
| C-20 | `domain/calculated_channel.py:526-700` (ROCOF) | **K**: the input is a *measured* frequency channel in Hz; windows are in ms |
| C-21 | `domain/coherence.py:152-273`, `domain/mode_shape.py:56-184`, `domain/damping_estimation.py:248-525` (`f0`), `domain/oscillation_peaks.py:323-412` | **K**: target and detected component frequencies, not the nominal. (`rms_nominal_frequency_hz` in `oscillation_peaks.py` is passed from C-07 and moves with it) |

### 3.4 Frontend

| ID | Where (`frontend/index.html`) | What | Class |
|---|---|---|---|
| C-22 | `:29071-29075` (inventory cache `nominalFrequency: data.source.nominal_frequency`), `:42160-42182` (`wwCcResolveNominalFrequencyAuthority`), `:43946-43994`, `:43171-43185`, `:45127`, `:42058-42068,42135,42441,42892,42953,42964` | The RMS builder's default: the cached **imported** value when `> 0` (note: `> 0`, not the 1–1000 predicate), else a 50/60 dropdown that defaults to `"50"`. The cache is a snapshot taken when channels load | **M** (default source, cache refresh, unusable handling) |
| C-23 | `:63386,63937,64147` (oscillation panels) | Labels the origin as "assumed default" or "from the recording": a binary mapping. The new `manual` and `import_supplied` origins would be shown as "from the recording" | **M** (label mapping) |
| C-24 | `:22925` (Technical facts card: `source.nominal_frequency + " Hz"`), `:36667` (Recording Info row: gated by NF-2), `:42360,44070,4061` (a calculated channel's stored `nominal_frequency_hz` in lists and generated names), `:55476-55477` (reason-code texts) | Displays. The Technical facts card shows the **imported** value and is *not* under the NF-2 gate, so it would disagree with a Manual value (**O-11**). Stored-parameter displays are correct as history | **M** (the facts card); **D** (stored parameters) |

**Count by class (24 entries):** **M = 18** (C-01 to C-13, C-15, C-16, C-22, C-23, C-24; C-24 is split, its stored-parameter displays being **D**); **D = 3** (C-14, C-18, C-19); **K = 2** (C-20, C-21); **X = 1** (C-17). The Auto Base deferral is the only deferral. C-07, C-09, C-10 and C-13 migrate only through another entry.

### 3.5 Cross-check against the NF-1 tripwire

`ALLOWED_DIRECT_READERS` freezes 11 `metadata.nominal_frequency` reads: `compliance_measurement_service` 1, `compliance_readiness_service` 1, `import_service` 1, `nominal_frequency_service` 1, `oscillation_representation_service` 1, `overcurrent_analysis_service` 2, `phasor_analysis_service` 2, `synchronization_service` 2. Nine are consumers (C-01 to C-06); the tripwire is **blind to** C-11 to C-17 (they never read the metadata: they hard-code 50), to C-22 to C-24 (frontend), and to C-08 (it reads a derived dict). That is why the inventory above is wider than the tripwire, and why section 9 adds a second guard.

## 4. Current-to-target authority matrix and engineering behaviour

**Target path for every backend consumer** (one rule, section 6.1): resolve once per request through the NF-1 accessor for the recording that *grounds the channel* (a calculated channel resolves through its `reference_source_id`), receive a typed outcome, and never call an engine function with a value the outcome does not mark usable.

### 4.1 Matrix

Columns: **Valid declared** and **Assumed 50** = Auto result (identical to today by construction). **Manual** = the stored valid value. **Unusable** = declared but invalid, no Manual (target behaviour).

| ID | Today's source | Valid declared | Assumed 50 | Manual | Unusable (no Manual) |
|---|---|---|---|---|---|
| C-01 phasor family | declared per role; override | same value; agree-or-override rule kept | 50, origin `assumed_default` | the Manual value of **each** role's recording; the agree-or-override rule is applied to the *effective* values | typed `needs_configuration` with the existing `invalid_reference_frequency` code (**O-5**); never reaches `1/f` |
| C-02 overcurrent | declared (one role); override | same | 50 | Manual of that recording | as C-01 |
| C-03 event detection | declared | same | 50 | Manual | existing typed refusal `invalid_nominal_frequency`; the echoed `nominal_frequency_hz` keeps its type (**O-7**) |
| C-04 compliance readiness | declared; `None` if invalid | same; step carries it | 50 | Manual; a changed value makes `find_equivalent_rms` miss, so a **new** RMS step is proposed (natural versioning) | `blocked` step, wording changed from "unknown" to "declared unusable" |
| C-05 compliance measurement | declared, unvalidated | same | 50 | Manual | `None` ("do not guess"), never an exception |
| C-06/07 oscillation | declared + origin | same, origin `recording_metadata` | 50, `assumed_default` | Manual, origin `manual` (new label, C-23) | existing `unavailable("invalid_nominal_frequency")` |
| C-08 cross-signal | first member, else 50 | all members agree: that value | assumed flag as today | members agree: that value | members differ: limiting evidence `nominal_frequency_mixed`, no value picked (**O-9**) |
| C-11–13 power | hard-coded 50 | recording's value (**numerical change for non-50 recordings**, **O-2**) | 50 (unchanged) | Manual | typed refusal with the existing 400 `invalid_nominal_frequency`; V and I must agree (section 7) |
| C-14 RMS parameter | request parameter | unchanged: an explicit parameter | | | unchanged (already validated) |
| C-15 eligibility endpoint | request body, unvalidated | validate the body value (400 `invalid_nominal_frequency`) | | | HTTP 500 today → 400 (**O-10**) |
| C-22 builder | cached imported value | default = effective value from the NF-1 `GET` | default 50, shown as assumed | default = Manual | no preselected frequency; explicit choice required (**O-8**) |

### 4.2 What changing the frequency does mathematically

| Algorithm | Role of f | Effect of a change from f₀ to f₁ |
|---|---|---|
| Trailing RMS (`evaluate_rms`, `calculated_channel.py:392`) | window `1/f` seconds, half-open `(t−1/f, t]` | window length changes; **steady-state error and ripple grow quickly when f₁ ≠ the signal's frequency** (section 5, P1) |
| Sliding phasor (`sliding_phasor.py`), single-point phasor (`phasor.py:194`) | DFT reference frequency **and** window `1/f` | mismatched f gives a magnitude bias **and** a rotating angle (P2): the angle sweeps 360° over the record |
| Selected-time RMS (`overcurrent.py:345`) | window `1/f` | as RMS |
| Waveform-form detector (`rms_detector.py:365`) | single-bin DFT at f, periodicity lag, `3/f` minimum duration, `5/f` windows, 1 s slice cap | a wrong f can turn `likely_instantaneous` into `uncertain` (P4), which blocks RMS/phasor eligibility |
| Event detection (`event_detection.py:187`) | RMS window, baseline `max(3/f, 0.25·duration)`, persistence and merge gaps in cycles | detection thresholds move in time |
| Oscillation representation (`oscillation_representation.py:82-150`) | RMS window and the roll-off bandwidth `0.4429·f` | the analysable modulation band moves |
| Waveform evidence (`waveform_evidence.py:197`) | window `round(fs/f)` samples, `≥ 3` cycles | see C-17 |

### 4.3 Physical calibration, side conversion, PU

Frequency enters none of: sample values, calibration authority, scale factors, CT/VT ratios, Measurement Side conversion, or the PU division. A frequency change affects PU or side-converted output only **through** a channel whose *values* are frequency-dependent (an RMS or power channel): the conversion of those values is unchanged. The oracle (section 5.3) checks this as an identity.

### 4.4 Algorithm envelopes versus the NF-1 range (1–1000 Hz)

Measured by the probes and read from the constants (`calculated_channel.py:95`, `overcurrent.py:319`, `phasor.py:125`, `rms_detector.py:70-106`):

| Nominal f | RMS (≥ 4 spc) min fs | Overcurrent (≥ 4 spc) | Phasor (≥ 8 spc) | Window / min record | Detector |
|---|---|---|---|---|---|
| 1 Hz | 4 Hz | 4 Hz | 8 Hz | 1 s | **`uncertain` always** (needs 3 s, slice capped at 1 s) |
| 2 Hz | 8 Hz | 8 Hz | 16 Hz | 0.5 s | **`uncertain` always** |
| 3–5 Hz | 12–20 Hz | 12–20 Hz | 24–40 Hz | 0.33–0.2 s | works |
| 16.7 / 25 Hz | 67 / 100 Hz | 67 / 100 Hz | 134 / 200 Hz | 60 / 40 ms | works |
| 50 Hz | 200 Hz | 200 Hz | 400 Hz | 20 ms | works |
| 60 Hz | 240 Hz | 240 Hz | 480 Hz | 16.67 ms | works |
| 400 Hz | 1.6 kHz | 1.6 kHz | 3.2 kHz | 2.5 ms | works |
| 1000 Hz | 4 kHz | 4 kHz | **8 kHz** | 1 ms | works |

Consequences the migration must keep: a 5 kHz recording at a Manual 1000 Hz passes the RMS gate (5 spc) but **must be refused by the phasor family** (`insufficient_sampling_density`, already returned by the estimator at `phasor.py:248`); a Manual 1 or 2 Hz makes the detector useless, so RMS creation will always demand the override for such a value. These are existing per-algorithm refusals, not new rules; the NF-1 range stays as it is (decision D2 of the earlier assessment is not reopened). **No consumer supports "the full NF-1 range" unconditionally**; each keeps its own gate.

## 5. Numerical acceptance oracles

All values below were **measured** with `scripts/diagnostics/nf3a_numerical_probes.py` on `2adf9db` (output in `evidence/nf-3a-2026-11-25/numerical_probes.json`). Signal: `100·cos(2πf_sig·t + φ)`, expected RMS `70.7107`. "spc" = samples per cycle at the nominal frequency. Steady state = after two cycles.

### 5.1 Frequency-selection correctness (the property NF-3 must prove)

For every migrated consumer and for each of {50 declared, 60 declared, assumed 50, Manual 60 on a 50 Hz recording, Manual 50 on a 60 Hz recording}: **the consumer's output is bit-for-bit the output of the unmodified engine called directly with the expected frequency**. This is independent of numerical accuracy and catches a consumer that reads the wrong source, an ignored Manual value, or a swapped recording. For Auto valid, it must equal the *frozen pre-migration output* exactly (NF-3B).

### 5.2 Numerical algorithm correctness (kernel versus closed form)

Matched frequency (signal = nominal), 0.5 s records:

| Case | fs | spc | RMS mean error | RMS ripple p-p | Phasor mag. mean error | Phasor ripple p-p | Phasor angle p-p |
|---|---|---|---|---|---|---|---|
| 50 Hz, integer spc | 5000 | 100 | 0 | 0 | 0 | 0 | 0° |
| 50 Hz, integer spc | 4800 | 96 | 0 | 0 | 0 | 0 | 0° |
| **50 Hz, non-integer spc** | **4096** | **81.92** | 2·10⁻⁵ % | **0.098 %** | 4·10⁻⁵ % | **0.195 %** | 0.112° |
| 60 Hz, non-integer spc | 5000 | 83.33 | −1.6·10⁻⁴ % | 0.402 % | 3.8·10⁻⁴ % | 0.804 % | 0.461° |
| **60 Hz, non-integer spc** | **4096** | **68.27** | −1.5·10⁻⁴ % | **0.393 %** | 3.7·10⁻⁴ % | **0.785 %** | 0.450° |
| 60 Hz, integer spc | 4800 | 80 | 0 | 0 | 0 | 0 | 0° |

**Proposed tolerances** (≈1.3× the observed worst case, to be confirmed by the owner as part of the contract): integer spc, relative error ≤ 10⁻⁹; non-integer spc at 50 Hz, RMS ripple ≤ 0.13 % and phasor ripple ≤ 0.26 %; at 60 Hz, RMS ripple ≤ 0.52 % and phasor ripple ≤ 1.05 %, angle ripple ≤ 0.6°. A *regression* in these numbers means the migration changed the kernel, which NF-3 must not do.

### 5.3 Physical-calibration, side and PU identities

* Sample arrays, `calibration_authority`, scale factors and `SourceMetadata` hash identical before and after a Manual set, change and clear (extends the NF-1 hash test to the consumer paths).
* PU and side-converted values of a frequency-independent channel are bit-identical across a Manual change. For an RMS channel, `PU(RMS_f₁) = RMS_f₁ / base` exactly: the PU step is the same division on the new values.

### 5.4 Wrong or mismatched frequency (the cost of a wrong Manual value)

| Signal | Nominal used | RMS mean error | RMS ripple p-p | Phasor mag. mean error | Phasor angle p-p |
|---|---|---|---|---|---|
| 50 Hz | 60 Hz | −0.21 % | 16.9 % | −4.3 % | 360° (rotates) |
| 60 Hz | 50 Hz | −0.10 % | 12.6 % | −6.3 % | 359° (rotates) |
| 60 Hz, single-point phasor | 50 Hz | | | +1.99 % | |
| 50 Hz, single-point phasor | 60 Hz | | | +0.58 % | |

This is why a Manual value must carry its origin into results (**O-6**): the system cannot tell a wrong value from a right one.

### 5.5 Power channels (C-11 to C-13), `P = 43.301 MW`, `Q = 25.0 Mvar` expected (V 100 kV pk, I 1 kA pk, 30° lag)

| Signal | Window f (what the code does) | P mean error | P ripple p-p | Q mean error |
|---|---|---|---|---|
| 50 Hz | 50 | 0 | 0 | 0 |
| **60 Hz** | **50 (today)** | **−11.80 %** | **36.8 %** | **−13.21 %** |
| 60 Hz | 60 (target) | 0 (4800 Hz); +0.0013 to +0.0014 % (5000 / 4096 Hz) | 0 (4800 Hz); 1.8 to 1.9 % (5000 / 4096 Hz) | −0.0015 to −0.0016 % |
| 50 Hz at 4096 Hz | 50 | +0.0002 % | 0.45 % | −0.0001 % |

The "60 Hz, window 50" row is exactly what a 60 Hz recording receives today. **Acceptance for NF-3F:** the 60 Hz rows reach the "target" row within the §5.2 tolerance; the 50 Hz rows are bit-identical to the frozen pre-migration values.

### 5.6 Detector (C-05, C-15 and every eligibility check)

A 60 Hz signal classified with nominal 50 Hz gives `uncertain`; with 60 Hz, `likely_instantaneous`. A 50 Hz signal with nominal 60 Hz is still `likely_instantaneous`. A magnitude trace stays `likely_magnitude_or_rms` at either. Consequence: **a 60 Hz recording from CSV or BEN (which assume 50 Hz) cannot create an RMS channel today without an override; the Manual value is what fixes that**, and the oracle for the migration is exactly this flip.

### 5.7 Waveform evidence (C-17), recorded for the PU decision

| fs | Signal | Window used | Cycles in window | Evidence-RMS ripple p-p |
|---|---|---|---|---|
| 4800 / 5000 | 50 Hz | 96 / 100 | 1.0 | 0 |
| 4800 / 5000 | 60 Hz | 96 / 100 | **1.2** | **12.6 %** |
| 4096 | 50 Hz | 82 | 1.001 | 0.098 % |
| 4096 | 60 Hz | 82 | 1.201 | 12.7 % |

## 6. Invalid and unavailable frequency

### 6.1 Rules (target)

1. **Resolve once per request**, at the service boundary, into a typed outcome: `usable(hz, origin, revision)` or `unusable(reason, imported_text)`. The accessor already exists (`nominal_frequency_service.effective_nominal_frequency`).
2. **An engine function is never called with a recording-derived value that is not usable.** The probe shows why the engines cannot be trusted to refuse: for 0, `evaluate_rms`, `estimate_phasor`, `estimate_trailing_rms_at_time` and `classify_waveform_form` all raise `ZeroDivisionError`; for NaN, `evaluate_rms` and the detector raise `ValueError` while the estimators return results; for −50 and +∞ the RMS functions **return arrays instead of refusing** (the earlier assessment measured a mean of 90 where 100 is correct) (`evidence/nf-3a-2026-11-25/numerical_probes.json`, P6).
3. **Unusable is a typed, named state, not a guess.** Phasor family and overcurrent: `needs_configuration` with the existing `invalid_reference_frequency` (the frontend already maps it to a readable sentence, `index.html:55477`); oscillation: existing `invalid_nominal_frequency`; power/RMS creation: existing 400 `invalid_nominal_frequency`; compliance: blocked/`None`. No new public enumerated value is needed unless **O-5** chooses one.
4. **Native waveform viewing is never affected** (DEC-217): no viewing path reads the frequency.
5. **The imported value is preserved and reported** (`imported_text`), so the engineer sees what was declared and can supply a Manual value.
6. **An explicit analysis-level override** (`reference_frequency_hz` per request, builder parameter) keeps winning over the recording-level value, exactly as today, and is validated by the existing predicate.

### 6.2 Algorithm feasibility is a second, separate gate

Usable under NF-1 ≠ feasible for the algorithm (section 4.4). Each consumer keeps its own prerequisites and typed reasons (`insufficient_sampling_density`, `recording_too_short`, `uncertain`). NF-3 adds **no** new numeric gate; it only ensures the existing gates are evaluated with the *effective* value (C-11 evaluates them at 50 today).

## 7. Refresh, staleness and dependency strategy

### 7.1 What exists (verified)

* **Backend has no process-wide numerical cache.** Per-request memos only (`compliance_trace_service.py:112`, `independent_side_service.py:194`, `calculated_group_aware_per_unit.py:159`). Phasor, overcurrent, oscillation, compliance, event detection and eligibility are recomputed on every request.
* **Calculated channels are stored, immutable and eager** (`domain/calculated_channel.py:268-306`: `time`, `values`, `parameters`, `dependency_ids`, `reference_source_id`; "no edit-in-place; create another one"). The registry is in-memory only (`calculated_channel_registry.py`): there is **no persisted channel from an earlier run to migrate**.
* The workspace and recording lifecycle already clears NF-1 state (`remove_source`, `remove_workspace`).

### 7.2 Strategy

| Artifact | On a frequency change | Mechanism |
|---|---|---|
| **Live analyses** (phasor family, overcurrent, oscillation, compliance, event detection, eligibility) | next request uses the new value; nothing to invalidate | resolved per request; the response **echoes the frequency (and origin) it used** (`reference_frequency_hz` already, `nominal_frequency_hz` for oscillation) |
| **Existing RMS and power channels** | **never recomputed, overwritten or deleted; never silently presented as current** | *derived staleness*: channel is stale when `parameters["nominal_frequency_hz"]` ≠ the effective value of its grounding recording now; a channel built on a stale channel is stale via `dependency_ids` (walk the DAG, compare each ancestor's own recording) |
| **Mixed-source channels** (V from one recording, I from another; `Add` of two RMS channels from two recordings) | each ancestor is compared against **its own** recording; a power channel stores both inputs' recordings and is stale if either differs | one DAG walk per list request (in-memory, trivial) |
| **Compliance readiness steps** | a changed frequency changes `find_equivalent_rms` and proposes a **new** RMS step | already how it works; the old channel is untouched |
| **Frontend panels** | a visible analysis result is flagged "computed at 60 Hz; the recording is now 50 Hz" when its echoed frequency ≠ the current one; the builder default and the inventory cache are refreshed | NF-2's `wwRdNf` revision is the trigger (see 7.3) |
| **In-flight calculations** | each request resolves once and stamps what it used, so a `PUT` landing mid-request yields a result that is *self-consistent* and is then correctly seen as stale or current by the comparison | no locking across requests |

**Never:** retain a stored channel as if it reflected the new setting; recompute silently; take the first recording's frequency for a multi-recording calculation (DEC-217).

**Remedy for a stale channel:** create a new channel (existing behaviour). A one-click "recreate at the new frequency" is a UX convenience, not required (**O-4**).

### 7.3 Frontend refresh

NF-2 holds the authoritative revision per recording. NF-3 should publish a single in-page event (`nominal-frequency-changed`, `{sourceId, revision, effectiveHz, origin}`) from the `wwRdNf` apply/auto success path, and let the consumers subscribe: the inventory cache (`index.html:29071`), the builder (`:43946-43994`), and the open analysis panels. This keeps the NF-2 control accepted visually and unchanged; it only adds an event emission (a **functional necessity** in the sense of the owner's NF-2 closure note, so it should be confirmed rather than assumed).

### 7.4 Performance and responsiveness

* The accessor is a dictionary read under a lock (microseconds); it is called **once per request**, never inside a sample loop, never per channel in a loop over thousands.
* The numerical kernels are not touched, so their cost is unchanged. Acceptance includes a timing benchmark of RMS, sliding phasor and event detection on a 10⁶-sample record before and after each slice, within noise (proposed ±5 %).
* The staleness walk is O(channels + edges) per list request. The advisory counts are computed at list time, not stored.

### 7.5 Wiring risk and the guard

Services do not currently receive the NF-1 registry; threading it through the phasor, overcurrent, compliance, oscillation, synchronization and calculated-channel entry points is a wide signature change. **The failure mode is a forgotten call path that silently keeps using the imported value** while the UI says Manual. The repository already solved the same problem for PU: `tests/test_pu_core_001_dispatch_registry_guard.py` ("no production call path omits the group registries"). NF-3 should add the same kind of guard: an AST/call-graph test that every production caller of a migrated consumer passes the frequency authority, and that the direct-reader allow-list shrinks to the importer and the authority only.

## 8. Release-gate transition (NF-2 preview to active control)

### 8.1 What stays until the evidence below exists

* `nominalFrequencyOverride` is absent from `frontend/config.js`, the container entrypoint, compose files, the Dockerfile, workflows and scripts (verified again on `e3296a3`; static tests in `backend/tests/test_frontend_nf2_release_gate.py`).
* `WW_NF_CONSUMERS_MIGRATED = false` (`frontend/index.html:37156`), so "Preview: calculations do not use this setting yet." stays.
* No wording anywhere says or implies that saving a Manual value updates calculations (checked in NF-2 by a browser test).
* The accepted NF-2 visual presentation is not changed by NF-3 except for the one line below.

### 8.2 Evidence required before either gate moves

All of the following, recorded in a gate-opening document and approved by the owner:

1. **Inventory closed:** every **M** entry in section 3 is migrated or explicitly re-classified by the owner; the direct-reader tripwire lists only the importer and the authority; the new call-path guard passes.
2. **Auto equals baseline:** for each migrated consumer, golden outputs for {50, 60, assumed, 4096 Hz non-integer, unusable} are identical to the NF-3B frozen outputs.
3. **Manual is effective:** per consumer, a Manual value changes the output to the §5.1 bit-for-bit expectation and, where applicable, within the §5.2/§5.5 tolerances.
4. **Unusable is typed:** per consumer, no exception, no HTTP 500, no silent number (§6).
5. **Stale cues and refresh:** derived staleness (including DAG and mixed-source cases), advisory, builder refresh and panel flags tested in the browser.
6. **Regression:** full backend suite with zero failures on the exact commit; Recording Details, Calculated Channels, analysis panels and Waveform browser regressions with **no new failures**. The **14 unresolved baseline-equivalent WUI failures** (NF-2 record) must be unchanged as a set; the owner decides whether to triage them first (**O-12**).
7. **Mutation checks** per slice (as for R0/R1A/NF-1/NF-2), with equivalents explained.
8. **Protected-file integrity** against the previous verified commit for everything a slice must not touch.
9. **Server-side enforcement in place** if **O-1** is approved.
10. **Interactive owner UAT in an isolated DEV-like environment with the gate on** (NF-2 visual acceptance did not cover this).
11. **A single, separate gate-opening commit** that (a) flips `WW_NF_CONSUMERS_MIGRATED` and replaces the preview line with a statement of what the setting now applies to, including any deferred consumer (**O-3**), and (b) introduces the deliberate deployment path for `nominalFrequencyOverride` (for example an environment variable read by the entrypoint), updating the static test that today forbids it. Both need owner approval; neither is part of NF-3B–NF-3H.

### 8.3 Rollback

* **UI gate off** returns the original read-only row; no data is lost.
* **Hidden-effect hazard:** if consumers honour the registry while the UI gate is off, a Manual value set earlier (or through the live `PUT`) would silently keep affecting calculations with no UI. **O-1** (server-side enforcement) removes the hazard: with the setting off, the accessor returns Auto for every consumer, `PUT manual` is refused, and behaviour equals today's exactly.
* The registry is in-memory: a restart clears all Manual values, a natural reset to Auto.
* Each slice is independently revertible because it touches one consumer group and one test set; no slice changes the NF-1 resolver, registry, API or the NF-2 UI.

## 9. Proposed slices

Ordering principle: **dependency first, then regression risk, then numerical risk.** Each slice follows the R0/R1A/NF-1/NF-2 method: frozen baseline committed first; separate implementation commit; differential and mutation checks; protected-file integrity; full-suite run on the exact commit; handover; owner review before the next slice. NF-001 numbering in brackets.

| Slice | Content | Behaviour change |
|---|---|---|
| **NF-3B** | Frozen baselines + consumer accessor + call-path guard (**[NF-3 prerequisite]**) | **none** |
| **NF-3C** | Validating consumers: oscillation, event detection/sync, compliance readiness and measurement **[NF-3]** | Manual effective; Auto identical |
| **NF-3D** | Phasor family and overcurrent **[NF-4]** | unusable → typed refusal; Auto identical |
| **NF-3E** | Calculated-channel RMS default, eligibility validation, builder, derived staleness, advisory, provenance **[NF-5, NF-6]** | RMS default source; eligibility 500 → 400 |
| **NF-3F** | Power channels **[NF-7, power part]** | **numerical change** for non-50 recordings (O-2) |
| **NF-3G** | Oscillation cross-signal multi-recording rule **[NF-8]** | behaviour change (O-9) |
| **NF-3H** | Remove silent 50 Hz defaults from engine entry points (hardening) | none for migrated paths |
| **NF-3I** | Gate transition (section 8.2) | UI text; deployment path |

Auto Base evidence (C-17) is **not** in this sequence (O-3).

### 9.1 NF-3B — frozen baselines, accessor, guard (recommended first)

* **Consumers:** none changed.
* **Files likely:** new `backend/app/services/nominal_frequency_consumer.py` (typed outcome + `frequency_for_source(...)`, thin wrapper over `effective_nominal_frequency`); new `backend/tests/test_nf3b_frozen_consumer_baselines.py`; `backend/tests/test_nf3b_frequency_call_path_guard.py`; extends the NF-1 tripwire only in documentation. **No production consumer file is edited.**
* **Numerical tests:** capture, as committed golden data, each consumer's current output for {50 declared, 60 declared, assumed 50, 4096 Hz non-integer, unusable 0, NaN, −50} **including the current defects** (HTTP 500 for the eligibility request 0; `ZeroDivisionError` paths) so a later slice can show *exactly* what it changed. Add the §5 closed-form probes as permanent tests.
* **Browser tests:** none.
* **Invariants:** NF-1 resolver/registry/API and NF-2 UI byte-identical; `ALLOWED_DIRECT_READERS` unchanged; full suite unchanged.
* **Acceptance:** goldens reproducible; accessor returns the NF-1 outcome for every recording class; the guard fails on a synthetic consumer that omits it; mutation checks kill a wrong-source accessor.
* **Release / rollback:** revert one commit; no deployment effect.

### 9.2 NF-3C — validating consumers

* **Consumers:** C-03, C-04, C-05, C-06, C-07 (labels), C-24 (facts card, per **O-11**).
* **Files likely:** `synchronization_service.py`, `compliance_readiness_service.py`, `compliance_measurement_service.py`, `oscillation_representation_service.py`, `oscillation_spectrum_service.py` (origin mapping), their routers' dependency wiring, `frontend/index.html` (origin labels at `:63386,63937,64147`; facts card).
* **Numerical tests:** Auto = frozen; Manual per §5.1; unusable per §6; compliance readiness opens a new RMS step when the Manual value changes; measurement never raises.
* **Browser tests:** oscillation panel labels (`recording`/`assumed`/`manual`); Recording Details facts card agrees with the row.
* **Invariants:** existing typed codes and messages; `nominal_frequency_assumed` tripwire inventory (`test_comtrade_nominal_frequency_provenance.py`) updated *deliberately*; stored synchronization offsets untouched.
* **Acceptance:** §8.2 items 2–4 for these consumers.
* **Rollback:** revert one commit; accessor stays.

### 9.3 NF-3D — phasor family and overcurrent

* **Consumers:** C-01, C-02, C-09, C-10.
* **Files likely:** `phasor_analysis_service.py` (`_fetch_role_candidate`, the three selection sites), `overcurrent_analysis_service.py`, wiring in the five analysis routers; message text for `reference_frequency_conflict` ("declaring different nominal frequencies" becomes "…effective nominal frequencies").
* **Numerical tests:** start with **failing tests** that reproduce the unguarded declared value (0, −50, NaN) through HTTP with an Engineering Context; then green; Auto = frozen across phasor/sequence/impedance/distance/overcurrent; multi-recording agree-or-override with one assumed and one Manual value; sampling-density refusal at Manual 1000 Hz on 5 kHz.
* **Browser tests:** phasor, sequence, impedance, distance, overcurrent panels show the typed sentence for an unusable recording and recover after a Manual value.
* **Invariants:** override semantics; calibration gate ordering (blocked before frequency); `window_seconds`, `reference_frequency_hz` echoes unchanged; no change to estimators.
* **Acceptance:** §8.2 items 2–4; protection-analysis results bit-identical for valid Auto.
* **Rollback:** revert one commit.

### 9.4 NF-3E — RMS channels, eligibility, builder, staleness

* **Consumers:** C-14 (default only), C-15, C-22, C-24 (stored-parameter displays stay).
* **Files likely:** `api/v1/calculated_channels.py`, `schemas/calculated_channel.py`, `calculated_channel_service.py` (provenance recording only; the RMS parameter and kernel unchanged), a small `services/calculated_channel_staleness.py`, `frontend/index.html` (inventory cache, builder default and cache refresh, stale marker, one-line advisory), the NF-2 event emission (7.3).
* **Numerical tests:** eligibility 0/−50/NaN → 400, never 500; RMS parameters and values unchanged for an explicit parameter; derived staleness over a three-level DAG and a two-recording `Add`; origin/revision recorded in parameters (additive).
* **Browser tests:** builder default follows the effective value and refreshes on a change; unusable recording requires an explicit choice (O-8); stale marker and advisory; creation while a `PUT` is in flight.
* **Invariants:** an explicit `nominal_frequency_hz` parameter keeps working and is validated; channels immutable; ROCOF untouched.
* **Acceptance:** §8.2 items 2–5.
* **Rollback:** revert one commit; the stale walk is read-only.

### 9.5 NF-3F — power channels (needs O-2)

* **Consumers:** C-11, C-12, C-13.
* **Files likely:** `calculated_channel_service.py` (the two prerequisite gates, the two evaluator calls, the stored parameter), tests. The kernels already accept a frequency; **no domain function is edited**.
* **Numerical tests:** §5.5 table; 50 Hz bit-identical to frozen; V and I from two recordings must agree or the request is refused with a typed reason; stored `parameters["nominal_frequency_hz"]` equals the value used.
* **Browser tests:** creating a power channel on a 60 Hz recording.
* **Invariants:** calibration, units, sign convention, `window_mode`, null policies unchanged.
* **Acceptance:** §5.5; §8.2 items 2–4.
* **Rollback:** revert one commit. **Do not start before O-2.**

### 9.6 NF-3G — oscillation cross-signal (needs O-9)

* **Consumers:** C-08, C-07 (cross-signal part). **Files:** `oscillation_classification.py`, `oscillation_cross_signal_service.py`. **Tests:** all members agree; members differ → `nominal_frequency_mixed` limiting evidence and no value picked; assumed flag preserved. **Rollback:** revert one commit.

### 9.7 NF-3H — remove silent defaults

* **Consumers:** C-16. After NF-3C–NF-3F no production caller omits the frequency; make `reference_frequency_hz`/`nominal_frequency_hz` required in `compute_sliding_phasor`, `evaluate_power_channel`, `evaluate_three_phase_power_channel` and `extract_waveform_evidence` (the last only once O-3 is settled), so a future caller cannot silently get 50 Hz. This edits domain signatures (not algorithms) and is therefore listed separately and needs its own approval.

### 9.8 NF-3I — gate transition

Section 8.2 items 9–11. Not part of the migration; separate approval.

## 10. Regression and UI/UAT requirements (every slice)

* **Backend:** full suite, zero failures, on the exact final commit. The tripwires (`ALLOWED_DIRECT_READERS`, `nominal_frequency_assumed` inventory, the new call-path guard) are updated only by deliberate, reviewed edits; no assertion is relaxed.
* **Browser:** Recording Details regression (gate off and on), the NF-2 spec, Calculated Channels builder, the analysis panels a slice touches, and the Waveform regression, run sequentially in the isolated setup. The 14 known failures are compared as a **set**.
* **Mutation checks:** per slice, mutate the consumer to read the imported value, ignore Manual, accept an unusable value, swap recordings, drop the guard; each must be killed.
* **Owner UAT checklist (gate on, isolated):** 50 and 60 Hz recordings; CSV (assumed); unparseable `lf`; `lf = 0` (the `declared_zero` scenario exists in the test corpus); a Manual 60 on a 50 Hz recording (expect the visible degradation, section 5.4); change the frequency with RMS and power channels present (stale cue and advisory); two recordings with different frequencies in one phasor analysis; reset and re-add.

## 11. Existing defects and behaviours that NF-3 would change (change-governance format)

Each is **reported, not fixed**. Approval is requested through section 13.

### D-A. Power channels ignore the recording's frequency
* **Issue:** DFT window fixed at 1/50 s; prerequisite gates at 50 Hz; stored parameter says 50.0 (`calculated_channel_service.py:1071,1075,1290,1294,1493,1502,1547,1554`; `domain/calculated_channel.py:965,1031`).
* **Evidence:** measured on exact signals: 60 Hz recording, **P −11.80 %, Q −13.21 %, P ripple 36.8 %**; 50 Hz exact (§5.5, probe P3).
* **Proposed solution:** NF-3F: pass the effective frequency; both inputs' recordings must agree or the request is refused.
* **Benefits:** correct power for non-50 Hz recordings; truthful stored parameter.
* **Risks:** numerical output changes for non-50 recordings, including any value an engineer has already relied on.
* **Expected impact:** none for 50 Hz recordings (bit-identical, tested); corrected for others.

### D-B. RMS-eligibility endpoint raises HTTP 500 for a frequency of 0
* **Issue:** `RmsEligibilityRequest.nominal_frequency_hz` is not validated; the detector divides by it.
* **Evidence:** HTTP probe: `POST …/calculated-channels/rms-eligibility` with `0` → **500**; `-50` → 200 `uncertain`; RMS *creation* with 0 or −50 → 400 `invalid_nominal_frequency` (`evidence/.../http_probe.json`).
* **Proposed solution:** validate the body with `nominal_frequency_valid`, return the same 400 as creation (NF-3E; **O-10**).
* **Benefits:** no 500; consistent contract. **Risks:** a client that relied on the 200-for-negative response (none known; the frontend sends only builder values > 0). **Expected impact:** error-path only.

### D-C. Declared frequency reaches engines unvalidated (phasor family, overcurrent, compliance measurement)
* **Issue:** the explicit override is validated, the recording's declared value is not (`phasor_analysis_service.py:375-387,418,708`; `overcurrent_analysis_service.py:303,334`; `compliance_measurement_service.py:298`).
* **Evidence:** the engine functions raise `ZeroDivisionError` for 0 and `ValueError` for NaN (RMS and detector), and return arrays instead of refusing for −50 and +∞ (probe P6; the earlier assessment measured a mean of 90 where 100 is correct). COMTRADE accepts all of these without warning and the upload returns 201 (HTTP probe; earlier R1A finding). End-to-end HTTP exposure through these services **was not exercised** here.
* **Proposed solution:** NF-3C/NF-3D: resolve to a typed outcome first; refuse with existing codes.
* **Benefits:** no exception and no silent wrong number from a corrupt declaration. **Risks:** a recording that "worked" by accident (for example declared −50 yielding wrong numbers) now says why it cannot. **Expected impact:** error-path only.

### D-D. Oscillation cross-signal takes the first member's frequency
* **Issue:** `next(s["nominal_frequency_hz"] for s in meta if ...)` then a 50 Hz constant (`oscillation_classification.py:259-261`).
* **Evidence:** code inspection; DEC-217 forbids it.
* **Proposed solution:** NF-3G: agreement or `nominal_frequency_mixed` evidence. **Benefits:** no silently chosen frequency. **Risks:** an analysis that used to give a verdict now reports limiting evidence. **Expected impact:** only multi-recording analyses with differing frequencies.

## 12. Reconciliation with earlier decisions and documents

* **DEC-217:** no conflict. Resolution, immutability, unusable-value policy, "never silently recalculated", "never take the first recording's" and progressive rollout are all carried. This assessment *adds* the server-side enforcement question (O-1), which DEC-217 does not address.
* **NF-001 assessment:** the 21-row consumer table is confirmed and extended. **New in this document:** the measured error magnitudes (P −11.8 %/Q −13.2 %), the non-integer-spc results, the detector's sub-3 Hz blindness, the HTTP-verified eligibility 500, the identity-based natural versioning in compliance readiness, the frontend facts card and origin labels (C-23, C-24), the `> 0` versus 1–1000 mismatch in the builder (C-22), the hidden-effect hazard, and the slice split. **Corrected:** NF-001 listed the facts card nowhere; it is a display that would disagree with a Manual value.
* **R0/R1A:** `rms_prerequisites.py` deliberately does not validate the frequency (its docstring says so), so the resolver's typed outcome must precede it; R1A's `nominal_frequency_assumed` flag remains the Auto input for COMTRADE and CSV/BEN; the R1A reader-inventory tripwire is updated consciously in NF-3C. The RMS display enhancement (R1) stays on hold until NF-3C–NF-3E and **must consume the same accessor**.
* **NF-1:** resolver, registry, API, validity predicate and tripwire are not changed by any slice.
* **NF-2:** UI unchanged except the event emission (7.3) and, at NF-3I, the preview line.
* **PU / CT-VT / side conversion:** frequency-independent (§4.3). Auto Base evidence (C-17) is PU-coupled and left to PU-MIG, subject to **O-3**. PU-MIG S1–S6 are **not** touched or started.
* **Protection and calculated-channel correctness:** protection analyses reach the frequency only through C-01/C-02; calculated channels keep their immutability, null policies, calibration gate and units.
* **WUI-001–004:** untouched. The 14 unresolved baseline-equivalent failures are carried as unresolved.

## 13. Open owner decisions

None of these was silently chosen. **Recommendation** is mine; each needs an owner answer.

| ID | Decision | Recommendation |
|---|---|---|
| **O-1** | **Server-side enforcement of the release gate.** Today only the UI is gated; the NF-1 `PUT` is live everywhere. Add a backend setting (default off): off ⇒ accessor returns Auto and `PUT manual` is refused (409), on ⇒ NF-3 behaviour. Cost: NF-1 tests that `PUT` a Manual value need the setting; the isolated preview needs the setting as well as the UI flag | **Yes**, in NF-3B. Alternative: rely on the UI gate and accept that API users can change calculations |
| **O-2** | Approve the **numerical change to power channels** (−11.8 % P / −13.2 % Q on a 60 Hz recording becomes ≈ 0) and the V/I-must-agree rule | **Approve**, with the §5.5 golden vectors |
| **O-3** | **Auto Base evidence (C-17)**: defer to PU-MIG (recommended) or migrate in NF-3. Either way, state at gate opening that the setting does not (yet) apply to Auto Base voltage evidence | **Defer**; word the NF-3I statement accordingly |
| **O-4** | Existing channels after a change: **stale marker + one advisory only** (recommended), or also a one-click "recreate at the new frequency" | Marker + advisory; recreate stays an explicit action |
| **O-5** | Reason code for an unusable recording in the phasor family and overcurrent: **reuse `invalid_reference_frequency`** (already mapped to a sentence in the UI) or add a new public code | Reuse; no new enumerated value |
| **O-6** | Additive API fields for provenance: origin and revision in analysis results and in new calculated-channel parameters (D8 of the earlier assessment) | **Yes**: a wrong Manual value is silent (§5.4), so the origin must travel |
| **O-7** | Event-detection response when the recording is unusable: keep `nominal_frequency_hz: float` (non-null) as today, reporting the declared value, or make it nullable | Keep as today (no schema change) |
| **O-8** | RMS builder for an unusable recording: **no preselected frequency**, explicit choice required (today the dropdown defaults to 50) | Yes |
| **O-9** | Oscillation cross-signal: replace "first member / 50 Hz" by agreement-or-`nominal_frequency_mixed` | Yes |
| **O-10** | Fix the eligibility-endpoint 500 (D-B) inside NF-3E or as a separate contract fix | Inside NF-3E; separate approval was the earlier assessment's request |
| **O-11** | The Technical facts card (`index.html:22925`) and any other display of the imported value: show the **effective** value (with the same origin wording) once the gate opens | Yes, so two displays never disagree |
| **O-12** | Gate-opening evidence: must the **14 unresolved WUI failures** be triaged first, or is "unchanged as a set" sufficient? Is interactive DEV UAT mandatory? | Triage separately; require "unchanged as a set" and mandatory UAT |

Not reopened: the 1–1000 Hz validity range, the Auto/Manual semantics, Manual-equal-to-Auto stored, workspace scope, in-memory registry, immutability of originals.

## 14. Recommended first implementation slice

**NF-3B (section 9.1), conditional on O-1.** Rationale: (1) no consumer or output changes, so zero numerical risk; (2) it creates the frozen baselines that make "Auto is identical" a proof for every later slice and records the four existing defects as tests; (3) it adds the single accessor and the call-path guard that remove the "forgotten call path" failure mode (7.5); (4) it is independently revertible; (5) if O-1 is approved, it also puts the server-side gate in place *before* any consumer can honour a Manual value, so no later slice can create a hidden effect.

The first *behaviour-changing* slice should then be **NF-3C** (the consumers that already validate): lowest blast radius, existing typed refusals, and the oscillation origin labels are the smallest visible change.

## 15. Evidence and artefacts

| File | Content |
|---|---|
| `scripts/diagnostics/nf3a_numerical_probes.py` | P1 RMS, P2 phasor, P3 power, P4 detector, P5 envelope, P6 invalid values, P7 waveform evidence, P8 detector range |
| `scripts/diagnostics/nf3a_http_probe.py` | eligibility and RMS creation over HTTP for 50/60/0 Hz recordings |
| `docs/project-memory/evidence/nf-3a-2026-11-25/numerical_probes.json` | measured output of the above |
| `docs/project-memory/evidence/nf-3a-2026-11-25/http_probe.json` | measured HTTP statuses |

Reproduce from `backend/`: `PYTHONPATH=. python ../scripts/diagnostics/nf3a_numerical_probes.py`. The probes import production code read-only and change nothing; the HTTP probe uses an isolated temporary storage directory.

## 16. Limits of this assessment

* Phasor family, overcurrent and compliance exposure to an unusable recording is **inferred** from call sites and the engine probe, not driven through HTTP (NF-3D/NF-3C begin with failing tests for exactly that).
* The 4096 Hz oracle uses exact time arrays. A real COMTRADE file rounds timestamps to microseconds, which can make the spacing test (`rtol = 1e-6`) classify the record as irregular and make the phasor estimator refuse it (`irregular_sampling_not_supported`). That is an existing limitation, independent of NF-3, and should be checked on real 4096 Hz files before the 4096 Hz acceptance case is promoted to a browser test.
* No browser, DEV or deployment evidence was produced or claimed.
* The proposed tolerances (§5.2) and the ±5 % timing bound (§7.4) are proposals, not owner-approved values.
