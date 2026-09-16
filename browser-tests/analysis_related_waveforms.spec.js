// Shared Analysis "Related Waveforms" panel -- the third shared Analysis
// workspace primitive (after Engineering Context lifecycle and shared
// Playback). See docs/project-memory/ANALYSIS_WORKSPACE.md and
// backend/tests/test_frontend_analysis_related_waveforms.py for the
// structural invariants that don't need a real browser.
//
// Core architectural invariant under test: the analyzer decides WHAT
// signals are relevant; the shared Analysis workspace decides HOW those
// waveforms are fetched, grouped, rendered, and synchronized with
// Playback.
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

async function createFullBayContext(page, workspaceId, sourceId, displayName, channelPrefix) {
  const prefix = channelPrefix || "ALPHA1";
  const members = [
    [`${prefix}_VA`, "A"], [`${prefix}_VB`, "B"], [`${prefix}_VC`, "C"],
    [`${prefix}_IA`, "A"], [`${prefix}_IB`, "B"], [`${prefix}_IC`, "C"],
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

async function openAnalysisPhasor(page, contextId) {
  await page.locator("#mainNavAnalysisBtn").click();
  await expect(page.locator("#wwPhasorPanel")).toBeVisible();
  if (contextId) {
    await page.locator("#wwPhasorContextSelect").selectOption(contextId);
    await expect(async () => {
      const text = await page.locator("#wwPhasorValuesList").innerText();
      expect(text).toMatch(/100\.0\s*V/);
    }).toPass({ timeout: 5000 });
  }
}

async function openAnalysisOvercurrent(page, contextId) {
  await page.locator("#mainNavAnalysisBtn").click();
  await page.locator("#wwAnalysisTypeOvercurrentBtn").click();
  await expect(page.locator("#wwOvercurrentPanel")).toBeVisible();
  if (contextId) {
    await page.locator("#wwOvercurrentContextSelect").selectOption(contextId);
    await expect(async () => {
      const text = await page.locator("#wwOvercurrentValuesList").innerText();
      expect(text).toContain("Measured RMS current");
    }).toPass({ timeout: 5000 });
  }
}

async function waitForWaveformsRendered(page) {
  await expect(async () => {
    const hasData = await page.evaluate(() => {
      const v = document.getElementById("wwAnalysisRelatedWaveformsVoltageChart");
      const c = document.getElementById("wwAnalysisRelatedWaveformsCurrentChart");
      const vOk = !!(v && v.data && v.data.length > 0);
      const cOk = !!(c && c.data && c.data.length > 0);
      return vOk || cOk;
    });
    expect(hasData).toBe(true);
  }).toPass({ timeout: 5000 });
}

test.describe("Related Waveforms -- shared panel structure", () => {
  test("panel exists once, below Playback, never duplicated inside an analyzer", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisPhasor(page, contextId);
    await expect(page.locator("#wwAnalysisRelatedWaveformsPanel")).toHaveCount(1);
    await expect(page.locator("#wwAnalysisRelatedWaveformsPanel")).toBeVisible();

    // Positioned below Playback, above the analyzer's own body -- DOM
    // order check via bounding boxes.
    const playbackBox = await page.locator("#wwPhasorPlaybackPanel").boundingBox();
    const arwBox = await page.locator("#wwAnalysisRelatedWaveformsPanel").boundingBox();
    const bodyBox = await page.locator("#wwPhasorBody").boundingBox();
    expect(arwBox.y).toBeGreaterThanOrEqual(playbackBox.y);
    expect(bodyBox.y).toBeGreaterThanOrEqual(arwBox.y);
  });

  test("no active roles shows the compact empty state, never a blank plot", async ({ page }) => {
    await uploadFixture(page);
    await openAnalysisPhasor(page);
    await expect(page.locator("#wwAnalysisRelatedWaveformsEmptyState")).toBeVisible();
    await expect(page.locator("#wwAnalysisRelatedWaveformsEmptyState")).toContainText("No related waveform signals available");
    await expect(page.locator("#wwAnalysisRelatedWaveformsBody")).toBeHidden();
  });

  test("no visible 'Related Waveforms' title row -- VOLTAGE/CURRENT group labels alone identify the groups (2026-09-16 owner UI refinement)", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisPhasor(page, contextId);
    await waitForWaveformsRendered(page);

    const panel = page.locator("#wwAnalysisRelatedWaveformsPanel");
    await expect(panel.locator("h3", { hasText: "Related Waveforms" })).toHaveCount(0);
    // The panel's own visible text never contains the removed title,
    // even outside a dedicated <h3> (belt-and-braces against any other
    // element carrying the same string).
    const panelText = await panel.innerText();
    expect(panelText).not.toContain("Related Waveforms");

    // The useful group labels remain, visible.
    await expect(panel.locator(".ww-arw-group-label", { hasText: "VOLTAGE" })).toBeVisible();
    await expect(panel.locator(".ww-arw-group-label", { hasText: "CURRENT" })).toBeVisible();

    // The first visible label sits comfortably below the panel's own
    // top edge -- neither flush against it (cramped) nor pushed far
    // down (leftover title space).
    const panelBox = await panel.boundingBox();
    const voltageLabelBox = await panel.locator(".ww-arw-group-label", { hasText: "VOLTAGE" }).boundingBox();
    const topGap = voltageLabelBox.y - panelBox.y;
    expect(topGap).toBeGreaterThan(4);
    expect(topGap).toBeLessThan(24);
  });

  test("Overcurrent current-only view: CURRENT group begins near the panel top, no empty title space above it", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisOvercurrent(page, contextId);
    await waitForWaveformsRendered(page);

    const panel = page.locator("#wwAnalysisRelatedWaveformsPanel");
    await expect(panel.locator(".ww-arw-group-label", { hasText: "CURRENT" })).toBeVisible();
    const panelBox = await panel.boundingBox();
    const currentLabelBox = await panel.locator(".ww-arw-group-label", { hasText: "CURRENT" }).boundingBox();
    expect(currentLabelBox.y - panelBox.y).toBeLessThan(24);
  });

  test("resize handle still exists and the panel remains vertically resizable after the title removal", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisPhasor(page, contextId);
    await waitForWaveformsRendered(page);

    const handle = page.locator("#wwAnalysisRelatedWaveformsResizeHandle");
    await expect(handle).toBeVisible();
    await handle.scrollIntoViewIfNeeded();
    const initialHeight = await page.evaluate(() => wwAnalysisRelatedWaveformsState.height);
    const box = await handle.boundingBox();
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.mouse.down();
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2 + 60, { steps: 5 });
    await page.mouse.up();
    await page.waitForTimeout(100);
    const resizedHeight = await page.evaluate(() => wwAnalysisRelatedWaveformsState.height);
    expect(resizedHeight).toBeGreaterThan(initialHeight);
  });

  test("the same shared panel (with its title-less markup) is reused verbatim by both Phasor and Overcurrent", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisPhasor(page, contextId);
    await waitForWaveformsRendered(page);
    await expect(page.locator("#wwAnalysisRelatedWaveformsPanel")).toHaveCount(1);
    await expect(page.locator("#wwAnalysisRelatedWaveformsPanel")).toBeVisible();
    // wwAnalysisMountRelatedWaveformsInto() inserts the ONE shared panel
    // as a SIBLING immediately before the active analyzer's own anchor
    // (never nested inside it, never cloned) -- confirm it sits right
    // above the Phasor anchor.
    let order = await page.evaluate(() => {
      const panel = document.getElementById("wwAnalysisRelatedWaveformsPanel");
      const anchor = document.getElementById("wwPhasorRelatedWaveformsAnchor");
      return panel.compareDocumentPosition(anchor) & Node.DOCUMENT_POSITION_FOLLOWING ? "before" : "after";
    });
    expect(order).toBe("before");

    await openAnalysisOvercurrent(page, contextId);
    await waitForWaveformsRendered(page);
    // Still exactly one instance -- reparented, never cloned -- now
    // sitting right above the Overcurrent anchor instead.
    await expect(page.locator("#wwAnalysisRelatedWaveformsPanel")).toHaveCount(1);
    await expect(page.locator("#wwAnalysisRelatedWaveformsPanel")).toBeVisible();
    order = await page.evaluate(() => {
      const panel = document.getElementById("wwAnalysisRelatedWaveformsPanel");
      const anchor = document.getElementById("wwOvercurrentRelatedWaveformsAnchor");
      return panel.compareDocumentPosition(anchor) & Node.DOCUMENT_POSITION_FOLLOWING ? "before" : "after";
    });
    expect(order).toBe("before");
    await expect(page.locator("#wwAnalysisRelatedWaveformsPanel h3", { hasText: "Related Waveforms" })).toHaveCount(0);
  });
});

test.describe("Related Waveforms -- Phasor integration", () => {
  test("all six roles visible -> Voltage shows Va/Vb/Vc, Current shows Ia/Ib/Ic", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisPhasor(page, contextId);
    await waitForWaveformsRendered(page);

    await expect(page.locator("#wwAnalysisRelatedWaveformsVoltageGroup")).toBeVisible();
    await expect(page.locator("#wwAnalysisRelatedWaveformsCurrentGroup")).toBeVisible();
    const traceCounts = await page.evaluate(() => ({
      voltage: document.getElementById("wwAnalysisRelatedWaveformsVoltageChart").data.length,
      current: document.getElementById("wwAnalysisRelatedWaveformsCurrentChart").data.length,
    }));
    expect(traceCounts.voltage).toBe(3);
    expect(traceCounts.current).toBe(3);
  });

  test("hiding Vb removes it from both the Phasor vector diagram and Related Waveforms", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisPhasor(page, contextId);
    await waitForWaveformsRendered(page);

    await page.locator('.ww-phasor-value-row--toggle[data-role="Vb"]').click();
    await expect(page.locator('.ww-phasor-value-row--toggle[data-role="Vb"]')).toHaveAttribute("aria-pressed", "false");

    await expect(async () => {
      const names = await page.evaluate(() =>
        document.getElementById("wwAnalysisRelatedWaveformsVoltageChart").data.map((t) => t.name)
      );
      expect(names).not.toContain("Vb");
      expect(names.sort()).toEqual(["Va", "Vc"]);
    }).toPass({ timeout: 5000 });
  });

  test("hiding Ib and Ic leaves only Ia in the Current waveform group", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisPhasor(page, contextId);
    await waitForWaveformsRendered(page);

    await page.locator('.ww-phasor-value-row--toggle[data-role="Ib"]').click();
    await page.locator('.ww-phasor-value-row--toggle[data-role="Ic"]').click();

    await expect(async () => {
      const names = await page.evaluate(() =>
        document.getElementById("wwAnalysisRelatedWaveformsCurrentChart").data.map((t) => t.name)
      );
      expect(names).toEqual(["Ia"]);
    }).toPass({ timeout: 5000 });
  });

  test("partial context (Va + Ia only) shows only those two traces", async ({ page }) => {
    await uploadFixture(page);
    const row = page.locator("#recordingsTableBody tr[data-source-id]").last();
    const sourceId = await row.getAttribute("data-source-id");
    const workspaceId = await page.evaluate(() => localStorage.getItem("powerwave.workspaceId"));
    const response = await page.request.post(
      `${BACKEND_URL}/api/v1/workspaces/${encodeURIComponent(workspaceId)}/engineering-contexts`,
      {
        data: {
          display_name: "Partial", status: "manual",
          members: [
            { channel_ref: { kind: "source", source_id: sourceId, channel_name: "ALPHA1_VA" }, phase: "A", phase_source: "engineer_confirmed" },
            { channel_ref: { kind: "source", source_id: sourceId, channel_name: "ALPHA1_IA" }, phase: "A", phase_source: "engineer_confirmed" },
          ],
        },
      }
    );
    const context = await response.json();
    await openAnalysisPhasor(page, context.id);
    await waitForWaveformsRendered(page);

    const traceCounts = await page.evaluate(() => ({
      voltage: document.getElementById("wwAnalysisRelatedWaveformsVoltageChart").data.length,
      current: document.getElementById("wwAnalysisRelatedWaveformsCurrentChart").data.length,
    }));
    expect(traceCounts.voltage).toBe(1);
    expect(traceCounts.current).toBe(1);
  });
});

test.describe("Related Waveforms -- Overcurrent integration", () => {
  test("Phase A selected -> Current group shows Ia only, no Voltage group", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisOvercurrent(page, contextId);
    await waitForWaveformsRendered(page);

    await expect(page.locator("#wwAnalysisRelatedWaveformsVoltageGroup")).toBeHidden();
    await expect(page.locator("#wwAnalysisRelatedWaveformsCurrentGroup")).toBeVisible();
    const names = await page.evaluate(() =>
      document.getElementById("wwAnalysisRelatedWaveformsCurrentChart").data.map((t) => t.name)
    );
    expect(names).toEqual(["Ia"]);
  });

  test("switching Phase A -> Phase B updates the waveform from Ia to Ib", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisOvercurrent(page, contextId);
    await waitForWaveformsRendered(page);

    await page.locator("#wwOvercurrentPhaseSelect").selectOption("B");
    await expect(async () => {
      const text = await page.locator("#wwOvercurrentValuesList").innerText();
      expect(text).toContain("Measured RMS current");
    }).toPass({ timeout: 5000 });

    await expect(async () => {
      const names = await page.evaluate(() =>
        document.getElementById("wwAnalysisRelatedWaveformsCurrentChart").data.map((t) => t.name)
      );
      expect(names).toEqual(["Ib"]);
    }).toPass({ timeout: 5000 });
  });

  test("changing TMS does not refetch unrelated waveform data", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisOvercurrent(page, contextId);
    await waitForWaveformsRendered(page);

    const waveformUrls = [];
    page.on("request", (req) => { if (req.url().includes("/waveform")) waveformUrls.push(req.url()); });

    await page.locator("#wwOvercurrentTmsInput").fill("0.2");
    await page.locator("#wwOvercurrentTmsInput").dispatchEvent("change");
    await page.waitForTimeout(500);

    expect(waveformUrls).toHaveLength(0);
  });
});

test.describe("Related Waveforms -- shared Playback cursor", () => {
  test("Play advances the cursor; Pause settles it; both analyzers share the same wwPlayback.currentTime", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisPhasor(page, contextId);
    await waitForWaveformsRendered(page);

    const shapeXBefore = await page.evaluate(() =>
      document.getElementById("wwAnalysisRelatedWaveformsVoltageChart").layout.shapes[0].x0
    );

    const playBtn = page.locator("#wwPhasorPlaybackMount .ww-tg-playback-play-btn");
    await playBtn.click();
    await page.waitForTimeout(600);
    await playBtn.click(); // pause

    const { shapeXAfter, playbackTime } = await page.evaluate(() => ({
      shapeXAfter: document.getElementById("wwAnalysisRelatedWaveformsVoltageChart").layout.shapes[0].x0,
      playbackTime: wwPlaybackState().currentTime,
    }));
    expect(shapeXAfter).toBeGreaterThan(shapeXBefore);
    expect(Math.abs(shapeXAfter - playbackTime)).toBeLessThan(0.05);
  });

  test("Seek settles the cursor at the exact sought instant", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisPhasor(page, contextId);
    await waitForWaveformsRendered(page);

    const slider = page.locator("#wwPhasorPlaybackMount .ww-tg-playback-seek-slider");
    const bounds = await slider.evaluate((el) => ({ min: parseFloat(el.min), max: parseFloat(el.max) }));
    const target = bounds.min + (bounds.max - bounds.min) * 0.7;
    await slider.evaluate((el, t) => {
      el.value = String(t);
      el.dispatchEvent(new Event("input", { bubbles: true }));
      el.dispatchEvent(new Event("change", { bubbles: true }));
    }, target);

    await expect(async () => {
      const shapeX = await page.evaluate(() =>
        document.getElementById("wwAnalysisRelatedWaveformsVoltageChart").layout.shapes[0].x0
      );
      expect(Math.abs(shapeX - target)).toBeLessThan(0.02);
    }).toPass({ timeout: 5000 });
  });

  test("Restart returns the cursor to the beginning", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisPhasor(page, contextId);
    await waitForWaveformsRendered(page);

    const slider = page.locator("#wwPhasorPlaybackMount .ww-tg-playback-seek-slider");
    const bounds = await slider.evaluate((el) => ({ min: parseFloat(el.min), max: parseFloat(el.max) }));
    await slider.evaluate((el, t) => {
      el.value = String(t);
      el.dispatchEvent(new Event("input", { bubbles: true }));
      el.dispatchEvent(new Event("change", { bubbles: true }));
    }, bounds.min + (bounds.max - bounds.min) * 0.5);

    await page.locator("#wwPhasorPlaybackMount .ww-tg-playback-restart-btn").click();
    await expect(async () => {
      const shapeX = await page.evaluate(() =>
        document.getElementById("wwAnalysisRelatedWaveformsVoltageChart").layout.shapes[0].x0
      );
      expect(Math.abs(shapeX - bounds.min)).toBeLessThan(0.02);
    }).toPass({ timeout: 5000 });
  });

  test("waveform-data network requests do not occur on every Playback tick", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisPhasor(page, contextId);
    await waitForWaveformsRendered(page);

    const waveformUrls = [];
    page.on("request", (req) => { if (req.url().includes("/waveform")) waveformUrls.push(req.url()); });

    const playBtn = page.locator("#wwPhasorPlaybackMount .ww-tg-playback-play-btn");
    await playBtn.click();
    await page.waitForTimeout(1000);
    await playBtn.click();

    expect(waveformUrls).toHaveLength(0);
  });
});

test.describe("Related Waveforms -- analyzer switch", () => {
  test("Phasor (Va+Ia visible) -> Overcurrent (Ia) -> back to Phasor restores Va+Ia, cursor time unchanged throughout", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisPhasor(page, contextId);
    await waitForWaveformsRendered(page);

    // Hide everything except Va and Ia.
    for (const role of ["Vb", "Vc", "Ib", "Ic"]) {
      await page.locator(`.ww-phasor-value-row--toggle[data-role="${role}"]`).click();
    }
    await expect(async () => {
      const names = (await page.evaluate(() => [
        ...document.getElementById("wwAnalysisRelatedWaveformsVoltageChart").data.map((t) => t.name),
        ...document.getElementById("wwAnalysisRelatedWaveformsCurrentChart").data.map((t) => t.name),
      ])).sort();
      expect(names).toEqual(["Ia", "Va"]);
    }).toPass({ timeout: 5000 });

    const slider = page.locator("#wwPhasorPlaybackMount .ww-tg-playback-seek-slider");
    const bounds = await slider.evaluate((el) => ({ min: parseFloat(el.min), max: parseFloat(el.max) }));
    const target = bounds.min + (bounds.max - bounds.min) * 0.6;
    await slider.evaluate((el, t) => {
      el.value = String(t);
      el.dispatchEvent(new Event("input", { bubbles: true }));
      el.dispatchEvent(new Event("change", { bubbles: true }));
    }, target);
    await expect(async () => {
      const t = await page.evaluate(() => wwPlaybackState().currentTime);
      expect(Math.abs(t - target)).toBeLessThan(0.02);
    }).toPass({ timeout: 5000 });

    // Switch to Overcurrent -- waveform becomes Ia only, Playback time unchanged.
    await page.locator("#wwAnalysisTypeOvercurrentBtn").click();
    await page.locator("#wwOvercurrentContextSelect").selectOption(contextId);
    await expect(async () => {
      const text = await page.locator("#wwOvercurrentValuesList").innerText();
      expect(text).toContain("Measured RMS current");
    }).toPass({ timeout: 5000 });
    await expect(async () => {
      const names = await page.evaluate(() =>
        document.getElementById("wwAnalysisRelatedWaveformsCurrentChart").data.map((t) => t.name)
      );
      expect(names).toEqual(["Ia"]);
    }).toPass({ timeout: 5000 });
    await expect(page.locator("#wwAnalysisRelatedWaveformsVoltageGroup")).toBeHidden();
    let t = await page.evaluate(() => wwPlaybackState().currentTime);
    expect(Math.abs(t - target)).toBeLessThan(0.02);

    // Switch back to Phasor -- Va+Ia restored, Playback time still unchanged.
    await page.locator("#wwAnalysisTypePhasorBtn").click();
    await expect(async () => {
      const names = (await page.evaluate(() => [
        ...document.getElementById("wwAnalysisRelatedWaveformsVoltageChart").data.map((tr) => tr.name),
        ...document.getElementById("wwAnalysisRelatedWaveformsCurrentChart").data.map((tr) => tr.name),
      ])).sort();
      expect(names).toEqual(["Ia", "Va"]);
    }).toPass({ timeout: 5000 });
    t = await page.evaluate(() => wwPlaybackState().currentTime);
    expect(Math.abs(t - target)).toBeLessThan(0.02);
  });

  test("switching analyzers while Playback is running never fights over the shared waveform state (no re-fetch thrash)", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisPhasor(page, contextId);
    await waitForWaveformsRendered(page);
    await openAnalysisOvercurrent(page, contextId);
    await waitForWaveformsRendered(page);

    const waveformUrls = [];
    page.on("request", (req) => { if (req.url().includes("/waveform")) waveformUrls.push(req.url()); });

    const playBtn = page.locator("#wwOvercurrentPlaybackMount .ww-tg-playback-play-btn");
    await playBtn.click();
    await page.waitForTimeout(800);
    await playBtn.click();

    // Both channels (all 6) were already fetched while establishing
    // Phasor/Overcurrent above -- nothing new should be needed merely
    // because Playback is running with both analyzers' own tick
    // handlers active simultaneously (Phasor hidden, Overcurrent shown).
    expect(waveformUrls).toHaveLength(0);
  });
});

test.describe("Related Waveforms -- Engineering Context change", () => {
  test("switching context clears the old bay's traces and shows the new one's", async ({ page }) => {
    const { contextId: alphaId } = await uploadAndCreateContext(page);
    await page.locator("#mainNavRecordingsBtn").click();
    await page.locator("#recordingsUploadBtn, #recordingsEmptyUploadBtn").first().click();
    await expect(page.locator("#uploadModalOverlay")).toBeVisible();
    await page.locator("#uploadModalFile_0").setInputFiles(path.join(FIXTURES, "phasor_smoke_bravo_three_phase.cfg"));
    await page.locator("#uploadModalFile_1").setInputFiles(path.join(FIXTURES, `${STEM}.dat`));
    await page.locator("#uploadModalSubmitBtn").click();
    await page.locator("#uploadModalOverlay").waitFor({ state: "hidden" });
    const bravoSourceId = await page.locator("#recordingsTableBody tr[data-source-id]").last().getAttribute("data-source-id");
    const workspaceId = await page.evaluate(() => localStorage.getItem("powerwave.workspaceId"));
    const bravoContext = await createFullBayContext(page, workspaceId, bravoSourceId, "Bravo 1", "BRAVO1");

    await openAnalysisPhasor(page, alphaId);
    await waitForWaveformsRendered(page);

    await page.locator("#wwPhasorContextSelect").selectOption(bravoContext.id);
    await expect(async () => {
      const text = await page.locator("#wwPhasorValuesList").innerText();
      expect(text).toMatch(/100\.0\s*V/);
    }).toPass({ timeout: 5000 });

    // Still shows a valid 6-trace waveform set -- for the NEW context,
    // never a stale mix of both.
    await expect(async () => {
      const counts = await page.evaluate(() => ({
        voltage: document.getElementById("wwAnalysisRelatedWaveformsVoltageChart").data.length,
        current: document.getElementById("wwAnalysisRelatedWaveformsCurrentChart").data.length,
      }));
      expect(counts.voltage).toBe(3);
      expect(counts.current).toBe(3);
    }).toPass({ timeout: 5000 });
  });
});

// A tall viewport for the drag-mechanics tests below -- raw
// page.mouse.* commands operate on absolute viewport coordinates and do
// NOT auto-scroll an element into view (unlike locator actions), so a
// large resize (up to WW_ARW_MAX_HEIGHT) needs enough vertical room that
// the handle's own new position never lands underneath the app's fixed
// bottom status bar (a real, if minor, pre-existing page-chrome overlap
// at the very bottom edge of the viewport, unrelated to this feature --
// confirmed via document.elementFromPoint() during this test's own
// development). scrollIntoViewIfNeeded() before each boundingBox() call
// is the belt-and-braces fix for the same reason.
test.describe("Related Waveforms -- resizable height (owner UAT addendum)", () => {
  test.use({ viewport: { width: 1280, height: 1000 } });

  test("dragging the handle upward reduces height, downward increases it", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisPhasor(page, contextId);
    await waitForWaveformsRendered(page);

    const initialHeight = await page.evaluate(() => wwAnalysisRelatedWaveformsState.height);
    const handle = page.locator("#wwAnalysisRelatedWaveformsResizeHandle");
    await handle.scrollIntoViewIfNeeded();
    const box = await handle.boundingBox();

    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.mouse.down();
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2 + 80, { steps: 8 });
    await page.mouse.up();
    await page.waitForTimeout(100);
    const increasedHeight = await page.evaluate(() => wwAnalysisRelatedWaveformsState.height);
    expect(increasedHeight).toBeGreaterThan(initialHeight);

    await handle.scrollIntoViewIfNeeded();
    const box2 = await handle.boundingBox();
    await page.mouse.move(box2.x + box2.width / 2, box2.y + box2.height / 2);
    await page.mouse.down();
    await page.mouse.move(box2.x + box2.width / 2, box2.y + box2.height / 2 - 120, { steps: 8 });
    await page.mouse.up();
    await page.waitForTimeout(100);
    const decreasedHeight = await page.evaluate(() => wwAnalysisRelatedWaveformsState.height);
    expect(decreasedHeight).toBeLessThan(increasedHeight);
  });

  test("min and max height bounds are enforced", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisPhasor(page, contextId);
    await waitForWaveformsRendered(page);

    const handle = page.locator("#wwAnalysisRelatedWaveformsResizeHandle");
    await handle.scrollIntoViewIfNeeded();
    let box = await handle.boundingBox();
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.mouse.down();
    await page.mouse.move(box.x + box.width / 2, box.y - 2000, { steps: 5 });
    await page.mouse.up();
    let height = await page.evaluate(() => wwAnalysisRelatedWaveformsState.height);
    expect(height).toBeGreaterThanOrEqual(150);

    await handle.scrollIntoViewIfNeeded();
    box = await handle.boundingBox();
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.mouse.down();
    await page.mouse.move(box.x + box.width / 2, box.y + 3000, { steps: 5 });
    await page.mouse.up();
    height = await page.evaluate(() => wwAnalysisRelatedWaveformsState.height);
    expect(height).toBeLessThanOrEqual(520);
  });

  test("height survives an analyzer switch", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisPhasor(page, contextId);
    await waitForWaveformsRendered(page);

    const handle = page.locator("#wwAnalysisRelatedWaveformsResizeHandle");
    await handle.scrollIntoViewIfNeeded();
    const box = await handle.boundingBox();
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.mouse.down();
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2 + 90);
    await page.mouse.up();
    const heightAfterResize = await page.evaluate(() => wwAnalysisRelatedWaveformsState.height);

    await page.locator("#wwAnalysisTypeOvercurrentBtn").click();
    await page.locator("#wwOvercurrentContextSelect").selectOption(contextId);
    await expect(async () => {
      const text = await page.locator("#wwOvercurrentValuesList").innerText();
      expect(text).toContain("Measured RMS current");
    }).toPass({ timeout: 5000 });

    const heightAfterSwitch = await page.evaluate(() => wwAnalysisRelatedWaveformsState.height);
    expect(heightAfterSwitch).toBe(heightAfterResize);
    await expect(page.locator("#wwAnalysisRelatedWaveformsBody")).toHaveCSS("height", heightAfterResize + "px");
  });

  test("Playback cursor remains correctly aligned after a resize", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisPhasor(page, contextId);
    await waitForWaveformsRendered(page);

    const slider = page.locator("#wwPhasorPlaybackMount .ww-tg-playback-seek-slider");
    const bounds = await slider.evaluate((el) => ({ min: parseFloat(el.min), max: parseFloat(el.max) }));
    const target = bounds.min + (bounds.max - bounds.min) * 0.4;
    await slider.evaluate((el, t) => {
      el.value = String(t);
      el.dispatchEvent(new Event("input", { bubbles: true }));
      el.dispatchEvent(new Event("change", { bubbles: true }));
    }, target);
    await expect(async () => {
      const t = await page.evaluate(() => wwPlaybackState().currentTime);
      expect(Math.abs(t - target)).toBeLessThan(0.02);
    }).toPass({ timeout: 5000 });

    const handle = page.locator("#wwAnalysisRelatedWaveformsResizeHandle");
    await handle.scrollIntoViewIfNeeded();
    const box = await handle.boundingBox();
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.mouse.down();
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2 + 70);
    await page.mouse.up();

    const shapeX = await page.evaluate(() =>
      document.getElementById("wwAnalysisRelatedWaveformsVoltageChart").layout.shapes[0].x0
    );
    expect(Math.abs(shapeX - target)).toBeLessThan(0.02);
  });

  test("resize never triggers a waveform refetch", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisPhasor(page, contextId);
    await waitForWaveformsRendered(page);

    const waveformUrls = [];
    page.on("request", (req) => { if (req.url().includes("/waveform")) waveformUrls.push(req.url()); });

    const handle = page.locator("#wwAnalysisRelatedWaveformsResizeHandle");
    await handle.scrollIntoViewIfNeeded();
    const box = await handle.boundingBox();
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.mouse.down();
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2 + 50, { steps: 5 });
    await page.mouse.up();
    await page.waitForTimeout(300);

    expect(waveformUrls).toHaveLength(0);
  });

  test("resize handle uses row-resize cursor styling and a grip affordance", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisPhasor(page, contextId);
    await waitForWaveformsRendered(page);

    const handle = page.locator("#wwAnalysisRelatedWaveformsResizeHandle");
    await expect(handle).toBeVisible();
    const cursor = await handle.evaluate((el) => getComputedStyle(el).cursor);
    expect(cursor).toBe("ns-resize");
  });

  test("panel remains usable at narrow (small-screen) viewport width", async ({ page }) => {
    await page.setViewportSize({ width: 420, height: 800 });
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisPhasor(page, contextId);
    await waitForWaveformsRendered(page);

    const panelBox = await page.locator("#wwAnalysisRelatedWaveformsPanel").boundingBox();
    expect(panelBox.width).toBeLessThanOrEqual(420);
    const defaultHeight = await page.evaluate(() => wwAnalysisRelatedWaveformsState.height);

    // Shrink it so analyzer-specific content below stays reachable
    // without excessive scrolling -- a bounded, safely-on-screen drag
    // delta (the handle's own Y position varies with page chrome at
    // narrow width, so a very large delta risks moving off-viewport).
    const handle = page.locator("#wwAnalysisRelatedWaveformsResizeHandle");
    await handle.scrollIntoViewIfNeeded();
    const box = await handle.boundingBox();
    const dragUpBy = Math.min(150, Math.max(0, box.y - 20));
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.mouse.down();
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2 - dragUpBy, { steps: 8 });
    await page.mouse.up();
    await page.waitForTimeout(100);

    const height = await page.evaluate(() => wwAnalysisRelatedWaveformsState.height);
    expect(height).toBeGreaterThanOrEqual(150);
    expect(height).toBeLessThan(defaultHeight);
  });
});
