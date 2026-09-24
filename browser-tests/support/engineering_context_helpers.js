// Shared Engineering Context seeding helpers for Analysis Playwright
// suites (Phasor/Overcurrent/Impedance/Distance Protection/Sequence
// Components/Related Waveforms).
//
// DEC-104 (2026-09-23): a successful source upload now ALSO runs the same
// Engineering Context discovery every one of these suites used to trigger
// manually -- `app.services.workspace_preparation_service.
// prepare_workspace_source()` synchronously auto-creates a `suggested`
// Engineering Context for any cleanly phase-detectable channel cluster
// (three-letter-prefix Voltage/Current sets, e.g. ALPHA1_VA/VB/VC/IA/IB/IC)
// BEFORE any test-side code ever runs. A test that then POSTs its own
// "manual" context claiming the SAME channels now 409s
// (`channel_already_in_context`) -- see DECISIONS.md DEC-111.
//
// `reuseOrCreateFullBayContext()` is the fix: discover the context
// DEC-104 already created for a given channel-name prefix and reuse it,
// only falling back to a manual POST if discovery genuinely finds
// nothing (a prefix DEC-104's own detector cannot cluster, or a bare-role
// fixture). This mirrors the equivalent, already-established backend
// pattern (`backend/tests/test_engineering_context_api.py`'s own
// `_upload()` vs. `_upload_without_clearing()`), adapted for the browser:
// prefer discovery/reuse over a blind duplicate POST.
//
// For the rarer case where a test genuinely needs a context DEC-104's
// upload-time discovery cannot produce (a deliberately partial bay, or a
// test whose own explicit purpose is exercising manual context
// creation/the fallback discovery bootstrap itself), `clearContexts()`
// removes whatever auto-discovery already created so the test's own
// manual POST has a clean slate -- exactly the scenario DEC-104's own
// design doc already anticipates ("a group/context the user -- or a
// test -- deleted after upload").

const BACKEND_URL = `http://127.0.0.1:${process.env.PW_BACKEND_PORT || "8000"}`;

function contextsUrl(workspaceId) {
  return `${BACKEND_URL}/api/v1/workspaces/${encodeURIComponent(workspaceId)}/engineering-contexts`;
}

async function fetchContexts(page, workspaceId) {
  const response = await page.request.get(contextsUrl(workspaceId));
  if (!response.ok()) return [];
  return response.json();
}

async function postContext(page, workspaceId, body) {
  const response = await page.request.post(contextsUrl(workspaceId), { data: body });
  if (!response.ok()) {
    throw new Error(`POST engineering-contexts failed (${response.status()}): ${await response.text()}`);
  }
  return response.json();
}

async function deleteContext(page, workspaceId, contextId) {
  await page.request.delete(`${contextsUrl(workspaceId)}/${encodeURIComponent(contextId)}`);
}

// Removes every existing Engineering Context in the workspace (or, when
// `sourceId` is given, only those with at least one member referencing
// that source) -- clears whatever DEC-104's upload-time discovery already
// created so a test can manually construct its own context from a clean
// slate, exactly like `_upload()` already does on the backend side.
async function clearContexts(page, workspaceId, sourceId) {
  const contexts = await fetchContexts(page, workspaceId);
  for (const context of contexts) {
    if (
      sourceId &&
      !context.members.some((m) => m.channel_ref.kind === "source" && m.channel_ref.source_id === sourceId)
    ) {
      continue;
    }
    await deleteContext(page, workspaceId, context.id);
  }
}

// Finds the (normally DEC-104-auto-created) context whose members are
// exactly this source's `${channelPrefix}_*` channels.
async function findContextByChannelPrefix(page, workspaceId, sourceId, channelPrefix) {
  const contexts = await fetchContexts(page, workspaceId);
  const needle = `${channelPrefix}_`;
  return (
    contexts.find((c) =>
      c.members.some(
        (m) =>
          m.channel_ref.kind === "source" &&
          m.channel_ref.source_id === sourceId &&
          m.channel_ref.channel_name.startsWith(needle)
      )
    ) || null
  );
}

// The main entry point every analyzer suite's own "full bay" setup
// wants: reuse the context DEC-104's upload-time discovery already
// created for `channelPrefix` (the common case), or fall back to a
// manual POST with the given `roles` ([channelSuffix, phase] pairs, e.g.
// ["VA", "A"]) if discovery genuinely produced nothing for this prefix.
// `displayName` is only used for the fallback POST -- the auto-created
// context already carries `channelPrefix` itself as its own display name
// (see app.domain.engineering_context_detection._display_name()), which
// none of these suites assert on.
async function reuseOrCreateFullBayContext(page, workspaceId, sourceId, channelPrefix, roles, displayName) {
  const existing = await findContextByChannelPrefix(page, workspaceId, sourceId, channelPrefix);
  if (existing) return existing;
  const members = roles.map(([suffix, phase]) => ({
    channel_ref: { kind: "source", source_id: sourceId, channel_name: `${channelPrefix}_${suffix}` },
    phase,
    phase_source: "engineer_confirmed",
  }));
  return postContext(page, workspaceId, { display_name: displayName || channelPrefix, status: "manual", members });
}

// DEC-105 (2026-09-23) made ANY first-ever non-empty context list --
// including one that already existed the instant Analysis's very first
// fetch runs, exactly DEC-104's own new upload-time-prepared common case
// -- auto-select its first context the moment Analysis/an analyzer tab
// opens (see wwAnalysisPublishContexts()'s own "fresh discovered" signal
// in frontend/index.html). Several pre-DEC-105-era Playwright tests still
// unconditionally call `.selectOption(contextId)` immediately afterward
// -- now a REDUNDANT re-selection of the SAME already-auto-selected
// value. Reproduced directly: that redundant re-selection can race the
// auto-select's own in-flight "claim the Time Group, then refine to a
// safe start time" sequence (`wwPhasorLoadForSelectedContext()` et al.)
// closely enough that the follow-up refined-time fetch is sometimes never
// issued, leaving the panel stuck showing the FIRST, transient
// `analysis_time=0` response (`needs_configuration` / "insufficient
// window history") instead of the settled, resolved one -- a genuine,
// timing-dependent race in the app's own claim/refine sequence, but one
// no real engineer can trigger (a real click happens well after the
// auto-select has already settled). This helper avoids the race the same
// way already-correct suites (`post_upload_readiness.spec.js`) avoid it
// entirely: only calls `.selectOption()` when the control isn't ALREADY
// showing `contextId` (an auto-select from a genuinely different
// context, or a real context SWITCH, still selects for real).
async function ensureContextSelected(page, selectLocator, contextId) {
  const current = await selectLocator.inputValue();
  if (current !== contextId) {
    await selectLocator.selectOption(contextId);
  }
}

module.exports = {
  BACKEND_URL,
  fetchContexts,
  postContext,
  deleteContext,
  clearContexts,
  findContextByChannelPrefix,
  reuseOrCreateFullBayContext,
  ensureContextSelected,
};
