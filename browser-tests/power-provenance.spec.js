// Stage 3B-2C-3 browser tests: calculated POWER physical calibration provenance
// (DEC-213, OD-12).
//
// Verifies via backend API and UI assertions that:
//   A  BEN5K Unverified Va+Ia → active_power → "exploratory_unverified" in API
//      and "⚠ exploratory" badge visible in channel-manager list (UI)
//   B  Nested calc: BEN5K Unverified Va → reverse_polarity → active_power with
//      original Ia → "exploratory_unverified" inherited through the chain
//   C  Two POWER channels: BEN5K (exploratory) + COMTRADE (not_assessed) →
//      each shows its own correct status, no cross-contamination
//   D  COMTRADE Not-Assessed Va+Ia → active_power → "not_assessed" (no badge)
//   E  No JS errors, no uncaught exceptions during all scenarios
//
// All mandatory scenarios use committed fixtures:
//   - synthetic_ben5k_phasor.ben  (Va + Ia, both CALIBRATION_UNVERIFIED)
//   - synth_ascii.cfg/.dat        (VA + IA, COMTRADE = not-assessed)
// No env-var gate for mandatory scenarios.

"use strict";

const { test, expect } = require("./support/test");
const path = require("path");

const BEN5K_PHASOR = path.join(
  __dirname, "..", "backend", "tests", "fixtures", "ben", "synthetic_ben5k_phasor.ben"
);
const COMTRADE_CFG = path.join(
  __dirname, "..", "backend", "tests", "fixtures", "comtrade", "synth_ascii.cfg"
);
const COMTRADE_DAT = path.join(
  __dirname, "..", "backend", "tests", "fixtures", "comtrade", "synth_ascii.dat"
);

const PORT = process.env.PW_BACKEND_PORT || "8000";
const BACKEND = `http://127.0.0.1:${PORT}`;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Navigate to recordings page (or stay there if already on index). */
async function ensureRecordingsPage(page) {
  const btn = page.locator("#mainNavRecordingsBtn");
  if (await btn.count() > 0) {
    await btn.click();
  } else {
    await page.goto("/index.html");
  }
}

async function uploadBen5k(page) {
  await ensureRecordingsPage(page);
  await page.locator("#recordingsUploadBtn, #recordingsEmptyUploadBtn").first().click();
  await expect(page.locator("#uploadModalOverlay")).toBeVisible();
  await page.locator("#uploadModalFormatSelect").selectOption("ben");
  await page.locator("#uploadModalFile_0").setInputFiles(BEN5K_PHASOR);
  await page.locator("#uploadModalSubmitBtn").click();
  await page.locator("#uploadModalOverlay").waitFor({ state: "hidden", timeout: 30000 });
  const row = page.locator("#recordingsTableBody tr[data-source-id]").last();
  await expect(row).toBeVisible();
  return row.getAttribute("data-source-id");
}

async function uploadComtrade(page) {
  await ensureRecordingsPage(page);
  await page.locator("#recordingsUploadBtn, #recordingsEmptyUploadBtn").first().click();
  await expect(page.locator("#uploadModalOverlay")).toBeVisible();
  await page.locator("#uploadModalFile_0").setInputFiles(COMTRADE_CFG);
  await page.locator("#uploadModalFile_1").setInputFiles(COMTRADE_DAT);
  await page.locator("#uploadModalSubmitBtn").click();
  await page.locator("#uploadModalOverlay").waitFor({ state: "hidden" });
  const row = page.locator("#recordingsTableBody tr[data-source-id]").last();
  await expect(row).toBeVisible();
  return row.getAttribute("data-source-id");
}

async function getWorkspaceId(page) {
  return page.evaluate(() => localStorage.getItem("powerwave.workspaceId"));
}

async function getSourceChannels(page, workspaceId, sourceId) {
  const r = await page.request.get(
    `${BACKEND}/api/v1/workspaces/${encodeURIComponent(workspaceId)}/sources/${encodeURIComponent(sourceId)}/channels`
  );
  if (!r.ok()) return { analog_channels: [] };
  const data = await r.json();
  return data;
}

/** POST a calculated POWER channel via the backend API. */
async function createPowerChannel(page, workspaceId, { name, operation, voltInput, currInput, unit, referenceSourceId }) {
  const r = await page.request.post(
    `${BACKEND}/api/v1/workspaces/${encodeURIComponent(workspaceId)}/calculated-channels`,
    {
      data: {
        name,
        operation,
        inputs: [voltInput, currInput],
        parameters: {},
        unit: unit || "MW",
        engineering_type: "Power",
        null_policy: "propagate_null",
        reference_source_id: referenceSourceId,
      },
    }
  );
  return r;
}

/** Create a reverse-polarity calc channel (Voltage) over a source channel. */
async function createReversePolarity(page, workspaceId, { name, sourceId, channelName, unit, refSourceId }) {
  const r = await page.request.post(
    `${BACKEND}/api/v1/workspaces/${encodeURIComponent(workspaceId)}/calculated-channels`,
    {
      data: {
        name,
        operation: "reverse_polarity",
        inputs: [{ kind: "source", source_id: sourceId, channel_name: channelName }],
        parameters: {},
        unit: unit || "kV",
        engineering_type: "Voltage",
        null_policy: "propagate_null",
        reference_source_id: refSourceId,
      },
    }
  );
  return r;
}

/** Navigate to the calculated-channels page and return the channel list as parsed JSON. */
async function getCalcChannelList(page, workspaceId) {
  const r = await page.request.get(
    `${BACKEND}/api/v1/workspaces/${encodeURIComponent(workspaceId)}/calculated-channels`
  );
  expect(r.ok()).toBe(true);
  return r.json();
}

/** Navigate to the calculated-channels manager page (triggers UI render). */
async function navigateToCalcPage(page) {
  await page.locator("#mainNavCalculatedChannelsBtn").click();
  await expect(page.locator("#pageCalculatedChannels")).toBeVisible();
}

// ---------------------------------------------------------------------------
// Scenario A: BEN5K Unverified Va → reverse_polarity → exploratory_unverified
// (active_power requires ≥1 cycle; fixtures are 10 ms — provenance is operation-agnostic)
// ---------------------------------------------------------------------------

test.describe("Scenario A — BEN5K Unverified source → exploratory_unverified + badge", () => {
  test("API provenance is exploratory_unverified and badge appears in channel list", async ({ page }) => {
    await page.goto("/index.html");

    // Track JS errors.
    const jsErrors = [];
    page.on("pageerror", (err) => jsErrors.push(err.message));

    const benSourceId = await uploadBen5k(page);
    const workspaceId = await getWorkspaceId(page);
    expect(workspaceId, "workspace ID must exist after upload").toBeTruthy();

    // Discover Va channel (reverse_polarity only needs voltage; operation-agnostic provenance).
    const meta = await getSourceChannels(page, workspaceId, benSourceId);
    const voltCh = (meta.analog_channels || []).find(c => c.engineering_type === "Voltage");
    expect(voltCh, "BEN5K phasor fixture must expose a Voltage channel — check synthetic_ben5k_phasor.ben").toBeTruthy();

    // Create reverse_polarity channel — provenance comes from leaf source authorities, not operation.
    const createResp = await createReversePolarity(page, workspaceId, {
      name: "Va_rev_exploratory",
      sourceId: benSourceId,
      channelName: voltCh.name,
      unit: voltCh.unit || "kV",
      refSourceId: benSourceId,
    });

    // Creation with Unverified inputs must succeed (Unverified is allowed by Stage 3B-2B-2).
    expect(
      createResp.ok(),
      `reverse_polarity creation from BEN5K Unverified must not be blocked: ${createResp.status()}`
    ).toBe(true);

    const created = await createResp.json();

    // --- API assertion: provenance fields present on the POST response ---
    expect(
      created.calibration_provenance_status,
      "POST response must include calibration_provenance_status"
    ).toBe("exploratory_unverified");
    expect(
      created.calibration_provenance_reason,
      "POST response must include calibration_provenance_reason"
    ).toBe("physical_calibration_unverified");

    // --- API assertion: GET list includes provenance fields ---
    const list = await getCalcChannelList(page, workspaceId);
    const inList = list.find(c => c.id === created.id);
    expect(inList, "created channel must appear in GET list").toBeTruthy();
    expect(inList.calibration_provenance_status).toBe("exploratory_unverified");
    expect(inList.calibration_provenance_reason).toBe("physical_calibration_unverified");

    // --- UI assertion: badge visible in channel-manager list ---
    // Reload so the frontend re-fetches ww.calculatedChannels from the backend
    // (channels created via API are not in the in-memory map until the app restarts).
    await page.reload();
    await expect(page.locator("#recordingsTableBody tr[data-source-id]")).toBeVisible({ timeout: 10000 });
    await navigateToCalcPage(page);
    const channelRow = page.locator(`.ww-cc-list-row[data-calculated-channel-id="${created.id}"]`);
    await expect(channelRow).toBeVisible({ timeout: 8000 });
    const badge = channelRow.locator(".ww-calc-provenance-badge--exploratory");
    await expect(badge).toBeVisible();
    await expect(badge).toContainText("exploratory");

    // --- Scenario E: no JS errors ---
    expect(jsErrors, "No JS errors must occur").toHaveLength(0);
  });
});

// ---------------------------------------------------------------------------
// Scenario B: Nested calc — reverse_polarity(reverse_polarity(BEN5K Va)) → exploratory_unverified
// Tests that DFS leaf-authority traversal propagates through two calc hops.
// ---------------------------------------------------------------------------

test.describe("Scenario B — Nested calc chain inherits exploratory_unverified", () => {
  test("reverse_polarity(reverse_polarity(BEN5K Va)) → exploratory_unverified", async ({ page }) => {
    await page.goto("/index.html");

    const benSourceId = await uploadBen5k(page);
    const workspaceId = await getWorkspaceId(page);
    expect(workspaceId).toBeTruthy();

    const meta = await getSourceChannels(page, workspaceId, benSourceId);
    const voltCh = (meta.analog_channels || []).find(c => c.engineering_type === "Voltage");
    expect(voltCh, "BEN5K phasor fixture must expose a Voltage channel — check synthetic_ben5k_phasor.ben").toBeTruthy();

    // Level 1: reverse_polarity of BEN5K Va (Unverified leaf).
    const rpResp = await createReversePolarity(page, workspaceId, {
      name: "Va_reversed_L1",
      sourceId: benSourceId,
      channelName: voltCh.name,
      unit: voltCh.unit || "kV",
      refSourceId: benSourceId,
    });
    expect(rpResp.ok(), `L1 reverse_polarity creation failed: ${rpResp.status()}`).toBe(true);
    const rp = await rpResp.json();

    // Level 2: reverse_polarity of the Level-1 calc — exercises DFS two hops deep.
    const nestedResp = await page.request.post(
      `${BACKEND}/api/v1/workspaces/${encodeURIComponent(workspaceId)}/calculated-channels`,
      {
        data: {
          name: "Va_reversed_L2",
          operation: "reverse_polarity",
          inputs: [{ kind: "calculated", calculated_channel_id: rp.id }],
          parameters: {},
          unit: voltCh.unit || "kV",
          engineering_type: "Voltage",
          null_policy: "propagate_null",
          reference_source_id: benSourceId,
        },
      }
    );

    expect(
      nestedResp.ok(),
      `Nested calc creation from Unverified calc must succeed: ${nestedResp.status()}`
    ).toBe(true);

    const nested = await nestedResp.json();
    expect(nested.calibration_provenance_status).toBe("exploratory_unverified");
    expect(nested.calibration_provenance_reason).toBe("physical_calibration_unverified");
  });
});

// ---------------------------------------------------------------------------
// Scenario C: Two calc channels — BEN5K (exploratory) + COMTRADE (not_assessed)
// Tests no cross-contamination between independent sources.
// ---------------------------------------------------------------------------

test.describe("Scenario C — Mixed provenance: no cross-contamination", () => {
  test("BEN5K and COMTRADE calc channels each carry their own status", async ({ page }) => {
    await page.goto("/index.html");

    const benSourceId = await uploadBen5k(page);
    const workspaceId = await getWorkspaceId(page);
    const comSourceId = await uploadComtrade(page);
    expect(workspaceId).toBeTruthy();

    // BEN5K channels.
    const benMeta = await getSourceChannels(page, workspaceId, benSourceId);
    const benVolt = (benMeta.analog_channels || []).find(c => c.engineering_type === "Voltage");
    expect(benVolt, "BEN5K fixture must expose a Voltage channel — check synthetic_ben5k_phasor.ben").toBeTruthy();

    // COMTRADE channels.
    const comMeta = await getSourceChannels(page, workspaceId, comSourceId);
    const comVolt = (comMeta.analog_channels || []).find(c => c.engineering_type === "Voltage");
    expect(comVolt, "COMTRADE fixture must expose a Voltage channel — check synth_ascii.cfg").toBeTruthy();

    // Create BEN5K calc channel (reverse_polarity — provenance comes from source, not operation).
    const benPowerResp = await createReversePolarity(page, workspaceId, {
      name: "Va_ben5k_exploratory",
      sourceId: benSourceId,
      channelName: benVolt.name,
      unit: benVolt.unit || "kV",
      refSourceId: benSourceId,
    });
    expect(benPowerResp.ok()).toBe(true);
    const benPower = await benPowerResp.json();

    // Create COMTRADE calc channel.
    const comPowerResp = await createReversePolarity(page, workspaceId, {
      name: "VA_comtrade_not_assessed",
      sourceId: comSourceId,
      channelName: comVolt.name,
      unit: comVolt.unit || "kV",
      refSourceId: comSourceId,
    });
    expect(comPowerResp.ok()).toBe(true);
    const comPower = await comPowerResp.json();

    // BEN5K Power: exploratory_unverified.
    expect(benPower.calibration_provenance_status).toBe("exploratory_unverified");

    // COMTRADE Power: not_assessed (backward compat — not exploratory, no badge).
    expect(comPower.calibration_provenance_status).toBe("not_assessed");
    expect(comPower.calibration_provenance_reason).toBeNull();

    // Verify via GET list that statuses are independent.
    const list = await getCalcChannelList(page, workspaceId);
    const benInList = list.find(c => c.id === benPower.id);
    const comInList = list.find(c => c.id === comPower.id);
    expect(benInList).toBeTruthy();
    expect(comInList).toBeTruthy();
    expect(benInList.calibration_provenance_status).toBe("exploratory_unverified");
    expect(comInList.calibration_provenance_status).toBe("not_assessed");

    // --- UI: BEN5K channel shows badge; COMTRADE channel does NOT ---
    // Reload so the frontend re-fetches ww.calculatedChannels from the backend.
    await page.reload();
    await expect(page.locator("#recordingsTableBody tr[data-source-id]").first()).toBeVisible({ timeout: 10000 });
    await navigateToCalcPage(page);
    const benRow = page.locator(`.ww-cc-list-row[data-calculated-channel-id="${benPower.id}"]`);
    const comRow = page.locator(`.ww-cc-list-row[data-calculated-channel-id="${comPower.id}"]`);
    await expect(benRow).toBeVisible({ timeout: 8000 });
    await expect(comRow).toBeVisible({ timeout: 8000 });

    // BEN5K row must have the exploratory badge.
    await expect(benRow.locator(".ww-calc-provenance-badge--exploratory")).toBeVisible();

    // COMTRADE row must NOT have an exploratory badge.
    await expect(comRow.locator(".ww-calc-provenance-badge--exploratory")).toHaveCount(0);
  });
});

// ---------------------------------------------------------------------------
// Scenario D: COMTRADE Not-Assessed → not_assessed → no badge (backward compat)
// ---------------------------------------------------------------------------

test.describe("Scenario D — COMTRADE Not-Assessed → not_assessed, no badge", () => {
  test("COMTRADE-only calc channel has not_assessed status and no exploratory badge", async ({ page }) => {
    await page.goto("/index.html");

    const comSourceId = await uploadComtrade(page);
    const workspaceId = await getWorkspaceId(page);
    expect(workspaceId).toBeTruthy();

    const meta = await getSourceChannels(page, workspaceId, comSourceId);
    const voltCh = (meta.analog_channels || []).find(c => c.engineering_type === "Voltage");
    expect(voltCh, "COMTRADE fixture must expose a Voltage channel — check synth_ascii.cfg").toBeTruthy();

    const r = await createReversePolarity(page, workspaceId, {
      name: "VA_comtrade_backward_compat",
      sourceId: comSourceId,
      channelName: voltCh.name,
      unit: voltCh.unit || "kV",
      refSourceId: comSourceId,
    });
    expect(r.ok()).toBe(true);
    const created = await r.json();

    // Not_assessed — existing sources without calibration authority.
    expect(created.calibration_provenance_status).toBe("not_assessed");
    expect(created.calibration_provenance_reason).toBeNull();

    // Must NOT claim all_verified or exploratory_unverified.
    expect(created.calibration_provenance_status).not.toBe("all_verified");
    expect(created.calibration_provenance_status).not.toBe("exploratory_unverified");

    // --- UI: no badge for not_assessed ---
    // Reload so the frontend re-fetches ww.calculatedChannels from the backend.
    await page.reload();
    await expect(page.locator("#recordingsTableBody tr[data-source-id]")).toBeVisible({ timeout: 10000 });
    await navigateToCalcPage(page);
    const channelRow = page.locator(`.ww-cc-list-row[data-calculated-channel-id="${created.id}"]`);
    await expect(channelRow).toBeVisible({ timeout: 8000 });
    await expect(channelRow.locator(".ww-calc-provenance-badge--exploratory")).toHaveCount(0);
  });
});

// ---------------------------------------------------------------------------
// Scenario E: Waveform sidebar — exploratory badge in trace list + cursor row
// ---------------------------------------------------------------------------

test.describe("Scenario E — Waveform sidebar: exploratory badge in trace list", () => {
  test("BEN5K calc shows ⚠ exploratory badge in waveform sidebar; COMTRADE calc does not", async ({ page }) => {
    const jsErrors = [];
    page.on("pageerror", (err) => jsErrors.push(err.message));
    await page.goto("/index.html");

    const benSourceId = await uploadBen5k(page);
    const workspaceId = await getWorkspaceId(page);
    const comSourceId = await uploadComtrade(page);
    expect(workspaceId).toBeTruthy();

    const benMeta = await getSourceChannels(page, workspaceId, benSourceId);
    const benVolt = (benMeta.analog_channels || []).find(c => c.engineering_type === "Voltage");
    expect(benVolt, "BEN5K fixture must expose a Voltage channel — check synthetic_ben5k_phasor.ben").toBeTruthy();

    const comMeta = await getSourceChannels(page, workspaceId, comSourceId);
    const comVolt = (comMeta.analog_channels || []).find(c => c.engineering_type === "Voltage");
    expect(comVolt, "COMTRADE fixture must expose a Voltage channel — check synth_ascii.cfg").toBeTruthy();

    const benResp = await createReversePolarity(page, workspaceId, {
      name: "Va_ben5k_wf_e",
      sourceId: benSourceId,
      channelName: benVolt.name,
      unit: benVolt.unit || "kV",
      refSourceId: benSourceId,
    });
    expect(benResp.ok()).toBe(true);
    const benCalc = await benResp.json();

    const comResp = await createReversePolarity(page, workspaceId, {
      name: "VA_comtrade_wf_e",
      sourceId: comSourceId,
      channelName: comVolt.name,
      unit: comVolt.unit || "kV",
      refSourceId: comSourceId,
    });
    expect(comResp.ok()).toBe(true);
    const comCalc = await comResp.json();

    // Reload so ww.calculatedChannels is re-fetched from the backend.
    await page.reload();
    await expect(page.locator("#recordingsTableBody tr[data-source-id]").first()).toBeVisible({ timeout: 10000 });

    // Navigate to waveform — sidebar renders all calc channels.
    await page.locator("#mainNavWaveformBtn").click();

    // BEN5K row: must have exploratory badge (also in cursor-value table row).
    const benRow = page.locator(`#calculatedChannelsSidebarBody tr[data-calculated-channel-id="${benCalc.id}"]`);
    await expect(benRow).toBeAttached({ timeout: 10000 });
    await expect(benRow.locator(".ww-calc-provenance-badge--exploratory")).toBeVisible();

    // COMTRADE row: no exploratory badge.
    const comRow = page.locator(`#calculatedChannelsSidebarBody tr[data-calculated-channel-id="${comCalc.id}"]`);
    await expect(comRow).toBeAttached({ timeout: 10000 });
    await expect(comRow.locator(".ww-calc-provenance-badge--exploratory")).toHaveCount(0);

    expect(jsErrors, "No JS errors").toHaveLength(0);
  });
});

// ---------------------------------------------------------------------------
// Scenario F: Peak annotation — wwPeakValueLineText appends ⚠ for exploratory
// ---------------------------------------------------------------------------

test.describe("Scenario F — Peak annotation: exploratory channels append ⚠ glyph", () => {
  test("wwPeakValueLineText appends ⚠ for exploratory_unverified; omits it for not_assessed", async ({ page }) => {
    const jsErrors = [];
    page.on("pageerror", (err) => jsErrors.push(err.message));
    await page.goto("/index.html");

    const benSourceId = await uploadBen5k(page);
    const workspaceId = await getWorkspaceId(page);
    const comSourceId = await uploadComtrade(page);
    expect(workspaceId).toBeTruthy();

    const benMeta = await getSourceChannels(page, workspaceId, benSourceId);
    const benVolt = (benMeta.analog_channels || []).find(c => c.engineering_type === "Voltage");
    expect(benVolt, "BEN5K fixture must expose a Voltage channel — check synthetic_ben5k_phasor.ben").toBeTruthy();

    const comMeta = await getSourceChannels(page, workspaceId, comSourceId);
    const comVolt = (comMeta.analog_channels || []).find(c => c.engineering_type === "Voltage");
    expect(comVolt, "COMTRADE fixture must expose a Voltage channel — check synth_ascii.cfg").toBeTruthy();

    const benResp = await createReversePolarity(page, workspaceId, {
      name: "Va_ben5k_peak_f",
      sourceId: benSourceId,
      channelName: benVolt.name,
      unit: benVolt.unit || "kV",
      refSourceId: benSourceId,
    });
    expect(benResp.ok()).toBe(true);
    const benCalc = await benResp.json();

    const comResp = await createReversePolarity(page, workspaceId, {
      name: "VA_comtrade_peak_f",
      sourceId: comSourceId,
      channelName: comVolt.name,
      unit: comVolt.unit || "kV",
      refSourceId: comSourceId,
    });
    expect(comResp.ok()).toBe(true);
    const comCalc = await comResp.json();

    // Reload so ww.calculatedChannels is populated.
    await page.reload();
    await expect(page.locator("#recordingsTableBody tr[data-source-id]").first()).toBeVisible({ timeout: 10000 });

    // Navigate to waveform (wwPeakValueLineText reads ww.calculatedChannels).
    await page.locator("#mainNavWaveformBtn").click();

    // Wait for sidebar rows — confirms ww.calculatedChannels is populated.
    const benSidebarRow = page.locator(`#calculatedChannelsSidebarBody tr[data-calculated-channel-id="${benCalc.id}"]`);
    await expect(benSidebarRow).toBeAttached({ timeout: 10000 });
    const comSidebarRow = page.locator(`#calculatedChannelsSidebarBody tr[data-calculated-channel-id="${comCalc.id}"]`);
    await expect(comSidebarRow).toBeAttached({ timeout: 10000 });

    // BEN5K channel (exploratory_unverified) → peak text must include ⚠.
    const benPeakText = await page.evaluate((channelId) => {
      return window.wwPeakValueLineText({
        type: "peak_max",
        data: {
          available: true,
          peakValue: 1.234,
          unit: "kV",
          sourceId: channelId,
          perUnitStatus: null,
          perUnitReferenceCompatibility: null,
        },
      });
    }, benCalc.id);

    expect(benPeakText, "BEN5K exploratory peak text must contain ⚠").toContain("⚠");
    expect(benPeakText, "BEN5K exploratory peak text must have Maximum prefix").toContain("Maximum");

    // COMTRADE channel (not_assessed) → peak text must NOT include ⚠.
    const comPeakText = await page.evaluate((channelId) => {
      return window.wwPeakValueLineText({
        type: "peak_max",
        data: {
          available: true,
          peakValue: 2.345,
          unit: "kV",
          sourceId: channelId,
          perUnitStatus: null,
          perUnitReferenceCompatibility: null,
        },
      });
    }, comCalc.id);

    expect(comPeakText, "COMTRADE not_assessed peak text must NOT contain ⚠").not.toContain("⚠");

    expect(jsErrors, "No JS errors").toHaveLength(0);
  });
});

// ---------------------------------------------------------------------------
// Scenario G: ENG → PU → ENG transition — no stale labels or JS errors
// ---------------------------------------------------------------------------

test.describe("Scenario G — ENG→PU→ENG: no stale labels or JS errors", () => {
  test("toggling PU mode with an exploratory channel causes no duplicate traces or JS errors", async ({ page }) => {
    const jsErrors = [];
    page.on("pageerror", (err) => jsErrors.push(err.message));
    await page.goto("/index.html");

    const benSourceId = await uploadBen5k(page);
    const workspaceId = await getWorkspaceId(page);
    expect(workspaceId).toBeTruthy();

    const meta = await getSourceChannels(page, workspaceId, benSourceId);
    const voltCh = (meta.analog_channels || []).find(c => c.engineering_type === "Voltage");
    expect(voltCh, "BEN5K fixture must expose a Voltage channel — check synthetic_ben5k_phasor.ben").toBeTruthy();

    const resp = await createReversePolarity(page, workspaceId, {
      name: "Va_ben5k_pu_g",
      sourceId: benSourceId,
      channelName: voltCh.name,
      unit: voltCh.unit || "kV",
      refSourceId: benSourceId,
    });
    expect(resp.ok()).toBe(true);
    const calc = await resp.json();

    await page.reload();
    await expect(page.locator("#recordingsTableBody tr[data-source-id]").first()).toBeVisible({ timeout: 10000 });

    await page.locator("#mainNavWaveformBtn").click();

    // Show the calc channel in the waveform.
    const sidebarRow = page.locator(`#calculatedChannelsSidebarBody tr[data-calculated-channel-id="${calc.id}"]`);
    await expect(sidebarRow).toBeAttached({ timeout: 10000 });
    await sidebarRow.click({ force: true });
    await expect(sidebarRow).toHaveAttribute("aria-pressed", "true");

    // Toggle ENG → PU.
    await page.locator("#wwUnitPerUnitBtn").click();
    await expect(page.locator("#wwUnitPerUnitBtn")).toHaveAttribute("aria-pressed", "true");

    // Toggle PU → ENG.
    await page.locator("#wwUnitEngineeringBtn").click();
    await expect(page.locator("#wwUnitEngineeringBtn")).toHaveAttribute("aria-pressed", "true");

    // Sidebar must have exactly one row for this channel — no duplicate from the PU round trip.
    await expect(
      page.locator(`#calculatedChannelsSidebarBody tr[data-calculated-channel-id="${calc.id}"]`)
    ).toHaveCount(1);

    // Badge still visible — no stale label replacement.
    await expect(sidebarRow.locator(".ww-calc-provenance-badge--exploratory")).toBeVisible();

    expect(jsErrors, "No JS errors").toHaveLength(0);
  });
});

// ---------------------------------------------------------------------------
// Scenario H: Source removal — cascade deletes the exploratory calc channel
// ---------------------------------------------------------------------------

test.describe("Scenario H — Source removal: exploratory calc channel cascade-deleted", () => {
  test("deleting the BEN5K source removes the exploratory calc channel from the list", async ({ page }) => {
    const jsErrors = [];
    page.on("pageerror", (err) => jsErrors.push(err.message));
    await page.goto("/index.html");

    const benSourceId = await uploadBen5k(page);
    const workspaceId = await getWorkspaceId(page);
    expect(workspaceId).toBeTruthy();

    const meta = await getSourceChannels(page, workspaceId, benSourceId);
    const voltCh = (meta.analog_channels || []).find(c => c.engineering_type === "Voltage");
    expect(voltCh, "BEN5K fixture must expose a Voltage channel — check synthetic_ben5k_phasor.ben").toBeTruthy();

    const resp = await createReversePolarity(page, workspaceId, {
      name: "Va_ben5k_cascade_h",
      sourceId: benSourceId,
      channelName: voltCh.name,
      unit: voltCh.unit || "kV",
      refSourceId: benSourceId,
    });
    expect(resp.ok()).toBe(true);
    const calc = await resp.json();

    // Confirm channel is present before deletion.
    const listBefore = await getCalcChannelList(page, workspaceId);
    expect(listBefore.some(c => c.id === calc.id), "Calc channel must be present before source deletion").toBe(true);

    // Delete the BEN5K source.
    const delResp = await page.request.delete(
      `${BACKEND}/api/v1/workspaces/${encodeURIComponent(workspaceId)}/sources/${encodeURIComponent(benSourceId)}`
    );
    expect(delResp.ok(), `Source deletion failed: ${delResp.status()}`).toBe(true);

    // Cascade: calc channel must be gone from the API list.
    const listAfter = await getCalcChannelList(page, workspaceId);
    expect(listAfter.some(c => c.id === calc.id), "Calc channel must be removed by cascade delete").toBe(false);

    // UI: reload → calc page shows no row for the deleted channel.
    await page.reload();
    // After deleting the only source, recordings table is empty.
    await expect(page.locator("#recordingsTableBody tr[data-source-id]")).toHaveCount(0, { timeout: 10000 });
    await page.locator("#mainNavCalculatedChannelsBtn").click();
    await expect(page.locator("#pageCalculatedChannels")).toBeVisible();
    await expect(page.locator(`.ww-cc-list-row[data-calculated-channel-id="${calc.id}"]`)).toHaveCount(0);

    expect(jsErrors, "No JS errors").toHaveLength(0);
  });
});
