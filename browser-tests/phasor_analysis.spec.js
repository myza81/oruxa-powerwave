// Phasor Analysis -- bay-centric redesign + Playback integration real-
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
// Phasor Playback integration: Phasor mounts the SAME reusable Playback
// control surface (`wwCreatePlaybackControlsHtml()`/
// `wwWirePlaybackControls()`/`wwSyncPlaybackControls()`) -- there is no
// separate "Analysis Time" input any more, the mounted seek scrubber
// (`.ww-tg-playback-seek-slider`) IS Phasor's own analysis time control.
// Owner product decision (2026-09-12): Playback controls are Analysis-
// only now -- the Waveform Time Group toolbar no longer mounts this
// surface at all (see DECISIONS.md DEC-085's own "Update (2026-09-12)"
// section and playback.spec.js's own header comment); Phasor's own mount
// is the sole control surface, while the Waveform Time Group canvas still
// shows the PASSIVE Playback Cursor overlay (`.ww-tg-playback-cursor-
// overlay`) reflecting the shared clock. These tests reuse the EXACT
// `seekTo()`/`seekSliderBounds()` interaction helpers `playback.spec.js`
// already established for that same scrubber class, and assert against
// the ONE shared `wwPlayback` controller (`wwPlaybackState()`) -- never a
// second, Phasor-specific clock.
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
const {
  BACKEND_URL,
  reuseOrCreateFullBayContext,
  clearContexts,
  postContext,
  ensureContextSelected,
} = require("./support/engineering_context_helpers");

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

// Returns the full six-role Engineering Context for `sourceId` -- DEC-104
// (2026-09-23) upload-time preparation normally already auto-created it
// (a `suggested` context, display name "ALPHA1") before this ever runs, so
// this discovers and reuses that one rather than POSTing a duplicate
// (which now 409s -- see DECISIONS.md DEC-111 and
// support/engineering_context_helpers.js's own header comment). Falls
// back to a manual POST only if discovery genuinely finds nothing.
// Returns { workspaceId, sourceId, contextId } is NOT this function's own
// shape -- see uploadAndCreateContext() below for that; this returns the
// raw context object.
async function createFullBayContext(page, workspaceId, sourceId, displayName) {
  return reuseOrCreateFullBayContext(page, workspaceId, sourceId, "ALPHA1", ALPHA_ROLES, displayName);
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

// DEC-105 already auto-selects the first (or only) context the instant
// Analysis opens whenever this workspace's very first context fetch is
// non-empty -- normally true here, since uploadAndCreateContext() reuses
// what DEC-104's own upload-time preparation already created. A test's
// OWN redundant `.selectOption(contextId)` on that SAME, already-selected
// value can race the auto-select's own in-flight claim/refine sequence
// (see support/engineering_context_helpers.js's own header comment on
// ensureContextSelected()) -- this only selects for real when needed.
async function selectPhasorContext(page, contextId) {
  await ensureContextSelected(page, page.locator("#wwPhasorContextSelect"), contextId);
  // The initial claim of a Time Group genuinely issues two real fetches
  // in sequence (t=0, honestly "insufficient window history", then the
  // refined safe start time -- see wwPhasorComputeInitialClaimTime()).
  // Callers that immediately act on the panel afterward (switch Input
  // Source, seek, read values) must never race that still-in-flight
  // Recording fetch -- `wwPhasorSetInputSource()`'s own Manual switch, in
  // particular, does not invalidate/abort an in-flight Recording fetch,
  // so a late response can overwrite a just-entered Manual result. Every
  // caller here always uses a fully-resolvable full/near-full bay, so
  // waiting for a REAL resolved value (never merely the absence of
  // "Needs configuration" -- that text may simply not have painted yet
  // on an earlier, equally transient empty/loading state, which would
  // let this settle-check pass too early) is the correct settled state.
  await expect(async () => {
    const text = await page.locator("#wwPhasorValuesList").innerText();
    expect(text).toMatch(/\d+\.\d\s*(V|A)\b/);
  }).toPass({ timeout: 10000 });
}

async function openAnalysisPhasor(page) {
  await page.locator("#mainNavAnalysisBtn").click();
  await expect(page.locator("#pageAnalysis")).toBeVisible();
  await expect(page.locator("#wwAnalysisTypePhasorBtn")).toHaveClass(/active/);
  await expect(page.locator("#wwPhasorPanel")).toBeVisible();
}

// Reused verbatim from browser-tests/playback.spec.js's own established
// interaction pattern for the SAME `.ww-tg-playback-seek-slider` class --
// Phasor mounts the identical markup, so the identical technique applies.
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
    await selectPhasorContext(page, contextId);

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

    // 4. Playback integration: the mounted Playback control surface (NOT
    //    a separate Analysis Time field -- that control no longer
    //    exists) is populated, and this bay's own resolved Time Group was
    //    automatically claimed at a valid time (bounds.start, per
    //    wwPlaybackRestart()'s own existing semantics).
    await expect(page.locator("#wwPhasorPlaybackPanel")).toBeVisible();
    const seekSlider = page.locator("#wwPhasorPlaybackMount .ww-tg-playback-seek-slider");
    await expect(seekSlider).toBeVisible();
    const initialTime = Number(await seekSlider.inputValue());
    expect(Number.isFinite(initialTime)).toBe(true);

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

    // 10. Change analysis time via the Playback seek scrubber -- the ONE
    //     time control now -- a real backend round-trip happens, but the
    //     Ia/Ib/Ic visibility preference set above SURVIVES it.
    await seekTo(seekSlider, 1.5);
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

  test("scale legend replaces the old Imaginary-axis-adjacent numbers (owner UAT clarification, 2026-09-16)", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisPhasor(page);
    await selectPhasorContext(page, contextId);
    await expect(async () => {
      const text = await page.locator("#wwPhasorValuesList").innerText();
      expect(text).toMatch(/100\.0\s*V/);
    }).toPass({ timeout: 5000 });

    // The old bare numeric ring labels are gone.
    await expect(page.locator("#wwPhasorSvg text.ww-phasor-ring-label")).toHaveCount(0);

    // The new legend exists, with a header and one line per present
    // family, each carrying its own value AND real engineering unit --
    // never a bare unlabeled number.
    const legend = page.locator("#wwPhasorSvg text.ww-phasor-scale-legend");
    await expect(legend).toHaveCount(3); // "Scale" header + V line + I line
    await expect(page.locator("#wwPhasorSvg text.ww-phasor-scale-legend--header", { hasText: "Scale" })).toHaveCount(1);
    const legendTexts = await legend.allTextContents();
    const voltageLine = legendTexts.find((t) => t.startsWith("V:"));
    const currentLine = legendTexts.find((t) => t.startsWith("I:"));
    expect(voltageLine).toBeTruthy();
    expect(currentLine).toBeTruthy();
    // Each line shows the inner/middle/outer ring breakdown (three
    // numbers, one per ring) and carries a real unit (not a bare number)
    // -- the fixture's known channels are V/A.
    expect(voltageLine).toMatch(/^V:\s*[\d.]+\s*\/\s*[\d.]+\s*\/\s*[\d.]+\s*V$/);
    expect(currentLine).toMatch(/^I:\s*[\d.]+\s*\/\s*[\d.]+\s*\/\s*[\d.]+\s*A$/);

    // Legend sits in the quiet top-right corner, well clear of both
    // axis-direction labels (never placed directly on an axis).
    const legendBox = await legend.first().boundingBox();
    const realLabelBox = await page.locator("#wwPhasorSvg text.ww-phasor-axis-title", { hasText: "Real" }).boundingBox();
    const imaginaryLabelBox = await page.locator("#wwPhasorSvg text.ww-phasor-axis-title", { hasText: "Imaginary" }).boundingBox();
    // Legend is above the Real label (smaller y = higher on screen).
    expect(legendBox.y).toBeLessThan(realLabelBox.y);
    // Legend is to the right of the Imaginary label's own horizontal position.
    expect(legendBox.x).toBeGreaterThan(imaginaryLabelBox.x);

    // Real/Imaginary axis labels remain, unaffected.
    await expect(page.locator("#wwPhasorSvg text.ww-phasor-axis-title", { hasText: "Real" })).toHaveCount(1);
    await expect(page.locator("#wwPhasorSvg text.ww-phasor-axis-title", { hasText: "Imaginary" })).toHaveCount(1);

    // Vector rendering is unaffected -- still one polygon/label per role.
    await expect(page.locator("#wwPhasorSvg polygon")).toHaveCount(6);
    await expect(page.locator("#wwPhasorSvg text.ww-phasor-vector-label")).toHaveCount(6);

    // Bottom note still conveys the scale ratio and the engineering-
    // values-unaffected reassurance.
    await expect(page.locator("#wwPhasorScaleNote")).toContainText("Current vectors scaled");
    await expect(page.locator("#wwPhasorScaleNote")).toContainText("engineering values are unaffected");
  });

  test("chart UX refinement: grid lines and Real/Imaginary axis labels render alongside the existing rings/vectors", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisPhasor(page);
    await selectPhasorContext(page, contextId);
    await expect(async () => {
      const text = await page.locator("#wwPhasorValuesList").innerText();
      expect(text).toMatch(/100\.0\s*V/);
    }).toPass({ timeout: 5000 });

    // NEW: rectilinear grid + axis-direction labels.
    await expect(page.locator("#wwPhasorSvg line.ww-phasor-grid-line")).toHaveCount(12); // 3 radii x 4 lines each
    await expect(page.locator("#wwPhasorSvg text.ww-phasor-axis-title")).toHaveCount(2);
    await expect(page.locator("#wwPhasorSvg text.ww-phasor-axis-title", { hasText: "Real" })).toHaveCount(1);
    await expect(page.locator("#wwPhasorSvg text.ww-phasor-axis-title", { hasText: "Imaginary" })).toHaveCount(1);

    // EXISTING elements untouched: circular rings, vectors, current
    // (dashed) vs voltage (solid) styling, visibility toggle behavior.
    await expect(page.locator("#wwPhasorSvg circle.ww-phasor-ring")).toHaveCount(3);
    await expect(page.locator("#wwPhasorSvg polygon")).toHaveCount(6); // one arrowhead per available role
    await expect(page.locator("#wwPhasorSvg line.ww-phasor-vector--current")).toHaveCount(3); // Ia/Ib/Ic dashed

    const vaRow = page.locator('.ww-phasor-value-row--toggle[data-role="Va"]');
    await vaRow.click();
    await expect(page.locator("#wwPhasorSvg polygon")).toHaveCount(5); // visibility toggle still works
  });

  test("no context selected shows an explanatory empty state, not a broken diagram", async ({ page }) => {
    // DEC-105 (2026-09-23): the first time this workspace session ever
    // has a usable (non-empty) context list -- true here the instant
    // Analysis opens, since uploadAndCreateContext() reuses the context
    // DEC-104's own upload-time preparation already created -- Phasor now
    // auto-selects it immediately (see support/engineering_context_
    // helpers.js's own header comment). "No context selected" is
    // therefore no longer reachable merely by opening Phasor with an
    // existing context; this explicitly deselects (the blank option) to
    // reach the state this test actually wants to verify -- the SAME
    // empty-state rendering an engineer would see after clearing their
    // own selection.
    await uploadAndCreateContext(page);
    await openAnalysisPhasor(page);
    await expect(page.locator("#wwPhasorContextSelect")).not.toHaveValue("");
    await page.locator("#wwPhasorContextSelect").selectOption("");
    await expect(page.locator("#wwPhasorEmptyState")).toBeVisible();
    await expect(page.locator("#wwPhasorEmptyState")).toHaveText("Select an Engineering Context to begin.");
    // `#wwPhasorBody` (Inputs/Values, Diagram) is no longer hidden here --
    // architectural correction, see docs/project-memory/ANALYSIS_INPUT_SOURCE.md:
    // it is ALWAYS visible once the Phasor tab is open, independent of
    // recording/context state (Recording remains the active input source
    // in this scenario -- a context DOES exist -- but none is selected
    // yet, so there is simply nothing to plot).
    await expect(page.locator("#wwPhasorBody")).toBeVisible();
    await expect(page.locator("#wwPhasorPlaybackPanel")).toBeHidden();
    await expect(page.locator("#wwPhasorSvg")).toBeEmpty();
  });

  test("analyzer menu shows requested entries and placeholder entries are safe", async ({ page }) => {
    await page.goto("/index.html");
    await openAnalysisPhasor(page);

    // Scoped by aria-label, not the bare class -- Compliance & Capability
    // Slice 1 reuses the exact same `.ww-analysis-type-nav` class for its
    // own (unrelated) function sub-nav, so the bare class now resolves to
    // two elements on the page.
    const menu = page.locator(".ww-analysis-type-nav[aria-label='Analysis type']");
    await expect(menu).toContainText("Analyzers");
    await expect(menu.locator(".ww-analysis-type-item")).toHaveText([
      "Overcurrent",
      "Impedance Locus",
      "Distance Protection",
      "Phasor",
      "Sequence Components",
    ]);
    await expect(menu).not.toContainText("Differential");

    // Every analyzer is now REAL -- Impedance Locus v1 (implemented
    // 2026-09-17), Sequence Components v1 (implemented 2026-09-18), and
    // Distance Protection v1 (implemented 2026-09-18) activated the last
    // three placeholders; see docs/project-memory/
    // IMPEDANCE_LOCUS_ANALYSIS.md, SEQUENCE_COMPONENTS_ANALYSIS.md, and
    // DISTANCE_PROTECTION_ANALYSIS.md.
    await page.locator("#wwAnalysisTypeImpedanceBtn").click();
    await expect(page.locator("#wwAnalysisTypeImpedanceBtn")).toHaveClass(/active/);
    await expect(page.locator("#wwImpedancePanel")).toBeVisible();
    await expect(page.locator("#wwImpedancePanel")).not.toContainText("not implemented yet");
    await expect(page.locator("#wwImpedanceInputSourceRecordingBtn")).toBeVisible();

    await page.locator("#wwAnalysisTypeSequenceBtn").click();
    await expect(page.locator("#wwAnalysisTypeSequenceBtn")).toHaveClass(/active/);
    await expect(page.locator("#wwSequencePanel")).toBeVisible();
    await expect(page.locator("#wwSequencePanel")).not.toContainText("not implemented yet");
    await expect(page.locator("#wwSequenceInputSourceRecordingBtn")).toBeVisible();

    await page.locator("#wwAnalysisTypeDistanceBtn").click();
    await expect(page.locator("#wwAnalysisTypeDistanceBtn")).toHaveClass(/active/);
    await expect(page.locator("#wwDistancePanel")).toBeVisible();
    await expect(page.locator("#wwDistancePanel")).not.toContainText("not implemented yet");
    await expect(page.locator("#wwDistanceInputSourceRecordingBtn")).toBeVisible();

    await page.locator("#wwAnalysisTypeOvercurrentBtn").click();
    await expect(page.locator("#wwAnalysisTypeOvercurrentBtn")).toHaveClass(/active/);
    await expect(page.locator("#wwOvercurrentPanel")).toBeVisible();
  });

  test("partial bay (Voltage Phase A only) renders Va and marks the other five roles Missing, never a whole-page failure", async ({ page }) => {
    // A deliberately incomplete context (Phase A Voltage only, the other
    // five channels left unclaimed) -- the bay-centric redesign treats
    // this as a NORMAL partial result, never a whole-result failure.
    // DEC-104 upload-time preparation auto-creates a FULL six-role
    // context for this source first (see support/engineering_context_
    // helpers.js) -- this test genuinely needs a context shape DEC-104's
    // own discovery never produces (a partial bay), so it clears that
    // auto-created context before manually constructing its own, exactly
    // the "a test deleted it after upload" fallback scenario DEC-104's
    // own design already anticipates.
    await uploadFixture(page);
    const row = page.locator("#recordingsTableBody tr[data-source-id]").last();
    await expect(row).toBeVisible();
    const sourceId = await row.getAttribute("data-source-id");
    const workspaceId = await page.evaluate(() => localStorage.getItem("powerwave.workspaceId"));
    await clearContexts(page, workspaceId, sourceId);
    const context = await postContext(page, workspaceId, {
      display_name: "Bravo 1 (partial)", status: "manual",
      members: [
        { channel_ref: { kind: "source", source_id: sourceId, channel_name: "ALPHA1_VA" }, phase: "A", phase_source: "engineer_confirmed" },
      ],
    });

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

// Phasor Playback integration: Phasor consumes the ONE shared, reusable
// `wwPlayback` controller (see browser-tests/playback.spec.js for that
// controller's own foundational coverage) -- never a second clock/timer.
// These scenarios exercise the mounted Playback control surface end to
// end against the real aggregated `/phasor-diagram` endpoint.
test.describe("Phasor Analysis -- Playback integration", () => {
  test("Play advances shared time, produces repeated aggregated results, and never mutates the Engineering Context", async ({ page }) => {
    const { workspaceId, contextId } = await uploadAndCreateContext(page);
    await openAnalysisPhasor(page);
    await selectPhasorContext(page, contextId);
    await expect(page.locator("#wwPhasorSvg polygon")).toHaveCount(6);

    // Hide Ib/Ic before playing -- visibility must survive playback.
    await page.locator('.ww-phasor-value-row--toggle[data-role="Ib"]').click();
    await page.locator('.ww-phasor-value-row--toggle[data-role="Ic"]').click();
    await expect(page.locator("#wwPhasorSvg polygon")).toHaveCount(4);

    let diagramFetchCount = 0;
    page.on("request", (request) => { if (request.url().includes("/phasor-diagram")) diagramFetchCount += 1; });

    const playBtn = page.locator("#wwPhasorPlaybackMount .ww-tg-playback-play-btn");
    await playBtn.click();
    await expect(playBtn).toHaveText("Pause");

    // DEC-099 (2026-09-19) already diagnosed and fixed this EXACT flake
    // shape elsewhere in this repo (playback.spec.js's own 4x-speed
    // suite): a tight fixed-duration request-counting window occasionally
    // lets the first throttled fetch land just outside it under real
    // backend contention -- not a production race (the throttle is a
    // steady ~100ms/~10Hz, see WW_PHASOR_PLAYBACK_THROTTLE_MS). Retries
    // instead of a single fixed wait, so a slow-starting first response
    // under load gets more than one throttle interval to accumulate a
    // second request.
    // Repeated aggregated results -- more than the one static fetch this
    // page already made before Play.
    await expect(async () => {
      expect(diagramFetchCount).toBeGreaterThan(1);
    }).toPass({ timeout: 5000 });
    // Hidden roles remain hidden throughout playback; the other four
    // (Va/Vb/Vc/Ia) keep updating.
    await expect(page.locator("#wwPhasorSvg polygon")).toHaveCount(4);
    await expect(page.locator('.ww-phasor-value-row--toggle[data-role="Ib"]')).toHaveAttribute("aria-pressed", "false");
    await expect(page.locator('.ww-phasor-value-row--toggle[data-role="Ic"]')).toHaveAttribute("aria-pressed", "false");

    // Visibility is a pure frontend display preference -- confirm the
    // Engineering Context's own membership was never touched by any of
    // this.
    const contextResponse = await page.request.get(
      `${BACKEND_URL}/api/v1/workspaces/${encodeURIComponent(workspaceId)}/engineering-contexts/${encodeURIComponent(contextId)}`
    );
    expect(contextResponse.ok()).toBeTruthy();
    const contextBody = await contextResponse.json();
    expect(contextBody.members).toHaveLength(6);
  });

  test("Pause converges to the exact settled time and stops issuing requests", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisPhasor(page);
    await selectPhasorContext(page, contextId);
    await expect(page.locator("#wwPhasorSvg polygon")).toHaveCount(6);

    const requestedTimes = [];
    page.on("request", (request) => {
      const url = request.url();
      if (!url.includes("/phasor-diagram")) return;
      const match = url.match(/analysis_time=([-0-9.eE]+)/);
      if (match) requestedTimes.push(Number(match[1]));
    });

    const playBtn = page.locator("#wwPhasorPlaybackMount .ww-tg-playback-play-btn");
    await playBtn.click();
    await page.waitForTimeout(500);
    await playBtn.click(); // Pause
    await expect(playBtn).toHaveText("Play");

    const pausedTime = await page.evaluate(() => wwPlaybackState().currentTime);

    // The queue drains and settles -- no further requests once the exact
    // convergence fetch (if any) completes.
    await expect(async () => {
      const countAtCheck = requestedTimes.length;
      await page.waitForTimeout(250);
      expect(requestedTimes.length).toBe(countAtCheck);
    }).toPass({ timeout: 5000 });

    // Displayed playback time equals the LAST accepted Phasor request's
    // own analysis_time (single-source workspace -- zero alignment
    // offset, so workspace time and the API's own source-relative
    // analysis_time are numerically identical here). Retries the whole
    // convergence read, not just a single snapshot: under real backend
    // contention (this describe block's own full-suite run puts real
    // load on the one shared backend process) the exact convergence
    // fetch `wwPhasorMaybeFetchForPlayback()`'s own trailing re-check
    // schedules after Pause can itself still be in flight when the
    // 250ms-quiet window above happened to sample, in which case a
    // further convergence request arrives shortly after and must still
    // be picked up here rather than judged against the stale one before it.
    await expect(async () => {
      expect(requestedTimes.length).toBeGreaterThan(0);
      const lastRequestedTime = requestedTimes[requestedTimes.length - 1];
      expect(Math.abs(lastRequestedTime - pausedTime)).toBeLessThan(0.01);
    }).toPass({ timeout: 5000 });
  });

  test("Seek while paused converges exactly to the released position", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisPhasor(page);
    await selectPhasorContext(page, contextId);
    await expect(page.locator("#wwPhasorSvg polygon")).toHaveCount(6);

    const seekSlider = page.locator("#wwPhasorPlaybackMount .ww-tg-playback-seek-slider");
    const { min, max } = await seekSliderBounds(seekSlider);
    const target = min + (max - min) * 0.75;

    let lastRequestedTime = null;
    page.on("request", (request) => {
      const url = request.url();
      if (!url.includes("/phasor-diagram")) return;
      const match = url.match(/analysis_time=([-0-9.eE]+)/);
      if (match) lastRequestedTime = Number(match[1]);
    });

    await seekTo(seekSlider, target);
    await expect(async () => {
      expect(lastRequestedTime).not.toBeNull();
      expect(Math.abs(lastRequestedTime - target)).toBeLessThan(0.01);
    }).toPass({ timeout: 5000 });

    const state = await page.evaluate(() => wwPlaybackState().state);
    expect(state).toBe("paused"); // was not playing before the seek -- lands paused, not stopped
  });

  test("Speed selection (4x) keeps Phasor's own request rate throttled, never one request per tick", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisPhasor(page);
    await selectPhasorContext(page, contextId);
    await expect(page.locator("#wwPhasorSvg polygon")).toHaveCount(6);

    await page.locator("#wwPhasorPlaybackMount .ww-tg-playback-speed-select").selectOption("4");

    let diagramFetchCount = 0;
    page.on("request", (request) => { if (request.url().includes("/phasor-diagram")) diagramFetchCount += 1; });

    await page.locator("#wwPhasorPlaybackMount .ww-tg-playback-play-btn").click();

    // DEC-099 flake fix (test-synchronization bug, confirmed by direct
    // reproduction -- not assumed): the throttle
    // (WW_PHASOR_PLAYBACK_THROTTLE_MS, ~100ms) plus ordinary rAF/backend
    // scheduling jitter means the FIRST throttled fetch can legitimately
    // land just outside a short, FIXED real-time window under unlucky
    // timing -- reproduced directly (1 failure in 30 isolated runs,
    // `diagramFetchCount === 0` after a flat 600ms wait, no combined-
    // suite load needed). Not a production defect: the throttle is
    // wall-clock-paced and correct by design, structurally independent
    // of `speed` (a higher speed moves more RECORDING time per real
    // second, never more REQUESTS per real second -- see
    // WW_PHASOR_PLAYBACK_THROTTLE_MS's own comment). Waiting
    // AUTHORITATIVELY for the first fetch removes that race; the
    // request-RATE claim itself (never one-per-frame) is still proven
    // with a real, bounded time window afterward -- exactly what a
    // fixed interval is legitimately for (a rate measurement, not a
    // readiness signal).
    await expect(async () => {
      expect(diagramFetchCount).toBeGreaterThan(0);
    }).toPass({ timeout: 5000 });

    // At 4x over a further ~600ms of real time (with the throttle at
    // ~100ms), the request count must stay bounded -- nowhere near one
    // per rAF frame (which would be dozens at 60 fps).
    await page.waitForTimeout(600);
    expect(diagramFetchCount).toBeLessThan(15);
  });

  test("Restart lands at the Time Group's own start; insufficient history is reported honestly, never dodged", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisPhasor(page);
    await selectPhasorContext(page, contextId);
    await expect(page.locator("#wwPhasorSvg polygon")).toHaveCount(6);

    const seekSlider = page.locator("#wwPhasorPlaybackMount .ww-tg-playback-seek-slider");
    const { min } = await seekSliderBounds(seekSlider);

    // Move away from the start first.
    await seekTo(seekSlider, 1.5);
    await expect(async () => {
      const text = await page.locator("#wwPhasorValuesList").innerText();
      expect(text).toMatch(/100\.0\s*V/);
    }).toPass({ timeout: 5000 });

    await page.locator("#wwPhasorPlaybackMount .ww-tg-playback-restart-btn").click();
    await expect(page.locator("#wwPhasorPlaybackMount .ww-tg-playback-play-btn")).toHaveText("Play");
    await expect(async () => {
      expect(Number(await seekSlider.inputValue())).toBeCloseTo(min, 3);
    }).toPass({ timeout: 5000 });

    // At exactly the Time Group's own start, a full one-cycle trailing
    // window cannot exist yet -- Phasor reports this honestly rather than
    // Playback silently shifting its own start forward to dodge it.
    await expect(async () => {
      const text = await page.locator("#wwPhasorValuesList").innerText();
      expect(text).toContain("Needs configuration");
    }).toPass({ timeout: 5000 });
  });

  test("Switching Engineering Context while playing stops the old group and resolves the new one statically", async ({ page }) => {
    const { workspaceId, contextId } = await uploadAndCreateContext(page);
    await openAnalysisPhasor(page);
    await selectPhasorContext(page, contextId);
    await expect(page.locator("#wwPhasorSvg polygon")).toHaveCount(6);

    await page.locator("#wwPhasorPlaybackMount .ww-tg-playback-play-btn").click();
    await page.waitForTimeout(300);
    expect(await page.evaluate(() => wwPlaybackState().state)).toBe("playing");

    const secondSourceId = await uploadSecondSource(page);
    const secondContext = await createFullBayContext(page, workspaceId, secondSourceId, "Bravo 1");
    await page.locator("#mainNavAnalysisBtn").click();
    await expect(page.locator(`#wwPhasorContextSelect option[value="${secondContext.id}"]`)).toHaveCount(1);
    await page.locator("#wwPhasorContextSelect").selectOption(secondContext.id);

    // The old group's own playback does not continue through an
    // unresolved transition -- the shared controller now belongs to the
    // NEW context's own group, landed statically (never auto-playing
    // through the switch).
    await expect(async () => {
      const state = await page.evaluate(() => wwPlaybackState());
      expect(state.state).not.toBe("playing");
    }).toPass({ timeout: 5000 });
    await expect(async () => {
      await expect(page.locator("#wwPhasorSvg polygon")).toHaveCount(6);
    }).toPass({ timeout: 5000 });
  });

  test("Waveform and Phasor share one Playback clock across page navigation", async ({ page }) => {
    // Owner product decision (2026-09-12): Playback controls are
    // Analysis-only now -- Waveform has no seek slider of its own any
    // more, only the PASSIVE Playback Cursor overlay reflecting the
    // shared clock. This test now drives both seeks from Phasor's own
    // mount and confirms: (a) wwPlaybackState().currentTime -- the one
    // authoritative shared coordinate both pages read -- carries across
    // a page navigation untouched, and (b) the Waveform canvas's own
    // passive cursor overlay actually renders at the shared time once
    // that page is the visible one.
    const { sourceId, contextId } = await uploadAndCreateContext(page);

    // Display a channel on Waveform so a real Time Group canvas exists
    // (uploadAndCreateContext() creates the Engineering Context directly
    // via the backend API, but never displays anything itself) -- this is
    // what the passive cursor overlay assertion below needs to render
    // into, independent of which page actually drives the seek.
    await page.locator(`#recordingsTableBody tr[data-source-id="${sourceId}"]`).click();
    await expect(page.locator("#wwWorkspaceLoading")).toBeHidden();
    const channelRow = page.locator('#channelGroups tr.channel-row--toggle[data-channel-kind="analog"]').first();
    await expect(channelRow).toBeVisible();
    await channelRow.click();
    await expect(channelRow).toHaveAttribute("aria-pressed", "true");

    await openAnalysisPhasor(page);
    await selectPhasorContext(page, contextId);
    const phasorSlider = page.locator("#wwPhasorPlaybackMount .ww-tg-playback-seek-slider");
    await expect(phasorSlider).toBeVisible();
    await seekTo(phasorSlider, 1.25);
    await expect(async () => {
      const currentTime = await page.evaluate(() => wwPlaybackState().currentTime);
      expect(Math.abs(currentTime - 1.25)).toBeLessThan(0.01);
    }).toPass({ timeout: 5000 });

    // Navigate to Waveform -- the shared clock must carry across
    // unchanged, and the passive cursor overlay must now actually render
    // (it only draws while the Waveform page itself is the visible one).
    await page.locator("#mainNavWaveformBtn").click();
    const canvas = page.locator("#wwTimeGroupCanvases .ww-time-group-canvas").first();
    await expect(canvas).toBeVisible();
    expect(await page.evaluate(() => wwPlaybackState().currentTime)).toBeCloseTo(1.25, 1);
    await expect(canvas.locator(".ww-tg-playback-cursor-overlay")).toBeVisible();

    // Back to Phasor, seek further -- confirm the shared time again
    // carries back to Waveform correctly (both directions, not just one).
    await page.locator("#mainNavAnalysisBtn").click();
    await expect(page.locator(`#wwPhasorContextSelect`)).toHaveValue(contextId);
    await seekTo(phasorSlider, 1.8);
    await expect(async () => {
      const currentTime = await page.evaluate(() => wwPlaybackState().currentTime);
      expect(Math.abs(currentTime - 1.8)).toBeLessThan(0.01);
    }).toPass({ timeout: 5000 });

    await page.locator("#mainNavWaveformBtn").click();
    expect(await page.evaluate(() => wwPlaybackState().currentTime)).toBeCloseTo(1.8, 1);
  });
});

// UAT fix (2026-09-11): Phasor auto-bootstraps Engineering Context
// suggestions when a workspace has loaded sources but no contexts yet --
// see docs/project-memory/PHASOR_ANALYSIS.md's own "Automatic Engineering
// Context bootstrap" section. These scenarios exercise the REAL backend
// suggestion endpoint (POST .../sources/{id}/engineering-contexts/suggest)
// end-to-end -- the phasor_smoke_three_phase fixture's own channel names
// (ALPHA1_VA/VB/VC/IA/IB/IC) are genuinely detectable by the real
// Guardrail Slice 1 detector, so no mocking is needed.
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
    // DEC-104 (2026-09-23) upload-time preparation already auto-created
    // ALPHA1's own context synchronously during the upload above -- this
    // test's own purpose is exercising the FALLBACK bootstrap path for
    // "no contexts yet" (still a real, defended scenario -- see DEC-104's
    // own "a group/context the user, or a test, deleted after upload"
    // case), so it clears that auto-created context first to genuinely
    // reach that state, rather than the no-longer-reachable "upload alone
    // never creates a context" precondition this test originally relied on.
    const sourceIdForClear = await page.locator("#recordingsTableBody tr[data-source-id]").last().getAttribute("data-source-id");
    const workspaceIdForClear = await page.evaluate(() => localStorage.getItem("powerwave.workspaceId"));
    await clearContexts(page, workspaceIdForClear, sourceIdForClear);
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

  // ---- Multi-upload bootstrap fix: source-coverage-driven discovery ----
  test("a later-uploaded, uncovered source is discovered automatically without disturbing the already-usable bay", async ({ page }) => {
    // 1. Upload event A -> auto-bootstrap suggests ALPHA1 (unchanged
    //    fresh-bootstrap path).
    await uploadFixture(page);
    await openAnalysisPhasor(page);
    await expect(page.locator("#wwPhasorContextSelect option")).toHaveCount(2, { timeout: 10000 }); // blank + ALPHA1
    await expect(page.locator("#wwPhasorContextSelect")).not.toHaveValue("");
    const alphaContextId = await page.locator("#wwPhasorContextSelect").inputValue();
    // A generous timeout, not 5000ms: the very first auto-claim of a Time
    // Group genuinely issues two real fetches in sequence (t=0, honestly
    // "insufficient window history", then the refined safe start time --
    // see wwPhasorComputeInitialClaimTime()) and this describe block's
    // own full-suite run puts real load on the one shared backend
    // process, occasionally slowing the second fetch past a tight window.
    await expect(async () => {
      const text = await page.locator("#wwPhasorValuesList").innerText();
      expect(text).toMatch(/100\.0\s*V/);
    }).toPass({ timeout: 10000 });

    // 2. Upload event B (a second, ROOTED source, BRAVO1_*) WITHOUT
    //    clearing the workspace -- via the SPA nav, never page.goto(),
    //    so the current session (and ALPHA1's own selection) survives.
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
    // DEC-104 upload-time preparation already auto-covered BRAVO1 too, so
    // it is no longer genuinely "uncovered" at this point -- clear it to
    // reach the state this test's own name describes and exercise the
    // fallback discovery bootstrap it targets (same rationale as the
    // "no contexts + loaded source" scenario above).
    const workspaceIdForClear = await page.evaluate(() => localStorage.getItem("powerwave.workspaceId"));
    await clearContexts(page, workspaceIdForClear, bravoSourceId);

    // 3. Re-enter Phasor -- ALPHA1 remains selected and usable
    //    IMMEDIATELY (never blanked/reset), while BRAVO1 (uncovered) is
    //    discovered in the background.
    await page.locator("#mainNavAnalysisBtn").click();
    await expect(page.locator("#wwPhasorContextSelect")).toHaveValue(alphaContextId);
    const valuesTextRightAfterReentry = await page.locator("#wwPhasorValuesList").innerText();
    expect(valuesTextRightAfterReentry).toMatch(/100\.0\s*V/); // ALPHA1's own values, uninterrupted

    // 4. BRAVO1 appears in the selector once discovery completes.
    await expect(page.locator("#wwPhasorContextSelect option")).toHaveCount(3, { timeout: 10000 }); // blank + ALPHA1 + BRAVO1
    // ALPHA1 is still the selected value -- adding BRAVO1 never jumps
    // the engineer away from their own already-open bay.
    await expect(page.locator("#wwPhasorContextSelect")).toHaveValue(alphaContextId);

    // Exactly one suggestion request was made for BRAVO1's own new
    // source -- never a duplicate, never one for ALPHA1 (already
    // covered).
    const bravoSuggestUrls = suggestUrls.filter((url) => url.includes(encodeURIComponent(bravoSourceId)));
    expect(bravoSuggestUrls).toHaveLength(1);
    const alphaSuggestUrls = suggestUrls.filter((url) => !url.includes(encodeURIComponent(bravoSourceId)));
    expect(alphaSuggestUrls).toHaveLength(0);

    // 5b. Selecting BRAVO1 loads its own six roles correctly.
    const bravoOption = page.locator("#wwPhasorContextSelect option", { hasText: "BRAVO1" });
    await expect(bravoOption).toHaveCount(1);
    const bravoContextId = await bravoOption.getAttribute("value");
    await page.locator("#wwPhasorContextSelect").selectOption(bravoContextId);
    await expect(page.locator("#wwPhasorSvg polygon")).toHaveCount(6);
    await expect(async () => {
      const text = await page.locator("#wwPhasorValuesList").innerText();
      expect(text).toMatch(/100\.0\s*V/);
      expect(text).toMatch(/40\.0\s*A/);
    }).toPass({ timeout: 5000 });
  });

  // ---- Time Group relabel hardening (2026-09-19 hardening pass) ----
  //
  // Root cause (see docs/project-memory/DECISIONS.md DEC-097's own
  // closing section and this pass's own DEC-098): a Time Group's own
  // `group_id` is ALWAYS its current origin source's own `source_id`
  // (app.domain.time_grouping: earliest `start_time`, ties broken by
  // `source_id` string), recomputed fresh from the LIVE source set on
  // every call, never cached/persisted (DEC-057, deliberate/approved).
  // The original flaky test above exercises this via TWO fixtures that
  // happen to share the exact same recorded start timestamp
  // (`phasor_smoke_three_phase`/`phasor_smoke_bravo_three_phase`, both
  // `06/03/2026 10:00:00.000000`), so which one becomes origin is a
  // 50/50 `source_id`-string coin flip -- genuinely random, exactly the
  // kind of timing-dependent reproduction task instruction explicitly
  // forbids relying on. This test instead uploads a THIRD fixture
  // (`phasor_smoke_charlie_earlier_overlap`) whose own recorded start
  // time is ONE FULL SECOND EARLIER than ALPHA1's (09:59:59 vs
  // 10:00:00) while its own absolute interval still overlaps ALPHA1's
  // (both 2s long) -- `(start_time, source_id)` ordering GUARANTEES
  // Charlie becomes the new origin/group_id every single run,
  // deterministically, with zero dependency on source_id randomness.
  test("Time Group relabel (new overlapping-but-earlier source becomes origin) never disturbs Playback continuity", async ({ page }) => {
    // 1. Upload ALPHA1 -> fresh bootstrap claims its own Time Group
    //    (a solo absolute group, so group_id === ALPHA1's own source_id
    //    trivially).
    await uploadFixture(page);
    const alphaSourceId = await page.locator("#recordingsTableBody tr[data-source-id]").last().getAttribute("data-source-id");
    await openAnalysisPhasor(page);
    await expect(page.locator("#wwPhasorContextSelect option")).toHaveCount(2, { timeout: 10000 });
    // A generous timeout, not 5000ms -- see the identical comment in "a
    // later-uploaded, uncovered source is discovered automatically..."
    // above: the very first auto-claim of a Time Group genuinely issues
    // two real fetches in sequence, and a full-suite run's own backend
    // contention can occasionally slow the second one past a tight window.
    await expect(async () => {
      const text = await page.locator("#wwPhasorValuesList").innerText();
      expect(text).toMatch(/100\.0\s*V/);
    }).toPass({ timeout: 10000 });

    await expect(async () => {
      const activeTimeGroupId = await page.evaluate(() => wwPlaybackState().activeTimeGroupId);
      expect(activeTimeGroupId).toBe(alphaSourceId);
    }).toPass({ timeout: 5000 });

    // 2. Advance Playback to a genuinely non-start position -- proves
    //    continuity (not merely "still 0, which would pass even with
    //    the old bug since Restart also lands there").
    const seekSlider = page.locator("#wwPhasorPlaybackMount .ww-tg-playback-seek-slider");
    const bounds = await seekSliderBounds(seekSlider);
    const targetTime = bounds.min + (bounds.max - bounds.min) * 0.6;
    await seekTo(seekSlider, targetTime);
    await expect(async () => {
      const currentTime = await page.evaluate(() => wwPlaybackState().currentTime);
      expect(Math.abs(currentTime - targetTime)).toBeLessThan(0.02);
    }).toPass({ timeout: 5000 });
    const currentTimeBeforeUpload = await page.evaluate(() => wwPlaybackState().currentTime);
    const stateBeforeUpload = await page.evaluate(() => wwPlaybackState().state);

    // 3. Upload CHARLIE1 -- an unrelated, never-Engineering-Context'd
    //    source that overlaps ALPHA1's own absolute interval but starts
    //    one second earlier, DETERMINISTICALLY becoming the new
    //    Time Group origin (see comment above).
    await page.locator("#mainNavRecordingsBtn").click();
    await page.locator("#recordingsUploadBtn, #recordingsEmptyUploadBtn").first().click();
    await expect(page.locator("#uploadModalOverlay")).toBeVisible();
    await page.locator("#uploadModalFile_0").setInputFiles(path.join(FIXTURES, "phasor_smoke_charlie_earlier_overlap.cfg"));
    await page.locator("#uploadModalFile_1").setInputFiles(path.join(FIXTURES, `${STEM}.dat`));
    await page.locator("#uploadModalSubmitBtn").click();
    await page.locator("#uploadModalOverlay").waitFor({ state: "hidden" });
    const charlieSourceId = await page.locator("#recordingsTableBody tr[data-source-id]").last().getAttribute("data-source-id");
    expect(charlieSourceId).not.toBe(alphaSourceId);

    // 4. The relabel genuinely happened (this test actually exercises
    //    the race, never a no-op) -- `wwPlayback.activeTimeGroupId` now
    //    follows Charlie's own id, deterministically, every run.
    await expect(async () => {
      const activeTimeGroupId = await page.evaluate(() => wwPlaybackState().activeTimeGroupId);
      expect(activeTimeGroupId).toBe(charlieSourceId);
    }).toPass({ timeout: 5000 });

    // 5. Playback continuity survived the relabel -- the fix's own
    //    entire point: a relabel updates ONLY the tracked id, never
    //    `currentTime`/`state` (never a Restart, never a reset to
    //    `bounds.start`).
    const currentTimeAfterUpload = await page.evaluate(() => wwPlaybackState().currentTime);
    const stateAfterUpload = await page.evaluate(() => wwPlaybackState().state);
    expect(currentTimeAfterUpload).toBeCloseTo(currentTimeBeforeUpload, 6);
    expect(stateAfterUpload).toBe(stateBeforeUpload);

    // 6. Re-entering Phasor observes the FINAL authoritative Time Group
    //    reliably -- ALPHA1 remains selected and usable, with no
    //    intermediate "Needs configuration" flash and no Restart-driven
    //    `analysis_time=0` request.
    const phasorDiagramRequestTimes = [];
    page.on("request", (request) => {
      const url = request.url();
      if (!url.includes("/phasor-diagram")) return;
      const match = url.match(/analysis_time=([0-9.eE+-]+)/);
      if (match) phasorDiagramRequestTimes.push(parseFloat(match[1]));
    });
    const alphaContextIdSelected = await page.locator("#wwPhasorContextSelect").inputValue();
    await page.locator("#mainNavAnalysisBtn").click();
    await expect(page.locator("#wwPhasorContextSelect")).toHaveValue(alphaContextIdSelected);
    const valuesTextRightAfterReentry = await page.locator("#wwPhasorValuesList").innerText();
    expect(valuesTextRightAfterReentry).toMatch(/100\.0\s*V/);

    await expect(async () => {
      const currentTime = await page.evaluate(() => wwPlaybackState().currentTime);
      expect(Math.abs(currentTime - targetTime)).toBeLessThan(0.02);
    }).toPass({ timeout: 5000 });
    // No request ever asked for a time near ALPHA1's own bounds.start
    // -- a Restart would have. NOT a raw `targetTime` comparison:
    // Charlie's own start_time is genuinely, correctly one second
    // EARLIER than ALPHA1's (that is what makes it deterministically
    // become the new coordinate origin at all -- see this test's own
    // header comment), so ALPHA1's own `alignment_offset_s` correctly
    // shifts by that same one second once Charlie becomes origin
    // (DEC-057's own documented `timestamp_placement_offset_s =
    // source_start_time - origin_start_time` composition) -- a REAL,
    // intentional consequence of a genuine origin change, never
    // something this hardening pass's fix is meant to mask. The fix's
    // own job is narrower and already proven above (workspace
    // `currentTime`/`state` untouched, no Restart) -- this final check
    // only confirms the resulting SOURCE-RELATIVE analysis_time is the
    // mathematically CORRECT one for that same unchanged workspace
    // time, derived the exact same way `wwWorkspaceTimeToSourceTime()`
    // itself would, never independently re-derived.
    const expectedAnalysisTime = await page.evaluate(
      (sid) => wwWorkspaceTimeToSourceTime(sid, wwPlaybackState().currentTime),
      alphaSourceId
    );
    expect(phasorDiagramRequestTimes.length).toBeGreaterThan(0);
    for (const t of phasorDiagramRequestTimes) {
      expect(Math.abs(t - expectedAnalysisTime)).toBeLessThan(0.05);
    }
  });

  test("removing a covered source does not block discovery of a still-uncovered one", async ({ page }) => {
    // 1. Upload A -> auto-bootstrap covers it.
    await uploadFixture(page);
    await openAnalysisPhasor(page);
    await expect(page.locator("#wwPhasorContextSelect option")).toHaveCount(2, { timeout: 10000 });

    // 2. Upload B (BRAVO1) but do NOT visit Phasor again yet -- B stays
    //    genuinely uncovered and unattempted.
    await page.locator("#mainNavRecordingsBtn").click();
    await page.locator("#recordingsUploadBtn, #recordingsEmptyUploadBtn").first().click();
    await expect(page.locator("#uploadModalOverlay")).toBeVisible();
    await page.locator("#uploadModalFile_0").setInputFiles(path.join(FIXTURES, "phasor_smoke_bravo_three_phase.cfg"));
    await page.locator("#uploadModalFile_1").setInputFiles(path.join(FIXTURES, `${STEM}.dat`));
    await page.locator("#uploadModalSubmitBtn").click();
    await page.locator("#uploadModalOverlay").waitFor({ state: "hidden" });

    // 3. Remove source A entirely -- the old workspace-wide
    //    `bootstrapAttempted` boolean would have permanently blocked ANY
    //    further discovery for the rest of the session; the new
    //    per-source `attemptedSourceIds` must not.
    const alphaRow = page.locator("#recordingsTableBody tr[data-source-id]").first();
    const alphaSourceId = await alphaRow.getAttribute("data-source-id");
    await page.locator(`button[data-action="remove"][data-source-id="${alphaSourceId}"]`).click();
    await expect(page.locator("#confirmOverlay")).toBeVisible();
    await page.locator("#confirmRemoveBtn").click();
    await expect(page.locator("#confirmOverlay")).toBeHidden();
    await expect(page.locator(`#recordingsTableBody tr[data-source-id="${alphaSourceId}"]`)).toHaveCount(0);

    // 4. Re-enter Phasor -- BRAVO1 is still discoverable and gets
    //    suggested/selected normally.
    await page.locator("#mainNavAnalysisBtn").click();
    await expect(async () => {
      const text = await page.locator("#wwPhasorValuesList").innerText();
      expect(text).toMatch(/100\.0\s*V/);
      expect(text).toMatch(/40\.0\s*A/);
    }).toPass({ timeout: 10000 });
    await expect(page.locator("#wwPhasorSvg polygon")).toHaveCount(6);
  });

  test("two bare-role sources each get their own distinct Default Context, never deduplicated by display name", async ({ page }) => {
    const BARE_STEM = "phasor_bare_three_phase";

    // Upload the SAME bare-role fixture TWICE -- two genuinely different
    // sources, each producing its OWN "Default Context" suggestion (same
    // display name, different ids). Coverage is keyed by source id, so
    // neither is ever skipped as "already represented" merely because
    // their context happens to share a display name.
    await page.goto("/index.html");
    for (let i = 0; i < 2; i++) {
      await page.locator("#recordingsUploadBtn, #recordingsEmptyUploadBtn").first().click();
      await expect(page.locator("#uploadModalOverlay")).toBeVisible();
      await page.locator("#uploadModalFile_0").setInputFiles(path.join(FIXTURES, `${BARE_STEM}.cfg`));
      await page.locator("#uploadModalFile_1").setInputFiles(path.join(FIXTURES, `${STEM}.dat`));
      await page.locator("#uploadModalSubmitBtn").click();
      await page.locator("#uploadModalOverlay").waitFor({ state: "hidden" });
    }

    await openAnalysisPhasor(page);
    await expect(page.locator("#wwPhasorContextSelect option")).toHaveCount(3, { timeout: 10000 }); // blank + 2x "Default Context"
    const optionValues = await page.locator("#wwPhasorContextSelect option").evaluateAll(
      (opts) => opts.map((o) => o.value).filter((v) => v !== "")
    );
    expect(new Set(optionValues).size).toBe(2); // two distinct ids, never deduplicated
    const optionLabels = await page.locator("#wwPhasorContextSelect option").allTextContents();
    expect(optionLabels.filter((label) => label === "Default Context")).toHaveLength(2);

    // Both are independently usable.
    for (const contextId of optionValues) {
      await selectPhasorContext(page, contextId);
      await expect(page.locator("#wwPhasorSvg polygon")).toHaveCount(6);
    }
  });

  // ---- Scenario B: existing context ----
  test("existing context -> selector populated immediately, no suggestion request made", async ({ page }) => {
    let suggestRequested = false;
    page.on("request", (request) => {
      if (request.url().includes("/engineering-contexts/suggest")) suggestRequested = true;
    });

    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisPhasor(page);

    // Selector populated immediately from the existing context -- no
    // bootstrap ran (no `/suggest` request), so this genuinely proves
    // "existing context" never depends on the fallback discovery path.
    // DEC-105 (2026-09-23): unlike this test's own original assumption,
    // the FIRST time this workspace session ever has a usable context
    // list now auto-selects it immediately, regardless of whether that
    // list came from a manual POST (here) or DEC-104's own upload-time
    // preparation -- see support/engineering_context_helpers.js's own
    // header comment. Values render with zero manual selection.
    await expect(page.locator("#wwPhasorContextSelect option")).toHaveCount(2); // blank + Alpha 1
    await expect(page.locator("#wwPhasorContextSelect")).toHaveValue(contextId);
    await expect(page.locator("#wwPhasorEmptyState")).toBeHidden();
    await expect(async () => {
      const text = await page.locator("#wwPhasorValuesList").innerText();
      expect(text).toMatch(/100\.0\s*V/);
    }).toPass({ timeout: 5000 });
    expect(suggestRequested).toBe(false);
  });

  // ---- Scenario C: no source ----
  // Updated by the Manual Input / Calculator mode architectural work
  // (see docs/project-memory/ANALYSIS_INPUT_SOURCE.md): a genuinely
  // empty workspace now auto-selects Manual, which hides the WHOLE
  // Recording-only section (Bay/Context bar, Playback, Related
  // Waveforms, and this "no event sources" empty-state paragraph along
  // with it) rather than showing that message as the page's own
  // headline state -- Phasor remains fully usable as a standalone
  // calculator regardless. `#wwPhasorBody` (Inputs/Values, Diagram) is
  // therefore no longer hidden here at all; see the dedicated "Manual
  // Input / Calculator mode" describe block below for full empty-
  // workspace coverage.
  test("empty workspace -> Manual auto-selected, Recording-only section (including the no-sources message) hidden, Phasor remains usable", async ({ page }) => {
    await page.goto("/index.html");
    await openAnalysisPhasor(page);

    await expect(page.locator("#wwPhasorInputSourceManualBtn")).toHaveAttribute("aria-pressed", "true");
    await expect(page.locator("#wwPhasorInputSourceRecordingBtn")).toBeDisabled();
    await expect(page.locator("#wwPhasorRecordingSection")).toBeHidden();
    await expect(page.locator("#wwPhasorEmptyState")).toContainText("No event sources are available");
    await expect(page.locator("#wwPhasorEmptyState")).not.toContainText("Engineering Context");
    await expect(page.locator("#wwPhasorBody")).toBeVisible();
    await expect(page.locator("#wwPhasorManualInputSection")).toBeVisible();
  });
});

test.describe("Phasor Analysis -- Manual Input / Calculator mode (Analysis Input Source)", () => {
  // Phasor's own implementation of the shared Analysis Input Source
  // concept (see docs/project-memory/ANALYSIS_INPUT_SOURCE.md) --
  // Overcurrent's own DEC-095 slice was the first; this is the second,
  // reusing the SAME shared shell from day one (never the flawed
  // intermediate "Manual coupled to recording lifecycle" design
  // Overcurrent briefly shipped and then corrected). No IEC/RMS/CT/VT
  // math is re-derived in this file -- every assertion here is end-to-
  // end through the SAME production backend endpoint/domain functions
  // backend/tests/test_phasor_diagram_api.py's own
  // TestManualPhasorDiagramEndpoint already golden-tests directly.

  async function enterRole(page, roleKey, { magnitude, unit, angleDeg, enabled = true } = {}) {
    if (enabled) await page.locator(`#wwPhasorManual${roleKey}Enabled`).check();
    if (unit !== undefined) await page.locator(`#wwPhasorManual${roleKey}Unit`).selectOption(unit);
    if (magnitude !== undefined) {
      await page.locator(`#wwPhasorManual${roleKey}Magnitude`).fill(String(magnitude));
      await page.locator(`#wwPhasorManual${roleKey}Magnitude`).dispatchEvent("change");
      // Same harness finding documented elsewhere in this suite: `.fill()`
      // leaves focus in the field, so an explicit blur settles the
      // browser's own native blur-triggered "change" before the next
      // action (never a production concern).
      await page.locator(`#wwPhasorManual${roleKey}Magnitude`).blur();
    }
    if (angleDeg !== undefined) {
      await page.locator(`#wwPhasorManual${roleKey}Angle`).fill(String(angleDeg));
      await page.locator(`#wwPhasorManual${roleKey}Angle`).dispatchEvent("change");
      await page.locator(`#wwPhasorManual${roleKey}Angle`).blur();
    }
  }

  async function setRatio(page, prefix, { primary, secondary }) {
    if (primary !== undefined) {
      await page.locator(`#wwPhasorManual${prefix}PrimaryInput`).fill(String(primary));
      await page.locator(`#wwPhasorManual${prefix}PrimaryInput`).dispatchEvent("change");
    }
    if (secondary !== undefined) {
      await page.locator(`#wwPhasorManual${prefix}SecondaryInput`).fill(String(secondary));
      await page.locator(`#wwPhasorManual${prefix}SecondaryInput`).dispatchEvent("change");
    }
  }

  async function openEmptyWorkspacePhasor(page) {
    await page.goto("/index.html");
    await openAnalysisPhasor(page);
  }

  test("empty workspace: Manual auto-selected, Recording shown disabled with hint, Phasor fully usable with zero recordings", async ({ page }) => {
    await openEmptyWorkspacePhasor(page);
    await expect(page.locator("#wwPhasorBody")).toBeVisible();
    await expect(page.locator("#wwPhasorInputSourceManualBtn")).toHaveAttribute("aria-pressed", "true");
    await expect(page.locator("#wwPhasorInputSourceRecordingBtn")).toBeDisabled();
    await expect(page.locator("#wwPhasorInputSourceHint")).toBeVisible();
    await expect(page.locator("#wwPhasorInputSourceHint")).toContainText("No recording loaded");
    await expect(page.locator("#wwPhasorManualInputSection")).toBeVisible();
    await expect(page.locator("#wwPhasorRecordingSection")).toBeHidden();
  });

  test("golden owner worked example: VT 132000/110, CT 1200/1, Primary Va/Vb/Vc=132kV, Ia/Ib/Ic=1200A -> 110 V / 1 A secondary, zero recording-dependent requests", async ({ page }) => {
    const recordingRequestUrls = [];
    page.on("request", (req) => {
      const url = req.url();
      if (url.includes("/phasor-diagram") || url.includes("/waveform") || url.includes("/phasor?")) recordingRequestUrls.push(url);
    });

    await openEmptyWorkspacePhasor(page);

    await page.locator("#wwPhasorManualVoltageBasisSelect").selectOption("primary");
    await setRatio(page, "Vt", { primary: 132000, secondary: 110 });
    await enterRole(page, "Va", { magnitude: 132, unit: "kV", angleDeg: 0 });
    await enterRole(page, "Vb", { magnitude: 132, unit: "kV", angleDeg: -120 });
    await enterRole(page, "Vc", { magnitude: 132, unit: "kV", angleDeg: 120 });

    await page.locator("#wwPhasorManualCurrentBasisSelect").selectOption("primary");
    await setRatio(page, "Ct", { primary: 1200, secondary: 1 });
    await enterRole(page, "Ia", { magnitude: 1200, unit: "A", angleDeg: -30 });
    await enterRole(page, "Ib", { magnitude: 1200, unit: "A", angleDeg: -150 });
    await enterRole(page, "Ic", { magnitude: 1200, unit: "A", angleDeg: 90 });

    // DEC-099 flake fix (root cause, confirmed by direct reproduction --
    // not assumed): each field's own "change" event independently
    // triggers a fresh `/phasor-manual` request (`wwPhasorRequestManualDiagram()`),
    // so entering all six roles above dispatches many overlapping
    // requests; only the LATEST one (by generation counter) is ever
    // rendered, exactly as designed. The role label itself (e.g. "Va")
    // is rendered even for an UNAVAILABLE/"Missing" role -- so
    // `text.toContain("Va")` was satisfied as early as the very FIRST
    // request (right after Va's own magnitude was entered), long before
    // Vb/Vc/Ia/Ib/Ic existed at all. Under normal local load this went
    // unnoticed (all requests settle well within the time the test's own
    // remaining interactions take), but under real backend latency
    // (proven via a temporary `page.route()` delay injected specifically
    // on Ic's own request) this exact condition let the test read a
    // STALE, partially-populated render -- reproducing the real observed
    // failure symptom byte-for-byte ("Ic: Missing", every other role
    // correct).
    //
    // Waiting for Ic's own MAGNITUDE alone (the first fix attempt) is
    // still insufficient: `enterRole()` fills magnitude and angle as two
    // SEPARATE fields, each dispatching its own independent "change" and
    // therefore its own independent request -- so there is a genuine
    // intermediate, fully-valid rendered state where Ic's magnitude has
    // already updated to "1.0 A" but its angle has not yet advanced past
    // whatever it showed before (reproduced directly: a real run landed
    // exactly here, magnitude correct at "1.0 A" but angle still the
    // stale "+120.0" left over from an earlier in-progress edit). Only
    // Ic showing BOTH its own final magnitude AND its own final angle
    // together guarantees every other role's value in the SAME response
    // is also fully current, since every response carries the complete
    // state and only the latest-generation response is ever rendered.
    await expect(async () => {
      const text = await page.locator("#wwPhasorValuesList").innerText();
      expect(text).toMatch(/Ic[\s\S]*?1\.0\s*A[\s\S]*?\+90\.0/);
    }).toPass({ timeout: 5000 });

    const text = await page.locator("#wwPhasorValuesList").innerText();
    for (const [role, angle] of [["Va", "0.0"], ["Vb", "-120.0"], ["Vc", "+120.0"]]) {
      expect(text).toMatch(new RegExp(`${role}[\\s\\S]*?110\\.0\\s*V[\\s\\S]*?${angle.replace("+", "\\+")}`));
    }
    for (const [role, angle] of [["Ia", "-30.0"], ["Ib", "-150.0"], ["Ic", "\\+90.0"]]) {
      expect(text).toMatch(new RegExp(`${role}[\\s\\S]*?1\\.0\\s*A[\\s\\S]*?${angle}`));
    }

    await expect(page.locator("#wwPhasorSvg polygon")).toHaveCount(6);
    expect(recordingRequestUrls).toEqual([]);

    // Graphical scale is derived from the CANONICAL secondary values
    // (110V/1A), never the raw entered Primary magnitudes (132kV/1200A)
    // -- basis conversion must happen before scale derivation, not after.
    const legendTexts = await page.locator("#wwPhasorSvg text.ww-phasor-scale-legend").allTextContents();
    const voltageLine = legendTexts.find((t) => t.startsWith("V:"));
    const currentLine = legendTexts.find((t) => t.startsWith("I:"));
    expect(voltageLine).toMatch(/126\.5/); // 1.15 * 110V secondary
    expect(currentLine).toMatch(/1\.1/); // 1.15 * 1A secondary (toFixed(1) => "1.1")
    expect(voltageLine).not.toMatch(/151800/); // NOT 1.15 * 132000V primary
    expect(currentLine).not.toMatch(/1380/); // NOT 1.15 * 1200A primary
  });

  test("mixed basis: Voltage Primary, Current Secondary -- the two selectors are truly independent", async ({ page }) => {
    await openEmptyWorkspacePhasor(page);

    await page.locator("#wwPhasorManualVoltageBasisSelect").selectOption("primary");
    await setRatio(page, "Vt", { primary: 132000, secondary: 110 });
    await enterRole(page, "Va", { magnitude: 132, unit: "kV", angleDeg: 0 });

    await page.locator("#wwPhasorManualCurrentBasisSelect").selectOption("secondary");
    await expect(page.locator("#wwPhasorManualCtRatioRow")).toBeHidden();
    await enterRole(page, "Ia", { magnitude: 1, unit: "A", angleDeg: -30 });

    await expect(async () => {
      const text = await page.locator("#wwPhasorValuesList").innerText();
      expect(text).toMatch(/Va[\s\S]*?110\.0\s*V/);
      expect(text).toMatch(/Ia[\s\S]*?1\.0\s*A/);
    }).toPass({ timeout: 5000 });
  });

  test("VT/PT and CT ratio fields only appear when their own family's basis is Primary", async ({ page }) => {
    await openEmptyWorkspacePhasor(page);
    await expect(page.locator("#wwPhasorManualVtRatioRow")).toBeVisible(); // default basis is Primary
    await expect(page.locator("#wwPhasorManualCtRatioRow")).toBeVisible();

    await page.locator("#wwPhasorManualVoltageBasisSelect").selectOption("secondary");
    await expect(page.locator("#wwPhasorManualVtRatioRow")).toBeHidden();
    await expect(page.locator("#wwPhasorManualCtRatioRow")).toBeVisible(); // Current basis untouched

    await page.locator("#wwPhasorManualCurrentBasisSelect").selectOption("secondary");
    await expect(page.locator("#wwPhasorManualCtRatioRow")).toBeHidden();
  });

  test("kA equals A, kV equals V (shared engineering-unit layer)", async ({ page }) => {
    await openEmptyWorkspacePhasor(page);
    await page.locator("#wwPhasorManualVoltageBasisSelect").selectOption("secondary");
    await page.locator("#wwPhasorManualCurrentBasisSelect").selectOption("secondary");

    // The backend always reports the canonical base unit ('V'/'A',
    // never auto-rescaled to kV/kA for display) -- entering the SAME
    // physical magnitude via a different declared unit must therefore
    // produce byte-for-byte identical rendered output.
    await enterRole(page, "Va", { magnitude: 132000, unit: "V", angleDeg: 0 });
    await enterRole(page, "Ia", { magnitude: 1200, unit: "A", angleDeg: 0 });
    await expect(async () => {
      const text = await page.locator("#wwPhasorValuesList").innerText();
      expect(text).toMatch(/Va[\s\S]*?132000\.0\s*V/);
      expect(text).toMatch(/Ia[\s\S]*?1200\.0\s*A/);
    }).toPass({ timeout: 5000 });
    const textV = await page.locator("#wwPhasorValuesList").innerText();

    await enterRole(page, "Va", { magnitude: 132, unit: "kV" });
    await enterRole(page, "Ia", { magnitude: 1.2, unit: "kA" });
    await expect(async () => {
      const text = await page.locator("#wwPhasorValuesList").innerText();
      expect(text).toMatch(/Va[\s\S]*?132000\.0\s*V/);
      expect(text).toMatch(/Ia[\s\S]*?1200\.0\s*A/);
    }).toPass({ timeout: 5000 });
    const textKv = await page.locator("#wwPhasorValuesList").innerText();
    expect(textKv).toBe(textV);
  });

  test("angle normalization: 240 degrees entered reports as -120 degrees", async ({ page }) => {
    await openEmptyWorkspacePhasor(page);
    await page.locator("#wwPhasorManualVoltageBasisSelect").selectOption("secondary");
    await enterRole(page, "Va", { magnitude: 110, unit: "V", angleDeg: 240 });
    await expect(async () => {
      const text = await page.locator("#wwPhasorValuesList").innerText();
      expect(text).toMatch(/Va[\s\S]*?-120\.0°/);
    }).toPass({ timeout: 5000 });
  });

  test("partial input: only Va and Ia enabled -- the other four roles report Missing, never blocking the two valid ones", async ({ page }) => {
    await openEmptyWorkspacePhasor(page);
    await page.locator("#wwPhasorManualVoltageBasisSelect").selectOption("secondary");
    await page.locator("#wwPhasorManualCurrentBasisSelect").selectOption("secondary");
    await enterRole(page, "Va", { magnitude: 110, unit: "V", angleDeg: 0 });
    await enterRole(page, "Ia", { magnitude: 1, unit: "A", angleDeg: -30 });

    await expect(async () => {
      const text = await page.locator("#wwPhasorValuesList").innerText();
      expect(text).toMatch(/Va[\s\S]*?110\.0\s*V/);
    }).toPass({ timeout: 5000 });
    const text = await page.locator("#wwPhasorValuesList").innerText();
    for (const role of ["Vb", "Vc", "Ib", "Ic"]) {
      expect(text).toMatch(new RegExp(`${role}[\\s\\S]{0,20}Missing`));
    }
    await expect(page.locator("#wwPhasorSvg polygon")).toHaveCount(2);
  });

  test("invalid VT ratio blocks only Voltage roles; Current roles remain available", async ({ page }) => {
    await openEmptyWorkspacePhasor(page);
    await page.locator("#wwPhasorManualVoltageBasisSelect").selectOption("primary");
    await setRatio(page, "Vt", { primary: 0, secondary: 110 });
    await enterRole(page, "Va", { magnitude: 132, unit: "kV", angleDeg: 0 });

    await page.locator("#wwPhasorManualCurrentBasisSelect").selectOption("secondary");
    await enterRole(page, "Ia", { magnitude: 1, unit: "A", angleDeg: -30 });

    await expect(async () => {
      const text = await page.locator("#wwPhasorValuesList").innerText();
      expect(text).toMatch(/Ia[\s\S]*?1\.0\s*A/);
    }).toPass({ timeout: 5000 });
    const text = await page.locator("#wwPhasorValuesList").innerText();
    expect(text).toMatch(/Va[\s\S]{0,30}Needs configuration/);
    await expect(page.locator("#wwPhasorSvg polygon")).toHaveCount(1); // only Ia plotted
  });

  test("invalid magnitude (negative) on one row never corrupts other valid rows, and no fabricated vector is plotted", async ({ page }) => {
    await openEmptyWorkspacePhasor(page);
    await page.locator("#wwPhasorManualVoltageBasisSelect").selectOption("secondary");
    await enterRole(page, "Va", { magnitude: -5, unit: "V", angleDeg: 0 });
    await enterRole(page, "Vb", { magnitude: 110, unit: "V", angleDeg: -120 });

    await expect(async () => {
      const text = await page.locator("#wwPhasorValuesList").innerText();
      expect(text).toMatch(/Vb[\s\S]*?110\.0\s*V/);
    }).toPass({ timeout: 5000 });
    const text = await page.locator("#wwPhasorValuesList").innerText();
    expect(text).toMatch(/Va[\s\S]{0,20}Missing/);
    await expect(page.locator("#wwPhasorSvg polygon")).toHaveCount(1); // only Vb plotted
  });

  test("disabled large vector never inflates the Current scale -- only the enabled Ia drives it", async ({ page }) => {
    await openEmptyWorkspacePhasor(page);
    await page.locator("#wwPhasorManualCurrentBasisSelect").selectOption("secondary");
    await enterRole(page, "Ia", { magnitude: 10, unit: "A", angleDeg: 0 });
    // Ib's own magnitude/unit/angle are filled in, but its checkbox is
    // left UNCHECKED -- a disabled role must report Missing and be
    // completely excluded from the family's own scale derivation.
    await enterRole(page, "Ib", { magnitude: 10000, unit: "A", angleDeg: -120, enabled: false });

    await expect(async () => {
      const text = await page.locator("#wwPhasorValuesList").innerText();
      expect(text).toMatch(/Ia[\s\S]*?10\.0\s*A/);
    }).toPass({ timeout: 5000 });
    const text = await page.locator("#wwPhasorValuesList").innerText();
    expect(text).toMatch(/Ib[\s\S]{0,20}Missing/);

    const legendTexts = await page.locator("#wwPhasorSvg text.ww-phasor-scale-legend").allTextContents();
    const currentLine = legendTexts.find((t) => t.startsWith("I:"));
    expect(currentLine).toMatch(/11\.5/); // 1.15 * 10A -- Ia alone
    expect(currentLine).not.toMatch(/11500/); // NOT 1.15 * 10000A from the disabled Ib
    await expect(page.locator("#wwPhasorSvg polygon")).toHaveCount(1); // only Ia plotted
  });

  test("all-zero-magnitude Voltage family renders safely -- no NaN/divide-by-zero, zero remains a valid value, Current stays unaffected", async ({ page }) => {
    await openEmptyWorkspacePhasor(page);
    await page.locator("#wwPhasorManualVoltageBasisSelect").selectOption("secondary");
    await page.locator("#wwPhasorManualCurrentBasisSelect").selectOption("secondary");
    await enterRole(page, "Va", { magnitude: 0, unit: "V", angleDeg: 0 });
    await enterRole(page, "Ia", { magnitude: 10, unit: "A", angleDeg: 90 });

    await expect(async () => {
      const text = await page.locator("#wwPhasorValuesList").innerText();
      expect(text).toMatch(/Ia[\s\S]*?10\.0\s*A/);
    }).toPass({ timeout: 5000 });
    const text = await page.locator("#wwPhasorValuesList").innerText();
    // A genuine zero magnitude is a VALID Manual Phasor input (e.g. a
    // de-energized phase), never treated as Missing/invalid.
    expect(text).toMatch(/Va[\s\S]*?0\.0\s*V/);
    expect(text).not.toMatch(/NaN/);

    // No "V:" legend line is drawn for an all-zero Voltage family
    // (nothing to scale a ring to -- safe fallback, never a divide by
    // zero), but Current's own scale is completely unaffected.
    const legendTexts = await page.locator("#wwPhasorSvg text.ww-phasor-scale-legend").allTextContents();
    expect(legendTexts.some((t) => t.startsWith("V:"))).toBe(false);
    const currentLine = legendTexts.find((t) => t.startsWith("I:"));
    expect(currentLine).toMatch(/11\.5/);

    // No SVG attribute is NaN anywhere in the diagram.
    const svgContent = await page.locator("#wwPhasorSvg").innerHTML();
    expect(svgContent).not.toMatch(/NaN/);
  });

  test("Related Waveforms panel is hidden/collapsed entirely in Manual mode, never a fabricated waveform", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisPhasor(page);
    await selectPhasorContext(page, contextId);
    await expect(page.locator("#wwAnalysisRelatedWaveformsPanel")).toBeVisible();

    await page.locator("#wwPhasorInputSourceManualBtn").click();
    await page.locator("#wwPhasorManualVoltageBasisSelect").selectOption("secondary");
    await enterRole(page, "Va", { magnitude: 110, unit: "V", angleDeg: 0 });
    await expect(async () => {
      const text = await page.locator("#wwPhasorValuesList").innerText();
      expect(text).toMatch(/Va[\s\S]*?110\.0\s*V/);
    }).toPass({ timeout: 5000 });

    await expect(page.locator("#wwPhasorRecordingSection")).toBeHidden();
    await expect(page.locator("#wwAnalysisRelatedWaveformsPanel")).toBeHidden();
  });

  test("Playback movement does not move the Manual result or vectors", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisPhasor(page);
    await selectPhasorContext(page, contextId);
    await expect(page.locator("#wwPhasorInputSourceRecordingBtn")).toHaveAttribute("aria-pressed", "true");

    await page.locator("#wwPhasorInputSourceManualBtn").click();
    await page.locator("#wwPhasorManualVoltageBasisSelect").selectOption("secondary");
    await enterRole(page, "Va", { magnitude: 110, unit: "V", angleDeg: 0 });
    await expect(async () => {
      const text = await page.locator("#wwPhasorValuesList").innerText();
      expect(text).toMatch(/Va[\s\S]*?110\.0\s*V/);
    }).toPass({ timeout: 5000 });

    const textBefore = await page.locator("#wwPhasorValuesList").innerText();

    let diagramRequests = 0;
    page.on("request", (req) => {
      if (req.url().includes("/phasor-diagram")) diagramRequests++;
    });

    // Drive Playback via Overcurrent's own mount, which shares the SAME
    // Time Group this context resolved to -- Phasor's own mount is
    // hidden while Manual is active, so this is the only way to move
    // the shared clock while proving Manual stays inert.
    await page.locator("#wwAnalysisTypeOvercurrentBtn").click();
    await page.locator("#wwOvercurrentContextSelect").selectOption(contextId);
    const slider = page.locator("#wwOvercurrentPlaybackMount .ww-tg-playback-seek-slider");
    await expect(slider).toBeVisible();
    const { min, max } = await seekSliderBounds(slider);
    await seekTo(slider, min + (max - min) * 0.8);
    await page.locator("#wwOvercurrentPlaybackMount .ww-tg-playback-play-btn").click();
    await page.waitForTimeout(500);
    await page.locator("#wwOvercurrentPlaybackMount .ww-tg-playback-play-btn").click();

    await page.locator("#wwAnalysisTypePhasorBtn").click();
    await expect(page.locator("#wwPhasorInputSourceManualBtn")).toHaveAttribute("aria-pressed", "true");
    const textAfter = await page.locator("#wwPhasorValuesList").innerText();
    expect(textAfter).toBe(textBefore);
    expect(diagramRequests).toBe(0);
  });

  test("switching back to Recording restores the recording-driven diagram exactly; Manual/Recording state never cross-contaminates", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisPhasor(page);
    await selectPhasorContext(page, contextId);
    await expect(async () => {
      const text = await page.locator("#wwPhasorValuesList").innerText();
      expect(text).toMatch(/100\.0\s*V/);
    }).toPass({ timeout: 5000 });
    const recordingText = await page.locator("#wwPhasorValuesList").innerText();

    await page.locator("#wwPhasorInputSourceManualBtn").click();
    await page.locator("#wwPhasorManualVoltageBasisSelect").selectOption("secondary");
    await enterRole(page, "Va", { magnitude: 250, unit: "V", angleDeg: 45 });
    await expect(async () => {
      const text = await page.locator("#wwPhasorValuesList").innerText();
      expect(text).toMatch(/250\.0\s*V/);
    }).toPass({ timeout: 5000 });

    await page.locator("#wwPhasorInputSourceRecordingBtn").click();
    await expect(async () => {
      const text = await page.locator("#wwPhasorValuesList").innerText();
      expect(text).toMatch(/100\.0\s*V/);
    }).toPass({ timeout: 5000 });
    const restoredText = await page.locator("#wwPhasorValuesList").innerText();
    expect(restoredText).toBe(recordingText);

    // Manual's own values are untouched by the round trip.
    await page.locator("#wwPhasorInputSourceManualBtn").click();
    await expect(page.locator("#wwPhasorManualVaMagnitude")).toHaveValue("250");
    await expect(page.locator("#wwPhasorManualVaAngle")).toHaveValue("45");
  });

  test("Manual graphical scale is derived fresh from Manual's own values, never inherited from Recording's frozen scale (owner-reported bug fix)", async ({ page }) => {
    // Owner-reported defect: Manual Va=110V/45deg, Ia=10A/90deg rendered
    // under a graphical scale left over from Recording (this fixture's
    // own known balanced 100V/40A), collapsing the Current vector to
    // near-invisibility (the Values panel itself was always correct --
    // only the DIAGRAM's own graphical scale was stale). Proves the fix:
    // switching Input Source immediately recomputes each family's scale
    // from the NOW-active mode's own values only, in both directions.
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisPhasor(page);
    await selectPhasorContext(page, contextId);
    await expect(async () => {
      const text = await page.locator("#wwPhasorValuesList").innerText();
      expect(text).toMatch(/100\.0\s*V/);
      expect(text).toMatch(/40\.0\s*A/);
    }).toPass({ timeout: 5000 });

    // Recording's own scale, established from the 100V/40A fixture --
    // outer ring = 1.15 * 40A = 46.0A.
    const recordingLegendTexts = await page.locator("#wwPhasorSvg text.ww-phasor-scale-legend").allTextContents();
    const recordingCurrentLine = recordingLegendTexts.find((t) => t.startsWith("I:"));
    expect(recordingCurrentLine).toMatch(/46\.0/);

    // Switch to Manual and enter ONLY the owner's own repro values --
    // every other role stays disabled.
    await page.locator("#wwPhasorInputSourceManualBtn").click();
    await page.locator("#wwPhasorManualVoltageBasisSelect").selectOption("secondary");
    await page.locator("#wwPhasorManualCurrentBasisSelect").selectOption("secondary");
    await enterRole(page, "Va", { magnitude: 110, unit: "V", angleDeg: 45 });
    await enterRole(page, "Ia", { magnitude: 10, unit: "A", angleDeg: 90 });
    await expect(async () => {
      const text = await page.locator("#wwPhasorValuesList").innerText();
      expect(text).toMatch(/Va[\s\S]*?110\.0\s*V/);
      expect(text).toMatch(/Ia[\s\S]*?10\.0\s*A/);
    }).toPass({ timeout: 5000 });

    // The scale must now derive ONLY from Manual's own 110V/10A --
    // outer ring = 1.15 * 110V = 126.5V, 1.15 * 10A = 11.5A -- NEVER the
    // recording's stale 100V/40A values.
    const manualLegendTexts = await page.locator("#wwPhasorSvg text.ww-phasor-scale-legend").allTextContents();
    const manualVoltageLine = manualLegendTexts.find((t) => t.startsWith("V:"));
    const manualCurrentLine = manualLegendTexts.find((t) => t.startsWith("I:"));
    expect(manualVoltageLine).toMatch(/126\.5/);
    expect(manualCurrentLine).toMatch(/11\.5/);
    expect(manualCurrentLine).not.toMatch(/46\.0/);

    // Geometry: the Current vector is NOT collapsed near the origin --
    // its rendered endpoint reaches a substantial fraction of the
    // 90-unit plot radius (owner requirement: "Ia is not collapsed near
    // origin"; before the fix this was a ~4-unit sliver).
    const iaLine = page.locator("#wwPhasorSvg line.ww-phasor-vector--current").first();
    const x2 = Number(await iaLine.getAttribute("x2"));
    const y2 = Number(await iaLine.getAttribute("y2"));
    expect(Math.hypot(x2, y2)).toBeGreaterThan(50);

    // Switching back to Recording restores ITS OWN scale exactly --
    // Manual's own edits never contaminate Recording's in the other
    // direction either.
    await page.locator("#wwPhasorInputSourceRecordingBtn").click();
    await expect(async () => {
      const text = await page.locator("#wwPhasorValuesList").innerText();
      expect(text).toMatch(/100\.0\s*V/);
    }).toPass({ timeout: 5000 });
    const restoredLegendTexts = await page.locator("#wwPhasorSvg text.ww-phasor-scale-legend").allTextContents();
    const restoredCurrentLine = restoredLegendTexts.find((t) => t.startsWith("I:"));
    expect(restoredCurrentLine).toMatch(/46\.0/);
  });

  test("Recording mode with zero recordings shows a clean neutral state, never a crash or stale Manual result relabeled as Recording", async ({ page }) => {
    await openEmptyWorkspacePhasor(page);
    await page.locator("#wwPhasorManualVoltageBasisSelect").selectOption("secondary");
    await enterRole(page, "Va", { magnitude: 110, unit: "V", angleDeg: 0 });
    await expect(async () => {
      const text = await page.locator("#wwPhasorValuesList").innerText();
      expect(text).toMatch(/110\.0\s*V/);
    }).toPass({ timeout: 5000 });

    await expect(page.locator("#wwPhasorInputSourceRecordingBtn")).toBeDisabled();
    await page.locator("#wwPhasorInputSourceRecordingBtn").click({ force: true });
    await expect(page.locator("#wwPhasorInputSourceManualBtn")).toHaveAttribute("aria-pressed", "true");
  });

  for (const width of [1366, 1024]) {
    test(`at ${width}px: Manual Phasors panel fits cleanly, Recording shown disabled (not hidden), no overflow`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await openEmptyWorkspacePhasor(page);
      await page.locator("#wwPhasorManualVoltageBasisSelect").selectOption("secondary");
      await enterRole(page, "Va", { magnitude: 110, unit: "V", angleDeg: 0 });
      await expect(async () => {
        const text = await page.locator("#wwPhasorValuesList").innerText();
        expect(text).toMatch(/110\.0\s*V/);
      }).toPass({ timeout: 5000 });

      const overflowX = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      expect(overflowX).toBeLessThanOrEqual(1);
      await expect(page.locator("#wwPhasorInputSourceRecordingBtn")).toBeVisible();
      await expect(page.locator("#wwPhasorInputSourceRecordingBtn")).toBeDisabled();
      await expect(page.locator("#wwPhasorManualVoltageBasisSelect")).toBeVisible();
      await expect(page.locator("#wwPhasorManualCurrentBasisSelect")).toBeVisible();
    });
  }
});
