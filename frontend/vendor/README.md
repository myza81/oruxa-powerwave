# Vendored libraries — waveform preview only

This is a pre-built, minified library bundle vendored as a plain static
file (no npm/build step anywhere in this project — see
`docs/architecture/oruxa-architecture.md`), used **only** by
`waveform-prototype.html` (the isolated single-channel waveform preview,
not the main application) — nothing else in the frontend references it.

| Directory | Library | Version | License | Source |
|---|---|---|---|---|
| `plotly/` | [Plotly.js (cartesian-only build)](https://github.com/plotly/plotly.js) | 3.7.0 | MIT | npm `plotly.js-cartesian-dist-min`, `plotly-cartesian.min.js` |

Plotly's **cartesian-only** distribution was used deliberately, not the
full `plotly.js` bundle — the preview only needs line/scatter charts (no
3D, maps, or other trace types Plotly otherwise bundles), and the
cartesian build is roughly a third of the full bundle's size.

`plotly/LICENSE` is the vendored library's unmodified upstream license
text.

## History

This directory originally held two candidates (`uplot/` and `plotly/`)
during Phase 2B's renderer UAT. Following the owner's hands-on comparison,
**Plotly.js was selected** as the waveform rendering foundation
(DEC-022, `docs/project-memory/DECISIONS.md`) and `uplot/` was removed —
see `docs/project-memory/MIGRATION_PLAN.md`'s Phase 2B closure record for
the full comparison history and rationale. If a future phase ever
reconsiders the renderer, this history (and the removed adapter's shape)
is recoverable from Git history at the commit that removed it, not
preserved here.
