// Pane-header relocation must keep controls usable beside the existing overlay drawer.
const { test, expect } = require('./support/test');
const { uploadRecord } = require('./support/event_reconstruction_helpers');

for (const layout of ['Grouped','Separate','Custom']) test(`pane controls remain reachable beside Annotations in ${layout}`, async ({page},info) => {
  test.setTimeout(60000);
  await page.goto('/index.html');
  await uploadRecord(page, { station:'DRAWER_CLEARANCE', startClock:'10:00:00.000000', durationS:0.2,
    channels:[{name:'VA',unit:'V',phase:'A',amplitude:11000,frequencyHz:50},
      {name:'VB',unit:'V',phase:'B',amplitude:11000,frequencyHz:50}] });
  const source=await page.locator('#wwRdRecordingList .ww-rd-recording-item').first().getAttribute('data-source-id');
  await page.locator('#mainNavWaveformBtn').click();
  for(const name of ['VA','VB']) await page.locator(`#channelGroups tr.channel-row--toggle[data-source-id="${source}"][data-channel-name="${name}"]`).click();
  if(layout==='Custom') await page.evaluate(source=>{
    ww.customGroups=['VA','VB'].map(name=>({id:name,label:name,channelKeys:[wwChannelKey(source,name)]}));
  },source);
  await page.locator('#layoutMode'+layout+'Btn').click();
  const ready=()=>page.waitForFunction(()=>ww.panels.length && ww.panels.every(p=>p.plotlyReady && p.chartEl._fullLayout));
  await ready();
  const widths=()=>page.locator('#viewWaveform .ww-chart').evaluateAll(nodes=>nodes.map(node=>node.getBoundingClientRect().width));
  for(const size of [{width:1280,height:800},{width:1024,height:640}]) {
    await page.setViewportSize(size);
    await page.evaluate(()=>new Promise(requestAnimationFrame));
    const before=await widths();
    await page.evaluate(()=>wwSetAnnotationDrawerOpen(true));
    const drawer=page.locator('#wwAnnotationDrawer');await expect(drawer).toHaveClass(/--open/);
    const groups=page.locator('#viewWaveform .ww-pane-header-tools');
    for(const group of await groups.all()) {
      for(const button of await group.locator('button').all()) {
        await button.focus();await expect(button).toBeInViewport({ratio:1});
        await button.click({trial:true});
        const right=await button.evaluate(el=>el.getBoundingClientRect().right);
        expect(right).toBeLessThan((await drawer.boundingBox()).x);
      }
    }
    expect(await widths()).toEqual(before);
    await page.locator('.ww-pane-unit-mode:visible [data-pane-unit-mode="per_unit"]').first().click();await ready();
    await expect(page.locator('.ww-pane-unit-mode:visible [data-pane-unit-mode="per_unit"]').first()).toHaveAttribute('aria-pressed','true');
    await page.locator('.ww-pane-unit-mode:visible [data-pane-unit-mode="engineering"]').last().click();await ready();
    await expect(drawer).toHaveClass(/--open/);
    if(size.width===1024) await page.screenshot({path:info.outputPath(`annotations-${layout.toLowerCase()}.png`)});
    await page.evaluate(()=>wwSetAnnotationDrawerOpen(false));
    await expect.poll(()=>page.locator('#viewWaveform .ww-panel-header').evaluateAll(nodes=>nodes.map(node=>node.style.paddingRight)))
      .toEqual((await groups.all()).map(()=>'0px'));
  }
});
