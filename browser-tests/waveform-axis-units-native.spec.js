const base=require('./support/test');
const {chromium}=require('playwright');
const fs=require('fs'),path=require('path');
const {setupUnits,readyUnits,customUnits,axisCaps,assertCapGeometry}=require('./support/waveform_axis_unit_helpers');
const {expect}=base;
const test=base.test.extend({context:async({},use,info)=>{
  const extension=info.outputPath('zoom-extension');fs.mkdirSync(extension,{recursive:true});
  fs.writeFileSync(path.join(extension,'manifest.json'),JSON.stringify({manifest_version:3,name:'WUI-004 native zoom check',version:'1.0',permissions:['tabs'],background:{service_worker:'background.js'}}));
  fs.writeFileSync(path.join(extension,'background.js'),'chrome.runtime.onInstalled.addListener(()=>{});');
  const context=await chromium.launchPersistentContext(info.outputPath('private-profile'),{channel:'chromium',headless:true,
    baseURL:`http://127.0.0.1:${process.env.PW_FRONTEND_PORT||'8101'}`,viewport:{width:1366,height:768},
    ignoreDefaultArgs:['--disable-extensions'],args:[`--disable-extensions-except=${extension}`,`--load-extension=${extension}`]});
  try{await use(context)}finally{await context.close()}
}});
test.setTimeout(90000);
for(const layout of ['Grouped','Separate','Custom'])for(const theme of ['light','dark'])for(const zoom of [1,1.25])
test(`${layout} ${theme} ${zoom*100}% native zoom axis units`,async({page,context},info)=>{
  await setupUnits(page,['kV','A','Hz']);
  if(layout==='Custom')await customUnits(page);else await page.locator('#layoutMode'+layout+'Btn').click();await readyUnits(page);
  await page.evaluate(theme=>PowerwaveTheme.setTheme(theme),theme);
  const worker=context.serviceWorkers()[0]||await context.waitForEvent('serviceworker');
  expect(await worker.evaluate(async({url,zoom})=>{const tab=(await chrome.tabs.query({})).find(t=>t.url===url);await chrome.tabs.setZoom(tab.id,zoom);return chrome.tabs.getZoom(tab.id)},{url:page.url(),zoom})).toBe(zoom);
  await expect.poll(()=>page.evaluate(()=>devicePixelRatio)).toBe(zoom);
  await page.waitForFunction(()=>ww.panels.every(p=>Math.abs(p.chartEl._fullLayout.width-p.chartEl.getBoundingClientRect().width)<2));
  const bounds=await assertCapGeometry(page);
  for(const cap of await page.locator('[data-waveform-axis-unit]').all())await expect(cap).toBeVisible();
  const cdp=await context.newCDPSession(page),image=await cdp.send('Page.captureScreenshot',{format:'png'});
  fs.writeFileSync(info.outputPath(`${layout}-${theme}-${zoom*100}.png`),Buffer.from(image.data,'base64'));await cdp.detach();
  await info.attach('axis-caps.json',{body:JSON.stringify({layout,theme,zoom,panes:await axisCaps(page),bounds}),contentType:'application/json'});
});
