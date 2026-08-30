// Minimal Playwright config for the Powerwave browser smoke-test
// foundation. See docs/development/BROWSER_SMOKE_TEST.md.
//
// Deliberately targets LOCAL code only -- never a deployed hostname
// (dev.powerwave.oruxa.uk, etc). `webServer` starts a real backend
// (uvicorn, the SAME app.main:create_app factory the real app/Docker
// image uses -- no second entrypoint) and serves the real
// frontend/index.html statically, waiting on deterministic health/URL
// checks rather than a fixed sleep, then tears both down when the run
// ends. Ports/paths are all overridable via env vars with localhost
// defaults -- nothing here is VPS- or Docker-specific.
const path = require("path");
const os = require("os");
const fs = require("fs");

const REPO_ROOT = path.resolve(__dirname, "..");

// 8000/8101 are not arbitrary: they are the SAME defaults already
// checked into frontend/config.js (apiBaseUrl) and the backend's own
// DEFAULT_CORS_ORIGINS (see backend/app/config.py) -- using them means
// this smoke suite needs zero config.js edits and no CORS_ORIGINS
// override to run against local code out of the box.
const BACKEND_PORT = process.env.PW_BACKEND_PORT || "8000";
const FRONTEND_PORT = process.env.PW_FRONTEND_PORT || "8101";
const PYTHON = process.env.PW_PYTHON || "python3";

// A fresh, unique storage dir per config load -- test isolation
// (section 14): a brand-new backend process each run, with nowhere for
// a previous run's state to have been written even if STORAGE_PATH's
// directory itself were reused. WorkspaceRegistry is in-memory/
// ephemeral regardless (see docs/project-memory/DECISIONS.md DEC-015),
// so this only matters for the backend's own boot-time writable-
// directory check, not for the workspace state the smoke test cares
// about.
const STORAGE_PATH = process.env.PW_STORAGE_PATH || fs.mkdtempSync(path.join(os.tmpdir(), "powerwave-smoke-"));

module.exports = {
  testDir: __dirname,
  testMatch: "*.spec.js",
  timeout: 30_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: `http://127.0.0.1:${FRONTEND_PORT}`,
  },
  webServer: [
    {
      command: `${PYTHON} -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port ${BACKEND_PORT}`,
      cwd: path.join(REPO_ROOT, "backend"),
      url: `http://127.0.0.1:${BACKEND_PORT}/health`,
      env: { STORAGE_PATH },
      reuseExistingServer: !process.env.CI,
      timeout: 30_000,
    },
    {
      command: `${PYTHON} -m http.server ${FRONTEND_PORT} --bind 127.0.0.1`,
      cwd: path.join(REPO_ROOT, "frontend"),
      url: `http://127.0.0.1:${FRONTEND_PORT}/index.html`,
      reuseExistingServer: !process.env.CI,
      timeout: 15_000,
    },
  ],
};
