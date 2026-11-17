// P3: exact-event calculated Hz/MW export, through native upload and actual plots.
const { test, expect } = require("./support/test");
const fs = require("fs");
const path = require("path");
const crypto = require("crypto");
const evidence = require("../backend/tests/fixtures/ben/gpth_2022_legacy_slow.json");

test("GPTH legacy Slow: 20 calculated channels plot all independent Hz/MW export values", async ({ page }, testInfo) => {
  test.setTimeout(120000);
  const filename = process.env.GPTH_SLOW_BEN_PATH;
  test.skip(!filename || !fs.existsSync(filename), "Set GPTH_SLOW_BEN_PATH to the original owner reference");
  const files = evidence.files.map(file => {
    const bytes = fs.readFileSync(path.join(path.dirname(filename), file.name));
    expect(crypto.createHash("sha256").update(bytes).digest("hex")).toBe(file.sha256);
    return bytes;
  });
  const cfg = files[1].toString("utf8").split(/\r?\n/).slice(2, 22).map(line => line.split(","));
  const dat = files[2].toString("utf8").replace(/\x1a/g, "").trim().split(/\r?\n/)
    .map(line => line.split(",").map(Number));
  expect(dat).toHaveLength(1402);
  const errors = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.goto("/index.html");
  await page.locator("#recordingsUploadBtn, #recordingsEmptyUploadBtn").first().click();
  await page.locator("#uploadModalFormatSelect").selectOption("ben");
  await page.locator("#uploadModalFile_0").setInputFiles(filename);
  await page.locator("#uploadModalSubmitBtn").click();
  await expect(page.locator("#uploadModalOverlay")).toBeHidden({ timeout: 30000 });
  const recording = page.locator("#recordingsTableBody tr[data-source-id]").first();
  const sid = await recording.getAttribute("data-source-id");
  await recording.click();
  const rows = page.locator('#channelGroups tr.channel-row--toggle[data-channel-kind="analog"]');
  await expect(rows).toHaveCount(20);
  expect((await rows.evaluateAll(items => items.map(item => item.getAttribute("data-channel-name")))).sort())
    .toEqual(evidence.analog.map(c => c.name).sort());
  for (let i = 0; i < evidence.analog.length; i++) {
    const channel = evidence.analog[i];
    const column = channel.export_column;
    expect(cfg[column][1].trim()).toBe(channel.name);
    expect(cfg[column][4]).toBe(channel.unit);
    const gain = Number(cfg[column][5]), offset = Number(cfg[column][6]);
    const raw = dat.map(row => row[column + 2]);
    const expected = raw.map(value => value * gain + offset);
    const row = page.locator(`#channelGroups tr.channel-row--toggle[data-channel-name="${channel.name}"]`);
    if (await row.getAttribute("aria-pressed") !== "true") await row.click();
    const plotted = () => page.evaluate(({ sid, name }) => {
      const traces = [...document.querySelectorAll(".ww-chart")].flatMap(chart => chart.data || []);
      const trace = traces.find(item => item.meta === `${sid}::${name}`);
      return trace ? Array.from(trace.y) : [];
    }, { sid, name: channel.name });
    await expect.poll(async () => (await plotted()).length).toBe(1402);
    const actual = await plotted();
    expect(Math.max(...actual.map((value, j) => Math.abs(value - expected[j]) / (1e-9 + 5e-11 * Math.abs(raw[j])))),
      `${channel.name}: independent export mismatch`).toBeLessThanOrEqual(1);
    if (i === 2) await page.screenshot({ path: testInfo.outputPath("gpth-slow-frequency-negative-power.png") });
    if (i !== 0) await row.click();
  }
  expect(errors).toEqual([]);
});
