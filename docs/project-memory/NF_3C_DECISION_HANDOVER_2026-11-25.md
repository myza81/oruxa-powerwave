# NF-3C decision handover — owner review of NF-3B and the decisions NF-3C needs

**Date:** 2026-11-25 · **Branch:** `feature/nf-3b-frozen-baselines-accessor-gate` (local), based on the NF-3B tip `5c7b0a9`
**Status:** analysis and decision evidence only. **No production code, test, API, UI or configuration change; no push, merge or deployment; NF-3C is not started.**
Sources: [NF-3A assessment](NF_3A_CONSUMER_MIGRATION_ASSESSMENT_2026-11-25.md) (section numbers below refer to it), [NF-3B report](NF_3B_FROZEN_BASELINES_ACCESSOR_GATE_2026-11-25.md), the frozen baseline `backend/tests/fixtures/nf3b_baselines/nf3b_frozen_baselines.json`, and the code at `5c7b0a9`. Where a statement rests on reading code rather than on a run, it says so.

---

## 1. Correction to my NF-3C release assumption

The NF-3B handover said that NF-3C "changes no output at all in a normal environment, because the gate returns Auto until you open it". **That was wrong as a general statement.** The gate neutralises only the *Manual* value. Moving a consumer from "read the imported value" to "ask the central authority" changes behaviour in **Auto** mode wherever the old and new paths differ. Section 2 lists every such difference found for the NF-3C consumers, each classified.

For an ordinary recording (valid declared value, or an importer-assumed 50 Hz) the new path returns the same number, so those outputs stay identical. That is a property to be *proved* by the frozen baseline in each commit, not assumed.

## 2. Observable changes NF-3C would make in Auto mode

NF-3C consumers (NF-3A section 9.2): event detection and synchronization (C-03), compliance readiness (C-04), compliance measurement (C-05), oscillation representation and its origin labels (C-06, C-07), the Technical facts card (C-24) and the three frontend origin labels (C-23). "Before" is measured in the frozen baseline (`c70182c`) unless marked *code*.

| # | Category | Where | Before (measured) | After (proposed) | Class |
|---|---|---|---|---|---|
| **OC-1** | invalid-frequency handling; error/status | compliance measurement `_classify_input_type` | declared **0** or **+∞** → `ZeroDivisionError`; **NaN** → `ValueError` (service level; **HTTP exposure was not driven**, so whether it is a 500 on the measurement endpoint is *code-inferred*) | typed "unresolved" (`None`, the existing "do not guess" outcome). Removes the exception | **Intentional correctness fix.** The strict xfail `test_compliance_measurement_does_not_raise_for_zero_hertz` flips |
| **OC-2** | availability | same | declared **1001 Hz** (outside the NF-1 range) → classified `"rms"` | `None` (unusable) | **Intentional, but a behaviour that "worked"**; a declared value over 1000 Hz is almost certainly an error, yet this is a visible change. Owner should know |
| **OC-3** | none | same | −50, 0.5 → `None` already; valid → `instantaneous` | unchanged | no change |
| **OC-4** | provenance wording | compliance readiness blocked step | declared invalid → `blocked`, text "…nominal frequency of this recording is **unknown**…" | still `blocked`; text says the declared value is **unusable** and names it. State, step identity and executability unchanged | **Intentional wording correction.** No repository test or frontend string matches the old text (searched) |
| **OC-5** | calculation identity | readiness `find_equivalent_rms` | reuses an RMS channel whose stored frequency equals the needed one | identical in Auto | no change. (With Manual a changed value proposes a *new* RMS step; the older channel is not flagged stale until NF-3E, see section 5, O-4) |
| **OC-6** | status/response | event detection (`POST …/synchronization/detect-event`) | invalid declared value → **HTTP 200**, `found:false`, reason "No usable nominal frequency is available for this source." and the declared value echoed (0.0, −50.0, 1001.0). **a declared NaN is echoed as JSON `null` although the schema field is a required, non-null `float`** (measured over HTTP; ±∞ serialises the same way, checked on the serializer, not over HTTP) | unchanged under O-7 option A; see section 3 | **No change if O-7 = A.** The `null` for NaN/∞ is a **pre-existing contract mismatch** that NF-3C should not silently carry or silently "fix" |
| **OC-7** | provenance label | oscillation representation / spectrum `nominal_frequency_origin` | two documented values: `recording_metadata`, `assumed_default`. A **BEN** recording (upload-supplied value) reports `recording_metadata` (*code*, from the provenance flag; BEN is not in the baseline, see Gap G-1) | NF-1 origin passed through: BEN becomes **`import_supplied`**; a Manual value `manual`; an unusable value `unusable` | **Intentional contract change** (the field's documented value set grows). Visible in Auto only for BEN and for unusable recordings. Needs O-6 and the frontend mapping in the same commit |
| **OC-8** | invalid handling | oscillation representation, invalid declared value | `status: unavailable`, `reason_code: invalid_nominal_frequency`, declared value echoed, origin `recording_metadata` (measured, for 0, −50, NaN, ∞, 0.5, 1001) | same status and code; origin becomes `unusable` | **Intentional**; availability and reason code unchanged |
| **OC-9** | availability | oscillation representation | valid and assumed → `ready` or `unavailable(form_unconfirmed)` | identical (the same 1–1000 Hz predicate decides) | no change |
| **OC-10** | assumed-default behaviour | all NF-3C consumers | assumed (CSV, unparseable `lf`) → 50 Hz, flagged assumed | identical: the NF-1 resolver returns the 50 Hz default with origin `assumed_default`. The only divergence would be an importer writing an assumed flag *and* a value other than 50; no shipped importer does (R1A tests), and `SourceMetadata.nominal_frequency` is a non-optional `float` | no change; stated so it is not assumed |
| **OC-11** | mixed-recording selection | oscillation **cross-signal** (`oscillation_classification`, first member else 50 Hz) | order-dependent (measured: swapping two recordings changes the verdict) | **unchanged in NF-3C**: that rule is NF-3G (O-9) | no change in NF-3C; **a limitation to disclose**: until NF-3G a Manual value on one of several recordings does not give an order-independent cross-recording verdict |
| **OC-12** | provenance display | Technical facts card (`renderRecordingDetails`, Recordings page row) | `source.nominal_frequency + " Hz"` for every recording: an assumed 50 looks like a declared 50; 0 → "0 Hz"; a declared NaN reaches the browser as JSON `null` and prints **"null Hz"** (*code reading*, not browser-run) | effective value plus origin where it informs (section 4) | **Intentional correctness fix**; ordinary declared recordings look exactly as today |
| **OC-13** | risk of mis-labelling | frontend labels at three sites (`index.html` 63387, 63938, 64148) | `origin === "assumed_default" ? "assumed default" : "from the recording"` | must learn `manual`, `import_supplied`, `unusable` | **Regression risk**: if the backend ever emits `manual` before the frontend maps it, a Manual value is displayed as "from the recording", a false provenance statement. Backend and frontend mapping must ship in one commit, with a browser test per site |

**Categories you listed and where they land:** invalid handling OC-1, OC-2, OC-8; error/status OC-1 and OC-6; assumed default OC-10 (no change); mixed selection OC-11 (no change until NF-3G); availability OC-2, OC-9; provenance OC-4, OC-7, OC-12, OC-13.

**Intentional fixes:** OC-1, OC-2, OC-4, OC-8, OC-12. **Intentional contract changes needing approval:** OC-7 (O-6). **Regression risks to test deliberately:** OC-13, OC-2 (a recording that classified before and now does not), and OC-1's unverified HTTP exposure.

**Gaps in the NF-3B baseline that NF-3C must close before changing anything (new, found while preparing this handover):**
* **G-1** no BEN-provenance recording in the in-process or HTTP baseline, so OC-7's BEN change is not yet frozen. NF-3C's first commit adds it from the pristine tree, as NF-3B did for `power_gate`.
* **G-2** the compliance-measurement HTTP endpoints were not driven with an unusable recording (OC-1).
* **G-3** the facts card and the three origin labels have no browser test today.

---

## 3. Owner decisions O-6, O-7, O-11: exact text, options, consequences, recommendation

Each block quotes the assessment's wording (section 13) and the conditions stated elsewhere in it, then adds options.

### O-6 Additive API fields for provenance

**Assessment text (section 13):** "Additive API fields for provenance: origin and revision in analysis results and in new calculated-channel parameters (D8 of the earlier assessment)." **My recommendation then:** "**Yes**: a wrong Manual value is silent (§5.4), so the origin must travel."

**Conditions it rests on (not to be lost):**
* §5.4: a wrong Manual value is **silent**. Measured cost of a mismatched frequency: RMS ripple **12–17 %**, phasor magnitude **−4 to −6 %** with a *rotating* angle. Nothing in the numbers tells the engineer the frequency was wrong, so the origin is the only cue.
* §7.2/§6.1: the result must record the value *and* origin *and* the revision used, so a stored result can be recognised as computed before or after a change.
* The calculated-channel half of O-6 (parameters of new channels) belongs to **NF-3E**; NF-3C touches only analysis results.
* The field today documents two values: `"recording_metadata" | "assumed_default"` (`schemas/oscillation.py:23`).
* You asked that the machine-readable `manual` origin be preserved unless a separate API change is justified. `manual` already exists in NF-1; what is new is *emitting it in these responses*.

**Options for NF-3C (analysis results only):**

| | Option | Consequence |
|---|---|---|
| **A** (recommended) | The existing `nominal_frequency_origin` carries the NF-1 origin (`recording_metadata`, `import_supplied`, `assumed_default`, `manual`, `unusable`); add **`nominal_frequency_revision`** (int). Frontend maps all five in the same commit | One field, one meaning, no duplicate. BEN reports `import_supplied` (accurate; a visible Auto change for BEN only, OC-7). Clients that treat any non-`assumed_default` value as "from the recording" would mislabel `manual`: only the Powerwave frontend consumes it (three sites) |
| B | Keep `nominal_frequency_origin` two-valued and add a second field `nominal_frequency_origin_detail` carrying the NF-1 origin | **Rejected:** a Manual value has no honest place in the two-value field (it would have to read `recording_metadata` or `assumed_default`), so the legacy field would state something false |
| C | Do not add fields; show provenance only in the UI from a separate NF-1 `GET` | Results stop being self-describing; an exported or API-consumed result loses the origin, which is exactly the silent-wrong-value case §5.4 warns about |

**Sub-choice for A (needs your answer): the BEN label.** Today a BEN recording is displayed "from the recording"; the format declares no frequency, the uploader supplied it. Options: (1) show it as **"supplied at import"** (accurate, visible BEN change); (2) fold `import_supplied` into the existing "from the recording" wording to keep Auto output identical. I recommend (1): NF-1 deliberately distinguishes the two, and an Auto-mode change that is a correct provenance statement is the intent of the migration.

**Revision:** additive, informational in stateless analysis responses; it earns its keep in NF-3E when a channel records the revision it was computed with. Adding it in NF-3C now avoids a second contract change; cost is one optional integer.

**Recommendation: A, with the BEN label (1), analysis results only; calculated-channel parameters stay for NF-3E.**

### O-7 Event-detection response when the recording is unusable

**Assessment text:** "Event-detection response when the recording is unusable: keep `nominal_frequency_hz: float` (non-null) as today, reporting the declared value, or make it nullable." **Recommendation then:** "Keep as today (no schema change)."
Matrix row C-03: "existing typed refusal `invalid_nominal_frequency`; the echoed `nominal_frequency_hz` keeps its type (**O-7**)."

**Facts established since (measured, in the frozen baseline):**
* The endpoint returns **HTTP 200 `found:false`** with the reason text for an unusable value, not a 4xx. The text is "No usable nominal frequency is available for this source."
* The echoed field is `float` (required) in `schemas/event_detection.py`, but for a declared **NaN the wire value is `null`** (measured over HTTP). Pydantic serialises ±∞ as `null` too (checked on the serializer only, not over HTTP). So **today's contract is already violated** for non-finite declared values.
* The frontend does **not** read `nominal_frequency_hz` from this response (it uses `found` and the candidate), so the field matters to API consumers and tests only.
* "Reporting the declared value" and "the effective value" differ only when a Manual value exists (declared 50, Manual 60): the echo should be the value the detector actually used.

**Options:**

| | Option | Consequence |
|---|---|---|
| **A** (recommended) | Keep `float`, non-null. Usable → the **effective** value (what the detector used). Unusable → the **declared** value as today. No schema change. Document the NaN/∞ → `null` mismatch as a known pre-existing issue, do not widen it | Zero schema change; Auto output identical for every finite recording; the `null` oddity persists for NaN/∞ |
| B | Make it `float | None`: effective value when usable, `null` when unusable | Fixes the mismatch honestly, but is an API schema change and loses the visible declared value (0, −50, 1001 are informative). Needs an owner decision on a public field |
| C | A plus an additive `nominal_frequency_origin` | Lets the response carry provenance like the analyses (O-6), at the cost of one more field on an endpoint whose consumer ignores it |

**Recommendation: A**, with the NaN/∞ mismatch recorded as a separate contract defect for a later, owner-approved fix. If you prefer provenance on every response, C is the smallest consistent extension.

### O-11 Technical facts card shows the effective value

**Assessment text:** "The Technical facts card (`index.html:22925`) and any other display of the imported value: show the **effective** value (with the same origin wording) once the gate opens." **Recommendation then:** "Yes, so two displays never disagree."
C-24: "The Technical facts card shows the **imported** value and is *not* under the NF-2 gate, so it would disagree with a Manual value."

**Facts established since:**
* The card is in `renderRecordingDetails(source)`, rendered in the **Recordings table row** expansion. The NF-2 control is in **Recording Details > Recording Info**. They are different places.
* The card is built synchronously from the source summary, which carries only the **imported** value: ordinary declared 50 and assumed 50 look identical; 0 prints "0 Hz"; a declared NaN arrives as `null` and prints "null Hz" (code reading).
* There is no existing path that gives that card the effective value; it needs either an extra NF-1 `GET` or an additive field on the source summary.
* The NF-2 row is gated by the UI flag; the card is not, so it is visible to everyone.

**Options:**

| | Option | Consequence |
|---|---|---|
| **A** (recommended) | Card shows the **effective** value with origin wording **only where it informs** (assumed, unusable, Manual); a plain declared value is **exactly as today**. Data from the NF-1 `GET`, fetched when the row is expanded, refreshed by the existing NF-2 invalidation hooks | No visible change for ordinary recordings (OC-12). Assumed/unusable/Manual become visible. Costs one request per expanded row and a refresh rule |
| B | Add the effective value and origin to the **source summary** (additive) and render from it | No extra request, but an API change (one more O-6-family field) and the summary is a **snapshot taken when channels load**, so it still goes stale after a `PUT` and needs the same refresh hook |
| C | Leave the value as imported but **relabel** it "Imported nominal frequency" | Smallest and truthful; no plumbing. The card then deliberately differs from the Recording Details row with a Manual value, which is acceptable only because the label says "imported". Does not fix assumed/NaN presentation |

**Recommendation: A**, staged so Auto-valid output is unchanged. Its wording follows section 4: effective value, origin where informative, the imported value shown separately when a Manual override exists. Your condition applies: nothing may call an engineer-entered value measured or verified.

---

## 4. Manual origin label (adopted as instructed)

| Element | Wording |
|---|---|
| Origin label for `manual` | **Manual override** |
| Contextual explanation | "Set in Recording Details." |
| Imported/Auto reference | shown **separately** where useful, e.g. "Imported: 50 Hz" or "Auto: 50 Hz" |
| Never | "measured", "verified", "confirmed", or any phrase implying physical evidence |
| Machine-readable value | `manual`, **unchanged**; no new code is introduced. (`import_supplied` and `unusable` already exist in NF-1; their emission in analysis results is O-6) |

Proposed companions, for your approval (they are not decided): `assumed_default` keeps "assumed default"; `recording_metadata` keeps "from the recording"; `import_supplied` "supplied at import"; `unusable` "unusable declared value". All five appear at the three oscillation sites (C-23) and the facts card. The existing NF-2 wording in Recording Details is not changed.

---

## 5. Dependencies of O-4, O-5, O-8, O-9, O-10 on NF-3C

| Decision | Needed before NF-3C? | Reason |
|---|---|---|
| **O-4** stale marker plus advisory for existing channels | **No**, with one disclosed interim state | NF-3C creates RMS channels only through compliance preparation, using the current effective value. If a Manual value later changes, readiness correctly proposes a new RMS step (identity includes the stored frequency, OC-5), but the **old channel is not flagged stale** until NF-3E. Acceptable only because the gate stays closed until NF-3I, where the inventory must be closed |
| **O-5** reason code for the phasor family and overcurrent | **No** | NF-3D only. NF-3C's refusals use their own typed outcomes (blocked step, `None`, the existing `invalid_nominal_frequency` code) |
| **O-8** RMS builder with no preselected frequency | **No** | NF-3E (C-22) |
| **O-9** cross-signal rule | **No hard dependency; a disclosed limit** | NF-3C maps labels and origins only for C-07. The first-member rule stays until NF-3G (OC-11). Until then Manual is not order-independent for cross-recording oscillation. If you want that closed first, NF-3G can be moved before NF-3I; it does not block NF-3C |
| **O-10** eligibility endpoint HTTP 500 | **No** | NF-3E. Oscillation calls the eligibility check with a value it has already validated |
| **O-2** power correction | No | NF-3F |
| **O-12** gate-opening evidence | No | NF-3I |

**One new question the above surfaces (D-1):** NF-3C's behaviour with a Manual value can only be exercised in a **non-deployed** process today (NF-3B refuses to start a deployed build with the gate open). If you want **DEV UAT of NF-3C itself**, a small prerequisite change is needed (section 7). If UAT of NF-3C is local and isolated, nothing is needed.

---

## 6. The five pre-NF-3C checks

1. **The seven expected failures are strict.** Each of the seven `@pytest.mark.xfail(strict=True, reason=…)` markers is in `test_nf3b_independent_oracles.py`; `pytest.ini` adds only `--strict-markers`. A run lists exactly seven `XFAIL`, each with its slice: NF-3D ×2 (phasor, overcurrent), NF-3C ×1 (compliance measurement), NF-3E ×1 (eligibility), NF-3F ×2 (power value, stored parameter), NF-3G ×1 (oscillation order). **Demonstrated, not only declared:** in a scratch copy I fixed the compliance-measurement defect; the test reported `[XPASS(strict)]` and **FAILED**. A defect fix therefore forces its marker to be removed in the same commit.
2. **Historical behaviour is separated from desired correctness.** `test_nf3b_frozen_baselines.py` freezes what the code *did* at `c70182c` and says so in its module docstring ("not engineering oracles"); its `TestLegacyDefects…` class names each wrong behaviour as a defect with the slice that must invert it. `test_nf3b_independent_oracles.py` holds the closed-form expectations: part 1 (kernels correct at the matching frequency) passes today; part 2 (consumers must refuse/adopt) is the seven strict xfails. Values are never copied from one into the other.
3. **DEV UAT without enabling PROD:** section 7.
4. **NF-3C before/after matrix:** section 8.
5. **No consumer migration or numerical change has occurred in NF-3B.** `git diff c70182c HEAD` is empty for all of `frontend/`, `backend/app/domain/`, `backend/app/providers/`, every consumer service (phasor, overcurrent, calculated-channel, compliance readiness and measurement, synchronization, oscillation, auto-base) and `api/v1/calculated_channels.py`. The call-path guard fails if any consumer imports the accessor or adds a frequency read. 2,971 recorded outputs are byte-identical between pristine `c70182c` and the NF-3B tip (SHA-256 `b5609564…0b7`). The only production edits are the gate, the accessor, the NF-1 router and one additive field.

---

## 7. Exercising the Manual gate in DEV UAT without enabling it in PROD

**Today (NF-3B, as built):** a DEV deploy **cannot** open the gate by design: `load_settings` raises `ConfigurationError` for the variable in any build with `APP_VERSION` set or `ENVIRONMENT=production`, and a static test fails if any compose, workflow, script, `.env*` or entrypoint file names it. Local isolated runs (no `APP_VERSION`, not production) can open it; that is what the preview instructions use.

**Proposed mechanism for a DEV UAT (design only, nothing implemented; needs your approval, see D-1).** Defence in depth; the PROD protection is in *code*, not in a file someone might copy:

1. **PROD refusal is unconditional:** the backend refuses the variable whenever `ENVIRONMENT=production`, regardless of `APP_VERSION` or value. `compose.prod.yaml` already hard-codes `ENVIRONMENT: production`, so a PROD host cannot start with it open even if a stray `.env` carries it.
2. **DEV opt-in is one explicit line in one file:** `compose.dev.yaml` (the existing precedent is `BEN5K_EXPERIMENTAL_ENABLED: "1"` there, "enabled for DEV only"). The deployed-build refusal is relaxed to "deployed non-production **and** `ENVIRONMENT=development`".
3. **The static test becomes an allow-list,** not a blanket ban: exactly `compose.dev.yaml` may name the variable; `compose.yaml`, `compose.prod.yaml`, `.env.example`, the deploy workflows, `scripts/` and `frontend/config.js` may not; a test asserts `load_settings` raises for `production` with any other setting.
4. **The UI flag needs its own deliberate DEV path** (today the entrypoint cannot emit it, enforced by a test): the entrypoint would emit `nominalFrequencyOverride` only when `ENVIRONMENT=development` and a DEV-only variable is set in `compose.dev.yaml`. The two switches stay independent, as NF-3B established.
5. **Branch hygiene:** the enabling change is a **separate, last commit on the UAT branch** and is not merged to `main` until the NF-3I gate-opening decision.
6. **Observable verification after every deploy (read-only):** `GET …/sources/{id}/nominal-frequency` now returns `manual_override_enabled`. DEV UAT expects `true`; the PROD release check asserts `false` with one request. No new endpoint is needed.

**Residual risk, stated:** if a PROD host were started with `ENVIRONMENT` set to something other than `production`, the code rule would not catch it; `compose.prod.yaml` hard-codes the value and PROD deploys use it, which is the same trust the BEN5K DEV-only flag already relies on.

**Alternative that needs no change:** UAT of NF-3C in a local isolated stack (no `APP_VERSION`), as for NF-2. NF-3I's own checklist (section 8.2, items 9–11) still requires an isolated DEV-like UAT with the gate on before the gate opens.

---

## 8. NF-3C before/after behaviour matrix (Auto mode; Manual only inside an opened process)

"Before" is the frozen baseline. "After" is the proposed NF-3C behaviour. A cell saying **same** is a promise the frozen baseline must prove in the NF-3C commit.

| Case | Event detection | Compliance readiness | Compliance measurement | Oscillation representation | Facts card |
|---|---|---|---|---|---|
| **Valid declared** (50, 60) | 200, echoes value. **Same** | executable RMS step with the value; reuse by stored frequency. **Same** | classification from the detector. **Same** | `ready`/`unavailable(form_unconfirmed)`, origin `recording_metadata`. **Same** | "50 Hz". **Same** |
| **Assumed** (CSV, unparseable `lf`: 50 Hz) | 200, echoes 50. **Same** | step with 50. **Same** | **Same** | origin `assumed_default`. **Same** | "50 Hz" → **"50 Hz (assumed)"** (OC-12) |
| **Supplied at import** (BEN) | **Same** | **Same** | **Same** | `recording_metadata` → **`import_supplied`** (OC-7; not yet in the baseline, G-1) | "supplied at import" wording only if you choose the sub-choice (1) |
| **Invalid declared**: 0, −50, 0.5, NaN, ±∞ | 200 `found:false`, same reason text, echoes declared (NaN/∞ wire `null`). **Same under O-7 A** | `blocked`, same executability; text "unknown" → **"declared unusable"** (OC-4) | 0/NaN/+∞ **raise today** → **unresolved `None`** (OC-1); −50 and 0.5 already `None`: **same** | `unavailable(invalid_nominal_frequency)`, same code; origin → **`unusable`** (OC-8) | "0 Hz" / "null Hz" → **"Unusable (declared …)"** (OC-12) |
| **Invalid by range**: 1001 | 200 `found:false`, echoes 1001. **Same** | `blocked` (**wording** as above) | classifies `"rms"` today → **`None`** (OC-2) | `unavailable`, origin → `unusable` | "1001 Hz" → "Unusable" |
| **Manual set** (gate open only) | detector uses the Manual value; echoes it | step and reuse use the Manual value; an older channel with another frequency is not reused (OC-5) | detector uses it | value and origin `manual` ("Manual override", "Set in Recording Details."), imported value shown separately | effective value, "Manual override", imported value separately |
| **Manual set, gate closed** | **Same as Auto** (the stored value is ignored) | **Same** | **Same** | **Same** | **Same** |
| **Mixed recordings** | n/a (one recording per call) | n/a (a group belongs to one recording) | n/a | n/a for a single signal. **Cross-signal across recordings: first member decides, unchanged (NF-3G, O-9)** (OC-11) | n/a |

**Not decided here, needing your answer before NF-3C starts:** O-6 (option A and the BEN label), O-7 (A, B or C), O-11 (A, B or C), the label companions in section 4, and D-1 (whether NF-3C needs DEV UAT, which would add the small prerequisite of section 7).

## 9. Limits of this handover

* OC-1's HTTP exposure, the facts card's "null Hz", and the BEN label change are **code-inferred**, not run (G-1 to G-3 close them inside NF-3C's first, behaviour-neutral commit).
* The 14 baseline-equivalent Waveform failures, plus 9 that fail identically on `c70182c`, remain **unresolved** and are not touched.
* The DEV UAT mechanism in section 7 is a design for your approval; no configuration, workflow or code has been changed.
