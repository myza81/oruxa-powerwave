// D5A-2B2C-1B -- recorded Impedance Locus / Distance Protection take the measurement side of the consumed Voltage and
// Current channels, and the VT/CT of the Measurement Groups that own them, from Recording Details only (DEC-216). The page
// shows them read-only ("Recorded input -- from Recording Details" + "Configure in Recording Details"), has no Recording-basis
// input, and its requests carry only the requested OUTPUT side. Real backend, real frontend, the same bay fixture the other
// Analysis suites use.
//
// Supersedes d5a_ctvt_authority.spec.js, whose tests drove a user-chosen Recording basis and request-carried ratios.

const { test, expect } = require("./support/test");
const path = require("path");
const { reuseOrCreateFullBayContext } = require("./support/engineering_context_helpers");
const { setGroupSide, setRecordedSide } = require("./support/current_side_helpers");

const BACKEND = `http://127.0.0.1:${process.env.PW_BACKEND_PORT || "8000"}`;
const FIXTURES = path.join(__dirname, "..", "backend", "tests", "fixtures", "comtrade");
const STEM = "phasor_smoke_three_phase";
const ALPHA_ROLES = [["VA", "A"], ["VB", "B"], ["VC", "C"], ["IA", "A"], ["IB", "B"], ["IC", "C"]];
const FORBIDDEN_PARAMS = ["recording_basis", "voltage_side", "current_side", "vt_primary", "vt_secondary", "ct_primary", "ct_secondary"];

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
  if (!groups.some((g) => g.kind === "voltage") || !groups.some((g) => g.kind === "current")) {
    await page.request.post(`${base}/sources/${sourceId}/measurement-groups/suggest`, { data: {} });
    groups = await (await page.request.get(`${base}/sources/${sourceId}/measurement-groups`)).json();
  }
  const voltage = groups.find((g) => g.kind === "voltage");
  const current = groups.find((g) => g.kind === "current");
  expect(voltage && current).toBeTruthy();
  return { workspaceId, sourceId, contextId: context.id, base, voltage, current };
}

async function putVt(page, s, body) {
  const r = await page.request.put(`${s.base}/sources/${s.sourceId}/measurement-groups/${s.voltage.id}/voltage-config`, { data: body });
  expect(r.ok(), await r.text()).toBeTruthy();
}
async function putCt(page, s, body) {
  const r = await page.request.put(`${s.base}/sources/${s.sourceId}/measurement-groups/${s.current.id}/current-config`, { data: body });
  expect(r.ok(), await r.text()).toBeTruthy();
}
// Nominal voltage only: Recording Details shows nominal / 110 V, but no VT ratio is stored.
const NOMINAL_ONLY = { nominal_voltage_ll_kv: 132, vt_primary_v: null, vt_secondary_v: null, clear_vt: true };
const MANUAL_VT = { vt_primary_v: 132000, vt_secondary_v: 110 };
const MANUAL_CT = { update_ct_only: true, ct_primary_a: 1200, ct_secondary_a: 1 };

const PANELS = {
  impedance: { name: "Impedance", btn: "#wwAnalysisTypeImpedanceBtn", panel: "#wwImpedancePanel", endpoint: "/impedance?" },
  distance: { name: "Distance", btn: "#wwAnalysisTypeDistanceBtn", panel: "#wwDistancePanel", endpoint: "/distance-protection?" },
};

async function openPanel(page, kind, contextId) {
  const p = PANELS[kind];
  await page.locator("#mainNavAnalysisBtn").click();
  await expect(page.locator("#pageAnalysis")).toBeVisible();
  await page.locator(p.btn).click();
  await expect(page.locator(p.panel)).toBeVisible();
  await expect(page.locator(`#ww${p.name}ContextSelect option[value="${contextId}"]`)).toHaveCount(1);
  if ((await page.locator(`#ww${p.name}ContextSelect`).inputValue()) !== contextId) {
    await page.locator(`#ww${p.name}ContextSelect`).selectOption(contextId);
  }
  await page.waitForFunction((k) => wwCtVtStateOf(wwCtVtPanel(k)).status === "ready", kind);
}

// The `/impedance` / `/distance-protection` request URLs the page sends from now on.
function collectRequests(page, kind) {
  const urls = [];
  page.on("request", (r) => { if (r.url().includes(PANELS[kind].endpoint) || r.url().includes(PANELS[kind].endpoint.replace("?", "-locus?"))) urls.push(r.url()); });
  return urls;
}

for (const kind of ["impedance", "distance"]) {
  const { name } = PANELS[kind];

  test.describe(`D5A-2B2C-1B recorded input from Recording Details -- ${name}`, () => {
    test("no Recording-basis input; the block shows both sides, the VT/CT that convert, and the requests carry only the output side", async ({ page }) => {
      const s = await seed(page);
      await putCt(page, s, MANUAL_CT);
      await putVt(page, s, MANUAL_VT);
      const requests = collectRequests(page, kind);
      await openPanel(page, kind, s.contextId);

      await expect(page.locator(`#ww${name}RecordingBasisSelect`)).toHaveCount(0);
      await expect(page.locator(`#ww${name}RecordingBasisField`)).toHaveCount(0);
      await expect(page.locator(`#ww${name}OutputBasisSelect`)).toBeEnabled();                      // the output side stays editable
      const block = page.locator(`#ww${name}CtVtAuthority`);
      await expect(block).toBeVisible();
      await expect(block.locator("input, select, textarea")).toHaveCount(0);                         // never an editor
      await expect(block.locator('[data-ctvt-value="voltage-side"]')).toContainText("Primary");
      await expect(block.locator('[data-ctvt-value="voltage-side"]')).toContainText("declared by the recording");
      await expect(block.locator('[data-ctvt-value="current-side"]')).toContainText("Primary");
      // The fixture records Primary and the default output side is Secondary: both quantities convert with their own group's ratio.
      await expect(block.locator('[data-ctvt-value="voltage-ratio"]')).toContainText("132 kV / 110 V");
      await expect(block.locator('[data-ctvt-value="voltage-ratio"]')).toContainText(s.voltage.display_name);
      await expect(block.locator('[data-ctvt-value="current-ratio"]')).toContainText("1200 A / 1 A");
      await expect(block.locator('[data-ctvt-value="current-ratio"]')).toContainText(s.current.display_name);
      await expect(block.locator("[data-ctvt-code]")).toHaveCount(0);
      await expect(page.locator(`#ww${name}StatusRow`)).toBeHidden();                                // computed
      await expect(async () => expect(requests.length).toBeGreaterThan(0)).toPass({ timeout: 8000 });
      for (const href of requests) {
        const params = new URL(href).searchParams;
        expect(params.get("impedance_basis")).toBe("secondary");
        for (const forbidden of FORBIDDEN_PARAMS) expect(params.has(forbidden), `${forbidden} in ${href}`).toBe(false);
      }
    });

    test("switching the output side re-reads the authority: a quantity already on the output side needs no ratio and the result still computes", async ({ page }) => {
      const s = await seed(page);
      await putCt(page, s, MANUAL_CT);
      await putVt(page, s, MANUAL_VT);
      await openPanel(page, kind, s.contextId);
      const block = page.locator(`#ww${name}CtVtAuthority`);
      await expect(block.locator('[data-ctvt-value="voltage-ratio"]')).toContainText("132 kV / 110 V");
      const request = page.waitForRequest((r) => r.url().includes(PANELS[kind].endpoint) && r.url().includes("impedance_basis=primary"));
      await page.locator(`#ww${name}OutputBasisSelect`).selectOption("primary");
      await request;
      await expect(block.locator('[data-ctvt-value="voltage-ratio"]')).toContainText("not needed", { timeout: 10000 });
      await expect(block.locator('[data-ctvt-value="voltage-ratio"]')).toContainText("voltage is already Primary");
      await expect(block.locator('[data-ctvt-value="current-ratio"]')).toContainText("not needed");
      await expect(page.locator(`#ww${name}StatusRow`)).toBeHidden();
    });

    test("a nominal-only VT is a valid auto-derived VT: shown normally, no warning, the calculation runs", async ({ page }) => {
      const s = await seed(page);
      await putCt(page, s, MANUAL_CT);
      await putVt(page, s, NOMINAL_ONLY);                   // nominal 132 kV, no stored VT
      await openPanel(page, kind, s.contextId);

      const block = page.locator(`#ww${name}CtVtAuthority`);
      await expect(block.locator('[data-ctvt-value="voltage-ratio"]')).toContainText("132 kV / 110 V");
      await expect(block.locator('[data-ctvt-value="voltage-ratio"]')).toContainText("Auto-derived");
      await expect(block.locator('[data-ctvt-value="current-ratio"]')).toContainText("1200 A / 1 A");
      await expect(block.locator("[data-ctvt-code]")).toHaveCount(0);                      // nothing to confirm or fix
      for (const word of ["display-only", "assumed", "provisional", "unverified"]) await expect(block).not.toContainText(word);
      await expect(page.locator(`#ww${name}StatusRow`)).toBeHidden();                       // computed
    });

    test("a missing CT blocks with the specific message, a Configure button and keeps Related Waveforms", async ({ page }) => {
      const s = await seed(page);
      await putVt(page, s, MANUAL_VT);                      // CT is never derived: it stays unconfigured
      await openPanel(page, kind, s.contextId);

      const block = page.locator(`#ww${name}CtVtAuthority`);
      await expect(block.locator('[data-ctvt-value="current-ratio"]')).toContainText("not configured");
      await expect(block.locator('[data-ctvt-code="ct_authority_unavailable"]')).toContainText(`CT is not configured for '${s.current.display_name}'`);
      await expect(page.locator(`#ww${name}StatusRow`)).toContainText("CT is not configured for");
      await expect(page.locator(`#ww${name}StatusRow`)).toContainText("Recording Details");
      await expect(block.locator("[data-ctvt-configure]")).toHaveCount(2);                   // voltage group and current group

      // No number is shown, and Related Waveforms stay available while the calculation is blocked.
      await expect(page.locator(`#ww${name}ValuesList`)).toBeEmpty();
      await expect(page.locator("#wwAnalysisRelatedWaveformsVoltageGroup")).toBeVisible();
      await expect(page.locator("#wwAnalysisRelatedWaveformsEmptyState")).toBeHidden();
      await expect(async () => {
        const n = await page.evaluate(() => document.getElementById("wwAnalysisRelatedWaveformsVoltageChart").data.length);
        expect(n).toBeGreaterThan(0);
      }).toPass({ timeout: 8000 });
    });

    test("Configure in Recording Details opens the owning group; a saved manual VT then takes precedence over the auto-derived one", async ({ page }) => {
      const s = await seed(page);
      await putCt(page, s, MANUAL_CT);
      await putVt(page, s, NOMINAL_ONLY);
      await openPanel(page, kind, s.contextId);
      const block = page.locator(`#ww${name}CtVtAuthority`);
      await expect(block.locator('[data-ctvt-value="voltage-ratio"]')).toContainText("Auto-derived");
      await block.locator('[data-ctvt-configure="voltage"]').click();
      await expect(page.locator("#pageRecordingDetails")).toBeVisible();
      expect(await page.evaluate(() => wwRdState.selectedGroupId)).toBe(s.voltage.id);

      await putVt(page, s, { vt_primary_v: 66000, vt_secondary_v: 110 });      // the engineer's own VT (Edit -> Save)
      await page.locator("#mainNavAnalysisBtn").click();
      await expect(page.locator(PANELS[kind].panel)).toBeVisible();
      await expect(block.locator('[data-ctvt-value="voltage-ratio"]')).toContainText("66 kV / 110 V", { timeout: 10000 });
      await expect(block.locator('[data-ctvt-value="voltage-ratio"]')).toContainText("Manual");
      await expect(block.locator('[data-ctvt-value="voltage-ratio"]')).not.toContainText("Auto-derived");
      await expect(block.locator("[data-ctvt-code]")).toHaveCount(0);
    });

    test("an engineer's side for a Measurement Group replaces the declaration, is disclosed, and reaches the next computation", async ({ page }) => {
      const s = await seed(page);
      await putCt(page, s, MANUAL_CT);
      await putVt(page, s, MANUAL_VT);
      await setGroupSide(page, s, s.voltage.id, "secondary");               // the recording declares Primary; the engineer says Secondary
      await openPanel(page, kind, s.contextId);
      const block = page.locator(`#ww${name}CtVtAuthority`);
      await expect(block.locator('[data-ctvt-value="voltage-side"]')).toContainText("Secondary");
      await expect(block.locator('[data-ctvt-value="voltage-side"]')).toContainText(`set by engineer for ${s.voltage.display_name}`);
      await expect(block.locator('[data-ctvt-value="voltage-ratio"]')).toContainText("not needed");   // Secondary voltage, Secondary output
      await expect(block.locator('[data-ctvt-value="current-side"]')).toContainText("Primary");       // Voltage and Current are independent
      await expect(block.locator('[data-ctvt-value="current-ratio"]')).toContainText("1200 A / 1 A");
      await expect(block.locator('[data-ctvt-code="SIDE_OVERRIDES_DECLARATION_VOLTAGE"]')).toContainText("declares the voltage as primary");
      await expect(page.locator(`#ww${name}StatusRow`)).toBeHidden();

      // A later change in Recording Details is picked up when the engineer returns to the analyzer.
      await setGroupSide(page, s, s.voltage.id, "primary");
      await page.locator("#mainNavRecordingDetailsBtn").click();
      await expect(page.locator("#pageRecordingDetails")).toBeVisible();
      await page.locator("#mainNavAnalysisBtn").click();
      await expect(page.locator(PANELS[kind].panel)).toBeVisible();
      await expect(block.locator('[data-ctvt-value="voltage-side"]')).toContainText("declared by the recording", { timeout: 10000 });
      await expect(block.locator('[data-ctvt-value="voltage-ratio"]')).toContainText("132 kV / 110 V");
    });

    test("an engineer's recording correction is honoured and the declaration is left untouched", async ({ page }) => {
      const s = await seed(page);
      await putCt(page, s, MANUAL_CT);
      await putVt(page, s, MANUAL_VT);
      await setRecordedSide(page, s, "secondary", "the recorder's flag is wrong");
      await openPanel(page, kind, s.contextId);
      const block = page.locator(`#ww${name}CtVtAuthority`);
      await expect(block.locator('[data-ctvt-value="voltage-side"]')).toContainText("Secondary");
      await expect(block.locator('[data-ctvt-value="voltage-side"]')).toContainText("set by engineer for the recording");
      await expect(block.locator('[data-ctvt-value="voltage-ratio"]')).toContainText("not needed");
      await expect(block.locator('[data-ctvt-value="current-ratio"]')).toContainText("not needed");
      await expect(page.locator(`#ww${name}StatusRow`)).toBeHidden();
      const channels = await (await page.request.get(`${s.base}/sources/${s.sourceId}/channels`)).json();
      expect(JSON.stringify(channels)).toContain("primary");                              // the recording's own declaration is still there
    });

    test("Manual mode keeps its own inputs and hides the recorded block", async ({ page }) => {
      const s = await seed(page);
      await openPanel(page, kind, s.contextId);
      await expect(page.locator(`#ww${name}CtVtAuthority`)).toBeVisible();
      await page.locator(`#ww${name}InputSourceManualBtn`).click();
      await expect(page.locator(`#ww${name}CtVtAuthority`)).toBeHidden();
      await expect(page.locator(`#ww${name}ManualVtPrimaryInput`)).toBeAttached();
      await expect(page.locator(`#ww${name}ManualCtPrimaryInput`)).toBeAttached();
      await expect(page.locator(`#ww${name}ManualVoltageBasisSelect`)).toBeAttached();
      await expect(page.locator(`#ww${name}ManualCurrentBasisSelect`)).toBeAttached();
      await expect(page.locator(`#ww${name}OutputBasisSelect`)).toBeEnabled();
      await page.locator(`#ww${name}InputSourceRecordingBtn`).click();
      await expect(page.locator(`#ww${name}CtVtAuthority`)).toBeVisible();
    });
  });
}

// Owner review of 1B: a recorded Distance result with no valid loop impedance evaluates no zone, so the page says
// "Not evaluated" -- never "Not Operated", which is the geometric result of a valid impedance.
test.describe("D5A-2B2C-1B Distance zone state without a valid impedance", () => {
  test("a blocked result shows Not evaluated for every zone; fixing the cause restores the geometric states", async ({ page }) => {
    const s = await seed(page);
    await putVt(page, s, MANUAL_VT);                      // the CT is missing: a Primary current cannot be converted
    await openPanel(page, "distance", s.contextId);
    const list = page.locator("#wwDistanceZoneStateList");
    await expect(page.locator("#wwDistanceStatusRow")).toContainText("CT is not configured for");
    await expect(list).toContainText("Not evaluated");
    await expect(list).not.toContainText("Not Operated");
    await expect(list.locator(".ww-dist-zone-state-badge--not-evaluated")).not.toHaveCount(0);
    await expect(list.locator(".ww-dist-zone-state-badge--not-operated, .ww-dist-zone-state-badge--operated")).toHaveCount(0);

    await putCt(page, s, MANUAL_CT);                      // the engineer configures the CT in Recording Details and returns
    await page.locator("#mainNavRecordingDetailsBtn").click();
    await page.locator("#mainNavAnalysisBtn").click();
    await expect(page.locator("#wwDistanceStatusRow")).toBeHidden({ timeout: 10000 });
    await expect(list).not.toContainText("Not evaluated");
    await expect(list.locator(".ww-dist-zone-state-badge--not-operated")).not.toHaveCount(0);     // valid impedance, zones evaluated
  });
});
