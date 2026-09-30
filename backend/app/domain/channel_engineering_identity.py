"""Deterministic channel engineering identity interpretation.

This module is deliberately smaller than a classifier: broad engineering
quantity still comes from structured metadata/unit semantics upstream
(`channel_classification`). The resolver here interprets deterministic
engineering role tokens in a channel name so grouping layers can share one
grammar instead of each parsing names differently.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.domain.channel_classification import CURRENT, VOLTAGE, classify_analog_channel
from app.domain.measurement_group import KIND_CURRENT, KIND_VOLTAGE, kind_for_engineering_type
from app.domain.phase_identity import (
    PHASE_SOURCE_DETECTED_FROM_NAME,
    PHASE_SOURCE_STRUCTURED_METADATA,
)

ROLE_TOKEN_KIND_SINGLE = "single"
ROLE_TOKEN_KIND_NEUTRAL = "neutral"
ROLE_TOKEN_KIND_PAIR = "pair"
ROLE_TOKEN_KIND_L123 = "l123"

REPRESENTATION_REFERENCE = "reference"
REPRESENTATION_PAIR = "pair"

ROLE_POSITION_PREFIX = "prefix"
ROLE_POSITION_SUFFIX = "suffix"

_PAIR_TOKENS = frozenset({"RY", "YR", "YB", "BY", "BR", "RB", "AB", "BA", "BC", "CB", "CA", "AC"})
_NEUTRAL_TOKENS = frozenset({"RN", "YN", "BN", "AN", "CN"})
_SINGLE_TOKENS = frozenset({"R", "Y", "B", "A", "C"})
_L123_TOKENS = frozenset({"L1", "L2", "L3"})

_ROLE_MARKER_TO_KIND = {
    "V": KIND_VOLTAGE,
    "U": KIND_VOLTAGE,
    "I": KIND_CURRENT,
}

_TRAILING_UNIT_DECORATION = re.compile(r"^(?P<label>.*)\s+\((?P<unit>[^()]+)\)$")
_SEPARATED_ROLE_PREFIX = re.compile(r"^(?P<role>[A-Za-z][A-Za-z0-9]{0,2})(?P<sep>[\s_-]+)(?P<context>.+)$")
_SEPARATED_ROLE_SUFFIX = re.compile(r"^(?P<context>.+?)(?P<sep>[\s_-]+)(?P<role>[A-Za-z][A-Za-z0-9]{0,2})$")


@dataclass(frozen=True, slots=True)
class ChannelEngineeringIdentityInput:
    name: str
    engineering_type: str
    phase_label: str | None = None
    unit: str | None = None


@dataclass(frozen=True, slots=True)
class EngineeringRoleToken:
    marker: str
    kind: str
    raw_token: str
    token_kind: str
    original_label: str
    position: str

    @property
    def representation(self) -> str:
        return REPRESENTATION_PAIR if self.token_kind == ROLE_TOKEN_KIND_PAIR else REPRESENTATION_REFERENCE


@dataclass(slots=True)
class ChannelEngineeringIdentity:
    name: str
    engineering_type: str
    kind: str | None
    context_hint: str | None = None
    role_token: EngineeringRoleToken | None = None
    phase_raw_token: str | None = None
    phase_token_kind: str | None = None
    phase_source: str | None = None
    original_phase_label: str | None = None
    name_raw_token: str | None = None
    name_token_kind: str | None = None
    name_original_label: str | None = None
    unit_decoration: str | None = None
    unit_decoration_engineering_type: str | None = None
    evidence: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)

    @property
    def has_role(self) -> bool:
        return self.role_token is not None

    @property
    def has_conflict(self) -> bool:
        return bool(self.issues)


def _clean_context_hint(context: str | None) -> str | None:
    if context is None:
        return None
    cleaned = context.strip().strip("_- ").strip()
    return cleaned or None


def _recognized_unit_decoration(name: str) -> tuple[str, str | None, str | None]:
    match = _TRAILING_UNIT_DECORATION.match(name.strip())
    if not match:
        return name.strip(), None, None
    unit = match.group("unit").strip()
    unit_engineering_type = classify_analog_channel(parameter_type=None, unit=unit)
    if unit_engineering_type not in {VOLTAGE, CURRENT}:
        return name.strip(), None, None
    return match.group("label").strip(), unit, unit_engineering_type


def _phase_part(role: str) -> tuple[str, str] | None:
    upper = role.upper()
    for token in sorted(_PAIR_TOKENS, key=len, reverse=True):
        if upper == token:
            return token, ROLE_TOKEN_KIND_PAIR
    if upper in _L123_TOKENS:
        return upper, ROLE_TOKEN_KIND_L123
    if upper in _NEUTRAL_TOKENS:
        return upper[:-1], ROLE_TOKEN_KIND_NEUTRAL
    if upper in _SINGLE_TOKENS:
        return upper, ROLE_TOKEN_KIND_SINGLE
    return None


def _parse_role_text(role_text: str, position: str) -> EngineeringRoleToken | None:
    role = role_text.strip()
    if len(role) < 2:
        return None
    marker = role[0].upper()
    kind = _ROLE_MARKER_TO_KIND.get(marker)
    if kind is None:
        return None
    parsed_phase = _phase_part(role[1:])
    if parsed_phase is None:
        return None
    raw_token, token_kind = parsed_phase
    if kind == KIND_CURRENT and token_kind == ROLE_TOKEN_KIND_PAIR:
        return None
    return EngineeringRoleToken(
        marker=marker,
        kind=kind,
        raw_token=raw_token,
        token_kind=token_kind,
        original_label=role[1:],
        position=position,
    )


def _match_name_role(undecorated_name: str) -> tuple[str | None, EngineeringRoleToken | None]:
    stripped = undecorated_name.strip()
    if not stripped:
        return None, None

    prefix = _SEPARATED_ROLE_PREFIX.match(stripped)
    if prefix:
        token = _parse_role_text(prefix.group("role"), ROLE_POSITION_PREFIX)
        if token is not None:
            return _clean_context_hint(prefix.group("context")), token

    suffix = _SEPARATED_ROLE_SUFFIX.match(stripped)
    if suffix:
        token = _parse_role_text(suffix.group("role"), ROLE_POSITION_SUFFIX)
        if token is not None:
            return _clean_context_hint(suffix.group("context")), token

    for role_len in (4, 3, 2):
        if len(stripped) <= role_len:
            continue
        role_text = stripped[-role_len:]
        token = _parse_role_text(role_text, ROLE_POSITION_SUFFIX)
        if token is not None:
            return _clean_context_hint(stripped[:-role_len]), token

    token = _parse_role_text(stripped, ROLE_POSITION_SUFFIX)
    if token is not None:
        return None, token
    return None, None


def _match_structured_label(phase_label: str | None, kind: str | None) -> tuple[str, str] | None:
    if not phase_label or not phase_label.strip():
        return None
    upper = phase_label.strip().upper()
    if upper in _L123_TOKENS:
        return upper, ROLE_TOKEN_KIND_L123
    if upper in _SINGLE_TOKENS:
        return upper, ROLE_TOKEN_KIND_SINGLE
    if upper in _NEUTRAL_TOKENS:
        return upper[:-1], ROLE_TOKEN_KIND_NEUTRAL
    if kind == KIND_VOLTAGE and upper in _PAIR_TOKENS:
        return upper, ROLE_TOKEN_KIND_PAIR
    return None


def identity_evidence_letters(raw_token: str | None, token_kind: str | None) -> list[str]:
    if not raw_token or not token_kind:
        return []
    if token_kind == ROLE_TOKEN_KIND_PAIR:
        return [raw_token[0], raw_token[1]]
    return [raw_token]


def resolve_channel_engineering_identity(ch: ChannelEngineeringIdentityInput) -> ChannelEngineeringIdentity:
    """Resolve deterministic semantic identity evidence for one channel.

    Conflicts are reported in `issues`; callers decide whether that means
    exclusion or `needs_review` for their own grouping semantics.
    """
    kind = kind_for_engineering_type(ch.engineering_type)
    undecorated_name, unit_decoration, unit_engineering_type = _recognized_unit_decoration(ch.name)
    context_hint, role_token = _match_name_role(undecorated_name)
    identity = ChannelEngineeringIdentity(
        name=ch.name,
        engineering_type=ch.engineering_type,
        kind=kind,
        context_hint=context_hint,
        role_token=role_token,
        unit_decoration=unit_decoration,
        unit_decoration_engineering_type=unit_engineering_type,
    )

    if unit_decoration is not None:
        identity.evidence.append(f"unit_decoration:{unit_decoration}")
        if unit_engineering_type != ch.engineering_type:
            identity.issues.append("unit_decoration_conflicts_with_engineering_type")

    if role_token is None:
        return identity

    identity.name_raw_token = role_token.raw_token
    identity.name_token_kind = role_token.token_kind
    identity.name_original_label = role_token.original_label
    identity.evidence.append(f"name_role:{role_token.marker}{role_token.original_label}")

    if kind is not None and role_token.kind != kind:
        identity.issues.append("name_role_conflicts_with_engineering_type")

    structured = _match_structured_label(ch.phase_label, kind)
    if structured is not None:
        identity.phase_raw_token, identity.phase_token_kind = structured
        identity.phase_source = PHASE_SOURCE_STRUCTURED_METADATA
        identity.original_phase_label = ch.phase_label.strip() if ch.phase_label else ""
        identity.evidence.append(f"structured_phase:{identity.original_phase_label}")
    else:
        identity.phase_raw_token = role_token.raw_token
        identity.phase_token_kind = role_token.token_kind
        identity.phase_source = PHASE_SOURCE_DETECTED_FROM_NAME
        identity.original_phase_label = role_token.original_label

    return identity
