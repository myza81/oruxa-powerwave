const base = require('./support/test');
const {chromium} = require('playwright');
const fs = require('fs');
const path = require('path');
const {setupToolbarGroups, readyToolbarCharts, activateToolbarGroup, placeToolbarCursors} = require('./support/waveform_toolbar_refinement_helpers');
const {expect} = base;
const before = process.env.HEADER_PHASE === 'before';

// Real per-tab browser zoom, with a private profile; CSS zoom is not a substitute.
const test = base.test.extend({context: async ({}, use, info) => {
  const extension = info.outputPath('zoom-extension');
  fs.mkdirSync(extension, {recursive: true});
  fs.writeFileSync(path.join(extension, 'manifest.json'), JSON.stringify({manifest_version: 3,
    name: 'Local Time Group header verification', version: '1.0', permissions: ['tabs'],
    background: {service_worker: 'background.js'}}));
  fs.writeFileSync(path.join(extension, 'background.js'), 'chrome.runtime.onInstalled.addListener(() => {});');
  const context = await chromium.launchPersistentContext(info.outputPath('private-profile'), {
    channel: 'chromium', headless: true, baseURL: `http://127.0.0.1:${process.env.PW_FRONTEND_PORT || '8101'}`,
    viewport: {width: 1280, height: 800}, ignoreDefaultArgs: ['--disable-extensions'],
    args: [`--disable-extensions-except=${extension}`, `--load-extension=${extension}`],
  });
  try {await use(context);} finally {await context.close();}
}});
test.setTimeout(120000);

async function capture(context, page, info, name, locator, zoom) {
  const cdp = await context.newCDPSession(page);
  const box = locator ? await locator.boundingBox() : null;
  const shot = await cdp.send('Page.captureScreenshot', {format: 'png', ...(box ? {clip: {
    x: box.x * zoom, y: box.y * zoom, width: box.width * zoom, height: box.height * zoom, scale: 1}} : {})});
  fs.writeFileSync(info.outputPath(name + '.png'), Buffer.from(shot.data, 'base64'));
  await cdp.detach();
}

async function groupEvidence(page) {
  return page.evaluate(() => [...document.querySelectorAll('#wwTimeGroupCanvases > .ww-time-group-canvas')].map(canvas => {
    const id = canvas.dataset.timeGroupId, cursors = wwTimeGroupCursorState(id);
    const rect = el => {const r=el.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height,right:r.right,bottom:r.bottom}};
    const header=canvas.querySelector('.ww-tg-header'), title=header.querySelector('.ww-tg-header-title'), meta=header.querySelector('.ww-tg-header-meta');
    const readout=canvas.querySelector('.ww-tg-cursor-readout');
    const expected=wwTimeGroupHeaderText(id);
    return {title:title.textContent, meta:meta.textContent, expected,
      header:rect(header), titleBox:rect(title), metaBox:rect(meta), readoutBox:rect(readout),
      inHeader:readout.parentElement===header, hidden:readout.hidden,
      values:[...readout.querySelectorAll('.ww-tg-cursor-readout-value')].map(el=>el.textContent),
      colors:[...readout.querySelectorAll('.ww-tg-cursor-readout-value')].map(el=>getComputedStyle(el).color),
      expectedValues:[wwFormatCursorPointTime(cursors.a.time,id),wwFormatCursorPointTime(cursors.b.time,id),wwFormatCursorDuration(cursors.b.time-cursors.a.time)],
      cursorTimes:[cursors.a.time,cursors.b.time], t0:wwT0ForGroup(id), range:wwTimeGroupVisibleRange(id),
      plots:ww.panels.filter(p=>wwPanelTimeGroupId(p)===id).map(p=>({width:p.chartEl._fullLayout.width,height:p.chartEl._fullLayout.height,
        x:p.chartEl._fullLayout.xaxis.range,y:p.chartEl._fullLayout.yaxis.range})),
      projection:['a','b'].map(kind=>({expected:wwCursorTimeToPixelX(id,cursors[kind].time),
        actual:canvas.querySelector(`[data-cursor-line="${kind}"]`)?.getBoundingClientRect().x})),
      sticky:getComputedStyle(canvas.querySelector('.ww-tg-sticky-top')).position,
      rulerSticky:getComputedStyle(canvas.querySelector('.ww-tg-ruler')).position,
      dormantFitHidden:canvas.querySelector('.ww-tg-fit-record-btn').hidden};
  }));
}

for (const viewport of [{width:1280,height:800},{width:1366,height:768}])
for (const theme of ['light','dark']) for (const zoom of [1,1.25]) {
  const sources=zoom===1.25?3:theme==='light'?1:2, multipleGroups=sources===3;
  test(`${before?'before':'after'} metadata ${viewport.width} ${theme} ${zoom*100}% ${sources} sources`, async ({page,context},info) => {
    await page.setViewportSize(viewport);
    const groups=await setupToolbarGroups(page,{sources,multipleGroups});
    expect(groups).toHaveLength(multipleGroups?2:1);
    await page.evaluate(theme=>PowerwaveTheme.setTheme(theme),theme);
    const worker=context.serviceWorkers()[0] || await context.waitForEvent('serviceworker');
    expect(await worker.evaluate(async ({url,zoom})=>{
      const tab=(await chrome.tabs.query({})).find(t=>t.url===url);await chrome.tabs.setZoom(tab.id,zoom);return chrome.tabs.getZoom(tab.id);
    },{url:page.url(),zoom})).toBe(zoom);
    await expect.poll(()=>page.evaluate(()=>devicePixelRatio)).toBe(zoom);
    await readyToolbarCharts(page);
    const evidence=[];
    const initial=await groupEvidence(page);
    expect(initial.every(group=>group.hidden)).toBe(true);
    for(const id of groups) {
      await activateToolbarGroup(page,id);await page.locator('#wwCursorModeBtn').click();await placeToolbarCursors(page,id);
    }
    for(const mode of ['absolute','elapsed']) {
      await page.locator(mode==='absolute'?'#timeModeAbsoluteBtn':'#timeModeElapsedBtn').click();
      await readyToolbarCharts(page);
      for(let i=0;i<groups.length;i++) {
        const canvas=page.locator(`.ww-time-group-canvas[data-time-group-id="${groups[i]}"]`);
        await canvas.locator('.ww-tg-header-title').scrollIntoViewIfNeeded();
        await page.evaluate(()=>wwUpdateAllCursorOverlays());
        const state=(await groupEvidence(page))[i];evidence.push({mode,...state});
        expect(state.meta).toBe(state.expected.meta);expect(state.meta).toBe(initial[i].meta);
        expect(state.meta).toContain(' UTC · ');expect(state.meta).toMatch(/\d+ sources?$/);
        expect(state.values).toEqual(state.expectedValues);expect(state.hidden).toBe(false);
        expect(state.sticky).toBe('sticky');expect(state.rulerSticky).toBe('sticky');expect(state.dormantFitHidden).toBe(true);
        expect(state.plots.map(p=>[p.width,p.height])).toEqual(initial[i].plots.map(p=>[p.width,p.height]));
        expect(state.cursorTimes).toEqual(evidence[i]?.cursorTimes || state.cursorTimes);expect(state.t0).toBe(null);
        for(const point of state.projection)expect(Math.abs(point.actual-point.expected)).toBeLessThan(2);
        if(!before) {
          expect(state.inHeader).toBe(true);
          expect(state.metaBox.y).toBeGreaterThanOrEqual(state.titleBox.bottom);
          expect(Math.abs(state.metaBox.x-state.titleBox.x)).toBeLessThan(1);
          expect(state.metaBox.right).toBeLessThanOrEqual(state.header.right+1);
          expect(state.readoutBox.right).toBeLessThanOrEqual(state.header.right+1);
          const below=state.readoutBox.y>=state.metaBox.bottom-1;
          expect(below || state.readoutBox.x>=state.metaBox.right+8).toBe(true);
          expect(state.header.height).toBeLessThan(95);
        }
        if(mode==='absolute') await capture(context,page,info,`group-${i+1}-${theme}-${zoom*100}`,canvas.locator('.ww-tg-sticky-top'),zoom);
      }
      if(mode==='absolute')await capture(context,page,info,`workspace-${theme}-${zoom*100}`,null,zoom);
    }
    await page.evaluate(()=>{ww.customGroups=['Voltage','Current'].map(type=>({id:type,label:type,
      channelKeys:[...ww.displayed].filter(([,entry])=>entry.channel.engineeringType===type).map(([key])=>key)}));});
    // Layout rebuilds preserve each canvas's metadata, cursor readout and navigation.
    for(const layout of ['Separate','Custom','Grouped']) {
      await page.locator('#layoutMode'+layout+'Btn').click();await readyToolbarCharts(page);
      expect((await groupEvidence(page)).map(g=>({meta:g.meta,values:g.values,cursorTimes:g.cursorTimes})))
        .toEqual(evidence.slice(groups.length).map(g=>({meta:g.meta,values:g.values,cursorTimes:g.cursorTimes})));
    }
    // Disable each group's cursor mode independently; its metadata remains visible.
    for(const id of groups) {await activateToolbarGroup(page,id);await page.locator('#wwCursorModeBtn').click();}
    expect((await groupEvidence(page)).map(g=>g.hidden)).toEqual(groups.map(()=>true));
    for(const meta of await page.locator('#wwTimeGroupCanvases .ww-tg-header-meta').all())await expect(meta).toBeVisible();
    await info.attach('header-evidence.json',{body:JSON.stringify({viewport,theme,zoom,sources,initial,evidence}),contentType:'application/json'});
  });
}
