const {expect}=require('@playwright/test');
const {uploadRecord,workspaceId,sourceIdFor,BACKEND}=require('./event_reconstruction_helpers');

async function json(response,status=200){expect(response.status(),await response.text()).toBe(status);return response.json();}
async function setupUnits(page,units=['V','A','Hz','MW','Mvar']){
  await page.goto('/index.html');
  const channels=units.map((unit,i)=>({name:'Misleading title '+i,unit,amplitude:100+i,frequencyHz:5}));
  await uploadRecord(page,{station:'UNIT_METADATA',startClock:'10:00:00.000000',durationS:.5,channels});
  const sid=await sourceIdFor(page,'UNIT_METADATA'),base=`${BACKEND}/api/v1/workspaces/${await workspaceId(page)}`;
  await page.locator('#mainNavWaveformBtn').click();
  await page.evaluate(async sid=>wwAddSelectedChannels([...document.querySelectorAll('#channelGroups tr.channel-row--toggle[data-channel-kind="analog"]')].filter(row=>row.dataset.sourceId===sid).map(analogMetaFromRow)),sid);
  await readyUnits(page);return {sid,base};
}
async function readyUnits(page){
  await page.waitForFunction(()=>ww.panels.length && ww.panels.every(p=>p.plotlyReady && p.chartEl._fullLayout && p.containerEl.querySelector('[data-waveform-axis-unit]')));
}
async function customUnits(page){
  await page.evaluate(()=>{ww.customGroups=[{id:'units',label:'Title must not determine units',channelKeys:[...ww.displayed.keys()]}];});
  await page.locator('#layoutModeCustomBtn').click();await readyUnits(page);
}
async function axisCaps(page){return page.evaluate(()=>ww.panels.map(p=>({id:p.id,units:p.channels.map(c=>c.unit),
  caps:[...p.containerEl.querySelectorAll('[data-waveform-axis-unit]')].map(n=>({axis:n.dataset.waveformAxisUnit,text:n.textContent,title:n.title})),
  axes:p.chartEl.data.map(t=>t.yaxis||'y')})));}
async function assertCapGeometry(page){
  const geometry=await page.evaluate(()=>ww.panels.map(p=>{
    const rect=n=>{const b=n.getBoundingClientRect();return {left:b.left,right:b.right,top:b.top,bottom:b.bottom,width:b.width,height:b.height};};
    const chart=rect(p.chartEl),s=p.chartEl._fullLayout._size,plot={left:chart.left+s.l,right:chart.left+s.l+s.w,top:chart.top+s.t};
    const ticks=[...p.chartEl.querySelectorAll('.ytick text,.y2tick text')].map(rect);
    return {plot,chart,header:rect(p.headerEl),labels:[...p.containerEl.querySelectorAll('[data-waveform-axis-unit]')].map(n=>({text:n.textContent,box:rect(n),font:getComputedStyle(n).fontSize,pointer:getComputedStyle(n).pointerEvents})),ticks};
  }));
  for(const pane of geometry)for(const label of pane.labels){
    expect(label.box.height).toBe(10);expect(label.font).toBe('10px');expect(label.pointer).toBe('none');
    expect(label.box.top).toBeGreaterThanOrEqual(pane.chart.top-.5);expect(label.box.bottom).toBeLessThanOrEqual(pane.plot.top+.5);
    expect(label.box.top).toBeGreaterThanOrEqual(pane.header.bottom-.5);
    expect(label.box.left).toBeGreaterThanOrEqual(pane.plot.left);expect(label.box.right).toBeLessThanOrEqual(pane.plot.right);
    for(const tick of pane.ticks)expect(label.box.right<=tick.left || label.box.left>=tick.right || label.box.bottom<=tick.top || label.box.top>=tick.bottom).toBe(true);
  }
  return geometry;
}
module.exports={json,setupUnits,readyUnits,customUnits,axisCaps,assertCapGeometry};
