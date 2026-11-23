// Recorded Overcurrent (D5A-2B2C-1A, DEC-216) takes the Primary/Secondary side of its current channel from Recording
// Details (Level 1: the recording, Level 2: the Current Measurement Group); the page has no basis input. The shared
// `phasor_smoke_three_phase` fixture declares PRIMARY, so a recorded number would need a CT. Specs that are about
// something else (layout, chart, playback, related waveforms) set the uploaded recording's side to SECONDARY through the
// same API Recording Details saves through -- as an engineer would -- which needs no CT (`setRecordedSide`).

const BACKEND = `http://127.0.0.1:${process.env.PW_BACKEND_PORT || "8000"}`;

// Level 1 (the recording) through the Recording Details API. `side: null` returns to the recording's own evidence.
async function setRecordedSide(page, { workspaceId, sourceId }, side, note = null) {
  const r = await page.request.put(
    `${BACKEND}/api/v1/workspaces/${encodeURIComponent(workspaceId)}/sources/${encodeURIComponent(sourceId)}/measurement-side`,
    { data: { side, note } },
  );
  if (!r.ok()) throw new Error(`PUT measurement-side failed (${r.status()}): ${await r.text()}`);
}

// Level 2 (one Measurement Group) through the Recording Details API.
async function setGroupSide(page, { workspaceId, sourceId }, groupId, side) {
  const r = await page.request.put(
    `${BACKEND}/api/v1/workspaces/${encodeURIComponent(workspaceId)}/sources/${encodeURIComponent(sourceId)}/measurement-groups/${encodeURIComponent(groupId)}/measurement-side`,
    { data: { side } },
  );
  if (!r.ok()) throw new Error(`PUT group measurement-side failed (${r.status()}): ${await r.text()}`);
}

module.exports = { setRecordedSide, setGroupSide };
