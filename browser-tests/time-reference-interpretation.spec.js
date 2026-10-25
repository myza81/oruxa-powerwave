const { test, expect } = require("./support/test");
const { clockFixture } = require("./support/ben5k_clock");
const { uploadRecord, addRecords, selectChannel, waitForPlot } = require("./support/event_reconstruction_helpers");
async function getApi(page, suffix) {
 return page.evaluate(async suffix => (await fetch(apiBaseUrl()+"/api/v1/workspaces/"+currentWorkspaceId()+suffix)).json(),suffix);
}
async function timingState(page) {
 return page.evaluate(()=>({
  groups:Array.from(ww.timeGroups,([id,g])=>({id,sources:g.sourceIds})),
  timing:Array.from(ww.sourceTiming),
  offsets:Array.from(ww.alignmentOffsets),
  cursors:Array.from(ww.timeGroupCursorState),
  firstSamples:ww.panels.flatMap(p=>p.channels.map((c,i)=>({id:c.sourceId,x:p.chartEl.data?.[i]?.x?.[0]}))),
 }));
}
for (const timezoneId of ["UTC", "America/New_York", "Asia/Kuala_Lumpur"]) {
 test.describe(timezoneId,()=>{
  test.use({timezoneId});
  test("interpret once: automatic Waveform alignment, shared consumers, raw reset and reload",async({page},testInfo)=>{
   const errors=[];page.on("pageerror",e=>errors.push(e.message));
   await page.goto("/index.html");
   await uploadRecord(page,{station:"KTBR",date:"16/10/2026",startClock:"18:03:14.037467",triggerClock:"18:03:14.537467",rateHz:5000,durationS:.6});
   await page.locator("#mainNavRecordingsBtn").click();
   await page.locator("#recordingsUploadBtn, #recordingsEmptyUploadBtn").first().click();
   await page.locator("#uploadModalFormatSelect").selectOption("ben");
   await page.locator("#uploadModalFile_0").setInputFiles({name:"GPTH.ben",mimeType:"application/octet-stream",buffer:clockFixture()});
   await page.locator("#uploadModalSubmitBtn").click();
   await expect(page.locator("#uploadModalOverlay")).toBeHidden();
   const sources=await getApi(page,"/sources");
   const gpth=sources.find(s=>s.station_name==="CLOCK TEST").source_id;
   const ktbr=sources.find(s=>s.station_name==="KTBR").source_id;
   const row=()=>page.locator(`#recordingsTableBody tr[data-source-id="${gpth}"]`);
   await row().click();
   await expect(page.locator("#workspaceRow")).toBeVisible();
   for(const sid of [ktbr,gpth]) {
    const source=page.locator(`#channelGroups details.source-recording[data-source-id="${sid}"]`);
    if(!await source.evaluate(el=>el.open)) await source.locator(":scope > summary").click();
    await source.locator('tr.channel-row--toggle[data-channel-kind="analog"]').first().click();
   }
   await expect(page.locator("#wwWorkspaceLoading")).toBeHidden();
   await expect.poll(async()=> (await timingState(page)).firstSamples.filter(s=>Number.isFinite(s.x)).length).toBe(2);
   await page.evaluate(async ktbr=>{
    await fetch(apiBaseUrl()+"/api/v1/workspaces/"+currentWorkspaceId()+"/synchronization/t0",{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({source_id:ktbr,t0_workspace_time:.4})});
    await wwFetchSynchronizationStateForWorkspace();
    const cursor=wwEnsureTimeGroupCursorStateEntry(ktbr);cursor.enabled=true;cursor.a.time=.4;
   },ktbr);
   await page.locator("#mainNavRecordingsBtn").click();
   await row().locator('[data-action="details"]').click();
   const select=page.locator(`.recording-time-reference[data-source-id="${gpth}"]`);
   await expect(select).toHaveValue("raw");
   expect(await select.locator("option").count()).toBe(106);
   await select.selectOption("480");
   await expect(select).toBeEnabled();
   await expect(page.locator(`.recording-details-row[data-details-for="${gpth}"]`)).toContainText("2026-10-16T10:03:14.535400Z");
   await expect.poll(async()=> (await timingState(page)).groups.length).toBe(1);
   const aligned=await getApi(page,"/synchronization/sources");
   expect(aligned.find(s=>s.source_id===ktbr).timestamp_placement_offset_s).toBeCloseTo(.002067,10);
   const t0=await getApi(page,"/synchronization/t0?source_id="+ktbr);
   expect(t0.t0_workspace_time).toBeCloseTo(.402067,10);
   const channels=await getApi(page,`/sources/${gpth}/channels`);
   expect(channels.timebase.trigger_time_utc).toBe("2026-10-16T10:03:14.535400Z");
   expect(channels.source.time_basis).toBe("unknown");
   expect(channels.timebase.time_reference_interpretation.provenance).toBe("user_assigned");
   expect((await getApi(page,"/event-reconstruction/definition")).defined).toBe(false);
   // The interpretation rebuilds Plotly panels; metadata can be ready first.
   await expect.poll(async()=>{
    const samples=(await timingState(page)).firstSamples;
    return [ktbr,gpth].filter(id=>Number.isFinite(samples.find(s=>s.id===id)?.x)).length;
   }).toBe(2);
   const state=await timingState(page);
   expect(state.cursors.find(([id])=>id===gpth)[1].a.time).toBeCloseTo(.402067,10);
   // Plotted source-native first samples are mapped once, with the common t0 subtracted.
   expect(state.firstSamples.find(s=>s.id===ktbr).x-state.firstSamples.find(s=>s.id===gpth).x).toBeCloseTo(.002067,10);
   await page.screenshot({path:testInfo.outputPath("automatic-interpretation.png")});
   // Existing Event Reconstruction uses the same effective timestamps when opened.
   await addRecords(page,["KTBR","CLOCK TEST"]);
   await selectChannel(page,"KTBR","VA");await selectChannel(page,"CLOCK TEST","CLOCK VR");await waitForPlot(page,2);
   const er=await getApi(page,"/event-reconstruction/definition");
   expect(er.members.find(m=>m.record_id===gpth).recorded_placement_s).toBeCloseTo(-.002067,10);
   await page.locator("#mainNavRecordingsBtn").click();
   await select.selectOption("raw");await expect(select).toBeEnabled();
   await expect.poll(async()=> (await timingState(page)).groups.length).toBe(2);
   expect((await getApi(page,`/sources/${gpth}`)).trigger_time_utc).toBeNull();
   expect((await getApi(page,"/synchronization/t0?source_id="+ktbr)).t0_workspace_time).toBeCloseTo(.4,10);
   expect((await getApi(page,"/event-reconstruction/definition")).members.find(m=>m.record_id===gpth).recorded_placement_s).toBeNull();
   await select.selectOption("480");await expect(select).toBeEnabled();
   const nonce=await page.evaluate(()=>powerwavePageSessionId);
   const storage=await page.evaluate(()=>({...localStorage,...sessionStorage}));
   expect(JSON.stringify(storage)).not.toContain(nonce);
   expect(JSON.stringify(storage)).not.toMatch(/offset_minutes|time_reference_interpretation/);
   await page.reload();
   expect(await page.evaluate(()=>powerwavePageSessionId)).not.toBe(nonce);
   const reloaded=await getApi(page,`/sources/${gpth}`);
   expect(reloaded.trigger_time_utc).toBeNull();expect(reloaded.time_reference_interpretation).toBeNull();
   expect(reloaded.trigger_time).toBe("2026-10-16T18:03:14.535400");
   expect(errors).toEqual([]);
  });
 });
}
