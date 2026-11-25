"""NF-3A HTTP probe (read-only against the existing API): what does the RMS-eligibility endpoint do with unusual frequencies,
and what does a recording whose declared frequency is unusable do on the engine paths reachable without an Engineering Context?"""
import json
import sys
import warnings
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path.cwd()))
from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402
from tests import comtrade_frequency_scenarios as scn  # noqa: E402
import tempfile

out = {}
settings = Settings(environment="development", storage_type="local", storage_path=tempfile.mkdtemp(prefix="nf3a-"),
                    cors_origins=("http://localhost:8101",), database_url=None, max_event_upload_size_mb=100,
                    git_sha="local", version="local")
variants = scn.build_variants()
out["variant_keys_sample"] = [k for k in variants][:20]
with TestClient(create_app(settings), raise_server_exceptions=False) as c:
    ws = "ws-nf3a-probe"
    for key in ("declared_60", "declared_zero", "declared_50"):
        if key not in variants:
            out.setdefault("missing_keys", []).append(key)
    sids = {}
    for key in [k for k in ("declared_50", "declared_60", "declared_zero") if k in variants]:
        files = {"cfg_file": ("e.cfg", variants[key].encode("latin-1"), "application/octet-stream"),
                 "dat_file": ("e.dat", scn._DAT.encode(), "application/octet-stream")}
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            r = c.post(f"/api/v1/workspaces/{ws}/sources", files=files)
        sids[key] = r.json().get("source_id")
        out[f"upload_{key}"] = r.status_code
    chan = None
    for key, sid in sids.items():
        r = c.get(f"/api/v1/workspaces/{ws}/sources/{sid}/channels")
        if r.status_code == 200 and chan is None:
            chan = r.json()["analog_channels"][0]["name"]
            out["channel_used"] = chan
        out[f"source_summary_nominal_{key}"] = (r.json().get("source") or {}).get("nominal_frequency") if r.status_code == 200 else r.status_code
    for key, sid in sids.items():
        rows = []
        for f in (50, 60, 0, -50):
            body = {"input": {"kind": "source", "source_id": sid, "channel_name": chan}, "nominal_frequency_hz": f}
            r = c.post(f"/api/v1/workspaces/{ws}/calculated-channels/rms-eligibility", json=body)
            rows.append({"request_nominal_hz": f, "http": r.status_code, "body": (r.json() if r.status_code != 500 else r.text[:60])})
        out[f"rms_eligibility_{key}"] = rows
        # creating an RMS channel with an explicit unusual frequency
        rows = []
        for f in (0, -50, 60):
            body = {"operation": "rms", "name": f"R{f}", "inputs": [{"kind": "source", "source_id": sid, "channel_name": chan}],
                    "parameters": {"nominal_frequency_hz": f}}
            r = c.post(f"/api/v1/workspaces/{ws}/calculated-channels", json=body)
            detail = r.json().get("detail") if r.status_code >= 400 and r.status_code != 500 else None
            rows.append({"request_nominal_hz": f, "http": r.status_code, "code": (detail or {}).get("code") if isinstance(detail, dict) else detail})
        out[f"rms_create_{key}"] = rows
print(json.dumps(out, indent=1, default=str))
