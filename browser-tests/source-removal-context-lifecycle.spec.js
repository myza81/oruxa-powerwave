const { test, expect } = require("./support/test");
const { uploadRecord, sourceIdFor } = require("./support/event_reconstruction_helpers");

test("a context list fetched before source deletion cannot start analysis afterward", async ({ page }) => {
  const failures = [];
  page.on("response", response => {
    if (response.status() >= 400) failures.push({ method: response.request().method(), path: new URL(response.url()).pathname, status: response.status() });
  });
  await page.goto("/index.html");
  await uploadRecord(page, { station: "REMOVAL_CONTEXT", startClock: "10:00:00.000000" });
  const sid = await sourceIdFor(page, "REMOVAL_CONTEXT");
  await page.waitForLoadState("networkidle");
  // Delay one completed backend response, retaining its real context members.
  await page.evaluate(sid => {
    const publish = wwAnalysisPublishContexts;
    window.removedContextPublished = false;
    wwAnalysisPublishContexts = function(contexts) {
      if (contexts.some(context => context.members.some(member => member.channel_ref.source_id === sid))) window.removedContextPublished = true;
      return publish(contexts);
    };
    const original = window.fetch;
    let hold = true;
    window.fetch = async (url, options) => {
      const response = await original(url, options);
      if (hold && String(url).endsWith("/engineering-contexts") && (!options || !options.method || options.method === "GET")) {
        hold = false;
        return new Promise(resolve => { window.releaseContextList = () => resolve(response); });
      }
      return response;
    };
    const fetchContexts = wwAnalysisFetchContexts;
    wwAnalysisFetchContexts = function(...args) {
      window.pendingContextFetch = fetchContexts(...args);
      return window.pendingContextFetch;
    };
    wwAnalysisLoadContexts();
  }, sid);
  await page.waitForFunction(() => typeof window.releaseContextList === "function");
  await page.evaluate(sid => performRemoveSource(sid), sid);
  await page.evaluate(async () => { window.releaseContextList(); await window.pendingContextFetch; });
  await page.waitForLoadState("networkidle");
  expect(failures).toEqual([]);
  expect(await page.evaluate(() => window.removedContextPublished)).toBe(false);
});

for (const kind of ["readiness", "discovery"]) {
  test(`source deletion invalidates pending ${kind} before another request`, async ({ page }) => {
    const failures = [];
    page.on("response", response => {
      if (response.status() >= 400) failures.push({ method: response.request().method(), path: new URL(response.url()).pathname, status: response.status() });
    });
    await page.goto("/index.html");
    await uploadRecord(page, { station: "PENDING_CONTEXT", startClock: "10:00:00.000000" });
    const sid = await sourceIdFor(page, "PENDING_CONTEXT");
    await page.waitForLoadState("networkidle");
    await page.evaluate(async ({ sid, kind }) => {
      const contexts = await wwAnalysisFetchContexts(currentWorkspaceId());
      const original = window.fetch;
      let hold = true;
      window.fetch = async (url, options) => {
        const response = await original(url, options);
        if (hold && (kind === "readiness" ? String(url).includes("/input-readiness?") : String(url).endsWith("/sources"))) {
          hold = false;
          if (kind === "readiness") window.heldReadinessStatus = (await response.clone().json()).status;
          return new Promise(resolve => { window.releasePending = () => resolve(response); });
        }
        return response;
      };
      wwAnalysisContextState.attemptedSourceIds.delete(sid);
      window.pendingBootstrap = kind === "readiness"
        ? wwAnalysisFindFirstCompatibleContext(currentWorkspaceId(), contexts, "distance", ["voltage_phase_a", "current_phase_a"])
        : wwAnalysisDiscoverUncoveredSources(currentWorkspaceId(), ww.epoch, [], true);
    }, { sid, kind });
    await page.waitForFunction(() => typeof window.releasePending === "function");
    if (kind === "readiness") expect(await page.evaluate(() => window.heldReadinessStatus)).toBe("resolved");
    await page.evaluate(sid => performRemoveSource(sid), sid);
    const result = await page.evaluate(async () => { window.releasePending(); return await window.pendingBootstrap; });
    await page.waitForLoadState("networkidle");
    expect(failures).toEqual([]);
    if (kind === "readiness") expect(result).toBeNull();
  });
}
