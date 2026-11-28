"""The one definition of the nominal-derived VT (owner decision, D5A 2026-11-21): valid engineering
configuration, never relabelled, refused only when the nominal itself is not an accepted value."""

from __future__ import annotations

import math

import pytest

from app.domain.auto_nominal_vt import (
    AUTHORITY_AUTO_NOMINAL, AUTO_NOMINAL_VT_SECONDARY_V, REFUSED_BASE_NOT_ACCEPTED, REFUSED_INVALID_NOMINAL,
    REFUSED_MANUAL_CONFLICT, REFUSED_NO_NOMINAL, derive_auto_nominal_vt,
)
from app.domain.voltage_group_config import VoltageBaseConfiguration


def _config(nominal, **over) -> VoltageBaseConfiguration:
    return VoltageBaseConfiguration(measurement_group_id="g", workspace_id="w", nominal_voltage_ll_kv=nominal, **over)


def test_a_valid_nominal_derives_primary_and_the_110_v_secondary():
    derived = derive_auto_nominal_vt(_config(132.0))
    assert derived.derived and (derived.primary_v, derived.secondary_v) == (132000.0, 110.0)
    assert AUTO_NOMINAL_VT_SECONDARY_V == 110.0 and AUTHORITY_AUTO_NOMINAL == "auto_nominal"
    assert derived.refused_reason is None


def test_the_provenance_note_never_calls_the_value_assumed_or_provisional():
    note = derive_auto_nominal_vt(_config(275.0)).provenance_note
    assert note == "Auto-derived from nominal voltage 275 kV; secondary 110 V default"
    for word in ("assum", "provisional", "unverified", "display-only"):
        assert word not in note.lower()


@pytest.mark.parametrize("authority", ["legacy_manual", "manual", "auto_resolved"])
def test_every_accepted_base_authority_derives(authority):
    assert derive_auto_nominal_vt(_config(33.0, base_authority=authority)).derived


@pytest.mark.parametrize("authority", ["needs_review", "unavailable"])
def test_a_base_that_is_not_accepted_is_refused_but_still_names_the_nominal(authority):
    derived = derive_auto_nominal_vt(_config(132.0, base_authority=authority))
    assert not derived.derived and derived.refused_reason == REFUSED_BASE_NOT_ACCEPTED and derived.nominal_ll_kv == 132.0
    assert derived.provenance_note is None


def test_a_genuine_conflict_with_channel_evidence_is_refused():
    derived = derive_auto_nominal_vt(_config(132.0, manual_conflict_detected=True))
    assert not derived.derived and derived.refused_reason == REFUSED_MANUAL_CONFLICT and derived.nominal_ll_kv == 132.0


@pytest.mark.parametrize("nominal", [None])
def test_no_nominal_means_nothing_to_derive(nominal):
    assert derive_auto_nominal_vt(_config(nominal)).refused_reason == REFUSED_NO_NOMINAL
    assert derive_auto_nominal_vt(None).refused_reason == REFUSED_NO_NOMINAL


@pytest.mark.parametrize("nominal", [0, -1.0, math.nan, math.inf, True, "132"])
def test_an_invalid_nominal_is_refused(nominal):
    derived = derive_auto_nominal_vt(_config(nominal))
    assert not derived.derived and derived.refused_reason == REFUSED_INVALID_NOMINAL and derived.nominal_ll_kv is None
