// Test-only lifecycle: a fresh browser context owns its workspace UUIDs.
// Close pages before deleting resources so playback cannot race teardown.
const base = require("@playwright/test");
const { attach } = require("./transport_diagnostics");
const { registerLocalBackend, wrapLocalAPI } = require("./local_backend_transport");
registerLocalBackend(process.env.PW_BACKEND_PORT || "8000");
const test = base.test.extend({
  workspaceCleanup: [async ({ context }, use, testInfo) => {
    wrapLocalAPI(context.request);
    const diagnostics = attach(context, testInfo);
    diagnostics.api(context.request);
    const owned = new Map();
    const backendOrigin = `http://127.0.0.1:${process.env.PW_BACKEND_PORT || "8000"}`;
    context.on("request", request => {
      const url = new URL(request.url());
      const match = url.pathname.match(/^\/api\/v1\/workspaces\/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})($|\/)/i);
      if (match && url.origin === backendOrigin) {
        owned.set(match[1], url.origin);
      }
    });
    await use();
    diagnostics.phase("context-close");
    await context.close();
    diagnostics.phase("cleanup");
    const api = await base.request.newContext();
    wrapLocalAPI(api);
    diagnostics.api(api);
    try {
      for (const [id, origin] of owned) {
        const response = await api.delete(`${origin}/api/v1/workspaces/${id}`);
        base.expect([200, 204, 404], `cleanup of test workspace ${id}`).toContain(response.status());
      }
    } finally { await api.dispose(); }
  }, { auto: true }],
});
module.exports = { ...base, test };
