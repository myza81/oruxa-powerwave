"""Scenario runner for the frozen COMTRADE nominal-frequency baseline (RMS display R1A).

Not a test module (no `test_` prefix, same convention as `rms_baseline_scenarios.py`). Two callers share it so the
scenarios can never drift apart:

* `tests/fixtures/comtrade_frequency/generate_comtrade_frequency_baseline.py` runs every scenario ONCE against the
  pristine pre-R1A production tree and freezes the outcome in
  `tests/fixtures/comtrade_frequency/comtrade_frequency_baseline.json`.
* `tests/test_comtrade_frequency_baseline.py` re-runs the same scenarios against the code under test.

What is captured, per scenario: whether the parser accepted the file; the exception class and message; the Python
warnings it raised (category and message); the effective nominal frequency in `RecordingMetadata` and
`SamplingInformation`; the provenance dict returned by `load_with_provenance`; a SHA-256 fingerprint of the whole
parsed record (waveform samples and timestamps, channel descriptors, sampling and timing information); and, through
the real upload endpoint, the HTTP status, the source's effective nominal frequency, its stored
`preparation_provenance` and the `(frequency, origin)` pair the oscillation analysis derives from them.
"""

from __future__ import annotations

import hashlib
import re
import tempfile
import warnings
from pathlib import Path

import numpy as np

from app.domain.calculated_channel import nominal_frequency_valid
from app.providers.base import ProviderLoadError
from app.providers.comtrade import ComtradeProvider

HERE = Path(__file__).resolve().parent
FIXTURE_DIR = HERE / "fixtures" / "comtrade_frequency"
BASELINE_PATH = FIXTURE_DIR / "comtrade_frequency_baseline.json"
COMTRADE_FIXTURES = HERE / "fixtures" / "comtrade"

WS = "ws-comtrade-frequency"

_DAT = "1,0,0,0,0\n2,250,1000,-1000,0\n3,500,2000,-2000,1\n4,750,3000,-3000,1\n"

#: The 1999 CFG skeleton; `{lf}` is the whole nominal-frequency line.
_CFG_1999 = (
    "SYNTH_STATION,SYNTH_DEV,1999\n"
    "3,2A,1D\n"
    "1,VA,A,,V,0.1,0.0,0,-32767,32767,110.0,1.0,P\n"
    "2,IA,A,,A,0.01,0.0,0,-32767,32767,600.0,5.0,C\n"
    "1,BRK_A,,,0\n"
    "{lf}\n"
    "1\n"
    "4000.0,4\n"
    "06/03/2026,10:00:00.000000\n"
    "06/03/2026,10:00:00.005000\n"
    "ASCII\n"
    "1.0\n"
)

#: Same skeleton for the 1991 layout (no revision year, no timemult line).
_CFG_1991 = (
    "SYNTH_STATION,SYNTH_DEV\n"
    "3,2A,1D\n"
    "1,VA,A,,V,0.1,0.0,0,-32767,32767,110.0,1.0,P\n"
    "2,IA,A,,A,0.01,0.0,0,-32767,32767,600.0,5.0,C\n"
    "1,BRK_A,,,0\n"
    "{lf}\n"
    "1\n"
    "4000.0,4\n"
    "06/03/2026,10:00:00.000000\n"
    "06/03/2026,10:00:00.005000\n"
    "ASCII\n"
)

#: 2013 layout: revision year, timemult and the `time_code,local_code` line.
_CFG_2013 = (
    "SYNTH_STATION,SYNTH_DEV,2013\n"
    "3,2A,1D\n"
    "1,VA,A,,V,0.1,0.0,0,-32767,32767,110.0,1.0,P\n"
    "2,IA,A,,A,0.01,0.0,0,-32767,32767,600.0,5.0,C\n"
    "1,BRK_A,,,0\n"
    "{lf}\n"
    "1\n"
    "4000.0,4\n"
    "06/03/2026,10:00:00.000000\n"
    "06/03/2026,10:00:00.005000\n"
    "ASCII\n"
    "1.0\n"
    "+8h00,+8h00\n"
)

# (key, the whole lf line as written in the file). The line is stripped by the parser, so surrounding whitespace is
# included on purpose in a few variants.
LF_LINES: list[tuple[str, str]] = [
    # --- valid declared values ------------------------------------------------------------------------------
    ("declared_50", "50"),
    ("declared_50_0", "50.0"),
    ("declared_60", "60"),
    ("declared_60_0", "60.0"),
    ("declared_25", "25"),
    ("declared_16_7", "16.7"),
    ("declared_400", "400"),
    ("declared_1000", "1000"),
    ("declared_50_padded", "   50   "),
    ("declared_plus_50", "+50"),
    ("declared_exponent_5e1", "5e1"),
    ("declared_underscore_5_0", "5_0"),
    # --- declared but outside the RMS frequency-validation range (1..1000 Hz) --------------------------------
    ("declared_out_of_range_1001", "1001"),
    ("declared_out_of_range_0_5", "0.5"),
    ("declared_tiny", "1e-9"),
    ("declared_huge", "1e308"),
    # --- explicitly invalid numeric values that Python `float()` accepts -------------------------------------
    ("declared_zero", "0"),
    ("declared_zero_float", "0.0"),
    ("declared_negative_zero", "-0.0"),
    ("declared_negative_50", "-50"),
    ("declared_nan", "nan"),
    ("declared_nan_upper", "NaN"),
    ("declared_inf", "inf"),
    ("declared_negative_inf", "-inf"),
    ("declared_infinity_word", "Infinity"),
    ("declared_overflow_1e999", "1e999"),
    # --- unparseable by `float()`: the parser's fallback path -----------------------------------------------
    ("unparseable_text", "abc"),
    ("unparseable_unit_suffix", "50Hz"),
    ("unparseable_unit_suffix_spaced", "50 Hz"),
    ("unparseable_two_values_comma", "50,60"),
    ("unparseable_two_values_space", "50 60"),
    ("unparseable_trailing_comma", "50,"),
    ("unparseable_comma_decimal", "50,5"),
    ("unparseable_hex", "0x32"),
    ("unparseable_empty", ""),
    ("unparseable_whitespace_only", "    "),
    ("unparseable_only_comma", ","),
    ("unparseable_double_dot", "50..0"),
    ("unparseable_dash_only", "-"),
    ("unparseable_none_word", "None"),
    ("unparseable_superscript_digit", "5²"),
]

# (key, builder name, lf text): the other CFG layouts, so the fallback is exercised for every revision.
LAYOUT_VARIANTS: list[tuple[str, str, str]] = [
    ("rev1991_declared_60", "1991", "60"),
    ("rev1991_unparseable", "1991", "abc"),
    ("rev1991_empty", "1991", ""),
    ("rev2013_declared_60", "2013", "60"),
    ("rev2013_unparseable", "2013", "abc"),
    ("rev2013_empty", "2013", ""),
]

_SKELETONS = {"1999": _CFG_1999, "1991": _CFG_1991, "2013": _CFG_2013}


def build_variants() -> dict[str, str]:
    """Every scenario's CFG text, keyed by scenario name."""
    out: dict[str, str] = {}
    for key, lf in LF_LINES:
        out[key] = _CFG_1999.format(lf=lf)
    for key, layout, lf in LAYOUT_VARIANTS:
        out[key] = _SKELETONS[layout].format(lf=lf)

    # The lf line absent altogether (truncated file, and the line removed with the rest shifted up).
    lines = _CFG_1999.format(lf="50").splitlines()
    lf_index = lines.index("50")
    out["missing_lf_line_removed"] = "\n".join(lines[:lf_index] + lines[lf_index + 1:]) + "\n"
    out["missing_lf_file_truncated"] = "\n".join(lines[:lf_index]) + "\n"

    # Other fallback paths the parser has, which must not be mistaken for a frequency substitution.
    out["other_unrecognised_rev_yr_declared_60"] = _CFG_1999.format(lf="60").replace(",1999\n", ",ABCD\n", 1)
    out["other_unrecognised_rev_yr_unparseable_lf"] = _CFG_1999.format(lf="abc").replace(",1999\n", ",ABCD\n", 1)
    out["other_nonstandard_rev_yr_2005_declared_60"] = _CFG_1999.format(lf="60").replace(",1999\n", ",2005\n", 1)
    out["other_unparseable_timemult_declared_60"] = _CFG_1999.format(lf="60").replace("ASCII\n1.0\n", "ASCII\nx\n", 1)
    out["other_binary32_declared_60"] = _CFG_1999.format(lf="60").replace("ASCII\n", "BINARY32\n", 1)
    out["other_bad_nrates"] = _CFG_1999.format(lf="60").replace("\n1\n4000.0,4\n", "\nx\n4000.0,4\n", 1)
    return out


def _normalise_text(text: str, cfg_path: Path) -> str:
    # `repr()` doubles the backslashes of a Windows path, so replace both spellings.
    for spelling in (str(cfg_path), str(cfg_path).replace("\\", "\\\\")):
        text = text.replace(spelling, "<CFG>")
    for spelling in (str(cfg_path.parent), str(cfg_path.parent).replace("\\", "\\\\")):
        text = text.replace(spelling, "<DIR>")
    return text


def _number(value) -> object:
    """JSON-safe and exact: floats (including NaN and inf) are written via repr so nothing is rounded away."""
    if isinstance(value, float):
        return repr(value)
    return value


_TEMP_PATH = re.compile(r"[A-Za-z]:[\\/][^'\"]*?event\.(?:cfg|dat)")


def _json_safe(value):
    if isinstance(value, str):
        return _TEMP_PATH.sub("<FILE>", value)
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, float):
        return _number(value)
    return value


def record_fingerprint(record, cfg_path: Path) -> str:
    """SHA-256 over every observable part of the parsed record except the (temporary) source path."""
    digest = hashlib.sha256()
    data = record.waveform_data
    digest.update(repr(list(data.columns)).encode())
    for column in data.columns:
        digest.update(np.ascontiguousarray(data[column].to_numpy()).tobytes())
    digest.update(_normalise_text(repr(record.analog_channels), cfg_path).encode())
    digest.update(_normalise_text(repr(record.digital_channels), cfg_path).encode())
    digest.update(_normalise_text(repr(record.sampling_info), cfg_path).encode())
    digest.update(_normalise_text(repr(record.timing_info), cfg_path).encode())
    digest.update(_normalise_text(repr(record.metadata), cfg_path).encode())
    return digest.hexdigest()


def run_parser(cfg_text: str) -> dict:
    """Load one CFG through `ComtradeProvider.load_with_provenance` and report everything observable."""
    with tempfile.TemporaryDirectory(prefix="oruxa-comtrade-freq-") as tmp:
        cfg_path = Path(tmp) / "e.cfg"
        cfg_path.write_bytes(cfg_text.encode("latin-1"))
        (Path(tmp) / "e.dat").write_text(_DAT)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            try:
                record, provenance = ComtradeProvider().load_with_provenance(cfg_path)
                outcome: dict = {
                    "accepted": True,
                    "metadata_nominal_frequency": _number(record.metadata.nominal_frequency),
                    "sampling_nominal_frequency": _number(record.sampling_info.nominal_frequency),
                    "provenance": _json_safe(provenance),
                    "record_sha256": record_fingerprint(record, cfg_path),
                    "frequency_valid_for_rms": bool(nominal_frequency_valid(record.metadata.nominal_frequency)),
                }
            except ProviderLoadError as exc:
                outcome = {"accepted": False, "exception": type(exc).__name__, "message": _normalise_text(str(exc), cfg_path)}
            except Exception as exc:  # noqa: BLE001 -- an unexpected exception is behaviour worth freezing
                outcome = {"accepted": False, "exception": type(exc).__name__, "message": _normalise_text(str(exc), cfg_path)}
        outcome["warnings"] = [
            {"category": w.category.__name__, "message": _normalise_text(str(w.message), cfg_path)} for w in caught
        ]
        return outcome


def run_parser_scenarios() -> dict[str, dict]:
    return {key: run_parser(text) for key, text in build_variants().items()}


def run_fixture_sweep() -> dict[str, dict]:
    """Every checked-in COMTRADE fixture: nominal frequency, provenance and whole-record fingerprint."""
    out: dict[str, dict] = {}
    for cfg in sorted(COMTRADE_FIXTURES.glob("*.cfg")):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            try:
                record, provenance = ComtradeProvider().load_with_provenance(cfg)
                out[cfg.name] = {
                    "accepted": True,
                    "metadata_nominal_frequency": _number(record.metadata.nominal_frequency),
                    "provenance": _json_safe(provenance),
                    "record_sha256": record_fingerprint(record, cfg),
                }
            except Exception as exc:  # noqa: BLE001
                out[cfg.name] = {"accepted": False, "exception": type(exc).__name__, "message": _normalise_text(str(exc), cfg)}
        out[cfg.name]["warnings"] = [
            {"category": w.category.__name__, "message": _normalise_text(str(w.message), cfg)} for w in caught
        ]
    return out


def run_api_scenarios(client) -> dict[str, dict]:
    """Upload each parseable variant through the real source-import endpoint and read back what the application
    stores: the effective nominal frequency, `preparation_provenance`, the response body keys, and the
    `(frequency, origin)` pair the oscillation analysis derives (the existing consumer of the provenance flag)."""
    from app.services.oscillation_representation_service import _nominal_frequency

    out: dict[str, dict] = {}
    for key, text in build_variants().items():
        files = {"cfg_file": ("e.cfg", text.encode("latin-1"), "application/octet-stream"),
                 "dat_file": ("e.dat", _DAT.encode(), "application/octet-stream")}
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            response = client.post(f"/api/v1/workspaces/{WS}/sources", files=files)
        entry: dict = {"status": response.status_code}
        if response.status_code == 200 or response.status_code == 201:
            body = response.json()
            entry["response_keys"] = sorted(body)
            entry["response_nominal_frequency"] = _json_safe(body.get("nominal_frequency"))
            active = client.app.state.workspace_registry.get(WS, body["source_id"])
            entry["stored_nominal_frequency"] = _number(active.metadata.nominal_frequency)
            entry["stored_preparation_provenance"] = _json_safe(active.metadata.preparation_provenance)
            freq, origin = _nominal_frequency(active)
            entry["oscillation_frequency_and_origin"] = [_number(freq), origin]
        else:
            body = response.json()
            entry["error"] = _json_safe(body.get("detail", body)) if isinstance(body, dict) else None
        out[key] = entry
    return out
