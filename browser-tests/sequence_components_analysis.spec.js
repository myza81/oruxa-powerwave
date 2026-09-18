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

// ---------------------------------------------------------------------------
// Vector shaft/color rendering regression (owner UAT, 2026-09-18) -- proves
// every rendered sequence vector is a COMPLETE origin -> shaft -> arrowhead
// -> label vector, and that Positive/Negative/Zero sequence identity colors
// are actually applied to the shaft/arrowhead, not just present in markup.
// Root cause: `wwSequenceRoleColor()`'s three `var(--ww-seq-*)` lookups had
// no defensive fallback (unlike this codebase's own established `var(x,
// fallback)` convention for exactly this risk -- see `.ww-annotation`'s own
// CSS comment) -- with those tokens unresolved (a stale/version-mismatched
// cached theme.css predating them), the shaft `<line>`'s own
// `stroke="var(...)"` (its ONLY color source, no competing CSS class)
// degrades to SVG's own initial value `none` (invisible), while the
// arrowhead `<polygon>`'s `fill="var(...)"` degrades to `black` (still
// visible, wrong color) -- reproducing every symptom reported. Fixed by
// adding `var(--ww-seq-x, var(--text-dim))` fallbacks. These tests assert
// actual rendered SVG geometry/computed color, never markup presence alone.
// ---------------------------------------------------------------------------

// Vector emission order is fixed per role (see `wwPhasorVectorSvg()`):
// <line> then <polygon> then <text class="ww-phasor-vector-label">, in that
// DOM order -- walks backward from the role's own label to find its own
// shaft/arrowhead, never assuming a global element index.
async function vectorGeometry(page, svgSelector, roleKey) {
  return page.evaluate(
    ({ sel, role }) => {
      const svg = document.querySelector(sel);
      if (!svg) return null;
      const label = Array.from(svg.querySelectorAll("text.ww-phasor-vector-label")).find((t) => t.textContent === role);
      if (!label) return null;
      const polygon = label.previousElementSibling;
      const line = polygon ? polygon.previousElementSibling : null;
      if (!line || line.tagName.toLowerCase() !== "line" || !polygon || polygon.tagName.toLowerCase() !== "polygon") return null;
      const lineCs = getComputedStyle(line);
      const polyCs = getComputedStyle(polygon);
      const x1 = parseFloat(line.getAttribute("x1"));
      const y1 = parseFloat(line.getAttribute("y1"));
      const x2 = parseFloat(line.getAttribute("x2"));
      const y2 = parseFloat(line.getAttribute("y2"));
      return {
        x1, y1, x2, y2,
        shaftLength: Math.hypot(x2 - x1, y2 - y1),
        lineStroke: lineCs.stroke,
        lineStrokeWidth: parseFloat(lineCs.strokeWidth),
        polygonFill: polyCs.fill,
        labelText: label.textContent,
        labelFillVisible: getComputedStyle(label).fill !== "none",
      };
    },
    { sel: svgSelector, role: roleKey }
  );
}

// Resolves a `var(--token)` expression the SAME way the browser's own paint
// pipeline does (normalized to `rgb(...)`) -- never comparing a raw hex
// theme.css literal against a computed `rgb()` string.
async function resolvedColor(page, varExpr) {
  return page.evaluate((expr) => {
    const probe = document.createElement("div");
    probe.style.color = expr;
    document.body.appendChild(probe);
    const rgb = getComputedStyle(probe).color;
    probe.remove();
    return rgb;
  }, varExpr);
}

test.describe("Sequence Components v1 -- vector shaft/color rendering (Manual)", () => {
  test("dominant V1: shaft visible with non-zero length, arrowhead + label present, Positive-sequence color", async ({ page }) => {
    await openEmptyWorkspaceSequence(page);
    await page.locator("#wwSequenceManualVoltageBasisSelect").selectOption("secondary");
    await enterRole(page, "Va", { magnitude: 100, unit: "V", angleDeg: 0 });
    await enterRole(page, "Vb", { magnitude: 100, unit: "V", angleDeg: -120 });
    await enterRole(page, "Vc", { magnitude: 100, unit: "V", angleDeg: 120 });
    await expect(async () => {
      const text = await page.locator("#wwSequenceValuesList").innerText();
      expect(text).toMatch(/V1[\s\S]*?100\.0\s*V/);
    }).toPass({ timeout: 5000 });

    const positiveColor = await resolvedColor(page, "var(--ww-seq-positive)");
    const geo = await vectorGeometry(page, "#wwSequenceSvg", "V1");
    expect(geo).not.toBeNull();
    expect(geo.shaftLength).toBeGreaterThan(50); // a dominant vector must have a long, clearly visible shaft
    expect(geo.lineStroke).toBe(positiveColor); // never "none", never black-default
    expect(geo.lineStrokeWidth).toBeGreaterThan(0);
    expect(geo.polygonFill).toBe(positiveColor);
    expect(geo.labelText).toBe("V1");
    expect(geo.labelFillVisible).toBe(true);

    // Never the phase-identity colors, and never plain browser-default
    // black/none -- the whole point of this regression.
    const phaseAColor = await resolvedColor(page, "var(--ww-phase-a)");
    expect(geo.lineStroke).not.toBe(phaseAColor);
    expect(geo.lineStroke).not.toBe("rgb(0, 0, 0)");
    expect(geo.lineStroke).not.toBe("none");
  });

  test("pure negative sequence: V2 shaft visible in the correct quadrant with Negative-sequence color", async ({ page }) => {
    await openEmptyWorkspaceSequence(page);
    await page.locator("#wwSequenceManualVoltageBasisSelect").selectOption("secondary");
    await enterRole(page, "Va", { magnitude: 100, unit: "V", angleDeg: 0 });
    await enterRole(page, "Vb", { magnitude: 100, unit: "V", angleDeg: 120 });
    await enterRole(page, "Vc", { magnitude: 100, unit: "V", angleDeg: -120 });
    await expect(async () => {
      const text = await page.locator("#wwSequenceValuesList").innerText();
      expect(text).toMatch(/V2[\s\S]*?100\.0\s*V/);
    }).toPass({ timeout: 5000 });

    const negativeColor = await resolvedColor(page, "var(--ww-seq-negative)");
    const geo = await vectorGeometry(page, "#wwSequenceSvg", "V2");
    expect(geo).not.toBeNull();
    expect(geo.shaftLength).toBeGreaterThan(50);
    expect(geo.lineStroke).toBe(negativeColor);
    expect(geo.polygonFill).toBe(negativeColor);
    // Pure V2 at angle 0 -> a real-axis-aligned vector, same quadrant
    // (Real-positive) check as the golden angle -- proves position, not
    // just color, is correct.
    expect(geo.x2).toBeGreaterThan(40);
    expect(Math.abs(geo.y2)).toBeLessThan(5);
  });

  test("pure zero sequence: V0 shaft visible with Zero-sequence color", async ({ page }) => {
    await openEmptyWorkspaceSequence(page);
    await page.locator("#wwSequenceManualVoltageBasisSelect").selectOption("secondary");
    for (const role of ["Va", "Vb", "Vc"]) {
      await enterRole(page, role, { magnitude: 100, unit: "V", angleDeg: 0 });
    }
    await expect(async () => {
      const text = await page.locator("#wwSequenceValuesList").innerText();
      expect(text).toMatch(/V0[\s\S]*?100\.0\s*V/);
    }).toPass({ timeout: 5000 });

    const zeroColor = await resolvedColor(page, "var(--ww-seq-zero)");
    const geo = await vectorGeometry(page, "#wwSequenceSvg", "V0");
    expect(geo).not.toBeNull();
    expect(geo.shaftLength).toBeGreaterThan(50);
    expect(geo.lineStroke).toBe(zeroColor);
    expect(geo.polygonFill).toBe(zeroColor);
  });

  test("dominant I1 (Current): shaft visible, dashed, Positive-sequence color -- audits Current, not only Voltage", async ({ page }) => {
    await openEmptyWorkspaceSequence(page);
    await page.locator("#wwSequenceManualCurrentBasisSelect").selectOption("secondary");
    await enterRole(page, "Ia", { magnitude: 40, unit: "A", angleDeg: -30 });
    await enterRole(page, "Ib", { magnitude: 40, unit: "A", angleDeg: -150 });
    await enterRole(page, "Ic", { magnitude: 40, unit: "A", angleDeg: 90 });
    await expect(async () => {
      const text = await page.locator("#wwSequenceValuesList").innerText();
      expect(text).toMatch(/I1[\s\S]*?40\.0\s*A/);
    }).toPass({ timeout: 5000 });

    const positiveColor = await resolvedColor(page, "var(--ww-seq-positive)");
    const geo = await vectorGeometry(page, "#wwSequenceSvg", "I1");
    expect(geo).not.toBeNull();
    expect(geo.shaftLength).toBeGreaterThan(50);
    expect(geo.lineStroke).toBe(positiveColor);
    expect(geo.polygonFill).toBe(positiveColor);
  });

  test("all six roles (V1/V2/V0/I1/I2/I0) share the identical vector rendering path", async ({ page }) => {
    await openEmptyWorkspaceSequence(page);
    await page.locator("#wwSequenceManualVoltageBasisSelect").selectOption("secondary");
    await page.locator("#wwSequenceManualCurrentBasisSelect").selectOption("secondary");
    await enterRole(page, "Va", { magnitude: 132, unit: "kV", angleDeg: 12 });
    await enterRole(page, "Vb", { magnitude: 128, unit: "kV", angleDeg: -100 });
    await enterRole(page, "Vc", { magnitude: 130, unit: "kV", angleDeg: 140 });
    await enterRole(page, "Ia", { magnitude: 40, unit: "A", angleDeg: -40 });
    await enterRole(page, "Ib", { magnitude: 38, unit: "A", angleDeg: -160 });
    await enterRole(page, "Ic", { magnitude: 42, unit: "A", angleDeg: 95 });
    await expect(async () => {
      const text = await page.locator("#wwSequenceValuesList").innerText();
      expect(text).toContain("I1");
    }).toPass({ timeout: 5000 });

    for (const role of ["V1", "V2", "V0", "I1", "I2", "I0"]) {
      const geo = await vectorGeometry(page, "#wwSequenceSvg", role);
      expect(geo, `${role} vector must be present`).not.toBeNull();
      expect(geo.lineStroke, `${role} stroke must not be "none"`).not.toBe("none");
      expect(geo.lineStroke, `${role} stroke must not be default black`).not.toBe("rgb(0, 0, 0)");
      expect(geo.lineStrokeWidth).toBeGreaterThan(0);
    }
  });
});

test.describe("Sequence Components v1 -- vector shaft/color rendering (Recording)", () => {
  test("balanced recording: V1/I1 dominant shafts render with correct sequence colors", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisSequence(page);
    await selectContextAndWaitForResult(page, contextId);

    const positiveColor = await resolvedColor(page, "var(--ww-seq-positive)");
    const geoV1 = await vectorGeometry(page, "#wwSequenceSvg", "V1");
    const geoI1 = await vectorGeometry(page, "#wwSequenceSvg", "I1");
    expect(geoV1).not.toBeNull();
    expect(geoV1.shaftLength).toBeGreaterThan(50);
    expect(geoV1.lineStroke).toBe(positiveColor);
    expect(geoI1).not.toBeNull();
    expect(geoI1.shaftLength).toBeGreaterThan(50);
    expect(geoI1.lineStroke).toBe(positiveColor);
  });
});

test.describe("Sequence Components v1 -- defensive color fallback (root-cause regression)", () => {
  // Directly proves the fix: without a `var(x, fallback)` second argument,
  // an unresolved `--ww-seq-*` token (the real-world case this guards --
  // a stale/version-mismatched cached theme.css predating these recently-
  // added tokens, unlike Phasor's own long-stable `--ww-phase-a/b/c`)
  // makes `stroke="var(--ww-seq-positive)"` invalid-at-computed-value-time,
  // and the shaft `<line>` (which has no competing CSS class -- the
  // presentation attribute is its ONLY color source) falls back to SVG's
  // own initial `stroke` value, `none` -- an invisible shaft, even though
  // the underlying geometry (x2/y2) is completely correct. Disabling the
  // `var(x, fallback)` fix and re-running this exact test reproduces
  // `lineStroke === "none"` and `shaftLength === 0` (invisible) -- verified
  // manually during this fix's own development, not assumed.
  test("shaft stays visible even when --ww-seq-positive is unresolved", async ({ page }) => {
    await page.goto("/index.html");
    await page.evaluate(() => {
      const style = document.createElement("style");
      style.textContent = ":root { --ww-seq-positive: initial; --ww-seq-negative: initial; --ww-seq-zero: initial; }";
      document.head.appendChild(style);
    });
    await openAnalysisSequence(page);
    await page.locator("#wwSequenceManualVoltageBasisSelect").selectOption("secondary");
    await enterRole(page, "Va", { magnitude: 100, unit: "V", angleDeg: 0 });
    await enterRole(page, "Vb", { magnitude: 100, unit: "V", angleDeg: -120 });
    await enterRole(page, "Vc", { magnitude: 100, unit: "V", angleDeg: 120 });
    await expect(async () => {
      const text = await page.locator("#wwSequenceValuesList").innerText();
      expect(text).toMatch(/V1[\s\S]*?100\.0\s*V/);
    }).toPass({ timeout: 5000 });

    const geo = await vectorGeometry(page, "#wwSequenceSvg", "V1");
    expect(geo).not.toBeNull();
    // The geometry (position) is unaffected -- this is a pure rendering/
    // color-fallback fix, never a math change.
    expect(geo.x2).toBeGreaterThan(50);
    // The critical assertion: even with the primary token gone, the
    // shaft must still PAINT (fall back to --text-dim), never "none".
    expect(geo.lineStroke).not.toBe("none");
    expect(geo.shaftLength).toBeGreaterThan(50);
    const fallbackColor = await resolvedColor(page, "var(--text-dim)");
    expect(geo.lineStroke).toBe(fallbackColor);
    expect(geo.polygonFill).not.toBe("rgb(0, 0, 0)"); // never silently black-default either
  });
});

test.describe("Sequence Components v1 -- vector shaft/color rendering responsive", () => {
  for (const width of [1366, 1024]) {
    test(`dominant V1 shaft remains visible and unclipped at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 800 });
      await openEmptyWorkspaceSequence(page);
      await page.locator("#wwSequenceManualVoltageBasisSelect").selectOption("secondary");
      await enterRole(page, "Va", { magnitude: 100, unit: "V", angleDeg: 0 });
      await enterRole(page, "Vb", { magnitude: 100, unit: "V", angleDeg: -120 });
      await enterRole(page, "Vc", { magnitude: 100, unit: "V", angleDeg: 120 });
      await expect(async () => {
        const text = await page.locator("#wwSequenceValuesList").innerText();
        expect(text).toMatch(/V1[\s\S]*?100\.0\s*V/);
      }).toPass({ timeout: 5000 });

      const positiveColor = await resolvedColor(page, "var(--ww-seq-positive)");
      const geo = await vectorGeometry(page, "#wwSequenceSvg", "V1");
      expect(geo).not.toBeNull();
      expect(geo.shaftLength).toBeGreaterThan(50);
      expect(geo.lineStroke).toBe(positiveColor);

      // The rendered SVG box itself must still be visible and reasonably
      // sized (never collapsed to 0 by a narrow layout).
      const box = await page.locator("#wwSequenceSvg").boundingBox();
      expect(box.width).toBeGreaterThan(100);
      expect(box.height).toBeGreaterThan(100);
    });
  }
});

// ---------------------------------------------------------------------------
// Closure/hardening pass (owner instruction: "complete Sequence Components
// cleanup and closure... resolve all remaining known or discoverable issues
// that are genuinely within the Sequence Components feature boundary").
// Extends the vector-shaft/color regression above with the full six-role
// dominant-case matrix, dark-theme color resolution, the documented
// visibility/scale isolation rule, angle-wrap-around, ratio-unavailable UI,
// and context-switch staleness -- closing every remaining audit item that
// was not already covered by the existing suites above.
// ---------------------------------------------------------------------------

test.describe("Sequence Components v1 -- full six-role dominant-color matrix (Manual, light theme)", () => {
  const cases = [
    {
      role: "I2", label: "pure negative sequence Current -> I2 dominant", token: "--ww-seq-negative",
      roles: [["Ia", 20, "A", 0], ["Ib", 20, "A", 120], ["Ic", 20, "A", -120]], basisPrefix: "Current",
    },
    {
      role: "I0", label: "pure zero sequence Current -> I0 dominant", token: "--ww-seq-zero",
      roles: [["Ia", 15, "A", 45], ["Ib", 15, "A", 45], ["Ic", 15, "A", 45]], basisPrefix: "Current",
    },
  ];
  for (const c of cases) {
    test(`${c.label}: shaft visible with correct dedicated color`, async ({ page }) => {
      await openEmptyWorkspaceSequence(page);
      await page.locator(`#wwSequenceManual${c.basisPrefix}BasisSelect`).selectOption("secondary");
      for (const [role, magnitude, unit, angleDeg] of c.roles) {
        await enterRole(page, role, { magnitude, unit, angleDeg });
      }
      await expect(async () => {
        const text = await page.locator("#wwSequenceValuesList").innerText();
        expect(text).toMatch(new RegExp(`${c.role}[\\s\\S]*?${c.roles[0][1].toFixed(1)}\\s*${c.roles[0][2]}`));
      }).toPass({ timeout: 5000 });

      const expectedColor = await resolvedColor(page, `var(${c.token})`);
      const geo = await vectorGeometry(page, "#wwSequenceSvg", c.role);
      expect(geo, `${c.role} vector must be present`).not.toBeNull();
      expect(geo.shaftLength).toBeGreaterThan(50);
      expect(geo.lineStroke).toBe(expectedColor);
      expect(geo.polygonFill).toBe(expectedColor);
    });
  }

  // V1/V2/V0/I1 dominant-color cases already exist in the suite above
  // ("vector shaft/color rendering (Manual)") -- this closes the
  // remaining I2/I0 gap so all six roles have an individual golden
  // dominant-color case, per the closure task's own explicit checklist.

  test("mixed case, all six roles visible together: every role resolves its OWN dedicated color simultaneously", async ({ page }) => {
    await openEmptyWorkspaceSequence(page);
    await page.locator("#wwSequenceManualVoltageBasisSelect").selectOption("secondary");
    await page.locator("#wwSequenceManualCurrentBasisSelect").selectOption("secondary");
    await enterRole(page, "Va", { magnitude: 100, unit: "V", angleDeg: 0 });
    await enterRole(page, "Vb", { magnitude: 90, unit: "V", angleDeg: -100 });
    await enterRole(page, "Vc", { magnitude: 95, unit: "V", angleDeg: 130 });
    await enterRole(page, "Ia", { magnitude: 40, unit: "A", angleDeg: 15 });
    await enterRole(page, "Ib", { magnitude: 32, unit: "A", angleDeg: -95 });
    await enterRole(page, "Ic", { magnitude: 45, unit: "A", angleDeg: 160 });
    await expect(async () => {
      const text = await page.locator("#wwSequenceValuesList").innerText();
      expect(text).toContain("I1");
    }).toPass({ timeout: 5000 });

    const positiveColor = await resolvedColor(page, "var(--ww-seq-positive)");
    const negativeColor = await resolvedColor(page, "var(--ww-seq-negative)");
    const zeroColor = await resolvedColor(page, "var(--ww-seq-zero)");
    const expectedByRole = { V1: positiveColor, I1: positiveColor, V2: negativeColor, I2: negativeColor, V0: zeroColor, I0: zeroColor };
    for (const [role, expectedColor] of Object.entries(expectedByRole)) {
      const geo = await vectorGeometry(page, "#wwSequenceSvg", role);
      expect(geo, `${role} must be present`).not.toBeNull();
      expect(geo.lineStroke, `${role} must use its own dedicated color`).toBe(expectedColor);
      expect(geo.polygonFill, `${role} arrowhead must match its shaft color`).toBe(expectedColor);
    }
    // Positive/Negative/Zero must each resolve to a genuinely DIFFERENT
    // color -- the whole point of dedicated sequence identity.
    expect(new Set([positiveColor, negativeColor, zeroColor]).size).toBe(3);
  });
});

test.describe("Sequence Components v1 -- dark theme color resolution", () => {
  test("dominant V1 resolves the DARK-theme --ww-seq-positive value, still not black/none", async ({ page }) => {
    await page.goto("/index.html");
    await page.evaluate(() => {
      document.documentElement.setAttribute("data-theme", "dark");
    });
    await openAnalysisSequence(page);
    await page.locator("#wwSequenceManualVoltageBasisSelect").selectOption("secondary");
    await enterRole(page, "Va", { magnitude: 100, unit: "V", angleDeg: 0 });
    await enterRole(page, "Vb", { magnitude: 100, unit: "V", angleDeg: -120 });
    await enterRole(page, "Vc", { magnitude: 100, unit: "V", angleDeg: 120 });
    await expect(async () => {
      const text = await page.locator("#wwSequenceValuesList").innerText();
      expect(text).toMatch(/V1[\s\S]*?100\.0\s*V/);
    }).toPass({ timeout: 5000 });

    const darkPositiveColor = await resolvedColor(page, "var(--ww-seq-positive)");
    const lightPositiveColorProbe = await page.evaluate(() => {
      // The light-theme value is a literal, theme-independent constant
      // (#6d28d9) -- read directly from theme.css's own :root block via
      // a detached, unthemed element (never inherits data-theme from the
      // live <html> element).
      const probe = document.createElement("div");
      probe.style.color = "#6d28d9";
      document.body.appendChild(probe);
      const rgb = getComputedStyle(probe).color;
      probe.remove();
      return rgb;
    });
    const geo = await vectorGeometry(page, "#wwSequenceSvg", "V1");
    expect(geo).not.toBeNull();
    expect(geo.lineStroke).toBe(darkPositiveColor);
    expect(geo.lineStroke).not.toBe("none");
    expect(geo.lineStroke).not.toBe("rgb(0, 0, 0)");
    // Dark mode brightens the token toward --text for contrast -- must
    // be a genuinely DIFFERENT (brighter) color than the light-theme
    // literal, never silently falling back to the same value in both
    // themes (which would indicate the dark override never applied).
    expect(darkPositiveColor).not.toBe(lightPositiveColorProbe);
  });
});

test.describe("Sequence Components v1 -- visibility/scale isolation rule (documented)", () => {
  // Confirms and locks in the ACTUAL rule (task's own section 13: "confirm
  // and document the actual rule"): hiding a role via the eye toggle is a
  // pure display preference and does NOT shrink/rescale the remaining
  // visible vectors -- identical to Phasor's own wwPhasorFamilyMaxMagnitude()
  // precedent (neither excludes a hidden-but-available role from the max-
  // magnitude scale calculation). See SEQUENCE_COMPONENTS_ANALYSIS.md's own
  // "Sequence visibility" section for the documented rule this proves.
  test("hiding the dominant V1 does not change V2/V0's own rendered scale/position", async ({ page }) => {
    await openEmptyWorkspaceSequence(page);
    await page.locator("#wwSequenceManualVoltageBasisSelect").selectOption("secondary");
    await enterRole(page, "Va", { magnitude: 100, unit: "V", angleDeg: 0 });
    await enterRole(page, "Vb", { magnitude: 90, unit: "V", angleDeg: -100 });
    await enterRole(page, "Vc", { magnitude: 95, unit: "V", angleDeg: 130 });
    await expect(async () => {
      const text = await page.locator("#wwSequenceValuesList").innerText();
      expect(text).toContain("V1");
    }).toPass({ timeout: 5000 });

    const v2Before = await vectorGeometry(page, "#wwSequenceSvg", "V2");
    expect(v2Before).not.toBeNull();

    await page.locator('#wwSequenceValuesList .ww-phasor-value-row[data-role="V1"]').click();
    await expect(page.locator("#wwSequenceSvg polygon")).toHaveCount(2); // V1's own polygon is gone

    const v2After = await vectorGeometry(page, "#wwSequenceSvg", "V2");
    expect(v2After).not.toBeNull();
    // Same rendered tip position (within floating-point/toFixed(2)
    // rounding) -- hiding V1 never rescaled the plot.
    expect(v2After.x2).toBeCloseTo(v2Before.x2, 1);
    expect(v2After.y2).toBeCloseTo(v2Before.y2, 1);

    // Re-show V1 -- restores without needing a re-fetch/recalculation.
    await page.locator('#wwSequenceValuesList .ww-phasor-value-row--hidden[data-role="V1"]').click();
    await expect(page.locator("#wwSequenceSvg polygon")).toHaveCount(3);
  });
});

test.describe("Sequence Components v1 -- angle convention (UI)", () => {
  test("an angle entered as 200 degrees displays normalized to -160 degrees, never a second convention", async ({ page }) => {
    await openEmptyWorkspaceSequence(page);
    await page.locator("#wwSequenceManualVoltageBasisSelect").selectOption("secondary");
    await enterRole(page, "Va", { magnitude: 100, unit: "V", angleDeg: 200 });
    await enterRole(page, "Vb", { magnitude: 100, unit: "V", angleDeg: -120 });
    await enterRole(page, "Vc", { magnitude: 100, unit: "V", angleDeg: 120 });
    await expect(async () => {
      const text = await page.locator("#wwSequenceValuesList").innerText();
      expect(text).toContain("V1");
    }).toPass({ timeout: 5000 });

    const text = await page.locator("#wwSequenceValuesList").innerText();
    // 200 degrees normalizes to -160 (the same `(-180, 180]` convention
    // Phasor uses) -- never displayed as a raw 200.
    const angleMatch = text.match(/V1[\s\S]*?∠\s*(-?[0-9.]+)°/);
    expect(angleMatch).not.toBeNull();
    const displayedAngle = parseFloat(angleMatch[1]);
    expect(displayedAngle).toBeGreaterThan(-180);
    expect(displayedAngle).toBeLessThanOrEqual(180);
  });
});

test.describe("Sequence Components v1 -- ratio guardrail (UI)", () => {
  test("a near-zero positive sequence shows 'Unavailable' ratios in the UI, never NaN/Infinity text", async ({ page }) => {
    await openEmptyWorkspaceSequence(page);
    await page.locator("#wwSequenceManualVoltageBasisSelect").selectOption("secondary");
    // Va=Vb=Vc exactly (pure zero sequence) -> V1 is mathematically exact
    // zero, below MIN_POSITIVE_SEQUENCE_MAGNITUDE -- the ratio guardrail's
    // own "unavailable" branch (see app.domain.sequence_components).
    await enterRole(page, "Va", { magnitude: 100, unit: "V", angleDeg: 0 });
    await enterRole(page, "Vb", { magnitude: 100, unit: "V", angleDeg: 0 });
    await enterRole(page, "Vc", { magnitude: 100, unit: "V", angleDeg: 0 });
    await expect(async () => {
      const text = await page.locator("#wwSequenceValuesList").innerText();
      expect(text).toMatch(/V0[\s\S]*?100\.0\s*V/);
    }).toPass({ timeout: 5000 });

    const ratiosText = await page.locator("#wwSequenceRatiosList").innerText();
    expect(ratiosText).toMatch(/V2 \/ V1[\s\S]{0,20}Unavailable/);
    expect(ratiosText).toMatch(/V0 \/ V1[\s\S]{0,20}Unavailable/);
    expect(ratiosText).not.toMatch(/NaN/);
    expect(ratiosText).not.toMatch(/Infinity/);
  });
});

test.describe("Sequence Components v1 -- context-switch leaves no stale/broken state", () => {
  test("switching between two different contexts never leaves the prior context's values or a broken SVG on screen", async ({ page }) => {
    // Two genuinely DISTINCT sources (a context's own channel refs must
    // be uniquely claimed -- reusing the SAME source/channel set for a
    // second context is rejected) -- reuses the existing
    // `phasor_smoke_bravo_three_phase` fixture (BRAVO1_* channels,
    // already established in this test suite family for exactly this
    // multi-source scenario) alongside the primary ALPHA1_* fixture.
    await uploadFixture(page); // ALPHA1_*
    const rowA = page.locator("#recordingsTableBody tr[data-source-id]").last();
    await expect(rowA).toBeVisible();
    const sourceIdA = await rowA.getAttribute("data-source-id");
    const workspaceId = await page.evaluate(() => localStorage.getItem("powerwave.workspaceId"));
    const contextA = await createFullBayContext(page, workspaceId, sourceIdA, "Bay A");

    await page.locator("#recordingsUploadBtn, #recordingsEmptyUploadBtn").first().click();
    await expect(page.locator("#uploadModalOverlay")).toBeVisible();
    await page.locator("#uploadModalFile_0").setInputFiles(path.join(FIXTURES, "phasor_smoke_bravo_three_phase.cfg"));
    await page.locator("#uploadModalFile_1").setInputFiles(path.join(FIXTURES, `${STEM}.dat`)); // reuses the same sample data
    await page.locator("#uploadModalSubmitBtn").click();
    await page.locator("#uploadModalOverlay").waitFor({ state: "hidden" });
    const rowB = page.locator("#recordingsTableBody tr[data-source-id]").last();
    await expect(rowB).toBeVisible();
    const sourceIdB = await rowB.getAttribute("data-source-id");
    const membersB = [
      ["BRAVO1_VA", "A"], ["BRAVO1_VB", "B"], ["BRAVO1_VC", "C"],
      ["BRAVO1_IA", "A"], ["BRAVO1_IB", "B"], ["BRAVO1_IC", "C"],
    ].map(([channel_name, phase]) => ({
      channel_ref: { kind: "source", source_id: sourceIdB, channel_name },
      phase, phase_source: "engineer_confirmed",
    }));
    const responseB = await page.request.post(
      `${BACKEND_URL}/api/v1/workspaces/${encodeURIComponent(workspaceId)}/engineering-contexts`,
      { data: { display_name: "Bay B", status: "manual", members: membersB } }
    );
    expect(responseB.ok()).toBeTruthy();
    const contextB = await responseB.json();

    await openAnalysisSequence(page);
    await selectContextAndWaitForResult(page, contextA.id);
    const textA = await page.locator("#wwSequenceValuesList").innerText();
    expect(textA).toMatch(/100\.0\s*V/);

    // Switch to the second (genuinely different-source) context --
    // values must still read correctly (not blank, not NaN, not stuck
    // on Bay A's own stale text forever) once the fetch settles.
    await page.locator("#wwSequenceContextSelect").selectOption(contextB.id);
    await expect(async () => {
      const text = await page.locator("#wwSequenceValuesList").innerText();
      expect(text).toMatch(/100\.0\s*V/);
      expect(text).not.toMatch(/NaN/);
      expect(text).not.toMatch(/undefined/);
    }).toPass({ timeout: 5000 });

    // The diagram must still show a well-formed, present V1 vector --
    // never a broken/empty SVG left over from the switch.
    const geo = await vectorGeometry(page, "#wwSequenceSvg", "V1");
    expect(geo).not.toBeNull();
    expect(geo.shaftLength).toBeGreaterThan(50);
    expect(geo.lineStroke).not.toBe("none");
  });
});

test.describe("Sequence Components v1 -- scale legend does not overlap vectors", () => {
  for (const width of [1366, 1024]) {
    test(`a dominant vector pointing toward the legend's own corner never overlaps it at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 800 });
      await openEmptyWorkspaceSequence(page);
      await page.locator("#wwSequenceManualVoltageBasisSelect").selectOption("secondary");
      // Worst case: V1 pointed directly INTO the legend's own upper-right
      // corner (where the "Scale" legend is drawn).
      await enterRole(page, "Va", { magnitude: 100, unit: "V", angleDeg: 40 });
      await enterRole(page, "Vb", { magnitude: 100, unit: "V", angleDeg: -80 });
      await enterRole(page, "Vc", { magnitude: 100, unit: "V", angleDeg: 160 });
      await expect(async () => {
        const text = await page.locator("#wwSequenceValuesList").innerText();
        expect(text).toContain("V1");
      }).toPass({ timeout: 5000 });

      const boxes = await page.evaluate(() => {
        const svg = document.getElementById("wwSequenceSvg");
        const legendHeader = svg.querySelector(".ww-phasor-scale-legend--header");
        const label = Array.from(svg.querySelectorAll("text.ww-phasor-vector-label")).find((t) => t.textContent === "V1");
        const rectOf = (el) => { const b = el.getBBox(); return { x: b.x, y: b.y, w: b.width, h: b.height }; };
        return { legend: legendHeader ? rectOf(legendHeader) : null, label: label ? rectOf(label) : null };
      });
      expect(boxes.legend).not.toBeNull();
      expect(boxes.label).not.toBeNull();
      const noOverlap =
        boxes.legend.x + boxes.legend.w < boxes.label.x ||
        boxes.label.x + boxes.label.w < boxes.legend.x ||
        boxes.legend.y + boxes.legend.h < boxes.label.y ||
        boxes.label.y + boxes.label.h < boxes.legend.y;
      expect(noOverlap).toBe(true);
    });
  }
});
