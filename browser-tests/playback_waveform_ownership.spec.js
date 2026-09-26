// Playback Cursor visual ownership (owner UAT, 2026-09-26) -- real-browser
// regression for the "green vertical line on Waveform after visiting
// Analysis first" bug. See DECISIONS.md DEC-085's own "Update
// (2026-09-26)" section.
//
// Rule under test: the shared Playback Controller (`wwPlayback`) is
// cross-Analysis timing infrastructure and keeps its time/state across
// page navigation, but the Playback Cursor VISUALIZATION is Analysis-
// owned -- the Waveform Time Group canvas never renders its dormant
// `.ww-tg-playback-cursor-overlay` (a `--ok` green 2px line). Only
// Waveform-owned Cursor A / Cursor B / Suggested Event markers remain.
//
// Owner reproduction path, per analyzer that mounts the shared Playback
// ribbon today (Phasor, Impedance Locus, Distance Protection, Sequence
// Components -- Overcurrent mounts the same ribbon and is covered by the
// same controller-level fix, see overcurrent_analysis.spec.js):
//   upload -> recording displayed on Waveform -> open the analyzer (it
//   claims/refines the shared playback time) -> navigate to Waveform
//   -> no Playback Cursor overlay, no green vertical line.
//
// "No green line" is asserted two ways, deliberately: (1) DOM state --
// every overlay's own `hidden` property is true (not merely "not visible
// because its page is hidden", which would pass trivially while the
// overlay is still armed to appear); (2) rendered pixels -- a screenshot
// of the Time Group panels is scanned for any column dominated by the
// `--ok` color, with a positive control proving the scan actually
// detects the line when it IS painted.

const { test, expect } = require("@playwright/test");
const path = require("path");
const { reuseOrCreateFullBayContext } = require("./support/engineering_context_helpers");

const FIXTURES = path.join(__dirname, "..", "backend", "tests", "fixtures", "comtrade");
const STEM = "phasor_smoke_three_phase";
const ALPHA_ROLES = [["VA", "A"], ["VB", "B"], ["VC", "C"], ["IA", "A"], ["IB", "B"], ["IC", "C"]];

const ANALYZERS = [
  { name: "Phasor", tabBtn: "#wwAnalysisTypePhasorBtn", select: "#wwPhasorContextSelect", mount: "#wwPhasorPlaybackMount" },
  { name: "Impedance Locus", tabBtn: "#wwAnalysisTypeImpedanceBtn", select: "#wwImpedanceContextSelect", mount: "#wwImpedancePlaybackMount" },
  { name: "Distance Protection", tabBtn: "#wwAnalysisTypeDistanceBtn", select: "#wwDistanceContextSelect", mount: "#wwDistancePlaybackMount" },
  { name: "Sequence Components", tabBtn: "#wwAnalysisTypeSequenceBtn", select: "#wwSequenceContextSelect", mount: "#wwSequencePlaybackMount" },
];

async function uploadFixture(page) {
  await page.goto("/index.html");
  await page.locator("#recordingsUploadBtn, #recordingsEmptyUploadBtn").first().click();
  await expect(page.locator("#uploadModalOverlay")).toBeVisible();
  await page.locator("#uploadModalFile_0").setInputFiles(path.join(FIXTURES, `${STEM}.cfg`));
  await page.locator("#uploadModalFile_1").setInputFiles(path.join(FIXTURES, `${STEM}.dat`));
  await page.locator("#uploadModalSubmitBtn").click();
  await page.locator("#uploadModalOverlay").waitFor({ state: "hidden" });
}

// Upload, open the recording on Waveform and display its first analog
// channel (a displayed source is what forms the Time Group an analyzer
// claims), and make sure the DEC-104 full-bay context exists.
async function setupDisplayedRecording(page) {
  await uploadFixture(page);
  const row = page.locator("#recordingsTableBody tr[data-source-id]").last();
  await expect(row).toBeVisible();
  const sourceId = await row.getAttribute("data-source-id");
  const workspaceId = await page.evaluate(() => localStorage.getItem("powerwave.workspaceId"));
  const context = await reuseOrCreateFullBayContext(page, workspaceId, sourceId, "ALPHA1", ALPHA_ROLES, "Alpha 1");

  await row.click();
  await expect(page.locator("#wwWorkspaceLoading")).toBeHidden();
  const channelRow = page.locator('#channelGroups tr.channel-row--toggle[data-channel-kind="analog"]').first();
  await expect(channelRow).toBeVisible();
  await channelRow.click();
  await expect(channelRow).toHaveAttribute("aria-pressed", "true");
  const canvas = page.locator("#wwTimeGroupCanvases .ww-time-group-canvas").first();
  await expect(canvas).toBeVisible();
  await expect(canvas.locator(".ww-chart .plotly").first()).toBeVisible();
  return { canvas, sourceId, contextId: context.id };
}

// Opens `analyzer` and waits until it has claimed the shared playback
// clock for this context's Time Group (the claim is what used to arm the
// Waveform overlay).
async function openAnalyzerAndClaimTime(page, analyzer, contextId) {
  await page.locator("#mainNavAnalysisBtn").click();
  await expect(page.locator("#pageAnalysis")).toBeVisible();
  await page.locator(analyzer.tabBtn).click();
  await expect(page.locator(analyzer.tabBtn)).toHaveClass(/active/);
  const select = page.locator(analyzer.select);
  await expect(page.locator(`${analyzer.select} option[value="${contextId}"]`)).toHaveCount(1);
  if ((await select.inputValue()) !== contextId) await select.selectOption(contextId);
  await expect(page.locator(`${analyzer.mount} .ww-tg-playback-play-btn`)).toBeVisible();
  await expect.poll(() => page.evaluate(() => {
    const s = wwPlaybackState();
    return s.activeTimeGroupId !== null && Number.isFinite(s.currentTime);
  })).toBe(true);
}

// Every Waveform Playback Cursor overlay must be DOM-hidden -- not just
// invisible because its page happens to be hidden.
async function expectNoArmedPlaybackOverlay(page) {
  const states = await page.evaluate(() =>
    Array.from(document.querySelectorAll(".ww-tg-playback-cursor-overlay")).map((el) => el.hidden)
  );
  expect(states.length).toBeGreaterThan(0);
  for (const hidden of states) expect(hidden).toBe(true);
  await expect(page.locator(".ww-tg-playback-cursor-overlay:visible")).toHaveCount(0);
}

// Pixel scan: fraction of the tallest single screenshot column whose
// pixels match the `--ok` (Playback Cursor) color. A 2px vertical line
// spanning the panels scores ~1.0; waveform traces (never a vertical run
// of one color) score far below the threshold.
async function maxGreenColumnRatio(page, canvas, testInfo, label) {
  const png = await canvas.locator(".ww-tg-panels").screenshot();
  if (testInfo) await testInfo.attach(label, { body: png, contentType: "image/png" });
  return page.evaluate(async (b64) => {
    const probe = document.createElement("div");
    probe.style.color = "var(--ok)";
    document.body.appendChild(probe);
    const [r, g, b] = getComputedStyle(probe).color.match(/\d+/g).map(Number);
    probe.remove();
    const img = new Image();
    img.src = "data:image/png;base64," + b64;
    await img.decode();
    const c = document.createElement("canvas");
    c.width = img.width;
    c.height = img.height;
    const ctx = c.getContext("2d");
    ctx.drawImage(img, 0, 0);
    const data = ctx.getImageData(0, 0, c.width, c.height).data;
    const TOL = 28;
    let best = 0;
    for (let x = 0; x < c.width; x++) {
      let hits = 0;
      for (let y = 0; y < c.height; y++) {
        const i = (y * c.width + x) * 4;
        if (Math.abs(data[i] - r) <= TOL && Math.abs(data[i + 1] - g) <= TOL && Math.abs(data[i + 2] - b) <= TOL) hits++;
      }
      best = Math.max(best, hits / c.height);
    }
    return best;
  }, png.toString("base64"));
}

const GREEN_LINE_THRESHOLD = 0.5;

test.describe("Playback Cursor is Analysis-owned -- never rendered on Waveform", () => {
  for (const analyzer of ANALYZERS) {
    test(`${analyzer.name} first -> Waveform shows no green Playback Cursor`, async ({ page }, testInfo) => {
      const { canvas, contextId } = await setupDisplayedRecording(page);
      await openAnalyzerAndClaimTime(page, analyzer, contextId);
      const claimedTime = await page.evaluate(() => wwPlaybackState().currentTime);

      // Analysis -> Waveform (the owner's exact reproduction step).
      await page.locator("#mainNavWaveformBtn").click();
      await expect(page.locator("#workspaceRow")).toBeVisible();
      await expect(canvas).toBeVisible();
      // Give the page-entry resize/overlay resync hooks time to run.
      await page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))));
      await page.waitForTimeout(250);

      await expectNoArmedPlaybackOverlay(page);
      expect(await maxGreenColumnRatio(page, canvas, testInfo, `${analyzer.name} -> Waveform`)).toBeLessThan(GREEN_LINE_THRESHOLD);

      // Shared timing is untouched by the visual-ownership rule.
      const after = await page.evaluate(() => wwPlaybackState());
      expect(after.activeTimeGroupId).not.toBeNull();
      expect(after.currentTime).toBeCloseTo(claimedTime, 6);
    });
  }

  test("pixel scan positive control: a painted Playback Cursor line IS detected", async ({ page }) => {
    // Proves the green-line scan above is sensitive -- without this, a
    // broken detector would pass the no-line assertions vacuously.
    const { canvas } = await setupDisplayedRecording(page);
    await canvas.evaluate((canvasEl) => {
      const overlay = canvasEl.querySelector(".ww-tg-playback-cursor-overlay");
      const line = overlay.querySelector(".ww-tg-playback-cursor-line");
      const panels = canvasEl.querySelector(".ww-tg-panels");
      const ruler = canvasEl.querySelector(".ww-tg-ruler");
      overlay.style.top = panels.offsetTop + "px";
      overlay.style.height = Math.max(0, ruler.offsetTop - panels.offsetTop) + "px";
      line.style.left = Math.round(panels.getBoundingClientRect().width / 2) + "px";
      overlay.hidden = false;
    });
    expect(await maxGreenColumnRatio(page, canvas, null, "")).toBeGreaterThanOrEqual(GREEN_LINE_THRESHOLD);
  });

  test("Playing in Analysis then returning to Waveform: no cursor, clock still advancing", async ({ page }, testInfo) => {
    const { canvas, contextId } = await setupDisplayedRecording(page);
    await openAnalyzerAndClaimTime(page, ANALYZERS[0], contextId);
    const mount = page.locator("#wwPhasorPlaybackMount");
    await page.locator("#wwPhasorPlaybackMount .ww-tg-playback-speed-select").selectOption("0.25");
    await mount.locator(".ww-tg-playback-play-btn").click();
    await expect(mount.locator(".ww-tg-playback-play-btn")).toHaveText("Pause");

    await page.locator("#mainNavWaveformBtn").click();
    await expect(canvas).toBeVisible();
    const t1 = await page.evaluate(() => wwPlaybackState().currentTime);
    await page.waitForTimeout(300);
    const t2 = await page.evaluate(() => wwPlaybackState().currentTime);
    // Playback keeps running (shared clock, rAF chain intact) ...
    expect(await page.evaluate(() => wwPlaybackState().state)).toBe("playing");
    expect(t2).toBeGreaterThan(t1);
    // ... but its per-tick rendering never paints the Waveform overlay.
    await expectNoArmedPlaybackOverlay(page);
    expect(await maxGreenColumnRatio(page, canvas, testInfo, "Phasor playing -> Waveform")).toBeLessThan(GREEN_LINE_THRESHOLD);

    // Back on Analysis the ribbon still reflects the advanced time.
    await page.locator("#mainNavAnalysisBtn").click();
    await mount.locator(".ww-tg-playback-play-btn").click(); // Pause
    await expect(mount.locator(".ww-tg-playback-play-btn")).toHaveText("Play");
    const frozen = await page.evaluate(() => wwPlaybackState().currentTime);
    expect(frozen).toBeGreaterThan(t1);
  });

  test("Navigation lifecycle: no armed overlay across Waveform/Analysis/Recordings/Compliance/analyzer switches", async ({ page }) => {
    const { canvas, contextId } = await setupDisplayedRecording(page);
    // Waveform -> Analysis (Phasor claims time)
    await openAnalyzerAndClaimTime(page, ANALYZERS[0], contextId);
    await expectNoArmedPlaybackOverlay(page);
    // Analyzer -> different analyzer
    await openAnalyzerAndClaimTime(page, ANALYZERS[1], contextId);
    await expectNoArmedPlaybackOverlay(page);
    // Analysis -> Recordings
    await page.locator("#mainNavRecordingsBtn").click();
    await expect(page.locator("#pageRecordings")).toBeVisible();
    await expectNoArmedPlaybackOverlay(page);
    // Recordings -> Analysis -> Compliance
    await page.locator("#mainNavAnalysisBtn").click();
    await expect(page.locator("#pageAnalysis")).toBeVisible();
    await page.locator("#mainNavComplianceBtn").click();
    await expect(page.locator("#pageCompliance")).toBeVisible();
    await expectNoArmedPlaybackOverlay(page);
    // Compliance -> Waveform
    await page.locator("#mainNavWaveformBtn").click();
    await expect(canvas).toBeVisible();
    await expectNoArmedPlaybackOverlay(page);
  });

  test("Cursor A/B still work on Waveform after Analysis claimed playback time", async ({ page }) => {
    const { canvas, contextId } = await setupDisplayedRecording(page);
    await openAnalyzerAndClaimTime(page, ANALYZERS[0], contextId);
    await page.locator("#mainNavWaveformBtn").click();
    await expect(canvas).toBeVisible();

    const cursorBtn = canvas.locator(".ww-tg-cursor-mode-btn");
    await cursorBtn.click();
    await expect(cursorBtn).toHaveAttribute("aria-pressed", "true");
    await expect(canvas.locator(".ww-tg-cursor-overlay")).toBeVisible();
    // `.ww-cursor-line` itself is a zero-width positioning box; the
    // rendered line is its 1px `.ww-cursor-stroke`.
    await expect(canvas.locator(".ww-cursor-line--a .ww-cursor-stroke")).toBeVisible();
    await expect(canvas.locator(".ww-cursor-line--b .ww-cursor-stroke")).toBeVisible();
    await expect(canvas.locator(".ww-tg-cursor-readout")).toBeVisible();
    // Cursor A/B coexist with (and are independent of) the dormant
    // Playback overlay, which stays hidden.
    await expectNoArmedPlaybackOverlay(page);
  });
});
