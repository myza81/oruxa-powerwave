// WUI-002 exact-artwork verification, including actual Chrome per-tab zoom.
const base = require('./support/test');
const { chromium } = require('playwright');
const { uploadRecord } = require('./support/event_reconstruction_helpers');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const phase = process.env.WUI_ICON_PHASE || 'after';
const origin = `http://127.0.0.1:${process.env.PW_FRONTEND_PORT || '8101'}/${phase === 'before' ? 'before/' : ''}`;

const test = base.test.extend({
  context: async ({}, use, info) => {
    const extension = info.outputPath('zoom-extension');
    fs.mkdirSync(extension, { recursive: true });
    fs.writeFileSync(path.join(extension, 'manifest.json'), JSON.stringify({
      manifest_version: 3, name: 'Local toolbar zoom verification', version: '1.0',
      permissions: ['tabs'], background: { service_worker: 'background.js' },
    }));
    fs.writeFileSync(path.join(extension, 'background.js'), 'chrome.runtime.onInstalled.addListener(() => {});');
    const context = await chromium.launchPersistentContext(info.outputPath('private-profile'), {
      channel: 'chromium', headless: true, baseURL: origin, viewport: { width: 1280, height: 800 },
      ignoreDefaultArgs: ['--disable-extensions'],
      args: [`--disable-extensions-except=${extension}`, `--load-extension=${extension}`],
    });
    context.setDefaultTimeout(15000);
    try { await use(context); } finally { await context.close(); }
  },
});
const { expect } = base;
// Native tab zoom uses a fresh persistent browser profile and captures SVG/source
// evidence. Allow cold-profile startup on Windows without weakening assertions.
test.setTimeout(90000);
const exactControls = ['wwZoomXInBtn','wwZoomXOutBtn','wwAutoscaleXBtn','wwCursorModeBtn',
  'wwAnnotateBtn','wwSplitViewBtn','clearWorkspaceBtn'];

async function setZoom(context, page, factor) {
  const worker = context.serviceWorkers()[0] || await context.waitForEvent('serviceworker', { timeout: 15000 });
  const result = await worker.evaluate(async ({ url, factor }) => {
    const tab = (await chrome.tabs.query({})).find(tab => tab.url === url);
    if (!tab) throw new Error('Private verification tab not found');
    await chrome.tabs.setZoom(tab.id, factor);
    return chrome.tabs.getZoom(tab.id);
  }, { url: page.url(), factor });
  expect(result).toBe(factor);
  await expect.poll(() => page.evaluate(() => innerWidth)).toBe(1280 / factor);
  await expect.poll(() => page.evaluate(() => devicePixelRatio)).toBe(factor);
  return page.evaluate(() => ({ width: innerWidth, height: innerHeight, dpr: devicePixelRatio }));
}

for (const layout of ['Grouped','Separate','Custom']) for (const theme of ['light','dark']) for (const zoom of [1, 1.25]) {
  test(`${phase} ${layout} ${theme} toolbar icons at ${zoom * 100}% browser zoom`, async ({ page, context }, info) => {
    const response = await page.goto('index.html');
    const body = await response.body();
    const sourceFile = phase === 'before' ? '../.local-data/icon-before-index.html' : '../frontend/index.html';
    const normalize = value => value.replace(/^\uFEFF/, '').replace(/\r\n/g, '\n');
    expect(normalize(body.toString('utf8'))).toBe(normalize(fs.readFileSync(path.join(__dirname, sourceFile), 'utf8')));
    const errors = [];
    page.on('response', r => { if (r.url().includes('/assets/icons/') && r.status() >= 400) errors.push(r.url()); });
    await uploadRecord(page, {
      station: 'WUI_ICONS', startClock: '10:00:00.000000', durationS: 2,
      channels: [{ name: 'KPDN1 VR', unit: 'V', phase: 'R', amplitude: 11000, frequencyHz: 50 }],
    });
    const row = page.locator('#wwRdRecordingList .ww-rd-recording-item').first();
    const sourceId = await row.getAttribute('data-source-id');
    await row.click();
    await page.locator('#mainNavWaveformBtn').click();
    await page.locator(`#channelGroups tr.channel-row--toggle[data-source-id="${sourceId}"][data-channel-name="KPDN1 VR"]`).click();
    await expect(page.locator('#viewWaveform .ww-panel')).toHaveCount(1);
    await page.locator('#layoutMode' + layout + 'Btn').click();
    await page.locator('#wwCursorModeBtn').click();
    await expect(page.locator('#wwCursorModeBtn')).toHaveAttribute('aria-pressed','true');
    await page.evaluate(t => PowerwaveTheme.setTheme(t), theme);
    const zoomMetrics = await setZoom(context, page, zoom);
    const toolbar = page.locator('#wwToolbar');
    await expect(toolbar).toBeInViewport({ ratio: 1 });
    for (const button of await toolbar.locator('button:visible').all()) {
      await expect(button).toBeInViewport({ ratio: 1 });
      if (await button.isEnabled()) await button.click({ trial: true });
    }
    const evidence = [];
    for (const id of exactControls.concat(layout === 'Custom' ? ['editChannelGroupsBtn'] : [])) {
      const button = page.locator('#' + id);
      await expect(button).toBeVisible();
      if (phase === 'after') {
        const icon = button.locator('.ww-icon').first();
        const data = await icon.evaluate(el => {
          const r = el.getBoundingClientRect(), p = el.parentElement.getBoundingClientRect(), s = getComputedStyle(el);
          return { key: el.dataset.wwIcon, width: r.width, height: r.height, mask: s.maskImage || s.webkitMaskImage,
            inside: r.left >= p.left && r.right <= p.right && r.top >= p.top && r.bottom <= p.bottom };
        });
        expect(data.key).toMatch(/^WUI002_/);
        expect(data.width).toBe(17); expect(data.height).toBe(17); expect(data.inside).toBe(true);
        expect(data.mask).toContain('/wui-002/'); evidence.push({ id, ...data });
      }
    }
    expect(await page.locator('#wwZoomXOutBtn').evaluate(el => Number(getComputedStyle(el).opacity))).toBeLessThan(0.6);
    await page.locator('#wwZoomXInBtn').hover();
    await page.locator('#wwZoomXInBtn').focus();
    await page.keyboard.press('Tab');
    await page.keyboard.press('Shift+Tab');
    await expect(page.locator('#wwZoomXInBtn')).toBeFocused();
    expect(await page.locator('#wwZoomXInBtn').evaluate(el => getComputedStyle(el).outlineStyle)).toBe('solid');
    await page.mouse.move(2, 2);
    // CDP screenshot clips use device-independent pixels before native tab zoom.
    // Playwright locator screenshots otherwise crop the wrong region at 125%.
    const box = await toolbar.boundingBox();
    const cdp = await context.newCDPSession(page);
    const screenshot = await cdp.send('Page.captureScreenshot', { format: 'png',
      clip: { x: box.x * zoom, y: box.y * zoom, width: box.width * zoom, height: box.height * zoom, scale: 1 } });
    fs.writeFileSync(info.outputPath(`${phase}-toolbar-${theme}-${zoom * 100}.png`), Buffer.from(screenshot.data, 'base64'));
    if (phase === 'after') {
      const header = page.locator('#viewWaveform .ww-panel-header').first();
      const group = header.locator('.ww-pane-unit-mode');
      await expect(group).toBeVisible();
      await expect(page.locator('#viewWaveform .ww-pane-unit-mode:visible')).toHaveCount(1);
      await expect(page.locator('#wwToolbar #wwUnitModeToggle')).toHaveCount(0);
      const bounds = await header.boundingBox();
      for (const button of await header.locator('[data-pane-unit-mode], [data-pane-y]').all()) {
        await expect(button).toBeInViewport({ratio:1});
        const rect=await button.boundingBox();
        expect(rect.x+rect.width).toBeLessThanOrEqual(bounds.x+bounds.width+0.5);
        await button.click({trial:true});
      }
      const paneShot = await cdp.send('Page.captureScreenshot',{format:'png',clip:{
        x:bounds.x*zoom,y:bounds.y*zoom,width:bounds.width*zoom,height:bounds.height*zoom,scale:1}});
      fs.writeFileSync(info.outputPath(`voltage-header-${theme}-${zoom*100}.png`),Buffer.from(paneShot.data,'base64'));
    }
    const fullShot=await cdp.send('Page.captureScreenshot',{format:'png'});
    fs.writeFileSync(info.outputPath(`integrated-${layout.toLowerCase()}-${theme}-${zoom*100}.png`),Buffer.from(fullShot.data,'base64'));
    await cdp.detach();
    // Exact original vector geometry and the mockup's stroke contract are retained in one asset each.
    if (phase === 'after') {
      const provenance = JSON.parse(fs.readFileSync(path.join(__dirname,'../frontend/assets/icons/waveform/wui-002/provenance.json'),'utf8'));
      for (const item of provenance.icons) {
        const response = await page.request.get('/' + item.asset);
        expect(response.status()).toBe(200);
        const svg = await response.text();
        expect(svg).toContain('viewBox="0 0 24 24"');
        expect(svg).toContain('stroke-width="1.8"');
        expect(svg).toContain('stroke-linecap="round"');
        expect(svg).toContain('stroke-linejoin="round"');
        const geometry = svg.slice(svg.indexOf('>') + 1, svg.lastIndexOf('</svg>')).trim();
        expect(crypto.createHash('sha256').update(geometry).digest('hex')).toBe(item.geometry_sha256);
      }
    }
    // Owner decision: preserve the established artwork for mockup gaps.
    for (const [id, key] of Object.entries({ timeModeElapsedBtn: 'TIME_ELAPSED', timeModeAbsoluteBtn: 'TIME_ABSOLUTE',
      wwAnnotationListBtn: 'ANNOTATIONS',
      layoutModeGroupedBtn: 'VIEW_GROUPED', layoutModeSeparateBtn: 'VIEW_SEPARATE', layoutModeCustomBtn: 'VIEW_CUSTOM' })) {
      await expect(page.locator('#' + id + ' [data-ww-icon]')).toHaveAttribute('data-ww-icon', key);
    }
    if (phase === 'after') {
      await expect(page.locator('#wwUnitEngineeringBtn')).toHaveText('ENG');
      expect((await page.locator('#wwUnitPerUnitBtn').innerText()).trim()).toBe('PU');
      await expect(page.locator('#wwUnitModeWarning')).toBeHidden();
    }
    expect(errors).toEqual([]);
    await expect(page.locator('#wwDetectEventBtn, #timeModeRelativeBtn').first()).toBeHidden();
    await expect(page.locator('#viewWaveform [data-pane-y]')).toHaveCount(3);
    await info.attach('icon-evidence.json', { body: JSON.stringify({ phase, layout, theme, browserZoom: zoom, zoomMetrics,
      receivedHtmlSha256: crypto.createHash('sha256').update(body).digest('hex'), icons: evidence }, null, 2), contentType: 'application/json' });
  });
}
