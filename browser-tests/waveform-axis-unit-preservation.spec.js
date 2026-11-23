// Runs unchanged against accepted ec10270 and WUI-004. The collected projection
// must match exactly; UI labels/titles and generated workspace/source IDs excluded.
const {test,expect}=require('./support/test');
const {setupPaneScenario,paneLayout}=require('./support/waveform_pane_helpers');
test.setTimeout(90000);
for(const layout of ['Grouped','Separate','Custom'])test(`${layout} exact waveform geometry and engineering projection`,async({page},info)=>{
  await page.setViewportSize({width:1366,height:768});await setupPaneScenario(page,{sources:1,voltages:3,currents:true});
  await paneLayout(page,layout);await page.locator('#wwCursorModeBtn').click();
  await page.evaluate(async()=>{
    const p=ww.panels[0],c=p.channels[0],s=wwTimeGroupCursorState(wwPanelTimeGroupId(p));s.a.visible=s.b.visible=true;s.a.time=.02;s.b.time=.08;
    wwUpdateAllCursorOverlays();await wwCreateCalloutFromClick(p,c,.02);const note=[...ww.annotations.values()][0];wwEndAnnotationEdit(note.id,true);
    await wwStepZoomYPanel(p,'in');
  });
  await page.waitForTimeout(150);
  const projection=await page.evaluate(()=>({panels:ww.panels.map(p=>({
    channels:p.channels.map(c=>({name:c.channelName,unit:c.unit,time:c.time,values:c.values})),
    traces:p.chartEl.data.map(t=>({x:Array.from(t.x),y:Array.from(t.y),axis:t.yaxis||'y'})),
    xrange:p.chartEl._fullLayout.xaxis.range,yrange:p.chartEl._fullLayout.yaxis.range,
    plot:p.chartEl._fullLayout._size,height:p.chartEl._fullLayout.height,
    cursor:wwTimeGroupCursorState(wwPanelTimeGroupId(p)),
    cursorMarks:[...p.containerEl.closest('.ww-time-group-canvas').querySelectorAll('.ww-cursor-line')].map(n=>({left:n.style.left,top:n.style.top,height:n.style.height})),
  })),notes:[...ww.annotations.values()].map(n=>({type:n.type,time:wwAnchoredAnnotationTime(n),value:wwAnchoredAnnotationValue(n),unit:n.data.unit}))}));
  expect(projection.panels.length).toBeGreaterThan(0);
  await info.attach('projection.json',{body:JSON.stringify(projection),contentType:'application/json'});
});
