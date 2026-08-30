// Minimal real-browser smoke-test foundation (pre-CSV/Excel-ingestion
// safety net). See docs/development/BROWSER_SMOKE_TEST.md and
// docs/project-memory/DECISIONS.md for the governing decision.
//
// This is deliberately ONE sequential walkthrough, not eight independent
// tests: Smokes C-G each depend on state the earlier steps establish
// (an uploaded source, a displayed channel, its own rendered Time Group
// canvas), so re-doing setup per check would only add runtime without
// adding isolation -- a fresh backend process (via playwright.config.js's
// webServer) and a fresh page load already give this run a clean
// workspace (section 14). test.step() still reports each Smoke
// individually in output.
//
// Selectors are the same stable ids/data-attributes/classes already used
// throughout the app's own frontend and its existing backend-side
// frontend regression tests (backend/tests/test_frontend_*.py) -- no new
// data-testid attributes were added; none were needed.

const { test, expect } = require("@playwright/test");
const path = require("path");

const FIXTURES = path.join(__dirname, "..", "backend", "tests", "fixtures", "comtrade");

test("Powerwave smoke: upload, display, Time Group, cursor, rename", async ({ page }) => {
  const consoleErrors = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(msg.text());
  });
  page.on("pageerror", (err) => consoleErrors.push(`pageerror: ${err.message}`));

  // ---- Smoke A: app loads ----
  await test.step("Smoke A - app loads, RECORDINGS area exists", async () => {
    await page.goto("/index.html");
    await expect(page.locator("#pageRecordings")).toBeVisible();
  });

  // ---- Smoke B: upload one known COMTRADE fixture ----
  let sourceId;
  await test.step("Smoke B - upload synth_ascii fixture, source appears in RECORDINGS", async () => {
    await page.locator("#recordingsUploadBtn, #recordingsEmptyUploadBtn").first().click();
    await expect(page.locator("#uploadModalOverlay")).toBeVisible();
    await page.locator("#uploadModalFile_0").setInputFiles(path.join(FIXTURES, "synth_ascii.cfg"));
    await page.locator("#uploadModalFile_1").setInputFiles(path.join(FIXTURES, "synth_ascii.dat"));
    await page.locator("#uploadModalSubmitBtn").click();
    await page.locator("#uploadModalOverlay").waitFor({ state: "hidden" });

    const row = page.locator("#recordingsTableBody tr[data-source-id]").first();
    await expect(row).toBeVisible();
    sourceId = await row.getAttribute("data-source-id");
    expect(sourceId).toBeTruthy();
  });

  // ---- Smoke C: display one analog channel ----
  await test.step("Smoke C - toggle one analog channel, waveform trace renders", async () => {
    await page.locator("#recordingsTableBody tr[data-source-id]").first().click();
    const row = page.locator('#channelGroups tr.channel-row--toggle[data-channel-kind="analog"]').first();
    await expect(row).toBeVisible();
    await expect(row).toHaveAttribute("data-source-id", sourceId);
    await row.click();
    await expect(row).toHaveAttribute("aria-pressed", "true");
    // A real Plotly-rendered trace inside this channel's own panel --
    // survival check only (section 16): existence of the rendered
    // chart surface, never pixel/layout assertions.
    await expect(page.locator(".ww-chart .plotly").first()).toBeVisible();
  });

  // ---- Smoke D: Time Group canvas exists ----
  await test.step("Smoke D - displayed channel belongs to a rendered Time Group canvas", async () => {
    const canvas = page.locator("#wwTimeGroupCanvases .ww-time-group-canvas").first();
    await expect(canvas).toBeVisible();
    await expect(canvas.locator(".ww-tg-toolbar-row")).toBeVisible();
    await expect(canvas.locator(".ww-tg-panels .ww-chart").first()).toBeVisible();
  });

  // ---- Smoke E: cursor interaction ----
  await test.step("Smoke E - Cursor A/B mode toggles on for this Time Group", async () => {
    const canvas = page.locator("#wwTimeGroupCanvases .ww-time-group-canvas").first();
    const cursorBtn = canvas.locator(".ww-tg-cursor-mode-btn");
    await expect(cursorBtn).toBeVisible();
    await cursorBtn.click();
    await expect(cursorBtn).toHaveAttribute("aria-pressed", "true");
    await expect(canvas.locator(".ww-tg-cursor-readout")).toBeVisible();
    await cursorBtn.click(); // back off, tidy state for the next step
  });

  // ---- Smoke F: channel context menu ----
  await test.step("Smoke F - right-click an analog row: native menu suppressed, Powerwave menu appears", async () => {
    const row = page.locator('#channelGroups tr.channel-row--toggle[data-channel-kind="analog"]').first();
    let defaultPrevented = null;
    await page.evaluate(() => {
      window.__smokeContextMenuResult = null;
      document.addEventListener(
        "contextmenu",
        (e) => {
          setTimeout(() => {
            window.__smokeContextMenuResult = e.defaultPrevented;
          }, 0);
        },
        false
      );
    });
    const box = await row.boundingBox();
    await page.mouse.move(box.x + 20, box.y + box.height / 2);
    await page.mouse.down({ button: "right" });
    await page.mouse.up({ button: "right" });
    defaultPrevented = await page.waitForFunction(() => window.__smokeContextMenuResult !== null).then(
      () => page.evaluate(() => window.__smokeContextMenuResult)
    );
    expect(defaultPrevented).toBe(true);
    await expect(page.locator("#wwChannelContextMenu")).toBeVisible();
  });

  // ---- Smoke G: Rename modal opens, targets the right channel ----
  await test.step("Smoke G - Rename... opens, targets the right-clicked channel", async () => {
    const channelName = await page
      .locator('#channelGroups tr.channel-row--toggle[data-channel-kind="analog"]')
      .first()
      .getAttribute("data-channel-name");
    await page.locator("#wwChannelMenuRenameBtn").click();
    await expect(page.locator("#wwChannelRenameOverlay")).toBeVisible();
    await expect(page.locator("#wwChannelRenameOriginal")).toHaveText(channelName);
    // Close without applying -- this slice only proves the modal opens
    // correctly targeted, not a full rename regression (already covered
    // by the channel-presentation feature's own dedicated test suite).
    await page.locator("#wwChannelRenameCancelBtn").click();
    await expect(page.locator("#wwChannelRenameOverlay")).toBeHidden();
  });

  // ---- Smoke H: no console/page errors across the whole run ----
  await test.step("Smoke H - zero unexpected console/page errors", async () => {
    expect(consoleErrors, `Unexpected console/page errors:\n${consoleErrors.join("\n")}`).toEqual([]);
  });
});
