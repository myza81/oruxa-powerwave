// Waveform/Event Reconstruction empty-state consistency (owner ticket):
// Waveform's own #wwToolbar used to be hidden outright whenever the
// workspace was empty -- unlike Event Reconstruction's own #wwErToolbar,
// which is NEVER hidden (individual tools disable via runtime state
// instead, the panel-header tool visibility rule this now also follows).
// A persistent panel-header shell (#wwEmptyWorkspaceHeader, reusing Event
// Reconstruction's own .ww-tg-sticky-top/.ww-tg-header classes verbatim)
// plus the existing #wwEmptyState message take over showing "nothing to
// look at yet", mirroring Event Reconstruction's own always-present
// #wwErCanvas header + #wwErEmptyState pattern.

const { test, expect } = require("@playwright/test");
const {
  collectConsoleErrors, uploadRecord, openEventReconstruction,
} = require("./support/event_reconstruction_helpers");

test.describe("Waveform -- no recordings", () => {
  test("top toolbar stays visible; the empty-state panel shell shows the no-recordings message; page-unsupported tools stay hidden", async ({ page }) => {
    const consoleErrors = collectConsoleErrors(page);
    await page.goto("/index.html");
    await page.locator("#mainNavWaveformBtn").click();

    await expect(page.locator("#wwToolbar")).toBeVisible();
    await expect(page.locator("#wwEmptyWorkspaceHeader")).toBeVisible();
    await expect(page.locator("#wwEmptyState")).toBeVisible();
    await expect(page.locator("#wwEmptyState")).toHaveText(
      "No recordings loaded. Open or add a recording to begin waveform analysis."
    );

    // Runtime-dependent controls: relevant to Waveform, but nothing to
    // act on yet -- rendered, disabled where the existing logic already
    // disables them (this ticket does not change per-tool enable logic).
    await expect(page.locator("#timeModeElapsedBtn")).toBeVisible();
    await expect(page.locator("#timeModeAbsoluteBtn")).toBeVisible();

    // Page-unsupported tools (panel-header tool visibility, DEC-154):
    // Waveform has no "relative to an event" concept -- hidden outright,
    // not shown disabled.
    await expect(page.locator("#timeModeRelativeBtn")).toBeHidden();

    expect(consoleErrors).toEqual([]);
  });

  test("the empty-state message switches to 'select channels' once a recording exists but nothing is displayed yet", async ({ page }) => {
    const consoleErrors = collectConsoleErrors(page);
    await page.goto("/index.html");
    await page.locator("#mainNavWaveformBtn").click();
    await uploadRecord(page, { station: "STN_A", startClock: "10:00:00.000000", durationS: 4 });
    await page.locator('#recordingsTableBody tr[data-source-id]').first().click();
    await expect(page.locator("#workspaceRow")).toBeVisible();

    await expect(page.locator("#wwToolbar")).toBeVisible();
    await expect(page.locator("#wwEmptyWorkspaceHeader")).toBeVisible();
    await expect(page.locator("#wwEmptyState")).toHaveText("Select channels from the sidebar to display waveforms.");

    expect(consoleErrors).toEqual([]);
  });

  test("no blank page structure: the Waveform panel/workspace shell always renders, in both themes", async ({ page }) => {
    await page.goto("/index.html");
    await page.locator("#mainNavWaveformBtn").click();
    await expect(page.locator("#viewWaveform")).toBeVisible();
    await expect(page.locator("#wwEmptyWorkspaceHeader .ww-tg-header-title")).toHaveText("Waveform");

    await page.evaluate(() => document.documentElement.setAttribute("data-theme", "dark"));
    await expect(page.locator("#wwToolbar")).toBeVisible();
    await expect(page.locator("#wwEmptyWorkspaceHeader")).toBeVisible();
    await expect(page.locator("#wwEmptyState")).toBeVisible();
  });
});

test.describe("Waveform -- recording loaded", () => {
  test("existing workflow is unaffected: selecting a channel hides the empty-state shell, plots normally, and the toolbar stays visible throughout", async ({ page }) => {
    const consoleErrors = collectConsoleErrors(page);
    await page.goto("/index.html");
    await page.locator("#mainNavWaveformBtn").click();
    await uploadRecord(page, { station: "STN_A", startClock: "10:00:00.000000", durationS: 4 });
    await page.locator('#recordingsTableBody tr[data-source-id]').first().click();
    await expect(page.locator("#workspaceRow")).toBeVisible();

    const channelRow = page.locator('#channelGroups tr.channel-row--toggle[data-channel-kind="analog"]').first();
    if ((await channelRow.getAttribute("aria-pressed")) !== "true") await channelRow.click();
    await expect(page.locator(".ww-time-group-canvas")).toBeVisible();

    await expect(page.locator("#wwToolbar")).toBeVisible();
    await expect(page.locator("#wwEmptyWorkspaceHeader")).toBeHidden();
    await expect(page.locator("#wwEmptyState")).toBeHidden();
    // Each Time Group canvas keeps its own real header -- unaffected by
    // the placeholder shell, which only exists for the zero-canvas case.
    await expect(page.locator(".ww-time-group-canvas .ww-tg-header-title").first()).toHaveText("Time Group 1");

    // Deselecting the one displayed channel returns to the empty shell,
    // now correctly reading "select channels" (a recording exists).
    await channelRow.click();
    await expect(page.locator("#wwEmptyWorkspaceHeader")).toBeVisible();
    await expect(page.locator("#wwEmptyState")).toHaveText("Select channels from the sidebar to display waveforms.");
    await expect(page.locator("#wwToolbar")).toBeVisible();

    expect(consoleErrors).toEqual([]);
  });

  test("no stale hidden buttons after navigating away to Event Reconstruction and back to Waveform", async ({ page }) => {
    await page.goto("/index.html");
    await page.locator("#mainNavWaveformBtn").click();
    await uploadRecord(page, { station: "STN_A", startClock: "10:00:00.000000", durationS: 4 });
    await page.locator('#recordingsTableBody tr[data-source-id]').first().click();
    await expect(page.locator("#workspaceRow")).toBeVisible();
    const channelRow = page.locator('#channelGroups tr.channel-row--toggle[data-channel-kind="analog"]').first();
    if ((await channelRow.getAttribute("aria-pressed")) !== "true") await channelRow.click();
    await expect(page.locator(".ww-time-group-canvas")).toBeVisible();

    await openEventReconstruction(page);
    await expect(page.locator("#wwErToolbar")).toBeVisible();

    await page.locator("#mainNavWaveformBtn").click();
    await expect(page.locator("#wwToolbar")).toBeVisible();
    await expect(page.locator("#wwEmptyWorkspaceHeader")).toBeHidden();
    await expect(page.locator(".ww-time-group-canvas")).toBeVisible();
    // No duplicate/stale placeholder header lingering alongside the real
    // per-canvas one (scoped to actual Time Group canvases -- excludes
    // the empty-workspace placeholder, which stays correctly hidden, and
    // Event Reconstruction's own canvas header, a different page).
    await expect(page.locator(".ww-time-group-canvas .ww-tg-header-title")).toHaveCount(1);
  });
});

test.describe("Event Reconstruction -- no regression", () => {
  test("its own top toolbar and empty-state behaviour are unchanged", async ({ page }) => {
    await page.goto("/index.html");
    await openEventReconstruction(page);
    await expect(page.locator("#wwErToolbar")).toBeVisible();
    await expect(page.locator("#wwErEmptyState")).toBeVisible();
    await expect(page.locator("#wwErEmptyState")).toHaveText(
      "No reconstruction records selected. Select records in the left panel to place them on one common timeline."
    );
  });
});
