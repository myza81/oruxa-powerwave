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

    await page.locator("#wwPhasorContextSelect").selectOption({ label: "KPDN1" });
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
