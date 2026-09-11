const { test, expect } = require("@playwright/test");
const path = require("path");

const FIXTURES = path.join(__dirname, "..", "backend", "tests", "fixtures", "comtrade");
const STEM = "phasor_smoke_three_phase";
const BARE_STEM = "phasor_bare_three_phase";

async function uploadBareFixture(page) {
  await page.goto("/index.html");
  await page.locator("#recordingsUploadBtn, #recordingsEmptyUploadBtn").first().click();
  await expect(page.locator("#uploadModalOverlay")).toBeVisible();
  await page.locator("#uploadModalFile_0").setInputFiles(path.join(FIXTURES, `${BARE_STEM}.cfg`));
  await page.locator("#uploadModalFile_1").setInputFiles(path.join(FIXTURES, `${STEM}.dat`));
  await page.locator("#uploadModalSubmitBtn").click();
  await page.locator("#uploadModalOverlay").waitFor({ state: "hidden" });
}

async function openAnalysisPhasor(page) {
  await page.locator("#mainNavAnalysisBtn").click();
  await expect(page.locator("#pageAnalysis")).toBeVisible();
  await expect(page.locator("#wwAnalysisTypePhasorBtn")).toHaveClass(/active/);
  await expect(page.locator("#wwPhasorPanel")).toBeVisible();
}

test.describe("Phasor bare Engineering Context bootstrap", () => {
  test("bare VA/VB/VC/IA/IB/IC source populates the Bay selector and roles", async ({ page }) => {
    await uploadBareFixture(page);
    await openAnalysisPhasor(page);

    await expect(page.locator("#wwPhasorContextSelect option")).toHaveCount(2, { timeout: 10000 });
    await expect(page.locator("#wwPhasorContextSelect option").nth(1)).toHaveText("Default Context");
    await expect(page.locator("#wwPhasorContextSelect")).not.toHaveValue("");
    await expect(page.locator("#wwPhasorContextBadge")).toContainText("Suggested");

    await expect(async () => {
      const text = await page.locator("#wwPhasorValuesList").innerText();
      for (const role of ["Va", "Vb", "Vc", "Ia", "Ib", "Ic"]) expect(text).toContain(role);
    }).toPass({ timeout: 5000 });
  });
});
