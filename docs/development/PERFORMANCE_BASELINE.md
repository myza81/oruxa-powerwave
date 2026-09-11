# Performance baseline

Pre-Advanced Foundation Slice F2. A reproducible before/after reference
for real import/parse and waveform-retrieval performance, through the
actual application code path (real upload -> real parser -> real
in-memory registry -> real waveform endpoint), so future work (Event
Playback, protection plots, calculated-signal-heavy analysis, and
whatever comes after) can be measured against known, dated application
performance rather than guessed at.

**This document measures. It does not optimize.** No production code
changed to produce these numbers (see
[Production code changes](#production-code-changes-none) below). If a
future baseline run finds a genuinely concerning regression or a
production-code defect, that is reported separately, per the project's
existing change-governance rule (`CLAUDE.md`/`AGENTS.md`) -- never
silently fixed as a side effect of a benchmark run.

## What the pre-existing DEC-050 performance test does NOT cover

`backend/tests/test_dec050_slice8_performance.py` (unchanged by this
slice) measures ONE narrow thing: the Per-Unit conversion overhead
RATIO, at the `extract_waveform_range()` service-layer call, against an
`ActiveSource` already constructed directly in Python (no file, no
parser, no HTTP). It does not exercise: file upload, CFG/DAT or CSV
parsing, temp-file staging, the FastAPI HTTP layer, process memory, or
waveform response payload size. This slice adds exactly what that test
does not cover -- it does not replace or modify that test.

## Reproduction command

```bash
cd backend
python tests/perf/baseline_runner.py run --scenario medium_comtrade
python tests/perf/baseline_runner.py run --scenario large_comtrade
python tests/perf/baseline_runner.py run --scenario csv_medium
# or, all three in one invocation:
python tests/perf/baseline_runner.py run --scenario all
```

This is a **standalone script, not a pytest test** -- it is never
auto-collected by the normal `pytest tests/` regression run (see
[CI considerations](#ci-considerations) below), so a routine `pytest`
invocation never generates or processes a 50-100 MB fixture. Each
`run --scenario <name>` prints one JSON object to stdout with the full
measurement (the exact numbers this document's own
[Results](#results) table was built from).

Small, fast **correctness** tests for the same fixture generators and
pipeline (tens of KB, sub-second) DO run in normal regression --
`backend/tests/test_performance_baseline.py`.

## A. Benchmark design

Three scenarios, chosen to be representative rather than an exhaustive
matrix (per the task's own "prefer a small number of representative
scenarios" instruction):

| Scenario | Format | Channels | Sample rate | Target size |
|---|---|---|---|---|
| A -- medium recording | COMTRADE (BINARY) | 40 analog + 16 digital | 10 kHz | 15 MB |
| B -- large recording | COMTRADE (BINARY) | 64 analog + 32 digital | 20 kHz | 75 MB |
| C -- medium recording | CSV | 20 numeric channels | 5 kHz | 12 MB |

COMTRADE is prioritized (2 of 3 scenarios, including the only "large"
one) per the task's own stated priority; one CSV scenario demonstrates
the real, separate multi-step CSV ingestion pipeline (upload -> column
role assignment -> Time Axis confirmation -> convert) without doubling
the benchmark matrix for a format the task explicitly did not require
at both sizes. Excel was not benchmarked this slice -- not required,
and CSV already exercises the same underlying Data Preparation
conversion path (`preparation_conversion_service.py`) Excel shares.

No large binary fixture is committed to the repository. Every fixture
is generated deterministically into a temp directory at run time by
`backend/tests/perf/synthetic_comtrade.py` / `synthetic_csv.py`, and
discarded afterward.

### Why synthetic, and why these shapes

The repository's existing committed COMTRADE fixtures
(`backend/tests/fixtures/comtrade/*.cfg/.dat`) are all under 7 KB --
nowhere near the 10-100 MB range this slice needs, so a deterministic
generator was required (per the task's own instruction, rather than
committing a huge binary file).

- **BINARY DAT format**, not ASCII: the compact, common format real
  protection-grade recorders actually write, and the only way to reach
  a realistic file size without an absurd sample count.
- **Row layout copied verbatim** from
  `app.providers.comtrade._parse_binary_dat()`'s own documented format
  (`uint32(n) + uint32(ts) + int16*nA + uint16*nDw`, little-endian) --
  a generator/parser mismatch would surface immediately as a real parse
  failure in the correctness tests, not silently produce a
  non-representative benchmark.
- **Channel count/shape** (40-64 analog in 3-phase Voltage/Current
  banks, several digital channels) follows the task's own "20-100
  analog channels, several digital channels" guidance, and reuses the
  exact same `V{i}_R/Y/B` / `I{i}_R/Y/B` naming convention
  `test_dec050_slice8_performance.py`'s own `_large_active_source()`
  already established for a large synthetic analog set.
- **Sample count is DERIVED from the target file size and the row
  layout**, never hand-picked -- `n_samples = target_size_bytes //
  row_size_bytes`. Duration then falls out of `n_samples /
  sample_rate_hz` (documented per-scenario in the
  [Results](#results) table) rather than being independently chosen.
- **Every waveform value is a pure, seeded function of (sample index,
  channel index)** -- a fixed-frequency sinusoid per analog channel,
  a fixed-period toggle per digital channel. No `np.random` anywhere in
  the generated DATA (re-running the generator with the same parameters
  produces byte-identical output -- verified directly,
  `TestSyntheticComtradeFixtureGenerator/CsvFixtureGenerator::
  test_generated_fixture_is_deterministic`).
- **CSV row count** is similarly derived from a measured row's own
  encoded byte length (a two-pass estimate that accounts for the
  elapsed-time field growing a digit over the recording's duration),
  never a guessed row count.

## B. Metrics and methodology

### Wall-clock

`time.perf_counter()` (monotonic, high-resolution) around exactly the
operation being measured -- the HTTP `POST` for import, one `GET` for
each waveform request. Each scenario's `run` command reports a single
measurement (no repeat/median loop) -- adequate for an order-of-
magnitude baseline; a tighter statistical protocol was judged
disproportionate for this slice (task: "do not invent an elaborate
framework").

### Memory

**Exactly what the number means, stated explicitly (per the task's own
requirement) -- see `backend/tests/perf/mem_probe.py`'s own docstring
for the full reasoning:**

> **Peak RSS (Linux, `getrusage().ru_maxrss`) / peak working set size
> (Windows, `GetProcessMemoryInfo`)** -- an OS-reported, monotonically
> non-decreasing "high-water mark since process start," in bytes. NOT a
> delta. NOT a Python-allocation-only figure.

Neither `resource` (POSIX-only -- unavailable on this project's Windows
dev machines, where this baseline's first run happened) nor `psutil`
(not an existing dependency; the task instructs against adding one for
this benchmark alone) was usable on every environment this baseline
needs to run. `tracemalloc` (stdlib, genuinely cross-platform) was
considered and rejected: COMTRADE/CSV import is almost entirely
NumPy/pandas array allocation, and NumPy's C-level buffer allocator
does not route through CPython's tracked allocator `tracemalloc`
observes -- it would report a near-zero peak for exactly the
allocations this baseline cares about most. The chosen approach is
stdlib-only (`resource`/`ctypes`) on both platforms, and reports the
identical OS-level concept on each.

**Because it is a whole-process high-water mark, each scenario's
fixture GENERATION and its IMPORT/WAVEFORM measurement run in separate,
fresh subprocesses** (`baseline_runner.py`'s `gen-*` / `measure-*`
phases, orchestrated by `run`) -- otherwise generating a 75 MB
in-memory array before writing it to disk would inflate the "import"
peak-memory number with its own unrelated cost, and running scenario A
then scenario B in one long-lived process would let A's peak
contaminate B's reading (a monotonic high-water mark never resets).

A near-empty COMTRADE import (a smoke-test-scale ~52 KB fixture) was
also measured to establish this process's own fixed baseline footprint
(FastAPI/NumPy/pandas/Starlette import + TestClient/app startup, before
any real recording data is touched): **≈124 MB** peak working set on
this measurement machine. The "amplification factor" in the
[Results](#results) table is `(peak_memory - 124 MB) / file_size` --
memory attributable to this scenario's OWN data, over and above that
fixed process footprint.

### Waveform payload

`len(response.content)` on the real HTTP response object (`httpx`'s
`Response.content`, the exact serialized JSON bytes) -- never estimated
from Python object size, exactly as the task requires.

### Correctness (not performance) assertions, checked on every run

Import succeeds (`201`); analog/digital channel counts and sample count
match the generator's own known values exactly; the waveform request
succeeds (`200`); `returned_point_count > 0`; `time`/`values` arrays are
the same length as `returned_point_count`; the response payload is
non-empty. Any failure raises inside the measurement subprocess (a
non-zero exit), never silently degrading into a "measurement" with
wrong data.

## C. Results

Measured 2026-09-11, commit `0ae78b3`, on the environment described
under [Environment](#environment). **Single-run measurements on one
development machine -- see [Caveats](#caveats).**

| Scenario | Size | Channels | Samples | Import time | Peak memory | Waveform latency (full / reduced) | Payload (full / reduced) |
| -------- | ---: | -------: | ------: | ----------: | ----------: | ---------------------------------: | ------------------------: |
| A -- medium COMTRADE | 15.00 MB | 40 analog + 16 digital | 174,762 | 302 ms | 336.8 MB | 26.1 ms / 17.6 ms | 68.3 KB / 72.0 KB |
| B -- large COMTRADE | 75.00 MB | 64 analog + 32 digital | 561,737 | 1,657 ms | 1,213.6 MB | 45.0 ms / 34.3 ms | 64.1 KB / 76.3 KB |
| C -- medium CSV | 12.34 MB | 20 analog | 70,690 | 2,343 ms | 350.4 MB | 26.9 ms / 21.0 ms | 56.6 KB / 57.1 KB |

Additional detail per scenario:

- **A**: 10 kHz sample rate, 17.48 s duration. Full-range request
  returned a `min_max_envelope` (4,001 of 174,762 samples); the 2 s
  reduced-range request also returned an envelope (20,001 raw samples
  in that window, still over the 10,000-sample full-resolution
  threshold). Memory amplification over the ≈124 MB process baseline:
  **≈14.2x** file size.
- **B**: 20 kHz sample rate, 28.09 s duration. Full-range: envelope
  (4,002 of 561,737). Reduced-range (2 s window, 40,001 raw samples):
  envelope. Memory amplification: **≈14.5x** file size.
- **C**: 5 kHz sample rate, 14.14 s duration. Import time is
  `upload + column-role-configuration + convert` combined (131 ms +
  251 ms + 1,960 ms respectively) -- CSV's real parse cost is almost
  entirely in `convert` (`preparation_conversion_service.py`), not the
  initial byte upload. Full-range: envelope (4,001 of 70,690).
  Reduced-range (2 s window, 10,001 raw samples): envelope (right at
  the 10,000-sample threshold). Memory amplification: **≈18.4x** file
  size (CSV's row-oriented `csv.reader` + `WorkingOverlay` bookkeeping
  carries more intermediate Python object overhead than COMTRADE's
  direct vectorized binary read -- expected, not a defect).

Every scenario's correctness assertions (import success, exact
channel/sample counts, valid non-empty waveform response) passed.

## D. Interpretation

**Import performance: acceptable.** Even the largest scenario (75 MB,
562K samples, 64 analog + 32 digital channels) imports in under 1.7
seconds end-to-end through the real HTTP upload -> parse -> registry
path. This is well within an acceptable synchronous UI wait for a file
this size, and scales roughly linearly with size (0.3 s at 15 MB, 1.66
s at 75 MB -- a 5x size increase, 5.5x time increase).

**Memory behavior: acceptable, with a known, consistent amplification
factor.** Peak working set for the largest scenario (75 MB file) was
≈1.21 GB on this machine -- comfortably under the task's own example
"concerning" bar (100 MB import consuming >2 GB). The ≈14-18x
amplification factor (raw file bytes -> int16 DAT values -> float64
physical values -> a pandas DataFrame -> per-channel/per-source Python
object overhead) is consistent across both COMTRADE scenarios (14.2x,
14.5x) and is the expected cost of DEC-019's own "retain the full-
resolution `DisturbanceRecord` in memory" design, not a surprise this
slice discovered. CSV's higher factor (18.4x) is explained by its
additional `WorkingOverlay`/preparation-session bookkeeping layer,
which COMTRADE's direct-to-canonical import path does not have.

**Waveform API: looks suitable for a future playback consumer.** Every
measured waveform request -- full-range AND a 2-second reduced window,
across all three scenarios, including the 562K-sample file --
completed in under 50 ms and returned a payload of 55-80 KB. Critically,
**both latency and payload size stay small and roughly CONSTANT
regardless of the underlying recording's size**, because the existing
min/max envelope reduction (`FULL_RESOLUTION_DISPLAY_THRESHOLD =
10_000`, `DEFAULT_POINT_BUDGET = 4_000`) engages for every request in
this baseline once the requested range exceeds ~10,000 raw samples --
which it does even for a 2-second window on a 5-20 kHz recording. A
playback consumer issuing repeated windowed waveform requests as
playback advances should see this same bounded latency/payload
behavior, not a cost that grows with file size. No immediate
architectural concern surfaced by these measurements. **Caveat**: this
baseline measures one synchronous request at a time, in-process
(`TestClient`, no real network round trip, no concurrent-request
contention) -- a genuine playback implementation should still be
validated under its own realistic request cadence once built; this
baseline only establishes that the PER-REQUEST cost looks compatible,
not that a playback loop has been simulated (which the task explicitly
says not to do this slice).

**Headroom for the first advanced analytical feature: reasonable.**
Import for the largest scenario leaves the process at ≈1.2 GB peak
working set and completes in under 2 seconds -- there is substantial
headroom below both a multi-second wait and the >2 GB memory concern
threshold before a first advanced feature (operating on the already-
parsed in-memory data) would need its own investigation. This is not a
benchmark of any unimplemented algorithm -- only an observation that
today's baseline does not already consume the available budget.

**No immediate concern found.** Nothing in this baseline crossed the
task's own example "FOUND PERFORMANCE ISSUE" thresholds (100 MB
consuming >2 GB; an unexpectedly enormous waveform payload). CSV
`convert` being markedly slower per-MB than COMTRADE's binary import
(≈2.0 s for 12.3 MB / 70,690 rows, vs. COMTRADE's sub-second imports at
comparable-or-larger sizes) is a real, honestly-reported observation --
expected for row-oriented CSV text parsing vs. a vectorized binary
read, not "unexpectedly enormous," and well within an acceptable
synchronous upload wait for a file this size. Recorded here as an
observation for a future owner-prioritized CSV/Excel ingestion
performance pass, not raised as a blocking issue for this slice.

## E. Production code changes

**None.** Every file this slice adds or modifies is test
infrastructure or documentation:

- `backend/tests/perf/mem_probe.py` (new)
- `backend/tests/perf/synthetic_comtrade.py` (new)
- `backend/tests/perf/synthetic_csv.py` (new)
- `backend/tests/perf/baseline_runner.py` (new)
- `backend/tests/test_performance_baseline.py` (new)
- `docs/development/PERFORMANCE_BASELINE.md` (new, this document)
- `docs/project-memory/CURRENT_STATE.md` / `HANDOFF.md` (project
  memory)

No file under `backend/app/` (the actual application) changed.

## F. CI considerations

The 10-100 MB benchmark (`baseline_runner.py run --scenario ...`) is
**not** a pytest test and is **not** collected or run by the standard
`pytest tests/` regression (it lives in `tests/perf/`, none of its
files match pytest's `test_*.py` collection pattern) -- a routine test
run, in CI or locally, never generates or processes a large fixture.
It is an explicit, manually-invoked command (see
[Reproduction command](#reproduction-command)) -- no CI workflow change
was made or is required for this slice.

The small, fast correctness tests
(`backend/tests/test_performance_baseline.py`, sub-second, tens of KB)
DO run as part of normal regression, verifying the generators and
pipeline stay correct on every change without any performance cost to
routine CI runs.

## G. Environment

- **Date**: 2026-09-11
- **Commit**: `0ae78b3` (immediately prior to this slice's own commit)
- **Machine**: Windows 11 Pro (10.0.26200), Intel64 Family 6 Model 181
  (development laptop) -- see [Caveats](#caveats)
- **Python**: 3.14.4 (MSC v.1944 64 bit)
- **NumPy**: 2.4.6, **pandas**: 3.0.2, **FastAPI**: 0.141.1
- **CI**: GitHub Actions `ubuntu-latest` (`.github/workflows/ci.yml`) --
  these exact numbers were NOT reproduced on CI hardware for this
  slice; re-running the documented command there would use the POSIX
  `getrusage()` path in `mem_probe.py` instead of the Windows
  `GetProcessMemoryInfo` path, and will not exactly match the numbers
  above (see [Caveats](#caveats)).

## Caveats

- **Single-machine, single-run measurements.** These are a reference
  baseline for THIS machine/environment on THIS date, not a universal
  SLA or cross-machine guarantee -- re-running on different hardware,
  OS, or under CI load will produce different absolute numbers. Compare
  future runs against a freshly-reproduced baseline on comparable
  hardware, not against these numbers verbatim.
- **No repeated-run statistics.** Each measurement is one run, not a
  median/percentile over several -- adequate for an order-of-magnitude
  baseline, not for detecting a small (<20%) regression.
- **Windows vs. Linux memory metrics are analogous, not identical.**
  "Peak working set" (Windows) and "peak RSS" (Linux) are the same
  general OS concept but are not guaranteed numerically identical for
  the same workload -- do not directly compare a Windows-measured
  number against a future Linux-measured (CI) number as if they were
  the same metric.
- **In-process `TestClient`, not a real deployed server.** No real
  network round trip, no reverse proxy, no concurrent load -- these
  numbers isolate application-layer cost, not full deployed-request
  latency.
- **Synthetic data, not a real customer recording.** Deterministic
  sinusoid/toggle patterns exercise the real parser/reduction code
  paths structurally, but do not reproduce every real-world data
  irregularity (missing samples, multi-rate sections, unusual
  timestamps) a genuine field recording might contain.
