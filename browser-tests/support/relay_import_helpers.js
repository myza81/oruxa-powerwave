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
// "address name" | value | printed range, the nominal-current tap table, operating timers whose setting cell is blank with Infinity in the
// range column (as the real sheet has them), and zone notes.
// `overrides` maps an address to a replacement value; `notes` replaces the scheme notes.
const S7SA511_ROWS = [
  ["1103", "Un PRIMARY", "110", "1-1200 kV"], ["1104", "Un SECOND.", "100", "80-125 V"], ["1105", "In PRIMARY", "800", "10-5000 AMP"],
  ["1117", "RE/RL", "0.7", "-7.00 to 7.00"], ["1118", "XE/XL", "0.4", "-7.00 to 7.00"], ["1122", "X SEC", "0.4", "0.010-5.000 ohms/km"],
  ["1124", "LINELENGTH", "25", "1.0-550.0 km"], ["1201", "DIST.PROT.", "ON", "ON,OFF"], ["1202", "DIR. FD&T4", "FORWARDS", "FWD,RVS,N/DIR"],
  ["1203", "T4", "", "Infinity"],
  ["1301", "R1", "2", "0.05-65 ohms"], ["1302", "X1", "3", "0.05-130 ohms"], ["1303", "R1E", "6", "0.05-130 ohms"], ["1304", "DIREC. Z1", "FORWARDS", "FWD,RVS,N/DIR"],
  ["1305", "T1 1PHASE", "", "Infinity"], ["1306", "T1 >1PHASE", "", "Infinity"],
  ["1311", "R2", "3", "0.05-65 ohms"], ["1312", "X2", "5", "0.05-130 ohms"], ["1313", "R2E", "8", "0.05-130 ohms"], ["1314", "DIREC. Z2", "FORWARDS", "FWD,RVS,N/DIR"],
  ["1315", "T2 1PHASE", "", "Infinity"], ["1316", "T2 >1PHASE", "", "Infinity"],
  ["1321", "R3", "1", "0.05-65 ohms"], ["1322", "X3", "1.5", "0.05-130 ohms"], ["1323", "R3E", "3", "0.05-130 ohms"], ["1324", "DIREC. Z3", "REVERSE", "FWD,RVS,N/DIR"],
  ["1325", "T3", "", "Infinity"],
  ["1401", "R1B", "3", "0.05-65 ohms"], ["1402", "X1B", "5", "0.05-130 ohms"], ["1403", "R1BE", "8", "0.05-130 ohms"], ["1404", "DIREC. Z1B", "FORWARDS", "FWD,RVS,N/DIR"],
  ["1405", "T1B 1PHASE", "", "Infinity"], ["1406", "T1B >1PHASE", "", "Infinity"],
  ["1411", "R1L", "65", "0.05-65 ohms"], ["1412", "X1L", "130", "0.05-130 ohms"], ["1413", "R1LE", "130", "0.05-130 ohms"], ["1414", "DIREC. Z1L", "NON-DIRECTIONAL", "FWD,RVS,N/DIR"],
  ["1415", "T1L", "", "Infinity"],
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

// A multi-page variant of buildPdf for sheets longer than one page of text.
function buildPdfPages(pages) {
  const contents = pages.map((lines) => "BT /F1 10 Tf\n" + lines.map(([x, y, t]) => `1 0 0 1 ${x} ${y} Tm (${t}) Tj`).join("\n") + "\nET");
  const n = pages.length;
  const objs = ["<< /Type /Catalog /Pages 2 0 R >>", `<< /Type /Pages /Count ${n} /Kids [${pages.map((_, i) => `${4 + i} 0 R`).join(" ")}] >>`, "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"];
  pages.forEach((_, i) => objs.push(`<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 842] /Resources << /Font << /F1 3 0 R >> >> /Contents ${4 + n + i} 0 R >>`));
  contents.forEach((c) => objs.push(`<< /Length ${c.length} >>\nstream\n${c}\nendstream`));
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

// A synthetic Hitachi Energy RED670-shaped sheet (Relion 670 naming): name | value | printed range, function-instance
// headings (IMP_PROT/DistanceZones/ZMQPDIS:n) and instance-prefixed parameters (ZMnn-:X1). Invented numbers; the owner's
// real sheet is never committed. `fifthZone` adds an enabled reverse ZMQPDIS:5 instance.
function red670Zone(n, { operation = "ON", direction = "Forward", x1 = "6", r1 = "1", x0 = "18", r0 = "5", rfpp = "7", rfpe = "15", pp = "ON", pe = "ON", gate = "ON", t = "0.15", ibase = "1200", ubase = "220" } = {}) {
  const p = `ZM${String(n).padStart(2, "0")}-:`;
  return [
    [`IMP_PROT/DistanceZones/ZMQPDIS:${n}`], [p + "Operation", operation, "OFF/ON"], [p + "IBase", ibase, "1-99999"], [p + "UBase", ubase, "0.05-2000"],
    [p + "OperationDir", direction, "Off/Non-dir/Forw/Rev"], [p + "X1", x1, "0.1-3000"], [p + "R1", r1, "0.01-1000"], [p + "X0", x0, "0.1-9000"],
    [p + "R0", r0, "0.01-3000"], [p + "RFPP", rfpp, "0.1-3000"], [p + "RFPE", rfpe, "0.1-9000"], [p + "OperationPP", pp, "OFF/ON"],
    [p + "Timer tPP", gate, "OFF/ON"], [p + "tPP", t, "0-60"], [p + "OperationPE", pe, "OFF/ON"], [p + "Timer tPE", gate, "OFF/ON"],
    [p + "tPE", t, "0-60"], [p + "IMinOpPP", "20", "10-1000"], [p + "IMinOpPE", "10", "10-1000"],
  ];
}
function red670Pdf({ fifthZone = false, zones = {} } = {}) {
  const rows = [
    ["LZOP: 275kV AAAA - BBBB No 1", "Scheme: RED670_V1.2_21_F11L"], ["Utility ID: 1", "Active Group: SET-TEST-R1"], ["TAP NAME", "TAP SETTING", "TAP RANGE"],
    ["HW Configuration/TRM_61_6U_3I"],
  ];
  [[1, "CH1_IL1"], [2, "CH2_IL2"], [3, "CH3_IL3"], [4, "CH4_IN"]].forEach(([n, nm]) =>
    rows.push([`NAMECH${n}`, nm], [`ChannelType${n}`, "CurrentProtection"], [`CTsec${n}`, "1", "1-10"], [`CTprim${n}`, "1200", "1-99999"]));
  [[7, "CH7_UL1"], [8, "CH8_UL2"], [9, "CH9_UL3"]].forEach(([n, nm]) =>
    rows.push([`NAMECH${n}`, nm], [`ChannelType${n}`, "Voltage"], [`VTsec${n}`, "110", "0.001-999.999"], [`VTprim${n}`, "220", "0.05-2000"]));
  rows.push(...red670Zone(1, { x1: "6", r1: "1", rfpp: "7", t: "0.15", ...(zones[1] || {}) }));
  rows.push(...red670Zone(2, { x1: "11", r1: "1.5", x0: "30", r0: "9", rfpp: "10", rfpe: "20", t: "0.45", ...(zones[2] || {}) }));
  rows.push(...red670Zone(3, { x1: "20", r1: "3", x0: "50", r0: "15", rfpp: "18", rfpe: "28", t: "3", ...(zones[3] || {}) }));
  rows.push(...red670Zone(4, { operation: "OFF", direction: "Off", x1: "0.1", r1: "0.01", x0: "0.1", r0: "0.01", rfpp: "0.1", rfpe: "0.1", pp: "OFF", pe: "OFF", gate: "OFF", t: "0", ibase: "1", ubase: "0.05", ...(zones[4] || {}) }));
  if (fifthZone) rows.push(...red670Zone(5, { direction: "Reverse", x1: "9", r1: "1", rfpp: "6", t: "1", ...(zones[5] || {}) }));
  rows.push(["IMP_PROT/DirectionalImpedance/ZDRDIR:1"], ["ZD01-:IBase", "1200", "1-99999"], ["ZD01-:ArgNegRes", "115", "90-175"], ["ZD01-:ArgDir", "15", "5-45"]);
  rows.push(["Zone 1", "Forward direction timer set to 0.15s"], ["Zone 4", "Inactive (Having duplicated BB Protection)"]);
  const X = [40, 230, 340];
  const perPage = 58;
  const pages = [];
  for (let i = 0; i < rows.length; i += perPage) {
    let y = 820;
    pages.push(rows.slice(i, i + perPage).flatMap((cells) => { y -= 13; return cells.map((c, k) => [X[k], y, c]); }));
  }
  return buildPdfPages(pages);
}

// Rows -> a multi-page PDF with name | value | range at the given x positions (an empty value cell stays empty).
function rowsPdf(rows, X = [40, 230, 340], perPage = 58) {
  const pages = [];
  for (let i = 0; i < rows.length; i += perPage) {
    let y = 820;
    pages.push(rows.slice(i, i + perPage).flatMap((cells) => { y -= 13; return cells.map((c, k) => [X[k], y, c]).filter(([, , c]) => c !== ""); }));
  }
  return buildPdfPages(pages);
}

// A synthetic Hitachi Energy REL670-shaped sheet: the same Relion 670 ZMQPDIS naming as RED670, but bare channel labels
// (IL1..UL3) and no ChannelType rows; Zone 4 is an enabled reverse zone. Invented numbers. `notes` replaces the
// trailing scheme-requirement lines (document notes, never settings).
const REL670_NOTES = [["Zone 1 Forward direction timer set to 0.15s"], ["Zone 4 Reverse direction timer set to 3s"]];
function rel670Pdf({ notes = REL670_NOTES } = {}) {
  const rows = [
    ["LZOP: 132kV AAAA - BBBB No 1", "Scheme: REL670_V1.2_21"], ["Utility ID: 1", "Active Group: SET-TEST-R1"], ["TAP NAME", "TAP SETTING", "TAP RANGE"],
    ["HW Configuration/TRM_61_6U_3I"],
  ];
  [[1, "IL1"], [2, "IL2"], [3, "IL3"], [4, "IN"]].forEach(([n, nm]) =>
    rows.push([`NAMECH${n}`, nm], [`CTsec${n}`, "1", "1-10"], [`CTprim${n}`, n === 4 ? "600" : "900", "1-99999"]));
  [[7, "UL1"], [8, "UL2"], [9, "UL3"]].forEach(([n, nm]) =>
    rows.push([`NAMECH${n}`, nm], [`VTsec${n}`, "110", "0.001-999.999"], [`VTprim${n}`, "132", "0.05-2000"]));
  rows.push(...red670Zone(1, { x1: "6", rfpp: "8", rfpe: "12", t: "0.15", ubase: "132", ibase: "900" }));
  rows.push(...red670Zone(2, { x1: "11", rfpp: "10", rfpe: "20", t: "0.45", ubase: "132", ibase: "900" }));
  rows.push(...red670Zone(3, { x1: "20", rfpp: "18", rfpe: "28", t: "3", ubase: "132", ibase: "900" }));
  rows.push(...red670Zone(4, { direction: "Reverse", x1: "2", rfpp: "3", rfpe: "5", t: "3", ubase: "132", ibase: "900" }));
  rows.push(["IMP_PROT/DirectionalImpedance/ZDRDIR:1"], ["ZD01-:ArgNegRes", "115", "90-175"], ["ZD01-:ArgDir", "15", "5-45"]);
  rows.push(...notes);
  return rowsPdf(rows);
}

// A synthetic Siemens SIPROTEC 5 7SL87-shaped sheet: DIGSI addresses inside the names (a wide name column), Edit mode
// Primary, operate-delay setting cells that are BLANK with "Infinity" in the range column, a distance characteristic
// angle of 82.7 deg and the phase-phase load cutout in use. Invented numbers.
function sl87Pdf() {
  const zone = (n, mode, dir, x, rpp, rpg) => {
    const p = `21.901.357${n}.`;
    return [[`21 Distance prot.1 > Z${n}`], [p + "1 Mode", mode, "off/on/test"], [p + "101 Function mode", "ph-gnd and ph-ph", "SIP5_Function mode"],
      [p + "114 Zone-spec. residu. comp.", "YES", "NO/YES"], [p + "109 Directional mode", dir, "Fwd/Rev/Non-dir"], [p + "102 X reach", x, "0.05-600"],
      [p + "103 R (ph-g)", rpg, "0.05-600"], [p + "104 R (ph-ph)", rpp, "0.05-600"], [p + "113 Zone-inclination angle", "0", "0-45"],
      [p + "110 Operate delay (1-phase)", "", "Infinity"], [p + "112 Operate delay (multi-ph.)", "", "Infinity"],
      [p + "105 Kr", "1.7", "-0.33-11"], [p + "106 Kx", "0.6", "-0.33-11"]];
  };
  const rows = [
    ["LZOP: 275kV AAAA - BBBB No 2", "Scheme: 7SL87_8.81"], ["Utility ID: 1", "Active Group: SET-TEST"], ["TAP NAME", "TAP SETTING", "TAP RANGE"],
    ["Edit mode", "Primary", "Edit Mode"], ["91.115 Set. format residu. comp.", "Kr, Kx", "KR, Kx/K0"],
    ["11.931.8881.101 Rated primary current", "1500", "1-100000"], ["11.931.8881.102 Rated secondary current", "1", "1-5"],
    ["11.941.8911.101 Rated primary voltage", "275", "0.2-1200"], ["11.941.8911.102 Rated secondary voltage", "110", "80-230"],
    ["21.901.2311.107 Dist. characteristic angle", "82.7", "30-90"],
    ["21.901.3661.105 Use ph-ph load cutout", "YES", "NO/YES"], ["21.901.3661.106 R load cutout (ph-ph)", "44.8", "0.092-1375"],
    ["21.901.3661.107 Angle load cutout (ph-ph)", "45", "15-65"],
    ...zone(1, "on", "Forward", "4.7", "3.1", "11"), ...zone(2, "on", "Forward", "8.5", "3.6", "14"),
    ["Zone 1", "Forward direction timer set to 0.15s"],
  ];
  return rowsPdf(rows, [20, 330, 450]);
}

// A synthetic Hitachi Energy (ABB) REL511-shaped sheet (flat TAP NAME | TAP SETTING | TAP RANGE): Zone 1 On with Z1Block On,
// Zone 2 Off with Z2Block Off. Invented numbers.
function rel511Pdf() {
  const zone = (n, op, dir, x, rf, rfn, block) => [
    [`Operation_Z${n}`, op, "On/Off"], [`X1Z${n}`, x, "0.1-150"], [`R1Z${n}`, "0.5", "0.1-150"], [`X0Z${n}`, "9", "0.1-1200"],
    [`R0Z${n}`, "3", "0.1-1200"], [`RFZ${n}`, rf, "0.1-150"], [`RFNZ${n}`, rfn, "0.1-150"], [`Timer t${n}`, "On", "On/Off"],
    [`t${n}`, "0", "0.0-10.0 s"], [`DirZ${n}`, dir, "Non/Forward/Reverse"], [`Z${n}Block`, block, "On/Off"]];
  const rows = [
    ["LZOP: 132kV AAAA - BBBB No 1", "Scheme: REL511_V1.2_TNB"], ["Utility ID: 1", "Active Group: SET-TEST"], ["TAP NAME", "TAP SETTING", "TAP RANGE"],
    ["Ur", "110", "100/110/115/120"], ["Ir", "1", "1"], ["VTPrim Uphases", "132", "1-9999"], ["CTPrim Iphases", "600", "1-9999"],
    ...zone(1, "On", "Forward", "3", "4.6", "15", "On"), ...zone(2, "Off", "Forward", "5", "6", "17", "Off"),
    ["Length unit", "KM", "KM/MI"], ["Line Length", "16", "0-10,000"],
  ];
  return rowsPdf(rows);
}

// A synthetic Toshiba GRZ100-shaped sheet: CT / VT stated as ratios, Quad phase and Mho earth selections, blinders. Invented.
function grz100Pdf() {
  const rows = [
    ["LZOP: 132kV AAAA - BBBB 1", "Scheme: GRZ100_201A_Ver2.1"], ["Utility ID: 1", "Active Group: Rev0"], ["TAP NAME", "TAP SETTING", "TAP RANGE"],
    ["[Parameter]"], ["VT", "1200", "1-20000"], ["CT", "1200", "1-20000"], ["X1", "6.7", "0.0-999.9 ohms"], ["R1", "1.2", "0.0-999.9 ohms"],
    ["X0", "21", "0.0-999.9 ohms"], ["R0", "7", "0.0-999.9 ohms"], ["Line", "24.9", "0.0-399.9 km"],
    ["ZS-C", "Quad", "Mho/Quad"], ["ZG-C", "Mho", "Mho/Quad"],
    ["Z1S", "5.72", "0.10-250.00 ohms"], ["BFRS", "20", "0.5-100.0 ohms"], ["BFLS-angle", "120", "90-135 degree"],
    ["TZ1S", "0", "0.00-10.00 s"], ["TZ2S", "0.3", "0.00-10.00 s"], ["TZ1G", "0", "0.00-10.00 s"],
    ["Zone 1", "Forward direction timer set to 0.0s"],
  ];
  return rowsPdf(rows);
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

module.exports = { BACKEND_PORT, buildPdf, p441Pdf, siemens7sa511Pdf, red670Pdf, rel670Pdf, rel511Pdf, sl87Pdf, grz100Pdf, routeConfig, openDistance, pick };
