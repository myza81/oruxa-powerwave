const { test, expect } = require("./support/test");
const { uploadRecord, sourceIdFor } = require("./support/event_reconstruction_helpers");

async function recording(page) {
  await page.goto("/index.html");
  await uploadRecord(page, { station: "LIFECYCLE", date: "16/10/2026", startClock: "18:03:14.000000", triggerClock: "18:03:14.500000" });
  return sourceIdFor(page, "LIFECYCLE");
}

test("a late metadata response cannot resurrect a removed source", async ({ page }) => {
  const sid = await recording(page);
  await page.evaluate(sid => {
    const original = window.fetch;
    ww.sourceChannelsData.delete(sid);
    window.fetch = async (url, options) => {
      const response = await original(url, options);
      if (String(url).endsWith("/sources/" + sid + "/channels")) {
        return new Promise(resolve => { window.releaseMetadata = () => resolve(response); });
      }
      return response;
    };
    window.pendingMetadata = wwEnsureSourceChannelsFetched(sid);
  }, sid);
  await page.waitForFunction(() => typeof window.releaseMetadata === "function");
  await page.evaluate(sid => performRemoveSource(sid), sid);
  const stale = await page.evaluate(async sid => {
    window.releaseMetadata(); await window.pendingMetadata;
    return ww.sourceChannelsData.has(sid) || ww.sourceChannelInventory.has(sid);
  }, sid);
  expect(stale).toBe(false);
});

test("a failed source deletion preserves current selection and reports the failure", async ({ page }) => {
  const sid = await recording(page);
  await page.evaluate(sid => { focusedSourceId = sid; }, sid);
  await page.route("**/sources/" + sid, route => route.request().method() === "DELETE"
    ? route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ detail: { message: "Deletion refused" } }) }) : route.continue());
  await page.evaluate(sid => performRemoveSource(sid), sid);
  expect(await page.evaluate(() => focusedSourceId)).toBe(sid);
  await expect(page.locator("#workspaceResetError")).toBeVisible();
  await expect(page.locator("#workspaceResetError")).toContainText("Could not remove the recording");
});


test("a previous workspace's metadata cannot repopulate the new workspace", async ({ page }) => {
  const sid = await recording(page);
  await page.evaluate(sid => {
    const original = window.fetch;
    ww.sourceChannelsData.delete(sid);
    window.fetch = async (url, options) => {
      const response = await original(url, options);
      if (String(url).endsWith("/sources/" + sid + "/channels")) {
        return new Promise(resolve => { window.releaseMetadata = () => resolve(response); });
      }
      return response;
    };
    window.pendingMetadata = wwEnsureSourceChannelsFetched(sid);
  }, sid);
  await page.waitForFunction(() => typeof window.releaseMetadata === "function");
  const previous = await page.evaluate(() => currentWorkspaceId());
  await page.evaluate(() => resetToNewWorkspace());
  expect(await page.evaluate(() => currentWorkspaceId())).not.toBe(previous);
  expect(await page.evaluate(async sid => {
    window.releaseMetadata(); await window.pendingMetadata;
    return ww.sourceChannelsData.has(sid) || ww.sourceChannelInventory.has(sid);
  }, sid)).toBe(false);
});


test("workspace deletion stops analysis requests before its response returns", async ({ page }) => {
  const sid = await recording(page);
  await page.evaluate(() => {
    const original = window.fetch;
    window.fetch = async (url, options) => {
      const response = await original(url, options);
      if (options && options.method === "DELETE" && String(url).endsWith("/workspaces/" + currentWorkspaceId())) {
        return new Promise(resolve => { window.releaseDeletion = () => resolve(response); });
      }
      return response;
    };
    window.pendingReset = resetToNewWorkspace();
  });
  await page.waitForFunction(() => typeof window.releaseDeletion === "function");
  const result = await page.evaluate(async sid => {
    try {
      await wwPhasorFetchJson(apiBaseUrl() + "/api/v1/workspaces/" + currentWorkspaceId() + "/sources/" + sid + "/channels");
      return "unexpected success";
    } catch (error) { return error.name; }
  }, sid);
  await page.evaluate(async () => { window.releaseDeletion(); await window.pendingReset; });
  expect(result).toBe("AbortError");
});


test("failed workspace deletion retains recordings and restores analysis transport", async ({ page }) => {
  const sid = await recording(page);
  const workspace = await page.evaluate(() => currentWorkspaceId());
  await page.route("**/workspaces/" + workspace, route => route.request().method() === "DELETE"
    ? route.fulfill({ status: 500, contentType: "application/json", body: "{}" }) : route.continue());
  await page.evaluate(() => resetToNewWorkspace());
  await expect(page.locator("#workspaceResetError")).toContainText("Could not clear");
  expect(await page.evaluate(() => currentWorkspaceId())).toBe(workspace);
  const result = await page.evaluate(sid => wwPhasorFetchJson(apiBaseUrl() + "/api/v1/workspaces/" + currentWorkspaceId() + "/sources/" + sid + "/channels"), sid);
  expect(result).toBeTruthy();
  expect(await page.evaluate(() => wwAnalysisFetchAbortController.signal.aborted)).toBe(false);
});


test("workspace deletion cancels a pending recording metadata request before the backend sees it", async ({ page }) => {
  const sid = await recording(page);
  const badResponses = [];
  page.on("response", response => { if (response.status() >= 400) badResponses.push(response.url()); });
  let releaseRead, markStarted, markFinished;
  const gate = new Promise(resolve => { releaseRead = resolve; });
  const started = new Promise(resolve => { markStarted = resolve; });
  const finished = new Promise(resolve => { markFinished = resolve; });
  await page.route("**/sources/" + sid + "/channels", async route => {
    markStarted(); await gate;
    try { await route.continue(); } finally { markFinished(); }
  });
  await page.evaluate(sid => {
    ww.sourceChannelsData.delete(sid);
    window.pendingMetadata = wwEnsureSourceChannelsFetched(sid);
  }, sid);
  await started;
  try { await page.evaluate(() => resetToNewWorkspace()); }
  finally { releaseRead(); }
  await finished;
  expect(await page.evaluate(() => window.pendingMetadata)).toBe(false);
  expect(badResponses).toEqual([]);
  expect(await page.evaluate(sid => ww.sourceChannelsData.has(sid), sid)).toBe(false);
});

test("a workspace read continues to honor the caller's AbortSignal", async ({ page }) => {
  await page.goto("/index.html");
  expect(await page.evaluate(async () => {
    const caller = new AbortController(); caller.abort();
    try {
      await fetch(apiBaseUrl() + "/api/v1/workspaces/" + currentWorkspaceId() + "/sources", { signal: caller.signal });
      return "unexpected success";
    } catch (error) { return error.name; }
  })).toBe("AbortError");
});
