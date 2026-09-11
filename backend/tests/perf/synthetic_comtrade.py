"""Deterministic synthetic COMTRADE (CFG/DAT) fixture generator for the
performance baseline (Pre-Advanced Foundation Slice F2).

Produces a real, valid COMTRADE 1999 BINARY CFG/DAT pair that exercises
the exact SAME parser path as any real recorder file
(`app.providers.comtrade.ComtradeProvider.load()` ->
`_parse_cfg()`/`_parse_binary_dat()`) -- this generator writes the CFG
text fields and the DAT binary row layout by hand rather than going
through the provider itself, but the row layout is copied verbatim from
`_parse_binary_dat()`'s own documented format (`uint32(n) + uint32(ts)
+ int16*nA + uint16*nDw`, little-endian throughout), so a mismatch
would surface immediately as a real parse failure in the correctness
tests, not silently.

BINARY format was chosen over ASCII deliberately: it is the compact,
common format real protection-grade recorders actually write (2 bytes/
sample/analog-channel vs. ASCII's ~6-10 comma-separated decimal
characters), and is what this baseline needs to reach realistic 10-100
MB file sizes without an absurd sample count.

Every value is a pure function of (sample index, channel index, seed) --
`np.random.default_rng` is never used for the WAVEFORM data itself (only
available for future extension, not used today), so re-running this
generator with the same parameters always produces byte-identical
output.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np

_NOMINAL_FREQUENCY_HZ = 50.0
_START_TIME = datetime(2026, 1, 1, 10, 0, 0, 0)


@dataclass(frozen=True, slots=True)
class ComtradeFixtureInfo:
    cfg_path: Path
    dat_path: Path
    n_analog: int
    n_digital: int
    sample_rate_hz: float
    n_samples: int
    duration_seconds: float
    cfg_size_bytes: int
    dat_size_bytes: int
    total_size_bytes: int
    analog_channel_names: list[str]
    digital_channel_names: list[str]
    row_size_bytes: int


def _analog_channel_plan(n_analog: int) -> list[tuple[str, str, float, str]]:
    """One (name, unit, scale_a, kind) tuple per analog channel, grouped
    in 3-phase (R/Y/B) Voltage/Current banks -- the SAME naming
    convention `test_dec050_slice8_performance.py`'s own
    `_large_active_source()` already uses for a large synthetic analog
    set, reused here rather than inventing a second convention."""
    plan: list[tuple[str, str, float, str]] = []
    bank = 0
    while len(plan) < n_analog:
        is_voltage = (bank % 2) == 0
        prefix = "V" if is_voltage else "I"
        unit = "V" if is_voltage else "A"
        scale_a = 0.1 if is_voltage else 0.01
        kind = "Voltage" if is_voltage else "Current"
        for phase in ("R", "Y", "B"):
            if len(plan) >= n_analog:
                break
            plan.append((f"{prefix}{bank // 2}_{phase}", unit, scale_a, kind))
        bank += 1
    return plan


def _write_cfg(
    cfg_path: Path,
    *,
    analog_plan: list[tuple[str, str, float, str]],
    n_digital: int,
    sample_rate_hz: float,
    n_samples: int,
) -> None:
    lines: list[str] = []
    lines.append("PERFBASE_STATION,PERFBASE_DEV,1999")
    lines.append(f"{len(analog_plan) + n_digital},{len(analog_plan)}A,{n_digital}D")
    for i, (name, unit, scale_a, _kind) in enumerate(analog_plan, start=1):
        # Field order (COMTRADE 1999, 13 fields): An#,ch_id,ph,ccbm,uu,
        # a,b,skew,min,max,primary,secondary,PS -- see
        # app.providers.comtrade._parse_analog_line's own docstring.
        lines.append(f"{i},{name},,,{unit},{scale_a},0.0,0,-32767,32767,1.0,1.0,P")
    for i in range(1, n_digital + 1):
        lines.append(f"{i},D{i},,,0")
    lines.append(f"{_NOMINAL_FREQUENCY_HZ}")
    lines.append("1")
    lines.append(f"{sample_rate_hz},{n_samples}")
    lines.append(_START_TIME.strftime("%d/%m/%Y,%H:%M:%S.%f"))
    lines.append(_START_TIME.strftime("%d/%m/%Y,%H:%M:%S.%f"))
    lines.append("BINARY")
    lines.append("1.0")
    lines.append("")
    cfg_path.write_text("\n".join(lines), encoding="ascii")


def _write_dat_binary(
    dat_path: Path,
    *,
    n_analog: int,
    n_digital: int,
    sample_rate_hz: float,
    n_samples: int,
    analog_kinds: list[str],
) -> int:
    """Vectorized construction of the exact structured-array layout
    `app.providers.comtrade._parse_binary_dat()` reads, written with one
    `ndarray.tofile()` call. Returns the row size in bytes."""
    n_dwords = math.ceil(n_digital / 16) if n_digital > 0 else 0
    row_size = 8 + 2 * n_analog + 2 * n_dwords

    dtype_fields: list[tuple] = [("n", "<u4"), ("ts", "<u4")]
    if n_analog > 0:
        dtype_fields.append(("ana", "<i2", (n_analog,)))
    if n_dwords > 0:
        dtype_fields.append(("dw", "<u2", (n_dwords,)))
    dt = np.dtype(dtype_fields)

    rows = np.zeros(n_samples, dtype=dt)
    idx = np.arange(n_samples, dtype=np.uint32)
    rows["n"] = idx + 1
    t = idx.astype(np.float64) / sample_rate_hz
    rows["ts"] = np.round(t * 1_000_000).astype(np.uint32)

    if n_analog > 0:
        # Deterministic per-channel sinusoid at the nominal power-system
        # frequency, amplitude/phase varied by channel index only (never
        # `np.random`) -- a fixed, reproducible waveform shape, computed
        # one channel at a time (never one (n_samples, n_analog) float64
        # intermediate) so memory stays O(n_samples), not O(n_samples *
        # n_analog).
        for ch in range(n_analog):
            amplitude = 20000.0 if analog_kinds[ch] == "Voltage" else 15000.0
            phase_rad = (ch % 12) * (math.pi / 6.0)
            raw = amplitude * np.sin(2.0 * math.pi * _NOMINAL_FREQUENCY_HZ * t + phase_rad)
            rows["ana"][:, ch] = np.round(raw).astype(np.int16)

    if n_digital > 0:
        # Each digital channel toggles on a deterministic, channel-
        # specific period -- exercises the real bit-packing/unpacking
        # path (`_extract_digital_channels`) with genuinely varying
        # (not all-zero, not all-one) states.
        for ch in range(n_digital):
            period = 500 + ch * 97
            bit_state = ((idx // period) % 2).astype(np.uint16)
            word_index = ch // 16
            bit_index = ch % 16
            rows["dw"][:, word_index] |= bit_state << np.uint16(bit_index)

    rows.tofile(dat_path)
    return row_size


def generate_comtrade_fixture(
    out_dir: Path,
    *,
    n_analog: int,
    n_digital: int,
    sample_rate_hz: float,
    target_size_bytes: int,
    stem: str = "event",
) -> ComtradeFixtureInfo:
    """Generate a deterministic CFG/DAT pair into `out_dir`, sized so the
    DAT file is as close as possible to (never over) `target_size_bytes`
    -- `n_samples` is DERIVED from the target size and the row layout,
    never hand-picked, so the actual resulting size is reproducible from
    these parameters alone."""
    out_dir.mkdir(parents=True, exist_ok=True)
    analog_plan = _analog_channel_plan(n_analog)
    analog_kinds = [kind for (_name, _unit, _a, kind) in analog_plan]

    n_dwords = math.ceil(n_digital / 16) if n_digital > 0 else 0
    row_size = 8 + 2 * n_analog + 2 * n_dwords
    n_samples = max(int(target_size_bytes // row_size), 1)

    cfg_path = out_dir / f"{stem}.cfg"
    dat_path = out_dir / f"{stem}.dat"

    _write_cfg(
        cfg_path,
        analog_plan=analog_plan,
        n_digital=n_digital,
        sample_rate_hz=sample_rate_hz,
        n_samples=n_samples,
    )
    _write_dat_binary(
        dat_path,
        n_analog=n_analog,
        n_digital=n_digital,
        sample_rate_hz=sample_rate_hz,
        n_samples=n_samples,
        analog_kinds=analog_kinds,
    )

    cfg_size = cfg_path.stat().st_size
    dat_size = dat_path.stat().st_size

    return ComtradeFixtureInfo(
        cfg_path=cfg_path,
        dat_path=dat_path,
        n_analog=n_analog,
        n_digital=n_digital,
        sample_rate_hz=sample_rate_hz,
        n_samples=n_samples,
        duration_seconds=n_samples / sample_rate_hz,
        cfg_size_bytes=cfg_size,
        dat_size_bytes=dat_size,
        total_size_bytes=cfg_size + dat_size,
        analog_channel_names=[name for (name, _u, _a, _k) in analog_plan],
        digital_channel_names=[f"D{i}" for i in range(1, n_digital + 1)],
        row_size_bytes=row_size,
    )
