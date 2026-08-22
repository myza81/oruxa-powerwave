# Powerwave Per-Unit Measurement Model

Status: AUTHORITATIVE PRODUCT / ENGINEERING REQUIREMENT

This document defines the intended Per-Unit behaviour for
`oruxa_powerwave`.

It is the common reference for Claude, Codex and future development
agents. Before making any change related to Per-Unit, Voltage Base,
Current Base, measurement grouping, voltage-reference detection, PU
waveform display, PU significant-value reporting, or calculated-channel
PU behaviour, read this document in full.

Where existing code, tests, DEC-049 implementation details, or older
project-memory content conflict with this document, **the conflict must
be reported before implementation**. Existing behaviour must not
automatically be treated as authoritative merely because it is already
implemented or already covered by passing tests. Do not silently
reinterpret ambiguous requirements — surface the ambiguity and ask.

This document distinguishes, throughout, between:

- **`CURRENT IMPLEMENTATION`** — what is actually deployed today (DEC-049
  and its source-bound addendum), verified directly against the code as
  of 2026-08-22.
- **`APPROVED / CLARIFIED TARGET MODEL`** — the direction described in
  this document, approved as product/engineering direction (DEC-050) but
  **not yet implemented**.

Do not treat a `TARGET MODEL` section as already built. Do not treat a
`CURRENT IMPLEMENTATION` section as the final design.

---

## 1. Fundamental purpose

`oruxa_powerwave` (Powerwave) is a **disturbance-record analysis
application** — it is NOT a power-flow solver, a protection-relay
setting tool, or a network-modelling product. Its job is to help an
engineer look at a recorded disturbance (a COMTRADE file today; other
formats later) and understand what happened.

Per-Unit is an **interpretation/normalization layer over disturbance
measurements** — a way of re-expressing an already-recorded engineering
value against a chosen reference, for comparison and severity judgement.
It is not a simulation, not a power-flow quantity, and it never replaces
the actual recorded measurement.

**Actual engineering-unit values must always remain available.** A
Per-Unit value is a second, optional lens on the same data — never a
replacement for it.

Worked examples this document treats as the standing reference cases:

```text
Fault current = 31.0 kA RMS
```

optionally shown alongside:

```text
Fault current = 10.0 pu on an equipment rated-current base
```

and:

```text
275 kV voltage minimum = 192.5 kV = 0.70 pu
132 kV voltage minimum = 105.6 kV = 0.80 pu
```

These quantities may all originate from **the same disturbance
recording**, at the same instant, from different measurement points.

---

## 2. Critical requirement: ONE FILE ≠ ONE PU BASE

A single COMTRADE/CSV disturbance record may come from a disturbance
recorder installed at a 275/132 kV substation and may contain:

```text
275 kV lines
275 kV bus voltages
275/132 kV interbus transformer HV currents
275/132 kV interbus transformer LV currents
132 kV bus voltages
132 kV lines
other monitored bays
```

Therefore **one source may legitimately contain**:

- multiple voltage levels
- multiple voltage measurement groups
- multiple current measurement groups
- multiple equipment capacities
- multiple current bases

This is a **core requirement** and must not be simplified away in any
future implementation. See §20 for why the currently deployed model does
not yet satisfy this.

---

## 3. Canonical conceptual hierarchy (`TARGET MODEL`)

```text
Workspace
   ↓
Recording / Source
   ↓
Measurement Groups
   ↓
Channels
   ↓
Applicable Base Configuration
```

The source/file is the **container and ownership boundary**. It is
**NOT** itself the single PU base configuration.

The following mental model is explicitly **incorrect** as a long-term
target, even though it is what is currently implemented (§20):

```text
Source
   ↓
one Vbase
one Ibase
```

---

## 4. Measurement Group concept (`TARGET MODEL`)

A **Measurement Group** is a set of channels representing one
meaningful electrical measurement context — normally one three-phase
(or single) voltage or current measurement at one point in the plant.

Examples:

```text
NORTH BUS VOLTAGE
VR / VY / VB
```

```text
IBT1 HV CURRENT
IR / IY / IB
```

```text
IBT1 LV CURRENT
IR / IY / IB
```

```text
132 kV LINE A CURRENT
IR / IY / IB
```

Groups within the same source may have different base values. The
future data model should support this even though the currently
deployed DEC-049 implementation does not (§20/§22).

---

## 5. Voltage-group requirements (`TARGET MODEL`)

Different voltage measurement groups within one source can have
different Vbase.

Example:

```text
275 kV BUS group
Vbase = 275 kV

132 kV BUS group
Vbase = 132 kV
```

This allows the same event to report:

```text
275 kV bus → 0.70 pu
132 kV bus → 0.80 pu
```

using the appropriate base for each measurement group, in the same
recording, at the same time.

---

## 6. Voltage reference interpretation

This section is especially load-bearing and must not be simplified.

If channels are represented **individually as phases**:

```text
VR
VY
VB
```

or:

```text
VA
VB
VC
```

these normally represent **phase-to-ground / line-to-ground voltage**.
For example:

```text
VR = R phase to ground
VY = Y phase to ground
VB = B phase to ground
```

They must **NOT** be treated as line-to-line merely because all three of
R/Y/B (or A/B/C) exist together as a set.

By contrast, explicitly paired channel names:

```text
VRY
VYB
VBR
```

or:

```text
VAB
VBC
VCA
```

represent **phase-to-phase / line-to-line voltage**.

Generic channels such as:

```text
VBUS
BUS VOLTAGE
275KV BUS
```

without phase-specific representation may be treated as likely
line-to-line where appropriate, but automatic inference must always
remain overrideable by the engineer.

**`CURRENT IMPLEMENTATION` note**: `app.domain.voltage_reference`
already implements exactly this individual-phase-vs-paired-phase
naming distinction (verified directly in code, 2026-08-22) — VR/VY/VB,
VA/VB/VC, VAN → Line-to-Ground; VRY/VYB/VBR, VAB/VBC/VCA, VLL/VBUS →
Line-to-Line. This part of the detection logic is **already correct
per this document** and does not need to change. What is not yet
correct is *how the detected reference is used* for a Voltage channel's
own division — see §8.

---

## 7. Automatic detection + engineer authority

**Principle**: Powerwave should automatically infer obvious measurement
representation and grouping, but automation must never remove the
engineer's authority to correct it.

The UI should distinguish:

```text
Auto: Phase-to-Ground
```

from:

```text
Manual: Phase-to-Ground
```

and support:

```text
Override
Return to Auto
```

If detection is uncertain or conflicting: **do not silently guess**.
Record the ambiguity and require/allow engineer intervention.

**`CURRENT IMPLEMENTATION` note**: this principle is already
implemented for Voltage Reference at the source level — "Auto: X",
"Manual: X [Return to Auto]", and an honest "Automatic detection
unavailable" fallback all exist today (DEC-049 addendum). The target
model in §4/§5 extends this same principle to the measurement-group
level, not just the source level — the principle itself does not
change, only its scope.

---

## 8. Voltage PU mathematics — `[OPEN] Needs code/math review before implementation approval`

This is an explicit, currently-unresolved review item. **Do not decide
this from historical implementation alone** — the point of this section
is to record the requirement and the current gap plainly, not to
resolve it unilaterally.

**Worked scenario:**

```text
Nominal system base = 275 kV line-to-line

Healthy phase-to-ground measured waveform ≈ 158.8 kV
```

**Expected result:**

```text
≈ 1.0 pu
```

because the applicable phase voltage base is approximately:

```text
275 / √3 = 158.8 kV
```

**The engineering requirement is:**

> Healthy phase-to-ground voltage on a nominal 275 kV system should
> display approximately 1.0 pu when the nominal system base is entered
> as 275 kV LL.

**`[FACT]` — verified directly against `backend/app/domain/per_unit.py`
on 2026-08-22:** the currently deployed `resolve_per_unit()` computes a
Voltage channel's own PU base as `voltage_base_volts(profile)` — the
raw entered Vbase value, with **no adjustment for the channel's own
voltage reference**. `voltage_reference`/`√3` is consulted **only**
inside `resolve_current_base_amps()`, when deriving Ibase from Sbase —
never when dividing a Voltage channel's own measured value by its base.

**Consequence of the current implementation, worked through the
scenario above**: an engineer enters `Vbase = 275 kV` (intending the
nominal system LL base) against a phase-to-ground channel measuring
≈158.8 kV. The current code computes `158.8 / 275 ≈ 0.577 pu`, not the
expected `≈1.0 pu`.

**This is a documented architectural mismatch with the clarified
requirement above, not yet confirmed as a defect requiring a specific
fix** — multiple resolutions are possible and none is authorized by this
document:

- The applicable base for a phase-to-ground channel could be derived as
  `Vbase_LL / √3` when the channel's own resolved voltage reference is
  Line-to-Ground (mirroring the *shape* of the existing Ibase-derivation
  logic, but applied to the Voltage channel's own division — this is
  still "select the correct same-reference base," not "apply √3 to the
  measured value," and needs to be worded and reviewed carefully so it
  is never confused with decision 3's original "never auto-√3 a
  measured value" rule, which was about not fabricating an LL-equivalent
  measurement, not about which base a division uses).
  This document does not authorize this fix,
  and this document does not claim it is the correct one.
- The engineer could instead be asked to enter the base in the same
  reference as the channel (i.e. a phase base for a phase-to-ground
  channel, an LL base for a line-to-line channel) — a UX/product
  question, not purely a math one.
- Something else the owner has not yet specified.

**Required next step**: independent architecture/code review against
this document (the task explicitly authorized after this documentation
pass — see [HANDOFF.md](HANDOFF.md)), followed by an owner decision,
before any code changes. Do not implement any of the above without that
review and an explicit approval.

---

## 9. Current groups (`TARGET MODEL`)

Current base is **NOT** source-wide.

Example:

```text
IBT1 HV IR/IY/IB
```

is one current measurement group.

```text
IBT1 LV IR/IY/IB
```

is another.

They may belong to the same transformer and the same COMTRADE file but
require different current bases (different sides of a transformer
normally have different rated currents for the same MVA).

---

## 10. Preferred Current Base interpretation

The preferred engineering interpretation for equipment-related current
normalization is generally **equipment rated current**, derived from:

```text
Ibase = Sbase / (√3 × Vbase_LL)
```

Example for a 1000 MVA transformer:

```text
500 kV side:
Ibase ≈ 1.155 kA

275 kV side:
Ibase ≈ 2.099 kA
```

This supports event reporting such as:

```text
Fault current = 31.0 kA RMS
Fault current = 14.8 pu on equipment rated-current base
```

**Wording note**: the more precise phrase is:

```text
times rated current
```

rather than:

```text
times equipment capacity
```

— because the ratio being reported is current/current, not power-based.

**`CURRENT IMPLEMENTATION` note**: `Ibase = Sbase / (√3 × Vbase_LL)` is
already implemented exactly as written above (`resolve_current_base_amps()`
in `app/domain/per_unit.py`, verified 2026-08-22) and is unaffected by
the §8 review — the formula itself is correct; §8 only concerns a
Voltage channel's own division, never the Ibase derivation formula.

---

## 11. CT ratio interpretation

**CT primary rating ≠ automatically equipment Ibase.**

CT ratio represents measurement/protection transformation and may not
equal the equipment's own rated current.

Example:

```text
equipment rated current = 2.1 kA
CT = 4000/1 A
```

Using 4 kA as the PU base would express **"multiple of CT primary
nominal current,"** not **"multiple of equipment rated current."** These
are different engineering statements and must never be silently
conflated.

Possible roles for CT information in the target architecture:

- waveform scaling
- metadata
- validation
- grouping hints
- diagnostics
- an explicitly chosen alternative base, if ever approved

CT rating must **not** silently become the default PU equipment base.

---

## 12. Current-base flexibility (`TARGET MODEL`)

Each current measurement group may need an independent base method.
Potential model:

```text
1. Equipment rating
   Sbase + applicable Vbase → Ibase

2. Manual Ibase
   engineer enters known base current

3. CT primary reference
   optional explicit alternative, if ever approved

4. Not configured
   current remains without PU normalization
```

Do **not** state that every current group must have an Sbase.
Transmission lines and other contexts may use different engineering
reference choices. The architecture must remain flexible enough to
support all four modes above per group, not just per source.

**`CURRENT IMPLEMENTATION` note**: modes 1 ("derived"), 2 ("direct"),
and 4 ("none") already exist today, but scoped to one current base per
*source*, not per current measurement *group* (§20/§22). Mode 3 (CT
primary reference) does not exist in any form today and is not
authorized by this document — it is recorded here only as a possible
future option, `[PROPOSAL]`, not a requirement.

---

## 13. Actual values and PU values coexist

**PU must never destroy or overwrite original engineering-unit
measurements.**

Powerwave must remain able to show:

```text
31.0 kA
```

and:

```text
10.0 pu
```

for the same measurement. Similarly:

```text
192.5 kV
```

and:

```text
0.70 pu
```

Switching:

```text
Engineering Units ⇄ Per Unit
```

must be reversible and deterministic. Original imported data remains
immutable.

**`CURRENT IMPLEMENTATION` note**: this principle is already correctly
implemented — `ww.unitMode` is pure frontend presentation state, the
backend never mutates the retained `DisturbanceRecord`, and every
conversion is computed fresh per request from the immutable engineering
array (DEC-049, decision 1/2). This part of the current implementation
is consistent with the target model and does not need to change.

---

## 14. Significant-value interpretation (product context, not yet authorized)

The long-term value of PU is not merely changing axis labels. It should
eventually support event interpretation such as:

```text
VOLTAGE DIP

275 kV Bus
Minimum RMS: 192.5 kV
Minimum PU: 0.70 pu
```

and:

```text
FAULT CURRENT

IBT1 HV Phase R
Maximum RMS: 31.0 kA
Equipment-base current: 2.10 kA
Severity: 14.8 pu
```

This is consistent with Powerwave's purpose of extracting meaningful
disturbance values from a recording. **Do not implement this reporting
yet** unless separately approved — it is recorded here as product
context for the architecture, `[PROPOSAL]`, not a current requirement.

---

## 15. Automatic grouping principle (`TARGET MODEL`)

Powerwave should attempt to discover obvious measurement groups
automatically using:

- engineering type
- channel names
- common prefixes
- phase suffixes
- source metadata
- bay/equipment naming patterns

Examples:

```text
IBT1 HV IR
IBT1 HV IY
IBT1 HV IB
```

→ suggest:

```text
IBT1 HV CURRENT
```

```text
IBT1 LV IR
IBT1 LV IY
IBT1 LV IB
```

→ suggest a **different** group.

```text
NORTH BUS VR
NORTH BUS VY
NORTH BUS VB
```

→ suggest:

```text
NORTH BUS VOLTAGE
```

Automatic grouping is a **productivity feature, not final authority** —
it must always be correctable per §16.

---

## 16. Engineer correction capability (`TARGET MODEL`)

The target architecture must not make grouping irreversible. Future
functionality should be capable of supporting:

- move channel between groups
- split a group
- merge compatible groups
- create a group manually
- rename display group
- change Vbase
- change current-base method
- override voltage reference

These capabilities do not all need to appear in the first implementation
UI. Use progressive disclosure (§17).

---

## 17. UI principle

Approved UI philosophy:

> **Simple by default, flexible by structure.**

Do not make the form so simple that future legitimate engineering cases
become impossible. Do not make the default view so complex that
ordinary recordings become difficult to configure.

Conceptual direction only (not an implementation specification):

```text
Recording: SUBSTATION_EVENT.cfg

VOLTAGE GROUPS

275 kV NORTH BUS
VR · VY · VB
Vbase: 275 kV
Reference: Auto — Phase-to-Ground
[Edit]

132 kV SOUTH BUS
VR · VY · VB
Vbase: 132 kV
Reference: Auto — Phase-to-Ground
[Edit]


CURRENT GROUPS

IBT1 HV CURRENT
IR · IY · IB
Base: Equipment Rating
1000 MVA · 275 kV
Ibase: 2.10 kA
[Edit]

IBT1 LV CURRENT
IR · IY · IB
Base: Equipment Rating
1000 MVA · 132 kV
Ibase: 4.37 kA
[Edit]

132 kV LINE A CURRENT
IR · IY · IB
Base: Not configured
[Configure]
```

---

## 18. Identity model (`TARGET MODEL`)

Human-facing names are not reliable internal IDs. Conceptual identity
hierarchy:

```text
workspace_id
source_id
measurement_group_id
channel identity
```

Filename remains a display label. Measurement-group names may also be
display labels. Do not key important relationships solely using:

- filename
- channel text label
- user-facing group name

**`CURRENT IMPLEMENTATION` note**: `workspace_id` + `source_id` as the
stable, non-display identity is already correctly established (DEC-049
addendum — two uploads sharing an identical filename resolve to
independent configurations, verified via direct Playwright testing).
`measurement_group_id` does not exist yet, since measurement groups
themselves do not exist yet (§20).

---

## 19. Calculated-channel implications (`[OPEN]`, requires explicit design/approval)

Calculated channels require separate treatment once measurement groups
exist. This document records the question; it does **not** invent final
semantics.

**Same-group calculation:**

```text
IA + IB
```

may naturally inherit one current group's base.

**Cross-group calculation:**

```text
IBT HV current + IBT LV current
```

may not have one meaningful Ibase.

**Cross-source calculation** may also be ambiguous.

**`CURRENT IMPLEMENTATION` note**: the existing calculated-channel
inheritance rule (`derive_per_unit_profile_id()`, DEC-049 decisions
6/7) already handles an analogous problem one level up — at the
*source* level, not the *measurement-group* level. It inherits a
unary operation's single input's profile verbatim, and inherits an
Addition/Subtraction's profile only when every input resolves to the
exact same profile, otherwise leaving the result `base_required`. When
measurement groups are introduced, this exact same rule shape (verbatim
for unary ops, agreement-required for multi-input ops) is the natural
starting point to extend from `source_id` to `measurement_group_id` —
but this is a `[PROPOSAL]`, not a decision, and must be explicitly
reviewed and approved before implementation, not assumed.

---

## 20. Current Implementation Status

`[FACT]`, verified directly against `backend/app/domain/per_unit.py`,
`backend/app/services/per_unit_registry.py`, `backend/app/domain/
voltage_reference.py`, and `docs/project-memory/DECISIONS.md` (DEC-049
and its 2026-08-22 source-bound addendum), on 2026-08-22:

- Per-Unit configuration is keyed **`source_id → one PU configuration`**
  — one Voltage Base, one Voltage Reference (auto-detected or manually
  overridden), and one Current Base (none/derived/direct) per source,
  applied to **every** eligible Voltage/Current channel of that source.
- There is **no measurement-group concept anywhere in the code** — no
  `measurement_group_id`, no per-group base, no per-group voltage
  reference. A source with channels at two different voltage levels
  (e.g. a 275/132 kV interbus transformer recording) cannot be
  correctly configured today — this is a known, explicitly-deferred
  limitation already recorded in DEC-049's addendum ("a single source
  whose channels span multiple distinct voltage levels is not supported
  this pass").
- Voltage Reference auto-detection already correctly distinguishes
  individual-phase (→ Line-to-Ground) from paired-phase (→ Line-to-Line)
  channel naming (§6), but its result is currently used **only** to
  derive Ibase from Sbase — never to adjust a Voltage channel's own
  division (§8's open gap).
- The backend is the sole conversion authority (one shared
  `app/domain/per_unit.py`, called from all 8 display/measurement
  endpoints) — this part of the architecture is sound and is expected to
  remain the pattern under the target model too.
- Calculated-channel inheritance (`derive_per_unit_profile_id()`, the
  two-axis `mode`/`profile_id` provenance model) is implemented and
  tested at the source level.
- 766 backend tests and 26 frontend regression checks currently pass
  against this source-wide model. **Passing tests confirm the current
  implementation is internally consistent — they do not confirm it is
  the correct final product requirement** (see the status banner above).

---

## 21. Target Model

`[DECISION]` (DEC-050 — approved product/engineering direction;
implementation pending; see [DECISIONS.md](DECISIONS.md)):

```text
source
→ measurement groups
→ group-specific base configuration
```

A source is a container/ownership boundary. Within it, one or more
Measurement Groups (§4) are automatically discovered (§15) or manually
defined (§16), each independently carrying its own Voltage Base /
Voltage Reference / Current Base configuration (§5/§9/§12), with the
engineer always able to override automation (§7/§10/§16) and both
engineering-unit and PU values always available side by side (§13).

**This target model is approved direction. It is not yet implemented.**
Do not begin implementing it without the independent architecture/code
review this document's publication is meant to trigger (see
[HANDOFF.md](HANDOFF.md)).

---

## 22. Known deficiencies / technical debt

Recorded as **architectural mismatches with the clarified requirement**,
not asserted as implementation bugs unless independently confirmed by
code inspection (§8 is the one exception already confirmed by direct
code reading):

- Source-wide Vbase is too restrictive for a recording spanning more
  than one voltage level.
- Source-wide current base is incorrect for multi-bay/multi-side
  recordings (e.g. a transformer's HV and LV sides sharing one source).
- Voltage-reference detection currently operates at the source level;
  the target model requires it to operate in the context of a
  measurement group instead.
- Phase-to-ground PU voltage math needs explicit review before
  implementation approval — `[FACT]`-confirmed gap, see §8.
- Calculated-channel PU inheritance needs review once measurement groups
  exist — see §19.
- Existing tests (`test_per_unit_domain.py`, `test_per_unit_registry.py`,
  `test_per_unit_api.py`, `test_per_unit_display_endpoints.py`,
  `test_frontend_per_unit_mode.py`, `test_voltage_reference.py`) verify
  the CURRENT source-wide model. They are not wrong about what they
  test, but they encode source-wide assumptions that will need
  extension, not just preservation, once measurement groups are
  implemented. Passing today is not evidence the target model is
  unnecessary.
- The current "Manage Per-Unit Bases" UI (recently restructured for
  clarity, see the Phase 5C-UAT-series entries in
  [MIGRATION_PLAN.md](MIGRATION_PLAN.md)) reflects the incomplete
  source-wide architecture — its recent UI/UX cleanup improved
  presentation of the CURRENT model but did not add measurement-group
  capability, and was not intended to.

---

## 23. Relationship to DEC-049

DEC-049 (and its source-bound addendum) remains an accurate record of
what was decided and built at the time, and remains the correct
description of the **currently deployed** behaviour (§20). It is not
being rewritten or discredited by this document.

This document, and the accompanying DEC-050 (see
[DECISIONS.md](DECISIONS.md)), record that the source-bound model DEC-049
describes is **not the final target** for recordings containing
multiple electrical measurement contexts, and sets the direction
described in §21 as the approved future direction — implementation
pending, subject to the independent review this document's publication
triggers, and subject to the open review item in §8.

---

## 24. Scope reminder

This document is a specification. Per the task that produced it, it
does **not** authorize any code change, and no application code,
frontend code, or backend test was modified alongside it. The next
authorized step is an independent architecture/code review against this
document — not implementation (see [HANDOFF.md](HANDOFF.md)).
