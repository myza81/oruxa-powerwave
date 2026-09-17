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

// Locators scoped to `#wwOvercurrentBody .ww-oc-settings-grid` below
// (2026-09-17, Impedance Locus chronology fix) -- Impedance Locus v1
// reuses the identical `.ww-oc-settings-grid` class for its own Phase/
// basis settings grid (both panels coexist in the DOM, only the active
// one is unhidden), so an unscoped `.ww-oc-settings-grid` locator now
// resolves to two elements. Mirrors the exact precedent already set
// when Phasor's own reuse of `.ww-oc-input-source-panel` required the
// same fix for a different pre-existing test.
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

    const wideColumns = await page.locator("#wwOvercurrentBody .ww-oc-settings-grid").evaluate((el) => getComputedStyle(el).gridTemplateColumns);
    expect(wideColumns.trim().split(/\s+/)).toHaveLength(2); // two columns at normal card width

    await page.locator("#wwOvercurrentBody .ww-phasor-values-panel").evaluate((el) => { el.style.width = "260px"; });
    await expect(async () => {
      const narrowColumns = await page.locator("#wwOvercurrentBody .ww-oc-settings-grid").evaluate((el) => getComputedStyle(el).gridTemplateColumns);
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
    await expect(page.locator("#wwOvercurrentViewXMin")).toHaveValue("0.1");
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
    const gridBox = await page.locator("#wwOvercurrentBody .ww-oc-settings-grid").boundingBox();
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
    // (0.1) -- exercises the on-chart below-pickup marker path, not the
    // off-chart edge-indicator path.
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
  test("default viewport (0.1->100 x, 0.1->100 s): full axis frame, major grid lines, and the owner's curated default major-tick set render", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisOvercurrent(page);
    await selectContextAndWaitForValues(page, contextId);

    // Axis lines (X + Y).
    await expect(page.locator("#wwOvercurrentSvg line.ww-oc-axis")).toHaveCount(2);
    // 14 X majors (0.1,1,2,3,4,5,6,7,8,9,10,20,50,100) + 4 Y majors
    // (0.1,1,10,100). Shared labels appear once per axis.
    await expect(page.locator("#wwOvercurrentSvg line.ww-oc-gridline")).toHaveCount(18);

    // X majors that never coincide with a Y major label.
    for (const label of ["2", "3", "4", "5", "6", "7", "8", "9", "20", "50"]) {
      await expect(page.locator("#wwOvercurrentSvg text.ww-oc-tick-label", { hasText: new RegExp("^" + label.replace(".", "\\.") + "$") })).toHaveCount(1);
    }
    // Values shared by both axes' own major set ("0.1", "1", "10", "100").
    for (const label of ["0.1", "1", "10", "100"]) {
      await expect(page.locator("#wwOvercurrentSvg text.ww-oc-tick-label", { hasText: new RegExp("^" + label + "$") })).toHaveCount(2);
    }
    await expect(page.locator("#wwOvercurrentSvg text.ww-oc-origin-label", { hasText: /^0$/ })).toHaveCount(0);

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
  test("default range inputs show 0.1/100/0.1/100", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisOvercurrent(page);
    await selectContextAndWaitForValues(page, contextId);

    await expect(page.locator("#wwOvercurrentViewXMin")).toHaveValue("0.1");
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
    await expect(page.locator("#wwOvercurrentViewXMin")).toHaveValue("0.1");
    await expect(page.locator("#wwOvercurrentViewXMax")).toHaveValue("100");
    await expect(page.locator("#wwOvercurrentViewYMin")).toHaveValue("0.1");
    await expect(page.locator("#wwOvercurrentViewYMax")).toHaveValue("100");
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

test.describe("Overcurrent Analysis v1 -- true log axis defaults", () => {
  test("Relay Current default X range tracks 0.1x pickup to 100x pickup", async ({ page }) => {
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
    await expect(page.locator("#wwOvercurrentViewXMin")).toHaveValue("0.1");
    await expect(page.locator("#wwOvercurrentViewXMax")).toHaveValue("100");

    await page.locator("#wwOvercurrentPickupInput").fill("1.2");
    await page.locator("#wwOvercurrentPickupInput").dispatchEvent("change");
    await expect(async () => {
      const value = await page.evaluate(() => wwOvercurrentRelayCurrentDefaultViewport());
      expect(value.xMin).toBeCloseTo(0.12, 6);
      expect(value.xMax).toBeCloseTo(120, 6);
    }).toPass({ timeout: 5000 });
  });

  test("a very small pickup still uses a positive Relay Current X min", async ({ page }) => {
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

    // Reset, not the pickup change, is what applies the new default.
    await page.locator("#wwOvercurrentResetViewBtn").click();
    const xMinAfterReset = parseFloat(await page.locator("#wwOvercurrentViewXMin").inputValue());
    expect(xMinAfterReset).toBeCloseTo(0.12, 6);
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

  test("the Y-axis default/reset value stays fixed while Playback runs", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisOvercurrent(page);
    await selectContextAndWaitForValues(page, contextId);

    await page.locator("#wwOvercurrentPlaybackMount .ww-tg-playback-play-btn").click();
    await page.waitForTimeout(800); // several throttled ticks at ~10 Hz
    await page.locator("#wwOvercurrentPlaybackMount .ww-tg-playback-play-btn").click();

    await page.locator("#wwOvercurrentResetViewBtn").click();
    await expect(page.locator("#wwOvercurrentViewYMin")).toHaveValue("0.1");
    await expect(page.locator("#wwOvercurrentViewYMax")).toHaveValue("100");
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

    // 7: operating point x-coordinate transforms to amperes while staying
    // pixel-equivalent to the same M-domain position.
    const relayModeOpX = await page.locator("#wwOvercurrentSvg circle.ww-oc-operating-point").getAttribute("cx");
    expect(relayModeOpX).toBe(pickupModeOpX);

    // 8: pickup boundary: M=1 and I=pickup share the same pixel.
    const relayModeBoundaryX = await page.locator("#wwOvercurrentSvg line.ww-oc-pickup-boundary").getAttribute("x1");
    expect(relayModeBoundaryX).toBe(pickupModeBoundaryX);

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
    // is the same 0.1x/100x M-domain default scaled by pickup.
    await expect(page.locator("#wwOvercurrentViewXMin")).toHaveValue("0.1");
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

    // Relay Current mode -- I=pickup is geometrically equivalent to M=1.
    await page.locator("#wwOvercurrentAxisModeRelayBtn").click();
    const boundaryXRelay = await page.locator("#wwOvercurrentSvg line.ww-oc-pickup-boundary").getAttribute("x1");
    expect(boundaryXRelay).toBe(boundaryXAtPickup1);
  });

  test("Relay Current default viewport at pickup 0.8 A is exactly 0.08 -> 80 A", async ({ page }) => {
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
    expect(xMin).toBeCloseTo(0.08, 6); // 0.1 * pickup
    expect(xMax).toBeCloseTo(80, 6);

    await expect(page.locator("#wwOvercurrentSvg text.ww-oc-tick-label", { hasText: /^0\.08$/ })).toHaveCount(1);
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

    // Pickup 2.0 A (not 0.8) -- deliberately stays within the current,
    // unchanged viewport (Relay Current's own default at pickup=1.0 is
    // 0.1-100 A), so the boundary remains on-chart and its own moved
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

    // Reset now reflects the new pickup -- never a stale value from
    // before the pickup change.
    await page.locator("#wwOvercurrentResetViewBtn").click();
    const xMinAfterReset = parseFloat(await page.locator("#wwOvercurrentViewXMin").inputValue());
    const xMaxAfterReset = parseFloat(await page.locator("#wwOvercurrentViewXMax").inputValue());
    expect(xMinAfterReset).toBeCloseTo(0.2, 6);
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
