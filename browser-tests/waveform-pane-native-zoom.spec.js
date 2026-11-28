const base=require('./support/test');
const {chromium}=require('playwright');
const fs=require('fs'),path=require('path');
const {setupPaneScenario,paneLayout,voltagePane,assertLegend}=require('./support/waveform_pane_helpers');
const {expectTrueSubscripts}=require('./support/electrical_notation_helpers');
const {expect}=base;
const test=base.test.extend({context:async({},use,info)=>{
  const extension=info.outputPath('zoom-extension');fs.mkdirSync(extension,{recursive:true});
  fs.writeFileSync(path.join(extension,'manifest.json'),JSON.stringify({manifest_version:3,name:'WUI-003 native zoom check',version:'1.0',permissions:['tabs'],background:{service_worker:'background.js'}}));
  fs.writeFileSync(path.join(extension,'background.js'),'chrome.runtime.onInstalled.addListener(()=>{});');
  const context=await chromium.launchPersistentContext(info.outputPath('private-profile'),{channel:'chromium',headless:true,
    baseURL:`http://127.0.0.1:${process.env.PW_FRONTEND_PORT||'8101'}`,viewport:{width:1280,height:800},
    ignoreDefaultArgs:['--disable-extensions'],args:[`--disable-extensions-except=${extension}`,`--load-extension=${extension}`]});
  try{await use(context)}finally{await context.close()}
}});
test.setTimeout(120000);
async function shot(context,page,info,name,locator,zoom){
  const cdp=await context.newCDPSession(page),box=locator?await locator.boundingBox():null;
  const result=await cdp.send('Page.captureScreenshot',{format:'png',...(box?{clip:{x:box.x*zoom,y:box.y*zoom,width:box.width*zoom,height:box.height*zoom,scale:1}}:{})});
  fs.writeFileSync(info.outputPath(name+'.png'),Buffer.from(result.data,'base64'));await cdp.detach();
}
for(const layout of ['Grouped','Separate','Custom'])for(const theme of ['light','dark'])for(const zoom of [1,1.25])
test(`${layout} ${theme} ${zoom*100}% native zoom`,async({page,context},info)=>{
  const viewport=layout==='Separate'?{width:1280,height:800}:{width:1366,height:768};await page.setViewportSize(viewport);
  const scenario=await setupPaneScenario(page,{sources:2,voltages:8,currents:true});
  if(layout==='Custom'){
    const endpoint=`${scenario.backend}/api/v1/workspaces/${scenario.workspace}/calculated-channels/line-to-line-voltage`;
    const readiness=await(await page.request.get(endpoint+'/readiness')).json();const ready=readiness.find(r=>r.outputs.AB.available);
    expect(ready).toBeTruthy();const response=await page.request.post(endpoint,{data:{engineering_context_id:ready.engineering_context_id,output:'all_three'}});
    expect(response.ok()).toBe(true);const {channels}=await response.json();await page.evaluate(()=>wwFetchCalculatedChannels());
    for(const calc of channels)await page.locator(`#calculatedChannelsSidebarBody tr.channel-row--toggle[data-source-id="${calc.id}"]`).click();
  }
  await paneLayout(page,layout,{long:layout==='Custom'});
  await page.evaluate(theme=>PowerwaveTheme.setTheme(theme),theme);
  const worker=context.serviceWorkers()[0]||await context.waitForEvent('serviceworker');
  expect(await worker.evaluate(async({url,zoom})=>{const tab=(await chrome.tabs.query({})).find(t=>t.url===url);await chrome.tabs.setZoom(tab.id,zoom);return chrome.tabs.getZoom(tab.id)},{url:page.url(),zoom})).toBe(zoom);
  await expect.poll(()=>page.evaluate(()=>devicePixelRatio)).toBe(zoom);
  await page.waitForFunction(()=>ww.panels.every(p=>Math.abs(p.chartEl._fullLayout.width-p.chartEl.getBoundingClientRect().width)<2));
  const pane=await voltagePane(page),font=await page.evaluate(()=>parseFloat(getComputedStyle(document.documentElement).fontSize));
  const control=pane.locator('.ww-legend-toggle').first();await control.focus();
  await expect(control.locator('.ww-legend-label')).toHaveCSS('font-size',(font*.65)+'px');
  const target=await control.boundingBox();expect(target.height).toBeGreaterThanOrEqual(24);expect(target.width).toBeGreaterThanOrEqual(24);
  await expect(page.locator('.ww-pane-legend-tip')).toBeVisible();
  const identity=pane.locator('.ww-pane-identity');expect(parseFloat(await pane.locator('.ww-panel-label').evaluate(el=>getComputedStyle(el).fontSize))).toBeGreaterThan(font*.65);
  for(const button of await pane.locator('[data-pane-y], [data-pane-unit-mode]').all()){
    await button.focus();await expect(button).toBeVisible();await button.click({trial:true});
  }
  await assertLegend(page,pane);
  const header=pane.locator('.ww-panel-header');await identity.focus();
  await shot(context,page,info,`${layout}-${theme}-${zoom*100}-header`,header,zoom);
  if(layout!=='Separate'){
    const key=await control.getAttribute('data-channel-key');await control.click();
    await expect(control).toHaveAttribute('aria-pressed','false');
    const colors=await pane.locator('.ww-legend-toggle').evaluateAll(nodes=>nodes.slice(0,2).map(node=>getComputedStyle(node).color));
    expect(colors[0]).not.toBe(colors[1]);
    await control.focus();await page.mouse.move(1,1);
    await shot(context,page,info,`${layout}-${theme}-${zoom*100}-legend`,pane.locator('.ww-legend'),zoom);
    const more=pane.locator('.ww-pane-legend-more');await expect(more).toHaveCSS('font-size',(font*.65)+'px');
    await more.click();const popup=page.locator('.ww-pane-legend-popover');await expect(popup).toBeVisible();
    const row=popup.locator('[data-legend-toggle]').first();await expect(row).toHaveCSS('font-size',(font*.7)+'px');
    await expect(row).toHaveAttribute('aria-pressed','false');
    const bounds=await popup.boundingBox(),screen=await page.evaluate(()=>({width:innerWidth,height:innerHeight}));
    expect(bounds.x).toBeGreaterThanOrEqual(0);expect(bounds.x+bounds.width).toBeLessThanOrEqual(screen.width+1);expect(bounds.y+bounds.height).toBeLessThanOrEqual(screen.height+1);
    await shot(context,page,info,`${layout}-${theme}-${zoom*100}-popover`,popup,zoom);await page.keyboard.press('Escape');
    if(layout==='Custom'){
      await more.click();const rich=page.locator('.ww-pane-legend-popover');
      await expectTrueSubscripts(rich.locator('.ww-electrical-symbol'));
      await rich.locator('.ww-electrical-symbol').first().scrollIntoViewIfNeeded();
      await shot(context,page,info,`${layout}-${theme}-${zoom*100}-calculated`,rich,zoom);await page.keyboard.press('Escape');
    }
    expect(await page.evaluate(key=>ww.displayed.has(key),key)).toBe(false);
  }else await shot(context,page,info,`${layout}-${theme}-${zoom*100}-legend`,pane.locator('.ww-legend'),zoom);
  await shot(context,page,info,`${layout}-${theme}-${zoom*100}-workspace`,null,zoom);
  await info.attach('native-evidence.json',{body:JSON.stringify({layout,theme,zoom,viewport,rootFont:font,legendFont:font*.65,popoverFont:font*.7,target}),contentType:'application/json'});
});
