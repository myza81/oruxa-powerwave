# RD-1 Slice D2 Gate Check — 2026-11-18

## Purpose

Two domain-semantic gates must pass before `clear_nominal_voltage` can be
implemented safely. This document records the evidence and decisions for each.

---

## Gate 1: `secondary_voltage_ll_v` semantics under `clear_nominal_voltage`

**Question:** Is `secondary_voltage_ll_v` dependent on `nominal_voltage_ll_kv`?
If so, clearing the primary kV must also clear the secondary. If independent,
it must be preserved.

**Evidence — domain docstring** (`backend/app/domain/voltage_group_config.py`,
lines 157–162):

> Slice 5C-2: secondary equivalent L-L voltage in Volts (None = not
> established). This is the secondary-side equivalent of
> nominal_voltage_ll_kv, stored separately so the two are never
> conflated. Only populated when a VT ratio or explicit secondary
> configuration establishes a secondary equivalent.

**Analysis:**

`secondary_voltage_ll_v` is established independently through VT ratio
calibration or explicit secondary configuration — it is **NOT** a derived
quantity from `nominal_voltage_ll_kv`. The field exists precisely so the
two are never conflated.

Clearing `nominal_voltage_ll_kv` to `None` does not invalidate the secondary
equivalent, which may still be valid (derived from a separate VT ratio
calculation). Clearing it would destroy independently-established metadata.

**Decision: PRESERVE `secondary_voltage_ll_v` when `clear_nominal_voltage=True`.**

Gate 1: **PASS**

---

## Gate 2: `base_reference_side` vs `measurement_side` safety

**Question:** Is `base_reference_side` a physical calibration field?
Modifying physical calibration without rescaling waveform samples would
corrupt PU calculations.

**Evidence:**

- `measurement_side` on channels: populated from BEN/COMTRADE ingestion,
  represents physical calibration side of the instrument transformer.
  Immutable after recording import.
- `base_reference_side` on `VoltageBaseConfiguration` (`ReferenceSide` =
  `"unknown"|"primary"|"secondary"`): a configuration choice that determines
  which voltage value is used as the PU denominator when
  `base_authority="secondary"`. It does NOT rescale waveform samples.
- In `resolve_voltage_base_for_group()`: when `base_reference_side="secondary"`,
  the PU denominator switches to `secondary_voltage_ll_v` — no sample
  rescaling occurs; only the denominator value changes.

**Analysis:**

Setting `base_reference_side` via API is safe — it declares which equipment
rating the engineer is configuring as the PU reference, not a physical
measurement correction. The UI must label it as "voltage base reference side"
rather than "measurement correction" to avoid ambiguity.

**Decision: `base_reference_side` is safe to expose in D2 UI with clear labelling.**

Gate 2: **PASS**

---

## OQ-D2-4 resolution

Owner instruction: "include an appropriate reference-side control where the
existing authoritative backend supports it."

The existing PUT `/voltage-config` already accepts `base_reference_side`.
D2 UI includes a `base_reference_side` dropdown (Unknown / Primary / Secondary)
labelled "Base reference side" in the Edit panel. This matches the backend's
existing supported values without introducing new API contracts.

---

## D2 implementation authorised

Both gates pass. Implementation proceeds under D2 plan
([`RD1_SLICE_D2_PLAN_2026-11-18.md`](RD1_SLICE_D2_PLAN_2026-11-18.md)).

Key constraints carried forward:
- `clear_nominal_voltage=True` + `nominal_voltage_ll_kv` set → HTTP 422
- `secondary_voltage_ll_v` PRESERVED on clear (Gate 1)
- `reference_mode` / `reference_override` / `base_reference_side` PRESERVED on clear (D2 decision)
- UI must echo current `reference_override` and `base_reference_side` in PUT body
- PU invalidation required after Apply
