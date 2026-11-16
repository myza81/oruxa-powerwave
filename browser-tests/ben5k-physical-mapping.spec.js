// Physical mapping only. Existing packed-word gain/offset is intentionally
// retained; these checks do not certify BEN5K absolute calibration.
const { test, expect } = require("./support/test");
const fs = require("fs");
const crypto = require("crypto");
const goldens = require("../backend/tests/fixtures/ben/ben5k_physical_mapping.json");

for (const record of goldens.records) {
  test(`${record.id}: plotted affected Voltage and Current use physical payload slots`, async ({ page }) => {
    const referenceVariable = record.id === "gpth" ? "GPTH_BEN_PATH" : "PERMAS_BEN_PATH";
    const filename = process.env[referenceVariable];
    test.skip(!filename || !fs.existsSync(filename), `Exact owner BEN5K recording unavailable; set ${referenceVariable}`);
    const original = fs.readFileSync(filename);
    expect(crypto.createHash("sha256").update(original).digest("hex")).toBe(record.sha256);
    const errors = [];
    page.on("pageerror", error => errors.push(error.message));
    await page.goto("/index.html");
    await page.locator("#recordingsUploadBtn, #recordingsEmptyUploadBtn").first().click();
    await page.locator("#uploadModalFormatSelect").selectOption("ben");
    await page.locator("#uploadModalFile_0").setInputFiles(filename);
    await page.locator("#uploadModalSubmitBtn").click();
    await expect(page.locator("#uploadModalOverlay")).toBeHidden({ timeout: 30000 });
    const row = page.locator("#recordingsTableBody tr[data-source-id]").first();
    const sid = await row.getAttribute("data-source-id");
    await row.click();
    const names = record.id === "gpth" ? ["SDNK1 VR", "SDAI2 IB"] : ["KTBR2 VR", "KTBR2 IR"];
    for (const name of names) {
      const golden = record.channels.find(channel => channel.name === name);
      const gain = original.readFloatLE(golden.descriptor_offset + 28);
      const offset = original.readFloatLE(golden.descriptor_offset + 32);
      const expected = Array.from({ length: record.sample_count }, (_, i) => {
        const address = record.payload_offset + 2 * (i * record.words_per_sample + golden.physical_word_index);
        return original.readInt16BE(address) * gain + offset;
      });
      const channel = page.locator(`#channelGroups tr.channel-row--toggle[data-channel-kind="analog"][data-channel-name="${name}"]`);
      await channel.click();
      await expect(channel).toHaveAttribute("aria-pressed", "true");
      const plottedValues = () => page.evaluate(({ sid, name }) => {
        const traces = [...document.querySelectorAll(".ww-chart")].flatMap(chart => chart.data || []);
        const trace = traces.find(item => item.meta === `${sid}::${name}`);
        return trace ? Array.from(trace.y) : [];
      }, { sid, name });
      await expect.poll(async () => (await plottedValues()).length).toBe(expected.length);
      expect(await plottedValues()).toEqual(expected);
    }
    expect(errors).toEqual([]);
  });
}
