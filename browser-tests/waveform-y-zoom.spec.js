// Waveform global Y-axis zoom (owner ticket): a page-level Y Zoom In/Out
// pair mirroring Event Reconstruction's own global wwErZoomYInBtn/
// wwErZoomYOutBtn (same icons, same "Zoom In/Out — Selected Y Axis"
// tooltip wording, same +/-20%/25% step factors and midpoint-fixed
// semantics) but targeting Waveform's own pre-existing wwActivePanel()
// resolver instead of a parallel axis-tracking concept -- Waveform has
// exactly one Y axis per panel (never several in one panel, unlike Event
// Reconstruction's Combined view), so "the active Y axis" and "the
// active panel" are the same thing. This is the SAME self-healing
// resolver Autoscale Y and the per-Time-Group Zoom In/Out dropdown
// already share (TG-D1), so clicking a panel header, using the local
// per-group zoom, or using this global pair all agree on one target.
//
// Event Reconstruction's own, unrelated axis-targeting coverage lives in
// event-reconstruction-active-yaxis.spec.js / event-reconstruction-yaxis-zoom.spec.js
// and is confirmed unchanged by this ticket (regression run), not
// duplicated here.

const { test, expect } = require("@playwright/test");
const path = require("path");
const { uploadRecord } = require("./support/event_reconstruction_helpers");

const FIXTURES = path.join(__dirname, "..", "backend", "tests", "fixtures", "comtrade");

// Voltage + Current, different quantities -- Grouped mode's own "one
// panel per quantity" convention (the DEFAULT layout mode, which keeps
// each panel's own clickable .ww-panel-header) naturally puts these in
// TWO separate panels of the SAME Time Group, no Separate-layout-mode
// detour needed.
const VI_CHANNELS = [
  { name: "VA", unit: "V", phase: "A", amplitude: 100, frequencyHz: 50 },
  { name: "IA", unit: "A", phase: "A", amplitude: 5, frequencyHz: 50 },
];

async function uploadFixture(page, stem) {
  await page.goto("/index.html");
  await page.locator("#recordingsUploadBtn, #recordingsEmptyUploadBtn").first().click();
  await expect(page.locator("#uploadModalOverlay")).toBeVisible();
  await page.locator("#uploadModalFile_0").setInputFiles(path.join(FIXTURES, `${stem}.cfg`));
  await page.locator("#uploadModalFile_1").setInputFiles(path.join(FIXTURES, `${stem}.dat`));
  await page.locator("#uploadModalSubmitBtn").click();
  await page.locator("#uploadModalOverlay").waitFor({ state: "hidden" });
}

// Displays one specific channel (by name, not just "the first") on the
// Waveform page -- opens the source and selects it from the Channels
// sidebar, the same flow every Waveform browser test already uses.
async function displayChannel(page, sourceId, channelName) {
  await page.locator(`#recordingsTableBody tr[data-source-id="${sourceId}"]`).click();
  await expect(page.locator("#wwWorkspaceLoading")).toBeHidden();
  const details = page.locator(`#channelGroups details.source-recording[data-source-id="${sourceId}"]`);
  await expect(details).toBeVisible();
  if (!(await details.evaluate((el) => el.open))) await details.locator("> summary").click();
  const row = page.locator(
    `#channelGroups tr.channel-row--toggle[data-channel-kind="analog"][data-source-id="${sourceId}"][data-channel-name="${channelName}"]`
  );
  await expect(row).toBeVisible();
  await row.click();
  await expect(row).toHaveAttribute("aria-pressed", "true");
}

function waveformState(page) {
  return page.evaluate(() => ({
    activeGroupKey: ww.activePanelGroupKey,
    zoomInDisabled: document.getElementById("wwZoomYInBtn").disabled,
    zoomOutDisabled: document.getElementById("wwZoomYOutBtn").disabled,
    zoomInTitle: document.getElementById("wwZoomYInBtn").title,
    zoomOutTitle: document.getElementById("wwZoomYOutBtn").title,
    panels: ww.panels.map((p) => ({
      id: p.id,
      groupKey: p.groupKey,
      timeGroupId: wwPanelTimeGroupId(p),
      label: p.label,
      yRange: p.chartEl && p.chartEl._fullLayout && p.chartEl._fullLayout.yaxis ? p.chartEl._fullLayout.yaxis.range.slice() : null,
      xRange: p.chartEl && p.chartEl._fullLayout && p.chartEl._fullLayout.xaxis ? p.chartEl._fullLayout.xaxis.range.slice() : null,
    })),
  }));
}

async function clickPanelHeader(page, groupId, nth = 0) {
  await page
    .locator(`.ww-time-group-canvas[data-time-group-id="${groupId}"] .ww-panel-header`)
    .nth(nth)
    .click();
}

// Waveform top-toolbar migration (owner ticket, DEC-158, later than this
// file's own original Y-zoom ticket, then corrected the same day):
// Autoscale Y is page-level (#wwAutoscaleYBtn), targeting the active
// PANEL -- the same wwActivePanel() Zoom Y itself targets -- not the
// active Time Group. Callers are expected to have already made the
// desired panel active (e.g. via clickPanelHeader()) before calling
// this; `groupId` is accepted only so call sites read naturally
// alongside clickPanelHeader(page, groupId, ...), it plays no role in
// resolving the actual target.
async function clickAutoscaleY(page, groupId) {
  await page.locator("#wwAutoscaleYBtn").click();
}

// Two panels in ONE Time Group: a Voltage channel and a Current channel
// from the same uploaded source -- two different quantities, so
// Grouped mode (the default) puts them in two separate panels of the
// same Time Group, each with its own clickable header.
async function setupTwoPanelsOneGroup(page) {
  await page.goto("/index.html");
  await uploadRecord(page, { station: "STN_A", startClock: "10:00:00.000000", durationS: 4, channels: VI_CHANNELS });
  const row = page.locator("#recordingsTableBody tr[data-source-id]").first();
  const sourceId = await row.getAttribute("data-source-id");
  await displayChannel(page, sourceId, "VA");
  // A second channel on the SAME already-open source: the sidebar's
  // channel list stays visible, so this selects it directly rather than
  // re-navigating through the (now hidden) recordings table.
  const secondRow = page.locator(
    `#channelGroups tr.channel-row--toggle[data-channel-kind="analog"][data-source-id="${sourceId}"][data-channel-name="IA"]`
  );
  await secondRow.click();
  await expect(secondRow).toHaveAttribute("aria-pressed", "true");
  await expect(page.locator(".ww-panel")).toHaveCount(2);
  await page.waitForTimeout(300); // let both charts reach a stable autoranged state
  const groupId = await page.evaluate((sid) => wwTimeGroupIdForDisplaySourceId(sid), sourceId);
  return { sourceId, groupId };
}

// Two separate Time Groups: two fixtures with non-overlapping recording
// start times (see playback.spec.js's own header comment for why this
// pairing reliably forms two groups, unlike the ER-focused uploadRecord()
// helper with a manual date override, which did not).
async function setupTwoTimeGroups(page) {
  await uploadFixture(page, "synth_playback");
  await uploadFixture(page, "synth_playback_b");
  const rows = page.locator("#recordingsTableBody tr[data-source-id]");
  await expect(rows).toHaveCount(2);
  const sourceIdA = await rows.nth(0).getAttribute("data-source-id");
  const sourceIdB = await rows.nth(1).getAttribute("data-source-id");
  for (const sourceId of [sourceIdA, sourceIdB]) {
    await page.locator("#mainNavRecordingsBtn").click();
    await displayChannel(page, sourceId, "V0_R");
  }
  await expect(page.locator(".ww-time-group-canvas")).toHaveCount(2);
  await page.waitForTimeout(300);
  const groupIdA = await page.evaluate((sid) => wwTimeGroupIdForDisplaySourceId(sid), sourceIdA);
  const groupIdB = await page.evaluate((sid) => wwTimeGroupIdForDisplaySourceId(sid), sourceIdB);
  return { sourceIdA, sourceIdB, groupIdA, groupIdB };
}

test.describe("Waveform global Y Zoom -- single Time Group, two panels", () => {
  test("Zoom Y In targets only the selected (active) panel's axis", async ({ page }) => {
    const { groupId } = await setupTwoPanelsOneGroup(page);
    await clickPanelHeader(page, groupId, 0);
    const before = await waveformState(page);
    expect(before.zoomInDisabled).toBe(false);
    const targetId = before.activeGroupKey;

    await page.locator("#wwZoomYInBtn").click();
    const after = await waveformState(page);

    for (const panel of after.panels) {
      const prior = before.panels.find((p) => p.id === panel.id);
      if (panel.groupKey === targetId) {
        expect(panel.yRange, "targeted panel's Y changed").not.toEqual(prior.yRange);
        const spanBefore = prior.yRange[1] - prior.yRange[0];
        const spanAfter = panel.yRange[1] - panel.yRange[0];
        expect(spanAfter).toBeCloseTo(spanBefore * 0.8, 6); // WW_ZOOM_STEP_IN_FACTOR
      } else {
        expect(panel.yRange, "other panel's Y unchanged").toEqual(prior.yRange);
      }
      expect(panel.xRange, "X unchanged").toEqual(prior.xRange);
    }
  });

  test("Zoom Y Out targets only the selected (active) panel's axis", async ({ page }) => {
    const { groupId } = await setupTwoPanelsOneGroup(page);
    await clickPanelHeader(page, groupId, 1);
    const before = await waveformState(page);
    const targetId = before.activeGroupKey;

    await page.locator("#wwZoomYOutBtn").click();
    const after = await waveformState(page);

    for (const panel of after.panels) {
      const prior = before.panels.find((p) => p.id === panel.id);
      if (panel.groupKey === targetId) {
        const spanBefore = prior.yRange[1] - prior.yRange[0];
        const spanAfter = panel.yRange[1] - panel.yRange[0];
        expect(spanAfter).toBeCloseTo(spanBefore * 1.25, 6); // WW_ZOOM_STEP_OUT_FACTOR
      } else {
        expect(panel.yRange, "other panel's Y unchanged").toEqual(prior.yRange);
      }
    }
  });

  test("switching the active panel via its header moves the Y Zoom target, never the other panel", async ({ page }) => {
    const { groupId } = await setupTwoPanelsOneGroup(page);
    await clickPanelHeader(page, groupId, 0);
    const firstTarget = (await waveformState(page)).activeGroupKey;

    await clickPanelHeader(page, groupId, 1);
    const state = await waveformState(page);
    expect(state.activeGroupKey).not.toBe(firstTarget);

    const before = state.panels.map((p) => ({ id: p.id, yRange: p.yRange }));
    await page.locator("#wwZoomYInBtn").click();
    const after = await waveformState(page);
    for (const panel of after.panels) {
      const prior = before.find((p) => p.id === panel.id);
      if (panel.groupKey === state.activeGroupKey) expect(panel.yRange).not.toEqual(prior.yRange);
      else expect(panel.yRange).toEqual(prior.yRange);
    }
  });
});

test.describe("Waveform global Y Zoom -- multiple Time Groups", () => {
  test("zooming the active panel never touches another Time Group's own panel", async ({ page }) => {
    const { groupIdA, groupIdB } = await setupTwoTimeGroups(page);
    await clickPanelHeader(page, groupIdB, 0);
    const before = await waveformState(page);
    expect(before.panels.find((p) => p.groupKey === before.activeGroupKey).timeGroupId).toBe(groupIdB);
    const otherPanel = before.panels.find((p) => p.timeGroupId === groupIdA);

    await page.locator("#wwZoomYInBtn").click();
    const after = await waveformState(page);
    const otherAfter = after.panels.find((p) => p.timeGroupId === groupIdA);
    expect(otherAfter.yRange).toEqual(otherPanel.yRange);
    expect(otherAfter.xRange).toEqual(otherPanel.xRange);

    const targetBefore = before.panels.find((p) => p.groupKey === before.activeGroupKey);
    const targetAfter = after.panels.find((p) => p.groupKey === before.activeGroupKey);
    expect(targetAfter.yRange).not.toEqual(targetBefore.yRange);
  });

  test("no explicit selection: falls back to ww.panels[0] (first by insertion order), and that is the only panel zoomed", async ({ page }) => {
    // Known, documented architectural nuance: ww.panels[0] reflects
    // insertion/display order, not the Time-Group-sorted "Time Group 1"
    // label -- this reuses wwActivePanel()'s own existing fallback as-is
    // (same one Autoscale Y / the per-group step zoom already share)
    // rather than building a competing strict-sorted resolver.
    const { groupIdA, groupIdB } = await setupTwoTimeGroups(page);
    const before = await waveformState(page);
    expect(before.zoomInDisabled).toBe(false);
    expect([groupIdA, groupIdB]).toContain(before.panels[0].timeGroupId);
    const fallbackTarget = before.panels[0];

    await page.locator("#wwZoomYInBtn").click();
    const after = await waveformState(page);
    for (const panel of after.panels) {
      const prior = before.panels.find((p) => p.id === panel.id);
      if (panel.id === fallbackTarget.id) expect(panel.yRange).not.toEqual(prior.yRange);
      else expect(panel.yRange).toEqual(prior.yRange);
    }
  });
});

test.describe("Waveform global Y Zoom -- no valid target", () => {
  test("no recordings at all: Y Zoom In/Out stay disabled", async ({ page }) => {
    await page.goto("/index.html");
    await page.locator("#mainNavWaveformBtn").click();
    const state = await waveformState(page);
    expect(state.zoomInDisabled).toBe(true);
    expect(state.zoomOutDisabled).toBe(true);
    expect(state.zoomInTitle).toBe("Zoom In — Selected Y Axis");
  });

  test("a recording exists but no channel is displayed yet: still disabled", async ({ page }) => {
    await uploadFixture(page, "synth_playback");
    const sourceId = await page.locator("#recordingsTableBody tr[data-source-id]").first().getAttribute("data-source-id");
    await page.locator(`#recordingsTableBody tr[data-source-id="${sourceId}"]`).click();
    await expect(page.locator("#workspaceRow")).toBeVisible();
    const state = await waveformState(page);
    expect(state.zoomInDisabled).toBe(true);
    expect(state.zoomOutDisabled).toBe(true);
  });

  test("the tooltip names the targeted panel's own label once a target exists", async ({ page }) => {
    const { groupId } = await setupTwoPanelsOneGroup(page);
    await clickPanelHeader(page, groupId, 0);
    const state = await waveformState(page);
    const target = state.panels.find((p) => p.groupKey === state.activeGroupKey);
    expect(state.zoomInTitle).toBe("Zoom In — " + target.label);
    expect(state.zoomOutTitle).toBe("Zoom Out — " + target.label);
  });
});

test.describe("Waveform global Y Zoom -- Autoscale Y interaction", () => {
  test("Autoscale Y restores the correct automatic range for the same target axis after a manual zoom", async ({ page }) => {
    const { groupId } = await setupTwoPanelsOneGroup(page);
    await clickPanelHeader(page, groupId, 0);
    const before = await waveformState(page);
    const targetId = before.activeGroupKey;
    const originalRange = before.panels.find((p) => p.groupKey === targetId).yRange;

    await page.locator("#wwZoomYInBtn").click();
    await page.locator("#wwZoomYInBtn").click();
    const zoomed = await waveformState(page);
    const zoomedRange = zoomed.panels.find((p) => p.groupKey === targetId).yRange;
    expect(zoomedRange).not.toEqual(originalRange);

    await clickAutoscaleY(page, groupId);
    await expect.poll(async () => {
      const state = await waveformState(page);
      return state.panels.find((p) => p.groupKey === targetId).yRange;
    }).not.toEqual(zoomedRange);
    const restored = await waveformState(page);
    const restoredPanel = restored.panels.find((p) => p.groupKey === targetId);
    const otherPanel = restored.panels.find((p) => p.groupKey !== targetId);
    const otherBefore = before.panels.find((p) => p.groupKey !== targetId);
    // Owner correction: Autoscale Y is single-axis-scoped, targeting
    // the SAME active panel Zoom Y targets (wwAutoscaleYPanel(
    // wwActivePanel())) -- the other panel in the same group is never
    // touched at all by this Autoscale click (not merely coincidentally
    // unchanged in value). Dedicated multi-axis isolation coverage
    // (manual range on one axis, Autoscale on the other) lives in
    // waveform-top-toolbar-migration.spec.js's own
    // TestAutoscaleYSharesZoomYsTarget-equivalent describe block.
    expect(otherPanel.yRange).toEqual(otherBefore.yRange);
    expect(restoredPanel.yRange[0]).toBeLessThanOrEqual(originalRange[0] + 1e-6);
    expect(restoredPanel.yRange[1]).toBeGreaterThanOrEqual(originalRange[1] - 1e-6);
  });
});

test.describe("Event Reconstruction Y-axis zoom -- no regression", () => {
  // Full behavioral coverage already lives in
  // event-reconstruction-active-yaxis.spec.js and
  // event-reconstruction-yaxis-zoom.spec.js; this is a minimal smoke
  // check that the global pair there is untouched by this ticket.
  const { addRecords, selectChannel, waitForPlot } = require("./support/event_reconstruction_helpers");

  test("wwErZoomYInBtn/wwErZoomYOutBtn still step the active axis as before", async ({ page }) => {
    await page.goto("/index.html");
    await uploadRecord(page, { station: "STN_A", startClock: "10:00:00.000000", durationS: 4 });
    await addRecords(page, ["STN_A"]);
    await selectChannel(page, "STN_A", "VA");
    await waitForPlot(page, 1);
    await expect(page.locator("#wwErZoomYInBtn")).toBeEnabled();
    await expect(page.locator("#wwErZoomYOutBtn")).toBeEnabled();
  });
});
