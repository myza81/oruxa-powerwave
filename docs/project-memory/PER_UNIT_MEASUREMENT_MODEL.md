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

**Revision note (2026-08-23)**: following further owner clarification,
several sections below that were previously recorded as `[OPEN]` review
items are now resolved as **approved requirements — implementation still
pending**: §8 (voltage PU mathematics), §9/§12 (current-group voltage
linking), §11 (CT/VT scaling separation), §15 (auto-grouping lifecycle),
§19 (calculated-channel inheritance), and a refined domain model added
under §18. This document is a living specification, not a decision log —
the full decision history, including what was previously `[OPEN]` and
when it was resolved, is preserved verbatim in
[DECISIONS.md — DEC-050](DECISIONS.md#dec-050--per-unit-measurement-model-is-clarified-to-be-measurement-group-aware-the-currently-deployed-source-bound-model-dec-049-is-not-the-final-target)
and its 2026-08-23 addendum. **None of these resolutions are
implemented in code yet** — see §25 for the authorized next step
(Slice 1 only).

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

**`[DECISION]` Detection priority (approved 2026-08-23, implementation
pending)**: the detector must prioritize **explicit electrical
representation** over generic location/equipment vocabulary. A name
containing a generic word like "BUS" must never override explicit phase
structure. For example:

```text
NORTH BUS VA
NORTH BUS VB
NORTH BUS VC
```

must still be interpreted as individual phase-to-ground channels — the
presence of the word "BUS" does not make this a line-to-line
measurement. Likewise, explicit pair naming such as:

```text
VAB / VBC / VCA
```

remains explicit line-to-line evidence regardless of any other word
present in the channel name. The governing principle:

```text
explicit phase/pair representation
    > generic equipment/location vocabulary
```

This is a priority rule for resolving what evidence wins when a channel
name contains both kinds of signal — it does not change the underlying
phase-vs-pair classification itself (§6 above, already correctly
implemented, see below). Automatic detection remains overrideable by
the engineer in every case, and uncertain/conflicting detection must
never silently guess (§7).

**`CURRENT IMPLEMENTATION` note**: `app.domain.voltage_reference`
already implements the individual-phase-vs-paired-phase naming
distinction itself correctly (verified directly in code, 2026-08-22) —
VR/VY/VB, VA/VB/VC, VAN → Line-to-Ground; VRY/VYB/VBR, VAB/VBC/VCA,
VLL/VBUS → Line-to-Line. What is not yet correct is *how the detected
reference is used* for a Voltage channel's own division — see §8.

**`[FACT]` — a second, distinct conflict confirmed by direct code
reading on 2026-08-23, against the newly-recorded detection-priority
principle above**: `_classify_one_channel_name()` in
`app/domain/voltage_reference.py` checks its `_LL_EXPLICIT_SUBSTRINGS`
condition (`"BUS"`/`"LL"` appearing *anywhere* in the upper-cased name)
**before** it checks the single-phase-letter (`_LG_SINGLE_TOKENS`) case.
Concretely, for the input `"NORTH BUS VA"`: the substring check matches
`"BUS"` and returns `LINE_TO_LINE` immediately — the function never
reaches the single-phase-letter branch that would otherwise classify
`VA` as Line-to-Ground. This is the exact inversion the detection-
priority principle above forbids ("BUS" overriding explicit phase
structure). This is a confirmed, code-level conflict with this
document, **not fixed here** — it is an implementation detail for
Slice 3 (voltage groups, §24), not this documentation pass or Slice 1.

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

## 8. Voltage PU mathematics — `[DECISION]` approved requirement, implementation pending

**Resolved 2026-08-23** (previously recorded as an `[OPEN]` review item
— see [DECISIONS.md — DEC-050](DECISIONS.md#dec-050--per-unit-measurement-model-is-clarified-to-be-measurement-group-aware-the-currently-deployed-source-bound-model-dec-049-is-not-the-final-target)'s
2026-08-23 addendum for the full decision record). **This is an approved
requirement. It is not yet implemented in code** — see §24 for the
authorized implementation sequence (this is Slice 3 work, not Slice 1).

**The user-facing voltage base is normally the familiar nominal system
line-to-line voltage** — e.g. `500 kV`, `275 kV`, `132 kV`. The engineer
enters this one number regardless of how any individual channel happens
to be wired/measured.

**For a voltage measurement group whose channels represent individual
phase-to-ground quantities** (`VR`/`VY`/`VB` or `VA`/`VB`/`VC`), the
applicable phase base is derived internally as:

```text
Vbase_phase = Vbase_LL / √3
```

For a nominal 275 kV system:

```text
Vbase_LL = 275 kV
Vbase_phase ≈ 158.8 kV
```

A healthy phase-to-ground waveform around 158.8 kV therefore displays
approximately:

```text
1.0 pu
```

**For explicit line-to-line measurements** (`VRY`/`VYB`/`VBR` or
`VAB`/`VBC`/`VCA`):

```text
Vpu = Vmeasured_LL / Vbase_LL
```

— the entered Vbase is used directly, no √3 involved.

**The old blanket rule "never apply √3 to measured voltage division" is
no longer correct as a stated-that-way blanket statement.** The
corrected governing principle is:

> The PU denominator (base) must match the electrical reference of the
> measured channel.

This is a refinement, not a reversal, of the original intent: the
measured value itself is still never multiplied/divided by √3 to
fabricate an LL-equivalent reading from an LG measurement or vice versa
(that part of the original rule's *intent* — "never invent a
measurement that wasn't recorded" — still holds). What changes is that
**selecting the correct denominator** for a phase-to-ground channel now
correctly derives a phase base from the entered LL base, rather than
dividing a phase measurement by the raw LL number.

**`[FACT]` — verified directly against `backend/app/domain/per_unit.py`
on 2026-08-22, unaffected by this decision**: the currently deployed
`resolve_per_unit()` computes a Voltage channel's own PU base as
`voltage_base_volts(profile)` — the raw entered Vbase value, with no
adjustment for the channel's own voltage reference. `voltage_reference`/
`√3` is consulted only inside `resolve_current_base_amps()` (Ibase
derivation), never for a Voltage channel's own division. Worked through
the scenario above: entering `Vbase = 275 kV` against a phase-to-ground
channel measuring ≈158.8 kV currently computes `158.8 / 275 ≈ 0.577 pu`,
not the required `≈1.0 pu`. **This gap is now an approved-but-unbuilt
requirement, not merely an open question** — implementation is Slice 3
(§24), not this documentation pass and not Slice 1.

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

### Applicable Voltage Base for a Current Group — `[DECISION]` approved 2026-08-23, implementation pending

A current measurement group needs an **applicable voltage base** to
derive Ibase (§10), obtained flexibly:

```text
Current Measurement Group
        ↓
Applicable Voltage Base
        ├── link to an existing Voltage Measurement Group
        └── independent/manual Vbase when no suitable voltage group exists
```

Example:

```text
IBT1 HV CURRENT
Sbase = 1000 MVA
Linked voltage group = IBT1 HV / 275 kV
Ibase calculated from 275 kV
```

If the recording does not include the relevant voltage measurement
group, the engineer can still provide:

```text
manual applicable Vbase = 275 kV
```

**Do not force all current groups to depend on a voltage-channel
group** — the manual fallback is not a degraded case, it is a first-
class supported path (a recording may record a bay's current without
also recording its voltage).

---

## 10. Preferred Current Base interpretation

**`[DECISION]` Initial target current-base methods (approved 2026-08-23,
implementation pending)**:

```text
1. Equipment rating
   Sbase + applicable Vbase → Ibase

2. Manual Ibase
   engineer provides the known current base

3. Not configured
   no PU current normalization
```

**CT primary reference is explicitly excluded from this initial list**
— see §11 for why it is deferred, not merely deprioritized. Do not
require Sbase for all equipment categories: some current groups may not
have a meaningful equipment-MVA basis (e.g. a transmission line current
group with no associated transformer rating), and must remain usable
via method 2 (manual Ibase) or method 3 (not configured) without being
forced through method 1.

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

## 11. CT/VT ratio interpretation — `[DECISION]` deferred from initial implementation, approved 2026-08-23

**`[DECISION]` Do NOT include CT primary rating as a PU base method in
the initial measurement-group implementation.** This is a scope
decision, not merely a preference — CT-based basing does not appear in
§10's initial method list at all, and must not be added to Slice 1
through Slice 7 without a separate, explicit owner approval.

**CT primary rating ≠ automatically equipment Ibase.** CT ratio
represents measurement/protection transformation and may not equal the
equipment's own rated current.

Example:

```text
equipment rated current = 2.1 kA
CT = 4000/1 A
```

Using 4 kA as the PU base would express **"multiple of CT primary
nominal current,"** not **"multiple of equipment rated current."** These
are different engineering statements and must never be silently
conflated.

**The governing distinction:**

```text
CT/VT measurement scaling
    ≠
Per-Unit normalization
```

CT ratio answers:

> What primary current does the secondary recorder measurement
> represent?

Example:

```text
CT 2000:1
10 A secondary
→ 20 kA primary
```

The result of that scaling is still an **engineering-unit value** — it
has not become a PU value. Per-Unit answers a different question:

> How large is the primary measured current relative to the applicable
> engineering base?

Example:

```text
20 kA / 2 kA rated current = 10 pu
```

**Similarly, VT ratio is measurement scaling and not itself Vbase** —
the same distinction applies symmetrically to voltage.

Possible roles for CT/VT information in the target architecture, none
authorized by this document:

- primary/secondary scaling
- metadata
- validation
- grouping hints
- diagnostics
- an explicitly chosen alternative base, if ever separately approved in
  the future

CT/VT rating must **not** silently become the default PU equipment
base.

### The measurement pipeline — layers that must stay separate

```text
RAW / RECORDER MEASUREMENT
        ↓
Measurement scaling
CT / VT ratio where applicable
        ↓
PRIMARY ENGINEERING VALUE
A, kA, V, kV
        ↓
Disturbance analysis
RMS, peak, voltage recovery, etc.
        ↓
Per-Unit normalization
group-specific Vbase / Ibase
        ↓
pu
```

The architecture must keep these concepts separate. **Do not merge
primary/secondary (CT/VT) scaling into the PU feature** — they are
different layers of the same pipeline, each already has (or will have)
its own home: CT/VT scaling is a measurement/import-time concern
(outside this document's scope), disturbance analysis (RMS, peak) is
the existing Calculated Channels / annotation machinery (DEC-047/
DEC-048), and Per-Unit normalization is this document's own layer,
applied last, on top of an already-correct primary engineering value.

---

## 12. Current-base flexibility (`TARGET MODEL`)

Each current measurement group may need an independent base method. Per
§10's decided initial method list:

```text
1. Equipment rating
   Sbase + applicable Vbase → Ibase

2. Manual Ibase
   engineer enters known base current

3. Not configured
   current remains without PU normalization
```

CT primary reference is deliberately **not** in this list — see §11.

Do **not** state that every current group must have an Sbase.
Transmission lines and other contexts may use different engineering
reference choices. The architecture must remain flexible enough to
support all three modes above per group, not just per source.

**`CURRENT IMPLEMENTATION` note**: modes 1 ("derived"), 2 ("direct"),
and 3 ("none") already exist today under those internal names, but
scoped to one current base per *source*, not per current measurement
*group* (§20/§22), and with no voltage-group-linking or manual-Vbase-
fallback concept (§9) since no measurement group exists to link from or
to.

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

### Grouping lifecycle — `[DECISION]` approved 2026-08-23, implementation pending

Automatic grouping exists to reduce repetitive work. **Do NOT require
manual confirmation for every obvious phase set before the engineer can
configure it.** Instead, use this lifecycle:

```text
Powerwave detects group
        ↓
Suggested
        ↓
Engineer reviews/configures base and saves
        ↓
Confirmed
```

High-confidence suggestions may appear automatically, already grouped,
in the configuration UI — the engineer's own act of reviewing/
configuring/saving a group's base is what promotes it from `Suggested`
to `Confirmed`, not a separate, redundant "yes this is really a group"
confirmation step.

**Uncertain or contradictory grouping must appear as `Needs review`**
and must **not** silently drive PU conversion — a channel in a
`Needs review` group behaves like an unconfigured/`base_required`
channel until the engineer resolves the ambiguity, exactly as an
individual channel's conflicting voltage-reference evidence already
does today (§7). The engineer must always be able to correct group
membership later (§16), regardless of a group's current lifecycle
state.

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

### Refined conceptual domain model — `[DECISION]` approved 2026-08-23, implementation pending

The target domain model avoids one generic base object containing many
irrelevant nullable fields (e.g. a single record with both
voltage-only and current-only fields, most of them `null` for any given
row). Preferred conceptual structure — **conceptual, not a forced
class/file structure**; the implementation should stay minimal and
appropriate to the existing codebase's own conventions:

```text
MeasurementGroup
├── id
├── source_id
├── kind: voltage | current
├── display_name
├── channel_refs
├── grouping_status
└── type-specific configuration
```

Voltage group configuration:

```text
VoltageBaseConfiguration
├── nominal_voltage_ll_kv
├── reference_mode: auto | manual
├── reference: line_ground | line_line
└── detection evidence/status
```

Current group configuration:

```text
CurrentBaseConfiguration
├── method: equipment_rating | manual | none
├── equipment_rating_mva?
├── linked_voltage_group_id?
├── manual_voltage_base_kv?
└── manual_ibase_ka?
```

`grouping_status` is the lifecycle state from §15's own grouping
lifecycle (`suggested` / `confirmed` / `needs_review`). `channel_refs`
reuses the existing `ChannelRef` type already established in
`app.domain.calculated_channel` (§18's own identity-hierarchy
principle: group membership is keyed by stable channel identity, never
by display label).

---

## 19. Calculated-channel implications — `[DECISION]` initial rule approved 2026-08-23, implementation pending

For the **first group-aware implementation**, use the conservative
rule:

```text
same-group calculation
→ may inherit that measurement group's base
```

Examples, provided all required inputs resolve to the same compatible
measurement group:

```text
-IA
abs(IA)
IA + IB
```

For **cross-group**, **cross-source**, or otherwise **incompatible-base**
calculated channels, do **NOT** invent a PU base. The preferred initial
result is:

```text
base_required
```

or an equivalent PU-unavailable state — never an arbitrary pick among
candidate groups, and never a silent fallback to engineering units
without saying so.

```text
Cross-group calculation:

IBT HV current + IBT LV current

→ may not have one meaningful Ibase → base_required
```

**Final advanced cross-group semantics can be designed later**, if a
real engineering use case requires them — this document does not
attempt to solve that now, and no such use case has been approved.

**`CURRENT IMPLEMENTATION` note**: the existing calculated-channel
inheritance rule (`derive_per_unit_profile_id()`, DEC-049 decisions
6/7) already implements exactly this same shape one level up — at the
*source* level, not the *measurement-group* level. It inherits a unary
operation's single input's profile verbatim, and inherits an
Addition/Subtraction's profile only when every input resolves to the
exact same profile, otherwise leaving the result `base_required`. The
decision above confirms this is also the correct shape at the
measurement-group level: **the same function, extended from `source_id`
to `measurement_group_id`, is the approved direction** — no new
inheritance algorithm needs to be invented, only the identity it keys
on needs to change, in Slice 7 (§24), not Slice 1.

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
  division — §8's now-resolved (but not yet implemented) requirement.
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
code inspection (§8 and the §6 detection-priority finding below are
confirmed by direct code reading; both now have an approved-but-unbuilt
resolution, not merely an open question):

- Source-wide Vbase is too restrictive for a recording spanning more
  than one voltage level.
- Source-wide current base is incorrect for multi-bay/multi-side
  recordings (e.g. a transformer's HV and LV sides sharing one source).
- Voltage-reference detection currently operates at the source level;
  the target model requires it to operate in the context of a
  measurement group instead.
- Phase-to-ground PU voltage math does not yet implement the approved
  LL/LG-aware base resolution — `[FACT]`-confirmed gap, resolution
  approved, implementation pending (Slice 3), see §8.
- Calculated-channel PU inheritance needs review once measurement groups
  exist — see §19 (initial rule now decided: same-group only,
  `base_required` otherwise; extension of the existing source-level
  function, not a new algorithm).
- `_classify_one_channel_name()` in `backend/app/domain/
  voltage_reference.py` checks generic `"BUS"`/`"LL"` substring evidence
  before the single-phase-letter case, so a name like `"NORTH BUS VA"`
  is currently misclassified as Line-to-Line — `[FACT]`-confirmed gap
  against the detection-priority principle in §6, see §6 for the full
  finding. Not fixed in this pass; Slice 3 work.
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
pending. DEC-050's 2026-08-23 addendum resolved most of what was
previously open (§8, §9/§12, §11, §15, §19, and the domain-model
refinement in §18) into approved-but-unbuilt requirements, per DEC-050's
own addendum in [DECISIONS.md](DECISIONS.md).

---

## 24. Revised implementation sequence (Slices 1–8)

`[DECISION]` approved 2026-08-23 — sequencing only, not an
authorization to begin more than Slice 1 (§25):

```text
Slice 1 — Measurement-group domain model + identities + invariants
          No conversion behaviour change yet.

Slice 2 — Deterministic automatic grouping
          suggested / confirmed / ambiguous states

Slice 3 — Voltage groups
          corrected voltage-reference detection
          correct LL/LG PU base resolution

Slice 4 — Current groups
          equipment-rating/manual/not-configured methods
          voltage-group linking + manual Vbase fallback

Slice 5 — Group-aware PU resolution
          waveform and measurement/display endpoints

Slice 6 — Frontend group-based configuration workspace

Slice 7 — Calculated-channel same-group inheritance
          conservative base_required handling for incompatible cases

Slice 8 — migration, regression, performance verification and UAT
```

Each slice requires its own review/approval before implementation
begins, per the change-governance rule in
[CLAUDE.md](../../CLAUDE.md)/[AGENTS.md](../../AGENTS.md) — this
sequence is not a standing authorization to proceed slice-by-slice
without further approval.

---

## 25. Slice 1 scope — the only authorized next implementation step

**The next authorized implementation work, when separately instructed,
is Slice 1 only: Measurement-group domain model + identities +
invariants.** This document does not itself authorize starting Slice 1
— per its own governing task, "the final Slice 1 implementation prompt
will be issued separately after documentation is committed."

**Slice 1 must NOT yet change:**

- voltage PU math
- current PU math
- waveform display
- API behaviour, unless strictly internal scaffolding is required
- frontend UI
- grouping algorithm
- calculated-channel behaviour

The objective is to introduce the correct internal concept **safely**
before changing any observable behaviour — Slice 1 is additive
scaffolding, not a behavior change.

**Expected concerns for Slice 1:**

```text
workspace ownership
source ownership
stable measurement_group_id
group kind: voltage/current
channel membership
no channel silently belonging to incompatible duplicate groups
group status
group lifecycle when source/workspace is removed
clean invariants
```

---

## 26. Scope reminder

This document is a specification. Per the task that produced this
document and the 2026-08-23 revision, neither authorizes any code
change — no application code, frontend code, or backend test was
modified alongside either. The next authorized step is Slice 1 only
(§25), issued as a separate, explicit implementation prompt — not a
general go-ahead to implement this document's remaining sections (see
[HANDOFF.md](HANDOFF.md)).
