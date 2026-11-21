// D5A-OC-001 -- recorded Overcurrent takes its CT only from the Recording Details Measurement Group that owns
// the phase's own current channel (read-only block + "Configure in Recording Details"), never from a
// panel-local input. Real backend, real frontend, the same bay fixture the other D5A suites use.

const { test, expect } = require("./support/test");
const path = require("path");
const { reuseOrCreateFullBayContext } = require("./support/engineering_context_helpers");

const BACKEND = `http://127.0.0.1:${process.env.PW_BACKEND_PORT || "8000"}`;
const FIXTURES = path.join(__dirname, "..", "backend", "tests", "fixtures", "comtrade");
const STEM = "phasor_smoke_three_phase";
const ALPHA_ROLES = [["VA", "A"], ["VB", "B"], ["VC", "C"], ["IA", "A"], ["IB", "B"], ["IC", "C"]];

async function uploadFixture(page) {
  await page.goto("/index.html");
  await page.locator("#wwRdUploadBtn").first().click();
  await expect(page.locator("#uploadModalOverlay")).toBeVisible();
  await page.locator("#uploadModalFile_0").setInputFiles(path.join(FIXTURES, `${STEM}.cfg`));
  await page.locator("#uploadModalFile_1").setInputFiles(path.join(FIXTURES, `${STEM}.dat`));
  await page.locator("#uploadModalSubmitBtn").click();
  await page.locator("#uploadModalOverlay").waitFor({ state: "hidden" });
}

async function seed(page) {
  await uploadFixture(page);
  const row = page.locator("#wwRdRecordingList .ww-rd-recording-item").last();
  await expect(row).toBeVisible();
  const sourceId = await row.getAttribute("data-source-id");
  const workspaceId = await page.evaluate(() => localStorage.getItem("powerwave.workspaceId"));
  const context = await reuseOrCreateFullBayContext(page, workspaceId, sourceId, "ALPHA1", ALPHA_ROLES, "Alpha 1");
  const base = `${BACKEND}/api/v1/workspaces/${encodeURIComponent(workspaceId)}`;
  let groups = await (await page.request.get(`${base}/sources/${sourceId}/measurement-groups`)).json();
  if (!groups.some((g) => g.kind === "current")) {
    await page.request.post(`${base}/sources/${sourceId}/measurement-groups/suggest`, { data: {} });
    groups = await (await page.request.get(`${base}/sources/${sourceId}/measurement-groups`)).json();
  }
  const current = groups.find((g) => g.kind === "current");
  expect(current).toBeTruthy();
  return { workspaceId, sourceId, contextId: context.id, base, current };
}

async function putCt(page, s, body) {
  const r = await page.request.put(`${s.base}/sources/${s.sourceId}/measurement-groups/${s.current.id}/current-config`, { data: body });
  expect(r.ok(), await r.text()).toBeTruthy();
}
const MANUAL_CT = { update_ct_only: true, ct_primary_a: 1200, ct_secondary_a: 1 };
const CLEAR_CT = { update_ct_only: true, clear_ct: true };

async function openOvercurrent(page, contextId) {
  await page.locator("#mainNavAnalysisBtn").click();
  await expect(page.locator("#pageAnalysis")).toBeVisible();
  await page.locator("#wwAnalysisTypeOvercurrentBtn").click();
  await expect(page.locator("#wwOvercurrentPanel")).toBeVisible();
  await expect(page.locator(`#wwOvercurrentContextSelect option[value="${contextId}"]`)).toHaveCount(1);
  if ((await page.locator("#wwOvercurrentContextSelect").inputValue()) !== contextId) {
    await page.locator("#wwOvercurrentContextSelect").selectOption(contextId);
  }
  await page.waitForFunction(() => wwCtVtStateOf(wwCtVtPanel("overcurrent")).status === "ready");
}

// The recording's side declarations, as the API reports them (the fixture itself declares primary).
async function declareCurrentSide(page, side) {
  await page.route("**/protection-instrument-context?*", async (route) => {
    try {
      const response = await route.fetch();
      const body = await response.json();
      const q = body.current;
      if (side === "unknown") Object.assign(q, { declared_basis: null, side_status: "unknown", side: "unknown" });
      else Object.assign(q, { declared_basis: side, side_status: "recording_declared", side });
      await route.fulfill({ response, json: body });
    } catch (error) { /* page closed mid-fetch */ }
  });
}

const block = (page) => page.locator("#wwOvercurrentCtVtAuthority");
const ocRequests = (page) => {
  const urls = [];
  page.on("request", (r) => { if (/\/overcurrent\?/.test(r.url())) urls.push(new URL(r.url())); });
  return urls;
};

async function relayCurrentFromState(page) {
  return page.evaluate(() => {
    const r = wwOvercurrentState.latestResult;
    return r && r.status === "computed" ? { measured: r.measured_rms_current, relay: r.relay_secondary_current, basis: r.recording_basis } : null;
  });
}

test.describe("D5A-OC-001 authoritative CT -- recorded Overcurrent", () => {
  test("a primary recording uses the Measurement Group's CT, read-only, and converts exactly once", async ({ page }) => {
    const s = await seed(page);
    await putCt(page, s, MANUAL_CT);
    const requests = ocRequests(page);
    await openOvercurrent(page, s.contextId);

    // The fixture declares primary, so the Recording current basis is pre-selected, never assumed.
    await expect(page.locator("#wwOvercurrentBasisSelect")).toHaveValue("primary");
    await expect(block(page)).toBeVisible();
    await expect(block(page)).toContainText("CT from Recording Details");
    await expect(block(page).locator("input, select, textarea")).toHaveCount(0);                  // never an editor
    await expect(block(page).locator('[data-ctvt-value="current"]')).toContainText("1200 A / 1 A");
    await expect(block(page).locator('[data-ctvt-value="current"]')).toContainText("Manual");
    await expect(block(page).locator('[data-ctvt-value="current"]')).toContainText(s.current.display_name);
    await expect(block(page).locator('[data-ctvt-value="voltage"]')).toHaveCount(0);               // current-only
    await expect(page.locator("#wwOvercurrentCtPrimaryField")).toBeHidden();                       // no duplicate CT editor
    await expect(page.locator("#wwOvercurrentCtSecondaryField")).toBeHidden();
    await expect(page.locator("#wwOvercurrentStatusRow")).toBeHidden();                            // computed

    await expect(async () => {
      const last = requests[requests.length - 1];
      expect(last).toBeTruthy();
      expect(last.searchParams.get("recording_basis")).toBe("primary");
      expect(last.searchParams.get("ct_primary")).toBe("1200");
      expect(last.searchParams.get("ct_secondary")).toBe("1");
    }).toPass({ timeout: 8000 });
    // relay-secondary = recorded primary current x (CT secondary / CT primary), applied once.
    await expect(async () => {
      const r = await relayCurrentFromState(page);
      expect(r && r.basis).toBe("primary");
      expect(r.relay).toBeCloseTo(r.measured * (1 / 1200), 9);
    }).toPass({ timeout: 8000 });
  });

  test("a secondary recording is never converted again, even though a valid CT is configured", async ({ page }) => {
    const s = await seed(page);
    await putCt(page, s, MANUAL_CT);
    await declareCurrentSide(page, "secondary");
    const requests = ocRequests(page);
    await openOvercurrent(page, s.contextId);

    await expect(page.locator("#wwOvercurrentBasisSelect")).toHaveValue("secondary");
    await expect(block(page).locator('[data-ctvt-value="current"]')).toContainText("1200 A / 1 A");
    await expect(page.locator("#wwOvercurrentStatusRow")).toBeHidden();
    await expect(async () => {
      const last = requests[requests.length - 1];
      expect(last.searchParams.get("recording_basis")).toBe("secondary");
      expect(last.searchParams.has("ct_primary")).toBe(false);
      expect(last.searchParams.has("ct_secondary")).toBe(false);
    }).toPass({ timeout: 8000 });
    await expect(async () => {
      const r = await relayCurrentFromState(page);
      expect(r && r.basis).toBe("secondary");
      expect(r.relay).toBe(r.measured);                                // identical: the CT ratio was not applied
    }).toPass({ timeout: 8000 });
  });

  test("a missing CT blocks a primary recording with the group's name, a Configure button and keeps Related Waveforms", async ({ page }) => {
    const s = await seed(page);
    await putCt(page, s, CLEAR_CT);
    await openOvercurrent(page, s.contextId);

    await expect(page.locator("#wwOvercurrentBasisSelect")).toHaveValue("primary");
    await expect(block(page).locator('[data-ctvt-value="current"]')).toContainText("not configured");
    await expect(block(page).locator('[data-ctvt-code="CT_AUTHORITY_MISSING"]'))
      .toContainText(`CT is not configured for '${s.current.display_name}'`);
    await expect(page.locator("#wwOvercurrentStatusRow")).toContainText("CT is not configured for");
    await expect(page.locator("#wwOvercurrentStatusRow")).not.toContainText("CT primary and CT secondary current must both be");
    await expect(page.locator("#wwOvercurrentValuesList")).toHaveText("");                         // no number without a CT
    await expect(block(page).locator("[data-ctvt-configure]")).toHaveCount(1);

    // Related Waveforms stay available while the calculation is blocked.
    await expect(page.locator("#wwAnalysisRelatedWaveformsCurrentGroup")).toBeVisible();
    await expect(page.locator("#wwAnalysisRelatedWaveformsEmptyState")).toBeHidden();
    await expect(async () => {
      const n = await page.evaluate(() => document.getElementById("wwAnalysisRelatedWaveformsCurrentChart").data.length);
      expect(n).toBeGreaterThan(0);
    }).toPass({ timeout: 8000 });
  });

  test("a missing CT does not matter for a secondary recording", async ({ page }) => {
    const s = await seed(page);
    await putCt(page, s, CLEAR_CT);
    await declareCurrentSide(page, "secondary");
    await openOvercurrent(page, s.contextId);

    await expect(page.locator("#wwOvercurrentBasisSelect")).toHaveValue("secondary");
    await expect(page.locator("#wwOvercurrentStatusRow")).toBeHidden();
    await expect(page.locator("#wwOvercurrentValuesList")).toContainText("A secondary");
    await expect(block(page).locator("[data-ctvt-code]")).toHaveCount(0);                          // nothing to fix
    await expect(block(page).locator('[data-ctvt-value="current"]')).toContainText("not needed for a secondary recording");
  });

  test("Configure in Recording Details opens the current group; a CT saved there is used immediately on return", async ({ page }) => {
    const s = await seed(page);
    await putCt(page, s, CLEAR_CT);
    await openOvercurrent(page, s.contextId);
    await expect(block(page).locator('[data-ctvt-code="CT_AUTHORITY_MISSING"]')).toBeVisible();

    await block(page).locator('[data-ctvt-configure="current"]').click();
    await expect(page.locator("#pageRecordingDetails")).toBeVisible();
    expect(await page.evaluate(() => wwRdState.selectedGroupId)).toBe(s.current.id);

    await putCt(page, s, { update_ct_only: true, ct_primary_a: 600, ct_secondary_a: 1 });                // Edit -> Save in Recording Details
    const request = page.waitForRequest((r) => /\/overcurrent\?/.test(r.url()) && r.url().includes("ct_primary=600"));
    await page.locator("#mainNavAnalysisBtn").click();
    await expect(page.locator("#wwOvercurrentPanel")).toBeVisible();
    await expect(block(page).locator('[data-ctvt-value="current"]')).toContainText("600 A / 1 A", { timeout: 10000 });
    await expect(block(page).locator("[data-ctvt-code]")).toHaveCount(0);
    expect(new URL((await request).url()).searchParams.get("ct_secondary")).toBe("1");
    await expect(page.locator("#wwOvercurrentStatusRow")).toBeHidden();
    await expect(page.locator("#wwOvercurrentValuesList")).toContainText("A secondary");
  });

  test("a recording basis that contradicts the declared side is rejected, never converted", async ({ page }) => {
    const s = await seed(page);
    await putCt(page, s, MANUAL_CT);
    await declareCurrentSide(page, "secondary");
    await openOvercurrent(page, s.contextId);
    await expect(page.locator("#wwOvercurrentBasisSelect")).toHaveValue("secondary");

    const requests = ocRequests(page);
    await page.locator("#wwOvercurrentBasisSelect").selectOption("primary");
    const reject = block(page).locator('[data-ctvt-code="RECORDING_BASIS_CONTRADICTS_CURRENT"]');
    await expect(reject).toContainText("declares the current as secondary");
    await expect(page.locator("#wwOvercurrentStatusRow")).toContainText("No result is shown until the Recording basis matches");
    await expect(page.locator("#wwOvercurrentValuesList")).toHaveText("");
    await expect(page.locator("#wwOvercurrentSvg circle.ww-oc-operating-point")).toHaveCount(0);   // no operating point either
    // No CT is ever attached to a request the plan has rejected.
    expect(requests.filter((u) => u.searchParams.has("ct_primary"))).toEqual([]);
    // Related Waveforms stay available, and choosing the declared side restores the result.
    await expect(page.locator("#wwAnalysisRelatedWaveformsCurrentGroup")).toBeVisible();
    await page.locator("#wwOvercurrentBasisSelect").selectOption("secondary");
    await expect(page.locator("#wwOvercurrentStatusRow")).toBeHidden();
    await expect(page.locator("#wwOvercurrentValuesList")).toContainText("A secondary");
  });

  test("an undeclared side is chosen explicitly by the engineer and stays marked unverified", async ({ page }) => {
    const s = await seed(page);
    await putCt(page, s, MANUAL_CT);
    await declareCurrentSide(page, "unknown");
    await openOvercurrent(page, s.contextId);
    await expect(page.locator("#wwOvercurrentBasisSelect")).toHaveValue("secondary");                // never inferred from the CT
    await expect(block(page).locator("[data-ctvt-code]")).toHaveCount(0);

    const request = page.waitForRequest((r) => /\/overcurrent\?/.test(r.url()) && r.url().includes("ct_primary=1200"));
    await page.locator("#wwOvercurrentBasisSelect").selectOption("primary");
    const url = new URL((await request).url());
    expect(url.searchParams.get("recording_basis")).toBe("primary");
    await expect(block(page).locator('[data-ctvt-code="BASIS_UNVERIFIED"]')).toContainText("unverified");
  });

  test("changing the phase re-reads the authority for that phase's own channel", async ({ page }) => {
    const s = await seed(page);
    await putCt(page, s, MANUAL_CT);
    await openOvercurrent(page, s.contextId);
    const reads = [];
    page.on("request", (r) => { if (r.url().includes("/protection-instrument-context?")) reads.push(new URL(r.url())); });
    await page.locator("#wwOvercurrentPhaseSelect").selectOption("B");
    await expect(async () => expect(reads.some((u) => u.searchParams.get("phase") === "B" && u.searchParams.get("analysis") === "overcurrent")).toBe(true))
      .toPass({ timeout: 8000 });
    await page.waitForFunction(() => wwCtVtStateOf(wwCtVtPanel("overcurrent")).status === "ready");
    const channels = await page.evaluate(() => wwCtVtStateOf(wwCtVtPanel("overcurrent")).report.channels.map((c) => c.channel.channel_name));
    expect(channels).toHaveLength(1);
    expect(channels[0]).toMatch(/IB$/i);
  });

  test("a workspace reset keeps no CT, report or basis choice from the previous workspace", async ({ page }) => {
    const s = await seed(page);
    await putCt(page, s, MANUAL_CT);
    await openOvercurrent(page, s.contextId);
    await page.locator("#wwOvercurrentBasisSelect").selectOption("primary");
    await expect(block(page).locator('[data-ctvt-value="current"]')).toContainText("1200 A / 1 A");
    const state = await page.evaluate(() => {
      wwOvercurrentState.settings.ctPrimary = 900; wwOvercurrentState.settings.ctSecondary = 5;      // a Manual-mode CT
      wwOvercurrentResetState();
      const st = wwCtVtStateOf(wwCtVtPanel("overcurrent"));
      const s = wwOvercurrentState.settings;
      return { status: st.status, report: st.report, key: st.key, basis: s.recordingBasis, explicit: s.recordingBasisExplicit, ct: [s.ctPrimary, s.ctSecondary] };
    });
    expect(state).toEqual({ status: "idle", report: null, key: null, basis: "secondary", explicit: false, ct: [null, null] });
    await expect(block(page)).toBeHidden();
    await expect(page.locator("#wwOvercurrentCtPrimaryInput")).toHaveValue("");
  });

  test("a response for a previous selection can never overwrite a newer one", async ({ page }) => {
    const s = await seed(page);
    await putCt(page, s, MANUAL_CT);
    await openOvercurrent(page, s.contextId);
    const winner = await page.evaluate(async () => {
      // Two reads in flight; the older one resolves LAST and must be discarded.
      const real = window.wwPhasorFetchJson;
      let n = 0;
      window.wwPhasorFetchJson = (url) => {
        const mine = ++n;
        const report = real(url);
        return mine === 1 ? report.then((r) => new Promise((resolve) => setTimeout(() => resolve(Object.assign({}, r, { current: Object.assign({}, r.current, { primary: 111, secondary: 1, ratio: 111 }) })), 400)))
                          : report;
      };
      wwOvercurrentState.phase = "B";
      const first = wwCtVtRefresh("overcurrent", true);
      wwOvercurrentState.phase = "C";
      const second = wwCtVtRefresh("overcurrent", true);
      await Promise.all([first, second]);
      window.wwPhasorFetchJson = real;
      return wwCtVtStateOf(wwCtVtPanel("overcurrent")).report.current.primary;
    });
    expect(winner).toBe(1200);                                                                      // never the stale 111
  });

  test("Manual mode keeps its own CT inputs and hides the recorded CT block", async ({ page }) => {
    const s = await seed(page);
    await putCt(page, s, MANUAL_CT);
    await openOvercurrent(page, s.contextId);
    await expect(block(page)).toBeVisible();
    await page.locator("#wwOvercurrentInputSourceManualBtn").click();
    await expect(block(page)).toBeHidden();
    await expect(page.locator("#wwOvercurrentCtPrimaryField")).toBeVisible();                       // Manual default basis is Primary
    await expect(page.locator("#wwOvercurrentCtSecondaryField")).toBeVisible();
    await page.locator("#wwOvercurrentCtPrimaryInput").fill("1000");
    await page.locator("#wwOvercurrentCtPrimaryInput").dispatchEvent("change");
    await page.locator("#wwOvercurrentCtSecondaryInput").fill("5");
    await page.locator("#wwOvercurrentCtSecondaryInput").dispatchEvent("change");
    await expect(page.locator("#wwOvercurrentValuesList")).toContainText("A secondary");

    // Back to Recording: the typed Manual CT is never used for the recording.
    const request = page.waitForRequest((r) => /\/overcurrent\?/.test(r.url()) && r.url().includes("recording_basis=primary"));
    await page.locator("#wwOvercurrentInputSourceRecordingBtn").click();
    await expect(block(page)).toBeVisible();
    await expect(page.locator("#wwOvercurrentCtPrimaryField")).toBeHidden();
    const url = new URL((await request).url());
    expect(url.searchParams.get("ct_primary")).toBe("1200");
    expect(url.searchParams.get("ct_secondary")).toBe("1");
  });
});
