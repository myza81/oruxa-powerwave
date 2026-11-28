// UI relocation only: all pane controls project the existing workspace display state.
const { test, expect } = require('./support/test');
const { uploadRecord, workspaceId, BACKEND } = require('./support/event_reconstruction_helpers');
test.setTimeout(60000);

async function setup(page) {
  await page.goto('/index.html');
  const sources = [];
  for (const [station, clock] of [['VOLTAGE_A','10:00:00.000000'], ['VOLTAGE_B','10:10:00.000000']]) {
    await uploadRecord(page, { station, startClock: clock, durationS: 0.2, channels: [
      { name: 'VA', unit: 'V', phase: 'A', amplitude: 11000, frequencyHz: 50 },
      { name: 'VB', unit: 'V', phase: 'B', amplitude: 11000, frequencyHz: 50 },
      { name: 'IA', unit: 'A', phase: 'A', amplitude: 250, frequencyHz: 50 },
    ] });
    const row = page.locator('#wwRdRecordingList .ww-rd-recording-item').filter({ hasText: station });
    const source = await row.getAttribute('data-source-id'); sources.push(source);
    await row.click(); await page.locator('#mainNavWaveformBtn').click();
    const details = page.locator(`#channelGroups details.source-recording[data-source-id="${source}"]`);
    if (!(await details.evaluate(el=>el.open))) await details.locator(':scope > summary').click();
    for (const name of ['VA','VB','IA']) await page.locator(`#channelGroups tr.channel-row--toggle[data-source-id="${source}"][data-channel-name="${name}"]`).click();
    await page.locator('#mainNavRecordingDetailsBtn').click();
  }
  await page.locator('#mainNavWaveformBtn').click();
  await page.evaluate(() => {
    window.voltageDisplayJobs=[]; const apply=wwApplyUnitMode;
    wwApplyUnitMode=mode=>{ const job=apply(mode); window.voltageDisplayJobs.push(job); return job; };
  });
  await ready(page);
  return sources;
}
async function ready(page) {
  await page.evaluate(async()=>Promise.all(window.voltageDisplayJobs || []));
  await page.waitForFunction(() => ww.panels.length > 0 && ww.panels.every(p => p.plotlyReady && p.chartEl._fullLayout));
}
async function controls(page, mode) {
  await expect(page.locator('#wwToolbar [data-toolbar-group="voltage"], #wwToolbar #wwUnitModeToggle')).toHaveCount(0);
  await expect(page.locator('#wwUnitModeToggle')).toHaveCount(1);
  const state = await page.evaluate(() => ww.panels.map(p => ({ id: p.id,
    applicable: p.channels.some(c => { const type=wwIsCalculatedSourceId(c.sourceId) ? wwCalculatedEngineeringTypeFor(c.sourceId) : c.engineeringType;
      return (type==='Voltage' || (wwIsCalculatedSourceId(c.sourceId) && type==='Current')) && !wwChannelUsesAngleQuantity(c); }) })));
  const local = page.locator('#viewWaveform .ww-pane-unit-mode:visible');
  await expect(local).toHaveCount(state.filter(p=>p.applicable).length);
  expect(state.filter(p=>p.applicable).length).toBeGreaterThanOrEqual(2);
  for (const p of state) {
    const pane = page.locator(`[data-panel-id="${p.id}"]`);
    if (!p.applicable) { await expect(pane.locator('.ww-pane-unit-mode')).toBeHidden(); continue; }
    const group = pane.locator('.ww-pane-unit-mode');
    await group.scrollIntoViewIfNeeded();
    for (const value of ['engineering','per_unit']) {
      const button = group.locator(`[data-pane-unit-mode="${value}"]`);
      await expect(button).toBeVisible(); await expect(button).toHaveAttribute('aria-pressed',String(value===mode));
      await button.focus();
      await button.click({ trial: true });
    }
    const box = await pane.locator('.ww-panel-header').boundingBox();
    const a = await group.boundingBox(), b = await pane.locator('.ww-pane-y-tools').boundingBox();
    expect(a.x+a.width).toBeLessThanOrEqual(b.x+0.5);
    expect(b.x+b.width).toBeLessThanOrEqual(box.x+box.width+0.5);
  }
}
for (const layout of ['grouped','separate','custom']) test(`all Voltage panes share one state in ${layout}`, async ({page}) => {
  await setup(page);
  await page.locator('#layoutMode'+layout[0].toUpperCase()+layout.slice(1)+'Btn').click(); await ready(page);
  await controls(page,'engineering');
  const before = await page.evaluate(()=>({ keys:[...ww.displayed.keys()].sort(), ranges:[...ww.timeGroupViewports],
    currents:[...ww.displayed.values()].filter(e=>e.channel.engineeringType==='Current').map(e=>e.channel.values.slice()) }));
  await page.locator('.ww-pane-unit-mode:visible [data-pane-unit-mode="per_unit"]').last().click();
  await ready(page); await controls(page,'per_unit');
  await expect(page.locator('#wwPuConfigBanner')).toBeVisible();
  for (const glyph of await page.locator('.ww-pane-unit-mode:visible [data-pane-unit-warning]').all()) await expect(glyph).toBeVisible();
  const after = await page.evaluate(()=>({ keys:[...ww.displayed.keys()].sort(), ranges:[...ww.timeGroupViewports],
    currents:[...ww.displayed.values()].filter(e=>e.channel.engineeringType==='Current').map(e=>e.channel.values.slice()) }));
  expect(after).toEqual(before);
  const eng=page.locator('.ww-pane-unit-mode:visible [data-pane-unit-mode="engineering"]').first();
  await eng.focus(); await page.keyboard.press('Space'); await ready(page); await controls(page,'engineering');
  await expect(page.locator('#wwPuConfigBanner')).toBeHidden();
  await page.locator('.ww-pane-unit-mode:visible [data-pane-unit-mode="per_unit"]').first().click(); await ready(page);
  await page.locator('#wwPuConfigBannerBtn').click(); await expect(page.locator('#pageRecordingDetails')).toBeVisible();
});

test('mixed custom panes use channel metadata, long titles and annotation exclusions', async ({page},info)=>{
  await page.setViewportSize({width:1280,height:800}); const sources=await setup(page);
  await page.evaluate(sources=>{
    ww.customGroups=[{id:'mixed',label:'Current only title cannot determine voltage membership '+ 'long title '.repeat(18),
      channelKeys:sources.flatMap(source=>['VA','IA'].map(name=>wwChannelKey(source,name)))}];
    wwSetLayoutMode('custom');
  },sources); await ready(page);
  await controls(page,'engineering');
  const truncated = await page.locator('#viewWaveform .ww-panel-label').evaluateAll(nodes=>nodes.filter(n=>n.textContent.includes('Current only title')).map(n=>n.scrollWidth>n.clientWidth));
  expect(truncated).toEqual([true,true]);
  await expect(page.locator('.ww-pane-unit-mode:visible .ww-pane-unit-scope:visible')).toHaveCount(2);
  await page.locator('#wwAnnotateBtn').click(); await page.locator('#wwAnnotateMenu [data-annotation-type="text_note"]').click();
  await page.locator('.ww-pane-unit-mode:visible [data-pane-unit-mode="per_unit"]').last().click(); await ready(page);
  expect(await page.evaluate(()=>ww.annotations.size)).toBe(0);
  await expect(page.locator('.ww-annotation-textarea')).toHaveCount(0);
  await page.keyboard.press('Escape');
  await page.locator('#layoutModeSeparateBtn').click(); await ready(page); await controls(page,'per_unit');
  await page.locator('#layoutModeGroupedBtn').click(); await ready(page); await controls(page,'per_unit');
  await page.screenshot({path:info.outputPath('synchronized-voltage-panes.png'),fullPage:true});
});


test('calculated Voltage and Current retain display access; angle-only and raw Current stay excluded',async({page})=>{
  const sources=await setup(page);
  const workspace=await workspaceId(page);
  const response=await page.request.post(`${BACKEND}/api/v1/workspaces/${workspace}/calculated-channels`,{data:{
    name:'Current-looking custom title',operation:'reverse_polarity',parameters:{},
    inputs:[{kind:'source',source_id:sources[0],channel_name:'VA'}]
  }});
  expect(response.ok()).toBe(true); const calc=await response.json(); expect(calc.engineering_type).toBe('Voltage');
  await page.evaluate(()=>wwFetchCalculatedChannels());
  const calcRow=page.locator(`#calculatedChannelsSidebarBody tr.channel-row--toggle[data-source-id="${calc.id}"]`);
  await calcRow.click(); await ready(page);
  const calcPane=await page.evaluate(id=>ww.displayed.get(wwChannelKey(id,ww.calculatedChannels.get(id).name)).panel.id,calc.id);
  await expect(page.locator(`[data-panel-id="${calcPane}"] .ww-pane-unit-mode`)).toBeVisible();
  // UI fixture: inject the already-supported angle metadata, without changing samples or converters.
  await page.evaluate(source=>{
    for(const e of ww.displayed.values())if(e.channel.sourceId===source && e.channel.engineeringType==='Voltage')e.channel.engineeringQuantity='Voltage Angle';
    wwRebuildLayout();wwSyncUnitModeControls();
  },sources[1]); await ready(page);
  const hidden=await page.evaluate(source=>ww.panels.filter(p=>p.channels.some(c=>c.sourceId===source) && p.channels.every(c=>c.engineeringType==='Current'||wwChannelUsesAngleQuantity(c))).map(p=>p.id),sources[1]);
  expect(hidden.length).toBeGreaterThan(0);
  for(const id of hidden)await expect(page.locator(`[data-panel-id="${id}"] .ww-pane-unit-mode`)).toBeHidden();
  const currentResponse=await page.request.post(`${BACKEND}/api/v1/workspaces/${workspace}/calculated-channels`,{data:{
    name:'Voltage-looking Current result',operation:'reverse_polarity',parameters:{},
    inputs:[{kind:'source',source_id:sources[0],channel_name:'IA'}]
  }});
  expect(currentResponse.ok()).toBe(true);const currentCalc=await currentResponse.json();expect(currentCalc.engineering_type).toBe('Current');
  await page.evaluate(()=>wwFetchCalculatedChannels());
  await page.locator(`#calculatedChannelsSidebarBody tr.channel-row--toggle[data-source-id="${currentCalc.id}"]`).click();await ready(page);
  const currentPane=await page.evaluate(id=>ww.displayed.get(wwChannelKey(id,ww.calculatedChannels.get(id).name)).panel.id,currentCalc.id);
  await expect(page.locator(`[data-panel-id="${currentPane}"] .ww-pane-unit-mode`)).toBeVisible();
  await expect(page.locator(`[data-panel-id="${currentPane}"] .ww-pane-unit-scope`)).toHaveText('Calculated Current');
  await expect(page.locator(`[data-panel-id="${currentPane}"] .ww-pane-unit-mode`)).toHaveAttribute('title',
    'Calculated Current Display - shared across all waveform panes');
  await controls(page,'engineering');
});


test('keyboard focus follows a rebuilt selector and synchronization alone causes no requests',async({page})=>{
  await setup(page);
  const requests=[];page.on('request',request=>requests.push(request.url()));
  await page.evaluate(()=>{for(let i=0;i<3;i++)wwSyncUnitModeControls();});
  await page.evaluate(()=>new Promise(requestAnimationFrame));
  expect(requests).toEqual([]);
  const pu=page.locator('.ww-pane-unit-mode:visible [data-pane-unit-mode="per_unit"]').last();
  await pu.focus();await pu.press('Enter');await ready(page);
  await expect(page.locator(':focus')).toHaveAttribute('data-pane-unit-mode','per_unit');
  const eng=page.locator('.ww-pane-unit-mode:visible [data-pane-unit-mode="engineering"]').first();
  await eng.focus();await eng.press('Space');await ready(page);
  await expect(page.locator(':focus')).toHaveAttribute('data-pane-unit-mode','engineering');
  expect(await page.evaluate(()=>voltageDisplayJobs.length)).toBe(2);
});
