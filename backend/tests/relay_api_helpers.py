"""Shared relay-import API helpers for tests: a test client and the review / decision shorthands.

Relay-neutral (DEC-199): the relays themselves are exercised by the generic conformance suite
(``tests/test_relay_conformance.py``); these helpers serve the cross-relay security and capability tests.
"""

from __future__ import annotations

import io
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.relay_review_tokens import review_ref

UPLOAD = "/api/v1/relay-import/upload"
VALIDATE = "/api/v1/relay-import/review/validate"
APPLY = "/api/v1/relay-import/review/apply"


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    from app.config import Settings

    settings = Settings(environment="development", storage_type="local", storage_path=str(tmp_path_factory.mktemp("s")),
                        cors_origins=("http://localhost:8101",), database_url=None, max_event_upload_size_mb=100,
                        git_sha="local", version="local")
    with TestClient(create_app(replace(settings, max_relay_import_upload_size_mb=5))) as c:
        yield c


def upload(client, pdf: bytes) -> dict:
    r = client.post(UPLOAD, files={"file": ("sheet.pdf", io.BytesIO(pdf), "application/pdf")})
    assert r.status_code == 200, r.text
    return r.json()


def items(review) -> dict[str, dict]:
    """Review rows by canonical path; a value shown as two rows (R / X, magnitude / angle) keeps its primary row."""
    out: dict[str, dict] = {}
    for g in review["groups"]:
        for i in g["items"]:
            if i["item_id"]:
                out.setdefault(i["item_id"], i)
    return out


def group(review, zone_id: str) -> dict:
    return next(g for g in review["groups"] if g["id"] == f"zone-{zone_id}")


def raw_rows(review, zone_id: str) -> dict[str, dict]:
    """The zone's preserved raw settings (no canonical meaning), by their source name."""
    return {i["label"]: i for i in group(review, zone_id)["items"] if i["item_id"] is None}


def decisions(review, *, confirm=True, suggested=True, manual=()):
    confirmed = [i["item_id"] for g in review["groups"] for i in g["items"]
                 if i["item_id"] and i["primary"] and i["category"] == "assumption" and i["review_status"] == "to_confirm"]
    offered = [i["item_id"] for g in review["groups"] for i in g["items"] if i["item_id"] and i.get("suggestion")]
    return {**review_ref(review), "confirmed": confirmed if confirm else [],
            "suggested": offered if suggested else [], "manual": list(manual)}
