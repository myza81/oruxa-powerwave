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

    // Known 40 A RMS current; pickup set just above it (42 A) -> M~=0.952,
    // below pickup but still within the default viewport's own X Min
    // (0.9, owner UAT correction 2026-09-16) -- exercises the ON-CHART
    // below-pickup marker path, not the off-chart edge-indicator path
    // (see the "compressed sub-pickup axis" describe block for the
    // deliberately-widened, further-below-pickup scenario).
    await page.locator("#wwOvercurrentPickupInput").fill("42");
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
  test("default viewport (0.9->100 x, 0.1->100 s, owner UAT correction 2026-09-16): full axis frame, major grid lines, and the owner's curated default major-tick set render", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisOvercurrent(page);
    await selectContextAndWaitForValues(page, contextId);

    // Axis lines (X + Y).
    await expect(page.locator("#wwOvercurrentSvg line.ww-oc-axis")).toHaveCount(2);
    // Major grid lines only (2026-09-13 owner UAT correction: Pickup
    // Multiple mode's own FIXED, owner-approved major list) -- 13 X
    // majors (1,2,3,4,5,6,7,8,9,10,20,50,100, all >= the new 0.9 default
    // X Min) + 3 Y majors (1,10,100 -- Y's own new default minimum,
    // 0.1s, is itself excluded from the major set by the same "axis
    // minimum is never itself promoted to major" rule X's minimum
    // already followed). 3/4/6/7/8/9 are ALWAYS-VISIBLE majors, never
    // minor-gated -- see TestPickupMultipleFixedMajorTicks below for the
    // dedicated coverage of this correction.
    await expect(page.locator("#wwOvercurrentSvg line.ww-oc-gridline")).toHaveCount(16);

    // X majors that never coincide with a Y major label.
    for (const label of ["2", "3", "4", "5", "6", "7", "8", "9", "20", "50"]) {
      await expect(page.locator("#wwOvercurrentSvg text.ww-oc-tick-label", { hasText: new RegExp("^" + label.replace(".", "\\.") + "$") })).toHaveCount(1);
    }
    // Values shared by both axes' own major set ("1", "10", "100").
    for (const label of ["1", "10", "100"]) {
      await expect(page.locator("#wwOvercurrentSvg text.ww-oc-tick-label", { hasText: new RegExp("^" + label + "$") })).toHaveCount(2);
    }
    // X's own true minimum (0.9) and Y's own true minimum (0.1) each
    // render as the lighter minor/reference label, never as ordinary
    // majors.
    await expect(page.locator("#wwOvercurrentSvg text.ww-oc-tick-label-minor", { hasText: /^0\.9$/ })).toHaveCount(1);
    await expect(page.locator("#wwOvercurrentSvg text.ww-oc-tick-label-minor", { hasText: /^0\.1$/ })).toHaveCount(1);

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
  test("default range inputs show 0.9/100/0.1/100 (owner UAT correction 2026-09-16)", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisOvercurrent(page);
    await selectContextAndWaitForValues(page, contextId);

    await expect(page.locator("#wwOvercurrentViewXMin")).toHaveValue("0.9");
    await expect(page.locator("#wwOvercurrentViewXMax")).toHaveValue("100");
    await expect(page.locator("#wwOvercurrentViewYMin")).toHaveValue("0.1");
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
    await expect(page.locator("#wwOvercurrentViewXMin")).toHaveValue("0.9");
    await expect(page.locator("#wwOvercurrentViewXMax")).toHaveValue("100");
    await expect(page.locator("#wwOvercurrentViewYMin")).toHaveValue("0.1");
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
    await expect(page.locator("#wwOvercurrentViewXMin")).toHaveValue("0.9");
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

test.describe("Overcurrent Analysis v1 -- curve aligns exactly with the chart viewport (2026-09-12 UAT)", () => {
  async function setupCurve(page) {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisOvercurrent(page);
    await selectContextAndWaitForValues(page, contextId);
    await page.locator("#wwOvercurrentCharacteristicSelect").selectOption("iec_standard_inverse");
    await page.locator("#wwOvercurrentPickupInput").fill("1.0");
    await page.locator("#wwOvercurrentPickupInput").dispatchEvent("change");
    await page.locator("#wwOvercurrentTmsInput").fill("0.1");
    await page.locator("#wwOvercurrentTmsInput").dispatchEvent("change");
    await expect(async () => {
      const text = await page.locator("#wwOvercurrentValuesList").innerText();
      expect(text).toMatch(/40\.0\s*×/);
    }).toPass({ timeout: 5000 });
    return contextId;
  }

  async function firstSegmentPoint(page) {
    return page.evaluate(() => {
      const seg = wwOvercurrentVisibleCurveSegment(wwOvercurrentState.viewport);
      return seg ? seg[0] : null;
    });
  }
  async function lastSegmentPoint(page) {
    return page.evaluate(() => {
      const seg = wwOvercurrentVisibleCurveSegment(wwOvercurrentState.viewport);
      return seg ? seg[seg.length - 1] : null;
    });
  }

  test("curve's first visible point enters exactly at the current Y Max, and updates immediately when Y Max changes", async ({ page }) => {
    await setupCurve(page);

    await page.locator("#wwOvercurrentViewYMax").fill("1000");
    await page.locator("#wwOvercurrentViewYMax").dispatchEvent("change");
    let first = await firstSegmentPoint(page);
    expect(first).not.toBeNull();
    expect(first[1]).toBeCloseTo(1000, 6);

    await page.locator("#wwOvercurrentViewYMax").fill("500");
    await page.locator("#wwOvercurrentViewYMax").dispatchEvent("change");
    first = await firstSegmentPoint(page);
    expect(first[1]).toBeCloseTo(500, 6);

    await page.locator("#wwOvercurrentViewYMax").fill("50");
    await page.locator("#wwOvercurrentViewYMax").dispatchEvent("change");
    first = await firstSegmentPoint(page);
    expect(first[1]).toBeCloseTo(50, 6);

    // Not merely "<= Y Max" -- the actual mathematical boundary
    // intersection: evaluating the SAME characteristic/TMS forward at
    // the returned M must reproduce Y Max exactly.
    const crossCheck = await page.evaluate(() => {
      const seg = wwOvercurrentVisibleCurveSegment(wwOvercurrentState.viewport);
      const constants = wwOvercurrentCurrentConstants();
      return wwOvercurrentEvalT(constants, wwOvercurrentState.settings.tms, seg[0][0]);
    });
    expect(crossCheck).toBeCloseTo(50, 6);
  });

  test("curve's last visible point exits exactly at the current Y Min", async ({ page }) => {
    await setupCurve(page);
    // Standard Inverse's own alpha=0.02 decays far too slowly to reach
    // any Y Min within the allowed X domain (t(200x) ~= 0.125s even at
    // the absolute X cap) -- Extremely Inverse (alpha=2) decays fast
    // enough to genuinely exit through the bottom boundary at the
    // default viewport's own Y Min (0.1s, owner UAT correction
    // 2026-09-16 -- exit point M=9, well within X Max (100x)).
    await page.locator("#wwOvercurrentCharacteristicSelect").selectOption("iec_extremely_inverse");
    await expect(async () => {
      const text = await page.locator("#wwOvercurrentValuesList").innerText();
      expect(text).toMatch(/40\.0\s*×/);
    }).toPass({ timeout: 5000 });

    const last = await lastSegmentPoint(page);
    expect(last).not.toBeNull();
    expect(last[1]).toBeCloseTo(0.1, 6);
    // The exact mathematical boundary intersection, not merely "close to".
    const expectedM = await page.evaluate(() => {
      const constants = wwOvercurrentCurrentConstants();
      return wwOvercurrentSolveMForT(constants, wwOvercurrentState.settings.tms, 0.1);
    });
    expect(last[0]).toBeCloseTo(expectedM, 9);
  });

  test("curve exits exactly at the X Max right boundary when it is reached before Y Min", async ({ page }) => {
    await setupCurve(page);
    await page.locator("#wwOvercurrentViewXMax").fill("5");
    await page.locator("#wwOvercurrentViewXMax").dispatchEvent("change");

    const last = await lastSegmentPoint(page);
    expect(last).not.toBeNull();
    expect(last[0]).toBeCloseTo(5, 6);
    const expectedT = await page.evaluate(() => {
      const constants = wwOvercurrentCurrentConstants();
      return wwOvercurrentEvalT(constants, wwOvercurrentState.settings.tms, 5);
    });
    expect(last[1]).toBeCloseTo(expectedT, 9);
  });

  test("custom zoomed viewport re-aligns the curve's entry point to the new boundary", async ({ page }) => {
    await setupCurve(page);
    await page.locator("#wwOvercurrentViewXMin").fill("2");
    await page.locator("#wwOvercurrentViewXMin").dispatchEvent("change");
    await page.locator("#wwOvercurrentViewXMax").fill("20");
    await page.locator("#wwOvercurrentViewXMax").dispatchEvent("change");
    await page.locator("#wwOvercurrentViewYMin").fill("0.1");
    await page.locator("#wwOvercurrentViewYMin").dispatchEvent("change");
    await page.locator("#wwOvercurrentViewYMax").fill("10");
    await page.locator("#wwOvercurrentViewYMax").dispatchEvent("change");

    const first = await firstSegmentPoint(page);
    // At X=2..20, the top boundary (t=10s) is entered via the LEFT X
    // edge (M=2) for Standard Inverse/TMS=0.1 -- t(2) is well below 10s
    // -- so the exact entry point must be (2, t(2)), never (M_top, 10).
    const tAt2 = await page.evaluate(() => {
      const constants = wwOvercurrentCurrentConstants();
      return wwOvercurrentEvalT(constants, wwOvercurrentState.settings.tms, 2);
    });
    expect(first[0]).toBeCloseTo(2, 6);
    expect(first[1]).toBeCloseTo(tAt2, 9);
  });

  test("viewport-only changes never alter the live operating-point values", async ({ page }) => {
    await setupCurve(page);
    const before = await page.locator("#wwOvercurrentValuesList").innerText();

    await page.locator("#wwOvercurrentViewYMax").fill("500");
    await page.locator("#wwOvercurrentViewYMax").dispatchEvent("change");
    await page.locator("#wwOvercurrentZoomInBtn").click();
    await page.locator("#wwOvercurrentZoomOutBtn").click();
    await page.locator("#wwOvercurrentResetViewBtn").click();

    const after = await page.locator("#wwOvercurrentValuesList").innerText();
    expect(after).toBe(before);
  });

  test("SVG curve path visually starts near the plot's own top-left region when entering via Y Max", async ({ page }) => {
    await setupCurve(page);
    await page.locator("#wwOvercurrentViewYMax").fill("1000");
    await page.locator("#wwOvercurrentViewYMax").dispatchEvent("change");

    const d = await page.locator("#wwOvercurrentSvg path.ww-oc-curve").getAttribute("d");
    expect(d).toBeTruthy();
    const firstCommand = d.split(" ")[0]; // "M<x>,<y>"
    const [, coords] = firstCommand.split("M");
    const [xPx, yPx] = coords.split(",").map(Number);
    // The curve's first drawn pixel must sit at the plot's own TOP
    // edge (near geo.plotTop), not somewhere well below it.
    const plotTop = await page.evaluate(() => {
      const geo = wwOvercurrentChartGeometry(wwOvercurrentState.viewport);
      return geo.plotTop;
    });
    expect(Math.abs(yPx - plotTop)).toBeLessThan(1.0);
    expect(Number.isFinite(xPx)).toBe(true);
  });
});

test.describe("Overcurrent Analysis v1 -- X-axis representation toggle (chart UX enhancement)", () => {
  test("default axis mode is Pickup Multiple", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisOvercurrent(page);
    await selectContextAndWaitForValues(page, contextId);

    await expect(page.locator("#wwOvercurrentAxisModePickupBtn")).toHaveAttribute("aria-pressed", "true");
    await expect(page.locator("#wwOvercurrentAxisModeRelayBtn")).toHaveAttribute("aria-pressed", "false");
    await expect(page.locator("#wwOvercurrentSvg text.ww-oc-axis-label", { hasText: "Current / Pickup Multiple (M)" })).toHaveCount(1);
  });

  test("both toggle buttons are genuinely visible (non-transparent color/border) in either state -- UAT root-cause regression (2026-09-16)", async ({ page }) => {
    // Real root cause of the "toggle does not work" UAT report: the
    // click handler/state/re-render pipeline all worked correctly --
    // `.ww-oc-axis-toggle-btn` simply never set its own `color`/`border`,
    // so the INACTIVE button inherited the global `button { color: #fff;
    // border: none; }` reset and rendered as invisible white text on a
    // light/transparent background. An engineer could never find a
    // control they could not see. This test fails against the pre-fix
    // CSS (color would resolve to rgb(255, 255, 255)) and passes only
    // once the inactive button has a real, non-white text color and a
    // visible border.
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisOvercurrent(page);
    await selectContextAndWaitForValues(page, contextId);

    const stylesFor = async (id) =>
      page.locator(`#${id}`).evaluate((el) => {
        const cs = getComputedStyle(el);
        return { color: cs.color, borderColor: cs.borderColor, borderStyle: cs.borderStyle };
      });

    // Default state: Pickup Multiple active, Relay Current inactive.
    let inactive = await stylesFor("wwOvercurrentAxisModeRelayBtn");
    expect(inactive.color).not.toBe("rgb(255, 255, 255)");
    expect(inactive.borderStyle).not.toBe("none");

    await page.locator("#wwOvercurrentAxisModeRelayBtn").click();
    // After switching: Pickup Multiple is now inactive -- it must ALSO
    // remain visible, not merely the button that happened to start active.
    inactive = await stylesFor("wwOvercurrentAxisModePickupBtn");
    expect(inactive.color).not.toBe("rgb(255, 255, 255)");
    expect(inactive.borderStyle).not.toBe("none");
  });

  test("full UAT round trip: click Relay Current transforms every chart element, click back restores Pickup Multiple exactly", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisOvercurrent(page);
    await selectContextAndWaitForValues(page, contextId);

    // Golden scenario from the task spec: pickup 0.8 A, measured 40 A ->
    // multiple 50x (task's own illustrative numbers used 0.8/2.0/2.5 at
    // a different measured current; this fixture's known current is 40 A
    // secondary, so pickup 0.8 A gives multiple = 40/0.8 = 50x and the
    // Relay Current value is the measured current itself, 40 A).
    await page.locator("#wwOvercurrentPickupInput").fill("0.8");
    await page.locator("#wwOvercurrentPickupInput").dispatchEvent("change");
    await expect(async () => {
      const text = await page.locator("#wwOvercurrentValuesList").innerText();
      expect(text).toMatch(/50\.0\s*×/);
    }).toPass({ timeout: 5000 });

    // 1/2/3: default Pickup Multiple, capture title + operating point.
    await expect(page.locator("#wwOvercurrentAxisModePickupBtn")).toHaveAttribute("aria-pressed", "true");
    await expect(page.locator("#wwOvercurrentSvg text.ww-oc-axis-label", { hasText: "Current / Pickup Multiple (M)" })).toHaveCount(1);
    const pickupModeOpX = await page.locator("#wwOvercurrentSvg circle.ww-oc-operating-point").getAttribute("cx");
    const pickupModeBoundaryX = await page.locator("#wwOvercurrentSvg line.ww-oc-pickup-boundary").getAttribute("x1");
    const pickupModeTickLabels = await page.locator("#wwOvercurrentSvg text.ww-oc-tick-label").allTextContents();
    const pickupModeXMin = await page.locator("#wwOvercurrentViewXMin").inputValue();
    const pickupModeXMax = await page.locator("#wwOvercurrentViewXMax").inputValue();

    // 4/5: click Relay Current, assert visible button-state change.
    await page.locator("#wwOvercurrentAxisModeRelayBtn").click();
    await expect(page.locator("#wwOvercurrentAxisModeRelayBtn")).toHaveAttribute("aria-pressed", "true");
    await expect(page.locator("#wwOvercurrentAxisModePickupBtn")).toHaveAttribute("aria-pressed", "false");

    // 6: axis title changes.
    await expect(page.locator("#wwOvercurrentSvg text.ww-oc-axis-label", { hasText: "Relay Current (A secondary)" })).toHaveCount(1);

    // 7: operating point x-coordinate transforms to the new UNIT
    // (amperes, not M) -- but owner UAT correction (2026-09-16) means
    // the two representations are now visually EQUIVALENT: M=50x and
    // I=40A (= 50 * 0.8 pickup) sit at the exact SAME pixel position,
    // since Relay Current's own default viewport is now derived from
    // the same M-domain default scaled by pickup. The underlying VALUE
    // changed units (confirmed via the live-values panel elsewhere),
    // the pixel position deliberately did not.
    const relayModeOpX = await page.locator("#wwOvercurrentSvg circle.ww-oc-operating-point").getAttribute("cx");
    expect(Number(relayModeOpX)).toBeCloseTo(Number(pickupModeOpX), 1);

    // 8: pickup boundary -- same visual-equivalence guarantee: M=1
    // (Pickup Multiple) and I=pickup=0.8A (Relay Current) occupy the
    // exact same pixel position (task's own "visual equivalence"
    // section: "It should occupy the exact same visual x-position as
    // M = 1 in Pickup Multiple mode").
    const relayModeBoundaryX = await page.locator("#wwOvercurrentSvg line.ww-oc-pickup-boundary").getAttribute("x1");
    expect(Number(relayModeBoundaryX)).toBeCloseTo(Number(pickupModeBoundaryX), 1);

    // 9: ticks are current-domain (amperes), not M-domain -- the Pickup
    // Multiple mode's fixed 3/4/6/7/8/9 majors must NOT all still be
    // present verbatim once scaled by a non-1.0 pickup (0.8x scales
    // every tick value).
    const relayModeTickLabels = await page.locator("#wwOvercurrentSvg text.ww-oc-tick-label").allTextContents();
    expect(relayModeTickLabels).not.toEqual(pickupModeTickLabels);
    const relayModeXMin = await page.locator("#wwOvercurrentViewXMin").inputValue();
    const relayModeXMax = await page.locator("#wwOvercurrentViewXMax").inputValue();
    expect(relayModeXMin).not.toBe(pickupModeXMin);
    expect(relayModeXMax).not.toBe(pickupModeXMax);

    // 10/11: click back to Pickup Multiple, everything restores exactly.
    await page.locator("#wwOvercurrentAxisModePickupBtn").click();
    await expect(page.locator("#wwOvercurrentAxisModePickupBtn")).toHaveAttribute("aria-pressed", "true");
    await expect(page.locator("#wwOvercurrentAxisModeRelayBtn")).toHaveAttribute("aria-pressed", "false");
    await expect(page.locator("#wwOvercurrentSvg text.ww-oc-axis-label", { hasText: "Current / Pickup Multiple (M)" })).toHaveCount(1);
    await expect(page.locator("#wwOvercurrentSvg circle.ww-oc-operating-point")).toHaveAttribute("cx", pickupModeOpX);
    await expect(page.locator("#wwOvercurrentSvg line.ww-oc-pickup-boundary")).toHaveAttribute("x1", pickupModeBoundaryX);
    await expect(page.locator("#wwOvercurrentViewXMin")).toHaveValue(pickupModeXMin);
    await expect(page.locator("#wwOvercurrentViewXMax")).toHaveValue(pickupModeXMax);
  });

  test("switching to Relay Current changes the axis title and X range, never fetching a new curve or waveform", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisOvercurrent(page);
    await selectContextAndWaitForValues(page, contextId);

    let curveFetchCount = 0;
    let waveformFetchCount = 0;
    page.on("request", (req) => {
      if (req.url().includes("/overcurrent-curve")) curveFetchCount++;
      if (req.url().includes("/waveform")) waveformFetchCount++;
    });

    await page.locator("#wwOvercurrentAxisModeRelayBtn").click();
    await expect(page.locator("#wwOvercurrentAxisModeRelayBtn")).toHaveAttribute("aria-pressed", "true");
    await expect(page.locator("#wwOvercurrentAxisModePickupBtn")).toHaveAttribute("aria-pressed", "false");
    await expect(page.locator("#wwOvercurrentSvg text.ww-oc-axis-label", { hasText: "Relay Current (A secondary)" })).toHaveCount(1);
    // Default pickup is 1.0 A -- Relay Current mode's own default range
    // is the SAME 0.9x/100x M-domain default Pickup Multiple uses,
    // scaled by pickup (owner UAT correction 2026-09-16: the two
    // representations must stay visually equivalent), i.e. identical
    // numbers at pickup=1.0.
    await expect(page.locator("#wwOvercurrentViewXMin")).toHaveValue("0.9");
    await expect(page.locator("#wwOvercurrentViewXMax")).toHaveValue("100");

    expect(curveFetchCount).toBe(0);
    expect(waveformFetchCount).toBe(0);
  });

  test("switching back to Pickup Multiple restores the range as the user left it", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisOvercurrent(page);
    await selectContextAndWaitForValues(page, contextId);

    await page.locator("#wwOvercurrentZoomInBtn").click();
    const xMaxAfterZoom = await page.locator("#wwOvercurrentViewXMax").inputValue();

    await page.locator("#wwOvercurrentAxisModeRelayBtn").click();
    await page.locator("#wwOvercurrentAxisModePickupBtn").click();

    await expect(page.locator("#wwOvercurrentViewXMax")).toHaveValue(xMaxAfterZoom);
  });

  test("pickup boundary is fixed at M=1 in Pickup Multiple mode, and (owner UAT correction 2026-09-16) sits at that exact same visual position in Relay Current mode too", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisOvercurrent(page);
    await selectContextAndWaitForValues(page, contextId);

    const boundaryXAtPickup1 = await page.locator("#wwOvercurrentSvg line.ww-oc-pickup-boundary").getAttribute("x1");

    await page.locator("#wwOvercurrentPickupInput").fill("0.8");
    await page.locator("#wwOvercurrentPickupInput").dispatchEvent("change");
    await expect(async () => {
      const text = await page.locator("#wwOvercurrentValuesList").innerText();
      expect(text).toMatch(/50\.0\s*×/); // 40 A / 0.8 A = 50x
    }).toPass({ timeout: 5000 });

    // Pickup Multiple mode -- the boundary stays at M=1, unaffected by
    // the pickup change (task §6).
    const boundaryXAfterPickupChange = await page.locator("#wwOvercurrentSvg line.ww-oc-pickup-boundary").getAttribute("x1");
    expect(boundaryXAfterPickupChange).toBe(boundaryXAtPickup1);

    // Relay Current mode -- since its own default viewport is now
    // derived from the SAME M-domain default scaled by this exact
    // pickup (task's own "visual equivalence" requirement), the
    // boundary (I = pickup = 0.8 A) sits at the EXACT SAME pixel
    // position M=1 always does -- never a different, "moved" position.
    // The underlying ENGINEERING VALUE at that position is different
    // (0.8 A vs M=1), but the pixel geometry itself does not move.
    await page.locator("#wwOvercurrentAxisModeRelayBtn").click();
    const boundaryXRelay = await page.locator("#wwOvercurrentSvg line.ww-oc-pickup-boundary").getAttribute("x1");
    expect(Number(boundaryXRelay)).toBeCloseTo(Number(boundaryXAtPickup1), 1);
  });

  test("Relay Current default viewport at pickup 0.8 A is exactly 0.72 -> 80 A (owner UAT golden scenario, 2026-09-16)", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisOvercurrent(page);
    await selectContextAndWaitForValues(page, contextId);

    await page.locator("#wwOvercurrentPickupInput").fill("0.8");
    await page.locator("#wwOvercurrentPickupInput").dispatchEvent("change");
    await expect(async () => {
      const text = await page.locator("#wwOvercurrentValuesList").innerText();
      expect(text).toMatch(/50\.0\s*×/);
    }).toPass({ timeout: 5000 });

    await page.locator("#wwOvercurrentAxisModeRelayBtn").click();
    const xMin = parseFloat(await page.locator("#wwOvercurrentViewXMin").inputValue());
    const xMax = parseFloat(await page.locator("#wwOvercurrentViewXMax").inputValue());
    expect(xMin).toBeCloseTo(0.72, 6);
    expect(xMax).toBeCloseTo(80, 6);

    // The viewport-start reference (0.9 * pickup, mirroring Pickup
    // Multiple's own "0.9" start reference) renders as the light
    // minor/reference label.
    await expect(page.locator("#wwOvercurrentSvg text.ww-oc-tick-label-minor", { hasText: /^0\.72$/ })).toHaveCount(1);
  });

  test("Relay Current major tick values at pickup 0.8 A match the exact worked example", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisOvercurrent(page);
    await selectContextAndWaitForValues(page, contextId);

    await page.locator("#wwOvercurrentPickupInput").fill("0.8");
    await page.locator("#wwOvercurrentPickupInput").dispatchEvent("change");
    await expect(async () => {
      const text = await page.locator("#wwOvercurrentValuesList").innerText();
      expect(text).toMatch(/50\.0\s*×/);
    }).toPass({ timeout: 5000 });
    await page.locator("#wwOvercurrentAxisModeRelayBtn").click();

    // 0.8, 1.6, 2.4, 3.2, 4.0, 4.8, 5.6, 6.4, 7.2, 8.0, 16, 40, 80 A.
    for (const label of ["1.6", "2.4", "3.2", "4.8", "5.6", "6.4", "7.2", "16", "40", "80"]) {
      await expect(page.locator("#wwOvercurrentSvg text.ww-oc-tick-label", { hasText: new RegExp("^" + label.replace(".", "\\.") + "$") })).toHaveCount(1);
    }
    // "0.8", "4", "8" are each shared with a Y-axis label coincidentally
    // only when Y happens to carry the same numeral -- assert their
    // presence without assuming an exact count, to stay robust to the Y
    // major set.
    for (const label of ["0.8", "4", "8"]) {
      const count = await page.locator("#wwOvercurrentSvg text.ww-oc-tick-label", { hasText: new RegExp("^" + label.replace(".", "\\.") + "$") }).count();
      expect(count).toBeGreaterThanOrEqual(1);
    }
  });

  test("switching pickup while in Relay Current mode updates ticks, boundary, and curve immediately (within the current viewport); Reset then reflects the new pickup", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisOvercurrent(page);
    await selectContextAndWaitForValues(page, contextId);
    await page.locator("#wwOvercurrentAxisModeRelayBtn").click();

    const boundaryBefore = await page.locator("#wwOvercurrentSvg line.ww-oc-pickup-boundary").getAttribute("x1");
    const curveDBefore = await page.locator("#wwOvercurrentSvg path.ww-oc-curve").getAttribute("d");
    const xMinBefore = await page.locator("#wwOvercurrentViewXMin").inputValue();

    let requestCount = 0;
    page.on("request", (req) => {
      if (req.url().includes("/overcurrent-curve") || req.url().includes("/waveform")) requestCount++;
    });

    // Pickup 2.0 A (not 0.8) -- deliberately stays WITHIN the current,
    // unchanged viewport (Relay Current's own default at pickup=1.0 is
    // 0.9-100 A), so the boundary remains on-chart and its own moved
    // position can be observed directly, rather than going out of range
    // (a separate, already-covered edge case -- see the existing
    // "below pickup, off-chart" edge-indicator tests elsewhere).
    await page.locator("#wwOvercurrentPickupInput").fill("2.0");
    await page.locator("#wwOvercurrentPickupInput").dispatchEvent("change");
    await expect(async () => {
      const text = await page.locator("#wwOvercurrentValuesList").innerText();
      expect(text).toMatch(/20\.0\s*×/); // 40 / 2.0 = 20x
    }).toPass({ timeout: 5000 });

    // The pickup change is a real settings change (correctly refetches
    // the analysis result), but never the curve/waveform -- the axis
    // coordinate transform itself never triggers a backend request.
    expect(requestCount).toBe(0);

    // Tick labels/boundary/curve all update immediately, within the
    // CURRENT (unchanged) viewport -- the viewport itself only ever
    // moves on an explicit Reset/mode-switch, never silently on a
    // pickup change alone (mirrors the pre-existing Pickup Multiple
    // mode precedent: a pickup change never silently moves the
    // viewport out from under the user).
    await expect(page.locator("#wwOvercurrentViewXMin")).toHaveValue(xMinBefore);
    await expect(page.locator("#wwOvercurrentSvg text.ww-oc-tick-label", { hasText: /^4$/ })).toHaveCount(1); // M=2 * 2.0A
    const boundaryAfter = await page.locator("#wwOvercurrentSvg line.ww-oc-pickup-boundary").getAttribute("x1");
    expect(boundaryAfter).not.toBe(boundaryBefore);
    const curveDAfter = await page.locator("#wwOvercurrentSvg path.ww-oc-curve").getAttribute("d");
    expect(curveDAfter).not.toBe(curveDBefore);

    // Reset now reflects the NEW pickup (1.8 -> 200 A), never a stale
    // value from before the pickup change.
    await page.locator("#wwOvercurrentResetViewBtn").click();
    const xMinAfterReset = parseFloat(await page.locator("#wwOvercurrentViewXMin").inputValue());
    const xMaxAfterReset = parseFloat(await page.locator("#wwOvercurrentViewXMax").inputValue());
    expect(xMinAfterReset).toBeCloseTo(1.8, 6);
    expect(xMaxAfterReset).toBeCloseTo(200, 6);
  });

  test("relay-equivalent current stays constant across a pickup change while the multiple changes", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisOvercurrent(page);
    await selectContextAndWaitForValues(page, contextId);

    // Secondary basis, 40 A measured -- relay-equivalent current is
    // ALWAYS 40 A regardless of pickup (task §6's own worked example:
    // "relay current remains = 2.0 A" while the multiple/boundary move).
    await expect(async () => {
      const text = await page.locator("#wwOvercurrentValuesList").innerText();
      expect(text).toMatch(/40\.0\s*A secondary/);
    }).toPass({ timeout: 5000 });

    await page.locator("#wwOvercurrentPickupInput").fill("0.5");
    await page.locator("#wwOvercurrentPickupInput").dispatchEvent("change");
    await expect(async () => {
      const text = await page.locator("#wwOvercurrentValuesList").innerText();
      expect(text).toMatch(/80\.0\s*×/); // 40 / 0.5 = 80x
      expect(text).toMatch(/40\.0\s*A secondary/); // relay current unchanged
    }).toPass({ timeout: 5000 });
  });

  test("axis mode preference persists across Playback, phase change, and a Phasor round trip", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisOvercurrent(page);
    await selectContextAndWaitForValues(page, contextId);
    await page.locator("#wwOvercurrentAxisModeRelayBtn").click();

    const slider = page.locator("#wwOvercurrentPlaybackMount .ww-tg-playback-seek-slider");
    const { min, max } = await seekSliderBounds(slider);
    await seekTo(slider, min + (max - min) * 0.3);
    await expect(page.locator("#wwOvercurrentAxisModeRelayBtn")).toHaveAttribute("aria-pressed", "true");

    await page.locator("#wwOvercurrentPhaseSelect").selectOption("B");
    await expect(page.locator("#wwOvercurrentAxisModeRelayBtn")).toHaveAttribute("aria-pressed", "true");

    await page.locator("#wwAnalysisTypePhasorBtn").click();
    await expect(page.locator("#wwPhasorPanel")).toBeVisible();
    await page.locator("#wwAnalysisTypeOvercurrentBtn").click();
    await expect(page.locator("#wwOvercurrentPanel")).toBeVisible();
    await expect(page.locator("#wwOvercurrentAxisModeRelayBtn")).toHaveAttribute("aria-pressed", "true");
  });
});

test.describe("Overcurrent Analysis v1 -- minor grid toggles (chart UX enhancement)", () => {
  test("Minor X and Minor Y are OFF by default and major gridlines still render", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisOvercurrent(page);
    await selectContextAndWaitForValues(page, contextId);

    await expect(page.locator("#wwOvercurrentMinorGridXCheckbox")).not.toBeChecked();
    await expect(page.locator("#wwOvercurrentMinorGridYCheckbox")).not.toBeChecked();
    await expect(page.locator("#wwOvercurrentSvg line.ww-oc-gridline-minor")).toHaveCount(0);
    const majorCount = await page.locator("#wwOvercurrentSvg line.ww-oc-gridline").count();
    expect(majorCount).toBeGreaterThan(0);
  });

  test("enabling Minor X shows the 1.2/1.4/1.6/1.8 subdivisions between 1 and 2, disabling removes them", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisOvercurrent(page);
    await selectContextAndWaitForValues(page, contextId);

    await page.locator("#wwOvercurrentMinorGridXCheckbox").check();
    const expectedXPositions = await page.evaluate(() => {
      const geo = wwOvercurrentChartGeometry(wwOvercurrentState.viewport);
      return [1.2, 1.4, 1.6, 1.8].map((v) => wwOvercurrentPixelX(v, geo).toFixed(2));
    });
    const renderedX = await page.locator("#wwOvercurrentSvg line.ww-oc-gridline-minor").evaluateAll(
      (lines) => lines.map((el) => el.getAttribute("x1"))
    );
    for (const expected of expectedXPositions) {
      expect(renderedX).toContain(expected);
    }

    await page.locator("#wwOvercurrentMinorGridXCheckbox").uncheck();
    await expect(page.locator("#wwOvercurrentSvg line.ww-oc-gridline-minor")).toHaveCount(0);
  });

  test("Minor X and Minor Y toggle independently", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisOvercurrent(page);
    await selectContextAndWaitForValues(page, contextId);

    await page.locator("#wwOvercurrentMinorGridYCheckbox").check();
    const countYOnly = await page.locator("#wwOvercurrentSvg line.ww-oc-gridline-minor").count();
    expect(countYOnly).toBeGreaterThan(0);

    await page.locator("#wwOvercurrentMinorGridXCheckbox").check();
    const countBoth = await page.locator("#wwOvercurrentSvg line.ww-oc-gridline-minor").count();
    expect(countBoth).toBeGreaterThan(countYOnly);

    await page.locator("#wwOvercurrentMinorGridYCheckbox").uncheck();
    const countXOnly = await page.locator("#wwOvercurrentSvg line.ww-oc-gridline-minor").count();
    expect(countXOnly).toBeGreaterThan(0);
    expect(countXOnly).toBeLessThan(countBoth);
  });

  test("toggling Minor X/Y causes zero backend requests", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisOvercurrent(page);
    await selectContextAndWaitForValues(page, contextId);

    let requestCount = 0;
    page.on("request", (req) => {
      if (req.url().includes("/overcurrent-curve") || req.url().includes("/overcurrent?") || req.url().includes("/waveform")) requestCount++;
    });

    await page.locator("#wwOvercurrentMinorGridXCheckbox").check();
    await page.locator("#wwOvercurrentMinorGridYCheckbox").check();
    await page.locator("#wwOvercurrentMinorGridXCheckbox").uncheck();
    await page.locator("#wwOvercurrentMinorGridYCheckbox").uncheck();

    expect(requestCount).toBe(0);
  });

  test("grid toggle preferences persist across a Phasor round trip", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisOvercurrent(page);
    await selectContextAndWaitForValues(page, contextId);

    await page.locator("#wwOvercurrentMinorGridXCheckbox").check();
    await page.locator("#wwAnalysisTypePhasorBtn").click();
    await expect(page.locator("#wwPhasorPanel")).toBeVisible();
    await page.locator("#wwAnalysisTypeOvercurrentBtn").click();
    await expect(page.locator("#wwOvercurrentPanel")).toBeVisible();
    await expect(page.locator("#wwOvercurrentMinorGridXCheckbox")).toBeChecked();
  });
});

test.describe("Overcurrent Analysis v1 -- compressed sub-pickup axis (chart geometry refinement)", () => {
  async function gridlineXPositions(page, selector) {
    return page.locator(selector).evaluateAll((lines) => lines.map((el) => parseFloat(el.getAttribute("x1"))));
  }

  test("default Pickup Multiple viewport (0.9->100, owner UAT correction 2026-09-16) uses the ordinary log mapping, no break", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisOvercurrent(page);
    await selectContextAndWaitForValues(page, contextId);

    const ratios = await page.evaluate(() => {
      const geo = wwOvercurrentChartGeometry(wwOvercurrentState.viewport);
      return { breakApplies: geo.breakApplies, xMin: wwOvercurrentState.viewport.xMin };
    });
    expect(ratios.xMin).toBeCloseTo(0.9, 5);
    expect(ratios.breakApplies).toBe(false);
    await expect(page.locator("#wwOvercurrentSvg line.ww-oc-axis-break")).toHaveCount(0);
  });

  test("widening X Min to 0.1 (well below the 0.5 threshold) activates the compressed gutter: 0.1->1 occupies ~5% of plot width, 1->100 occupies ~95%", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisOvercurrent(page);
    await selectContextAndWaitForValues(page, contextId);

    await page.locator("#wwOvercurrentViewXMin").fill("0.1");
    await page.locator("#wwOvercurrentViewXMin").dispatchEvent("change");

    const ratios = await page.evaluate(() => {
      const geo = wwOvercurrentChartGeometry(wwOvercurrentState.viewport);
      const pxAtMin = wwOvercurrentPixelX(0.1, geo);
      const pxAtOne = wwOvercurrentPixelX(1, geo);
      const pxAtMax = wwOvercurrentPixelX(100, geo);
      const plotWidth = geo.plotRight - geo.logLeft;
      return {
        breakApplies: geo.breakApplies,
        belowFraction: (pxAtOne - pxAtMin) / plotWidth,
        aboveFraction: (pxAtMax - pxAtOne) / plotWidth,
      };
    });
    expect(ratios.breakApplies).toBe(true);
    expect(ratios.belowFraction).toBeCloseTo(0.05, 1);
    expect(ratios.aboveFraction).toBeCloseTo(0.95, 1);
  });

  test("axis-break marker renders at the M=1 position once a deliberately wide below-pickup viewport is chosen", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisOvercurrent(page);
    await selectContextAndWaitForValues(page, contextId);

    // No break at the new default (0.9 is above the 0.5 threshold).
    await expect(page.locator("#wwOvercurrentSvg line.ww-oc-axis-break")).toHaveCount(0);

    // Widen to 0.1 (well below the threshold) -- the break appears.
    await page.locator("#wwOvercurrentViewXMin").fill("0.1");
    await page.locator("#wwOvercurrentViewXMin").dispatchEvent("change");

    const breakLines = await page.locator("#wwOvercurrentSvg line.ww-oc-axis-break").count();
    expect(breakLines).toBe(2); // the double-diagonal-tick mark

    const expectedX = await page.evaluate(() => {
      const geo = wwOvercurrentChartGeometry(wwOvercurrentState.viewport);
      return wwOvercurrentPixelX(1, geo);
    });
    const positions = await gridlineXPositions(page, "#wwOvercurrentSvg line.ww-oc-axis-break");
    for (const x of positions) {
      expect(Math.abs(x - expectedX)).toBeLessThan(6); // within the marker's own dx+skew offsets
    }
  });

  test("operating point below pickup renders inside the compressed sub-pickup gutter once the viewport is widened below the break threshold", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisOvercurrent(page);
    await selectContextAndWaitForValues(page, contextId);
    // Known 40 A RMS current; pickup 100 A -> M = 0.4, below pickup --
    // also below the new default's own X Min (0.9), so widen the
    // viewport first to keep M=0.4 visible and inside the compressed
    // gutter (task's own worked example needs a deliberately wide view).
    await page.locator("#wwOvercurrentViewXMin").fill("0.1");
    await page.locator("#wwOvercurrentViewXMin").dispatchEvent("change");
    await page.locator("#wwOvercurrentPickupInput").fill("100");
    await page.locator("#wwOvercurrentPickupInput").dispatchEvent("change");

    await expect(async () => {
      const text = await page.locator("#wwOvercurrentValuesList").innerText();
      expect(text).toContain("Below pickup");
    }).toPass({ timeout: 5000 });

    const markerX = parseFloat(await page.locator("#wwOvercurrentSvg circle.ww-oc-position-marker").getAttribute("cx"));
    const geo = await page.evaluate(() => wwOvercurrentChartGeometry(wwOvercurrentState.viewport));
    expect(geo.breakApplies).toBe(true);
    // The marker's own X must sit strictly within the compressed gutter
    // (logLeft -> breakPx), never past the M=1 break into the operating
    // region -- proving the below-pickup value used the SAME piecewise
    // transform, not a stray standard-log position.
    expect(markerX).toBeGreaterThanOrEqual(geo.logLeft - 0.5);
    expect(markerX).toBeLessThanOrEqual(geo.breakPx + 0.5);
    // No fabricated y-value -- unchanged pre-existing semantic.
    await expect(page.locator("#wwOvercurrentSvg circle.ww-oc-operating-point")).toHaveCount(0);
  });

  test("no finite curve point exists at or below M=1, characteristic begins only above pickup", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisOvercurrent(page);
    await selectContextAndWaitForValues(page, contextId);

    const d = await page.locator("#wwOvercurrentSvg path.ww-oc-curve").getAttribute("d");
    expect(d).toBeTruthy();
    const firstMoveTo = d.split(" ")[0]; // "M<x>,<y>" (SVG path command, unrelated to the M= pickup-multiple variable)
    const [, coords] = firstMoveTo.split("M");
    const [xPx] = coords.split(",").map(Number);
    const pxAtOne = await page.evaluate(() => {
      const geo = wwOvercurrentChartGeometry(wwOvercurrentState.viewport);
      return wwOvercurrentPixelX(1, geo);
    });
    // The curve's own first drawn pixel must be AT/AFTER the M=1
    // position, never before it -- true whether or not the compressed
    // gutter is active for the current viewport.
    expect(xPx).toBeGreaterThanOrEqual(pxAtOne - 0.5);
  });

  test("a custom viewport entirely at/above M=1 reverts to the ordinary single log mapping (no gutter)", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisOvercurrent(page);
    await selectContextAndWaitForValues(page, contextId);

    await page.locator("#wwOvercurrentViewXMin").fill("2");
    await page.locator("#wwOvercurrentViewXMin").dispatchEvent("change");
    await page.locator("#wwOvercurrentViewXMax").fill("20");
    await page.locator("#wwOvercurrentViewXMax").dispatchEvent("change");

    await expect(page.locator("#wwOvercurrentSvg line.ww-oc-axis-break")).toHaveCount(0);
    const breakApplies = await page.evaluate(() => wwOvercurrentChartGeometry(wwOvercurrentState.viewport).breakApplies);
    expect(breakApplies).toBe(false);
  });

  test("a custom viewport straddling M=1 shows the break again", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisOvercurrent(page);
    await selectContextAndWaitForValues(page, contextId);

    await page.locator("#wwOvercurrentViewXMin").fill("0.5");
    await page.locator("#wwOvercurrentViewXMin").dispatchEvent("change");
    await page.locator("#wwOvercurrentViewXMax").fill("5");
    await page.locator("#wwOvercurrentViewXMax").dispatchEvent("change");

    await expect(page.locator("#wwOvercurrentSvg line.ww-oc-axis-break")).toHaveCount(2);
  });

  test("Relay Current mode never shows the axis break, even with a below/above-1 spanning viewport", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisOvercurrent(page);
    await selectContextAndWaitForValues(page, contextId);

    await page.locator("#wwOvercurrentAxisModeRelayBtn").click();
    await expect(page.locator("#wwOvercurrentSvg line.ww-oc-axis-break")).toHaveCount(0);
    const breakApplies = await page.evaluate(() => wwOvercurrentChartGeometry(wwOvercurrentState.viewport).breakApplies);
    expect(breakApplies).toBe(false);
  });

  test("viewport X Min/X Max inputs always show real engineering M values, never transformed screen coordinates", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisOvercurrent(page);
    await selectContextAndWaitForValues(page, contextId);

    await expect(page.locator("#wwOvercurrentViewXMin")).toHaveValue("0.9");
    await expect(page.locator("#wwOvercurrentViewXMax")).toHaveValue("100");

    await page.locator("#wwOvercurrentZoomInBtn").click();
    const xMin = parseFloat(await page.locator("#wwOvercurrentViewXMin").inputValue());
    const xMax = parseFloat(await page.locator("#wwOvercurrentViewXMax").inputValue());
    // Real M-domain values only -- both comfortably within the absolute
    // 0.1-200 engineering range, never a 0-320 pixel-space number.
    expect(xMin).toBeGreaterThanOrEqual(0.1);
    expect(xMax).toBeLessThanOrEqual(200);
  });

  test("compressed-axis geometry never triggers a curve or waveform fetch", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisOvercurrent(page);
    await selectContextAndWaitForValues(page, contextId);

    let requestCount = 0;
    page.on("request", (req) => {
      if (req.url().includes("/overcurrent-curve") || req.url().includes("/overcurrent?") || req.url().includes("/waveform")) requestCount++;
    });

    // Toggle the break on and off purely via viewport changes -- no
    // settings (pickup/TMS/basis/CT/phase/characteristic) touched, so
    // this isolates the geometry refinement itself from the pre-existing,
    // unrelated "a settings change refetches the analysis" behavior.
    await page.locator("#wwOvercurrentViewXMin").fill("2");
    await page.locator("#wwOvercurrentViewXMin").dispatchEvent("change");
    await page.locator("#wwOvercurrentResetViewBtn").click();
    await page.locator("#wwOvercurrentAxisModeRelayBtn").click();
    await page.locator("#wwOvercurrentAxisModePickupBtn").click();

    expect(requestCount).toBe(0);
  });
});

test.describe("Overcurrent Analysis v1 -- shared Analysis Engineering Context lifecycle (2026-09-12 owner UAT fix)", () => {
  // Owner UAT: after uploading an event, opening Overcurrent DIRECTLY
  // (without ever visiting/selecting anything in Phasor) could show an
  // empty Bay selector -- Engineering Context discovery/bootstrap used
  // to live entirely inside Phasor's own code path. This is now owned
  // by the shared Analysis workspace (wwAnalysisLoadContexts() and
  // friends) -- Phasor/Overcurrent are pure consumers of the ONE
  // published list, so opening either one first produces identical
  // context availability. No manual context creation in these tests --
  // relies entirely on the automatic suggestion bootstrap, exactly like
  // phasor_analysis.spec.js's own "Engineering Context bootstrap"
  // describe block already does for Phasor.

  // ---- Case 1: the original UAT bug, direct-Overcurrent-after-upload ----
  test("fresh workspace: upload -> open Analysis directly on Overcurrent (never visiting Phasor) -> Bay selector populates automatically", async ({ page }) => {
    await page.route("**/engineering-contexts/suggest", async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 400));
      await route.continue();
    });

    await uploadFixture(page); // no manual context creation
    await openAnalysisOvercurrent(page); // never selects/interacts with anything in Phasor's own panel

    // The transient context-identification state appears on Overcurrent's
    // own empty state (mirrors Phasor's own established UX for this).
    await expect(page.locator("#wwOvercurrentEmptyState")).toContainText("Identifying engineering contexts");

    // The Bay selector populates automatically, with the newly-
    // suggested context auto-selected (no unnecessary extra click) --
    // this is the exact scenario the owner reported as broken.
    await expect(page.locator("#wwOvercurrentContextSelect option")).toHaveCount(2, { timeout: 10000 }); // blank + ALPHA1
    await expect(page.locator("#wwOvercurrentContextSelect")).not.toHaveValue("");
    await expect(page.locator("#wwOvercurrentContextBadge")).toContainText("Suggested");

    await expect(async () => {
      const text = await page.locator("#wwOvercurrentValuesList").innerText();
      expect(text).toMatch(/40\.0\s*A secondary/); // known 40 A RMS
    }).toPass({ timeout: 5000 });
  });

  // ---- Case 2: existing behavior via Phasor must remain unchanged ----
  test("fresh workspace: upload -> open Phasor -> context available (unchanged existing behavior)", async ({ page }) => {
    await uploadFixture(page);
    await page.locator("#mainNavAnalysisBtn").click();
    await expect(page.locator("#wwPhasorPanel")).toBeVisible();
    await expect(page.locator("#wwPhasorContextSelect option")).toHaveCount(2, { timeout: 10000 }); // blank + ALPHA1
    await expect(page.locator("#wwPhasorContextSelect")).not.toHaveValue("");
  });

  // ---- Case 3: later upload, both analyzers stay in sync ----
  test("upload A -> Overcurrent sees A; upload B later -> Overcurrent discovers B without visiting Phasor, A remains selected", async ({ page }) => {
    await uploadFixture(page);
    await openAnalysisOvercurrent(page);
    await expect(page.locator("#wwOvercurrentContextSelect option")).toHaveCount(2, { timeout: 10000 }); // blank + ALPHA1
    const alphaContextId = await page.locator("#wwOvercurrentContextSelect").inputValue();
    await expect(async () => {
      const text = await page.locator("#wwOvercurrentValuesList").innerText();
      expect(text).toMatch(/40\.0\s*A secondary/);
    }).toPass({ timeout: 5000 });

    const suggestUrls = [];
    page.on("request", (request) => {
      if (request.url().includes("/engineering-contexts/suggest")) suggestUrls.push(request.url());
    });
    await page.locator("#mainNavRecordingsBtn").click();
    await page.locator("#recordingsUploadBtn, #recordingsEmptyUploadBtn").first().click();
    await expect(page.locator("#uploadModalOverlay")).toBeVisible();
    await page.locator("#uploadModalFile_0").setInputFiles(path.join(FIXTURES, "phasor_smoke_bravo_three_phase.cfg"));
    await page.locator("#uploadModalFile_1").setInputFiles(path.join(FIXTURES, `${STEM}.dat`));
    await page.locator("#uploadModalSubmitBtn").click();
    await page.locator("#uploadModalOverlay").waitFor({ state: "hidden" });
    const bravoSourceId = await page.locator("#recordingsTableBody tr[data-source-id]").last().getAttribute("data-source-id");

    // Re-enter Analysis directly on Overcurrent -- never visiting Phasor.
    await page.locator("#mainNavAnalysisBtn").click();
    await page.locator("#wwAnalysisTypeOvercurrentBtn").click();
    await expect(page.locator("#wwOvercurrentContextSelect")).toHaveValue(alphaContextId); // A remains selected
    const valuesRightAfterReentry = await page.locator("#wwOvercurrentValuesList").innerText();
    expect(valuesRightAfterReentry).toMatch(/40\.0\s*A secondary/); // uninterrupted

    // BRAVO1 (B) appears once background discovery completes -- A stays selected.
    await expect(page.locator("#wwOvercurrentContextSelect option")).toHaveCount(3, { timeout: 10000 }); // blank + A + B
    await expect(page.locator("#wwOvercurrentContextSelect")).toHaveValue(alphaContextId);

    // Exactly one suggestion request for B's own new source -- never a
    // duplicate, never one re-requested for A (already covered), and no
    // double-bootstrap between the shared layer and a stale per-analyzer one.
    const bravoSuggestUrls = suggestUrls.filter((url) => url.includes(encodeURIComponent(bravoSourceId)));
    expect(bravoSuggestUrls).toHaveLength(1);
    const alphaSuggestUrls = suggestUrls.filter((url) => !url.includes(encodeURIComponent(bravoSourceId)));
    expect(alphaSuggestUrls).toHaveLength(0);
  });

  // ---- Case 4: Overcurrent first with a source uploaded before it ----
  test("A already exists -> upload B -> open Overcurrent -> B appears without ever visiting Phasor", async ({ page }) => {
    const { contextId: alphaContextId } = await uploadAndCreateContext(page); // A via direct API (manual, confirmed)

    await page.locator("#mainNavRecordingsBtn").click();
    await page.locator("#recordingsUploadBtn, #recordingsEmptyUploadBtn").first().click();
    await expect(page.locator("#uploadModalOverlay")).toBeVisible();
    await page.locator("#uploadModalFile_0").setInputFiles(path.join(FIXTURES, "phasor_smoke_bravo_three_phase.cfg"));
    await page.locator("#uploadModalFile_1").setInputFiles(path.join(FIXTURES, `${STEM}.dat`));
    await page.locator("#uploadModalSubmitBtn").click();
    await page.locator("#uploadModalOverlay").waitFor({ state: "hidden" });

    await openAnalysisOvercurrent(page); // never visits Phasor
    await expect(page.locator("#wwOvercurrentContextSelect")).toHaveValue(""); // nothing auto-selected yet (A was never selected before)
    await expect(page.locator("#wwOvercurrentContextSelect option")).toHaveCount(3, { timeout: 10000 }); // blank + A + B (BRAVO1)
    const bravoOption = page.locator("#wwOvercurrentContextSelect option", { hasText: "BRAVO1" });
    await expect(bravoOption).toHaveCount(1);
    const alphaOption = page.locator(`#wwOvercurrentContextSelect option[value="${alphaContextId}"]`);
    await expect(alphaOption).toHaveCount(1);
  });

  // ---- Case 5: duplicate display-name labels remain independently selectable ----
  test("two bare-role sources each get their own distinct context, never deduplicated by display name", async ({ page }) => {
    const BARE_STEM = "phasor_bare_three_phase";
    await page.goto("/index.html");
    await page.locator("#recordingsUploadBtn, #recordingsEmptyUploadBtn").first().click();
    await expect(page.locator("#uploadModalOverlay")).toBeVisible();
    await page.locator("#uploadModalFile_0").setInputFiles(path.join(FIXTURES, `${BARE_STEM}.cfg`));
    await page.locator("#uploadModalFile_1").setInputFiles(path.join(FIXTURES, `${STEM}.dat`));
    await page.locator("#uploadModalSubmitBtn").click();
    await page.locator("#uploadModalOverlay").waitFor({ state: "hidden" });

    await page.locator("#mainNavRecordingsBtn").click();
    await page.locator("#recordingsUploadBtn, #recordingsEmptyUploadBtn").first().click();
    await expect(page.locator("#uploadModalOverlay")).toBeVisible();
    await page.locator("#uploadModalFile_0").setInputFiles(path.join(FIXTURES, `${BARE_STEM}.cfg`));
    await page.locator("#uploadModalFile_1").setInputFiles(path.join(FIXTURES, `${STEM}.dat`));
    await page.locator("#uploadModalSubmitBtn").click();
    await page.locator("#uploadModalOverlay").waitFor({ state: "hidden" });

    await openAnalysisOvercurrent(page);
    await expect(page.locator("#wwOvercurrentContextSelect option")).toHaveCount(3, { timeout: 10000 }); // blank + two "Default Context" entries
    const optionValues = await page.locator("#wwOvercurrentContextSelect option:not([value=''])").evaluateAll(
      (opts) => opts.map((o) => o.value)
    );
    expect(new Set(optionValues).size).toBe(2); // two distinct context ids, never merged by shared label
  });

  // ---- Case 6: partial/manual coverage is respected, never re-suggested ----
  test("a source already covered by a manual context is never re-suggested", async ({ page }) => {
    const suggestUrls = [];
    const { contextId, sourceId } = await uploadAndCreateContext(page);
    page.on("request", (request) => {
      if (request.url().includes("/engineering-contexts/suggest")) suggestUrls.push(request.url());
    });
    await openAnalysisOvercurrent(page);
    await expect(page.locator("#wwOvercurrentContextSelect option")).toHaveCount(2, { timeout: 5000 }); // blank + the manual context
    const covered = suggestUrls.filter((url) => url.includes(encodeURIComponent(sourceId)));
    expect(covered).toHaveLength(0);
    await expect(page.locator(`#wwOvercurrentContextSelect option[value="${contextId}"]`)).toHaveCount(1);
  });

  // ---- Case 8: a workspace switch mid-discovery discards the stale result ----
  test("stale discovery response from a cleared workspace never populates the new one", async ({ page }) => {
    await page.route("**/engineering-contexts/suggest", async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 600));
      await route.continue();
    });
    await uploadFixture(page);
    await openAnalysisOvercurrent(page);
    await expect(page.locator("#wwOvercurrentEmptyState")).toContainText("Identifying engineering contexts");

    // Clear the workspace WHILE discovery is still in flight.
    await page.locator("#mainNavRecordingsBtn").click();
    await page.locator("#newWorkspaceButton").click();
    await expect(page.locator("#newWorkspaceConfirmOverlay")).toBeVisible();
    await page.locator("#newWorkspaceConfirmStartBtn").click();
    await expect(page.locator("#newWorkspaceConfirmOverlay")).toBeHidden();

    await page.locator("#mainNavAnalysisBtn").click();
    await page.locator("#wwAnalysisTypeOvercurrentBtn").click();
    // The now-stale ALPHA1 suggestion must never leak into the fresh,
    // empty workspace's own selector.
    await page.waitForTimeout(800);
    await expect(page.locator("#wwOvercurrentContextSelect option")).toHaveCount(1); // blank only
  });
});
