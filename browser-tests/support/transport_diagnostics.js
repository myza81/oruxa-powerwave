// Opt-in LOCAL diagnostics. Never record headers, query strings, bodies or page nonces.
const fs = require("node:fs");
const path = require("node:path");
const dc = require("node:diagnostics_channel");
const directory = process.env.PW_DIAGNOSTICS_DIR;
let sequence = 0;
const socketIds = new WeakMap();
function record(event, fields = {}) {
  if (!directory) return;
  fs.appendFileSync(path.join(directory, `client-${process.pid}.jsonl`),
    JSON.stringify({ event, pid: process.pid, at: Date.now() / 1000, ...fields }) + "\n");
}
if (directory) {
  fs.mkdirSync(directory, { recursive: true });
  record("worker_process_start");
  process.once("exit", code => record("worker_process_stop", { code }));
  dc.channel("http.client.request.start").subscribe(({ request: req }) => {
    const url = new URL(req.path, `http://${req.getHeader("host")}`);
    if (url.hostname !== "127.0.0.1" || !url.pathname.startsWith("/api/v1/")) return;
    const id = ++sequence;
    let connection = req.socket;
    const socket = () => ({ socketId: connection && socketIds.get(connection), localPort: connection?.localPort, remotePort: connection?.remotePort, destroyed: connection?.destroyed });
    const observe = value => {
      connection = value;
      if (!socketIds.has(connection)) {
        const socketId = ++sequence;
        socketIds.set(connection, socketId);
        const endpoint = { socketId, localPort: connection.localPort, remotePort: connection.remotePort };
        connection.once("connect", () => {
          endpoint.localPort = connection.localPort;
          endpoint.remotePort = connection.remotePort;
          record("socket_connect", endpoint);
        });
        connection.once("end", () => record("socket_end", endpoint));
        connection.once("close", hadError => record("socket_close", { ...endpoint, hadError }));
      }
      record("http_socket", { id, ...socket() });
    };
    if (connection) observe(connection);
    else req.once("socket", observe);
    record("http_start", { id, method: req.method, path: url.pathname, reused: req.reusedSocket, ...socket() });
    req.once("response", response => record("http_response", { id, status: response.statusCode, ...socket() }));
    req.once("error", error => record("http_error", { id, code: error.code, ...socket() }));
    req.once("close", () => record("http_close", { id, ...socket() }));
  });
}
function attach(context, info) {
  if (!directory) return { phase() {}, api() {} };
  const identity = { worker: info.workerIndex, repeat: info.repeatEachIndex, test: info.titlePath.join(" > ") };
  let phase = "application";
  const ids = new WeakMap();
  const log = (event, fields) => record(event, { ...identity, phase, ...fields });
  log("context_start");
  context.on("request", request => {
    const url = new URL(request.url());
    if (!url.pathname.startsWith("/api/v1/")) return;
    const id = ++sequence; ids.set(request, id);
    log("browser_start", { id, method: request.method(), path: url.pathname });
  });
  context.on("response", response => {
    const id = ids.get(response.request());
    if (id) log("browser_response", { id, status: response.status() });
  });
  for (const [event, name] of [["requestfinished", "browser_end"], ["requestfailed", "browser_failed"]]) {
    context.on(event, request => {
      const id = ids.get(request);
      if (id) log(name, { id, error: request.failure()?.errorText });
    });
  }
  const wrapped = new WeakSet();
  return {
    phase(value) { phase = value; log("phase"); },
    api(api) {
      if (wrapped.has(api)) return;
      wrapped.add(api);
      const fetch = api.fetch.bind(api);
      api.fetch = async function(input, options) {
        const url = new URL(typeof input === "string" ? input : input.url(), `http://127.0.0.1:${process.env.PW_BACKEND_PORT || "8000"}`);
        const id = ++sequence, method = options?.method || "GET";
        log("api_start", { id, method, path: url.pathname });
        try {
          const response = await fetch(input, options);
          log("api_response", { id, status: response.status() });
          return response;
        } catch (error) {
          log("api_error", { id, error: /ECONNRESET/.test(error.message) ? "ECONNRESET" : /socket hang up/.test(error.message) ? "socket hang up" : error.name });
          throw error;
        }
      };
    },
  };
}
module.exports = { attach };
