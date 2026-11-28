// D5A: the recorded Impedance Locus / Distance Protection analyses take their CT/VT only from the Recording
// Details Measurement Groups (never a panel-local input). A fixture whose channels declare a measurement side
// (phasor_smoke_three_phase declares primary) therefore needs those groups configured before a recorded
// calculation that has to convert between bases can run. This does through the real API what Recording Details
// -> VT/CT -> Edit -> Save does.

const BACKEND_URL = `http://127.0.0.1:${process.env.PW_BACKEND_PORT || "8000"}`;

async function configureRecordedCtVt(page, workspaceId, sourceId, { vtPrimaryV = 132000, vtSecondaryV = 110, ctPrimaryA = 1200, ctSecondaryA = 1 } = {}) {
  const base = `${BACKEND_URL}/api/v1/workspaces/${encodeURIComponent(workspaceId)}/sources/${encodeURIComponent(sourceId)}/measurement-groups`;
  const list = async () => (await page.request.get(base)).json();
  let groups = await list();
  if (!groups.some((g) => g.kind === "voltage") || !groups.some((g) => g.kind === "current")) {
    await page.request.post(`${base}/suggest`, { data: {} });
    groups = await list();
  }
  for (const group of groups.filter((g) => g.kind === "voltage")) {
    const r = await page.request.put(`${base}/${group.id}/voltage-config`, { data: { vt_primary_v: vtPrimaryV, vt_secondary_v: vtSecondaryV } });
    if (!r.ok()) throw new Error(`PUT voltage-config failed (${r.status()}): ${await r.text()}`);
  }
  for (const group of groups.filter((g) => g.kind === "current")) {
    const r = await page.request.put(`${base}/${group.id}/current-config`, { data: { update_ct_only: true, ct_primary_a: ctPrimaryA, ct_secondary_a: ctSecondaryA } });
    if (!r.ok()) throw new Error(`PUT current-config failed (${r.status()}): ${await r.text()}`);
  }
}

module.exports = { configureRecordedCtVt };
