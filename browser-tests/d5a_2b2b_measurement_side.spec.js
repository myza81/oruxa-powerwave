// D5A-2B2B -- Recording Details: measurement side. Level 1 (recording) lives in Recording Info; Level 2 (the bay, within the
// selected recording) lives in Group Details. Real backend (the D5A-2B2A resolver and API), real frontend. The page renders only
// what the backend reports; these tests drive the real controls and confirm the backend state with direct API reads.

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
  await expect(page.locator("#wwRdSideSection")).toBeVisible();
  return { sourceId, workspaceId, base, item };
}

// ---- Level 1 (Recording Info) ----
const recRow = (page) => page.locator('#wwRdSideSection [data-ww-side-row="recording"]');
const recBtn = (page, side) => recRow(page).locator(`[data-ww-side-value="${side}"]`);

// ---- Level 2 (Group Details) ----
const baySection = (page) => page.locator("#wwRdSideBaySection");
const bayRow = (page, id) => baySection(page).locator(`[data-ww-side-row="bay"][data-ww-side-bay="${id}"]`);
const bayBtn = (page, id, side) => bayRow(page, id).locator(`[data-ww-side-value="${side}"]`);

async function openGroup(page, label) {
  await page.locator("#wwRdGroupsBody .ww-rd-group-item", { hasText: label }).first().click();
  await expect(baySection(page)).toBeVisible();
}
async function showRecordingInfo(page) {
  await page.locator("#wwRdTabRecordingInfo").click();
  await expect(page.locator("#wwRdSideSection")).toBeVisible();
}
async function showGroupDetails(page) {
  await page.locator("#wwRdTabGroupDetails").click();
  await expect(baySection(page)).toBeVisible();
}

async function expectActive(locatorFor, side, other) {
  await expect(locatorFor(side)).toHaveAttribute("aria-checked", "true");
  await expect(locatorFor(other)).toHaveAttribute("aria-checked", "false");
}
const recActive = (page, side) => expectActive((s) => recBtn(page, s), side, side === "primary" ? "secondary" : "primary");
const bayActive = (page, id, side) => expectActive((s) => bayBtn(page, id, s), side, side === "primary" ? "secondary" : "primary");

async function getJson(page, url) {
  const response = await page.request.get(url);
  expect(response.ok(), await response.text()).toBeTruthy();
  return response.json();
}

async function contexts(page, s) {
  await expect.poll(async () => (await getJson(page, `${s.base}/engineering-contexts`)).length).toBeGreaterThan(0);
  return getJson(page, `${s.base}/engineering-contexts`);
}

const assoc = (page, s, ctx, src) => getJson(page, `${s.base}/sources/${src || s.sourceId}/engineering-contexts/${ctx}/measurement-side`);

// Confirms a (suggested) bay through the real UI: review, then the explicit Confirm bay action.
async function confirmBayInUi(page, id) {
  await bayRow(page, id).getByRole("button", { name: "Confirm bay…" }).click();
  await expect(bayRow(page, id).locator("[data-ww-side-review]")).toBeVisible();
  await bayRow(page, id).locator('[data-ww-side-action="confirm-bay"]').click();
  await expect(bayBtn(page, id, "primary")).toBeEnabled();
}

// ------------------------------------------------------------------------------------------------ Level 1 (Recording Info)

test("Level 1: one selector, shown from the recording, correctable, with the contradiction disclosed", async ({ page }) => {
  const s = await seed(page);
  await expect(page.locator("#wwRdSideSection .ww-rd-section-heading")).toHaveText("Measurement Side");
  await expect(page.locator("#wwRdSideBaySection")).toHaveCount(0);       // no bay controls in Recording Info
  await expect(page.locator('#wwRdSideSection [data-ww-side-row="bay"]')).toHaveCount(0);
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
  await expect(recRow(page)).not.toContainText("Set by engineer"); // UI-REC-001: the normal state carries no provenance line
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

// ------------------------------------------------------------------------------------------------ Level 2 (Group Details)

test("Level 2: the bay setting is in Group Details, shared by the voltage and current groups, follows Level 1, survives, clears, no Reset", async ({ page }) => {
  const s = await seed(page);
  const [bay] = await contexts(page, s);
  await page.reload();
  await page.locator("#mainNavRecordingDetailsBtn").click();
  await page.locator("#wwRdRecordingList .ww-rd-recording-item").first().click();
  await openGroup(page, "VOLTAGE");
  await expect(page.locator("#wwRdSideSection")).toHaveCount(0);        // Level 1 is not in Group Details
  await expect(bayRow(page, bay.id)).toBeVisible();
  if (bay.status !== "confirmed") {
    await expect(bayBtn(page, bay.id, "primary")).toBeDisabled();
    await expect(bayRow(page, bay.id)).toContainText("Bay not confirmed; it follows the recording.");
    await confirmBayInUi(page, bay.id);
  }
  await expect(bayRow(page, bay.id)).toContainText("Follows the recording");
  await bayActive(page, bay.id, "primary");

  // The current group shows the SAME bay setting (one setting per bay, not per Voltage/Current group)
  await openGroup(page, "CURRENT");
  await expect(bayRow(page, bay.id)).toBeVisible();
  await bayActive(page, bay.id, "primary");
  await openGroup(page, "VOLTAGE");

  // Level 1 changes (in Recording Info): the bay follows
  await showRecordingInfo(page);
  await recBtn(page, "secondary").click();
  await recActive(page, "secondary");
  await showGroupDetails(page);
  await bayActive(page, bay.id, "secondary");
  await expect(bayRow(page, bay.id)).toContainText("Follows the recording");

  // manual choice: stays when Level 1 changes again
  await bayBtn(page, bay.id, "primary").click();
  await expect(bayRow(page, bay.id)).toContainText("Set manually");
  await bayActive(page, bay.id, "primary");
  await showRecordingInfo(page);
  await recBtn(page, "primary").click();                                // Level 1 back to Primary (== evidence, correction cleared)
  await recActive(page, "primary");
  await showGroupDetails(page);
  await bayBtn(page, bay.id, "secondary").click();                      // pin it on the other side
  await expect(bayRow(page, bay.id)).toContainText("Set manually");
  await showRecordingInfo(page);
  await recBtn(page, "secondary").click();                              // unrelated Level 1 change
  await recActive(page, "secondary");
  await showGroupDetails(page);
  await bayActive(page, bay.id, "secondary");
  await expect(bayRow(page, bay.id)).toContainText("Set manually");     // the override survived (it happens to equal Level 1 now)

  await showRecordingInfo(page);
  await recBtn(page, "primary").click();
  await recActive(page, "primary");
  await showGroupDetails(page);
  await bayActive(page, bay.id, "secondary");                           // still the engineer's choice
  expect((await assoc(page, s, bay.id)).override.side).toBe("secondary");

  // choosing the side the bay inherits clears the override: it follows Level 1 again
  await bayBtn(page, bay.id, "primary").click();
  await expect(bayRow(page, bay.id)).toContainText("Follows the recording");
  await bayActive(page, bay.id, "primary");
  expect((await assoc(page, s, bay.id)).override).toBeNull();

  // no Reset/Revert control and no per-phase selector anywhere in the section
  const labels = await baySection(page).locator("button").allTextContents();
  for (const label of labels) expect(["Primary", "Secondary"]).toContain(label.trim());
  await expect(baySection(page).locator("[role=radiogroup]")).toHaveCount(1);
});

test("Confirm bay is explicit: the channels and their phase evidence are reviewed, cancelling changes nothing, confirming changes only the status", async ({ page }) => {
  const s = await seed(page);
  const [bay] = await contexts(page, s);
  test.skip(bay.status === "confirmed", "this bay was created confirmed; nothing to confirm");
  await openGroup(page, "VOLTAGE");
  const before = await getJson(page, `${s.base}/engineering-contexts/${bay.id}`);
  await expect(bayBtn(page, bay.id, "secondary")).toBeDisabled();
  await bayRow(page, bay.id).getByRole("button", { name: "Confirm bay…" }).click();
  const review = bayRow(page, bay.id).locator("[data-ww-side-review]");
  await expect(review).toContainText("Confirm that these channels belong to");
  await expect(review).toContainText("ALPHA1_VA");
  await expect(review).toContainText("Phase evidence");
  await expect(review).toContainText("The channels and phases are not changed.");
  if (bay.status === "needs_review") await expect(review.locator('[data-ww-side-notice="needs-review"]')).toBeVisible();

  await review.getByRole("button", { name: "Cancel" }).click();          // nothing is confirmed by looking
  await expect(review).toHaveCount(0);
  await expect(bayBtn(page, bay.id, "secondary")).toBeDisabled();
  expect((await getJson(page, `${s.base}/engineering-contexts/${bay.id}`)).status).toBe(bay.status);

  await bayRow(page, bay.id).getByRole("button", { name: "Confirm bay…" }).click();
  await review.getByRole("button", { name: "Confirm bay", exact: true }).click();
  await expect(bayBtn(page, bay.id, "secondary")).toBeEnabled();
  const after = await getJson(page, `${s.base}/engineering-contexts/${bay.id}`);
  expect(after.status).toBe("confirmed");
  expect({ ...after, status: null }).toEqual({ ...before, status: null });   // members, phases and phase evidence untouched

  // Analysis keeps listing the same bay; only its status badge changes (it re-reads contexts on every visit)
  await page.locator("#mainNavAnalysisBtn").click();
  await page.locator("#wwAnalysisTypeOvercurrentBtn").click();
  await expect(page.locator(`#wwOvercurrentContextSelect option[value="${bay.id}"]`)).toHaveCount(1);
  if ((await page.locator("#wwOvercurrentContextSelect").inputValue()) === bay.id) {
    await expect(page.locator("#wwOvercurrentContextBadge")).toContainText("Confirmed");
  }
});

test("Level 2: a bay in conflict, and a bay with a manual choice over a declaration, are disclosed", async ({ page }) => {
  const s = await seed(page, { sides: { VB: "S" } });
  const [bay] = await contexts(page, s);
  await page.request.patch(`${s.base}/engineering-contexts/${bay.id}`, { data: { status: "confirmed" } });
  await page.reload();
  await page.locator("#mainNavRecordingDetailsBtn").click();
  await page.locator("#wwRdRecordingList .ww-rd-recording-item").first().click();
  await openGroup(page, "VOLTAGE");
  await expect(bayRow(page, bay.id)).toContainText("The voltage channels in this bay declare different sides");
  await expect(bayBtn(page, bay.id, "primary")).toHaveAttribute("aria-checked", "false");
  await bayBtn(page, bay.id, "primary").click();
  await expect(bayRow(page, bay.id)).toContainText("Set manually");
  await expect(baySection(page).locator('[data-ww-side-notice="bay-override"]')).toContainText("Differs from the side declared by 1 channel");
});

test("a group that is not in any bay says so and offers no control", async ({ page }) => {
  const s = await seed(page);
  for (const c of await contexts(page, s)) await page.request.delete(`${s.base}/engineering-contexts/${c.id}`);
  await page.reload();
  await page.locator("#mainNavRecordingDetailsBtn").click();
  await page.locator("#wwRdRecordingList .ww-rd-recording-item").first().click();
  await openGroup(page, "VOLTAGE");
  await expect(baySection(page)).toContainText("not part of a bay, so it follows the recording");
  await expect(baySection(page).locator("[role=radiogroup]")).toHaveCount(0);
});

// ------------------------------------------------------------------------------------------------ multi-recording bays

test("one bay in two recordings: each recording keeps its own side; a Level 2 change for one never touches the other", async ({ page }) => {
  const a = await seed(page, { v: "P", i: "P", prefix: "ALPHA1" }, "side_a");           // KPDN1 is Primary here ...
  const itemB = await upload(page, recording({ v: "S", i: "S", prefix: "BRAVO1" }), "side_b");   // ... and Secondary here
  const idB = await itemB.getAttribute("data-source-id");
  for (const c of await contexts(page, a)) await page.request.delete(`${a.base}/engineering-contexts/${c.id}`);
  const created = await page.request.post(`${a.base}/engineering-contexts`, { data: { display_name: "KPDN1", status: "confirmed", members: [
    ...["VA", "IA"].map((n) => ({ channel_ref: { kind: "source", source_id: a.sourceId, channel_name: `ALPHA1_${n}` }, phase: "A", phase_source: "engineer_confirmed" })),
    ...["VA", "IA"].map((n) => ({ channel_ref: { kind: "source", source_id: idB, channel_name: `BRAVO1_${n}` }, phase: "A", phase_source: "engineer_confirmed" })),
  ] } });
  expect(created.ok(), await created.text()).toBeTruthy();
  const kpdn1 = (await created.json()).id;

  await page.reload();
  await page.locator("#mainNavRecordingDetailsBtn").click();
  await itemFor(page, a.sourceId).click();
  await openGroup(page, "ALPHA1 VOLTAGE");
  await bayActive(page, kpdn1, "primary");
  await expect(bayRow(page, kpdn1)).toContainText("Follows the recording");

  await bayBtn(page, kpdn1, "secondary").click();                        // Level 2 for recording A only
  await expect(bayRow(page, kpdn1)).toContainText("Set manually");
  await bayActive(page, kpdn1, "secondary");
  expect((await assoc(page, a, kpdn1, a.sourceId)).override.side).toBe("secondary");
  const other = await assoc(page, a, kpdn1, idB);
  expect([other.override, other.effective_side, other.inherited_recording_side]).toEqual([null, "secondary", "secondary"]);

  await itemFor(page, idB).click();                                      // recording B: its own association, untouched
  await openGroup(page, "BRAVO1 VOLTAGE");
  await bayActive(page, kpdn1, "secondary");
  await expect(bayRow(page, kpdn1)).toContainText("Follows the recording");
  await bayBtn(page, kpdn1, "primary").click();                          // Level 2 for recording B only
  await expect(bayRow(page, kpdn1)).toContainText("Set manually");
  expect((await assoc(page, a, kpdn1, a.sourceId)).effective_side).toBe("secondary");   // A unchanged by B

  // each recording's Level 1 reaches only its own non-overridden bay associations
  await showRecordingInfo(page);
  await recBtn(page, "primary").click();                                 // B's Level 1 -> Primary (its evidence says Secondary)
  await expect(recRow(page)).toContainText("Set by engineer");
  expect((await assoc(page, a, kpdn1, a.sourceId)).effective_side).toBe("secondary");
  expect((await assoc(page, a, kpdn1, idB)).override.side).toBe("primary");
});

// ------------------------------------------------------------------------------------------------ CT/VT groups spanning bays

test("a group whose channels sit in two bays is disclosed, and different sides make its conversion authority ambiguous", async ({ page }) => {
  const s = await seed(page);
  for (const c of await contexts(page, s)) await page.request.delete(`${s.base}/engineering-contexts/${c.id}`);
  const make = async (name, names) => (await (await page.request.post(`${s.base}/engineering-contexts`, { data: {
    display_name: name, status: "confirmed",
    members: names.map((n) => ({ channel_ref: { kind: "source", source_id: s.sourceId, channel_name: `ALPHA1_${n}` }, phase: n[1], phase_source: "engineer_confirmed" })),
  } })).json()).id;
  const k1 = await make("KPDN1", ["VA", "IA"]);
  const k2 = await make("KPDN2", ["VB", "IB"]);
  await page.reload();
  await page.locator("#mainNavRecordingDetailsBtn").click();
  await page.locator("#wwRdRecordingList .ww-rd-recording-item").first().click();
  await openGroup(page, "VOLTAGE");                                      // one voltage group serving both bays
  await expect(baySection(page).locator("[role=radiogroup]")).toHaveCount(2);
  await expect(baySection(page).locator('[data-ww-side-notice="group-spans"]')).toContainText("KPDN1, KPDN2");
  await expect(baySection(page).locator('[data-ww-side-notice="group-spans"]')).toContainText("share one measurement side");
  await expect(baySection(page).locator('[data-ww-side-notice="group-ambiguous"]')).toHaveCount(0);

  await bayBtn(page, k1, "secondary").click();                          // the two bays now sit on different sides
  const ambiguous = baySection(page).locator('[data-ww-side-notice="group-ambiguous"]');
  await expect(ambiguous).toContainText("different or unresolved measurement sides");
  await expect(ambiguous).toContainText("blocked until this is resolved");
  const view = await assoc(page, s, k2);
  expect(view.group_ownership.find((o) => o.kind === "voltage")).toMatchObject({ status: "spans_bays_ambiguous", conversion_authority_ambiguous: true });
  expect(view.strict_usable).toBe(false);
  await bayBtn(page, k1, "primary").click();                            // resolved again: back to one shared side
  await expect(baySection(page).locator('[data-ww-side-notice="group-spans"]')).toBeVisible();
  await expect(ambiguous).toHaveCount(0);
});

// ------------------------------------------------------------------------------------------------ races and isolation

test("a quick second choice wins: selections are applied in order and the view shows the last one", async ({ page }) => {
  const s = await seed(page);
  let puts = 0;
  await page.route("**/measurement-side", async (route) => {
    if (route.request().method() === "PUT" && puts++ === 0) await new Promise((r) => setTimeout(r, 900));   // first save is slow
    await route.continue();
  });
  await recBtn(page, "secondary").click();
  await recBtn(page, "primary").click();
  await recActive(page, "primary");
  await expect.poll(() => puts).toBe(2);
  await page.waitForTimeout(1500);
  await recActive(page, "primary");                                      // the slow first save never overwrote the second
  await expect(recRow(page)).not.toContainText("Set by engineer"); // UI-REC-001: the normal state carries no provenance line
  expect((await getJson(page, `${s.base}/sources/${s.sourceId}/measurement-side`)).engineer_correction).toBeNull();
});

test("a slow read for one recording cannot appear on another", async ({ page }) => {
  const a = await seed(page, {}, "side_a");
  const itemB = await upload(page, recording({ prefix: "BRAVO1" }), "side_b");
  await itemB.click();
  await recBtn(page, "secondary").click();                               // B carries a correction, A does not
  await expect(recRow(page)).toContainText("Set by engineer");
  await a.item.click();
  await recActive(page, "primary");
  await expect(recRow(page)).not.toContainText("Set by engineer"); // UI-REC-001: the normal state carries no provenance line

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
  await expect(recRow(page)).not.toContainText("Set by engineer"); // UI-REC-001: the normal state carries no provenance line
  await page.waitForTimeout(2000);                                       // B's late answer arrives
  await recActive(page, "primary");
  await expect(recRow(page)).not.toContainText("Set by engineer"); // UI-REC-001: the normal state carries no provenance line
  await expect(page.locator('#wwRdSideSection[data-ww-side-source="' + a.sourceId + '"]')).toBeVisible();
});

test("lifecycle: another recording keeps its own state, and a workspace reset leaves nothing behind", async ({ page }) => {
  const a = await seed(page, {}, "side_a");
  await recBtn(page, "secondary").click();
  await expect(recRow(page)).toContainText("Set by engineer");
  const itemB = await upload(page, recording({ prefix: "BRAVO1" }), "side_b");
  await itemB.click();
  await recActive(page, "primary");                                      // B is untouched by A's correction
  await expect(recRow(page)).not.toContainText("Set by engineer"); // UI-REC-001: the normal state carries no provenance line
  await a.item.click();
  await recActive(page, "secondary");                                    // A keeps it

  await page.evaluate(() => resetToNewWorkspace());
  await expect(page.locator("#wwRdRecordingList .ww-rd-recording-item")).toHaveCount(0);
  await expect(page.locator("#wwRdSideSection")).toHaveCount(0);
  const gone = await page.request.get(`${a.base}/sources/${a.sourceId}/measurement-side`);
  expect(gone.status()).toBe(404);                                       // the old workspace was released server-side

  const fresh = await upload(page, recording(), "side_a");               // re-upload of the same file starts clean
  await fresh.click();
  await recActive(page, "primary");
  await expect(recRow(page)).not.toContainText("Set by engineer"); // UI-REC-001: the normal state carries no provenance line
});

// ------------------------------------------------------------------------------------------------ layout

test("fits a 13-inch laptop and a narrow window without clipping the controls", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 720 });
  const s = await seed(page);
  const [bay] = await contexts(page, s);
  await page.request.patch(`${s.base}/engineering-contexts/${bay.id}`, { data: { status: "confirmed" } });
  await page.reload();
  await page.locator("#mainNavRecordingDetailsBtn").click();
  await page.locator("#wwRdRecordingList .ww-rd-recording-item").first().click();
  const fits = async (section) => page.evaluate((sel) => {
    const body = document.getElementById("wwRdDetailsBody");
    const box = (el) => el.getBoundingClientRect();
    return {
      overflowX: body.scrollWidth > body.clientWidth + 1,
      clipped: Array.from(document.querySelectorAll(`${sel} .ww-rd-side-btn`))
        .filter((b) => box(b).right > box(body).right + 1 || box(b).left < box(body).left - 1).length,
    };
  }, section);
  await expect(page.locator("#wwRdSideSection .ww-rd-side-btn").first()).toBeVisible();
  expect(await fits("#wwRdSideSection")).toEqual({ overflowX: false, clipped: 0 });
  await openGroup(page, "VOLTAGE");
  await expect(baySection(page).locator(".ww-rd-side-btn").first()).toBeVisible();
  expect(await fits("#wwRdSideBaySection")).toEqual({ overflowX: false, clipped: 0 });

  await page.setViewportSize({ width: 600, height: 800 });
  await page.waitForTimeout(300);
  // The narrow layout shows one panel at a time; open the details panel the way the page itself does.
  await page.evaluate(() => { wwRdState.narrowPanel = "details"; wwRdApplyNarrowLayout(); });
  await expect(page.locator("#wwRdDetailsPanel")).toBeVisible();
  await expect(baySection(page).locator(".ww-rd-side-btn").first()).toBeVisible();
  expect(await fits("#wwRdSideBaySection")).toEqual({ overflowX: false, clipped: 0 });
  await showRecordingInfo(page);
  expect(await fits("#wwRdSideSection")).toEqual({ overflowX: false, clipped: 0 });
});
