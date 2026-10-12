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

// `overrides` maps a parameter code to a replacement value (e.g. { "300A": "1,43" } for
// an unreadable reach); `drop` lists parameter codes to leave out of the sheet; `extraRows` appends further rows (e.g. a conflicting duplicate).
function p441Pdf({ overrides = {}, extraRows = [], drop = [] } = {}) {
  let y = 800;
  const lines = [[40, y, "LZOP: 132kV AAAA - BBBB"], [230, y, "Scheme: SE_P441?A1???038?JE"]];
  const rows = P441_ROWS.filter((row) => !drop.includes(row[0])).map((row) => (overrides[row[0]] === undefined ? row : [row[0], row[1], overrides[row[0]], row[3]]));
  for (const row of [...rows, ...extraRows]) {
    y -= 12;
    row.forEach((cell, i) => lines.push([P441_X[i], y, cell]));
  }
  y -= 12;
  lines.push([40, y, "Zone 4 Defeated"]);
  return buildPdf(lines);
}


// A synthetic Siemens 7SA511-shaped sheet (invented numbers; the owner's real sheet is never committed):
// "address name" | value | printed range, the nominal-current tap table, Infinity delays and zone notes.
// `overrides` maps an address to a replacement value; `notes` replaces the scheme notes.
const S7SA511_ROWS = [
  ["1103", "Un PRIMARY", "110", "1-1200 kV"], ["1104", "Un SECOND.", "100", "80-125 V"], ["1105", "In PRIMARY", "800", "10-5000 AMP"],
  ["1117", "RE/RL", "0.7", "-7.00 to 7.00"], ["1118", "XE/XL", "0.4", "-7.00 to 7.00"], ["1122", "X SEC", "0.4", "0.010-5.000 ohms/km"],
  ["1124", "LINELENGTH", "25", "1.0-550.0 km"], ["1201", "DIST.PROT.", "ON", "ON,OFF"], ["1202", "DIR. FD&T4", "FORWARDS", "FWD,RVS,N/DIR"],
  ["1203", "T4", "Infinity", ""],
  ["1301", "R1", "2", "0.05-65 ohms"], ["1302", "X1", "3", "0.05-130 ohms"], ["1303", "R1E", "6", "0.05-130 ohms"], ["1304", "DIREC. Z1", "FORWARDS", "FWD,RVS,N/DIR"],
  ["1305", "T1 1PHASE", "Infinity", ""], ["1306", "T1 >1PHASE", "Infinity", ""],
  ["1311", "R2", "3", "0.05-65 ohms"], ["1312", "X2", "5", "0.05-130 ohms"], ["1313", "R2E", "8", "0.05-130 ohms"], ["1314", "DIREC. Z2", "FORWARDS", "FWD,RVS,N/DIR"],
  ["1315", "T2 1PHASE", "Infinity", ""], ["1316", "T2 >1PHASE", "Infinity", ""],
  ["1321", "R3", "1", "0.05-65 ohms"], ["1322", "X3", "1.5", "0.05-130 ohms"], ["1323", "R3E", "3", "0.05-130 ohms"], ["1324", "DIREC. Z3", "REVERSE", "FWD,RVS,N/DIR"],
  ["1325", "T3", "Infinity", ""],
  ["1401", "R1B", "3", "0.05-65 ohms"], ["1402", "X1B", "5", "0.05-130 ohms"], ["1403", "R1BE", "8", "0.05-130 ohms"], ["1404", "DIREC. Z1B", "FORWARDS", "FWD,RVS,N/DIR"],
  ["1405", "T1B 1PHASE", "Infinity", ""], ["1406", "T1B >1PHASE", "Infinity", ""],
  ["1411", "R1L", "65", "0.05-65 ohms"], ["1412", "X1L", "130", "0.05-130 ohms"], ["1413", "R1LE", "130", "0.05-130 ohms"], ["1414", "DIREC. Z1L", "NON-DIRECTIONAL", "FWD,RVS,N/DIR"],
  ["1415", "T1L", "Infinity", ""],
  ["1703", "PHPHE FLTS", "PHASE-PHASE ONLY", "PP,LEAD-PE,LAG-PE"], ["1704", "3PH FAULTS", "PHASE-PHASE ONLY", "EF,PP,PE"], ["1705", "1PH FAULTS", "PHASE-EARTH", "PE,PP"],
  ["7812", "DIST. PROT.", "EXIST", "EXIST,NOEXIST"],
];
function siemens7sa511Pdf({ overrides = {}, notes = true } = {}) {
  let y = 810;
  const lines = [[40, y, "LZOP: 132kV AAAA - BBBB"], [230, y, "Scheme: 7SA511_V3.2_1A"]];
  const row = (cells) => { y -= 11; cells.forEach((c, i) => c && lines.push([P441_X[i], y, c])); };
  row(["TAP NAME", "TAP SETTING", "TAP RANGE"]);
  row(["IN", "1", "1 AMP"]);
  for (const [code, name, value, range] of S7SA511_ROWS) row([`${code} ${name}`, overrides[code] ?? value, range]);
  if (notes) {
    row(["Zone 1", "Forward direction timer set to 0.15s (Delayed Zone 1)"]);
    row(["Zone 1B Inactive timer set to oos (Infinity)"]);
    row(["Zone 2", "Forward direction timer set to 0.45s"]);
  }
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

module.exports = { BACKEND_PORT, buildPdf, p441Pdf, siemens7sa511Pdf, routeConfig, openDistance, pick };
