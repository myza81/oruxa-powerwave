// Recording Details helpers for the Per-Unit browser specs.
//
// P0 remediation (PU-MIG): the Per-Unit Settings Hub, the Measurement-Group
// drawer/modal and the Measurement Groups overlay were retired. Base
// configuration is now edited in Recording Details -> Group Details. These
// helpers drive that real UI (real backend, nothing mocked) so that the
// original engineering assertions can be kept unchanged.
const { expect } = require("@playwright/test");

// Select a recording and one of its Measurement Groups in Recording Details and
// show the Group Details tab. Items are located by source id / group id, never
// by position.
async function openRdGroupDetails(page, sourceId, groupId) {
  await page.locator("#mainNavRecordingDetailsBtn").click();
  const recording = page.locator(`#wwRdRecordingList .ww-rd-recording-item[data-source-id="${sourceId}"]`);
  await expect(recording).toBeVisible();
  await recording.click();
  const group = page.locator(`#wwRdGroupsBody .ww-rd-group-item[data-group-id="${groupId}"]`);
  await expect(group).toBeVisible();
  await group.click();
  const details = page.locator("#wwRdTabGroupDetails");
  await expect(details).toBeVisible();
  await details.click();
  await expect(page.locator("#wwRdDetailsBody")).toBeVisible();
}

// Open the voltage Base Configuration editor of a voltage group.
async function openRdVoltageEditor(page, sourceId, groupId) {
  await openRdGroupDetails(page, sourceId, groupId);
  await page.locator("#wwRdDetailsBody #wwRdVoltageEditBtn").click();
  await expect(page.locator("#wwRdDetailsBody #wwRdVoltageApplyBtn")).toBeVisible();
}

// Open the Equipment Rating editor of a current group.
async function openRdCurrentEditor(page, sourceId, groupId) {
  await openRdGroupDetails(page, sourceId, groupId);
  await page.locator("#wwRdDetailsBody #wwRdCurrentEditBtn").click();
  await expect(page.locator("#wwRdDetailsBody #wwRdCurrentApplyBtn")).toBeVisible();
}

module.exports = { openRdGroupDetails, openRdVoltageEditor, openRdCurrentEditor };
