"""PU-MIG S6 -- a Source Default Voltage reports the reference side it is DECLARED on, exactly as the gate evaluated it.

Before S6 the response always said `unknown` for a Source Default Voltage base, although the stored `voltage_base_reference_side` is what the
reference-compatibility gate compares (`per_unit_reference.apply_source_reference`). That was a reporting omission (the authority is established and
used), not an unknown authority. What stays exactly as it was: a Source Default that stores nothing still reports Unknown; no number, verification state,
status or eligibility depends on the reported field; the stored label never becomes a Secondary denominator (D-5).
"""

from __future__ import annotations

import pytest

from tests.test_per_unit_voltage_reference_safety import checked, client, ROOT  # noqa: F401  (client is the shared fixture)
from tests.test_pu_mig_s2_d7_closeout import source_default
from tests.test_pu_mig_s2_raw_voltage_side import peak as pu_peak, provenance, wave


@pytest.mark.parametrize("flag,status,state", [
    ("S", "configured", "unverified_historical"),     # label matches the Secondary samples: the historical number, never verified (D-5)
    ("P", "base_required", "blocked"),                # a known mismatch with no ratio authority: refused, ENG shown
    ("", "configured", "unverified_historical"),      # no side established: historical Unverified (D-1)
])
def test_a_stored_secondary_declaration_is_reported_whatever_the_outcome(client, flag, status, state):
    sid = source_default(client, flag=flag, stored_side="secondary", value_kv=0.110)
    body, p = wave(client, sid), provenance(client, sid)
    assert (body["per_unit_status"], p["verification_state"]) == (status, state)         # unchanged outcomes
    assert p["base_reference_side"] == "secondary"                                         # the declaration the gate compared
    if status == "configured":
        assert pu_peak(body) == pytest.approx(1.0, rel=1e-12)                              # the historical number, unchanged
    assert p.get("denominator_side") is None and p.get("side_conversion") is None


def test_a_stored_primary_declaration_is_reported(client):
    sid = source_default(client, flag="", stored_side="primary", value_kv=0.110)
    p = provenance(client, sid)
    assert (p["verification_state"], p["base_reference_side"]) == ("unverified_historical", "primary")


def test_a_source_default_that_declares_nothing_still_reports_unknown(client):
    """Case A of the S6 question: genuinely unknown authority is preserved, not turned into a guess."""
    sid = source_default(client, flag="", stored_side="unknown", value_kv=0.110)
    p = provenance(client, sid)
    assert (p["verification_state"], p["base_reference_side"]) == ("unverified_historical", "unknown")


def test_the_132_kv_counterexample_reports_secondary_and_stays_unverified(client):
    sid = source_default(client, flag="S", stored_side="secondary", value_kv=132.0)
    body, p = wave(client, sid), provenance(client, sid)
    assert p["base_reference_side"] == "secondary" and p["verification_state"] == "unverified_historical"
    assert body["per_unit_verification_state"] == "unverified_historical"
    assert pu_peak(body) == pytest.approx(1.0, rel=1e-12)       # value_kv * 1000 / sqrt(3) samples on the nominal base: the helper's own scale


def test_measurement_group_reporting_is_unchanged(client, comtrade_fixtures_dir):
    """The group path already reported its configured side; S6 does not touch it."""
    from tests.test_per_unit_voltage_reference_safety import recording, setup_voltage_base, SECONDARY_V, VNAMES
    sid = recording(client, comtrade_fixtures_dir, "P")
    setup_voltage_base(client, sid, "secondary", scope="group", secondary_v=SECONDARY_V)
    assert provenance(client, sid, VNAMES[0])["base_reference_side"] == "secondary"
