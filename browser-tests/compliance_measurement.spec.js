// Compliance & Capability -- Slice 2 (Measurement Selection +
// Normalization Foundation) real-browser coverage. See
// browser-tests/compliance.spec.js for Slice 1's own workspace-shell
// coverage (menu order, page lifecycle, responsive layout) -- this file
// covers ONLY the new Measurement section: Assessment Quantity dropdown,
// quantity switching, availability/guardrail messages, and the
// Input/Input Type/Derived As/Base/Assessment Unit summary. Reference
// Layers/Event Alignment/Comparison Chart/Results logic is explicitly
// out of scope for this slice (task section 25) and is not tested here.
//
// Fixtures (backend/tests/fixtures/comtrade/), both committed, hand-
// verified end-to-end against the real backend before use (see this
// task's own final report):
//   - compliance_smoke_three_phase(.cfg/.dat): bare-role-named VA/VB/VC,
//     a known balanced 100 V RMS/50 Hz three-phase sinusoid -- the
//     INSTANTANEOUS scenario.
//   - compliance_smoke_rms_phase_a(.cfg/.dat): a single VA channel with
//     a smooth, always-positive, slowly-varying envelope -- COMTRADE
//     never sets `waveform_form` metadata away from "unknown", so this
//     exercises the real algorithmic detector fallback
//     (app.domain.rms_detector.classify_waveform_form), verified
//     directly to classify LIKELY_MAGNITUDE_OR_RMS before being
//     committed -- the RMS scenario.
//
// Compliance still does not register as an Engineering Context consumer
// (DEC-100/DEC-101) -- no Bay/Engineering Context selector exists or is
// used anywhere in this file; Measurement resolves channels purely from
// the workspace's own loaded sources.

const { test, expect } = require("@playwright/test");
const path = require("path");

const FIXTURES = path.join(__dirname, "..", "backend", "tests", "fixtures", "comtrade");
const BACKEND_URL = `http://127.0.0.1:${process.env.PW_BACKEND_PORT || "8000"}`;

const QUANTITY_LABELS = [
  "Phase A Voltage", "Phase B Voltage", "Phase C Voltage",
  "Line-Line AB Voltage", "Line-Line BC Voltage", "Line-Line CA Voltage",
  "Minimum Three-Phase Voltage", "Maximum Three-Phase Voltage",
  "Positive Sequence Voltage",
];

async function openCompliance(page) {
  await page.goto("/index.html");
  await page.locator("#mainNavComplianceBtn").click();
  await expect(page.locator("#pageCompliance")).toBeVisible();
}

async function uploadFixture(page, stem) {
  await page.locator("#recordingsUploadBtn, #recordingsEmptyUploadBtn").first().click();
  await expect(page.locator("#uploadModalOverlay")).toBeVisible();
  await page.locator("#uploadModalFile_0").setInputFiles(path.join(FIXTURES, `${stem}.cfg`));
  await page.locator("#uploadModalFile_1").setInputFiles(path.join(FIXTURES, `${stem}.dat`));
  await page.locator("#uploadModalSubmitBtn").click();
  await page.locator("#uploadModalOverlay").waitFor({ state: "hidden" });
  const row = page.locator("#recordingsTableBody tr[data-source-id]").last();
  await expect(row).toBeVisible();
  return row.getAttribute("data-source-id");
}

async function selectQuantity(page, label) {
  await page.locator("#wwComplianceMeasurementSelect").selectOption({ label });
}

test.describe("Compliance & Capability -- Slice 2 Measurement", () => {
  test("Assessment Quantity dropdown lists all nine quantities in order", async ({ page }) => {
    await openCompliance(page);
    const options = page.locator("#wwComplianceMeasurementSelect option");
    await expect(options).toHaveText(["Select a quantity…", ...QUANTITY_LABELS]);
  });

  test("no quantity selected shows the neutral empty state, never the summary", async ({ page }) => {
    await openCompliance(page);
    await expect(page.locator("#wwComplianceMeasurementEmptyState")).toBeVisible();
    await expect(page.locator("#wwComplianceMeasurementEmptyState")).toHaveText("No assessment quantity selected");
    await expect(page.locator("#wwComplianceMeasurementSummary")).toBeHidden();
  });

  test("empty workspace: selecting a quantity shows Missing Inputs with the exact channel(s) named", async ({ page }) => {
    await openCompliance(page);
    await selectQuantity(page, "Phase A Voltage");
    await expect(page.locator("#wwComplianceMeasurementSummary")).toBeVisible();
    await expect(page.locator("#wwComplianceMeasurementStatusRow")).toContainText("Missing: Va");
    await expect(page.locator("#wwComplianceMeasurementStatusRow")).toHaveClass(/ww-phasor-status--needs-configuration/);

    await selectQuantity(page, "Positive Sequence Voltage");
    await expect(page.locator("#wwComplianceMeasurementStatusRow")).toContainText("Missing: Va, Vb, Vc");
  });

  test("clearing the selection back to the placeholder returns to the empty state", async ({ page }) => {
    await openCompliance(page);
    await selectQuantity(page, "Phase A Voltage");
    await expect(page.locator("#wwComplianceMeasurementSummary")).toBeVisible();
    await page.locator("#wwComplianceMeasurementSelect").selectOption({ value: "" });
    await expect(page.locator("#wwComplianceMeasurementEmptyState")).toBeVisible();
    await expect(page.locator("#wwComplianceMeasurementSummary")).toBeHidden();
  });

  test.describe("single-phase recording (Va only)", () => {
    test("Phase A Voltage is available; Positive Sequence Voltage names the missing phases", async ({ page }) => {
      await page.goto("/index.html");
      await uploadFixture(page, "compliance_smoke_rms_phase_a");
      await openCompliance(page);

      await selectQuantity(page, "Phase A Voltage");
      await expect(page.locator("#wwComplianceMeasurementStatusRow")).toHaveText("Compatible");
      await expect(page.locator("#wwComplianceMeasurementInput")).toHaveText("Va");

      await selectQuantity(page, "Positive Sequence Voltage");
      await expect(page.locator("#wwComplianceMeasurementStatusRow")).toContainText("Missing: Vb, Vc");
    });

    test("RMS input reports Input Type RMS and Derived As Direct RMS", async ({ page }) => {
      await page.goto("/index.html");
      await uploadFixture(page, "compliance_smoke_rms_phase_a");
      await openCompliance(page);

      await selectQuantity(page, "Phase A Voltage");
      await expect(page.locator("#wwComplianceMeasurementStatusRow")).toHaveText("Compatible");
      await expect(page.locator("#wwComplianceMeasurementInputType")).toHaveText("RMS (Source-defined / unspecified)");
      await expect(page.locator("#wwComplianceMeasurementDerivedAs")).toHaveText("Direct RMS (Source-defined / unspecified)");
      // No Measurement Group exists in this workspace -- a normal,
      // non-error state (task section 16), never "Invalid Base".
      await expect(page.locator("#wwComplianceMeasurementBase")).toHaveText("Not configured");
      await expect(page.locator("#wwComplianceMeasurementUnit")).toHaveText("Engineering Units");
    });
  });

  test.describe("complete three-phase recording (Va/Vb/Vc)", () => {
    test("Min/Max/Positive Sequence are all available with Instantaneous/Fundamental RMS", async ({ page }) => {
      await page.goto("/index.html");
      await uploadFixture(page, "compliance_smoke_three_phase");
      await openCompliance(page);

      for (const label of ["Minimum Three-Phase Voltage", "Maximum Three-Phase Voltage", "Positive Sequence Voltage"]) {
        await selectQuantity(page, label);
        await expect(page.locator("#wwComplianceMeasurementStatusRow")).toHaveText("Compatible");
        await expect(page.locator("#wwComplianceMeasurementInputType")).toHaveText("Instantaneous");
        await expect(page.locator("#wwComplianceMeasurementDerivedAs")).toHaveText("Fundamental RMS");
      }
    });

    test("Positive Sequence Voltage input lists Va, Vb, Vc", async ({ page }) => {
      await page.goto("/index.html");
      await uploadFixture(page, "compliance_smoke_three_phase");
      await openCompliance(page);
      await selectQuantity(page, "Positive Sequence Voltage");
      await expect(page.locator("#wwComplianceMeasurementInput")).toHaveText("Va, Vb, Vc");
    });

    test("quantity switching updates the summary each time, never showing a stale result", async ({ page }) => {
      await page.goto("/index.html");
      await uploadFixture(page, "compliance_smoke_three_phase");
      await openCompliance(page);

      await selectQuantity(page, "Phase A Voltage");
      await expect(page.locator("#wwComplianceMeasurementInput")).toHaveText("Va");

      await selectQuantity(page, "Line-Line AB Voltage");
      await expect(page.locator("#wwComplianceMeasurementInput")).toHaveText("Va, Vb");
      await expect(page.locator("#wwComplianceMeasurementStatusRow")).toHaveText("Compatible");

      await selectQuantity(page, "Phase C Voltage");
      await expect(page.locator("#wwComplianceMeasurementInput")).toHaveText("Vc");
    });

    test("Base metadata: a confirmed Measurement Group with a nominal base shows kV/L-G and pu", async ({ page }) => {
      await page.goto("/index.html");
      const sourceId = await uploadFixture(page, "compliance_smoke_three_phase");
      const workspaceId = await page.evaluate(() => localStorage.getItem("powerwave.workspaceId"));

      // No Measurement Group configuration UI is exercised by this
      // Compliance-focused suite -- seeded directly via the existing,
      // already-tested Measurement Group REST API (the same "consumer
      // is real, its own upstream data is seeded directly" pattern
      // phasor_analysis.spec.js's own header comment already
      // establishes for Engineering Context).
      const groupResponse = await page.request.post(
        `${BACKEND_URL}/api/v1/workspaces/${encodeURIComponent(workspaceId)}/sources/${encodeURIComponent(sourceId)}/measurement-groups`,
        {
          data: {
            kind: "voltage", display_name: "Bus A", status: "confirmed",
            channel_refs: ["VA", "VB", "VC"].map((channel_name) => ({ kind: "source", source_id: sourceId, channel_name })),
          },
        }
      );
      expect(groupResponse.ok()).toBeTruthy();
      const group = await groupResponse.json();
      const configResponse = await page.request.put(
        `${BACKEND_URL}/api/v1/workspaces/${encodeURIComponent(workspaceId)}/sources/${encodeURIComponent(sourceId)}/measurement-groups/${encodeURIComponent(group.id)}/voltage-config`,
        { data: { nominal_voltage_ll_kv: 275.0, reference_mode: "manual", reference_override: "line_to_ground" } }
      );
      expect(configResponse.ok()).toBeTruthy();

      await openCompliance(page);
      await selectQuantity(page, "Phase A Voltage");
      await expect(page.locator("#wwComplianceMeasurementStatusRow")).toHaveText("Compatible");
      await expect(page.locator("#wwComplianceMeasurementBase")).toHaveText("275 kV L-G");
      await expect(page.locator("#wwComplianceMeasurementUnit")).toHaveText("pu");
    });
  });

  for (const viewport of [{ width: 1366, height: 900 }, { width: 1024, height: 800 }, { width: 800, height: 800 }]) {
    test(`no overflow with the Measurement summary visible at ${viewport.width}px`, async ({ page }) => {
      await page.setViewportSize(viewport);
      await page.goto("/index.html");
      await uploadFixture(page, "compliance_smoke_three_phase");
      await openCompliance(page);
      await selectQuantity(page, "Positive Sequence Voltage");
      await expect(page.locator("#wwComplianceMeasurementSummary")).toBeVisible();
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      expect(overflow).toBeLessThanOrEqual(1);
      const selectBox = await page.locator("#wwComplianceMeasurementSelect").boundingBox();
      const cardBox = await page.locator("#wwComplianceMeasurementCard").boundingBox();
      expect(selectBox.x + selectBox.width).toBeLessThanOrEqual(cardBox.x + cardBox.width + 1);
    });
  }

  test("opening Compliance still does not touch Playback, Analysis Input Source, or any analyzer state", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page, "compliance_smoke_three_phase");
    await page.locator("#mainNavAnalysisBtn").click();
    await expect(page.locator("#pageAnalysis")).toBeVisible();
    // Unlike Slice 1's own equivalent test (an empty workspace, where
    // Phasor's own no-recording fallback settles on "manual"), this
    // fixture upload gives Phasor a real bay to auto-bootstrap via its
    // bare-role-only detection fallback, so it legitimately settles on
    // "recording" instead -- wait for context loading to actually
    // finish (a real Engineering Context id assigned) rather than
    // asserting either specific mode.
    await expect(async () => {
      expect(await page.evaluate(() => wwPhasorState.contexts.length)).toBeGreaterThan(0);
    }).toPass({ timeout: 5000 });
    const before = await page.evaluate(() => JSON.stringify({
      playbackState: wwPlaybackState().state, inputSource: wwPhasorState.inputSource,
    }));

    await page.locator("#mainNavComplianceBtn").click();
    await expect(page.locator("#pageCompliance")).toBeVisible();
    await selectQuantity(page, "Positive Sequence Voltage");
    await expect(page.locator("#wwComplianceMeasurementStatusRow")).toHaveText("Compatible");

    const after = await page.evaluate(() => JSON.stringify({
      playbackState: wwPlaybackState().state, inputSource: wwPhasorState.inputSource,
    }));
    expect(after).toBe(before);
  });
});
