// WUI-001: Y actions now use the owning pane; global X/cursor/t0 contracts remain.
// Waveform top-toolbar migration (owner ticket): Zoom X In/Out,
// Autoscale X, Autoscale Y and A/B Cursors move from each Time Group
// Canvas's own local toolbar to the page-level #wwToolbar, joining the
// already-global Zoom Y pair (DEC-156, see waveform-y-zoom.spec.js for
// its own dedicated coverage, not duplicated here). Zoom X, Autoscale X
// and A/B Cursors share ONE "active Time Group" concept
// (wwActiveTimeGroupId(), a projection of wwActivePanel()'s own
// groupKey) -- the explicitly clicked panel's own Time Group if one was
// chosen, else the first Time Group that has a displayed channel;
// disabled only when none exists. Every action reuses an existing,
// unchanged core function (wwStepZoomX/wwResetOneTimeGroupView/
// wwToggleMeasurementCursors) -- only how groupId is resolved is new.
// t0 and Synchronize Sources stay local (out of scope for this ticket).
//
// Owner correction (same day as the migration itself): Autoscale Y
// shares Zoom Y's own exact SINGLE-AXIS target (wwActivePanel()
// directly, via wwAutoscaleYPanel()) -- never "every panel in the
// active Time Group." See the dedicated "Autoscale Y shares Zoom Y's
// own target" describe block below.

const { test, expect } = require("./support/test");
const path = require("path");
const { uploadRecord } = require("./support/event_reconstruction_helpers");

const FIXTURES = path.join(__dirname, "..", "backend", "tests", "fixtures", "comtrade");

async function uploadFixture(page, stem) {
  await page.goto("/index.html");
  await page.locator("#wwRdUploadBtn").first().click();
  await expect(page.locator("#uploadModalOverlay")).toBeVisible();
  await page.locator("#uploadModalFile_0").setInputFiles(path.join(FIXTURES, `${stem}.cfg`));
  await page.locator("#uploadModalFile_1").setInputFiles(path.join(FIXTURES, `${stem}.dat`));
  await page.locator("#uploadModalSubmitBtn").click();
  await page.locator("#uploadModalOverlay").waitFor({ state: "hidden" });
}

async function displayChannel(page, sourceId, channelName) {
  await page.locator(`#wwRdRecordingList .ww-rd-recording-item[data-source-id="${sourceId}"]`).click();
  await page.locator("#mainNavWaveformBtn").click();
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

async function clickPaneY(page, action) {
  const id = await page.evaluate(() => wwActivePanel()?.id);
  await page.locator(`#viewWaveform .ww-panel[data-panel-id="${id}"] [data-pane-y="${action}"]`).click();
}

function waveformState(page) {
  return page.evaluate(() => {
    const ids = ["wwZoomXInBtn", "wwZoomXOutBtn", "wwAutoscaleXBtn", "wwCursorModeBtn"];
    const buttons = {};
    for (const id of ids) {
      const el = document.getElementById(id);
      buttons[id] = { disabled: el.disabled, title: el.title, ariaPressed: el.getAttribute("aria-pressed") };
    }
    const active = wwActivePanel();
    const paneY = Object.fromEntries(['in','out','auto'].map(action => {
      const el = active?.headerEl.querySelector(`[data-pane-y="${action}"]`);
      return [action, {disabled:el?.disabled ?? true,title:el?.title ?? null}];
    }));
    return {
      activeGroupId: wwActiveTimeGroupId(),
      activePanelGroupKey: wwActivePanel() ? wwActivePanel().groupKey : null,
      activePanelId: active ? active.id : null,
      activePanelLabel: active ? active.label : null,
      buttons, paneY,
      panels: ww.panels.map((p) => ({
        id: p.id,
        groupKey: p.groupKey,
        label: p.label,
        timeGroupId: wwPanelTimeGroupId(p),
        xRange: p.chartEl && p.chartEl._fullLayout && p.chartEl._fullLayout.xaxis ? p.chartEl._fullLayout.xaxis.range.slice() : null,
        yRange: p.chartEl && p.chartEl._fullLayout && p.chartEl._fullLayout.yaxis ? p.chartEl._fullLayout.yaxis.range.slice() : null,
      })),
    };
  });
}

async function clickPanelHeader(page, groupId, nth = 0) {
  await page
    .locator(`.ww-time-group-canvas[data-time-group-id="${groupId}"] .ww-panel-header`)
    .nth(nth)
    .click();
}

const VI_CHANNELS = [
  { name: "VA", unit: "V", phase: "A", amplitude: 100, frequencyHz: 50 },
  { name: "IA", unit: "A", phase: "A", amplitude: 5, frequencyHz: 50 },
];

async function setupOneGroup(page) {
  await page.goto("/index.html");
  await uploadRecord(page, { station: "STN_A", startClock: "10:00:00.000000", durationS: 4, channels: VI_CHANNELS });
  const sourceId = await page.locator("#wwRdRecordingList .ww-rd-recording-item").first().getAttribute("data-source-id");
  await displayChannel(page, sourceId, "VA");
  const groupId = await page.evaluate((sid) => wwTimeGroupIdForDisplaySourceId(sid), sourceId);
  return { sourceId, groupId };
}

// Three different quantities (Voltage/Current/Frequency) -- Grouped
// mode's own "one panel per quantity" convention puts these in THREE
// separate panels of the SAME Time Group, matching the owner's own
// Autoscale Y correction example (Time Group 1: Voltage/Current/
// Frequency).
const VIF_CHANNELS = [
  { name: "VA", unit: "V", phase: "A", amplitude: 100, frequencyHz: 50 },
  { name: "IA", unit: "A", phase: "A", amplitude: 5, frequencyHz: 50 },
  { name: "F", unit: "Hz", amplitude: 1, frequencyHz: 0.5 },
];

async function setupThreePanelsOneGroup(page) {
  await page.goto("/index.html");
  await uploadRecord(page, { station: "STN_A", startClock: "10:00:00.000000", durationS: 4, channels: VIF_CHANNELS });
  const sourceId = await page.locator("#wwRdRecordingList .ww-rd-recording-item").first().getAttribute("data-source-id");
  await displayChannel(page, sourceId, "VA");
  for (const name of ["IA", "F"]) {
    const row = page.locator(
      `#channelGroups tr.channel-row--toggle[data-channel-kind="analog"][data-source-id="${sourceId}"][data-channel-name="${name}"]`
    );
    await row.click();
    await expect(row).toHaveAttribute("aria-pressed", "true");
  }
  await expect(page.locator(".ww-panel")).toHaveCount(3);
  await page.waitForTimeout(300);
  const groupId = await page.evaluate((sid) => wwTimeGroupIdForDisplaySourceId(sid), sourceId);
  return { sourceId, groupId };
}

async function setupTwoTimeGroups(page) {
  await uploadFixture(page, "synth_playback");
  await uploadFixture(page, "synth_playback_b");
  const rows = page.locator("#wwRdRecordingList .ww-rd-recording-item");
  await expect(rows).toHaveCount(2);
  const sourceIdA = await rows.nth(0).getAttribute("data-source-id");
  const sourceIdB = await rows.nth(1).getAttribute("data-source-id");
  for (const sourceId of [sourceIdA, sourceIdB]) {
    await page.locator("#mainNavRecordingDetailsBtn").click();
    await displayChannel(page, sourceId, "V0_R");
  }
  await expect(page.locator(".ww-time-group-canvas")).toHaveCount(2);
  await page.waitForTimeout(300);
  const groupIdA = await page.evaluate((sid) => wwTimeGroupIdForDisplaySourceId(sid), sourceIdA);
  const groupIdB = await page.evaluate((sid) => wwTimeGroupIdForDisplaySourceId(sid), sourceIdB);
  return { sourceIdA, sourceIdB, groupIdA, groupIdB };
}

test.describe("Waveform top toolbar -- controls present and complete", () => {
  test("Zoom X/Y, Autoscale X/Y and A/B Cursors all render in the page-level toolbar", async ({ page }) => {
    await page.goto("/index.html");
    for (const id of ["wwZoomXInBtn", "wwZoomXOutBtn", "wwAutoscaleXBtn", "wwCursorModeBtn"]) {
      await expect(page.locator("#" + id)).toHaveCount(1);
    }
  });

  test("no recordings loaded: the complete toolbar still renders, these controls stay visible but disabled", async ({ page }) => {
    const consoleErrors = [];
    page.on("console", (msg) => { if (msg.type() === "error") consoleErrors.push(msg.text()); });
    await page.goto("/index.html");
    await page.locator("#mainNavWaveformBtn").click();
    await expect(page.locator("#wwToolbar")).toBeVisible();
    await expect(page.locator("#wwEmptyState")).toBeVisible();
    const state = await waveformState(page);
    for (const id of ["wwZoomXInBtn", "wwZoomXOutBtn", "wwAutoscaleXBtn", "wwCursorModeBtn"]) {
      await expect(page.locator("#" + id)).toBeVisible();
      expect(state.buttons[id].disabled).toBe(true);
    }
    await expect(page.locator("#wwYAxisReadout")).toHaveCount(0);
    expect(state.activePanelId).toBeNull();
    // View/layout controls stay right-aligned, unaffected by this ticket.
    await expect(page.locator("#layoutModeToggle")).toBeVisible();
    expect(consoleErrors).toEqual([]);
  });

  test("a recording exists but no channel is displayed yet: still disabled", async ({ page }) => {
    await uploadFixture(page, "synth_playback");
    const sourceId = await page.locator("#wwRdRecordingList .ww-rd-recording-item").first().getAttribute("data-source-id");
    await page.locator(`#wwRdRecordingList .ww-rd-recording-item[data-source-id="${sourceId}"]`).click();
    await page.locator("#mainNavWaveformBtn").click();
    await expect(page.locator("#workspaceRow")).toBeVisible();
    const state = await waveformState(page);
    for (const id of ["wwZoomXInBtn", "wwZoomXOutBtn", "wwAutoscaleXBtn", "wwCursorModeBtn"]) {
      expect(state.buttons[id].disabled).toBe(true);
    }
  });

  test("once a channel is displayed, all five enable together, targeting the same active Time Group", async ({ page }) => {
    const { groupId } = await setupOneGroup(page);
    const state = await waveformState(page);
    expect(state.activeGroupId).toBe(groupId);
    // Zoom X Out starts disabled: a freshly-displayed Time Group opens
    // at its own full bounds, and Zoom Out reads as unavailable there
    // (the same nuance the now-removed local Zoom Out button had) --
    // every other control has no such "already at the limit" case.
    for (const id of ["wwZoomXInBtn", "wwAutoscaleXBtn", "wwCursorModeBtn"]) {
      expect(state.buttons[id].disabled, id).toBe(false);
    }
    expect(state.buttons.wwZoomXOutBtn.disabled).toBe(true);
    // The first valid axis remains the fallback target without a global label.
    expect(state.activePanelId).toBe(state.panels[0].id);
  });
});

test.describe("Waveform top toolbar -- per-Time-Group duplicate controls removed", () => {
  test("SUPERSEDED: the local canvas toolbar no longer shows Zoom/Autoscale/Cursor/t0/Sync controls at all -- a later Waveform toolbar refinement ticket moved t0 out the same way and removed Synchronize Sources outright; see waveform-toolbar-t0-sync-refinement.spec.js for that ticket's own full coverage", async ({ page }) => {
    await setupOneGroup(page);
    const canvas = page.locator(".ww-time-group-canvas").first();
    for (const cls of [
      ".ww-tg-zoom-in-split", ".ww-tg-zoom-out-split", ".ww-tg-reset-view-btn", ".ww-tg-autoscale-btn",
      ".ww-tg-cursor-mode-btn", ".ww-tg-t0-btn", ".ww-tg-sync-btn",
    ]) {
      await expect(canvas.locator(cls)).toHaveCount(0);
    }
    // Nothing left to separate: the hidden Fit Selected Record stub is
    // the toolbar's only remaining child.
    const sepCount = await canvas.locator(".ww-tg-toolbar .ww-toolbar-sep").count();
    expect(sepCount).toBe(0);
    await expect(canvas.locator(".ww-tg-toolbar .ww-tg-fit-record-btn")).toHaveCount(1);
  });
});

test.describe("Waveform top toolbar -- X-axis targeting (Zoom X, Autoscale X)", () => {
  test("Zoom X In/Out act on the active Time Group only; X range changes, Y stays", async ({ page }) => {
    const { groupIdA, groupIdB } = await setupTwoTimeGroups(page);
    await clickPanelHeader(page, groupIdB, 0);
    const before = await waveformState(page);
    expect(before.activeGroupId).toBe(groupIdB);

    await page.locator("#wwZoomXInBtn").click();
    const after = await waveformState(page);
    for (const panel of after.panels) {
      const prior = before.panels.find((p) => p.id === panel.id);
      if (panel.timeGroupId === groupIdB) {
        expect(panel.xRange, "target group X changed").not.toEqual(prior.xRange);
        expect(panel.yRange, "target group Y unchanged by X zoom").toEqual(prior.yRange);
      } else {
        expect(panel.xRange, "other group X unchanged").toEqual(prior.xRange);
      }
    }
  });

  test("Autoscale X restores the active Time Group's own full bounds, never another group's", async ({ page }) => {
    const { groupIdA, groupIdB } = await setupTwoTimeGroups(page);
    await clickPanelHeader(page, groupIdA, 0);
    await page.locator("#wwZoomXInBtn").click();
    await page.locator("#wwZoomXInBtn").click();
    const zoomed = await waveformState(page);
    const zoomedA = zoomed.panels.find((p) => p.timeGroupId === groupIdA);
    const otherBefore = zoomed.panels.find((p) => p.timeGroupId === groupIdB);

    await page.locator("#wwAutoscaleXBtn").click();
    await expect.poll(async () => {
      const state = await waveformState(page);
      return state.panels.find((p) => p.timeGroupId === groupIdA).xRange;
    }).not.toEqual(zoomedA.xRange);
    const restored = await waveformState(page);
    const otherAfter = restored.panels.find((p) => p.timeGroupId === groupIdB);
    expect(otherAfter.xRange).toEqual(otherBefore.xRange);
  });

  test("no explicit selection: Zoom X falls back to ww.panels[0]'s own Time Group, matching Zoom Y's own fallback", async ({ page }) => {
    const { groupIdA, groupIdB } = await setupTwoTimeGroups(page);
    const state = await waveformState(page);
    expect([groupIdA, groupIdB]).toContain(state.activeGroupId);
    expect(state.activeGroupId).toBe(state.panels[0].timeGroupId);
    expect(state.buttons.wwZoomXInBtn.disabled).toBe(false);
  });
});

test.describe("Waveform top toolbar -- A/B Cursors targeting", () => {
  test("toggling A/B Cursors affects only the active Time Group; never every group at once", async ({ page }) => {
    const { groupIdA, groupIdB } = await setupTwoTimeGroups(page);
    await clickPanelHeader(page, groupIdA, 0);
    let state = await waveformState(page);
    expect(state.activeGroupId).toBe(groupIdA);
    expect(state.buttons.wwCursorModeBtn.ariaPressed).toBe("false");

    await page.locator("#wwCursorModeBtn").click();
    state = await waveformState(page);
    expect(state.buttons.wwCursorModeBtn.ariaPressed).toBe("true");
    const groupACursorsEnabled = await page.evaluate((gid) => wwTimeGroupCursorState(gid).enabled, groupIdA);
    const groupBCursorsEnabled = await page.evaluate((gid) => wwTimeGroupCursorState(gid).enabled, groupIdB);
    expect(groupACursorsEnabled).toBe(true);
    expect(groupBCursorsEnabled).toBe(false); // never silently applied to every Time Group

    // Switching the active target to Group B and toggling again only
    // changes Group B -- Group A's own cursors stay on, untouched.
    await clickPanelHeader(page, groupIdB, 0);
    state = await waveformState(page);
    expect(state.activeGroupId).toBe(groupIdB);
    expect(state.buttons.wwCursorModeBtn.ariaPressed).toBe("false"); // Group B's own (still off) state
    await page.locator("#wwCursorModeBtn").click();
    const groupAStillOn = await page.evaluate((gid) => wwTimeGroupCursorState(gid).enabled, groupIdA);
    const groupBNowOn = await page.evaluate((gid) => wwTimeGroupCursorState(gid).enabled, groupIdB);
    expect(groupAStillOn).toBe(true);
    expect(groupBNowOn).toBe(true);
  });

  test("the button's own aria-pressed follows the active target when switched, no stale state", async ({ page }) => {
    const { groupIdA, groupIdB } = await setupTwoTimeGroups(page);
    await clickPanelHeader(page, groupIdA, 0);
    await page.locator("#wwCursorModeBtn").click(); // Group A cursors ON
    await clickPanelHeader(page, groupIdB, 0);
    const state = await waveformState(page);
    expect(state.buttons.wwCursorModeBtn.ariaPressed).toBe("false"); // Group B's own OFF state, not Group A's stale ON
  });
});

test.describe("Waveform top toolbar -- Autoscale Y shares Zoom Y's own target", () => {
  test("Autoscale Y resets only the selected Y-axis; the other two panels in the same Time Group are untouched", async ({ page }) => {
    const { groupId } = await setupThreePanelsOneGroup(page);
    // Select the middle (Current) panel -- matches the owner's own
    // Voltage/Current/Frequency example.
    await clickPanelHeader(page, groupId, 1);
    const before = await waveformState(page);
    const targetId = before.activePanelGroupKey;
    expect(before.panels.find((p) => p.groupKey === targetId).timeGroupId).toBe(groupId);
    const others = before.panels.filter((p) => p.groupKey !== targetId);
    expect(others).toHaveLength(2); // Voltage and Frequency

    await clickPaneY(page, "in");
    await clickPaneY(page, "in");
    const zoomed = await waveformState(page);
    const zoomedTarget = zoomed.panels.find((p) => p.groupKey === targetId);
    expect(zoomedTarget.yRange).not.toEqual(before.panels.find((p) => p.groupKey === targetId).yRange);
    for (const other of others) {
      expect(zoomed.panels.find((p) => p.id === other.id).yRange, "Zoom Y never touches other axes").toEqual(other.yRange);
    }

    await clickPaneY(page, "auto");
    await expect.poll(async () => {
      const state = await waveformState(page);
      return state.panels.find((p) => p.groupKey === targetId).yRange;
    }).not.toEqual(zoomedTarget.yRange);

    const restored = await waveformState(page);
    const restoredTarget = restored.panels.find((p) => p.groupKey === targetId);
    // Selected Y-axis returns to its (approximately) original automatic
    // range -- Autoscale Y undoes the manual Zoom In.
    const originalRange = before.panels.find((p) => p.groupKey === targetId).yRange;
    expect(restoredTarget.yRange[0]).toBeLessThanOrEqual(originalRange[0] + 1e-6);
    expect(restoredTarget.yRange[1]).toBeGreaterThanOrEqual(originalRange[1] - 1e-6);
    // Other Y-axes in the same Time Group remain completely unchanged
    // by the Autoscale Y click -- never "every panel in the group."
    for (const other of others) {
      expect(restored.panels.find((p) => p.id === other.id).yRange, "Autoscale Y never touches other axes").toEqual(other.yRange);
    }
  });

  test("other Time Groups remain unaffected by Autoscale Y", async ({ page }) => {
    const { groupIdA, groupIdB } = await setupTwoTimeGroups(page);
    await clickPanelHeader(page, groupIdB, 0);
    const before = await waveformState(page);
    const otherGroupPanel = before.panels.find((p) => p.timeGroupId === groupIdA);

    await clickPaneY(page, "in");
    await clickPaneY(page, "auto");
    await page.waitForTimeout(200);
    const after = await waveformState(page);
    const otherGroupAfter = after.panels.find((p) => p.timeGroupId === groupIdA);
    expect(otherGroupAfter.yRange).toEqual(otherGroupPanel.yRange);
  });

  test("no explicit selection: Autoscale Y falls back to ww.panels[0], the exact same panel Zoom Y falls back to", async ({ page }) => {
    const { groupIdA, groupIdB } = await setupTwoTimeGroups(page);
    const state = await waveformState(page);
    expect(state.paneY.auto.disabled).toBe(false);
    const fallbackPanel = state.panels[0];

    await clickPaneY(page, "in");
    const zoomed = await waveformState(page);
    const zoomedFallback = zoomed.panels.find((p) => p.id === fallbackPanel.id);
    expect(zoomedFallback.yRange).not.toEqual(fallbackPanel.yRange);

    await clickPaneY(page, "auto");
    await expect.poll(async () => {
      const s = await waveformState(page);
      return s.panels.find((p) => p.id === fallbackPanel.id).yRange;
    }).not.toEqual(zoomedFallback.yRange);
    // Every other panel (including the other Time Group's own) is
    // untouched -- the SAME single fallback panel Zoom Y itself used.
    const after = await waveformState(page);
    for (const panel of after.panels) {
      if (panel.id === fallbackPanel.id) continue;
      const prior = zoomed.panels.find((p) => p.id === panel.id);
      expect(panel.yRange).toEqual(prior.yRange);
    }
  });

  test("Zoom Y and Autoscale Y resolve exactly the same target when the active panel switches", async ({ page }) => {
    const { groupId } = await setupThreePanelsOneGroup(page);
    await clickPanelHeader(page, groupId, 0);
    const first = await waveformState(page);
    expect(first.paneY.in.title).toBe("Zoom Y In");
    expect(first.paneY.auto.title).toBe("Autoscale Y");

    await clickPanelHeader(page, groupId, 2);
    const second = await waveformState(page);
    expect(second.activePanelGroupKey).not.toBe(first.activePanelGroupKey);
    expect(second.paneY.in.title).toBe("Zoom Y In");
    expect(second.paneY.auto.title).toBe("Autoscale Y");
  });

  test("no valid Y-axis: Autoscale Y stays visible but disabled, matching Zoom Y exactly", async ({ page }) => {
    await page.goto("/index.html");
    await page.locator("#mainNavWaveformBtn").click();
    const state = await waveformState(page);
    expect(state.paneY.auto.disabled).toBe(true);
    expect(state.paneY.in.disabled).toBe(true);
    await expect(page.locator("#viewWaveform [data-pane-y]")).toHaveCount(0);
  });
});

test.describe("Waveform active-pane authority without a global Y readout", () => {
  test("no data: no active pane and no obsolete readout", async ({ page }) => {
    await page.goto("/index.html");
    await page.locator("#mainNavWaveformBtn").click();
    const state = await waveformState(page);
    expect(state.activePanelId).toBeNull();
    expect(state.activeGroupId).toBeNull();
    await expect(page.locator("#wwYAxisReadout")).toHaveCount(0);
  });

  test("the first valid Waveform axis remains the fallback target", async ({ page }) => {
    const { groupId } = await setupOneGroup(page);
    const state = await waveformState(page);
    expect(state.panels).toHaveLength(1);
    expect(state.activePanelId).toBe(state.panels[0].id);
    expect(state.activeGroupId).toBe(groupId);
  });

  test("selecting another Y-axis changes the actual active pane", async ({ page }) => {
    const { groupId } = await setupThreePanelsOneGroup(page);
    await clickPanelHeader(page, groupId, 0);
    const first = await waveformState(page);
    await clickPanelHeader(page, groupId, 2);
    const second = await waveformState(page);
    expect(second.activePanelId).not.toBe(first.activePanelId);
    expect(second.activePanelId).toBe(second.panels.find((p) => p.groupKey === second.activePanelGroupKey).id);
  });

  test("Zoom Y affects exactly the selected pane", async ({ page }) => {
    const { groupId } = await setupThreePanelsOneGroup(page);
    await clickPanelHeader(page, groupId, 1);
    const before = await waveformState(page);
    const targetPanel = before.panels.find((p) => p.id === before.activePanelId);

    await clickPaneY(page, "in");
    const after = await waveformState(page);
    expect(after.activePanelId).toBe(before.activePanelId);
    const changed = after.panels.find((p) => p.id === targetPanel.id);
    expect(changed.yRange).not.toEqual(targetPanel.yRange);
    for (const other of before.panels.filter((p) => p.id !== targetPanel.id)) {
      expect(after.panels.find((p) => p.id === other.id).yRange).toEqual(other.yRange);
    }
  });

  test("Autoscale Y affects exactly the selected pane", async ({ page }) => {
    const { groupId } = await setupThreePanelsOneGroup(page);
    await clickPanelHeader(page, groupId, 1);
    const before = await waveformState(page);
    const targetPanel = before.panels.find((p) => p.id === before.activePanelId);

    await clickPaneY(page, "in");
    await clickPaneY(page, "in");
    const zoomed = await waveformState(page);
    const zoomedTarget = zoomed.panels.find((p) => p.id === targetPanel.id);
    expect(zoomedTarget.yRange).not.toEqual(targetPanel.yRange);
    expect(zoomed.activePanelId).toBe(before.activePanelId);

    await clickPaneY(page, "auto");
    await expect.poll(async () => {
      const s = await waveformState(page);
      return s.panels.find((p) => p.id === targetPanel.id).yRange;
    }).not.toEqual(zoomedTarget.yRange);
    const restored = await waveformState(page);
    expect(restored.activePanelId).toBe(before.activePanelId);
    for (const other of before.panels.filter((p) => p.id !== targetPanel.id)) {
      expect(restored.panels.find((p) => p.id === other.id).yRange).toEqual(other.yRange);
    }
  });

  test("removing the active axis selects a valid remaining pane", async ({ page }) => {
    const { sourceId, groupId } = await setupThreePanelsOneGroup(page);
    await clickPanelHeader(page, groupId, 1); // Current
    const before = await waveformState(page);
    expect(before.activePanelLabel).toContain("Current");

    // Deselect the Current channel -- its own axis disappears entirely.
    const row = page.locator(
      `#channelGroups tr.channel-row--toggle[data-channel-kind="analog"][data-source-id="${sourceId}"][data-channel-name="IA"]`
    );
    await row.click();
    await expect(row).toHaveAttribute("aria-pressed", "false");
    await expect(page.locator(".ww-panel")).toHaveCount(2);

    const after = await waveformState(page);
    expect(after.activePanelId).not.toBe(before.activePanelId);
    expect(after.activePanelId).not.toBeNull();
    expect(after.panels.map(p=>p.id)).toContain(after.activePanelId);
  });

  test("clearing the workspace clears the actual active pane", async ({ page }) => {
    await setupOneGroup(page);
    expect((await waveformState(page)).activePanelId).not.toBeNull();
    await page.locator("#clearWorkspaceBtn").click();
    const state = await waveformState(page);
    expect(state.activePanelId).toBeNull();
    expect(state.panels).toHaveLength(0);
  });

  test("switching panes targets the owning Time Group", async ({ page }) => {
    const { groupIdA, groupIdB } = await setupTwoTimeGroups(page);
    await clickPanelHeader(page, groupIdA, 0);
    const stateA = await waveformState(page);
    expect(stateA.activeGroupId).toBe(groupIdA);
    expect(stateA.panels.find(p=>p.id===stateA.activePanelId).timeGroupId).toBe(groupIdA);

    await clickPanelHeader(page, groupIdB, 0);
    const stateB = await waveformState(page);
    expect(stateB.activeGroupId).toBe(groupIdB);
    expect(stateB.panels.find(p=>p.id===stateB.activePanelId).timeGroupId).toBe(groupIdB);
    expect(stateB.activePanelGroupKey).not.toBe(stateA.activePanelGroupKey);
  });
});

test.describe("Event Reconstruction -- active axis readout no regression", () => {
  test("wwErActiveAxisReadout keeps its own behaviour, untouched by Waveform's new readout", async ({ page }) => {
    const { addRecords, selectChannel, waitForPlot } = require("./support/event_reconstruction_helpers");
    await page.goto("/index.html");
    await uploadRecord(page, { station: "STN_A", startClock: "10:00:00.000000", durationS: 4 });
    await addRecords(page, ["STN_A"]);
    await selectChannel(page, "STN_A", "VA");
    await waitForPlot(page, 1);
    await expect(page.locator("#wwErActiveAxisReadout")).toHaveText(/^Y: /);
    await expect(page.locator("#wwErActiveAxisReadout")).not.toHaveText("Y: Select axis");
  });
});

test.describe("Waveform top toolbar -- spacing after Voltage Display relocation", () => {
  test("Time and horizontal controls have no vacant Voltage Display family", async ({ page }) => {
    await page.goto("/index.html");
    await page.locator("#mainNavWaveformBtn").click();
    await expect(page.locator("#wwDetectEventBtn")).toBeHidden();
    await expect(page.locator("#wwDetectEventSep")).toBeHidden();

    const timeBox = await page.locator("#timeModeToggle").boundingBox();
    const navigationBox = await page.locator("#wwZoomXOutBtn").boundingBox();
    await expect(page.locator("#wwToolbar #wwUnitModeToggle")).toHaveCount(0);
    const gap = navigationBox.x - (timeBox.x + timeBox.width);
    // A normal single-separator family gap: sep width (1px) + its own
    // 4px side margins + the toolbar's own 2px flex gaps on each side
    // of it -- comfortably under the ~20px a doubled pair of adjacent
    // separators would produce.
    expect(gap).toBeGreaterThan(5);
    expect(gap).toBeLessThan(16);
  });
});

// RETIRED (owner decision, P0 closeout 2026-11-25): "Per-Unit Settings icon" -- the two tests asserted
// the Per-Unit Settings Hub toolbar button (#wwOpenPerUnitSettingsBtn, pu_settings.svg), which PU-UI-001
// removed on purpose (1c60a1e). Per-unit configuration lives in Recording Details.

test.describe("Waveform top toolbar -- Clear Waveforms restored to the left operational group", () => {
  test("visible and disabled with no recordings; the complete toolbar stays stable", async ({ page }) => {
    await page.goto("/index.html");
    await page.locator("#mainNavWaveformBtn").click();
    const btn = page.locator("#clearWorkspaceBtn");
    await expect(btn).toBeVisible();
    await expect(btn).toBeDisabled();
    const iconSpan = btn.locator(".ww-icon");
    const maskImage = await iconSpan.evaluate((el) => getComputedStyle(el).webkitMaskImage || getComputedStyle(el).maskImage);
    // WUI-002: exact owner mockup artwork; the disabled-state contract is unchanged.
    expect(maskImage).toContain("/waveform/wui-002/clear.svg");
  });

  test("sits on the left, after Annotations and before the right-aligned view/layout group", async ({ page }) => {
    await page.goto("/index.html");
    const order = await page.evaluate(() => {
      const toolbar = document.getElementById("wwToolbar");
      const children = Array.from(toolbar.children);
      const indexOf = (id) => children.findIndex((el) => el.id === id || el.querySelector?.("#" + id));
      return {
        annotations: indexOf("wwAnnotationListBtn"),
        clear: indexOf("clearWorkspaceBtn"),
        spacer: children.findIndex((el) => el.classList.contains("toolbar-spacer")),
        splitView: indexOf("wwSplitViewBtn"),
      };
    });
    expect(order.annotations).toBeLessThan(order.clear);
    expect(order.clear).toBeLessThan(order.spacer);
    expect(order.spacer).toBeLessThan(order.splitView);
  });

  test("enables once a waveform is displayed; clears only the displayed panel, never the source recording", async ({ page }) => {
    const { groupId } = await setupOneGroup(page);
    const btn = page.locator("#clearWorkspaceBtn");
    await expect(btn).toBeEnabled();
    const sourceCountBefore = await page.locator("#wwRdRecordingList .ww-rd-recording-item").count();

    await btn.click();
    await expect(page.locator(".ww-panel")).toHaveCount(0);
    await expect(btn).toBeDisabled();
    // Navigate to Recordings to confirm the source recording itself is
    // still present -- display-only clear, never a server-side delete.
    await page.locator("#mainNavRecordingDetailsBtn").click();
    await expect(page.locator("#wwRdRecordingList .ww-rd-recording-item")).toHaveCount(sourceCountBefore);
  });

  test("no duplicate Clear control remains anywhere else in the toolbar", async ({ page }) => {
    await page.goto("/index.html");
    await expect(page.locator("#clearWorkspaceBtn")).toHaveCount(1);
  });
});

test.describe("Event Reconstruction -- spacing/icon/Clear Waveforms changes no regression", () => {
  test("ER's own toolbar is unaffected", async ({ page }) => {
    const { addRecords, selectChannel, waitForPlot, openEventReconstruction } = require("./support/event_reconstruction_helpers");
    await page.goto("/index.html");
    await uploadRecord(page, { station: "STN_A", startClock: "10:00:00.000000", durationS: 4 });
    await openEventReconstruction(page);
    await expect(page.locator("#wwErToolbar")).toBeVisible();
    // ER has no Clear Waveforms / Detect Event / Per-Unit Settings
    // controls of its own -- confirms this ticket did not leak anything
    // into its toolbar.
    await expect(page.locator("#wwErToolbar #clearWorkspaceBtn")).toHaveCount(0);
    await expect(page.locator("#wwErToolbar #wwDetectEventBtn")).toHaveCount(0);
    await expect(page.locator("#wwErToolbar #wwOpenPerUnitSettingsBtn")).toHaveCount(0);
  });
});

test.describe("Waveform top toolbar -- themes, layout, console", () => {
  test("no duplicated controls document-wide; both themes; narrower viewport; no console errors", async ({ page }) => {
    const consoleErrors = [];
    page.on("console", (msg) => { if (msg.type() === "error") consoleErrors.push(msg.text()); });
    await setupOneGroup(page);
    for (const id of ["wwZoomXInBtn", "wwZoomXOutBtn", "wwAutoscaleXBtn", "wwCursorModeBtn"]) {
      await expect(page.locator("#" + id)).toHaveCount(1); // exactly one instance document-wide, no leftover local duplicate
    }
    await page.evaluate(() => document.documentElement.setAttribute("data-theme", "dark"));
    await expect(page.locator("#wwToolbar")).toBeVisible();
    await expect(page.locator("#wwZoomXInBtn")).toBeVisible();
    await page.setViewportSize({ width: 1100, height: 800 });
    await page.waitForTimeout(200);
    await expect(page.locator("#wwToolbar")).toBeVisible();
    await expect(page.locator("#layoutModeToggle")).toBeVisible();
    expect(consoleErrors).toEqual([]);
  });
});

test.describe("Event Reconstruction -- no regression", () => {
  test("its own global Zoom X/Autoscale X/A-B-Cursors controls still work as before", async ({ page }) => {
    const { addRecords, selectChannel, waitForPlot } = require("./support/event_reconstruction_helpers");
    await page.goto("/index.html");
    await uploadRecord(page, { station: "STN_A", startClock: "10:00:00.000000", durationS: 4 });
    await addRecords(page, ["STN_A"]);
    await selectChannel(page, "STN_A", "VA");
    await waitForPlot(page, 1);
    await expect(page.locator("#wwErZoomInBtn")).toBeEnabled();
    await expect(page.locator("#wwErResetViewBtn")).toBeEnabled();
    await expect(page.locator("#wwErCursorModeBtn")).toBeEnabled();
  });
});
