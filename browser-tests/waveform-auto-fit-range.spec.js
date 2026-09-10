// Real-browser regression for the waveform time-axis auto-fit fix (owner
// UAT 2026-09-10, hardened same-day to preserve DEC-037). See
// docs/development/BROWSER_SMOKE_TEST.md for the general infrastructure
// this reuses (fresh backend + frontend per run, no Docker, local code
// only).
//
// Reproduces the reported symptom end to end: a long event establishes a
// wide default time extent; hiding it (without removing it from the
// workspace) must shrink the extent to whatever remains displayed; showing
// it again must widen the extent back out -- proving
// wwTimeExtentContributingSourceIds()/wwDeriveWorkspaceBounds()'s own union
// min/max (frontend/index.html) actually drives the rendered Plotly
// x-axis, not merely the underlying math. Only the SPAN (range[1]-range[0])
// is asserted, not absolute values -- span is invariant to the automatic
// timestamp-based placement offset between the two fixture sources, and is
// exactly the quantity the "5-minute range" vs "1-minute range" scenario in
// the task's own examples is about. The FIRST scenario below additionally
// proves DEC-037/Phase 4A-UAT10's own original "zero-channel source-open
// can still establish bounds" case survives this fix -- opening a source
// with no channel displayed yet has no Plotly chart at all (a Time Group
// Canvas only exists once a group backs a DISPLAYED channel), so that
// scenario reads ww.workspaceBounds directly instead of a chart's xaxis.
//
// Fixtures (backend/tests/fixtures/comtrade/range_event_long.*/
// range_event_short.*, deliberately synthetic and short -- see the task's
// own "shorter durations that preserve the same ratio/behavior" allowance):
// long = 5000 Hz/200 samples (0 -> 0.0398s), short = 5000 Hz/40 samples,
// starting 0.036s after long's own start (0.036 -> 0.0438s in the shared
// group coordinate once automatically placed) -- deliberately NON-
// CONTAINED (short's own end extends ~4ms past long's own end), so a
// correct union-min/max default extent (~0.0438s) is measurably different
// from "the long source's own duration alone" (~0.0398s). Both sources
// share one Time Group (their raw recorded absolute intervals overlap).

const { test, expect } = require("@playwright/test");
const path = require("path");

const FIXTURES = path.join(__dirname, "..", "backend", "tests", "fixtures", "comtrade");

const LONG_SPAN = 0.0398; // (200 - 1) / 5000
const SHORT_SPAN = 0.0078; // (40 - 1) / 5000
const UNION_SPAN = 0.0438; // 0.036 + SHORT_SPAN (non-contained: extends past LONG_SPAN)
const TOLERANCE = 0.0008;

async function uploadFixture(page, stem) {
  // The upload button only exists on the Recordings page -- navigate
  // back to it first if a prior step already moved on to Waveform (the
  // owner's own real multi-upload workflow: open source A, THEN upload
  // source B from Recordings, then return to A's already-open workspace
  // to toggle B's channel directly from the sidebar).
  const onRecordingsPage = await page.evaluate(() => {
    const el = document.getElementById("pageRecordings");
    return !!el && !el.hidden;
  });
  if (!onRecordingsPage) await page.locator("#mainNavRecordingsBtn").click();
  await page.locator("#recordingsUploadBtn, #recordingsEmptyUploadBtn").first().click();
  await expect(page.locator("#uploadModalOverlay")).toBeVisible();
  await page.locator("#uploadModalFile_0").setInputFiles(path.join(FIXTURES, `${stem}.cfg`));
  await page.locator("#uploadModalFile_1").setInputFiles(path.join(FIXTURES, `${stem}.dat`));
  await page.locator("#uploadModalSubmitBtn").click();
  await page.locator("#uploadModalOverlay").waitFor({ state: "hidden" });

  // Newly uploaded sources are APPENDED to the list, not prepended --
  // .last() (not .first(), which would keep re-resolving to the very
  // first source ever uploaded once a second source exists) is the
  // just-uploaded row.
  const row = page.locator("#recordingsTableBody tr[data-source-id]").last();
  await expect(row).toBeVisible();
  const sourceId = await row.getAttribute("data-source-id");
  expect(sourceId).toBeTruthy();
  return sourceId;
}

// `#recordingsTableBody` (the Recordings page's own table, `#pageRecordings`)
// and `#channelGroups` (the Workspace Sidebar's tree, `#channelsPanel`) are
// two different surfaces, but wwRenderWorkspaceRecordings() reconciles
// EVERY currently-uploaded source into the sidebar tree as soon as the
// sources list changes -- regardless of whether the Waveform page is
// currently the active one. So a `<details class="source-recording"
// data-source-id>` for a source can already exist while `#pageRecordings`
// is still the visible page (`#workspaceRow` stays `hidden` until the
// Waveform page is actually activated) -- the right signal for "do I need
// to navigate via the Recordings-page row" is `#workspaceRow`'s own
// hidden state, never merely whether the `<details>` node exists.
async function openSourceInWorkspace(page, sourceId) {
  const onWaveformPage = await page.evaluate(() => {
    const row = document.getElementById("workspaceRow");
    return !!row && !row.hidden;
  });
  if (!onWaveformPage) {
    // Not on the Waveform page yet -- only the Recordings-page row
    // ("Open ... for analysis") navigates there.
    await page.locator(`#recordingsTableBody tr[data-source-id="${sourceId}"]`).click();
    await expect(page.locator("#workspaceRow")).toBeVisible();
  }
  const details = page.locator(`details.source-recording[data-source-id="${sourceId}"]`);
  await expect(details).toBeVisible();
  const isOpen = await details.evaluate((el) => el.open);
  if (!isOpen) await details.locator("summary").first().click();
}

async function toggleVaChannel(page, sourceId) {
  await openSourceInWorkspace(page, sourceId);
  const row = page.locator(
    `#channelGroups tr.channel-row--toggle[data-channel-kind="analog"][data-source-id="${sourceId}"][data-channel-name="VA"]`
  );
  await expect(row).toBeVisible();
  const wasDisplayed = (await row.getAttribute("aria-pressed")) === "true";
  await row.click();
  await expect(row).toHaveAttribute("aria-pressed", wasDisplayed ? "false" : "true");
}

// DEC-037/Phase 4A-UAT10 preservation check (owner hardening pass,
// 2026-09-10): a source that has been opened into the workspace but has
// never had a channel displayed yet has no Time Group Canvas at all (one
// only exists once a group backs a DISPLAYED channel), so there is no
// Plotly chart to read a span from -- ww.workspaceBounds itself (a
// top-level `const` in frontend/index.html's own classic <script>, so a
// bare identifier reference from page.evaluate() sees it, same as
// `shell`) is the only place this initial extent is observable.
async function readWorkspaceBoundsSpan(page) {
  return page.evaluate(() => {
    if (typeof ww === "undefined" || !ww.workspaceBounds) return null;
    return Math.abs(ww.workspaceBounds.end - ww.workspaceBounds.start);
  });
}

async function waitForXAxisSpan(page, expectedSpan) {
  await page.waitForFunction(
    ({ expectedSpan, tolerance }) => {
      // panel.chartEl (the ".ww-chart" div itself) is what
      // Plotly.newPlot() is called on directly (frontend/index.html) --
      // Plotly attaches `.layout` to THAT element, never a nested child.
      const el = document.querySelector("#wwTimeGroupCanvases .ww-chart");
      if (!el || !el.layout || !el.layout.xaxis || !Array.isArray(el.layout.xaxis.range)) return false;
      const [x0, x1] = el.layout.xaxis.range;
      if (!Number.isFinite(x0) || !Number.isFinite(x1)) return false;
      return Math.abs(Math.abs(x1 - x0) - expectedSpan) <= tolerance;
    },
    { expectedSpan, tolerance: TOLERANCE },
    { timeout: 8000 }
  );
}

test("Waveform auto-fit: default time extent tracks the currently displayed source set", async ({ page }) => {
  const consoleErrors = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(msg.text());
  });
  page.on("pageerror", (err) => consoleErrors.push(`pageerror: ${err.message}`));

  await test.step("Load app", async () => {
    await page.goto("/index.html");
    await expect(page.locator("#pageRecordings")).toBeVisible();
  });

  let longId;
  let shortId;
  await test.step("Upload the long (0.0398s) event only", async () => {
    longId = await uploadFixture(page, "range_event_long");
  });

  await test.step("Open the long event with ZERO channels displayed -> DEC-037's own initial bounds are still established", async () => {
    await openSourceInWorkspace(page, longId);
    // Confirms the precondition this case actually needs: opening a
    // source does not auto-display any channel (Phase 4A-UAT9).
    const anyDisplayed = await page.locator("#channelGroups tr.channel-row--toggle[aria-pressed=\"true\"]").count();
    expect(anyDisplayed).toBe(0);
    await expect.poll(() => readWorkspaceBoundsSpan(page), {
      message: "ww.workspaceBounds should reflect the opened source's own native extent before any channel is picked",
    }).toBeGreaterThan(0);
    const span = await readWorkspaceBoundsSpan(page);
    expect(Math.abs(span - LONG_SPAN)).toBeLessThanOrEqual(TOLERANCE);
  });

  await test.step("Display only the long event's VA -> extent covers the long event alone", async () => {
    await toggleVaChannel(page, longId);
    await expect(page.locator(".ww-chart .plotly").first()).toBeVisible();
    await waitForXAxisSpan(page, LONG_SPAN);
  });

  await test.step("Upload the short (0.0078s, non-contained) event", async () => {
    shortId = await uploadFixture(page, "range_event_short");
    // The short event is now open/participating with zero channels of
    // its own displayed -- DEC-037 says it too may contribute its own
    // extent on its own... but wwTimeExtentContributingSourceIds()'s own
    // rule is "displayed OR never-yet-displayed," so a merely-uploaded,
    // never-displayed short event WOULD widen the union here already.
    // That is correct/expected (not tested further here -- the point of
    // this fixture ordering is only to isolate the single-source zero-
    // channel check above from any second-source interference); the
    // very next step deliberately DISPLAYS short's own channel, which is
    // the scenario this task actually needs proof of.
  });

  await test.step("Also display the short event's VA -> extent expands to the union (non-contained proof)", async () => {
    await toggleVaChannel(page, shortId);
    await waitForXAxisSpan(page, UNION_SPAN);
  });

  await test.step("Hide the long event (toggle its VA back off) -> extent shrinks to the short event alone", async () => {
    await toggleVaChannel(page, longId);
    await waitForXAxisSpan(page, SHORT_SPAN);
  });

  await test.step("Show the long event again -> extent expands back to the union", async () => {
    await toggleVaChannel(page, longId);
    await waitForXAxisSpan(page, UNION_SPAN);
  });

  await test.step("Hide the short event instead -> the long event's own extent remains (never collapses)", async () => {
    await toggleVaChannel(page, shortId);
    await waitForXAxisSpan(page, LONG_SPAN);
  });

  await test.step("Zero unexpected console/page errors", async () => {
    expect(consoleErrors, `Unexpected console/page errors:\n${consoleErrors.join("\n")}`).toEqual([]);
  });
});
