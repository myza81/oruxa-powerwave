# D5A-2B — Recorded-Path Correction: API and Mathematical Design Contract

**Status: DESIGN ONLY. Nothing here is implemented; no storage is introduced.** For owner review before D5A-2B numerical implementation.

## 1. Problem (verified, see D5A-1 F2/F3)

Recorded Impedance/Distance take one `recording_basis` for both V and I, so a recording with V and I on different sides is mis-scaled (V primary 66 kV, I secondary 2 A, `recording_basis=primary`: reports 33 000 Ω primary or 6 600 Ω secondary; truth 165 Ω / 33 Ω — wrong by exactly the CT ratio). The basis is caller-asserted and never reconciled with the recording.

## 2. Three distinct concepts

| Concept | Today | D5A-2B |
|---|---|---|
| Voltage recording side | implied by `recording_basis` | `voltage_side` |
| Current recording side | implied by `recording_basis` | `current_side` |
| Requested output/calculation side | `impedance_basis` | unchanged name and meaning (`output side`) |

## 3. Mathematical rule (verified numerically for all combinations)

Convert **each quantity directly into the output side**, then divide once:

```
V_out = V                      if voltage_side == output
      = V * vt_ratio           if voltage_side == secondary, output == primary
      = V / vt_ratio           if voltage_side == primary,   output == secondary
I_out analogously with ct_ratio         (ratio = primary / secondary)
Z_out = V_out / I_out                   (ratios are real positive scalars: angles are unchanged)
```

A ratio is required **only for a quantity whose side differs from the output**, so the legacy "no ratios when `recording_basis == impedance_basis`" rule is preserved exactly. Same-side cases are algebraically identical to today's `convert_impedance_basis` (`Z·vt/ct`, `Z·ct/vt`), checked to 1e-12.

Distance: the same per-quantity normalisation is applied to every leg before `Vloop = V1 − V2`, `Iloop = I1 − I2`. Linear scaling commutes with the subtraction only if both legs share a side — hence decision B3.

Overcurrent is current-only; `current_side` plays the role `recording_basis` plays today (output is relay-secondary amperes); no new maths.

### Regression oracle (from D5A-1; VT 110000:110 = 1000, CT 1000:5 = 200; true Z = 165 Ω primary / 33 Ω secondary)

| V side | I side | Output | Ratios required | Expected Z |
|---|---|---|---|---|
| primary (66 000 V) | primary (400 A) | primary | none | 165 Ω |
| primary | primary | secondary | VT, CT | 33 Ω |
| primary | secondary (2 A) | primary | CT | 165 Ω |
| primary | secondary | secondary | VT | 33 Ω |
| secondary (66 V) | primary | primary | VT | 165 Ω |
| secondary | primary | secondary | CT | 33 Ω |
| secondary | secondary | primary | VT, CT | 165 Ω |
| secondary | secondary | secondary | none | 33 Ω |

All four existing manual-mode pins (`test_d5a1_protection_ratio_semantics.py`) already pass on this rule; D5A-2B adds the same eight rows through the recorded HTTP endpoints, plus bit-for-bit legacy equivalence (omitting the new parameters must leave every existing recorded result unchanged — the existing 1,497 protection tests are the guard).

## 4. Proposed API (additive, backward compatible)

New optional query parameters on recorded `…/impedance`, `…/impedance-locus`, `…/distance-protection`, `…/distance-protection-locus` (and `current_side` on `…/overcurrent`):

- `voltage_side`, `current_side`: `primary` | `secondary`.
- Precedence per quantity: explicit `*_side` → else `recording_basis` → else `needs_configuration` (`voltage_side_required` / `current_side_required`).
- Omitting both new parameters is exactly today's behaviour.
- Invalid value → `needs_configuration` (`invalid_voltage_side` / `invalid_current_side`).
- Results echo `voltage_side`, `current_side` (and keep `recording_basis`) for provenance.
- Ratios still come from the request in this slice (legacy). The D5A-2A endpoint reports any disagreement.

A later opt-in (D5A-2C, needs D2) `basis_source=authoritative` would take ratios from Recording Details and sides from recording-declared/engineer-confirmed evidence, blocking on conflict. Not part of D5A-2B.

## 5. Engineer-confirmed measurement side: smallest data model

Evidence order: **recording-declared (per channel) is evidence; engineer confirmation fills gaps and may flag conflicts; nothing is inferred from a ratio.**

**Recommended (smallest):** three fields on each existing group configuration — `VoltageBaseConfiguration` and `CurrentBaseConfiguration` — no new registry:

- `measurement_side`: `unknown` (default) | `primary` | `secondary`
- `measurement_side_authority`: `not_configured` | `manual`
- `measurement_side_note`

Resolution per channel: recording-declared side if present; else the group's confirmed side; if both exist and differ → `side_conflict` (diagnostic now, blocking only in the later authoritative mode). Voltage and Current groups hold their own value, so the two sides stay independent.

**Group-level defaults with channel exceptions?** Not required now. A group's channels share one CT/VT set, so one side per group is the normal case; mixed members already surface as `mixed`, and an engineer can split the group. Per-channel exceptions would add a map and UI with no demonstrated need — defer until a real recording requires it.

**Do not reuse `base_reference_side`.** It is the *PU base's* side (a denominator), a different concept from where the samples were measured. The accepted PU engine reads only `channel.measurement_side`; the confirmed side above would be consumed by protection analyses only and **must not feed PU** unless the owner explicitly decides otherwise (B5).

Storage is the existing in-memory group-config registries; Recording Details (Codex) gains one field per group panel. No storage is introduced until this is approved.

## 6. Owner decisions required before D5A-2B

- **B1** Approve explicit `voltage_side`/`current_side` on the recorded endpoints with the precedence in §4.
- **B2** Confirm omitting them keeps today's single-`recording_basis` behaviour exactly.
- **B3** Mixed sides *within* one quantity (e.g. Va primary, Vb secondary): reject with `mixed_side_within_quantity` (recommended), or support per-channel sides?
- **B4** Approve the three-field group-level model and the precedence/conflict rule in §5 (storage change).
- **B5** Confirm engineer-confirmed side never feeds PU.
- **B6** Confirm output naming stays `impedance_basis`.
- **D2** (from D5A-1) Behaviour when request basis disagrees with declared side — diagnostic only now; blocking only in the opt-in authoritative mode?

## 7. Proposed D5A-2B implementation steps (after approval)

1. Domain: per-quantity normalisation in the recorded Impedance/Distance paths behind the new parameters, reusing `convert_manual_magnitude_to_secondary`-style ratio helpers; legacy path untouched when parameters are absent.
2. Eight-row oracle through HTTP for Impedance and for Distance (second leg at zero ⇒ Z = V1/I1), plus locus parity.
3. Overcurrent `current_side` alias.
4. Result echo fields and schema additions.
5. Full protection and PU regression; PU files untouched.
