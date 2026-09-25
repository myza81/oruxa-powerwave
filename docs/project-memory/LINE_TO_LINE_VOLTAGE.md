# Line-to-Line Voltage — Calculated Channel operation

Status: **implemented, awaiting owner UAT** —
[DECISIONS.md — DEC-115](DECISIONS.md#dec-115--line-to-line-voltage-is-a-dedicated-calculated-channel-engineering-operation-bay--engineering-context-input-instantaneous-vabvbcvca-with-declared-line-to-line-metadata-atomic-all-three-and-stable-pair-colors).

This document is the feature reference for the operation. It builds on
the Calculated Channels decisions (DEC-047 model, DEC-048 RMS,
DEC-084 null handling), the Engineering Context/resolver foundation
([ANALYSIS_INPUT_GUARDRAILS.md](ANALYSIS_INPUT_GUARDRAILS.md)), the
Phasor waveform-eligibility rule ([PHASOR_ANALYSIS.md](PHASOR_ANALYSIS.md)),
and the Per-Unit model ([PER_UNIT_MEASUREMENT_MODEL.md](PER_UNIT_MEASUREMENT_MODEL.md)).

## 1. What it is

A dedicated **engineering** operation on the Calculated Channels page,
labelled **"Line-to-Line Voltage (L-L)"**. It derives phase-to-phase
voltages from one bay's phase-to-neutral voltages:

```text
VAB = VA − VB
VBC = VB − VC
VCA = VC − VA        (cyclic AB → BC → CA; VAC is never used)
```

It is an exact difference, never `√3 × VLN`, so it stays correct during
unbalanced disturbances. It is **not** a Subtraction preset: it has its
own input model, validation, readiness, metadata and UI. Internally, the
pointwise arithmetic reuses `evaluate_subtraction()`, so there is still
only one subtraction implementation.

`operation = "line_to_line_voltage"` is deliberately **not** in
`ALL_OPERATIONS`. The generic `POST .../calculated-channels` endpoint
rejects it (422). The only way to create an L-L channel is through the
Engineering Context route below.

## 2. Input model: Bay / Engineering Context

The engineer chooses **one Bay / Engineering Context**, never individual
Va/Vb/Vc channels. Phase roles are resolved by the same authorities
Analysis uses. There is no second phase-name detector:

| Concern | Authority reused |
|---|---|
| Voltage + canonical phase A/B/C, ambiguity, phase identity missing | `resolve_analysis_inputs()` (DEC-087), via `check_phasor_diagram_readiness()` |
| Instantaneous vs RMS/magnitude (metadata first, multi-window detector fallback) | the Phasor waveform-form eligibility rule (DEC-088/107/108) |
| Reference-frequency agreement (drives the detector's cycle windows) | the same Phasor preflight, restricted to Va/Vb/Vc (`role_keys`) |
| Unit compatibility | `units_compatible()` (DEC-047: identical units, no conversion) |
| Timebase alignment | `timebases_aligned()` (DEC-047: proven instants, no resampling) |

Guardrails added for this operation:

- the resolved channel must be a phase **voltage magnitude**, not a
  DEC-078 *Voltage Angle* channel (which shares the broad `Voltage`
  engineering type);
- a calculated channel that already declares `line_to_line` is never
  accepted as a phase-to-neutral input;
- a Current channel never satisfies a Voltage role, because role matching
  is by engineering type plus phase.

## 3. Readiness

`GET /api/v1/workspaces/{ws}/calculated-channels/line-to-line-voltage/readiness`
returns **every** Engineering Context in the workspace, including
incomplete or unsupported ones (no bay is hidden). Each entry contains:

- `roles.Va/Vb/Vc`: `ready` / `missing` / `ambiguous` /
  `phase_identity_missing` / `unsupported_representation` /
  `needs_configuration`, plus the resolved channel label, unit and an
  actionable message;
- `outputs.AB/BC/CA/all_three`: `available` plus a `reason`. Readiness
  depends on the selected output: VAB needs Va+Vb, VBC needs Vb+Vc, VCA
  needs Vc+Va, and All Three needs all of them;
- the context `status` (`ready` / `incomplete` /
  `unsupported_representation` / `ambiguous`) and a one-line `summary`,
  e.g. `KPDN1 — Ready for All Three`, `KPDN2 — Ready for VAB only — Vc
  missing.`

RMS-magnitude-only phase voltages are rejected with:

> Line-to-line voltage requires either instantaneous phase voltages or
> full complex phase phasors. RMS magnitudes alone are insufficient.

## 4. Creation and atomicity

`POST /api/v1/workspaces/{ws}/calculated-channels/line-to-line-voltage`

```json
{ "engineering_context_id": "ec-…", "output": "AB|BC|CA|all_three",
  "names": {"AB": "optional custom name"},
  "null_policy": "propagate_null", "…estimation fields…": null }
```

The backend re-derives readiness and never trusts the client's verdict.
**All Three is atomic.** Every pair's readiness, every name (default names
included), the null-policy configuration and every evaluation are checked
before anything is written. If any pair is unavailable or any name
collides, **zero** channels are created. The response is
`{creation_batch_id, channels: [...]}`.

## 5. Domain model and metadata

One `CalculatedChannel` produces one scalar output. All Three creates
three ordinary channels. Three optional fields were added to
`CalculatedChannel` (`None` for every generic operation, so existing
channels are unchanged):

| Field | L-L value | Purpose |
|---|---|---|
| `voltage_representation` | `line_to_line` (from `voltage_reference.KNOWN_VOLTAGE_REFERENCES`) | electrical representation, read by Per-Unit |
| `phase_member` | `AB` / `BC` / `CA` (from `phase_identity`) | pair identity for Analysis/Compliance/colors |
| `creation_batch_id` | shared `llb-…` id for All Three, `null` for one pair | UI grouping only; never a dependency |

The output also has `engineering_type = Voltage`,
`waveform_form = instantaneous`, `inputs = [minuend, subtrahend]` (the
order encodes polarity), and `parameters = {pair, source_path:
"instantaneous", engineering_context_id, engineering_context_name}`.
None of these semantics are ever parsed from the channel name.

**Unary propagation.** Reverse Polarity, Absolute Value, Multiply by
Constant and RMS carry the input's `voltage_representation` through, so
RMS(VAB) is still line-to-line. RMS and Absolute Value also carry
`phase_member` (−VAB is VBA, so Reverse Polarity does not).
Multi-input operations never propagate either field, so DEC-052 is
unchanged.

**Dependencies.** L-L channels behave like any other calculated channel.
They are deleted individually (deleting one set member leaves the
others), deletion is blocked while another calculated channel depends
on them, removing the source cascades to them, and they can be used as
inputs to further calculations (e.g. RMS(VAB)).

**Null handling.** The same DEC-084 policies are validated and applied
by the same helpers as generic creation (`_validate_null_policy_configuration()`
/ `_effective_input_values()`, factored out of `create_calculated_channel()`
without behaviour change). There is no interpolation unless
*Estimate Missing Data* is chosen explicitly.

## 6. Per-Unit

A declared representation overrides name-based detection for the
channel's **own** Voltage denominator, on both resolution paths:

- **Measurement Group (DEC-050):** an L-L channel inherits a group only
  when both phases belong to the same group. The group's confirmed status
  and configured nominal still apply, but the denominator follows the
  declared `line_to_line` value (`Vbase_LL`), not the group's own
  line-to-ground reference.
- **Source Default (DEC-049):** `resolve_per_unit(...,
  explicit_voltage_reference=...)` does the same.

```text
nominal system 275 kV L-L
Va  (phase-to-ground source)   base = 275/√3 ≈ 158.77 kV
VAB (declared line_to_line)    base = 275 kV
```

Provenance reports `nominal_reference = line_to_line` for these channels.
**Generic Subtraction is unchanged:** `VR − VY` still resolves
`base_required` on the group path (DEC-052).

## 7. Plot All and colors

- After creation, the page shows **one result set** ("Created: KPDN1 VAB ·
  KPDN1 VBC · KPDN1 VCA") with **Plot All** (or **Plot** for one pair).
  Each channel in an All Three set also has a **Plot All (VAB, VBC, VCA)**
  row action, which remains available after a reload.
- Plotting uses the ordinary `wwAddSelectedChannels()` path. There is no
  second renderer.
- **Colors:** `wwDefaultChannelColor()` (the single color authority for
  traces, legend and sidebar dots) gives L-L channels fixed slots in the
  central `CHANNEL_TRACE_COLORS` palette: **AB → slot 0, BC → slot 1,
  CA → slot 2**. The slot is keyed on `operation` + `phase_member`, not on
  the name or on plot order. The colors are therefore always distinct from
  each other and stay the same across hide/show, zoom, layout redraw,
  page revisit and full reload. A user's explicit color override still
  wins, as for every channel. The palette is the same fixed palette every
  channel uses in both themes.

## 8. Deferred: the complex-phasor source path

**Deferred, not implemented.** The domain contract is kept ready for it:
`SOURCE_PATH_PHASOR` exists as vocabulary, and `parameters.source_path`
records which path produced a channel.

Architectural gap that blocks it today:

1. **There is no reachable phasor source when instantaneous waveforms are
   unavailable.** The only phasor engine (`estimate_phasor()`) estimates
   phasors *from instantaneous samples*. When instantaneous Va/Vb/Vc
   exist, the preferred instantaneous path already applies, so a
   phasor-derived path would never be chosen.
2. **Recorded magnitude + angle phasors have no role model.** A DEC-078
   CSV/Excel "Voltage" + "Voltage Angle" pair is the only other possible
   source. However, both channels have broad `engineering_type =
   Voltage` and the same phase, and nothing in Engineering Context or
   `RoleSpec` pairs a magnitude channel with its angle channel. Such a
   bay resolves as `ambiguous` today.
3. **Time series.** Given (2), a per-sample `|VA|∠θA − |VB|∠θB` on the
   shared source timebase would give a well-defined time series without
   inventing timestamps. That is the recommended design once a
   magnitude/angle role pairing exists (for example, a `RoleSpec`
   representation such as `phasor_magnitude`/`phasor_angle`).

Until then, such bays are reported as not available (ambiguous or
unsupported representation), and RMS-only data is never combined as
`VA_RMS − VB_RMS`.

## 9. Test coverage

- `backend/tests/test_line_to_line_voltage_domain.py`: frozen convention;
  balanced golden values (closed form `√3·V∠+30°`); an unbalanced
  disturbance proving exact subtraction rather than √3 scaling; VCA
  polarity; NaN propagation.
- `backend/tests/test_line_to_line_voltage_api.py`: readiness per bay and
  per output; exact pointwise values against the source arrays; metadata;
  atomic All Three (missing phase, name collision, duplicate names in one
  request, unsupported representation → 0 created); the generic endpoint
  refusing the operation; ambiguous, non-voltage, unknown-phase and
  already-L-L guardrails; cross-source unit mismatch and misaligned
  timebases; null policy; dependency, deletion and cascade behaviour.
- `backend/tests/test_line_to_line_voltage_per_unit.py`: 275 kV versus
  158.77 kV on both paths, name independence, RMS(VAB) propagation, and
  generic Subtraction still `base_required`.
- `browser-tests/line-to-line-voltage.spec.js`: selector readiness for
  KPDN1/KPDN2/MCRS; All Three → Create → result set → Plot All → three
  distinct trace colors that stay stable across hide/show, zoom, layout
  redraw, page revisit and reload; single pair on an incomplete bay;
  custom name; deleting one set member.
- Fixture `backend/tests/fixtures/comtrade/line_to_line_multibay`
  (50 Hz, 1 kHz, 2 s, kV/kA): KPDN1 has instantaneous VR/VY/VB with an
  unbalanced disturbance from 0.5 s (R sags to 30 %, Y shifts +15°), plus
  currents. KPDN2 has VR/VY only. MCRS has RMS-magnitude envelopes.

## 10. Known pre-existing issue (reported, not changed here)

`[FACT]` On the **Source Default (DEC-049)** path, a *generic*
Subtraction of two phase-to-ground Voltage channels (for example
`VR − VY` built with the Subtraction card) inherits the source profile
through the unanimous-source rule. It is then divided using the
**source's** auto-detected reference, which is line-to-ground
(`Vbase_LL/√3`). The group path refuses this case (DEC-052). The
source-default path does not, and `_resolve_effective_per_unit_for_calculated_channel()`
also falls back to it when the group path declines. The result is the
silently-wrong PU value DEC-052 was written to prevent. Verified
end-to-end on 2026-09-25 with this slice's fixture and a 275 kV Source
Default: generic `KPDN1_VR − KPDN1_VY` resolved `configured`, base
158.77 kV, reference `line_to_ground`. The result was the same with the
upload-time Measurement Groups removed and with them present. This slice does
not change generic Subtraction, per change governance. It needs an owner
decision (see HANDOFF).
