// Local harness only: retire FREE sockets before Uvicorn's existing idle expiry.
// Node Agent's documented hooks preserve normal pooling and active request budgets:
// https://nodejs.org/docs/latest-v24.x/api/http.html#agentkeepsocketalivesocket
const dc = require("node:diagnostics_channel");
const SERVER_KEEP_ALIVE_SECONDS = 5;
const CLIENT_IDLE_MS = 4000;
const ports = new Map();
const decorated = new WeakSet();
const trackedAgents = new Set();
const idleDeadlines = new WeakMap();
const wrappedAPIs = new WeakSet();

function registerLocalBackend(port, idleMs = CLIENT_IDLE_MS) {
  port = Number(port);
  if (!Number.isInteger(port) || port < 1 || port > 65535 || !Number.isFinite(idleMs) || idleMs <= 0) throw new Error("Invalid local transport policy");
  ports.set(port, idleMs);
  return () => { if (ports.get(port) === idleMs) ports.delete(port); };
}

dc.channel("http.client.request.start").subscribe(({ request }) => {
  const url = new URL(request.path, `http://${request.getHeader("host")}`);
  if (url.hostname !== "127.0.0.1" || !ports.has(Number(url.port || 80))) return;
  const agent = request.agent;
  if (!agent || decorated.has(agent)) return;
  decorated.add(agent);
  trackedAgents.add(new WeakRef(agent));
  const keep = agent.keepSocketAlive;
  const reuse = agent.reuseSocket;
  const previousTimeouts = new WeakMap();
  agent.keepSocketAlive = function(socket) {
    const reusable = keep.call(this, socket);
    const idleMs = socket.remoteAddress === "127.0.0.1" ? ports.get(socket.remotePort) : undefined;
    if (reusable && idleMs !== undefined) {
      // This hook runs only after the full response body has detached. Node
      // itself destroys timed-out sockets only while they are in its free pool.
      const previous = socket.timeout || 0;
      const budget = previous > 0 ? Math.min(previous, idleMs) : idleMs;
      previousTimeouts.set(socket, previous);
      idleDeadlines.set(socket, performance.now() + budget);
      socket.setTimeout(budget);
    }
    return reusable;
  };
  agent.reuseSocket = function(socket, request) {
    // Remove our FREE-pool deadline before the next active request begins.
    if (previousTimeouts.has(socket)) {
      socket.setTimeout(previousTimeouts.get(socket));
      previousTimeouts.delete(socket);
      idleDeadlines.delete(socket);
    }
    return reuse.call(this, socket, request);
  };
});
// A busy test worker can delay delivery of an idle timer. Check the same
// monotonic deadline BEFORE constructing another native Playwright request.
// Read Agent.freeSockets without modifying it; Node owns removal on destroy.
function wrapLocalAPI(api) {
  if (wrappedAPIs.has(api)) return;
  wrappedAPIs.add(api);
  const fetch = api.fetch.bind(api);
  api.fetch = function(...args) {
    const now = performance.now();
    for (const reference of trackedAgents) {
      const agent = reference.deref();
      if (!agent) { trackedAgents.delete(reference); continue; }
      for (const sockets of Object.values(agent.freeSockets)) for (const socket of sockets) {
        if (socket.remoteAddress === "127.0.0.1" && ports.has(socket.remotePort) &&
            idleDeadlines.has(socket) && now >= idleDeadlines.get(socket)) socket.destroy();
      }
    }
    return fetch(...args);
  };
}
module.exports = { registerLocalBackend, wrapLocalAPI, SERVER_KEEP_ALIVE_SECONDS, CLIENT_IDLE_MS };
