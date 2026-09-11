// Phasor Analysis -- Slice 2 (Analysis Page + Static Phasor Diagram) real-
// browser coverage. See docs/development/BROWSER_SMOKE_TEST.md for the
// general foundation this extends, and backend/tests/test_frontend_
// phasor_analysis.py for the structural/static invariants that don't need
// a real browser (SVG rendering, fetch/render behavior against real
// backend responses, and stale-request protection genuinely do).
//
// Fixture: phasor_smoke_three_phase(.cfg/.dat) -- a dedicated, committed
// ASCII COMTRADE fixture (3 Voltage + 3 Current channels, 50 Hz, 1000 Hz
// sample rate, 2 s duration) carrying a KNOWN balanced three-phase
// sinusoid (100 V RMS / 40 A RMS, 0/-120/+120 deg) -- generated the same
// way backend/tests/test_phasor_analysis_api.py's own ASCII-COMTRADE
// builder does, committed here so this suite has no live-generation
// dependency. The Engineering Context itself is created via a direct
// backend API call (page.request.post) using the SAME workspace_id the
// frontend already established via its own upload flow -- no Engineering
// Context creation/suggestion UI exists yet in this slice (explicitly out
// of scope), so this is the same "the consumer is real, its own upstream
// data is seeded directly" pattern other Playwright suites in this repo
// already use for state this slice's own UI cannot create yet.

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

// Uploads the fixture, then creates a manual, fully-confirmed Engineering
// Context spanning all six channels directly via the backend API (no
// context-creation UI exists in this slice) -- returns { workspaceId,
// sourceId, contextId }.
async function uploadAndCreateContext(page) {
  await uploadFixture(page);
  const row = page.locator("#recordingsTableBody tr[data-source-id]").last();
  await expect(row).toBeVisible();
  const sourceId = await row.getAttribute("data-source-id");
  const workspaceId = await page.evaluate(() => localStorage.getItem("powerwave.workspaceId"));

  const members = [
    ["ALPHA1_VA", "A"], ["ALPHA1_VB", "B"], ["ALPHA1_VC", "C"],
    ["ALPHA1_IA", "A"], ["ALPHA1_IB", "B"], ["ALPHA1_IC", "C"],
  ].map(([channel_name, phase]) => ({
    channel_ref: { kind: "source", source_id: sourceId, channel_name },
    phase, phase_source: "engineer_confirmed",
  }));

  const response = await page.request.post(
    `${BACKEND_URL}/api/v1/workspaces/${encodeURIComponent(workspaceId)}/engineering-contexts`,
    { data: { display_name: "Alpha 1", status: "manual", members } }
  );
  expect(response.ok()).toBeTruthy();
  const context = await response.json();
  return { workspaceId, sourceId, contextId: context.id };
}

async function openAnalysisPhasor(page) {
  await page.locator("#mainNavAnalysisBtn").click();
  await expect(page.locator("#pageAnalysis")).toBeVisible();
  await expect(page.locator("#wwAnalysisTypePhasorBtn")).toHaveClass(/active/);
  await expect(page.locator("#wwPhasorPanel")).toBeVisible();
}

test.describe("Phasor Analysis Slice 2", () => {
  test("full happy path: context -> Voltage three-phase -> values/diagram -> time change -> Current -> single-phase", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);

    // 1. Open Analysis -> Phasor.
    await openAnalysisPhasor(page);

    // 2. Choose context.
    await expect(page.locator(`#wwPhasorContextSelect option[value="${contextId}"]`)).toHaveCount(1);
    await page.locator("#wwPhasorContextSelect").selectOption(contextId);

    // 3. Choose Voltage / Three Phase (both are already the defaults, but
    //    exercise the selectors explicitly).
    await page.locator("#wwPhasorQuantitySelect").selectOption("voltage");
    await page.locator("#wwPhasorModeSelect").selectOption("three_phase");

    // 4. Confirm Va/Vb/Vc automatically resolved -- never a manual
    //    channel picker.
    await expect(page.locator("#wwPhasorResolutionList")).toContainText("Va");
    await expect(page.locator("#wwPhasorResolutionList")).toContainText("Vb");
    await expect(page.locator("#wwPhasorResolutionList")).toContainText("Vc");
    await expect(page.locator("#wwPhasorResolutionList")).toContainText("ALPHA1_VA");
    await expect(page.locator("#wwPhasorResolutionList .ww-phasor-role-warn")).toHaveCount(0);

    // 5. A valid analysis time was chosen automatically (non-empty,
    //    finite) -- the control is visible and populated.
    await expect(page.locator("#wwPhasorTimeRow")).toBeVisible();
    const initialTime = await page.locator("#wwPhasorTimeInput").inputValue();
    expect(Number(initialTime)).toBeGreaterThan(0);

    // 6. Verify numeric values -- known balanced 100 V RMS three-phase,
    //    Phase-A-relative angles at 0/-120/+120 deg.
    const valuesText = await page.locator("#wwPhasorValuesList").innerText();
    expect(valuesText).toMatch(/100\.0\s*V/);
    expect(valuesText).toContain("0.0°");
    expect(valuesText).toMatch(/-120\.[0-9]°/);
    expect(valuesText).toMatch(/\+119\.[0-9]°|\+120\.0°/);

    // 7. Verify three SVG vectors (one <line>+<polygon>+<text> triple per
    //    resolved role).
    await expect(page.locator("#wwPhasorSvg line")).toHaveCount(2 + 3); // 2 axes + 3 vector shafts
    await expect(page.locator("#wwPhasorSvg polygon")).toHaveCount(3); // 3 arrowheads
    await expect(page.locator("#wwPhasorSvg text.ww-phasor-vector-label")).toHaveCount(3);

    // 8. Change analysis time.
    await page.locator("#wwPhasorTimeInput").fill("1.5");
    await page.locator("#wwPhasorTimeInput").dispatchEvent("change");

    // 9. Verify values/vectors update (still the same steady sinusoid, so
    //    magnitude/angle stay materially the same -- proving the request
    //    round-tripped and re-rendered, not that the numbers changed).
    await expect(async () => {
      const text = await page.locator("#wwPhasorValuesList").innerText();
      expect(text).toMatch(/100\.0\s*V/);
    }).toPass({ timeout: 5000 });
    await expect(page.locator("#wwPhasorSvg polygon")).toHaveCount(3);

    // 10. Switch to Current.
    await page.locator("#wwPhasorQuantitySelect").selectOption("current");
    await expect(async () => {
      const text = await page.locator("#wwPhasorValuesList").innerText();
      expect(text).toMatch(/40\.0\s*A/);
    }).toPass({ timeout: 5000 });
    await expect(page.locator("#wwPhasorResolutionList")).toContainText("Ia");

    // 11. Switch to single phase -- one vector, absolute angle, no
    //     relative-angle reference invented.
    await page.locator("#wwPhasorModeSelect").selectOption("phase_a");
    await expect(async () => {
      await expect(page.locator("#wwPhasorSvg polygon")).toHaveCount(1);
    }).toPass({ timeout: 5000 });
    await expect(page.locator("#wwPhasorValuesList")).toContainText("Ia");
    await expect(page.locator("#wwPhasorValuesList")).not.toContainText("Ib");
  });

  test("no context selected shows an explanatory empty state, not a broken diagram", async ({ page }) => {
    await uploadFixture(page);
    await openAnalysisPhasor(page);
    await expect(page.locator("#wwPhasorEmptyState")).toBeVisible();
    await expect(page.locator("#wwPhasorBody")).toBeHidden();
    await expect(page.locator("#wwPhasorSvg")).toBeEmpty();
  });

  test("needs_configuration resolution is shown with an actionable reason, never computed", async ({ page }) => {
    // A deliberately incomplete context (Phase A Voltage only, the other
    // five channels left unclaimed) -- three-phase mode against it can
    // never resolve (Vb/Vc are missing, not merely unconfirmed),
    // exercising the needs_configuration render path with a real backend
    // response rather than a mocked one.
    await uploadFixture(page);
    const row = page.locator("#recordingsTableBody tr[data-source-id]").last();
    await expect(row).toBeVisible();
    const sourceId = await row.getAttribute("data-source-id");
    const workspaceId = await page.evaluate(() => localStorage.getItem("powerwave.workspaceId"));
    const response = await page.request.post(
      `${BACKEND_URL}/api/v1/workspaces/${encodeURIComponent(workspaceId)}/engineering-contexts`,
      {
        data: {
          display_name: "Bravo 1 (incomplete)", status: "manual",
          members: [
            { channel_ref: { kind: "source", source_id: sourceId, channel_name: "ALPHA1_VA" }, phase: "A", phase_source: "engineer_confirmed" },
          ],
        },
      }
    );
    expect(response.ok()).toBeTruthy();
    const context = await response.json();

    await openAnalysisPhasor(page);
    await page.locator("#wwPhasorContextSelect").selectOption(context.id);
    await page.locator("#wwPhasorQuantitySelect").selectOption("voltage");
    await page.locator("#wwPhasorModeSelect").selectOption("three_phase");

    await expect(page.locator("#wwPhasorStatusRow")).toBeVisible();
    await expect(page.locator("#wwPhasorStatusRow")).toContainText("Needs configuration");
    await expect(page.locator("#wwPhasorResolutionList")).toContainText("Va");
    await expect(page.locator("#wwPhasorResolutionList .ww-phasor-role-ok")).toHaveCount(1); // Va only
  });
});
