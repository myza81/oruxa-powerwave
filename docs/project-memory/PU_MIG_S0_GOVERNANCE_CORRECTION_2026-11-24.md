# PU-MIG S0 closure — governance correction

**Date:** 2026-11-24
**Authority:** the owner's direction "PU-MIG S0 Closure and S1 — Pure Denominator Resolver" (2026-11-24), which follows the owner's review of the S0 owner-review response (`PU_MIG_S0_OWNER_REVIEW_RESPONSE_2026-11-24.md`).
**Branch:** `feature/pu-mig-s1-pure-denominator-resolver`, created from `audit/pu-mig-s0-final-contract` (`d387033`). `d387033` differs from the DEV baseline `e9c621c4c15e0693d008670e9be8ae38b29c6d97` **only under `docs/`** (verified: `git diff --name-only e9c621c d387033` lists no path outside `docs/`), so every `backend/` and `frontend/` file is byte-identical to `e9c621c`. Local only: **not pushed, merged or deployed.**
**Scope:** documentation. This commit changes no production code, test, API or UI.

Labels: **[DECISION]** owner-decided · **[PENDING]** not decided; a recommendation exists but is not approved · **[FACT]** verified in a file or object · **[CORRECTION]** a statement in earlier S0 material that is wrong or overstated.

**Method.** Nothing is silently rewritten. Where an S0 document stated something that the owner has since declared undecided, the original wording stays in the document, struck through, with a dated pointer to this file; the text as first committed is also recoverable from git (`55f3218` for Amendment 7 and the matrix, `6562951` for the S0 report, `d387033` for the owner-review response). The preserved assessment itself is **not edited**.

---

## 1. Correction ledger

| ID | Where | As delivered | Why it is wrong | Corrected position | Applied to |
|---|---|---|---|---|---|
| **GC-1** | DEC-216 **Amendment 7**, first bullet (A7-3); matrix §2.2 first row; S0 report §4.3 and §2.1 row A7 | "Secondary base on Primary samples: base multiplied by the ratio" listed with the approved cases | DEC-216 says only that a legitimately configured secondary base is never reinterpreted as primary and that a needed conversion without a CT/VT blocks. It does **not** approve converting a Secondary-declared base onto Primary samples. That is decision **D-6**, which is **pending**. Today the combination is blocked when the sample side is known. | The Secondary-base-to-Primary-samples conversion is a **pending integration policy**. It may be demonstrated mathematically by the S1 pure resolver (the formula `base × ratio` is a property of the arithmetic), but it authorises **no live behaviour** in any PU consumer. | Amendment 7 (struck through and corrected); matrix banner; S0 report banner |
| **GC-2** | DEC-216 **Amendment 7**, second bullet (A7-6); matrix §2.2 second row | "Where the conversion is not authoritative (… or any contributing side not strict) PU still blocks" | A non-strict (Unknown or inferred) side does **not** block today: DEC-210 and DEC-211 retain such results as historical **Unverified**. The clause as written is option **B** of D-1 and so pre-decides an open question. | The amendment does **not** change, prohibit or remove historical Unverified behaviour. Only a **known** Primary/Secondary mismatch without an authoritative ratio blocks, exactly as DEC-210/211 already say. D-1 stays open under the owner's two-sided constraint (§2). | Amendment 7; matrix banner |
| **GC-3** | DEC-216 **Amendment 7**, last bullet (A7-9) | "Not decided here (open): OD-2, OD-3, OD-4, precedence, API deprecation" | Incomplete: omits D-5, D-6, D-7, N-1/N-2 and the D-4 distinction; OD-3 has since been agreed (D-2) and OD-4 agreed in principle (D-3). | The complete register is §2 of this document and Correction 3 of the amendment. | Amendment 7 |
| **GC-4** | S0 report (`PU_MIG_S0_FINAL_RECONCILIATION`) §1, row `e5c6fce` | "The assessment is the original delivered text recovered from the session transcript (no banner, no later edit)" and S0 report C-1/§6 mechanism wording | Already withdrawn by the owner-review response (X-1, X-3): the assessment is a **reconstruction** (§3 below), and the 0.956522 reading exists only for a particular engineer-visible stored state (M3/M6/M7), not "whenever" a VT winding rating is stored. | The owner-review response governs. This ledger records the corrections so they are not lost. | S0 report banner |
| **GC-5** | S0 report C-1 and §6 | `recording_metadata` listed among the VT ratio sources | **No production code writes `vt_authority = "recording_metadata"`**; the reachable authorities are `manual` and the derived `auto_nominal` (X-2). | As in the owner-review response §2.3. | S0 report banner |

**Not changed:** the assessment body; the v1 and v2 oracles; `pu_mig_oracle_expected.json`; the final oracle and its expected JSON; the probes and their recorded output; the owner-review response body.

---

## 2. Decision register (complete)

Status vocabulary: **DECIDED** (owner), **AGREED IN PRINCIPLE**, **PENDING** (open; recommendation only, never an approval). Nothing in S1 treats a PENDING item as approved production behaviour.

| ID | Subject | Status | Owner disposition / constraint | Options | Recommendation (proposal) |
|---|---|---|---|---|---|
| **D-1** (OD-2) | Historical Unknown/Unverified results, per class (raw Voltage, raw Current, calculated Voltage, calculated Current) | **PENDING production decision** | Historical Unknown/Unverified behaviour must **not be silently changed** and must **not be represented as verified engineering PU** | **R** retain · **R+** retain and make "not verified" an explicit uniform verification state · **N** R+ and block only the ≥100× combination (Secondary-declared base against a non-strict sample side) · **B** block | R+ for all four classes through S4; census before any N or B |
| **D-2** (OD-3) | Manual-base side metadata | **DECIDED** — agreed | Preserve existing manual Current base reference-side semantics through S4; no schema, API, UI or writer change | keep / re-label / replace | Keep through S4; decide replacement after UAT-3 |
| **D-3** (OD-4) | Calculated-channel lineage | **AGREED IN PRINCIPLE** | One shared, operation-aware lineage function; the final operation rules of S0 §7 remain subject to review (S0 §7 is a draft agenda) | approve / amend | Approve the architecture; review each operation row before S3; protection adoption separate |
| **D-4** (R-4) | Precedence between `secondary_voltage_ll_v` and nominal ÷ ratio (the 4.35 % case) | **PENDING production decision** | No general rule that the legacy secondary denominator always wins; distinguish an independently configured Secondary base from a value populated from a VT winding rating | P1 legacy wins · P2 derived wins · P3 block · P4 decide by recorded origin · P5 diagnostic only until an origin field exists | P5 now, P4 once an origin field is approved and a census exists |
| **D-5** (R-5) | What activates the legacy secondary path | **PENDING** | — | (i) stored `base_reference_side == "secondary"` and a valid `secondary_voltage_ll_v` (today) · (ii) effective (Recording Details) side secondary and a valid value | (i) through S4; decide (ii) only at S6 |
| **D-6** (R-6) | Primary samples against a Secondary-only base (converting a Secondary base onto Primary samples) | **PENDING** — and was wrongly shown as approved in Amendment 7 (GC-1) | — | convert with an authoritative, trusted ratio, else block · keep blocked | Convert only with a valid, trusted ratio, else block — **not part of Amendment 7** |
| **D-7** (R-7) | `auto_nominal` ratio for secondary PU | **PENDING** | DEC-215 already accepts a nominal-derived VT as a consumable ratio | accept and show provenance · require `manual`/recording metadata | Accept and show provenance (the derived denominator then equals a 110 V base for any nominal) |
| **D-8** (R-8) | API deprecation of `*_base_reference_side` | **PENDING** | — | none through S4 · deprecate | None through S4; revisit at S6 |
| **D-9** (R-9, R-10) | PU refresh scope after a side write; placement of the independent oracle in `backend/tests` | **PENDING** | — | refresh per source / per group · oracle in tests: yes / no | Refresh per source; oracle in tests, importing no application code. *S1 uses an unchanged copy of the S0 oracle output and a new independent oracle as **test fixtures** under `backend/tests/fixtures/pu_side_denominator/`; this is test-only evidence and stays subject to the owner's confirmation of D-9.* |
| **N-1** | One authority and one denominator policy for every PU consumer (waveform, calculated channels, provenance, coverage) | **AGREED IN PRINCIPLE** | Implemented in S2 as one shared function; coverage counts and compliance values will change for the same cases | yes / defer | Yes (a DEC-210 obligation) |
| **N-2** | Reason-code vocabulary | **PENDING** | — | A: reuse the existing names and add only the new ones · B: a separate PU namespace | A. **Every reason code in S1 is a proposal** |
| **N-3** | P0 browser-guardrail triage before S2 | **DECIDED** — agreed | See §4 | — | — |

**D-1 and D-4 are pending production decisions.** S1 is deliberately independent of both: the pure resolver receives one already-established base and never chooses between stored and derived base authorities, and it neither retains nor removes any historical Unverified result.

---

## 3. Provenance of the preserved original assessment

`PU_MIG_001_ASSESSMENT_2026-11-24.md` is **reconstructed from the session transcript**; it is **not verified against a surviving original file on disk**.

- The original file no longer exists (it was created in the main checkout, moved into an audit worktree and later carried with a banner).
- The preserved text is the transcript replay of the creating `Write` (transcript line 393, sha256 `ab5076a9…`, 33 017 characters) plus one `Edit` six seconds later and **before delivery** (line 407; one line-number reference), giving the delivered text (sha256 `c5e7088f…`, 33 033 characters).
- It was cross-checked against a surviving **git blob** (`88c9244`): that blob minus its later two-line owner-review banner is identical to the reconstruction (programmatic equality). Two independent sources therefore agree, **neither of which is the original disk file**. The equality is content equality modulo line endings, not a byte comparison with the disk file.
- Commit `e5c6fce` held only the pre-`Edit` payload and its message wrongly called it "byte-identical to what was delivered"; commit `4b53d09` corrected that.
- The v1 oracle is different: it **was** verified against a surviving original file (scratchpad `oracle/pu_mig_oracle.py`, sha256 `480d12a0…f6fa`).

The S0 matrix, v2 oracle and expected JSON were compared as git blobs against `88c9244`; `88c9244` is itself the first and only committed form.

---

## 4. S1 boundaries and the P0 gate

**S1 (this branch)** adds one pure-domain function with its independent oracle, tests and mutation evidence, and nothing else. It authorises none of S2–S6 and does not approve any PENDING item above.

**P0 stays a hard gate before S2.** The plan is preserved unchanged in `PU_MIG_S0_OWNER_REVIEW_RESPONSE_2026-11-24.md` §6 (131 browser failures identical on `3ed200c` and `e9c621c`; method, tiers, anti-vacuity and stop conditions). The owner's direction adds one explicit requirement: **replacement coverage for the retired Per-Unit Settings Hub controls must be provided through the current Recording Details workflow** (the Tier-1 failures that target `#wwOpenPerUnitSettingsBtn` and the Measurement-Group overlay, 22 of the 32 Tier-1 tests, are covered numerically by the backend suite but have no browser-level guard rail for the current configuration surface). That coverage is a P0 deliverable and an exit criterion for S2; it is not created here, and no browser test, spec or fixture is touched by S1.

---

## 5. What S1 does not touch

No live PU waveform, calculated-channel, provenance or coverage consumer is connected to the resolver; no current PU output changes; no Base Reference Side UI is removed; no auto-base writer changes; no public API or schema changes; historical Unverified runtime behaviour is unchanged; WUI-001–004 and the protection analyzers are untouched. These are enforced by tests (an import tripwire) and shown by the source diff in the S1 slice report.
