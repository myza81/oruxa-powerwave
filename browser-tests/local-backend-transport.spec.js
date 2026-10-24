const { test, expect } = require("./support/test");
const http = require("node:http");
const dc = require("node:diagnostics_channel");
const { registerLocalBackend } = require("./support/local_backend_transport");

async function server(handler) {
  const sockets = [];
  const app = http.createServer(handler);
  app.keepAliveTimeout = 5000;
  app.keepAliveTimeoutBuffer = 0;
  app.on("connection", socket => sockets.push(socket));
  await new Promise(resolve => app.listen(0, "127.0.0.1", resolve));
  const port = app.address().port;
  return { sockets, port, url: `http://127.0.0.1:${port}/probe`,
    async close() { app.closeAllConnections(); await new Promise(resolve => app.close(resolve)); } };
}

test("local transport retains warm pooling and leaves other ports unchanged", async ({ context }) => {
  const a = await server((req, res) => res.end("A"));
  const b = await server((req, res) => res.end("B"));
  const unregister = registerLocalBackend(a.port, 1000);
  try {
    for (const target of [a, b, a, b]) expect(await (await context.request.get(target.url)).text()).toBe(target === a ? "A" : "B");
    expect(a.sockets.length).toBe(1);
    expect(b.sockets.length).toBe(1);
  } finally { unregister(); await a.close(); await b.close(); }
});

test("free local sockets retire before server expiry and the next request uses a fresh socket", async ({ context }) => {
  let requests = 0;
  const app = await server((req, res) => { requests++; res.end("ok"); });
  const unregister = registerLocalBackend(app.port, 100);
  let clientSocket;
  const observed = ({ request }) => {
    if (new URL(request.path, `http://${request.getHeader("host")}`).port !== String(app.port)) return;
    if (request.socket) clientSocket = request.socket;
    else request.once("socket", socket => { clientSocket = socket; });
  };
  const channel = dc.channel("http.client.request.start"); channel.subscribe(observed);
  try {
    expect(await (await context.request.get(app.url)).text()).toBe("ok");
    await expect.poll(() => clientSocket?.timeout).toBe(100);
    if (!clientSocket.destroyed) await new Promise(resolve => clientSocket.once("close", resolve));
    expect(await (await context.request.get(app.url)).text()).toBe("ok");
    expect(app.sockets.length).toBe(2);
    expect(requests).toBe(2); // no retry and no extra operation
  } finally { channel.unsubscribe(observed); unregister(); await app.close(); }
});

test("free-socket expiry never cancels active response headers or bodies", async ({ context }) => {
  let accept, sendHeaders, sendBody;
  const accepted = new Promise(resolve => { accept = resolve; });
  const headers = new Promise(resolve => { sendHeaders = resolve; });
  const body = new Promise(resolve => { sendBody = resolve; });
  const app = await server(async (req, res) => {
    if (req.url === "/warm") return res.end("warm");
    accept();
    await headers; res.writeHead(200); res.write("first");
    await body; res.end("last");
  });
  const unregister = registerLocalBackend(app.port, 1000);
  let socket;
  const channel = dc.channel("http.client.request.start");
  const observe = ({ request }) => {
    if (new URL(request.path, `http://${request.getHeader("host")}`).port !== String(app.port)) return;
    if (request.socket) socket = request.socket;
    else request.once("socket", value => { socket = value; });
  };
  channel.subscribe(observe);
  try {
    expect(await (await context.request.get(app.url.replace("/probe", "/warm"))).text()).toBe("warm");
    const pending = context.request.get(app.url);
    await accepted;
    expect(app.sockets.length).toBe(1); // active work reused the warm socket
    expect(socket.timeout || 0).toBe(0); // free-pool budget removed before headers
    sendHeaders();
    // The active body must also retain the native request budget.
    expect(socket.timeout || 0).toBe(0);
    sendBody();
    expect(await (await pending).text()).toBe("firstlast");
  } finally { sendHeaders(); sendBody(); channel.unsubscribe(observe); unregister(); await app.close(); }
});

test("an active request still observes its original deadline without retry", async ({ context }) => {
  let requests = 0;
  const app = await server(() => { requests++; });
  const unregister = registerLocalBackend(app.port, 10);
  try {
    await expect(context.request.get(app.url, { timeout: 200 })).rejects.toThrow(/Timeout 200ms exceeded/);
    // Expiry may precede server arrival; neither outcome permits a retry.
    expect(requests).toBeLessThanOrEqual(1);
  } finally { unregister(); await app.close(); }
});


test("an overdue idle socket is retired synchronously after the client event loop was blocked", async ({ context }) => {
  const app = await server((req, res) => res.end("ok"));
  const unregister = registerLocalBackend(app.port, 200);
  let firstSocket;
  const channel = dc.channel("http.client.request.start");
  const observe = ({ request }) => {
    if (new URL(request.path, `http://${request.getHeader("host")}`).port !== String(app.port) || firstSocket) return;
    if (request.socket) firstSocket = request.socket;
    else request.once("socket", socket => { firstSocket = socket; });
  };
  channel.subscribe(observe);
  try {
    expect(await (await context.request.get(app.url)).text()).toBe("ok");
    expect(firstSocket.destroyed).toBe(false);
    // Deliberate controlled client stall: native timers cannot run during this.
    Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 300);
    const pending = context.request.get(app.url);
    const retiredBeforeDispatch = firstSocket.destroyed;
    expect(await (await pending).text()).toBe("ok");
    expect(retiredBeforeDispatch).toBe(true);
    expect(app.sockets.length).toBe(2);
  } finally { channel.unsubscribe(observe); unregister(); await app.close(); }
});
