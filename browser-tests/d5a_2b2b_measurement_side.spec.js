// D5A-2B2B -- Recording Details: measurement side (Level 1 recording, Level 2 bay). Real backend (the D5A-2B2A
// resolver and API), real frontend. The page renders only what the backend reports; these tests drive the real
// controls and confirm the backend state with direct API reads.

const { test, expect } = require("./support/test");
const { syntheticComtrade } = require("./support/synthetic_comtrade");

const BACKEND = `http://127.0.0.1:${process.env.PW_BACKEND_PORT || "8000"}`;
const NAMES = ["VA", "VB", "VC", "IA", "IB", "IC"];

// One three-phase bay (ALPHA1_*) whose per-channel P/S markers are chosen by the test.
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

const recRow = (page) => page.locator('#wwRdSideSection [data-ww-side-row="recording"]');
const recBtn = (page, side) => recRow(page).locator(`[data-ww-side-value="${side}"]`);
const bayRow = (page, id) => page.locator(`#wwRdSideSection [data-ww-side-row="bay"][data-ww-side-bay="${id}"]`);
const bayBtn = (page, id, side) => bayRow(page, id).locator(`[data-ww-side-value="${side}"]`);

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

async function bays(page, s) {
  await expect.poll(async () => (await getJson(page, `${s.base}/engineering-contexts`)).length).toBeGreaterThan(0);
  return getJson(page, `${s.base}/engineering-contexts`);
}

// ------------------------------------------------------------------------------------------------ Level 1

test("Level 1: one selector, shown from the recording, correctable, with the contradiction disclosed", async ({ page }) => {
  const s = await seed(page);
  await expect(page.locator("#wwRdSideSection .ww-rd-section-heading")).toHaveText("Measurement side");
  await recActive(page, "primary");
  await expect(recRow(page)).toContainText("From recording");
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
  await expect(recRow(page)).toContainText("From recording");
  await expect(notice).toHaveCount(0);
  expect((await getJson(page, `${s.base}/sources/${s.sourceId}/measurement-side`)).engineer_correction).toBeNull();
});

test("Level 1: mixed, undeclared and voltage/current-split recordings are shown honestly", async ({ page }) => {
  // genuinely mixed phases
  const mixed = await seed(page, { sides: { VB: "S" } }, "side_mixed");
  await expect(recRow(page)).toContainText("declare different sides (5 Primary, 1 Secondary)");
  await expect(recBtn(page, "primary")).toHaveAttribute("aria-checked", "false");
  await expect(recBtn(page, "secondary")).toHaveAttribute("aria-checked", "false");
  await recBtn(page, "primary").click();
  await recActive(page, "primary");
  await expect(page.locator('#wwRdSideSection [data-ww-side-notice="recording-override"]')).toContainText("declares Secondary on 1 channel");
  expect((await getJson(page, `${mixed.base}/sources/${mixed.sourceId}/measurement-side`)).recording_derived.status).toBe("mixed");

  // no P/S declaration at all
  const none = await upload(page, recording({ v: "", i: "", prefix: "BRAVO1" }), "side_none");
  await none.click();
  await expect(recRow(page)).toContainText("does not declare a measurement side");
  await expect(recBtn(page, "primary")).toHaveAttribute("aria-checked", "false");

  // voltage Primary + current Secondary: legitimate, not a conflict
  const split = await upload(page, recording({ v: "P", i: "S", prefix: "CHARLIE1" }), "side_split");
  await split.click();
  await expect(recRow(page)).toContainText("Recorded: voltage primary, current secondary");
  await expect(page.locator("#wwRdSideSection .ww-rd-provenance--unresolved")).toHaveCount(0);
});

test("Level 1: a partially declared recording is inferred until the engineer confirms it", async ({ page }) => {
  const s = await seed(page, { i: "" });
  await recActive(page, "primary");
  await expect(recRow(page)).toContainText("Inferred from the recording's declared channels (3 declare no side)");
  await recBtn(page, "primary").click();                                // confirming the same side is meaningful here
  await expect(recRow(page)).toContainText("Set by engineer");
  expect((await getJson(page, `${s.base}/sources/${s.sourceId}/measurement-side`)).engineer_correction.side).toBe("primary");
});

// ------------------------------------------------------------------------------------------------ Level 2

test("Level 2: bays follow Level 1, a manual choice survives, choosing the inherited side clears it, no Reset, no phases", async ({ page }) => {
  const s = await seed(page);
  const [bay] = await bays(page, s);
  // An auto-suggested bay is not confirmed: it follows the recording and offers confirmation instead of a manual choice.
  await page.reload();
  await page.locator("#mainNavRecordingDetailsBtn").click();
  await page.locator("#wwRdRecordingList .ww-rd-recording-item").first().click();
  await expect(bayRow(page, bay.id)).toBeVisible();
  if (bay.status !== "confirmed") {
    await expect(bayBtn(page, bay.id, "primary")).toBeDisabled();
    await expect(bayRow(page, bay.id)).toContainText("Bay not confirmed; it follows the recording.");
    await bayRow(page, bay.id).getByRole("button", { name: "Confirm bay" }).click();
  }
  await expect(bayRow(page, bay.id)).toContainText("Follows the recording");
  await bayActive(page, bay.id, "primary");

  // Level 1 changes: the bay follows
  await recBtn(page, "secondary").click();
  await bayActive(page, bay.id, "secondary");
  await expect(bayRow(page, bay.id)).toContainText("Follows the recording");

  // manual choice: stays when Level 1 changes again
  await bayBtn(page, bay.id, "primary").click();
  await expect(bayRow(page, bay.id)).toContainText("Set manually");
  await bayActive(page, bay.id, "primary");
  await recBtn(page, "primary").click();                                // Level 1 back to Primary (== evidence, correction cleared)
  await recActive(page, "primary");
  await bayBtn(page, bay.id, "secondary").click();                      // pin it on the other side
  await expect(bayRow(page, bay.id)).toContainText("Set manually");
  await recBtn(page, "secondary").click();                              // unrelated Level 1 change
  await recActive(page, "secondary");
  await bayActive(page, bay.id, "secondary");
  await expect(bayRow(page, bay.id)).toContainText("Set manually");     // the override survived (it happens to equal Level 1 now)

  await recBtn(page, "primary").click();
  await recActive(page, "primary");
  await bayActive(page, bay.id, "secondary");                           // still the engineer's choice
  const view = () => getJson(page, `${s.base}/engineering-contexts/${bay.id}/measurement-side`);
  expect((await view()).override.side).toBe("secondary");

  // choosing the side the bay inherits clears the override: it follows Level 1 again
  await bayBtn(page, bay.id, "primary").click();
  await expect(bayRow(page, bay.id)).toContainText("Follows the recording");
  await bayActive(page, bay.id, "primary");
  expect((await view()).override).toBeNull();

  // no Reset/Revert control and no per-phase selector anywhere in the section
  const labels = await page.locator("#wwRdSideSection button").allTextContents();
  for (const label of labels) expect(["Primary", "Secondary", "Confirm bay"]).toContain(label.trim());
  await expect(page.locator("#wwRdSideSection [role=radiogroup]")).toHaveCount(1 + 1);   // the recording and its one bay
});

test("Level 2: a bay in conflict, and a bay with a manual choice over a declaration, are disclosed", async ({ page }) => {
  const s = await seed(page, { sides: { VB: "S" } });
  const [bay] = await bays(page, s);
  await page.request.patch(`${s.base}/engineering-contexts/${bay.id}`, { data: { status: "confirmed" } });
  await page.locator("#wwRdRecordingList .ww-rd-recording-item").first().click();
  await page.reload();
  await page.locator("#mainNavRecordingDetailsBtn").click();
  await page.locator("#wwRdRecordingList .ww-rd-recording-item").first().click();
  await expect(bayRow(page, bay.id)).toContainText("The voltage channels in this bay declare different sides");
  await expect(bayBtn(page, bay.id, "primary")).toHaveAttribute("aria-checked", "false");
  await bayBtn(page, bay.id, "primary").click();
  await expect(bayRow(page, bay.id)).toContainText("Set manually");
  await expect(page.locator('#wwRdSideSection [data-ww-side-notice="bay-override"]')).toContainText("Differs from the side declared by 1 channel");
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
  await expect(recRow(page)).toContainText("From recording");
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
  await expect(recRow(page)).toContainText("From recording");

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
  await expect(recRow(page)).toContainText("From recording");
  await page.waitForTimeout(2000);                                       // B's late answer arrives
  await recActive(page, "primary");
  await expect(recRow(page)).toContainText("From recording");
  await expect(page.locator('#wwRdSideSection[data-ww-side-source="' + a.sourceId + '"]')).toBeVisible();
});

test("lifecycle: another recording keeps its own state, and a workspace reset leaves nothing behind", async ({ page }) => {
  const a = await seed(page, {}, "side_a");
  await recBtn(page, "secondary").click();
  await expect(recRow(page)).toContainText("Set by engineer");
  const itemB = await upload(page, recording({ prefix: "BRAVO1" }), "side_b");
  await itemB.click();
  await recActive(page, "primary");                                      // B is untouched by A's correction
  await expect(recRow(page)).toContainText("From recording");
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
  await expect(recRow(page)).toContainText("From recording");
});

// ------------------------------------------------------------------------------------------------ layout

test("fits a 13-inch laptop and a narrow window without clipping the controls", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 720 });
  const s = await seed(page);
  await bays(page, s);
  await page.reload();
  await page.locator("#mainNavRecordingDetailsBtn").click();
  await page.locator("#wwRdRecordingList .ww-rd-recording-item").first().click();
  const fits = async () => page.evaluate(() => {
    const body = document.getElementById("wwRdDetailsBody");
    const box = (el) => el.getBoundingClientRect();
    return {
      overflowX: body.scrollWidth > body.clientWidth + 1,
      clipped: Array.from(document.querySelectorAll("#wwRdSideSection .ww-rd-side-btn"))
        .filter((b) => box(b).right > box(body).right + 1 || box(b).left < box(body).left - 1).length,
    };
  });
  await expect(page.locator("#wwRdSideSection .ww-rd-side-btn").first()).toBeVisible();
  expect(await fits()).toEqual({ overflowX: false, clipped: 0 });
  await page.setViewportSize({ width: 600, height: 800 });
  await page.waitForTimeout(300);
  // The narrow layout shows one panel at a time; open the details panel the way the page itself does.
  await page.evaluate(() => { wwRdState.narrowPanel = "details"; wwRdApplyNarrowLayout(); });
  await expect(page.locator("#wwRdDetailsPanel")).toBeVisible();
  await expect(page.locator("#wwRdSideSection .ww-rd-side-btn").first()).toBeVisible();
  expect(await fits()).toEqual({ overflowX: false, clipped: 0 });
});
