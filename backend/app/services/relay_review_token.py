"""Signed relay review validation tokens (DEC-198 Amendment 5).

The relay review stays stateless: the platform keeps nothing between the upload and the user's later
validate / Apply requests. The server-authored interpretation therefore travels with the browser -- but
no longer as editable JSON. The upload returns an opaque, signed **validation token**:

    "v1." + base64url(zlib(canonical JSON payload)) + "." + base64url(HMAC-SHA256(key, "v1." + body))

The payload carries the token schema, the backend-generated ``import_id``, ``issued_at`` /
``expires_at`` (UTC seconds), the relay knowledge the interpretation was made with (profile id and
version, plus the parameter catalog id, version and semantic digest for a catalog-based profile) and
the canonical interpretation snapshot (`canonical_codec`). Validation and Apply accept a request only
after the token verifies -- signature first, then schema, expiry, import identity and relay knowledge
-- and rebuild every authoritative review fact (manual-resolution authority included) from it.

What this gives: integrity (any changed byte is refused before engineering validation), expiry,
binding to one import and to the relay knowledge it was interpreted with, and no fabricated review
state. What it does NOT give: revocation. A token stays cryptographically valid until it expires,
even after the browser removed or superseded that import -- refusing it earlier would need server-side
state. The browser's remove / supersede handling remains the guard for that.

The browser never sees the key or the verification logic; to it the token is an opaque string. Every
refusal carries the same user-facing message (`INVALID_REVIEW_TOKEN`); the internal ``reason`` is for
tests and logs, never shown.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import logging
import secrets
import time
import uuid
import zlib
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.config import ConfigurationError, Settings
from app.domain.relay_import.canonical_codec import SnapshotError, decode_model, encode_model
from app.domain.relay_import.canonical_distance import CanonicalDistanceProtectionModel

logger = logging.getLogger(__name__)

__all__ = [
    "INVALID_REVIEW_TOKEN", "TOKEN_SCHEMA", "ReviewTokenError", "ReviewTokenSigner", "current_relay_knowledge",
    "new_import_id", "relay_knowledge", "signer_from_settings",
]

TOKEN_SCHEMA = "oruxa.relay-review-token/1"
_PREFIX = "v1"
#: The one message a user sees for a token that cannot be used (tampered, expired, for another import,
#: or made with relay knowledge that has since changed).
INVALID_REVIEW_TOKEN = "This relay review is no longer valid. Please upload the setting file again."
#: Clock skew tolerated for ``issued_at`` (seconds) between instances.
_CLOCK_SKEW_S = 300
#: Hard limits before anything is decompressed or parsed (a real token is a few tens of kilobytes).
MAX_TOKEN_LENGTH = 4_000_000
MAX_PAYLOAD_BYTES = 32_000_000

#: The relay knowledge an interpretation was made with, as compared at verification.
Knowledge = dict[str, Any]


class ReviewTokenError(ValueError):
    """A validation token that cannot be used. ``str(error)`` is always `INVALID_REVIEW_TOKEN`."""

    def __init__(self, reason: str) -> None:
        super().__init__(INVALID_REVIEW_TOKEN)
        #: Internal: why it was refused (tests / logs only; never shown to the user).
        self.reason = reason


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(text: str) -> bytes:
    if not text or any(c not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_" for c in text):
        raise ReviewTokenError("malformed")
    try:
        data = base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
    except (binascii.Error, ValueError) as exc:
        raise ReviewTokenError("malformed") from exc
    if _b64(data) != text:      # canonical only: no second spelling of the same bytes (unused trailing bits)
        raise ReviewTokenError("malformed")
    return data


def canonical_json(payload: Any) -> bytes:
    """Deterministic serialisation: sorted keys, no insignificant whitespace, UTF-8."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def new_import_id() -> str:
    """A backend-generated identity for one accepted relay import."""
    return uuid.uuid4().hex


@dataclass(frozen=True)
class ReviewTokenSigner:
    key: bytes = field(repr=False)
    ttl_s: int

    def __post_init__(self) -> None:
        if not isinstance(self.key, bytes) or len(self.key) < 32:
            raise ValueError("the signing key must be at least 32 bytes")
        if self.ttl_s <= 0:
            raise ValueError("the token lifetime must be positive")

    def _mac(self, signed: bytes) -> bytes:
        return hmac.new(self.key, signed, hashlib.sha256).digest()

    def issue(self, model: CanonicalDistanceProtectionModel, *, import_id: str, knowledge: Knowledge,
              now: float | None = None) -> str:
        issued = int(time.time() if now is None else now)
        payload = {
            "schema": TOKEN_SCHEMA, "import_id": import_id, "issued_at": issued, "expires_at": issued + self.ttl_s,
            "knowledge": knowledge, "model": encode_model(model),
        }
        body = _b64(zlib.compress(canonical_json(payload), 9))
        signed = f"{_PREFIX}.{body}"
        return f"{signed}.{_b64(self._mac(signed.encode('ascii')))}"

    def verify(self, token: Any, *, import_id: Any, knowledge_for: Callable[[str], Knowledge | None],
               now: float | None = None) -> CanonicalDistanceProtectionModel:
        """The interpretation the token carries, or `ReviewTokenError`. The signature is checked before
        anything in the token is decompressed, parsed or believed."""
        if not isinstance(token, str) or not token or len(token) > MAX_TOKEN_LENGTH:
            raise ReviewTokenError("malformed")
        parts = token.split(".")
        if len(parts) != 3 or parts[0] != _PREFIX:
            raise ReviewTokenError("malformed")
        signed = f"{parts[0]}.{parts[1]}".encode("ascii", errors="replace")
        if not hmac.compare_digest(self._mac(signed), _unb64(parts[2])):
            raise ReviewTokenError("signature")
        payload = self._payload(_unb64(parts[1]))
        if payload.get("schema") != TOKEN_SCHEMA:
            raise ReviewTokenError("schema")
        moment = time.time() if now is None else now
        issued, expires = payload.get("issued_at"), payload.get("expires_at")
        if not isinstance(issued, int) or not isinstance(expires, int) or issued > moment + _CLOCK_SKEW_S:
            raise ReviewTokenError("schema")
        if moment >= expires:
            raise ReviewTokenError("expired")
        expected = str(payload.get("import_id", "")).encode("utf-8")
        if not isinstance(import_id, str) or not hmac.compare_digest(expected, import_id.encode("utf-8", errors="replace")):
            raise ReviewTokenError("import")
        knowledge = payload.get("knowledge")
        if not isinstance(knowledge, dict) or not isinstance(knowledge.get("profile_id"), str):
            raise ReviewTokenError("schema")
        if knowledge_for(knowledge["profile_id"]) != knowledge:
            raise ReviewTokenError("knowledge")
        try:
            return decode_model(payload.get("model"))
        except SnapshotError as exc:           # signed by us, so only a schema change between versions
            raise ReviewTokenError("schema") from exc

    @staticmethod
    def _payload(compressed: bytes) -> dict:
        try:
            inflater = zlib.decompressobj()
            raw = inflater.decompress(compressed, MAX_PAYLOAD_BYTES)
            if inflater.unconsumed_tail:
                raise ReviewTokenError("malformed")
            payload = json.loads(raw.decode("utf-8"))
        except (zlib.error, UnicodeDecodeError, ValueError) as exc:
            raise ReviewTokenError("malformed") from exc
        if not isinstance(payload, dict):
            raise ReviewTokenError("malformed")
        return payload


def signer_from_settings(settings: Settings) -> ReviewTokenSigner:
    """The signer for this process. A deployed build must configure the key (shared by every instance);
    outside a deployment, a missing key is replaced by a random per-process key -- tokens then do not
    survive a restart and are not accepted by another process, which is fine for local work only."""
    ttl_s = settings.relay_review_token_ttl_hours * 3600
    if settings.relay_review_signing_key:
        return ReviewTokenSigner(settings.relay_review_signing_key.encode("utf-8"), ttl_s)
    if settings.is_deployed:
        raise ConfigurationError("RELAY_REVIEW_SIGNING_KEY must be set in a deployed environment")
    logger.warning("RELAY_REVIEW_SIGNING_KEY is not set: relay review tokens use a random per-process key "
                   "(local development only)")
    return ReviewTokenSigner(secrets.token_bytes(32), ttl_s)


# --- relay knowledge ----------------------------------------------------------------------------------

def relay_knowledge(profile: Any) -> Knowledge:
    """What the interpretation depends on: the profile and its version, plus -- for a catalog-based
    profile -- the catalog id, version and semantic digest. Stable structured identities, not display text."""
    knowledge: Knowledge = {"profile_id": profile.profile_id, "profile_version": profile.version}
    catalog = getattr(profile, "catalog", None)
    if catalog is not None:
        knowledge["catalog"] = {"id": catalog.catalog_id, "version": catalog.version,
                                "digest": getattr(profile, "catalog_digest", None)}
    return knowledge


def current_relay_knowledge(profile_id: str) -> Knowledge | None:
    """The relay knowledge the running service would interpret ``profile_id`` with now -- from the same
    registry the upload interprets with -- or ``None`` when no such profile exists any more."""
    from app.services import relay_import_upload_service

    profile = relay_import_upload_service.default_registry().profile(profile_id)
    return relay_knowledge(profile) if profile is not None else None
