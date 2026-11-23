const { expect } = require('@playwright/test');
const { uploadRecord, workspaceId, BACKEND } = require('./event_reconstruction_helpers');

// Synthetic COMTRADE only. Names/units/phase fields are imported through the
// production API; no physical measurements or engineering authority are invented.
async function setupPaneScenario(page, { sources=2, voltages=8, currents=false, sameStation=false, separateTimeGroups=false }={}) {
  await page.goto('/index.html');
  const sourceIds=[];
  for(let index=0;index<sources;index++) {
    const names=['VA','VB','VC',...Array.from({length:Math.max(0,voltages-3)},(_,i)=>'Auxiliary '+(i+1))].slice(0,voltages);
    const channels=names.map((name,i)=>({name,unit:'V',phase:i<3?['A','B','C'][i]:'',amplitude:11000+i*200,frequencyHz:50}));
    if(currents)channels.push(...['IA','IB','IC'].map((name,i)=>({name,unit:'A',phase:['A','B','C'][i],amplitude:250+i*10,frequencyHz:50})));
    await uploadRecord(page,{station:sameStation?'SYNTHETIC Identical recording':'SYNTHETIC KPDN'+(index+1),
      startClock:separateTimeGroups && index?'10:10:00.000000':'10:00:00.000000',durationS:0.2,channels});
    const rows=page.locator('#wwRdRecordingList .ww-rd-recording-item');
    const ids=await rows.evaluateAll(nodes=>nodes.map(node=>node.dataset.sourceId));
    sourceIds.push(ids.find(id=>!sourceIds.includes(id)));
  }
  await page.locator('#mainNavWaveformBtn').click();
  await page.evaluate(async ids=>{
    const rows=[...document.querySelectorAll('#channelGroups tr.channel-row--toggle[data-channel-kind="analog"]')]
      .filter(row=>ids.includes(row.dataset.sourceId));
    await wwAddSelectedChannels(rows.map(analogMetaFromRow));
  },sourceIds);
  await readyPanes(page);
  return {sourceIds,workspace:await workspaceId(page),backend:BACKEND};
}
async function readyPanes(page) {
  await page.waitForFunction(()=>ww.panels.length>0 && ww.panels.every(panel=>panel.plotlyReady && panel.chartEl._fullLayout));
  await page.evaluate(()=>new Promise(requestAnimationFrame));
}
async function paneLayout(page,layout,{long=false}={}) {
  if(layout==='Custom') await page.evaluate(long=>{
    ww.customGroups=[{id:'wui003-voltage',label:long?'Owner comparison '+ 'long pane title '.repeat(16):'Voltage comparison',
      channelKeys:[...ww.channelMeta].filter(([,entry])=>(wwIsCalculatedSourceId(entry.sourceId)?wwCalculatedEngineeringTypeFor(entry.sourceId):entry.engineeringType)==='Voltage').map(([key])=>key)},
      {id:'wui003-current',label:'Current comparison',channelKeys:[...ww.channelMeta].filter(([,entry])=>(wwIsCalculatedSourceId(entry.sourceId)?wwCalculatedEngineeringTypeFor(entry.sourceId):entry.engineeringType)==='Current').map(([key])=>key)}];
  },long);
  await page.locator('#layoutMode'+layout+'Btn').click();await readyPanes(page);
}
async function voltagePane(page) {
  const id=await page.evaluate(()=>ww.panels.find(panel=>panel.channels.some(channel=>channel.engineeringType==='Voltage')).id);
  return page.locator(`[data-panel-id="${id}"]`);
}
async function assertLegend(page,pane) {
  const state=await pane.locator('.ww-legend').evaluate(el=>{
    const all=[...el.querySelectorAll(':scope > .ww-legend-item')],shown=all.filter(node=>!node.hidden);
    const more=el.querySelector('.ww-pane-legend-more'),box=el.getBoundingClientRect();
    return {all:all.length,shown:shown.length,moreHidden:more.hidden,moreText:more.textContent,
      rows:[...new Set(shown.map(node=>Math.round(node.getBoundingClientRect().top)))],
      inside:shown.concat(more.hidden?[]:[more]).every(node=>node.getBoundingClientRect().right<=box.right+1)};
  });
  expect(state.rows.length).toBeLessThanOrEqual(1);expect(state.inside).toBe(true);
  if(state.shown<state.all)expect(state.moreText).toBe('+'+(state.all-state.shown)+' more');
  expect(state.moreHidden).toBe(state.all===state.shown);return state;
}
module.exports={setupPaneScenario,readyPanes,paneLayout,voltagePane,assertLegend};
