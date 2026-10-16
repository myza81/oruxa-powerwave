"""DEC-198 Amendment 5: the relay review's validation context is a signed, opaque token.

The upload seals the server-authored interpretation (with the import id, issue / expiry times and the relay
knowledge it was made with) in an HMAC-SHA256-signed token; validate and Apply each verify it before trusting
anything in it. Tampering, fabricated review state, cross-import use, expiry and changed relay knowledge are
refused with one generic message, before any engineering validation. Statelessness has one honest limit,
pinned here too: an issued token is NOT revoked by a later upload or a browser-side Remove -- it stays valid
until it expires.
"""

from __future__ import annotations

import base64
import io
import json
import time
import zlib
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from app.config import ConfigurationError, Settings, load_settings
from app.domain.relay_import.canonical_codec import encode_model
from app.domain.relay_import.provenance import UnresolvedCause
from app.domain.relay_import.review_state import ReviewDecisions
from app.main import create_app
from app.services.relay_review_token import (
    INVALID_REVIEW_TOKEN, TOKEN_SCHEMA, ReviewTokenError, ReviewTokenSigner, current_relay_knowledge, signer_from_settings,
)
from app.services.relay_review_validation import InvalidReviewError, validate_review
from tests import relay_family_fixtures as F
from tests.relay_review_tokens import (
    TEST_IMPORT_ID, TEST_KNOWLEDGE, TEST_SIGNER, TEST_SIGNING_KEY, seal, sealed_knowledge_for, sign_payload,
)
from tests.test_relay_import_upload import _p441_pdf
from tests.test_relay_remaining_families import APPLY, UPLOAD, VALIDATE, client, decisions, upload  # noqa: F401

KEY = "k" * 40
INVALID = {"code": "invalid_review_token", "message": INVALID_REVIEW_TOKEN}
PP = "zones[Z1].resistive_reach.phase_phase"


def env(**extra) -> dict:
    return {"STORAGE_PATH": "/tmp/x", **extra}


def body_of(token: str) -> dict:
    """What a token carries (any client can read it -- it is signed, not secret)."""
    segment = token.split(".")[1]
    return json.loads(zlib.decompress(base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))))


def forged(payload: dict) -> str:
    """The attacker's best effort: a well-formed token around an edited payload, keeping the original MAC."""
    segment = base64.urlsafe_b64encode(zlib.compress(json.dumps(payload).encode(), 9)).rstrip(b"=").decode()
    return f"v1.{segment}.{'A' * 43}"


def refused(response) -> bool:
    return response.status_code == 400 and response.json()["detail"] == INVALID


@pytest.fixture(scope="module")
def sl87(client):
    return upload(client, F.sl87_pdf())["review"]


# --- configuration ------------------------------------------------------------------------------------------

class TestConfiguration:
    def test_a_deployed_environment_must_configure_the_key(self):
        with pytest.raises(ConfigurationError, match="RELAY_REVIEW_SIGNING_KEY must be set"):
            load_settings(env(ENVIRONMENT="production", CORS_ORIGINS="https://x"))
        with pytest.raises(ConfigurationError, match="RELAY_REVIEW_SIGNING_KEY must be set"):
            load_settings(env(APP_VERSION="0123456789abcdef0123456789abcdef01234567"))   # DEV on the VPS too

    def test_local_development_may_run_without_a_key(self):
        settings = load_settings(env())
        assert settings.relay_review_signing_key is None and not settings.is_deployed

    def test_a_short_key_is_refused_and_no_error_echoes_a_key(self):
        with pytest.raises(ConfigurationError) as exc:
            load_settings(env(RELAY_REVIEW_SIGNING_KEY="short-secret-value"))
        assert "short-secret-value" not in str(exc.value)

    def test_the_key_and_lifetime_are_read_from_the_environment_and_never_shown(self):
        settings = load_settings(env(ENVIRONMENT="production", CORS_ORIGINS="https://x", RELAY_REVIEW_SIGNING_KEY=KEY,
                                     RELAY_REVIEW_TOKEN_TTL_HOURS="2"))
        assert settings.relay_review_signing_key == KEY and settings.relay_review_token_ttl_hours == 2
        assert KEY not in repr(settings)
        assert load_settings(env()).relay_review_token_ttl_hours == 24                 # the default lifetime
        for bad in ("0", "-1", "soon"):
            with pytest.raises(ConfigurationError, match="RELAY_REVIEW_TOKEN_TTL_HOURS"):
                load_settings(env(RELAY_REVIEW_TOKEN_TTL_HOURS=bad))

    def test_the_app_refuses_to_start_deployed_without_a_key(self, tmp_path):
        settings = Settings(environment="production", storage_type="local", storage_path=str(tmp_path),
                            cors_origins=("https://x",), database_url=None, max_event_upload_size_mb=10,
                            git_sha="local", version="local")
        with pytest.raises(ConfigurationError):
            create_app(settings)

    def test_the_signer_uses_the_configured_key_or_a_local_per_process_key(self, tmp_path):
        base = Settings(environment="development", storage_type="local", storage_path=str(tmp_path), cors_origins=(),
                        database_url=None, max_event_upload_size_mb=10, git_sha="local", version="local")
        configured = signer_from_settings(replace(base, relay_review_signing_key=KEY, relay_review_token_ttl_hours=3))
        assert configured.key == KEY.encode() and configured.ttl_s == 3 * 3600 and KEY not in repr(configured)
        assert signer_from_settings(base).key != signer_from_settings(base).key        # random, never a fixed default


# --- the token ---------------------------------------------------------------------------------------------

class TestToken:
    def test_the_upload_returns_an_opaque_signed_token_bound_to_a_backend_import_id(self, client, sl87):
        assert sl87["validation_token"].startswith("v1.") and len(sl87["import_id"]) == 32
        assert "validation_context" not in sl87
        payload = body_of(sl87["validation_token"])
        assert set(payload) == {"schema", "import_id", "issued_at", "expires_at", "knowledge", "model"}
        assert payload["schema"] == TOKEN_SCHEMA and payload["import_id"] == sl87["import_id"]
        assert payload["expires_at"] - payload["issued_at"] == 24 * 3600
        assert payload["knowledge"] == current_relay_knowledge("siemens-siprotec5-7sl87")
        assert payload["knowledge"]["catalog"]["version"] == "1.1.0" and len(payload["knowledge"]["catalog"]["digest"]) == 64

    def test_a_round_trip_returns_the_sealed_interpretation(self):
        model = TEST_SIGNER.verify(seal(_model()), import_id=TEST_IMPORT_ID, knowledge_for=sealed_knowledge_for)
        assert encode_model(model) == encode_model(_model())

    def test_serialisation_is_deterministic(self):
        assert seal(_model(), now=1_000_000) == seal(_model(), now=1_000_000)

    @pytest.mark.parametrize("position", [0, 1, 2, 3, 10, 200, -60, -2, -1])
    @pytest.mark.parametrize("endpoint", [VALIDATE, APPLY])
    def test_changing_any_character_is_refused_on_validate_and_apply(self, client, sl87, endpoint, position):
        token = sl87["validation_token"]
        i = position % len(token)
        changed = token[:i] + ("B" if token[i] != "B" else "C") + token[i + 1:]
        assert refused(client.post(endpoint, json={"validation_token": changed, "import_id": sl87["import_id"]}))

    def test_no_other_spelling_of_the_signature_is_accepted(self):
        # canonical base64 only: even the unused trailing bits of the last character are checked
        token = seal(_model())
        start = token.rindex(".") + 1
        alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
        for i in range(start, len(token)):
            for ch in alphabet.replace(token[i], ""):
                with pytest.raises(ReviewTokenError):
                    TEST_SIGNER.verify(token[:i] + ch + token[i + 1:], import_id=TEST_IMPORT_ID, knowledge_for=sealed_knowledge_for)

    @pytest.mark.parametrize("token", ["", "v1", "v1..", "v2.abc.def", "v1.abc", "v1.a+b.c", "x" * 50, "v1.é.ç"])
    def test_malformed_tokens_are_refused(self, client, token):
        r = client.post(VALIDATE, json={"validation_token": token or "x", "import_id": "a" * 32})
        assert refused(r)

    def test_a_token_signed_with_another_key_is_refused(self, client, sl87):
        other = ReviewTokenSigner(b"another-deployment-key-0123456789abcdef", 3600)
        model = TEST_SIGNER.verify(seal(_model()), import_id=TEST_IMPORT_ID, knowledge_for=sealed_knowledge_for)
        token = other.issue(model, import_id=sl87["import_id"], knowledge=body_of(sl87["validation_token"])["knowledge"])
        assert refused(client.post(VALIDATE, json={"validation_token": token, "import_id": sl87["import_id"]}))

    def test_the_message_is_generic_and_reveals_nothing(self, client, sl87):
        r = client.post(VALIDATE, json={"validation_token": sl87["validation_token"][:-1] + "A", "import_id": sl87["import_id"]})
        text = json.dumps(r.json())
        for leak in ("hmac", "HMAC", "signature", "sha256", "RELAY_REVIEW_SIGNING_KEY", "expected", "key"):
            assert leak not in text


# --- the exploits that signing closes --------------------------------------------------------------------------

class TestTamperingAttacks:
    def test_unsupported_to_missing_then_a_manual_value_is_impossible(self, client, sl87):
        payload = body_of(sl87["validation_token"])
        text = json.dumps(payload)
        # the 7SL87 +R is Unsupported; the attacker rewrites every unsupported cause to missing ...
        edited = json.loads(text.replace('"v": "unsupported"', '"v": "missing"'))
        assert edited != payload
        body = {"validation_token": forged(edited), "import_id": sl87["import_id"], "manual": [{"item_id": PP, "value": 3.1}]}
        assert refused(client.post(VALIDATE, json=body))                       # ... and the token no longer verifies
        assert refused(client.post(APPLY, json=body))

    def test_a_planted_resolved_value_is_impossible(self, client, sl87):
        payload = body_of(sl87["validation_token"])
        zone = payload["model"]["zones"][0]
        pp = zone["resistive_reach"]["phase_phase"]
        pp["value"] = 3.1
        pp["provenance"]["status"] = {"_e": "MappingStatus", "v": "mapped"}
        pp["provenance"]["cause"] = None
        assert refused(client.post(VALIDATE, json={"validation_token": forged(payload), "import_id": sl87["import_id"]}))
        assert refused(client.post(APPLY, json={"validation_token": forged(payload), "import_id": sl87["import_id"]}))

    def test_even_a_validly_signed_altered_interpretation_still_refuses_what_its_review_does_not_offer(self):
        # defence in depth: were the key ever leaked, the manual-resolution authority still applies (Amendment 4)
        model = _model()
        token = seal(model)
        with pytest.raises(InvalidReviewError, match="cannot be resolved manually"):
            validate_review(token, TEST_IMPORT_ID, ReviewDecisions(manual={PP: 3.1}), signer=TEST_SIGNER,
                            knowledge_for=sealed_knowledge_for)

    def test_a_raw_unsigned_context_is_never_accepted(self, client, sl87):
        context = body_of(sl87["validation_token"])["model"]
        assert client.post(VALIDATE, json={"validation_context": context}).status_code == 422
        assert client.post(APPLY, json={"validation_context": context}).status_code == 422
        both = {"validation_token": sl87["validation_token"], "import_id": sl87["import_id"], "validation_context": context}
        assert client.post(VALIDATE, json=both).status_code == 422                 # not even ignored silently


# --- identity, expiry and relay knowledge ---------------------------------------------------------------------

class TestBinding:
    @pytest.mark.parametrize("endpoint", [VALIDATE, APPLY])
    def test_a_token_only_authorises_its_own_import(self, client, sl87, endpoint):
        other = upload(client, F.rel511_pdf())["review"]
        assert refused(client.post(endpoint, json={"validation_token": sl87["validation_token"], "import_id": other["import_id"]}))
        assert refused(client.post(endpoint, json={"validation_token": other["validation_token"], "import_id": sl87["import_id"]}))
        assert refused(client.post(endpoint, json={"validation_token": sl87["validation_token"], "import_id": "ü" * 32}))

    def test_an_expired_token_is_refused(self):
        token = seal(_model(), now=time.time() - 24 * 3600 - 1)
        with pytest.raises(ReviewTokenError) as exc:
            TEST_SIGNER.verify(token, import_id=TEST_IMPORT_ID, knowledge_for=sealed_knowledge_for)
        assert exc.value.reason == "expired" and str(exc.value) == INVALID_REVIEW_TOKEN
        fresh = seal(_model(), now=time.time() - 24 * 3600 + 60)               # still inside its lifetime
        TEST_SIGNER.verify(fresh, import_id=TEST_IMPORT_ID, knowledge_for=sealed_knowledge_for)

    def test_the_lifetime_is_the_configured_one(self):
        short = ReviewTokenSigner(TEST_SIGNING_KEY, ttl_s=60)
        token = short.issue(_model(), import_id=TEST_IMPORT_ID, knowledge=TEST_KNOWLEDGE, now=time.time() - 61)
        with pytest.raises(ReviewTokenError, match="no longer valid"):
            short.verify(token, import_id=TEST_IMPORT_ID, knowledge_for=sealed_knowledge_for)

    def test_a_token_from_the_future_is_refused(self):
        token = seal(_model(), now=time.time() + 3600)
        with pytest.raises(ReviewTokenError):
            TEST_SIGNER.verify(token, import_id=TEST_IMPORT_ID, knowledge_for=sealed_knowledge_for)

    @pytest.mark.parametrize("current", [
        None,                                                                        # the profile no longer exists
        {**TEST_KNOWLEDGE, "profile_version": "test-2"},
        {**TEST_KNOWLEDGE, "catalog": {"id": "x", "version": "1.0.0", "digest": "0" * 64}},
    ])
    def test_changed_relay_knowledge_requires_a_new_upload(self, current):
        with pytest.raises(ReviewTokenError) as exc:
            TEST_SIGNER.verify(seal(_model()), import_id=TEST_IMPORT_ID, knowledge_for=lambda _pid: current)
        assert exc.value.reason == "knowledge"

    def test_a_catalog_change_after_upload_invalidates_the_review(self, client, sl87, monkeypatch):
        changed = {**current_relay_knowledge("siemens-siprotec5-7sl87")}
        changed["catalog"] = {**changed["catalog"], "version": "1.2.0"}
        monkeypatch.setattr("app.services.relay_review_validation.current_relay_knowledge", lambda _pid: changed)
        assert refused(client.post(VALIDATE, json={"validation_token": sl87["validation_token"], "import_id": sl87["import_id"]}))
        assert refused(client.post(APPLY, json={"validation_token": sl87["validation_token"], "import_id": sl87["import_id"]}))

    def test_a_signed_payload_with_a_wrong_schema_or_snapshot_is_refused(self):
        now = int(time.time())
        good = {"schema": TOKEN_SCHEMA, "import_id": TEST_IMPORT_ID, "issued_at": now, "expires_at": now + 60,
                "knowledge": TEST_KNOWLEDGE, "model": encode_model(_model())}
        for change in ({"schema": "oruxa.relay-review-token/0"}, {"model": {"_t": "os.system"}}, {"expires_at": "never"},
                       {"knowledge": "x"}):
            with pytest.raises(ReviewTokenError):
                TEST_SIGNER.verify(sign_payload({**good, **change}), import_id=TEST_IMPORT_ID, knowledge_for=sealed_knowledge_for)


class TestStatelessSemantics:
    def test_apply_verifies_the_token_itself_without_a_prior_validate(self, client):
        review = upload(client, F.rel670_pdf())["review"]
        body = decisions(review, manual=[{"item_id": "zones[Z2].phase_timer_s", "value": 1.0}])
        assert client.post(APPLY, json=body).status_code == 200                # no validate call first
        body["validation_token"] = body["validation_token"][:-3] + "AAA"
        assert refused(client.post(APPLY, json=body))

    def test_an_issued_token_is_not_revoked_by_a_later_upload(self, client):
        # Honest limit of a stateless backend: superseding / removing an import in the browser does not revoke its
        # token -- it remains valid until it expires. The browser's own remove / supersede handling covers the UX.
        first = upload(client, _p441_pdf())["review"]
        upload(client, _p441_pdf())
        ok = client.post(VALIDATE, json={"validation_token": first["validation_token"], "import_id": first["import_id"]})
        assert ok.status_code == 200

    def test_a_token_from_another_process_is_refused_without_a_shared_key(self, tmp_path, sl87):
        settings = Settings(environment="development", storage_type="local", storage_path=str(tmp_path), cors_origins=(),
                            database_url=None, max_event_upload_size_mb=10, git_sha="local", version="local")
        with TestClient(create_app(settings)) as other:                            # its own per-process key
            r = other.post(VALIDATE, json={"validation_token": sl87["validation_token"], "import_id": sl87["import_id"]})
        assert refused(r)

    def test_instances_sharing_the_key_accept_each_others_tokens(self, tmp_path):
        settings = Settings(environment="production", storage_type="local", storage_path=str(tmp_path),
                            cors_origins=("https://x",), database_url=None, max_event_upload_size_mb=10,
                            git_sha="local", version="local", relay_review_signing_key=KEY)
        with TestClient(create_app(settings)) as a, TestClient(create_app(settings)) as b:
            review = a.post(UPLOAD, files={"file": ("s.pdf", io.BytesIO(F.sl87_pdf()), "application/pdf")}).json()["review"]
            r = b.post(VALIDATE, json={"validation_token": review["validation_token"], "import_id": review["import_id"]})
        assert r.status_code == 200


def _model():
    """A 7SL87 interpretation (its +R is Unsupported) through the shipped catalog."""
    from app.domain.parameter_catalog.interpreter import CatalogInterpreter
    from app.domain.parameter_catalog.loader import canonical_registry, default_store
    from app.services.relay_pdf_extractor import extract_pdf

    catalog = default_store().get("siemens-siprotec5-7sl87-catalog")
    model = CatalogInterpreter(catalog, canonical_registry()).interpret(extract_pdf(F.sl87_pdf()).document)
    assert model.zone("Z1").resistive_reach.phase_phase.provenance.cause is UnresolvedCause.UNSUPPORTED
    return model
