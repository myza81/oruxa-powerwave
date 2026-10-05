// Waveform toolbar refinement (owner ticket), two parts:
//
// Part 1 -- "Synchronize Sources" is removed from the Waveform UI
// outright (not merely hidden): its own entry point, the per-Time-Group
// `.ww-tg-sync-btn`, had exactly one caller and no other workflow
// reached any of the modal it opened, so it was genuinely dead code
// once that button was removed (see test_frontend_time_group_sync.py's
// own static removal coverage for the full audit). The underlying
// AUTOMATIC synchronization-state behaviour this modal only ever let an
// engineer EDIT -- alignment-offset fetch/apply at render time, the
// sidebar's own per-source sync badge -- is a separate, still-fully-used
// mechanism and is NOT part of this removal.
//
// Part 2 -- "Set Cursor A as t=0"/"Clear t=0" moves from each Time
// Group Canvas's own local toolbar (`.ww-tg-t0-btn`) to the page-level
// #wwT0Btn, beside #wwCursorModeBtn in the Waveform top-toolbar
// migration's own left operational group (DEC-158) -- same
// wwActiveTimeGroupId() targeting model (active Time Group,
// self-healing to the first valid one, else disabled). t0 itself keeps
// its exact existing semantics (Cursor A of the resolved Time Group
// only, promoted via the SAME PUT/DELETE .../synchronization/t0
// endpoints) -- only the control's location and target resolution
// moved.

const { test, expect } = require("@playwright/test");
const path = require("path");
const { uploadRecord } = require("./support/event_reconstruction_helpers");

const FIXTURES = path.join(__dirname, "..", "backend", "tests", "fixtures", "comtrade");

async function uploadFixture(page, stem) {
  await page.goto("/index.html");
  await page.locator("#recordingsUploadBtn, #recordingsEmptyUploadBtn").first().click();
  await expect(page.locator("#uploadModalOverlay")).toBeVisible();
  await page.locator("#uploadModalFile_0").setInputFiles(path.join(FIXTURES, `${stem}.cfg`));
  await page.locator("#uploadModalFile_1").setInputFiles(path.join(FIXTURES, `${stem}.dat`));
  await page.locator("#uploadModalSubmitBtn").click();
  await page.locator("#uploadModalOverlay").waitFor({ state: "hidden" });
}

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

function t0State(page) {
  return page.evaluate(() => {
    const btn = document.getElementById("wwT0Btn");
    return {
      activeGroupId: wwActiveTimeGroupId(),
      disabled: btn.disabled,
      ariaPressed: btn.getAttribute("aria-pressed"),
      title: btn.title,
      ariaLabel: btn.getAttribute("aria-label"),
      hidden: btn.hidden,
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
  const sourceId = await page.locator("#recordingsTableBody tr[data-source-id]").first().getAttribute("data-source-id");
  await displayChannel(page, sourceId, "VA");
  const groupId = await page.evaluate((sid) => wwTimeGroupIdForDisplaySourceId(sid), sourceId);
  return { sourceId, groupId };
}

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

test.describe("Waveform toolbar refinement -- Synchronize Sources removed", () => {
  test("no Synchronize Sources entry point anywhere in the Waveform UI, in any state", async ({ page }) => {
    await setupOneGroup(page);
    await expect(page.locator(".ww-tg-sync-btn")).toHaveCount(0);
    await expect(page.locator('[id="wwSyncOverlay"]')).toHaveCount(0);
    await expect(page.locator('[title*="Synchronize Sources"]')).toHaveCount(0);
  });

  test("no Synchronize Sources entry point with no recordings loaded either", async ({ page }) => {
    await page.goto("/index.html");
    await page.locator("#mainNavWaveformBtn").click();
    await expect(page.locator(".ww-tg-sync-btn")).toHaveCount(0);
    await expect(page.locator('[id="wwSyncOverlay"]')).toHaveCount(0);
  });

  test("the underlying automatic synchronization-state behaviour (sidebar sync badge) still works, untouched by the removal", async ({ page }) => {
    // Timestamp-Based Initial Alignment: two sources whose recorded
    // start times differ become a Reference + a shifted source,
    // entirely automatically -- no modal, no manual action, proving the
    // AUTOMATIC fetch/apply/badge mechanism survives the removal intact.
    await uploadFixture(page, "synth_playback");
    await uploadFixture(page, "synth_playback_b");
    const rows = page.locator("#recordingsTableBody tr[data-source-id]");
    await expect(rows).toHaveCount(2);
    await page.locator("#mainNavRecordingsBtn").click();
    // At least a "Reference" badge must render once two sources
    // coexist -- the sidebar's own badge rendering is unconditional on
    // there ever having been an editable sync modal. (Its containing
    // <details> may be collapsed by default, so this checks the badge
    // exists in the DOM, not that its accordion section is expanded.)
    expect(await page.locator(".source-recording-sync-badge--reference").count()).toBeGreaterThan(0);
  });
});

test.describe("Waveform toolbar refinement -- t0 migrated to the page-level toolbar", () => {
  test("no t0 control remains in any per-Time-Group local canvas toolbar", async ({ page }) => {
    const { groupId } = await setupOneGroup(page);
    const canvas = page.locator(`.ww-time-group-canvas[data-time-group-id="${groupId}"]`);
    await expect(canvas.locator(".ww-tg-t0-btn")).toHaveCount(0);
    // Nothing left to separate in the local toolbar either.
    await expect(canvas.locator(".ww-tg-toolbar .ww-toolbar-sep")).toHaveCount(0);
    await expect(canvas.locator(".ww-tg-toolbar .ww-tg-fit-record-btn")).toHaveCount(1);
  });

  test("#wwT0Btn renders once, beside #wwCursorModeBtn, visible even with no recordings loaded", async ({ page }) => {
    await page.goto("/index.html");
    await page.locator("#mainNavWaveformBtn").click();
    await expect(page.locator("#wwT0Btn")).toHaveCount(1);
    await expect(page.locator("#wwT0Btn")).toBeVisible();
    const state = await t0State(page);
    expect(state.hidden).toBe(false);
    expect(state.disabled).toBe(true); // no valid Time Group yet
  });

  test("becomes enabled once a channel is displayed and Cursor A is placed; disabled before Cursor A exists", async ({ page }) => {
    const { groupId } = await setupOneGroup(page);
    let state = await t0State(page);
    expect(state.activeGroupId).toBe(groupId);
    expect(state.disabled).toBe(true); // no t0, no Cursor A yet
    expect(state.ariaLabel).toContain("Set Cursor A as t=0");

    await page.locator("#wwCursorModeBtn").click(); // auto-places Cursor A/B
    state = await t0State(page);
    expect(state.disabled).toBe(false);
    expect(state.ariaPressed).toBe("false");
  });

  test("clicking sets t0 from Cursor A, toggles the button to Clear t=0, and clicking again clears it", async ({ page }) => {
    await setupOneGroup(page);
    await page.locator("#wwCursorModeBtn").click();
    await expect(page.locator("#wwT0Btn")).toBeEnabled();

    await page.locator("#wwT0Btn").click();
    await expect.poll(async () => (await t0State(page)).ariaPressed).toBe("true");
    let state = await t0State(page);
    expect(state.ariaLabel).toBe("Clear t=0");
    expect(state.title).toContain("Clear t=0 (currently");

    await page.locator("#wwT0Btn").click();
    await expect.poll(async () => (await t0State(page)).ariaPressed).toBe("false");
    state = await t0State(page);
    expect(state.ariaLabel).toContain("Set Cursor A as t=0");
  });

  test("targets the active Time Group only; setting t0 in Group A never affects Group B's own t0", async ({ page }) => {
    const { groupIdA, groupIdB } = await setupTwoTimeGroups(page);
    await clickPanelHeader(page, groupIdA, 0);
    expect((await t0State(page)).activeGroupId).toBe(groupIdA);
    await page.locator("#wwCursorModeBtn").click();
    await page.locator("#wwT0Btn").click();
    await expect.poll(async () => (await t0State(page)).ariaPressed).toBe("true");

    const groupAHasT0 = await page.evaluate((gid) => wwHasT0(gid), groupIdA);
    const groupBHasT0 = await page.evaluate((gid) => wwHasT0(gid), groupIdB);
    expect(groupAHasT0).toBe(true);
    expect(groupBHasT0).toBe(false);

    // Switching the active target to Group B shows GROUP B's own
    // (unset) state, never Group A's stale "Clear t=0".
    await clickPanelHeader(page, groupIdB, 0);
    const state = await t0State(page);
    expect(state.activeGroupId).toBe(groupIdB);
    expect(state.ariaPressed).toBe("false");
  });

  test("the resolved group always has Cursor A availability checked independently -- Group B's own Cursor A never enables acting on Group A", async ({ page }) => {
    const { groupIdA, groupIdB } = await setupTwoTimeGroups(page);
    await clickPanelHeader(page, groupIdB, 0);
    await page.locator("#wwCursorModeBtn").click(); // Group B cursors ON only
    await clickPanelHeader(page, groupIdA, 0);
    const state = await t0State(page);
    expect(state.activeGroupId).toBe(groupIdA);
    expect(state.disabled).toBe(true); // Group A has neither t0 nor its OWN Cursor A
  });

  test("no console errors across the full set/clear/retarget interaction, both themes", async ({ page }) => {
    const consoleErrors = [];
    page.on("console", (msg) => { if (msg.type() === "error") consoleErrors.push(msg.text()); });
    await setupOneGroup(page);
    await page.locator("#wwCursorModeBtn").click();
    await page.locator("#wwT0Btn").click();
    await expect.poll(async () => (await t0State(page)).ariaPressed).toBe("true");
    await page.evaluate(() => document.documentElement.setAttribute("data-theme", "dark"));
    await page.locator("#wwT0Btn").click();
    await expect.poll(async () => (await t0State(page)).ariaPressed).toBe("false");
    expect(consoleErrors).toEqual([]);
  });
});
