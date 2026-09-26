// Distance Protection v1 -- the FIFTH Analysis-menu analyzer -- real-
// browser coverage, written from day one (per the established "do not
// repeat the Impedance v1 browser-coverage gap" mandate -- see
// docs/project-memory/IMPEDANCE_LOCUS_ANALYSIS.md's own "Known
// limitations" section and the Sequence Components precedent that
// followed it).
//
// A SEPARATE analyzer from Impedance Locus -- own panel, own state, own
// R-X plot instance sharing the SAME equal-scale coordinate transform.
// `Operated`/`Not Operated` is PURE geometric element state; it never
// means a relay tripped, a breaker opened, or full relay logic
// completed. `Configured delay` is configuration information only in
// v1.
//
// Reuses the SAME `phasor_smoke_three_phase` fixture (3 Voltage + 3
// Current channels, 50 Hz, balanced 100 V RMS / 40 A RMS three-phase
// sinusoid, 2 s duration) every other Analysis Playwright suite already
// uses, and the same direct-backend-API Engineering Context seeding
// pattern (no context-creation UI exists yet). This fixture is a
// STEADY-STATE sinusoid, so a Recording-mode loop impedance is constant
// across time -- Zone-boundary-crossing coverage therefore exercises a
// live zone-SETTING change (reach) at a fixed Playback position rather
// than time evolution, which is the correct way to prove "instantaneous,
// never latched" element state against this fixture.

const { test, expect } = require("@playwright/test");
const path = require("path");
const { reuseOrCreateFullBayContext } = require("./support/engineering_context_helpers");

const FIXTURES = path.join(__dirname, "..", "backend", "tests", "fixtures", "comtrade");
const STEM = "phasor_smoke_three_phase";
const ALPHA_ROLES = [["VA", "A"], ["VB", "B"], ["VC", "C"], ["IA", "A"], ["IB", "B"], ["IC", "C"]];

async function uploadFixture(page) {
  await page.goto("/index.html");
  await page.locator("#recordingsUploadBtn, #recordingsEmptyUploadBtn").first().click();
  await expect(page.locator("#uploadModalOverlay")).toBeVisible();
  await page.locator("#uploadModalFile_0").setInputFiles(path.join(FIXTURES, `${STEM}.cfg`));
  await page.locator("#uploadModalFile_1").setInputFiles(path.join(FIXTURES, `${STEM}.dat`));
  await page.locator("#uploadModalSubmitBtn").click();
  await page.locator("#uploadModalOverlay").waitFor({ state: "hidden" });
}

// DEC-104 (2026-09-23) upload-time preparation normally already
// auto-created this full six-role context before this ever runs -- see
// support/engineering_context_helpers.js's own header comment. Discovers
// and reuses it instead of POSTing a duplicate (which now 409s).
async function createFullBayContext(page, workspaceId, sourceId, displayName) {
  return reuseOrCreateFullBayContext(page, workspaceId, sourceId, "ALPHA1", ALPHA_ROLES, displayName);
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

async function openAnalysisDistance(page) {
  await page.locator("#mainNavAnalysisBtn").click();
  await expect(page.locator("#pageAnalysis")).toBeVisible();
  await page.locator("#wwAnalysisTypeDistanceBtn").click();
  await expect(page.locator("#wwAnalysisTypeDistanceBtn")).toHaveClass(/active/);
  await expect(page.locator("#wwDistancePanel")).toBeVisible();
  await expect(page.locator("#wwPhasorPanel")).toBeHidden();
  await expect(page.locator("#wwImpedancePanel")).toBeHidden();
}

async function openEmptyWorkspaceDistance(page) {
  await page.goto("/index.html");
  await openAnalysisDistance(page);
}

// Mirrors impedance_analysis.spec.js's own documented root-cause fix:
// arms a REAL `page.waitForResponse()` for `/distance-protection-locus`
// BEFORE the triggering `selectOption()`, so the wait is deterministic
// rather than racing an independently-chosen timeout. DEC-105 (2026-09-23)
// already auto-selects the first/only context the instant Analysis opens
// -- every registered analyzer, including Distance Protection regardless
// of which tab is visible (see support/engineering_context_helpers.js's
// own header comment) -- normally true here since uploadAndCreateContext()
// reuses what DEC-104 already created, so `#wwDistanceContextSelect` may
// already show `contextId`; only arms/awaits the response wait when a
// selection actually happens, so it never hangs on a request a no-op
// re-selection would never issue.
async function selectContextAndWaitForResult(page, contextId) {
  await expect(page.locator(`#wwDistanceContextSelect option[value="${contextId}"]`)).toHaveCount(1);
  const select = page.locator("#wwDistanceContextSelect");
  if ((await select.inputValue()) !== contextId) {
    test.setTimeout(60000);
    // DEC-114 (2026-09-24): backend `compute_distance_locus()` no longer
    // repeats the ENTIRE static Phasor preparation once per one of the 120
    // sample points -- confirmed via a direct end-to-end reproduction
    // (real upload -> real auto-created context -> real HTTP GET against a
    // freshly started backend) that the SAME 120-point request that used
    // to take ~13-20s now completes in ~80-100ms. That speed-up REMOVES a
    // race this test used to rely on: DEC-105's own automatic initial-
    // context-selection fetch now routinely COMPLETES (and caches its own
    // matching `wwDistanceState.locusSignature`) before this explicit
    // reselect even runs, so `wwDistanceMaybeFetchLocus()`'s own signature
    // short-circuit correctly skips issuing a SECOND, redundant
    // `/distance-protection-locus` request -- the exact caching discipline
    // this suite already verifies elsewhere (e.g. "no full-locus or
    // waveform refetch occurs during Playback ticks"). A strict
    // `waitForResponse` here would wait forever for a request that
    // correct behavior legitimately never sends. Race a real response
    // against the locus state itself having been (re)populated since this
    // function started -- covers a genuinely new fetch AND an already-
    // cached hit, and the "changed since snapshot" comparison (not just
    // "non-empty") avoids a false-positive if a PRIOR, different context
    // already left a non-empty `locusPoints` array in place.
    const beforeSnapshot = await page.evaluate(() => JSON.stringify(wwDistanceState.locusPoints));
    const locusResponse = page.waitForResponse((r) => r.url().includes("/distance-protection-locus"), { timeout: 20000 }).catch(() => null);
    await select.selectOption(contextId);
    await Promise.race([
      locusResponse,
      expect(async () => {
        const current = await page.evaluate(() => JSON.stringify(wwDistanceState.locusPoints));
        expect(current).not.toBe(beforeSnapshot);
        expect(JSON.parse(current).length).toBeGreaterThan(0);
      }).toPass({ timeout: 20000 }),
    ]);
  }
  await expect(async () => {
    const text = await page.locator("#wwDistanceValuesList").innerText();
    expect(text).toContain("Loop");
  }).toPass({ timeout: 10000 });
}

async function waitForLocusCached(page, { minPoints = 20 } = {}) {
  await expect(async () => {
    const count = await page.evaluate(() =>
      wwDistanceState.locusPoints.filter((p) => p.status === "computed").length
    );
    expect(count).toBeGreaterThanOrEqual(minPoints);
  }).toPass({ timeout: 2000 });
}

async function locusPathSegmentCount(page) {
  return page.evaluate(() => {
    const el = document.querySelector("#wwDistanceSvg path.ww-dist-locus-path");
    if (!el) return 0;
    const d = el.getAttribute("d") || "";
    return (d.match(/M /g) || []).length + (d.match(/L /g) || []).length;
  });
}

async function cachedComputedLocusCount(page) {
  return page.evaluate(() => wwDistanceState.locusPoints.filter((p) => p.status === "computed").length);
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

async function enterManualLeg(page, legKey, { magnitude, unit, angleDeg } = {}) {
  if (unit !== undefined) await page.locator(`#wwDistanceManual${legKey}UnitSelect`).selectOption(unit);
  if (magnitude !== undefined) {
    await page.locator(`#wwDistanceManual${legKey}MagnitudeInput`).fill(String(magnitude));
    await page.locator(`#wwDistanceManual${legKey}MagnitudeInput`).dispatchEvent("change");
  }
  if (angleDeg !== undefined) {
    await page.locator(`#wwDistanceManual${legKey}AngleInput`).fill(String(angleDeg));
    await page.locator(`#wwDistanceManual${legKey}AngleInput`).dispatchEvent("change");
  }
}

async function enterGoldenAbManualLoop(page) {
  await page.locator("#wwDistanceManualVoltageBasisSelect").selectOption("secondary");
  await page.locator("#wwDistanceManualCurrentBasisSelect").selectOption("secondary");
  await enterManualLeg(page, "V1", { magnitude: 100, unit: "V", angleDeg: 0 });
  await enterManualLeg(page, "V2", { magnitude: 100, unit: "V", angleDeg: -120 });
  await enterManualLeg(page, "I1", { magnitude: 10, unit: "A", angleDeg: -20 });
  await enterManualLeg(page, "I2", { magnitude: 10, unit: "A", angleDeg: -140 });
}

test.describe("Distance Protection v1 -- analyzer navigation", () => {
  test("nav button activates the real panel, not the placeholder, and is a separate analyzer from Impedance Locus", async ({ page }) => {
    await page.goto("/index.html");
    await openAnalysisDistance(page);
    await expect(page.locator("#wwDistancePanel")).not.toContainText("not implemented yet");
    await expect(page.locator("#wwDistanceInputSourceRecordingBtn")).toBeVisible();
    await expect(page.locator("#wwDistanceInputSourceManualBtn")).toBeVisible();
    await expect(page.locator("#wwDistanceLoopSelect")).toBeVisible();
    await expect(page.locator("#wwDistanceCharacteristicSelect")).toBeVisible();
  });
});

test.describe("Distance Protection v1 -- empty workspace Manual mode (golden flow)", () => {
  test("empty workspace: Manual auto-selected, Recording shown disabled with hint, analyzer fully usable with zero recordings", async ({ page }) => {
    await openEmptyWorkspaceDistance(page);
    await expect(page.locator("#wwDistanceBody")).toBeVisible();
    await expect(page.locator("#wwDistanceInputSourceManualBtn")).toHaveAttribute("aria-pressed", "true");
    await expect(page.locator("#wwDistanceInputSourceRecordingBtn")).toBeDisabled();
    await expect(page.locator("#wwDistanceInputSourceHint")).toBeVisible();
    await expect(page.locator("#wwDistanceInputSourceHint")).toContainText("No recording loaded");
    await expect(page.locator("#wwDistanceManualInputSection")).toBeVisible();
    await expect(page.locator("#wwDistanceRecordingSection")).toBeHidden();
  });

  test("golden AB loop flow: known phasors -> loop impedance |Z|=10 /_20deg, point shown, zone state shown", async ({ page }) => {
    await openEmptyWorkspaceDistance(page);
    await page.locator("#wwDistanceLoopSelect").selectOption("AB");
    await enterGoldenAbManualLoop(page);

    await expect(async () => {
      const text = await page.locator("#wwDistanceValuesList").innerText();
      expect(text).toMatch(/Loop[\s\S]*?Zab/);
      expect(text).toMatch(/10\.0+\s*Ω/);
    }).toPass({ timeout: 5000 });

    const text = await page.locator("#wwDistanceValuesList").innerText();
    expect(text).toMatch(/\+20\.00°/);

    // No historical trail in Manual mode -- one point only.
    await expect(page.locator("#wwDistanceSvg path.ww-dist-locus-path")).toHaveCount(0);
    await expect(page.locator("#wwDistanceSvg circle.ww-dist-point--manual")).toHaveCount(1);

    // Zone State section always renders three rows, even with all zones
    // disabled (never structurally empty).
    const zoneText = await page.locator("#wwDistanceZoneStateList").innerText();
    expect(zoneText).toMatch(/Zone 1/);
    expect(zoneText).toMatch(/Zone 2/);
    expect(zoneText).toMatch(/Zone 3/);
    expect(zoneText).toMatch(/Not Operated/);
  });

  test("BC and CA loops never require the unrelated third phase, and each produces the same golden |Z|", async ({ page }) => {
    await openEmptyWorkspaceDistance(page);

    await page.locator("#wwDistanceLoopSelect").selectOption("BC");
    // DEC-117: V<sub>B</sub>/V<sub>C</sub> (textContent stays plain "VB").
    await expect(page.locator("#wwDistanceManualV1Label")).toHaveText("VB magnitude");
    await expect(page.locator("#wwDistanceManualV1Label .ww-electrical-sub")).toHaveText("B");
    await expect(page.locator("#wwDistanceManualV2Label")).toHaveText("VC magnitude");
    await expect(page.locator("#wwDistanceManualV2Label .ww-electrical-sub")).toHaveText("C");
    await page.locator("#wwDistanceManualVoltageBasisSelect").selectOption("secondary");
    await page.locator("#wwDistanceManualCurrentBasisSelect").selectOption("secondary");
    await enterManualLeg(page, "V1", { magnitude: 100, unit: "V", angleDeg: -120 });
    await enterManualLeg(page, "V2", { magnitude: 100, unit: "V", angleDeg: 120 });
    await enterManualLeg(page, "I1", { magnitude: 10, unit: "A", angleDeg: -140 });
    await enterManualLeg(page, "I2", { magnitude: 10, unit: "A", angleDeg: 100 });
    await expect(async () => {
      const text = await page.locator("#wwDistanceValuesList").innerText();
      expect(text).toMatch(/Zbc/);
      expect(text).toMatch(/10\.0+\s*Ω/);
    }).toPass({ timeout: 5000 });

    await page.locator("#wwDistanceLoopSelect").selectOption("CA");
    await expect(page.locator("#wwDistanceManualV1Label")).toHaveText("VC magnitude");
    await expect(page.locator("#wwDistanceManualV2Label")).toHaveText("VA magnitude");
    await expect(page.locator("#wwDistanceManualV2Label .ww-electrical-sub")).toHaveText("A");
    await enterManualLeg(page, "V1", { magnitude: 100, unit: "V", angleDeg: 120 });
    await enterManualLeg(page, "V2", { magnitude: 100, unit: "V", angleDeg: 0 });
    await enterManualLeg(page, "I1", { magnitude: 10, unit: "A", angleDeg: 100 });
    await enterManualLeg(page, "I2", { magnitude: 10, unit: "A", angleDeg: -20 });
    await expect(async () => {
      const text = await page.locator("#wwDistanceValuesList").innerText();
      expect(text).toMatch(/Zca/);
      expect(text).toMatch(/10\.0+\s*Ω/);
    }).toPass({ timeout: 5000 });
  });
});

test.describe("Distance Protection v1 -- Manual zone-state geometry", () => {
  test("Mho: a point exactly along the characteristic axis operates once reach exceeds |Z|, not before", async ({ page }) => {
    await openEmptyWorkspaceDistance(page);
    await page.locator("#wwDistanceCharacteristicSelect").selectOption("mho");
    await page.locator("#wwDistanceLoopSelect").selectOption("AB");
    await enterGoldenAbManualLoop(page); // -> |Z|=10 /_20deg

    await page.locator("#wwDistanceZone1AngleInput").fill("20");
    await page.locator("#wwDistanceZone1AngleInput").dispatchEvent("change");
    await page.locator("#wwDistanceZone1ReachInput").fill("5"); // < |Z| -> not operated
    await page.locator("#wwDistanceZone1ReachInput").dispatchEvent("change");
    await page.locator("#wwDistanceZone1Enabled").check();

    await expect(async () => {
      const zoneText = await page.locator("#wwDistanceZoneStateList").innerText();
      expect(zoneText).toMatch(/Zone 1[\s\S]*?Not Operated/);
    }).toPass({ timeout: 5000 });

    await page.locator("#wwDistanceZone1ReachInput").fill("15"); // > |Z| -> operated
    await page.locator("#wwDistanceZone1ReachInput").dispatchEvent("change");

    await expect(async () => {
      const zoneText = await page.locator("#wwDistanceZoneStateList").innerText();
      expect(zoneText).toMatch(/Zone 1[\s\S]*?Operated/);
    }).toPass({ timeout: 5000 });
    const badge = page.locator("#wwDistanceZoneStateList .ww-dist-zone-state-badge--operated").first();
    await expect(badge).toBeVisible();
    await expect(badge).toHaveText("Operated");

    // No trip/relay claim anywhere in the rendered result.
    const fullText = await page.locator("#wwDistancePanel").innerText();
    expect(fullText).not.toMatch(/Relay tripped/i);
    expect(fullText).not.toMatch(/Trip issued/i);
    expect(fullText).not.toMatch(/Breaker opened/i);
  });

  test("Quadrilateral: same loop, boundary derived from reactive/resistive reaches", async ({ page }) => {
    await openEmptyWorkspaceDistance(page);
    await page.locator("#wwDistanceLoopSelect").selectOption("AB");
    await enterGoldenAbManualLoop(page); // -> R=9.397, X=3.420
    await page.locator("#wwDistanceCharacteristicSelect").selectOption("quadrilateral");

    await page.locator("#wwDistanceZone1AngleInput").fill("90");
    await page.locator("#wwDistanceZone1AngleInput").dispatchEvent("change");
    await page.locator("#wwDistanceZone1ReactiveReachInput").fill("2"); // X=3.42 > 2 -> outside
    await page.locator("#wwDistanceZone1ReactiveReachInput").dispatchEvent("change");
    await page.locator("#wwDistanceZone1ResistiveForwardInput").fill("20");
    await page.locator("#wwDistanceZone1ResistiveForwardInput").dispatchEvent("change");
    await page.locator("#wwDistanceZone1ResistiveReverseInput").fill("20");
    await page.locator("#wwDistanceZone1ResistiveReverseInput").dispatchEvent("change");
    await page.locator("#wwDistanceZone1Enabled").check();

    await expect(async () => {
      const zoneText = await page.locator("#wwDistanceZoneStateList").innerText();
      expect(zoneText).toMatch(/Zone 1[\s\S]*?Not Operated/);
    }).toPass({ timeout: 5000 });

    await page.locator("#wwDistanceZone1ReactiveReachInput").fill("10"); // X=3.42 < 10 -> inside
    await page.locator("#wwDistanceZone1ReactiveReachInput").dispatchEvent("change");

    await expect(async () => {
      const zoneText = await page.locator("#wwDistanceZoneStateList").innerText();
      expect(zoneText).toMatch(/Zone 1[\s\S]*?Operated/);
    }).toPass({ timeout: 5000 });
  });

  test("characteristic switching never changes the measured impedance, only the zone geometry/state", async ({ page }) => {
    await openEmptyWorkspaceDistance(page);
    await page.locator("#wwDistanceLoopSelect").selectOption("AB");
    await enterGoldenAbManualLoop(page);
    await expect(async () => {
      const text = await page.locator("#wwDistanceValuesList").innerText();
      expect(text).toMatch(/10\.0+\s*Ω/);
    }).toPass({ timeout: 5000 });
    const before = await page.locator("#wwDistanceValuesList").innerText();

    await page.locator("#wwDistanceCharacteristicSelect").selectOption("quadrilateral");
    await expect(page.locator("#wwDistanceZone1ReactiveReachField")).toBeVisible();
    await expect(page.locator("#wwDistanceZone1ReachField")).toBeHidden();

    await expect(async () => {
      const text = await page.locator("#wwDistanceValuesList").innerText();
      expect(text).toBe(before);
    }).toPass({ timeout: 5000 });
  });

  test("multiple zones may operate simultaneously -- no priority suppression", async ({ page }) => {
    await openEmptyWorkspaceDistance(page);
    await page.locator("#wwDistanceCharacteristicSelect").selectOption("mho");
    await page.locator("#wwDistanceLoopSelect").selectOption("AB");
    await enterGoldenAbManualLoop(page); // -> |Z|=10 /_20deg
    for (const n of [1, 2, 3]) {
      await page.locator(`#wwDistanceZone${n}AngleInput`).fill("20");
      await page.locator(`#wwDistanceZone${n}AngleInput`).dispatchEvent("change");
      await page.locator(`#wwDistanceZone${n}ReachInput`).fill("15");
      await page.locator(`#wwDistanceZone${n}ReachInput`).dispatchEvent("change");
      await page.locator(`#wwDistanceZone${n}Enabled`).check();
    }
    await expect(async () => {
      const count = await page.locator("#wwDistanceZoneStateList .ww-dist-zone-state-badge--operated").count();
      expect(count).toBe(3);
    }).toPass({ timeout: 5000 });
  });
});

test.describe("Distance Protection v1 -- Recording mode", () => {
  test("Related Waveforms: AB loop pushes Va/Vb/Ia/Ib before pressing Play, then updates on loop switch", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisDistance(page);
    await selectContextAndWaitForResult(page, contextId);

    await expect(async () => {
      const names = await page.evaluate(() => ({
        v: document.getElementById("wwAnalysisRelatedWaveformsVoltageChart").data.map((t) => t.meta),
        c: document.getElementById("wwAnalysisRelatedWaveformsCurrentChart").data.map((t) => t.meta),
      }));
      expect(names.v.sort()).toEqual(["Va", "Vb"]);
      expect(names.c.sort()).toEqual(["Ia", "Ib"]);
    }).toPass({ timeout: 5000 });
    await expect(page.locator("#wwAnalysisRelatedWaveformsVoltageGroup")).toBeVisible();
    await expect(page.locator("#wwAnalysisRelatedWaveformsCurrentGroup")).toBeVisible();

    await page.locator("#wwDistanceLoopSelect").selectOption("BC");
    await expect(async () => {
      const names = await page.evaluate(() => ({
        v: document.getElementById("wwAnalysisRelatedWaveformsVoltageChart").data.map((t) => t.meta),
        c: document.getElementById("wwAnalysisRelatedWaveformsCurrentChart").data.map((t) => t.meta),
      }));
      expect(names.v.sort()).toEqual(["Vb", "Vc"]);
      expect(names.c.sort()).toEqual(["Ib", "Ic"]);
    }).toPass({ timeout: 5000 });
  });

  test("Engineering Context resolves loop phases from durable phase identity, never inferred from channel names", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisDistance(page);
    await selectContextAndWaitForResult(page, contextId);
    const text = await page.locator("#wwDistanceValuesList").innerText();
    expect(text).toMatch(/Zab/);
  });

  test("chronological locus reveal: current point visible, full future locus not visible until Playback progresses", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisDistance(page);
    await selectContextAndWaitForResult(page, contextId);
    await waitForLocusCached(page);

    const cached = await cachedComputedLocusCount(page);
    const drawn = await locusPathSegmentCount(page);
    expect(cached).toBeGreaterThanOrEqual(20);
    expect(drawn).toBeLessThan(cached * 0.25);
    await expect(page.locator("#wwDistanceSvg circle.ww-dist-point")).toHaveCount(1);
  });

  test("Play advances the marker and grows the visible trail; zones stay static while it moves", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisDistance(page);
    await selectContextAndWaitForResult(page, contextId);
    await waitForLocusCached(page);

    // A static reach large enough that the constant-amplitude fixture's
    // own loop impedance sits inside it for the whole recording -- proves
    // the zone geometry itself never redraws/animates while the point
    // trail moves underneath it.
    const currentZ = await page.evaluate(() => wwDistanceState.latestResult && wwDistanceState.latestResult.magnitude_ohm);
    expect(currentZ).toBeGreaterThan(0);
    await page.locator("#wwDistanceZone1ReachInput").fill(String(currentZ * 5));
    await page.locator("#wwDistanceZone1ReachInput").dispatchEvent("change");
    await page.locator("#wwDistanceZone1Enabled").check();
    await expect(async () => {
      const zoneText = await page.locator("#wwDistanceZoneStateList").innerText();
      expect(zoneText).toMatch(/Zone 1[\s\S]*?Operated/);
    }).toPass({ timeout: 5000 });

    const circleBefore = await page.evaluate(() => {
      const el = document.querySelector("#wwDistanceSvg circle.ww-dist-zone-boundary--zone1");
      return el ? el.getAttribute("r") : null;
    });
    const before = await locusPathSegmentCount(page);

    const playBtn = page.locator("#wwDistancePlaybackMount .ww-tg-playback-play-btn");
    await playBtn.click();
    await expect(playBtn).toHaveText("Pause");
    await page.waitForTimeout(700);
    await playBtn.click();

    const afterPlay = await locusPathSegmentCount(page);
    expect(afterPlay).toBeGreaterThan(before);

    const circleAfter = await page.evaluate(() => {
      const el = document.querySelector("#wwDistanceSvg circle.ww-dist-zone-boundary--zone1");
      return el ? el.getAttribute("r") : null;
    });
    expect(circleAfter).toBe(circleBefore);
  });

  test("zone state updates live at the current Playback point when a zone setting changes -- never latched", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisDistance(page);
    await selectContextAndWaitForResult(page, contextId);

    const currentZ = await page.evaluate(() => wwDistanceState.latestResult.magnitude_ohm);
    await page.locator("#wwDistanceZone1ReachInput").fill(String(currentZ * 0.5));
    await page.locator("#wwDistanceZone1ReachInput").dispatchEvent("change");
    await page.locator("#wwDistanceZone1Enabled").check();
    await expect(async () => {
      const zoneText = await page.locator("#wwDistanceZoneStateList").innerText();
      expect(zoneText).toMatch(/Zone 1[\s\S]*?Not Operated/);
    }).toPass({ timeout: 5000 });

    await page.locator("#wwDistanceZone1ReachInput").fill(String(currentZ * 5));
    await page.locator("#wwDistanceZone1ReachInput").dispatchEvent("change");
    await expect(async () => {
      const zoneText = await page.locator("#wwDistanceZoneStateList").innerText();
      expect(zoneText).toMatch(/Zone 1[\s\S]*?Operated/);
    }).toPass({ timeout: 5000 });

    await page.locator("#wwDistanceZone1ReachInput").fill(String(currentZ * 0.5));
    await page.locator("#wwDistanceZone1ReachInput").dispatchEvent("change");
    await expect(async () => {
      const zoneText = await page.locator("#wwDistanceZoneStateList").innerText();
      expect(zoneText).toMatch(/Zone 1[\s\S]*?Not Operated/);
    }).toPass({ timeout: 5000 });
  });

  test("no full-locus or waveform refetch occurs during Playback ticks", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisDistance(page);
    await selectContextAndWaitForResult(page, contextId);
    await waitForLocusCached(page);

    const locusUrls = [];
    const waveformUrls = [];
    page.on("request", (req) => {
      if (req.url().includes("/distance-protection-locus")) locusUrls.push(req.url());
      if (req.url().includes("/waveform")) waveformUrls.push(req.url());
    });

    const playBtn = page.locator("#wwDistancePlaybackMount .ww-tg-playback-play-btn");
    await playBtn.click();
    await page.waitForTimeout(1000);
    await playBtn.click();

    expect(locusUrls).toHaveLength(0);
    expect(waveformUrls).toHaveLength(0);
  });
});

test.describe("Distance Protection v1 -- R-X plot geometry", () => {
  for (const width of [1366, 1024]) {
    test(`equal px-per-ohm scale and correct quadrant plotting at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 800 });
      await openEmptyWorkspaceDistance(page);
      await page.locator("#wwDistanceLoopSelect").selectOption("AB");
      await enterGoldenAbManualLoop(page); // R=9.397 (+), X=3.420 (+)

      // Each field commit re-triggers an async Manual fetch -- wait for
      // the FINAL (golden) result to actually land before reading the
      // plotted point, rather than the first render a partial entry may
      // have already produced (an element existing is not proof it
      // reflects the fully-entered values).
      await expect(async () => {
        const text = await page.locator("#wwDistanceValuesList").innerText();
        expect(text).toMatch(/10\.0+\s*Ω/);
      }).toPass({ timeout: 5000 });
      await expect(page.locator("#wwDistanceSvg circle.ww-dist-point--manual")).toHaveCount(1);
      const { cx, cy } = await page.evaluate(() => {
        const el = document.querySelector("#wwDistanceSvg circle.ww-dist-point--manual");
        return { cx: parseFloat(el.getAttribute("cx")), cy: parseFloat(el.getAttribute("cy")) };
      });
      // toSvg(r, x) = [r * pxPerOhm, -x * pxPerOhm] -- the SAME factor
      // for both axes is proven by cx/R == -cy/X (cross-multiplied to
      // avoid a division-by-near-zero risk): cx*X == -cy*R. Production
      // rounds each SVG coordinate to 2 decimals (toFixed(2)) before
      // rendering -- precision 1 (0.05 tolerance) comfortably absorbs
      // that intentional rounding while still catching any genuine
      // unequal-axis-scale regression (which would differ by whole
      // units, not hundredths).
      const R = 9.396926207859085;
      const X = 3.4202014332566875;
      expect(cx * X).toBeCloseTo(-cy * R, 1);
      // Both R and X are positive here -- Quadrant I: cx > 0 (R
      // positive), cy < 0 (X positive, negated by the SVG transform).
      expect(cx).toBeGreaterThan(0);
      expect(cy).toBeLessThan(0);
    });
  }

  test("Mho zone boundary renders as a true <circle> (never an ellipse)", async ({ page }) => {
    await openEmptyWorkspaceDistance(page);
    await page.locator("#wwDistanceCharacteristicSelect").selectOption("mho");
    await page.locator("#wwDistanceZone1ReachInput").fill("10");
    await page.locator("#wwDistanceZone1ReachInput").dispatchEvent("change");
    await page.locator("#wwDistanceZone1Enabled").check();
    const circle = page.locator("#wwDistanceSvg circle.ww-dist-zone-boundary--zone1");
    await expect(circle).toHaveCount(1);
    await expect(circle).toHaveAttribute("r", /^\d/);
    await expect(page.locator("#wwDistanceSvg ellipse")).toHaveCount(0);
  });

  test("Quadrilateral zone boundary renders as a 4-point <polygon> preserving the configured reaches", async ({ page }) => {
    await openEmptyWorkspaceDistance(page);
    await page.locator("#wwDistanceCharacteristicSelect").selectOption("quadrilateral");
    await page.locator("#wwDistanceZone1AngleInput").fill("90");
    await page.locator("#wwDistanceZone1AngleInput").dispatchEvent("change");
    await page.locator("#wwDistanceZone1ReactiveReachInput").fill("10");
    await page.locator("#wwDistanceZone1ReactiveReachInput").dispatchEvent("change");
    await page.locator("#wwDistanceZone1ResistiveForwardInput").fill("5");
    await page.locator("#wwDistanceZone1ResistiveForwardInput").dispatchEvent("change");
    await page.locator("#wwDistanceZone1ResistiveReverseInput").fill("2");
    await page.locator("#wwDistanceZone1ResistiveReverseInput").dispatchEvent("change");
    await page.locator("#wwDistanceZone1Enabled").check();

    const polygon = page.locator("#wwDistanceSvg polygon.ww-dist-zone-boundary--zone1");
    await expect(polygon).toHaveCount(1);
    const points = await polygon.getAttribute("points");
    const coords = points.trim().split(/\s+/).map((p) => p.split(",").map(Number));
    expect(coords).toHaveLength(4);
    // theta=90 -> the classic axis-aligned box: R in [-2, 5], X in [0, 10].
    // toSvg negates X for SVG-y, so cy spans [-10*px, 0] and cx spans
    // [-2*px, 5*px] -- verified via the ratio between the two axis
    // extents rather than a hardcoded pixel value.
    const cxValues = coords.map((c) => c[0]);
    const cyValues = coords.map((c) => c[1]);
    const cxSpan = Math.max(...cxValues) - Math.min(...cxValues);
    const cySpan = Math.max(...cyValues) - Math.min(...cyValues);
    expect(cxSpan / cySpan).toBeCloseTo(7 / 10, 1); // (5-(-2)) / (10-0)
  });
});

test.describe("Distance Protection v1 -- Recording/Manual state isolation", () => {
  test("entering Manual values never overwrites the Recording-derived result, and vice versa", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisDistance(page);
    await selectContextAndWaitForResult(page, contextId);
    const recordingText = await page.locator("#wwDistanceValuesList").innerText();
    expect(recordingText).toMatch(/Zab/);

    await page.locator("#wwDistanceInputSourceManualBtn").click();
    await expect(page.locator("#wwDistanceManualInputSection")).toBeVisible();
    await enterGoldenAbManualLoop(page);
    await expect(async () => {
      const text = await page.locator("#wwDistanceValuesList").innerText();
      expect(text).toMatch(/10\.0+\s*Ω/);
    }).toPass({ timeout: 5000 });
    const manualText = await page.locator("#wwDistanceValuesList").innerText();
    expect(manualText).not.toBe(recordingText);

    await page.locator("#wwDistanceInputSourceRecordingBtn").click();
    await expect(async () => {
      const text = await page.locator("#wwDistanceValuesList").innerText();
      expect(text).toBe(recordingText);
    }).toPass({ timeout: 5000 });
  });
});
