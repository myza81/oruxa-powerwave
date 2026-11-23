const {test,expect}=require('./support/test');
const {workspaceId,BACKEND}=require('./support/event_reconstruction_helpers');
const {json,setupUnits,readyUnits,customUnits,axisCaps,assertCapGeometry}=require('./support/waveform_axis_unit_helpers');
test.setTimeout(90000);

test('resolved units follow actual raw metadata in every layout, never misleading names',async({page},info)=>{
  const units=['V','kV','A','kA','Hz','Hz/s','MW','Mvar','deg'];await setupUnits(page,units);
  for(const layout of ['Grouped','Separate','Custom']){
    if(layout==='Custom')await customUnits(page);else await page.locator('#layoutMode'+layout+'Btn').click();
    await readyUnits(page);
    const panes=await axisCaps(page);
    for(const pane of panes){const unique=[...new Set(pane.units)];expect(pane.caps[0].text).toBe(unique.length>1?'Mixed units':unique[0]);}
    if(layout==='Separate')expect(panes.map(p=>p.caps[0].text).sort()).toEqual(units.sort());
    await assertCapGeometry(page);
  }
  await info.attach('units.json',{body:JSON.stringify(await axisCaps(page)),contentType:'application/json'});
});

test('mixed units remain explicit and reconcile when channels are hidden or restored',async({page})=>{
  await setupUnits(page,['V','A']);await customUnits(page);
  await expect(page.locator('[data-waveform-axis-unit="y"]')).toHaveText('Mixed units');
  await expect(page.locator('[data-waveform-axis-unit="y"]')).toHaveAttribute('title','Y-axis units: V, A');
  await page.locator('.ww-legend-toggle').last().click();
  await expect(page.locator('[data-waveform-axis-unit="y"]')).toHaveText('V');
  await page.locator('.ww-legend-toggle').last().click();
  await expect(page.locator('[data-waveform-axis-unit="y"]')).toHaveText('Mixed units');
});

test('Voltage ENG/PU and recording-side changes use resolved response units, with no double conversion',async({page})=>{
  const {sid,base}=await setupUnits(page,['kV']);
  const group=await json(await page.request.post(`${base}/sources/${sid}/measurement-groups`,{data:{kind:'voltage',display_name:'Explicit voltage group',status:'confirmed',channel_refs:[{kind:'source',source_id:sid,channel_name:'Misleading title 0'}]}}),201);
  const groupUrl=`${base}/sources/${sid}/measurement-groups/${group.id}`;
  await json(await page.request.put(groupUrl+'/voltage-config',{data:{nominal_voltage_ll_kv:132,reference_mode:'manual',reference_override:'line_to_ground'}}));
  await json(await page.request.patch(groupUrl,{data:{status:'confirmed'}}));
  await page.evaluate(async()=>wwApplyUnitMode('per_unit'));
  await expect(page.locator('[data-waveform-axis-unit="y"]')).toHaveText('pu');
  const pu=await page.evaluate(()=>ww.panels[0].channels[0].values.slice());
  await json(await page.request.put(`${base}/sources/${sid}/measurement-side`,{data:{side:'secondary'}}));
  await page.evaluate(async()=>wwRefreshWaveformDisplayBasis());
  await expect(page.locator('[data-waveform-axis-unit="y"]')).toHaveText('pu');
  // WUI-004 displays the engine result; changing interpretation does not invent a conversion here.
  expect(await page.evaluate(()=>ww.panels[0].channels[0].values)).toEqual(pu);
  await page.evaluate(async()=>wwApplyUnitMode('engineering'));
  await expect(page.locator('[data-waveform-axis-unit="y"]')).toHaveText('kV');
});

test('calculated Current PU uses its resolved output and ENG restores A',async({page})=>{
  const {sid,base}=await setupUnits(page,['A']);
  const calc=await json(await page.request.post(`${base}/calculated-channels`,{data:{name:'Output title says Voltage',operation:'multiply_constant',inputs:[{kind:'source',source_id:sid,channel_name:'Misleading title 0'}],parameters:{constant:2}}}),201);
  await json(await page.request.put(`${base}/calculated-channels/${calc.id}/per-unit-config`,{data:{mode:'manual',current_base_value:2,current_base_unit:'kA',base_reference_side:'primary'}}));
  await page.evaluate(async()=>wwFetchCalculatedChannels());
  await page.locator(`#calculatedChannelsSidebarBody tr[data-source-id="${calc.id}"]`).click();
  await page.evaluate(async()=>wwApplyUnitMode('per_unit'));await readyUnits(page);
  await expect.poll(async()=>(await axisCaps(page)).find(p=>p.units.includes('pu'))?.caps[0].text).toBe('pu');
  await page.evaluate(async()=>wwApplyUnitMode('engineering'));
  expect((await axisCaps(page)).every(p=>p.caps[0].text==='A')).toBe(true);
});

test('calculated outputs with different units use backend output metadata',async({page})=>{
  const {sid,base}=await setupUnits(page,['V','Hz']);
  const result=[];
  for(const [operation,index,parameters] of [['multiply_constant',0,{constant:2}],['rocof',1,{window_ms:100}]]){
    result.push(await json(await page.request.post(`${base}/calculated-channels`,{data:{name:'Misleading output '+index,operation,inputs:[{kind:'source',source_id:sid,channel_name:'Misleading title '+index}],parameters,override:true}}),201));
  }
  await page.evaluate(async()=>wwFetchCalculatedChannels());
  for(const calc of result)await page.locator(`#calculatedChannelsSidebarBody tr[data-source-id="${calc.id}"]`).click();
  await page.locator('#layoutModeSeparateBtn').click();await readyUnits(page);
  for(const calc of result){const actual=await page.evaluate(id=>{const {panel,channel}=[...ww.displayed.values()].find(e=>e.channel.sourceId===id);return {unit:channel.unit,cap:panel.containerEl.querySelector('[data-waveform-axis-unit]').textContent};},calc.id);expect(actual.cap).toBe(calc.unit);expect(actual.unit).toBe(calc.unit);}
});

test('magnitude and uncalibrated angle axes retain distinct meanings through membership changes',async({page},info)=>{
  await page.goto('/index.html');const base=`${BACKEND}/api/v1/workspaces/${await workspaceId(page)}`;
  const csv='Time,Magnitude,Angle\n2026-11-03T10:00:00.000Z,100,20\n2026-11-03T10:00:00.010Z,110,30\n2026-11-03T10:00:00.020Z,90,40\n';
  const prep=await json(await page.request.post(`${base}/preparation-sources`,{multipart:{csv_file:{name:'Angle.csv',mimeType:'text/csv',buffer:Buffer.from(csv)}}}),201);
  const url=`${base}/preparation-sources/${prep.source_id}/working`;
  for(const [suffix,data] of [['header',{row_number:1}],['data-region',{start_row:2,end_row:4}],['columns/0/role',{role:'time_axis'}],['columns/1/role',{role:'waveform'}],['columns/2/role',{role:'waveform'}],['columns/1/engineering-quantity',{engineering_quantity:'Voltage'}],['columns/2/engineering-quantity',{engineering_quantity:'Voltage Angle'}],['columns/1/measured-unit',{measured_unit:'V'}],['time-axis',{column_indices:[0],interpreter_id:'absolute_datetime',confirmed:true}]])await json(await page.request.put(url+'/'+suffix,{data}));
  const source=await json(await page.request.post(`${base}/preparation-sources/${prep.source_id}/convert`));
  await page.evaluate(async()=>refreshAllSourceViews());await page.locator('#mainNavWaveformBtn').click();
  await page.evaluate(async sid=>wwAddSelectedChannels([...document.querySelectorAll('#channelGroups tr.channel-row--toggle[data-channel-kind="analog"]')].filter(row=>row.dataset.sourceId===sid).map(analogMetaFromRow)),source.source_id);await readyUnits(page);
  await expect(page.locator('[data-waveform-axis-unit="y"]')).toHaveText('V');
  await expect(page.locator('[data-waveform-axis-unit="y2"]')).toHaveText('Angle (unit n/a)');
  expect((await axisCaps(page))[0].axes).toEqual(['y','y2']);await assertCapGeometry(page);
  await page.screenshot({path:info.outputPath('magnitude-angle.png')});
  await page.locator('.ww-legend-toggle').first().click();
  await expect(page.locator('[data-waveform-axis-unit="y2"]')).toHaveCount(0);
  await expect(page.locator('[data-waveform-axis-unit="y"]')).toHaveText('Angle (unit n/a)');
});

test('unavailable metadata is explicit, even alongside channels with known units',async({page})=>{
  await setupUnits(page,['V','']);await customUnits(page);
  await expect(page.locator('[data-waveform-axis-unit="y"]')).toHaveText('Units incomplete');
  await page.locator('.ww-legend-toggle').first().click();
  await expect(page.locator('[data-waveform-axis-unit="y"]')).toHaveText('Unit n/a');
});

test('unit refresh and resize do not rebuild, fetch, change samples/ranges or disturb cursor/annotation anchors',async({page},info)=>{
  await setupUnits(page,['V']);
  await page.locator('#wwCursorModeBtn').click();
  await page.evaluate(async()=>{
    const p=ww.panels[0],c=p.channels[0],s=wwTimeGroupCursorState(wwPanelTimeGroupId(p));s.a.visible=true;s.a.time=.1;
    wwUpdateAllCursorOverlays();await wwCreateCalloutFromClick(p,c,.1);
    const note=[...ww.annotations.values()][0];wwEndAnnotationEdit(note.id,true);
    window.unitCounts={newPlot:0,react:0,fetch:0};for(const name of ['newPlot','react']){const f=Plotly[name];Plotly[name]=function(...a){unitCounts[name]++;return f.apply(this,a);};}
    const f=wwFetchChannelRange;wwFetchChannelRange=function(...a){unitCounts.fetch++;return f.apply(this,a);};
    window.unitBefore={values:c.values.slice(),time:c.time.slice(),range:p.chartEl._fullLayout.yaxis.range.slice(),margin:JSON.stringify(p.chartEl.layout.margin),note:wwAnchoredAnnotationTime(note),cursor:s.a.time};
    for(let i=0;i<5;i++)wwSyncWaveformAxisUnits(p);
  });
  await page.setViewportSize({width:1100,height:768});
  await page.evaluate(()=>wwSetPanelHeight(ww.panels[0],310));await page.waitForTimeout(250);
  await assertCapGeometry(page);
  const state=await page.evaluate(()=>{const p=ww.panels[0],c=p.channels[0],n=[...ww.annotations.values()][0];return {before:unitBefore,after:{values:c.values.slice(),time:c.time.slice(),range:p.chartEl._fullLayout.yaxis.range.slice(),margin:JSON.stringify(p.chartEl.layout.margin),note:wwAnchoredAnnotationTime(n),cursor:wwTimeGroupCursorState(wwPanelTimeGroupId(p)).a.time},counts:unitCounts};});
  expect(state.after).toEqual(state.before);expect(state.counts).toEqual({newPlot:0,react:0,fetch:0});
  await page.locator('[data-pane-y="in"]').click();await assertCapGeometry(page);
  await page.locator('[data-pane-y="auto"]').click();await assertCapGeometry(page);
  await info.attach('preserved-state.json',{body:JSON.stringify(state),contentType:'application/json'});
});
