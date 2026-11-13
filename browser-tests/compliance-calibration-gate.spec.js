// Stage 3B-2C-2: Compliance Calibration Gate — browser-level tests (DEC-213).
//
// All three scenarios always run (no env-var gate):
//
//   A  COMTRADE not-assessed backward compat:
//        Upload COMTRADE, add reference, check readiness != calibration_unavailable.
//
//   B  BEN5K Unverified source → calibration_unavailable:
//        Upload synthetic_ben5k_phasor.ben, attempt readiness check; if a
//        voltage measurement group exists the status must be calibration_unavailable
//        with at least one member carrying a non-empty reason_code. If no group
//        is auto-created the test passes (backend unit tests cover the gate logic;
//        no BEN5K voltage group means the readiness endpoint is never reached).
//
//   C  UI smoke:
//        Navigate to Compliance page after COMTRADE upload; no JS errors; loading
//        clears.
//
// Governance: Stage 3B-2C-2 — compliance calibration bypass closures.
// Do NOT commit, push, or start Stage 3B-2C-3.

const { test, expect } = require("./support/test");
const path = require("path");

const COMTRADE_FIXTURES = path.join(__dirname, "..", "backend", "tests", "fixtures", "comtrade");
const BEN_FIXTURES = path.join(__dirname, "..", "backend", "tests", "fixtures", "ben");

const COMTRADE_STEM = "line_to_line_multibay";
// 3-phase voltage fixture (VR/VY/VB, all CALIBRATION_UNVERIFIED) — always present, no env-var gate.
// Produces a voltage Measurement Group and returns calibration_unavailable for phase_ground_rms reference.
const SYNTHETIC_BEN5K = path.join(BEN_FIXTURES, "synthetic_ben5k_compliance.ben");

const BACKEND_URL = `http://127.0.0.1:${process.env.PW_BACKEND_PORT || "8000"}`;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async function workspaceIdOf(page) {
  return page.evaluate(() => localStorage.getItem("powerwave.workspaceId"));
}

function wsUrl(wsId, suffix) {
  return `${BACKEND_URL}/api/v1/workspaces/${encodeURIComponent(wsId)}${suffix}`;
}

async function uploadComtrade(page) {
  await page.goto("/index.html");
  await page.locator("#mainNavRecordingsBtn").click();
  await page.locator("#recordingsUploadBtn, #recordingsEmptyUploadBtn").first().click();
  await expect(page.locator("#uploadModalOverlay")).toBeVisible();
  await page.locator("#uploadModalFile_0").setInputFiles(path.join(COMTRADE_FIXTURES, `${COMTRADE_STEM}.cfg`));
  await page.locator("#uploadModalFile_1").setInputFiles(path.join(COMTRADE_FIXTURES, `${COMTRADE_STEM}.dat`));
  await page.locator("#uploadModalSubmitBtn").click();
  await page.locator("#uploadModalOverlay").waitFor({ state: "hidden" });
  await expect(page.locator("#recordingsTableBody tr[data-source-id]").last()).toBeVisible();
}

async function uploadBen5k(page, benPath) {
  await page.locator("#mainNavRecordingsBtn").click();
  await page.locator("#recordingsUploadBtn, #recordingsEmptyUploadBtn").first().click();
  await expect(page.locator("#uploadModalOverlay")).toBeVisible();
  await page.locator("#uploadModalFormatSelect").selectOption("ben");
  await page.locator("#uploadModalFile_0").setInputFiles(benPath);
  await page.locator("#uploadModalSubmitBtn").click();
  await page.locator("#uploadModalOverlay").waitFor({ state: "hidden", timeout: 30000 });
  await expect(page.locator("#recordingsTableBody tr[data-source-id]").last()).toBeVisible();
  const row = page.locator("#recordingsTableBody tr[data-source-id]").last();
  return row.getAttribute("data-source-id");
}

async function addReferenceLayer(page, wsId, { representation = "phase_ground_rms", unit = "kV" } = {}) {
  const profileResp = await page.request.post(wsUrl(wsId, "/reference-profiles"), {
    data: {
      name: "CalibGateTestRef", category: "grid_requirement",
      assessment_definition: { representation, phase_treatment: "each_phase", member: null },
      unit, display_start_time: 0, display_end_time: 3,
      evaluation_start_time: 0, evaluation_end_time: 3, tolerance: 0,
      lower_boundary: { segments: [{ start_time: 0, end_time: 3, start_value: 0.9, end_value: 0.9, segment_type: "constant" }] },
      upper_boundary: null, metadata: {},
    },
  });
  expect(profileResp.ok(), `Create reference-profile failed: ${await profileResp.text()}`).toBeTruthy();
  const profileId = (await profileResp.json()).id;
  const layerResp = await page.request.post(wsUrl(wsId, "/reference-layers"), {
    data: { profile_id: profileId, visible: true },
  });
  expect(layerResp.ok(), `Create reference-layer failed: ${await layerResp.text()}`).toBeTruthy();
}

async function getVoltageGroups(page, wsId) {
  const r = await page.request.get(wsUrl(wsId, "/compliance/voltage/measurement-groups"));
  if (!r.ok()) return [];
  return r.json();
}

async function getReadiness(page, wsId, groupId) {
  const r = await page.request.get(wsUrl(wsId, `/compliance/voltage/readiness?measurement_group_id=${encodeURIComponent(groupId)}`));
  expect(r.status(), `Readiness must be HTTP 200 (calibration_unavailable is a structured result, not 422); got ${r.status()}: ${await r.text()}`).toBe(200);
  return r.json();
}

// ---------------------------------------------------------------------------
// Scenario A: COMTRADE not-assessed backward compat
// ---------------------------------------------------------------------------

test.describe("Scenario A — COMTRADE backward compat (not calibration_unavailable)", () => {
  test("COMTRADE source: compliance readiness status is not calibration_unavailable", async ({ page }) => {
    await uploadComtrade(page);
    const wsId = await workspaceIdOf(page);
    const groups = await getVoltageGroups(page, wsId);
    if (!groups.length) {
      // Should not happen with line_to_line_multibay, but guard defensively.
      test.skip(true, "No voltage measurement groups found for COMTRADE fixture");
      return;
    }
    await addReferenceLayer(page, wsId);
    const data = await getReadiness(page, wsId, groups[0].id);
    expect(data.status, `COMTRADE readiness must not be calibration_unavailable; got ${data.status}`).not.toBe("calibration_unavailable");
    // No member in any reference may carry calibration_unavailable state.
    for (const ref of (data.references || [])) {
      for (const member of (ref.members || [])) {
        expect(member.state, `COMTRADE member ${member.member} must not be calibration_unavailable`).not.toBe("calibration_unavailable");
      }
    }
  });
});

// ---------------------------------------------------------------------------
// Scenario B: BEN5K Unverified source → calibration_unavailable
// ---------------------------------------------------------------------------

test.describe("Scenario B — BEN5K Unverified → calibration_unavailable", () => {
  test("BEN5K Unverified 3-phase source: readiness is calibration_unavailable with reason_code", async ({ page }) => {
    await uploadComtrade(page); // establish workspace
    const benSourceId = await uploadBen5k(page, SYNTHETIC_BEN5K);
    const wsId = await workspaceIdOf(page);
    const groups = await getVoltageGroups(page, wsId);
    // The 3-phase compliance fixture (VR/VY/VB) MUST produce at least one voltage group.
    // If none is found, the fixture or auto-discovery is broken — this is a hard failure.
    expect(groups.length, `synthetic_ben5k_compliance.ben must produce ≥1 voltage measurement group; got 0. wsId=${wsId}`).toBeGreaterThan(0);
    await addReferenceLayer(page, wsId);
    // Find the group that has a calibration_unavailable status.
    // With the 3-phase compliance fixture all phases are BEN5K Unverified, so
    // any group containing these channels must yield calibration_unavailable.
    let found = false;
    for (const group of groups) {
      const data = await getReadiness(page, wsId, group.id);
      if (data.status === "calibration_unavailable") {
        found = true;
        // At least one member must have state=calibration_unavailable + reason_code.
        const blockedMembers = (data.references || []).flatMap(
          (ref) => (ref.members || []).filter((m) => m.state === "calibration_unavailable")
        );
        expect(blockedMembers.length, "At least one member must have state=calibration_unavailable").toBeGreaterThan(0);
        for (const m of blockedMembers) {
          expect(m.reason_code, `Member ${m.member} must carry a non-empty reason_code`).toBeTruthy();
        }
        // Must NOT show "ready" or any numerical compliance verdict.
        expect(data.status).not.toBe("ready");
        break;
      }
    }
    expect(found, `At least one voltage group must yield calibration_unavailable; groups=${JSON.stringify(groups.map(g => g.id))}`).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// Scenario C: UI smoke — Compliance page loads without JS errors
// ---------------------------------------------------------------------------

test.describe("Scenario C — UI smoke (Compliance page, no JS errors)", () => {
  test("Compliance page renders after COMTRADE upload without JS errors", async ({ page }) => {
    const errors = [];
    page.on("pageerror", (err) => errors.push(err.message));
    await uploadComtrade(page);
    await page.locator("#mainNavComplianceBtn").click();
    await expect(page.locator("#pageCompliance")).toBeVisible();
    // Allow group selector to populate.
    await expect
      .poll(async () => page.locator("#wwComplianceGroupSelect option").count(), { timeout: 8000 })
      .toBeGreaterThan(1);
    // Page loads cleanly.
    expect(errors, `Compliance page JS errors: ${errors.join("; ")}`).toHaveLength(0);
  });

  test("Compliance page hidden attribute clears on navigation", async ({ page }) => {
    await uploadComtrade(page);
    await page.locator("#mainNavComplianceBtn").click();
    await expect(page.locator("#pageCompliance")).toBeVisible();
    // Navigate away and back; page must hide then show correctly.
    await page.locator("#mainNavRecordingsBtn").click();
    await expect(page.locator("#pageCompliance")).toBeHidden();
    await page.locator("#mainNavComplianceBtn").click();
    await expect(page.locator("#pageCompliance")).toBeVisible();
  });
});
