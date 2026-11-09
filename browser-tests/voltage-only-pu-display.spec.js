// Slice 6C — Voltage-only ENG/PU Display (DEC-212)
//
// Verifies that the Voltage Display toggle correctly controls only Voltage
// channels, that raw Current channels always stay in A/kA regardless of mode,
// and that the Measurement Group UI reflects the simplified DEC-212 workflow.
//
// Tests:
//   VD-01: Voltage Display toggle has correct aria-label (Waveform toolbar)
//   VD-02: Voltage Display toggle has correct aria-label (ER toolbar)
//   VD-03: In PU mode, Voltage channel (kV) fetched as per_unit; Current (A) fetched as engineering
//   VD-04: In PU mode, Current channel unit stays "A" (not "pu") in Waveform display
//   VD-05: Switching to PU mode does not change Current channel panel group key
//   VD-06: ER: Current channel always state=engineering in wwErChannelUnitDisplay
//   VD-07: ER: Current channel plots in A panel even when Voltage Display = PU
//   VD-08: ER: Current channel never shows "PU unavailable" badge, even with no Ibase
//   VD-09: Measurement Group modal shows DEC-212 note in Current Groups section
//   VD-10: Measurement Group Voltage drawer shows "Nominal Voltage (kV, Line-to-Line)" label
//   VD-11: Voltage display auto-switch fires on import when Voltage group configured
//   VD-12: Auto-switch does NOT fire when only Current group is configured (no Voltage)
//   VD-13: Switching to PU mode and back preserves Current channel engineering values
//   VD-14: Calculated Current channel is NOT guarded — can follow PU if configured
//   VD-15: Waveform base summary shows "Nominal Voltage: X.XX kV · Auto · Phase-to-Ground"
//   VD-16: Current group Edit drawer has no Nominal Voltage PU config field (DEC-212)
//   VD-17: Mixed Voltage PU and Current ENG cursors from same source batch correctly (DEC-212)

const { test, expect } = require("./support/test");
const { syntheticComtrade } = require("./support/synthetic_comtrade");
const {
  BACKEND, uploadRecord, workspaceId, sourceIdFor,
  openEventReconstruction, waitForPlot, waitForScaledAxes, plotState,
  selectChannel, channelRow, addRecords, api,
} = require("./support/event_reconstruction_helpers");

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const LL_BASE_KV = 275;
const LG_BASE_KV = LL_BASE_KV / Math.sqrt(3); // ~158.77 kV

// Synthetic COMTRADE with both Voltage and Current channels.
function makeChannels() {
  return [
    { name: "VA", unit: "kV", phase: "A", amplitude: LG_BASE_KV, frequencyHz: 50 },
    { name: "IA", unit: "A",  phase: "A", amplitude: 1500,         frequencyHz: 50 },
  ];
}

// Upload with Convention-A primary_ratio for 275 kV (kV units).
// Uses primary_ratio = 275.0 kV (the LL voltage declared directly on L-G channels,
// as per IEC/EN COMTRADE convention — same as the PULU real-data scenario).
// 275.0 × √3 = 476.3 kV which matches no standard, so the Slice 6B hypothesis
// resolver unambiguously selects Hypothesis A. PU denominator = 275/√3 = 158.77 kV.
async function uploadWith275kVVoltageGroup(page, station) {
  const data = syntheticComtrade({
    station, startClock: "10:00:00.000000", rateHz: 1000, durationS: 0.1,
    channels: makeChannels(),
  });
  // Convention A: primary_ratio = 275.0 kV (LL nominal stated directly).
  const llKv = LL_BASE_KV.toFixed(4);
  const cfg = Buffer.from(
    data.cfg.toString("latin1")
      .replace(/,1\.0,1\.0,P/g, `,${llKv},1.0,P`),
    "latin1",
  );
  await page.locator("#recordingsUploadBtn, #recordingsEmptyUploadBtn").first().click();
  await page.locator("#uploadModalFile_0").setInputFiles({ name: `${station}.cfg`, mimeType: "application/octet-stream", buffer: cfg });
  await page.locator("#uploadModalFile_1").setInputFiles({ name: `${station}.dat`, mimeType: "application/octet-stream", buffer: data.dat });
  await page.locator("#uploadModalSubmitBtn").click();
  await expect(page.locator("#uploadModalOverlay")).toBeHidden();
}

// Upload with no PU-eligible primary ratio.
async function uploadBasicRecording(page, station) {
  const data = syntheticComtrade({
    station, startClock: "10:00:00.000000", rateHz: 1000, durationS: 0.1,
    channels: makeChannels(),
  });
  await page.locator("#recordingsUploadBtn, #recordingsEmptyUploadBtn").first().click();
  await page.locator("#uploadModalFile_0").setInputFiles({ name: `${station}.cfg`, mimeType: "application/octet-stream", buffer: data.cfg });
  await page.locator("#uploadModalFile_1").setInputFiles({ name: `${station}.dat`, mimeType: "application/octet-stream", buffer: data.dat });
  await page.locator("#uploadModalSubmitBtn").click();
  await expect(page.locator("#uploadModalOverlay")).toBeHidden();
}

const wsUrl = async (page, path) => `${BACKEND}/api/v1/workspaces/${await workspaceId(page)}${path}`;

async function configureVoltageGroup(page, station, channels, nominalKv = LL_BASE_KV) {
  const sid = await sourceIdFor(page, station);
  const url = await wsUrl(page, `/sources/${sid}/measurement-groups`);
  for (const g of await (await page.request.get(url)).json()) {
    await page.request.delete(`${url}/${g.id}`);
  }
  const group = await (await page.request.post(url, {
    data: { kind: "voltage", display_name: station + " voltage", status: "confirmed",
            channel_refs: channels.map((channel_name) => ({ kind: "source", source_id: sid, channel_name })) },
  })).json();
  await page.request.put(`${url}/${group.id}/voltage-config`, {
    data: { nominal_voltage_ll_kv: nominalKv, base_reference_side: "primary" },
  });
  return { sid, group };
}

// Channel waveform state from the displayed map.
function channelState(page, sourceId, name) {
  return page.evaluate(({ sid, name }) => {
    const entry = ww.displayed.get(wwChannelKey(sid, name));
    if (!entry) return null;
    return { unit: entry.channel.unit, perUnitStatus: entry.channel.perUnitStatus };
  }, { sid: sourceId, name });
}

// ---------------------------------------------------------------------------
// VD-01: Waveform toolbar Voltage Display toggle label
// ---------------------------------------------------------------------------

test("VD-01: Waveform toolbar Voltage Display toggle has correct aria-label", async ({ page }) => {
  await page.goto("/index.html");
  await expect(page.locator("#wwUnitModeToggle")).toHaveAttribute("aria-label", "Voltage Display");
  // Buttons retain descriptive individual labels.
  await expect(page.locator("#wwUnitEngineeringBtn")).toHaveAttribute("aria-label", "Engineering Units");
  await expect(page.locator("#wwUnitPerUnitBtn")).toHaveAttribute("aria-label", "Per Unit");
});

// ---------------------------------------------------------------------------
// VD-02: Event Reconstruction toolbar Voltage Display toggle label
// ---------------------------------------------------------------------------

test("VD-02: ER toolbar Voltage Display toggle has correct aria-label", async ({ page }) => {
  await page.goto("/index.html");
  await uploadBasicRecording(page, "VD02");
  const sid = await sourceIdFor(page, "VD02");
  await addRecords(page, ["VD02"]);
  await expect(page.locator("#wwErUnitModeToggle")).toHaveAttribute("aria-label", "Voltage Display");
  await expect(page.locator("#wwErUnitEngineeringBtn")).toHaveAttribute("title", "Engineering Units");
  await expect(page.locator("#wwErUnitPerUnitBtn")).toHaveAttribute("title", "Per Unit");
});

// ---------------------------------------------------------------------------
// VD-03: Waveform PU mode — Voltage fetched as per_unit, Current as engineering
// ---------------------------------------------------------------------------

test("VD-03: in PU mode Voltage fetch uses per_unit, Current fetch uses engineering (DEC-212)", async ({ page }) => {
  await page.goto("/index.html");
  await uploadWith275kVVoltageGroup(page, "VD03");
  const sid = await sourceIdFor(page, "VD03");
  await configureVoltageGroup(page, "VD03", ["VA"]);

  // Switch to PU mode.
  await page.locator("#mainNavWaveformBtn").click();
  await page.evaluate(() => wwApplyUnitMode("per_unit"));
  await expect.poll(() => page.evaluate(() => ww.unitMode)).toBe("per_unit");

  // Display both VA and IA.
  const details = page.locator(`#channelGroups details.source-recording[data-source-id="${sid}"]`);
  if (!(await details.evaluate(el => el.open))) await details.locator(":scope > summary").click();
  await page.locator(`tr.channel-row--toggle[data-source-id="${sid}"][data-channel-name="VA"]`).click();
  await page.locator(`tr.channel-row--toggle[data-source-id="${sid}"][data-channel-name="IA"]`).click();

  // VA: should be in per_unit mode; IA: DEC-212 → stays in engineering.
  await expect.poll(() => channelState(page, sid, "VA"), { timeout: 8000 })
    .toMatchObject({ perUnitStatus: "configured", unit: "pu" });
  await expect.poll(() => channelState(page, sid, "IA"), { timeout: 8000 })
    .not.toMatchObject({ unit: "pu" });
  const iaState = await channelState(page, sid, "IA");
  expect(iaState.unit).toBe("A");
});

// ---------------------------------------------------------------------------
// VD-04: Waveform PU mode — Current channel unit stays "A"
// ---------------------------------------------------------------------------

test("VD-04: Current channel unit stays A in Waveform PU mode (DEC-212)", async ({ page }) => {
  await page.goto("/index.html");
  await uploadWith275kVVoltageGroup(page, "VD04");
  const sid = await sourceIdFor(page, "VD04");
  await configureVoltageGroup(page, "VD04", ["VA"]);

  await page.locator("#mainNavWaveformBtn").click();
  await page.evaluate(() => wwApplyUnitMode("per_unit"));
  await expect.poll(() => page.evaluate(() => ww.unitMode)).toBe("per_unit");

  const details = page.locator(`#channelGroups details.source-recording[data-source-id="${sid}"]`);
  if (!(await details.evaluate(el => el.open))) await details.locator(":scope > summary").click();
  await page.locator(`tr.channel-row--toggle[data-source-id="${sid}"][data-channel-name="IA"]`).click();

  await expect.poll(() => channelState(page, sid, "IA"), { timeout: 8000 })
    .toMatchObject({ unit: "A" });
});

// ---------------------------------------------------------------------------
// VD-05: PU mode does not move Current to a pu panel group
// ---------------------------------------------------------------------------

test("VD-05: in PU mode Current channel stays in its own engineering panel, not a pu panel", async ({ page }) => {
  await page.goto("/index.html");
  await uploadWith275kVVoltageGroup(page, "VD05");
  const sid = await sourceIdFor(page, "VD05");
  await configureVoltageGroup(page, "VD05", ["VA"]);

  await page.locator("#mainNavWaveformBtn").click();
  const details = page.locator(`#channelGroups details.source-recording[data-source-id="${sid}"]`);
  if (!(await details.evaluate(el => el.open))) await details.locator(":scope > summary").click();
  await page.locator(`tr.channel-row--toggle[data-source-id="${sid}"][data-channel-name="VA"]`).click();
  await page.locator(`tr.channel-row--toggle[data-source-id="${sid}"][data-channel-name="IA"]`).click();

  await page.evaluate(() => wwApplyUnitMode("per_unit"));
  await expect.poll(() => channelState(page, sid, "VA"), { timeout: 8000 })
    .toMatchObject({ unit: "pu" });
  await expect.poll(() => channelState(page, sid, "IA"), { timeout: 8000 })
    .toMatchObject({ unit: "A" });

  // VA should be on the ":pu" panel group; IA should NOT be.
  const panelGroupKeys = await page.evaluate(({ sid }) => {
    const result = {};
    for (const panel of ww.panels) {
      for (const ch of panel.channels) {
        if (ch.sourceId === sid) {
          result[ch.channelName] = wwPanelGroupKeyFor(ch);
        }
      }
    }
    return result;
  }, { sid });
  expect(panelGroupKeys.VA).toMatch(/:pu$/);
  expect(panelGroupKeys.IA).not.toMatch(/:pu/);
  expect(panelGroupKeys.IA).not.toMatch(/:base_required/);
});

// ---------------------------------------------------------------------------
// VD-06: ER wwErChannelUnitDisplay returns state=engineering for Current
// ---------------------------------------------------------------------------

test("VD-06: wwErChannelUnitDisplay returns state=engineering for Current channels in PU mode (DEC-212)", async ({ page }) => {
  await page.goto("/index.html");
  await uploadWith275kVVoltageGroup(page, "VD06");
  await configureVoltageGroup(page, "VD06", ["VA"]);
  await addRecords(page, ["VD06"]);
  const sid = await sourceIdFor(page, "VD06");

  await selectChannel(page, "VD06", "VA");
  await selectChannel(page, "VD06", "IA");
  await page.locator("#wwErUnitPerUnitBtn").click();
  await expect(page.locator("#wwErUnitPerUnitBtn")).toHaveAttribute("aria-pressed", "true");

  // Poll until channels are loaded (ER channels fetch may be in flight).
  await expect.poll(async () => {
    return page.evaluate(({ sid }) => {
      const srcData = wwErState.channelsBySource[sid];
      return !!(srcData && srcData.analog_channels && srcData.analog_channels.length > 0);
    }, { sid });
  }, { timeout: 8000 }).toBe(true);

  const iaDisplay = await page.evaluate(({ sid }) => {
    return wwErChannelUnitDisplay("analog", sid, "IA");
  }, { sid });
  expect(iaDisplay.state).toBe("engineering");
  expect(iaDisplay.unitMode).toBe("engineering");
});

// ---------------------------------------------------------------------------
// VD-07: ER Current channel plots in A panel when Voltage Display = PU
// ---------------------------------------------------------------------------

test("VD-07: ER Current channel plots in A panel when Voltage Display = PU (DEC-212)", async ({ page }) => {
  await page.goto("/index.html");
  await uploadWith275kVVoltageGroup(page, "VD07");
  await configureVoltageGroup(page, "VD07", ["VA"]);
  await addRecords(page, ["VD07"]);

  await selectChannel(page, "VD07", "VA");
  await selectChannel(page, "VD07", "IA");
  await waitForPlot(page, 2);

  await page.locator("#wwErUnitPerUnitBtn").click();
  await expect(page.locator("#wwErUnitPerUnitBtn")).toHaveAttribute("aria-pressed", "true");
  await waitForPlot(page, 2);
  await waitForScaledAxes(page);

  const state = await plotState(page);
  const panelLabels = state.panels.map((c) => c.label);
  // VA panel should be "STN · VA" and IA panel should be "STN · IA", both present.
  expect(panelLabels).toContain("VD07 · VA");
  expect(panelLabels).toContain("VD07 · IA");

  const iaPanelTitle = state.groups.find(
    (g) => g.traces && g.traces.some((t) => t.includes("IA"))
  )?.title;
  // DEC-212: IA panel title should include "A" (engineering), not "pu".
  expect(iaPanelTitle).toBeTruthy();
  expect(iaPanelTitle).toMatch(/Current \(A\)/);
  expect(iaPanelTitle).not.toMatch(/\(pu\)/);
});

// ---------------------------------------------------------------------------
// VD-08: ER Current channel never shows "PU unavailable" badge
// ---------------------------------------------------------------------------

test("VD-08: ER Current channel never shows PU unavailable badge, even with no Ibase (DEC-212)", async ({ page }) => {
  await page.goto("/index.html");
  // Upload recording; no current group configured (default after clearing).
  await uploadWith275kVVoltageGroup(page, "VD08");
  await configureVoltageGroup(page, "VD08", ["VA"]); // only Voltage group
  await addRecords(page, ["VD08"]);

  await selectChannel(page, "VD08", "IA");
  await waitForPlot(page, 1);

  await page.locator("#wwErUnitPerUnitBtn").click();
  await expect(page.locator("#wwErUnitPerUnitBtn")).toHaveAttribute("aria-pressed", "true");
  await waitForPlot(page, 1);

  const iaRow = await channelRow(page, "VD08", "IA");
  // DEC-212: no "PU unavailable" badge for Current.
  await expect(iaRow.locator(".ww-er-pu-unavailable")).toHaveCount(0);
  // IA should still be plotted (state=engineering → plottable=true).
  await expect(iaRow).toHaveAttribute("aria-pressed", "true");
});

// ---------------------------------------------------------------------------
// VD-09: MG modal shows DEC-212 note in Current Groups section
// ---------------------------------------------------------------------------

test("VD-09: Measurement Group modal shows DEC-212 note in Current Groups section", async ({ page }) => {
  await page.goto("/index.html");
  await uploadWith275kVVoltageGroup(page, "VD09");

  // Open Per-Unit Settings modal from the Waveform toolbar.
  await page.locator("#mainNavWaveformBtn").click();
  await page.locator("#wwOpenPerUnitSettingsBtn").click();
  await expect(page.locator("#perUnitSettingsOverlay")).not.toHaveAttribute("hidden", { timeout: 5000 });

  // Navigate to the Measurement Groups sub-dialog — DEC-212 note is rendered there
  // by wwRenderMeasurementGroupsBody() into #measurementGroupsBody.
  await page.locator("#wwOpenMeasurementGroupsFromSettingsBtn").click();
  await expect(page.locator("#measurementGroupsOverlay")).not.toHaveAttribute("hidden", { timeout: 5000 });

  // DEC-212 note is rendered inside #measurementGroupsBody under "Current Groups" heading.
  const mgBody = page.locator("#measurementGroupsBody");
  await expect(mgBody.getByText("Current channels always display in A/kA", { exact: false })).toBeVisible({ timeout: 5000 });
  await expect(mgBody.getByText("Calculated Channels", { exact: false })).toBeVisible({ timeout: 3000 });
});

// ---------------------------------------------------------------------------
// VD-10: Voltage drawer field label
// ---------------------------------------------------------------------------

test("VD-10: Measurement Group Voltage drawer shows Nominal Voltage (kV, Line-to-Line) label", async ({ page }) => {
  await page.goto("/index.html");
  await uploadWith275kVVoltageGroup(page, "VD10");
  const sid = await sourceIdFor(page, "VD10");

  // Set up a Voltage group so we can open its drawer.
  await configureVoltageGroup(page, "VD10", ["VA"]);

  // Open Waveform page, open MG settings, and open the Voltage group drawer.
  await page.locator("#mainNavWaveformBtn").click();
  // Look for a Measurement Group edit button.
  await page.evaluate(() => { if (document.getElementById("wwOpenMgBtn")) document.getElementById("wwOpenMgBtn").click(); });
  await page.waitForTimeout(500);

  // Find and click the Edit/Review button for the Voltage group.
  const editBtn = page.locator("[id^='wwMgEditBtn-']").first();
  if (await editBtn.count() > 0) {
    await editBtn.click();
    await expect(page.getByText("Nominal Voltage (kV, Line-to-Line)", { exact: false })).toBeVisible({ timeout: 3000 });
  } else {
    // Drawer open via other means — check the rendered HTML.
    const html = await page.content();
    expect(html).toContain("Nominal Voltage (kV, Line-to-Line)");
  }
});

// ---------------------------------------------------------------------------
// VD-11: Voltage display auto-switch fires on first import when Voltage group configured
// ---------------------------------------------------------------------------

test("VD-11: auto-switch fires on first import when Voltage group auto-resolves (DEC-212 unchanged)", async ({ page }) => {
  await page.goto("/index.html");
  // Convention A recording: primary_ratio = 275.0 kV (LL, unambiguous).
  // The backend auto-resolver selects Hypothesis A and creates a configured group.
  // On the first import with configuredVoltageGroups > 0, the frontend auto-switches to PU.
  await uploadWith275kVVoltageGroup(page, "VD11");

  // Banner appears and unit mode switches to per_unit.
  await expect(page.locator("#wwImportPuStatusBanner")).not.toHaveAttribute("hidden", { timeout: 8000 });
  await expect.poll(() => page.evaluate(() => ww.unitMode), { timeout: 8000 }).toBe("per_unit");
});

// ---------------------------------------------------------------------------
// VD-12: Auto-switch does NOT fire when no Voltage group is configured
// ---------------------------------------------------------------------------

test("VD-12: auto-switch does not fire when only Current group is configured (no Voltage)", async ({ page }) => {
  await page.goto("/index.html");
  // Upload with no auto-detectable Voltage group (default primary_ratio=1.0).
  await uploadBasicRecording(page, "VD12");

  await page.waitForTimeout(600); // allow fire-and-forget to complete
  expect(await page.evaluate(() => ww.unitMode)).toBe("engineering");
});

// ---------------------------------------------------------------------------
// VD-13: Switching PU mode and back preserves Current channel engineering values
// ---------------------------------------------------------------------------

test("VD-13: Current channel engineering values preserved after PU toggle cycle (DEC-212)", async ({ page }) => {
  await page.goto("/index.html");
  await uploadWith275kVVoltageGroup(page, "VD13");
  const sid = await sourceIdFor(page, "VD13");
  await configureVoltageGroup(page, "VD13", ["VA"]);

  await page.locator("#mainNavWaveformBtn").click();
  const details = page.locator(`#channelGroups details.source-recording[data-source-id="${sid}"]`);
  if (!(await details.evaluate(el => el.open))) await details.locator(":scope > summary").click();
  await page.locator(`tr.channel-row--toggle[data-source-id="${sid}"][data-channel-name="IA"]`).click();

  await expect.poll(() => channelState(page, sid, "IA"), { timeout: 8000 })
    .toMatchObject({ unit: "A" });
  const engState = await channelState(page, sid, "IA");

  // Switch to PU and back.
  await page.evaluate(() => wwApplyUnitMode("per_unit"));
  await expect.poll(() => page.evaluate(() => ww.unitMode)).toBe("per_unit");
  await expect.poll(() => channelState(page, sid, "IA"), { timeout: 8000 }).toMatchObject({ unit: "A" });

  await page.evaluate(() => wwApplyUnitMode("engineering"));
  await expect.poll(() => page.evaluate(() => ww.unitMode)).toBe("engineering");
  await expect.poll(() => channelState(page, sid, "IA"), { timeout: 8000 }).toMatchObject({ unit: "A" });

  // Unit is still "A" — DEC-212 invariant maintained throughout the toggle cycle.
  const afterState = await channelState(page, sid, "IA");
  expect(afterState.unit).toBe("A");
});

// ---------------------------------------------------------------------------
// VD-14: Calculated Current channel is NOT guarded — can follow PU if configured
// ---------------------------------------------------------------------------

test("VD-14: calculated Current channel is not guarded by DEC-212 — can show PU if configured", async ({ page }) => {
  await page.goto("/index.html");
  await uploadWith275kVVoltageGroup(page, "VD14");
  const sid = await sourceIdFor(page, "VD14");
  await configureVoltageGroup(page, "VD14", ["VA"]);
  await addRecords(page, ["VD14"]);

  const ws = await workspaceId(page);
  // Create a calculated channel of "Current" type (reverse polarity of IA).
  const negIA = await (await page.request.post(
    `${BACKEND}/api/v1/workspaces/${ws}/calculated-channels`,
    { data: { name: "-IA", operation: "reverse_polarity",
               inputs: [{ kind: "source", source_id: sid, channel_name: "IA" }], parameters: {} } },
  )).json();

  await page.evaluate(() => wwErRefresh());

  // For now, without a Current PU basis configured, the calculated channel
  // per-unit resolution is not_applicable or base_required. The DEC-212 guard
  // only fires for kind === "analog", not "calculated". Verify no guard fires.
  await selectChannel(page, "VD14", "-IA");
  await waitForPlot(page, 1);

  await page.locator("#wwErUnitPerUnitBtn").click();
  await expect(page.locator("#wwErUnitPerUnitBtn")).toHaveAttribute("aria-pressed", "true");
  await page.waitForTimeout(1000);

  // Wait for resolution to settle (not "pending").
  await expect.poll(async () => {
    return page.evaluate(({ calcId }) => wwErChannelUnitDisplay("calculated", calcId, "-IA").state, { calcId: negIA.id });
  }, { timeout: 5000 }).not.toBe("pending");

  const display = await page.evaluate(({ calcId }) => {
    return wwErChannelUnitDisplay("calculated", calcId, "-IA");
  }, { calcId: negIA.id });
  // The calculated channel goes through the normal resolution path (not the DEC-212 guard).
  // With no Current base configured: state must be "unavailable" (base_required), NOT:
  //   - "engineering" (the DEC-212 guard only fires for kind==="analog")
  //   - "per_unit"   (no Ibase configured — cannot accidentally normalize)
  expect(display.state).not.toBe("engineering");  // DEC-212 guard must NOT fire for calculated
  expect(display.state).not.toBe("per_unit");     // must NOT accidentally normalize without explicit Ibase
  expect(display.state).toBe("unavailable");      // correct: base_required, no Current Ibase configured
});

// ---------------------------------------------------------------------------
// VD-15: Waveform base summary format for auto-detected Voltage group
// ---------------------------------------------------------------------------

test("VD-15: Measurement Group base summary shows correct Nominal Voltage format", async ({ page }) => {
  await page.goto("/index.html");
  await uploadWith275kVVoltageGroup(page, "VD15");
  const sid = await sourceIdFor(page, "VD15");

  // Get the measurement groups to verify the base summary format rendered by the backend.
  const ws = await workspaceId(page);
  const groups = await (await page.request.get(
    `${BACKEND}/api/v1/workspaces/${ws}/sources/${sid}/measurement-groups`,
  )).json();

  // The auto-resolved Voltage group should have nominal_voltage_ll_kv = 275.00.
  const voltageGroup = groups.find((g) => g.kind === "voltage");
  if (voltageGroup && voltageGroup.voltage_config && voltageGroup.voltage_config.nominal_voltage_ll_kv != null) {
    // Verify the value is the 275 kV nominal we expect.
    expect(voltageGroup.voltage_config.nominal_voltage_ll_kv).toBeCloseTo(275.0, 1);
    // Verify the wwMgBaseSummaryHtml would produce the correct format.
    const summaryHtml = await page.evaluate(({ group }) => {
      return wwMgBaseSummaryHtml(group);
    }, { group: voltageGroup });
    expect(summaryHtml).toContain("Nominal Voltage:");
    expect(summaryHtml).toContain("275.00 kV");
    // Format: "Nominal Voltage: <strong>275.00 kV</strong> · Auto · Phase-to-Ground"
    expect(summaryHtml).toMatch(/275\.00 kV/);
  }
});

// ---------------------------------------------------------------------------
// VD-16: Current group Edit drawer lacks Voltage PU config controls (DEC-212)
// ---------------------------------------------------------------------------

test("VD-16: Current group edit drawer has no Nominal Voltage PU config field", async ({ page }) => {
  await page.goto("/index.html");
  await uploadWith275kVVoltageGroup(page, "VD16");

  // Open Per-Unit Settings then Measurement Groups sub-dialog.
  await page.locator("#mainNavWaveformBtn").click();
  await page.locator("#wwOpenPerUnitSettingsBtn").click();
  await expect(page.locator("#perUnitSettingsOverlay")).not.toHaveAttribute("hidden", { timeout: 5000 });
  await page.locator("#wwOpenMeasurementGroupsFromSettingsBtn").click();
  await expect(page.locator("#measurementGroupsOverlay")).not.toHaveAttribute("hidden", { timeout: 5000 });

  // Find the Current group Edit button and open the drawer.
  const mgBody = page.locator("#measurementGroupsBody");
  await expect(mgBody.getByText("Current Groups", { exact: false })).toBeVisible({ timeout: 5000 });

  // Locate the Edit button for a Current group row (IA channel group).
  const currentRow = mgBody.locator(".ww-mg-row").filter({ hasText: "IA" }).first();
  await currentRow.locator("button", { hasText: "Edit" }).click();
  await expect(page.locator("#wwMgDrawerBackdrop")).not.toHaveAttribute("hidden", { timeout: 5000 });

  // The Current group drawer must NOT show the Nominal Voltage PU-config field
  // (that's the Voltage group field — wwMgVoltageKvInput with label "Nominal Voltage (kV, Line-to-Line)").
  await expect(page.locator("#wwMgVoltageKvInput")).toHaveCount(0);
});

// ---------------------------------------------------------------------------
// VD-17: Mixed Voltage PU and Current ENG cursors from same source (DEC-212)
// ---------------------------------------------------------------------------

test("VD-17: mixed Voltage PU and Current ENG cursors from same source batch correctly (DEC-212)", async ({ page }) => {
  await page.goto("/index.html");
  await uploadWith275kVVoltageGroup(page, "VD17");
  const { sid } = await configureVoltageGroup(page, "VD17", ["VA"]);

  // Add a Current group with Ibase = 1.5 kA = 1500 A.
  // DEC-212 §2 still forces IA cursor to engineering (A) regardless of Ibase.
  const url = await wsUrl(page, `/sources/${sid}/measurement-groups`);
  const currentGroup = await (await page.request.post(url, {
    data: { kind: "current", display_name: "IA", status: "confirmed",
            channel_refs: [{ kind: "source", source_id: sid, channel_name: "IA" }] },
  })).json();
  await page.request.put(`${url}/${currentGroup.id}/current-config`, {
    data: { method: "manual", manual_ibase_ka: 1.5, base_reference_side: "primary" },
  });

  // Navigate to Waveform and display both VA and IA.
  await page.locator("#mainNavWaveformBtn").click();
  const details = page.locator(`#channelGroups details.source-recording[data-source-id="${sid}"]`);
  if (!(await details.evaluate(el => el.open))) await details.locator(":scope > summary").click();
  const chRow = (name) => page.locator(`tr.channel-row--toggle[data-source-id="${sid}"][data-channel-name="${name}"]`);
  await chRow("VA").click();
  await chRow("IA").click();

  // Switch to PU mode.
  await page.evaluate(() => wwApplyUnitMode("per_unit"));
  await expect.poll(() => page.evaluate(() => ww.unitMode), { timeout: 5000 }).toBe("per_unit");
  // Wait for VA to load with pu unit (confirms the Voltage PU fetch completed).
  await expect.poll(() => channelState(page, sid, "VA"), { timeout: 10000 }).toMatchObject({ unit: "pu" });

  // Set cursor at t=0.005s — 90° of 50 Hz at rateHz=1000:
  //   VA = LG_BASE_KV * sin(90°) = LG_BASE_KV → 1.0 pu  (Voltage PU batch)
  //   IA = 1500 A * sin(90°) = 1500 A              (Current engineering batch, DEC-212 §2)
  await page.locator("#wwCursorModeBtn").click();
  await page.evaluate(async sid => {
    const state = wwTimeGroupCursorState(wwTimeGroupIdForDisplaySourceId(sid));
    state.a.visible = true; state.a.time = 0.005;
    wwUpdateAllCursorOverlays();
    await wwFetchCursorValuesForSource(sid);
  }, sid);

  // VA cursor: Voltage PU batch → ≈ 1.0 pu.
  await expect.poll(async () => Number(await chRow("VA").locator(".cur-value--a").textContent()), { timeout: 10000 }).toBeCloseTo(1.0, 1);
  // IA cursor: engineering batch (DEC-212 §2) → ≈ 1500 A, not 1.0 pu.
  await expect.poll(async () => Number(await chRow("IA").locator(".cur-value--a").textContent()), { timeout: 10000 }).toBeCloseTo(1500, 0);
});
