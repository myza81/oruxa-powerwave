// Shared helpers for the Relay Import browser specs that need a P441-shaped
// setting sheet: a tiny real one-page text PDF (the backend parses uploads),
// opening Distance Protection, and picking a file.
//
// frontend/config.js pins the API to :8000. When PW_BACKEND_PORT is set the
// config is re-pointed per page via request interception -- nothing is committed.

const { expect } = require("@playwright/test");

const BACKEND_PORT = process.env.PW_BACKEND_PORT || "8000";

function buildPdf(lines) {
  const content = "BT /F1 10 Tf\n" + lines.map(([x, y, t]) => `1 0 0 1 ${x} ${y} Tm (${t}) Tj`).join("\n") + "\nET";
  const objs = [
    "<< /Type /Catalog /Pages 2 0 R >>",
    "<< /Type /Pages /Count 1 /Kids [4 0 R] >>",
    "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 842] /Resources << /Font << /F1 3 0 R >> >> /Contents 5 0 R >>",
    `<< /Length ${content.length} >>\nstream\n${content}\nendstream`,
  ];
  let out = "%PDF-1.4\n";
  const offsets = [];
  objs.forEach((o, i) => {
    offsets.push(out.length);
    out += `${i + 1} 0 obj\n${o}\nendobj\n`;
  });
  const xref = out.length;
  out += `xref\n0 ${objs.length + 1}\n0000000000 65535 f \n` + offsets.map((o) => `${String(o).padStart(10, "0")} 00000 n \n`).join("");
  out += `trailer\n<< /Size ${objs.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`;
  return Buffer.from(out, "latin1");
}

// code | name | value | printed range, as the owner's P441 sheet prints them.
const P441_ROWS = [
  ["0903", "Active Settings", "Group 1", "Grp 1/2/3/4"],
  ["090D", "Dist. Protection", "Enabled", "Enabled/Disabled"],
  ["092E", "Setting Values", "Secondary", "Sec'y/Primary"],
  ["0A01", "Main VT Primary", "132000", "100-1000000V"],
  ["0A02", "Main VT Sec'y", "110", "80-140V"],
  ["0A07", "Phase CT Primary", "1200", "1-30000A"],
  ["0A08", "Phase CT Sec'y", "1", "1A/5A"],
  ["0D07", "Distance Unit", "Kilometres", "Miles/km"],
  ["3002", "Line Length", "7.03", "0.3-1000"],
  ["3004", "Line Impedance", "2", "0.001-500 /I1"],
  ["3005", "Line Angle", "80", "-90 to +90 deg."],
  ["3007", "Zone Status", "01010", "P441 Zone Status"],
  ["3008", "kZ1 Res Comp", "0.718", "0-7"],
  ["3009", "kZ1 Angle", "-11.5", "-180 to +180 deg."],
  ["300A", "Z1", "1.43", "0.001-500 /I1"],
  ["300C", "R1G", "7.02", "0-400 /I1"],
  ["300D", "R1Ph", "2.11", "0-400 /I1"],
  ["300E", "tZ1", "0", "0-10.0 s"],
  ["3011", "Z2", "2.13", "0.001-500 /I1"],
  ["3012", "R2G", "10.47", "0-400 /I1"],
  ["3013", "R2Ph", "3.14", "0-400 /I1"],
  ["3014", "tZ2", "0.3", "0-10.0 s"],
  ["3017", "Z3", "4.48", "0.001-500 /I1"],
  ["3018", "R3G-R4G", "17.19", "0-400 /I1"],
  ["3019", "R3Ph-R4Ph", "6.34", "0-400 /I1"],
  ["301A", "tZ3", "3", "0-10.0 s"],
  ["301B", "Z4", "0.36", "0.001-500 /I1"],
  ["301C", "tZ4", "3", "0-10.0 s"],
  ["301D", "ZoneP - Direct", "Directional Fwd", "Directional FWD/REV"],
  ["3020", "Zp", "0.001", "0.001-500 /I1"],
  ["3023", "tZp", "10", "0-10.0 s"],
  ["3103", "Fault Type", "Both Enabled", "44x Fault Type"],
];
const P441_X = [40, 230, 340, 450];

function p441Pdf() {
  let y = 800;
  const lines = [[40, y, "LZOP: 132kV AAAA - BBBB"], [230, y, "Scheme: SE_P441?A1???038?JE"]];
  for (const row of P441_ROWS) {
    y -= 12;
    row.forEach((cell, i) => lines.push([P441_X[i], y, cell]));
  }
  y -= 12;
  lines.push([40, y, "Zone 4 Defeated"]);
  return buildPdf(lines);
}

async function routeConfig(page) {
  await page.route("**/config.js", (route) =>
    route.fulfill({
      contentType: "application/javascript",
      body: `window.POWERWAVE_CONFIG = { apiBaseUrl: "http://127.0.0.1:${BACKEND_PORT}", environment: "development", buildVersion: "local" };`,
    }),
  );
}

async function openDistance(page) {
  await page.goto("/index.html");
  await page.locator("#mainNavAnalysisBtn").click();
  await expect(page.locator("#pageAnalysis")).toBeVisible();
  await page.locator("#wwAnalysisTypeDistanceBtn").click();
  await expect(page.locator("#wwDistancePanel")).toBeVisible();
}

const pick = (page, name, buffer) =>
  page.locator("#wwRelayImportFileInput").setInputFiles({ name, mimeType: "application/pdf", buffer });

module.exports = { BACKEND_PORT, buildPdf, p441Pdf, routeConfig, openDistance, pick };
