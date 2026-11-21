// D5A -- recorded Impedance Locus / Distance Protection take CT/VT only from the Recording Details
// Measurement Group (read-only block + "Configure in Recording Details"), never from a panel-local
// input and never from a nominal-derived VT. Real backend, real frontend, the same bay fixture the
// other Analysis suites use.

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
}

// The fixture declares primary sides, so the Recording basis is pre-selected to Primary; ask for the
// opposite output basis so a VT/CT conversion is actually needed.
async function needConversion(page, kind) {
  const n = PANELS[kind].name;
  await page.waitForFunction((k) => wwCtVtStateOf(wwCtVtPanel(k)).status === "ready", kind);
  const recording = await page.locator(`#ww${n}RecordingBasisSelect`).inputValue();
  await page.locator(`#ww${n}OutputBasisSelect`).selectOption(recording === "primary" ? "secondary" : "primary");
}

for (const kind of ["impedance", "distance"]) {
  const { name } = PANELS[kind];

  test.describe(`D5A authoritative CT/VT -- ${name}`, () => {
    test("a nominal-only VT is a valid auto-derived VT: shown normally, no warning, the calculation runs", async ({ page }) => {
      const s = await seed(page);
      await putCt(page, s, MANUAL_CT);
      await putVt(page, s, NOMINAL_ONLY);                   // nominal 132 kV, no stored VT
      await openPanel(page, kind, s.contextId);
      await needConversion(page, kind);

      const block = page.locator(`#ww${name}CtVtAuthority`);
      await expect(block).toBeVisible();
      await expect(block.locator("input, select, textarea")).toHaveCount(0);               // never an editor
      await expect(block.locator('[data-ctvt-value="voltage"]')).toContainText("132 kV / 110 V");
      await expect(block.locator('[data-ctvt-value="voltage"]')).toContainText("Auto-derived");
      await expect(block.locator('[data-ctvt-value="current"]')).toContainText("1200 A / 1 A");
      await expect(block.locator("[data-ctvt-code]")).toHaveCount(0);                      // nothing to confirm or fix
      for (const word of ["display-only", "assumed", "provisional", "unverified"]) await expect(block).not.toContainText(word);
      await expect(page.locator(`#ww${name}StatusRow`)).toBeHidden();                       // computed
      expect(await page.evaluate((k) => wwCtVtBasisParams(k).vt_primary, kind)).toBe("132000");
    });

    test("a missing CT blocks with the specific message, a Configure button and keeps Related Waveforms", async ({ page }) => {
      const s = await seed(page);
      await putVt(page, s, MANUAL_VT);                      // CT is never derived: it stays unconfigured
      await openPanel(page, kind, s.contextId);
      await needConversion(page, kind);

      const block = page.locator(`#ww${name}CtVtAuthority`);
      await expect(block.locator('[data-ctvt-value="current"]')).toContainText("not configured");
      await expect(block.locator('[data-ctvt-code="CT_AUTHORITY_MISSING"]')).toContainText(`CT is not configured for '${s.current.display_name}'`);
      await expect(page.locator(`#ww${name}StatusRow`)).toContainText("CT is not configured for");
      await expect(page.locator(`#ww${name}StatusRow`)).not.toContainText("Valid VT and CT ratios are required");
      await expect(block.locator("[data-ctvt-configure]")).toHaveCount(2);

      // Related Waveforms stay available while the calculation is blocked.
      await expect(page.locator("#wwAnalysisRelatedWaveformsVoltageGroup")).toBeVisible();
      await expect(page.locator("#wwAnalysisRelatedWaveformsEmptyState")).toBeHidden();
      await expect(async () => {
        const n = await page.evaluate(() => document.getElementById("wwAnalysisRelatedWaveformsVoltageChart").data.length);
        expect(n).toBeGreaterThan(0);
      }).toPass({ timeout: 8000 });
    });

    test("Configure in Recording Details opens the voltage group; a saved manual VT then takes precedence over the auto-derived one", async ({ page }) => {
      const s = await seed(page);
      await putCt(page, s, MANUAL_CT);
      await putVt(page, s, NOMINAL_ONLY);
      await openPanel(page, kind, s.contextId);
      await needConversion(page, kind);
      const block = page.locator(`#ww${name}CtVtAuthority`);
      await expect(block.locator('[data-ctvt-value="voltage"]')).toContainText("Auto-derived");
      await block.locator('[data-ctvt-configure="voltage"]').click();
      await expect(page.locator("#pageRecordingDetails")).toBeVisible();
      expect(await page.evaluate(() => wwRdState.selectedGroupId)).toBe(s.voltage.id);

      await putVt(page, s, { vt_primary_v: 66000, vt_secondary_v: 110 });      // the engineer's own VT (Edit -> Save)
      await page.locator("#mainNavAnalysisBtn").click();
      await expect(page.locator(PANELS[kind].panel)).toBeVisible();
      await expect(block.locator('[data-ctvt-value="voltage"]')).toContainText("66 kV / 110 V", { timeout: 10000 });
      await expect(block.locator('[data-ctvt-value="voltage"]')).toContainText("Manual");
      await expect(block.locator('[data-ctvt-value="voltage"]')).not.toContainText("Auto-derived");
      await expect(block.locator("[data-ctvt-code]")).toHaveCount(0);
    });

    test("an undeclared measurement side needs an explicit Recording basis, then sends the authoritative ratios", async ({ page }) => {
      const s = await seed(page);
      await putCt(page, s, MANUAL_CT);
      await putVt(page, s, MANUAL_VT);
      // Same real report, but with the recording's side declarations removed.
      await page.route("**/protection-instrument-context?*", async (route) => {
        const response = await route.fetch();
        const body = await response.json();
        for (const q of [body.voltage, body.current]) Object.assign(q, { declared_basis: null, side_status: "unknown", side: "unknown" });
        await route.fulfill({ response, json: body });
      });
      await openPanel(page, kind, s.contextId);
      await page.waitForFunction((k) => wwCtVtStateOf(wwCtVtPanel(k)).status === "ready", kind);
      await page.locator(`#ww${name}OutputBasisSelect`).selectOption("primary");   // recording basis stays secondary
      const block = page.locator(`#ww${name}CtVtAuthority`);
      await expect(block.locator('[data-ctvt-code="BASIS_UNDECLARED"]')).toBeVisible();
      await expect(page.locator(`#ww${name}StatusRow`)).toContainText("choose the Recording basis explicitly");
      const request = page.waitForRequest((r) => r.url().includes(PANELS[kind].endpoint) && r.url().includes("vt_primary=132000"));
      await block.locator("[data-ctvt-confirm-basis]").click();
      const url = new URL((await request).url());
      expect(url.searchParams.get("ct_primary")).toBe("1200");
      expect(url.searchParams.get("ct_secondary")).toBe("1");
      expect(url.searchParams.get("recording_basis")).toBe("secondary");
      await expect(block.locator('[data-ctvt-code="BASIS_UNVERIFIED"]')).toContainText("unverified");
    });

    test("voltage and current on different declared sides are never converted", async ({ page }) => {
      const s = await seed(page);
      await putCt(page, s, MANUAL_CT);
      await putVt(page, s, MANUAL_VT);
      await page.route("**/protection-instrument-context?*", async (route) => {
        const response = await route.fetch();
        const body = await response.json();
        Object.assign(body.voltage, { declared_basis: "primary", side_status: "recording_declared", side: "primary" });
        Object.assign(body.current, { declared_basis: "secondary", side_status: "recording_declared", side: "secondary" });
        await route.fulfill({ response, json: body });
      });
      const requests = [];
      page.on("request", (r) => { if (r.url().includes(PANELS[kind].endpoint)) requests.push(r.url()); });
      await openPanel(page, kind, s.contextId);
      await page.waitForFunction((k) => wwCtVtStateOf(wwCtVtPanel(k)).status === "ready", kind);
      await page.locator(`#ww${name}RecordingBasisSelect`).selectOption("secondary");
      await page.locator(`#ww${name}OutputBasisSelect`).selectOption("primary");
      await expect(page.locator(`#ww${name}CtVtAuthority [data-ctvt-code="SIDES_DIFFER"]`)).toContainText("Independent-side mode is required");
      await expect(page.locator(`#ww${name}StatusRow`)).toContainText("Independent-side mode is required");
      expect(requests.filter((u) => u.includes("vt_primary="))).toEqual([]);
    });

    test("Manual mode keeps its own inputs and hides the recorded CT/VT block", async ({ page }) => {
      const s = await seed(page);
      await openPanel(page, kind, s.contextId);
      await needConversion(page, kind);
      await expect(page.locator(`#ww${name}CtVtAuthority`)).toBeVisible();
      await page.locator(`#ww${name}InputSourceManualBtn`).click();
      await expect(page.locator(`#ww${name}CtVtAuthority`)).toBeHidden();
      await expect(page.locator(`#ww${name}ManualVtPrimaryInput`)).toBeAttached();
      await expect(page.locator(`#ww${name}ManualCtPrimaryInput`)).toBeAttached();
      await page.locator(`#ww${name}InputSourceRecordingBtn`).click();
      await expect(page.locator(`#ww${name}CtVtAuthority`)).toBeVisible();
    });
  });
}
