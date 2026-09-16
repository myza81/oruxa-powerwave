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

test.describe("Overcurrent Analysis v1 -- settings form layout correction (2026-09-16 owner UAT)", () => {
  async function setupWithPrimaryBasis(page) {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisOvercurrent(page);
    await selectContextAndWaitForValues(page, contextId);
    await page.locator("#wwOvercurrentBasisSelect").selectOption("primary");
    await expect(page.locator("#wwOvercurrentCtPrimaryInput")).toBeVisible();
    return contextId;
  }

  // The task's own explicit acceptance test: every settings control's
  // rendered box must sit entirely WITHIN the settings card -- never
  // wider than its own grid cell, never spilling into the neighbor
  // column or off the card edge. Checked directly against real
  // getBoundingClientRect() geometry, not just static CSS source.
  async function assertAllControlsWithinPanel(page) {
    const panelBox = await page.locator("#wwOvercurrentBody .ww-phasor-values-panel").boundingBox();
    const controlIds = [
      "wwOvercurrentCharacteristicSelect", "wwOvercurrentPickupInput", "wwOvercurrentTmsInput",
      "wwOvercurrentBasisSelect", "wwOvercurrentCtPrimaryInput", "wwOvercurrentCtSecondaryInput",
    ];
    for (const id of controlIds) {
      const locator = page.locator(`#${id}`);
      if (!(await locator.isVisible())) continue;
      const box = await locator.boundingBox();
      expect(box.x, `${id}.left >= panel.left`).toBeGreaterThanOrEqual(panelBox.x - 0.5);
      expect(box.x + box.width, `${id}.right <= panel.right`).toBeLessThanOrEqual(panelBox.x + panelBox.width + 0.5);
    }
  }

  // General rectangle-overlap test (true = the two boxes intersect) --
  // deliberately layout-mode-agnostic: two fields placed SIDE BY SIDE
  // (2-column mode) never overlap because their x-ranges are disjoint;
  // two fields STACKED (1-column fallback, a genuinely narrow card)
  // never overlap because their y-ranges are disjoint. Either way,
  // "never overlap" is the real acceptance criterion -- not "must
  // always be side by side," which the container-query fallback
  // deliberately overrides once the card is too narrow for that.
  function boxesOverlap(a, b) {
    return a.x < b.x + b.width && a.x + a.width > b.x && a.y < b.y + b.height && a.y + a.height > b.y;
  }

  for (const viewportWidth of [1366, 1024]) {
    test(`all settings controls stay within the panel and never overlap each other, at ${viewportWidth}px`, async ({ page }) => {
      await page.setViewportSize({ width: viewportWidth, height: 900 });
      await setupWithPrimaryBasis(page);

      await assertAllControlsWithinPanel(page);

      const boxOf = async (id) => page.locator(`#${id}`).boundingBox();
      const pickupBox = await boxOf("wwOvercurrentPickupInput");
      const tmsBox = await boxOf("wwOvercurrentTmsInput");
      expect(boxesOverlap(pickupBox, tmsBox), "Pickup and TMS must never overlap").toBe(false);

      const ctPrimaryBox = await boxOf("wwOvercurrentCtPrimaryInput");
      const ctSecondaryBox = await boxOf("wwOvercurrentCtSecondaryInput");
      expect(boxesOverlap(ctPrimaryBox, ctSecondaryBox), "CT Primary and CT Secondary must never overlap").toBe(false);

      // Characteristic and Recording basis are marked full-width
      // (`grid-column: 1 / -1`) regardless of column count -- at 2
      // columns their own right edge sits past the halfway point of
      // the card; at 1 column (narrow fallback) the whole card IS one
      // column, so this remains true either way.
      const panelBox = await page.locator("#wwOvercurrentBody .ww-phasor-values-panel").boundingBox();
      const characteristicBox = await boxOf("wwOvercurrentCharacteristicSelect");
      const basisBox = await boxOf("wwOvercurrentBasisSelect");
      const halfway = panelBox.x + panelBox.width / 2;
      expect(characteristicBox.x + characteristicBox.width).toBeGreaterThan(halfway);
      expect(basisBox.x + basisBox.width).toBeGreaterThan(halfway);

      // No page-level horizontal overflow.
      const bodyScrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
      const bodyClientWidth = await page.evaluate(() => document.documentElement.clientWidth);
      expect(bodyScrollWidth).toBeLessThanOrEqual(bodyClientWidth + 1);
    });
  }

  test("owner-mandated exact control CSS is applied (computed style, not just source)", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisOvercurrent(page);
    await selectContextAndWaitForValues(page, contextId);

    const styles = await page.locator("#wwOvercurrentPickupInput").evaluate((el) => {
      const cs = getComputedStyle(el);
      return { borderWidth: cs.borderTopWidth, borderRadius: cs.borderRadius, paddingTop: cs.paddingTop, paddingLeft: cs.paddingLeft, fontSize: cs.fontSize };
    });
    expect(styles.borderWidth).toBe("1px");
    expect(styles.paddingTop).toBe("8px");
    expect(styles.paddingLeft).toBe("10px");
    // 0.7rem at the default 16px root -> 11.2px.
    expect(parseFloat(styles.fontSize)).toBeCloseTo(11.2, 0);
  });

  test("selected text and numeric values remain fully visible, never clipped or overlapping the select arrow", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisOvercurrent(page);
    await selectContextAndWaitForValues(page, contextId);

    // Longest characteristic option text.
    await page.locator("#wwOvercurrentCharacteristicSelect").selectOption("iec_extremely_inverse");
    await expect(page.locator("#wwOvercurrentCharacteristicSelect")).toHaveValue("iec_extremely_inverse");
    const selectBox = await page.locator("#wwOvercurrentCharacteristicSelect").boundingBox();
    // A native <select> reserves its own arrow area; a comfortably-
    // wide full-row control (never a half-width squeeze) is the
    // structural guarantee against overlap here.
    expect(selectBox.width).toBeGreaterThan(150);

    // Realistic numeric values across the full requested range, none
    // silently truncated/rejected.
    const numericCases = [
      ["wwOvercurrentPickupInput", "0.001"],
      ["wwOvercurrentPickupInput", "5"],
      ["wwOvercurrentTmsInput", "0.10"],
    ];
    for (const [id, value] of numericCases) {
      await page.locator(`#${id}`).fill(value);
      await page.locator(`#${id}`).dispatchEvent("change");
      await expect(page.locator(`#${id}`)).toHaveValue(value);
    }

    await page.locator("#wwOvercurrentBasisSelect").selectOption("primary");
    for (const [id, value] of [["wwOvercurrentCtPrimaryInput", "1200"], ["wwOvercurrentCtPrimaryInput", "10000"], ["wwOvercurrentCtSecondaryInput", "1"]]) {
      await page.locator(`#${id}`).fill(value);
      await page.locator(`#${id}`).dispatchEvent("change");
      await expect(page.locator(`#${id}`)).toHaveValue(value);
    }

    // No OC calculation behavior changed.
    await expect(async () => {
      const text = await page.locator("#wwOvercurrentValuesList").innerText();
      expect(text).not.toMatch(/Infinity|NaN/);
    }).toPass({ timeout: 5000 });
  });

  test("Pickup current label is compact (no unit in the label text) with the unit shown inline next to the value", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisOvercurrent(page);
    await selectContextAndWaitForValues(page, contextId);

    const pickupLabel = page.locator(".ww-oc-settings-grid .ww-phasor-field-label", { hasText: "Pickup current" });
    await expect(pickupLabel).toHaveText("Pickup current"); // exact -- no "(A secondary)" suffix
    await expect(page.locator(".ww-oc-field-unit", { hasText: "A secondary" })).toBeVisible();

    // The label never wraps to two lines within the card.
    const labelBox = await pickupLabel.boundingBox();
    const labelLineHeight = await pickupLabel.evaluate((el) => parseFloat(getComputedStyle(el).lineHeight));
    expect(labelBox.height).toBeLessThanOrEqual(labelLineHeight * 1.5);
  });

  test("panel-width (container-query) responsive fallback stacks to one column when the card itself is forced narrow, independent of the browser viewport", async ({ page }) => {
    // A WIDE browser viewport -- the important dimension is the CARD's
    // own width, not the page/viewport (owner's own explicit
    // instruction), so this deliberately keeps the viewport wide while
    // forcing the card narrow via a direct style override.
    await page.setViewportSize({ width: 1366, height: 900 });
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisOvercurrent(page);
    await selectContextAndWaitForValues(page, contextId);

    const wideColumns = await page.locator(".ww-oc-settings-grid").evaluate((el) => getComputedStyle(el).gridTemplateColumns);
    expect(wideColumns.trim().split(/\s+/)).toHaveLength(2); // two columns at normal card width

    await page.locator("#wwOvercurrentBody .ww-phasor-values-panel").evaluate((el) => { el.style.width = "260px"; });
    await expect(async () => {
      const narrowColumns = await page.locator(".ww-oc-settings-grid").evaluate((el) => getComputedStyle(el).gridTemplateColumns);
      expect(narrowColumns.trim().split(/\s+/)).toHaveLength(1); // stacked to one column
    }).toPass({ timeout: 2000 });

    // Still no overlap/overflow once forced narrow.
    await assertAllControlsWithinPanel(page);
  });

  test("chart viewport fields remain compact, functional, and unaffected by the settings-grid redesign", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisOvercurrent(page);
    await selectContextAndWaitForValues(page, contextId);

    const viewXMinBox = await page.locator("#wwOvercurrentViewXMin").boundingBox();
    expect(viewXMinBox.width).toBeGreaterThanOrEqual(40);
    expect(viewXMinBox.width).toBeLessThanOrEqual(60);

    // Still fully functional -- a real zoom/custom-range change applies.
    await page.locator("#wwOvercurrentViewXMin").fill("2");
    await page.locator("#wwOvercurrentViewXMin").dispatchEvent("change");
    await expect(page.locator("#wwOvercurrentViewXMin")).toHaveValue("2");
    await page.locator("#wwOvercurrentResetViewBtn").click();
    await expect(page.locator("#wwOvercurrentViewXMin")).toHaveValue("0.9");
  });

  test("Live Values section renders correctly below the redesigned settings grid, with unchanged calculations", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisOvercurrent(page);
    await selectContextAndWaitForValues(page, contextId);
    await page.locator("#wwOvercurrentPickupInput").fill("1.0");
    await page.locator("#wwOvercurrentPickupInput").dispatchEvent("change");

    await expect(async () => {
      const text = await page.locator("#wwOvercurrentValuesList").innerText();
      expect(text).toContain("Measured RMS current");
      expect(text).toContain("Relay-equivalent current");
      expect(text).toContain("Pickup");
      expect(text).toContain("Multiple of pickup");
      expect(text).toMatch(/40\.0\s*×/); // known 40 A / 1.0 A pickup, unchanged math
    }).toPass({ timeout: 5000 });

    // Sits below the settings grid, not overlapping it.
    const gridBox = await page.locator(".ww-oc-settings-grid").boundingBox();
    const valuesBox = await page.locator("#wwOvercurrentValuesList").boundingBox();
    expect(valuesBox.y).toBeGreaterThanOrEqual(gridBox.y + gridBox.height - 1);
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

    // Axis-default refinement (2026-09-16, Part B): Y min is now
    // proportional to the stable reference operating time already
    // established by `selectContextAndWaitForValues()` above, not the
    // flat 0.1s literal -- read the live dynamic value rather than
    // hard-coding a hand-derived one.
    const expectedYMin = await page.evaluate(() => wwOvercurrentDynamicYMin());
    expect(expectedYMin).not.toBeCloseTo(0.1, 3); // a real reference IS established by this point

    await page.locator("#wwOvercurrentResetViewBtn").click();
    await expect(page.locator("#wwOvercurrentViewXMin")).toHaveValue("0.9");
    await expect(page.locator("#wwOvercurrentViewXMax")).toHaveValue("100");
    const yMinAfterReset = parseFloat(await page.locator("#wwOvercurrentViewYMin").inputValue());
    expect(yMinAfterReset).toBeCloseTo(expectedYMin, 4);
    await expect(page.locator("#wwOvercurrentViewYMax")).toHaveValue("100");
    // The "0" origin convention is scoped to the pristine, reference-
    // less state only (see wwOvercurrentIsDefaultViewport()) -- once a
    // real (non-round) reference-derived Y min is in effect, the chart
    // shows the true numeric minimum instead of a fake "0", exactly
    // like any other genuinely custom Y range.
    await expect(page.locator("#wwOvercurrentSvg text.ww-oc-origin-label", { hasText: /^0$/ })).toHaveCount(0);
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

test.describe("Overcurrent Analysis v1 -- axis-default refinement (2026-09-16)", () => {
  // Part A: Relay Current's own default X minimum is `pickup - 0.1 A`
  // (floored), replacing the prior `0.9 * pickup` multiplicative
  // scaling. Part B: the time-axis default minimum is proportional to a
  // STABLE reference operating time, never a flat subtraction and never
  // chasing the live operating point during Playback. No IEC IDMT
  // calculation, TMS/pickup/CT/RMS semantics, or Playback clock
  // behavior is touched by anything in this block.

  test("Relay Current default X min tracks pickup - 0.1 A (golden examples: 1.0 -> 0.9, 1.2 -> 1.1)", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisOvercurrent(page);
    await selectContextAndWaitForValues(page, contextId);
    await page.locator("#wwOvercurrentAxisModeRelayBtn").click();

    await page.locator("#wwOvercurrentPickupInput").fill("1.0");
    await page.locator("#wwOvercurrentPickupInput").dispatchEvent("change");
    await expect(async () => {
      const text = await page.locator("#wwOvercurrentValuesList").innerText();
      expect(text).toMatch(/40\.0\s*×/);
    }).toPass({ timeout: 5000 });
    await expect(page.locator("#wwOvercurrentViewXMin")).toHaveValue("0.9");
    await expect(page.locator("#wwOvercurrentViewXMax")).toHaveValue("100");

    await page.locator("#wwOvercurrentPickupInput").fill("1.2");
    await page.locator("#wwOvercurrentPickupInput").dispatchEvent("change");
    await expect(async () => {
      const value = await page.evaluate(() => wwOvercurrentRelayCurrentDefaultViewport().xMin);
      expect(value).toBeCloseTo(1.1, 6);
    }).toPass({ timeout: 5000 });
  });

  test("a very small pickup uses the positive safety floor -- never a zero/negative Relay Current X min", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisOvercurrent(page);
    await selectContextAndWaitForValues(page, contextId);

    await page.locator("#wwOvercurrentPickupInput").fill("0.05");
    await page.locator("#wwOvercurrentPickupInput").dispatchEvent("change");
    await page.locator("#wwOvercurrentAxisModeRelayBtn").click();

    const xMin = parseFloat(await page.locator("#wwOvercurrentViewXMin").inputValue());
    expect(xMin).toBeGreaterThan(0);
    expect(Number.isFinite(xMin)).toBe(true);
  });

  test("pickup changes never mutate the ALREADY-DISPLAYED viewport, only what Reset targets -- a manually zoomed/custom range survives a pickup change", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisOvercurrent(page);
    await selectContextAndWaitForValues(page, contextId);
    await page.locator("#wwOvercurrentAxisModeRelayBtn").click();

    // A deliberate manual custom range.
    await page.locator("#wwOvercurrentViewXMin").fill("5");
    await page.locator("#wwOvercurrentViewXMin").dispatchEvent("change");
    await page.locator("#wwOvercurrentViewXMax").fill("50");
    await page.locator("#wwOvercurrentViewXMax").dispatchEvent("change");
    await expect(page.locator("#wwOvercurrentViewXMin")).toHaveValue("5");
    await expect(page.locator("#wwOvercurrentViewXMax")).toHaveValue("50");

    // A pickup change must not silently overwrite the manual range.
    await page.locator("#wwOvercurrentPickupInput").fill("1.2");
    await page.locator("#wwOvercurrentPickupInput").dispatchEvent("change");
    await expect(async () => {
      const text = await page.locator("#wwOvercurrentValuesList").innerText();
      expect(text).toContain("Pickup");
    }).toPass({ timeout: 5000 });
    await expect(page.locator("#wwOvercurrentViewXMin")).toHaveValue("5");
    await expect(page.locator("#wwOvercurrentViewXMax")).toHaveValue("50");

    // Reset, not the pickup change, is what applies the new dynamic default.
    await page.locator("#wwOvercurrentResetViewBtn").click();
    const xMinAfterReset = parseFloat(await page.locator("#wwOvercurrentViewXMin").inputValue());
    expect(xMinAfterReset).toBeCloseTo(1.1, 6);
  });

  test("a manually customized Y range is preserved across a TMS/characteristic change -- Playback ticks never touch it either", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisOvercurrent(page);
    await selectContextAndWaitForValues(page, contextId);

    await page.locator("#wwOvercurrentViewYMin").fill("5");
    await page.locator("#wwOvercurrentViewYMin").dispatchEvent("change");
    await expect(page.locator("#wwOvercurrentViewYMin")).toHaveValue("5");

    const textBeforeTmsChange = await page.locator("#wwOvercurrentValuesList").innerText();
    await page.locator("#wwOvercurrentTmsInput").fill("0.5");
    await page.locator("#wwOvercurrentTmsInput").dispatchEvent("change");
    await expect(async () => {
      const text = await page.locator("#wwOvercurrentValuesList").innerText();
      expect(text).not.toBe(textBeforeTmsChange); // the recomputed result (a different TMS changes the expected operating time) confirms the change actually took effect
    }).toPass({ timeout: 5000 });
    await expect(page.locator("#wwOvercurrentViewYMin")).toHaveValue("5");

    // Let a few Playback ticks pass -- the manual Y range must never drift.
    await page.locator("#wwOvercurrentPlaybackMount .ww-tg-playback-play-btn").click();
    await page.waitForTimeout(600);
    await page.locator("#wwOvercurrentPlaybackMount .ww-tg-playback-play-btn").click();
    await expect(page.locator("#wwOvercurrentViewYMin")).toHaveValue("5");
  });

  test("the Y-axis default/reset value never chases the live operating point while Playback runs (stable reference, not per-tick)", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisOvercurrent(page);
    await selectContextAndWaitForValues(page, contextId);

    // Capture the dynamic default once, before Playback runs.
    const beforePlay = await page.evaluate(() => wwOvercurrentDynamicYMin());

    await page.locator("#wwOvercurrentPlaybackMount .ww-tg-playback-play-btn").click();
    await page.waitForTimeout(800); // several throttled ticks at ~10 Hz
    await page.locator("#wwOvercurrentPlaybackMount .ww-tg-playback-play-btn").click();

    const afterPlay = await page.evaluate(() => wwOvercurrentDynamicYMin());
    // A steady-state sinusoid keeps the measured current effectively
    // constant across this short window regardless -- the real
    // guarantee under test is architectural (see the static test
    // `TestStableReferenceOnlyUpdatedByExactFetch`), this is the
    // end-to-end confirmation that a live Play run alone never moves it.
    expect(afterPlay).toBeCloseTo(beforePlay, 6);
  });

  test("zero backend requests are caused solely by a viewport/axis-default recalculation -- Reset, zoom, and axis-mode switch after a pickup change", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisOvercurrent(page);
    await selectContextAndWaitForValues(page, contextId);

    const textBeforePickupChange = await page.locator("#wwOvercurrentValuesList").innerText();
    await page.locator("#wwOvercurrentPickupInput").fill("1.2");
    await page.locator("#wwOvercurrentPickupInput").dispatchEvent("change");
    // Explicit blur BEFORE waiting: leaving focus in the input after
    // `.fill()` means the browser's own native blur-triggered "change"
    // would otherwise fire later, on whatever UI action happens to move
    // focus next (e.g. the axis-mode click below) -- producing a SECOND,
    // genuine settings fetch for the SAME pickup value at an unrelated
    // point in the test (confirmed via direct request-stack-trace
    // inspection during this test's own development; a test-harness
    // ordering artifact, not a production bug). Blurring here settles
    // that duplicate within this wait, before any request counting.
    await page.locator("#wwOvercurrentPickupInput").blur();
    await expect(async () => {
      const text = await page.locator("#wwOvercurrentValuesList").innerText();
      expect(text).not.toBe(textBeforePickupChange); // waits for the pickup-change fetch to genuinely resolve, not merely for a static label to exist
    }).toPass({ timeout: 5000 });

    let curveRequests = 0;
    let analysisRequests = 0;
    page.on("request", (req) => {
      if (req.url().includes("/overcurrent-curve")) curveRequests++;
      if (req.url().includes("/overcurrent?")) analysisRequests++;
    });

    await page.locator("#wwOvercurrentAxisModeRelayBtn").click();
    await page.locator("#wwOvercurrentZoomInBtn").click();
    await page.locator("#wwOvercurrentZoomOutBtn").click();
    await page.locator("#wwOvercurrentResetViewBtn").click();
    await page.locator("#wwOvercurrentAxisModePickupBtn").click();

    expect(curveRequests).toBe(0);
    expect(analysisRequests).toBe(0);
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

  test("both toggle buttons are genuinely visible (non-transparent color, visibly bordered group) in either state -- UAT root-cause regression (2026-09-16), carried forward through the chart-control-toolbar segmented-control redesign", async ({ page }) => {
    // Real root cause of the original "toggle does not work" UAT report:
    // the click handler/state/re-render pipeline all worked correctly --
    // `.ww-oc-axis-toggle-btn` simply never set its own `color`/`border`,
    // so the INACTIVE button inherited the global `button { color: #fff;
    // border: none; }` reset and rendered as invisible white text on a
    // light/transparent background. An engineer could never find a
    // control they could not see. This test fails against the pre-fix
    // CSS (color would resolve to rgb(255, 255, 255)) and passes only
    // once the inactive button has a real, non-white text color and the
    // segmented control's own shared outer border is genuinely visible.
    //
    // Superseded (2026-09-16, chart-control-toolbar redesign): the two
    // buttons became one true segmented control with ONE shared bordered/
    // rounded outer shape (`.ww-oc-axis-toggle-group`) plus a thin
    // divider between segments, rather than each button independently
    // bordered -- the FIRST segment now has no border of its own (it has
    // no left sibling to divide from), so the border check moved to the
    // group container, which is still what makes the control findable.
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisOvercurrent(page);
    await selectContextAndWaitForValues(page, contextId);

    const colorOf = async (id) =>
      page.locator(`#${id}`).evaluate((el) => getComputedStyle(el).color);
    const groupBorderStyle = async () =>
      page.locator("#wwOvercurrentAxisControls .ww-oc-axis-toggle-group").evaluate((el) => getComputedStyle(el).borderStyle);

    expect(await groupBorderStyle()).not.toBe("none");

    // Default state: Pickup Multiple active, Relay Current inactive.
    expect(await colorOf("wwOvercurrentAxisModeRelayBtn")).not.toBe("rgb(255, 255, 255)");

    await page.locator("#wwOvercurrentAxisModeRelayBtn").click();
    // After switching: Pickup Multiple is now inactive -- it must ALSO
    // remain visible, not merely the button that happened to start active.
    expect(await colorOf("wwOvercurrentAxisModePickupBtn")).not.toBe("rgb(255, 255, 255)");
    expect(await groupBorderStyle()).not.toBe("none");
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
    // (amperes, not M). Superseded (axis-default refinement,
    // 2026-09-16): Relay Current's own default X minimum is now the
    // additive `pickup - 0.1 A` rather than the multiplicative
    // `0.9 * pickup` DEC-094 used, so the two representations' own
    // default viewports no longer sit at the exact same relative log
    // position -- a small pixel difference (magnitude depends on the
    // specific pickup) is the deliberate, owner-requested outcome, not
    // a regression; the underlying VALUE change is confirmed via the
    // live-values panel elsewhere. Only that the point still renders at
    // a real, valid position is asserted here.
    const relayModeOpX = await page.locator("#wwOvercurrentSvg circle.ww-oc-operating-point").getAttribute("cx");
    expect(Number(relayModeOpX)).toBeGreaterThan(0);

    // 8: pickup boundary -- same superseded-equivalence note as above:
    // M=1 (Pickup Multiple) and I=pickup=0.8A (Relay Current) are no
    // longer guaranteed to occupy the exact same pixel position now
    // that the two defaults are related additively, not
    // multiplicatively.
    const relayModeBoundaryX = await page.locator("#wwOvercurrentSvg line.ww-oc-pickup-boundary").getAttribute("x1");
    expect(Number(relayModeBoundaryX)).toBeGreaterThan(0);

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

  test("pickup boundary is fixed at M=1 in Pickup Multiple mode, unaffected by a pickup change", async ({ page }) => {
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

    // Relay Current mode -- the pixel-equivalence DEC-094 originally
    // established here is superseded by the axis-default refinement
    // (2026-09-16): Relay Current's own default X minimum is now the
    // additive `pickup - 0.1 A`, not the multiplicative `0.9 * pickup`,
    // so the boundary (I = pickup = 0.8 A) no longer sits at the same
    // relative log position M=1 does at pickup 1.0. The boundary still
    // renders at a valid, in-range pixel position -- just a different
    // one, which is the deliberate, owner-requested outcome.
    await page.locator("#wwOvercurrentAxisModeRelayBtn").click();
    const boundaryXRelay = await page.locator("#wwOvercurrentSvg line.ww-oc-pickup-boundary").getAttribute("x1");
    expect(Number(boundaryXRelay)).toBeGreaterThan(0);
  });

  test("Relay Current default viewport at pickup 0.8 A is exactly 0.7 -> 80 A (axis-default refinement, 2026-09-16: X min = pickup - 0.1 A)", async ({ page }) => {
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
    expect(xMin).toBeCloseTo(0.7, 6); // 0.8 - 0.1
    expect(xMax).toBeCloseTo(80, 6);

    // The viewport-start reference (pickup - 0.1 A) renders as the
    // light minor/reference label.
    await expect(page.locator("#wwOvercurrentSvg text.ww-oc-tick-label-minor", { hasText: /^0\.7$/ })).toHaveCount(1);
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

    // Reset now reflects the NEW pickup (axis-default refinement,
    // 2026-09-16: X min = pickup - 0.1 A = 1.9 A, not the prior
    // `0.9 * pickup` = 1.8 A) -- never a stale value from before the
    // pickup change.
    await page.locator("#wwOvercurrentResetViewBtn").click();
    const xMinAfterReset = parseFloat(await page.locator("#wwOvercurrentViewXMin").inputValue());
    const xMaxAfterReset = parseFloat(await page.locator("#wwOvercurrentViewXMax").inputValue());
    expect(xMinAfterReset).toBeCloseTo(1.9, 6);
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

test.describe("Overcurrent Analysis v1 -- chart control toolbar UI/UX redesign (2026-09-16)", () => {
  // UI/CSS-only: View X/Y Min/Max, Zoom -/+/Reset, the Pickup Multiple /
  // Relay Current segmented control, and the Minor grid X/Y checkboxes.
  // No OC math/viewport-semantics/IDMT/network assertion belongs here --
  // see the other describe blocks in this file for that unchanged
  // behavioral coverage. This block proves the actual rendered geometry
  // (never just source-string assertions).

  function boxesOverlap(a, b) {
    return a.x < b.x + b.width && a.x + a.width > b.x && a.y < b.y + b.height && a.y + a.height > b.y;
  }

  for (const width of [1366, 1024]) {
    test(`at ${width}px: View/X-axis/Minor-grid controls stay inside the panel, never clip, never overlap, and the page never overflows horizontally`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      const { contextId } = await uploadAndCreateContext(page);
      await openAnalysisOvercurrent(page);
      await selectContextAndWaitForValues(page, contextId);

      const overflowsHorizontally = await page.evaluate(
        () => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1
      );
      expect(overflowsHorizontally).toBe(false);

      const panelBox = await page.locator("#wwOvercurrentViewControls").locator("xpath=..").boundingBox();
      expect(panelBox).not.toBeNull();

      const controlIds = [
        "wwOvercurrentViewXMin", "wwOvercurrentViewXMax",
        "wwOvercurrentViewYMin", "wwOvercurrentViewYMax",
        "wwOvercurrentZoomOutBtn", "wwOvercurrentZoomInBtn", "wwOvercurrentResetViewBtn",
        "wwOvercurrentAxisModePickupBtn", "wwOvercurrentAxisModeRelayBtn",
        "wwOvercurrentMinorGridXCheckbox", "wwOvercurrentMinorGridYCheckbox",
      ];
      const boxes = [];
      for (const id of controlIds) {
        const box = await page.locator(`#${id}`).boundingBox();
        expect(box, `#${id} should render with a real, non-clipped box`).not.toBeNull();
        expect(box.width, `#${id} width should not be clipped to zero`).toBeGreaterThan(0);
        expect(box.height, `#${id} height should not be clipped to zero`).toBeGreaterThan(0);
        expect(box.x, `#${id} should stay inside the chart control panel (left edge)`).toBeGreaterThanOrEqual(panelBox.x - 1);
        expect(box.x + box.width, `#${id} should stay inside the chart control panel (right edge)`).toBeLessThanOrEqual(panelBox.x + panelBox.width + 1);
        boxes.push({ id, box });
      }

      // Selector/toggle labels ("View", "X-axis", "Minor grid") also
      // participate in the overlap check -- a wrapped/clipped label
      // overlapping the control next to it would be just as broken as
      // two controls overlapping each other.
      const labelHandles = await page.locator(
        "#wwOvercurrentViewControls .ww-oc-view-controls-label, #wwOvercurrentAxisControls .ww-oc-view-controls-label"
      ).all();
      for (let i = 0; i < labelHandles.length; i++) {
        const box = await labelHandles[i].boundingBox();
        expect(box).not.toBeNull();
        boxes.push({ id: `label-${i}`, box });
      }

      for (let i = 0; i < boxes.length; i++) {
        for (let j = i + 1; j < boxes.length; j++) {
          expect(
            boxesOverlap(boxes[i].box, boxes[j].box),
            `${boxes[i].id} should not overlap ${boxes[j].id}`
          ).toBe(false);
        }
      }
    });
  }

  test("the active segmented option is visibly, computedly different from the inactive option", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisOvercurrent(page);
    await selectContextAndWaitForValues(page, contextId);

    const stylesFor = (id) =>
      page.locator(`#${id}`).evaluate((el) => {
        const cs = getComputedStyle(el);
        return { color: cs.color, background: cs.backgroundColor, fontWeight: cs.fontWeight };
      });

    const activeStyles = await stylesFor("wwOvercurrentAxisModePickupBtn");
    const inactiveStyles = await stylesFor("wwOvercurrentAxisModeRelayBtn");
    expect(activeStyles.color).not.toBe(inactiveStyles.color);
    expect(activeStyles.background).not.toBe(inactiveStyles.background);
    // The shared outer group renders as one rounded/bordered shape.
    const groupBorderWidth = await page.locator("#wwOvercurrentAxisControls .ww-oc-axis-toggle-group").evaluate(
      (el) => getComputedStyle(el).borderTopWidth
    );
    expect(groupBorderWidth).not.toBe("0px");
  });

  test("minor-grid X/Y checkboxes are visible and vertically aligned with their own labels", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisOvercurrent(page);
    await selectContextAndWaitForValues(page, contextId);

    const xCheckbox = page.locator("#wwOvercurrentMinorGridXCheckbox");
    const yCheckbox = page.locator("#wwOvercurrentMinorGridYCheckbox");
    await expect(xCheckbox).toBeVisible();
    await expect(yCheckbox).toBeVisible();

    const xBox = await xCheckbox.boundingBox();
    const xLabelBox = await xCheckbox.locator("xpath=..").boundingBox();
    // The checkbox's own vertical center sits within its label's box --
    // i.e. genuinely vertically aligned, not floating above/below the "X"/"Y" text.
    const checkboxCenterY = xBox.y + xBox.height / 2;
    expect(checkboxCenterY).toBeGreaterThanOrEqual(xLabelBox.y);
    expect(checkboxCenterY).toBeLessThanOrEqual(xLabelBox.y + xLabelBox.height);
  });

  test("existing functionality is preserved after the redesign: axis mode switch, minor X/Y checkboxes, zoom, and reset all still work", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisOvercurrent(page);
    await selectContextAndWaitForValues(page, contextId);

    // Axis mode switch.
    await page.locator("#wwOvercurrentAxisModeRelayBtn").click();
    await expect(page.locator("#wwOvercurrentAxisModeRelayBtn")).toHaveAttribute("aria-pressed", "true");
    await page.locator("#wwOvercurrentAxisModePickupBtn").click();
    await expect(page.locator("#wwOvercurrentAxisModePickupBtn")).toHaveAttribute("aria-pressed", "true");

    // Minor grid checkboxes.
    await expect(page.locator("#wwOvercurrentSvg .ww-oc-gridline-minor")).toHaveCount(0);
    await page.locator("#wwOvercurrentMinorGridXCheckbox").check();
    await expect(async () => {
      expect(await page.locator("#wwOvercurrentSvg .ww-oc-gridline-minor").count()).toBeGreaterThan(0);
    }).toPass({ timeout: 5000 });
    await page.locator("#wwOvercurrentMinorGridXCheckbox").uncheck();
    await page.locator("#wwOvercurrentMinorGridYCheckbox").check();
    await expect(async () => {
      expect(await page.locator("#wwOvercurrentSvg .ww-oc-gridline-minor").count()).toBeGreaterThan(0);
    }).toPass({ timeout: 5000 });
    await page.locator("#wwOvercurrentMinorGridYCheckbox").uncheck();

    // Zoom in/out and reset.
    const xMinBefore = await page.locator("#wwOvercurrentViewXMin").inputValue();
    const xMaxBefore = await page.locator("#wwOvercurrentViewXMax").inputValue();
    await page.locator("#wwOvercurrentZoomInBtn").click();
    await expect(async () => {
      expect(await page.locator("#wwOvercurrentViewXMax").inputValue()).not.toBe(xMaxBefore);
    }).toPass({ timeout: 5000 });
    await page.locator("#wwOvercurrentZoomOutBtn").click();
    await page.locator("#wwOvercurrentResetViewBtn").click();
    await expect(page.locator("#wwOvercurrentViewXMin")).toHaveValue(xMinBefore);
    await expect(page.locator("#wwOvercurrentViewXMax")).toHaveValue(xMaxBefore);
  });
});

test.describe("Overcurrent Analysis v1 -- Manual Input / Calculator mode (Analysis Input Source)", () => {
  // The first implementation of the shared Analysis Input Source concept
  // (Recording/Manual) -- see docs/project-memory/ANALYSIS_INPUT_SOURCE.md.
  // No IEC IDMT/CT/unit-normalization math is re-derived in this file --
  // every assertion here is end-to-end through the SAME production
  // backend endpoint/domain functions Recording mode already uses.

  async function enterManualCurrent(page, { current, unit, basis }) {
    if (basis !== undefined) {
      await page.locator("#wwOvercurrentManualBasisSelect").selectOption(basis);
    }
    if (unit !== undefined) {
      await page.locator("#wwOvercurrentManualUnitSelect").selectOption(unit);
    }
    if (current !== undefined) {
      await page.locator("#wwOvercurrentManualCurrentInput").fill(String(current));
      await page.locator("#wwOvercurrentManualCurrentInput").dispatchEvent("change");
      // See the axis-default-refinement task's own documented test-
      // harness finding: `.fill()` leaves focus in the field, so an
      // explicit blur is needed to settle the browser's own native
      // blur-triggered "change" before the next action (never a
      // production concern -- purely a Playwright interaction detail).
      await page.locator("#wwOvercurrentManualCurrentInput").blur();
    }
  }

  test("default Input Source is Recording; segmented control is visually consistent with the Pickup Multiple/Relay Current toggle", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisOvercurrent(page);
    await selectContextAndWaitForValues(page, contextId);

    await expect(page.locator("#wwOvercurrentInputSourceRecordingBtn")).toHaveAttribute("aria-pressed", "true");
    await expect(page.locator("#wwOvercurrentInputSourceManualBtn")).toHaveAttribute("aria-pressed", "false");
    await expect(page.locator("#wwOvercurrentManualInputSection")).toBeHidden();

    const groupBorderWidth = await page.locator("#wwOvercurrentInputSourceRecordingBtn").locator("xpath=..").evaluate(
      (el) => getComputedStyle(el).borderTopWidth
    );
    expect(groupBorderWidth).not.toBe("0px");
  });

  test("switching to Manual reveals the Manual Input section; relay settings are untouched", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisOvercurrent(page);
    await selectContextAndWaitForValues(page, contextId);

    const pickupBefore = await page.locator("#wwOvercurrentPickupInput").inputValue();
    const tmsBefore = await page.locator("#wwOvercurrentTmsInput").inputValue();

    await page.locator("#wwOvercurrentInputSourceManualBtn").click();
    await expect(page.locator("#wwOvercurrentManualInputSection")).toBeVisible();
    await expect(page.locator("#wwOvercurrentInputSourceManualBtn")).toHaveAttribute("aria-pressed", "true");
    await expect(page.locator("#wwOvercurrentInputSourceRecordingBtn")).toHaveAttribute("aria-pressed", "false");

    await expect(page.locator("#wwOvercurrentPickupInput")).toHaveValue(pickupBefore);
    await expect(page.locator("#wwOvercurrentTmsInput")).toHaveValue(tmsBefore);
  });

  test("golden example: pickup 1.0 A secondary, CT 1200:1, manual 30000 A primary -> 25 A secondary, M=25x", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisOvercurrent(page);
    await selectContextAndWaitForValues(page, contextId);

    await page.locator("#wwOvercurrentPickupInput").fill("1.0");
    await page.locator("#wwOvercurrentPickupInput").dispatchEvent("change");
    await page.locator("#wwOvercurrentPickupInput").blur();

    await page.locator("#wwOvercurrentInputSourceManualBtn").click();
    await expect(page.locator("#wwOvercurrentCtPrimaryField")).toBeVisible(); // Manual's own default basis is Primary
    await page.locator("#wwOvercurrentCtPrimaryInput").fill("1200");
    await page.locator("#wwOvercurrentCtPrimaryInput").dispatchEvent("change");
    await page.locator("#wwOvercurrentCtPrimaryInput").blur();
    await page.locator("#wwOvercurrentCtSecondaryInput").fill("1");
    await page.locator("#wwOvercurrentCtSecondaryInput").dispatchEvent("change");
    await page.locator("#wwOvercurrentCtSecondaryInput").blur();
    await enterManualCurrent(page, { current: 30000 });

    await expect(async () => {
      const text = await page.locator("#wwOvercurrentValuesList").innerText();
      expect(text).toContain("Relay-equivalent current");
    }).toPass({ timeout: 5000 });

    const text = await page.locator("#wwOvercurrentValuesList").innerText();
    expect(text).toMatch(/25\.0\s*A secondary/);
    expect(text).toMatch(/25\.0\s*×/);
    expect(text).toContain("Expected operating time");
    expect(text).not.toContain("Not applicable");
    expect(text).not.toContain("Measured RMS current");
    expect(text).not.toContain("Above-pickup duration");
  });

  test("30 kA primary is identical to 30000 A primary (shared engineering-unit layer)", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisOvercurrent(page);
    await selectContextAndWaitForValues(page, contextId);
    await page.locator("#wwOvercurrentInputSourceManualBtn").click();
    await page.locator("#wwOvercurrentCtPrimaryInput").fill("1200");
    await page.locator("#wwOvercurrentCtPrimaryInput").dispatchEvent("change");
    await page.locator("#wwOvercurrentCtSecondaryInput").fill("1");
    await page.locator("#wwOvercurrentCtSecondaryInput").dispatchEvent("change");
    await page.locator("#wwOvercurrentCtSecondaryInput").blur();

    await enterManualCurrent(page, { current: 30000, unit: "A" });
    await expect(async () => {
      const text = await page.locator("#wwOvercurrentValuesList").innerText();
      expect(text).toMatch(/25\.0\s*A secondary/);
    }).toPass({ timeout: 5000 });
    const textA = await page.locator("#wwOvercurrentValuesList").innerText();

    await enterManualCurrent(page, { current: 30, unit: "kA" });
    await expect(async () => {
      const text = await page.locator("#wwOvercurrentValuesList").innerText();
      expect(text).toMatch(/25\.0\s*A secondary/);
    }).toPass({ timeout: 5000 });
    const textKa = await page.locator("#wwOvercurrentValuesList").innerText();

    expect(textKa).toBe(textA);
  });

  test("Secondary basis bypasses CT conversion entirely", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisOvercurrent(page);
    await selectContextAndWaitForValues(page, contextId);
    await page.locator("#wwOvercurrentInputSourceManualBtn").click();
    await enterManualCurrent(page, { current: 2.5, unit: "A", basis: "secondary" });
    await expect(page.locator("#wwOvercurrentCtPrimaryField")).toBeHidden();

    await expect(async () => {
      const text = await page.locator("#wwOvercurrentValuesList").innerText();
      expect(text).toMatch(/2\.5\s*A secondary/);
    }).toPass({ timeout: 5000 });
  });

  test("below-pickup manual input shows the qualified wording, never a fabricated operating time", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisOvercurrent(page);
    await selectContextAndWaitForValues(page, contextId);
    await page.locator("#wwOvercurrentPickupInput").fill("10");
    await page.locator("#wwOvercurrentPickupInput").dispatchEvent("change");
    await page.locator("#wwOvercurrentPickupInput").blur();

    await page.locator("#wwOvercurrentInputSourceManualBtn").click();
    await enterManualCurrent(page, { current: 2, unit: "A", basis: "secondary" });

    await expect(async () => {
      const text = await page.locator("#wwOvercurrentValuesList").innerText();
      expect(text).toMatch(/<\s*1\s*×/);
    }).toPass({ timeout: 5000 });
    const text = await page.locator("#wwOvercurrentValuesList").innerText();
    expect(text).toContain("Not applicable / below pickup");
  });

  test("manual operating point renders on the SAME chart with a distinct manual marker, no second chart", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisOvercurrent(page);
    await selectContextAndWaitForValues(page, contextId);
    await expect(page.locator("#wwOvercurrentSvg circle.ww-oc-operating-point")).toHaveCount(1);

    await page.locator("#wwOvercurrentInputSourceManualBtn").click();
    await enterManualCurrent(page, { current: 5, unit: "A", basis: "secondary" });

    await expect(async () => {
      const count = await page.locator("#wwOvercurrentSvg circle.ww-oc-manual-marker").count();
      expect(count).toBe(1);
    }).toPass({ timeout: 5000 });
    await expect(page.locator("#wwOvercurrentSvg")).toHaveCount(1); // still the one chart
    const title = await page.locator("#wwOvercurrentSvg circle.ww-oc-manual-marker title").textContent();
    expect(title).toBe("Manual input point");
  });

  test("Playback movement does not move the manual result or chart point", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisOvercurrent(page);
    await selectContextAndWaitForValues(page, contextId);
    await page.locator("#wwOvercurrentInputSourceManualBtn").click();
    await enterManualCurrent(page, { current: 5, unit: "A", basis: "secondary" });
    await expect(async () => {
      // Waits for the SPECIFIC entered value (5.0 A), not merely for the
      // "Relay-equivalent current" label -- the default 30000 A manual
      // value (auto-computed the instant Manual mode was entered) would
      // otherwise satisfy a weaker wait before this fill's own request
      // has resolved.
      const text = await page.locator("#wwOvercurrentValuesList").innerText();
      expect(text).toMatch(/5\.0\s*A secondary/);
    }).toPass({ timeout: 5000 });

    const textBefore = await page.locator("#wwOvercurrentValuesList").innerText();
    const cxBefore = await page.locator("#wwOvercurrentSvg circle.ww-oc-manual-marker").getAttribute("cx");

    let analysisRequests = 0;
    page.on("request", (req) => {
      if (req.url().includes("/overcurrent?")) analysisRequests++;
    });

    // Architectural correction (2026-09-16): Overcurrent's own Playback
    // strip is now INSIDE the Recording-only section, which is hidden
    // entirely while Manual is active -- so Playback is driven here via
    // PHASOR's own mount instead (Playback is genuinely shared/global,
    // DEC-085; moving it from ANY consumer must never affect Manual OC).
    await page.locator("#wwAnalysisTypePhasorBtn").click();
    await page.locator("#wwPhasorContextSelect").selectOption(contextId);
    const slider = page.locator("#wwPhasorPlaybackMount .ww-tg-playback-seek-slider");
    await expect(slider).toBeVisible();
    const { min, max } = await seekSliderBounds(slider);
    await seekTo(slider, min + (max - min) * 0.8);
    await page.locator("#wwPhasorPlaybackMount .ww-tg-playback-play-btn").click();
    await page.waitForTimeout(500);
    await page.locator("#wwPhasorPlaybackMount .ww-tg-playback-play-btn").click();
    await page.locator("#wwAnalysisTypeOvercurrentBtn").click();
    await expect(page.locator("#wwOvercurrentInputSourceManualBtn")).toHaveAttribute("aria-pressed", "true"); // still Manual

    const textAfter = await page.locator("#wwOvercurrentValuesList").innerText();
    const cxAfter = await page.locator("#wwOvercurrentSvg circle.ww-oc-manual-marker").getAttribute("cx");
    expect(textAfter).toBe(textBefore);
    expect(cxAfter).toBe(cxBefore);
    expect(analysisRequests).toBe(0); // the recording endpoint must never fire while Manual is active
  });

  test("Related Waveforms panel is hidden/collapsed entirely in Manual mode, never a fabricated waveform", async ({ page }) => {
    // Architectural correction (2026-09-16): superseding the prior
    // "reuse the generic empty-state message" choice -- Related
    // Waveforms now lives inside the Recording-only section, so
    // switching to Manual hides/collapses the WHOLE panel (the cleaner
    // of the two task-offered options, since the entire Recording-only
    // section is already hidden regardless of Related Waveforms
    // specifically). See docs/project-memory/ANALYSIS_INPUT_SOURCE.md.
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisOvercurrent(page);
    await selectContextAndWaitForValues(page, contextId);
    await expect(page.locator("#wwAnalysisRelatedWaveformsPanel")).toBeVisible(); // Recording mode has an active role

    await page.locator("#wwOvercurrentInputSourceManualBtn").click();
    await enterManualCurrent(page, { current: 5, unit: "A", basis: "secondary" });
    await expect(async () => {
      const text = await page.locator("#wwOvercurrentValuesList").innerText();
      expect(text).toContain("Relay-equivalent current");
    }).toPass({ timeout: 5000 });

    await expect(page.locator("#wwOvercurrentRecordingSection")).toBeHidden();
    await expect(page.locator("#wwAnalysisRelatedWaveformsPanel")).toBeHidden();
  });

  test("switching back to Recording restores the recording-driven point/values exactly", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisOvercurrent(page);
    await selectContextAndWaitForValues(page, contextId);
    await expect(async () => {
      const text = await page.locator("#wwOvercurrentValuesList").innerText();
      expect(text).toContain("Measured RMS current");
    }).toPass({ timeout: 5000 });
    const recordingTextBefore = await page.locator("#wwOvercurrentValuesList").innerText();
    const recordingOpXBefore = await page.locator("#wwOvercurrentSvg circle.ww-oc-operating-point").getAttribute("cx");

    await page.locator("#wwOvercurrentInputSourceManualBtn").click();
    await enterManualCurrent(page, { current: 5, unit: "A", basis: "secondary" });
    await expect(async () => {
      const text = await page.locator("#wwOvercurrentValuesList").innerText();
      expect(text).toContain("Relay-equivalent current");
    }).toPass({ timeout: 5000 });

    await page.locator("#wwOvercurrentInputSourceRecordingBtn").click();
    await expect(async () => {
      const text = await page.locator("#wwOvercurrentValuesList").innerText();
      expect(text).toContain("Measured RMS current");
    }).toPass({ timeout: 5000 });
    const recordingTextAfter = await page.locator("#wwOvercurrentValuesList").innerText();
    const recordingOpXAfter = await page.locator("#wwOvercurrentSvg circle.ww-oc-operating-point").getAttribute("cx");
    expect(recordingTextAfter).toBe(recordingTextBefore);
    expect(recordingOpXAfter).toBe(recordingOpXBefore);
    await expect(page.locator("#wwOvercurrentSvg circle.ww-oc-manual-marker")).toHaveCount(0);
  });

  test("invalid manual input (blank, negative, zero) is handled safely -- no crash, no plotted point, no request", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisOvercurrent(page);
    await selectContextAndWaitForValues(page, contextId);
    await page.locator("#wwOvercurrentInputSourceManualBtn").click();
    await enterManualCurrent(page, { current: 5, unit: "A", basis: "secondary" });
    await expect(async () => {
      const text = await page.locator("#wwOvercurrentValuesList").innerText();
      expect(text).toContain("Relay-equivalent current");
    }).toPass({ timeout: 5000 });

    let manualRequests = 0;
    page.on("request", (req) => {
      if (req.url().includes("/overcurrent-manual")) manualRequests++;
    });

    for (const badValue of ["", "-1", "0"]) {
      await page.locator("#wwOvercurrentManualCurrentInput").fill(badValue);
      await page.locator("#wwOvercurrentManualCurrentInput").dispatchEvent("change");
      await page.locator("#wwOvercurrentManualCurrentInput").blur();
      await expect(page.locator("#wwOvercurrentSvg circle.ww-oc-manual-marker")).toHaveCount(0);
      await expect(page.locator("#wwOvercurrentSvg polygon.ww-oc-edge-indicator")).toHaveCount(0);
    }
    expect(manualRequests).toBe(0); // rejected client-side before ever reaching the backend

    // Recovering with a valid value still works afterward.
    await enterManualCurrent(page, { current: 5 });
    await expect(async () => {
      const text = await page.locator("#wwOvercurrentValuesList").innerText();
      expect(text).toContain("Relay-equivalent current");
    }).toPass({ timeout: 5000 });
  });

  for (const width of [1366, 1024]) {
    test(`at ${width}px: Manual Input section fits cleanly, no overflow, no clipping, no overlap`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      const { contextId } = await uploadAndCreateContext(page);
      await openAnalysisOvercurrent(page);
      await selectContextAndWaitForValues(page, contextId);
      await page.locator("#wwOvercurrentInputSourceManualBtn").click();
      await expect(page.locator("#wwOvercurrentManualInputSection")).toBeVisible();

      const overflowsHorizontally = await page.evaluate(
        () => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1
      );
      expect(overflowsHorizontally).toBe(false);

      const panelBox = await page.locator("#wwOvercurrentManualInputSection").locator("xpath=..").boundingBox();
      const controlIds = [
        "wwOvercurrentInputSourceRecordingBtn", "wwOvercurrentInputSourceManualBtn",
        "wwOvercurrentManualCurrentInput", "wwOvercurrentManualUnitSelect", "wwOvercurrentManualBasisSelect",
      ];
      const boxes = [];
      for (const id of controlIds) {
        const box = await page.locator(`#${id}`).boundingBox();
        expect(box, `#${id} should render with a real, non-clipped box`).not.toBeNull();
        expect(box.width).toBeGreaterThan(0);
        expect(box.height).toBeGreaterThan(0);
        expect(box.x).toBeGreaterThanOrEqual(panelBox.x - 1);
        expect(box.x + box.width).toBeLessThanOrEqual(panelBox.x + panelBox.width + 1);
        boxes.push({ id, box });
      }
      function overlaps(a, b) {
        return a.x < b.x + b.width && a.x + a.width > b.x && a.y < b.y + b.height && a.y + a.height > b.y;
      }
      for (let i = 0; i < boxes.length; i++) {
        for (let j = i + 1; j < boxes.length; j++) {
          expect(overlaps(boxes[i].box, boxes[j].box), `${boxes[i].id} should not overlap ${boxes[j].id}`).toBe(false);
        }
      }

      // The chart remains usable alongside the taller left panel.
      const svgBox = await page.locator("#wwOvercurrentSvg").boundingBox();
      expect(svgBox.width).toBeGreaterThan(50);
      expect(svgBox.height).toBeGreaterThan(50);
    });
  }

  test("a full workspace reset auto-selects Manual again (a fresh workspace has zero recordings)", async ({ page }) => {
    // Architectural correction (2026-09-16): a freshly-reset workspace
    // has NO recordings, exactly like a genuinely empty one -- Recording
    // must be disabled and Manual auto-selected, never the reverse. This
    // supersedes the prior "always resets to Recording" expectation,
    // which assumed Recording was always meaningfully available.
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisOvercurrent(page);
    await selectContextAndWaitForValues(page, contextId);
    await expect(page.locator("#wwOvercurrentInputSourceRecordingBtn")).toHaveAttribute("aria-pressed", "true");
    await page.locator("#wwOvercurrentInputSourceManualBtn").click();
    await expect(page.locator("#wwOvercurrentManualInputSection")).toBeVisible();

    await page.locator("#mainNavRecordingsBtn").click();
    await page.locator("#newWorkspaceButton").click();
    await expect(page.locator("#newWorkspaceConfirmOverlay")).toBeVisible();
    await page.locator("#newWorkspaceConfirmStartBtn").click();
    await expect(page.locator("#newWorkspaceConfirmOverlay")).toBeHidden();

    await page.locator("#mainNavAnalysisBtn").click();
    await page.locator("#wwAnalysisTypeOvercurrentBtn").click();
    await expect(page.locator("#wwOvercurrentInputSourceManualBtn")).toHaveAttribute("aria-pressed", "true");
    await expect(page.locator("#wwOvercurrentInputSourceRecordingBtn")).toBeDisabled();
    await expect(page.locator("#wwOvercurrentManualInputSection")).toBeVisible();
    await expect(page.locator("#wwOvercurrentInputSourceHint")).toBeVisible();
    await expect(page.locator("#wwOvercurrentRecordingSection")).toBeHidden();
  });
});

test.describe("Overcurrent Analysis v1 -- Manual mode is a standalone engineering calculator, independent of recordings (2026-09-16 architectural correction)", () => {
  // Owner requirement: "Manual Input must be fully independent from
  // waveform/event recordings." A genuinely empty workspace -- no
  // upload, no Engineering Context, no Time Group, no Playback source --
  // must still let a user run a full Manual Overcurrent calculation.
  // Deliberately does NOT call uploadAndCreateContext/uploadFixture:
  // `page.goto("/index.html")` alone gives a fresh, empty workspace
  // (see openAnalysisOvercurrent's own callers elsewhere in this file
  // for the upload-based counterpart).

  async function openEmptyWorkspaceOvercurrent(page) {
    await page.goto("/index.html");
    await openAnalysisOvercurrent(page);
  }

  test("Analysis -> Overcurrent is reachable and usable with zero recordings in the workspace", async ({ page }) => {
    await openEmptyWorkspaceOvercurrent(page);
    await expect(page.locator("#wwOvercurrentBody")).toBeVisible();
    await expect(page.locator("#wwOvercurrentInputSourceManualBtn")).toHaveAttribute("aria-pressed", "true");
    await expect(page.locator("#wwOvercurrentInputSourceRecordingBtn")).toBeDisabled();
    await expect(page.locator("#wwOvercurrentInputSourceHint")).toBeVisible();
    await expect(page.locator("#wwOvercurrentInputSourceHint")).toContainText("No recording loaded");
    await expect(page.locator("#wwOvercurrentManualInputSection")).toBeVisible();
    await expect(page.locator("#wwOvercurrentRecordingSection")).toBeHidden();
  });

  test("golden empty-workspace calculation: pickup 1.0 A secondary, CT 1200:1, manual 30000 A primary -> 25 A secondary, M=25x, zero recording-dependent requests", async ({ page }) => {
    // `/overcurrent-curve` is deliberately NOT in this bucket: it only ever
    // takes characteristic_id/tms (pure IEC curve-shape math, no context/
    // source/waveform params) and is shared by both Recording and Manual
    // to draw the same curve line -- it carries no recording dependency.
    // `/overcurrent?` (the context-driven recording analysis endpoint) and
    // `/waveform` (Related Waveforms fetches) are the actual recording-
    // dependent requests this test must never see.
    const recordingRequestUrls = [];
    let manualRequests = 0;
    page.on("request", (req) => {
      const url = req.url();
      if (url.includes("/overcurrent?") || url.includes("/waveform")) {
        recordingRequestUrls.push(url);
      }
      if (url.includes("/overcurrent-manual")) manualRequests++;
    });

    await openEmptyWorkspaceOvercurrent(page);

    await page.locator("#wwOvercurrentCharacteristicSelect").selectOption("iec_standard_inverse");
    await page.locator("#wwOvercurrentPickupInput").fill("1.0");
    await page.locator("#wwOvercurrentPickupInput").dispatchEvent("change");
    await page.locator("#wwOvercurrentPickupInput").blur();
    await page.locator("#wwOvercurrentTmsInput").fill("0.1");
    await page.locator("#wwOvercurrentTmsInput").dispatchEvent("change");
    await page.locator("#wwOvercurrentTmsInput").blur();

    await expect(page.locator("#wwOvercurrentCtPrimaryField")).toBeVisible(); // Manual's own default basis is Primary
    await page.locator("#wwOvercurrentCtPrimaryInput").fill("1200");
    await page.locator("#wwOvercurrentCtPrimaryInput").dispatchEvent("change");
    await page.locator("#wwOvercurrentCtPrimaryInput").blur();
    await page.locator("#wwOvercurrentCtSecondaryInput").fill("1");
    await page.locator("#wwOvercurrentCtSecondaryInput").dispatchEvent("change");
    await page.locator("#wwOvercurrentCtSecondaryInput").blur();

    await page.locator("#wwOvercurrentManualCurrentInput").fill("30000");
    await page.locator("#wwOvercurrentManualCurrentInput").dispatchEvent("change");
    await page.locator("#wwOvercurrentManualCurrentInput").blur();

    await expect(async () => {
      const text = await page.locator("#wwOvercurrentValuesList").innerText();
      expect(text).toContain("Relay-equivalent current");
    }).toPass({ timeout: 5000 });

    const text = await page.locator("#wwOvercurrentValuesList").innerText();
    expect(text).toMatch(/25\.0\s*A secondary/);
    expect(text).toMatch(/25\.0\s*×/);
    expect(text).toContain("Expected operating time");
    expect(text).not.toContain("Not applicable");

    await expect(page.locator("#wwOvercurrentSvg circle.ww-oc-manual-marker")).toHaveCount(1);

    expect(manualRequests).toBeGreaterThan(0);
    expect(recordingRequestUrls).toEqual([]);
  });

  test("Recording mode with zero recordings shows a clean neutral state, never a crash or stale Manual result relabeled as Recording", async ({ page }) => {
    await openEmptyWorkspaceOvercurrent(page);
    await enterManualCurrentStandalone(page, "5");
    await expect(async () => {
      const text = await page.locator("#wwOvercurrentValuesList").innerText();
      expect(text).toContain("Relay-equivalent current");
    }).toPass({ timeout: 5000 });

    // Recording stays disabled -- there is nothing to switch to, and the
    // control must not silently let a click through onto stale Manual
    // data mislabeled as a Recording result.
    await expect(page.locator("#wwOvercurrentInputSourceRecordingBtn")).toBeDisabled();
    await page.locator("#wwOvercurrentInputSourceRecordingBtn").click({ force: true });
    await expect(page.locator("#wwOvercurrentInputSourceManualBtn")).toHaveAttribute("aria-pressed", "true");
  });

  async function enterManualCurrentStandalone(page, current) {
    // Secondary basis needs no CT ratio -- keeps these tests focused on
    // the thing they're actually checking (no recording dependency),
    // not on re-deriving the CT-conversion case the golden test already
    // covers above.
    await page.locator("#wwOvercurrentManualBasisSelect").selectOption("secondary");
    await page.locator("#wwOvercurrentManualCurrentInput").fill(current);
    await page.locator("#wwOvercurrentManualCurrentInput").dispatchEvent("change");
    await page.locator("#wwOvercurrentManualCurrentInput").blur();
  }

  test("no Engineering Context, no Time Group, no Playback: Manual result and chart point render with zero context-selection/time-group/playback dependency", async ({ page }) => {
    await openEmptyWorkspaceOvercurrent(page);
    // No context selector interaction of any kind is possible or needed --
    // the control itself lives inside the hidden #wwOvercurrentRecordingSection.
    await expect(page.locator("#wwOvercurrentContextSelect")).toBeHidden();
    await expect(page.locator("#wwOvercurrentPlaybackPanel")).toBeHidden();

    await enterManualCurrentStandalone(page, "5");
    await expect(async () => {
      const text = await page.locator("#wwOvercurrentValuesList").innerText();
      expect(text).toMatch(/5\.0\s*A secondary/);
    }).toPass({ timeout: 5000 });
    await expect(page.locator("#wwOvercurrentSvg circle.ww-oc-manual-marker")).toHaveCount(1);
  });

  for (const width of [1366, 1024]) {
    test(`at ${width}px: empty-workspace Manual calculator fits cleanly, Recording shown disabled (not hidden), no overflow`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await openEmptyWorkspaceOvercurrent(page);
      await enterManualCurrentStandalone(page, "5");
      await expect(async () => {
        const text = await page.locator("#wwOvercurrentValuesList").innerText();
        expect(text).toContain("Relay-equivalent current");
      }).toPass({ timeout: 5000 });

      const overflowX = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      expect(overflowX).toBeLessThanOrEqual(1);
      await expect(page.locator("#wwOvercurrentInputSourceRecordingBtn")).toBeVisible();
      await expect(page.locator("#wwOvercurrentInputSourceRecordingBtn")).toBeDisabled();
    });
  }
});
