// Event Reconstruction -- Slice 0 (frontend shell only).
//
// Covers the new main-menu entry, the page shell (left recording panel,
// waveform workspace shell, standard interaction toolbar), its shared
// Waveform visual language, and the boundary it must keep with the
// shared Waveform engine: opening Event Reconstruction or using its
// controls must never change Waveform state.

const { test, expect } = require("@playwright/test");
const path = require("path");

const FIXTURES = path.join(__dirname, "..", "backend", "tests", "fixtures", "comtrade");

function collectConsoleErrors(page) {
  const errors = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") errors.push(msg.text());
  });
  page.on("pageerror", (err) => errors.push(`pageerror: ${err.message}`));
  return errors;
}

async function uploadSynthAscii(page) {
  await page.locator("#recordingsUploadBtn, #recordingsEmptyUploadBtn").first().click();
  await expect(page.locator("#uploadModalOverlay")).toBeVisible();
  await page.locator("#uploadModalFile_0").setInputFiles(path.join(FIXTURES, "synth_ascii.cfg"));
  await page.locator("#uploadModalFile_1").setInputFiles(path.join(FIXTURES, "synth_ascii.dat"));
  await page.locator("#uploadModalSubmitBtn").click();
  await page.locator("#uploadModalOverlay").waitFor({ state: "hidden" });
  const row = page.locator("#recordingsTableBody tr[data-source-id]").first();
  await expect(row).toBeVisible();
  return row.getAttribute("data-source-id");
}

test.describe("Event Reconstruction -- Slice 0 shell", () => {
  test("menu entry sits immediately after Waveform and switches pages normally", async ({ page }) => {
    const consoleErrors = collectConsoleErrors(page);
    await page.goto("/index.html");

    const navOrder = await page.locator("#mainSidebarMenu .shell-nav-list .shell-nav-item").evaluateAll((items) =>
      items.map((item) => item.id)
    );
    expect(navOrder).toEqual([
      "mainNavRecordingsBtn",
      "mainNavWaveformBtn",
      "mainNavEventReconstructionBtn",
      "mainNavTableBtn",
      "mainNavCalculatedChannelsBtn",
      "mainNavAnalysisBtn",
      "mainNavComplianceBtn",
      "mainNavCalculatorBtn",
    ]);
    await expect(page.locator("#mainNavEventReconstructionBtn .shell-nav-label")).toHaveText("Event Reconstruction");

    const erNav = page.locator("#mainNavEventReconstructionBtn");
    await erNav.click();
    await expect(page.locator("#pageEventReconstruction")).toBeVisible();
    await expect(erNav).toHaveAttribute("aria-current", "page");
    await expect(page.locator("#workspaceRow")).toBeHidden();
    await expect(page.locator("#pageRecordings")).toBeHidden();

    // Every other page still switches, and Event Reconstruction hides.
    const pages = [
      ["#mainNavWaveformBtn", "#workspaceRow"],
      ["#mainNavRecordingsBtn", "#pageRecordings"],
      ["#mainNavCalculatedChannelsBtn", "#pageCalculatedChannels"],
      ["#mainNavAnalysisBtn", "#pageAnalysis"],
      ["#mainNavComplianceBtn", "#pageCompliance"],
      ["#mainNavCalculatorBtn", "#pageCalculator"],
    ];
    for (const [navSelector, pageSelector] of pages) {
      await page.locator(navSelector).click();
      await expect(page.locator(pageSelector)).toBeVisible();
      await expect(page.locator("#pageEventReconstruction")).toBeHidden();
      await expect(erNav).not.toHaveAttribute("aria-current", "page");
      await erNav.click();
      await expect(page.locator("#pageEventReconstruction")).toBeVisible();
      await expect(page.locator(pageSelector)).toBeHidden();
    }

    expect(consoleErrors).toEqual([]);
  });

  test("empty workspace shows the left recording panel, the workspace shell and the toolbar", async ({ page }) => {
    const consoleErrors = collectConsoleErrors(page);
    await page.goto("/index.html");
    await page.locator("#mainNavEventReconstructionBtn").click();

    // Left recording panel, left of the main workspace.
    const sidebar = page.locator("#wwErSidebar");
    await expect(sidebar).toBeVisible();
    await expect(page.locator("#wwErRecordingsHeading")).toContainText("Recordings");
    await expect(page.locator("#wwErRecordingsCountBadge")).toHaveText("(0)");
    await expect(page.locator("#wwErRecordingsPanel")).toContainText("No recordings loaded yet. Upload one from Recordings.");
    const sidebarBox = await sidebar.boundingBox();
    const mainBox = await page.locator("#wwErMain").boundingBox();
    expect(sidebarBox.x + sidebarBox.width).toBeLessThanOrEqual(mainBox.x);
    expect(Math.round(sidebarBox.width)).toBe(320);

    // Workspace shell with an honest empty state -- no fake data.
    await expect(page.locator("#wwErCanvas .ww-tg-header-title")).toHaveText("Reconstruction Timeline");
    await expect(page.locator("#wwErCanvasMeta")).toHaveText("No reconstruction records selected");
    await expect(page.locator("#wwErEmptyState")).toBeVisible();
    await expect(page.locator("#wwErPanels .ww-chart")).toHaveCount(0);
    await expect(page.locator("#pageEventReconstruction .ww-time-group-canvas")).toHaveCount(0);

    // Standard interaction controls.
    await expect(page.locator("#wwErDragModeZoomBtn")).toBeVisible();
    await expect(page.locator("#wwErDragModePanBtn")).toBeVisible();
    await expect(page.locator("#wwErDragModeZoomBtn")).toHaveAttribute("aria-label", "Box Zoom");
    await expect(page.locator("#wwErDragModePanBtn")).toHaveAttribute("aria-label", "Pan");
    for (const id of ["#wwErZoomInBtn", "#wwErZoomOutBtn", "#wwErResetViewBtn"]) {
      await expect(page.locator(id)).toBeVisible();
      // No reconstruction canvas exists yet, so these cannot act on anything.
      await expect(page.locator(id)).toBeDisabled();
    }
    await expect(page.locator("#wwErZoomInBtn")).toHaveText("Zoom In");
    await expect(page.locator("#wwErZoomOutBtn")).toHaveText("Zoom Out");
    await expect(page.locator("#wwErResetViewBtn")).toHaveText("Reset Time View");

    // Same toolbar visual language as the Waveform toolbar.
    const toolbarStyles = await page.evaluate(() => {
      const pick = (el) => {
        const style = getComputedStyle(el);
        return {
          backgroundImage: style.backgroundImage,
          borderBottom: style.borderBottom,
          padding: style.padding,
          gap: style.gap,
        };
      };
      return { er: pick(document.getElementById("wwErToolbar")), waveform: pick(document.getElementById("wwToolbar")) };
    });
    expect(toolbarStyles.er).toEqual(toolbarStyles.waveform);

    expect(consoleErrors).toEqual([]);
  });

  test("drag mode is Event Reconstruction state only and never changes Waveform", async ({ page }) => {
    await page.goto("/index.html");
    await page.locator("#mainNavEventReconstructionBtn").click();

    await expect(page.locator("#wwErDragModeZoomBtn")).toHaveAttribute("aria-pressed", "true");
    await page.locator("#wwErDragModePanBtn").click();
    await expect(page.locator("#wwErDragModePanBtn")).toHaveAttribute("aria-pressed", "true");
    await expect(page.locator("#wwErDragModeZoomBtn")).toHaveAttribute("aria-pressed", "false");

    // The Waveform toolbar's own drag mode is untouched.
    await expect(page.locator("#dragModeZoomBtn")).toHaveAttribute("aria-pressed", "true");
    await expect(page.locator("#dragModePanBtn")).toHaveAttribute("aria-pressed", "false");

    await page.locator("#wwErDragModeZoomBtn").click();
    await expect(page.locator("#wwErDragModeZoomBtn")).toHaveAttribute("aria-pressed", "true");
    await expect(page.locator("#wwErDragModePanBtn")).toHaveAttribute("aria-pressed", "false");
  });

  test("lists uploaded recordings read-only and leaves the Waveform workspace intact", async ({ page }) => {
    const consoleErrors = collectConsoleErrors(page);
    await page.goto("/index.html");
    const sourceId = await uploadSynthAscii(page);

    // Open in Waveform and display one channel.
    await page.locator("#recordingsTableBody tr[data-source-id]").first().click();
    const channelRow = page.locator('#channelGroups tr.channel-row--toggle[data-channel-kind="analog"]').first();
    await expect(channelRow).toBeVisible();
    if ((await channelRow.getAttribute("aria-pressed")) !== "true") await channelRow.click();
    await expect(channelRow).toHaveAttribute("aria-pressed", "true");
    const waveformCanvases = page.locator("#wwTimeGroupCanvases .ww-time-group-canvas");
    await expect(waveformCanvases.first()).toBeVisible();
    const canvasCountBefore = await waveformCanvases.count();
    const traceCountBefore = await page.locator("#wwTimeGroupCanvases .ww-chart .scatterlayer .trace").count();
    expect(traceCountBefore).toBeGreaterThan(0);

    // Event Reconstruction lists the recording, read-only.
    await page.locator("#mainNavEventReconstructionBtn").click();
    await expect(page.locator("#wwErRecordingsCountBadge")).toHaveText("(1)");
    const erRow = page.locator(`#wwErRecordingsPanel .ww-er-source-row[data-source-id="${sourceId}"]`);
    await expect(erRow).toBeVisible();
    await expect(erRow.locator(".source-recording-name")).not.toHaveText("");
    await expect(erRow.locator(".source-recording-meta")).toContainText("analog");
    await expect(erRow.locator(".source-recording-time-identity")).not.toHaveText("");
    await expect(page.locator("#wwErRecordingsPanel .channel-row--toggle")).toHaveCount(0);
    await expect(page.locator("#wwErRecordingsPanel .source-recording-sync-badge")).toHaveCount(0);
    await expect(page.locator("#wwErPanels .ww-chart")).toHaveCount(0);

    // Back on Waveform, nothing was rebuilt or lost.
    await page.locator("#mainNavWaveformBtn").click();
    await expect(page.locator("#workspaceRow")).toBeVisible();
    await expect(channelRow).toHaveAttribute("aria-pressed", "true");
    await expect(waveformCanvases).toHaveCount(canvasCountBefore);
    await expect(page.locator("#wwTimeGroupCanvases .ww-chart .scatterlayer .trace")).toHaveCount(traceCountBefore);

    expect(consoleErrors).toEqual([]);
  });

  test("responsive Sources drawer opens the Event Reconstruction panel only", async ({ page }) => {
    await page.setViewportSize({ width: 800, height: 800 });
    await page.goto("/index.html");
    await page.locator("#mainNavEventReconstructionBtn").click();

    const toggle = page.locator("#shellSidebarToggleBtn");
    await expect(toggle).toBeVisible();
    await toggle.click();
    await expect(page.locator("#pageEventReconstruction")).toHaveClass(/shell-sidebar-open/);
    await expect(page.locator("#workspaceRow")).not.toHaveClass(/shell-sidebar-open/);
    await expect(page.locator("#wwErSidebar")).toBeInViewport();

    await page.locator("#wwErSidebarBackdrop").click({ position: { x: 700, y: 400 } });
    await expect(page.locator("#pageEventReconstruction")).not.toHaveClass(/shell-sidebar-open/);

    // The drawer toggle still controls Waveform's own panel there.
    await page.locator("#mainNavWaveformBtn").click();
    await toggle.click();
    await expect(page.locator("#workspaceRow")).toHaveClass(/shell-sidebar-open/);
    await expect(page.locator("#pageEventReconstruction")).not.toHaveClass(/shell-sidebar-open/);
  });
});
