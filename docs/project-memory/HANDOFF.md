# Handoff

Short, current-state continuation note for the next agent/session. This
document is replaced/updated in place, not appended to indefinitely — Git
history already provides the detailed historical trail.

Last updated: **2026-08-14**

## What was most recently done

Completed the full `powerwave` → `oruxa_powerwave` discovery audit and
wrote it into [POWERWAVE_DISCOVERY.md](POWERWAVE_DISCOVERY.md) (replacing
the earlier skeleton). This covered: existing `powerwave` architecture,
`oruxa_powerwave`'s current (still domain-empty) architecture, the file
import pipeline, the internal data model, session/state management,
synchronization (including a mid-audit re-verification after `powerwave`'s
`main` advanced two commits), timestamp/sample-rate handling, calculated
signals, waveform rendering, measurements/analytics, large-dataset
behaviour, background processing, test coverage, GUI/domain separation, a
reuse-candidate classification (A/B/C), a proposed frontend/backend
boundary, multi-user risks, engineering-integrity risks, architectural
risks, a migration comparison matrix, proposed migration phases, a
recommended first implementation slice, nine open questions, and a closing
recommendation. Everything design/sequencing-oriented is marked
`[PROPOSAL]`; nothing was written into [DECISIONS.md](DECISIONS.md).

Before that, in the same session: resolved the Git/GitHub sync issues left
open from the project-memory-setup task (see below) and fast-forwarded the
local `powerwave` clone from `a5c7289` to `3156392`.

## What was verified

- Both repositories' Git/GitHub state was checked and reconciled before any
  discovery work began (see "Git/GitHub sync" below).
- `powerwave` was re-confirmed at `3156392` before each investigation agent
  started; agents were instructed to stop and report a discrepancy rather
  than proceed if the repo wasn't at that commit.
- A prior investigation pass (from earlier in this session, before the
  project-memory-setup task) had covered five subsystems at the older
  commit `a5c7289`. Two of those — session state and synchronization — were
  directly affected by commit `3156392`'s changes (new
  `absolute_alignment.py`, `alignment_summary.py`, `viewport_policy.py`,
  and manifest-persistence changes). Rather than trusting the older
  findings, a dedicated re-verification pass checked ten specific prior
  claims one by one against the current code — three turned out to be now
  inaccurate, two now incomplete, five still accurate. The other three
  unaffected subsystems (calculated signals, analytics catalog, and most of
  visualization rendering) were confirmed via `git diff --stat` to be
  genuinely untouched by the new commits before being carried forward
  as-is.
- `oruxa_powerwave`'s own current state (backend/frontend/deploy) was
  re-confirmed unchanged since an earlier direct inspection, via `git log`
  on the relevant paths, before being written into the discovery document.
- No production application code was changed — only documentation
  (`docs/project-memory/**`).

## Git/GitHub sync (resolved this session, method now established)

Both repositories are synced with GitHub and were reconfirmed independently
(not by trusting locally-cached refs) before discovery began:

- **`oruxa_powerwave`**: `origin`'s configured SSH URL
  (`git@github.com:myza81/oruxa-powerwave.git`) is still not authenticated
  in these sandboxed sessions (`Permission denied (publickey)`, confirmed
  repeatedly). The established, repeatable workaround: push to the
  **explicit HTTPS URL** (`https://github.com/myza81/oruxa-powerwave.git`)
  as a one-off push target — this does **not** modify `origin`'s config
  (never run `git remote set-url`) and a credential helper handles auth
  silently. Verify success by fetching from that same explicit HTTPS URL
  into `FETCH_HEAD` and comparing SHAs — **do not trust the local
  `origin/main` tracking ref**, which stays stale (reads whatever it was at
  the last successful `git fetch origin`) since SSH fetch still fails here.
- **`powerwave`**: `origin` is HTTPS already
  (`https://github.com/myza81/powerwave.git`) and authenticates fine for
  both fetch and (when needed) fast-forward pull. It was 2 commits behind
  `origin/main` at the start of this task; fast-forwarded cleanly
  (`git pull --ff-only`) to `3156392`. The one pre-existing untracked
  0-byte file (`Make`) was left untouched throughout.

If a future machine has a working SSH key for `oruxa_powerwave`, plain
`git fetch origin`/`git push origin main` will work normally and the
HTTPS-workaround caveats above won't apply there — but until then, use the
explicit-HTTPS-URL method, not `git remote set-url` (which would be an
unnecessary git-config change).

## What files were changed this session

Created/rewritten:
- `docs/project-memory/POWERWAVE_DISCOVERY.md` — full discovery findings
  (was a skeleton).

Modified:
- `docs/project-memory/CURRENT_STATE.md` — reflects discovery completion,
  updated repository-identity/sync notes, updated blockers/next-activity.
- `docs/project-memory/HANDOFF.md` — this file.

(Earlier in the session, before this task: created the whole
`docs/project-memory/` framework and modified `CLAUDE.md`/`AGENTS.md` — see
Git history for that commit if needed; not repeated here per this
document's own "don't become a diary" rule.)

## What remains unresolved

- `[OPEN]` Nine open questions from the discovery audit need owner
  decisions — see "Open Questions" in
  [POWERWAVE_DISCOVERY.md](POWERWAVE_DISCOVERY.md) for the full list with
  context. None have been decided; none should be assumed resolved one way
  or the other.
- `[OPEN]` No migration phase, frontend/backend boundary, or first
  implementation slice is approved. All of it is `[PROPOSAL]` in
  [POWERWAVE_DISCOVERY.md](POWERWAVE_DISCOVERY.md), pending owner review.

## What should be done next

Per [POWERWAVE_DISCOVERY.md](POWERWAVE_DISCOVERY.md)'s own closing
recommendation: the project owner should review the document (especially
the Open Questions and Proposed Migration Phases sections), record any
approved direction in [DECISIONS.md](DECISIONS.md), and only then approve a
first implementation slice. No implementation should start before that.

## What must not be assumed

- Do not assume any `[PROPOSAL]` in
  [POWERWAVE_DISCOVERY.md](POWERWAVE_DISCOVERY.md) (migration phases,
  frontend/backend boundary, first slice) is approved — none of it has been
  transferred into [DECISIONS.md](DECISIONS.md).
- Do not assume `powerwave` is still at `3156392` by the time you read
  this — it is actively developed (it advanced twice during this very
  session). Re-verify against current `HEAD` before relying on specific
  line numbers or claims from the discovery document for anything beyond
  general architectural understanding; the document says this about itself
  too.
- Do not assume `oruxa_powerwave` must reproduce any specific `powerwave`
  behaviour — see [DECISIONS.md — DEC-001](DECISIONS.md#dec-001--migrate-and-evolve-powerwave-do-not-copy-paste-or-blindly-rewrite-it).
- Do not trust a locally-cached `origin/main` ref for `oruxa_powerwave` as
  proof of sync state on a machine with the same SSH problem — see the
  Git/GitHub sync section above.

## Owner approval needed before proceeding?

- Not needed to *read* or *discuss* the discovery findings.
- **Yes**, before recording any `[DECISION]` in
  [DECISIONS.md](DECISIONS.md), before approving any migration phase, and
  before any implementation work begins — per the change-governance rule in
  [CLAUDE.md](../../CLAUDE.md) / [AGENTS.md](../../AGENTS.md) and per the
  discovery document's own closing recommendation.
