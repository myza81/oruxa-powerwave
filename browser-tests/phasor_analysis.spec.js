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
// `wwWirePlaybackControls()`/`wwSyncPlaybackControls()`) the Waveform Time
// Group toolbar uses -- there is no separate "Analysis Time" input any
// more, the mounted seek scrubber (`.ww-tg-playback-seek-slider`) IS
// Phasor's own analysis time control. These tests reuse the EXACT
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

  test("no context selected shows an explanatory empty state, not a broken diagram", async ({ page }) => {
    // Uses uploadAndCreateContext() (a MANUAL context, created directly
    // via the backend API) rather than a bare uploadFixture() -- a
    // workspace with an EXISTING context never runs the automatic
    // suggestion bootstrap (see the "existing context -> ... no
    // suggestion request made" scenario below), so "no context selected"
    // is a genuinely stable state here, never a transient one a
    // fast-enough auto-bootstrap could race past.
    await uploadAndCreateContext(page);
    await openAnalysisPhasor(page);
    await expect(page.locator("#wwPhasorEmptyState")).toBeVisible();
    await expect(page.locator("#wwPhasorEmptyState")).toHaveText("Select an Engineering Context to begin.");
    await expect(page.locator("#wwPhasorBody")).toBeHidden();
    await expect(page.locator("#wwPhasorPlaybackPanel")).toBeHidden();
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

// Phasor Playback integration: Phasor consumes the ONE shared, reusable
// `wwPlayback` controller (see browser-tests/playback.spec.js for that
// controller's own foundational coverage) -- never a second clock/timer.
// These scenarios exercise the mounted Playback control surface end to
// end against the real aggregated `/phasor-diagram` endpoint.
test.describe("Phasor Analysis -- Playback integration", () => {
  test("Play advances shared time, produces repeated aggregated results, and never mutates the Engineering Context", async ({ page }) => {
    const { workspaceId, contextId } = await uploadAndCreateContext(page);
    await openAnalysisPhasor(page);
    await page.locator("#wwPhasorContextSelect").selectOption(contextId);
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
    await page.waitForTimeout(600);

    // Repeated aggregated results -- more than the one static fetch this
    // page already made before Play.
    expect(diagramFetchCount).toBeGreaterThan(1);
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
    await page.locator("#wwPhasorContextSelect").selectOption(contextId);
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
    // analysis_time are numerically identical here).
    expect(requestedTimes.length).toBeGreaterThan(0);
    const lastRequestedTime = requestedTimes[requestedTimes.length - 1];
    expect(Math.abs(lastRequestedTime - pausedTime)).toBeLessThan(0.01);
  });

  test("Seek while paused converges exactly to the released position", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisPhasor(page);
    await page.locator("#wwPhasorContextSelect").selectOption(contextId);
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
    await page.locator("#wwPhasorContextSelect").selectOption(contextId);
    await expect(page.locator("#wwPhasorSvg polygon")).toHaveCount(6);

    await page.locator("#wwPhasorPlaybackMount .ww-tg-playback-speed-select").selectOption("4");

    let diagramFetchCount = 0;
    page.on("request", (request) => { if (request.url().includes("/phasor-diagram")) diagramFetchCount += 1; });

    await page.locator("#wwPhasorPlaybackMount .ww-tg-playback-play-btn").click();
    await page.waitForTimeout(600);

    // At 4x over ~600ms of real time (with the throttle at ~100ms), the
    // request count must stay bounded -- nowhere near one per rAF frame
    // (which would be dozens at 60 fps).
    expect(diagramFetchCount).toBeGreaterThan(0);
    expect(diagramFetchCount).toBeLessThan(15);
  });

  test("Restart lands at the Time Group's own start; insufficient history is reported honestly, never dodged", async ({ page }) => {
    const { contextId } = await uploadAndCreateContext(page);
    await openAnalysisPhasor(page);
    await page.locator("#wwPhasorContextSelect").selectOption(contextId);
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
    await page.locator("#wwPhasorContextSelect").selectOption(contextId);
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
    const { contextId } = await uploadAndCreateContext(page);

    // Display a channel in Waveform and play it to a specific time.
    const row = page.locator("#recordingsTableBody tr[data-source-id]").last();
    await row.click();
    await expect(page.locator("#wwWorkspaceLoading")).toBeHidden();
    const channelRow = page.locator('#channelGroups tr.channel-row--toggle[data-channel-kind="analog"]').first();
    await expect(channelRow).toBeVisible();
    await channelRow.click();
    await expect(channelRow).toHaveAttribute("aria-pressed", "true");
    const canvas = page.locator("#wwTimeGroupCanvases .ww-time-group-canvas").first();
    await expect(canvas).toBeVisible();
    const waveformSlider = canvas.locator(".ww-tg-playback-seek-slider");
    await seekTo(waveformSlider, 1.25);
    await expect(async () => {
      const currentTime = await page.evaluate(() => wwPlaybackState().currentTime);
      expect(Math.abs(currentTime - 1.25)).toBeLessThan(0.01);
    }).toPass({ timeout: 5000 });

    // Open Phasor -- it must reflect the SAME shared time, never reset it.
    await openAnalysisPhasor(page);
    await page.locator("#wwPhasorContextSelect").selectOption(contextId);
    const phasorSlider = page.locator("#wwPhasorPlaybackMount .ww-tg-playback-seek-slider");
    await expect(async () => {
      expect(Number(await phasorSlider.inputValue())).toBeCloseTo(1.25, 1);
    }).toPass({ timeout: 5000 });

    // Seek further from Phasor, then confirm Waveform reflects it too.
    await seekTo(phasorSlider, 1.8);
    await expect(async () => {
      const currentTime = await page.evaluate(() => wwPlaybackState().currentTime);
      expect(Math.abs(currentTime - 1.8)).toBeLessThan(0.01);
    }).toPass({ timeout: 5000 });

    await page.locator("#mainNavWaveformBtn").click();
    await expect(canvas).toBeVisible();
    await expect(async () => {
      expect(Number(await waveformSlider.inputValue())).toBeCloseTo(1.8, 1);
    }).toPass({ timeout: 5000 });
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
    await expect(async () => {
      const text = await page.locator("#wwPhasorValuesList").innerText();
      expect(text).toMatch(/100\.0\s*V/);
    }).toPass({ timeout: 5000 });

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

    // 5. Selecting BRAVO1 loads its own six roles correctly.
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
      await page.locator("#wwPhasorContextSelect").selectOption(contextId);
      await expect(page.locator("#wwPhasorSvg polygon")).toHaveCount(6);
    }
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
