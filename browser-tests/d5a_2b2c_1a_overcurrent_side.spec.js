// D5A-2B2C-1A (DEC-216) -- recorded Overcurrent consumes the measurement side and CT that Recording Details decides:
// Level 1 (the recording) and Level 2 (the Current Measurement Group that owns the phase's current channel). The page has
// no Recording-basis input; its request carries neither a basis nor a CT; it shows the answer read-only with a link to
// Recording Details. Real backend, real frontend; every side/CT change goes through the same API Recording Details uses.
// Supersedes d5a_oc_ct_authority.spec.js (D5A-OC-001), which chose the basis in the page.

const { test, expect } = require("./support/test");
const path = require("path");
const { reuseOrCreateFullBayContext } = require("./support/engineering_context_helpers");
const { syntheticComtrade } = require("./support/synthetic_comtrade");
const { setRecordedSide, setGroupSide } = require("./support/current_side_helpers");

const BACKEND = `http://127.0.0.1:${process.env.PW_BACKEND_PORT || "8000"}`;
const FIXTURES = path.join(__dirname, "..", "backend", "tests", "fixtures", "comtrade");
const STEM = "phasor_smoke_three_phase";                       // declares PRIMARY on every channel; 40 A RMS current
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

async function seedFrom(page, bayName) {
  const row = page.locator("#wwRdRecordingList .ww-rd-recording-item").last();
  await expect(row).toBeVisible();
  const sourceId = await row.getAttribute("data-source-id");
  const workspaceId = await page.evaluate(() => localStorage.getItem("powerwave.workspaceId"));
  const context = await reuseOrCreateFullBayContext(page, workspaceId, sourceId, "ALPHA1", ALPHA_ROLES, bayName);
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

async function seed(page) {
  await uploadFixture(page);
  return seedFrom(page, "Alpha 1");
}

// A synthetic recording whose channels declare the given COMTRADE P/S flag ("P", "S" or "" = undeclared), by role suffix.
async function seedSynthetic(page, sideOf) {
  const channels = [];
  for (const [suffix, phase] of ALPHA_ROLES) {
    const isVoltage = suffix[0] === "V";
    channels.push({ name: `ALPHA1_${suffix}`, phase, unit: isVoltage ? "V" : "A", amplitude: isVoltage ? 100 : 40, frequencyHz: 50, side: sideOf(suffix) });
  }
  const files = syntheticComtrade({ station: "ALPHA", startClock: "10:00:00.000000", rateHz: 5000, durationS: 2.0, channels });
  await page.goto("/index.html");
  await page.locator("#wwRdUploadBtn").first().click();
  await expect(page.locator("#uploadModalOverlay")).toBeVisible();
  await page.locator("#uploadModalFile_0").setInputFiles({ name: "ALPHA_synthetic.cfg", mimeType: "application/octet-stream", buffer: files.cfg });
  await page.locator("#uploadModalFile_1").setInputFiles({ name: "ALPHA_synthetic.dat", mimeType: "application/octet-stream", buffer: files.dat });
  await page.locator("#uploadModalSubmitBtn").click();
  await page.locator("#uploadModalOverlay").waitFor({ state: "hidden" });
  return seedFrom(page, "Alpha 1");
}

// A recording that declares NO Primary/Secondary side at all (the COMTRADE P/S column is empty).
const seedUndeclared = (page) => seedSynthetic(page, () => "");

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
  await page.waitForFunction(() => wwOcRecordedInputState().status === "ready");
}

// After a change in Recording Details, the page re-reads on its next context (re)load; this is that same read.
async function rereadAuthority(page) {
  await page.evaluate(() => wwOcRecordedInputRefresh(true));
  await page.waitForFunction(() => wwOcRecordedInputState().status === "ready");
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
    return r && r.status === "computed"
      ? { measured: r.measured_rms_current, relay: r.relay_secondary_current, basis: r.recording_basis, authority: r.measurement_side_authority }
      : null;
  });
}

test.describe("D5A-2B2C-1A recorded Overcurrent -- side and CT from Recording Details", () => {
  test("a Primary recording uses its group's CT, read-only; the request carries neither a basis nor a CT", async ({ page }) => {
    const s = await seed(page);
    await putCt(page, s, MANUAL_CT);
    const requests = ocRequests(page);
    await openOvercurrent(page, s.contextId);

    await expect(page.locator("#wwOvercurrentBasisSelect")).toHaveCount(0);                          // no basis input
    await expect(block(page)).toBeVisible();
    await expect(block(page).locator("input, select, textarea")).toHaveCount(0);                     // never an editor
    await expect(block(page).locator('[data-oc-value="side"]')).toContainText("Primary");
    await expect(block(page).locator('[data-oc-value="side"]')).toContainText("declared by the recording");
    await expect(block(page).locator('[data-oc-value="ct"]')).toContainText("1200 A / 1 A");
    await expect(block(page).locator('[data-oc-value="ct"]')).toContainText("Manual");
    await expect(block(page).locator('[data-oc-value="ct"]')).toContainText(s.current.display_name);
    await expect(page.locator("#wwOvercurrentCtPrimaryField")).toBeHidden();                         // no duplicate CT editor
    await expect(page.locator("#wwOvercurrentCtSecondaryField")).toBeHidden();
    await expect(page.locator("#wwOvercurrentStatusRow")).toBeHidden();                              // computed

    await expect(async () => {
      expect(requests.length).toBeGreaterThan(0);
      for (const url of requests) {
        expect(url.searchParams.has("recording_basis")).toBe(false);
        expect(url.searchParams.has("ct_primary")).toBe(false);
        expect(url.searchParams.has("ct_secondary")).toBe(false);
      }
    }).toPass({ timeout: 8000 });
    // relay-secondary = recorded primary current x (CT secondary / CT primary), applied once, by the backend.
    await expect(async () => {
      const r = await relayCurrentFromState(page);
      expect(r && r.basis).toBe("primary");
      expect(r.authority).toBe("recording_channel_declared");
      expect(r.relay).toBeCloseTo(r.measured * (1 / 1200), 9);
    }).toPass({ timeout: 8000 });
  });

  test("a Current-group Secondary setting overrides a Primary recording: no CT is applied and the override is disclosed", async ({ page }) => {
    const s = await seed(page);
    await putCt(page, s, MANUAL_CT);
    await setGroupSide(page, s, s.current.id, "secondary");                                           // Level 2
    await openOvercurrent(page, s.contextId);

    await expect(block(page).locator('[data-oc-value="side"]')).toContainText("Secondary");
    await expect(block(page).locator('[data-oc-value="side"]')).toContainText(`set by engineer for ${s.current.display_name}`);
    await expect(block(page).locator('[data-oc-value="ct"]')).toContainText("not applied to a Secondary current");
    await expect(block(page).locator('[data-oc-code="SIDE_OVERRIDES_DECLARATION"]')).toContainText("declares primary");
    await expect(page.locator("#wwOvercurrentStatusRow")).toBeHidden();
    await expect(async () => {
      const r = await relayCurrentFromState(page);
      expect(r && r.basis).toBe("secondary");
      expect(r.authority).toBe("engineer_group_override");
      expect(r.relay).toBe(r.measured);                                  // identical: the CT ratio was not applied
    }).toPass({ timeout: 8000 });
  });

  test("a recording-wide Secondary correction is used when no group overrides it", async ({ page }) => {
    const s = await seed(page);
    await putCt(page, s, MANUAL_CT);
    await setRecordedSide(page, s, "secondary", "the P/S flag of this recorder is wrong");             // Level 1
    await openOvercurrent(page, s.contextId);
    await expect(block(page).locator('[data-oc-value="side"]')).toContainText("set by engineer for the recording");
    await expect(async () => {
      const r = await relayCurrentFromState(page);
      expect(r && r.basis).toBe("secondary");
      expect(r.authority).toBe("engineer_recording_correction");
      expect(r.relay).toBe(r.measured);
    }).toPass({ timeout: 8000 });
  });

  test("a missing CT blocks a Primary recording with the group's name and a Configure button, and keeps Related Waveforms", async ({ page }) => {
    const s = await seed(page);
    await putCt(page, s, CLEAR_CT);
    await openOvercurrent(page, s.contextId);

    await expect(block(page).locator('[data-oc-value="side"]')).toContainText("Primary");
    await expect(block(page).locator('[data-oc-value="ct"]')).toContainText("not configured");
    await expect(block(page).locator('[data-oc-code="invalid_ct_values"]'))
      .toContainText(`CT is not configured for the Current Measurement Group '${s.current.display_name}'`);
    await expect(page.locator("#wwOvercurrentStatusRow")).toContainText("CT is not configured for");
    await expect(page.locator("#wwOvercurrentValuesList")).toHaveText("");                           // no number without a CT
    await expect(block(page).locator("[data-oc-configure]")).toHaveCount(1);

    // Related Waveforms stay available while the calculation is blocked.
    await expect(page.locator("#wwAnalysisRelatedWaveformsCurrentGroup")).toBeVisible();
    await expect(page.locator("#wwAnalysisRelatedWaveformsEmptyState")).toBeHidden();
    await expect(async () => {
      const n = await page.evaluate(() => document.getElementById("wwAnalysisRelatedWaveformsCurrentChart").data.length);
      expect(n).toBeGreaterThan(0);
    }).toPass({ timeout: 8000 });
  });

  test("a missing CT does not matter for a Secondary recording", async ({ page }) => {
    const s = await seed(page);
    await putCt(page, s, CLEAR_CT);
    await setRecordedSide(page, s, "secondary");
    await openOvercurrent(page, s.contextId);

    await expect(page.locator("#wwOvercurrentStatusRow")).toBeHidden();
    await expect(page.locator("#wwOvercurrentValuesList")).toContainText("A secondary");
    // Nothing to fix: the only message is the non-blocking disclosure that this setting overrides the declared side.
    await expect(block(page).locator('[data-oc-code]:not([data-oc-code="SIDE_OVERRIDES_DECLARATION"])')).toHaveCount(0);
    await expect(block(page).locator('[data-oc-value="ct"]')).toContainText("not needed for a Secondary current");
    await expect(block(page).locator(".ww-ctvt-missing")).toHaveCount(0);                              // no critical CT styling
  });

  test("a recording that declares no side is blocked until an engineer defines it; Related Waveforms stay available", async ({ page }) => {
    const s = await seedUndeclared(page);
    await putCt(page, s, MANUAL_CT);
    await openOvercurrent(page, s.contextId);

    await expect(block(page).locator('[data-oc-value="side"]')).toContainText("not defined");
    await expect(block(page).locator('[data-oc-row="ct"]')).toHaveCount(0);                          // no CT claim without a side
    await expect(block(page).locator('[data-oc-code="measurement_side_unresolved"]')).toContainText("not defined by the recording");
    await expect(page.locator("#wwOvercurrentStatusRow")).toContainText("Recording Details");
    await expect(page.locator("#wwOvercurrentValuesList")).toHaveText("");                           // never a guessed number
    await expect(page.locator("#wwOvercurrentSvg circle.ww-oc-operating-point")).toHaveCount(0);
    await expect(page.locator("#wwAnalysisRelatedWaveformsCurrentGroup")).toBeVisible();
    // The magnitude (40 A) and the CT (1200:1) never decide the side.
    expect(await relayCurrentFromState(page)).toBeNull();

    await setRecordedSide(page, s, "primary", "from the relay report");
    await rereadAuthority(page);
    await expect(block(page).locator('[data-oc-value="side"]')).toContainText("set by engineer for the recording");
    await expect(block(page).locator("[data-oc-code]")).toHaveCount(0);
    await expect(async () => {
      const r = await relayCurrentFromState(page);
      expect(r && r.basis).toBe("primary");
      expect(r.relay).toBeCloseTo(r.measured / 1200, 9);
    }).toPass({ timeout: 8000 });
    await expect(page.locator("#wwOvercurrentStatusRow")).toBeHidden();
  });

  test("Configure in Recording Details opens the current group; a CT saved there is used immediately on return", async ({ page }) => {
    const s = await seed(page);
    await putCt(page, s, CLEAR_CT);
    await openOvercurrent(page, s.contextId);
    await expect(block(page).locator('[data-oc-code="invalid_ct_values"]')).toBeVisible();

    await block(page).locator("[data-oc-configure]").click();
    await expect(page.locator("#pageRecordingDetails")).toBeVisible();
    expect(await page.evaluate(() => wwRdState.selectedGroupId)).toBe(s.current.id);

    await putCt(page, s, { update_ct_only: true, ct_primary_a: 600, ct_secondary_a: 1 });                // Edit -> Save in Recording Details
    await page.locator("#mainNavAnalysisBtn").click();
    await expect(page.locator("#wwOvercurrentPanel")).toBeVisible();
    await expect(block(page).locator('[data-oc-value="ct"]')).toContainText("600 A / 1 A", { timeout: 10000 });
    await expect(block(page).locator("[data-oc-code]")).toHaveCount(0);
    await expect(page.locator("#wwOvercurrentStatusRow")).toBeHidden();
    await expect(page.locator("#wwOvercurrentValuesList")).toContainText("A secondary");
    await expect(async () => {
      const r = await relayCurrentFromState(page);
      expect(r && r.relay).toBeCloseTo(r.measured / 600, 9);
    }).toPass({ timeout: 8000 });
  });

  test("a side changed in Recording Details reaches the result on return, with no stale number", async ({ page }) => {
    const s = await seed(page);
    await putCt(page, s, MANUAL_CT);
    await openOvercurrent(page, s.contextId);
    await expect(async () => {
      const r = await relayCurrentFromState(page);
      expect(r && r.basis).toBe("primary");
    }).toPass({ timeout: 8000 });

    await page.locator("#mainNavRecordingDetailsBtn").click();
    await expect(page.locator("#pageRecordingDetails")).toBeVisible();
    await setGroupSide(page, s, s.current.id, "secondary");                                           // changed in Recording Details
    await page.locator("#mainNavAnalysisBtn").click();
    await expect(page.locator("#wwOvercurrentPanel")).toBeVisible();
    await expect(block(page).locator('[data-oc-value="side"]')).toContainText("Secondary", { timeout: 10000 });
    await expect(async () => {
      const r = await relayCurrentFromState(page);
      expect(r && r.basis).toBe("secondary");
      expect(r.relay).toBe(r.measured);
    }).toPass({ timeout: 8000 });
    await expect(page.locator("#wwOvercurrentStatusRow")).toBeHidden();
  });

  test("a direct API client cannot override Recording Details with a legacy basis or CT", async ({ page }) => {
    const s = await seed(page);
    await putCt(page, s, MANUAL_CT);
    const call = async (extra) => (await page.request.get(`${s.base}/engineering-contexts/${s.contextId}/overcurrent`, {
      params: { phase: "A", analysis_time: 1.0, characteristic_id: "iec_standard_inverse", tms: 0.1, pickup_current_secondary: 1.0, ...extra },
    })).json();
    const contradicting = await call({ recording_basis: "secondary" });
    expect(contradicting.status).toBe("needs_configuration");
    expect(contradicting.reason_code).toBe("recording_basis_contradicts_measurement_side");
    expect(contradicting.relay_secondary_current).toBeNull();
    const wrongCt = await call({ recording_basis: "primary", ct_primary: 2000, ct_secondary: 5 });
    expect(wrongCt.reason_code).toBe("request_ct_differs_from_authority");
    expect(wrongCt.relay_secondary_current).toBeNull();
    const authoritative = await call({});
    expect(authoritative.status).toBe("computed");
    expect(authoritative.relay_secondary_current).toBeCloseTo(authoritative.measured_rms_current / 1200, 9);
  });

  test("changing the phase re-reads the authority for that phase's own channel", async ({ page }) => {
    const s = await seed(page);
    await putCt(page, s, MANUAL_CT);
    await openOvercurrent(page, s.contextId);
    const reads = [];
    page.on("request", (r) => { if (r.url().includes("/overcurrent-recorded-input?")) reads.push(new URL(r.url())); });
    await page.locator("#wwOvercurrentPhaseSelect").selectOption("B");
    await expect(async () => expect(reads.some((u) => u.searchParams.get("phase") === "B")).toBe(true)).toPass({ timeout: 8000 });
    await page.waitForFunction(() => wwOcRecordedInputState().status === "ready" && wwOcRecordedInputState().report.phase === "B");
    const channel = await page.evaluate(() => wwOcRecordedInputState().report.channel_ref.channel_name);
    expect(channel).toMatch(/IB$/i);
  });

  test("a workspace reset keeps no authority, report or CT from the previous workspace", async ({ page }) => {
    const s = await seed(page);
    await putCt(page, s, MANUAL_CT);
    await openOvercurrent(page, s.contextId);
    await expect(block(page).locator('[data-oc-value="ct"]')).toContainText("1200 A / 1 A");
    const state = await page.evaluate(() => {
      wwOvercurrentState.settings.ctPrimary = 900; wwOvercurrentState.settings.ctSecondary = 5;      // a Manual-mode CT
      wwOvercurrentResetState();
      const st = wwOcRecordedInputState();
      const s = wwOvercurrentState.settings;
      return { status: st.status, report: st.report, key: st.key, ct: [s.ctPrimary, s.ctSecondary], basis: "recordingBasis" in s };
    });
    expect(state).toEqual({ status: "idle", report: null, key: null, ct: [null, null], basis: false });
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
        return mine === 1 ? report.then((r) => new Promise((resolve) => setTimeout(() => resolve(Object.assign({}, r, { ct: Object.assign({}, r.ct, { primary: 111, secondary: 1, ratio: 111 }) })), 400)))
                          : report;
      };
      wwOvercurrentState.phase = "B";
      const first = wwOcRecordedInputRefresh(true);
      wwOvercurrentState.phase = "C";
      const second = wwOcRecordedInputRefresh(true);
      await Promise.all([first, second]);
      window.wwPhasorFetchJson = real;
      return wwOcRecordedInputState().report.ct.primary;
    });
    expect(winner).toBe(1200);                                                                      // never the stale 111
  });

  test("a calculated current channel is blocked with an explicit not-available-yet limitation, no configure link, and Related Waveforms still work", async ({ page }) => {
    const s = await seed(page);
    const created = await page.request.post(`${s.base}/calculated-channels`, { data: {
      name: "IA_scaled", operation: "multiply_constant", parameters: { constant: 1.0 },
      inputs: [{ kind: "source", source_id: s.sourceId, channel_name: "ALPHA1_IA" }] } });
    expect(created.ok(), await created.text()).toBeTruthy();
    const calc = await created.json();
    const ctx = await page.request.post(`${s.base}/engineering-contexts`, { data: { display_name: "Calculated IA", status: "manual", members: [
      { channel_ref: { kind: "calculated", calculated_channel_id: calc.id }, phase: "A", phase_source: "engineer_confirmed" }] } });
    expect(ctx.ok(), await ctx.text()).toBeTruthy();
    const contextId = (await ctx.json()).id;
    const calculatedBefore = JSON.stringify(await (await page.request.get(`${s.base}/calculated-channels`)).json());

    await page.reload();
    await page.locator("#mainNavAnalysisBtn").click();
    await page.locator("#wwAnalysisTypeOvercurrentBtn").click();
    await expect(page.locator(`#wwOvercurrentContextSelect option[value="${contextId}"]`)).toHaveCount(1);
    await page.locator("#wwOvercurrentContextSelect").selectOption(contextId);
    await page.waitForFunction(() => wwOcRecordedInputState().status === "ready" && wwOcRecordedInputState().report.reason_code === "calculated_channel_side_unavailable");

    await expect(block(page).locator('[data-oc-value="side"]')).toContainText("not available for a calculated channel");
    await expect(block(page).locator('[data-oc-value="side"]')).not.toContainText("not defined");
    await expect(block(page).locator("[data-oc-configure]")).toHaveCount(0);                          // nothing in Recording Details can fix it
    await expect(block(page).locator('[data-oc-row="ct"]')).toHaveCount(0);
    await expect(block(page).locator('[data-oc-code="calculated_channel_side_unavailable"]'))
      .toContainText("Measurement-side support for calculated channels is not available yet");
    await expect(page.locator("#wwOvercurrentStatusRow")).toContainText("not available yet");
    await expect(page.locator("#wwOvercurrentStatusRow")).not.toContainText("Measurement Group");      // never suggests configuring one
    await expect(page.locator("#wwOvercurrentValuesList")).toHaveText("");                            // no number, no guess
    expect(await relayCurrentFromState(page)).toBeNull();

    // Related Waveforms stay functional for the calculated channel.
    await expect(page.locator("#wwAnalysisRelatedWaveformsCurrentGroup")).toBeVisible();
    await expect(async () => {
      const n = await page.evaluate(() => document.getElementById("wwAnalysisRelatedWaveformsCurrentChart").data.length);
      expect(n).toBeGreaterThan(0);
    }).toPass({ timeout: 8000 });
    // The valid calculated channel was neither deleted nor modified.
    expect(JSON.stringify(await (await page.request.get(`${s.base}/calculated-channels`)).json())).toBe(calculatedBefore);
  });

  test("a Current group with mixed P/S declarations blocks until the engineer resolves it; the declarations and the discrepancy stay visible", async ({ page }) => {
    const s = await seedSynthetic(page, (suffix) => (suffix === "IB" ? "S" : "P"));             // IA Primary, IB Secondary, IC Primary
    await putCt(page, s, MANUAL_CT);
    const groups = await (await page.request.get(`${s.base}/sources/${s.sourceId}/measurement-groups`)).json();
    const group = groups.find((g) => g.id === s.current.id);
    expect(group.channel_refs.map((r) => r.channel_name).sort()).toEqual(["ALPHA1_IA", "ALPHA1_IB", "ALPHA1_IC"]);   // one mixed group
    const declared = async () => (await (await page.request.get(`${s.base}/sources/${s.sourceId}/channels`)).json()).analog_channels
      .filter((c) => /_I[ABC]$/.test(c.name)).map((c) => `${c.name}:${c.measurement_side}`).sort();
    const originalDeclarations = ["ALPHA1_IA:primary", "ALPHA1_IB:secondary", "ALPHA1_IC:primary"];
    expect(await declared()).toEqual(originalDeclarations);

    await openOvercurrent(page, s.contextId);
    await expect(block(page).locator('[data-oc-code="measurement_side_conflict"]')).toContainText(`'${s.current.display_name}'`);
    await expect(page.locator("#wwOvercurrentStatusRow")).toContainText("declare different measurement sides");
    await expect(page.locator("#wwOvercurrentValuesList")).toHaveText("");                            // blocked, never a guess
    await expect(block(page).locator("[data-oc-configure]")).toHaveCount(1);
    await expect(page.locator("#wwAnalysisRelatedWaveformsCurrentGroup")).toBeVisible();

    // The link opens the group so the engineer can resolve it; the correction is made there (Level 2).
    await block(page).locator("[data-oc-configure]").click();
    await expect(page.locator("#pageRecordingDetails")).toBeVisible();
    expect(await page.evaluate(() => wwRdState.selectedGroupId)).toBe(s.current.id);
    await setGroupSide(page, s, s.current.id, "primary");
    await page.locator("#mainNavAnalysisBtn").click();
    await expect(page.locator("#wwOvercurrentPanel")).toBeVisible();
    await expect(block(page).locator('[data-oc-value="side"]')).toContainText("set by engineer", { timeout: 10000 });
    await expect(block(page).locator('[data-oc-code="measurement_side_conflict"]')).toHaveCount(0);
    await expect(async () => {
      const r = await relayCurrentFromState(page);
      expect(r && r.basis).toBe("primary");
      expect(r.authority).toBe("engineer_group_override");
      expect(r.relay).toBeCloseTo(r.measured / 1200, 9);
    }).toPass({ timeout: 8000 });

    // Phase B is the channel whose own declaration (Secondary) the correction overrides: the discrepancy is disclosed ...
    await page.locator("#wwOvercurrentPhaseSelect").selectOption("B");
    await expect(block(page).locator('[data-oc-code="SIDE_OVERRIDES_DECLARATION"]')).toContainText("declares secondary", { timeout: 10000 });
    // ... and the recording's original P/S declarations were never rewritten.
    expect(await declared()).toEqual(originalDeclarations);
  });

  test("Manual mode keeps its own CT inputs and hides the recorded block; the typed Manual CT is never used for the recording", async ({ page }) => {
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

    // Back to Recording: the typed Manual CT is never used for the recording; the group's 1200:1 is.
    await page.locator("#wwOvercurrentInputSourceRecordingBtn").click();
    await expect(block(page)).toBeVisible();
    await expect(page.locator("#wwOvercurrentCtPrimaryField")).toBeHidden();
    await expect(async () => {
      const r = await relayCurrentFromState(page);
      expect(r && r.basis).toBe("primary");
      expect(r.relay).toBeCloseTo(r.measured / 1200, 9);
    }).toPass({ timeout: 8000 });
  });
});
