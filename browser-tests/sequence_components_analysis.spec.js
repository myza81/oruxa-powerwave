// Sequence Components v1 -- the FOURTH Analysis-menu analyzer -- real-
// browser coverage. Task's own explicit mandate: "Do not repeat the
// Impedance v1 browser-coverage gap" (Impedance Locus v1 shipped with
// zero Playwright coverage in its own first slice and had to add it
// after the fact) -- this suite exists from day one.
//
// Reuses the SAME `phasor_smoke_three_phase` fixture (3 Voltage + 3
// Current channels, 50 Hz, balanced 100 V RMS / 40 A RMS three-phase
// sinusoid, 2 s duration) every other Analysis Playwright suite already
// uses, and the same direct-backend-API Engineering Context seeding
// pattern (no context-creation UI exists yet). Manual mode interaction
// helpers (`enterRole`/`setRatio`) are reused verbatim in shape from
// `phasor_analysis.spec.js`'s own Manual Input suite -- Sequence
// Components' own Manual form is the identical six-role, two-basis
// Manual Phasor architecture, never a separate sequence-entry model.

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

async function openAnalysisSequence(page) {
  await page.locator("#mainNavAnalysisBtn").click();
  await expect(page.locator("#pageAnalysis")).toBeVisible();
  await page.locator("#wwAnalysisTypeSequenceBtn").click();
  await expect(page.locator("#wwAnalysisTypeSequenceBtn")).toHaveClass(/active/);
  await expect(page.locator("#wwSequencePanel")).toBeVisible();
  await expect(page.locator("#wwPhasorPanel")).toBeHidden();
}

async function selectContextAndWaitForResult(page, contextId) {
  await expect(page.locator(`#wwSequenceContextSelect option[value="${contextId}"]`)).toHaveCount(1);
  await page.locator("#wwSequenceContextSelect").selectOption(contextId);
  await expect(async () => {
    const text = await page.locator("#wwSequenceValuesList").innerText();
    expect(text).toMatch(/100\.0\s*V/);
  }).toPass({ timeout: 5000 });
}

async function enterRole(page, roleKey, { magnitude, unit, angleDeg, enabled = true } = {}) {
  if (enabled) await page.locator(`#wwSequenceManual${roleKey}Enabled`).check();
  if (unit !== undefined) await page.locator(`#wwSequenceManual${roleKey}Unit`).selectOption(unit);
  if (magnitude !== undefined) {
    await page.locator(`#wwSequenceManual${roleKey}Magnitude`).fill(String(magnitude));
    await page.locator(`#wwSequenceManual${roleKey}Magnitude`).dispatchEvent("change");
    await page.locator(`#wwSequenceManual${roleKey}Magnitude`).blur();
  }
  if (angleDeg !== undefined) {
    await page.locator(`#wwSequenceManual${roleKey}Angle`).fill(String(angleDeg));
    await page.locator(`#wwSequenceManual${roleKey}Angle`).dispatchEvent("change");
    await page.locator(`#wwSequenceManual${roleKey}Angle`).blur();
  }
}

async function setRatio(page, prefix, { primary, secondary }) {
  if (primary !== undefined) {
    await page.locator(`#wwSequenceManual${prefix}PrimaryInput`).fill(String(primary));
    await page.locator(`#wwSequenceManual${prefix}PrimaryInput`).dispatchEvent("change");
  }
  if (secondary !== undefined) {
    await page.locator(`#wwSequenceManual${prefix}SecondaryInput`).fill(String(secondary));
    await page.locator(`#wwSequenceManual${prefix}SecondaryInput`).dispatchEvent("change");
  }
}

// Extracts a sequence role's own rendered magnitude (in the given unit)
// from the Values list's plain-text rendering -- robust to the
// exponential-notation formatting `wwFormatEngineeringValue()` uses for
// a near-zero (but not exactly float-zero) magnitude, e.g. "1.40e-14".
function extractMagnitude(text, role, unit) {
  const escaped = role.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const re = new RegExp(escaped + "\\s*\\n([0-9.eE+-]+)\\s*" + unit);
  const m = text.match(re);
  return m ? parseFloat(m[1]) : null;
}

async function openEmptyWorkspaceSequence(page) {
  await page.goto("/index.html");
  await openAnalysisSequence(page);
}

test.describe("Sequence Components v1 -- analyzer navigation", () => {
  test("nav button activates the real panel, not the placeholder", async ({ page }) => {
    await page.goto("/index.html");
    await openAnalysisSequence(page);
    await expect(page.locator("#wwSequencePanel")).not.toContainText("not implemented yet");
    await expect(page.locator("#wwSequenceInputSourceRecordingBtn")).toBeVisible();
    await expect(page.locator("#wwSequenceInputSourceManualBtn")).toBeVisible();
  });
});

test.describe("Sequence Components v1 -- empty workspace Manual mode (golden flow)", () => {
  test("empty workspace: Manual auto-selected, Recording shown disabled with hint, analyzer fully usable with zero recordings", async ({ page }) => {
    await openEmptyWorkspaceSequence(page);
    await expect(page.locator("#wwSequenceBody")).toBeVisible();
    await expect(page.locator("#wwSequenceInputSourceManualBtn")).toHaveAttribute("aria-pressed", "true");
    await expect(page.locator("#wwSequenceInputSourceRecordingBtn")).toBeDisabled();
    await expect(page.locator("#wwSequenceInputSourceHint")).toBeVisible();
    await expect(page.locator("#wwSequenceInputSourceHint")).toContainText("No recording loaded");
    await expect(page.locator("#wwSequenceManualInputSection")).toBeVisible();
    await expect(page.locator("#wwSequenceRecordingSection")).toBeHidden();
  });

  test("golden flow: balanced Va/Vb/Vc -> V1 dominant, V2~=0, V0~=0, sequence diagram renders", async ({ page }) => {
    await openEmptyWorkspaceSequence(page);

    // Secondary basis needs no VT ratio -- keeps this golden flow's own
    // focus on the transform itself, matching task section 22's "enter
    // balanced Va/Vb/Vc" with no basis-conversion setup implied.
    await page.locator("#wwSequenceManualVoltageBasisSelect").selectOption("secondary");
    await enterRole(page, "Va", { magnitude: 100, unit: "V", angleDeg: 0 });
    await enterRole(page, "Vb", { magnitude: 100, unit: "V", angleDeg: -120 });
    await enterRole(page, "Vc", { magnitude: 100, unit: "V", angleDeg: 120 });

    await expect(async () => {
      const text = await page.locator("#wwSequenceValuesList").innerText();
      expect(text).toMatch(/V1[\s\S]*?100\.0\s*V/);
    }).toPass({ timeout: 5000 });

    const text = await page.locator("#wwSequenceValuesList").innerText();
    expect(extractMagnitude(text, "V1", "V")).toBeCloseTo(100.0, 1);
    expect(Math.abs(extractMagnitude(text, "V2", "V"))).toBeLessThan(0.001);
    expect(Math.abs(extractMagnitude(text, "V0", "V"))).toBeLessThan(0.001);

    // Only the Voltage family was entered -- exactly the three Voltage
    // sequence vectors (V1/V2/V0) are drawn, no Current vectors.
    await expect(page.locator("#wwSequenceSvg polygon")).toHaveCount(3);

    // Ratios: V2/V1 and V0/V1 both read as a small (near-zero) percent,
    // never "Unavailable" (|V1| is genuinely large here). Current's own
    // ratios ARE "Unavailable" in this test -- Current was never
    // entered at all, an expected, independent Missing state.
    const ratiosText = await page.locator("#wwSequenceRatiosList").innerText();
    expect(ratiosText).toMatch(/V2 \/ V1\s*\n\s*[0-9.]+%/);
    expect(ratiosText).toMatch(/V0 \/ V1\s*\n\s*[0-9.]+%/);
  });
});

test.describe("Sequence Components v1 -- Manual golden scenarios", () => {
  test("pure zero sequence: Va=Vb=Vc -> V0 dominant, V1~=0, V2~=0", async ({ page }) => {
    await openEmptyWorkspaceSequence(page);
    await page.locator("#wwSequenceManualVoltageBasisSelect").selectOption("secondary");
    for (const role of ["Va", "Vb", "Vc"]) {
      await enterRole(page, role, { magnitude: 100, unit: "V", angleDeg: 0 });
    }
    await expect(async () => {
      const text = await page.locator("#wwSequenceValuesList").innerText();
      expect(text).toMatch(/V0[\s\S]*?100\.0\s*V/);
    }).toPass({ timeout: 5000 });
    const text = await page.locator("#wwSequenceValuesList").innerText();
    expect(extractMagnitude(text, "V0", "V")).toBeCloseTo(100.0, 1);
    expect(Math.abs(extractMagnitude(text, "V1", "V"))).toBeLessThan(0.001);
    expect(Math.abs(extractMagnitude(text, "V2", "V"))).toBeLessThan(0.001);
  });

  test("pure negative sequence: reverse rotation -> V2 dominant, V1~=0, V0~=0", async ({ page }) => {
    await openEmptyWorkspaceSequence(page);
    await page.locator("#wwSequenceManualVoltageBasisSelect").selectOption("secondary");
    await enterRole(page, "Va", { magnitude: 100, unit: "V", angleDeg: 0 });
    await enterRole(page, "Vb", { magnitude: 100, unit: "V", angleDeg: 120 });
    await enterRole(page, "Vc", { magnitude: 100, unit: "V", angleDeg: -120 });
    await expect(async () => {
      const text = await page.locator("#wwSequenceValuesList").innerText();
      expect(text).toMatch(/V2[\s\S]*?100\.0\s*V/);
    }).toPass({ timeout: 5000 });
    const text = await page.locator("#wwSequenceValuesList").innerText();
    expect(extractMagnitude(text, "V2", "V")).toBeCloseTo(100.0, 1);
    expect(Math.abs(extractMagnitude(text, "V1", "V"))).toBeLessThan(0.001);
    expect(Math.abs(extractMagnitude(text, "V0", "V"))).toBeLessThan(0.001);
  });

  test("Manual basis conversion: Primary VT 132000/110, balanced 132kV Primary -> 110V secondary V1, zero recording-dependent requests", async ({ page }) => {
    const recordingRequestUrls = [];
    await openEmptyWorkspaceSequence(page);
    page.on("request", (req) => {
      const url = req.url();
      if (url.includes("/sequence-components?") || url.includes("/phasor-diagram") || url.includes("/waveform")) recordingRequestUrls.push(url);
    });

    await page.locator("#wwSequenceManualVoltageBasisSelect").selectOption("primary");
    await setRatio(page, "Vt", { primary: 132000, secondary: 110 });
    await enterRole(page, "Va", { magnitude: 132, unit: "kV", angleDeg: 0 });
    await enterRole(page, "Vb", { magnitude: 132, unit: "kV", angleDeg: -120 });
    await enterRole(page, "Vc", { magnitude: 132, unit: "kV", angleDeg: 120 });

    await expect(async () => {
      const text = await page.locator("#wwSequenceValuesList").innerText();
      expect(text).toContain("V1");
    }).toPass({ timeout: 5000 });

    const text = await page.locator("#wwSequenceValuesList").innerText();
    expect(extractMagnitude(text, "V1", "V")).toBeCloseTo(110.0, 1);
    expect(recordingRequestUrls).toEqual([]);
  });

  test("Voltage and Current independent bases: Voltage Primary, Current Secondary in the same evaluation", async ({ page }) => {
    await openEmptyWorkspaceSequence(page);

    await page.locator("#wwSequenceManualVoltageBasisSelect").selectOption("primary");
    await setRatio(page, "Vt", { primary: 132000, secondary: 110 });
    await enterRole(page, "Va", { magnitude: 132, unit: "kV", angleDeg: 0 });
    await enterRole(page, "Vb", { magnitude: 132, unit: "kV", angleDeg: -120 });
    await enterRole(page, "Vc", { magnitude: 132, unit: "kV", angleDeg: 120 });

    await page.locator("#wwSequenceManualCurrentBasisSelect").selectOption("secondary");
    await enterRole(page, "Ia", { magnitude: 1, unit: "A", angleDeg: -30 });
    await enterRole(page, "Ib", { magnitude: 1, unit: "A", angleDeg: -150 });
    await enterRole(page, "Ic", { magnitude: 1, unit: "A", angleDeg: 90 });

    await expect(async () => {
      const text = await page.locator("#wwSequenceValuesList").innerText();
      expect(text).toContain("I1");
    }).toPass({ timeout: 5000 });

    const text = await page.locator("#wwSequenceValuesList").innerText();
    expect(extractMagnitude(text, "V1", "V")).toBeCloseTo(110.0, 1);
    expect(extractMagnitude(text, "I1", "A")).toBeCloseTo(1.0, 1);
    await expect(page.locator("#wwSequenceSvg polygon")).toHaveCount(6);
  });

  test("incomplete Voltage family (Vc never entered) reports Missing without blocking Current", async ({ page }) => {
    await openEmptyWorkspaceSequence(page);
    // Secondary basis for both families -- isolates the "incomplete
    // phase set" guardrail from the unrelated "invalid ratio" guardrail.
    await page.locator("#wwSequenceManualVoltageBasisSelect").selectOption("secondary");
    await page.locator("#wwSequenceManualCurrentBasisSelect").selectOption("secondary");
    await enterRole(page, "Va", { magnitude: 100, unit: "V", angleDeg: 0 });
    await enterRole(page, "Vb", { magnitude: 100, unit: "V", angleDeg: -120 });
    await enterRole(page, "Ia", { magnitude: 10, unit: "A", angleDeg: 0 });
    await enterRole(page, "Ib", { magnitude: 10, unit: "A", angleDeg: -120 });
    await enterRole(page, "Ic", { magnitude: 10, unit: "A", angleDeg: 120 });

    await expect(async () => {
      const text = await page.locator("#wwSequenceValuesList").innerText();
      expect(text).toMatch(/I1[\s\S]*?10\.0\s*A/);
    }).toPass({ timeout: 5000 });

    const text = await page.locator("#wwSequenceValuesList").innerText();
    expect(text).toMatch(/V1[\s\S]{0,40}Missing/);
    expect(extractMagnitude(text, "I1", "A")).toBeCloseTo(10.0, 1);

    const ratiosText = await page.locator("#wwSequenceRatiosList").innerText();
    expect(ratiosText).toMatch(/V2 \/ V1[\s\S]{0,20}Unavailable/);
    expect(ratiosText).toMatch(/V0 \/ V1[\s\S]{0,20}Unavailable/);
    // Current ratios ARE available -- Voltage's own incompleteness never
    // blocks Current.
    expect(ratiosText).not.toMatch(/I2 \/ I1[\s\S]{0,20}Unavailable/);
  });
});

test.describe("Sequence Components v1 -- Recording mode", () => {
  test("balanced recording -> V1~=100V/40A dominant, Related Waveforms shows Va/Vb/Vc/Ia/Ib/Ic", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisSequence(page);
    await selectContextAndWaitForResult(page, contextId);

    const text = await page.locator("#wwSequenceValuesList").innerText();
    expect(extractMagnitude(text, "V1", "V")).toBeCloseTo(100.0, 0);
    expect(extractMagnitude(text, "I1", "A")).toBeCloseTo(40.0, 0);

    await expect(async () => {
      const info = await page.evaluate(() => {
        const v = document.getElementById("wwAnalysisRelatedWaveformsVoltageChart");
        const c = document.getElementById("wwAnalysisRelatedWaveformsCurrentChart");
        return {
          vNames: v && v.data ? v.data.map((t) => t.name) : [],
          cNames: c && c.data ? c.data.map((t) => t.name) : [],
        };
      });
      expect(info.vNames).toEqual(["Va", "Vb", "Vc"]);
      expect(info.cNames).toEqual(["Ia", "Ib", "Ic"]);
    }).toPass({ timeout: 5000 });
    await expect(page.locator("#wwAnalysisRelatedWaveformsVoltageGroup")).toBeVisible();
    await expect(page.locator("#wwAnalysisRelatedWaveformsCurrentGroup")).toBeVisible();
    await expect(page.locator("#wwAnalysisRelatedWaveformsEmptyState")).toBeHidden();
  });

  test("Playback: Play then Pause updates the sequence result and settles", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisSequence(page);
    await selectContextAndWaitForResult(page, contextId);

    const playBtn = page.locator("#wwSequencePlaybackMount .ww-tg-playback-play-btn");
    await expect(playBtn).toBeVisible();
    await playBtn.click();
    await expect(playBtn).toHaveText("Pause");
    await page.waitForTimeout(500);
    await playBtn.click(); // pause

    await expect(async () => {
      const text = await page.locator("#wwSequenceValuesList").innerText();
      expect(extractMagnitude(text, "V1", "V")).toBeCloseTo(100.0, 0);
    }).toPass({ timeout: 5000 });

    // Settles -- no further silent change once paused. Compares only V1
    // (the dominant, physically meaningful component) magnitude/angle --
    // V2/V0's own magnitude is near the estimator's numerical noise
    // floor for a genuinely balanced recording, so their ANGLE is not a
    // meaningful/stable quantity to compare byte-for-byte (a near-zero
    // vector's angle is inherently noisy, the same numerical-validity
    // caveat the ratio guardrail itself exists for -- never a product
    // bug).
    const settledV1 = extractMagnitude(await page.locator("#wwSequenceValuesList").innerText(), "V1", "V");
    await page.waitForTimeout(400);
    const stillSettledV1 = extractMagnitude(await page.locator("#wwSequenceValuesList").innerText(), "V1", "V");
    expect(stillSettledV1).toBeCloseTo(settledV1, 3);
  });

  test("visibility toggle hides/shows a vector without changing calculated values", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisSequence(page);
    await selectContextAndWaitForResult(page, contextId);

    await expect(page.locator("#wwSequenceSvg polygon")).toHaveCount(6);
    const textBefore = await page.locator("#wwSequenceValuesList").innerText();

    await page.locator('#wwSequenceValuesList .ww-phasor-value-row[data-role="V1"]').click();
    await expect(page.locator("#wwSequenceSvg polygon")).toHaveCount(5);

    // The underlying calculated value itself is unchanged -- visibility
    // is purely a display preference (task's own section 12).
    const textAfterHide = await page.locator("#wwSequenceValuesList").innerText();
    expect(extractMagnitude(textAfterHide, "V1", "V")).toBeCloseTo(extractMagnitude(textBefore, "V1", "V"), 3);

    await page.locator('#wwSequenceValuesList .ww-phasor-value-row[data-role="V1"]').click();
    await expect(page.locator("#wwSequenceSvg polygon")).toHaveCount(6);
  });
});

test.describe("Sequence Components v1 -- Recording <-> Manual state isolation", () => {
  test("Manual values survive switching to Recording and back; Recording never overwrites Manual fields", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisSequence(page);

    // Enter Manual values first (still on Recording input source by
    // default once a recording exists -- switch explicitly).
    await page.locator("#wwSequenceInputSourceManualBtn").click();
    await enterRole(page, "Va", { magnitude: 77, unit: "V", angleDeg: 5 });
    await expect(async () => {
      const text = await page.locator("#wwSequenceValuesList").innerText();
      expect(text).toContain("Missing"); // incomplete family, still a valid Manual state
    }).toPass({ timeout: 5000 });

    // Switch to Recording -- selects the real context, Recording values render.
    await page.locator("#wwSequenceInputSourceRecordingBtn").click();
    await selectContextAndWaitForResult(page, contextId);

    // Switch back to Manual -- the Va=77V/5deg entry must still be there,
    // never overwritten/reset by the Recording fetch.
    await page.locator("#wwSequenceInputSourceManualBtn").click();
    await expect(page.locator("#wwSequenceManualVaMagnitude")).toHaveValue("77");
    await expect(page.locator("#wwSequenceManualVaAngle")).toHaveValue("5");
    await expect(page.locator("#wwSequenceManualVaEnabled")).toBeChecked();
  });
});

test.describe("Sequence Components v1 -- responsive layout", () => {
  for (const width of [1366, 1024]) {
    test(`no horizontal overflow, values/diagram remain visible at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 800 });
      const { contextId } = await uploadAndCreateContext(page);
      await openAnalysisSequence(page);
      await selectContextAndWaitForResult(page, contextId);

      await expect(page.locator("#wwSequenceValuesList")).toBeVisible();
      await expect(page.locator("#wwSequenceRatiosList")).toBeVisible();
      await expect(page.locator("#wwSequenceSvg")).toBeVisible();

      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      expect(overflow).toBeLessThanOrEqual(1);

      // Magnitude/angle text must not be visually clipped to an empty box.
      const box = await page.locator("#wwSequenceValuesList").boundingBox();
      expect(box.width).toBeGreaterThan(50);
    });
  }
});
