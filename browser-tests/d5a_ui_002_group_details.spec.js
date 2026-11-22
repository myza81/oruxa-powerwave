// D5A-UI-002 -- Recording Details: measurement side. Level 1 (the recording) lives in Recording Info; Level 2 (ONE selected
// Voltage or Current Measurement Group of that recording) lives in Group Details. Real backend (the shared resolver and API),
// real frontend. The page renders only what the backend reports; these tests drive the real controls and confirm the backend
// state with direct API reads.

const { test, expect } = require("./support/test");
const { syntheticComtrade } = require("./support/synthetic_comtrade");

const BACKEND = `http://127.0.0.1:${process.env.PW_BACKEND_PORT || "8000"}`;
const NAMES = ["VA", "VB", "VC", "IA", "IB", "IC"];

// One three-phase bay (<prefix>_*) whose per-channel P/S markers are chosen by the test.
function recording({ v = "P", i = "P", sides = {}, prefix = "ALPHA1" } = {}) {
  return syntheticComtrade({
    station: `STN_${prefix}`, startClock: "10:00:00.000000", rateHz: 1000, durationS: 0.2,
    channels: NAMES.map((n) => ({
      name: `${prefix}_${n}`, phase: n[1], unit: n[0] === "V" ? "V" : "A", amplitude: n[0] === "V" ? 100 : 5, frequencyHz: 50,
      side: sides[n] !== undefined ? sides[n] : (n[0] === "V" ? v : i),
    })),
  });
}

async function openRd(page) {
  await page.goto("/index.html");
  await page.locator("#mainNavRecordingDetailsBtn").click();
  await expect(page.locator("#pageRecordingDetails")).toBeVisible();
}

const itemFor = (page, sourceId) => page.locator(`#wwRdRecordingList .ww-rd-recording-item[data-source-id="${sourceId}"]`);

// Uploads one recording and returns its row, found by the source id that is new after the upload.
async function upload(page, files, stem) {
  const known = await page.locator("#wwRdRecordingList .ww-rd-recording-item").evaluateAll((els) => els.map((e) => e.getAttribute("data-source-id")));
  await page.locator("#wwRdUploadBtn").click();
  await expect(page.locator("#uploadModalOverlay")).toBeVisible();
  await page.locator("#uploadModalFile_0").setInputFiles({ name: `${stem}.cfg`, mimeType: "application/octet-stream", buffer: files.cfg });
  await page.locator("#uploadModalFile_1").setInputFiles({ name: `${stem}.dat`, mimeType: "application/octet-stream", buffer: files.dat });
  await page.locator("#uploadModalSubmitBtn").click();
  await page.locator("#uploadModalOverlay").waitFor({ state: "hidden" });
  await expect(page.locator("#wwRdRecordingList .ww-rd-recording-item")).toHaveCount(known.length + 1, { timeout: 10000 });
  const ids = await page.locator("#wwRdRecordingList .ww-rd-recording-item").evaluateAll((els) => els.map((e) => e.getAttribute("data-source-id")));
  return itemFor(page, ids.find((id) => !known.includes(id)));
}

async function seed(page, opts = {}, stem = "side_a") {
  await openRd(page);
  const item = await upload(page, recording(opts), stem);
  await item.click();
  const sourceId = await item.getAttribute("data-source-id");
  const workspaceId = await page.evaluate(() => localStorage.getItem("powerwave.workspaceId"));
  const base = `${BACKEND}/api/v1/workspaces/${encodeURIComponent(workspaceId)}`;
  if (page.viewportSize().width <= 692) {   // narrow layout shows one panel at a time: go to the details panel
    await page.evaluate(() => { wwRdState.narrowPanel = "details"; wwRdApplyNarrowLayout(); });
  }
  await expect(page.locator("#wwRdSideSection")).toBeVisible();
  return { sourceId, workspaceId, base, item };
}

async function getJson(page, url) {
  const response = await page.request.get(url);
  expect(response.ok(), await response.text()).toBeTruthy();
  return response.json();
}

// ---- Level 1 (Recording Info) ----
const recRow = (page) => page.locator('#wwRdSideSection [data-ww-side-row="recording"]');
const recBtn = (page, side) => recRow(page).locator(`[data-ww-side-value="${side}"]`);

// ---- Level 2 (Group Details): the one Measurement Value card of the selected group ----
const card = (page) => page.locator("#wwRdSideGroupSection");
const gBtn = (page, side) => card(page).locator(`[data-ww-side-value="${side}"]`);

async function openGroup(page, label) {
  await page.locator("#wwRdGroupsBody .ww-rd-group-item", { hasText: label }).first().click();
  await expect(card(page)).toBeVisible();
  await expect(page.locator("#wwRdTabGroupDetails")).toHaveAttribute("aria-selected", "true");
}
async function showRecordingInfo(page) {
  await page.locator("#wwRdTabRecordingInfo").click();
  await expect(page.locator("#wwRdSideSection")).toBeVisible();
}

async function expectActive(locatorFor, side, other) {
  await expect(locatorFor(side)).toHaveAttribute("aria-checked", "true");
  await expect(locatorFor(other)).toHaveAttribute("aria-checked", "false");
}
const recActive = (page, side) => expectActive((s) => recBtn(page, s), side, side === "primary" ? "secondary" : "primary");
const gActive = (page, side) => expectActive((s) => gBtn(page, s), side, side === "primary" ? "secondary" : "primary");

// The backend's own record of this recording's Measurement Groups, by kind (first of each kind).
async function groups(page, s, sourceId = s.sourceId) {
  const list = await getJson(page, `${s.base}/sources/${sourceId}/measurement-groups`);
  return Object.fromEntries(["voltage", "current"].map((k) => [k, list.find((g) => g.kind === k)]));
}
const groupSide = (page, s, gid, sourceId = s.sourceId) => getJson(page, `${s.base}/sources/${sourceId}/measurement-groups/${gid}/measurement-side`);

// ------------------------------------------------------------------------------------------------ Level 1 (Recording Info)

test("Level 1: one selector, shown from the recording, correctable, with the contradiction disclosed", async ({ page }) => {
  const s = await seed(page);
  await expect(page.locator("#wwRdSideSection .ww-rd-section-heading")).toHaveText("Measurement Side");
  await expect(page.locator("#wwRdSideGroupSection")).toHaveCount(0);       // no group controls in Recording Info
  await expect(page.locator('#wwRdSideSection [data-ww-side-row="group"]')).toHaveCount(0);
  await recActive(page, "primary");
  await expect(recRow(page)).not.toContainText("Set by engineer"); // UI-REC-001: the normal state carries no provenance line
  await expect(page.locator('#wwRdSideSection [data-ww-side-notice="recording-override"]')).toHaveCount(0);

  await recBtn(page, "secondary").click();
  await recActive(page, "secondary");                                   // immediate (optimistic) ...
  await expect(recRow(page)).toContainText("Set by engineer");          // ... then confirmed by the backend view
  const notice = page.locator('#wwRdSideSection [data-ww-side-notice="recording-override"]');
  await expect(notice).toContainText("The recording declares Primary on 6 channels");
  await expect(notice).toContainText("original declarations are kept");
  const stored = await getJson(page, `${s.base}/sources/${s.sourceId}/measurement-side`);
  expect(stored.engineer_correction.side).toBe("secondary");
  expect(stored.recording_derived.side).toBe("primary");                // the evidence itself is untouched
  expect(stored.authority).toBe("engineer_recording_correction");

  await recBtn(page, "primary").click();                                // back to what the recording declares: no Reset needed
  await recActive(page, "primary");
  await expect(recRow(page)).not.toContainText("Set by engineer");
  await expect(notice).toHaveCount(0);
  expect((await getJson(page, `${s.base}/sources/${s.sourceId}/measurement-side`)).engineer_correction).toBeNull();
});

test("Level 1: mixed, undeclared and voltage/current-split recordings are shown honestly", async ({ page }) => {
  const mixed = await seed(page, { sides: { VB: "S" } }, "side_mixed");
  await expect(recRow(page)).toContainText("declare different sides (5 Primary, 1 Secondary)");
  await expect(recBtn(page, "primary")).toHaveAttribute("aria-checked", "false");
  await expect(recBtn(page, "secondary")).toHaveAttribute("aria-checked", "false");
  await recBtn(page, "primary").click();
  await recActive(page, "primary");
  await expect(page.locator('#wwRdSideSection [data-ww-side-notice="recording-override"]')).toContainText("declares Secondary on 1 channel");
  expect((await getJson(page, `${mixed.base}/sources/${mixed.sourceId}/measurement-side`)).recording_derived.status).toBe("mixed");

  const none = await upload(page, recording({ v: "", i: "", prefix: "BRAVO1" }), "side_none");
  await none.click();
  await expect(recRow(page)).toContainText("does not declare a measurement side");
  await expect(recBtn(page, "primary")).toHaveAttribute("aria-checked", "false");

  const split = await upload(page, recording({ v: "P", i: "S", prefix: "CHARLIE1" }), "side_split");
  await split.click();
  await expect(recRow(page)).toContainText("Recorded: voltage primary, current secondary");
  await expect(page.locator("#wwRdSideSection .ww-rd-provenance--unresolved")).toHaveCount(0);
});

test("Level 1: a partially declared recording is inferred until the engineer confirms it", async ({ page }) => {
  const s = await seed(page, { i: "" });
  await recActive(page, "primary");
  await expect(recRow(page)).toContainText("Inferred from the recording's declared channels (3 declare no side)");
  await recBtn(page, "primary").click();
  await expect(recRow(page)).toContainText("Set by engineer");
  expect((await getJson(page, `${s.base}/sources/${s.sourceId}/measurement-side`)).engineer_correction.side).toBe("primary");
});

// ------------------------------------------------------------------------------------------------ Group Details: one group at a time

test("a Voltage group shows only the voltage sections, a Current group only the current sections", async ({ page }) => {
  await seed(page);
  const headings = async () => (await page.locator("#wwRdDetailsBody .ww-rd-section-heading").allTextContents()).map((t) => t.replace(/Edit$/, "").trim());

  await openGroup(page, "VOLTAGE");
  await expect(page.locator(".ww-rd-details-group-name")).toHaveText("ALPHA1 VOLTAGE");
  expect(await headings()).toEqual(["Measurement Value", "Voltage Base Configuration", "Voltage Transformer (VT)"]);
  await expect(card(page)).toContainText("Primary or secondary values for voltage.");
  await expect(page.locator("#wwRdDetailsBody")).not.toContainText("Equipment Rating");
  await expect(page.locator("#wwRdDetailsBody")).not.toContainText("Current Transformer (CT)");
  await expect(page.locator("#wwRdDetailsBody .ww-rd-details-channels")).toContainText("ALPHA1_VA");
  await expect(page.locator("#wwRdDetailsBody .ww-rd-details-channels")).not.toContainText("ALPHA1_IA");
  await expect(page.locator("#wwRdDetailsBody [data-ww-side-row=\"group\"] [role=\"radio\"]")).toHaveText(["Primary", "Secondary"]);

  await openGroup(page, "CURRENT");
  await expect(page.locator(".ww-rd-details-group-name")).toHaveText("ALPHA1 CURRENT");
  expect(await headings()).toEqual(["Measurement Value", "Equipment Rating", "Current Transformer (CT)"]);
  await expect(card(page)).toContainText("Primary or secondary values for current.");
  await expect(page.locator("#wwRdDetailsBody")).not.toContainText("Voltage Base Configuration");
  await expect(page.locator("#wwRdDetailsBody")).not.toContainText("Voltage Transformer (VT)");
  await expect(page.locator("#wwRdDetailsBody .ww-rd-details-channels")).toContainText("ALPHA1_IA");
  // exactly one measurement-side control for the group: never per phase, never both quantities
  await expect(page.locator("#wwRdDetailsBody [data-ww-side-row=\"group\"]")).toHaveCount(1);
  await expect(page.locator("#wwRdDetailsBody [role=\"radiogroup\"]")).toHaveCount(1);
  await expect(page.locator("#wwRdDetailsBody").getByRole("button", { name: /reset|confirm bay/i })).toHaveCount(0);
});

test("every Group Details section is a card with its icon; unconfigured engineering values are shown as they are", async ({ page }) => {
  await seed(page);
  await openGroup(page, "VOLTAGE");
  const cards = page.locator("#wwRdDetailsBody .ww-rd-gcard");
  await expect(cards).toHaveCount(3);
  for (let n = 0; n < 3; n++) {
    await expect(cards.nth(n).locator(".ww-rd-info-icon svg")).toBeVisible();
    const look = await cards.nth(n).evaluate((el) => ({ radius: parseFloat(getComputedStyle(el).borderTopLeftRadius), border: getComputedStyle(el).borderTopWidth }));
    expect(look.radius).toBeGreaterThanOrEqual(10);
    expect(look.border).toBe("1px");
  }
  await expect(cards.nth(1)).toContainText("Voltage Base Configuration");
  await expect(cards.nth(1).getByRole("button", { name: "Edit" })).toBeVisible();
  await expect(cards.nth(2)).toContainText("Not configured");             // the real VT state: no invented 275 kV / 110 V
  await expect(cards.nth(2)).not.toContainText("275");
  await openGroup(page, "CURRENT");
  await expect(page.locator("#wwRdDetailsBody .ww-rd-gcard")).toHaveCount(3);
  const rating = page.locator("#wwRdDetailsBody .ww-rd-gcard", { hasText: "Equipment Rating" });
  await expect(rating).toContainText("Not specified");
  await expect(page.locator("#wwRdDetailsBody .ww-rd-gcard", { hasText: "Current Transformer (CT)" })).toContainText("Not configured");
  await expect(page.locator("#wwRdDetailsBody")).not.toContainText("1200");
});

test("existing Edit buttons keep working inside the cards", async ({ page }) => {
  await seed(page);
  await openGroup(page, "VOLTAGE");
  await page.locator("#wwRdVoltageEditBtn").click();
  await expect(page.locator("#wwRdVltKv")).toBeVisible();
  await expect(card(page)).toBeVisible();                                  // the side card is still there while a form is open
  await page.locator("#wwRdVoltageCancelBtn").click();
  await expect(page.locator("#wwRdVoltageEditBtn")).toBeVisible();
  await page.locator("#wwRdVtEditBtn").click();
  await expect(page.locator("#wwRdVtPrimaryKv")).toBeVisible();
  await page.locator("#wwRdVtCancelBtn").click();
  await openGroup(page, "CURRENT");
  await page.locator("#wwRdCtEditBtn").click();
  await expect(page.locator("#wwRdCtPrimaryA")).toBeVisible();
  await page.locator("#wwRdCtCancelBtn").click();
  await page.locator("#wwRdCurrentEditBtn").click();
  await expect(page.locator("#wwRdCurMva")).toBeVisible();
  await page.locator("#wwRdCurrentCancelBtn").click();
  await expect(page.locator("#wwRdCurrentEditBtn")).toBeVisible();
});

// ------------------------------------------------------------------------------------------------ independent Voltage / Current settings

test("the Voltage and the Current group of one bay keep independent settings, saved to their own groups and kept after reload", async ({ page }) => {
  const s = await seed(page);
  const g = await groups(page, s);
  await openGroup(page, "VOLTAGE");
  await gActive(page, "primary");
  await expect(card(page)).not.toContainText("Set manually");               // the normal state carries no status line
  await gBtn(page, "secondary").click();
  await gActive(page, "secondary");                                          // immediate, then confirmed by the backend view
  await expect(card(page)).toContainText("Set manually");
  expect((await groupSide(page, s, g.voltage.id)).override.side).toBe("secondary");
  expect((await groupSide(page, s, g.current.id)).override).toBeNull();      // the Current group was not touched

  await openGroup(page, "CURRENT");
  await gActive(page, "primary");                                            // Primary voltage <-> Secondary current is legitimate: here the reverse
  await gBtn(page, "secondary").click();
  await gActive(page, "secondary");
  await openGroup(page, "VOLTAGE");
  await gActive(page, "secondary");                                          // switching groups preserved both settings
  expect((await groupSide(page, s, g.current.id)).effective_side).toBe("secondary");

  // Primary voltage with Secondary current: change the voltage group back to what the recording declares.
  await gBtn(page, "primary").click();
  await gActive(page, "primary");
  await expect(card(page)).not.toContainText("Set manually");
  expect((await groupSide(page, s, g.voltage.id)).override).toBeNull();      // no Reset needed: the group follows again
  await openGroup(page, "CURRENT");
  await gActive(page, "secondary");
  const view = await groupSide(page, s, g.current.id);
  expect(view.override.side).toBe("secondary");
  expect(view.status).toBe("resolved");                                     // mixed references are not a conflict
  expect(view.overridden_declarations).toHaveLength(3);
  await expect(card(page).locator('[data-ww-side-notice="group-override"]')).toContainText("Differs from the side declared by 3 channels");

  // Reload: the configuration lives in the backend, not in the page.
  await page.reload();
  await page.locator("#mainNavRecordingDetailsBtn").click();
  await page.locator("#wwRdRecordingList .ww-rd-recording-item").first().click();
  await openGroup(page, "CURRENT");
  await gActive(page, "secondary");
  await openGroup(page, "VOLTAGE");
  await gActive(page, "primary");
});

test("Level 1 changes reach the groups that follow it, while a manually set group keeps its value", async ({ page }) => {
  const s = await seed(page);
  const g = await groups(page, s);
  await openGroup(page, "VOLTAGE");
  await gBtn(page, "secondary").click();                                     // pinned
  await gActive(page, "secondary");
  await showRecordingInfo(page);
  await recBtn(page, "secondary").click();                                   // Level 1 -> Secondary
  await recActive(page, "secondary");
  await openGroup(page, "CURRENT");
  await gActive(page, "secondary");                                          // the follower follows
  await openGroup(page, "VOLTAGE");
  await gActive(page, "secondary");                                          // the pinned group is unchanged
  await showRecordingInfo(page);
  await recBtn(page, "primary").click();                                     // Level 1 back to Primary
  await recActive(page, "primary");
  await openGroup(page, "CURRENT");
  await gActive(page, "primary");                                            // the follower follows again
  await openGroup(page, "VOLTAGE");
  await gActive(page, "secondary");                                          // the manual override survived
  expect((await groupSide(page, s, g.voltage.id)).override.side).toBe("secondary");
});

test("a group whose channels declare different sides is shown as unresolved, not guessed; choosing resolves only that group", async ({ page }) => {
  const s = await seed(page, { sides: { VB: "S" } }, "side_mixed");
  const g = await groups(page, s);
  await openGroup(page, "VOLTAGE");
  await expect(card(page)).toContainText("The voltage channels in this group declare different sides");
  await expect(gBtn(page, "primary")).toHaveAttribute("aria-checked", "false");
  await expect(gBtn(page, "secondary")).toHaveAttribute("aria-checked", "false");   // no false highlight
  await gBtn(page, "primary").click();
  await gActive(page, "primary");
  await expect(card(page).locator('[data-ww-side-notice="group-override"]')).toContainText("Differs from the side declared by 1 channel");
  const view = await groupSide(page, s, g.voltage.id);
  expect(view.status).toBe("resolved");
  expect(view.override.side).toBe("primary");
  expect(view.channels.find((c) => c.channel_name === "ALPHA1_VB").declared_side).toBe("secondary");   // evidence retained
  await openGroup(page, "CURRENT");
  await gActive(page, "primary");                                            // the current group was never in conflict
  await expect(card(page)).not.toContainText("different sides");
});

test("a recording with no side evidence leaves every group unresolved until the engineer decides", async ({ page }) => {
  const s = await seed(page, { v: "", i: "" }, "side_none");
  await openGroup(page, "VOLTAGE");
  await expect(card(page)).toContainText("The side of this group is not resolved. Select it.");
  await expect(gBtn(page, "primary")).toHaveAttribute("aria-checked", "false");
  await expect(gBtn(page, "secondary")).toHaveAttribute("aria-checked", "false");
  await gBtn(page, "secondary").click();
  await gActive(page, "secondary");
  await openGroup(page, "CURRENT");
  await expect(gBtn(page, "secondary")).toHaveAttribute("aria-checked", "false");   // the other group is still unresolved
  await expect(card(page)).toContainText("not resolved");
  const g = await groups(page, s);
  expect((await groupSide(page, s, g.current.id)).status).toBe("unresolved");
});

// ------------------------------------------------------------------------------------------------ several recordings, races, lifecycle

test("two recordings keep separate group settings", async ({ page }) => {
  const a = await seed(page, { prefix: "KPDN1" }, "side_a");
  const itemB = await upload(page, recording({ prefix: "KPDN2" }), "side_b");
  await a.item.click();
  await openGroup(page, "KPDN1 VOLTAGE");
  await gBtn(page, "secondary").click();
  await gActive(page, "secondary");
  await itemB.click();
  await openGroup(page, "KPDN2 VOLTAGE");
  await gActive(page, "primary");                                            // B's group is not A's
  await a.item.click();
  await openGroup(page, "KPDN1 VOLTAGE");
  await gActive(page, "secondary");
});

test("a quick second choice wins and a slow save never lands on another group", async ({ page }) => {
  const s = await seed(page);
  const g = await groups(page, s);
  let puts = 0;
  await page.route("**/measurement-groups/*/measurement-side", async (route) => {
    if (route.request().method() === "PUT" && puts++ === 0) await new Promise((r) => setTimeout(r, 900));   // first save is slow
    await route.continue();
  });
  await openGroup(page, "VOLTAGE");
  await gBtn(page, "secondary").click();
  await gBtn(page, "primary").click();
  await gActive(page, "primary");
  await openGroup(page, "CURRENT");                                          // the engineer moves on while the saves run
  await gActive(page, "primary");
  await expect.poll(() => puts).toBe(2);
  await page.waitForTimeout(1500);
  await gActive(page, "primary");                                            // the current group never showed the voltage choice
  await expect(card(page)).toHaveAttribute("data-ww-side-kind", "current");
  await openGroup(page, "VOLTAGE");
  await gActive(page, "primary");
  expect((await groupSide(page, s, g.voltage.id)).override).toBeNull();      // the slow first save never overwrote the second
});

test("a slow read for one recording cannot appear on another", async ({ page }) => {
  const a = await seed(page, {}, "side_a");
  const itemB = await upload(page, recording({ prefix: "BRAVO1" }), "side_b");
  await itemB.click();
  await recBtn(page, "secondary").click();                               // B carries a correction, A does not
  await expect(recRow(page)).toContainText("Set by engineer");
  await a.item.click();
  await recActive(page, "primary");
  await expect(recRow(page)).not.toContainText("Set by engineer");

  let reads = 0;
  await page.route("**/measurement-side", async (route) => {
    if (route.request().method() === "GET" && !route.request().url().includes("/sources/") && reads++ === 0) {
      await new Promise((r) => setTimeout(r, 1500));                     // the first overview read (for B) is slow
    }
    await route.continue();
  });
  await itemB.click();                                                   // slow read starts for B ...
  await a.item.click();                                                  // ... A is opened before it returns
  await recActive(page, "primary");
  await page.waitForTimeout(2000);                                       // B's late answer arrives
  await recActive(page, "primary");
  await expect(recRow(page)).not.toContainText("Set by engineer");
  await expect(page.locator('#wwRdSideSection[data-ww-side-source="' + a.sourceId + '"]')).toBeVisible();
});

test("lifecycle: deleting a group or a recording releases its setting, and a workspace reset leaves nothing behind", async ({ page }) => {
  const a = await seed(page, {}, "side_a");
  const g = await groups(page, a);
  await openGroup(page, "VOLTAGE");
  await gBtn(page, "secondary").click();
  await gActive(page, "secondary");
  const itemB = await upload(page, recording({ prefix: "BRAVO1" }), "side_b");
  await itemB.click();
  await showRecordingInfo(page);
  await recActive(page, "primary");                                      // B is untouched by A's settings
  await openGroup(page, "BRAVO1 VOLTAGE");
  await gActive(page, "primary");
  await a.item.click();
  await openGroup(page, "VOLTAGE");
  await gActive(page, "secondary");                                      // A keeps its own

  // Removing the group releases its override (the channels follow the recording again).
  const removed = await page.request.delete(`${a.base}/sources/${a.sourceId}/measurement-groups/${g.voltage.id}`);
  expect(removed.status()).toBe(204);
  expect((await getJson(page, `${a.base}/sources/${a.sourceId}/measurement-side`)).channels
    .filter((c) => c.channel_name.startsWith("ALPHA1_V")).map((c) => c.effective_side)).toEqual(["primary", "primary", "primary"]);

  await page.evaluate(() => resetToNewWorkspace());
  await expect(page.locator("#wwRdRecordingList .ww-rd-recording-item")).toHaveCount(0);
  await expect(page.locator("#wwRdSideSection")).toHaveCount(0);
  const gone = await page.request.get(`${a.base}/sources/${a.sourceId}/measurement-side`);
  expect(gone.status()).toBe(404);                                       // the old workspace was released server-side

  const fresh = await upload(page, recording(), "side_a");               // re-upload of the same file starts clean
  await fresh.click();
  await recActive(page, "primary");
  await openGroup(page, "VOLTAGE");
  await gActive(page, "primary");
  await expect(card(page)).not.toContainText("Set manually");
});

test("Recording Info is unchanged by the Group Details work", async ({ page }) => {
  await seed(page);
  await showRecordingInfo(page);
  await expect(page.locator('#wwRdDetailsBody [data-ww-info="metadata"]')).toBeVisible();
  await expect(page.locator("#wwRdSideSection .ww-rd-section-heading")).toHaveText("Measurement Side");
  await expect(page.locator("#wwRdSideSection")).toContainText("Measurement side values for voltage and current.");
  await expect(page.locator("#wwRdDetailsBody")).toHaveClass(/ww-rd-details-body--info/);
  await expect(page.locator("#wwRdDetailsBody")).not.toHaveClass(/ww-rd-details-body--group/);
  await expect(page.locator("#wwRdDetailsBody .ww-rd-gcard")).toHaveCount(0);
  await openGroup(page, "VOLTAGE");
  await expect(page.locator("#wwRdDetailsBody")).toHaveClass(/ww-rd-details-body--group/);
  await showRecordingInfo(page);
  await expect(page.locator("#wwRdDetailsBody")).not.toHaveClass(/ww-rd-details-body--group/);
});

// ------------------------------------------------------------------------------------------------ layout

for (const [width, height] of [[1600, 900], [1280, 720], [900, 800], [600, 800]]) {
  test(`Group Details fits ${width}px without clipping or horizontal overflow`, async ({ page }) => {
    await page.setViewportSize({ width, height });
    await seed(page);
    const narrow = width <= 692;
    for (const kind of ["VOLTAGE", "CURRENT"]) {
      if (narrow) await page.evaluate(() => { wwRdState.narrowPanel = "groups"; wwRdApplyNarrowLayout(); });
      await page.locator("#wwRdGroupsBody .ww-rd-group-item", { hasText: kind }).first().click();
      if (narrow) await page.evaluate(() => { wwRdState.narrowPanel = "details"; wwRdApplyNarrowLayout(); });
      await expect(card(page)).toBeVisible();
      const fit = await page.evaluate(() => {
        const b = document.getElementById("wwRdDetailsBody");
        const box = b.getBoundingClientRect();
        const outside = Array.from(b.querySelectorAll(".ww-rd-gcard, .ww-rd-gcard *"))
          .filter((el) => el.getBoundingClientRect().width > 0 && el.getBoundingClientRect().right > box.right + 1).map((el) => el.className);
        return { overflow: b.scrollWidth - b.clientWidth, outside };
      });
      expect(fit.overflow).toBeLessThanOrEqual(0);
      expect(fit.outside).toEqual([]);
    }
  });
}
