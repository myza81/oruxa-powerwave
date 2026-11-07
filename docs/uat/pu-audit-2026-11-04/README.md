# Owner UAT — PU audit Slices 1–4 and Stages 5A–5B

Prepared 2026-11-04 for **DEV only**. Owner approved the six PU commits,
ephemeral workspace design and feature-branch UAT route in the
[release plan](../../project-memory/PU_AUDIT_DEV_READINESS_2026-11-04.md).
The release also includes the separately authorized Peak/modal fix. Final
push/deployment confirmation is still required. Do not run a
destructive workspace reset against an analysis you want to keep.

Record: tester/date/browser/viewport, full deployed API and frontend SHAs,
workspace id, original filenames, accepted bases/sides and screenshots. Use one
browser tab for edits; tabs on the same origin share a live workspace. A backend
restart/deployment/rollback loses that workspace. Keep these notes externally.

## Get deterministic example recordings

From this repository, generate six small files in a fresh temporary directory:

```powershell
$uatFiles = Join-Path $env:TEMP ('powerwave-pu-uat-' + [guid]::NewGuid().ToString('N'))
python docs/uat/pu-audit-2026-11-04/generate_fixtures.py $uatFiles
Write-Output $uatFiles
```

The generator uses only Python's standard library. Alternatively use the
generated `uat-fixtures` directory supplied with the readiness evidence. Upload
each matching `.cfg` / `.dat` pair through **Recordings → Upload**. The examples
are synthetic; they contain no owner data and do not represent CT/VT scaling.

| Pair | Sample reference | Current peak per phase | Use |
|---|---|---:|---|
| `PU_UAT_PRIMARY` | COMTRADE P | 4199 A | Main automatic/manual/nested/Voltage/Power tests |
| `PU_UAT_SECONDARY` | COMTRADE S | 4.199 A | Secondary reference checks |
| `PU_UAT_UNKNOWN` | No P/S declaration | 4199 A | Unknown physical side, fail-closed checks |

Each recording has 201 samples at 1 kHz over 200 ms, 50 Hz, starting at
10:00:00.000. Channels are balanced three-phase **BUS VR/VY/VB** in kV, and
**IBT1 HV IR/IY/IB**, **IBT1 LV IR/IY/IB** in A. HV/LV labels identify separate
test authorities: these are synthetic identical currents, not a transformer
ratio model. The R currents are equal and in phase. At 5 ms they reach their
positive peak; at 15 ms their negative peak. Three auto-discovered groups should
appear: BUS VOLTAGE, IBT1 HV CURRENT and IBT1 LV CURRENT.

Expected displayed values may be rounded (e.g. 2.0995 becomes 2.1 in a cursor
cell). Use a Peak annotation for the recorded sample maximum; use cursors near
5/15 ms as a sign/unit check. Do not require an exactly clicked time to have the
peak value unless the displayed cursor time confirms the peak sample. For RMS
and Power interior windows allow 0.2% fixture quantization/window tolerance;
recorded R-phase instantaneous peaks have exact expected values below.

## Initial setup on the approved DEV build

- [ ] Open `https://dev.powerwave.oruxa.uk`; hard-refresh. Confirm backend
  connectivity and the full deployed version against the release record. Both
  `/health.git_sha` and frontend `/config.js` `buildVersion` must match the approved
  deployment SHA and say development. Do not test mixed versions.
- [ ] Use a disposable workspace and upload `PU_UAT_PRIMARY.cfg/.dat`.
- [ ] Open **Waveform → Per-Unit settings → Measurement Groups**. Select this
  recording. Review channel membership in the three groups above. If a group is
  missing, first use **Suggest groups** and review; do not continue with a
  different membership or silently substitute Source Default.
- [ ] Edit BUS VOLTAGE: nominal **275 kV L-L**, automatic reference. Save.
  Confirm L-G/phase reference and confirmed/ready status. Saving a reviewed
  suggested group is the existing confirmation workflow.
- [ ] Edit both Current groups: **Manual Ibase, 2 kA, base reference Primary**.
  Save each. This declaration describes the base independently of the recording's
  measurement side. Confirm each is ready/confirmed.
- [ ] In **Calculated Channels → New Channel → Addition**, use the input picker
  and **+ Add Channel** to add **IBT1 HV IR** and **IBT1 LV IR**, both from this
  recording. Name the result **UAT sum** and create it. Keep the default null
  policy. Preview/definition must show Current, A and these exact inputs.
- [ ] In Waveform select UAT sum; switch to **PU** and **Separate** view.
  Add **Maximum Peak (+Peak)** from the annotation menu and select this trace.
  Enable A/B cursors; position near 5 and 15 ms and record the displayed times.

The readiness review exercised this import/group-save/Addition-builder path
locally for all three fixture pairs. Actual DEV owner UAT remains to be done.

## Automatic bases and live updates

1. [ ] With both Primary groups at 2 kA, UAT sum is **configured, 4.199 pu peak**
   (`(4199 + 4199) / 2000`). Open its context menu → **Per-unit configuration**:
   Automatic, automatic common Current base **2 kA**, Primary measurement/base
   sides. It must not claim just one input group owns the cross-group base.
2. [ ] Switch to ENG: peak **8398 A**. Return to PU: **4.199 pu**. List row,
   plot/legend, cursor units, callout and Peak must agree after each change.
   Existing cursor times/annotation sample anchors must not move.
3. [ ] Edit only LV's Current group base to **4 kA, Primary**. In Automatic the
   sum becomes PU unavailable with a differing-bases explanation; Waveform
   safely shows its physical **8398 A**, with A labels, rather than a fabricated
   pu value. Individual HV/LV inputs still use their own accepted group bases.
4. [ ] Optionally set a **Source Default direct Current base 1 kA, Primary**
   through the existing Per-Unit Source Default editor. The incompatible grouped
   sum must remain unavailable; it must not become 8.398 pu. A genuinely
   ungrouped channel may still use its Source Default. Do not delete groups in
   this workspace just to create that extra case.
5. [ ] Restore LV to **2 kA, Primary**. Automatic sum returns to **4.199 pu**
   without recreating the channel. Leave LV at 4 kA again for the manual tests.

## Result-specific manual override, edits and rejection

Open UAT sum's **Per-unit configuration** from its Waveform context menu (also
available from its Calculated Channels row action).

1. [ ] Choose **Manual override → 4 kA → Primary → Save PU configuration**.
   The accepted result is **2.0995 pu peak**, even with input bases 2/4 kA.
   Provenance says manual calculated Current base; source/group bases and their
   sides stay 2/4 kA Primary. ENG remains **8398 A**.
2. [ ] Close/reopen: Manual, 4 kA and Primary remain. Navigate to another page
   and back; refresh and reselect the calculated result. The same live workspace
   still holds the configuration. An empty initial plot after refresh is not
   evidence that the stored base was lost.
3. [ ] Edit to **2 kA, Primary** and save: **4.199 pu**. Enter **4000 A, Primary**
   and save: **2.0995 pu**. Reopen and check the equivalent accepted base/unit.
4. [ ] Starting from accepted 4 kA Primary, attempt **0**, then **-4**. Each
   rejected save must show an error, retain the open form and leave the prior
   accepted base/provenance, 2.0995 pu waveform, cursor/annotation values and
   input group settings intact. Close/reopen to distinguish unsaved form text
   from the saved authoritative configuration. If the browser prevents submission
   itself, verify the accepted state is still intact; server rejection is
   separately covered by automated API regressions.
5. [ ] With the same Primary samples, submit **4 kA, Secondary**, then
   **4 kA, Unknown**. Both must reject; neither may reinterpret the samples or
   replace the accepted Primary base. Selecting Primary on a different recording
   with Unknown sample side does not establish its measurement side.
6. [ ] Check immediate synchronization after each accepted base edit: calculated
   list row, plot/legend, cursor A/B, callout and Peak all use the current values
   and unit. Rapid ENG/PU changes must settle on the last selected mode. A slower
   old response must not restore a previous base or label.

## Unassigned, Return to Automatic and nested channels

1. [ ] Set **Unassigned** and save. PU is explicitly unavailable; the physical
   sum is still **8398 A**. Close/reopen and refresh/reselect: Unassigned remains.
   It must not silently behave like Automatic.
2. [ ] Click the separate **Return to Automatic** action. With input bases still
   2/4 kA, Automatic is saved but PU remains unavailable. Restore LV to 2 kA:
   Automatic becomes **4.199 pu**. No old manual 4 kA denominator remains active.
3. [ ] Restore LV to 4 kA. Save UAT sum Manual **4 kA Primary** again. Create
   **Absolute Value** with **UAT sum** as its sole calculated input; name it
   **UAT child**. Definition/preview stays physical A; peak **8398 A**.
4. [ ] In Automatic the child is unavailable because the original source bases
   differ. It must not inherit the parent's manual 4 kA base.
5. [ ] Save the child Manual **2 kA Primary**: child peak **4.199 pu** while the
   parent remains **2.0995 pu**. Parent Unassigned does not disable the child's
   own valid Manual choice or alter the physical child calculation.
6. [ ] Return the child to Automatic: unavailable until original HV/LV bases
   agree. Restore both to 2 kA Primary and confirm child **4.199 pu** even while
   the parent is Unassigned. Its automatic authority is the source leaves.
7. [ ] In **Event Reconstruction**, add this recording and select the child.
   Choose its own ENG/PU controls: ENG peak **8398 A**, eligible PU **4.199 pu**.
   Make source bases incompatible, return to ER and verify retained channel
   selection, clear PU-unavailable reason and no falsely labeled PU trace. ENG
   remains available. ER mode must not change because Waveform mode changed.

## Independent Primary / Secondary / Unknown reference checks

Use each separate recording's own groups and inputs; do not mix different
recordings/time authorities accidentally.

| Check | Setup/action | Expected |
|---|---|---|
| Primary mismatch | PRIMARY recording; independently declare one input Group's base Secondary | New cross-group Automatic unavailable despite equal numeric bases. Restore Primary explicitly. |
| Primary unknown base | PRIMARY; set one base's reference Unknown | Automatic across those groups unavailable; sample P must not silently fill that base declaration. |
| Equipment-derived base | PRIMARY; change a Current group to equipment-rating method, 1000 MVA, linked to 275 kV BUS Voltage Group | Base **2.099455524 kA**, Primary. This does not change the recorded samples. |
| Method transition | Switch that derived group to Manual, enter its numeric equivalent but leave side Unknown | The former derived Primary declaration must not silently carry into the new manual method. Cross-group eligibility requires an explicit valid side. |
| Distinct secondary authorities | SECONDARY; save both Current groups Manual **0.004 kA = 4 A**, Secondary. Create their R-current Addition | Physical sum peak **8.398 A**. Automatic unavailable even though both bases are 4 A; a shared secondary-reference identity is not established. A result Manual Secondary base must also reject across these two authorities. |
| Established single secondary authority | SECONDARY; create Absolute Value of **IBT1 HV IR** only. Set result Manual **4 A, Secondary** | Accepted, peak **1.04975 pu**. Primary or Unknown manual result side rejects without replacing that accepted configuration. |
| Unknown physical side | UNKNOWN; independently save both Group bases **2 kA, Primary** and create their R-current Addition | Physical sum **8398 A**, automatic unavailable. A result Manual **4 kA, Primary** must reject because choosing base side does not declare sample side. |

CSV/BEN remain Unknown absent an approved provider/declaration contract; this
release adds no sample-side editor. Existing same-group/shared-default automatic
compatibility is preserved; do not interpret that historical behavior as a new
proof of cross-group physical equivalence. No CT/VT ratio scaling occurs in any
case, and filenames or apparent magnitudes do not establish side.

## Voltage PU, linked bases and rejected configuration saves

Use PRIMARY and BUS VOLTAGE. Restore its nominal 275 kV, automatic L-G reference.

1. [ ] Display **BUS VR**: physical positive peak **224.536559755 kV**; L-G
   base **158.771324027 kV**; instantaneous peak **sqrt(2) = 1.414213562 pu**.
   Create an **RMS** calculated result of BUS VR at 50 Hz, one cycle: interior
   RMS approximately **1 pu**, not sqrt(2). Ignore established edge-window gaps.
2. [ ] Choose Manual reference **L-G** on that Voltage Group and save. Same
   correct values. Return to Automatic and save; same reference/value result.
3. [ ] Attempt nominal voltage **0** or **-132**. Reject without changing the
   accepted 275 kV base or displayed PU values. A malformed missing-reference
   API request and rejected membership/status PATCH are covered by automated
   atomicity tests; this interface need not expose nonexistent-channel inputs.
4. [ ] Configure HV Current equipment rating **1000 MVA**, linked to BUS.
   Record **2.099455524 kA**, calculated independently as
   `1000 / (sqrt(3) * 275)`. Reject an invalid Voltage change: this linked base
   must remain unchanged. Accept **132 kV**: base becomes **4.373865676 kA**
   and raw BUS VR peak becomes **2.946278255 pu**. Restore 275 kV and confirm
   both original values return. A linked Current base must use nominal L-L.
5. [ ] Generic Voltage **Subtraction BUS VR − BUS VY**, and Absolute Value/RMS
   descendants of that generic result, must not acquire an automatic PU base
   from a group or Source Default (DEC-052/116). ENG still works. The dedicated
   **Line-to-Line Voltage (L-L)** operation retains its declared L-L semantics;
   with a ready BUS engineering context and 275 kV base, its theoretical sine
   amplitude is sqrt(2) pu. This 1 kHz fixture samples the L-L maximum between
   sample instants: the **recorded L-L peak is 1.406469794 pu**, not exactly
   sqrt(2). Do not substitute generic subtraction for the dedicated operation.
6. [ ] If using Compliance, select the ready BUS phase-voltage RMS measurement:
   interior approximately **1 pu** at 275 kV. Missing/unsupported measured units
   must report unavailable, not configured with unconverted numbers. The
   synthetic pack has valid units; unsupported-unit API cases are automated.

## Peak/modal overlap regression — expected corrected behavior

- [ ] With a Maximum Peak annotation present, reopen Per-unit configuration.
  Provenance and controls must render above the Peak. Close the dialog, drag the
  Peak to the position occupied by Save and reopen. Save must still work without
  moving the annotation, forced clicking, reload or lost configuration.
- [ ] Repeat with Minimum Peak at 1280 × 720 and the engineer's normal viewport.
  Check base/unit/side fields, Return to Automatic, Save and both Close controls.
  Verify successful 4-to-2 kA saves give 2.0995-to-4.199 pu; rejected zero leaves
  the accepted base/value intact. Header Close, Escape and backdrop Close retain
  their existing behavior. No annotation should intercept modal input.
- [ ] Close the dialog and drag the Peak normally by its header in the waveform
  work area. Its box moves; its data anchor, accepted base and numerical values
  do not. If an annotation covers a control, stop and preserve a screenshot:
  that behavior is now a regression, not an accepted release limitation.

## Power Calculator and calculated Power smoke tests

PU settings must not alter engineering Power arithmetic.

1. [ ] **Calculator → Power & Current → Current**: 100 MVA, 132 kV, three-phase
   L-L gives **437.4 A**. Single-phase gives **757.6 A**. Return to three-phase.
2. [ ] **P-Q-S**: P=80 MW and Q=60 MVAr, S left derived, gives **100 MVA** and
   PF **0.800 lagging**. **Power Factor**: S=100 MVA, PF=0.8 gives P=80 MW,
   Q=+60 MVAr lagging; choosing leading gives **-60 MVAr**. Zero apparent power
   reports undefined PF safely; no NaN/Infinity or silently invented value.
3. [ ] **V-I Phasors**: V=11 kV at 0 degrees, I=100 A at -30 degrees gives
   P approximately **0.952628 MW**, Q **+0.55 MVAr**, S **1.1 MVA**,
   PF **0.8660 lagging**. I angle +30 degrees changes Q to **-0.55 MVAr** and
   PF leading. These are RMS phasor inputs; no extra sqrt(2) factor applies.
4. [ ] Using PRIMARY, create single-phase **Active Power**, **Reactive Power**
   and **Apparent Power** with BUS VR / IBT1 HV IR, 50 Hz, default supported
   window. Interior expected P and apparent magnitude approximately
   **471.4145 MW / MVA**, Q approximately **0 Mvar** (balanced in-phase inputs).
   Confirm exact input references/type and retained MW/Mvar/MVA units in the
   list, preview, plot and cursors. The compact label may omit repeated input
   names; the expression/details must retain the correct inputs.
5. [ ] Create the dedicated three-phase P/Q/apparent operations. In the set
   picker choose the matching BUS-voltage / HV-current set if offered. Otherwise
   use its existing **Manual selection** option: select BUS VR/VY/VB as the
   three phase-to-neutral voltages, and IBT1 HV IR/IY/IB as the corresponding
   currents, in that order. Review and explicitly confirm phase-to-neutral
   meaning and phase alignment using the existing confirmation checkboxes.
   Interior expected
   P/apparent approximately **1414.2435 MW / MVA**, Q approximately zero.
   Respect existing readiness requirements; do not misclassify or relabel
   channels to force a result. All channels use the same sample side/timebase here.
6. [ ] Change UAT sum/child manual Current bases and toggle PU. These Power
   results and standalone Calculator numbers remain unchanged; Power is not
   normalized by the new manual Current result base. No new Power PU editor
   should appear. Verify phase subscripts/units remain readable.

## Finish and record

- [ ] Record every pass/failure and accepted limitation; capture the deployed
  full SHA with each report. Do not treat automated local passes as owner signoff.
- [ ] Before deliberately testing reset, save screenshots/settings externally.
  Confirm **Start New Workspace** removes old sources/calculations/manual bases.
  Reimporting the same file does not restore the removed calculated result/base.
- [ ] Stop on unexplained values, unit inconsistencies, rejected-save mutation,
  unknown-side bypass, unrecoverable controls or mixed deployment versions.
  Preserve the evidence; request the reviewed rollback if needed.
- [ ] Owner outcome: **Accept / Accept with listed limitations / Reject**.
  No PROD deployment, merge, further remediation or consolidated audit follows
  automatically from completing this checklist.
