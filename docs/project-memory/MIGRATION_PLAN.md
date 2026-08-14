# Migration Plan — `powerwave` → `oruxa_powerwave`

This document answers:

> **How do we currently intend to get from `powerwave` to `oruxa_powerwave`?**

It is sequencing/direction, not discovery (see
[POWERWAVE_DISCOVERY.md](POWERWAVE_DISCOVERY.md) for what `powerwave`
actually does) and not the decision log itself (see
[DECISIONS.md](DECISIONS.md) for what has been approved). This document
stays high level until the discovery audit is complete; detailed phases are
not invented ahead of that evidence.

## Governing principle

`[DECISION]` See [DECISIONS.md — DEC-001](DECISIONS.md#dec-001--migrate-and-evolve-powerwave-do-not-copy-paste-or-blindly-rewrite-it):
`oruxa_powerwave` will retain many capabilities from `powerwave`, but
workflows, UI/UX, architecture, and selected functionality may intentionally
differ. This is not a copy-and-paste conversion, and existing `powerwave`
behaviour must not automatically be assumed to be the correct future
behaviour for `oruxa_powerwave`.

Where mature engineering logic already exists in `powerwave` and is suitable
for reuse, the project prefers reuse or controlled extraction over
unnecessary reimplementation — but this is a preference to weigh per
subsystem once discovery evidence exists, not a blanket mandate to port
everything.

## Current migration objective

`[FACT]` The immediate objective, as of 2026-08-14, is **discovery**: build a
detailed technical understanding of `powerwave` (see
[POWERWAVE_DISCOVERY.md](POWERWAVE_DISCOVERY.md)) before deciding how to
migrate its functionality. No implementation phases are approved yet.

## Phases

`[OPEN]` Phase definitions are intentionally not written yet. Per the task
that established this framework: *"Do not invent detailed implementation
phases before the discovery audit is completed."* Once discovery is complete
and phase proposals are reviewed, this section will separate:

- **Proposed phases** — drafted from discovery evidence, not yet approved.
- **Approved phases** — explicitly signed off by the project owner.
- **In progress phases** — approved phases currently being implemented.
- **Completed phases** — approved phases that have shipped.

Until then, this section stays empty rather than pre-filled with placeholder
phases that could be mistaken for approved direction.

## Next planned discovery activity

`[FACT]` Run the detailed `powerwave` → `oruxa_powerwave` discovery audit and
populate [POWERWAVE_DISCOVERY.md](POWERWAVE_DISCOVERY.md). A first pass was
partially run on 2026-08-14 and did not complete (see
[HANDOFF.md](HANDOFF.md)); it needs to be resumed/redone as its own task, not
folded into this plan ahead of time.
