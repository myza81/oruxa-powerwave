"""Base-authority state model for Voltage and Current measurement groups.

DEC-050 Slice 5B — authority foundation.

Defines the ``BaseAuthorityState`` vocabulary and predicate utilities that
the future automatic-authority workflow (Slices 5C+) will consult when
deciding whether a measurement group's configured base may be used for PU
resolution.

Design constraints:
  §1  Authority state and Measurement Group identity status (confirmed /
      manual / suggested / …) are INDEPENDENT concepts.  A suggested group
      may eventually carry ``auto_resolved`` authority; a confirmed group
      whose automatic evidence is subsequently contradicted must transition
      to ``unavailable``, not silently keep its old value.
  §2  ``legacy_manual`` is the backward-compatible default for every
      ``VoltageBaseConfiguration`` and ``CurrentBaseConfiguration`` that
      was persisted before this field existed.  It preserves exactly the
      same PU behaviour those configurations had before Slice 5B.
  §3  Manual engineer override (``manual`` or ``legacy_manual``) takes
      precedence over any subsequent automatic recommendation.
  §4  An ``unavailable`` state means the previously resolved automatic base
      is no longer usable, even when the Measurement Group's status is
      ``confirmed`` or ``manual``.  The active resolvers do not check this
      field yet (Slice 5B establishes the vocabulary; Slice 5C wires it).
  §5  ``needs_review`` means evidence was analysed but insufficient or
      contradictory.  It does not produce a usable base; it signals that
      engineer attention is required.
  §6  No automatic PU activation is performed by this module.  It provides
      types and pure predicates only.
"""

from __future__ import annotations

from typing import Literal

# ---------------------------------------------------------------------------
# Type alias
# ---------------------------------------------------------------------------

BaseAuthorityState = Literal[
    "legacy_manual",   # Configured before base_authority existed; treated as manual
    "manual",          # Explicitly set by engineer in the new system
    "auto_resolved",   # Set by automatic evidence resolution (Slice 5C+)
    "needs_review",    # Evidence analysed but insufficient or contradictory
    "unavailable",     # Formerly auto_resolved; subsequently invalidated
]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_AUTHORITY_LEGACY = "legacy_manual"
BASE_AUTHORITY_MANUAL = "manual"
BASE_AUTHORITY_AUTO = "auto_resolved"
BASE_AUTHORITY_NEEDS_REVIEW = "needs_review"
BASE_AUTHORITY_UNAVAILABLE = "unavailable"

KNOWN_BASE_AUTHORITY_STATES: tuple[BaseAuthorityState, ...] = (
    BASE_AUTHORITY_LEGACY,
    BASE_AUTHORITY_MANUAL,
    BASE_AUTHORITY_AUTO,
    BASE_AUTHORITY_NEEDS_REVIEW,
    BASE_AUTHORITY_UNAVAILABLE,
)

# ---------------------------------------------------------------------------
# Predicates
# ---------------------------------------------------------------------------

def is_base_eligible_for_pu(state: str) -> bool:
    """True when the authority state permits the configured base to be used
    for PU resolution.

    ``legacy_manual`` and ``manual`` are always eligible (engineer-approved).
    ``auto_resolved`` is eligible (evidence was resolved, no contradictions).
    ``needs_review`` and ``unavailable`` are NOT eligible — engineer attention
    or re-resolution is required first.

    This predicate describes the INTENDED gate once Slice 5C wires it into
    ``resolve_voltage_base_for_group()`` and ``resolve_current_base_for_group()``.
    The live resolvers do not call it yet (Slice 5B establishes the vocabulary
    only; Slice 5C activates the gate).
    """
    return state in (BASE_AUTHORITY_LEGACY, BASE_AUTHORITY_MANUAL, BASE_AUTHORITY_AUTO)


def is_engineer_approved(state: str) -> bool:
    """True when the base was established (or implicitly confirmed) by an
    engineer rather than automatic evidence.

    ``legacy_manual``: configured before the authority field existed —
    implicit engineer approval by virtue of the engineer having entered the
    value.

    ``manual``: explicitly set by the engineer in the new system.

    All other states (``auto_resolved``, ``needs_review``, ``unavailable``)
    are not engineer-approved, even if the Measurement Group itself is
    ``confirmed`` or ``manual`` status.
    """
    return state in (BASE_AUTHORITY_LEGACY, BASE_AUTHORITY_MANUAL)


def is_auto_resolved(state: str) -> bool:
    """True when the base was established by automatic evidence resolution
    (not by an engineer), and has not since been invalidated.
    """
    return state == BASE_AUTHORITY_AUTO


def is_base_invalidated(state: str) -> bool:
    """True when the base was previously auto_resolved but has subsequently
    been contradicted or invalidated.  An invalidated base must NOT be used
    for PU even when the Measurement Group's status is ``confirmed``.
    """
    return state == BASE_AUTHORITY_UNAVAILABLE


def is_base_state_valid(state: str) -> bool:
    """True when ``state`` is a known ``BaseAuthorityState`` value."""
    return state in KNOWN_BASE_AUTHORITY_STATES


def should_invalidate_on_contradiction(state: str) -> bool:
    """True when new contradictory evidence should cause this state to
    transition to ``unavailable``.

    Only ``auto_resolved`` bases are invalidated on contradiction — an
    engineer-approved base (``legacy_manual`` / ``manual``) persists until
    the engineer explicitly changes it.
    """
    return state == BASE_AUTHORITY_AUTO
