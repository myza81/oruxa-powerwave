// WUI-001 behavioral coverage; real isolated backend and source frontend.
const { test, expect } = require("./support/test");
const path = require("path");
const fs = require("fs");
const crypto = require("crypto");
const { uploadRecord } = require("./support/event_reconstruction_helpers");

const FIXTURES = path.join(__dirname, "..", "backend", "tests", "fixtures", "comtrade");

// Voltage + Current, different quantities -- Grouped mode's own "one
// panel per quantity" convention (the DEFAULT layout mode, which keeps
// each panel's own clickable .ww-panel-header) naturally puts these in
// TWO separate panels of the SAME Time Group, no Separate-layout-mode
// detour needed.
const VI_CHANNELS = [
  { name: "VA", unit: "V", phase: "A", amplitude: 100, frequencyHz: 50 },
  { name: "IA", unit: "A", phase: "A", amplitude: 5, frequencyHz: 50 },
];

async function uploadFixture(page, stem) {
  await page.goto("/index.html");
  await page.locator("#wwRdUploadBtn").first().click();
  await expect(page.locator("#uploadModalOverlay")).toBeVisible();
  await page.locator("#uploadModalFile_0").setInputFiles(path.join(FIXTURES, `${stem}.cfg`));
  await page.locator("#uploadModalFile_1").setInputFiles(path.join(FIXTURES, `${stem}.dat`));
  await page.locator("#uploadModalSubmitBtn").click();
  await page.locator("#uploadModalOverlay").waitFor({ state: "hidden" });
}

// Displays one specific channel (by name, not just "the first") on the
// Waveform page -- opens the source and selects it from the Channels
// sidebar, the same flow every Waveform browser test already uses.
async function displayChannel(page, sourceId, channelName) {
  await page.locator(`#wwRdRecordingList .ww-rd-recording-item[data-source-id="${sourceId}"]`).click();
  await page.locator("#mainNavWaveformBtn").click();
  await expect(page.locator("#wwWorkspaceLoading")).toBeHidden();
  const details = page.locator(`#channelGroups details.source-recording[data-source-id="${sourceId}"]`);
  await expect(details).toBeVisible();
  if (!(await details.evaluate((el) => el.open))) await details.locator("> summary").click();
  const row = page.locator(
    `#channelGroups tr.channel-row--toggle[data-channel-kind="analog"][data-source-id="${sourceId}"][data-channel-name="${channelName}"]`
  );
  await expect(row).toBeVisible();
  await row.click();
  await expect(row).toHaveAttribute("aria-pressed", "true");
}

// Two panels in ONE Time Group: a Voltage channel and a Current channel
// from the same uploaded source -- two different quantities, so
// Grouped mode (the default) puts them in two separate panels of the
// same Time Group, each with its own clickable header.
async function setupTwoPanelsOneGroup(page, channels = VI_CHANNELS) {
  const response = await page.goto("/index.html");
  const sourceHash = crypto.createHash('sha256').update((await response.body()).toString('utf8').replace(/^\uFEFF/, '')).digest('hex');
  await uploadRecord(page, { station: "STN_A", startClock: "10:00:00.000000", durationS: 4, channels });
  const row = page.locator("#wwRdRecordingList .ww-rd-recording-item").first();
  const sourceId = await row.getAttribute("data-source-id");
  await displayChannel(page, sourceId, channels[0].name);
  // A second channel on the SAME already-open source: the sidebar's
  // channel list stays visible, so this selects it directly rather than
  // re-navigating through the (now hidden) recordings table.
  const secondRow = page.locator(
    `#channelGroups tr.channel-row--toggle[data-channel-kind="analog"][data-source-id="${sourceId}"][data-channel-name="${channels[1].name}"]`
  );
  await secondRow.click();
  await expect(secondRow).toHaveAttribute("aria-pressed", "true");
  await expect(page.locator(".ww-panel")).toHaveCount(2);
  await page.waitForTimeout(300); // let both charts reach a stable autoranged state
  const groupId = await page.evaluate((sid) => wwTimeGroupIdForDisplaySourceId(sid), sourceId);
  return { sourceId, groupId, sourceHash };
}

// Two separate Time Groups: two fixtures with non-overlapping recording
// start times (see playback.spec.js's own header comment for why this
// pairing reliably forms two groups, unlike the ER-focused uploadRecord()
// helper with a manual date override, which did not).
async function setupTwoTimeGroups(page) {
  await uploadFixture(page, "synth_playback");
  await uploadFixture(page, "synth_playback_b");
  const rows = page.locator("#wwRdRecordingList .ww-rd-recording-item");
  await expect(rows).toHaveCount(2);
  const sourceIdA = await rows.nth(0).getAttribute("data-source-id");
  const sourceIdB = await rows.nth(1).getAttribute("data-source-id");
  for (const sourceId of [sourceIdA, sourceIdB]) {
    await page.locator("#mainNavRecordingDetailsBtn").click();
    await displayChannel(page, sourceId, "V0_R");
  }
  await expect(page.locator(".ww-time-group-canvas")).toHaveCount(2);
  await page.waitForTimeout(300);
  const groupIdA = await page.evaluate((sid) => wwTimeGroupIdForDisplaySourceId(sid), sourceIdA);
  const groupIdB = await page.evaluate((sid) => wwTimeGroupIdForDisplaySourceId(sid), sourceIdB);
  return { sourceIdA, sourceIdB, groupIdA, groupIdB };
}


async function snapshot(page) {
  return page.evaluate(() => ({
    labels: [...document.querySelectorAll('#viewWaveform .ww-panel-label, #viewWaveform .ww-legend-label, #channelGroups [class*=badge], #channelGroups [class*=warning]')].map(el=>el.outerHTML),
    viewports: [...ww.timeGroupViewports], cursors: [...ww.timeGroupCursorState], t0: [...ww.timeGroupT0State],
    panes: ww.panels.map(p => ({id:p.id,x:p.chartEl._fullLayout.xaxis.range.slice(),y:p.chartEl._fullLayout.yaxis.range.slice(),
      y2:p.chartEl._fullLayout.yaxis2?.range.slice(), height:p.height, values:p.channels.map(c=>c.values.slice())}))
  }));
}
for (const mode of ['grouped','separate','custom']) test(`local Y controls isolate scale in ${mode}`, async ({page}, info) => {
  await setupTwoTimeGroups(page);
  await page.evaluate(mode=>wwSetLayoutMode(mode),mode);
  const panels=page.locator('#viewWaveform .ww-panel');
  await expect(panels).toHaveCount(2);
  const targetId=await page.evaluate(()=>ww.panels[1].id);
  const target=page.locator(`#viewWaveform .ww-panel[data-panel-id="${targetId}"]`), buttons=target.locator('[data-pane-y]');
  await expect(buttons).toHaveCount(3); await expect(buttons.first()).toBeEnabled();
  await page.evaluate(async()=>{const g=wwPanelTimeGroupId(ww.panels[1]);wwToggleMeasurementCursors(g);await wwSetT0FromCursorAForGroup(g);});
  await page.waitForFunction(() => ww.panels.every(p => p.chartEl.data?.[0]?.y.length > 0));
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  const before=await snapshot(page);
  expect(before.t0.length).toBeGreaterThan(0);
  expect(before.cursors.some(([,c])=>c.a.visible && c.b.visible && c.a.time !== c.b.time)).toBe(true);
  await page.evaluate(()=>{window.wuiNewPlots=0;const original=Plotly.newPlot;Plotly.newPlot=function(...args){window.wuiNewPlots++;return original.apply(this,args);};});
  let requests=0; page.on('request',r=>{if(/\/waveform(?:\?|$)/.test(r.url()))requests++;});
  await target.locator('[data-pane-y=in]').click();
  await expect.poll(async () => (await snapshot(page)).panes[1].y[1]-(await snapshot(page)).panes[1].y[0]).toBeCloseTo((before.panes[1].y[1]-before.panes[1].y[0])*.8,6);
  const after=await snapshot(page);
  expect(after.panes[1].y[1]-after.panes[1].y[0]).toBeCloseTo((before.panes[1].y[1]-before.panes[1].y[0])*.8,6);
  expect(after.panes[0]).toEqual(before.panes[0]);
  expect(after.viewports).toEqual(before.viewports);expect(after.cursors).toEqual(before.cursors);expect(after.t0).toEqual(before.t0);expect(after.labels).toEqual(before.labels);
  expect(after.panes[1].x).toEqual(before.panes[1].x);expect(after.panes[1].values).toEqual(before.panes[1].values);
  expect(await page.evaluate(()=>ww.activePanelGroupKey===ww.panels[1].groupKey)).toBe(true);
  await target.locator('[data-pane-y=out]').click();
  const restored=await snapshot(page);restored.panes[1].y.forEach((v,i)=>expect(v).toBeCloseTo(before.panes[1].y[i],6));
  await target.locator('[data-pane-y=in]').click();await target.locator('[data-pane-y=auto]').click();
  expect(await target.locator('.ww-chart').evaluate(c=>c.layout.yaxis.autorange)).toBe(true);
  expect(requests).toBe(0);
  expect(await page.evaluate(()=>window.wuiNewPlots)).toBe(0);
  const scaled=await snapshot(page);
  expect(scaled.panes[0]).toEqual(before.panes[0]);
  expect(scaled.viewports).toEqual(before.viewports);expect(scaled.cursors).toEqual(before.cursors);expect(scaled.t0).toEqual(before.t0);
  expect(scaled.labels).toEqual(before.labels);
  expect(await page.evaluate(()=>wwActiveTimeGroupId()===wwPanelTimeGroupId(ww.panels[1]))).toBe(true);
  await expect(page.locator('#wwT0Btn')).toHaveAttribute('aria-pressed','true');
  for(const theme of ['light','dark']) {
    await page.evaluate(t=>PowerwaveTheme.setTheme(t),theme);await page.setViewportSize({width:1280,height:800});
    await expect(buttons.first()).toBeVisible();
    await page.screenshot({path:info.outputPath(`${mode}-${theme}.png`),fullPage:true});
  }
  if(mode==='separate') {await target.locator('.ww-legend-remove').click();await expect(panels).toHaveCount(1);}
});
test('native keyboard activation, annotation capture, readiness and resize',async({page})=>{
  await setupTwoPanelsOneGroup(page);
  const pane=page.locator('#viewWaveform .ww-panel').last(),button=pane.locator('[data-pane-y=in]');
  await pane.locator('.ww-pane-identity').focus();
  await page.keyboard.press('Tab');await expect(pane.locator('[data-pane-y=out]')).toBeFocused();
  await page.keyboard.press('Tab');await expect(button).toBeFocused();
  await page.evaluate(()=>wwEnterAnnotationPlacementMode('text_note'));
  for(const key of ['Enter','Space']) {
    const before=await snapshot(page);await button.focus();await button.press(key);const after=await snapshot(page);
    expect(after.panes[1].y[1]-after.panes[1].y[0]).toBeCloseTo((before.panes[1].y[1]-before.panes[1].y[0])*.8,6);
    expect(await page.evaluate(()=>ww.annotations.size)).toBe(0);
    expect(await page.evaluate(()=>ww.annotationPlacementType)).toBe('text_note');
  }
  for(const type of ['text_note','callout','peak_max','peak_min']) {
    await page.evaluate(t=>wwEnterAnnotationPlacementMode(t),type);
    const before=await snapshot(page);await button.click();const after=await snapshot(page);
    expect(after.panes[1].y[1]-after.panes[1].y[0]).toBeCloseTo((before.panes[1].y[1]-before.panes[1].y[0])*.8,6);
    expect(await page.evaluate(()=>ww.annotations.size)).toBe(0);
    expect(await page.evaluate(()=>ww.annotationPlacementType)).toBe(type);
  }
  await page.keyboard.press('Escape');
  await page.evaluate(()=>{const p=ww.panels[1];p.plotlyReady=false;wwSyncPaneYControls(p);});await expect(button).toBeDisabled();
  await page.evaluate(()=>{const p=ww.panels[1];p.plotlyReady=true;wwSyncPaneYControls(p);});await expect(button).toBeEnabled();
  const handle=pane.locator('.ww-resize-handle');await handle.scrollIntoViewIfNeeded();const box=await handle.boundingBox();const old=(await snapshot(page)).panes[1].height;
  await page.mouse.move(box.x+20,box.y+2);await page.mouse.down();await page.mouse.move(box.x+20,box.y+42);await page.mouse.up();
  expect((await snapshot(page)).panes[1].height).toBeGreaterThan(old);
});
test('secondary axis and reversed primary range keep their contracts',async({page})=>{
 await setupTwoPanelsOneGroup(page);
 await page.evaluate(async()=>{
   const p=ww.panels[1], base=p.channels[0];
   const angle={...base,channelName:'Test angle',engineeringQuantity:'Current Angle',values:base.time.map((t)=>90*Math.sin(t))};
   p.channels.push(angle);wwAddTraceToPanel(p,angle);
   await Plotly.relayout(p.chartEl,{'yaxis2.range':[-180,180],'yaxis2.autorange':false,'yaxis.range':[10,-10]});
 });
 expect(await page.evaluate(()=>wwPanelNeedsSecondaryAxis(ww.panels[1]) && ww.panels[1].chartEl.data[1].yaxis==='y2')).toBe(true);
 const before=await snapshot(page);await page.locator('#viewWaveform .ww-panel').last().locator('[data-pane-y=in]').click();
 const after=await snapshot(page);expect(after.panes[1].y).toEqual([8,-8]);expect(after.panes[1].y2).toEqual(before.panes[1].y2);
 await page.locator('#viewWaveform .ww-panel').last().locator('[data-pane-y=auto]').click();
 expect((await snapshot(page)).panes[1].y2).toEqual(before.panes[1].y2);
});

// Owner UAT: real nonzero traces with the reported Custom pane identities.
// Scroll each pane into view and check painting/hit targets, not just DOM presence.
for (const mode of ['custom', 'grouped', 'separate']) {
  test(`owner UAT: every local Y control is painted and reachable in ${mode}`, async ({ page }, info) => {
    await page.setViewportSize({ width: 1366, height: 768 });
    const { sourceHash } = await setupTwoPanelsOneGroup(page, [
      { name: 'KPDN1 VR', unit: 'V', phase: 'R', amplitude: 11000, frequencyHz: 50 },
      { name: 'KPDN1 IB', unit: 'A', phase: 'B', amplitude: 250, frequencyHz: 50 },
    ]);
    // Chromium decodes away the UTF-8 BOM; compare the same HTML text on both sides.
    expect(sourceHash).toBe(crypto.createHash('sha256').update(fs.readFileSync(path.join(__dirname, '../frontend/index.html'), 'utf8').replace(/^\uFEFF/, '')).digest('hex'));
    const origin = await page.evaluate(() => ({ frontend: location.origin, backend: apiBaseUrl() }));
    await page.locator(`#layoutMode${mode[0].toUpperCase() + mode.slice(1)}Btn`).click();
    const panes = page.locator('#viewWaveform .ww-panel');
    await expect(panes).toHaveCount(2);
    if (mode === 'custom') {
      await expect(panes.nth(0).locator('.ww-panel-label')).toHaveText('KPDN1 VR');
      await expect(panes.nth(1).locator('.ww-panel-label')).toHaveText('KPDN1 IB');
    }
    const inspect = (button) => button.evaluate(el => {
      const rect = el.getBoundingClientRect();
      const style = getComputedStyle(el);
      const icon = el.querySelector('.ww-icon');
      const iconStyle = getComputedStyle(icon);
      const hit = document.elementFromPoint(rect.x + rect.width / 2, rect.y + rect.height / 2);
      return {
        action: el.dataset.paneY, title: el.title, disabled: el.disabled,
        display: style.display, visibility: style.visibility, opacity: style.opacity,
        rect: { x: rect.x, y: rect.y, width: rect.width, height: rect.height },
        paintedIcon: icon.getBoundingClientRect().width > 0 && icon.getBoundingClientRect().height > 0
          && iconStyle.display !== 'none' && iconStyle.visibility === 'visible'
          && (iconStyle.maskImage || iconStyle.webkitMaskImage) !== 'none',
        hit: hit === el || el.contains(hit),
        hitElement: hit?.outerHTML.slice(0, 500),
      };
    });
    await page.screenshot({ path: info.outputPath(`owner-${mode}-initial.png`), fullPage: true });
    const evidence = [];
    for (const theme of ['light', 'dark']) {
      await page.evaluate(t => PowerwaveTheme.setTheme(t), theme);
      for (let paneIndex = 0; paneIndex < 2; paneIndex++) {
        const pane = panes.nth(paneIndex);
        // A tall pane can intersect the viewport while its title is under the sticky group bar.
        await pane.locator('.ww-panel-header').evaluate(el => el.scrollIntoView({ block: 'center' }));
        await expect(pane.locator('[data-pane-y]')).toHaveCount(3);
        for (const action of ['in', 'out', 'auto']) {
          const button = pane.locator(`[data-pane-y="${action}"]`);
          await expect(button).toBeVisible();
          await expect(button).toBeInViewport({ ratio: 1 });
          await expect(button).toBeEnabled();
          const result = await inspect(button);
          expect(result.visibility).toBe('visible');
          expect(Number(result.opacity)).toBeGreaterThan(0.5);
          expect(result.rect.width).toBeGreaterThanOrEqual(24);
          expect(result.rect.height).toBeGreaterThanOrEqual(24);
          expect(result.paintedIcon).toBe(true);
          expect(result.hit, JSON.stringify({ mode, theme, paneIndex, ...result })).toBe(true);
          evidence.push({ mode, theme, paneIndex, ...result });
          await button.click({ trial: true });
        }
      }
      await page.locator('#activeViewArea').evaluate(el => { el.scrollTop = 0; });
      await page.screenshot({ path: info.outputPath(`owner-${mode}-${theme}.png`), fullPage: true });
    }
    // Tab/focus must also expose a control when its header sits beneath the sticky group bar.
    const focusState = await page.evaluate(() => {
      const pane = ww.panels[0];
      const header = pane.headerEl;
      const scroll = document.getElementById('activeViewArea');
      const sticky = pane.containerEl.closest('.ww-time-group-canvas').querySelector('.ww-tg-sticky-top');
      scroll.scrollTop = 0;
      scroll.scrollTop += header.getBoundingClientRect().top - sticky.getBoundingClientRect().top;
      return { scrollTop: scroll.scrollTop };
    });
    const beforeFocus = await snapshot(page);
    const focused = panes.first().locator('[data-pane-y=in]');
    await focused.focus();
    expect(await snapshot(page)).toEqual(beforeFocus);
    const focusResult = await inspect(focused);
    expect(focusResult.hit, JSON.stringify({ mode, focusState, ...focusResult })).toBe(true);
    await focused.click({ trial: true });
    await info.attach('rendered-controls.json', { body: JSON.stringify({ sourceHash, origin, controls: evidence, focusResult }, null, 2), contentType: 'application/json' });
  });
}
