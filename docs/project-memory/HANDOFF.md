# Handoff

Short, current-state continuation note for the next agent/session. This
document is replaced/updated in place, not appended to indefinitely — Git
history already provides the detailed historical trail.

Last updated: **2026-08-14**

## What was most recently done

**Implemented Phase 1**: COMTRADE upload → ephemeral parse → channel-list
API, end to end, backend and frontend. This is the first production code
change in this repository's Powerwave-domain history — everything before
this was documentation/governance. Full detail in
[MIGRATION_PLAN.md — Phase 1 Implementation Record](MIGRATION_PLAN.md#phase-1--implementation-record-2026-08-14);
summarized here for continuation purposes.

Before writing any code: re-verified both repos current with GitHub,
re-read the ported `powerwave` COMTRADE provider/models in full (not from
memory), and **empirically investigated** (not assumed) whether FastAPI's
upload mechanism touches disk — see "Ephemeral storage — what was actually
verified" below.

**A late-arriving critical requirement changed the design mid-task**: the
owner decided `oruxa_powerwave` must not persistently retain uploaded event
files at all (DECISIONS.md DEC-015) — a stronger requirement than the
earlier Phase 0 design assumed (which had originals going into
`StorageBackend`'s `original` category). The implementation was built
around this from the start, not retrofitted: uploaded bytes are staged in
a per-request `tempfile.TemporaryDirectory()` only long enough for the
unmodified `ComtradeProvider` to parse them, then deleted; only lightweight
channel/timing metadata is kept afterward, in memory, in a
`workspace_id`/`source_id`-scoped registry (never `StorageBackend`, never a
database).

## Ephemeral storage — what was actually verified (not claimed)

This was investigated empirically, with a small standalone reproduction
(FastAPI `TestClient` + `lsof`/`os.path.exists` checks), not inferred from
documentation or memory:

- **Starlette's own multipart parser** (a FastAPI dependency, not
  application code) spools any uploaded file part over 1 MB
  (`starlette.formparsers.MultiPartParser.spool_max_size`) to a
  `tempfile.SpooledTemporaryFile` that rolls over to a real OS temp file.
  Confirmed with a live request: a 500 KB part stayed in memory
  (`_rolled=False`); a 5 MB part rolled to disk (`_rolled=True`), backed by
  a real file descriptor (`lsof` showed a path under the OS temp
  directory). **This happens before this application's route handler code
  runs at all.**
- That file is created and immediately unlinked (`os.path.exists()` on the
  reported path returned `False` even *during* the request) — Python's
  `tempfile.TemporaryFile` "no name" semantics, so it's never visible via a
  directory listing and is reclaimed automatically (by the OS, even across
  a crash) once the file descriptor closes at the end of request handling.
- Given COMTRADE `.dat` files in the expected Phase 1 size range (up to
  ~100 MB) will almost always exceed 1 MB, **this spooling is not an edge
  case — it happens for essentially every real upload**, regardless of
  anything this implementation does.
- **On top of that**, `import_service.py` deliberately writes the same
  bytes a second time, into its own `tempfile.TemporaryDirectory()`,
  because `ComtradeProvider.load()` requires a real filesystem path with a
  same-directory, same-stem `.dat` companion (`_find_dat_file`). This
  second temp usage is disclosed, not hidden, and is always cleaned up
  (Python `with` block, runs on success, failure, or any exception).
- **A genuinely zero-disk-touch path would require rewriting
  `ComtradeProvider`'s internal file I/O to accept in-memory buffers.**
  This was judged disproportionate for this slice (preserving proven
  `powerwave` parsing logic unmodified was itself an explicit instruction)
  and is recorded as an `[OPEN]` item for owner review rather than silently
  claimed as already achieved. "Not persistently retained" (the actual
  requirement, DEC-015) is satisfied; "never touches disk at all" is not,
  and the two should not be conflated.

## What was verified (testing/parity)

- **168 backend tests pass** (`cd backend && pytest`), up from the
  pre-existing suite — new tests cover the ported provider, a COMTRADE
  migration-parity golden-value test, the workspace registry, and the full
  API (upload validation, error taxonomy, lifecycle, response-size
  discipline).
- **Migration parity, verified two ways**: (1) two synthetic fixtures
  (`backend/tests/fixtures/comtrade/synth_{ascii,binary}.{cfg,dat}`,
  authored for this migration) produce byte-identical results to
  `powerwave`'s own canonical `ComtradeProvider` (same commit, `3156392`) —
  committed as `test_comtrade_parity.py`. (2) One real `powerwave` sample
  file (`PTAI_MVLY_relay.CFG`, 4224 samples, 40 channels) was cross-checked
  the same way, locally, and also matched exactly — **not committed to
  this repository**, because `powerwave/samples/README.md` notes sample
  files "may be large or confidential" (real substation event data). This
  was a deliberate choice, not an oversight — see the note in
  [MIGRATION_PLAN.md](MIGRATION_PLAN.md).
- **Performance baseline measured**, not estimated: ~5 ms for a tiny
  synthetic file, ~9 ms for a 562 KB / 4,224-sample real file, ~152 ms for
  a 15.7 MB / 32,693-sample / 130-channel real file (all local, this
  development machine). Response body size stayed ~350-360 bytes
  regardless of input size, confirming the "no waveform arrays in
  responses" design holds in practice. Parse-only peak memory for the
  15.7 MB file was ~229 MB resident — **no measurement was taken near the
  actual ~100 MB configured ceiling**; extrapolation suggests a 100 MB
  file could need 1+ GB resident memory. Flagged as `[OPEN]`, not verified.
- Frontend JS syntax was checked (Node `Function` constructor parse check)
  and the full upload → channels → delete flow was exercised end-to-end
  against a live local server via `curl`, using the exact request shape
  the frontend's `fetch()` calls send (`cfg_file`/`dat_file` multipart
  fields) — not just unit-tested in isolation.
- No production code outside the intended scope was touched. `git status`
  confirms only `backend/app/{domain,providers,services,schemas,api}/`
  (new), `backend/app/{config,main}.py` (modified), `backend/requirements.txt`
  (modified), `backend/tests/**` (new tests + two pre-existing files fixed
  for `Settings`'s new required field), `frontend/index.html` (modified),
  and `docs/project-memory/**` (this documentation).

## What files were changed this session

New:
- `backend/app/domain/{__init__,channels,disturbance_record,metadata,source,timing}.py`
- `backend/app/providers/{__init__,base,comtrade}.py`
- `backend/app/services/{__init__,workspace_registry,import_service,errors}.py`
- `backend/app/schemas/{__init__,source}.py`
- `backend/app/api/__init__.py`, `backend/app/api/v1/{__init__,sources}.py`
- `backend/tests/{test_comtrade_provider,test_comtrade_parity,test_workspace_registry,test_sources_api}.py`
- `backend/tests/fixtures/comtrade/synth_{ascii,binary}.{cfg,dat}` (synthetic, authored for this migration)

Modified:
- `backend/app/config.py` — added `MAX_EVENT_UPLOAD_SIZE_MB` / `max_event_upload_size_bytes`.
- `backend/app/main.py` — mounted the v1 router, added the ephemeral
  `WorkspaceRegistry` to app state, added a Content-Length pre-check
  middleware.
- `backend/requirements.txt` — added `python-multipart`, `numpy`, `pandas`.
- `backend/tests/conftest.py`, `backend/tests/test_config.py`,
  `backend/tests/test_storage.py` — updated for `Settings`'s new field;
  added config tests for the new setting.
- `frontend/index.html` — full upload/channel-list UI (was a placeholder).
- `docs/project-memory/{DECISIONS,MIGRATION_PLAN,CURRENT_STATE,HANDOFF}.md` — this work.

No backend/frontend/provider/API/test/database/storage-implementation file
was touched outside this list.

## Owner UAT checklist

Per this phase's instructions — a concise, hands-on checklist. Waveform
behaviour is intentionally **not** included (out of scope for this phase).

1. **Upload is understandable.** Open the frontend, locate the two file
   slots (Configuration file / Data file), and confirm it's clear what
   goes where.
2. **File-size guidance is visible.** Confirm the "Best experience with
   event records up to 100 MB" text is visible before uploading.
3. **Oversized-file warning is clear.** Try selecting a combined pair over
   100 MB (or lower the server's `MAX_EVENT_UPLOAD_SIZE_MB` for testing)
   and confirm both the client-side warning and the server's actual
   rejection are understandable, not cryptic.
4. **Loading/parsing feedback is understandable.** Upload a real `.cfg`/
   `.dat` pair and confirm it's clear the app is working, not frozen,
   during the request.
5. **Successful import is obvious.** Confirm a clear success indicator
   appears with the station name and channel counts.
6. **Source metadata looks correct.** Compare the displayed station name,
   recorder, nominal frequency, timing mode, sample count, duration, and
   sampling rate(s) against what you'd expect from the file (e.g. via
   `powerwave` itself, or the file's own CFG header).
7. **Analog channels are correctly listed.** Confirm names, units, phase,
   scale, and offset look right for a known file.
8. **Digital channels are correctly listed.** Confirm names and normal
   states look right.
9. **Error handling is understandable.** Try an unsupported file type, a
   `.cfg` with no matching `.dat`, and a corrupt file; confirm each
   produces a clear, non-technical message (never a raw Python error).
10. **General responsiveness feels acceptable.** For a file in your normal
    working size range, confirm the upload-to-result time feels reasonable
    (see the measured baseline above for reference numbers on this
    development machine).

Two things worth deciding while doing this UAT, not just checking boxes:

- **UAT-1 (open)**: does the two-explicit-slots upload interaction feel
  right, or would you rather select/drag both files at once and let the
  app pair them automatically by filename? Either is a small frontend-only
  change (see [MIGRATION_PLAN.md](MIGRATION_PLAN.md) UAT-1).
- Whether the ~229 MB memory usage for a ~16 MB file (and the extrapolated
  1+ GB for a 100 MB file) is a concern for your actual deployment target
  before this goes further.

## What remains unresolved

See the `[OPEN]` items in [CURRENT_STATE.md — Known blockers](CURRENT_STATE.md#known-blockers)
— all carried forward accurately, none newly resolved by claiming success
where it wasn't verified (particularly the disk-touch question above).

## What should be done next

Per this phase's explicit closing instruction: **stop here**. Do not begin
Phase 1.5 (CSV/Excel), waveform rendering, calculated signals, or any later
phase without the owner working through the UAT checklist above and giving
explicit go-ahead for whatever comes next.

## What must not be assumed

- Do not assume the upload path is disk-free — it isn't, by design
  necessity, though it is genuinely ephemeral (see the investigation
  above). Don't let a future session claim "memory-only" without re-reading
  this.
- Do not assume the two-slot upload UI is a final decision — it's an
  explicitly temporary Phase 1 choice (UAT-1 remains open).
- Do not assume performance/memory behaviour at ~100 MB — only measured up
  to ~16 MB.
- Do not assume CSV/Excel, waveform rendering, or any later phase is
  authorized — none are.
- Do not assume `powerwave` is still at commit `3156392` — it is actively
  developed; re-verify before relying on specific line numbers for future
  work.

## Owner approval needed before proceeding?

- Not needed to run the UAT checklist above.
- **Yes**, before Phase 1.5 or any later phase begins, before deploying
  Phase 1 to DEV/PROD, and before any change to the ephemeral-storage or
  upload-size decisions recorded in DECISIONS.md — per the change-governance
  rule in [CLAUDE.md](../../CLAUDE.md) / [AGENTS.md](../../AGENTS.md).
