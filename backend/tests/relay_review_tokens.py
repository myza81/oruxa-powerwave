"""Test helpers for signed relay review validation tokens (DEC-198 Amendment 5).

Validation and Apply take a signed token, never a raw interpretation. Tests that validate a model they
built in memory seal it here with an explicit, deterministic test key (never a deployment key) and a
fixed test relay knowledge; tests that go through the API use the token the upload returned.
"""

from __future__ import annotations

from app.domain.relay_import.canonical_distance import CanonicalDistanceProtectionModel
from app.domain.relay_import.review_state import ReviewDecisions
from app.services.relay_apply_settings import apply_reviewed_settings
from app.services.relay_review_token import ReviewTokenSigner
from app.services.relay_review_validation import reviewed_state, validate_review

#: Deterministic test-only key (at least 32 bytes). Never used outside the test suite.
TEST_SIGNING_KEY = b"oruxa-relay-review-test-signing-key-0001"
TEST_SIGNER = ReviewTokenSigner(TEST_SIGNING_KEY, ttl_s=24 * 3600)
TEST_IMPORT_ID = "test-import-0001"
#: The relay knowledge a model built in a test is sealed with (no shipped profile is involved).
TEST_KNOWLEDGE = {"profile_id": "test-profile", "profile_version": "test-1"}


def sealed_knowledge_for(profile_id: str) -> dict | None:
    return TEST_KNOWLEDGE if profile_id == TEST_KNOWLEDGE["profile_id"] else None


def seal(model: CanonicalDistanceProtectionModel, import_id: str = TEST_IMPORT_ID, **kw) -> str:
    """A token for ``model``, as the upload would issue it."""
    return TEST_SIGNER.issue(model, import_id=import_id, knowledge=kw.pop("knowledge", TEST_KNOWLEDGE), **kw)


def validate_model(model: CanonicalDistanceProtectionModel, decisions: ReviewDecisions = ReviewDecisions()):
    return validate_review(seal(model), TEST_IMPORT_ID, decisions, signer=TEST_SIGNER, knowledge_for=sealed_knowledge_for)


def reviewed_model_state(model: CanonicalDistanceProtectionModel, decisions: ReviewDecisions = ReviewDecisions()):
    return reviewed_state(seal(model), TEST_IMPORT_ID, decisions, signer=TEST_SIGNER, knowledge_for=sealed_knowledge_for)


def apply_model(model: CanonicalDistanceProtectionModel, decisions: ReviewDecisions = ReviewDecisions()):
    return apply_reviewed_settings(seal(model), TEST_IMPORT_ID, decisions, signer=TEST_SIGNER,
                                   knowledge_for=sealed_knowledge_for)


def review_ref(review: dict) -> dict:
    """The request fields that refer an API review back to the backend: its token and import id."""
    return {"validation_token": review["validation_token"], "import_id": review["import_id"]}


def sign_payload(payload: object, key: bytes = TEST_SIGNING_KEY) -> str:
    """A correctly signed token around an arbitrary payload (test-only): proves that what the token
    carries is still checked after the signature verifies (schema, expiry, identity, knowledge, snapshot)."""
    import base64
    import hashlib
    import hmac
    import zlib

    from app.services.relay_review_token import canonical_json

    def b64(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")

    signed = "v1." + b64(zlib.compress(canonical_json(payload), 9))
    return f"{signed}.{b64(hmac.new(key, signed.encode('ascii'), hashlib.sha256).digest())}"
