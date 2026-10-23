// Unknown recorder time is distinct from the existing naive-source policy.
const { test, expect } = require("@playwright/test");

// Synthetic file using the GPTH header clock, without owner waveform data.
const { clockFixture } = require("./support/ben5k_clock");

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
