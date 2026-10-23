const { test, expect } = require("./support/test");
const { clockFixture } = require("./support/ben5k_clock");

test("retained calculated result rejects raw reset and a new page session", async ({ page }) => {
  await page.goto("/index.html");
  const result = await page.evaluate(async encoded => {
    const base = apiBaseUrl() + "/api/v1/workspaces/" + currentWorkspaceId();
    const ids = [];
    for (let i = 0; i < 2; i++) {
      const form = new FormData();
      form.append("ben_file", new Blob([Uint8Array.from(atob(encoded), c => c.charCodeAt(0))]), "clock.ben");
      const response = await fetch(base + "/sources", { method: "POST", body: form });
      if (!response.ok) throw new Error(await response.text());
      ids.push((await response.json()).source_id);
    }
    const interpret = (id, offset) => fetch(base + "/sources/" + id + "/time-reference", {
      method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ offset_minutes: offset })
    });
    for (const id of ids) await interpret(id, 480);
    const response = await fetch(base + "/calculated-channels", { method: "POST",
      headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: "sum", operation: "addition",
        inputs: ids.map(id => ({ kind: "source", source_id: id, channel_name: "CLOCK VR" })) }) });
    if (!response.ok) throw new Error(await response.text());
    const channel = await response.json();
    const waveform = () => fetch(base + "/calculated-channels/" + channel.id + "/waveform");
    const original = await (await waveform()).json();
    await interpret(ids[1], null);
    const denied = await waveform();
    const definitions = await (await fetch(base + "/calculated-channels")).json();
    await interpret(ids[1], 480);
    const restored = await (await waveform()).json();
    return { base, ids, id: channel.id, denied: denied.status, definitions, same: JSON.stringify(original.values) === JSON.stringify(restored.values) };
  }, clockFixture().toString("base64"));
  expect(result.denied).toBe(400);
  expect(result.definitions[0].timing_status).toBe("incompatible");
  expect(result.same).toBe(true);
  // Exercise the real interpretation control with an already plotted calculated result.
  await page.evaluate(async () => { await refreshAllSourceViews(); await wwFetchCalculatedChannels(); });
  await page.locator(`#recordingsTableBody tr[data-source-id="${result.ids[0]}"]`).click();
  await page.evaluate(async id => { await wwAddSelectedChannels([wwCalculatedChannelMeta(ww.calculatedChannels.get(id))]); }, result.id);
  const plottedCount = () => page.evaluate(id => Array.from(ww.displayed.values()).find(e => e.channel.sourceId === id)?.channel.values.length || 0, result.id);
  await expect.poll(plottedCount).toBeGreaterThan(0);
  await page.locator("#mainNavRecordingsBtn").click();
  await page.locator(`#recordingsTableBody tr[data-source-id="${result.ids[1]}"] [data-action="details"]`).click();
  const select = page.locator(`.recording-time-reference[data-source-id="${result.ids[1]}"]`);
  await select.selectOption("raw"); await expect(select).toBeEnabled();
  await expect.poll(plottedCount).toBe(0);
  await expect.poll(() => page.evaluate(id => ww.calculatedChannels.get(id).timing_status, result.id)).toBe("incompatible");
  await expect(page.locator("#wwCcListBody")).toContainText("do not have compatible sample times");
  await select.selectOption("480"); await expect(select).toBeEnabled();
  await expect.poll(plottedCount).toBeGreaterThan(0);
  await page.reload();
  expect(await page.evaluate(async r => (await fetch(r.base + "/calculated-channels/" + r.id + "/waveform")).status, result)).toBe(400);
});

async function seed(page) {
  await page.goto("/index.html");
  await page.evaluate(() => {
    const context = id => ({ id: "ctx-" + id, members: [{ channel_ref: { kind: "source", source_id: id, channel_name: "V" } }] });
    for (const [state, id] of [[wwImpedanceState, "affected"], [wwSequenceState, "affected"], [wwOvercurrentState, "other"]]) {
      state.inputSource = WW_ANALYSIS_INPUT_SOURCE_RECORDING;
      state.contexts = [context(id)]; state.selectedContextId = "ctx-" + id;
      state.anchorDisplaySourceId = null; state.analysisTime = 0;
      state.latestResult = { marker: "old" };
    }
    wwImpedanceState.locusPoints = [{ x: 1 }]; wwImpedanceState.locusSignature = "cached";
    wwSequenceState.frozenVoltageScale = 42;
  });
}

test("timing invalidation clears Impedance and Sequence but retains unrelated results", async ({ page }) => {
  await seed(page);
  const r = await page.evaluate(() => {
    const old = wwOvercurrentState.latestResult, generation = wwOvercurrentState.requestGeneration;
    const signature = wwImpedanceLocusSignature(), epoch = ww.epoch;
    wwInvalidateAnalysisTiming("affected");
    return { impedance: wwImpedanceState.latestResult, locus: wwImpedanceState.locusPoints,
      sequence: wwSequenceState.latestResult, scale: wwSequenceState.frozenVoltageScale,
      signatureChanged: signature !== wwImpedanceLocusSignature(), epochStable: epoch === ww.epoch,
      unaffected: old === wwOvercurrentState.latestResult && generation === wwOvercurrentState.requestGeneration };
  });
  expect(r).toEqual({ impedance: null, locus: [], sequence: null, scale: null, signatureChanged: true, epochStable: true, unaffected: true });
});

for (const analyser of ["Impedance", "Sequence"]) {
  test(analyser + " ignores an in-flight result completed after timing invalidation", async ({ page }) => {
    await seed(page);
    const r = await page.evaluate(async analyser => {
      // Hold the actual request function at its asynchronous transport boundary.
      const transports = [];
      const transport = () => new Promise((resolve, reject) => { transports.push({ resolve, reject }); });
      const original = analyser === "Impedance" ? wwImpedanceFetchAnalysis : wwSequenceFetchAnalysis;
      if (analyser === "Impedance") wwImpedanceFetchAnalysis = transport;
      else wwSequenceFetchAnalysis = transport;
      const pending = analyser === "Impedance" ? wwImpedanceRequestAnalysis() : wwSequenceRequestAnalysis();
      wwInvalidateAnalysisTiming("affected");
      // Start a real replacement transport before completing the obsolete one.
      const replacement = analyser === "Impedance" ? wwImpedanceRequestAnalysis() : wwSequenceRequestAnalysis();
      transports[0].resolve({ marker: "obsolete response" });
      await pending;
      const r = {
        result: (analyser === "Impedance" ? wwImpedanceState : wwSequenceState).latestResult,
        fetchedTime: analyser === "Impedance" ? wwImpedancePlaybackFetchedTime : wwSequencePlaybackFetchedTime,
        newerBusy: analyser === "Impedance" ? wwImpedancePlaybackFetchInFlight : wwSequencePlaybackFetchInFlight,
      };
      transports[1].reject(new Error("Replacement transport test completed"));
      await replacement;
      if (analyser === "Impedance") wwImpedanceFetchAnalysis = original;
      else wwSequenceFetchAnalysis = original;
      return r;
    }, analyser);
    expect(r).toEqual({ result: null, fetchedTime: null, newerBusy: true });
  });
}

test("transitive catalogue timing and related waveform caches follow every input", async ({ page }) => {
  await seed(page);
  const r = await page.evaluate(() => {
    const raw = id => ({ kind: "source", source_id: id, channel_name: "V" });
    ww.calculatedChannels.set("calc-parent", { id: "calc-parent", inputs: [raw("reference"), raw("affected")] });
    ww.calculatedChannels.set("calc-child", { id: "calc-child", inputs: [{ kind: "calculated", calculated_channel_id: "calc-parent" }] });
    const before = wwDisplayTimingFingerprint("calc-child");
    wwAnalysisRelatedWaveformsState.roles = [{ channelRef: { kind: "calculated", calculated_channel_id: "calc-child" } }];
    wwAnalysisRelatedWaveformsState.channelCache.set("old", { values: [1] });
    const generation = wwAnalysisRelatedWaveformsState.requestGeneration;
    wwInvalidateAnalysisTiming("affected");
    return { changed: before !== wwDisplayTimingFingerprint("calc-child"), roots: wwTimingSourcesForDisplay("calc-child").sort(),
      empty: wwAnalysisRelatedWaveformsState.channelCache.size === 0,
      guarded: wwAnalysisRelatedWaveformsState.requestGeneration > generation };
  });
  expect(r).toEqual({ changed: true, roots: ["affected", "reference"], empty: true, guarded: true });
});


test("shared Waveform and reconstruction transport rejects old timing even without abort", async ({ page }) => {
  await seed(page);
  const result = await page.evaluate(async () => {
    const originalFetch = window.fetch;
    let release;
    window.fetch = () => new Promise(resolve => { release = resolve; });
    const pending = wwFetchWaveformRange({ requestState: {}, sourceId: "affected", channelName: "V", isCalculated: false,
      nativeStart: 0, nativeEnd: 1, pointBudget: 100, unitMode: "engineering", timeOffsetS: 0 });
    wwInvalidateAnalysisTiming("affected");
    release(new Response(JSON.stringify({ time: [0], values: [99] }), { status: 200 }));
    const result = await pending;
    window.fetch = originalFetch;
    return result;
  });
  expect(result).toEqual({ superseded: true });
});


test("obsolete Impedance locus response cannot refill its invalidated cache", async ({ page }) => {
  await seed(page);
  const result = await page.evaluate(async () => {
    const oldBounds = wwDeriveTimeGroupBounds, oldFetch = wwImpedanceFetchLocus;
    wwDeriveTimeGroupBounds = () => ({ start: 0, end: 1 });
    wwImpedanceState.activeTimeGroupId = "test-group";
    let release;
    wwImpedanceFetchLocus = () => new Promise(resolve => { release = resolve; });
    const pending = wwImpedanceMaybeFetchLocus();
    wwInvalidateAnalysisTiming("affected");
    release({ points: [{ r: 999, x: 999 }] });
    await pending;
    wwDeriveTimeGroupBounds = oldBounds; wwImpedanceFetchLocus = oldFetch;
    return { points: wwImpedanceState.locusPoints, signature: wwImpedanceState.locusSignature };
  });
  expect(result).toEqual({ points: [], signature: null });
});


test("reconstruction timing invalidates only affected per-unit resolutions", async ({ page }) => {
  await seed(page);
  const r = await page.evaluate(async () => {
    const pu = wwErState.perUnit, oldFetch = wwErFetchPerUnitResolution;
    pu.requested["src|other|V"] = pu.generation;
    const stable = pu.resolutions["src|other|V"] = { status: "configured", marker: "keep" };
    let release, calls = 0;
    wwErFetchPerUnitResolution = () => { calls++; return new Promise(resolve => { release = resolve; }); };
    const channels = [{ kind: "analog", sourceId: "affected", channelName: "V" }, { kind: "analog", sourceId: "other", channelName: "V" }];
    wwErEnsurePerUnitResolutions(channels);
    wwInvalidateAnalysisTiming("affected");
    wwErEnsurePerUnitResolutions([channels[1]]);
    release({ status: "configured", marker: "obsolete" });
    await Promise.resolve();
    wwErFetchPerUnitResolution = oldFetch;
    return { calls, stable: pu.resolutions["src|other|V"] === stable, staleAbsent: pu.resolutions["src|affected|V"] === undefined };
  });
  expect(r).toEqual({ calls: 1, stable: true, staleAbsent: true });
});


test("hidden recording results invalidate while independent manual results survive", async ({ page }) => {
  await seed(page);
  const result = await page.evaluate(() => {
    wwImpedanceState.inputSource = WW_ANALYSIS_INPUT_SOURCE_MANUAL;
    const manual = wwImpedanceState.manual.latestResult = { marker: "manual calculation" };
    const generation = wwImpedanceState.manualRequestGeneration;
    wwInvalidateAnalysisTiming("affected");
    return { recording: wwImpedanceState.latestResult, locus: wwImpedanceState.locusPoints,
      manualStable: manual === wwImpedanceState.manual.latestResult && generation === wwImpedanceState.manualRequestGeneration };
  });
  expect(result).toEqual({ recording: null, locus: [], manualStable: true });
});


test("calculated preview clears affected traces and keeps unrelated plotted arrays", async ({ page }) => {
  await seed(page);
  const result = await page.evaluate(async () => {
    for (const [id, sid] of [["calc-touched", "affected"], ["calc-kept", "other"]]) {
      ww.calculatedChannels.set(id, { id, inputs: [{ kind: "source", source_id: sid, channel_name: "V" }] });
    }
    const chartEl = document.createElement("div"); document.body.appendChild(chartEl);
    await Plotly.newPlot(chartEl, [{ uid: "calc-touched", x: [0], y: [99] }, { uid: "calc-kept", x: [0], y: [42] }]);
    wwCcPreview.panelsByType.set("test", { ready: true, chartEl });
    wwInvalidateAnalysisTiming("affected");
    await new Promise(resolve => requestAnimationFrame(resolve));
    const result = chartEl.data.map(trace => ({ id: trace.uid, values: trace.y }));
    wwCcPreview.panelsByType.delete("test"); Plotly.purge(chartEl); chartEl.remove();
    return result;
  });
  expect(result).toEqual([{ id: "calc-touched", values: [] }, { id: "calc-kept", values: [42] }]);
});


test("Compliance rejects late readiness and clears calculated traces after a dependency reset", async ({ page }) => {
  await seed(page);
  const result = await page.evaluate(async () => {
    ww.calculatedChannels.set("calc-compliance", { id: "calc-compliance", reference_source_id: "reference",
      inputs: ["reference", "affected"].map(id => ({ kind: "source", source_id: id, channel_name: "V" })) });
    const state = wwComplianceState;
    state.groups = [{ id: "measurement", source_id: "reference" }]; state.selectedGroupId = "measurement";
    state.readiness = { references: [{ members: [{ calculated_channel_id: "calc-compliance" }] }] };
    state.traces = { traces: [{ x: [0], y: [99] }] };
    const alignment = state.alignment = { measurement_event_origin_s: .125 };
    const originalFetch = wwComplianceFetchJson;
    let release;
    wwComplianceFetchJson = () => new Promise(resolve => { release = resolve; });
    wwComplianceRefreshReadiness();
    wwInvalidateAnalysisTiming("affected");
    release({ references: [], marker: "obsolete" });
    await Promise.resolve();
    wwComplianceFetchJson = originalFetch;
    return { readiness: state.readiness, traces: state.traces, alignmentStable: state.alignment === alignment };
  });
  expect(result).toEqual({ readiness: null, traces: null, alignmentStable: true });
});


test("obsolete transport releases its busy marker after the selected context moves away", async ({ page }) => {
  await seed(page);
  const result = await page.evaluate(async () => {
    const original = wwImpedanceFetchAnalysis;
    let release;
    wwImpedanceFetchAnalysis = () => new Promise(resolve => { release = resolve; });
    const pending = wwImpedanceRequestAnalysis();
    wwImpedanceState.contexts = [{ id: "other-context", members: [{ channel_ref: { kind: "source", source_id: "other", channel_name: "V" } }] }];
    wwImpedanceState.selectedContextId = "other-context";
    wwImpedanceState.requestGeneration += 1;
    wwImpedanceState.latestResult = null;
    wwInvalidateAnalysisTiming("affected");
    release({ marker: "obsolete" });
    await pending;
    wwImpedanceFetchAnalysis = original;
    return { result: wwImpedanceState.latestResult, busy: wwImpedancePlaybackFetchInFlight };
  });
  expect(result).toEqual({ result: null, busy: false });
});
