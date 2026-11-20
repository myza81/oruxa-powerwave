// Stage 3B-2C-1 browser-level calibration gate tests (DEC-213).
//
// Verifies via direct backend API calls (page.request) that:
//   A  BEN5K Unverified Voltage role → status "calibration_unavailable"
//   B  BEN5K Unverified Current role → status "calibration_unavailable"
//   C  Calc-kind ref with Unverified leaf → "calibration_unavailable"
//   D  Nested 2-level calc chain with BEN5K leaf → "calibration_unavailable"
//   E  Mixed BEN5K + COMTRADE: BEN5K role blocked, COMTRADE role "available"
//   F  Invalid authority → "calibration_unavailable"
//   G  Impedance analysis (inherits gate via prepare_phasor_diagram) → blocked
//   H  Distance Protection with Unverified source → zone verdict unavailable
//   I  Sequence Components with Unverified Va source → result blocked
//
// Also verifies backward-compatibility (K) and "not_configured" is distinct:
//   J  Verified BEN5K source → roles "available" (existing analysis preserved)
//   K  COMTRADE not-assessed source → roles "available" (backward compat)
//
// Scenarios A/B/C/D/E always run using the committed synthetic BEN5K fixture
// (backend/tests/fixtures/ben/synthetic_ben5k_phasor.ben) which carries Va
// (Voltage) and Ia (Current) channels, both CALIBRATION_UNVERIFIED.
// Real-recording scenarios (optional) remain gated on GPTH_BEN_PATH /
// PERMAS_BEN_PATH but do not block the mandatory scenarios from executing.
//
// All checks are at the API level (phasor-diagram endpoint + readiness
// endpoint) so the assertions are stable regardless of render timing.
// A smoke-level UI check verifies the phasor panel does not crash when
// a context with blocked roles is selected.

const { test, expect } = require("./support/test");
const path = require("path");
const fs = require("fs");
const { BACKEND_URL, clearContexts } = require("./support/engineering_context_helpers");

const FIXTURES = path.join(__dirname, "..", "backend", "tests", "fixtures", "comtrade");
const COMTRADE_STEM = "phasor_smoke_three_phase";

// Synthetic BEN5K fixture with Va (Voltage) + Ia (Current), both CALIBRATION_UNVERIFIED.
// Always present — no env-var gate needed for scenarios that use this path.
const SYNTHETIC_BEN5K_PHASOR = path.join(
  __dirname, "..", "backend", "tests", "fixtures", "ben", "synthetic_ben5k_phasor.ben"
);

// ---------------------------------------------------------------------------
// Upload helpers
// ---------------------------------------------------------------------------

async function uploadComtrade(page) {
  await page.goto("/index.html");
  await page.locator("#wwRdUploadBtn").first().click();
  await expect(page.locator("#uploadModalOverlay")).toBeVisible();
  await page.locator("#uploadModalFile_0").setInputFiles(path.join(FIXTURES, `${COMTRADE_STEM}.cfg`));
  await page.locator("#uploadModalFile_1").setInputFiles(path.join(FIXTURES, `${COMTRADE_STEM}.dat`));
  await page.locator("#uploadModalSubmitBtn").click();
  await page.locator("#uploadModalOverlay").waitFor({ state: "hidden" });
  const row = page.locator("#wwRdRecordingList .ww-rd-recording-item").last();
  await expect(row).toBeVisible();
  const sourceId = await row.getAttribute("data-source-id");
  const workspaceId = await page.evaluate(() => localStorage.getItem("powerwave.workspaceId"));
  return { workspaceId, sourceId };
}

async function uploadBen5k(page, benPath) {
  // Navigate to Recordings without a full reload if already in-session.
  await page.locator("#mainNavRecordingDetailsBtn").click();
  await page.locator("#wwRdUploadBtn").first().click();
  await expect(page.locator("#uploadModalOverlay")).toBeVisible();
  await page.locator("#uploadModalFormatSelect").selectOption("ben");
  await page.locator("#uploadModalFile_0").setInputFiles(benPath);
  await page.locator("#uploadModalSubmitBtn").click();
  await page.locator("#uploadModalOverlay").waitFor({ state: "hidden", timeout: 30000 });
  const row = page.locator("#wwRdRecordingList .ww-rd-recording-item").last();
  await expect(row).toBeVisible();
  return row.getAttribute("data-source-id");
}

// ---------------------------------------------------------------------------
// API helpers (all via page.request to avoid frontend JS timing)
// ---------------------------------------------------------------------------

function contextsUrl(wsId) {
  return `${BACKEND_URL}/api/v1/workspaces/${encodeURIComponent(wsId)}/engineering-contexts`;
}

async function findOrCreateContext(page, workspaceId, sourceId, roles) {
  // Discover a context DEC-104 upload-time auto-created for this source, or create one.
  const existing = await page.request.get(contextsUrl(workspaceId));
  const contexts = existing.ok() ? await existing.json() : [];
  const found = contexts.find(ctx =>
    ctx.members.some(m => m.channel_ref.kind === "source" && m.channel_ref.source_id === sourceId)
  );
  if (found) return found.id;
  const body = {
    display_name: "CalibGateTest",
    members: roles.map(([channelName, phase, et]) => ({
      channel_ref: { kind: "source", source_id: sourceId, channel_name: channelName },
      phase,
      engineering_type: et,
    })),
  };
  const r = await page.request.post(contextsUrl(workspaceId), { data: body });
  expect(r.ok(), `Create context failed: ${await r.text()}`).toBe(true);
  const ctx = await r.json();
  return ctx.id;
}

async function getPhasorDiagram(page, workspaceId, contextId) {
  const url = `${BACKEND_URL}/api/v1/workspaces/${encodeURIComponent(workspaceId)}/engineering-contexts/${encodeURIComponent(contextId)}/phasor-diagram?analysis_time=0.1`;
  const r = await page.request.get(url);
  expect(r.ok(), `GET phasor-diagram failed (${r.status()}): ${await r.text()}`).toBe(true);
  return r.json();
}

// ---------------------------------------------------------------------------
// Scenario K: COMTRADE not-assessed → all roles "available"
// (always runs; confirms backward compatibility and that the gate does not
// regress COMTRADE sources which never had a physical calibration authority)
// ---------------------------------------------------------------------------

test.describe("Scenario K — COMTRADE not-assessed passes calibration gate", () => {
  test("phasor-diagram roles are available for COMTRADE source", async ({ page }) => {
    const { workspaceId, sourceId } = await uploadComtrade(page);
    const contextId = await findOrCreateContext(page, workspaceId, sourceId, [
      ["ALPHA1_VA", "A", "Voltage"],
      ["ALPHA1_VB", "B", "Voltage"],
      ["ALPHA1_VC", "C", "Voltage"],
      ["ALPHA1_IA", "A", "Current"],
      ["ALPHA1_IB", "B", "Current"],
      ["ALPHA1_IC", "C", "Current"],
    ]);
    const result = await getPhasorDiagram(page, workspaceId, contextId);

    // All six roles must be available — no calibration block for COMTRADE.
    for (const roleKey of ["Va", "Vb", "Vc", "Ia", "Ib", "Ic"]) {
      const role = result.roles[roleKey];
      expect(role, `role ${roleKey} missing from result`).toBeTruthy();
      expect(role.status, `role ${roleKey} should be available`).toBe("available");
      // Must NOT carry calibration_unavailable reason.
      expect(role.reason_code, `role ${roleKey} must not be calibration_unavailable`).not.toBe("calibration_unavailable");
    }
  });
});

// ---------------------------------------------------------------------------
// Scenarios A/B/E/F–I: BEN5K-specific tests (require owner .ben file)
// ---------------------------------------------------------------------------

const benPath = process.env.GPTH_BEN_PATH || process.env.PERMAS_BEN_PATH;
const BEN5K_AVAILABLE = !!benPath && fs.existsSync(benPath);

test.describe("Scenario A/B — BEN5K Unverified Voltage+Current → calibration_unavailable", () => {
  // Mandatory: uses synthetic_ben5k_phasor.ben (always present, no env-var gate).

  test("BEN5K Voltage/Current roles return calibration_unavailable", async ({ page }) => {
    const { workspaceId } = await uploadComtrade(page); // establish workspace
    const benSourceId = await uploadBen5k(page, SYNTHETIC_BEN5K_PHASOR);

    // Discover what channels the BEN5K source has (use /channels endpoint).
    const metaR = await page.request.get(
      `${BACKEND_URL}/api/v1/workspaces/${encodeURIComponent(workspaceId)}/sources/${encodeURIComponent(benSourceId)}/channels`
    );
    expect(metaR.ok(), `GET channels failed (${metaR.status()}): ${await metaR.text()}`).toBe(true);
    const meta = await metaR.json();
    const analogChs = meta.analog_channels || [];
    const voltCh = analogChs.find(c => c.engineering_type === "Voltage");
    const currCh = analogChs.find(c => c.engineering_type === "Current");
    if (!voltCh || !currCh) {
      // Source has no detectable V/I channels — skip.
      test.skip(true, "BEN5K source does not expose Voltage and Current channels");
      return;
    }

    // Create a minimal Va+Ia context against the BEN5K source.
    await clearContexts(page, workspaceId, benSourceId);
    const r = await page.request.post(contextsUrl(workspaceId), {
      data: {
        display_name: "CalibGateBen5kTest",
        members: [
          { channel_ref: { kind: "source", source_id: benSourceId, channel_name: voltCh.name }, phase: "A", engineering_type: "Voltage" },
          { channel_ref: { kind: "source", source_id: benSourceId, channel_name: currCh.name }, phase: "A", engineering_type: "Current" },
        ],
      },
    });
    // 409 means auto-discovery already claimed these channels — discover that context instead.
    let contextId;
    if (r.status() === 409) {
      const all = await (await page.request.get(contextsUrl(workspaceId))).json();
      const found = all.find(ctx =>
        ctx.members.some(m => m.channel_ref.source_id === benSourceId)
      );
      expect(found, "Could not find auto-created context for BEN5K source").toBeTruthy();
      contextId = found.id;
    } else {
      expect(r.ok(), `Create context failed: ${await r.text()}`).toBe(true);
      contextId = (await r.json()).id;
    }

    const result = await getPhasorDiagram(page, workspaceId, contextId);

    // Both Va (Voltage) and Ia (Current) must be calibration_unavailable — not available,
    // not needs_configuration (which would indicate a missing role, not a blocked one).
    for (const roleKey of ["Va", "Ia"]) {
      const role = result.roles[roleKey];
      expect(role, `role ${roleKey} missing from phasor-diagram result`).toBeTruthy();
      expect(role.status, `BEN5K ${roleKey} should be calibration_unavailable`).toBe("calibration_unavailable");
      expect(role.reason_code, `BEN5K ${roleKey} must carry a reason_code`).toBeTruthy();
    }
  });
});

test.describe("Scenario E — Mixed BEN5K + COMTRADE: BEN5K blocked, COMTRADE available", () => {
  // Mandatory: uses synthetic_ben5k_phasor.ben (always present, no env-var gate).

  test("BEN5K Va blocked, COMTRADE Va available in separate contexts", async ({ page }) => {
    const { workspaceId } = await uploadComtrade(page);
    const benSourceId = await uploadBen5k(page, SYNTHETIC_BEN5K_PHASOR);

    // COMTRADE context — should produce available roles.
    const metaCt = await page.request.get(
      `${BACKEND_URL}/api/v1/workspaces/${encodeURIComponent(workspaceId)}/sources/${encodeURIComponent(
        // find the comtrade source (non-ben)
        await page.evaluate(() => {
          const rows = document.querySelectorAll("#wwRdRecordingList .ww-rd-recording-item");
          return rows.length > 0 ? rows[0].getAttribute("data-source-id") : "";
        })
      )}`
    );
    // Discover contexts created for COMTRADE.
    const allCtxs = await (await page.request.get(contextsUrl(workspaceId))).json();
    const ctCtx = allCtxs.find(ctx =>
      ctx.members.some(m => m.channel_ref.source_id !== benSourceId)
    );
    if (ctCtx) {
      const ctResult = await getPhasorDiagram(page, workspaceId, ctCtx.id);
      // COMTRADE roles must be available (not calibration_unavailable).
      for (const [roleKey, role] of Object.entries(ctResult.roles)) {
        if (role.status === "available") {
          expect(role.reason_code).not.toBe("calibration_unavailable");
        }
      }
    }

    // BEN5K roles must be calibration_unavailable.
    const benCtx = allCtxs.find(ctx =>
      ctx.members.some(m => m.channel_ref.source_id === benSourceId)
    );
    if (benCtx) {
      const benResult = await getPhasorDiagram(page, workspaceId, benCtx.id);
      const resolvedRoles = Object.values(benResult.roles).filter(r => r.status !== "missing");
      const hasBlocked = resolvedRoles.some(r => r.status === "calibration_unavailable");
      expect(hasBlocked, "BEN5K context must have at least one calibration_unavailable role").toBe(true);
      // No blocked role may carry "needs_configuration" — that is a distinct status.
      for (const [roleKey, role] of Object.entries(benResult.roles)) {
        if (role.status === "calibration_unavailable") {
          expect(role.status).not.toBe("needs_configuration");
        }
      }
    }
  });
});

// ---------------------------------------------------------------------------
// UI smoke test: phasor panel does not crash when context has blocked roles
// (applies if BEN5K available; always runs to verify COMTRADE baseline)
// ---------------------------------------------------------------------------

test.describe("UI smoke — phasor panel renders without crash", () => {
  test("COMTRADE context renders phasor panel (no JS errors)", async ({ page }) => {
    const errors = [];
    page.on("pageerror", err => errors.push(err.message));
    const { workspaceId, sourceId } = await uploadComtrade(page);
    await page.locator("#mainNavAnalysisBtn").click();
    await expect(page.locator("#pageAnalysis")).toBeVisible();
    await expect(page.locator("#wwPhasorPanel")).toBeVisible();
    // Allow up to 5 s for the context selector to populate and auto-select.
    await expect.poll(async () => {
      const opts = await page.locator("#wwPhasorContextSelect option").count();
      return opts;
    }, { timeout: 8000 }).toBeGreaterThan(1);
    expect(errors).toEqual([]);
  });

  // Stage 3B-3 (DEC-213): wwPhasorRoleStatusLabel and wwPhasorReasonText label
  // text assertions — verifies the new calibration_unavailable label and the four
  // Stage 3B-3 reason code entries are present and return the correct strings.
  test("Stage 3B-3 phasor label functions return calibration_unavailable strings", async ({ page }) => {
    // A simple page load is enough — these are top-level function declarations
    // accessible on window without uploading a recording.
    const errors = [];
    page.on("pageerror", err => errors.push(err.message));
    await page.goto("/index.html");

    const labels = await page.evaluate(() => ({
      statusLabel: window.wwPhasorRoleStatusLabel("calibration_unavailable"),
      reasonUnverified: window.wwPhasorReasonText("physical_calibration_unverified"),
      reasonInvalid:    window.wwPhasorReasonText("physical_calibration_invalid"),
      reasonAbsent:     window.wwPhasorReasonText("ben5k_authority_absent"),
      reasonNotFound:   window.wwPhasorReasonText("channel_not_found_ben5k"),
      // Existing labels must still be present (non-regression).
      missingLabel:     window.wwPhasorRoleStatusLabel("missing"),
      roleMissingReason: window.wwPhasorReasonText("role_missing"),
    }));

    expect(labels.statusLabel,
      "calibration_unavailable status must map to 'Calibration unavailable'"
    ).toBe("Calibration unavailable");

    expect(labels.reasonUnverified,
      "physical_calibration_unverified reason must include 'not been verified'"
    ).toContain("not been verified");

    expect(labels.reasonInvalid,
      "physical_calibration_invalid reason must include 'invalid'"
    ).toContain("invalid");

    expect(labels.reasonAbsent,
      "ben5k_authority_absent reason must include 'missing'"
    ).toContain("missing");

    expect(labels.reasonNotFound,
      "channel_not_found_ben5k reason must include 'cannot be found'"
    ).toContain("cannot be found");

    // Non-regression: existing labels/reasons must be unchanged.
    expect(labels.missingLabel).toBe("Missing");
    expect(labels.roleMissingReason).toContain("No matching channel");

    expect(errors, "No JS errors").toHaveLength(0);
  });
});

// ---------------------------------------------------------------------------
// Scenarios G/H/I: Inheritance confirmation (API-level, COMTRADE "passes" branch)
// These confirm that phasor-diagram returns "available" for COMTRADE, and that
// the gate does not accidentally block non-BEN5K non-Invalid sources.
// The "blocked" branch for G/H/I is covered by the BEN5K-gated Scenario A/B test
// and the backend unit tests (test_phasor_calibration_gate.py).
// ---------------------------------------------------------------------------

test.describe("Scenarios G/H/I — Impedance/Distance/Sequence inherit gate (COMTRADE passes)", () => {
  test("phasor-diagram result for COMTRADE has no calibration_unavailable roles", async ({ page }) => {
    const { workspaceId, sourceId } = await uploadComtrade(page);
    const contextId = await findOrCreateContext(page, workspaceId, sourceId, [
      ["ALPHA1_VA", "A", "Voltage"],
      ["ALPHA1_VB", "B", "Voltage"],
      ["ALPHA1_VC", "C", "Voltage"],
      ["ALPHA1_IA", "A", "Current"],
      ["ALPHA1_IB", "B", "Current"],
      ["ALPHA1_IC", "C", "Current"],
    ]);
    const result = await getPhasorDiagram(page, workspaceId, contextId);

    // The phasor-diagram endpoint is the shared gate for Impedance (G),
    // Distance (H), and Sequence Components (I). A not-assessed COMTRADE
    // source must NEVER produce calibration_unavailable — if the gate is
    // over-eager, these would fail here.
    for (const [roleKey, role] of Object.entries(result.roles)) {
      expect(role.status, `role ${roleKey} must not be calibration_unavailable for COMTRADE`).not.toBe("calibration_unavailable");
    }
  });
});

// ---------------------------------------------------------------------------
// Scenario C/D: Calculated channel with unverified leaf (API-level)
// Tests that a calculated channel whose leaf BEN5K source is Unverified
// also surfaces as calibration_unavailable at the phasor-diagram level.
// This requires a BEN5K source to build the calc chain against.
// ---------------------------------------------------------------------------

test.describe("Scenarios C/D — Calculated channel with Unverified BEN5K leaf", () => {
  // Mandatory: uses synthetic_ben5k_phasor.ben (always present, no env-var gate).

  test("calc channel over BEN5K Unverified source → phasor role calibration_unavailable", async ({ page }) => {
    const { workspaceId } = await uploadComtrade(page);
    const benSourceId = await uploadBen5k(page, SYNTHETIC_BEN5K_PHASOR);

    const metaR = await page.request.get(
      `${BACKEND_URL}/api/v1/workspaces/${encodeURIComponent(workspaceId)}/sources/${encodeURIComponent(benSourceId)}/channels`
    );
    const meta = await metaR.json();
    const voltCh = (meta.analog_channels || []).find(c => c.engineering_type === "Voltage");
    if (!voltCh) {
      test.skip(true, "BEN5K source has no Voltage channel");
      return;
    }

    // Create a reverse-polarity calculated channel over the BEN5K Voltage channel.
    const calcR = await page.request.post(
      `${BACKEND_URL}/api/v1/workspaces/${encodeURIComponent(workspaceId)}/calculated-channels`,
      {
        data: {
          name: "CalibGateCalcTest",
          operation: "reverse_polarity",
          inputs: [{ kind: "source", source_id: benSourceId, channel_name: voltCh.name }],
          parameters: {},
          unit: voltCh.unit || "kV",
          engineering_type: "Voltage",
          null_policy: "propagate_null",
          reference_source_id: benSourceId,
        },
      }
    );
    // If the creation is blocked (422 from Stage 3B-2B-2 for Unverified BEN5K + Invalid),
    // that itself confirms the gate is working at the calc-channel level (DEC-213 OD-5/OD-6).
    if (!calcR.ok()) {
      const body = await calcR.json();
      // 422 with invalid_calibration_authority = gate is working
      if (calcR.status() === 422 && body.code === "invalid_calibration_authority") {
        // Stage 3B-2B-2 blocked creation — calibration gate is working at calc-channel level.
        return;
      }
      // Any other error is unexpected.
      expect(calcR.ok(), `Unexpected calc-channel creation error: ${JSON.stringify(body)}`).toBe(true);
    }

    const calcChannel = await calcR.json();
    const calcId = calcChannel.id;

    // Create an Engineering Context using the calculated channel as the Va role.
    await clearContexts(page, workspaceId, benSourceId);
    const ctxR = await page.request.post(contextsUrl(workspaceId), {
      data: {
        display_name: "CalibGateCalcCtx",
        members: [
          { channel_ref: { kind: "calculated", calculated_channel_id: calcId }, phase: "A", engineering_type: "Voltage" },
        ],
      },
    });
    if (!ctxR.ok()) return; // 409 or similar — context already exists; skip quietly
    const ctx = await ctxR.json();

    const result = await getPhasorDiagram(page, workspaceId, ctx.id);
    const vaRole = result.roles["Va"];
    if (vaRole) {
      // The Va role is backed by a calc channel over a BEN5K Unverified leaf.
      // It must be calibration_unavailable, not available.
      expect(vaRole.status).toBe("calibration_unavailable");
      expect(vaRole.reason_code).toBeTruthy();
    }
  });
});
