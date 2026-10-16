"""User-facing copy carries no product name, and the Zone P note has its own spacing.

The product/domain name must not leak into anything a user reads: UI text, helper and
status messages, provenance descriptions, accessibility labels, API-visible schema text.
Code comments, repository/package identifiers, paths and project-memory history may keep
it (a rename is a technical refactor), so the scan skips comments and is limited to the
shipped frontend files and the relay-review responses.
"""

from __future__ import annotations

import io
import json
import pathlib
import re

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.schemas import relay_import as relay_schemas
from tests.test_relay_import_upload import _p441_pdf
from tests.test_relay_review_state import REVERSE, UPLOAD, VALIDATE
from tests.relay_review_tokens import review_ref

ROOT = pathlib.Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"
BRAND = re.compile("oruxa", re.IGNORECASE)

#: Documented exceptions: frontend files whose only occurrences are internal path references.
#: (theme.css and vendor/README.md name docs/architecture/oruxa-architecture.md in comments/docs.)
EXEMPT_FILES = {"theme.css", "README.md"}


def _code_lines(text: str):
    """Yield (number, line) for lines outside // comments, /* */ and <!-- --> blocks."""
    in_block = False
    for number, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if in_block:
            if "*/" in stripped or "-->" in stripped:
                in_block = False
            continue
        if stripped.startswith("//"):
            continue
        if stripped.startswith(("/*", "<!--")) and not re.search(r"(\*/|-->)\s*$", stripped):
            in_block = True
            continue
        if stripped.startswith(("/*", "<!--", "*")):
            continue
        yield number, line


def _frontend_files():
    for path in sorted(FRONTEND.rglob("*")):
        if path.is_file() and path.suffix in {".html", ".js", ".css", ".svg", ".md"} and "vendor" not in path.parts:
            if path.name not in EXEMPT_FILES:
                yield path


@pytest.mark.parametrize("path", list(_frontend_files()), ids=lambda p: str(p.relative_to(FRONTEND)))
def test_shipped_frontend_text_has_no_product_name(path):
    text = path.read_text(encoding="utf-8")
    offenders = [n for n, line in _code_lines(text) if BRAND.search(line)]
    assert not offenders, f"{path.name}: line(s) {offenders[:5]}"


def test_schema_text_visible_in_the_api_docs_has_no_product_name():
    schema = json.dumps(relay_schemas.ReviewSuggestionOut.model_json_schema())
    schema += json.dumps(relay_schemas.ReviewValidationIn.model_json_schema())
    assert not BRAND.search(schema)


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as c:
        yield c


def _upload(client):
    return client.post(UPLOAD, files={"file": ("sheet.pdf", io.BytesIO(_p441_pdf()), "application/pdf")}).json()


def test_relay_review_responses_carry_no_product_name(client):
    upload = _upload(client)
    ctx = review_ref(upload["review"])
    body = {**ctx, "suggested": [REVERSE.format(z) for z in ("Z1", "Z2", "Z3")]}
    state = client.post(VALIDATE, json=body).json()
    # the opaque validation token and import id are data, not copy
    visible = {k: v for k, v in upload["review"].items() if k not in ("validation_token", "import_id")}
    for payload in (visible, upload["interpretation_warnings"], state):
        assert not BRAND.search(json.dumps(payload, ensure_ascii=False))


def test_zone_p_note_is_neutral_and_the_suggestion_is_still_a_suggestion(client):
    upload = _upload(client)
    notes = [g.get("state_note") for g in upload["review"]["groups"] if g.get("state_note")]
    assert any(
        n == "Zone status was not explicitly decoded. The 10.0 s operating delay is interpreted as a "
        "defeated/inactive distance zone. Its extracted settings are kept for reference."
        for n in notes
    ), notes
    state = client.post(
        VALIDATE,
        json={**review_ref(upload["review"]), "suggested": [REVERSE.format("Z1")]},
    ).json()
    item = {i["item_id"]: i for i in state["items"]}[REVERSE.format("Z1")]
    assert item["resolution_origin"] == "suggestion" and item["category"] == "missing"


def test_zone_p_note_has_its_own_spacing_rule_matching_the_item_padding():
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    assert '"ww-rr-dim ww-rr-state-note"' in html
    rule = re.search(r":is\(\.ww-rr-state-note\) \{([^}]*)\}", html)
    assert rule, "the Zone P note needs a spacing rule"
    assert re.search(r"padding:\s*6px 10px 2px", rule.group(1))
    items = re.search(r":is\(\.ww-rr-items\) \{([^}]*)\}", html).group(1)
    assert "padding: 0 10px 6px" in items  # same 10px side padding: the note lines up with the rows
