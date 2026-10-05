// UAT fix (owner-reported): the Analyser's "No recording loaded. Manual
// mode is available." hint was shown whenever an analyzer had zero
// Engineering Contexts -- including after a genuinely successful upload
// whose channel names simply did not match any detectable three-phase
// bay pattern. Investigation found the underlying RECORDING-MODE
// AVAILABILITY gate (wwPhasorState.contexts.length > 0, etc.) was never
// wrong -- a context-less source truly has nothing Recording mode could
// compute, a deliberate, pre-existing design choice (see
// wwOvercurrentUpdateInputSourceAvailability()'s own comment). The real
// bug was the HINT TEXT always claiming "no recording" regardless of
// whether one actually existed. Fix: a new wwAnalysisHasAnyRecording()
// resolver (reusing #wwRecordingsCountBadge, the same signal Waveform's
// own wwUpdateEmptyState() already treats as authoritative) drives the
// hint's own text, so it only ever claims "no recording" when that is
// literally true.

const { test, expect } = require("@playwright/test");
const { uploadRecord } = require("./support/event_reconstruction_helpers");

const VI_CHANNELS = [
  { name: "VA", unit: "V", phase: "A", amplitude: 100, frequencyHz: 50 },
  { name: "VB", unit: "V", phase: "B", amplitude: 100, frequencyHz: 50 },
  { name: "VC", unit: "V", phase: "C", amplitude: 100, frequencyHz: 50 },
  { name: "IA", unit: "A", phase: "A", amplitude: 5, frequencyHz: 50 },
  { name: "IB", unit: "A", phase: "B", amplitude: 5, frequencyHz: 50 },
  { name: "IC", unit: "A", phase: "C", amplitude: 5, frequencyHz: 50 },
];

// Deliberately generic names a bay-detection heuristic cannot match --
// confirms the "uploaded but no Engineering Context" branch, distinct
// from "nothing uploaded at all."
const GENERIC_CHANNELS = [
  { name: "CH1", unit: "V", amplitude: 100, frequencyHz: 50 },
  { name: "CH2", unit: "V", amplitude: 100, frequencyHz: 50 },
  { name: "CH3", unit: "V", amplitude: 100, frequencyHz: 50 },
];

// Resolves once no /api/v1 request has been in flight for `quietMs`.
// Every analyzer auto-selects a context and computes in the background, so
// removing a source while one of those requests is still out can make it
// 404 on arrival (the same class of race as DEC-099's Playback case) --
// something this file's console-error check must not conflate with the
// recording-state behaviour under test.
function trackApiRequests(page) {
  let pending = 0;
  const isApi = (request) => request.url().includes("/api/v1/");
  page.on("request", (request) => { if (isApi(request)) pending += 1; });
  page.on("requestfinished", (request) => { if (isApi(request)) pending -= 1; });
  page.on("requestfailed", (request) => { if (isApi(request)) pending -= 1; });
  return async function waitForApiIdle(quietMs = 800, timeoutMs = 30000) {
    const start = Date.now();
    let quietSince = null;
    while (Date.now() - start < timeoutMs) {
      if (pending <= 0) {
        quietSince = quietSince === null ? Date.now() : quietSince;
        if (Date.now() - quietSince >= quietMs) return;
      } else {
        quietSince = null;
      }
      await page.waitForTimeout(100);
    }
    throw new Error("API requests did not settle");
  };
}

function phasorHint(page) {
  return page.locator("#wwPhasorInputSourceHint");
}

// The hint element is `hidden` in the static markup, so toBeHidden() alone
// passes before any context has loaded. "Recording detected" therefore means
// the shared context list has been published and auto-selected.
async function expectRecordingReady(page) {
  await expect(page.locator("#wwPhasorContextSelect")).not.toHaveValue("", { timeout: 15000 });
  await expect(phasorHint(page)).toBeHidden();
}

async function openAnalysis(page) {
  await page.locator("#mainNavAnalysisBtn").click();
  await expect(page.locator("#pageAnalysis")).toBeVisible();
}

test.describe("Analyser recording detection", () => {
  test("1. Upload recording -> navigate to Analyser -> recording detected (hint hidden, Recording mode enabled)", async ({ page }) => {
    await page.goto("/index.html");
    await uploadRecord(page, { station: "STN_A", startClock: "10:00:00.000000", durationS: 1, channels: VI_CHANNELS });
    await openAnalysis(page);
    await expectRecordingReady(page);
    await expect(page.locator("#wwPhasorInputSourceRecordingBtn")).toBeEnabled();
  });

  test("2. Existing loaded recording -> Analyser does not show the no-recording notice, even when no Engineering Context was detected", async ({ page }) => {
    await page.goto("/index.html");
    await uploadRecord(page, { station: "STN_GENERIC", startClock: "10:00:00.000000", durationS: 1, channels: GENERIC_CHANNELS });
    await openAnalysis(page);
    await expect(phasorHint(page)).toBeVisible({ timeout: 10000 });
    // The notice is shown (Recording mode genuinely has nothing to
    // select), but it must NEVER claim no recording was loaded -- a
    // recording clearly was.
    await expect(phasorHint(page)).not.toContainText("No recording loaded");
    await expect(phasorHint(page)).toContainText("No Engineering Context could be detected");
    // The recording itself is still visible in the sidebar -- state is
    // consistent, not lost.
    await expect(page.locator("#recordingsTableBody tr[data-source-id]")).toHaveCount(1);
  });

  test("3. No recording at all -> the true manual-mode notice still appears, verbatim", async ({ page }) => {
    await page.goto("/index.html");
    await openAnalysis(page);
    await expect(phasorHint(page)).toBeVisible();
    await expect(phasorHint(page)).toHaveText("No recording loaded. Manual mode is available.");
    await expect(page.locator("#wwPhasorInputSourceRecordingBtn")).toBeDisabled();
  });

  test("4. Switching from Waveform/Event Reconstruction to Analyser preserves recording context", async ({ page }) => {
    await page.goto("/index.html");
    await uploadRecord(page, { station: "STN_B", startClock: "10:00:00.000000", durationS: 1, channels: VI_CHANNELS });
    const sourceId = await page.locator("#recordingsTableBody tr[data-source-id]").first().getAttribute("data-source-id");
    await page.locator(`#recordingsTableBody tr[data-source-id="${sourceId}"]`).click();
    await expect(page.locator("#workspaceRow")).toBeVisible();

    await page.locator("#mainNavEventReconstructionBtn").click();
    await expect(page.locator("#pageEventReconstruction")).toBeVisible();

    await openAnalysis(page);
    await expectRecordingReady(page);
    const options = await page.locator("#wwPhasorContextSelect option").allTextContents();
    expect(options.length).toBeGreaterThan(1); // placeholder + at least one real bay
  });

  test("5. Clearing/removing the recording returns Analyser to manual mode with the true no-recording notice", async ({ page }) => {
    await page.goto("/index.html");
    await uploadRecord(page, { station: "STN_C", startClock: "10:00:00.000000", durationS: 1, channels: VI_CHANNELS });
    await openAnalysis(page);
    await expectRecordingReady(page);

    await page.locator("#mainNavRecordingsBtn").click();
    await page.locator('button[data-action="remove"]').first().click();
    await expect(page.locator("#confirmOverlay")).toBeVisible();
    await page.locator("#confirmRemoveBtn").click();
    await expect(page.locator("#confirmOverlay")).toBeHidden();
    await expect(page.locator("#recordingsTableBody tr[data-source-id]")).toHaveCount(0);

    await openAnalysis(page);
    await expect(phasorHint(page)).toBeVisible({ timeout: 10000 });
    await expect(phasorHint(page)).toHaveText("No recording loaded. Manual mode is available.");
  });

  test("6. Multiple recordings do not cause stale/incorrect active-recording state", async ({ page }) => {
    await page.goto("/index.html");
    // First recording: generic names, no detectable context.
    await uploadRecord(page, { station: "STN_D1", startClock: "10:00:00.000000", durationS: 1, channels: GENERIC_CHANNELS });
    await openAnalysis(page);
    await expect(phasorHint(page)).toBeVisible({ timeout: 10000 });
    await expect(phasorHint(page)).not.toContainText("No recording loaded");

    // Second recording, same workspace, proper phase-named channels --
    // the hint must update to reflect the NOW-available context, never
    // stay stuck on the first recording's own stale state.
    await page.locator("#mainNavRecordingsBtn").click();
    await uploadRecord(page, { station: "STN_D2", startClock: "10:00:00.000000", durationS: 1, channels: VI_CHANNELS });
    await openAnalysis(page);
    await expectRecordingReady(page);
    await expect(page.locator("#recordingsTableBody tr[data-source-id]")).toHaveCount(2);
  });

  test("7. No console errors across upload, navigation, removal and re-navigation", async ({ page }) => {
    const consoleErrors = [];
    page.on("console", (msg) => { if (msg.type() === "error") consoleErrors.push(msg.text()); });
    page.on("pageerror", (err) => consoleErrors.push(`pageerror: ${err.message}`));
    const waitForApiIdle = trackApiRequests(page);

    await page.goto("/index.html");
    await uploadRecord(page, { station: "STN_E", startClock: "10:00:00.000000", durationS: 1, channels: VI_CHANNELS });
    await openAnalysis(page);
    await expectRecordingReady(page);

    await page.locator("#mainNavWaveformBtn").click();
    await openAnalysis(page);
    // Let every simultaneously-auto-selected analyzer's own background
    // computation settle before removing the source (see
    // trackApiRequests()).
    await waitForApiIdle();

    await page.locator("#mainNavRecordingsBtn").click();
    await page.locator('button[data-action="remove"]').first().click();
    await page.locator("#confirmRemoveBtn").click();
    await expect(page.locator("#recordingsTableBody tr[data-source-id]")).toHaveCount(0);

    await openAnalysis(page);
    await expect(phasorHint(page)).toHaveText("No recording loaded. Manual mode is available.");

    expect(consoleErrors).toEqual([]);
  });
});
