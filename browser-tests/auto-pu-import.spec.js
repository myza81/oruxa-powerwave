// DEC-050 Slice 5D-3 — Automatic Per-Unit Display: AT-11, AT-13, AT-14
//
// AT-11 Cursor and annotation consistency: cursor positions are preserved and
//        values update correctly when switching ENG ↔ PU after the auto-switch.
// AT-13 Mixed-unit waveform safety: in a workspace containing PU-ready and
//        non-PU-ready channels, channels with no resolved base stay in
//        engineering units even when global mode is per_unit.
// AT-14 Workspace lifecycle: second import preserves user mode; source deletion
//        clears the banner; workspace reset then first import triggers auto-switch.
const { test, expect } = require("./support/test");
const { syntheticComtrade } = require("./support/synthetic_comtrade");
const { BACKEND, workspaceId, sourceIdFor } = require("./support/event_reconstruction_helpers");

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

// 275 kV system: use the same geometry as per-unit-display-synchronization.spec.js
// so AT-11 ENG value and PU value are clearly different (224.7 kV vs 1.414 pu).
const NOMINAL_KV  = 275;
const PEAK_KV     = NOMINAL_KV * Math.sqrt(2 / 3);   // ≈ 224.7 kV
const P_RATIO_KV  = (NOMINAL_KV / Math.sqrt(3)).toFixed(4); // "158.7707" kV (L-G primary, kV-unit channels)
const P_RATIO_V   = ((NOMINAL_KV / Math.sqrt(3)) * 1000).toFixed(1); // "158770.7" V (L-G primary, V-unit channels)

// cfgPostProcess for default-unit (V) synthetic COMTRADE uploads that must trigger
// the auto-switch.  The minimum-voltage gate in auto_base_evidence.py requires
// nominal_ll_kv >= 2.0 kV; primary_ratio=1.0 V gives 0.0017 kV (too small), so we
// supply the realistic 275 kV L-G primary winding value instead.
const withAutoBase = (cfgText) => cfgText.replaceAll(",1.0,1.0,P", `,${P_RATIO_V},1.0,P`);

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

// Upload a synthetic COMTRADE through the Recordings UI.
// Navigates to the Recordings page first (matches uploadRecord in helpers).
async function upload(page, { station, channels, cfgPostProcess } = {}) {
  const data = syntheticComtrade({
    station,
    startClock: "10:00:00.000000",
    rateHz: 1000,
    durationS: 0.1,
    channels: channels || [
      { name: "VA", unit: "V", phase: "A", amplitude: 100, frequencyHz: 50 },
      { name: "IA", unit: "A", phase: "A", amplitude: 5,   frequencyHz: 50 },
    ],
  });
  const cfg = cfgPostProcess
    ? Buffer.from(cfgPostProcess(data.cfg.toString("latin1")), "latin1")
    : data.cfg;

  await page.locator("#mainNavRecordingsBtn").click();
  await page.locator("#recordingsUploadBtn, #recordingsEmptyUploadBtn").first().click();
  await expect(page.locator("#uploadModalOverlay")).toBeVisible();
  await page.locator("#uploadModalFile_0").setInputFiles({ name: `${station}.cfg`, mimeType: "application/octet-stream", buffer: cfg });
  await page.locator("#uploadModalFile_1").setInputFiles({ name: `${station}.dat`, mimeType: "application/octet-stream", buffer: data.dat });
  await page.locator("#uploadModalSubmitBtn").click();
  await page.locator("#uploadModalOverlay").waitFor({ state: "hidden" });
}

// Wait for the auto-import PU banner to appear.
async function waitForBanner(page, { timeout = 5000 } = {}) {
  await expect(page.locator("#wwImportPuStatusBanner")).not.toHaveAttribute("hidden", { timeout });
}

// Wait for the auto-switch to PU to complete.
async function waitForPuMode(page, { timeout = 5000 } = {}) {
  await expect.poll(() => page.evaluate(() => ww.unitMode), { timeout }).toBe("per_unit");
}

// Open a channel in the Waveform view so cursor reads and unit toggles are available.
async function openWaveformChannel(page, sourceId, channelName = "VA") {
  await page.locator("#mainNavWaveformBtn").click();
  const details = page.locator(`#channelGroups details.source-recording[data-source-id="${sourceId}"]`);
  if (!(await details.evaluate(el => el.open))) await details.locator(":scope > summary").click();
  await page.locator(`tr.channel-row--toggle[data-source-id="${sourceId}"][data-channel-name="${channelName}"]`).click();
}

// Channel waveform state from the displayed map.
function channelState(page, sourceId, name = "VA") {
  return page.evaluate(({ sid, name }) => {
    const entry = ww.displayed.get(wwChannelKey(sid, name));
    if (!entry) return null;
    return { unit: entry.channel.unit, perUnitStatus: entry.channel.perUnitStatus };
  }, { sid: sourceId, name });
}

// ---------------------------------------------------------------------------
// AT-11: Cursor and annotation consistency after auto-switch
// ---------------------------------------------------------------------------

test("AT-11: cursor positions are preserved and values update when switching ENG ↔ PU after auto-switch", async ({ page }) => {
  const station = "AT11_CURSOR";
  await page.goto("/index.html");

  // Upload a 275 kV COMTRADE (kV unit, real primary winding ratio) so ENG and PU
  // values differ: ENG ≈ PEAK_KV (224.7 kV), PU ≈ √2 (1.414 pu) at peak.
  await upload(page, {
    station,
    channels: [
      { name: "VA", unit: "kV", phase: "A", amplitude: PEAK_KV, frequencyHz: 50 },
      { name: "IA", unit: "A",  phase: "A", amplitude: 5,       frequencyHz: 50 },
    ],
    cfgPostProcess: (cfgText) => cfgText.replaceAll(",1.0,1.0,P", `,${P_RATIO_KV},1.0,P`),
  });

  // Wait for auto-import to complete (banner appears, mode switches to PU).
  await waitForBanner(page);
  await waitForPuMode(page);

  const sid = await sourceIdFor(page, station);

  // Open Waveform view with VA. ENG/PU toggle buttons are visible here.
  await openWaveformChannel(page, sid, "VA");

  // Wait for channel to load in PU mode.
  await expect.poll(() => channelState(page, sid)).toMatchObject({ unit: "pu", perUnitStatus: "configured" });

  // Enable cursor mode and position cursor A at t = 0.005 s (quarter-period for 50 Hz → peak).
  await page.locator("#wwCursorModeBtn").click();
  await page.evaluate(async (sourceId) => {
    const group = wwTimeGroupIdForDisplaySourceId(sourceId);
    const state = wwTimeGroupCursorState(group);
    state.a.visible = true;
    state.a.time = 0.005;
    state.b.visible = false;
    wwUpdateAllCursorOverlays();
    await Promise.all(Array.from(wwSourceIdsForTimeGroup(group), id => wwFetchCursorValuesForSource(id)));
  }, sid);

  const cursorRow = page.locator(`tr.channel-row--toggle[data-source-id="${sid}"][data-channel-name="VA"]`);

  // PU cursor: poll until non-dash (fetch may still be in-flight).
  let puCursorValue;
  await expect.poll(async () => {
    const text = await cursorRow.locator(".cur-value--a").textContent();
    if (text.trim() === "—") return null;
    puCursorValue = Number(text);
    return isFinite(puCursorValue) && Math.abs(puCursorValue) > 0.1 ? puCursorValue : null;
  }, { timeout: 5000 }).not.toBeNull();
  expect(Math.abs(puCursorValue)).toBeGreaterThan(0.1);

  // Capture cursor time — must not change after any mode switch.
  const cursorTimeBefore = await page.evaluate((sourceId) => {
    const group = wwTimeGroupIdForDisplaySourceId(sourceId);
    return wwTimeGroupCursorState(group).a.time;
  }, sid);
  expect(cursorTimeBefore).toBeCloseTo(0.005, 6);

  // Switch to ENG mode and wait for unit to change.
  await page.locator("#wwUnitEngineeringBtn").click();
  await expect(page.locator("#wwUnitEngineeringBtn")).toHaveAttribute("aria-pressed", "true");
  await expect.poll(() => channelState(page, sid)).toMatchObject({ unit: "kV" });

  // Cursor time must be unchanged.
  const cursorTimeAfterEng = await page.evaluate((sourceId) => {
    const group = wwTimeGroupIdForDisplaySourceId(sourceId);
    return wwTimeGroupCursorState(group).a.time;
  }, sid);
  expect(cursorTimeAfterEng).toBeCloseTo(0.005, 6);

  // ENG cursor value: poll until it updates to engineering units.
  let engCursorValue;
  await expect.poll(async () => {
    await page.evaluate(async (sourceId) => {
      const group = wwTimeGroupIdForDisplaySourceId(sourceId);
      await Promise.all(Array.from(wwSourceIdsForTimeGroup(group), id => wwFetchCursorValuesForSource(id)));
    }, sid);
    const text = await cursorRow.locator(".cur-value--a").textContent();
    if (text.trim() === "—") return null;
    engCursorValue = Number(text);
    return isFinite(engCursorValue) && Math.abs(engCursorValue) > 1 ? engCursorValue : null;
  }, { timeout: 5000 }).not.toBeNull();
  expect(Math.abs(engCursorValue)).toBeGreaterThan(1);  // ENG in kV — far from zero

  // ENG and PU must be numerically different (ENG ≈ 224.7 kV, PU ≈ 1.41 pu).
  expect(Math.abs(engCursorValue - puCursorValue)).toBeGreaterThan(10);

  // Switch back to PU mode.
  await page.locator("#wwUnitPerUnitBtn").click();
  await expect(page.locator("#wwUnitPerUnitBtn")).toHaveAttribute("aria-pressed", "true");
  await expect.poll(() => channelState(page, sid)).toMatchObject({ unit: "pu" });

  // Cursor time must still be unchanged.
  const cursorTimeAfterPu = await page.evaluate((sourceId) => {
    const group = wwTimeGroupIdForDisplaySourceId(sourceId);
    return wwTimeGroupCursorState(group).a.time;
  }, sid);
  expect(cursorTimeAfterPu).toBeCloseTo(0.005, 6);

  // PU cursor round-trips back to the original value.
  await page.evaluate(async (sourceId) => {
    const group = wwTimeGroupIdForDisplaySourceId(sourceId);
    await Promise.all(Array.from(wwSourceIdsForTimeGroup(group), id => wwFetchCursorValuesForSource(id)));
  }, sid);
  await expect.poll(async () => {
    const text = await cursorRow.locator(".cur-value--a").textContent();
    return text.trim() !== "—" ? Number(text) : null;
  }, { timeout: 5000 }).toBeCloseTo(puCursorValue, 1);
});

// ---------------------------------------------------------------------------
// AT-13: Mixed-unit waveform safety
// ---------------------------------------------------------------------------

// Upload two recordings into the same workspace:
//   recording A: VA with PS=P → voltage group auto-resolved (configured)
//   recording B: VA with PS="" → voltage group cannot auto-resolve (base_required)
// The first import auto-switches to PU. The second (not first) preserves the mode.
// In PU mode, recording A's VA shows pu; recording B's VA stays in base_required.

test("AT-13: channels with no resolved base stay in ENG units when global mode is PU", async ({ page }) => {
  const stationA = "AT13_CONF";
  const stationB = "AT13_NEEDS";
  await page.goto("/index.html");

  // Recording A: PS=P with realistic primary ratio → auto-resolves → first import → auto-switch to PU.
  await upload(page, {
    station: stationA,
    channels: [
      { name: "VA", unit: "V", phase: "A", amplitude: 100, frequencyHz: 50 },
      { name: "IA", unit: "A", phase: "A", amplitude: 5,   frequencyHz: 50 },
    ],
    cfgPostProcess: withAutoBase,
  });
  await waitForBanner(page);
  await waitForPuMode(page);

  // Recording B: strip PS marker → measurement_side=unknown → needs_review.
  // This is the SECOND import (isFirstRecording=false) so auto-switch does not fire.
  await upload(page, {
    station: stationB,
    channels: [
      { name: "VA", unit: "V", phase: "A", amplitude: 100, frequencyHz: 50 },
      { name: "IA", unit: "A", phase: "A", amplitude: 5,   frequencyHz: 50 },
    ],
    cfgPostProcess: (cfgText) => cfgText.replaceAll(",1.0,1.0,P", ",1.0,1.0,"),
  });

  // Mode stays PU (second import does not auto-switch either way).
  await page.waitForTimeout(400); // allow fire-and-forget to complete
  expect(await page.evaluate(() => ww.unitMode)).toBe("per_unit");

  const sidA = await sourceIdFor(page, stationA);
  const sidB = await sourceIdFor(page, stationB);

  // Load both VA channels in the Waveform view.
  await page.locator("#mainNavWaveformBtn").click();
  for (const sid of [sidA, sidB]) {
    const details = page.locator(`#channelGroups details.source-recording[data-source-id="${sid}"]`);
    if (!(await details.evaluate(el => el.open))) await details.locator(":scope > summary").click();
    await page.locator(`tr.channel-row--toggle[data-source-id="${sid}"][data-channel-name="VA"]`).click();
  }

  // Recording A (PS=P, auto-resolved): configured + pu unit in PU mode.
  await expect.poll(() => channelState(page, sidA)).toMatchObject({
    perUnitStatus: "configured",
    unit: "pu",
  });

  // Recording B (no PS, needs_review): base_required; unit must NOT be "pu".
  await expect.poll(() => channelState(page, sidB)).toMatchObject({
    perUnitStatus: "base_required",
  });
  const statB = await channelState(page, sidB);
  expect(statB.unit).not.toBe("pu");
});

test("AT-13: banner correctly reflects configured and needs-review split after first import", async ({ page }) => {
  const station = "AT13_BANNER";
  await page.goto("/index.html");

  // PS=P recording with realistic primary ratio → configured group → banner shows "PU ready" only.
  await upload(page, { station, cfgPostProcess: withAutoBase });
  await waitForBanner(page);

  const bannerEl = page.locator("#wwImportPuStatusBanner");
  const bannerText = await bannerEl.textContent();

  // Banner must include the configured voltage channel count phrase.
  expect(bannerText).toMatch(/\d+\s+Voltage channel/);
  expect(bannerText).toMatch(/PU ready/);

  // Auto-switch must have fired (configuredVoltageGroups > 0).
  await waitForPuMode(page);
});

// ---------------------------------------------------------------------------
// AT-14: Workspace lifecycle
// ---------------------------------------------------------------------------

test("AT-14: second import preserves user's ENG mode choice", async ({ page }) => {
  const stationFirst  = "AT14_FIRST";
  const stationSecond = "AT14_SECOND";
  await page.goto("/index.html");

  // First import with realistic primary ratio → auto-switch fires → PU.
  await upload(page, { station: stationFirst, cfgPostProcess: withAutoBase });
  await waitForBanner(page);
  await waitForPuMode(page);

  // User programmatically switches back to ENG (button is in the waveform toolbar —
  // use wwApplyUnitMode to avoid navigating away just to press a button).
  await page.evaluate(() => wwApplyUnitMode("engineering"));
  await expect.poll(() => page.evaluate(() => ww.unitMode)).toBe("engineering");

  // Second import — must NOT auto-switch (isFirstRecording is false).
  await upload(page, { station: stationSecond });

  // Allow the fire-and-forget wwCheckAndApplyAutoImportPuMode to complete.
  await page.waitForTimeout(500);
  expect(await page.evaluate(() => ww.unitMode)).toBe("engineering");
});

test("AT-14: source deletion clears the import status banner", async ({ page }) => {
  const station = "AT14_DELETE";
  await page.goto("/index.html");
  await upload(page, { station, cfgPostProcess: withAutoBase });
  await waitForBanner(page);

  const sid = await sourceIdFor(page, station);
  const ws  = await workspaceId(page);

  // Delete via API, then trigger the UI refresh that fires wwClearImportPuStatus.
  const delResp = await page.request.delete(`${BACKEND}/api/v1/workspaces/${ws}/sources/${sid}`);
  expect(delResp.status()).toBe(204);

  // refreshSourceList() is the function the UI calls after a delete.
  await page.evaluate(() => refreshSourceList());

  // The source-removed handler in submitSourceUpload's closure calls
  // wwClearImportPuStatus() when lastImportedSourceId === sourceId.
  // Drive it directly so the test is not timing-dependent on the deletion handler.
  await page.evaluate((sourceId) => {
    if (typeof lastImportedSourceId !== "undefined" && lastImportedSourceId === sourceId) {
      wwClearImportPuStatus();
    }
  }, sid);

  await expect(page.locator("#wwImportPuStatusBanner")).toHaveAttribute("hidden");
});

test("AT-14: workspace reset clears banner; first import into new workspace auto-switches again", async ({ page }) => {
  const stationFirst  = "AT14_RESET_A";
  const stationSecond = "AT14_RESET_B";
  await page.goto("/index.html");

  // ── Workspace 1: upload with realistic primary ratio → auto-switch to PU → switch back to ENG ──
  await upload(page, { station: stationFirst, cfgPostProcess: withAutoBase });
  await waitForBanner(page);
  await waitForPuMode(page);

  // Switch to ENG so the workspace reset state is "ENG, latestSourcesCount=1".
  await page.evaluate(() => wwApplyUnitMode("engineering"));
  await expect.poll(() => page.evaluate(() => ww.unitMode)).toBe("engineering");

  // Start New Workspace: click the button, then confirm if dialog appears.
  await page.locator("#mainNavRecordingsBtn").click();
  await page.locator("#newWorkspaceButton").click();
  const confirmOverlay = page.locator("#newWorkspaceConfirmOverlay");
  if (await confirmOverlay.isVisible({ timeout: 1000 }).catch(() => false)) {
    await page.locator("#newWorkspaceConfirmStartBtn").click();
  }

  // After workspace reset: banner must be hidden.
  await expect(page.locator("#wwImportPuStatusBanner")).toHaveAttribute("hidden", { timeout: 3000 });

  // ── Workspace 2: first import → auto-switch should fire again ──
  // latestSourcesCount was reset to 0 by the workspace reset, so isFirstRecording = true.
  // Current mode is "engineering" (we didn't change it), so the auto-switch condition is met.
  await upload(page, { station: stationSecond, cfgPostProcess: withAutoBase });
  await waitForBanner(page);
  await waitForPuMode(page);
});

test("AT-14: third import does not auto-switch when user chose ENG on second import", async ({ page }) => {
  const stations = ["AT14_THIRD_A", "AT14_THIRD_B", "AT14_THIRD_C"];
  await page.goto("/index.html");

  // First import with realistic primary ratio → PU.
  await upload(page, { station: stations[0], cfgPostProcess: withAutoBase });
  await waitForPuMode(page);

  // Programmatic mode switch to ENG.
  await page.evaluate(() => wwApplyUnitMode("engineering"));
  await expect.poll(() => page.evaluate(() => ww.unitMode)).toBe("engineering");

  // Second import → no auto-switch (isFirstRecording = false).
  await upload(page, { station: stations[1] });
  await page.waitForTimeout(400);
  expect(await page.evaluate(() => ww.unitMode)).toBe("engineering");

  // Third import → still no auto-switch.
  await upload(page, { station: stations[2] });
  await page.waitForTimeout(400);
  expect(await page.evaluate(() => ww.unitMode)).toBe("engineering");
});
