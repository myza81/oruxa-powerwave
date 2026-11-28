// Temporary screenshot script for Slice C-3 UAT.
// Run from browser-tests/ directory.
// Usage: node take-c3-shots.js <output-dir>

const { chromium } = require("playwright");
const path = require("path");

const COMTRADE = path.join(__dirname, "..", "backend", "tests", "fixtures", "comtrade");
const BASE = process.env.PW_FRONTEND_URL || "http://localhost:8101";

(async () => {
    const outDir = process.argv[2] || __dirname;
    const browser = await chromium.launch();

    // Upload fixture, navigate to RD, select recording, return page ready for group selection
    async function uploadAndSelectRecording(page, mockGroupFn) {
        await page.goto(BASE + "/index.html");
        await page.locator("#recordingsUploadBtn, #recordingsEmptyUploadBtn").first().click();
        await page.waitForSelector("#uploadModalOverlay", { state: "visible" });
        await page.locator("#uploadModalFile_0").setInputFiles(path.join(COMTRADE, "synth_ascii.cfg"));
        await page.locator("#uploadModalFile_1").setInputFiles(path.join(COMTRADE, "synth_ascii.dat"));
        await page.locator("#uploadModalSubmitBtn").click();
        await page.locator("#uploadModalOverlay").waitFor({ state: "hidden" });
        await page.click("#mainNavRecordingDetailsBtn");
        await page.waitForSelector("#pageRecordingDetails", { state: "visible", timeout: 8000 });
        await page.waitForSelector(".ww-rd-recording-item", { state: "visible", timeout: 8000 });

        if (mockGroupFn) {
            await page.route("**/measurement-groups", async route => {
                const response = await route.fetch();
                const groups = await response.json();
                const ref = groups[0] || {};
                const mockGroup = mockGroupFn(ref);
                await route.fulfill({ json: [...groups, mockGroup] });
            });
        }

        await page.click(".ww-rd-recording-item");
        await page.waitForSelector(".ww-rd-group-item", { state: "visible", timeout: 8000 });
    }

    async function selectGroupByKind(page, kind, narrow) {
        if (!narrow) {
            await page.click("#wwRdTabGroupDetails");
        }
        await page.click(`#wwRdGroupKindFilter button[data-kind="${kind}"]`);
        await page.waitForSelector(".ww-rd-group-item", { state: "visible", timeout: 5000 });
        await page.click(".ww-rd-group-item");
        await page.waitForSelector(".ww-rd-section", { state: "visible", timeout: 5000 });
        await page.waitForTimeout(400);
    }

    async function selectGroupByName(page, name, narrow) {
        if (!narrow) {
            await page.click("#wwRdTabGroupDetails");
        }
        await page.waitForSelector(`#wwRdGroupsBody .ww-rd-group-item`, { state: "visible", timeout: 8000 });
        // Find the group item that contains the given text
        const item = page.locator("#wwRdGroupsBody .ww-rd-group-item", { hasText: name });
        await item.waitFor({ state: "visible", timeout: 8000 });
        await item.click();
        await page.waitForSelector(".ww-rd-section", { state: "visible", timeout: 5000 });
        await page.waitForTimeout(400);
    }

    // Shot 1: 1366x768 light — Voltage Group needs_review state (synth_ascii default)
    {
        const ctx = await browser.newContext({ viewport: { width: 1366, height: 768 }, colorScheme: "light" });
        const page = await ctx.newPage();
        await uploadAndSelectRecording(page, null);
        await selectGroupByKind(page, "voltage", false);
        const outPath = path.join(outDir, "c3-1366x768-light-voltage-needs-review.png");
        await page.screenshot({ path: outPath, fullPage: false });
        await ctx.close();
        console.log("saved:", outPath);
    }

    // Shot 2: 1366x768 light — Current Group (new equipment-capacity design)
    // Inject a mock current group with method="equipment_rating" to show the new design.
    {
        const ctx = await browser.newContext({ viewport: { width: 1366, height: 768 }, colorScheme: "light" });
        const page = await ctx.newPage();
        await uploadAndSelectRecording(page, (ref) => ({
            id: "mock-cg-equipment",
            workspace_id: ref.workspace_id || "mock-ws",
            source_id: ref.source_id || "mock-src",
            kind: "current",
            display_name: "MOCK_CURRENT_EQUIPMENT",
            channel_refs: [{ channel_name: "IA", channel_id: "mock-ia" }, { channel_name: "IB", channel_id: "mock-ib" }, { channel_name: "IC", channel_id: "mock-ic" }],
            status: "confirmed",
            created_at: null,
            pu_status: "not_applicable",
            pu_reason: null,
            voltage_config: null,
            current_config: {
                base_reference_side: "primary",
                method: "equipment_rating",
                equipment_rating_mva: 100.0,
                linked_voltage_group_id: "mock-vg-linked",
                manual_voltage_base_kv: null,
                manual_ibase_ka: null,
                resolved_ibase_ka: 0.4374,
                applicable_voltage_ll_kv: 132.0,
                base_authority: "auto_resolved"
            }
        }));
        await selectGroupByName(page, "MOCK_CURRENT_EQUIPMENT", false);
        const outPath = path.join(outDir, "c3-1366x768-light-current-group.png");
        await page.screenshot({ path: outPath, fullPage: false });
        await ctx.close();
        console.log("saved:", outPath);
    }

    // Shot 3: 1366x768 dark — Voltage Group available state (mock injection)
    {
        const ctx = await browser.newContext({ viewport: { width: 1366, height: 768 }, colorScheme: "dark" });
        const page = await ctx.newPage();
        await page.evaluate(() => {
            try { localStorage.setItem("ww-theme", "dark"); } catch (e) {}
        });
        await uploadAndSelectRecording(page, (ref) => ({
            id: "mock-vg-available",
            workspace_id: ref.workspace_id || "mock-ws",
            source_id: ref.source_id || "mock-src",
            kind: "voltage",
            display_name: "MOCK_AVAILABLE_GROUP",
            channel_refs: [],
            status: "confirmed",
            created_at: null,
            pu_status: "configured",
            pu_reason: null,
            voltage_config: {
                nominal_voltage_ll_kv: 132.0,
                reference_mode: "auto",
                reference_override: null,
                effective_reference: "line_to_ground",
                evidence_names: [],
                detection_reason: "mock",
                base_reference_side: "primary",
                secondary_voltage_ll_v: null,
                manual_conflict_detected: false,
                manual_conflict_detail: null,
                base_authority: "auto_resolved"
            },
            current_config: null
        }));
        await page.evaluate(() => {
            document.documentElement.setAttribute("data-theme", "dark");
        });
        await page.waitForTimeout(100);
        await selectGroupByName(page, "MOCK_AVAILABLE_GROUP", false);
        const outPath = path.join(outDir, "c3-1366x768-dark-voltage-available.png");
        await page.screenshot({ path: outPath, fullPage: false });
        await ctx.close();
        console.log("saved:", outPath);
    }

    // Shot 4: 390x844 light — narrow Voltage Group
    {
        const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, colorScheme: "light" });
        const page = await ctx.newPage();
        await uploadAndSelectRecording(page, null);
        // In narrow mode, click a voltage group directly (tab click not needed; group click advances to details)
        await page.click(`#wwRdGroupKindFilter button[data-kind="voltage"]`);
        await page.waitForSelector(".ww-rd-group-item", { state: "visible", timeout: 5000 });
        await page.click(".ww-rd-group-item");
        await page.waitForSelector(".ww-rd-section", { state: "visible", timeout: 5000 });
        await page.waitForTimeout(400);
        const outPath = path.join(outDir, "c3-390x844-light-voltage-narrow.png");
        await page.screenshot({ path: outPath, fullPage: false });
        await ctx.close();
        console.log("saved:", outPath);
    }

    await browser.close();
    console.log("Done.");
})().catch(e => { console.error(e); process.exit(1); });
