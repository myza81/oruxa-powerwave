// Unknown recorder time is distinct from the existing naive-source policy.
const { test, expect } = require("@playwright/test");

// Synthetic file using the GPTH header clock, without owner waveform data.
function clockFixture() {
  const n = 3000, words = 40;
  const header = Buffer.alloc(0xdc);
  Buffer.from("0100040028ff03006e00ca00", "hex").copy(header);
  header.writeUInt16LE(5, 14);
  header.writeUInt16LE(1234, 12);
  header.write("CLOCK TEST", 16);
  header.writeUInt32LE(5000000, 0x54);
  header.writeUInt32LE(2500, 0x58);
  header.writeUInt32LE(n, 0x5c);
  header.writeUInt16LE(words, 0x60);
  Buffer.from("7e0a1012030e353600", "hex").copy(header, 0x64);
  header.writeUInt32LE(n - 1, 0x7a);
  const analog = Buffer.alloc(58), digital = Buffer.alloc(58);
  analog[1] = 1;
  analog.writeUInt16LE(0x528, 2);
  analog.write("CLOCK VR", 4);
  analog.writeFloatLE(0.01, 28);
  analog.writeFloatLE(-100, 36);
  analog.writeFloatLE(100, 40);
  analog[57] = 255;
  digital[0] = digital[1] = 1;
  digital[3] = digital[57] = 255;
  digital.write("CLOCK CB", 4);
  const payload = Buffer.alloc(n * words * 2);
  for (let i = 0; i < n; i++) {
    payload.writeUInt16BE(1000 + i % 100, i * words * 2);
    payload.writeUInt16BE(i % 2 ? 2 : 0, (i * words + 38) * 2);
  }
  return Buffer.concat([header, Buffer.alloc(0xaae - 0xdc + 12 * 22 + 4), analog, digital, payload]);
}

for (const timezoneId of ["UTC", "America/New_York", "Asia/Kuala_Lumpur"]) {
  test.describe(timezoneId, () => {
    test.use({ timezoneId });

    test("unknown clock stays on its original day with full precision", async ({ page }) => {
      await page.goto("/index.html");
      const result = await page.evaluate(() => {
        const source = {
          time_basis: "unknown", timing_reference: "relative_elapsed",
          start_time: "2026-10-16T18:03:14.035400",
          trigger_time: "2026-10-16T18:03:14.535400",
          // Even stale canonical companions cannot override explicit UNKNOWN.
          start_time_utc: "2026-10-16T18:03:14.035400Z",
          trigger_time_utc: "2026-10-16T18:03:14.535400Z",
        };
        return {
          recording: wwFormatRecordingTimeIdentity(source),
          sidebar: wwFormatRecordingTimeIdentity(source, { compact: true }),
          trigger: wwFormatSourceTimestamp(source, "trigger_time"),
          anchor: wwRecordingDisplayStartTime(source),
          midnight: wwFormatSourceTimestamp({ time_basis: "unknown", trigger_time: "2026-10-16T23:59:59.999999" }, "trigger_time"),
          verified: wwFormatEngineeringTimestamp("2026-10-16T10:03:14.537467Z"),
          verifiedRollover: wwFormatEngineeringTimestamp("2026-10-16T18:03:14.535400Z"),
        };
      });
      expect(result).toEqual({
        recording: "2026-10-16 18:03:14.035400 (timezone unverified)",
        sidebar: "2026-10-16 18:03:14.035400 (timezone unverified)",
        trigger: "2026-10-16 18:03:14.535400 (timezone unverified)",
        anchor: null,
        midnight: "2026-10-16 23:59:59.999999 (timezone unverified)",
        verified: "2026-10-16 18:03:14.537467",
        verifiedRollover: "2026-10-17 02:03:14.535400",
      });
    });

    test("upload, recording details, sidebar and waveform retain clock authority", async ({ page }, testInfo) => {
      const errors = [];
      page.on("pageerror", error => errors.push(error.message));
      await page.goto("/index.html");
      await page.locator("#recordingsUploadBtn, #recordingsEmptyUploadBtn").first().click();
      await page.locator("#uploadModalFormatSelect").selectOption("ben");
      await page.locator("#uploadModalFile_0").setInputFiles({ name: "clock.ben", mimeType: "application/octet-stream", buffer: clockFixture() });
      await page.locator("#uploadModalSubmitBtn").click();
      await expect(page.locator("#uploadModalOverlay")).toBeHidden();
      const row = page.locator("#recordingsTableBody tr[data-source-id]").first();
      await expect(row.locator(".recording-start-time-cell")).toHaveText("2026-10-16 18:03:14.035400 (timezone unverified)");
      await row.locator('[data-action="details"]').click();
      await expect(page.locator(".recording-details-row").first()).toContainText("2026-10-16 18:03:14.535400 (timezone unverified)");
      await row.click();
      await expect(page.locator("#workspaceRow")).toBeVisible();
      const source = page.locator("#channelGroups details.source-recording").first();
      await expect(source.locator(":scope > summary")).toContainText("2026-10-16 18:03:14.035400 (timezone unverified)");
      const channel = source.locator('tr.channel-row--toggle[data-channel-kind="analog"]').first();
      await channel.click();
      await expect(channel).toHaveAttribute("aria-pressed", "true");
      const timing = await page.evaluate(() => Array.from(ww.sourceTiming.values())[0]);
      expect(timing.recordingStartTime).toBeNull();
      expect(timing.timingReference).toBe("relative_elapsed");
      await expect(page.locator("#wwWorkspaceLoading")).toBeHidden();
      await expect(page.locator(".ww-chart .plotly").first()).toBeVisible();
      expect(errors).toEqual([]);
      await page.screenshot({ path: testInfo.outputPath("unknown-timezone.png") });
    });
  });
}
