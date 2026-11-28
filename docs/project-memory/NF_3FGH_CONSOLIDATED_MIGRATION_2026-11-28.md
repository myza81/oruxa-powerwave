# NF-3F / NF-3G / NF-3H — consolidated consumer migration: completion record

Date: 2026-11-28. Status: **implemented and verified locally; awaiting owner review.** Not pushed, merged or deployed. No feature gate was changed and NF-3I was not started.

## 1. Base, branch and commits

| Item | Value |
|---|---|
| Accepted integration (functional) | `ae5dfd9` on `feature/nf-integration` (preserved, untouched); acceptance documentation HEAD `c5ebe6d` |
| Accepted main baseline | `885bf8d` |
| New branch / worktree | `feature/nf-3fgh-consolidated` / `.local-data/nf-3fgh`, created from `c5ebe6d`; zero non-documentation files differ from `ae5dfd9` |
| Decision record | `ca96723` — DEC-217 **Amendment 1** (O-2, O-9, the acceptance contract, NF-3H scope, O-3 confirmed) |
| **NF-3F** | `113fd5e` — power channels |
| **NF-3G** | `550a808` — oscillation cross-signal |
| **NF-3H** | `194d8ba` — silent-default retirement |

Applied: AGENTS.md, DEC-217 (+ Amendment 1), DEC-218, the NF-3A to NF-3E records and the NF integration record. No decision was reopened.

## 2. What changed

**NF-3F (O-2) — C-11, C-12, C-13.** `calculated_channel_service` resolves ONE frequency for a power calculation through the existing `NominalFrequencyAccess.for_sources` contract (all voltage and current inputs; three-phase uses all six). That value drives the recording-length and sampling-density gates (previously a literal `50.0` ×4), the evaluator call (previously the domain default) and the stored `nominal_frequency_hz` (previously a literal `50.0` ×2). Disagreement is refused with **HTTP 400, `nominal_frequency_mixed`**, naming each input and its frequency; an unusable frequency keeps the existing 400 `invalid_nominal_frequency`; nothing is written on refusal. A new channel records `nominal_frequency_basis = recording` and the recording's origin and revision (NF-3E provenance) and is assessed by the **existing** staleness authority against **each** recording that grounds one of its inputs; its stale-input remedy text says "power channel". A power channel stored before NF-3F keeps its values and parameters, has no basis, and is treated as explicit. The power kernels are unchanged. A caller that supplies no authority (no production caller; a static test pins that) keeps the one sanctioned default, `DEFAULT_NOMINAL_FREQUENCY_HZ`.

**NF-3G (O-9) — C-08, C-07 (cross-signal).** `classify_component` no longer takes the first member's frequency. Members that agree use the agreed value; members that disagree give **no** frequency, nothing is compared with a nominal value, and the result carries `nominal_frequency_mixed` limiting evidence (every declared value and `any_assumed`). The result is independent of member order; family, behaviour and supporting evidence are unchanged. The agreement tolerance and rule (`AGREEMENT_REL_TOL/ABS_TOL`, `frequencies_agree`, `agreed_frequency`) moved from the accessor into `app/domain/nominal_frequency.py` so the domain classifier applies the **same** rule without importing a service; the accessor imports and re-exports them and its outcomes are unchanged. The assumed-frequency fallback constant now aliases the single sanctioned default. Oscillation mathematics is unchanged.

**NF-3H — C-16.** `compute_sliding_phasor`, `evaluate_power_channel` and `evaluate_three_phase_power_channel` take the frequency as a required argument. No production caller omits it; 32 test call sites that relied on the silent default now pass the explicit `50.0` they were receiving. The resolver's 50 Hz assumed-frequency fallback is **retained**; `extract_waveform_evidence` (Auto Base evidence, C-17) is **excluded** under O-3 and keeps its default. Not every 50 Hz constant was removed.

Files: 9 application files (F 4, G 3, H 2, no overlap; `git diff --stat ae5dfd9 HEAD -- backend/app`: +189/−48) and 30 files overall including tests and manifests (+4,193/−119).

## 3. Numerical evidence

Acceptance contract (owner, 2026-11-28): primary criterion is **bit-for-bit equality with the unmodified kernel called directly with the intended frequency**; 50 Hz bit-identical to the frozen baseline; 1e-9 for integer-cycle ideal cases; 1e-3 for the existing strict-xfail oracle; the non-integer-cycle ripple figures are fixture evidence.

| Evidence | Result |
|---|---|
| Channel values == kernel called directly (single-phase P and Q; three-phase P and Q; 50, 60 Hz, assumed, declared-50-on-60-Hz-signal, Manual 60 on 50 Hz and Manual 50 on 60 Hz; fs 4800, 5000, 4096) | `np.array_equal` on every case |
| 50 Hz recording, migrated path vs the pre-migration path | `np.array_equal` (fs 4800, 5000, 4096); the frozen NF-3B HTTP and NF-3E baselines are unchanged apart from the classified additions below |
| §5.5 closed form, integer cycles (50 Hz @4800/5000, 60 Hz @4800), P and Q, three-phase | max relative error ≤ 1e-9 |
| 60 Hz recording @5000 Hz / @4096 Hz (non-integer) | measured P mean +0.0014 % / +0.0014 %, Q mean −0.0016 % / −0.0015 %, P peak-to-peak ripple 1.86 % / 1.81 % — the documented §5.5 target row |
| 60 Hz recording with the OLD fixed 50 Hz window (the defect) | measured P mean −11.76 %, Q mean −13.21 %, P peak-to-peak 36.8 % — the documented defect row |
| NF-3B strict-xfail oracles (power closed form < 1e-3; stored frequency = the one used; swapping recordings does not change the oscillation verdict) | flipped to passing; expectations unchanged |

Disclosure: for the non-integer 60 Hz records my test asserts the **mean** error below 1e-3 and a 2.5 % sanity ceiling on the instantaneous error. The 2.5 % is a guard value chosen by this slice (about 2.7× the observed 0.93 %), not an owner-approved figure; the ripple figures remain evidence, not requirements.

## 4. Changes to frozen records (history untouched)

Every difference between "history + earlier approved changes" and the new output is generated, classified and written as a reviewable manifest; an unclassified difference aborts generation. No frozen baseline file was edited or regenerated and no expected value was altered.

| Manifest | Entries | Kinds |
|---|---|---|
| `nf3f_approved_changes.json` (NF-3B HTTP baseline; NF-3E Phase A power group) | 98 + 7 | provenance added (42 + 6), stored frequency effective (4 + 1), values corrected for the recording's frequency (12), refused for an unusable frequency (40) |
| `nf3g_approved_changes.json` (NF-3B oscillation selection) | 34 | nominal comparison withheld (15), `nominal_frequency_mixed` reported (19); only the three disagreeing-member cases change; `probable_type` and supporting evidence never change |
| `nf3h_approved_changes.json` (NF-3B kernel baseline) | 32 | silent default retired (the `windowdefault` calls now record `TypeError`) |

Also updated, deliberately and in the same commits: the two NF-3B strict-xfail oracles (markers removed), the release-gate test that asserted "Manual leaves power channels unchanged" (its docstring announced the edit), the NF-3E staleness test (split into the legacy-channel case plus the new tests), and the call-path guard inventories (the six power literals, the three silent defaults and the oscillation 50.0 literal are gone; the guard confirms the **one** remaining migrate-class row is the Auto Base default).

## 5. Verification

| Check | Result |
|---|---|
| Focused regression per slice (NF, PU, calculated channel, compliance, phasor, overcurrent, oscillation, power, frontend NF suites) | F 5,136 passed; G 2,835 passed; H 6,221 passed; 0 failed |
| New tests | NF-3F 62, NF-3G 59, NF-3H 10 |
| **Full backend, `194d8ba`** | **16,894 passed, 410 skipped, 0 failed, 0 xfailed** (14 min 29 s). Baseline `ae5dfd9`: 16,760 / 410 / 3 xfailed. The 3 strict xfails flipped and are now passes |
| BEN owner-reference files (with `--ben-reference-dir`) | 1,015 passed (same as baseline) |
| **Full browser, `194d8ba`** | **1,883 passed, 8 failed, 9 skipped, 0 flaky, 0 retries** (1 h 02 min). Baseline `ae5dfd9`: 1,882 / 9 / 9 |
| Mutation checks (23: wrong source, ignored Manual, accepted disagreement, unusable accepted, dropped provenance, staleness off, first-source-only staleness, first-member decides, largest-value decides, evidence dropped, assumed provenance lost, no-disagreement rule, loosened tolerance, restored defaults, a caller omitting the frequency) | **23 / 23 killed**; every mutated file was restored (working tree clean) |

**Browser reconciliation against `ae5dfd9`.** The 8 failures are exactly the baseline's documented set: the six CSV/Excel specs and the two `waveform-legend-visibility.spec.js:9` Grouped/Custom tests (intermittent on pristine `885bf8d` as well, per the integration record). The baseline's one unreproduced `waveform-pane-drawer-clearance` observation did not recur. **No new failure.** Skips (9) are the eight documented owner-recording skips plus the gated NF-2 screenshot spec. As before this is not an unconditional pass: it carries the documented legend-visibility timing qualification. The frontend and browser specs are byte-identical to `ae5dfd9`, so this slice changes no UI.

## 6. Remaining consumer inventory

All of NF-3A's migrate-class consumers are now on the central authority **except one that is excluded by decision**.

| Consumer | State |
|---|---|
| C-01..C-10 (phasor family, overcurrent, event detection, compliance, oscillation representation, line-to-line, protection analyses) | migrated in NF-3C / NF-3D |
| C-14, C-15 (RMS default and eligibility) and the staleness, provenance and refresh surfaces | NF-3E |
| **C-11, C-12, C-13** (power gates, evaluators, stored parameter) | **NF-3F** |
| **C-08, C-07 cross-signal** | **NF-3G** (see limitation 1) |
| **C-16** (sliding phasor, power kernels) | **NF-3H** |
| **C-17** Auto Base evidence (`extract_waveform_evidence`) | **not migrated, by owner decision O-3**: stays with the Per-Unit workstream; the gate-opening wording must say the setting does not apply to it |
| Resolver 50 Hz fallback, `DEFAULT_NOMINAL_FREQUENCY_HZ`, the explicit RMS `nominal_frequency_hz` parameter (DEC-048) | retained by design |

## 7. Known limitations and findings (reported, not changed)

1. **Oscillation: native members carry no frequency.** A signal analysed in its native representation reaches the classifier with `nominal_frequency_hz = None` (the native spectrum needs no frequency; an NF-3C design). Such a member neither agrees nor disagrees, so a component built from native signals (typical MW/frequency analyses) still falls back to the flagged 50 Hz assumption exactly as before, and `nominal_frequency_mixed` arises only where members carry frequencies (the RMS-magnitude representation). Feeding native members the recording's effective frequency would change Auto-mode output (the `nominal_frequency_assumed` evidence) and is outside the approved O-9 scope, so it was **not** done; it needs an owner decision. A test pins the unchanged behaviour.
2. **A recording whose declared frequency is unusable can no longer create a power channel** (400 `invalid_nominal_frequency`); before, power was computed at a fixed 50 Hz. This is the NF-3A matrix behaviour for C-11..C-13; a Manual value restores it.
3. **The no-authority path of the power service** (non-production callers only) still evaluates at the one sanctioned 50 Hz default and stores no provenance.
4. **Power channels have no explicit-frequency option**; a new one always follows the recording. A channel stored before NF-3F stays explicit and is never flagged.
5. **Pre-existing, unchanged:** a comment in the single-phase power branch cites `PHASOR_MIN_SAMPLES_PER_CYCLE = 8`, but the gate applied is the RMS constant `MIN_SAMPLES_PER_CYCLE = 4`; `calculated_channel_staleness._agree` is a third, pairwise copy of the agreement arithmetic. Neither was touched (outside scope; NF-3A says NF-3 adds no new numeric gate).
6. The legend-visibility timing flake and the CSV/Excel failures are carried unchanged.
7. F-1 (RMS window rounding), the RMS Waveform Toggle, WUI work and Auto Base evidence were not touched.

## 8. NF-3I readiness (gate activation is NOT part of this work)

Engineering consumers are complete, so the NF-3A section 8.2 inventory condition is met (the one open row is the O-3 exclusion). What remains is the separately authorised gate transition:

- **Owner review and acceptance** of this candidate (`194d8ba` functional; documentation commit follows).
- **A single, separate gate-opening commit** that (a) flips `WW_NF_CONSUMERS_MIGRATED`, (b) replaces the preview line with a statement of what the setting applies to **including that it does not apply to Auto Base evidence (C-17)**, and (c) introduces the deliberate deployment path for the Manual server gate (`NOMINAL_FREQUENCY_MANUAL_OVERRIDE_ENABLED`) and `nominalFrequencyOverride`, **editing the refusal in `config.py` (a deployed build rejects the variable) in the same reviewed commit** and updating the static tests that forbid them.
- **O-12:** whether the documented browser qualification (CSV/Excel set and the legend timing flake) is acceptable "unchanged as a set", and that interactive owner UAT is mandatory.
- **Interactive UAT in an isolated DEV-like environment with the gate on** (NF-3A section 10 checklist: 50 and 60 Hz, CSV assumed, unparseable and zero `lf`, Manual 60 on a 50 Hz recording, a frequency change with RMS and **power** channels present, two recordings with different frequencies in a phasor analysis **and in a power calculation**, reset and re-add).
- **Decision for the owner:** limitation 1 (should native oscillation members carry the recording's frequency?).

Gate state, verified on this tree: `WW_NF_CONSUMERS_MIGRATED = false`; `nominal_frequency_manual_override_enabled` and `ben5k_experimental_enabled` default to false; no deployment file sets the Manual gate; `compose.dev.yaml` (the pre-existing DEV overlay, unchanged) is the only file that enables BEN5K.

## 9. Governance compliance (DEC-218)

Documents consulted: AGENTS.md, CLAUDE.md, the project-memory README, DEC-217/218/219, NF-3A (sections 4, 5.5, 8, 9.5-9.7, 11, 13), NF-3B, NF-3C, NF-3E and the NF integration record. Decisions preserved: DEC-217 and its Amendment 1, DEC-218, DEC-219, O-1, O-3, the NF-3E staleness and Option B policy, the PU S1-S6 authorities. Approved amendments: DEC-217 Amendment 1 only (the owner's O-2/O-9 decisions, recorded as instructed). No existing policy was changed; no unresolved policy conflict; one owner decision is requested (limitation 1). Deviation from scope: none (no F-1, RMS, WUI, Auto Base, NF-3I, push, merge, deploy or PROD activity).
