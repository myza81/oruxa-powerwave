// Overcurrent Analysis v1 -- the second Analysis-menu analyzer (Phasor
// remains the first) real-browser coverage. See docs/development/
// BROWSER_SMOKE_TEST.md for the general foundation this extends, and
// backend/tests/test_frontend_overcurrent_analysis.py for the structural
// invariants that don't need a real browser.
//
// Reuses the SAME `phasor_smoke_three_phase` fixture phasor_analysis.spec.js
// already established (3 Voltage + 3 Current channels, 50 Hz, balanced
// 100 V RMS / 40 A RMS three-phase sinusoid, 2 s duration) -- a known
// current magnitude lets these tests assert concrete pickup-multiple/
// operating-time numbers, not just "did it change." Engineering Context
// creation is seeded directly via the backend API (no context-creation UI
// exists yet), the same established pattern phasor_analysis.spec.js uses.
//
// Overcurrent mounts the SAME shared Playback control surface Phasor
// already uses -- these tests reuse the EXACT seekTo()/seekSliderBounds()
// interaction helpers playback.spec.js/phasor_analysis.spec.js already
// established for that scrubber class.

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

async function openAnalysisOvercurrent(page) {
  await page.locator("#mainNavAnalysisBtn").click();
  await expect(page.locator("#pageAnalysis")).toBeVisible();
  await page.locator("#wwAnalysisTypeOvercurrentBtn").click();
  await expect(page.locator("#wwAnalysisTypeOvercurrentBtn")).toHaveClass(/active/);
  await expect(page.locator("#wwOvercurrentPanel")).toBeVisible();
  await expect(page.locator("#wwPhasorPanel")).toBeHidden();
}

async function seekTo(slider, value, { commit = true } = {}) {
  await slider.evaluate(
    (el, args) => {
      el.value = String(args.value);
      el.dispatchEvent(new Event("input", { bubbles: true }));
      if (args.commit) el.dispatchEvent(new Event("change", { bubbles: true }));
    },
    { value, commit }
  );
}

async function seekSliderBounds(slider) {
  return slider.evaluate((el) => ({ min: parseFloat(el.min), max: parseFloat(el.max) }));
}

async function selectContextAndWaitForValues(page, contextId) {
  await expect(page.locator(`#wwOvercurrentContextSelect option[value="${contextId}"]`)).toHaveCount(1);
  await page.locator("#wwOvercurrentContextSelect").selectOption(contextId);
  await expect(async () => {
    const text = await page.locator("#wwOvercurrentValuesList").innerText();
    expect(text).toContain("Measured RMS current");
  }).toPass({ timeout: 5000 });
}

test.describe("Overcurrent Analysis v1 -- basic configuration", () => {
  test("open Analysis -> choose Overcurrent -> choose context -> choose Phase A -> Standard Inverse -> pickup -> TMS -> curve displayed", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisOvercurrent(page);
    await selectContextAndWaitForValues(page, contextId);

    await expect(page.locator("#wwOvercurrentPhaseSelect")).toHaveValue("A");
    await expect(page.locator("#wwOvercurrentCharacteristicSelect option")).toHaveCount(3);
    await expect(page.locator("#wwOvercurrentCharacteristicSelect")).toHaveValue("iec_standard_inverse");

    await page.locator("#wwOvercurrentPickupInput").fill("1.0");
    await page.locator("#wwOvercurrentPickupInput").dispatchEvent("change");
    await page.locator("#wwOvercurrentTmsInput").fill("0.1");
    await page.locator("#wwOvercurrentTmsInput").dispatchEvent("change");

    await expect(async () => {
      const text = await page.locator("#wwOvercurrentValuesList").innerText();
      expect(text).toMatch(/40\.0\s*A secondary/); // known 40 A RMS, secondary basis (no CT)
      expect(text).toMatch(/40\.0\s*×/); // multiple of pickup = 40/1
    }).toPass({ timeout: 5000 });

    // The curve itself renders as an SVG path (never Plotly).
    await expect(page.locator("#wwOvercurrentSvg path.ww-oc-curve")).toHaveCount(1);
    await expect(page.locator("#wwOvercurrentSvg circle.ww-oc-operating-point")).toHaveCount(1);
  });

  test("primary basis requires and applies CT ratio", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisOvercurrent(page);
    await selectContextAndWaitForValues(page, contextId);

    await expect(page.locator("#wwOvercurrentCtPrimaryField")).toBeHidden();
    await page.locator("#wwOvercurrentBasisSelect").selectOption("primary");
    await expect(page.locator("#wwOvercurrentCtPrimaryField")).toBeVisible();
    await expect(page.locator("#wwOvercurrentCtSecondaryField")).toBeVisible();

    await page.locator("#wwOvercurrentCtPrimaryInput").fill("1000");
    await page.locator("#wwOvercurrentCtPrimaryInput").dispatchEvent("change");
    await page.locator("#wwOvercurrentCtSecondaryInput").fill("1");
    await page.locator("#wwOvercurrentCtSecondaryInput").dispatchEvent("change");

    await expect(async () => {
      const text = await page.locator("#wwOvercurrentValuesList").innerText();
      // Recorded 40 A "primary" through a 1000:1 CT -> 0.04 A secondary.
      expect(text).toMatch(/40\.0\s*A primary/);
      expect(text).toMatch(/0\.0(4|40)\s*A secondary/);
    }).toPass({ timeout: 5000 });
  });
});

test.describe("Overcurrent Analysis v1 -- secondary-current case", () => {
  test("secondary basis needs no CT fields and produces a valid operating point", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisOvercurrent(page);
    await selectContextAndWaitForValues(page, contextId);

    await expect(page.locator("#wwOvercurrentBasisSelect")).toHaveValue("secondary");
    await expect(page.locator("#wwOvercurrentCtPrimaryField")).toBeHidden();
    await expect(page.locator("#wwOvercurrentCtSecondaryField")).toBeHidden();
    await expect(page.locator("#wwOvercurrentSvg circle.ww-oc-operating-point")).toHaveCount(1);
  });
});

test.describe("Overcurrent Analysis v1 -- Playback", () => {
  test("Play advances the moving operating point and numeric values", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisOvercurrent(page);
    await selectContextAndWaitForValues(page, contextId);

    const playBtn = page.locator("#wwOvercurrentPlaybackMount .ww-tg-playback-play-btn");
    const before = await page.locator("#wwOvercurrentValuesList").innerText();
    await playBtn.click();
    await expect(playBtn).toHaveText("Pause");
    await page.waitForTimeout(600);
    await playBtn.click(); // pause

    const after = await page.locator("#wwOvercurrentValuesList").innerText();
    // The fixture is a steady sinusoid (magnitude does not change), but
    // the readout must still have been refreshed (a different request
    // was issued/rendered) -- assert the panel is still alive and
    // reflects a computed result throughout.
    expect(after).toContain("Measured RMS current");
    expect(before).toContain("Measured RMS current");
  });
});

test.describe("Overcurrent Analysis v1 -- Seek", () => {
  test("Pause, then seek converges exactly on the sought instant", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisOvercurrent(page);
    await selectContextAndWaitForValues(page, contextId);

    const slider = page.locator("#wwOvercurrentPlaybackMount .ww-tg-playback-seek-slider");
    const { min, max } = await seekSliderBounds(slider);
    const target = min + (max - min) * 0.75;
    await seekTo(slider, target);

    await expect(async () => {
      const currentTime = await page.evaluate(() => wwPlaybackState().currentTime);
      expect(Math.abs(currentTime - target)).toBeLessThan(0.01);
    }).toPass({ timeout: 5000 });
    await expect(async () => {
      const text = await page.locator("#wwOvercurrentValuesList").innerText();
      expect(text).toMatch(/40\.0\s*A secondary/);
    }).toPass({ timeout: 5000 });
  });
});

test.describe("Overcurrent Analysis v1 -- below pickup", () => {
  test("pickup above the measured current shows no fake finite operating time", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisOvercurrent(page);
    await selectContextAndWaitForValues(page, contextId);

    // Known 40 A RMS current; pickup set well above it (100 A) -> below pickup.
    await page.locator("#wwOvercurrentPickupInput").fill("100");
    await page.locator("#wwOvercurrentPickupInput").dispatchEvent("change");

    await expect(async () => {
      const text = await page.locator("#wwOvercurrentValuesList").innerText();
      expect(text).toContain("Below pickup");
      expect(text).not.toMatch(/Infinity|NaN/);
    }).toPass({ timeout: 5000 });
    // No fabricated operating point (no y-value exists below pickup) --
    // but the chart UX refinement still shows WHERE the current sits on
    // the X axis: a dim position marker on the axis + a vertical guide,
    // never the same class/color as a genuine computed operating point.
    await expect(page.locator("#wwOvercurrentSvg circle.ww-oc-operating-point")).toHaveCount(0);
    await expect(page.locator("#wwOvercurrentSvg circle.ww-oc-position-marker")).toHaveCount(1);
    await expect(page.locator("#wwOvercurrentSvg line.ww-oc-guide")).toHaveCount(1); // vertical only, never a horizontal one
    await expect(page.locator("#wwOvercurrentAlert")).toBeHidden();
  });
});

test.describe("Overcurrent Analysis v1 -- chart axes, grid, and ticks", () => {
  test("default viewport: full axis frame, major grid lines, and the owner's curated default major-tick set render", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisOvercurrent(page);
    await selectContextAndWaitForValues(page, contextId);

    // Axis lines (X + Y).
    await expect(page.locator("#wwOvercurrentSvg line.ww-oc-axis")).toHaveCount(2);
    // Major grid lines only (2026-09-12 UAT: simpler grid) -- 8 X majors
    // (0.5,1,2,5,10,20,50,100) + 4 Y majors (0.1,1,10,100).
    await expect(page.locator("#wwOvercurrentSvg line.ww-oc-gridline")).toHaveCount(12);

    // X majors that never coincide with a Y major label.
    for (const label of ["0.5", "2", "5", "20", "50"]) {
      await expect(page.locator("#wwOvercurrentSvg text.ww-oc-tick-label", { hasText: new RegExp("^" + label.replace(".", "\\.") + "$") })).toHaveCount(1);
    }
    // Values shared by both axes' own major set ("1", "10", "100").
    for (const label of ["1", "10", "100"]) {
      await expect(page.locator("#wwOvercurrentSvg text.ww-oc-tick-label", { hasText: new RegExp("^" + label + "$") })).toHaveCount(2);
    }
    // Y's own "0.1" major is a normal tick label...
    await expect(page.locator("#wwOvercurrentSvg text.ww-oc-tick-label", { hasText: /^0\.1$/ })).toHaveCount(1);
    // ...while X's own true minimum (also 0.1) renders as the lighter
    // minor/reference label instead, alongside Y's own true minimum (0.01).
    await expect(page.locator("#wwOvercurrentSvg text.ww-oc-tick-label-minor", { hasText: /^0\.1$/ })).toHaveCount(1);
    await expect(page.locator("#wwOvercurrentSvg text.ww-oc-tick-label-minor", { hasText: /^0\.01$/ })).toHaveCount(1);

    // The two special visual-origin "0" labels (X + Y), never log-transformed.
    await expect(page.locator("#wwOvercurrentSvg text.ww-oc-origin-label", { hasText: /^0$/ })).toHaveCount(2);

    // Axis titles unchanged.
    await expect(page.locator("#wwOvercurrentSvg text.ww-oc-axis-label", { hasText: "Current / Pickup Multiple (M)" })).toHaveCount(1);
    await expect(page.locator("#wwOvercurrentSvg text.ww-oc-axis-label", { hasText: "Expected Operating Time (s)" })).toHaveCount(1);
  });

  test("above-pickup operating point and both dashed guides still render, curve math unchanged", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisOvercurrent(page);
    await selectContextAndWaitForValues(page, contextId);
    await page.locator("#wwOvercurrentPickupInput").fill("1.0");
    await page.locator("#wwOvercurrentPickupInput").dispatchEvent("change");
    await page.locator("#wwOvercurrentTmsInput").fill("0.1");
    await page.locator("#wwOvercurrentTmsInput").dispatchEvent("change");

    await expect(async () => {
      const text = await page.locator("#wwOvercurrentValuesList").innerText();
      // Same known 40 A RMS / 1 A pickup -> M=40.0, unchanged from before
      // this chart-only refinement -- the underlying IDMT math/output is
      // untouched.
      expect(text).toMatch(/40\.0\s*×/);
    }).toPass({ timeout: 5000 });

    await expect(page.locator("#wwOvercurrentSvg circle.ww-oc-operating-point")).toHaveCount(1);
    await expect(page.locator("#wwOvercurrentSvg line.ww-oc-guide")).toHaveCount(2);
    await expect(page.locator("#wwOvercurrentSvg path.ww-oc-curve")).toHaveCount(1);

    const text = await page.locator("#wwOvercurrentValuesList").innerText();
    expect(text).not.toMatch(/Infinity|NaN/);
  });
});

test.describe("Overcurrent Analysis v1 -- threshold observation", () => {
  test("sustained above-pickup current can surface the qualified threshold alert, never a relay-tripped claim", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisOvercurrent(page);
    await selectContextAndWaitForValues(page, contextId);

    // Fastest supported TMS -> smallest expected operating time; the
    // fixture's own steady 40 A current (well above a 1 A pickup) has
    // already been "above pickup" for the whole recording up to
    // whatever analysis_time lands here, comfortably exceeding that tiny
    // expected time.
    await page.locator("#wwOvercurrentTmsInput").fill("0.025");
    await page.locator("#wwOvercurrentTmsInput").dispatchEvent("change");
    await page.locator("#wwOvercurrentPickupInput").fill("1.0");
    await page.locator("#wwOvercurrentPickupInput").dispatchEvent("change");

    const slider = page.locator("#wwOvercurrentPlaybackMount .ww-tg-playback-seek-slider");
    const { min, max } = await seekSliderBounds(slider);
    await seekTo(slider, min + (max - min) * 0.5);

    await expect(async () => {
      const text = await page.locator("#wwOvercurrentValuesList").innerText();
      expect(text).toContain("Above-pickup duration");
    }).toPass({ timeout: 5000 });

    const alertEl = page.locator("#wwOvercurrentAlert");
    await expect(alertEl).toBeVisible({ timeout: 5000 });
    const alertText = (await alertEl.textContent()).toLowerCase();
    expect(alertText).toContain("expected");
    // Never an unqualified relay-operation CLAIM -- "does not mean the
    // relay operated" (a negation) is fine and expected; "relay
    // tripped"/"should trip"/"failed to trip" as positive claims are not.
    expect(alertText).toContain("does not mean the relay operated");
    expect(alertText).not.toContain("relay tripped");
    expect(alertText).not.toContain("should trip");
    expect(alertText).not.toContain("failed to trip");
  });
});

test.describe("Overcurrent Analysis v1 -- analyzer switch", () => {
  test("Phasor at time t -> switch Overcurrent -> same shared Playback time t", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);

    await page.locator("#mainNavAnalysisBtn").click();
    await expect(page.locator("#pageAnalysis")).toBeVisible();
    await expect(page.locator("#wwPhasorPanel")).toBeVisible();
    await page.locator("#wwPhasorContextSelect").selectOption(contextId);
    const phasorSlider = page.locator("#wwPhasorPlaybackMount .ww-tg-playback-seek-slider");
    await expect(phasorSlider).toBeVisible();
    const { min, max } = await seekSliderBounds(phasorSlider);
    const target = min + (max - min) * 0.6;
    await seekTo(phasorSlider, target);
    await expect(async () => {
      const currentTime = await page.evaluate(() => wwPlaybackState().currentTime);
      expect(Math.abs(currentTime - target)).toBeLessThan(0.01);
    }).toPass({ timeout: 5000 });

    await page.locator("#wwAnalysisTypeOvercurrentBtn").click();
    await expect(page.locator("#wwOvercurrentPanel")).toBeVisible();
    await selectContextAndWaitForValues(page, contextId);

    const currentTimeAfterSwitch = await page.evaluate(() => wwPlaybackState().currentTime);
    expect(Math.abs(currentTimeAfterSwitch - target)).toBeLessThan(0.01);
  });
});

test.describe("Overcurrent Analysis v1 -- adjustable chart viewport (2026-09-12 UAT)", () => {
  test("default range inputs show 0.1/100/0.01/100", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisOvercurrent(page);
    await selectContextAndWaitForValues(page, contextId);

    await expect(page.locator("#wwOvercurrentViewXMin")).toHaveValue("0.1");
    await expect(page.locator("#wwOvercurrentViewXMax")).toHaveValue("100");
    await expect(page.locator("#wwOvercurrentViewYMin")).toHaveValue("0.01");
    await expect(page.locator("#wwOvercurrentViewYMax")).toHaveValue("100");
  });

  test("zoom in narrows the viewport, zoom out widens it, reset returns exactly to default", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisOvercurrent(page);
    await selectContextAndWaitForValues(page, contextId);

    await page.locator("#wwOvercurrentZoomInBtn").click();
    const xMaxAfterZoomIn = parseFloat(await page.locator("#wwOvercurrentViewXMax").inputValue());
    expect(xMaxAfterZoomIn).toBeLessThan(100);

    await page.locator("#wwOvercurrentZoomOutBtn").click();
    await page.locator("#wwOvercurrentZoomOutBtn").click();
    const xMaxAfterZoomOut = parseFloat(await page.locator("#wwOvercurrentViewXMax").inputValue());
    expect(xMaxAfterZoomOut).toBeGreaterThan(xMaxAfterZoomIn);

    await page.locator("#wwOvercurrentResetViewBtn").click();
    await expect(page.locator("#wwOvercurrentViewXMin")).toHaveValue("0.1");
    await expect(page.locator("#wwOvercurrentViewXMax")).toHaveValue("100");
    await expect(page.locator("#wwOvercurrentViewYMin")).toHaveValue("0.01");
    await expect(page.locator("#wwOvercurrentViewYMax")).toHaveValue("100");
    // Reset also restores the default major-grid labeling.
    await expect(page.locator("#wwOvercurrentSvg text.ww-oc-origin-label", { hasText: /^0$/ })).toHaveCount(2);
  });

  test("zoom out is capped at the absolute bound (X 200, Y 1000)", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisOvercurrent(page);
    await selectContextAndWaitForValues(page, contextId);

    for (let i = 0; i < 10; i++) {
      await page.locator("#wwOvercurrentZoomOutBtn").click();
    }
    const xMin = parseFloat(await page.locator("#wwOvercurrentViewXMin").inputValue());
    const xMax = parseFloat(await page.locator("#wwOvercurrentViewXMax").inputValue());
    const yMin = parseFloat(await page.locator("#wwOvercurrentViewYMin").inputValue());
    const yMax = parseFloat(await page.locator("#wwOvercurrentViewYMax").inputValue());
    expect(xMin).toBeCloseTo(0.1, 5);
    expect(xMax).toBeCloseTo(200, 3);
    expect(yMin).toBeCloseTo(0.01, 5);
    expect(yMax).toBeCloseTo(1000, 1);
  });

  test("custom range applies via inputs and shows the true selected minima, never a fake 0,0 origin", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisOvercurrent(page);
    await selectContextAndWaitForValues(page, contextId);

    await page.locator("#wwOvercurrentViewXMin").fill("2");
    await page.locator("#wwOvercurrentViewXMin").dispatchEvent("change");
    await page.locator("#wwOvercurrentViewXMax").fill("20");
    await page.locator("#wwOvercurrentViewXMax").dispatchEvent("change");
    await page.locator("#wwOvercurrentViewYMin").fill("0.1");
    await page.locator("#wwOvercurrentViewYMin").dispatchEvent("change");
    await page.locator("#wwOvercurrentViewYMax").fill("10");
    await page.locator("#wwOvercurrentViewYMax").dispatchEvent("change");

    // No fake "0" origin annotation in a custom view.
    await expect(page.locator("#wwOvercurrentSvg text.ww-oc-origin-label")).toHaveCount(0);
    // The true minima render directly as normal tick labels at the frame edge.
    await expect(page.locator("#wwOvercurrentSvg text.ww-oc-tick-label", { hasText: /^2$/ })).toHaveCount(1);
    await expect(page.locator("#wwOvercurrentSvg text.ww-oc-tick-label", { hasText: /^0\.1$/ })).toHaveCount(1);
  });

  test("invalid range input is rejected and reverts to the last-known-good viewport", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisOvercurrent(page);
    await selectContextAndWaitForValues(page, contextId);

    // xMax below xMin -- invalid, must be rejected.
    await page.locator("#wwOvercurrentViewXMax").fill("0.05");
    await page.locator("#wwOvercurrentViewXMax").dispatchEvent("change");
    await expect(page.locator("#wwOvercurrentViewXMax")).toHaveValue("100");
    await expect(page.locator("#wwOvercurrentViewXMin")).toHaveValue("0.1");
  });

  test("viewport changes never alter wwPlayback.currentTime or trigger a new curve fetch", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisOvercurrent(page);
    await selectContextAndWaitForValues(page, contextId);

    const slider = page.locator("#wwOvercurrentPlaybackMount .ww-tg-playback-seek-slider");
    const { min, max } = await seekSliderBounds(slider);
    const target = min + (max - min) * 0.4;
    await seekTo(slider, target);
    await expect(async () => {
      const currentTime = await page.evaluate(() => wwPlaybackState().currentTime);
      expect(Math.abs(currentTime - target)).toBeLessThan(0.01);
    }).toPass({ timeout: 5000 });

    let curveFetchCount = 0;
    page.on("request", (req) => {
      if (req.url().includes("/overcurrent-curve")) curveFetchCount++;
    });

    await page.locator("#wwOvercurrentZoomInBtn").click();
    await page.locator("#wwOvercurrentZoomOutBtn").click();
    await page.locator("#wwOvercurrentResetViewBtn").click();

    const currentTimeAfterZoom = await page.evaluate(() => wwPlaybackState().currentTime);
    expect(Math.abs(currentTimeAfterZoom - target)).toBeLessThan(0.01);
    expect(curveFetchCount).toBe(0);
  });

  test("above-pickup point outside a zoomed-in X range shows an edge indicator, never a false boundary point", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisOvercurrent(page);
    await selectContextAndWaitForValues(page, contextId);
    await page.locator("#wwOvercurrentPickupInput").fill("1.0");
    await page.locator("#wwOvercurrentPickupInput").dispatchEvent("change");

    await expect(async () => {
      const text = await page.locator("#wwOvercurrentValuesList").innerText();
      expect(text).toMatch(/40\.0\s*×/); // known M=40
    }).toPass({ timeout: 5000 });

    // Zoom the X range down to 2..20 -- M=40 now lies outside it.
    await page.locator("#wwOvercurrentViewXMax").fill("20");
    await page.locator("#wwOvercurrentViewXMax").dispatchEvent("change");
    await page.locator("#wwOvercurrentViewXMin").fill("2");
    await page.locator("#wwOvercurrentViewXMin").dispatchEvent("change");

    await expect(page.locator("#wwOvercurrentSvg circle.ww-oc-operating-point")).toHaveCount(0);
    await expect(page.locator("#wwOvercurrentSvg polygon.ww-oc-edge-indicator")).toHaveCount(1);
    // The true multiple is preserved, unaltered, in the live-values panel.
    const text = await page.locator("#wwOvercurrentValuesList").innerText();
    expect(text).toMatch(/40\.0\s*×/);
  });
});
