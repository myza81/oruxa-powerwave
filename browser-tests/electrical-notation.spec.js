// DEC-117: cross-cutting guardrails for the shared electrical-symbol
// formatter. Per-surface coverage lives in the area suites (Calculated
// Channels, Phasor, Sequence, Impedance, Distance, Related Waveforms,
// Compliance); this file pins the formatter contract itself, the TRUE
// visual subscript position in hostile layout contexts (the owner-UAT
// superscript defect), and the plain-by-design cases.
//
//   rich  -> real subscript: V<sub>A</sub> V<sub>AB</sub> V<sub>1</sub> I<sub>2</sub>
//   plain -> concatenated:   VA VAB V1 I2 (never an underscore-joined form)

const { test, expect } = require("@playwright/test");
const fs = require("fs");
const os = require("os");
const path = require("path");

const { expectTrueSubscripts } = require("./support/electrical_notation_helpers");

const FIXTURES = path.join(__dirname, "..", "backend", "tests", "fixtures", "comtrade");

test.describe("Electrical notation (DEC-117) -- shared formatter", () => {
  test("contract: rich -> real subscript, plain -> VA/VAB/V1/I2, never an underscore", async ({ page }) => {
    await page.goto("/index.html");
    const out = await page.evaluate(() => {
      const cases = [["V", "A"], ["V", "AB"], ["V", "1"], ["I", "2"], ["V", "0"], ["I", "0"]];
      return {
        rows: cases.map(([q, s]) => ({
          key: q + s,
          text: wwElectricalSymbolText(q, s),
          html: wwElectricalSymbolHtml(q, s),
          plotly: wwElectricalSymbolPlotly(q, s),
          svg: wwElectricalSymbolSvg(q, s),
        })),
        roles: ["Va", "Vb", "Vc", "V1", "V2", "V0", "I1", "I2", "I0", "Ia", "Za"].map((k) => ({
          key: k, text: wwRoleLabelText(k), html: wwRoleLabelHtml(k), plotly: wwRoleLabelPlotly(k), svg: wwRoleLabelSvg(k),
        })),
        formula: { html: wwLineToLineFormulaHtml("BC"), text: wwLineToLineFormulaText("BC") },
        // Not a supported symbol (phase currents are deliberately plain):
        unsupported: { html: wwElectricalSymbolHtml("I", "A"), text: wwElectricalSymbolText("I", "A") },
        voltageShorthand: [wwVoltageSymbolText("CA"), wwVoltageSymbolHtml("CA")],
      };
    });
    for (const r of out.rows) {
      const [q, s] = [r.key[0], r.key.slice(1)];
      expect(r.text).toBe(q + s);
      expect(r.html).toBe(`<span class="ww-electrical-symbol">${q}<sub class="ww-electrical-sub">${s}</sub></span>`);
      expect(r.plotly).toBe(`${q}<sub>${s}</sub>`);
      expect(r.svg).toMatch(new RegExp(`^${q}<tspan [^>]*dy="[0-9.]+em"[^>]*>${s}</tspan>$`));
    }
    const role = Object.fromEntries(out.roles.map((r) => [r.key, r]));
    expect(role.Va.text).toBe("VA");
    expect(role.V1.plotly).toBe("V<sub>1</sub>");
    expect(role.I2.html).toContain('<sub class="ww-electrical-sub">2</sub>');
    expect(role.Ia).toEqual({ key: "Ia", text: "Ia", html: "Ia", plotly: "Ia", svg: "Ia" }); // phase current: plain
    expect(role.Za.html).toBe("Za"); // impedance: out of scope
    expect(out.formula.text).toBe("VBC = VB − VC");
    expect((out.formula.html.match(/<sub class="ww-electrical-sub">/g) || []).length).toBe(3);
    expect(out.unsupported).toEqual({ html: "IA", text: "IA" });
    expect(out.voltageShorthand[0]).toBe("VCA");
    // Never an underscore-joined symbol in ANY output.
    const all = JSON.stringify(out);
    expect(all).not.toMatch(new RegExp("[VI]" + "_" + "\\{?(AB|BC|CA|A|B|C|0|1|2)"));
  });

  test("true visual subscript in normal, flex, grid, .ww-cc-field and SVG contexts (light + dark)", async ({ page }) => {
    await page.goto("/index.html");
    for (const theme of ["light", "dark"]) {
      await page.evaluate((t) => {
        document.documentElement.setAttribute("data-theme", t);
        document.getElementById("zzProbe")?.remove();
        const symbols = [["V", "A"], ["V", "AB"], ["V", "1"], ["I", "2"]].map(([q, s]) => wwElectricalSymbolHtml(q, s)).join(" ");
        const probe = document.createElement("div");
        probe.id = "zzProbe";
        probe.style.cssText = "position:fixed;left:10px;top:10px;z-index:9999;background:var(--panel);padding:8px;font-size:14px";
        probe.innerHTML =
          '<p class="zz-ctx">' + symbols + "</p>" +
          '<div class="zz-ctx" style="display:flex;gap:12px;align-items:center">' + symbols + "</div>" +
          '<div class="zz-ctx" style="display:grid;grid-template-columns:repeat(4,auto)">' + symbols + "</div>" +
          // The owner-UAT context: generic `.ww-cc-field span { display: flex }`.
          '<label class="ww-cc-field zz-ctx"><span>' + symbols + "</span></label>" +
          '<div class="zz-ctx" style="display:inline-flex"><strong>' + symbols + "</strong></div>" +
          '<svg class="zz-svg" viewBox="0 0 120 20" width="240" height="40"><text x="4" y="14" font-size="12">' + wwElectricalSymbolSvg("V", "AB") + "</text></svg>";
        document.body.appendChild(probe);
      }, theme);
      const geometry = await expectTrueSubscripts(page.locator("#zzProbe .ww-electrical-symbol"), 20);
      expect(geometry.map((g) => g.text)).toEqual(Array(5).fill(["VA", "VAB", "V1", "I2"]).flat()); // textContent = plain fallback
      const svgDrop = await page.locator("#zzProbe .zz-svg text").evaluate((text) => {
        const tspan = text.querySelector("tspan");
        const r = document.createRange(); r.setStart(text.firstChild, 0); r.setEnd(text.firstChild, 1);
        return tspan.getBoundingClientRect().bottom - r.getBoundingClientRect().bottom;
      });
      expect(svgDrop, "SVG subscript lowered").toBeGreaterThan(0.5);
    }
  });

  test("source name with spaces (SLKS VB) and the Phase column stay exactly as supplied", async ({ page }) => {
    // The owner's example naming, generated from a committed fixture at
    // test time (no new fixture files): KPDN1_VR -> "SLKS VR", etc.
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "pw-notation-"));
    const cfg = fs.readFileSync(path.join(FIXTURES, "line_to_line_multibay.cfg"), "utf8").replace(/KPDN1_/g, "SLKS ");
    fs.writeFileSync(path.join(dir, "slks_names.cfg"), cfg);
    fs.copyFileSync(path.join(FIXTURES, "line_to_line_multibay.dat"), path.join(dir, "slks_names.dat"));

    await page.goto("/index.html");
    await page.locator("#recordingsUploadBtn, #recordingsEmptyUploadBtn").first().click();
    await page.locator("#uploadModalFile_0").setInputFiles(path.join(dir, "slks_names.cfg"));
    await page.locator("#uploadModalFile_1").setInputFiles(path.join(dir, "slks_names.dat"));
    await page.locator("#uploadModalSubmitBtn").click();
    await page.locator("#uploadModalOverlay").waitFor({ state: "hidden" });
    await page.locator("#recordingsTableBody tr[data-source-id]").first().click();

    const rows = page.locator('#channelGroups tr.channel-row--toggle[data-channel-kind="analog"]');
    await expect(rows.first()).toBeVisible();
    for (const name of ["SLKS VR", "SLKS VY", "SLKS VB"]) {
      const row = rows.filter({ hasText: name });
      await expect(row).toHaveCount(1);
      await expect(row.locator("td").first()).toContainText(name); // source name verbatim
      const phase = row.locator("td").nth(1);
      await expect(phase).toHaveText(/^(A|B|C|—)$/); // phase classification: a plain letter
      await expect(row.locator(".ww-electrical-symbol")).toHaveCount(0);
    }
    // Nothing in the source-channel table is a system symbol.
    await expect(page.locator("#channelGroups .ww-electrical-symbol")).toHaveCount(0);
  });
});
