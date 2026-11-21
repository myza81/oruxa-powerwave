# D5A-UNIT-001 — Recorded Impedance and Distance did not normalise channel units

**Status:** **CORRECTED** (owner-authorised) in commit `303d307`. Found during D5A-2B1 verification; classified as a numerical-correctness defect, not an approved contract.

**Compatibility statement:** physically incorrect historical legacy recorded-impedance results **change**. No numerical compatibility is claimed for the defective outputs. V/A and kV/kA recordings are numerically unchanged.

## 1. Root cause and exact code correction

The legacy recorded paths computed `Z = V / I` from the *raw* channel magnitudes (`magnitude_rms` in each channel's own unit) and reported the result in fields named `*_ohm`. The value was in ohms only when voltage and current shared an SI scale (V/A, kV/kA). For kV/A it was 1000× too small and for V/kA 1000× too large. The error reached Distance zone classification because zones are evaluated from that same point.

Corrected paths (single-time **and** locus, both analyses):

- `impedance_analysis_service._impedance_analysis_from_diagram` and `distance_protection_analysis_service._distance_analysis_from_diagram` now normalise each voltage to volts and each current to amperes before the existing calculation, using the shared unit layer (`engineering_units.scale_to_canonical`) through `side_conversion.normalise_to_volts` / `normalise_to_amperes`. No second unit system was introduced.
- The low-current floor (1 mA) is now judged on amperes. Impedance judges `|I|`; Distance judges the loop current `|I1 − I2|` (for a balanced set √3 × the phase current), unchanged semantics, now in the right unit.
- Phasor angles, the impedance/loop formulas, Mho/Quadrilateral characteristics, CT/VT conversion rules (`convert_impedance_basis`, legacy basis rules) and manual mode are untouched. No second CT/VT application was added.
- The D5A-2B1 strict path uses the same helper; it also stopped labelling a non-finite magnitude as a unit error (only the unit decides).
- Distance v1 has no ground loops or k0/residual/zero-sequence compensation (explicit non-scope in `distance_protection.py`/`impedance.py`), so there is no compensated-current path to correct; the loops it has (AB, BC, CA) are verified.

## 2. Numerical before/after matrix (true 66 kV / 400 A ⇒ 165 Ω at +30°)

| Voltage / Current unit | Before: recorded Impedance and Distance | After | Strict mode | Manual mode |
|---|---|---|---|---|
| V / A | 165 | **165** (unchanged) | 165 | 165 |
| V / kA | 165 000 | **165** | 165 | 165 |
| kV / A | 0.165 | **165** | 165 | 165 |
| kV / kA | 165 | **165** (unchanged) | 165 | 165 |

Equal across the four combinations to ~4e-8 (limited by the test fixture's six-decimal sample quantisation). After CT/VT (VT 110000:110, CT 1000:5): 33 Ω secondary / 165 Ω primary for all four, for both legacy basis directions, and legacy equals strict for equivalent inputs.

## 3. Distance-zone classification impact

Zone states are now computed from physically correct ohms. Mho reach along 30° for a true 165 Ω: 200 Ω → operated, 150 Ω → not operated, 165.5 Ω → operated, 164.5 Ω → not operated, identical for all four unit combinations; the Quadrilateral (R 142.9 Ω, X 82.5 Ω) is likewise unit-independent. Historical results that were wrong and now change: a 10 Ω reach on a kV/A recording reported **operated** (0.165 Ω) and now **not operated**; a 1000 Ω reach on a V/kA recording reported **not operated** (165 000 Ω) and now **operated**. **No relay setting was altered to preserve historical classifications.**

## 4. Unknown and unsupported units

If the shared unit layer cannot normalise a consumed voltage or current unit, the analysis returns `needs_configuration` with `unsupported_voltage_unit` or `unsupported_current_unit` (single-time, locus per point, legacy and strict). It never divides raw magnitudes, never assumes volts or amperes, never infers a measurement side, and never falls back to the old behaviour. Verified: cross-quantity units (`A` as voltage, `V` as current), blank, `None` and unknown strings normalise to nothing; the wiring is tested for all four endpoints. A non-finite magnitude is left to the existing guardrails.

## 5. Algorithm version and provenance

- `impedance_locus_v1` → **`impedance_locus_v2`**; `distance_protection_v1` → **`distance_protection_v2`** (returned as `algorithm_version` on every recorded result, including strict).
- Manual versions unchanged (`impedance_manual_v1`, `distance_protection_manual_v1`).
- New `ZONE_GEOMETRY_ENGINE_VERSION = "distance_protection_v1"`: the zone-geometry engine did not change. The relay-conformance goldens stamp this constant, so none of the 50 golden files was regenerated.
- The frontend does not read `algorithm_version`.

## 6. Historical outputs expected to change (fixture survey, de-duplicated)

A recording's recorded impedance and zone results change when its voltage and current units have different SI scales.

- **Repository fixtures:** 17 files pair voltage and current; **1 changes** — `comtrade/synth_measurement_groups.cfg` (kV voltage, A current). The other 16 (V/A and kV/kA) are unchanged. 6 files have no voltage/current pair. No existing test asserted the defective value on a mixed-scale recording, so no existing numerical assertion needed updating; only the four D5A-2B1 characterisation tests (now converted) changed.
- **Owner BEN reference records** (read-only survey of `…/Tripping Event`): 132 records pair voltage and current; **19 change** (kV voltage with A current, e.g. the KAWA 275 kV and EMPP records); 113 are unchanged; 43 have no pair. Results are never persisted, so no stored data is affected — a re-analysis of those 19 records now yields the physically correct ohms and zone states.
- Survey is by unit scale per file; it does not decide which channels a given engineering context pairs.

## 7. API contract consistency (`recording_basis`)

`recording_basis` is `str | None = None` in the signature so strict requests need not send it; the legacy path re-raises the identical missing-field `422`. OpenAPI cannot express this conditional rule, so the parameter descriptions now state it (a test asserts the wording for all four endpoints):

| Parameter | Mode | Contract |
|---|---|---|
| `impedance_basis` | both | required; the requested **output** side |
| `recording_basis` | legacy | required whenever neither side parameter is supplied (else the historical 422); ignored, never used to infer a side, in strict mode |
| `voltage_side`, `current_side` | strict | supplying either selects strict mode, which then requires both; validated against the recording's per-channel declarations; never inferred from `recording_basis` or a CT/VT ratio; ratios come from Recording Details groups |

Runtime behaviour and existing clients are unchanged; only descriptions were added.

## 8. Verification

- **New tests:** `test_d5a_unit001_recorded_unit_normalisation.py` — 63 tests with an independent 165 Ω oracle: four unit combinations on `/impedance`, `/impedance-locus`, `/distance-protection` (loops AB, BC, CA) and its locus; CT/VT primary↔secondary conversions; legacy-vs-strict parity; 1 mA floor (kA and A, above/below, loop vs phase, zero current); zone classification inside/outside/near reach (Mho, Quadrilateral); unknown units; manual-mode non-regression; multi-recording isolation with different units; versions; OpenAPI wording; the original 1000-fold defect cannot recur. Mutation checks of the strict conversion (D5A-2B1) were retained.
- **D5A-2B1 file:** 70 tests (14 moved to the file above and converted).
- **Full backend suite on the final state:** 13 623 tests — **13 194 passed, 7 failed, 422 skipped, 27 warnings**. The 7 failures are the known Codex-owned frontend tests, identical to the baseline; no new failure. Categories (from the JUnit result): protection/phasor/sequence/relay-conformance 2 258 tests, 0 failed; D5A 224, 0 failed; Measurement Group/group-aware 408, 0 failed; PU 956, 0 failed; calculated-channel 678, 0 failed; engineering-context 94, 0 failed.

## 9. Not changed

PU formulas and authority, Overcurrent mathematics, CT/VT conversion policy and authority, Source Default (DEC-049) and H2 compatibility, Recording Details configuration, storage, and every frontend file.

## 10. Remaining owner decisions

D5A-2B2 (engineer-confirmed measurement-side model) remains open — see `D5A2B2_MEASUREMENT_SIDE_DATA_MODEL_PROPOSAL_2026-11-21.md`. No further decision is required for this correction; the owner may wish to inform users of the 19 reference records whose recorded impedance now differs.
