// Compliance & Capability -- DEC-166: the simplified Operating Envelope
// Reference Profile editor, real-browser coverage. Normal use needs only
// Name, Category, the Lower/Upper boundary POINT lists and Phase
// Evaluation; defaults are visible under Advanced Settings; edge geometry
// is inferred from adjacent points and translated into the unchanged
// segment model on Save.
//
// Every saved-profile assertion reads the stored profile back through the
// real API (never the DOM alone), and every preview assertion inspects the
// real Plotly trace data of `#wwRefEditorPreviewPlot`.
//
// The frontend's point -> segment translation and boundary-crossing check
// are mirrors of the backend's (app.domain.reference_envelope /
// app.domain.reference_profile); the last describe block replays the SAME
// golden vectors pytest uses, so the two cannot drift.

const { test, expect } = require("@playwright/test");
const path = require("path");
const fs = require("fs");
const { expectTrueSubscripts } = require("./support/electrical_notation_helpers");

const BACKEND_URL = `http://127.0.0.1:${process.env.PW_BACKEND_PORT || "8000"}`;
const VECTORS = JSON.parse(fs.readFileSync(
  path.join(__dirname, "..", "backend", "tests", "fixtures", "reference_envelope_vectors.json"), "utf8",
));

async function workspaceIdOf(page) {
  return page.evaluate(() => localStorage.getItem("powerwave.workspaceId"));
}
function profilesUrl(workspaceId) {
  return `${BACKEND_URL}/api/v1/workspaces/${encodeURIComponent(workspaceId)}/reference-profiles`;
}

async function openCompliance(page) {
  await page.goto("/index.html");
  await page.locator("#mainNavComplianceBtn").click();
  await expect(page.locator("#pageCompliance")).toBeVisible();
}

async function openNewEditor(page) {
  await openCompliance(page);
  await page.locator("#wwComplianceAddReferenceBtn").click();
  await page.locator("#wwRefAddNewProfileBtn").click();
  await expect(page.locator("#wwRefEditorOverlay")).toBeVisible();
}

const cap = (boundary) => (boundary === "upper" ? "Upper" : "Lower");

// Brings the boundary's table to exactly rows.length rows and fills them.
async function setPoints(page, boundary, rows) {
  const body = page.locator(`#wwRefEditor${cap(boundary)}Body tr`);
  while ((await body.count()) < rows.length) await page.locator(`#wwRefEditor${cap(boundary)}AddRowBtn`).click();
  while ((await body.count()) > rows.length) await body.last().locator(".ww-ref-segment-row-remove").click();
  for (let i = 0; i < rows.length; i++) {
    await body.nth(i).locator(".ww-ref-pt-time").fill(String(rows[i][0]));
    await body.nth(i).locator(".ww-ref-pt-value").fill(String(rows[i][1]));
  }
}

async function setBoundaries(page, { lower, upper }) {
  await page.locator("#wwRefEditorLowerEnabled").setChecked(lower);
  await page.locator("#wwRefEditorUpperEnabled").setChecked(upper);
}

async function previewTraces(page) {
  return page.evaluate(() => {
    const el = document.getElementById("wwRefEditorPreviewPlot");
    return el && el.data ? el.data.map((t) => ({
      role: t.meta && t.meta.role, boundary: t.meta && t.meta.boundary, x: t.x, y: t.y, fill: t.fill, dash: t.line && t.line.dash,
    })) : [];
  });
}
const boundaryTrace = (traces, boundary) => traces.find((t) => t.role === "boundary" && t.boundary === boundary);

async function saveEditor(page, name) {
  await page.locator("#wwRefEditorName").fill(name);
  await expect(page.locator("#wwRefEditorSaveBtn")).toBeEnabled();
  await page.locator("#wwRefEditorSaveBtn").click();
  await expect(page.locator("#wwRefEditorOverlay")).toBeHidden();
  const response = await page.request.get(profilesUrl(await workspaceIdOf(page)));
  const profile = (await response.json()).find((p) => p.name === name);
  expect(profile, `saved profile ${name}`).toBeTruthy();
  return profile;
}

const segmentRows = (boundary) => boundary.segments.map((s) => [s.start_time, s.end_time, s.start_value, s.end_value, s.segment_type]);
const LVRT_POINTS = [[0, 0], [0.15, 0], [0.15, 0.9], [3, 0.9]];

async function createViaApi(page, overrides) {
  const body = {
    name: "API Profile", category: "custom_reference", assessment_definition: { representation: "line_line_rms", phase_treatment: "each_phase" },
    unit: "pu", display_start_time: 0, display_end_time: 3, evaluation_start_time: 0, evaluation_end_time: 3, tolerance: 0,
    lower_boundary: { segments: [{ start_time: 0, end_time: 3, start_value: 0.9, end_value: 0.9, segment_type: "constant" }] },
    upper_boundary: null, metadata: {}, ...overrides,
  };
  const response = await page.request.post(profilesUrl(await workspaceIdOf(page)), { data: body });
  expect(response.ok()).toBeTruthy();
  return response.json();
}

// Add Reference UX: saved references (the library) are listed in the Add Reference
// dialog; Edit sits behind each row's "more" control.
async function openEditorFor(page, name) {
  const row = page.locator("#wwRefAddList .ww-ref-picker-item", { hasText: name });
  // A create closes the dialog asynchronously; retry until it is genuinely open with the row listed.
  await expect(async () => {
    if (!(await page.locator("#wwRefAddOverlay").isVisible())) await page.locator("#wwComplianceAddReferenceBtn").click();
    await expect(row.locator(".ww-ref-row-menu summary")).toBeVisible({ timeout: 1500 });
  }).toPass({ timeout: 15000 });
  await row.locator(".ww-ref-row-menu summary").click();
  await row.locator("button:has-text('Edit')").click();
  await expect(page.locator("#wwRefEditorOverlay")).toBeVisible();
}

test.describe("DEC-166 -- defaults and normal-form hierarchy", () => {
  test("a new profile exposes only Name, Category, Operating Envelope and Phase Evaluation; defaults are visible under Advanced Settings", async ({ page }) => {
    await openNewEditor(page);

    // Normal form.
    await expect(page.locator("#wwRefEditorName")).toBeVisible();
    await expect(page.locator("#wwRefEditorCategory")).toHaveValue("custom_reference");
    await expect(page.locator("#wwRefEditorLowerEnabled")).toBeChecked();
    await expect(page.locator("#wwRefEditorUpperEnabled")).not.toBeChecked();
    await expect(page.locator("#wwRefEditorPhaseTreatment")).toHaveValue("each_phase");
    await expect(page.locator("#wwRefEditorPhaseTreatment option")).toHaveText(["Each Phase", "Minimum", "Maximum", "Single"]);
    await expect(page.locator("#wwRefEditorCategory option")).toHaveText([
      "Grid Requirement", "Equipment Capability", "Project Requirement", "Custom Reference",
    ]);
    await expect(page.locator("#wwRefEditorMemberField")).toBeHidden();

    // Retired from the normal workflow: nothing about location, interpretation source,
    // a generic Specific Member field or a per-row segment type.
    const editorText = await page.locator("#wwRefEditorOverlay").innerText();
    for (const retired of ["Measurement location", "Interpretation source", "Specific member", "Constant", "Linear"]) {
      expect(editorText).not.toContain(retired);
    }
    await expect(page.locator("#wwRefEditorOverlay .ww-ref-seg-type")).toHaveCount(0);

    // Advanced Settings: collapsed, and the defaults are exactly what is used.
    await expect(page.locator("#wwRefEditorAdvanced")).not.toHaveAttribute("open", "");
    await page.locator("#wwRefEditorAdvanced summary").click();
    await expect(page.locator("#wwRefEditorUnit")).toHaveValue("pu");
    await expect(page.locator("#wwRefEditorRepresentation")).toHaveValue("line_line_rms");
    await expect(page.locator("#wwRefEditorRepresentation option")).toHaveText(["Line-Line RMS", "Phase-Ground RMS", "Positive-Sequence RMS"]);
    await expect(page.locator("#wwRefEditorEvalStart")).toHaveValue("0");
    await expect(page.locator("#wwRefEditorTolerance")).toHaveValue("0");
    await expect(page.locator("#wwRefEditorEvalEndAuto")).toBeChecked();
    await expect(page.locator("#wwRefEditorDisplayStartAuto")).toBeChecked();
    await expect(page.locator("#wwRefEditorDisplayEndAuto")).toBeChecked();
    await expect(page.locator("#wwRefEditorAdvanced")).toContainText("Auto — same as display end");

    // Reference Source / Metadata is separate and collapsed.
    await expect(page.locator("#wwRefEditorMetadata")).not.toHaveAttribute("open", "");
    await expect(page.locator("#wwRefEditorSaveBtn")).toHaveText("Save Reference");
  });

  test("a profile saved with every default records pu, Line-Line RMS, Each Phase, evaluation from t = 0, tolerance 0", async ({ page }) => {
    await openNewEditor(page);
    await setPoints(page, "lower", [[0, 0.9], [3, 0.9]]);
    const profile = await saveEditor(page, "All Defaults");

    expect(profile.unit).toBe("pu");
    expect(profile.assessment_definition.representation).toBe("line_line_rms");
    expect(profile.assessment_definition.phase_treatment).toBe("each_phase");
    expect(profile.assessment_definition.member).toBeNull();
    expect(profile.assessment_definition.measurement_location).toBe("unspecified");
    expect(profile.assessment_definition.provenance).toBe("unspecified");
    expect(profile.evaluation_start_time).toBe(0);
    expect(profile.tolerance).toBe(0);
    expect([profile.display_start_time, profile.display_end_time]).toEqual([0, 3]);
    expect(profile.evaluation_end_time).toBe(3);
  });
});

test.describe("DEC-166 -- Operating Envelope boundaries and Compliance Region", () => {
  test("lower-only: Compliance Region 'At or Above Lower Boundary', saved with no upper boundary", async ({ page }) => {
    await openNewEditor(page);
    await setPoints(page, "lower", LVRT_POINTS);
    await expect(page.locator("#wwRefEditorComplianceRegion")).toHaveText("At or Above Lower Boundary");
    await expect(page.locator("#wwRefEditorAssessmentSummary")).toHaveText(
      "Assessment: Each VAB, VBC and VCA must remain at or above the lower boundary.",
    );
    const profile = await saveEditor(page, "Lower Only");
    expect(profile.lower_boundary).not.toBeNull();
    expect(profile.upper_boundary).toBeNull();
  });

  test("upper-only: Compliance Region 'At or Below Upper Boundary', saved with no lower boundary", async ({ page }) => {
    await openNewEditor(page);
    await setBoundaries(page, { lower: false, upper: true });
    await setPoints(page, "upper", [[0, 1.1], [3, 1.1]]);
    await expect(page.locator("#wwRefEditorComplianceRegion")).toHaveText("At or Below Upper Boundary");
    await expect(page.locator("#wwRefEditorAssessmentSummary")).toHaveText(
      "Assessment: Each VAB, VBC and VCA must remain at or below the upper boundary.",
    );
    const profile = await saveEditor(page, "Upper Only");
    expect(profile.lower_boundary).toBeNull();
    expect(segmentRows(profile.upper_boundary)).toEqual([[0, 3, 1.1, 1.1, "constant"]]);
  });

  test("lower + upper: Compliance Region 'Inside Envelope', both boundaries saved", async ({ page }) => {
    await openNewEditor(page);
    await setBoundaries(page, { lower: true, upper: true });
    await setPoints(page, "lower", [[0, 0.9], [3, 0.9]]);
    await setPoints(page, "upper", [[0, 1.1], [3, 1.1]]);
    await expect(page.locator("#wwRefEditorComplianceRegion")).toHaveText("Inside Envelope");
    await expect(page.locator("#wwRefEditorAssessmentSummary")).toHaveText(
      "Assessment: Each VAB, VBC and VCA must remain inside the operating envelope.",
    );
    const profile = await saveEditor(page, "Inside Envelope");
    expect(segmentRows(profile.lower_boundary)).toEqual([[0, 3, 0.9, 0.9, "constant"]]);
    expect(segmentRows(profile.upper_boundary)).toEqual([[0, 3, 1.1, 1.1, "constant"]]);
  });

  test("at least one boundary must exist: Save is blocked with a clear message", async ({ page }) => {
    await openNewEditor(page);
    await setPoints(page, "lower", [[0, 0.9], [3, 0.9]]);
    await page.locator("#wwRefEditorName").fill("No Boundary");
    await setBoundaries(page, { lower: false, upper: false });
    await expect(page.locator("#wwRefEditorValidation")).toContainText("Enable a lower boundary, an upper boundary, or both.");
    await expect(page.locator("#wwRefEditorSaveBtn")).toBeDisabled();
    await expect(page.locator("#wwRefEditorComplianceRegion")).toHaveText("Enable a boundary");
  });
});

test.describe("DEC-166 -- point list translation (automatic connection)", () => {
  test("a duplicate timestamp is a CONNECTED vertical edge: preview polyline and stored segments", async ({ page }) => {
    await openNewEditor(page);
    await setPoints(page, "lower", LVRT_POINTS);

    const lower = boundaryTrace(await previewTraces(page), "lower");
    // Consecutive points (0.15, 0) -> (0.15, 0.9) are drawn as one connected polyline.
    expect(lower.x).toEqual([0, 0.15, 0.15, 3]);
    expect(lower.y).toEqual([0, 0, 0.9, 0.9]);

    const profile = await saveEditor(page, "Vertical Edge");
    expect(segmentRows(profile.lower_boundary)).toEqual([
      [0, 0.15, 0, 0, "constant"],
      [0.15, 3, 0.9, 0.9, "constant"],
    ]);
    // The stored segments project straight back to the same four points (lossless).
    expect(profile.point_editable).toBe(true);
    expect(profile.lower_points).toEqual([
      { time: 0, value: 0 }, { time: 0.15, value: 0 }, { time: 0.15, value: 0.9 }, { time: 3, value: 0.9 },
    ]);
  });

  test("horizontal and diagonal edges are inferred, never chosen", async ({ page }) => {
    await openNewEditor(page);
    await setPoints(page, "lower", [[0, 0.2], [1, 0.2], [2, 0.9], [3, 0.9]]);
    const profile = await saveEditor(page, "Edge Inference");
    expect(segmentRows(profile.lower_boundary)).toEqual([
      [0, 1, 0.2, 0.2, "constant"],
      [1, 2, 0.2, 0.9, "linear"],
      [2, 3, 0.9, 0.9, "constant"],
    ]);
  });

  test("a vertical edge saved on an existing profile re-opens as the same point list", async ({ page }) => {
    await openNewEditor(page);
    await setPoints(page, "lower", LVRT_POINTS);
    await saveEditor(page, "Re-open Me");
    await openEditorFor(page, "Re-open Me");
    const rows = page.locator("#wwRefEditorLowerBody tr");
    await expect(rows).toHaveCount(4);
    for (let i = 0; i < LVRT_POINTS.length; i++) {
      await expect(rows.nth(i).locator(".ww-ref-pt-time")).toHaveValue(String(LVRT_POINTS[i][0]));
      await expect(rows.nth(i).locator(".ww-ref-pt-value")).toHaveValue(String(LVRT_POINTS[i][1]));
    }
  });

  test("decreasing time is rejected, never silently sorted", async ({ page }) => {
    await openNewEditor(page);
    await setPoints(page, "lower", [[0, 0.9], [0.15, 0.9], [0.1, 0.5]]);
    await page.locator("#wwRefEditorName").fill("Decreasing");
    await expect(page.locator("#wwRefEditorLowerMessage")).toBeVisible();
    await expect(page.locator("#wwRefEditorLowerMessage")).toContainText("Point 3: time 0.1 s is earlier than the previous point (0.15 s)");
    await expect(page.locator("#wwRefEditorSaveBtn")).toBeDisabled();
    await expect(page.locator("#wwRefEditorLowerBody tr").nth(2)).toHaveAttribute("data-row-error", "true");
    // The order the engineer typed is untouched.
    await expect(page.locator("#wwRefEditorLowerBody tr").nth(1).locator(".ww-ref-pt-time")).toHaveValue("0.15");
    await expect(page.locator("#wwRefEditorLowerBody tr").nth(2).locator(".ww-ref-pt-time")).toHaveValue("0.1");

    // Fixing the point re-enables Save.
    await page.locator("#wwRefEditorLowerBody tr").nth(2).locator(".ww-ref-pt-time").fill("1");
    await expect(page.locator("#wwRefEditorLowerMessage")).toBeHidden();
    await expect(page.locator("#wwRefEditorSaveBtn")).toBeEnabled();
  });

  test("identical consecutive points, hanging vertical edges and half-filled rows are rejected inline", async ({ page }) => {
    await openNewEditor(page);
    await page.locator("#wwRefEditorName").fill("Bad Points");

    await setPoints(page, "lower", [[0, 0.9], [1, 0.9], [1, 0.9]]);
    await expect(page.locator("#wwRefEditorLowerMessage")).toContainText("duplicates the previous point");

    await setPoints(page, "lower", [[0, 0.9], [1, 0.9], [1, 0.2]]);
    await expect(page.locator("#wwRefEditorLowerMessage")).toContainText("vertical edge at the very end");

    await setPoints(page, "lower", [[0, 0], [0, 0.9], [1, 0.9]]);
    await expect(page.locator("#wwRefEditorLowerMessage")).toContainText("vertical edge at the very start");

    await setPoints(page, "lower", [[0, 0.9], [1, 0.9]]);
    await page.locator("#wwRefEditorLowerAddRowBtn").click();
    await page.locator("#wwRefEditorLowerBody tr").nth(2).locator(".ww-ref-pt-time").fill("2");
    await expect(page.locator("#wwRefEditorLowerMessage")).toContainText("point 3: enter both a time and a voltage");
    await expect(page.locator("#wwRefEditorSaveBtn")).toBeDisabled();

    // A fully blank extra row carries no data and is simply ignored.
    await page.locator("#wwRefEditorLowerBody tr").nth(2).locator(".ww-ref-pt-time").fill("");
    await expect(page.locator("#wwRefEditorLowerMessage")).toBeHidden();
    await expect(page.locator("#wwRefEditorSaveBtn")).toBeEnabled();
  });

  test("a single point is not a boundary", async ({ page }) => {
    await openNewEditor(page);
    await page.locator("#wwRefEditorName").fill("One Point");
    await setPoints(page, "lower", [[0, 0.9]]);
    await expect(page.locator("#wwRefEditorLowerMessage")).toContainText("at least two points");
    await expect(page.locator("#wwRefEditorSaveBtn")).toBeDisabled();
  });

  test("negative-time points are accepted; evaluation still starts at t = 0", async ({ page }) => {
    await openNewEditor(page);
    await setPoints(page, "lower", [[-0.2, 1], [0, 1], [0.15, 0], [3, 0.9]]);
    await expect(page.locator("#wwRefEditorLowerMessage")).toBeHidden();
    const profile = await saveEditor(page, "Pre-disturbance");
    expect(profile.display_start_time).toBe(-0.2);
    expect(profile.evaluation_start_time).toBe(0);
    expect(profile.lower_boundary.segments[0].start_time).toBe(-0.2);
  });

  test("keyboard: Enter in the last voltage cell appends a point and focuses its time cell", async ({ page }) => {
    await openNewEditor(page);
    const rows = page.locator("#wwRefEditorLowerBody tr");
    await rows.nth(1).locator(".ww-ref-pt-value").focus();
    await page.keyboard.press("Enter");
    await expect(rows).toHaveCount(3);
    await expect(rows.nth(2).locator(".ww-ref-pt-time")).toBeFocused();
  });
});

test.describe("DEC-166 -- boundary consistency (no inverted envelope)", () => {
  test("a lower boundary above the upper boundary is rejected, names the interval, and is never repaired", async ({ page }) => {
    await openNewEditor(page);
    await setBoundaries(page, { lower: true, upper: true });
    await setPoints(page, "lower", [[0, 1.2], [3, 1.2]]);
    await setPoints(page, "upper", [[0, 1.1], [3, 1.1]]);
    await page.locator("#wwRefEditorName").fill("Inverted");
    await expect(page.locator("#wwRefEditorValidation")).toContainText("The lower boundary rises above the upper boundary between t = 0 s and t = 3 s");
    await expect(page.locator("#wwRefEditorSaveBtn")).toBeDisabled();
    // Offending rows are marked in both tables; values are not swapped.
    await expect(page.locator("#wwRefEditorLowerBody tr").first()).toHaveAttribute("data-row-error", "true");
    await expect(page.locator("#wwRefEditorUpperBody tr").first()).toHaveAttribute("data-row-error", "true");
    await expect(page.locator("#wwRefEditorLowerBody tr").first().locator(".ww-ref-pt-value")).toHaveValue("1.2");
    // No shading is drawn for an invalid envelope.
    expect((await previewTraces(page)).some((t) => t.role === "region")).toBe(false);

    // Correcting the lower boundary clears the error.
    await setPoints(page, "lower", [[0, 0.9], [3, 0.9]]);
    await expect(page.locator("#wwRefEditorValidation")).not.toContainText("rises above");
    await expect(page.locator("#wwRefEditorSaveBtn")).toBeEnabled();
  });

  test("a crossing that only appears part-way along a ramp is still caught", async ({ page }) => {
    await openNewEditor(page);
    await setBoundaries(page, { lower: true, upper: true });
    await setPoints(page, "lower", [[0, 0.5], [3, 1.5]]);
    await setPoints(page, "upper", [[0, 1.0], [3, 1.0]]);
    await page.locator("#wwRefEditorName").fill("Ramp Cross");
    await expect(page.locator("#wwRefEditorValidation")).toContainText("rises above the upper boundary");
    await expect(page.locator("#wwRefEditorSaveBtn")).toBeDisabled();
  });

  test("boundaries with different extents are accepted; display range is the union", async ({ page }) => {
    await openNewEditor(page);
    await setBoundaries(page, { lower: true, upper: true });
    await setPoints(page, "lower", [[-0.5, 0.8], [3, 0.8]]);
    await setPoints(page, "upper", [[0, 1.1], [5, 1.1]]);
    await page.locator("#wwRefEditorName").fill("Union Extent");
    await expect(page.locator("#wwRefEditorValidation")).toHaveText("");
    await page.locator("#wwRefEditorAdvanced summary").click();
    await expect(page.locator("#wwRefEditorDisplayStart")).toHaveValue("-0.5");
    await expect(page.locator("#wwRefEditorDisplayEnd")).toHaveValue("5");
    const profile = await saveEditor(page, "Union Extent");
    expect([profile.display_start_time, profile.display_end_time]).toEqual([-0.5, 5]);
    expect(profile.lower_boundary.segments[0].end_time).toBe(3); // no requirement invented beyond a boundary's own extent
    expect(profile.upper_boundary.segments[0].end_time).toBe(5);
  });
});

test.describe("DEC-166 -- Phase Evaluation and the generated assessment summary", () => {
  test("Minimum / Maximum / Each Phase summaries update immediately; no voltage selector outside Single", async ({ page }) => {
    await openNewEditor(page);
    await setPoints(page, "lower", [[0, 0.9], [3, 0.9]]);
    const summary = page.locator("#wwRefEditorAssessmentSummary");
    const member = page.locator("#wwRefEditorMemberField");

    await page.locator("#wwRefEditorPhaseTreatment").selectOption("minimum");
    await expect(summary).toHaveText("Assessment: The minimum of VAB, VBC and VCA must remain at or above the lower boundary.");
    await expect(member).toBeHidden();

    await setBoundaries(page, { lower: false, upper: true });
    await setPoints(page, "upper", [[0, 1.1], [3, 1.1]]);
    await page.locator("#wwRefEditorPhaseTreatment").selectOption("maximum");
    await expect(summary).toHaveText("Assessment: The maximum of VAB, VBC and VCA must remain at or below the upper boundary.");
    await expect(member).toBeHidden();

    await page.locator("#wwRefEditorPhaseTreatment").selectOption("each_phase");
    await expect(summary).toHaveText("Assessment: Each VAB, VBC and VCA must remain at or below the upper boundary.");
    await expect(member).toBeHidden();

    const profile = await (async () => {
      await page.locator("#wwRefEditorPhaseTreatment").selectOption("maximum");
      return saveEditor(page, "Maximum Phase");
    })();
    expect(profile.assessment_definition.phase_treatment).toBe("maximum");
    expect(profile.assessment_definition.member).toBeNull();
  });

  test("Single reveals the VAB / VBC / VCA selector only then, and the summary names the chosen voltage", async ({ page }) => {
    await openNewEditor(page);
    await setBoundaries(page, { lower: false, upper: true });
    await setPoints(page, "upper", [[0, 1.1], [3, 1.1]]);
    await expect(page.locator("#wwRefEditorMemberField")).toBeHidden();

    await page.locator("#wwRefEditorPhaseTreatment").selectOption("single");
    await expect(page.locator("#wwRefEditorMemberField")).toBeVisible();
    // Native <option> text is plain notation by design (AGENTS.md rule 3).
    await expect(page.locator("#wwRefEditorMember option")).toHaveText(["VAB", "VBC", "VCA"]);
    await expect(page.locator("#wwRefEditorAssessmentSummary")).toHaveText("Assessment: VAB must remain at or below the upper boundary.");

    await page.locator("#wwRefEditorMember").selectOption("BC");
    await expect(page.locator("#wwRefEditorAssessmentSummary")).toHaveText("Assessment: VBC must remain at or below the upper boundary.");
    await expectTrueSubscripts(page.locator("#wwRefEditorAssessmentSummary .ww-electrical-symbol"), 1);

    const profile = await saveEditor(page, "Single VBC");
    expect(profile.assessment_definition.phase_treatment).toBe("single");
    expect(profile.assessment_definition.member).toBe("BC");

    // Leaving Single hides the selector again.
    await openEditorFor(page, "Single VBC");
    await expect(page.locator("#wwRefEditorMember")).toHaveValue("BC");
    await page.locator("#wwRefEditorPhaseTreatment").selectOption("each_phase");
    await expect(page.locator("#wwRefEditorMemberField")).toBeHidden();
  });

  test("summary symbols are true subscripts (DEC-117)", async ({ page }) => {
    await openNewEditor(page);
    await setPoints(page, "lower", [[0, 0.9], [3, 0.9]]);
    await expectTrueSubscripts(page.locator("#wwRefEditorAssessmentSummary .ww-electrical-symbol"), 3);
    await page.locator("#wwRefEditorPhaseTreatment").selectOption("minimum");
    await expectTrueSubscripts(page.locator("#wwRefEditorAssessmentSummary .ww-electrical-symbol"), 3);
  });
});

test.describe("DEC-166 -- live preview", () => {
  test("the preview redraws as points change and shades the valid region between two boundaries", async ({ page }) => {
    await openNewEditor(page);
    await setPoints(page, "lower", [[0, 0.8], [3, 0.8]]);
    let traces = await previewTraces(page);
    expect(boundaryTrace(traces, "lower").y).toEqual([0.8, 0.8]);
    expect(traces.some((t) => t.role === "region")).toBe(false);

    await page.locator("#wwRefEditorLowerBody tr").nth(1).locator(".ww-ref-pt-value").fill("0.7");
    traces = await previewTraces(page);
    expect(boundaryTrace(traces, "lower").y).toEqual([0.8, 0.7]);

    await setBoundaries(page, { lower: true, upper: true });
    await setPoints(page, "upper", [[0, 1.1], [3, 1.1]]);
    traces = await previewTraces(page);
    expect(boundaryTrace(traces, "upper").dash).toBe("dash");
    const region = traces.find((t) => t.role === "region");
    expect(region, "valid-region shading").toBeTruthy();
    expect(region.fill).toBe("toself");
    // The ring spans both boundaries: lower left->right, upper right->left, closed.
    expect(region.x).toEqual([0, 3, 3, 0, 0]);
    expect(region.y).toEqual([0.8, 0.7, 1.1, 1.1, 0.8]);

    await setBoundaries(page, { lower: true, upper: false });
    traces = await previewTraces(page);
    expect(traces.some((t) => t.boundary === "upper")).toBe(false);
    expect(traces.some((t) => t.role === "region")).toBe(false);
  });

  test("shading is limited to the span where BOTH boundaries are defined", async ({ page }) => {
    await openNewEditor(page);
    await setBoundaries(page, { lower: true, upper: true });
    await setPoints(page, "lower", [[-1, 0.8], [3, 0.8]]);
    await setPoints(page, "upper", [[0, 1.1], [2, 1.1]]);
    const region = (await previewTraces(page)).find((t) => t.role === "region");
    expect(Math.min(...region.x)).toBe(0);
    expect(Math.max(...region.x)).toBe(2);
  });

  test("the preview axis follows the Unit override", async ({ page }) => {
    await openNewEditor(page);
    await setPoints(page, "lower", [[0, 0.9], [3, 0.9]]);
    await page.locator("#wwRefEditorAdvanced summary").click();
    await page.locator("#wwRefEditorUnit").selectOption("kV");
    await expect(page.locator(".ww-ref-voltage-heading").first()).toHaveText("Voltage (kV)");
    const title = await page.evaluate(() => {
      const t = document.getElementById("wwRefEditorPreviewPlot").layout.yaxis.title;
      return typeof t === "string" ? t : t.text;
    });
    expect(title).toBe("Voltage (kV)");
  });
});

test.describe("DEC-166 -- Advanced Settings and metadata", () => {
  test("Auto display/evaluation windows track the points; overrides persist", async ({ page }) => {
    await openNewEditor(page);
    await page.locator("#wwRefEditorAdvanced summary").click();
    await setPoints(page, "lower", [[-0.2, 1], [3, 1]]);
    await expect(page.locator("#wwRefEditorDisplayStart")).toHaveValue("-0.2");
    await expect(page.locator("#wwRefEditorDisplayStart")).toBeDisabled();
    await expect(page.locator("#wwRefEditorDisplayEnd")).toHaveValue("3");
    await expect(page.locator("#wwRefEditorEvalEnd")).toHaveValue("3");
    await expect(page.locator("#wwRefEditorEvalStart")).toHaveValue("0");

    // Evaluation end follows the automatic display end.
    await page.locator("#wwRefEditorLowerBody tr").nth(1).locator(".ww-ref-pt-time").fill("5");
    await expect(page.locator("#wwRefEditorDisplayEnd")).toHaveValue("5");
    await expect(page.locator("#wwRefEditorEvalEnd")).toHaveValue("5");

    // Overrides.
    await page.locator("#wwRefEditorUnit").selectOption("kV");
    await page.locator("#wwRefEditorRepresentation").selectOption("phase_ground_rms");
    await expect(page.locator("#wwRefEditorAssessmentSummary")).toHaveText(
      "Assessment: Each VA, VB and VC must remain at or above the lower boundary.",
    );
    await page.locator("#wwRefEditorEvalStart").fill("0.1");
    await page.locator("#wwRefEditorTolerance").fill("0.02");
    await page.locator("#wwRefEditorDisplayEndAuto").setChecked(false);
    await expect(page.locator("#wwRefEditorDisplayEnd")).toBeEnabled();
    await page.locator("#wwRefEditorDisplayEnd").fill("6");
    await expect(page.locator("#wwRefEditorEvalEnd")).toHaveValue("6"); // still tracking (Auto)
    await page.locator("#wwRefEditorEvalEndAuto").setChecked(false);
    await page.locator("#wwRefEditorEvalEnd").fill("4");

    const profile = await saveEditor(page, "Overrides");
    expect(profile.unit).toBe("kV");
    expect(profile.assessment_definition.representation).toBe("phase_ground_rms");
    expect(profile.evaluation_start_time).toBe(0.1);
    expect(profile.tolerance).toBe(0.02);
    expect([profile.display_start_time, profile.display_end_time]).toEqual([-0.2, 6]);
    expect(profile.evaluation_end_time).toBe(4);

    // Re-opening shows the overrides as overrides (Advanced open, Auto cleared where overridden).
    await openEditorFor(page, "Overrides");
    await expect(page.locator("#wwRefEditorAdvanced")).toHaveAttribute("open", "");
    await expect(page.locator("#wwRefEditorDisplayStartAuto")).toBeChecked();
    await expect(page.locator("#wwRefEditorDisplayEndAuto")).not.toBeChecked();
    await expect(page.locator("#wwRefEditorEvalEndAuto")).not.toBeChecked();
    await expect(page.locator("#wwRefEditorDisplayEnd")).toHaveValue("6");
  });

  test("an evaluation window that is not after its start is rejected", async ({ page }) => {
    await openNewEditor(page);
    await setPoints(page, "lower", [[-0.5, 0.9], [-0.1, 0.9]]); // entirely before t = 0
    await page.locator("#wwRefEditorName").fill("Pre Only");
    await expect(page.locator("#wwRefEditorValidation")).toContainText("Evaluation end (-0.1 s) must be later than evaluation start (0 s)");
    await expect(page.locator("#wwRefEditorSaveBtn")).toBeDisabled();
  });

  test("Reference Source / Metadata stays usable and is saved; location and interpretation source are gone", async ({ page }) => {
    await openNewEditor(page);
    await setPoints(page, "lower", [[0, 0.9], [3, 0.9]]);
    await page.locator("#wwRefEditorMetadata summary").click();
    await page.locator("#wwRefEditorMetaJurisdiction").fill("Malaysia");
    await page.locator("#wwRefEditorMetaDocumentTitle").fill("Grid Code");
    await page.locator("#wwRefEditorMetaDocumentRevision").fill("2025");
    await page.locator("#wwRefEditorMetaSourceSection").fill("4.2");
    await page.locator("#wwRefEditorMetaSourcePage").fill("17");
    await page.locator("#wwRefEditorMetaNotes").fill("Fault ride-through");
    const profile = await saveEditor(page, "With Metadata");
    expect(profile.metadata).toMatchObject({
      jurisdiction: "Malaysia", document_title: "Grid Code", document_revision: "2025",
      source_section: "4.2", source_page: "17", notes: "Fault ride-through", authority: null,
    });
  });
});

test.describe("DEC-166 -- legacy / imported profiles keep their engineering meaning", () => {
  const GAP = { segments: [
    { start_time: 0, end_time: 1, start_value: 0.9, end_value: 0.9, segment_type: "constant" },
    { start_time: 2, end_time: 3, start_value: 0.9, end_value: 0.9, segment_type: "constant" },
  ] };

  test("a profile with a gap opens with read-only boundaries and is saved back unchanged", async ({ page }) => {
    await openCompliance(page);
    await createViaApi(page, {
      name: "Gap Profile", lower_boundary: GAP, display_end_time: 3,
      assessment_definition: { representation: "line_line_rms", phase_treatment: "minimum", measurement_location: "connection_point", provenance: "project_agreement" },
    });
    await page.reload();
    await page.locator("#mainNavComplianceBtn").click();
    await openEditorFor(page, "Gap Profile");

    await expect(page.locator("#wwRefEditorLegacyNotice")).toBeVisible();
    await expect(page.locator("#wwRefEditorLowerTable")).toBeHidden();
    await expect(page.locator("#wwRefEditorLowerAddRowBtn")).toBeHidden();
    await expect(page.locator("#wwRefEditorLowerLegacyTable")).toBeVisible();
    await expect(page.locator("#wwRefEditorLowerLegacyBody tr")).toHaveCount(2);
    await expect(page.locator("#wwRefEditorLowerEnabled")).toBeDisabled();
    // The preview draws the gap as a line break.
    const lower = boundaryTrace(await previewTraces(page), "lower");
    expect(lower.y).toContain(null);

    // Everything else stays editable.
    const profile = await saveEditor(page, "Gap Profile Renamed");
    expect(profile.lower_boundary).toEqual(GAP);
    expect(profile.assessment_definition.measurement_location).toBe("connection_point");
    expect(profile.assessment_definition.provenance).toBe("project_agreement");
    expect(profile.assessment_definition.phase_treatment).toBe("minimum");
    expect(profile.point_editable).toBe(false);
  });

  test("a fully unspecified legacy assessment definition is preserved, not replaced by a default", async ({ page }) => {
    await openCompliance(page);
    await createViaApi(page, { name: "Unspecified Legacy", assessment_definition: {} });
    await page.reload();
    await page.locator("#mainNavComplianceBtn").click();
    await openEditorFor(page, "Unspecified Legacy");
    await expect(page.locator("#wwRefEditorRepresentation")).toHaveValue("unspecified");
    await expect(page.locator("#wwRefEditorPhaseTreatment")).toHaveValue("unspecified");
    await expect(page.locator("#wwRefEditorRepresentation option[data-legacy]")).toHaveText("Unspecified (legacy)");
    await expect(page.locator("#wwRefEditorPhaseTreatment option[data-legacy]")).toHaveText("Not specified (legacy)");
    await expect(page.locator("#wwRefEditorAssessmentSummary")).toHaveText("Assessment: The assessed voltage must remain at or above the lower boundary.");

    const profile = await saveEditor(page, "Unspecified Legacy Renamed");
    expect(profile.assessment_definition.representation).toBe("unspecified");
    expect(profile.assessment_definition.phase_treatment).toBe("unspecified");
  });

  test("a stored display window that differs from the derived extent is kept as an explicit override", async ({ page }) => {
    await openCompliance(page);
    await createViaApi(page, { name: "Wide Display", display_start_time: -1, display_end_time: 4, evaluation_end_time: 3 });
    await page.reload();
    await page.locator("#mainNavComplianceBtn").click();
    await openEditorFor(page, "Wide Display");
    await expect(page.locator("#wwRefEditorAdvanced")).toHaveAttribute("open", "");
    await expect(page.locator("#wwRefEditorDisplayStartAuto")).not.toBeChecked();
    await expect(page.locator("#wwRefEditorDisplayStart")).toHaveValue("-1");
    const profile = await saveEditor(page, "Wide Display Renamed");
    expect([profile.display_start_time, profile.display_end_time, profile.evaluation_end_time]).toEqual([-1, 4, 3]);
  });

  test("export then import keeps a vertical-edge envelope point-editable and identical", async ({ page }) => {
    await openNewEditor(page);
    await setBoundaries(page, { lower: true, upper: true });
    await setPoints(page, "lower", LVRT_POINTS);
    await setPoints(page, "upper", [[0, 1.1], [3, 1.1]]);
    const original = await saveEditor(page, "Portable Envelope");

    const workspaceId = await workspaceIdOf(page);
    const envelope = await (await page.request.get(`${profilesUrl(workspaceId)}/${encodeURIComponent(original.id)}/export`)).json();
    expect(envelope.schema_version).toBe(2);
    expect(envelope.profile.lower_boundary.segments).toHaveLength(2);

    const imported = await (await page.request.post(`${profilesUrl(workspaceId)}/import`, { data: envelope })).json();
    expect(imported.id).not.toBe(original.id);
    expect(imported.point_editable).toBe(true);
    expect(imported.lower_points).toEqual(original.lower_points);
    expect(imported.upper_points).toEqual(original.upper_points);
    expect(imported.assessment_definition).toEqual(original.assessment_definition);
  });
});

test.describe("DEC-166 -- frontend translation mirrors the backend (golden vectors)", () => {
  test("wwRefEnvPointsToSegments matches every point -> segment vector", async ({ page }) => {
    await openCompliance(page);
    for (const vector of VECTORS.points_to_segments) {
      const result = await page.evaluate(
        (points) => wwRefEnvPointsToSegments(points.map(([time, value]) => ({ time, value }))), vector.points,
      );
      if (vector.error) {
        expect(result.error && result.error.code, vector.name).toBe(vector.error);
        expect(result.error.index ?? null, `${vector.name} index`).toBe(vector.error_point_index ?? null);
      } else {
        expect(result.error, vector.name).toBeUndefined();
        expect(result.segments.map((s) => [s.start_time, s.end_time, s.start_value, s.end_value, s.segment_type]), vector.name)
          .toEqual(vector.segments);
      }
    }
  });

  test("wwRefEnvFindCrossing matches every crossing vector", async ({ page }) => {
    await openCompliance(page);
    for (const vector of VECTORS.crossing) {
      const crossing = await page.evaluate(({ lower, upper }) => {
        const toSegments = (rows) => wwRefEnvPointsToSegments(rows.map(([time, value]) => ({ time, value }))).segments;
        return wwRefEnvFindCrossing(toSegments(lower), toSegments(upper));
      }, { lower: vector.lower, upper: vector.upper });
      expect(crossing !== null, vector.name).toBe(vector.crosses);
      if (vector.crosses) expect(crossing.time, vector.name).toBe(vector.time);
    }
  });
});

test.describe("boundary point inputs use the app's standard form-control style", () => {
  const STYLE_PROPS = [
    "height", "borderTopLeftRadius", "borderTopColor", "borderTopWidth", "backgroundColor", "paddingLeft", "paddingRight",
    "paddingTop", "paddingBottom", "fontFamily", "fontSize", "color",
  ];
  const styleOf = (locator) => locator.evaluate((el, props) => {
    const cs = getComputedStyle(el);
    return Object.fromEntries(props.map((p) => [p, cs[p]]));
  }, STYLE_PROPS);

  test("Time and Voltage inputs match the standard text input (Name) in every box property", async ({ page }) => {
    await openNewEditor(page);
    await setBoundaries(page, { lower: true, upper: true });
    await setPoints(page, "lower", [[0, 0.9], [3, 0.9]]);
    await setPoints(page, "upper", [[0, 1.1], [3, 1.1]]);
    const reference = await styleOf(page.locator("#wwRefEditorName"));
    for (const selector of [
      "#wwRefEditorLowerBody .ww-ref-pt-time", "#wwRefEditorLowerBody .ww-ref-pt-value",
      "#wwRefEditorUpperBody .ww-ref-pt-time", "#wwRefEditorUpperBody .ww-ref-pt-value",
    ]) {
      const style = await styleOf(page.locator(selector).first());
      for (const prop of STYLE_PROPS) {
        // Height may differ only by the native number-input line box; compare within 2px.
        if (prop === "height") expect(Math.abs(parseFloat(style.height) - parseFloat(reference.height)), selector).toBeLessThanOrEqual(2);
        else expect(style[prop], `${selector} ${prop}`).toBe(reference[prop]);
      }
    }
  });

  test("focus uses the standard highlight; a lower and upper row are aligned and symmetrical", async ({ page }) => {
    await openNewEditor(page);
    await setBoundaries(page, { lower: true, upper: true });
    await setPoints(page, "lower", [[0, 0.9], [3, 0.9]]);
    await setPoints(page, "upper", [[0, 1.1], [3, 1.1]]);
    const time = page.locator("#wwRefEditorLowerBody .ww-ref-pt-time").first();
    const resting = await time.evaluate((el) => getComputedStyle(el).borderTopColor);
    await time.focus();
    const focused = await time.evaluate((el) => ({ border: getComputedStyle(el).borderTopColor, outline: getComputedStyle(el).outlineStyle }));
    expect(focused.border).not.toBe(resting);
    await page.locator("#wwRefEditorName").focus();
    const nameFocus = await page.locator("#wwRefEditorName").evaluate((el) => getComputedStyle(el).borderTopColor);
    expect(focused.border).toBe(nameFocus); // exactly the standard focus colour
    expect(focused.outline).toBe("none");

    const box = (selector) => page.locator(selector).first().boundingBox();
    const lowerTime = await box("#wwRefEditorLowerBody .ww-ref-pt-time");
    const lowerValue = await box("#wwRefEditorLowerBody .ww-ref-pt-value");
    const upperTime = await box("#wwRefEditorUpperBody .ww-ref-pt-time");
    const upperValue = await box("#wwRefEditorUpperBody .ww-ref-pt-value");
    expect(Math.abs(lowerTime.width - lowerValue.width)).toBeLessThanOrEqual(1); // consistent widths
    expect(Math.abs(lowerTime.width - upperTime.width)).toBeLessThanOrEqual(1); // symmetrical sections
    expect(Math.abs(lowerValue.width - upperValue.width)).toBeLessThanOrEqual(1);
    expect(Math.abs(lowerTime.y - upperTime.y)).toBeLessThanOrEqual(1); // rows align across sections
    // The delete control is centred on the row, and row numbers align with the field centre.
    const remove = await box("#wwRefEditorLowerBody .ww-ref-segment-row-remove");
    const index = await box("#wwRefEditorLowerBody .ww-ref-pt-index");
    expect(Math.abs((remove.y + remove.height / 2) - (lowerTime.y + lowerTime.height / 2))).toBeLessThanOrEqual(2);
    expect(Math.abs((index.y + index.height / 2) - (lowerTime.y + lowerTime.height / 2))).toBeLessThanOrEqual(2);
  });

  test("the invalid state marks the specific field with the app's error tokens", async ({ page }) => {
    await openNewEditor(page);
    await page.locator("#wwRefEditorName").fill("Invalid Fields");
    await setPoints(page, "lower", [[0, 0.9], [0.15, 0.9], [0.1, 0.5]]); // time decreases at point 3
    const rows = page.locator("#wwRefEditorLowerBody tr");
    const badTime = rows.nth(2).locator(".ww-ref-pt-time");
    await expect(badTime).toHaveAttribute("aria-invalid", "true");
    await expect(rows.nth(2).locator(".ww-ref-pt-value")).not.toHaveAttribute("aria-invalid", "true");
    await expect(rows.nth(1).locator(".ww-ref-pt-time")).not.toHaveAttribute("aria-invalid", "true");
    const invalid = await badTime.evaluate((el) => {
      const probe = document.createElement("div");
      document.body.appendChild(probe);
      probe.style.color = "var(--error)";
      const error = getComputedStyle(probe).color;
      probe.style.backgroundColor = "var(--error-wash)";
      const wash = getComputedStyle(probe).backgroundColor;
      probe.remove();
      const cs = getComputedStyle(el);
      return { border: cs.borderTopColor, background: cs.backgroundColor, error, wash };
    });
    expect(invalid.border).toBe(invalid.error);
    expect(invalid.background).toBe(invalid.wash);
    await rows.nth(2).locator(".ww-ref-pt-time").fill("1");
    await expect(rows.nth(2).locator(".ww-ref-pt-time")).not.toHaveAttribute("aria-invalid", "true");

    // Incomplete row: only the empty field is flagged.
    await page.locator("#wwRefEditorLowerAddRowBtn").click();
    await rows.nth(3).locator(".ww-ref-pt-time").fill("2");
    await expect(rows.nth(3).locator(".ww-ref-pt-value")).toHaveAttribute("aria-invalid", "true");
    await expect(rows.nth(3).locator(".ww-ref-pt-time")).not.toHaveAttribute("aria-invalid", "true");

    // Crossing: the offending rows' voltage fields are flagged.
    await setPoints(page, "lower", [[0, 1.2], [3, 1.2]]);
    await setBoundaries(page, { lower: true, upper: true });
    await setPoints(page, "upper", [[0, 1.1], [3, 1.1]]);
    await expect(page.locator("#wwRefEditorLowerBody .ww-ref-pt-value").first()).toHaveAttribute("aria-invalid", "true");
  });

  test("unit heading stays dynamic; keyboard entry, Add Point and delete still work in the restyled table", async ({ page }) => {
    await openNewEditor(page);
    await page.locator("#wwRefEditorAdvanced summary").click();
    for (const unit of ["kV", "V", "pu"]) {
      await page.locator("#wwRefEditorUnit").selectOption(unit);
      await expect(page.locator(".ww-ref-voltage-heading").first()).toHaveText(`Voltage (${unit})`);
    }
    await setPoints(page, "lower", [[0, 0.9], [1, 0.9], [2, 0.9]]);
    await expect(page.locator("#wwRefEditorLowerBody tr")).toHaveCount(3);
    await page.locator("#wwRefEditorLowerBody tr").nth(1).locator(".ww-ref-segment-row-remove").click();
    await expect(page.locator("#wwRefEditorLowerBody tr")).toHaveCount(2);
    await expect(page.locator("#wwRefEditorLowerBody .ww-ref-pt-index")).toHaveText(["1", "2"]);
    // Tab walks Time -> Voltage within a row.
    await page.locator("#wwRefEditorLowerBody .ww-ref-pt-time").first().focus();
    await page.keyboard.press("Tab");
    await expect(page.locator("#wwRefEditorLowerBody .ww-ref-pt-value").first()).toBeFocused();
    // Native numeric entry still accepts a decimal value.
    await page.locator("#wwRefEditorLowerBody .ww-ref-pt-value").first().fill("0.875");
    await expect(page.locator("#wwRefEditorLowerBody .ww-ref-pt-value").first()).toHaveValue("0.875");
  });
});
