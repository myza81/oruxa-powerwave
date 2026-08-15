# Vendored libraries — Phase 2B renderer UAT only

These are pre-built, minified library bundles vendored as plain static
files (no npm/build step anywhere in this project — see
`docs/architecture/oruxa-architecture.md`), used **only** by
`waveform-prototype.html` (Phase 2B's isolated renderer-comparison
prototype, not the main application). If the owner's UAT eliminates a
candidate, delete its subdirectory here and the corresponding adapter in
`waveform-prototype.html` — nothing else in the frontend references these
files.

| Directory | Library | Version | License | Source |
|---|---|---|---|---|
| `uplot/` | [uPlot](https://github.com/leeoniya/uPlot) | 1.6.32 | MIT | npm `uplot`, `dist/uPlot.iife.min.js` + `dist/uPlot.min.css` |
| `plotly/` | [Plotly.js (cartesian-only build)](https://github.com/plotly/plotly.js) | 3.7.0 | MIT | npm `plotly.js-cartesian-dist-min`, `plotly-cartesian.min.js` |

Plotly's **cartesian-only** distribution was used deliberately, not the
full `plotly.js` bundle — this prototype only needs line/scatter charts
(no 3D, maps, or other trace types Plotly otherwise bundles), and the
cartesian build is roughly a third of the full bundle's size. See
`docs/project-memory/MIGRATION_PLAN.md`'s Phase 2B record for the measured
size comparison against uPlot.

Each subdirectory's own `LICENSE` file is the vendored library's
unmodified upstream license text.
