// P2 acceptance uses the original independent export, through the real UI.
const { test, expect } = require("./support/test");
const fs = require("fs");
const path = require("path");
const crypto = require("crypto");
const evidence = require("../backend/tests/fixtures/ben/ben5k_fast_ac_scaling.json").bphe;

test("BPHE: all 14 channels and both duplicate-name occurrences plot the independent export", async ({ page }, testInfo) => {
  test.setTimeout(120000);
  const filename = process.env.BPHE_BEN_PATH;
  test.skip(!filename || !fs.existsSync(filename), "Original BPHE reference unavailable; set BPHE_BEN_PATH");
  const files = evidence.files.map(file => {
    const location = path.join(path.dirname(filename), file.name);
    const bytes = fs.readFileSync(location);
    expect(crypto.createHash("sha256").update(bytes).digest("hex")).toBe(file.sha256);
    return bytes;
  });
  const cfg = files[1].toString("utf8").split(/\r?\n/).slice(2, 16).map(line => line.split(","));
  const dat = files[2].toString("utf8").replace(/\x1a/g, "").trim().split(/\r?\n/)
    .map(line => line.split(",").map(Number));
  expect(dat).toHaveLength(1148);
  const names = evidence.channels.map(c => c.name + (c.occurrence ? `_${c.occurrence}` : ""));
  const errors = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.goto("/index.html");
  await page.locator("#wwRdUploadBtn").first().click();
  await page.locator("#uploadModalFormatSelect").selectOption("ben");
  await page.locator("#uploadModalFile_0").setInputFiles(filename);
  await page.locator("#uploadModalSubmitBtn").click();
  await expect(page.locator("#uploadModalOverlay")).toBeHidden({ timeout: 30000 });
  const recording = page.locator("#wwRdRecordingList .ww-rd-recording-item").first();
  const sid = await recording.getAttribute("data-source-id");
  await recording.click();
  const rows = page.locator('#channelGroups tr.channel-row--toggle[data-channel-kind="analog"]');
  await expect(rows).toHaveCount(14);
  expect((await rows.evaluateAll(items => items.map(item => item.getAttribute("data-channel-name")))).sort()).toEqual([...names].sort());
  const duplicateValues = [];
  for (let column = 0; column < names.length; column++) {
    const name = names[column];
    expect(cfg[column][1].trim()).toBe(evidence.channels[column].name);
    const gain = Number(cfg[column][5]);
    const offset = Number(cfg[column][6]);
    const expected = dat.map(row => row[column + 2] * gain + offset);
    const row = page.locator(`#channelGroups tr.channel-row--toggle[data-channel-name="${name}"]`);
    if (await row.getAttribute("aria-pressed") !== "true") await row.click();
    const plotted = () => page.evaluate(({ sid, name }) => {
      const traces = [...document.querySelectorAll(".ww-chart")].flatMap(chart => chart.data || []);
      const trace = traces.find(item => item.meta === `${sid}::${name}`);
      return trace ? Array.from(trace.y) : [];
    }, { sid, name });
    await expect.poll(async () => (await plotted()).length).toBe(1148);
    const actual = await plotted();
    const maxNormalizedError = Math.max(...actual.map((v, i) => Math.abs(v - expected[i]) / (1e-9 + 3e-8 * Math.abs(expected[i]))));
    expect(maxNormalizedError, `${name}: independent export mismatch`).toBeLessThanOrEqual(1);
    if (column === 7 || column === 8) duplicateValues.push(actual);
    if (column === 8) await page.screenshot({ path: testInfo.outputPath("bphe-duplicate-channel.png") });
    await row.click();
    await expect(row).toHaveAttribute("aria-pressed", "false");
  }
  expect(duplicateValues[0]).not.toEqual(duplicateValues[1]);
  expect(errors).toEqual([]);
});
