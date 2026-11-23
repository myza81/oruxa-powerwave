const {expect}=require('@playwright/test');
const {uploadRecord}=require('./event_reconstruction_helpers');

// Synthetic COMTRADE fixtures, imported through the normal local application.
async function setupToolbarGroups(page,{sources=3,multipleGroups=true,layout='Grouped'}={}) {
  await page.goto('/index.html');const ids=[];
  for(let i=0;i<sources;i++) {
    await uploadRecord(page,{station:'SYNTHETIC HEADER '+(i+1),startClock:multipleGroups && i===sources-1 && sources>1?'10:15:08.000000':'10:04:08.000000',durationS:7,
      channels:[{name:'VA',unit:'V',phase:'A',amplitude:11000,frequencyHz:50},
        {name:'VB',unit:'V',phase:'B',amplitude:11000,frequencyHz:50},
        {name:'IA',unit:'A',phase:'A',amplitude:250,frequencyHz:50}]});
    const all=await page.locator('#wwRdRecordingList .ww-rd-recording-item').evaluateAll(nodes=>nodes.map(n=>n.dataset.sourceId));
    ids.push(all.find(id=>!ids.includes(id)));
  }
  await page.locator('#mainNavWaveformBtn').click();
  await page.evaluate(async ids=>{
    const rows=[...document.querySelectorAll('#channelGroups tr.channel-row--toggle[data-channel-kind="analog"]')].filter(row=>ids.includes(row.dataset.sourceId));
    await wwAddSelectedChannels(rows.map(analogMetaFromRow));
  },ids);
  if(layout==='Custom')await page.evaluate(()=>{
    ww.customGroups=['Voltage','Current'].map(type=>({id:type,label:'Owner '+type+' comparison',
      channelKeys:[...ww.displayed].filter(([,entry])=>entry.channel.engineeringType===type).map(([key])=>key)}));
  });
  await page.locator('#layoutMode'+layout+'Btn').click();await readyToolbarCharts(page);
  // Canvas order is the existing sorted Time Group order, which can differ
  // from channel-add order because imported source identities are random.
  return page.locator('#wwTimeGroupCanvases > .ww-time-group-canvas').evaluateAll(nodes=>nodes.map(node=>node.dataset.timeGroupId));
}
async function readyToolbarCharts(page) {
  await page.waitForFunction(()=>ww.panels.length>0 && ww.panels.every(p=>p.plotlyReady && p.chartEl._fullLayout));
  await page.waitForFunction(()=>[...new Set(ww.panels.map(wwPanelTimeGroupId))].every(id=>{
    const range=wwTimeGroupVisibleRange(id);return range && Number.isFinite(range.start) && Number.isFinite(range.end);
  }));
  // Native tab zoom schedules the existing Plotly resize asynchronously.
  await page.waitForFunction(()=>ww.panels.every(p=>Math.abs(p.chartEl._fullLayout.width-p.chartEl.getBoundingClientRect().width)<2));
  await page.evaluate(()=>new Promise(requestAnimationFrame));
}
async function toolbarRanges(page) {
  return page.evaluate(()=>Object.fromEntries([...new Set(ww.panels.map(wwPanelTimeGroupId))].map(id=>[id,{...wwTimeGroupVisibleRange(id)}])));
}
async function activateToolbarGroup(page,id) {
  const button=page.locator(`.ww-time-group-canvas[data-time-group-id="${id}"] .ww-pane-identity`).first();
  await button.focus();
  // Center in the scroll box so the owning sticky header stays above it.
  await button.evaluate(node=>node.scrollIntoView({block:'center',inline:'nearest',behavior:'instant'}));
  await button.click();
  expect(await page.evaluate(()=>wwActiveTimeGroupId())).toBe(id);
}
async function placeToolbarCursors(page,id) {
  return page.evaluate(id=>{
    const range=wwTimeGroupVisibleRange(id);
    const state=wwTimeGroupCursorState(id);state.a.visible=true;state.a.time=range.start+2;state.b.visible=true;state.b.time=range.start+4.304;
    wwUpdateAllCursorOverlays();wwSyncGlobalWaveformToolbar();
    return {a:state.a.time,b:state.b.time};
  },id);
}
module.exports={setupToolbarGroups,readyToolbarCharts,toolbarRanges,activateToolbarGroup,placeToolbarCursors};
