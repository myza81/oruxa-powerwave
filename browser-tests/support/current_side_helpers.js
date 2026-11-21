// Overcurrent (D5A-OC-001) pre-selects the Recording current basis from the side the recording declares, so
// the shared `phasor_smoke_three_phase` fixture (which declares PRIMARY) now needs a CT before it shows a
// number. Specs that are about something else (layout, chart, playback, related waveforms) leave the side
// undeclared instead, which keeps the explicit engineer-selected basis they were written for.
async function leaveCurrentSideUndeclared(page) {
  await page.route("**/protection-instrument-context?*", async (route) => {
    try {
      const response = await route.fetch();
      const body = await response.json();
      if (body.current) Object.assign(body.current, { declared_basis: null, side_status: "unknown", side: "unknown" });
      for (const channel of body.channels || []) if (channel.quantity === "current") channel.declared_side = "unknown";
      await route.fulfill({ response, json: body });
    } catch (error) {
      // The page was closed while the report was in flight (end of a test): nothing left to answer.
    }
  });
}

module.exports = { leaveCurrentSideUndeclared };
