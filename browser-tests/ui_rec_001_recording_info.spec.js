// UI-REC-001 -- Recording Info tab of the Recording Details third column: metadata card, Measurement Side card,
// Per-unit Configuration card. Presentation only: these tests check the structure the owner's mockup prescribes and that
// the existing behaviour (Level 1 selection, Review affected groups, tab navigation, Group Details) is untouched.

const { test, expect } = require("./support/test");
const { syntheticComtrade } = require("./support/synthetic_comtrade");

const NAMES = ["VA", "VB", "VC", "IA", "IB", "IC"];

function recording({ side = "P", prefix = "PULU", station = "PULU" } = {}) {
  return syntheticComtrade({
    station, startClock: "18:04:08.817733", triggerClock: "18:04:09.317733", rateHz: 1000, durationS: 0.2,
    channels: NAMES.map((n) => ({
      name: `${prefix}_${n}`, phase: n[1], unit: n[0] === "V" ? "V" : "A", amplitude: n[0] === "V" ? 100 : 5, frequencyHz: 50, side,
    })),
  });
}

// Uploads one more recording and returns its row (found by the source id that is new after the upload).
async function upload(page, files, stem) {
  const ids = () => page.locator("#wwRdRecordingList .ww-rd-recording-item").evaluateAll((els) => els.map((e) => e.getAttribute("data-source-id")));
  const known = await ids();
  await page.locator("#wwRdUploadBtn").click();
  await page.locator("#uploadModalFile_0").setInputFiles({ name: `${stem}.cfg`, mimeType: "application/octet-stream", buffer: files.cfg });
  await page.locator("#uploadModalFile_1").setInputFiles({ name: `${stem}.dat`, mimeType: "application/octet-stream", buffer: files.dat });
  await page.locator("#uploadModalSubmitBtn").click();
  await page.locator("#uploadModalOverlay").waitFor({ state: "hidden" });
  await expect(page.locator("#wwRdRecordingList .ww-rd-recording-item")).toHaveCount(known.length + 1, { timeout: 10000 });
  const fresh = (await ids()).find((id) => !known.includes(id));
  return page.locator(`#wwRdRecordingList .ww-rd-recording-item[data-source-id="${fresh}"]`);
}

async function seed(page, opts) {
  await page.goto("/index.html");
  await page.locator("#mainNavRecordingDetailsBtn").click();
  const files = recording(opts);
  await page.locator("#wwRdUploadBtn").click();
  await page.locator("#uploadModalFile_0").setInputFiles({ name: "PULU_260306_180409317.cfg", mimeType: "application/octet-stream", buffer: files.cfg });
  await page.locator("#uploadModalFile_1").setInputFiles({ name: "PULU_260306_180409317.dat", mimeType: "application/octet-stream", buffer: files.dat });
  await page.locator("#uploadModalSubmitBtn").click();
  await page.locator("#uploadModalOverlay").waitFor({ state: "hidden" });
  await page.locator("#wwRdRecordingList .ww-rd-recording-item").first().click();
  if (page.viewportSize().width <= 692) {   // narrow layout shows one panel at a time: go to the details panel
    await page.evaluate(() => { wwRdState.narrowPanel = "details"; wwRdApplyNarrowLayout(); });
  }
  await expect(page.locator("#wwRdSideSection")).toBeVisible();
}

// The Per-unit card needs the measurement groups, which load after the first render: re-enter the tab to read them.
async function showRecordingInfoAgain(page) {
  await page.locator("#wwRdTabGroupDetails").click();
  await page.locator("#wwRdTabRecordingInfo").click();
}

const body = (page) => page.locator("#wwRdDetailsBody");
const recBtn = (page, side) => page.locator(`#wwRdSideSection [data-ww-side-row="recording"] [data-ww-side-value="${side}"]`);

test("metadata is one bordered two-column card with a divider, real values and no overflow", async ({ page }) => {
  await page.setViewportSize({ width: 1600, height: 900 });
  await seed(page);
  const card = page.locator('#wwRdDetailsBody [data-ww-info="metadata"]');
  await expect(card).toBeVisible();
  const tables = card.locator(".ww-rd-config-table");
  await expect(tables).toHaveCount(2);
  await expect(tables.nth(0).locator(".ww-rd-config-label")).toHaveText(["Station", "Recorder", "Original file", "Format", "File size (cfg+dat)"]);
  await expect(tables.nth(1).locator(".ww-rd-config-label")).toHaveText(["Start time", "Trigger time", "Duration", "Sample rate", "Nominal frequency", "Channels"]);
  await expect(tables.nth(0)).toContainText("PULU_260306_180409317.cfg");
  await expect(tables.nth(1)).toContainText("2026-03-06 18:04:08.817733");
  await expect(tables.nth(1)).toContainText("2026-03-06 18:04:09.317733");
  await expect(tables.nth(1)).toContainText("6 analog / 0 digital");

  const look = await card.evaluate((el) => {
    const second = el.querySelectorAll(".ww-rd-config-table")[1];
    const a = el.querySelectorAll(".ww-rd-config-table")[0].getBoundingClientRect();
    const b = second.getBoundingClientRect();
    return {
      radius: parseFloat(getComputedStyle(el).borderTopLeftRadius), border: getComputedStyle(el).borderTopWidth,
      divider: getComputedStyle(second).borderLeftWidth, sideBySide: b.left >= a.right - 1,
    };
  });
  expect(look.radius).toBeGreaterThanOrEqual(10);
  expect(look.border).toBe("1px");
  expect(look.divider).toBe("1px");
  expect(look.sideBySide).toBe(true);
});

test("Measurement Side is the approved heading, description and pill control only", async ({ page }) => {
  await seed(page);
  const card = page.locator("#wwRdSideSection");
  await expect(card.locator(".ww-rd-section-heading")).toHaveText("Measurement Side");
  await expect(card).toContainText("Measurement side values for voltage and current.");
  await expect(card.locator('[role="radio"]')).toHaveText(["Primary", "Secondary"]);
  await expect(recBtn(page, "primary")).toHaveAttribute("aria-checked", "true");
  // Nothing beyond the mockup in the normal state: no "Recording" label, no status or explanatory line.
  for (const gone of ["Recording", "From recording", "Detected from recording metadata", "Applies to the recording by default", "Set by engineer"]) {
    await expect(card).not.toContainText(gone);
  }
  await expect(card.locator(".ww-rd-provenance")).toHaveCount(0);
  const pill = await card.locator(".ww-rd-side-group").evaluate((el) => ({
    cls: el.className, radius: parseFloat(getComputedStyle(el).borderTopLeftRadius), h: el.getBoundingClientRect().height,
    activeBg: getComputedStyle(el.querySelector(".ww-rd-side-btn--active")).backgroundColor,
    idleBg: getComputedStyle(el.querySelector(".ww-rd-side-btn:not(.ww-rd-side-btn--active)")).backgroundColor,
  }));
  expect(pill.cls).toContain("ww-rd-side-group--pill");
  expect(pill.radius).toBeGreaterThan(15);
  expect(pill.h).toBeGreaterThan(30);
  expect(pill.activeBg).not.toBe(pill.idleBg);
});

test("Level 1 selection, correction and its disclosure still work and are saved through the existing API", async ({ page }) => {
  await seed(page);
  await recBtn(page, "secondary").click();
  await expect(recBtn(page, "secondary")).toHaveAttribute("aria-checked", "true");
  await expect(page.locator('#wwRdSideSection [data-ww-side-notice="recording-override"]')).toContainText("The recording declares Primary on 6 channels");
  await expect(page.locator("#wwRdSideSection")).toContainText("Set by engineer");   // an exceptional state keeps its compact message
  await recBtn(page, "primary").click();
  await expect(recBtn(page, "primary")).toHaveAttribute("aria-checked", "true");
  await expect(page.locator("#wwRdSideSection .ww-rd-provenance")).toHaveCount(0);
});

test("an undeclared recording still asks for a side (unresolved evidence is not hidden)", async ({ page }) => {
  await seed(page, { side: "" });
  await expect(page.locator("#wwRdSideSection")).toContainText("does not declare a measurement side");
  await expect(page.locator('#wwRdSideSection [role="radio"][aria-checked="true"]')).toHaveCount(0);
});

test("Per-unit Configuration card shows the real warning, and Review affected groups navigates", async ({ page }) => {
  await seed(page);
  await showRecordingInfoAgain(page);
  const card = page.locator("#wwRdDetailsBody .ww-rd-pu-config-section");
  await expect(card).toBeVisible();
  await expect(card.locator(".ww-rd-section-heading")).toHaveText("Per-unit Configuration");
  await expect(card.locator(".ww-rd-pu-config-issue")).toHaveText("1 voltage group needs a nominal voltage base.");
  await expect(card.locator(".ww-rd-pu-config-issue svg")).toBeVisible();
  await expect(card.locator(".ww-rd-pu-review-btn")).toHaveText("Review affected groups");
  // Existing behaviour, unchanged: filter the group list to the voltage groups that need attention.
  await card.locator(".ww-rd-pu-review-btn").click();
  await expect(page.locator('#wwRdGroupKindFilter button[data-kind="voltage"]')).toHaveAttribute("aria-pressed", "true");
});

test("the Per-unit Configuration card is there on the first Recording Info load, with no loop and no request of its own", async ({ page }) => {
  await page.goto("/index.html");
  await page.locator("#mainNavRecordingDetailsBtn").click();
  const files = recording();
  await page.locator("#wwRdUploadBtn").click();
  await page.locator("#uploadModalFile_0").setInputFiles({ name: "PULU_260306_180409317.cfg", mimeType: "application/octet-stream", buffer: files.cfg });
  await page.locator("#uploadModalFile_1").setInputFiles({ name: "PULU_260306_180409317.dat", mimeType: "application/octet-stream", buffer: files.dat });
  await page.locator("#uploadModalSubmitBtn").click();
  await page.locator("#uploadModalOverlay").waitFor({ state: "hidden" });
  await page.reload();                                  // a first load: nothing cached in the page
  await page.locator("#mainNavRecordingDetailsBtn").click();
  await page.evaluate(() => {                           // count how often the details are drawn
    window.__rdDraws = 0;
    const original = window.wwRdRenderDetails;
    window.wwRdRenderDetails = function () { window.__rdDraws += 1; return original.apply(this, arguments); };
  });
  await page.locator("#wwRdRecordingList .ww-rd-recording-item").first().click();
  // No tab switch, no second click: the card appears as soon as the groups are known.
  const card = page.locator("#wwRdDetailsBody .ww-rd-pu-config-section");
  await expect(card).toBeVisible();
  await expect(card.locator(".ww-rd-pu-config-issue")).toHaveText("1 voltage group needs a nominal voltage base.");
  const requests = [];
  page.on("request", (r) => { if (r.method() === "GET" && r.url().includes("/api/v1/")) requests.push(r.url()); });
  const draws = await page.evaluate(() => window.__rdDraws);
  await page.waitForTimeout(1200);
  expect(await page.evaluate(() => window.__rdDraws)).toBe(draws);        // settled: no re-render loop
  expect(draws).toBeLessThanOrEqual(6);
  expect(requests.filter((u) => /measurement-groups$|measurement-side$/.test(u))).toEqual([]);   // and nothing is re-requested
  await expect(page.locator("#wwRdSideSection")).toHaveCount(1);                      // no duplicated sections
  await expect(page.locator("#wwRdDetailsBody .ww-rd-pu-config-section")).toHaveCount(1);
});

test("groups arriving late never pull the engineer out of Group Details or onto another recording", async ({ page }) => {
  await seed(page);
  const second = await upload(page, recording({ prefix: "BRAVO1" }), "side_b");
  let held = false;
  await page.route("**/measurement-groups", async (route) => {
    if (route.request().method() === "GET" && !held) { held = true; await new Promise((r) => setTimeout(r, 1200)); }
    await route.continue();
  });
  await second.click();                                  // groups for this recording are slow
  await page.locator("#wwRdTabGroupDetails").click();    // the engineer moves to Group Details meanwhile
  await page.waitForTimeout(1800);
  await expect(page.locator("#wwRdTabGroupDetails")).toHaveAttribute("aria-selected", "true");
  await expect(body(page)).toHaveClass(/ww-rd-details-body--group/);
  await expect(body(page).locator(".ww-rd-info-card")).toHaveCount(0);
});

test("header and tabs keep their behaviour; Group Details keeps its own layout", async ({ page }) => {
  await seed(page);
  await expect(page.locator("#wwRdRecordingContextInfo")).toContainText("PULU");
  await expect(page.locator("#wwRdRecordingContextInfo .ww-rd-group-badge")).toHaveText("COMTRADE");
  await expect(page.locator("#wwRdViewWaveformBtn")).toBeEnabled();
  await expect(page.locator("#wwRdTabRecordingInfo")).toHaveAttribute("aria-selected", "true");

  await page.locator("#wwRdGroupsBody .ww-rd-group-item", { hasText: "VOLTAGE" }).first().click();
  await expect(page.locator("#wwRdTabGroupDetails")).toHaveAttribute("aria-selected", "true");
  // Group Details is not on the Recording Info card surface and has no Recording Info cards; it has its own Level 2 card.
  await expect(body(page)).not.toHaveClass(/ww-rd-details-body--info/);
  await expect(body(page).locator(".ww-rd-info-card")).toHaveCount(0);
  await expect(page.locator("#wwRdSideGroupSection")).toBeVisible();

  await page.locator("#wwRdTabRecordingInfo").click();
  await expect(body(page)).toHaveClass(/ww-rd-details-body--info/);
  await expect(page.locator("#wwRdSideSection")).toBeVisible();
});

for (const [width, height] of [[1600, 900], [1280, 800], [1000, 800], [900, 800], [640, 800]]) {
  test(`no horizontal overflow or clipping at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height });
    await seed(page);
    await showRecordingInfoAgain(page);
    await expect(page.locator("#wwRdDetailsBody .ww-rd-pu-config-section")).toBeVisible();
    const fit = await page.evaluate(() => {
      const b = document.getElementById("wwRdDetailsBody");
      const box = b.getBoundingClientRect();
      const wide = Array.from(b.querySelectorAll(".ww-rd-info-card, .ww-rd-info-card *"))
        .filter((el) => el.getBoundingClientRect().right > box.right + 1).map((el) => el.className);
      return { overflow: b.scrollWidth - b.clientWidth, wide };
    });
    expect(fit.overflow).toBeLessThanOrEqual(0);
    expect(fit.wide).toEqual([]);
  });
}
