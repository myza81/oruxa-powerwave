// WUI-002: visual grouping must retain the existing Waveform control contracts.
const { test, expect } = require('./support/test');
const { uploadRecord } = require('./support/event_reconstruction_helpers');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const controls = [
  'timeModeElapsedBtn', 'timeModeAbsoluteBtn', 'wwUnitEngineeringBtn', 'wwUnitPerUnitBtn',
  'wwZoomXOutBtn', 'wwZoomXInBtn', 'wwAutoscaleXBtn', 'wwCursorModeBtn', 'wwT0Btn',
  'wwAnnotateBtn', 'wwAnnotationListBtn', 'layoutModeGroupedBtn', 'layoutModeSeparateBtn',
  'layoutModeCustomBtn', 'wwSplitViewBtn', 'clearWorkspaceBtn',
];
const sha = text => crypto.createHash('sha256').update(text.replace(/^\uFEFF/, '')).digest('hex');

async function setup(page) {
  const response = await page.goto('/index.html');
  expect(sha(await response.text())).toBe(sha(fs.readFileSync(path.join(__dirname, '../frontend/index.html'), 'utf8')));
  await uploadRecord(page, {
    station: 'WUI_TOOLBAR', startClock: '10:00:00.000000', durationS: 4,
    channels: [
      { name: 'KPDN1 VR', unit: 'V', phase: 'R', amplitude: 11000, frequencyHz: 50 },
      { name: 'KPDN1 IB', unit: 'A', phase: 'B', amplitude: 250, frequencyHz: 50 },
    ],
  });
  const sourceId = await page.locator('#wwRdRecordingList .ww-rd-recording-item').first().getAttribute('data-source-id');
  await page.locator(`#wwRdRecordingList [data-source-id="${sourceId}"]`).click();
  await page.locator('#mainNavWaveformBtn').click();
  for (const name of ['KPDN1 VR', 'KPDN1 IB']) {
    await page.locator(`#channelGroups tr.channel-row--toggle[data-source-id="${sourceId}"][data-channel-name="${name}"]`).click();
  }
  await expect(page.locator('#viewWaveform .ww-panel')).toHaveCount(2);
  await page.waitForFunction(() => ww.panels.every(p => p.plotlyReady && p.chartEl.data?.[0]?.y.length));
  return sourceId;
}

async function createNote(page) {
  await page.locator('#wwAnnotateBtn').click();
  await page.locator('#wwAnnotateMenu [data-annotation-type="text_note"]').click();
  await page.locator('#viewWaveform .ww-chart').first().click({ position: { x: 260, y: 100 } });
  const text = page.locator('.ww-annotation-textarea');
  await expect(text).toBeVisible();
  await text.fill('Review voltage and current');
  await page.locator('#wwToolbar .ww-toolbar-caption').first().click(); // normal blur-save, no new action
  await expect(page.locator('#wwAnnotationCountBadge')).toHaveText('1');
}

async function toolbarGeometry(page) {
  const toolbar = page.locator('#wwToolbar');
  const box = await toolbar.boundingBox();
  expect(box.height, 'compact toolbar height').toBeLessThanOrEqual(82);
  const rectangles = [];
  for (const button of await toolbar.locator('button:visible').all()) {
    await expect(button).toBeInViewport({ ratio: 1 });
    const rect = await button.boundingBox();
    expect(rect.x).toBeGreaterThanOrEqual(box.x);
    expect(rect.x + rect.width).toBeLessThanOrEqual(box.x + box.width + 0.5);
    expect(rect.y + rect.height).toBeLessThanOrEqual(box.y + box.height + 0.5);
    if (await button.isEnabled()) await button.click({ trial: true });
    const id = await button.getAttribute('id');
    for (const prior of rectangles) {
      const x = Math.min(rect.x + rect.width, prior.x + prior.width) - Math.max(rect.x, prior.x);
      const y = Math.min(rect.y + rect.height, prior.y + prior.height) - Math.max(rect.y, prior.y);
      expect(x > 0.5 && y > 0.5, `${id} overlaps ${prior.id}`).toBe(false);
    }
    rectangles.push({ id, ...rect });
  }
  return { toolbar: box, buttons: rectangles };
}

for (const viewport of [{ width: 1366, height: 768 }, { width: 1280, height: 800 }]) {
  for (const theme of ['light', 'dark']) {
    test(`${theme} toolbar fits ${viewport.width}x${viewport.height}, with Custom, cursors and a note`, async ({ page }, info) => {
      await page.setViewportSize(viewport);
      await setup(page);
      await page.evaluate(t => PowerwaveTheme.setTheme(t), theme);
      await page.locator('#layoutModeCustomBtn').click();
      await page.locator('#wwCursorModeBtn').click();
      await expect(page.locator('#wwT0Btn')).toBeEnabled();
      await page.locator('#wwT0Btn').click();
      await expect(page.locator('#wwT0Btn')).toHaveAttribute('aria-pressed', 'true');
      await createNote(page);
      for (const id of controls.concat('editChannelGroupsBtn')) await expect(page.locator('#' + id)).toBeVisible();
      await expect(page.locator('#wwToolbar [data-toolbar-group]')).toHaveCount(6);
      const geometry = await toolbarGeometry(page);
      await info.attach('toolbar-geometry.json', { body: JSON.stringify(geometry, null, 2), contentType: 'application/json' });
      for (const id of ['timeModeRelativeBtn', 'wwDetectEventBtn', 'wwDetectEventSep']) await expect(page.locator('#' + id)).toBeHidden();
      await expect(page.locator('#wwZoomYInBtn, #wwZoomYOutBtn, #wwAutoscaleYBtn')).toHaveCount(0);
      await expect(page.locator('#viewWaveform [data-pane-y]')).toHaveCount(6);
      await page.screenshot({ path: info.outputPath(`toolbar-${theme}-${viewport.width}x${viewport.height}.png`), fullPage: true });
      // Native Tab order and visible keyboard focus remain intact.
      await page.locator('#timeModeElapsedBtn').focus();
      await page.keyboard.press('Space');
      expect(await page.evaluate(() => ww.timeMode)).toBe('elapsed');
      await page.keyboard.press('Tab');
      await expect(page.locator('#timeModeAbsoluteBtn')).toBeFocused();
      expect(await page.locator('#timeModeAbsoluteBtn').evaluate(el => getComputedStyle(el).outlineStyle)).toBe('solid');
      await page.keyboard.press('Space');
      await expect(page.locator('#timeModeAbsoluteBtn')).toHaveAttribute('aria-pressed', 'true');
      const hoverButton = page.locator('#wwAnnotationListBtn');
      const normalBackground = await hoverButton.evaluate(el => getComputedStyle(el).backgroundColor);
      await hoverButton.hover();
      await expect.poll(() => hoverButton.evaluate(el => getComputedStyle(el).backgroundColor)).not.toBe(normalBackground);
    });
  }
}

test('empty workspace keeps direct controls and existing disabled states', async ({ page }) => {
  await page.goto('/index.html');
  await page.locator('#mainNavWaveformBtn').click();
  for (const id of controls.filter(id=>!['wwUnitEngineeringBtn','wwUnitPerUnitBtn'].includes(id))) await expect(page.locator('#' + id)).toBeVisible();
  await expect(page.locator('.ww-pane-unit-mode:visible')).toHaveCount(0);
  for (const id of ['wwZoomXOutBtn', 'wwZoomXInBtn', 'wwAutoscaleXBtn', 'wwCursorModeBtn', 'wwT0Btn', 'clearWorkspaceBtn']) {
    await expect(page.locator('#' + id)).toBeDisabled();
  }
  await expect(page.locator('#editChannelGroupsBtn')).toBeHidden();
  await expect(page.locator('#wwYAxisReadout')).toHaveCount(0);
  expect(await page.evaluate(()=>wwActivePanel())).toBeUndefined();
  await toolbarGeometry(page);
});

test('existing time, X, cursor, t0, annotation, layout, Split and Clear actions remain direct', async ({ page }) => {
  const sourceId = await setup(page);
  const group = await page.evaluate(() => wwActiveTimeGroupId());
  const currentRange = () => page.evaluate(g => ww.timeGroupViewports.get(g), group);
  const beforeTime = await currentRange();
  await page.locator('#timeModeElapsedBtn').click();
  expect(await page.evaluate(() => ww.timeMode)).toBe('elapsed');
  await page.locator('#timeModeAbsoluteBtn').click();
  expect(await page.evaluate(() => ww.timeMode)).toBe('absolute');
  expect(await currentRange()).toEqual(beforeTime);
  await page.locator('#wwZoomXInBtn').click();
  await expect.poll(async () => { const r = await currentRange(); return r.end - r.start; }).toBeCloseTo((beforeTime.end - beforeTime.start) * 0.8, 5);
  await page.locator('#wwZoomXOutBtn').click();
  await expect.poll(currentRange).toEqual(beforeTime);
  await page.locator('#wwZoomXInBtn').click();
  await page.locator('#wwAutoscaleXBtn').click();
  await expect.poll(currentRange).toEqual(beforeTime);
  await page.locator('#wwCursorModeBtn').click();
  await expect(page.locator('#wwCursorModeBtn')).toHaveAttribute('aria-pressed', 'true');
  await page.locator('#wwT0Btn').click();
  await expect(page.locator('#wwT0Btn')).toHaveAttribute('aria-pressed', 'true');
  await page.locator('#wwT0Btn').click();
  await expect(page.locator('#wwT0Btn')).toHaveAttribute('aria-pressed', 'false');
  for (const type of ['text_note', 'callout', 'peak_max', 'peak_min']) {
    await page.locator('#wwAnnotateBtn').click();
    await expect(page.locator('#wwAnnotateMenu [role="menuitem"]')).toHaveCount(4);
    await page.locator(`#wwAnnotateMenu [data-annotation-type="${type}"]`).click();
    expect(await page.evaluate(() => ww.annotationPlacementType)).toBe(type);
    await page.keyboard.press('Escape');
  }
  await createNote(page);
  await page.locator('#wwAnnotationListBtn').click();
  await expect(page.locator('#wwAnnotationDrawer')).toHaveClass(/ww-annotation-drawer--open/);
  await page.locator('#wwAnnotationDrawerCloseBtn').click();
  for (const mode of ['Separate', 'Grouped', 'Custom']) {
    await page.locator(`#layoutMode${mode}Btn`).click();
    expect(await page.evaluate(() => ww.layoutMode)).toBe(mode.toLowerCase());
  }
  await page.locator('#editChannelGroupsBtn').click();
  await expect(page.locator('#groupEditorOverlay')).toBeVisible();
  await page.locator('#groupEditorCancelBtn').click();
  await page.locator('#wwSplitViewBtn').click();
  await expect(page.locator('#wwSplitTablePane')).toBeVisible();
  await page.locator('#wwSplitViewBtn').click();
  await expect(page.locator('#wwSplitTablePane')).toBeHidden();
  await page.locator('#clearWorkspaceBtn').click();
  await expect(page.locator('#viewWaveform .ww-panel')).toHaveCount(0);
  // Existing Clear semantics retain free workspace Text Notes.
  expect(await page.evaluate(() => ww.annotations.size)).toBe(1);
  await expect(page.locator(`#wwRdRecordingList [data-source-id="${sourceId}"]`)).toHaveCount(1);
});

test('PU warnings and the existing Recording Details correction entry remain visible', async ({ page }, info) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await setup(page);
  await page.locator('#layoutModeCustomBtn').click();
  await page.locator('#wwUnitPerUnitBtn').click();
  await expect(page.locator('#wwUnitPerUnitBtn')).toHaveAttribute('aria-pressed', 'true');
  await expect(page.locator('#wwUnitModeWarning')).toBeVisible();
  await expect(page.locator('#wwPuConfigBanner')).toBeVisible();
  await toolbarGeometry(page);
  await page.screenshot({ path: info.outputPath('toolbar-pu-warning.png'), fullPage: true });
  await page.locator('#wwPuConfigBannerBtn').click();
  await expect(page.locator('#pageRecordingDetails')).toBeVisible();
  await page.locator('#mainNavWaveformBtn').click();
  await page.locator('#wwUnitEngineeringBtn').click();
  await expect(page.locator('#wwUnitEngineeringBtn')).toHaveAttribute('aria-pressed', 'true');
  await expect(page.locator('#wwUnitModeWarning')).toBeHidden();
  await expect(page.locator('#wwPuConfigBanner')).toBeHidden();
});

test('Waveform-specific styles leave Event Reconstruction button geometry unchanged', async ({ page }) => {
  await page.goto('/index.html');
  await page.locator('#mainNavEventReconstructionBtn').click();
  const button = page.locator('#wwErZoomInBtn');
  await expect(button).toBeVisible();
  expect((await button.boundingBox()).width).toBe(30);
  expect((await button.boundingBox()).height).toBe(30);
  await expect(page.locator('#wwErToolbar [data-toolbar-group]')).toHaveCount(0);
});
