const {test,expect}=require('./support/test');
const {setupPaneScenario,paneLayout,voltagePane,assertLegend,readyPanes}=require('./support/waveform_pane_helpers');
test.setTimeout(90000);
const legendToggle=(pane,key)=>pane.locator(`.ww-legend-toggle[data-channel-key="${key}"]`);
const sidebar=(page,c)=>page.locator(`#channelGroups tr.channel-row--toggle[data-source-id="${c.sourceId}"][data-channel-name="${c.channelName}"]`);
async function firstChannel(page){return page.evaluate(()=>{const c=ww.panels[0].channels[0];return {sourceId:c.sourceId,channelName:c.channelName,key:wwChannelKey(c.sourceId,c.channelName)}})}
async function visible(page,key){return page.evaluate(key=>ww.displayed.has(key),key)}

for(const layout of ['Grouped','Custom'])test(`${layout}: legend and sidebar synchronize hidden members and overflow`,async({page})=>{
  await setupPaneScenario(page);await paneLayout(page,layout);const pane=await voltagePane(page),c=await firstChannel(page);
  const before=await assertLegend(page,pane);await legendToggle(pane,c.key).click();
  await expect.poll(()=>visible(page,c.key)).toBe(false);
  await expect(legendToggle(pane,c.key)).toHaveAttribute('aria-pressed','false');
  await expect(sidebar(page,c)).toHaveClass(/channel-row--hidden/);
  expect((await assertLegend(page,pane)).all).toBe(before.all);
  expect(await page.evaluate(key=>ww.panels.flatMap(p=>p.channels).some(c=>wwChannelKey(c.sourceId,c.channelName)===key),c.key)).toBe(false);
  await legendToggle(pane,c.key).click();await expect.poll(()=>visible(page,c.key)).toBe(true);await readyPanes(page);
  await expect(sidebar(page,c)).not.toHaveClass(/channel-row--hidden/);
  await sidebar(page,c).click();await expect(legendToggle(pane,c.key)).toHaveAttribute('aria-pressed','false');
  const off=await assertLegend(page,pane);expect(off.moreText).toBe(before.moreText);
  await sidebar(page,c).click();await expect(legendToggle(pane,c.key)).toHaveAttribute('aria-pressed','true');
  await pane.locator('.ww-pane-legend-more').click();
  const popup=page.locator('.ww-pane-legend-popover'),target=popup.locator('[data-legend-toggle]').last();
  const key=await target.getAttribute('data-channel-key');await target.click();
  await expect(popup).toBeVisible();await expect(target).toHaveAttribute('aria-pressed','false');
  await target.click();await expect.poll(()=>visible(page,key)).toBe(true);
  await expect(target).toHaveAttribute('aria-pressed','true');await page.keyboard.press('Escape');
  await page.setViewportSize({width:1024,height:768});await expect.poll(async()=>(await assertLegend(page,pane)).inside).toBe(true);
});

test('duplicate recording/channel names target only the canonical source and retain full disclosure',async({page})=>{
  await setupPaneScenario(page,{sameStation:true,voltages:3});const c=await firstChannel(page),pane=await voltagePane(page);
  const before=await page.evaluate(()=>[...ww.displayed.keys()]);
  const control=legendToggle(pane,c.key);await control.click();
  expect(await page.evaluate(()=>[...ww.displayed.keys()])).toEqual(before.filter(key=>key!==c.key));
  const labels=await pane.locator('.ww-legend-item').evaluateAll(nodes=>nodes.map(n=>n.dataset.compactLabel));
  expect(new Set(labels).size).toBe(labels.length);await control.focus();
  await expect(page.locator('.ww-pane-legend-tip')).toContainText('SYNTHETIC Identical recording');
  await expect(page.locator('.ww-pane-legend-tip')).toContainText(c.sourceId);
  await control.click();await expect.poll(()=>visible(page,c.key)).toBe(true);
});

test('Enter/Space toggle once and legend actions do not activate panes, cursors or annotations',async({page})=>{
  await setupPaneScenario(page,{currents:true});const c=await firstChannel(page),pane=await voltagePane(page);
  await page.evaluate(()=>{wwSetActivePanel(ww.panels.find(p=>p.channels[0].engineeringType==='Current'));window.activeBefore=ww.activePanelGroupKey});
  await page.locator('#wwCursorModeBtn').click();
  await page.locator('#wwAnnotateBtn').click();await page.locator('#wwAnnotateMenu [data-annotation-type="text_note"]').click();
  const state=()=>page.evaluate(()=>({active:ww.activePanelGroupKey,cursors:JSON.stringify([...ww.timeGroupCursorState]),notes:ww.annotations.size,placement:ww.annotationPlacementType}));
  const before=await state();await legendToggle(pane,c.key).focus();await page.keyboard.press('Enter');
  await expect.poll(()=>visible(page,c.key)).toBe(false);await expect(legendToggle(pane,c.key)).toBeFocused();
  await page.keyboard.press('Space');await expect.poll(()=>visible(page,c.key)).toBe(true);await readyPanes(page);
  expect(await state()).toEqual(before);
  await legendToggle(pane,c.key).dispatchEvent('keydown',{key:'Enter',repeat:true});expect(await visible(page,c.key)).toBe(true);
  await pane.locator('.ww-pane-legend-more').click();await page.keyboard.press('Escape');
  await expect(page.locator('.ww-pane-legend-popover')).toHaveCount(0);expect(await state()).toEqual(before);
});

for(const layout of ['Grouped','Separate','Custom'])test(`${layout}: last-channel removal and sidebar Show all preserve existing lifecycle`,async({page})=>{
  await setupPaneScenario(page,{sources:1,voltages:1});await paneLayout(page,layout);const c=await firstChannel(page);
  await legendToggle(await voltagePane(page),c.key).click();await expect(page.locator('#viewWaveform .ww-panel')).toHaveCount(0);
  await expect(page.locator('.ww-pane-legend-popover')).toHaveCount(0);await expect(sidebar(page,c)).toHaveClass(/channel-row--hidden/);
  const all=sidebar(page,c).locator('xpath=ancestor::details[contains(@class,"channel-subgroup")][1]').locator('.group-toggle-btn');
  await expect(all).toHaveText('Show all');await all.click();await readyPanes(page);
  await expect(legendToggle(await voltagePane(page),c.key)).toHaveAttribute('aria-pressed','true');
  if(layout==='Separate'){
    await page.locator('#viewWaveform .ww-legend-remove').click();await expect(page.locator('#viewWaveform .ww-panel')).toHaveCount(0);
    await sidebar(page,c).click();await readyPanes(page);await expect(page.locator('#viewWaveform .ww-panel')).toHaveCount(1);
  }
  await expect(all).toHaveText('Hide all');await all.click();await expect(page.locator('#viewWaveform .ww-panel')).toHaveCount(0);
});

test('hidden membership survives supported layout round trips, rename and recolor',async({page})=>{
  await setupPaneScenario(page,{sources:1,voltages:3});const c=await firstChannel(page);await sidebar(page,c).click();
  for(const layout of ['Custom','Separate','Grouped','Custom','Grouped']){
    // Include hidden members from the existing metadata inventory in the custom definition.
    if(layout==='Custom')await page.evaluate(()=>{ww.customGroups=[{id:'known',label:'Known channels',channelKeys:[...ww.channelMeta.keys()]}]});
    await page.locator('#layoutMode'+layout+'Btn').click();await readyPanes(page);
    if(layout==='Separate')await expect(page.locator(`.ww-legend-toggle[data-channel-key="${c.key}"]`)).toHaveCount(0);
    else await expect(legendToggle(await voltagePane(page),c.key)).toHaveAttribute('aria-pressed','false');
  }
  await page.evaluate(c=>{wwSetChannelDisplayName(c.sourceId,c.channelName,'Owner hidden alias');wwSetChannelColorOverride(c.sourceId,c.channelName,'#a020f0')},c);
  const control=legendToggle(await voltagePane(page),c.key);await expect(control).toContainText('Owner hidden alias');
  await expect(control.locator('.ww-legend-dot')).toHaveCSS('background-color','rgb(160, 32, 240)');
  await control.click();await expect.poll(()=>visible(page,c.key)).toBe(true);
});

test('legend hide/show preserves physical samples and engineering metadata',async({page})=>{
  await setupPaneScenario(page,{sources:1,voltages:3});const c=await firstChannel(page);
  const before=await page.evaluate(key=>{const entry=ww.displayed.get(key);window.physical=entry.channel.values.slice();window.inventory=JSON.stringify([...ww.sourceChannelsData]);return {values:window.physical,source:key}},c.key);
  const control=legendToggle(await voltagePane(page),c.key);await control.click();await control.click();
  await expect.poll(()=>visible(page,c.key)).toBe(true);await readyPanes(page);
  expect(await page.evaluate(key=>({values:ww.displayed.get(key).channel.values,inventoryUnchanged:JSON.stringify([...ww.sourceChannelsData])===window.inventory}),c.key))
    .toEqual({values:before.values,inventoryUnchanged:true});
});

test('partial source Show all/Hide all synchronizes every surviving legend entry',async({page})=>{
  await setupPaneScenario(page,{voltages:3});const c=await firstChannel(page),pane=await voltagePane(page);
  await legendToggle(pane,c.key).click();const row=sidebar(page,c);
  const all=row.locator('xpath=ancestor::details[contains(@class,"channel-subgroup")][1]').locator('.group-toggle-btn');
  await expect(all).toHaveText('Show all');await all.click();
  await expect.poll(()=>visible(page,c.key)).toBe(true);await expect(all).toHaveText('Hide all');await all.click();
  await expect(pane.locator('.ww-legend-toggle[aria-pressed="false"]')).toHaveCount(3);
  await expect(pane.locator('.ww-legend-toggle[aria-pressed="true"]')).toHaveCount(3);
  await expect(pane.locator('.ww-legend-toggle')).toHaveCount(6);await all.click();
  await expect(pane.locator('.ww-legend-toggle[aria-pressed="true"]')).toHaveCount(6);
});

test('known PU membership survives hide and layout changes without a second eligibility rule',async({page})=>{
  await setupPaneScenario(page,{sources:1,voltages:3});
  await page.locator('#viewWaveform [data-pane-unit-mode="per_unit"]').first().click();
  await page.waitForFunction(()=>ww.panels.every(p=>p.channels.every(c=>!!c.perUnitStatus && wwPanelGroupKeyFor(c)===p.groupKey)));
  const c=await firstChannel(page);await legendToggle(await voltagePane(page),c.key).click();
  for(const layout of ['Custom','Separate','Grouped']){
    await paneLayout(page,layout);
    if(layout!=='Separate')await expect(legendToggle(await voltagePane(page),c.key)).toHaveAttribute('aria-pressed','false');
  }
  await legendToggle(await voltagePane(page),c.key).click();await expect.poll(()=>visible(page,c.key)).toBe(true);
});

test('calculated-channel legend uses the existing calculated sidebar handler and canonical identity',async({page})=>{
  const {workspace,backend}=await setupPaneScenario(page,{sources:1,voltages:3});
  const endpoint=`${backend}/api/v1/workspaces/${workspace}/calculated-channels/line-to-line-voltage`;
  const readiness=await(await page.request.get(endpoint+'/readiness')).json();const ready=readiness.find(r=>r.outputs.AB.available);expect(ready).toBeTruthy();
  const response=await page.request.post(endpoint,{data:{engineering_context_id:ready.engineering_context_id,output:'all_three'}});
  expect(response.ok()).toBe(true);const {channels}=await response.json();await page.evaluate(()=>wwFetchCalculatedChannels());
  for(const calc of channels)await page.locator(`#calculatedChannelsSidebarBody tr.channel-row--toggle[data-source-id="${calc.id}"]`).click();
  await paneLayout(page,'Custom');const pane=await voltagePane(page),calc=channels[0];
  const key=await page.evaluate(id=>{const c=[...ww.displayed.values()].find(e=>e.channel.sourceId===id).channel;return wwChannelKey(c.sourceId,c.channelName)},calc.id);
  const control=legendToggle(pane,key);await control.click();await expect.poll(()=>visible(page,key)).toBe(false);
  await expect(page.locator(`#calculatedChannelsSidebarBody tr[data-source-id="${calc.id}"]`)).toHaveClass(/channel-row--hidden/);
  await control.click();await expect.poll(()=>visible(page,key)).toBe(true);await expect(control).toHaveAttribute('aria-pressed','true');
});

for(const layout of ['Grouped','Custom'])test(`${layout}: cursor drag strips cannot cover legend or pane controls`,async({page})=>{
  await setupPaneScenario(page,{currents:true});await paneLayout(page,layout);
  const pane=await voltagePane(page),c=await firstChannel(page);
  const groupId=await pane.evaluate(node=>node.closest('.ww-time-group-canvas').dataset.timeGroupId);
  await page.evaluate(()=>wwSetActivePanel(ww.panels.find(p=>p.channels[0].engineeringType==='Current')));
  await page.locator('#wwCursorModeBtn').click();
  const active=await page.evaluate(()=>ww.activePanelGroupKey);
  async function alignCursor(control){
    await control.focus();await control.evaluate(node=>node.scrollIntoView({block:'center',inline:'nearest'}));
    const box=await control.boundingBox(),x=box.x+box.width/2;
    const time=await page.evaluate(({groupId,x})=>{
      const state=wwTimeGroupCursorState(groupId);state.enabled=true;state.a.visible=true;state.b.visible=false;
      state.a.time=wwCursorPixelXToTime(groupId,x);wwUpdateAllCursorOverlays();return state.a.time;
    },{groupId,x});
    expect(Math.abs(await page.evaluate(({groupId,time})=>wwCursorTimeToPixelX(groupId,time),{groupId,time})-x)).toBeLessThan(1);
    expect(await control.evaluate(node=>{const r=node.getBoundingClientRect();return node.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2))})).toBe(true);
    return time;
  }
  const control=legendToggle(pane,c.key),time=await alignCursor(control);await control.click();
  await expect.poll(()=>visible(page,c.key)).toBe(false);
  expect(await page.evaluate(id=>wwTimeGroupCursorState(id).a.time,groupId)).toBe(time);
  expect(await page.evaluate(()=>ww.activePanelGroupKey)).toBe(active);
  const identity=pane.locator('.ww-pane-identity'),next=await alignCursor(identity);await identity.click();
  expect(await page.evaluate(id=>wwTimeGroupCursorState(id).a.time,groupId)).toBe(next);
  const zoom=pane.locator('[data-pane-y="in"]'),last=await alignCursor(zoom);await zoom.click();
  expect(await page.evaluate(id=>wwTimeGroupCursorState(id).a.time,groupId)).toBe(last);
  expect(await page.evaluate(()=>ww.annotations.size)).toBe(0);
});
