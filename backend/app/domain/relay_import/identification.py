"""Relay identification: which relay family/model does a document most likely
belong to?  ``RawRelayDocument -> RelayIdentifier -> RelayIdentification``.

Relay Import Slice 5. Identification is **not interpretation**: it never
reads an engineering value, never populates the canonical model and never
makes a document "validated". A catalogue entry only means the relay is
*recognisable*.

This module is relay-neutral. Everything relay-specific (model tokens,
family markers, parameter-naming signatures, manufacturer aliases) arrives as
data -- ``RelayIdentificationDescriptor`` objects and a ``ManufacturerAliases``
table -- supplied by a catalogue that lives outside the domain package. The
identifier itself contains no relay names.

Scoring (deterministic, inspectable; **not** a probability)
-----------------------------------------------------------
Each descriptor is scored independently by summing evidence points, each
evidence kind capped so that repetition cannot masquerade as proof:

====================  ======  =============================================
evidence kind         points  meaning
====================  ======  =============================================
scheme_model             100  model token inside a scheme/template field
labelled_model            90  model token inside a model/type/order-code
                              field (``Type``, ``Product Code``, ...)
model_mention             10  model token elsewhere (cap 30, i.e. 3 places)
family_marker             25  family/brand marker (cap 25)
parameter_signature       20  distinctive parameter-naming family that
                              occurs at least ``min_matches`` times (cap 40)
manufacturer_name         10  manufacturer or alias named (cap 10)
====================  ======  =============================================

Generic protection vocabulary (zone, reach, resistance, CT, VT, ...) is never
evidence: descriptors carry only distinctive tokens/patterns. Tokens match
only as whole alphanumeric runs, so a model token never matches inside a
longer identifier (a station code that merely begins with a manufacturer's
initials, say).

Decision rules (``ScoringRules``): the best candidate must reach
``identify_threshold`` (60) *and* lead every other candidate by at least
``ambiguity_margin`` (30) -- or ``indirect_ambiguity_margin`` (60) when it has
no explicit scheme/model field behind it. Otherwise:

* best below the threshold            -> ``unknown`` (a valid outcome);
* best at/above it but with a rival
  inside the margin                   -> ``ambiguous`` (nothing is picked).

Confidence is categorical: ``high`` = identified and the model token sits in
an explicit scheme/model field; ``medium`` = identified from combined
indirect evidence only; ``low`` = ambiguous, or unknown with weak candidates;
``none`` = no evidence at all.

Determinism: no randomness, no clock, no I/O; candidates are ordered by
(-score, profile_id) and evidence by document order.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Mapping

from app.domain.relay_import.raw_document import RawRelayDocument, RawSetting

_MATCH_TEXT_LIMIT = 80
_FIELD_VALUE_LIMIT = 120


class IdentificationStatus(StrEnum):
    IDENTIFIED = "identified"
    AMBIGUOUS = "ambiguous"
    UNKNOWN = "unknown"


class IdentificationConfidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NONE = "none"


class EvidenceKind(StrEnum):
    SCHEME_MODEL = "scheme_model"
    LABELLED_MODEL = "labelled_model"
    MODEL_MENTION = "model_mention"
    FAMILY_MARKER = "family_marker"
    PARAMETER_SIGNATURE = "parameter_signature"
    MANUFACTURER_NAME = "manufacturer_name"


#: Evidence kinds that put the model in an explicit identifying field.
EXPLICIT_MODEL_KINDS = frozenset({EvidenceKind.SCHEME_MODEL, EvidenceKind.LABELLED_MODEL})


@dataclass(frozen=True)
class ScoringRules:
    scheme_model: int = 100
    labelled_model: int = 90
    model_mention: int = 10
    model_mention_cap: int = 30
    family_marker: int = 25
    family_marker_cap: int = 25
    parameter_signature: int = 20
    parameter_signature_cap: int = 40
    manufacturer_name: int = 10
    manufacturer_name_cap: int = 10
    identify_threshold: int = 60
    ambiguity_margin: int = 30
    #: Required lead when the best candidate has no explicit scheme/model
    #: field behind it. Incidental mentions can name a sibling line (a sheet
    #: for one product quoting another's name in option text), so indirect
    #: evidence alone must win by more to be trusted.
    indirect_ambiguity_margin: int = 60
    #: Field labels (compared case-insensitively, whitespace-normalised).
    scheme_labels: tuple[str, ...] = ("scheme name", "template name", "scheme", "template")
    model_labels: tuple[str, ...] = (
        "relay type", "relay model", "device type", "ordering code", "order code",
        "product code", "order no", "catalogue no", "mlfb", "model", "type",
    )
    version_labels: tuple[str, ...] = (
        "firmware version", "software version", "sw version", "main software", "firmware",
    )


DEFAULT_RULES = ScoringRules()


@dataclass(frozen=True)
class ParameterSignature:
    """A distinctive parameter-naming family of one relay line.

    ``pattern`` is a regular expression searched in ``target`` of each raw
    entry: ``name``, ``parameter_id`` or ``text`` (the whole source line).
    It counts only when at least ``min_matches`` entries match, so a stray
    coincidence is not evidence.
    """

    signature_id: str
    pattern: str
    target: str = "name"
    min_matches: int = 1
    ignore_case: bool = False

    def __post_init__(self) -> None:
        if self.target not in {"name", "parameter_id", "text"}:
            raise ValueError(f"unknown signature target {self.target!r}")
        if self.min_matches < 1:
            raise ValueError("min_matches must be >= 1")
        re.compile(self.pattern)


@dataclass(frozen=True)
class RelayIdentificationDescriptor:
    """Identification-only description of one recognisable relay line.

    Deliberately carries no engineering mapping: that belongs to a future
    ``RelayProfile``. ``manufacturer`` is the normalised identity, or ``None``
    when the project has not established it (never guessed).
    """

    profile_id: str
    relay_family: str
    manufacturer: str | None = None
    model: str | None = None
    #: Regex fragments for the model identifier; matched as whole
    #: alphanumeric runs, case-insensitively.
    model_patterns: tuple[str, ...] = ()
    #: Regex fragments for family/brand markers (not the model itself).
    family_markers: tuple[str, ...] = ()
    parameter_signatures: tuple[ParameterSignature, ...] = ()

    def __post_init__(self) -> None:
        if not self.profile_id:
            raise ValueError("profile_id is required")
        for fragment in (*self.model_patterns, *self.family_markers):
            re.compile(fragment)


def _norm(text: str) -> str:
    return " ".join(text.casefold().replace("_", " ").replace("-", " ").split())


@dataclass(frozen=True)
class ManufacturerAliases:
    """Brand transitions: canonical manufacturer name -> other names it has
    been published under. The source spelling is kept in the result; the
    canonical name is exposed separately."""

    table: tuple[tuple[str, tuple[str, ...]], ...] = ()

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, tuple[str, ...]]) -> "ManufacturerAliases":
        return cls(tuple((name, tuple(aliases)) for name, aliases in mapping.items()))

    def names_for(self, canonical: str) -> tuple[str, ...]:
        for name, aliases in self.table:
            if name == canonical:
                return (name, *aliases)
        return (canonical,)

    def normalize(self, name: str) -> str | None:
        """Canonical manufacturer for an exact (case/space-insensitive)
        known name or alias, else ``None``."""
        wanted = _norm(name)
        for canonical, aliases in self.table:
            if wanted in {_norm(n) for n in (canonical, *aliases)}:
                return canonical
        return None


@dataclass(frozen=True)
class IdentificationEvidence:
    kind: EvidenceKind
    points: int
    matched_text: str
    detail: str
    setting_id: str | None = None
    page: int | None = None


@dataclass(frozen=True)
class IdentificationCandidate:
    profile_id: str
    relay_family: str
    manufacturer: str | None
    model: str | None
    score: int
    evidence: tuple[IdentificationEvidence, ...]

    @property
    def has_explicit_model_evidence(self) -> bool:
        return any(e.kind in EXPLICIT_MODEL_KINDS for e in self.evidence)


@dataclass(frozen=True)
class RelayIdentification:
    status: IdentificationStatus
    confidence: IdentificationConfidence
    #: Selected identity -- set only when ``status`` is ``identified``.
    profile_id: str | None = None
    #: Normalised manufacturer. For an ambiguous result it is set only when
    #: every tied candidate agrees.
    manufacturer: str | None = None
    #: The spelling found in the document, when a name/alias was present.
    manufacturer_source_name: str | None = None
    relay_family: str | None = None
    model: str | None = None
    #: Explicit version text only (a ``V<n>`` marker in the scheme name or a
    #: labelled firmware/software field); never inferred.
    version: str | None = None
    version_source: str | None = None
    scheme_name: str | None = None
    score: int = 0
    #: Evidence for the selected candidate (empty unless identified).
    evidence: tuple[IdentificationEvidence, ...] = ()
    #: Every candidate with positive score, best first.
    candidates: tuple[IdentificationCandidate, ...] = ()
    #: Candidates worth showing next to the result: all tied ones when
    #: ambiguous; for an identified result, rivals that also reached the
    #: identification threshold.
    alternatives: tuple[IdentificationCandidate, ...] = ()
    warnings: tuple[str, ...] = ()

@dataclass(frozen=True)
class _Source:
    text: str
    setting_id: str | None = None
    page: int | None = None


@dataclass(frozen=True)
class _Field:
    role: str  # "scheme" | "model" | "version"
    label: str
    value: str
    setting_id: str | None
    page: int | None


def _token_regex(fragments: tuple[str, ...]) -> re.Pattern[str] | None:
    if not fragments:
        return None
    body = "|".join(f"(?:{f})" for f in fragments)
    return re.compile(rf"(?<![A-Za-z0-9])(?:{body})(?![A-Za-z0-9])", re.IGNORECASE)


def _clip(text: str, limit: int = _MATCH_TEXT_LIMIT) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _label_pattern(label: str) -> str:
    return r"\s+".join(re.escape(part) for part in label.split())


def _setting_text(s: RawSetting) -> str:
    parts: list[str] = []
    if s.source_text:
        parts.append(s.source_text)
    else:
        parts.extend(str(p) for p in (s.parameter_id, s.name, s.raw_value) if p is not None)
    if s.setting_range and s.setting_range.text:
        parts.append(s.setting_range.text)
    parts.extend(s.notes)
    return " ".join(parts)


class RelayIdentifier:
    def __init__(
        self,
        descriptors: tuple[RelayIdentificationDescriptor, ...],
        aliases: ManufacturerAliases | None = None,
        rules: ScoringRules = DEFAULT_RULES,
    ) -> None:
        ids = [d.profile_id for d in descriptors]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate identification descriptor profile_id")
        self._descriptors = tuple(descriptors)
        self._aliases = aliases or ManufacturerAliases()
        self._rules = rules
        self._model_tokens = {d.profile_id: _token_regex(d.model_patterns) for d in descriptors}
        self._family_tokens = {
            d.profile_id: tuple((f, _token_regex((f,))) for f in d.family_markers) for d in descriptors
        }
        self._alias_tokens: dict[str, tuple[tuple[str, re.Pattern[str]], ...]] = {}
        for d in descriptors:
            if d.manufacturer:
                self._alias_tokens[d.profile_id] = tuple(
                    (name, _token_regex((re.escape(name),))) for name in self._aliases.names_for(d.manufacturer)
                )
        self._signatures = {
            d.profile_id: tuple(
                (sig, re.compile(sig.pattern, re.IGNORECASE if sig.ignore_case else 0))
                for sig in d.parameter_signatures
            )
            for d in descriptors
        }
        labels = {
            **{_norm(lbl): "scheme" for lbl in rules.scheme_labels},
            **{_norm(lbl): "model" for lbl in rules.model_labels},
            **{_norm(lbl): "version" for lbl in rules.version_labels},
        }
        self._label_roles = labels
        alternation = "|".join(
            _label_pattern(lbl) for lbl in sorted({*rules.scheme_labels, *rules.model_labels, *rules.version_labels}, key=len, reverse=True)
        )
        self._inline_field = re.compile(
            rf"(?<![A-Za-z0-9])(?P<label>{alternation})\s*[:=]\s*(?P<value>\S+(?: \S+)*)", re.IGNORECASE
        )
        self._scheme_version = re.compile(r"(?<![A-Za-z0-9])(?:Ver\.?|V)\s?(\d+(?:\.\d+)*)(?![A-Za-z0-9])", re.IGNORECASE)

    # ------------------------------------------------------------------
    @property
    def rules(self) -> ScoringRules:
        return self._rules

    def identify(self, document: RawRelayDocument) -> RelayIdentification:
        fields = self._fields(document)
        sources = self._sources(document)
        targets = {
            "name": [x.name or "" for x in document.settings],
            "parameter_id": [x.parameter_id or "" for x in document.settings],
            "text": [x.source_text or _setting_text(x) for x in document.settings],
        }
        scheme_name = next((f.value for f in fields if f.role == "scheme"), None)

        candidates = [c for d in self._descriptors if (c := self._score(d, document, fields, sources, targets)) is not None]
        candidates.sort(key=lambda c: (-c.score, c.profile_id))
        ranked = tuple(candidates)
        rules = self._rules

        if not sources:
            return RelayIdentification(
                IdentificationStatus.UNKNOWN, IdentificationConfidence.NONE, scheme_name=scheme_name,
                warnings=("The document contains no readable content to identify.",),
            )
        top = ranked[0] if ranked else None
        if top is None or top.score < rules.identify_threshold:
            warnings = ()
            if top is not None:
                weak = ", ".join(f"{c.profile_id} ({c.score})" for c in ranked[:3])
                warnings = (f"Only weak evidence for: {weak}; below the identification threshold of {rules.identify_threshold}.",)
            return RelayIdentification(
                IdentificationStatus.UNKNOWN,
                IdentificationConfidence.LOW if top is not None else IdentificationConfidence.NONE,
                scheme_name=scheme_name, candidates=ranked, warnings=warnings,
            )

        margin = rules.ambiguity_margin if top.has_explicit_model_evidence else rules.indirect_ambiguity_margin
        tied = [top] + [c for c in ranked[1:] if top.score - c.score < margin]
        if len(tied) > 1:
            manufacturers = {c.manufacturer for c in tied}
            families = {c.relay_family for c in tied}
            return RelayIdentification(
                IdentificationStatus.AMBIGUOUS,
                IdentificationConfidence.LOW,
                manufacturer=next(iter(manufacturers)) if len(manufacturers) == 1 else None,
                relay_family=next(iter(families)) if len(families) == 1 else None,
                scheme_name=scheme_name,
                candidates=ranked,
                alternatives=tuple(tied),
                warnings=(
                    "Several relay types match similarly: "
                    + ", ".join(f"{c.profile_id} ({c.score})" for c in tied)
                    + ". No relay was selected.",
                ),
            )

        warnings: list[str] = []
        rivals = [c for c in ranked[1:] if c.score >= rules.identify_threshold]
        if rivals:
            warnings.append(
                "The document also references: " + ", ".join(f"{c.profile_id} ({c.score})" for c in rivals) + "."
            )
        explicit = top.has_explicit_model_evidence
        if not explicit:
            warnings.append("Identified from indirect evidence only; no explicit scheme or model field named the relay.")
        version, version_source = self._version(fields)
        seen = next(
            (e.matched_text for e in top.evidence if e.kind is EvidenceKind.MANUFACTURER_NAME), None
        )
        return RelayIdentification(
            IdentificationStatus.IDENTIFIED,
            IdentificationConfidence.HIGH if explicit else IdentificationConfidence.MEDIUM,
            profile_id=top.profile_id,
            manufacturer=top.manufacturer,
            manufacturer_source_name=seen,
            relay_family=top.relay_family,
            model=top.model,
            version=version,
            version_source=version_source,
            scheme_name=scheme_name,
            score=top.score,
            evidence=top.evidence,
            candidates=ranked,
            alternatives=tuple(rivals),
            warnings=tuple(warnings),
        )

    # ------------------------------------------------------------------
    def _sources(self, document: RawRelayDocument) -> list[_Source]:
        sources = [_Source(_clip(h, 400)) for h in document.identification_hints]
        sections: set[str] = set()
        for s in document.settings:
            sources.append(_Source(_setting_text(s), s.setting_id, s.location.page))
            sections.update(s.section_path)
        sources.extend(_Source(title) for title in sorted(sections))
        return [s for s in sources if s.text.strip()]

    def _fields(self, document: RawRelayDocument) -> list[_Field]:
        fields: list[_Field] = []
        for hint in document.identification_hints:
            fields.extend(self._inline_fields(hint, None, None))
        for s in document.settings:
            role = self._label_roles.get(_norm(s.name or "").rstrip(":")) if s.name else None
            if role and s.raw_value not in (None, ""):
                fields.append(_Field(role, s.name or "", _clip(str(s.raw_value), _FIELD_VALUE_LIMIT), s.setting_id, s.location.page))
            text = s.source_text or _setting_text(s)
            fields.extend(self._inline_fields(text, s.setting_id, s.location.page))
        return fields

    def _inline_fields(self, text: str, setting_id: str | None, page: int | None) -> list[_Field]:
        out = []
        for m in self._inline_field.finditer(text):
            role = self._label_roles.get(_norm(m.group("label")))
            if role:
                out.append(_Field(role, m.group("label"), _clip(m.group("value"), _FIELD_VALUE_LIMIT), setting_id, page))
        return out

    def _version(self, fields: list[_Field]) -> tuple[str | None, str | None]:
        field_version = next((f for f in fields if f.role == "version"), None)
        if field_version:
            return field_version.value, f"labelled field '{field_version.label}'"
        for f in fields:
            if f.role == "scheme":
                m = self._scheme_version.search(f.value)
                if m:
                    return m.group(1), "scheme name"
        return None, None

    # ------------------------------------------------------------------
    def _score(
        self,
        d: RelayIdentificationDescriptor,
        document: RawRelayDocument,
        fields: list[_Field],
        sources: list[_Source],
        targets: dict[str, list[str]],
    ) -> IdentificationCandidate | None:
        rules = self._rules
        evidence: list[IdentificationEvidence] = []
        token = self._model_tokens[d.profile_id]
        consumed: set[str] = set()

        if token is not None:
            for role, kind, points, label in (
                ("scheme", EvidenceKind.SCHEME_MODEL, rules.scheme_model, "scheme/template field"),
                ("model", EvidenceKind.LABELLED_MODEL, rules.labelled_model, "model/type field"),
            ):
                for f in fields:
                    if f.role == role and (m := token.search(f.value)):
                        evidence.append(
                            IdentificationEvidence(
                                kind, points, _clip(m.group(0)), f"{label} '{f.label}': {_clip(f.value)}", f.setting_id, f.page
                            )
                        )
                        if f.setting_id:
                            consumed.add(f.setting_id)
                        break
            mentions = 0
            for src in sources:
                if mentions * rules.model_mention >= rules.model_mention_cap:
                    break
                if src.setting_id in consumed:
                    continue
                if m := token.search(src.text):
                    mentions += 1
                    evidence.append(
                        IdentificationEvidence(
                            EvidenceKind.MODEL_MENTION, rules.model_mention, _clip(m.group(0)),
                            f"model identifier in document text: {_clip(src.text)}", src.setting_id, src.page,
                        )
                    )

        family_points = 0
        for fragment, regex in self._family_tokens[d.profile_id]:
            if family_points >= rules.family_marker_cap:
                break
            for src in sources:
                if m := regex.search(src.text):
                    family_points += rules.family_marker
                    evidence.append(
                        IdentificationEvidence(
                            EvidenceKind.FAMILY_MARKER, rules.family_marker, _clip(m.group(0)),
                            f"family marker in document text: {_clip(src.text)}", src.setting_id, src.page,
                        )
                    )
                    break

        signature_points = 0
        for sig, regex in self._signatures[d.profile_id]:
            if signature_points >= rules.parameter_signature_cap:
                break
            texts = targets[sig.target]
            hits = [i for i, text in enumerate(texts) if text and regex.search(text)]
            if len(hits) >= sig.min_matches:
                signature_points += rules.parameter_signature
                first = document.settings[hits[0]]
                evidence.append(
                    IdentificationEvidence(
                        EvidenceKind.PARAMETER_SIGNATURE, rules.parameter_signature,
                        _clip(texts[hits[0]]),
                        f"parameter naming '{sig.signature_id}' ({len(hits)} entries)", first.setting_id, first.location.page,
                    )
                )

        name_points = 0
        for name, regex in self._alias_tokens.get(d.profile_id, ()):
            if name_points >= rules.manufacturer_name_cap:
                break
            for src in sources:
                if m := regex.search(src.text):
                    name_points += rules.manufacturer_name
                    evidence.append(
                        IdentificationEvidence(
                            EvidenceKind.MANUFACTURER_NAME, rules.manufacturer_name, _clip(m.group(0)),
                            f"manufacturer name in document text: {_clip(src.text)}", src.setting_id, src.page,
                        )
                    )
                    break

        score = sum(e.points for e in evidence)
        if score <= 0:
            return None
        return IdentificationCandidate(d.profile_id, d.relay_family, d.manufacturer, d.model, score, tuple(evidence))
