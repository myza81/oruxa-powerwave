"""Scenario runner for the frozen Calculated Channels RMS behavioural baseline
(RMS display R0).

Not a test module (no `test_` prefix, same convention as
`relay_api_helpers.py`). Two callers share it so the scenarios can never drift
apart:

* `tests/fixtures/rms_golden/generate_rms_service_baseline.py` runs every
  scenario ONCE against the pristine pre-R0 production tree and freezes the
  outcome in `tests/fixtures/rms_golden/service_behaviour_baseline.json`.
* `tests/test_rms_service_behaviour_baseline.py` re-runs the same scenarios
  against the code under test and requires an identical outcome.

What is captured (per scenario): eligibility status / reason / override
requirement; exception class, code, message and attributes; the HTTP status
and normalised JSON body for the API scenarios; the created channel's
metadata and provenance; and SHA-256 hashes of the raw bytes of the result
samples and timestamps. Validation precedence is captured by the multi-failure
scenarios.

Inputs come from the FROZEN `rms_golden_vectors.npz` (not regenerated), so a
different libm on another platform cannot change what is being compared.
"""

from __future__ import annotations

import hashlib
import io
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from app.domain.calculated_channel import (
    ESTIMATION_METHOD_HOLD_LAST,
    ESTIMATION_METHOD_LINEAR,
    ESTIMATION_METHOD_LOCAL_MEAN,
    ESTIMATION_METHOD_NEAREST,
    ESTIMATION_METHOD_PCHIP,
    NULL_POLICY_ESTIMATE,
    NULL_POLICY_PROPAGATE,
    NULL_POLICY_REQUIRE_MANUAL,
    NULL_POLICY_ZERO,
    OP_ABSOLUTE_VALUE,
    OP_ADDITION,
    OP_MULTIPLY_CONSTANT,
    OP_REVERSE_POLARITY,
    OP_RMS,
    OP_SUBTRACTION,
    ChannelRef,
)
from app.domain.channel_classification import (
    WAVEFORM_FORM_INSTANTANEOUS,
    WAVEFORM_FORM_MAGNITUDE,
    WAVEFORM_FORM_RMS,
    WAVEFORM_FORM_UNKNOWN,
)
from app.domain.channels import AnalogChannel
from app.domain.disturbance_record import DisturbanceRecord
from app.domain.metadata import FORMAT_VARIANT_BEN5K_LEGACY, RecordingMetadata
from app.domain.physical_calibration import (
    CALIBRATION_INVALID,
    CALIBRATION_UNVERIFIED,
    CALIBRATION_VERIFIED,
    PhysicalCalibrationAuthority,
)
from app.domain.source import ActiveSource, AnalogChannelSummary, SourceMetadata
from app.domain.timing import SamplingInformation, TimingInformation
from app.services.calculated_channel_registry import CalculatedChannelRegistry
from app.services.calculated_channel_service import (
    check_rms_eligibility,
    create_calculated_channel,
    extract_calculated_waveform_range,
)
from app.services.workspace_registry import WorkspaceRegistry

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "rms_golden"
VECTORS_PATH = FIXTURE_DIR / "rms_golden_vectors.npz"
MANIFEST_PATH = FIXTURE_DIR / "manifest.json"
SERVICE_BASELINE_PATH = FIXTURE_DIR / "service_behaviour_baseline.json"

WS = "ws-rms-baseline"
BASE_START = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
NOT_SET = object()
DEFAULT = object()

_AUTHORITIES = {
    "verified": PhysicalCalibrationAuthority(
        status=CALIBRATION_VERIFIED, reason="lab_verified_crosscheck", transform_id="ben5k_v1_raw_s16_linear_scale_offset"),
    "unverified": PhysicalCalibrationAuthority(
        status=CALIBRATION_UNVERIFIED, reason="ben5k_absolute_calibration_unverified",
        transform_id="ben5k_v1_raw_s16_linear_scale_offset"),
    "invalid": PhysicalCalibrationAuthority(
        status=CALIBRATION_INVALID, reason="transform_id_mismatch_invalidated",
        transform_id="ben5k_v1_raw_s16_linear_scale_offset"),
}


# ---------------------------------------------------------------------------
# Frozen inputs
# ---------------------------------------------------------------------------

_VECTORS_CACHE: dict[str, tuple[np.ndarray, np.ndarray]] | None = None


def load_service_inputs() -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """`{name: (time, values)}` for every frozen `svc_*` input."""
    global _VECTORS_CACHE
    if _VECTORS_CACHE is None:
        with np.load(VECTORS_PATH) as data:
            names = sorted({key.split("__")[0] for key in data.files if key.startswith("svc_")})
            _VECTORS_CACHE = {n: (data[f"{n}__time"].copy(), data[f"{n}__values"].copy()) for n in names}
    return _VECTORS_CACHE


# ---------------------------------------------------------------------------
# Source construction (mirrors the established service-test patterns)
# ---------------------------------------------------------------------------


def build_source(
    source_id: str, time: np.ndarray, values: np.ndarray, *, channel: str = "VA", unit: str = "kV",
    form: str = WAVEFORM_FORM_UNKNOWN, engineering_type: str = "Voltage",
    ben5k: bool = False, authority=NOT_SET, with_record_channel: bool = True, extra_channels: dict | None = None,
) -> ActiveSource:
    """`authority=NOT_SET` and `ben5k=False` reproduces the plain COMTRADE-style
    fixture (empty `record.analog_channels`, calibration not assessed). Otherwise
    a full `AnalogChannel` carrying `authority` (a key of `_AUTHORITIES`, or
    `None` for an absent authority) is attached, optionally on a BEN5K record."""
    channels = {channel: values, **(extra_channels or {})}
    record_channels = []
    if authority is not NOT_SET or ben5k:
        if with_record_channel:
            auth = None if authority in (NOT_SET, None) else _AUTHORITIES[authority]
            record_channels = [AnalogChannel(name=channel, unit=unit, index=0, calibration_authority=auth)]
    record = DisturbanceRecord(
        metadata=RecordingMetadata(
            station_name="SYNTH", recorder_name="TEST", source_file="synthetic.cfg",
            provider_type="BEN" if ben5k else "COMTRADE", nominal_frequency=50.0,
            format_variant=FORMAT_VARIANT_BEN5K_LEGACY if ben5k else None,
        ),
        waveform_data=pd.DataFrame({"time": time, **channels}),
        analog_channels=record_channels, digital_channels=[],
        sampling_info=SamplingInformation(sampling_rates=[1.0], samples_per_rate=[len(time)]),
        timing_info=TimingInformation(start_time=BASE_START, trigger_time=BASE_START),
    )
    metadata = SourceMetadata(
        source_id=source_id, workspace_id=WS, provider_type="BEN" if ben5k else "COMTRADE",
        original_filenames=("synthetic.cfg", "synthetic.dat"), created_at=BASE_START,
        station_name="SYNTH", recorder_name="TEST", nominal_frequency=50.0,
        timing_reference="absolute", start_time=BASE_START, trigger_time=BASE_START,
        sample_count=len(time), duration_seconds=float(time[-1] - time[0]) if len(time) else 0.0,
        elapsed_start_seconds=float(time[0]) if len(time) else 0.0,
        elapsed_end_seconds=float(time[-1]) if len(time) else 0.0,
        sampling_rates=(1.0,), samples_per_rate=(len(time),),
        analog_channels=[
            AnalogChannelSummary(
                name=name, index=i, unit=unit, engineering_type=engineering_type,
                waveform_form=form,
            )
            for i, name in enumerate(channels)
        ],
        digital_channels=[],
    )
    return ActiveSource(metadata=metadata, record=record)


class Env:
    """One fresh pair of registries per scenario."""

    def __init__(self) -> None:
        self.sources = WorkspaceRegistry()
        self.calcs = CalculatedChannelRegistry()

    def add(self, source: ActiveSource) -> None:
        self.sources.add(source)

    def ref(self, source_id: str = "src1", channel: str = "VA") -> ChannelRef:
        return ChannelRef(kind="source", source_id=source_id, channel_name=channel)


# ---------------------------------------------------------------------------
# Snapshots
# ---------------------------------------------------------------------------


def _sha(array) -> str:
    return hashlib.sha256(np.ascontiguousarray(array).tobytes()).hexdigest()


def snap_exception(exc: BaseException) -> dict:
    out = {"type": type(exc).__name__, "message": getattr(exc, "message", None) or str(exc)}
    for attr in ("code", "reason", "input_ref"):
        if hasattr(exc, attr):
            out[attr] = getattr(exc, attr)
    return out


def snap_eligibility(result) -> dict:
    return {"status": result.status, "reason": result.reason, "override_required": result.override_required}


def _ref_label(ref: ChannelRef, env: Env, workspace: str = WS) -> str:
    if ref.kind == "source":
        return f"source:{ref.source_id}:{ref.channel_name}"
    channel = env.calcs.get(workspace, ref.calculated_channel_id)
    return f"calculated:{channel.name if channel else '?'}"


def snap_channel(channel, env: Env) -> dict:
    return {
        "name": channel.name, "unit": channel.unit, "operation": channel.operation,
        "inputs": [_ref_label(r, env) for r in channel.inputs],
        "parameters": channel.parameters,
        "dependency_ids_count": len(channel.dependency_ids),
        "reference_source_id": channel.reference_source_id,
        "engineering_type": channel.engineering_type, "waveform_form": channel.waveform_form,
        "null_policy": channel.null_policy, "estimation_method": channel.estimation_method,
        "max_gap_value": channel.max_gap_value, "max_gap_unit": channel.max_gap_unit,
        "local_mean_radius": channel.local_mean_radius,
        "voltage_representation": channel.voltage_representation, "phase_member": channel.phase_member,
        "creation_batch_id": channel.creation_batch_id,
        "time": {"dtype": str(channel.time.dtype), "shape": list(channel.time.shape), "sha256": _sha(channel.time)},
        "values": {
            "dtype": str(channel.values.dtype), "shape": list(channel.values.shape), "sha256": _sha(channel.values),
            "nan_count": int(np.isnan(channel.values).sum()),
            "first_finite_index": int(np.argmax(np.isfinite(channel.values))) if np.isfinite(channel.values).any() else None,
        },
    }


def attempt_create(env: Env, *, name="RMS(VA)", inputs=None, parameters=DEFAULT, override=False, **kwargs) -> dict:
    inputs = inputs if inputs is not None else [env.ref()]
    if parameters is DEFAULT:
        parameters = {"nominal_frequency_hz": 50.0}
    try:
        channel = create_calculated_channel(
            workspace_id=WS, name=name, operation=OP_RMS, inputs=inputs, parameters=parameters,
            source_registry=env.sources, calc_registry=env.calcs, override=override, **kwargs,
        )
    except Exception as exc:  # noqa: BLE001 -- every outcome is the thing being recorded
        return {"ok": False, "error": snap_exception(exc), "registered_after": len(env.calcs.list_for_workspace(WS))}
    return {"ok": True, "channel": snap_channel(channel, env), "registered_after": len(env.calcs.list_for_workspace(WS))}


def attempt_eligibility(env: Env, *, inputs=None, frequency=50.0) -> dict:
    ref = (inputs or [env.ref()])[0]
    try:
        result = check_rms_eligibility(
            workspace_id=WS, input_ref=ref, nominal_frequency_hz=frequency,
            source_registry=env.sources, calc_registry=env.calcs,
        )
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": snap_exception(exc)}
    return {"ok": True, "eligibility": snap_eligibility(result)}


def _both(env: Env, **kwargs) -> dict:
    """Eligibility plus create with override False and True, each on a fresh
    registry state so one attempt cannot influence the next."""
    out = {"eligibility": attempt_eligibility(env, frequency=kwargs.get("elig_frequency", 50.0))}
    for flag in (False, True):
        fresh = Env()
        for source in env.sources.list_for_workspace(WS):
            fresh.add(source)
        out[f"create_override_{flag}"] = attempt_create(fresh, override=flag, **{k: v for k, v in kwargs.items() if k != "elig_frequency"})
    return out


# ---------------------------------------------------------------------------
# Service-level scenarios
# ---------------------------------------------------------------------------

DATA_KEYS = ("svc_instantaneous", "svc_magnitude_like", "svc_uncertain", "svc_rms_shaped")
FORMS = (WAVEFORM_FORM_UNKNOWN, WAVEFORM_FORM_INSTANTANEOUS, WAVEFORM_FORM_RMS, WAVEFORM_FORM_MAGNITUDE)


def _single(data_key: str, **source_kwargs) -> Env:
    time, values = load_service_inputs()[data_key]
    env = Env()
    env.add(build_source("src1", time, values, **source_kwargs))
    return env


def scenarios_eligibility_matrix() -> dict:
    out = {}
    for form in FORMS:
        for data_key in DATA_KEYS:
            out[f"form={form}/data={data_key}"] = _both(_single(data_key, form=form))
    return out


def scenarios_frequency() -> dict:
    out = {}
    values = [None, 0, 0.5, 1, 1000, 1000.0001, -50, float("nan"), float("inf"), True, "50", 50, 60, 50.0]
    for freq in values:
        env = _single("svc_instantaneous", form=WAVEFORM_FORM_INSTANTANEOUS)
        out[f"frequency={freq!r}"] = attempt_create(env, parameters={"nominal_frequency_hz": freq})
    env = _single("svc_instantaneous", form=WAVEFORM_FORM_INSTANTANEOUS)
    out["frequency=<parameter missing>"] = attempt_create(env, parameters={})
    env = _single("svc_instantaneous", form=WAVEFORM_FORM_INSTANTANEOUS)
    out["frequency=<parameters is None>"] = attempt_create(env, parameters=None)
    for freq in (1, 60, 1000, 0.5):
        env = _single("svc_instantaneous", form=WAVEFORM_FORM_INSTANTANEOUS)
        out[f"eligibility/frequency={freq!r}"] = attempt_eligibility(env, frequency=freq)
    return out


def scenarios_validation_precedence() -> dict:
    out = {}
    cases = {
        "instantaneous+short": ("svc_short_instantaneous", WAVEFORM_FORM_INSTANTANEOUS),
        "instantaneous+sparse": ("svc_sparse_instantaneous", WAVEFORM_FORM_INSTANTANEOUS),
        "instantaneous+short+sparse": ("svc_short_and_sparse", WAVEFORM_FORM_INSTANTANEOUS),
        "unknown+short": ("svc_short_instantaneous", WAVEFORM_FORM_UNKNOWN),
        "unknown+sparse": ("svc_sparse_instantaneous", WAVEFORM_FORM_UNKNOWN),
        "unknown+short+sparse": ("svc_short_and_sparse", WAVEFORM_FORM_UNKNOWN),
        "rms+short+sparse": ("svc_short_and_sparse", WAVEFORM_FORM_RMS),
        "rms+short": ("svc_short_instantaneous", WAVEFORM_FORM_RMS),
        "magnitude+sparse": ("svc_sparse_instantaneous", WAVEFORM_FORM_MAGNITUDE),
    }
    for label, (data_key, form) in cases.items():
        out[label] = _both(_single(data_key, form=form))
        env = _single(data_key, form=form)
        out[f"{label}+invalid_frequency_0"] = {
            f"override_{flag}": attempt_create(_clone(env), parameters={"nominal_frequency_hz": 0}, override=flag)
            for flag in (False, True)
        }
    return out


def _clone(env: Env) -> Env:
    fresh = Env()
    for source in env.sources.list_for_workspace(WS):
        fresh.add(source)
    return fresh


def scenarios_calibration() -> dict:
    out = {}
    for ben5k in (True, False):
        for authority in ("verified", "unverified", "invalid", None):
            env = _single("svc_instantaneous", form=WAVEFORM_FORM_INSTANTANEOUS, ben5k=ben5k, authority=authority)
            out[f"ben5k={ben5k}/authority={authority}"] = _both(env)
    env = _single("svc_instantaneous", form=WAVEFORM_FORM_INSTANTANEOUS, ben5k=True, authority="verified",
                  with_record_channel=False)
    out["ben5k=True/record channel missing"] = _both(env)
    for authority in ("invalid", "unverified"):
        env = _single("svc_uncertain", form=WAVEFORM_FORM_UNKNOWN, ben5k=True, authority=authority)
        out[f"ben5k=True/authority={authority}/uncertain data"] = _both(env)
    env = _single("svc_instantaneous", form=WAVEFORM_FORM_RMS, ben5k=True, authority="invalid")
    out["ben5k=True/authority=invalid/declared rms"] = _both(env)
    env = _single("svc_instantaneous", form=WAVEFORM_FORM_INSTANTANEOUS, ben5k=True, authority="invalid")
    out["ben5k=True/authority=invalid/invalid frequency"] = {
        f"override_{flag}": attempt_create(_clone(env), parameters={"nominal_frequency_hz": 0}, override=flag)
        for flag in (False, True)
    }
    return out


def scenarios_null_policy() -> dict:
    out = {}
    policies = {
        "propagate": dict(null_policy=NULL_POLICY_PROPAGATE),
        "zero": dict(null_policy=NULL_POLICY_ZERO),
        "require_manual": dict(null_policy=NULL_POLICY_REQUIRE_MANUAL),
        "estimate_linear": dict(null_policy=NULL_POLICY_ESTIMATE, estimation_method=ESTIMATION_METHOD_LINEAR,
                                max_gap_value=2, max_gap_unit="samples"),
        "estimate_hold_last": dict(null_policy=NULL_POLICY_ESTIMATE, estimation_method=ESTIMATION_METHOD_HOLD_LAST,
                                   max_gap_value=1, max_gap_unit="samples"),
        "estimate_nearest": dict(null_policy=NULL_POLICY_ESTIMATE, estimation_method=ESTIMATION_METHOD_NEAREST,
                                 max_gap_value=1, max_gap_unit="samples"),
        "estimate_local_mean": dict(null_policy=NULL_POLICY_ESTIMATE, estimation_method=ESTIMATION_METHOD_LOCAL_MEAN,
                                    max_gap_value=1, max_gap_unit="samples", local_mean_radius=3),
        "estimate_pchip": dict(null_policy=NULL_POLICY_ESTIMATE, estimation_method=ESTIMATION_METHOD_PCHIP,
                               max_gap_value=1, max_gap_unit="samples"),
        "estimate_missing_method": dict(null_policy=NULL_POLICY_ESTIMATE),
        "propagate_with_estimation_fields": dict(null_policy=NULL_POLICY_PROPAGATE, estimation_method=ESTIMATION_METHOD_LINEAR),
        "unknown_policy": dict(null_policy="no_such_policy"),
    }
    for data_key in ("svc_instantaneous_nan", "svc_instantaneous"):
        for label, kwargs in policies.items():
            env = _single(data_key, form=WAVEFORM_FORM_INSTANTANEOUS)
            out[f"data={data_key}/policy={label}"] = attempt_create(env, **kwargs)
    # Detector-eligible (unknown form) NaN-bearing input under propagate/zero.
    for label in ("propagate", "zero"):
        env = _single("svc_instantaneous_nan", form=WAVEFORM_FORM_UNKNOWN)
        out[f"data=svc_instantaneous_nan/unknown form/policy={label}"] = _both(env, **policies[label])
    return out


def scenarios_chains() -> dict:
    """Calculated-from-calculated inputs: trusted form propagation and RMS-of-RMS."""
    out = {}
    time, values = load_service_inputs()["svc_instantaneous"]

    def base_env(form: str) -> Env:
        env = Env()
        env.add(build_source("src1", time, values, form=form, extra_channels={"VB": values.copy()}))
        return env

    def make(env: Env, name: str, operation: str, inputs, parameters=None) -> ChannelRef:
        channel = create_calculated_channel(
            workspace_id=WS, name=name, operation=operation, inputs=inputs, parameters=parameters or {},
            source_registry=env.sources, calc_registry=env.calcs,
        )
        return ChannelRef(kind="calculated", calculated_channel_id=channel.id)

    for form in (WAVEFORM_FORM_INSTANTANEOUS, WAVEFORM_FORM_UNKNOWN):
        for label, build in {
            "reverse_polarity": lambda e: make(e, "-VA", OP_REVERSE_POLARITY, [e.ref()]),
            "multiply_constant": lambda e: make(e, "VA*2", OP_MULTIPLY_CONSTANT, [e.ref()], {"constant": 2.0}),
            "absolute_value": lambda e: make(e, "|VA|", OP_ABSOLUTE_VALUE, [e.ref()]),
            "addition": lambda e: make(e, "VA+VB", OP_ADDITION, [e.ref(), e.ref(channel="VB")]),
            "subtraction": lambda e: make(e, "VA-VB", OP_SUBTRACTION, [e.ref(), e.ref(channel="VB")]),
            "rms": lambda e: make(e, "RMS(VA)", OP_RMS, [e.ref()], {"nominal_frequency_hz": 50.0}),
        }.items():
            env = base_env(form)
            ref = build(env)
            out[f"source form={form}/input={label}"] = {
                "eligibility": attempt_eligibility(env, inputs=[ref]),
                "create_override_False": attempt_create(_copy_with_calcs(env), name="RMS(derived)", inputs=[ref], override=False),
                "create_override_True": attempt_create(_copy_with_calcs(env), name="RMS(derived)", inputs=[ref], override=True),
            }
    # Chain of RMS of RMS of RMS, explicit.
    env = base_env(WAVEFORM_FORM_INSTANTANEOUS)
    first = make(env, "RMS1", OP_RMS, [env.ref()], {"nominal_frequency_hz": 50.0})
    second_result = attempt_create(env, name="RMS2", inputs=[first], override=True)
    out["rms_of_rms/second with override"] = second_result
    return out


def _copy_with_calcs(env: Env) -> Env:
    fresh = Env()
    for source in env.sources.list_for_workspace(WS):
        fresh.add(source)
    for calc in env.calcs.list_for_workspace(WS):
        fresh.calcs.add(calc)
    return fresh


def scenarios_display_range() -> dict:
    """Existing display extraction of a created RMS channel (timestamps and samples as served)."""
    env = _single("svc_instantaneous", form=WAVEFORM_FORM_INSTANTANEOUS)
    channel = create_calculated_channel(
        workspace_id=WS, name="RMS(VA)", operation=OP_RMS, inputs=[env.ref()], parameters={"nominal_frequency_hz": 50.0},
        source_registry=env.sources, calc_registry=env.calcs,
    )
    result = extract_calculated_waveform_range(channel, start_time=None, end_time=None)
    return {"full_range": {
        "representation": result.representation, "original_sample_count": result.original_sample_count,
        "time_sha256": _sha(result.time), "values_sha256": _sha(result.values),
        "unit": result.unit, "per_unit_status": result.per_unit_status,
    }}


def run_service_scenarios() -> dict:
    out = {}
    for group, fn in (
        ("eligibility_matrix", scenarios_eligibility_matrix), ("frequency", scenarios_frequency),
        ("validation_precedence", scenarios_validation_precedence), ("calibration", scenarios_calibration),
        ("null_policy", scenarios_null_policy), ("chains", scenarios_chains), ("display_range", scenarios_display_range),
    ):
        out[group] = fn()
    return out


# ---------------------------------------------------------------------------
# API-level scenarios (real upload -> parse -> calculate), through a TestClient
# ---------------------------------------------------------------------------


def ascii_comtrade(fs: float, values: np.ndarray) -> tuple[bytes, bytes]:
    n = int(values.shape[0])
    cfg_lines = [
        "SYNTH_STATION,SYNTH_DEV,1999", "1,1A,0D",
        "1,VA,A,,V,1.0,0.0,0,-999999,999999,110.0,1.0,P",
        "50", "1", f"{fs},{n}", "06/03/2026,10:00:00.000000", "06/03/2026,10:00:00.000000", "ASCII", "1.0",
    ]
    dat_lines = [f"{i + 1},{round(i * (1_000_000.0 / fs))},{float(values[i]):.6f}" for i in range(n)]
    return ("\r\n".join(cfg_lines) + "\r\n").encode("ascii"), ("\r\n".join(dat_lines) + "\r\n").encode("ascii")


_ID_KEYS = {"id", "source_id", "calculated_channel_id", "reference_source_id", "created_at"}


def normalise(obj, ids: dict):
    if isinstance(obj, dict):
        out = {}
        for key, value in obj.items():
            if key in _ID_KEYS and isinstance(value, str):
                out[key] = ids.setdefault(value, f"<{key}:{len(ids)}>")
            elif key == "timing_fingerprint" and isinstance(value, str):
                out[key] = "<fingerprint>"  # a digest that includes the (random) source id
            elif key in ("dependency_ids", "timing_source_ids") and isinstance(value, list):
                out[key] = [ids.setdefault(v, f"<dep:{len(ids)}>") for v in value]
            else:
                out[key] = normalise(value, ids)
        return out
    if isinstance(obj, list):
        return [normalise(v, ids) for v in obj]
    return obj


def run_api_scenarios(client) -> dict:
    base = f"/api/v1/workspaces/{WS}"
    inputs = load_service_inputs()
    ids: dict = {}
    out: dict = {}

    def upload(key: str, fs: float) -> str:
        cfg, dat = ascii_comtrade(fs, inputs[key][1])
        response = client.post(
            f"{base}/sources",
            files={"cfg_file": (f"{key}.cfg", io.BytesIO(cfg), "application/octet-stream"),
                   "dat_file": (f"{key}.dat", io.BytesIO(dat), "application/octet-stream")},
        )
        assert response.status_code == 201, response.text
        return response.json()["source_id"]

    def record(label: str, response) -> None:
        try:
            body = response.json()
        except ValueError:
            body = response.text
        out[label] = {"status": response.status_code, "body": normalise(body, ids)}

    sources = {
        "instantaneous": upload("svc_instantaneous", 5000.0), "uncertain": upload("svc_uncertain", 2000.0),
        "magnitude": upload("svc_magnitude_like", 5000.0), "rms_shaped": upload("svc_rms_shaped", 2000.0),
        "short": upload("svc_short_instantaneous", 5000.0), "sparse": upload("svc_sparse_instantaneous", 150.0),
    }

    def elig(label, source_key, **body):
        payload = {"input": {"kind": "source", "source_id": sources[source_key], "channel_name": "VA"}, **body}
        record(f"rms-eligibility/{label}", client.post(f"{base}/calculated-channels/rms-eligibility", json=payload))

    def create(label, source_key, *, name, override=None, parameters=None, **extra):
        payload = {"name": name, "operation": "rms",
                   "inputs": [{"kind": "source", "source_id": sources[source_key], "channel_name": "VA"}],
                   "parameters": {"nominal_frequency_hz": 50.0} if parameters is None else parameters, **extra}
        if override is not None:
            payload["override"] = override
        response = client.post(f"{base}/calculated-channels", json=payload)
        record(f"create/{label}", response)
        return response

    for key in ("instantaneous", "uncertain", "magnitude", "rms_shaped", "short", "sparse"):
        elig(f"{key}/50", key, nominal_frequency_hz=50.0)
    elig("instantaneous/60", "instantaneous", nominal_frequency_hz=60.0)
    for freq in (0, 0.5, -50, 1001):
        elig(f"instantaneous/{freq}", "instantaneous", nominal_frequency_hz=freq)
    elig("instantaneous/string", "instantaneous", nominal_frequency_hz="x")
    elig("instantaneous/missing", "instantaneous")
    record("rms-eligibility/unknown source", client.post(
        f"{base}/calculated-channels/rms-eligibility",
        json={"input": {"kind": "source", "source_id": "no-such", "channel_name": "VA"}, "nominal_frequency_hz": 50.0}))

    ok = create("instantaneous/ok", "instantaneous", name="RMS(VA) ok")
    create("instantaneous/duplicate name", "instantaneous", name="RMS(VA) ok")
    for freq in (0, 0.5, 1001, "x", None):
        create(f"instantaneous/frequency={freq!r}", "instantaneous", name=f"RMS f {freq!r}", parameters={"nominal_frequency_hz": freq})
    create("instantaneous/no parameters", "instantaneous", name="RMS none", parameters={})
    create("instantaneous/frequency=60", "instantaneous", name="RMS 60", parameters={"nominal_frequency_hz": 60.0})
    for key in ("uncertain", "magnitude", "rms_shaped", "short", "sparse"):
        create(f"{key}/no override", key, name=f"RMS {key}")
        create(f"{key}/override false", key, name=f"RMS {key} f", override=False)
        create(f"{key}/override true", key, name=f"RMS {key} t", override=True)
    create("instantaneous/invalid frequency + override", "short", name="RMS bad f", override=True, parameters={"nominal_frequency_hz": 0})

    calc_id = ok.json()["id"]
    record("calculated-channels/list", client.get(f"{base}/calculated-channels"))
    record("calculated-channels/waveform", client.get(f"{base}/calculated-channels/{calc_id}/waveform"))
    record("calculated-channels/cursor-values", client.post(
        f"{base}/calculated-channels/cursor-values",
        json={"calculated_channel_ids": [calc_id], "cursor_a_time": 0.01, "cursor_b_time": 0.3}))
    record("calculated-channels/peak-values", client.post(
        f"{base}/calculated-channels/peak-values",
        json={"requests": [{"calculated_channel_id": calc_id, "mode": "max"}], "start_time": 0.0, "end_time": 0.5}))
    # The long waveform arrays are reduced to a digest so the baseline stays reviewable.
    wf = out["calculated-channels/waveform"]["body"]
    if isinstance(wf, dict) and "values" in wf:
        out["calculated-channels/waveform"]["body"] = {
            **{k: v for k, v in wf.items() if k not in ("time", "values")},
            "time_sha256": hashlib.sha256(json.dumps(wf["time"]).encode()).hexdigest(),
            "values_sha256": hashlib.sha256(json.dumps(wf["values"]).encode()).hexdigest(),
            "null_count": sum(1 for v in wf["values"] if v is None),
        }
    return out
