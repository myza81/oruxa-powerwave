const {test,expect}=require('./support/test');
const {setupPaneScenario,readyPanes,paneLayout,voltagePane,assertLegend}=require('./support/waveform_pane_helpers');
const {expectTrueSubscripts}=require('./support/electrical_notation_helpers');
test.setTimeout(90000);

test('legend fits actual width, reports omissions, and opens the complete interactive list',async({page},info)=>{
  await page.setViewportSize({width:1800,height:768});await setupPaneScenario(page);
  const pane=await voltagePane(page);const wide=await assertLegend(page,pane);
  expect(wide.all).toBe(16);expect(wide.shown).toBeGreaterThan(0);
  await page.setViewportSize({width:900,height:768});await page.waitForTimeout(100);
  const narrow=await assertLegend(page,pane);expect(narrow.shown).toBeLessThan(wide.shown);
  const more=pane.locator('.ww-pane-legend-more');await more.focus();await page.keyboard.press('Enter');
  const popup=page.locator('.ww-pane-legend-popover');await expect(popup).toBeVisible();
  await expect(popup.locator('li')).toHaveCount(16);await expect(popup.locator('[data-legend-toggle]')).toHaveCount(16);
  const before=await page.evaluate(()=>[...ww.displayed.keys()]);
  const bounds=await popup.boundingBox();expect(bounds.x).toBeGreaterThanOrEqual(0);expect(bounds.x+bounds.width).toBeLessThanOrEqual(900);
  expect(bounds.y+bounds.height).toBeLessThanOrEqual(768);
  await expect(popup.locator('[data-legend-toggle]').first()).toBeFocused();await page.keyboard.press('ArrowDown');await expect(popup.locator('[data-legend-toggle]').nth(1)).toBeFocused();
  await page.keyboard.press('End');await expect(popup.locator('[data-legend-toggle]').last()).toBeFocused();
  await page.keyboard.press('Escape');await expect(popup).toHaveCount(0);await expect(more).toBeFocused();
  expect(await page.evaluate(()=>[...ww.displayed.keys()])).toEqual(before);
  await info.attach('adaptive-fit.json',{body:JSON.stringify({wide,narrow}),contentType:'application/json'});
});

test('same recording keeps short names; identical recording names and display aliases remain distinguishable',async({page})=>{
  await setupPaneScenario(page,{sources:1,voltages:3});
  let labels=await page.locator('#viewWaveform .ww-legend-item').evaluateAll(nodes=>nodes.map(node=>node.dataset.compactLabel));
  expect(labels).toEqual(['VA','VB','VC']);
  await page.evaluate(()=>{
    const first=ww.panels[0].channels[0];wwSetChannelDisplayName(first.sourceId,'VA','Shared alias');wwSetChannelDisplayName(first.sourceId,'VB','Shared alias');
  });
  labels=await page.locator('#viewWaveform .ww-legend-item').evaluateAll(nodes=>nodes.map(node=>node.dataset.compactLabel));
  expect(new Set(labels).size).toBe(3);expect(labels[0]).toContain('VA');expect(labels[1]).toContain('VB');
});

test('identical recording names and filenames use authoritative identity to resolve collisions',async({page})=>{
  await setupPaneScenario(page,{sameStation:true,voltages:3});
  const labels=await page.locator('#viewWaveform .ww-legend-item').evaluateAll(nodes=>nodes.map(node=>node.dataset.compactLabel));
  expect(new Set(labels).size).toBe(labels.length);
});

test('legend resize and disclosure do not fetch, recreate plots, change canonical identity or place annotations',async({page})=>{
  await setupPaneScenario(page);
  await page.evaluate(()=>{
    window.wuiNewPlots=0;const plot=Plotly.newPlot;Plotly.newPlot=function(...args){window.wuiNewPlots++;return plot.apply(this,args)};
    window.wuiIdentity=[...ww.displayed.keys()];window.wuiSamples=ww.panels.map(p=>p.chartEl.data.map(t=>({meta:t.meta,y:t.y.slice()})));
  });
  const requests=[];page.on('request',r=>{if(/waveform\?|cursor-values|annotation-anchor/.test(r.url()))requests.push(r.url())});
  await page.locator('#wwAnnotateBtn').click();await page.locator('#wwAnnotateMenu [data-annotation-type="text_note"]').click();
  const pane=await voltagePane(page);await pane.locator('.ww-legend-toggle').first().focus();
  await expect(page.locator('.ww-pane-legend-tip')).toBeVisible();
  await pane.locator('.ww-pane-legend-more').click();await expect(page.locator('.ww-pane-legend-popover')).toBeVisible();
  await page.locator('.ww-pane-legend-popover [data-legend-toggle]').last().focus();await page.keyboard.press('Escape');
  await page.setViewportSize({width:1024,height:640});await page.setViewportSize({width:1366,height:768});
  await page.evaluate(()=>new Promise(requestAnimationFrame));
  expect(requests).toEqual([]);
  expect(await page.evaluate(()=>({plots:window.wuiNewPlots,identity:[...ww.displayed.keys()],notes:ww.annotations.size,
    sameSamples:JSON.stringify(window.wuiSamples)===JSON.stringify(ww.panels.map(p=>p.chartEl.data.map(t=>({meta:t.meta,y:t.y.slice()}))))})))
    .toEqual({plots:0,identity:await page.evaluate(()=>window.wuiIdentity),notes:0,sameSamples:true});
});

test('long custom titles leave all local controls reachable; header identity follows its own Time Group',async({page})=>{
  await page.setViewportSize({width:1024,height:640});await setupPaneScenario(page,{sources:2,voltages:3,separateTimeGroups:true});
  await paneLayout(page,'Custom',{long:true});
  const panes=page.locator('#viewWaveform .ww-panel');await expect(panes).toHaveCount(2);
  for(const pane of await panes.all()) {
    const identity=pane.locator('.ww-pane-identity');await identity.focus();
    expect(await pane.locator('.ww-panel-label').evaluate(node=>node.scrollWidth>node.clientWidth)).toBe(true);
    const expected=await pane.evaluate(node=>node.closest('.ww-time-group-canvas').querySelector('.ww-tg-header-title').textContent);
    await expect(pane.locator('.ww-pane-time-group')).toContainText(expected);
    for(const button of await pane.locator('.ww-pane-header-tools button').all()) {await button.focus();await button.click({trial:true});}
  }
});

test('rename, colour, batch removal, Separate removal and layout rebuild refresh presentation and dispose old UI',async({page})=>{
  await setupPaneScenario(page);
  const pane=await voltagePane(page);
  await pane.locator('.ww-pane-legend-more').click();
  await page.evaluate(()=>{window.oldPane=ww.panels[0];window.oldKeys=[...ww.displayed.keys()];const c=oldPane.channels[0];wwSetChannelDisplayName(c.sourceId,c.channelName,'Owner alias');wwSetChannelColorOverride(c.sourceId,c.channelName,'#a020f0')});
  await expect(page.locator('.ww-pane-legend-popover')).toContainText('Owner alias');
  await page.keyboard.press('Escape');
  const alias=pane.locator('.ww-legend-item').filter({hasText:'Owner alias'});await expect(alias).toBeVisible();
  await expect(alias.locator('.ww-legend-dot')).toHaveCSS('background-color','rgb(160, 32, 240)');
  expect(await page.evaluate(()=>[...ww.displayed.keys()])).toEqual(await page.evaluate(()=>window.oldKeys));
  await paneLayout(page,'Separate');
  expect(await page.evaluate(()=>({observer:oldPane.legendObserver,frame:oldPane.legendFitFrame}))).toEqual({observer:null,frame:null});
  const count=await page.locator('#viewWaveform .ww-panel').count();
  await page.locator('#viewWaveform .ww-legend-remove').first().click();await expect(page.locator('#viewWaveform .ww-panel')).toHaveCount(count-1);
  await paneLayout(page,'Grouped');
  await page.evaluate(()=>wwRemoveChannelsByKeys(ww.panels[0].channels.slice(0,2).map(c=>wwChannelKey(c.sourceId,c.channelName))));
  await assertLegend(page,await voltagePane(page));
  await page.evaluate(()=>wwClearWorkspace({resetSourceBounds:true}));
  await expect(page.locator('.ww-pane-legend-popover,.ww-pane-legend-tip')).toHaveCount(0);
});

test('calculated channels keep rich notation and reference/calibration qualifications in the full legend',async({page})=>{
  const {workspace,backend}=await setupPaneScenario(page,{sources:1,voltages:3});
  const contexts=await (await page.request.get(`${backend}/api/v1/workspaces/${workspace}/engineering-contexts`)).json();
  const readiness=await (await page.request.get(`${backend}/api/v1/workspaces/${workspace}/calculated-channels/line-to-line-voltage/readiness`)).json();
  const ready=readiness.find(r=>r.outputs.AB.available);expect(ready,JSON.stringify(readiness)).toBeTruthy();
  const created=await page.request.post(`${backend}/api/v1/workspaces/${workspace}/calculated-channels/line-to-line-voltage`,{data:{engineering_context_id:ready.engineering_context_id,output:'all_three'}});
  expect(created.ok(),await created.text()).toBe(true);const {channels}=await created.json();
  await page.evaluate(()=>wwFetchCalculatedChannels());
  for(const calc of channels)await page.locator(`#calculatedChannelsSidebarBody tr.channel-row--toggle[data-source-id="${calc.id}"]`).click();
  await paneLayout(page,'Custom');
  const pane=await voltagePane(page);await page.setViewportSize({width:800,height:768});
  await page.locator('#wwSplitViewBtn').click();await readyPanes(page);
  const more=pane.locator('.ww-pane-legend-more');await more.click();
  const popup=page.locator('.ww-pane-legend-popover');await expectTrueSubscripts(popup.locator('.ww-electrical-symbol'));
  expect(contexts.length).toBeGreaterThan(0);
  expect(await popup.locator('li').count()).toBe(6);
  await expect(popup).toContainText('Calculated Channels');await expect(popup).toContainText('(V)');
});

test('popover projects existing qualification metadata without changing waveform arrays',async({page})=>{
  await setupPaneScenario(page);
  const values=await page.evaluate(()=>{
    const panel=ww.panels[0],first=panel.channels[0],second=panel.channels[1];
    // Presentation-state fixture: exercise the already-supported warning states.
    // This does not certify calibration or configure/change an engineering base.
    const reference=wwDisplayedReference;
    // Component-level projection fixture: status objects come from the existing
    // shared formatter; no PU engine or channel engineering state is altered.
    wwDisplayedReference=(source,name)=>source===first.sourceId && name===first.channelName
      ? wwPuReferenceStatus('configured','unverified') : source===second.sourceId && name===second.channelName
      ? wwPuReferenceStatus('base_required','incompatible') : reference(source,name);
    ww.sourceChannelsData.get(first.sourceId).analog_channels.find(c=>c.name===first.channelName).calibration_status='unverified';
    wwRenderLegend(panel);return panel.channels.map(c=>c.values.slice());
  });
  const pane=await voltagePane(page);await pane.locator('.ww-pane-legend-more').click();
  const popup=page.locator('.ww-pane-legend-popover');
  await expect(popup).toContainText('Unverified reference');await expect(popup).toContainText('PU unavailable');
  await expect(popup).toContainText('Calibration unverified');
  expect(await page.evaluate(()=>ww.panels[0].channels.map(c=>c.values.slice()))).toEqual(values);
});
