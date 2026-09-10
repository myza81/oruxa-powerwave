// UAT regression (2026-09-10): Raw Data Preview's sticky column-header
// row let scrolled-under row values show through it. A first fix
// (commit 4d68e9d, changing the header's `background` from a low-alpha
// wash token to the opaque --panel token) proved INSUFFICIENT in real
// UAT -- structural source-text tests had only proven the CSS token
// existed, never that the rendered header was actually opaque.
//
// Root cause found via real computed styles (getComputedStyle), not
// source reading: `.ww-data-prep-table th.ww-data-prep-col-ignored`
// (every column defaults to "Not Assigned" until a role is picked, so
// this hits nearly every header on a freshly uploaded source) applied
// element-level `opacity: 0.45`. CSS `opacity` composites the WHOLE
// element -- background included -- against whatever sits behind it,
// so the header's own `background: var(--panel)` was genuinely solid
// in isolation while the element's overall on-screen paint was only
// 45% opaque. The fix replaced that with a `color`-only dimming rule
// (never touches background compositing) -- see frontend/index.html's
// own comment at the `.ww-data-prep-table th.ww-data-prep-col-ignored`
// rule for the full explanation.
//
// This test asserts the REAL rendered state a structural test cannot:
// computed `opacity` is 1, computed `background-color` has full alpha,
// and the header cell's own bounding box stays pinned to the top of
// its scroll container after the table is scrolled -- proving both
// "opaque" and "still sticky" on the actual browser-painted element,
// for exactly the "Not Assigned" column header the real bug hit.

const { test, expect } = require("@playwright/test");

function csvRows(n) {
  const lines = [];
  for (let i = 0; i < n; i++) {
    const minute = String(Math.floor(i / 60)).padStart(2, "0");
    const second = String(i % 60).padStart(2, "0");
    const value = (70 + (i % 10) + i * 0.01).toFixed(2);
    lines.push("2026-08-31 13:" + minute + ":" + second + "," + value);
  }
  return lines.join("\n") + "\n";
}

// Parses a computed `rgb(r, g, b)` / `rgba(r, g, b, a)` string into its
// alpha channel (1 when the format carries no alpha component at all).
function alphaOf(colorString) {
  const match = colorString.match(/rgba?\(([^)]+)\)/);
  if (!match) throw new Error("Unexpected color format: " + colorString);
  const parts = match[1].split(",").map((p) => p.trim());
  return parts.length === 4 ? Number(parts[3]) : 1;
}

test("Data Preparation: Raw Data Preview sticky header stays fully opaque while scrolled", async ({ page }) => {
  const consoleErrors = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(msg.text());
  });
  page.on("pageerror", (err) => consoleErrors.push(`pageerror: ${err.message}`));

  await test.step("Setup - upload a CSV with enough rows to scroll, leave columns Not Assigned", async () => {
    await page.goto("/index.html");
    await expect(page.locator("#pageRecordings")).toBeVisible();

    await page.locator("#recordingsUploadBtn, #recordingsEmptyUploadBtn").first().click();
    await expect(page.locator("#uploadModalOverlay")).toBeVisible();
    await page.locator("#uploadModalFormatSelect").selectOption("csv");
    await page.locator("#uploadModalFile_0").setInputFiles({
      name: "sticky_header.csv",
      mimeType: "text/csv",
      buffer: Buffer.from(csvRows(120)),
    });
    await page.locator("#uploadModalSubmitBtn").click();
    await page.locator("#uploadModalOverlay").waitFor({ state: "hidden" });

    const row = page.locator('#recordingsTableBody tr[data-source-id][data-recording-kind="csv"]').first();
    await expect(row).toBeVisible();
    await row.click();
    await expect(page.locator("#pageDataPreparation")).toBeVisible();
    await expect(page.locator("#wwDataPrepTable tbody tr").first()).toBeVisible();
  });

  await test.step("The sticky header cell for a Not Assigned column is fully opaque and stays pinned after scrolling", async () => {
    const wrap = page.locator("#wwDataPrepTable").locator(
      "xpath=ancestor::*[contains(concat(' ', normalize-space(@class), ' '), ' ww-data-prep-table-wrap ')][1]"
    );
    await wrap.scrollIntoViewIfNeeded();

    // The header cell under test: the FIRST real column header (index 0
    // is the always-empty corner cell) -- every column in this upload is
    // left at its default "Not Assigned" role, i.e. carries
    // .ww-data-prep-col-ignored, the exact class the real regression was
    // in.
    const th = page.locator("#wwDataPrepTable thead tr th").nth(1);
    await expect(th).toHaveClass(/ww-data-prep-col-ignored/);

    const before = await th.evaluate((el) => el.getBoundingClientRect().top);

    // Scroll the table's own scroll container, not the page -- this is
    // what makes body rows travel underneath the sticky header.
    await wrap.evaluate((el) => { el.scrollTop = Math.round(el.scrollHeight * 0.4); });
    await page.waitForTimeout(100);

    const after = await th.evaluate((el) => {
      const cs = getComputedStyle(el);
      const rect = el.getBoundingClientRect();
      return {
        top: rect.top,
        position: cs.position,
        opacity: cs.opacity,
        backgroundColor: cs.backgroundColor,
      };
    });

    // Still sticky: the header cell's own screen position did not move
    // with the scroll (it would have moved up by the same amount as the
    // scroll delta if it were an ordinary, non-sticky element).
    expect(after.position).toBe("sticky");
    expect(Math.abs(after.top - before)).toBeLessThan(1);

    // The actual regression: NOT a check that the CSS token/string
    // exists (that already passed before this fix, and was still
    // broken in real UAT) -- the element's own computed opacity and
    // background alpha, as the browser actually paints them.
    expect(after.opacity).toBe("1");
    expect(alphaOf(after.backgroundColor)).toBe(1);
  });

  await test.step("No unexpected console/page errors", async () => {
    expect(consoleErrors).toEqual([]);
  });
});
