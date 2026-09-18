// Impedance Locus v1 -- the THIRD Analysis-menu analyzer -- real-browser
// coverage. Closes the "no real-browser Playwright coverage" gap the
// Impedance Locus v1 slice itself explicitly flagged (see
// docs/project-memory/IMPEDANCE_LOCUS_ANALYSIS.md's own "Known
// limitations" section) and adds regression coverage for the two UAT
// bugs this same task fixes:
//
//   1. Related Waveforms rendered blank axes with no Va/Ia trace in
//      Recording mode (root cause: the pushed role objects never
//      carried `channelRef`, so the shared panel had no channel
//      identity to fetch -- see `wwImpedanceComputeActiveRelatedWaveformRoles()`
//      and `app.domain.impedance.ImpedanceAnalysisResult`'s own
//      `voltage_channel_ref`/`current_channel_ref` fields).
//   2. The full impedance locus was visible immediately, even before
//      Playback had progressed -- fixed by chronologically clipping the
//      drawn locus PATH to `wwImpedanceVisibleLocusCutoffTime()` while
//      the full locus stays cached/computed upfront for performance.
//
// Reuses the SAME `phasor_smoke_three_phase` fixture (3 Voltage + 3
// Current channels, 50 Hz, balanced 100 V RMS / 40 A RMS three-phase
// sinusoid, 2 s duration) every other Analysis Playwright suite already
// uses, and the same direct-backend-API Engineering Context seeding
// pattern (no context-creation UI exists yet).

const { test, expect } = require("@playwright/test");
const path = require("path");

const FIXTURES = path.join(__dirname, "..", "backend", "tests", "fixtures", "comtrade");
const BACKEND_URL = `http://127.0.0.1:${process.env.PW_BACKEND_PORT || "8000"}`;
const STEM = "phasor_smoke_three_phase";

async function uploadFixture(page) {
  await page.goto("/index.html");
  await page.locator("#recordingsUploadBtn, #recordingsEmptyUploadBtn").first().click();
  await expect(page.locator("#uploadModalOverlay")).toBeVisible();
  await page.locator("#uploadModalFile_0").setInputFiles(path.join(FIXTURES, `${STEM}.cfg`));
  await page.locator("#uploadModalFile_1").setInputFiles(path.join(FIXTURES, `${STEM}.dat`));
  await page.locator("#uploadModalSubmitBtn").click();
  await page.locator("#uploadModalOverlay").waitFor({ state: "hidden" });
}

async function createFullBayContext(page, workspaceId, sourceId, displayName) {
  const members = [
    ["ALPHA1_VA", "A"], ["ALPHA1_VB", "B"], ["ALPHA1_VC", "C"],
    ["ALPHA1_IA", "A"], ["ALPHA1_IB", "B"], ["ALPHA1_IC", "C"],
  ].map(([channel_name, phase]) => ({
    channel_ref: { kind: "source", source_id: sourceId, channel_name },
    phase, phase_source: "engineer_confirmed",
  }));
  const response = await page.request.post(
    `${BACKEND_URL}/api/v1/workspaces/${encodeURIComponent(workspaceId)}/engineering-contexts`,
    { data: { display_name: displayName, status: "manual", members } }
  );
  expect(response.ok()).toBeTruthy();
  return response.json();
}

async function uploadAndCreateContext(page) {
  await uploadFixture(page);
  const row = page.locator("#recordingsTableBody tr[data-source-id]").last();
  await expect(row).toBeVisible();
  const sourceId = await row.getAttribute("data-source-id");
  const workspaceId = await page.evaluate(() => localStorage.getItem("powerwave.workspaceId"));
  const context = await createFullBayContext(page, workspaceId, sourceId, "Alpha 1");
  return { workspaceId, sourceId, contextId: context.id };
}

async function openAnalysisImpedance(page) {
  await page.locator("#mainNavAnalysisBtn").click();
  await expect(page.locator("#pageAnalysis")).toBeVisible();
  await page.locator("#wwAnalysisTypeImpedanceBtn").click();
  await expect(page.locator("#wwAnalysisTypeImpedanceBtn")).toHaveClass(/active/);
  await expect(page.locator("#wwImpedancePanel")).toBeVisible();
  await expect(page.locator("#wwPhasorPanel")).toBeHidden();
  await expect(page.locator("#wwOvercurrentPanel")).toBeHidden();
}

// Root cause of a real intermittent failure (see docs/project-memory/
// DECISIONS.md's own hardening-pass entry): selecting a context
// synchronously dispatches BOTH the current-point fetch AND the locus
// fetch (`wwImpedanceLoadForSelectedContext()` -> `wwImpedanceRequestExactPlaybackFetch()`
// + `wwImpedanceMaybeFetchLocus()`, in that order, same call stack) --
// the ORIGINAL helper only ever waited for the current-point result
// text, then a SEPARATE caller-side `waitForLocusCached()` re-POLLED
// `wwImpedanceState.locusPoints` against its own independent, tighter-
// than-this-project's-own-configured-default `{timeout: 5000}` window
// (this suite's own `playwright.config.js` already sets `expect.timeout:
// 10_000`). Under real (not pathological) backend latency during a
// long combined multi-spec run, the 120-point `/impedance-locus`
// round trip can occasionally still be in flight when that independent
// 5s window expires -- the test was observing state BEFORE the real
// network response had a chance to land, never a production ordering
// defect (the fetch's own request-generation/epoch/workspace guards
// were independently code-reviewed and are already correct -- see
// `wwImpedanceMaybeFetchLocus()`'s own comment). Fix: arm a REAL
// `page.waitForResponse()` for the actual `/impedance-locus` HTTP
// round trip BEFORE the triggering `selectOption()` action (the
// deterministic condition the task itself asks for -- "relevant API
// response completed" -- never a value-polling loop racing an
// independently-chosen timeout), so `waitForLocusCached()` below is
// left as a fast, near-instant synchronous-render-catch-up check only.
async function selectContextAndWaitForResult(page, contextId) {
  await expect(page.locator(`#wwImpedanceContextSelect option[value="${contextId}"]`)).toHaveCount(1);
  const locusResponse = page.waitForResponse((r) => r.url().includes("/impedance-locus"), { timeout: 15000 });
  await page.locator("#wwImpedanceContextSelect").selectOption(contextId);
  await expect(async () => {
    const text = await page.locator("#wwImpedanceValuesList").innerText();
    expect(text).toContain("Phase impedance");
  }).toPass({ timeout: 10000 });
  await locusResponse;
}

async function waitForLocusCached(page, { minPoints = 20 } = {}) {
  // By the time selectContextAndWaitForResult() returns, the real
  // `/impedance-locus` HTTP response has already completed (armed and
  // awaited there) -- this is now just the synchronous render/state-
  // commit that follows it settling, never a real network wait.
  await expect(async () => {
    const count = await page.evaluate(() =>
      wwImpedanceState.locusPoints.filter((p) => p.status === "computed").length
    );
    expect(count).toBeGreaterThanOrEqual(minPoints);
  }).toPass({ timeout: 2000 });
}

async function locusPathSegmentCount(page) {
  return page.evaluate(() => {
    const el = document.querySelector("#wwImpedanceSvg path.ww-imp-locus-path");
    if (!el) return 0;
    const d = el.getAttribute("d") || "";
    return (d.match(/M /g) || []).length + (d.match(/L /g) || []).length;
  });
}

async function cachedComputedLocusCount(page) {
  return page.evaluate(() => wwImpedanceState.locusPoints.filter((p) => p.status === "computed").length);
}

async function seekTo(slider, value) {
  await slider.evaluate((el, v) => {
    el.value = String(v);
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
  }, value);
}

async function seekSliderBounds(slider) {
  return slider.evaluate((el) => ({ min: parseFloat(el.min), max: parseFloat(el.max) }));
}

test.describe("Impedance Locus v1 -- Related Waveforms", () => {
  test("Recording mode, Phase A: Va and Ia traces render before pressing Play", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisImpedance(page);
    await selectContextAndWaitForResult(page, contextId);

    await expect(page.locator("#wwAnalysisTypeImpedanceBtn")).toHaveClass(/active/); // still on Impedance -- Play never clicked

    await expect(async () => {
      const info = await page.evaluate(() => {
        const v = document.getElementById("wwAnalysisRelatedWaveformsVoltageChart");
        const c = document.getElementById("wwAnalysisRelatedWaveformsCurrentChart");
        return {
          vNames: v && v.data ? v.data.map((t) => t.name) : [],
          vLen: v && v.data && v.data[0] ? v.data[0].x.length : 0,
          cNames: c && c.data ? c.data.map((t) => t.name) : [],
          cLen: c && c.data && c.data[0] ? c.data[0].x.length : 0,
        };
      });
      expect(info.vNames).toEqual(["Va"]);
      expect(info.vLen).toBeGreaterThan(1);
      expect(info.cNames).toEqual(["Ia"]);
      expect(info.cLen).toBeGreaterThan(1);
    }).toPass({ timeout: 5000 });

    // Groups must actually be visible (non-empty data alone is not
    // sufficient proof of a rendered trace -- the group container
    // itself must not be hidden).
    await expect(page.locator("#wwAnalysisRelatedWaveformsVoltageGroup")).toBeVisible();
    await expect(page.locator("#wwAnalysisRelatedWaveformsCurrentGroup")).toBeVisible();
    await expect(page.locator("#wwAnalysisRelatedWaveformsEmptyState")).toBeHidden();
  });

  test("switching Phase A -> Phase B updates the waveform traces from Va/Ia to Vb/Ib", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisImpedance(page);
    await selectContextAndWaitForResult(page, contextId);
    await expect(async () => {
      const names = await page.evaluate(() => document.getElementById("wwAnalysisRelatedWaveformsCurrentChart").data.map((t) => t.name));
      expect(names).toEqual(["Ia"]);
    }).toPass({ timeout: 5000 });

    await page.locator("#wwImpedancePhaseSelect").selectOption("B");

    await expect(async () => {
      const names = await page.evaluate(() => ({
        v: document.getElementById("wwAnalysisRelatedWaveformsVoltageChart").data.map((t) => t.name),
        c: document.getElementById("wwAnalysisRelatedWaveformsCurrentChart").data.map((t) => t.name),
      }));
      expect(names.v).toEqual(["Vb"]);
      expect(names.c).toEqual(["Ib"]);
    }).toPass({ timeout: 5000 });
  });

  test("responsive: waveform traces and cursor remain visible at 1366px and 1024px", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    for (const width of [1366, 1024]) {
      await page.setViewportSize({ width, height: 800 });
      await openAnalysisImpedance(page);
      await selectContextAndWaitForResult(page, contextId);
      await expect(async () => {
        const info = await page.evaluate(() => {
          const v = document.getElementById("wwAnalysisRelatedWaveformsVoltageChart");
          return { vLen: v && v.data && v.data[0] ? v.data[0].x.length : 0 };
        });
        expect(info.vLen).toBeGreaterThan(1);
      }).toPass({ timeout: 5000 });
      await expect(page.locator("#wwAnalysisRelatedWaveformsVoltageGroup")).toBeVisible();
    }
  });
});

test.describe("Impedance Locus v1 -- chronological locus reveal", () => {
  test("initial state: current point visible, full future locus not visible", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisImpedance(page);
    await selectContextAndWaitForResult(page, contextId);
    await waitForLocusCached(page);

    const cached = await cachedComputedLocusCount(page);
    const drawn = await locusPathSegmentCount(page);
    // The full locus is cached internally (proves "compute/cache
    // upfront" is preserved)...
    expect(cached).toBeGreaterThanOrEqual(20);
    // ...but only a small leading portion (near the start of the
    // recording) is actually drawn.
    expect(drawn).toBeLessThan(cached * 0.25);

    // The current marker itself must still be present.
    await expect(page.locator("#wwImpedanceSvg circle.ww-imp-point")).toHaveCount(1);
  });

  test("Play advances the marker and grows the visible trail; Pause stops it", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisImpedance(page);
    await selectContextAndWaitForResult(page, contextId);
    await waitForLocusCached(page);

    const before = await locusPathSegmentCount(page);
    const markerBefore = await page.evaluate(() => {
      const el = document.querySelector("#wwImpedanceSvg circle.ww-imp-point");
      return el ? { cx: el.getAttribute("cx"), cy: el.getAttribute("cy") } : null;
    });

    const playBtn = page.locator("#wwImpedancePlaybackMount .ww-tg-playback-play-btn");
    await playBtn.click();
    await expect(playBtn).toHaveText("Pause");
    await page.waitForTimeout(700);
    await playBtn.click(); // pause

    const afterPlay = await locusPathSegmentCount(page);
    expect(afterPlay).toBeGreaterThan(before);

    // Pause: the trail must stop growing (a brief settle window is
    // allowed for the in-flight exact-fetch, then it must be stable).
    await page.waitForTimeout(300);
    const settled = await locusPathSegmentCount(page);
    await page.waitForTimeout(500);
    const stillSettled = await locusPathSegmentCount(page);
    expect(stillSettled).toBe(settled);

    const markerAfter = await page.evaluate(() => {
      const el = document.querySelector("#wwImpedanceSvg circle.ww-imp-point");
      return el ? { cx: el.getAttribute("cx"), cy: el.getAttribute("cy") } : null;
    });
    expect(markerAfter).not.toBeNull();
    expect(markerBefore).not.toBeNull();
  });

  test("Seek forward immediately expands the trail to the sought position", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisImpedance(page);
    await selectContextAndWaitForResult(page, contextId);
    await waitForLocusCached(page);
    const cached = await cachedComputedLocusCount(page);

    const slider = page.locator("#wwImpedancePlaybackMount .ww-tg-playback-seek-slider");
    const { min, max } = await seekSliderBounds(slider);
    const target = min + (max - min) * 0.6;
    await seekTo(slider, target);

    await expect(async () => {
      const currentTime = await page.evaluate(() => wwPlaybackState().currentTime);
      expect(Math.abs(currentTime - target)).toBeLessThan(0.02);
    }).toPass({ timeout: 5000 });

    await expect(async () => {
      const drawn = await locusPathSegmentCount(page);
      // Roughly 60% of the way through the recording -> roughly 60%
      // of the cached locus should now be drawn (generous tolerance:
      // structural growth, not an exact per-sample match).
      expect(drawn).toBeGreaterThan(cached * 0.35);
      expect(drawn).toBeLessThan(cached * 0.85);
    }).toPass({ timeout: 5000 });
  });

  test("Restart collapses the trail back to the start portion", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisImpedance(page);
    await selectContextAndWaitForResult(page, contextId);
    await waitForLocusCached(page);
    const cached = await cachedComputedLocusCount(page);

    const slider = page.locator("#wwImpedancePlaybackMount .ww-tg-playback-seek-slider");
    const { min, max } = await seekSliderBounds(slider);
    await seekTo(slider, min + (max - min) * 0.8);
    await expect(async () => {
      const drawn = await locusPathSegmentCount(page);
      expect(drawn).toBeGreaterThan(cached * 0.5);
    }).toPass({ timeout: 5000 });

    await page.locator("#wwImpedancePlaybackMount .ww-tg-playback-restart-btn").click();

    await expect(async () => {
      const drawn = await locusPathSegmentCount(page);
      expect(drawn).toBeLessThan(cached * 0.25);
    }).toPass({ timeout: 5000 });

    // The cached locus itself must survive Restart unchanged (never
    // discarded/refetched merely because Playback restarted).
    const cachedAfter = await cachedComputedLocusCount(page);
    expect(cachedAfter).toBe(cached);
  });

  test("At the end of the event, the entire cached locus becomes visible", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisImpedance(page);
    await selectContextAndWaitForResult(page, contextId);
    await waitForLocusCached(page);
    const cached = await cachedComputedLocusCount(page);

    const slider = page.locator("#wwImpedancePlaybackMount .ww-tg-playback-seek-slider");
    const { max } = await seekSliderBounds(slider);
    await seekTo(slider, max);

    await expect(async () => {
      const drawn = await locusPathSegmentCount(page);
      expect(drawn).toBeGreaterThanOrEqual(cached * 0.9);
    }).toPass({ timeout: 5000 });
  });

  test("no full-locus or waveform refetch occurs during Playback ticks", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisImpedance(page);
    await selectContextAndWaitForResult(page, contextId);
    await waitForLocusCached(page);

    const locusUrls = [];
    const waveformUrls = [];
    page.on("request", (req) => {
      if (req.url().includes("/impedance-locus")) locusUrls.push(req.url());
      if (req.url().includes("/waveform")) waveformUrls.push(req.url());
    });

    const playBtn = page.locator("#wwImpedancePlaybackMount .ww-tg-playback-play-btn");
    await playBtn.click();
    await page.waitForTimeout(1000);
    await playBtn.click(); // pause

    expect(locusUrls).toHaveLength(0);
    expect(waveformUrls).toHaveLength(0);
  });
});

test.describe("Impedance Locus v1 -- Manual mode unaffected", () => {
  test("Manual mode shows no Related Waveforms and no progressive trail", async ({ page }) => {
    await page.goto("/index.html");
    await openAnalysisImpedance(page);

    await expect(page.locator("#wwImpedanceInputSourceManualBtn")).toBeVisible();
    await page.locator("#wwImpedanceInputSourceManualBtn").click();
    await expect(page.locator("#wwImpedanceRecordingSection")).toBeHidden();
    await expect(page.locator("#wwImpedanceManualInputSection")).toBeVisible();

    await expect(async () => {
      const text = await page.locator("#wwImpedanceValuesList").innerText();
      expect(text).toContain("Phase impedance");
    }).toPass({ timeout: 5000 });

    // No locus path is ever drawn in Manual mode -- one point only.
    await expect(page.locator("#wwImpedanceSvg path.ww-imp-locus-path")).toHaveCount(0);
    await expect(page.locator("#wwImpedanceSvg circle.ww-imp-point--manual")).toHaveCount(1);
  });
});
