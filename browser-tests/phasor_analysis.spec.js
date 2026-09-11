// Phasor Analysis -- bay-centric redesign (Phasor UAT redesign) real-
// browser coverage. See docs/development/BROWSER_SMOKE_TEST.md for the
// general foundation this extends, and backend/tests/test_frontend_
// phasor_analysis.py for the structural/static invariants that don't need
// a real browser (SVG rendering, fetch/render behavior against real
// backend responses, and stale-request protection genuinely do).
//
// Selecting an Engineering Context is now the ONLY primary control --
// there is no Quantity/Mode selector any more. Every supported role
// (Va/Vb/Vc/Ia/Ib/Ic) is resolved and estimated together via one
// aggregated request; a partial bay is a normal result. Individual vector
// VISIBILITY is a pure frontend display preference -- toggling it must
// never issue a new `/phasor-diagram` request.
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

// Uploads a SECOND source into the SAME (already open, same-session)
// workspace without a full page reload -- a channel can only belong to
// one Engineering Context at a time, so testing "switching Engineering
// Context resets visibility" needs a genuinely second source/bay, not a
// reused one. Navigates to Recordings via the SPA nav (never
// page.goto()) so the current JS session -- and whatever Phasor state
// this test is mid-way through exercising -- survives. Deliberately
// does NOT navigate back to Analysis itself -- the caller must create
// its own Engineering Context against the returned source id FIRST,
// then return to Analysis (wwRenderAnalysisPage() re-fetches the
// context list fresh every time that page is shown), or a context
// created after the Analysis page's own one-shot fetch would not
// appear in the selector.
async function uploadSecondSource(page) {
  await page.locator("#mainNavRecordingsBtn").click();
  await page.locator("#recordingsUploadBtn, #recordingsEmptyUploadBtn").first().click();
  await expect(page.locator("#uploadModalOverlay")).toBeVisible();
  await page.locator("#uploadModalFile_0").setInputFiles(path.join(FIXTURES, `${STEM}.cfg`));
  await page.locator("#uploadModalFile_1").setInputFiles(path.join(FIXTURES, `${STEM}.dat`));
  await page.locator("#uploadModalSubmitBtn").click();
  await page.locator("#uploadModalOverlay").waitFor({ state: "hidden" });
  return page.locator("#recordingsTableBody tr[data-source-id]").last().getAttribute("data-source-id");
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

async function openAnalysisPhasor(page) {
  await page.locator("#mainNavAnalysisBtn").click();
  await expect(page.locator("#pageAnalysis")).toBeVisible();
  await expect(page.locator("#wwAnalysisTypePhasorBtn")).toHaveClass(/active/);
  await expect(page.locator("#wwPhasorPanel")).toBeVisible();
}

test.describe("Phasor Analysis -- bay-centric redesign", () => {
  test("full bay: all six roles together, visibility toggles locally, persists across time change, resets on context switch", async ({ page }) => {
    const { workspaceId, sourceId, contextId } = await uploadAndCreateContext(page);

    // 1. Open Analysis -> Phasor.
    await openAnalysisPhasor(page);

    // No Quantity/Mode selector exists any more -- Bay is the only
    // primary control.
    await expect(page.locator("#wwPhasorQuantitySelect")).toHaveCount(0);
    await expect(page.locator("#wwPhasorModeSelect")).toHaveCount(0);

    // 2. Choose context.
    await expect(page.locator(`#wwPhasorContextSelect option[value="${contextId}"]`)).toHaveCount(1);
    await page.locator("#wwPhasorContextSelect").selectOption(contextId);

    // 3. All six roles resolved and shown together -- never a manual
    //    channel picker, never a Quantity/Mode-scoped subset.
    await expect(async () => {
      const text = await page.locator("#wwPhasorValuesList").innerText();
      expect(text.toLowerCase()).toContain("voltage");
      expect(text.toLowerCase()).toContain("current");
      for (const role of ["Va", "Vb", "Vc", "Ia", "Ib", "Ic"]) expect(text).toContain(role);
    }).toPass({ timeout: 5000 });
    const valuesText = await page.locator("#wwPhasorValuesList").innerText();
    expect(valuesText).toMatch(/100\.0\s*V/); // known balanced 100 V RMS
    expect(valuesText).toMatch(/40\.0\s*A/); // known balanced 40 A RMS

    // 4. A valid analysis time was chosen automatically.
    await expect(page.locator("#wwPhasorTimeRow")).toBeVisible();
    const initialTime = await page.locator("#wwPhasorTimeInput").inputValue();
    expect(Number(initialTime)).toBeGreaterThan(0);

    // 5. Six SVG vectors (one <line>+<polygon>+<text> triple per role).
    await expect(page.locator("#wwPhasorSvg polygon")).toHaveCount(6);
    await expect(page.locator("#wwPhasorSvg text.ww-phasor-vector-label")).toHaveCount(6);

    // 6. Both families present -> the graphical scaling ratio is shown,
    //    transparently, alongside the diagram.
    await expect(page.locator("#wwPhasorScaleNote")).toBeVisible();
    await expect(page.locator("#wwPhasorScaleNote")).toContainText("Current vectors scaled");

    // 7. Hide Vb -- toggled LOCALLY (no new /phasor-diagram request), its
    //    vector disappears, the other five remain.
    let diagramFetchCount = 0;
    page.on("request", (request) => { if (request.url().includes("/phasor-diagram")) diagramFetchCount += 1; });
    const vbRow = page.locator('.ww-phasor-value-row--toggle[data-role="Vb"]');
    await expect(vbRow).toHaveAttribute("aria-pressed", "true");
    await vbRow.click();
    await expect(vbRow).toHaveAttribute("aria-pressed", "false");
    await expect(page.locator("#wwPhasorSvg polygon")).toHaveCount(5);
    expect(diagramFetchCount).toBe(0);

    // 8. Show Vb again.
    await vbRow.click();
    await expect(vbRow).toHaveAttribute("aria-pressed", "true");
    await expect(page.locator("#wwPhasorSvg polygon")).toHaveCount(6);
    expect(diagramFetchCount).toBe(0);

    // 9. Hide all three Current roles -- Voltage remains fully visible.
    for (const role of ["Ia", "Ib", "Ic"]) {
      await page.locator(`.ww-phasor-value-row--toggle[data-role="${role}"]`).click();
    }
    await expect(page.locator("#wwPhasorSvg polygon")).toHaveCount(3);
    expect(diagramFetchCount).toBe(0);

    // 10. Change analysis time -- a real backend round-trip happens, but
    //     the Ia/Ib/Ic visibility preference set above SURVIVES it.
    await page.locator("#wwPhasorTimeInput").fill("1.5");
    await page.locator("#wwPhasorTimeInput").dispatchEvent("change");
    await expect(async () => {
      const text = await page.locator("#wwPhasorValuesList").innerText();
      expect(text).toMatch(/100\.0\s*V/);
    }).toPass({ timeout: 5000 });
    expect(diagramFetchCount).toBeGreaterThan(0);
    await expect(page.locator("#wwPhasorSvg polygon")).toHaveCount(3); // still only Voltage visible

    // 11/12. Switching to a genuinely different Engineering Context
    //        resets visibility -- all six available roles visible again.
    //        A channel can only belong to one Engineering Context at a
    //        time, so this uploads a SECOND source (a second bay's own
    //        recording) rather than reusing the first's channels.
    const secondSourceId = await uploadSecondSource(page);
    const secondContext = await createFullBayContext(page, workspaceId, secondSourceId, "Bravo 1");
    await page.locator("#mainNavAnalysisBtn").click();
    await expect(page.locator(`#wwPhasorContextSelect option[value="${secondContext.id}"]`)).toHaveCount(1);
    await page.locator("#wwPhasorContextSelect").selectOption(secondContext.id);
    await expect(async () => {
      await expect(page.locator("#wwPhasorSvg polygon")).toHaveCount(6);
    }).toPass({ timeout: 5000 });
  });

  test("no context selected shows an explanatory empty state, not a broken diagram", async ({ page }) => {
    await uploadFixture(page);
    await openAnalysisPhasor(page);
    await expect(page.locator("#wwPhasorEmptyState")).toBeVisible();
    await expect(page.locator("#wwPhasorBody")).toBeHidden();
    await expect(page.locator("#wwPhasorSvg")).toBeEmpty();
  });

  test("partial bay (Voltage Phase A only) renders Va and marks the other five roles Missing, never a whole-page failure", async ({ page }) => {
    // A deliberately incomplete context (Phase A Voltage only, the other
    // five channels left unclaimed) -- the bay-centric redesign treats
    // this as a NORMAL partial result, never a whole-result failure.
    await uploadFixture(page);
    const row = page.locator("#recordingsTableBody tr[data-source-id]").last();
    await expect(row).toBeVisible();
    const sourceId = await row.getAttribute("data-source-id");
    const workspaceId = await page.evaluate(() => localStorage.getItem("powerwave.workspaceId"));
    const response = await page.request.post(
      `${BACKEND_URL}/api/v1/workspaces/${encodeURIComponent(workspaceId)}/engineering-contexts`,
      {
        data: {
          display_name: "Bravo 1 (partial)", status: "manual",
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

    // No whole-result blocking banner -- a partial bay is a normal result.
    await expect(page.locator("#wwPhasorStatusRow")).toBeHidden();
    await expect(async () => {
      const text = await page.locator("#wwPhasorValuesList").innerText();
      expect(text).toMatch(/100\.0\s*V/); // Va computed
      expect(text).toContain("Missing"); // Vb/Vc/Ia/Ib/Ic
    }).toPass({ timeout: 5000 });
    await expect(page.locator("#wwPhasorSvg polygon")).toHaveCount(1); // only Va drawn
    // A role with nothing to show has no visibility toggle.
    await expect(page.locator('.ww-phasor-value-row--toggle[data-role="Vb"]')).toHaveCount(0);
  });
});

// UAT fix (2026-09-11): Phasor auto-bootstraps Engineering Context
// suggestions when a workspace has loaded sources but no contexts yet --
// see docs/project-memory/PHASOR_ANALYSIS.md's own "Automatic Engineering
// Context bootstrap" section. These scenarios exercise the REAL backend
// suggestion endpoint (POST .../sources/{id}/engineering-contexts/suggest)
// end-to-end -- the phasor_smoke_three_phase fixture's own channel names
// (ALPHA1_VA/VB/VC/IA/IB/IC) are genuinely detectable by the existing,
// unchanged Guardrail Slice 1 detector (verified directly against the
// real backend before writing these tests), so no mocking is needed.
test.describe("Phasor Analysis -- Engineering Context bootstrap (UAT fix)", () => {
  // ---- Scenario A: bootstrap succeeds ----
  test("no contexts + loaded source -> automatic suggestion populates the Bay selector", async ({ page }) => {
    // Delay the suggest POST slightly so the transient "Identifying
    // engineering contexts…" state is reliably observable in a real
    // browser (bootstrap otherwise completes fast enough locally that a
    // fixed-interval poll could miss it) -- a standard Playwright
    // technique, not a change to the app's own timing.
    await page.route("**/engineering-contexts/suggest", async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 400));
      await route.continue();
    });

    await uploadFixture(page); // no manual context creation this time
    await openAnalysisPhasor(page);

    // 4. Verify the temporary context-identification state appears.
    await expect(page.locator("#wwPhasorEmptyState")).toContainText("Identifying engineering contexts");

    // 5/6. The suggestion request succeeds and the Bay selector is
    // populated automatically, with the newly-suggested context
    // auto-selected (owner instruction: no unnecessary extra click).
    await expect(page.locator("#wwPhasorContextSelect option")).toHaveCount(2, { timeout: 10000 }); // blank + ALPHA1
    await expect(page.locator("#wwPhasorContextSelect")).not.toHaveValue("");
    await expect(page.locator("#wwPhasorContextBadge")).toContainText("Suggested");

    // 7. Normal aggregation proceeds -- every resolvable role computed.
    await expect(async () => {
      const text = await page.locator("#wwPhasorValuesList").innerText();
      expect(text).toMatch(/100\.0\s*V/);
      expect(text).toMatch(/40\.0\s*A/);
    }).toPass({ timeout: 5000 });
  });

  // ---- Scenario B: existing context ----
  test("existing context -> selector populated immediately, no suggestion request made", async ({ page }) => {
    let suggestRequested = false;
    page.on("request", (request) => {
      if (request.url().includes("/engineering-contexts/suggest")) suggestRequested = true;
    });

    await uploadAndCreateContext(page);
    await openAnalysisPhasor(page);

    // Selector populated immediately from the existing context -- no
    // bootstrap ran, so (matching this fix's own explicit "preserve
    // already-working behavior" requirement) nothing is auto-selected;
    // the ordinary "pick a context" empty state is shown, exactly as it
    // already was before this fix.
    await expect(page.locator("#wwPhasorContextSelect option")).toHaveCount(2); // blank + Alpha 1
    await expect(page.locator("#wwPhasorEmptyState")).toBeVisible();
    await expect(page.locator("#wwPhasorEmptyState")).toHaveText("Select an Engineering Context to begin.");
    expect(suggestRequested).toBe(false);
  });

  // ---- Scenario C: no source ----
  test("empty workspace -> no-data message, never implies detection failed", async ({ page }) => {
    await page.goto("/index.html");
    await openAnalysisPhasor(page);

    await expect(page.locator("#wwPhasorEmptyState")).toContainText("No event sources are available");
    await expect(page.locator("#wwPhasorEmptyState")).not.toContainText("Engineering Context");
    await expect(page.locator("#wwPhasorBody")).toBeHidden();
  });
});
