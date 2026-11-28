// P3 UAT: actual rendered measurements after mouse interactions.
const { test, expect } = require("./support/test");
const fs = require("fs"), path = require("path"), crypto = require("crypto");
const { syntheticComtrade } = require("./support/synthetic_comtrade");
const { BACKEND, workspaceId } = require("./support/event_reconstruction_helpers");
const slow = require("../backend/tests/fixtures/ben/gpth_2022_legacy_slow.json");
test.setTimeout(90000);
const rowFor = (page, name) => page.locator(`#channelGroups tr.channel-row--toggle[data-channel-name="${name}"]`);
const duration = t => Math.abs(t) > 0 && Math.abs(t) < .001 ? `${(t * 1e6).toFixed(1)} \u00b5s`
  : Math.abs(t) < 1 ? `${(t * 1000).toFixed(3)} ms` : `${t.toFixed(3)} s`;
const valueText = v => v === 0 ? "0.0" : Math.abs(v) >= 1 ? v.toFixed(1) : Math.abs(v) >= .001 ? v.toFixed(3) : v.toExponential(2);
async function upload(page, files, ben = true) {
  await page.goto("/index.html");
  await page.locator("#wwRdUploadBtn").first().click();
  if (ben) await page.locator("#uploadModalFormatSelect").selectOption("ben");
  for (let i = 0; i < files.length; i++) await page.locator(`#uploadModalFile_${i}`).setInputFiles(files[i]);
  await page.locator("#uploadModalSubmitBtn").click();
  await expect(page.locator("#uploadModalOverlay")).toBeHidden();
  const row = page.locator("#wwRdRecordingList .ww-rd-recording-item").first(), sid = await row.getAttribute("data-source-id");
  await row.click();
  await page.locator("#mainNavWaveformBtn").click();   // selecting a recording in Recording Details no longer opens Waveform
  return `${BACKEND}/api/v1/workspaces/${await workspaceId(page)}/sources/${sid}`;
}
async function display(page, name) {
  await rowFor(page, name).click();
  await expect(rowFor(page, name)).toHaveAttribute("aria-pressed", "true");
  await expect(page.locator(".ww-chart .plotly").first()).toBeVisible();
  // COMTRADE/BEN32 can open in clock mode; explicitly exercise elapsed UI.
  await page.locator("#timeModeElapsedBtn").click();
}
async function assertRuler(page, range, event = false) {
  const scale = range[1] - range[0] < 1 ? 1000 : 1;
  await expect(page.locator(".ww-tg-ruler-chart .xtitle")).toHaveText(`${event ? "Event " : ""}Time (${scale === 1000 ? "ms" : "s"})`);
  const drawn = await page.evaluate(() => {
    const chart = document.querySelector(".ww-chart"), ruler = document.querySelector(".ww-tg-ruler-chart");
    return { main: chart._fullLayout.xaxis.range, ruler: ruler._fullLayout.xaxis.range,
      ticks: [...ruler.querySelectorAll(".xtick text")].map(e => e.textContent.replace(/\u2212/g, "-")), values: ruler.layout.xaxis.tickvals };
  });
  for (const key of ["main", "ruler"]) drawn[key].forEach((t, i) => expect(t).toBeCloseTo(range[i], 8));
  expect(drawn.ticks.map(Number)).toEqual(drawn.values.map(v => Number((v * scale).toFixed(scale === 1000 ? 1 : 3))));
  return drawn;
}
async function placePeak(page, name, mode, time, values, unit, screenshotPath) {
  const finite = values.map((v, i) => ({ v, i })).filter(p => p.v !== null && Number.isFinite(p.v));
  const winner = finite.reduce((a, b) => (mode === "max" ? b.v > a.v : b.v < a.v) ? b : a);
  await page.locator("#wwAnnotateBtn").click();
  await page.locator(`#wwAnnotateMenu [data-annotation-type="peak_${mode}"]`).click();
  // Placement guidance changes layout; measure the rendered trace afterward.
  const click = await page.evaluate(() => {
    const chart = document.querySelector(".ww-chart"), data = chart.data[0], rect = chart.getBoundingClientRect();
    const i = Math.floor(data.x.length * .75);
    return { x: rect.left + chart._fullLayout.xaxis._offset + chart._fullLayout.xaxis.l2p(data.x[i]),
      y: rect.top + chart._fullLayout.yaxis._offset + chart._fullLayout.yaxis.l2p(data.y[i]) };
  });
  const response = page.waitForResponse(r => r.url().endsWith("/peak-values") && r.request().method() === "POST");
  await page.mouse.click(click.x, click.y);
  const result = (await (await response).json()).results[0];
  expect(result.sample_index).toBe(winner.i);
  expect(result.elapsed_seconds).toBeCloseTo(time[winner.i], 9);
  expect(Math.abs(result.value - winner.v)).toBeLessThan(2e-7);
  expect(result.unit).toBe(unit);
  await expect.poll(() => page.evaluate(({ name, mode }) => [...ww.annotations.values()].filter(a =>
    a.type === `peak_${mode}` && a.data.channelName === name).length, { name, mode })).toBe(1);
  const annotation = await page.evaluate(({ name, mode }) => [...ww.annotations.values()].find(a =>
    a.type === `peak_${mode}` && a.data.channelName === name), { name, mode });
  expect(annotation.data.sampleIndex).toBe(winner.i);
  const box = page.locator(`.ww-annotation[data-annotation-id="${annotation.id}"]`), label = mode === "max" ? "Maximum" : "Minimum";
  await expect(box.locator(".ww-annotation-header")).toHaveText(label);
  await expect(box.locator(".ww-peak-value-line")).toHaveText(`${label}: ${valueText(winner.v)} ${unit}`);
  await expect(box.locator(".ww-peak-time-line")).toHaveText(`t = ${duration(time[winner.i])}`);
  const markerError = await page.evaluate(({ id, t, v }) => {
    const chart = document.querySelector(".ww-chart"), rect = chart.getBoundingClientRect();
    // X overlays follow the shared ruler's plot area; Y follows this panel.
    const ruler = document.querySelector(".ww-tg-ruler-chart"), rulerRect = ruler.getBoundingClientRect();
    const marker = document.querySelector(`.ww-callout-connector-group[data-annotation-id="${id}"] .ww-callout-anchor-marker`).getBoundingClientRect();
    return [marker.x + marker.width / 2 - (rulerRect.left + ruler._fullLayout.xaxis._offset + ruler._fullLayout.xaxis.l2p(t)),
      marker.y + marker.height / 2 - (rect.top + chart._fullLayout.yaxis._offset + chart._fullLayout.yaxis.l2p(v))];
  }, { id: annotation.id, t: time[winner.i], v: result.value });
  markerError.forEach(delta => expect(Math.abs(delta), JSON.stringify({ name, mode, markerError })).toBeLessThan(1));
  if (screenshotPath) await page.screenshot({ path: screenshotPath, fullPage: true });
  await page.evaluate(id => wwDeleteAnnotation(id), annotation.id);
}
async function dragCursor(page, kind, time, name, expected, origin = null) {
  const handle = page.locator(`.ww-tg-cursor-label-layer [data-cursor-drag="${kind}"]`);
  await handle.scrollIntoViewIfNeeded();
  const target = await page.evaluate(({ time, origin }) => {
    const chart = document.querySelector(".ww-tg-ruler-chart"), rect = chart.getBoundingClientRect();
    return rect.left + chart._fullLayout.xaxis._offset + chart._fullLayout.xaxis.l2p(time - (origin || 0));
  }, { time, origin });
  const box = await handle.boundingBox();
  await page.mouse.move(box.x + 6, box.y + box.height / 2); await page.mouse.down();
  await page.mouse.move(target, box.y + box.height / 2, { steps: 3 }); await page.mouse.up();
  await expect(rowFor(page, name).locator(`.cur-value--${kind}`)).toHaveText(valueText(expected));
  await expect(page.locator(`.ww-tg-cursor-readout-value--${kind}`)).toHaveText(origin === null ? duration(time)
    : `${time - origin < 0 ? "-" : "+"}${duration(Math.abs(time - origin))}`);
  // Equal formatted values at two times must not hide a pending value response.
  await expect.poll(() => page.evaluate(({ name, kind }) =>
    [...ww.cursorValues.entries()].find(([key]) => key.endsWith(`::${name}`))[1][kind + "SampleTime"],
    { name, kind })).toBeCloseTo(time, 9);
  const resolved = await page.evaluate(({ name, kind }) => {
    const entry = [...ww.cursorValues.entries()].find(([key]) => key.endsWith(`::${name}`))[1];
    return { time: entry[kind + "SampleTime"], value: entry[kind + "Value"] };
  }, { name, kind });
  expect(resolved.time).toBeCloseTo(time, 9); expect(Math.abs(resolved.value - expected)).toBeLessThan(2e-7);
}

test("GPTH Slow: independent negative peaks, endpoint cursors, seconds ruler and event t0", async ({ page }, testInfo) => {
  const filename = process.env.GPTH_SLOW_BEN_PATH;
  test.skip(!filename, "Set GPTH_SLOW_BEN_PATH to the pinned original recording");
  const files = slow.files.map(f => {
    const bytes = fs.readFileSync(path.join(path.dirname(filename), f.name));
    expect(crypto.createHash("sha256").update(bytes).digest("hex")).toBe(f.sha256); return bytes;
  });
  const cfg = files[1].toString().split(/\r?\n/).slice(2, 22).map(line => line.split(","));
  const dat = files[2].toString().replace(/\x1a/g, "").trim().split(/\r?\n/).map(line => line.split(",").map(Number));
  const values = dat.map(row => row[2] * Number(cfg[0][5]) + Number(cfg[0][6])), time = values.map((_, i) => i / 20);
  await upload(page, [filename]); await display(page, "POWER TBIN 1");
  expect((await assertRuler(page, [0, 70.05])).ticks).toEqual(["0", "20", "40", "60"]);
  await placePeak(page, "POWER TBIN 1", "max", time, values, "MW", testInfo.outputPath("maximum-callout.png"));
  await placePeak(page, "POWER TBIN 1", "min", time, values, "MW");
  await page.locator("#wwCursorModeBtn").click();
  for (const [kind, i] of [["a", 0], ["b", 382], ["a", 1401], ["a", 382], ["b", 0]]) await dragCursor(page, kind, time[i], "POWER TBIN 1", values[i]);
  await page.screenshot({ path: testInfo.outputPath("elapsed-cursors.png"), fullPage: true });
  // Existing t0 uses the requested pointer time, not a sample-snapped origin.
  const origin = await page.evaluate(() => wwTimeGroupCursorState(wwActiveTimeGroupId()).a.time);
  expect(origin).toBeCloseTo(19.1, 3);
  await page.locator("#wwT0Btn").click(); await assertRuler(page, [-origin, 70.05 - origin], true);
  await dragCursor(page, "b", 70.05, "POWER TBIN 1", values[1401], origin);
  await expect(page.locator(".ww-tg-cursor-readout-value--a")).toHaveText("+0.000 ms");
  await page.locator("#wwT0Btn").click(); await assertRuler(page, [0, 70.05]);
});

for (const [rateHz, durationS] of [[5000, .2], [20, 70.05], [1, 180]]) {
  test(`COMTRADE ${rateHz} Hz / ${durationS}s: positive-only, negative-only and bipolar extrema`, async ({ page }) => {
    const channels = ["Positive", "Negative", "Bipolar"].map(name => ({ name, unit: "MW", amplitude: 30000 }));
    const record = syntheticComtrade({ station: "UAT_SIGNS", startClock: "10:00:00.000000", rateHz, durationS, channels });
    const time = Array.from({ length: Math.round(rateHz * durationS) + 1 }, (_, i) => i / rateHz);
    const values = [time.map((_, i) => 10 + i % 21), time.map((_, i) => -10 - i % 21), time.map((_, i) => i % 2 ? 50 : -50)];
    const dat = Buffer.from(time.map((t, i) => [i + 1, Math.round(t * 1e6), ...values.map(v => v[i])].join(",")).join("\n") + "\n");
    await upload(page, [{ name: "signs.cfg", buffer: record.cfg, mimeType: "text/plain" }, { name: "signs.dat", buffer: dat, mimeType: "text/plain" }], false);
    for (let c = 0; c < channels.length; c++) {
      await display(page, channels[c].name); await assertRuler(page, [0, durationS]);
      for (const mode of ["max", "min"]) await placePeak(page, channels[c].name, mode, time, values[c], "MW");
      if (await page.locator("#wwCursorModeBtn").getAttribute("aria-pressed") !== "true") await page.locator("#wwCursorModeBtn").click();
      await dragCursor(page, "a", 0, channels[c].name, values[c][0]);
      await dragCursor(page, "b", durationS, channels[c].name, values[c][values[c].length - 1]);
      if (rateHz === 20 && c === 2) {
        await page.locator("#timeModeAbsoluteBtn").click();
        await expect(page.locator(".ww-tg-ruler-chart .xtitle")).toHaveText("Record Time");
        await expect(page.locator(".ww-tg-ruler-chart .xtick text").first()).toContainText("10:00:");
        await page.locator("#timeModeElapsedBtn").click(); await assertRuler(page, [0, durationS]);
      }
      await rowFor(page, channels[c].name).click();
    }
  });
}
for (const [name, variable, fallback, channel] of [
  ["GPTH Fast", "GPTH_BEN_PATH", null, "SDAI2 IB"], ["Permas Fast", "PERMAS_BEN_PATH", null, "KTBR2 IR"],
  ["BPHE Fast", "BPHE_BEN_PATH", null, "YGPN/BBTU1 IR"], ["BEN32 Fast", null, "synthetic_fast.ben", "LINE1 VR"],
  ["BEN32 Slow", null, "synthetic_slow.ben", "POWER LINE1"],
]) {
  test(`${name}: rendered extrema and ruler preserve native time/value domain`, async ({ page }) => {
    const filename = variable ? process.env[variable] : path.join(__dirname, "../backend/tests/fixtures/ben", fallback);
    test.skip(!filename, `Set ${variable} to the existing owner reference`);
    const url = await upload(page, [filename]); await display(page, channel);
    const response = await page.request.get(`${url}/waveform`, { params: { channel_name: channel, point_budget: 1000000 } });
    expect(response.status()).toBe(200); const full = await response.json();
    expect(full.time.length).toBe(full.values.length); expect(full.time.length).toBeGreaterThan(1);
    await assertRuler(page, [full.time[0], full.time[full.time.length - 1]]);
    for (const mode of ["max", "min"]) await placePeak(page, channel, mode, full.time, full.values, full.unit);
    await page.locator("#wwCursorModeBtn").click();
    await dragCursor(page, "a", full.time[0], channel, full.values[0]);
    await dragCursor(page, "b", full.time[full.time.length - 1], channel, full.values[full.values.length - 1]);
  });
}
