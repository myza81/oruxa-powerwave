# D5A-2B2 — Engineer-Confirmed Measurement-Side Data Model (PROPOSAL ONLY)

No storage, API or frontend is introduced by D5A-2B1. This is a design for owner review.

## 1. Why it is needed

Strict mode (D5A-2B1) refuses any consumed channel whose recorded side is undeclared (`*_side_authority_unavailable`). COMTRADE declares P/S per channel, but other providers and some COMTRADE files declare nothing, and an automatic declaration can be wrong. An engineer needs a way to state, and correct, the side — without that statement being silently mistaken for recording evidence, and without feeding PU.

## 2. Proposed fields (group level, on the existing group configurations)

On both `VoltageBaseConfiguration` and `CurrentBaseConfiguration` (so voltage and current sides stay independent):

| Field | Values | Default |
|---|---|---|
| `measurement_side` | `unknown` \| `primary` \| `secondary` | `unknown` |
| `measurement_side_authority` | `not_configured` \| `manual` | `not_configured` |
| `measurement_side_note` | free text (who/why) | `None` |

Same in-memory registries, same Recording Details editing surface (Codex), same copy-on-boundary rules. **Not** `base_reference_side`: that is the PU base's side (a denominator), a different concept.

## 3. Precedence against per-channel recording declarations

For each consumed channel, with `declared` = the recording's own P/S marker and `confirmed` = its group's engineer-confirmed side:

| `declared` | `confirmed` | Resolved side | Strict mode |
|---|---|---|---|
| side X | unknown | X (`recording_declared`) | allowed |
| side X | X | X (`recording_declared`, `engineer_confirmed`) | allowed |
| side X | Y ≠ X | **conflict** | blocked: `*_side_evidence_conflict` |
| unknown | side Y | Y (`engineer_confirmed`) | allowed |
| unknown | unknown | unresolved | blocked: `*_side_authority_unavailable` |

The recording declaration is never overwritten; a confirmation fills a gap or exposes a conflict.

## 4. Correcting incorrect automatic evidence without silent override

If the recording says `P` but the engineer knows the channel is `S`, the row above is a **conflict**, not an override. Resolution requires an explicit second act: the engineer records a correction — a channel-level exception (below) carrying `corrects_declared_side`, an authority (`manual`), a note, and a timestamp. A correction is reported in every result (`side_evidence: "engineer_correction"`, with the original declared value preserved), so it can never pass as independent recording evidence, and a conflict without a correction stays blocked. This keeps "independent confirmed declaration" and "engineer correction" distinguishable and auditable.

## 5. Mixed-side groups and channel-level exceptions

A group's members normally share one CT/VT set and therefore one side, so a group-level value is the common case. Genuinely mixed groups (members recorded on different sides) are unusual: today they are reported `mixed` and rejected for a calculation that consumes both (D5A-2B1). Recommended order:

1. **Now (B2):** group-level fields only; a mixed group is resolved by splitting the group.
2. **Only if a real recording requires it:** an optional per-channel map `side_overrides: {channel_name → {side, authority, note, corrects_declared_side?}}` on the same configuration. It is also the home for §4 corrections, so if corrections are wanted, this map is needed with them. Defer both unless the owner wants corrections in the first release.

## 6. Interaction with the rest of the system

- **PU:** the accepted PU engine reads only `channel.measurement_side`. The confirmed side is consumed by protection analyses only and must not feed PU (owner decision B5, reaffirmed); a test should assert PU outputs are unchanged when a confirmed side is set.
- **D5A-2A context API:** gains `side_evidence` values `recording_declared | engineer_confirmed | engineer_correction | conflict | none` and diagnostics `*_SIDE_EVIDENCE_CONFLICT`.
- **Strict mode:** reads the resolved side via the same `resolve_channel_facts`; no new strict-mode reason codes other than the evidence conflict.
- **Persistence:** same in-memory lifetime as all group configuration. No new persistence mechanism.
- **Frontend (Codex):** one side selector + note per group panel; a conflict banner. Not part of this slice.

## 7. Questions for the owner

1. Approve group-level `measurement_side` / `_authority` / `_note` (storage change) as the first D5A-2B2 step?
2. Are engineer **corrections** of a contradicting recording declaration wanted in the first release (requires the per-channel map), or is a conflict simply left blocked until the recording is fixed?
3. Should confirmation be allowed when the recording declares nothing but the CT/VT ratio is configured? (Recommended: yes — ratio is irrelevant to side; the engineer's statement is the evidence.)
4. Confirm that the confirmed side never feeds PU, including PU reference-side safeguards.
5. Should strict mode also accept the legacy request-ratio path for engineers who have no Measurement Group CT/VT configured? (Currently: no — ratios come only from Recording Details.)
