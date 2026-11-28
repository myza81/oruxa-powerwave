const {test,expect}=require('./support/test');
const {setupToolbarGroups,activateToolbarGroup,placeToolbarCursors}=require('./support/waveform_toolbar_refinement_helpers');
test.setTimeout(90000);

test('Time Group headers retain bounded sticky handoff and live cursor updates',async({page},info)=>{
  await page.setViewportSize({width:1280,height:800});
  const groups=await setupToolbarGroups(page);
  for(const id of groups){await activateToolbarGroup(page,id);await page.locator('#wwCursorModeBtn').click();await placeToolbarCursors(page,id);}
  const scroller=page.locator('#activeViewArea');
  for(const id of groups){
    const canvas=page.locator(`.ww-time-group-canvas[data-time-group-id="${id}"]`);
    await canvas.locator('.ww-tg-header-title').scrollIntoViewIfNeeded();
    await page.evaluate(id=>{
      const root=document.getElementById('activeViewArea'),canvas=document.querySelector(`.ww-time-group-canvas[data-time-group-id="${id}"]`);
      root.scrollTop+=canvas.getBoundingClientRect().top-root.getBoundingClientRect().top+80;
    },id);
    await expect.poll(async()=>Math.abs((await canvas.locator('.ww-tg-sticky-top').boundingBox()).y-(await scroller.boundingBox()).y)).toBeLessThan(2);
    await expect(canvas.locator('.ww-tg-header-meta')).toBeInViewport({ratio:1});
    await expect(canvas.locator('.ww-tg-cursor-readout')).toBeInViewport({ratio:1});
    const meta=await canvas.locator('.ww-tg-header-meta').textContent();
    const expected=await page.evaluate(id=>{
      const state=wwTimeGroupCursorState(id);state.a.time+=0.125;
      wwUpdateAllCursorOverlays();return wwFormatCursorPointTime(state.a.time,id);
    },id);
    await expect(canvas.locator('.ww-tg-cursor-readout-value--a')).toHaveText(expected);
    expect(await canvas.locator('.ww-tg-header-meta').textContent()).toBe(meta);
  }
  const first=page.locator(`.ww-time-group-canvas[data-time-group-id="${groups[0]}"]`);
  const second=page.locator(`.ww-time-group-canvas[data-time-group-id="${groups[1]}"]`);
  expect((await first.locator('.ww-tg-sticky-top').boundingBox()).y).toBeLessThan((await second.locator('.ww-tg-sticky-top').boundingBox()).y-20);
  await page.screenshot({path:info.outputPath('sticky-second-time-group.png')});
});

test('long metadata and cursor readouts wrap within their owning header',async({page},info)=>{
  await page.setViewportSize({width:1280,height:800});
  const [id]=await setupToolbarGroups(page,{sources:1,multipleGroups:false});
  await activateToolbarGroup(page,id);await page.locator('#wwCursorModeBtn').click();await placeToolbarCursors(page,id);
  const canvas=page.locator(`.ww-time-group-canvas[data-time-group-id="${id}"]`);
  // Presentation stress only: real formatted metadata repeated, without changing
  // timestamps/source/cursor state or injecting extra sources into the domain.
  await canvas.evaluate(el=>{
    el.querySelector('.ww-tg-header').style.maxWidth='340px';
    const meta=el.querySelector('.ww-tg-header-meta');meta.textContent=[meta.textContent,meta.textContent,meta.textContent].join(' · ');
    for(const value of el.querySelectorAll('.ww-tg-cursor-readout-value'))value.textContent+='123456789';
  });
  for(const theme of ['light','dark']){
    await page.evaluate(theme=>PowerwaveTheme.setTheme(theme),theme);
    const bounds=await canvas.evaluate(el=>{
      const header=el.querySelector('.ww-tg-header'),identity=header.querySelector('.ww-tg-header-identity'),readout=header.querySelector('.ww-tg-cursor-readout');
      const rect=node=>{const r=node.getBoundingClientRect();return {left:r.left,right:r.right,top:r.top,bottom:r.bottom}};
      return {header:rect(header),identity:rect(identity),readout:rect(readout),overflow:header.scrollWidth>header.clientWidth,
        items:[...readout.children].map(rect)};
    });
    expect(bounds.overflow).toBe(false);
    expect(bounds.readout.top).toBeGreaterThanOrEqual(bounds.identity.bottom);
    for(const item of bounds.items){expect(item.right).toBeLessThanOrEqual(bounds.header.right+1);expect(item.left).toBeGreaterThanOrEqual(bounds.header.left);}
    await canvas.locator('.ww-tg-header').screenshot({path:info.outputPath(`wrapped-${theme}.png`)});
  }
});
