# Engineering Unit Normalization — shared domain layer

**Status: implemented** — see
[DECISIONS.md — DEC-091](DECISIONS.md#dec-091--shared-engineering-unit-normalization-appengineeringunits-becomes-the-one-authoritative-parsingnormalizationcanonical-conversion-layer-for-every-analyzer-fixing-a-real-overcurrent-uat-defect).

This document is authoritative for **Engineering Quantity vs Measured
Unit**, canonical calculation units, alias normalization, the prefix/
case policy, ambiguous-unit behaviour, Active/Reactive/Apparent Power
separation, display-unit vs calculation-unit, per-consumer migration
status, and the future-analyzer invariant every new analyzer must
follow. Read [PER_UNIT_MEASUREMENT_MODEL.md](PER_UNIT_MEASUREMENT_MODEL.md)
and [OVERCURRENT_ANALYSIS.md](OVERCURRENT_ANALYSIS.md) alongside this
document for how each of those features consumes (or deliberately does
not consume) this layer.

## The defect that triggered this module

Owner UAT found a real Overcurrent Analysis bug:

```
measured current = 2.4 kA primary
CT = 1200 / 1
Buggy result:   relay-equivalent current = 0.002 A
Correct result: 2400 A x (1/1200) = 2.0 A secondary
```

`app.domain.overcurrent.convert_to_relay_secondary()` multiplied the raw
channel value (`2.4`) directly by the CT ratio, treating "2.4" as if it
were already 2.4 amperes rather than 2.4 **kilo**amperes — its own
docstring at the time explicitly (and incorrectly) waved off the gap.
The owner's explicit instruction was to fix this **without** a private
`kA * 1000` special case in Overcurrent — to treat it as a shared
engineering-unit architecture gap, since the identical mistake is
possible anywhere a kV/MW/Mvar/MVA-labelled value is combined with a
number that assumes a specific base unit (CT/VT ratios, Distance
impedance, Differential comparison, future Power calculations).

## Engineering Quantity vs Measured Unit

Two distinct concepts, already established by `app.domain.
channel_classification` (DEC-077/DEC-080) and reused, never
re-invented, here:

- **Engineering Quantity** — what is being measured: `Voltage`,
  `Current`, `Active Power`, `Reactive Power`, `Apparent Power`,
  `Frequency`, `ROCOF` (`KNOWN_ENGINEERING_QUANTITIES`). This decides
  which unit family is even legal.
- **Measured Unit** — how the channel's own numbers are scaled: `V` vs
  `kV` vs `MV` for a Voltage channel, `A` vs `kA` for a Current channel,
  etc. (`MEASURED_UNIT_OPTIONS`, keyed by Engineering Quantity).

Unit normalization is always **quantity-aware**: the same string `"M"`
prefix means something different (and is only legal at all) within the
unit family a given Engineering Quantity actually supports — there is
no quantity-agnostic "parse an SI unit" function anywhere in this
module, deliberately.

## Canonical calculation units

Every Engineering Quantity this module knows has exactly one canonical
**calculation** unit — the unit all cross-value arithmetic (CT/VT
ratios, RMS-vs-pickup comparisons, future Distance/Differential/Power
calculations) happens in:

| Engineering Quantity | Canonical calculation unit |
|---|---|
| Voltage | V |
| Current | A |
| Active Power | W |
| Reactive Power | var |
| Apparent Power | VA |
| Frequency | Hz |
| ROCOF | Hz/s |

The canonical calculation unit is **independent of the display unit**.
A channel declared `2.4 kA` is genuinely `2400 A` internally for any
calculation that needs dimensional consistency (CT ratio application,
pickup comparison) — but the UI continues to display `2.4 kA`
(`measured_rms_current`/`measured_rms_current_unit` on the Overcurrent
result, for example, are unchanged: still the original source value and
unit). Canonical conversion is for **calculation**, never for
**presentation** — see "Display vs calculation units" below.

## Supported unit families and aliases

`app.domain.engineering_units._ALIASES` is a closed, per-quantity table
— not generic SI-prefix parsing. Every recognized string maps to
`(canonical_unit, scale_to_canonical)`:

| Quantity | Recognized units | Scale to canonical |
|---|---|---|
| Current | `A`/`a`, `kA`/`KA`/`ka` | 1, 1 000 |
| Voltage | `V`/`v`, `kV`/`KV`/`kv`, `MV`/`Mv`/`mv` | 1, 1 000, 1 000 000 |
| Active Power | `W`/`w`, `kW`/`KW`/`kw`, `MW`/`Mw`/`mw`, `GW`/`Gw`/`gw` | 1, 1e3, 1e6, 1e9 |
| Reactive Power | `var`/`VAR`/`Var`, `kvar`/`kVAR`/`KVAR`, `Mvar`/`MVAR`/`mvar`, `Gvar`/`GVAR`/`gvar` | 1, 1e3, 1e6, 1e9 |
| Apparent Power | `VA`/`va`, `kVA`/`KVA`/`kva`, `MVA`/`Mva`/`mva`, `GVA`/`Gva`/`gva` | 1, 1e3, 1e6, 1e9 |
| Frequency | `Hz`/`hz`/`HZ` | 1 |
| ROCOF | `Hz/s` | 1 |

Every recognized alias also normalizes to **one canonical spelling** per
quantity (e.g. `var`/`VAR`/`Var` all normalize to the canonical `var`;
`kvar`/`kVAR`/`KVAR` all normalize to `kvar`) — this is what the task's
"accepting VAR/kVAR/KVAR/MVAR/GVAR aliases into one canonical spelling"
requirement means in practice.

Anything not in this table (unrecognized unit, blank unit, `None` unit,
or a unit belonging to a *different* quantity's family, e.g. `"kV"`
passed for `Current`) is **never guessed** — it resolves to
`normalization_status = "unsupported"`, `canonical_unit = None`,
`scale_to_canonical = None`. Leading/trailing whitespace is stripped
before lookup; internal casing is not otherwise altered (see next
section).

## Prefix/case handling policy — the critical safety rule

**This module does NOT do generic `raw_unit.lower()` then derive a
multiplier.** Real recorded files carry inconsistent casing — `KA`/`ka`
for kiloamperes, `mw` sometimes meaning *mega*watt rather than
*milli*watt depending on the source device's own labelling convention —
so a blind case-fold-then-SI-prefix-lookup would be actively unsafe in
this domain (a wrong guess is a silent 10⁶x error, not a crash).

Instead, `_ALIASES` is a **deliberate, closed, quantity-aware alias
table** where every entry has already committed to one explicit
interpretation. The power-system-specific policy this table encodes:
lowercase `m`/`M`/`g`/`G` prefixes **always** mean mega/giga in this
domain (`mw` = megawatt, `mvar` = megavar, `mva` = mega-volt-ampere) —
**never** milli, because milli-scale power/current/voltage readings do
not occur in the recordings this system processes. Any prefix/casing
combination the table does not explicitly list is refused
(`unsupported`), never silently resolved by a generic rule.

## Normalization status vocabulary

`parse_engineering_unit(engineering_quantity, raw_unit)` returns a
`ParsedEngineeringUnit` with `normalization_status` one of:

- **`exact`** — the (whitespace-stripped) input is already byte-identical
  to the table's own canonical-cased spelling for that entry (e.g. raw
  `"kA"` — the table's own canonical form for that entry IS `"kA"`).
- **`normalized_alias`** — the input needed a case/spelling correction
  to reach the canonical form (e.g. `"KA"`, `"ka"` -> `"kA"`).
- **`unsupported`** — blank/`None`/unrecognized/wrong-quantity unit.
  Never guessed at; callers must treat this as a needs-configuration
  condition, not fall back to assuming a default unit.
- **`ambiguous`** — reserved for a future quantity/prefix combination
  this table would explicitly decline to resolve one way (the concept
  the task's own spec asked to leave room for). No alias entry
  currently seeded in `_ALIASES` actually produces this status, since
  every entry already commits to one explicit interpretation per the
  policy above — it exists in the type/status vocabulary for forward
  compatibility, not because a live ambiguous case exists today.

## Active/Reactive/Apparent Power stay distinct Engineering Quantities

`Active Power`, `Reactive Power`, and `Apparent Power` share the same
broad `POWER` category in `app.domain.channel_classification` (used for
generic UI-facing bucketing), but they are three **separate** Engineering
Quantities and are never arithmetic-interchangeable merely because W/
var/VA share SI dimensions. `100 MW + 20 Mvar` is not a valid operation
in this codebase's model — combining them meaningfully requires an
explicitly-defined complex-power-aware operation, which does not exist
here yet. `Apparent Power` (`ENGINEERING_QUANTITY_APPARENT_POWER =
"Apparent Power"`) was added as a first-class Engineering Quantity by
this same change (previously reachable only via the generic broad
`POWER` category, with no controlled unit list of its own) —
`MEASURED_UNIT_OPTIONS[ENGINEERING_QUANTITY_APPARENT_POWER] = ("",
"VA", "kVA", "MVA", "GVA")`.

## Display vs calculation units

Canonical conversion exists **only** for calculations that require
dimensional consistency across values with potentially different
declared units (CT/VT ratio application, a pickup comparison, a future
Distance V/I -> Ω calculation). It is never applied to presentation:
Related Waveforms, waveform/table/cursor values, and Phasor magnitude
output all continue to display the value in its own original source
unit (`2.4 kA` stays displayed as `2.4 kA`) — see the per-consumer audit
below for exactly which surfaces do/don't touch this module.

## API

`backend/app/domain/engineering_units.py`:

- `parse_engineering_unit(engineering_quantity, raw_unit) ->
  ParsedEngineeringUnit` — the core parse/classify function.
- `scale_to_canonical(engineering_quantity, raw_unit) -> float | None`
  — convenience wrapper, `None` for any unsupported/ambiguous status.
- `convert_value_to_canonical(value, engineering_quantity, raw_unit) ->
  float | None` — `None` if `value` is `None`/non-finite or the unit is
  unresolvable; otherwise `value * scale`.
- `convert_array_to_canonical(values, engineering_quantity, raw_unit) ->
  np.ndarray | None` — array counterpart; `None` under the same
  guardrail; never mutates the input array (`astype(..., copy=True)`);
  NaN propagates through the multiply, never coerced to zero/dropped.

## Per-consumer audit and migration status

| Consumer | Status | Notes |
|---|---|---|
| **Overcurrent** (`app.domain.overcurrent`) | **Fixed (DEC-091)** | `convert_to_relay_secondary()`/`convert_array_to_relay_secondary()` now normalize via this module before applying the CT ratio. See [OVERCURRENT_ANALYSIS.md](OVERCURRENT_ANALYSIS.md). |
| **Per Unit** (`app.domain.per_unit`) | SAFE — normalized, partially migrated | Already unit-aware pre-existing (`VOLTAGE_UNIT_SCALE`/`CURRENT_UNIT_SCALE`, fail-closed). The scale *values* (1000.0 etc.) are now sourced from this module (`parse_engineering_unit(...).scale_to_canonical`) so the number is typed once, not three times across the codebase. The *lookup breadth* stays PU's own: PU case-folds its whole key (`.strip().lower()`), accepting any casing of `v`/`kv`/`a`/`ka` (e.g. `"Kv"`), which is intentionally more permissive than this module's own quantity-aware exact-alias table — a full call-through migration would have silently narrowed PU's already-shipped acceptance set, which the owner's "do not change PU's numerical behavior" instruction ruled out. All existing PU tests pass unchanged (byte-for-byte). |
| **Phasor** (`app.domain.phasor`) | SAFE — audited, no change | Never reads a `unit` parameter at all; the service layer attaches `candidate.unit` to the OUTPUT only (`PhasorRoleResult.unit`), with zero cross-unit/cross-channel arithmetic. `162.4 kV` in -> `162.4 kV` out is correct as-is (magnitude is reported with its own unit). This module is available for a *future* Phasor calculation that needs cross-unit arithmetic, but nothing today requires it. |
| **Calculated Channels** (`app.domain.calculated_channel`) | SAFE BUT RESTRICTIVE — audited, unchanged (follow-up candidate) | `units_compatible()` requires EXACT unit-string equality for multi-input operations (`1 kA + 500 A` is rejected outright, never converted). This is safe (never silently combines incompatible values) but more restrictive than necessary. Not changed in this pass — the owner's own instruction was "do not introduce a large redesign if it would expand scope excessively"; a future pass could use this module to accept quantity-compatible + convertible units (normalize, then calculate) instead of exact-string equality, without weakening the existing safety property that genuinely incompatible quantities can never combine. |
| **RMS / waveform / cursor / Related Waveforms** | SAFE — normalized (RMS/PU) or presentation-only (waveform/cursor/Related Waveforms) | `waveform_service.py` routes every PU conversion through `apply_per_unit_to_value()`/`apply_per_unit_to_array()` (already correct). Waveform/cursor/table/Related-Waveforms values are display surfaces — they intentionally preserve/display the source engineering value+unit (`2.4 kA` stays `2.4 kA`), never silently converting for presentation. |
| **CT/VT (Overcurrent's own CT Primary/CT Secondary fields)** | SAFE by product convention | Plain number fields, always ampere-rated by definition (labelled "(A)" in the UI) — they need no unit normalization themselves; only the *measured current* being scaled by them does. |
| **Measurement Groups / voltage_group_config.py / current_group_config.py** | SAFE — pre-existing, not migrated this pass | `_VOLTAGE_UNIT_TO_KV`/`_CURRENT_UNIT_TO_KA` are their own independently-duplicated V/kV, A/kA scale lookups, structurally the same duplication pattern this module was created to stop. Not migrated in this pass (out of the explicit task scope — PU was the only consumer named for migration); flagged here as a known follow-up so a future change doesn't reintroduce a fourth copy of the same table. |
| **Future analyzers** (Distance, Differential, Sequence Components, further Power calculations) | Guardrail established | See "Future-analyzer invariant" below. |

## Future-analyzer invariant

> **Any Analysis calculation combining or comparing engineering
> quantities must first establish quantity compatibility and canonical-
> unit normalization**, using `app.domain.engineering_units` — never a
> private, per-analyzer unit-scale dictionary.

Examples this invariant is meant to prevent re-deriving from scratch:

- **Distance** (V/I -> Ω): a Voltage channel and a Current channel must
  each be normalized to their own canonical unit (V, A) before the
  ratio is computed — never assume both channels' raw numbers share a
  base unit.
- **Differential** (compare currents from multiple sources/CTs): every
  input current must be normalized to canonical amperes before
  comparison — mirrors exactly the Overcurrent CT-ratio fix in this
  same change.
- **Power** (V x I -> W/var/VA): both operands normalized to canonical
  units first; the *result*'s Engineering Quantity (Active/Reactive/
  Apparent) must be chosen explicitly by the calculation, never
  inferred from unit spelling alone.

A new analyzer that needs unit-aware arithmetic should add new
Engineering Quantities/aliases to this module (if the quantity doesn't
already exist) rather than declaring its own local scale dictionary —
the entire reason this module exists is that Overcurrent, Per Unit, and
(pre-emptively) Distance/Differential/Power all needed the *same*
V/kV, A/kA-shaped lookup, and had already started duplicating it three
times before this fix.

## Numeric golden tests

Verified in `backend/tests/test_engineering_units.py` (Engineering
Quantity level) and `backend/tests/test_overcurrent_domain.py` /
`test_overcurrent_analysis_service.py` / `test_overcurrent_analysis_api.py`
(end-to-end through Overcurrent):

| Input | Output |
|---|---|
| 2.4 kA | 2400 A |
| 275 kV | 275 000 V |
| 100 MW | 100 000 000 W |
| 35 Mvar | 35 000 000 var |
| 120 MVA | 120 000 000 VA |
| 500 kVA | 500 000 VA |
| 2.4 kA primary, CT 1200:1, pickup 0.8 A secondary | relay current 2.0 A, pickup multiple 2.5x |
