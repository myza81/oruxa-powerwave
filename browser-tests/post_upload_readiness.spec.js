// DEC-104 (2026-09-23): Shared post-upload workspace/source preparation.
// Owner UAT established a new application-wide invariant: once a source
// is successfully uploaded, every top-level function that can operate on
// it must be ready to use INDEPENDENTLY -- no page (Waveform, Analysis,
// Compliance, Table, Calculated Channels) may depend on another page
// having been opened first merely to materialize shared metadata
// (Measurement Group discovery, Engineering Context discovery).
//
// This is the single most important acceptance test the owner's own task
// specification called out by name: upload once, then go STRAIGHT to
// Compliance (bay selector already populated) and STRAIGHT to Analysis
// (Engineering Context already populated) in the same session, with NO
// intervening visit to "Manage Measurement Groups," no explicit
// `/suggest` call from this test, and no prior page visit of any kind.
//
// Fixture: compliance_smoke_multibay(.cfg/.dat) (already committed,
// reused verbatim from compliance_measurement.spec.js) -- four bays
// (KPDN1/KPDN2/SLKS/SGT1), each a clean VR/VY/VB triplet. Verified
// directly against the real backend (see app.services.workspace_
// preparation_service.prepare_workspace_source()) to produce FOUR
// `suggested` Measurement Groups AND four `suggested` Engineering
// Contexts from ONE upload, with zero manual/explicit trigger -- exactly
// the shared discovery this suite exercises through the real UI.
//
// This file deliberately does NOT seed any Measurement Group or
// Engineering Context via a direct backend API call (contrast every
// other Playwright suite in this repo, which seeds state that slice's
// own UI cannot create yet) -- the entire point here is that upload
// ALONE is sufficient.

const { test, expect } = require("@playwright/test");
const path = require("path");

const FIXTURES = path.join(__dirname, "..", "backend", "tests", "fixtures", "comtrade");
const STEM = "compliance_smoke_multibay";

async function uploadFixture(page) {
  await page.goto("/index.html");
  await page.locator("#recordingsUploadBtn, #recordingsEmptyUploadBtn").first().click();
  await expect(page.locator("#uploadModalOverlay")).toBeVisible();
  await page.locator("#uploadModalFile_0").setInputFiles(path.join(FIXTURES, `${STEM}.cfg`));
  await page.locator("#uploadModalFile_1").setInputFiles(path.join(FIXTURES, `${STEM}.dat`));
  await page.locator("#uploadModalSubmitBtn").click();
  await page.locator("#uploadModalOverlay").waitFor({ state: "hidden" });
  const row = page.locator("#recordingsTableBody tr[data-source-id]").last();
  await expect(row).toBeVisible();
}

test.describe("DEC-104: shared post-upload workspace preparation", () => {
  test("upload -> directly to Compliance: bay selector is ready with no prior page visits", async ({ page }) => {
    await uploadFixture(page);

    // Straight to Compliance from Recordings -- never visits "Manage
    // Measurement Groups" first.
    await page.locator("#mainNavComplianceBtn").click();
    await expect(page.locator("#pageCompliance")).toBeVisible();

    await expect(page.locator("#wwComplianceGroupField")).toBeVisible();
    const options = await page.locator("#wwComplianceGroupSelect option").allTextContents();
    expect(new Set(options.slice(1))).toEqual(new Set(["KPDN1 VOLTAGE", "KPDN2 VOLTAGE", "SLKS VOLTAGE", "SGT1 VOLTAGE"]));
    await expect(page.locator("#wwComplianceManageGroupsBtn")).toBeHidden();

    await page.locator("#wwComplianceGroupSelect").selectOption({ label: "KPDN1 VOLTAGE" });
    await page.locator("#wwComplianceMeasurementSelect").selectOption({ label: "Phase A Voltage" });
    await expect(page.locator("#wwComplianceMeasurementStatusRow")).toHaveText("Compatible");
    await expect(page.locator("#wwComplianceMeasurementInput")).toHaveText("Va");
  });

  test("upload -> directly to Analysis: Engineering Context is ready with no prior bootstrap dependency", async ({ page }) => {
    await uploadFixture(page);

    // Straight to Analysis from Recordings -- never visits Compliance or
    // "Manage Measurement Groups" first, and this test issues no
    // `/engineering-contexts/suggest` call of its own.
    await page.locator("#mainNavAnalysisBtn").click();
    await expect(page.locator("#pageAnalysis")).toBeVisible();
    await expect(page.locator("#wwAnalysisTypePhasorBtn")).toHaveClass(/active/);

    // The context already exists (created at upload time) -- Phasor's
    // own page-owned fallback bootstrap (wwAnalysisDiscoverUncoveredSources())
    // never needs to run because nothing is left uncovered; the
    // "Identifying engineering contexts…" transient state must never
    // even appear.
    await expect(page.locator("#wwPhasorEmptyState")).not.toContainText("Identifying engineering contexts");
    const options = await page.locator("#wwPhasorContextSelect option").allTextContents();
    expect(new Set(options.slice(1))).toEqual(new Set(["KPDN1", "KPDN2", "SLKS", "SGT1"]));

    // 2026-09-23 regression fix (see DECISIONS.md DEC-104's own
    // follow-up entry): the point of THIS assertion is that a bay is
    // already auto-selected and its values already rendered WITHOUT any
    // click of our own -- a prior version of this test manually called
    // `selectOption()` here, which accidentally masked a real regression
    // where upload-time-prepared contexts (as opposed to contexts
    // discovered while Analysis was already open) never triggered each
    // analyzer's own "auto-select the first bay" behavior at all.
    await expect(page.locator("#wwPhasorContextSelect")).not.toHaveValue("");
    await expect(page.locator("#wwPhasorEmptyState")).toBeHidden();
    await expect(async () => {
      const text = await page.locator("#wwPhasorValuesList").innerText();
      expect(text).toMatch(/Va/);
    }).toPass({ timeout: 5000 });
  });

  test("upload -> directly to Compliance -> directly to Analysis, same session, no bootstrap in between", async ({ page }) => {
    await uploadFixture(page);

    await page.locator("#mainNavComplianceBtn").click();
    await expect(page.locator("#pageCompliance")).toBeVisible();
    await expect(page.locator("#wwComplianceGroupField")).toBeVisible();
    await expect(page.locator("#wwComplianceGroupSelect option")).toHaveCount(5); // placeholder + 4 bays

    await page.locator("#mainNavAnalysisBtn").click();
    await expect(page.locator("#pageAnalysis")).toBeVisible();
    await expect(page.locator("#wwPhasorContextSelect option")).toHaveCount(5, { timeout: 10000 }); // blank + 4 bays
  });

  test("re-uploading a second source into the same workspace does not duplicate or disturb the first bay's discovery", async ({ page }) => {
    await uploadFixture(page);
    await page.locator("#mainNavRecordingsBtn").click();
    await page.locator("#recordingsUploadBtn, #recordingsEmptyUploadBtn").first().click();
    await expect(page.locator("#uploadModalOverlay")).toBeVisible();
    await page.locator("#uploadModalFile_0").setInputFiles(path.join(FIXTURES, "compliance_smoke_three_phase.cfg"));
    await page.locator("#uploadModalFile_1").setInputFiles(path.join(FIXTURES, "compliance_smoke_three_phase.dat"));
    await page.locator("#uploadModalSubmitBtn").click();
    await page.locator("#uploadModalOverlay").waitFor({ state: "hidden" });

    await page.locator("#mainNavComplianceBtn").click();
    await expect(page.locator("#pageCompliance")).toBeVisible();
    // 4 original bays + 1 newly-discovered bay from the second upload --
    // idempotent, additive-only, never duplicated on repeated visits.
    await expect(page.locator("#wwComplianceGroupSelect option")).toHaveCount(6);
    await page.locator("#mainNavRecordingsBtn").click();
    await page.locator("#mainNavComplianceBtn").click();
    await expect(page.locator("#wwComplianceGroupSelect option")).toHaveCount(6);
  });
});

// 2026-09-23 owner-UAT regression fix: "Analysis/Analyzer worked before
// DEC-104, but does not work after DEC-104." Root cause (see DECISIONS.md
// DEC-104's own follow-up entry): every analyzer's "auto-select the first
// bay" behavior was wired ONLY to `wwAnalysisPublishFreshContextsDiscovered()`,
// which itself only ever fired from INSIDE the discovery/suggest bootstrap
// path (`wwAnalysisDiscoverUncoveredSources()`'s own blocking branch) --
// correct before DEC-104, when a context could only ever come into being
// WHILE that bootstrap ran. After DEC-104, a freshly-uploaded source's
// context is normally already fully formed by the time Analysis's very
// first fetch runs, so that bootstrap path never executes at all, and
// nothing ever fired the "fresh" signal -- every analyzer silently fell
// back to its own "Select an Engineering Context to begin." empty state,
// forcing a manual click before ANY analyzer would compute or render
// anything, even though the bay was already fully discovered and listed
// in the selector.
//
// This suite proves the REAL owner workflow end-to-end for all five
// Analysis-menu analyzers, deliberately WITHOUT ever selecting a context
// by hand -- the previous version of the "upload -> directly to Analysis"
// test above manually called `selectOption()` before checking values,
// which is exactly the kind of test that would pass even with the
// regression present (see DECISIONS.md DEC-104's own follow-up entry,
// section D). The assertion that matters is not "the context appears in
// the dropdown" -- it is "input resolution reaches resolved state AND the
// analyzer's own backend request succeeds AND the result renders,"
// exactly as the owner specified.
//
// Fixture: phasor_smoke_three_phase(.cfg/.dat) -- already committed and
// already reused verbatim by phasor_analysis.spec.js/overcurrent_analysis.spec.js/
// impedance_analysis.spec.js/sequence_components_analysis.spec.js/
// distance_protection_analysis.spec.js's own suites (their own "consumer
// is real, seed via direct API" tests) -- the ONE bay this repo already
// has committed with BOTH Voltage and Current channels (ALPHA1_VA/VB/VC/
// IA/IB/IC, a known balanced 100 V RMS/40 A RMS three-phase sinusoid),
// which every one of these five analyzers needs to produce a real,
// assertable result. `compliance_smoke_multibay` above is Voltage-only
// and cannot exercise Overcurrent/Impedance/Distance Protection, which
// all require Current.
test.describe("DEC-104 regression fix: analyzers auto-resolve and compute immediately after upload, with zero manual context selection", () => {
  async function uploadPhasorSmokeFixture(page) {
    await page.goto("/index.html");
    await page.locator("#recordingsUploadBtn, #recordingsEmptyUploadBtn").first().click();
    await expect(page.locator("#uploadModalOverlay")).toBeVisible();
    await page.locator("#uploadModalFile_0").setInputFiles(path.join(FIXTURES, "phasor_smoke_three_phase.cfg"));
    await page.locator("#uploadModalFile_1").setInputFiles(path.join(FIXTURES, "phasor_smoke_three_phase.dat"));
    await page.locator("#uploadModalSubmitBtn").click();
    await page.locator("#uploadModalOverlay").waitFor({ state: "hidden" });
    const row = page.locator("#recordingsTableBody tr[data-source-id]").last();
    await expect(row).toBeVisible();
  }

  test("Phasor: input resolution + computation + render succeed with no manual context selection", async ({ page }) => {
    await uploadPhasorSmokeFixture(page);
    await page.locator("#mainNavAnalysisBtn").click();
    await expect(page.locator("#pageAnalysis")).toBeVisible();
    await expect(page.locator("#wwAnalysisTypePhasorBtn")).toHaveClass(/active/);

    await expect(page.locator("#wwPhasorContextSelect")).not.toHaveValue("");
    await expect(page.locator("#wwPhasorEmptyState")).toBeHidden();
    await expect(async () => {
      const text = await page.locator("#wwPhasorValuesList").innerText();
      expect(text).toMatch(/100\.0\s*V/);
      expect(text).toMatch(/40\.0\s*A/);
    }).toPass({ timeout: 5000 });
  });

  test("Overcurrent: input resolution + computation + render succeed with no manual context selection", async ({ page }) => {
    await uploadPhasorSmokeFixture(page);
    await page.locator("#mainNavAnalysisBtn").click();
    await expect(page.locator("#pageAnalysis")).toBeVisible();
    await page.locator("#wwAnalysisTypeOvercurrentBtn").click();
    await expect(page.locator("#wwAnalysisTypeOvercurrentBtn")).toHaveClass(/active/);

    await expect(page.locator("#wwOvercurrentContextSelect")).not.toHaveValue("");
    await expect(async () => {
      const text = await page.locator("#wwOvercurrentValuesList").innerText();
      expect(text).toContain("Measured RMS current");
    }).toPass({ timeout: 5000 });
  });

  test("Impedance Locus: input resolution + computation + render succeed with no manual context selection", async ({ page }) => {
    await uploadPhasorSmokeFixture(page);
    await page.locator("#mainNavAnalysisBtn").click();
    await expect(page.locator("#pageAnalysis")).toBeVisible();
    await page.locator("#wwAnalysisTypeImpedanceBtn").click();
    await expect(page.locator("#wwAnalysisTypeImpedanceBtn")).toHaveClass(/active/);

    await expect(page.locator("#wwImpedanceContextSelect")).not.toHaveValue("");
    await expect(async () => {
      const text = await page.locator("#wwImpedanceValuesList").innerText();
      expect(text).toContain("Phase impedance");
    }).toPass({ timeout: 10000 });
  });

  test("Sequence Components: input resolution + computation + render succeed with no manual context selection", async ({ page }) => {
    await uploadPhasorSmokeFixture(page);
    await page.locator("#mainNavAnalysisBtn").click();
    await expect(page.locator("#pageAnalysis")).toBeVisible();
    await page.locator("#wwAnalysisTypeSequenceBtn").click();
    await expect(page.locator("#wwAnalysisTypeSequenceBtn")).toHaveClass(/active/);

    await expect(page.locator("#wwSequenceContextSelect")).not.toHaveValue("");
    await expect(async () => {
      const text = await page.locator("#wwSequenceValuesList").innerText();
      expect(text).toMatch(/100\.0\s*V/);
    }).toPass({ timeout: 5000 });
  });

  test("Distance Protection: input resolution + computation + render succeed with no manual context selection", async ({ page }) => {
    await uploadPhasorSmokeFixture(page);
    await page.locator("#mainNavAnalysisBtn").click();
    await expect(page.locator("#pageAnalysis")).toBeVisible();
    await page.locator("#wwAnalysisTypeDistanceBtn").click();
    await expect(page.locator("#wwAnalysisTypeDistanceBtn")).toHaveClass(/active/);

    await expect(page.locator("#wwDistanceContextSelect")).not.toHaveValue("");
    await expect(async () => {
      const text = await page.locator("#wwDistanceValuesList").innerText();
      expect(text).toContain("Loop");
    }).toPass({ timeout: 10000 });
  });

  test("all five analyzers are simultaneously auto-selected from ONE upload and ONE Analysis-page visit, before switching any tab", async ({ page }) => {
    // Every analyzer registers as a context consumer at page load,
    // regardless of which tab is initially visible (see
    // wwAnalysisRegisterContextConsumer() call sites) -- so the ONE
    // fetch+publish cycle wwRenderAnalysisPage() triggers must reach
    // and auto-select all five, not just whichever tab happens to be
    // showing. Switching tabs afterward must never trigger a fresh
    // discovery/selection race -- each was already resolved.
    await uploadPhasorSmokeFixture(page);
    await page.locator("#mainNavAnalysisBtn").click();
    await expect(page.locator("#pageAnalysis")).toBeVisible();
    await expect(page.locator("#wwPhasorContextSelect")).not.toHaveValue("", { timeout: 10000 });

    for (const [tabId, selectId] of [
      ["wwAnalysisTypeOvercurrentBtn", "wwOvercurrentContextSelect"],
      ["wwAnalysisTypeImpedanceBtn", "wwImpedanceContextSelect"],
      ["wwAnalysisTypeSequenceBtn", "wwSequenceContextSelect"],
      ["wwAnalysisTypeDistanceBtn", "wwDistanceContextSelect"],
    ]) {
      await page.locator(`#${tabId}`).click();
      // Already selected the instant the tab becomes visible -- no
      // "Identifying…"/discovery delay of any kind at this point.
      await expect(page.locator(`#${selectId}`)).not.toHaveValue("");
    }
  });
});
