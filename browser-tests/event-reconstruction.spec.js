// Event Reconstruction -- Slice 0 shell (DEC-123), Slice 2 selection
// workflow (DEC-125) and the record model (DEC-128).
//
// Covers the main-menu entry, the page shell and its Waveform visual
// language, the left-panel record/member workflow (chronological record
// list, eligibility, add/remove, reference, corrections, stale (removed)
// records, large-gap warning, clear), independent records that overlap in
// time (never merged, unlike Waveform Time Groups), and the boundary with
// Waveform: Event Reconstruction never changes Waveform, Time Groups or
// Synchronise Sources state, and plots nothing yet.

const { test, expect } = require("@playwright/test");
const path = require("path");
const fs = require("fs");

const FIXTURES = path.join(__dirname, "..", "backend", "tests", "fixtures", "comtrade");
const BACKEND = `http://127.0.0.1:${process.env.PW_BACKEND_PORT || "8000"}`;

function collectConsoleErrors(page) {
  const errors = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") errors.push(msg.text());
  });
  page.on("pageerror", (err) => errors.push(`pageerror: ${err.message}`));
  return errors;
}

// synth_ascii.cfg with its station name and start/trigger lines replaced,
// so each upload is a recognisable, independently imported record.
function cfgBuffer(station, startClock) {
  const lines = fs.readFileSync(path.join(FIXTURES, "synth_ascii.cfg"), "latin1").split(/\r?\n/);
  lines[0] = lines[0].replace("SYNTH_STATION", station);
  const stampLines = lines.map((l, i) => (/^\d{2}\/\d{2}\/\d{4},/.test(l) ? i : -1)).filter((i) => i >= 0);
  const [h, m, s] = startClock.split(":");
  const startSeconds = Number(h) * 3600 + Number(m) * 60 + Number(s);
  const fmt = (t) => {
    const hh = String(Math.floor(t / 3600)).padStart(2, "0");
    const mm = String(Math.floor((t % 3600) / 60)).padStart(2, "0");
    const ss = (t % 60).toFixed(6).padStart(9, "0");
    return `06/03/2026,${hh}:${mm}:${ss}`;
  };
  lines[stampLines[0]] = fmt(startSeconds);
  lines[stampLines[1]] = fmt(startSeconds + 0.005);
  return Buffer.from(lines.join("\r\n"), "latin1");
}

async function upload(page, station, startClock) {
  await page.locator("#mainNavRecordingsBtn").click();
  await page.locator("#recordingsUploadBtn, #recordingsEmptyUploadBtn").first().click();
  await expect(page.locator("#uploadModalOverlay")).toBeVisible();
  await page.locator("#uploadModalFile_0").setInputFiles({ name: `${station}.cfg`, mimeType: "application/octet-stream", buffer: cfgBuffer(station, startClock) });
  await page.locator("#uploadModalFile_1").setInputFiles({ name: `${station}.dat`, mimeType: "application/octet-stream", buffer: fs.readFileSync(path.join(FIXTURES, "synth_ascii.dat")) });
  await page.locator("#uploadModalSubmitBtn").click();
  await page.locator("#uploadModalOverlay").waitFor({ state: "hidden" });
}

async function openEventReconstruction(page) {
  await page.locator("#mainNavEventReconstructionBtn").click();
  await expect(page.locator("#pageEventReconstruction")).toBeVisible();
}

async function workspaceId(page) {
  return page.evaluate(() => localStorage.getItem("powerwave.workspaceId"));
}

async function api(page, pathSuffix) {
  const resp = await page.request.get(`${BACKEND}/api/v1/workspaces/${await workspaceId(page)}${pathSuffix}`);
  expect(resp.ok()).toBeTruthy();
  return resp.json();
}

function escapeRegExp(text) {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

// Rows are matched by their exact recording name, so "STN_FAR" never
// matches "STN_FAR_TWIN".
const exactName = (page, station) => page.locator(".source-recording-name", { hasText: new RegExp(`^${escapeRegExp(station)}$`) });
const recordRow = (page, station) => page.locator("#wwErRecordsPanel .ww-er-record-row", { has: exactName(page, station) });
const memberRow = (page, station) => page.locator("#wwErMembersPanel .ww-er-member-row", { has: exactName(page, station) });
const staleRows = (page) => page.locator('#wwErMembersPanel .ww-er-member-row[data-member-status="stale"]');

async function addRecord(page, station) {
  await recordRow(page, station).locator('button[data-er-action="add-record"]').click();
  await expect(recordRow(page, station).getByText("In reconstruction")).toBeVisible();
}

async function setCorrection(page, station, ms) {
  const row = memberRow(page, station);
  await row.locator("input[data-er-correction-input]").fill(String(ms));
  await row.locator('button[data-er-action="set-correction"]').click();
}

async function sourceIdFor(page, station) {
  const sources = await api(page, "/sources");
  return sources.find((s) => s.station_name === station).source_id;
}

// Removes a recording through the Recordings page, as an engineer would.
async function removeRecording(page, station) {
  const sourceId = await sourceIdFor(page, station);
  await page.locator("#mainNavRecordingsBtn").click();
  await page.locator(`button[data-action="remove"][data-source-id="${sourceId}"]`).click();
  await expect(page.locator("#confirmOverlay")).toBeVisible();
  await page.locator("#confirmRemoveBtn").click();
  await expect(page.locator("#confirmOverlay")).toBeHidden();
  await expect(page.locator(`#recordingsTableBody tr[data-source-id="${sourceId}"]`)).toHaveCount(0);
  return sourceId;
}

test.describe("Event Reconstruction -- Slice 0 shell", () => {
  test("menu entry sits immediately after Waveform and switches pages normally", async ({ page }) => {
    const consoleErrors = collectConsoleErrors(page);
    await page.goto("/index.html");

    const navOrder = await page.locator("#mainSidebarMenu .shell-nav-list .shell-nav-item").evaluateAll((items) =>
      items.map((item) => item.id)
    );
    expect(navOrder).toEqual([
      "mainNavRecordingsBtn",
      "mainNavWaveformBtn",
      "mainNavEventReconstructionBtn",
      "mainNavTableBtn",
      "mainNavCalculatedChannelsBtn",
      "mainNavAnalysisBtn",
      "mainNavComplianceBtn",
      "mainNavCalculatorBtn",
    ]);
    await expect(page.locator("#mainNavEventReconstructionBtn .shell-nav-label")).toHaveText("Event Reconstruction");

    const erNav = page.locator("#mainNavEventReconstructionBtn");
    await erNav.click();
    await expect(page.locator("#pageEventReconstruction")).toBeVisible();
    await expect(erNav).toHaveAttribute("aria-current", "page");
    await expect(page.locator("#workspaceRow")).toBeHidden();
    await expect(page.locator("#pageRecordings")).toBeHidden();

    const pages = [
      ["#mainNavWaveformBtn", "#workspaceRow"],
      ["#mainNavRecordingsBtn", "#pageRecordings"],
      ["#mainNavCalculatedChannelsBtn", "#pageCalculatedChannels"],
      ["#mainNavAnalysisBtn", "#pageAnalysis"],
      ["#mainNavComplianceBtn", "#pageCompliance"],
      ["#mainNavCalculatorBtn", "#pageCalculator"],
    ];
    for (const [navSelector, pageSelector] of pages) {
      await page.locator(navSelector).click();
      await expect(page.locator(pageSelector)).toBeVisible();
      await expect(page.locator("#pageEventReconstruction")).toBeHidden();
      await expect(erNav).not.toHaveAttribute("aria-current", "page");
      await erNav.click();
      await expect(page.locator("#pageEventReconstruction")).toBeVisible();
      await expect(page.locator(pageSelector)).toBeHidden();
    }

    expect(consoleErrors).toEqual([]);
  });

  test("empty workspace shows the left panel, the workspace shell and the toolbar", async ({ page }) => {
    const consoleErrors = collectConsoleErrors(page);
    await page.goto("/index.html");
    await openEventReconstruction(page);

    const sidebar = page.locator("#wwErSidebar");
    await expect(sidebar).toBeVisible();
    await expect(page.locator("#wwErDefinitionHeading")).toContainText("Reconstruction");
    await expect(page.locator("#wwErMemberCountBadge")).toHaveText("(0)");
    await expect(page.locator("#wwErRecordsCountBadge")).toHaveText("(0)");
    await expect(page.locator("#wwErRecordsPanel")).toContainText("No recordings loaded yet. Upload one from Recordings.");
    await expect(page.locator("#wwErClearBtn")).toBeHidden();
    const sidebarBox = await sidebar.boundingBox();
    const mainBox = await page.locator("#wwErMain").boundingBox();
    expect(sidebarBox.x + sidebarBox.width).toBeLessThanOrEqual(mainBox.x);
    expect(Math.round(sidebarBox.width)).toBe(320);

    await expect(page.locator("#wwErCanvas .ww-tg-header-title")).toHaveText("Reconstruction Timeline");
    await expect(page.locator("#wwErCanvasMeta")).toHaveText("No reconstruction records selected");
    await expect(page.locator("#wwErEmptyState")).toBeVisible();
    await expect(page.locator("#wwErPanels .ww-chart")).toHaveCount(0);
    await expect(page.locator("#pageEventReconstruction .ww-time-group-canvas")).toHaveCount(0);

    await expect(page.locator("#wwErDragModeZoomBtn")).toHaveAttribute("aria-label", "Box Zoom");
    await expect(page.locator("#wwErDragModePanBtn")).toHaveAttribute("aria-label", "Pan");
    for (const id of ["#wwErZoomInBtn", "#wwErZoomOutBtn", "#wwErResetViewBtn"]) {
      await expect(page.locator(id)).toBeVisible();
      await expect(page.locator(id)).toBeDisabled();
    }

    const toolbarStyles = await page.evaluate(() => {
      const pick = (el) => {
        const style = getComputedStyle(el);
        return { backgroundImage: style.backgroundImage, borderBottom: style.borderBottom, padding: style.padding, gap: style.gap };
      };
      return { er: pick(document.getElementById("wwErToolbar")), waveform: pick(document.getElementById("wwToolbar")) };
    });
    expect(toolbarStyles.er).toEqual(toolbarStyles.waveform);

    expect(consoleErrors).toEqual([]);
  });

  test("drag mode is Event Reconstruction state only and never changes Waveform", async ({ page }) => {
    await page.goto("/index.html");
    await openEventReconstruction(page);

    await expect(page.locator("#wwErDragModeZoomBtn")).toHaveAttribute("aria-pressed", "true");
    await page.locator("#wwErDragModePanBtn").click();
    await expect(page.locator("#wwErDragModePanBtn")).toHaveAttribute("aria-pressed", "true");
    await expect(page.locator("#wwErDragModeZoomBtn")).toHaveAttribute("aria-pressed", "false");
    await expect(page.locator("#dragModeZoomBtn")).toHaveAttribute("aria-pressed", "true");
    await expect(page.locator("#dragModePanBtn")).toHaveAttribute("aria-pressed", "false");
  });

  test("responsive Sources drawer opens the Event Reconstruction panel only", async ({ page }) => {
    await page.setViewportSize({ width: 800, height: 800 });
    await page.goto("/index.html");
    await openEventReconstruction(page);

    const toggle = page.locator("#shellSidebarToggleBtn");
    await expect(toggle).toBeVisible();
    await toggle.click();
    await expect(page.locator("#pageEventReconstruction")).toHaveClass(/shell-sidebar-open/);
    await expect(page.locator("#workspaceRow")).not.toHaveClass(/shell-sidebar-open/);
    await expect(page.locator("#wwErSidebar")).toBeInViewport();

    await page.locator("#wwErSidebarBackdrop").click({ position: { x: 700, y: 400 } });
    await expect(page.locator("#pageEventReconstruction")).not.toHaveClass(/shell-sidebar-open/);

    await page.locator("#mainNavWaveformBtn").click();
    await toggle.click();
    await expect(page.locator("#workspaceRow")).toHaveClass(/shell-sidebar-open/);
    await expect(page.locator("#pageEventReconstruction")).not.toHaveClass(/shell-sidebar-open/);
  });
});

async function createCalculatedChannel(page, sourceId) {
  const resp = await page.request.post(`${BACKEND}/api/v1/workspaces/${await workspaceId(page)}/calculated-channels`, {
    data: { name: "-VA", operation: "reverse_polarity", inputs: [{ kind: "source", source_id: sourceId, channel_name: "VA" }], parameters: {} },
  });
  expect(resp.status()).toBe(201);
  return resp.json();
}

async function openMemberTree(page, station) {
  const row = memberRow(page, station);
  const tree = row.locator("details.ww-er-member-tree");
  if (!(await tree.evaluate((el) => el.open))) await tree.locator(":scope > summary").click();
  return row;
}

test.describe("Event Reconstruction -- independent records (DEC-128)", () => {
  test("records with identical timestamps stay separate members while Waveform still groups them", async ({ page }) => {
    const consoleErrors = collectConsoleErrors(page);
    await page.goto("/index.html");
    await upload(page, "AGJH 500kV", "09:59:30");
    await upload(page, "BAHS 275kV", "10:00:00");
    await upload(page, "BTGH", "10:00:00");
    const bahs = await sourceIdFor(page, "BAHS 275kV");
    const btgh = await sourceIdFor(page, "BTGH");

    // Waveform keeps its Time Group model: BAHS and BTGH overlap, so they
    // form one Time Group there.
    const groupsBefore = await api(page, "/synchronization/time-groups");
    const shared = groupsBefore.find((g) => g.source_ids.includes(bahs));
    expect(shared.source_ids.slice().sort()).toEqual([bahs, btgh].sort());

    // Event Reconstruction lists three records, one row each.
    await openEventReconstruction(page);
    await expect(page.locator("#wwErRecordsCountBadge")).toHaveText("(3)");
    const names = await page.locator('#wwErRecordsPanel .ww-er-record-row[data-eligible="true"] .source-recording-name').allTextContents();
    expect(names[0]).toBe("AGJH 500kV");
    expect(names.slice(1).sort()).toEqual(["BAHS 275kV", "BTGH"]);
    expect(names).toHaveLength(3); // never one merged "BAHS 275kV + BTGH" row

    await addRecord(page, "AGJH 500kV");
    await addRecord(page, "BAHS 275kV");
    await addRecord(page, "BTGH");
    await expect(page.locator("#wwErMemberCountBadge")).toHaveText("(3)");
    await expect(page.locator("#wwErCanvasMeta")).toHaveText("3 records selected");
    for (const station of ["AGJH 500kV", "BAHS 275kV", "BTGH"]) {
      const row = await openMemberTree(page, station);
      await expect(row.locator("details.ww-er-member-tree details.source-recording")).toHaveCount(1);
      await expect(row.locator("details.ww-er-member-tree .source-recording-name")).toHaveText(station);
    }

    // Each record owns its correction.
    await setCorrection(page, "BTGH", 4);
    await expect(memberRow(page, "BTGH").locator(".ww-er-correction-value")).toHaveText("+4.000 ms");
    await expect(memberRow(page, "BAHS 275kV").locator(".ww-er-correction-value")).toHaveText("0.000 ms");
    const definition = await api(page, "/event-reconstruction/definition");
    const byId = Object.fromEntries(definition.members.map((m) => [m.record_id, m]));
    expect(byId[bahs].reconstruction_offset_s).toBeCloseTo(30, 9);
    expect(byId[btgh].reconstruction_offset_s).toBeCloseTo(30.004, 9);
    expect(byId[btgh].source_timings.map((t) => t.source_id)).toEqual([btgh]);

    // Channel selection is per record: the same channel name in BAHS and
    // BTGH are two different selections.
    await memberRow(page, "BAHS 275kV").locator('tr.ww-er-channel-row[data-er-channel-name="VA"]').click();
    await memberRow(page, "BTGH").locator('tr.ww-er-channel-row[data-er-channel-name="VA"]').click();
    const selections = await page.evaluate(() => wwErSelectedChannelsForPlotting());
    expect(selections.map((s) => s.recordId).sort()).toEqual([bahs, btgh].sort());

    // Waveform's Time Groups are untouched.
    expect(await api(page, "/synchronization/time-groups")).toEqual(groupsBefore);
    expect(consoleErrors).toEqual([]);
  });
});

test.describe("Event Reconstruction -- Slice 2A channel browser", () => {
  test("member tree mirrors the Waveform tree and inherits names and colours read-only", async ({ page }) => {
    const consoleErrors = collectConsoleErrors(page);
    await page.goto("/index.html");
    await upload(page, "STN_A", "10:00:00");
    await upload(page, "STN_B", "10:00:10");
    const sourceA = await sourceIdFor(page, "STN_A");
    const calc = await createCalculatedChannel(page, sourceA);

    // Waveform is the master of presentation: rename/recolour there.
    await page.evaluate((sid) => {
      wwSetChannelDisplayName(sid, "VB", "Bus VB renamed");
      wwSetChannelColorOverride(sid, "VB", "#123456");
    }, sourceA);
    // Analog only (DEC-127): Waveform's analog subgroups for this recording.
    const waveformSubgroups = await page.evaluate((sid) =>
      Array.from(document.querySelectorAll(`#channelGroups details.source-recording[data-source-id="${sid}"] details.channel-group[data-group="analog"] details.channel-subgroup`))
        .map((d) => d.dataset.subgroup + ":" + d.querySelectorAll("tr").length), sourceA);

    await openEventReconstruction(page);
    await addRecord(page, "STN_A");
    await addRecord(page, "STN_B");
    const rowA = await openMemberTree(page, "STN_A");

    // Same hierarchy and grouping as Waveform for this recording.
    const tree = rowA.locator("details.ww-er-member-tree");
    await expect(tree.locator("details.source-recording")).toHaveCount(1);
    await expect(tree.locator("details.channel-group > summary")).toContainText(["Analog Channels", "Calculated Channels"]);
    const erSubgroups = await tree.evaluate((root) =>
      Array.from(root.querySelectorAll("details.channel-group"))
        .filter((g) => !g.classList.contains("ww-er-member-tree") && !/Calculated Channels/.test(g.querySelector("summary").textContent))
        .flatMap((g) => Array.from(g.querySelectorAll("details.channel-subgroup")))
        .map((d) => d.querySelector("summary").childNodes[1].textContent.trim() + ":" + d.querySelectorAll("tr").length));
    expect(erSubgroups).toEqual(waveformSubgroups);

    // Calculated channel: under its timing parent only.
    const calcRow = rowA.locator('tr.ww-er-channel-row[data-er-kind="calculated"]');
    await expect(calcRow).toHaveCount(1);
    await expect(calcRow).toHaveAttribute("data-er-timing-source-id", calc.reference_source_id);
    await expect(calcRow).toContainText("-VA");
    const rowB = await openMemberTree(page, "STN_B");
    await expect(rowB.locator('tr.ww-er-channel-row[data-er-kind="calculated"]')).toHaveCount(0);

    // Inherited name and colour, through Waveform's resolvers.
    const renamed = rowA.locator('tr.ww-er-channel-row[data-er-channel-name="VB"]');
    await expect(renamed).toContainText("Bus VB renamed");
    await expect(renamed.locator(".channel-color-dot")).toHaveAttribute("style", /#123456/);
    const vaColour = await page.evaluate((sid) => wwColorForChannel(sid, "VA"), sourceA);
    await expect(rowA.locator('tr.ww-er-channel-row[data-er-channel-name="VA"] .channel-color-dot')).toHaveAttribute("style", new RegExp(vaColour));

    // A later Waveform change is inherited on refresh -- nothing is copied.
    await page.evaluate((sid) => wwSetChannelDisplayName(sid, "VB", "Bus VB again"), sourceA);
    await page.locator("#mainNavRecordingsBtn").click();
    await openEventReconstruction(page);
    await openMemberTree(page, "STN_A");
    await expect(memberRow(page, "STN_A").locator('tr.ww-er-channel-row[data-er-channel-name="VB"]')).toContainText("Bus VB again");

    // No property editing from Event Reconstruction.
    await memberRow(page, "STN_A").locator('tr.ww-er-channel-row[data-er-channel-name="VA"]').click({ button: "right" });
    await expect(page.locator("#wwChannelContextMenu")).toBeHidden();
    await expect(page.locator("#pageEventReconstruction").getByText(/Rename|Change colou?r/)).toHaveCount(0);
    await expect(page.locator('#pageEventReconstruction input[type="color"]')).toHaveCount(0);

    expect(consoleErrors).toEqual([]);
  });

  test("channel selection is Event Reconstruction state only and never changes Waveform", async ({ page }) => {
    const consoleErrors = collectConsoleErrors(page);
    await page.goto("/index.html");
    await upload(page, "STN_A", "10:00:00");
    await upload(page, "STN_B", "10:00:10");
    const sourceA = await sourceIdFor(page, "STN_A");
    const calc = await createCalculatedChannel(page, sourceA);

    // One channel displayed in Waveform first.
    await page.locator("#recordingsTableBody tr[data-source-id]").first().click();
    await expect(page.locator("#workspaceRow")).toBeVisible();
    const wfRow = page.locator('#channelGroups tr.channel-row--toggle[data-channel-kind="analog"]').first();
    if ((await wfRow.getAttribute("aria-pressed")) !== "true") await wfRow.click();
    await expect(wfRow).toHaveAttribute("aria-pressed", "true");
    const waveformBefore = await page.evaluate(() => ({
      displayed: Array.from(ww.displayed.keys()).sort(),
      digital: Array.from(ww.digitalDisplayed.keys()).sort(),
      expanded: Array.from(document.querySelectorAll("#channelGroups details[data-expand-key]")).map((d) => d.dataset.expandKey + "=" + d.open),
    }));
    const calcsBefore = await api(page, "/calculated-channels");

    await openEventReconstruction(page);
    await addRecord(page, "STN_A");
    await addRecord(page, "STN_B");
    const rowA = await openMemberTree(page, "STN_A");

    // Row toggle and group "Include all".
    const vaRow = rowA.locator('tr.ww-er-channel-row[data-er-channel-name="VA"]');
    await expect(vaRow).toHaveAttribute("aria-pressed", "false");
    await vaRow.click();
    await expect(vaRow).toHaveAttribute("aria-pressed", "true");
    await expect(vaRow).not.toHaveClass(/ww-er-channel-row--unselected/);
    const currentSubgroup = rowA.locator("details.channel-subgroup", { has: page.locator('tr[data-er-channel-name="IA"]') });
    await currentSubgroup.locator(".ww-er-group-toggle-btn").click();
    await expect(currentSubgroup).toHaveAttribute("open", "");
    await expect(currentSubgroup.locator(".ww-er-group-toggle-btn")).toHaveText("Exclude all");
    await rowA.locator('tr.ww-er-channel-row[data-er-kind="calculated"]').click();
    await vaRow.press("Space");
    await expect(vaRow).toHaveAttribute("aria-pressed", "false");
    await expect(rowA.locator(".ww-er-selected-count")).toHaveText("(2 selected)");

    // Collapsing in Event Reconstruction never touches the Waveform tree.
    await rowA.locator('details.channel-group[data-er-expand-key$=":calculated"] > summary').click();

    const selections = await page.evaluate(() => wwErSelectedChannelsForPlotting());
    expect(selections.map((s) => s.kind + ":" + s.channelName).sort()).toEqual(["analog:IA", "calculated:-VA"]);
    expect(new Set(selections.map((s) => s.recordId))).toEqual(new Set([sourceA]));
    const calcSelection = selections.find((s) => s.kind === "calculated");
    expect(calcSelection.sourceId).toBe(calc.id);
    expect(calcSelection.timingSourceId).toBe(calc.reference_source_id);

    const waveformAfter = await page.evaluate(() => ({
      displayed: Array.from(ww.displayed.keys()).sort(),
      digital: Array.from(ww.digitalDisplayed.keys()).sort(),
      expanded: Array.from(document.querySelectorAll("#channelGroups details[data-expand-key]")).map((d) => d.dataset.expandKey + "=" + d.open),
    }));
    expect(waveformAfter).toEqual(waveformBefore);
    expect(await api(page, "/calculated-channels")).toEqual(calcsBefore);

    // Selections survive a page round trip; Waveform keeps its own display.
    await page.locator("#mainNavWaveformBtn").click();
    await expect(wfRow).toHaveAttribute("aria-pressed", "true");
    await openEventReconstruction(page);
    await expect(memberRow(page, "STN_A").locator(".ww-er-selected-count")).toHaveText("(2 selected)");

    expect(consoleErrors).toEqual([]);
  });

  test("an overlapping upload never stales a member; a removed record loses its tree and its selections are not plotted", async ({ page }) => {
    await page.goto("/index.html");
    await upload(page, "STN_BASE", "10:00:00");
    await upload(page, "STN_REF", "10:00:10");
    await openEventReconstruction(page);
    await addRecord(page, "STN_REF");
    await addRecord(page, "STN_BASE");
    const base = await openMemberTree(page, "STN_BASE");
    await base.locator('tr.ww-er-channel-row[data-er-channel-name="VA"]').click();
    expect((await page.evaluate(() => wwErSelectedChannelsForPlotting())).length).toBe(1);

    // Overlaps STN_BASE (one Waveform Time Group) -- a separate record.
    await upload(page, "STN_OVERLAP", "10:00:00.005");
    await openEventReconstruction(page);
    await expect(memberRow(page, "STN_BASE")).toHaveAttribute("data-member-status", "current");
    await expect(memberRow(page, "STN_BASE").locator(".ww-er-selected-count")).toHaveText("(1 selected)");
    await expect(recordRow(page, "STN_OVERLAP").locator('button[data-er-action="add-record"]')).toBeEnabled();
    expect((await page.evaluate(() => wwErSelectedChannelsForPlotting())).length).toBe(1);

    // Removing the recording makes its member stale.
    await removeRecording(page, "STN_BASE");
    await openEventReconstruction(page);
    const stale = staleRows(page);
    await expect(stale).toHaveCount(1);
    await expect(stale.locator("details.ww-er-member-tree")).toHaveCount(0);
    await expect(stale.locator("tr.ww-er-channel-row")).toHaveCount(0);
    await expect(stale).toContainText("Channel selection is unavailable for a removed record.");
    expect(await page.evaluate(() => wwErSelectedChannelsForPlotting())).toEqual([]);

    // Records that are not members (eligible or not) never get a tree.
    await expect(page.locator("#wwErRecordsPanel tr.ww-er-channel-row")).toHaveCount(0);
    await expect(page.locator("#wwErRecordsPanel details.ww-er-member-tree")).toHaveCount(0);

    // Removing the stale member drops its inert selections too.
    await page.locator('#wwErNotices button[data-er-action="remove-stale"]').click();
    await expect(staleRows(page)).toHaveCount(0);
    expect(await page.evaluate(() => Object.keys(wwErState.selectedChannels))).toEqual([]);
  });
});

test.describe("Event Reconstruction -- analog-only scope (DEC-127)", () => {
  test("no digital channels in Event Reconstruction; Waveform digital browser and visibility unchanged", async ({ page }) => {
    const consoleErrors = collectConsoleErrors(page);
    await page.goto("/index.html");
    await upload(page, "STN_A", "10:00:00");
    await upload(page, "STN_B", "10:00:10");
    const sourceA = await sourceIdFor(page, "STN_A");
    await createCalculatedChannel(page, sourceA);

    // Waveform: show one digital channel and record its digital browser.
    await page.locator("#recordingsTableBody tr[data-source-id]").first().click();
    await expect(page.locator("#workspaceRow")).toBeVisible();
    const digitalGroup = page.locator(`#channelGroups details.source-recording[data-source-id="${sourceA}"] details.channel-group[data-group="digital"]`);
    await expect(digitalGroup).toHaveCount(1);
    if (!(await digitalGroup.evaluate((el) => el.open))) await digitalGroup.locator(":scope > summary").click();
    const digitalRow = digitalGroup.locator('tr.channel-row--toggle[data-channel-kind="digital"]').first();
    await digitalRow.click();
    await expect(digitalRow).toHaveAttribute("aria-pressed", "true");
    const digitalBefore = await page.evaluate((sid) => ({
      displayed: Array.from(ww.digitalDisplayed.keys()).sort(),
      subgroups: Array.from(document.querySelectorAll(`#channelGroups details.source-recording[data-source-id="${sid}"] details.channel-group[data-group="digital"] details.channel-subgroup`))
        .map((d) => d.dataset.subgroup + ":" + d.querySelectorAll("tr").length),
    }), sourceA);
    expect(digitalBefore.displayed.length).toBe(1);
    expect(digitalBefore.subgroups.length).toBeGreaterThan(0);

    await openEventReconstruction(page);
    await addRecord(page, "STN_A");
    await addRecord(page, "STN_B");
    const rowA = await openMemberTree(page, "STN_A");
    const pageEr = page.locator("#pageEventReconstruction");
    await expect(pageEr.locator('tr.ww-er-channel-row[data-er-kind="digital"]')).toHaveCount(0);
    await expect(pageEr.locator("details.channel-group > summary", { hasText: "Digital Channels" })).toHaveCount(0);
    for (const label of ["Triggered", "Never Triggered", "Spare"]) {
      await expect(pageEr.locator("details.channel-subgroup > summary", { hasText: label })).toHaveCount(0);
    }

    // Native analog and calculated analog remain selectable.
    await rowA.locator('tr.ww-er-channel-row[data-er-kind="analog"]').first().click();
    await rowA.locator('tr.ww-er-channel-row[data-er-kind="calculated"]').click();
    expect((await page.evaluate(() => wwErSelectedChannelsForPlotting())).map((s) => s.kind).sort()).toEqual(["analog", "calculated"]);

    // A digital selection can never reach plotting: rejected, then pruned.
    await page.evaluate(() => {
      const member = wwErCurrentMembers()[0];
      wwErState.selectedChannels["injected"] = { recordId: member.record_id, kind: "digital", sourceId: member.source_ids[0], channelName: "BRK_A", timingSourceId: member.source_ids[0] };
    });
    expect((await page.evaluate(() => wwErSelectedChannelsForPlotting())).some((s) => s.kind === "digital")).toBe(false);
    await page.evaluate(() => wwErRefresh());
    expect(await page.evaluate(() => Object.prototype.hasOwnProperty.call(wwErState.selectedChannels, "injected"))).toBe(false);

    // Waveform digital state and browser are untouched.
    const digitalAfter = await page.evaluate((sid) => ({
      displayed: Array.from(ww.digitalDisplayed.keys()).sort(),
      subgroups: Array.from(document.querySelectorAll(`#channelGroups details.source-recording[data-source-id="${sid}"] details.channel-group[data-group="digital"] details.channel-subgroup`))
        .map((d) => d.dataset.subgroup + ":" + d.querySelectorAll("tr").length),
    }), sourceA);
    expect(digitalAfter).toEqual(digitalBefore);
    await page.locator("#mainNavWaveformBtn").click();
    await expect(digitalRow).toHaveAttribute("aria-pressed", "true");

    expect(consoleErrors).toEqual([]);
  });
});

test.describe("Event Reconstruction -- Slice 2 selection workflow", () => {
  test("records are listed chronologically; ineligible records show the backend reason and cannot be added", async ({ page }) => {
    const consoleErrors = collectConsoleErrors(page);
    await page.goto("/index.html");
    // Uploaded out of chronological order on purpose.
    await upload(page, "STN_LATE", "10:00:20");
    await upload(page, "STN_EARLY", "10:00:00");
    await upload(page, "STN_MIDDLE", "10:00:10");

    // A Time-of-Day record cannot come from a COMTRADE upload, so it is
    // appended to the real backend response.
    await page.route("**/event-reconstruction/records", async (route) => {
      const response = await route.fetch();
      const records = await response.json();
      records.push({
        record_id: "tod-record", source_ids: ["tod-record"], time_reference_type: "time_of_day",
        eligible: false, reason_code: "time_of_day_not_supported",
        reason_message: "This record has a time of day but no calendar date. Time-of-day records are not supported by Event Reconstruction yet.",
        start_time_utc: null, end_time_utc: null, duration_s: 1.0, in_reconstruction: false,
      });
      await route.fulfill({ response, json: records });
    });

    await openEventReconstruction(page);
    const eligibleRows = page.locator('#wwErRecordsPanel .ww-er-record-row[data-eligible="true"] .source-recording-name');
    await expect(eligibleRows).toHaveText(["STN_EARLY", "STN_MIDDLE", "STN_LATE"]);
    await expect(page.locator("#wwErRecordsCountBadge")).toHaveText("(4)");

    const ineligible = page.locator('#wwErRecordsPanel .ww-er-record-row[data-eligible="false"]');
    await expect(ineligible).toHaveCount(1);
    await expect(ineligible).toHaveAttribute("data-reason-code", "time_of_day_not_supported");
    await expect(ineligible).toContainText("no calendar date");
    await expect(ineligible).toContainText("Not eligible");
    await expect(ineligible.locator('button[data-er-action="add-record"]')).toHaveCount(0);
    await expect(page.locator("#wwErNotices")).toContainText("Add two or more records");

    expect(consoleErrors).toEqual([]);
  });

  test("create, update, change reference, correct, reset, re-enter and clear", async ({ page }) => {
    const consoleErrors = collectConsoleErrors(page);
    await page.goto("/index.html");
    await upload(page, "STN_A", "10:00:00");
    await upload(page, "STN_B", "10:00:10");
    await upload(page, "STN_C", "10:00:20");
    await openEventReconstruction(page);

    await addRecord(page, "STN_A");
    await expect(page.locator("#wwErMemberCountBadge")).toHaveText("(1)");
    await expect(memberRow(page, "STN_A").locator(".ww-er-badge--reference")).toBeVisible();
    await expect(page.locator("#wwErNotices")).toContainText("A reconstruction needs at least two records.");
    await addRecord(page, "STN_B");
    await addRecord(page, "STN_C");
    await expect(page.locator("#wwErMemberCountBadge")).toHaveText("(3)");
    await expect(page.locator("#wwErCanvasMeta")).toHaveText("3 records selected");
    await expect(memberRow(page, "STN_B")).toContainText("+10.000 s from reference");

    // Update membership: remove a non-reference member.
    await memberRow(page, "STN_C").locator('button[data-er-action="remove-member"]').click();
    await expect(page.locator("#wwErMemberCountBadge")).toHaveText("(2)");
    await expect(recordRow(page, "STN_C").locator('button[data-er-action="add-record"]')).toBeVisible();

    // Sub-millisecond correction is stored at full precision.
    await setCorrection(page, "STN_B", 12.3456);
    await expect(memberRow(page, "STN_B").locator(".ww-er-correction-value")).toHaveText("+12.346 ms");
    let definition = await api(page, "/event-reconstruction/definition");
    const memberB = definition.members.find((m) => !m.is_reference);
    expect(memberB.correction_s).toBeCloseTo(0.0123456, 12);

    // Changing the reference keeps every stored correction.
    await memberRow(page, "STN_B").locator('button[data-er-action="make-reference"]').click();
    await expect(memberRow(page, "STN_B").locator(".ww-er-badge--reference")).toBeVisible();
    await expect(memberRow(page, "STN_A")).toContainText("from reference");
    definition = await api(page, "/event-reconstruction/definition");
    expect(definition.reference_record_id).toBe(memberB.record_id);
    expect(definition.members.find((m) => m.record_id === memberB.record_id).correction_s).toBeCloseTo(0.0123456, 12);
    await expect(memberRow(page, "STN_B").locator(".ww-er-correction-value")).toHaveText("+12.346 ms");

    // Reset, then leave and come back: the definition is restored from the backend.
    await memberRow(page, "STN_B").locator('button[data-er-action="reset-correction"]').click();
    await expect(memberRow(page, "STN_B").locator(".ww-er-correction-value")).toHaveText("0.000 ms");
    await page.locator("#mainNavRecordingsBtn").click();
    await openEventReconstruction(page);
    await expect(page.locator("#wwErMemberCountBadge")).toHaveText("(2)");
    await expect(memberRow(page, "STN_B").locator(".ww-er-badge--reference")).toBeVisible();

    // Clear asks first, then removes only the reconstruction.
    await page.locator("#wwErClearBtn").click();
    await expect(page.locator("#wwErClearConfirmOverlay")).toBeVisible();
    await page.locator("#wwErClearCancelBtn").click();
    await expect(page.locator("#wwErMemberCountBadge")).toHaveText("(2)");
    await page.locator("#wwErClearBtn").click();
    await page.locator("#wwErClearConfirmBtn").click();
    await expect(page.locator("#wwErMemberCountBadge")).toHaveText("(0)");
    await expect(page.locator("#wwErClearBtn")).toBeHidden();
    await expect(page.locator("#wwErRecordsCountBadge")).toHaveText("(3)");
    expect((await api(page, "/event-reconstruction/definition")).defined).toBe(false);
    expect(await api(page, "/sources")).toHaveLength(3);

    expect(consoleErrors).toEqual([]);
  });

  test("a removed record's member keeps its correction unapplied and is only removed explicitly", async ({ page }) => {
    const consoleErrors = collectConsoleErrors(page);
    await page.goto("/index.html");
    await upload(page, "STN_BASE", "10:00:00");
    await upload(page, "STN_REF", "10:00:10");
    await upload(page, "STN_SPARE", "10:00:20");
    await openEventReconstruction(page);
    await addRecord(page, "STN_REF");
    await addRecord(page, "STN_BASE");
    await setCorrection(page, "STN_BASE", -5);
    await expect(memberRow(page, "STN_BASE").locator(".ww-er-correction-value")).toHaveText("-5.000 ms");

    const removedId = await removeRecording(page, "STN_BASE");
    await openEventReconstruction(page);

    const stale = staleRows(page);
    await expect(stale).toHaveCount(1);
    await expect(stale).toHaveAttribute("data-record-id", removedId);
    await expect(stale.getByText("Stale")).toBeVisible();
    await expect(stale).toContainText("Its recording was removed.");
    await expect(stale).toContainText("Correction -5.000 ms (kept, not applied)");
    await expect(stale.locator("input[data-er-correction-input]")).toHaveCount(0);
    await expect(page.locator("#wwErNotices")).toContainText("1 member was removed");
    await expect(page.locator("#wwErCanvasMeta")).toContainText("removed records to resolve");
    // Membership edits wait until the stale member is resolved.
    await expect(recordRow(page, "STN_SPARE").locator('button[data-er-action="add-record"]')).toBeDisabled();

    await page.locator('#wwErNotices button[data-er-action="remove-stale"]').click();
    await expect(staleRows(page)).toHaveCount(0);
    const definition = await api(page, "/event-reconstruction/definition");
    expect(definition.status).toBe("ready");
    expect(definition.members.map((m) => m.correction_s)).toEqual([0]);
    expect(definition.members.some((m) => m.record_id === removedId)).toBe(false);
    await expect(recordRow(page, "STN_SPARE").locator('button[data-er-action="add-record"]')).toBeEnabled();

    expect(consoleErrors).toEqual([]);
  });

  test("a removed reference is never replaced automatically", async ({ page }) => {
    await page.goto("/index.html");
    await upload(page, "STN_BASE", "10:00:00");
    await upload(page, "STN_OTHER", "10:00:10");
    await openEventReconstruction(page);
    await addRecord(page, "STN_BASE");
    await addRecord(page, "STN_OTHER");
    const before = await api(page, "/event-reconstruction/definition");

    await removeRecording(page, "STN_BASE");
    await openEventReconstruction(page);
    await expect(page.locator("#wwErNotices")).toContainText("Reference needs to be chosen again");
    await expect(staleRows(page).locator(".ww-er-badge--reference")).toBeVisible();
    await expect(page.locator('#wwErNotices button[data-er-action="remove-stale"]')).toHaveCount(0);
    const after = await api(page, "/event-reconstruction/definition");
    expect(after.reference_record_id).toBe(before.reference_record_id);
    expect(after.placements_available).toBe(false);

    // The engineer chooses a current member as reference explicitly.
    await memberRow(page, "STN_OTHER").locator('button[data-er-action="make-reference"]').click();
    await expect(memberRow(page, "STN_OTHER").locator(".ww-er-badge--reference")).toBeVisible();
    await expect(page.locator('#wwErNotices button[data-er-action="remove-stale"]')).toBeVisible();
  });

  test("a large time gap between records is a warning, not a rejection", async ({ page }) => {
    await page.goto("/index.html");
    await upload(page, "STN_MORNING", "10:00:00");
    await upload(page, "STN_NOON", "12:00:00");
    await openEventReconstruction(page);
    await addRecord(page, "STN_MORNING");
    await addRecord(page, "STN_NOON");

    const notice = page.locator('#wwErNotices .ww-er-notice--warn', { hasText: "Large time gap" });
    await expect(notice).toBeVisible();
    await expect(notice).toContainText("warning threshold 3600 s");
    await expect(notice).toContainText("Between STN_MORNING and STN_NOON");
    const definition = await api(page, "/event-reconstruction/definition");
    expect(definition.status).toBe("ready");
    expect(definition.warnings).toHaveLength(1);
    await expect(page.locator("#wwErStatus")).not.toHaveClass(/error/);
  });

  test("never changes Waveform, Time Groups, Synchronise Sources or source data, and plots nothing", async ({ page }) => {
    const consoleErrors = collectConsoleErrors(page);
    await page.goto("/index.html");
    await upload(page, "STN_A", "10:00:00");
    await upload(page, "STN_B", "10:00:10");
    await upload(page, "STN_A_TWIN", "10:00:00");

    // Display one channel in Waveform first.
    await page.locator("#recordingsTableBody tr[data-source-id]").first().click();
    await expect(page.locator("#workspaceRow")).toBeVisible();
    const channelRow = page.locator('#channelGroups tr.channel-row--toggle[data-channel-kind="analog"]').first();
    if ((await channelRow.getAttribute("aria-pressed")) !== "true") await channelRow.click();
    await expect(channelRow).toHaveAttribute("aria-pressed", "true");
    const traces = page.locator("#wwTimeGroupCanvases .ww-chart .scatterlayer .trace");
    await expect(traces.first()).toBeVisible();
    const traceCount = await traces.count();

    const syncBefore = await api(page, "/synchronization/sources");
    const groupsBefore = await api(page, "/synchronization/time-groups");
    const sourcesBefore = await api(page, "/sources");

    await openEventReconstruction(page);
    await addRecord(page, "STN_A");
    await addRecord(page, "STN_B");
    await addRecord(page, "STN_A_TWIN");
    await setCorrection(page, "STN_A_TWIN", 2);
    await setCorrection(page, "STN_B", -9999);
    await memberRow(page, "STN_B").locator('button[data-er-action="make-reference"]').click();
    await expect(memberRow(page, "STN_B").locator(".ww-er-badge--reference")).toBeVisible();
    await expect(page.locator("#pageEventReconstruction .plotly")).toHaveCount(0);
    await expect(page.locator("#wwErEmptyState")).toHaveText("Plotting the reconstruction on its common timeline is not available yet.");
    for (const id of ["#wwErZoomInBtn", "#wwErZoomOutBtn", "#wwErResetViewBtn"]) await expect(page.locator(id)).toBeDisabled();

    expect(await api(page, "/synchronization/sources")).toEqual(syncBefore);
    expect(await api(page, "/synchronization/time-groups")).toEqual(groupsBefore);
    expect(await api(page, "/sources")).toEqual(sourcesBefore);

    await page.locator("#mainNavWaveformBtn").click();
    await expect(channelRow).toHaveAttribute("aria-pressed", "true");
    await expect(traces).toHaveCount(traceCount);

    expect(consoleErrors).toEqual([]);
  });
});

test.describe("Event Reconstruction -- Slice 3B time mapping", () => {
  test("frontend mapping uses the backend total offset, resolves calculated parents and drops removed records", async ({ page }) => {
    const consoleErrors = collectConsoleErrors(page);
    await page.goto("/index.html");
    await upload(page, "STN_REF", "10:00:00");
    await upload(page, "STN_FAR", "12:00:00");
    const farId = await sourceIdFor(page, "STN_FAR");
    const calc = await createCalculatedChannel(page, farId);
    await openEventReconstruction(page);
    await addRecord(page, "STN_REF");
    await addRecord(page, "STN_FAR");
    await setCorrection(page, "STN_FAR", 0.123);
    await expect(memberRow(page, "STN_FAR").locator(".ww-er-correction-value")).toHaveText("+0.123 ms");

    const definition = await api(page, "/event-reconstruction/definition");
    const apiFar = definition.members.flatMap((m) => m.source_timings || []).find((t) => t.source_id === farId);
    expect(apiFar.within_record_offset_s).toBe(0);
    const result = await page.evaluate(({ farId, calcId }) => {
      const far = wwErSourceTiming(farId);
      const viaCalc = wwErSourceTiming(calcId);
      const elapsed = Array.from({ length: 1001 }, (_, k) => k * 0.0002); // 5 kHz, 200 ms
      const mapped = elapsed.map((t) => wwErSourceElapsedToReconstructionTime(t, far.totalOffsetS));
      const back = mapped.map((x) => wwErReconstructionTimeToSourceElapsed(x, far.totalOffsetS));
      let spacingError = 0, roundTripError = 0;
      for (let k = 1; k < mapped.length; k++) spacingError = Math.max(spacingError, Math.abs(mapped[k] - mapped[k - 1] - 0.0002));
      for (let k = 0; k < back.length; k++) roundTripError = Math.max(roundTripError, Math.abs(back[k] - elapsed[k]));
      return { far, viaCalc, spacingError, roundTripError, openBound: wwErReconstructionTimeToSourceElapsed(null, far.totalOffsetS) };
    }, { farId, calcId: calc.id });

    expect(result.far.totalOffsetS).toBe(apiFar.total_reconstruction_offset_s);
    expect(result.far.totalOffsetS).toBeCloseTo(7200.000123, 9);
    expect(result.far.startS).toBe(apiFar.reconstruction_start_s);
    expect(result.far.recordId).toBe(farId);
    expect(result.viaCalc).toEqual(result.far);
    expect(result.viaCalc.timingSourceId).toBe(farId);
    expect(result.spacingError).toBeLessThan(1e-9);
    expect(result.roundTripError).toBeLessThan(1e-9);
    expect(result.openBound).toBeNull();
    await expect(page.locator("#pageEventReconstruction .plotly")).toHaveCount(0);

    // An identical-timestamp upload changes nothing for STN_FAR.
    await upload(page, "STN_FAR_TWIN", "12:00:00");
    await openEventReconstruction(page);
    await expect(memberRow(page, "STN_FAR")).toHaveAttribute("data-member-status", "current");
    expect(await page.evaluate((id) => wwErSourceTiming(id), farId)).toEqual(result.far);

    // A removed record exposes no mapping.
    await removeRecording(page, "STN_FAR");
    await openEventReconstruction(page);
    await expect(staleRows(page)).toHaveCount(1);
    const afterStale = await page.evaluate(({ farId, calcId, refName }) => ({
      far: wwErSourceTiming(farId),
      calc: wwErSourceTiming(calcId),
      ref: wwErSourceTiming(wwErState.sources.find((s) => s.station_name === refName).source_id),
    }), { farId, calcId: calc.id, refName: "STN_REF" });
    expect(afterStale.far).toBeNull();
    expect(afterStale.calc).toBeNull();
    expect(afterStale.ref.totalOffsetS).toBe(0);

    expect(consoleErrors).toEqual([]);
  });
});
