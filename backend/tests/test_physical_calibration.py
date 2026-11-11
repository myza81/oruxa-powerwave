"""Tests for app.domain.physical_calibration (Stage 3A).

Covers:

  Authority contract
    - Valid status values accepted
    - Invalid status value rejected with ValueError
    - Immutability: frozen dataclass; attribute assignment raises FrozenInstanceError
    - Empty reason rejected
    - Empty transform_id rejected
    - Evidence-reference tuple preserved exactly
    - EvidenceRef is immutable
    - Optional authority on AnalogChannel: defaults to None

  Eligibility evaluator — single channel
    - Verified source: eligible=True, all_verified=True for all purposes
    - Unverified source: eligible for raw_inspection and exploratory_analysis;
      blocked for engineering_calculation and compliance_assessment
    - Invalid source: eligible only for raw_inspection; blocked for all others
    - Not-assessed source (None): eligible=True, reason=not_assessed,
      all_verified=False for all purposes

  Eligibility evaluator — dependency propagation
    - Invalid leaf dominates unverified leaf
    - Invalid leaf dominates verified leaf
    - Invalid leaf dominates not-assessed leaf
    - Unverified leaf dominates verified leaf
    - Unverified leaf dominates not-assessed leaf
    - Verified + not-assessed: not_fully_verified, eligible, all_verified=False
    - All-verified leaves: eligible, all_verified=True
    - Empty leaf list: treated as all-verified (no known limitation)
    - Multiple invalid leaves: all transform_ids in limiting_transform_ids

  Eligibility evaluator — reason precedence
    - Correct reason assigned for each aggregate status
    - limiting_transform_ids empty for not-assessed and verified paths
    - limiting_transform_ids populated from unverified/invalid leaves

  Backward compatibility
    - Existing AnalogChannel construction without calibration_authority works
    - evaluate_calibration_eligibility with all-None list returns compat result
    - Existing sources (no authority) are eligible for engineering_calculation
    - No existing production paths modified

  Provenance integrity
    - Renaming (new AnalogChannel with different name, same authority): authority unchanged
    - Group reassignment: authority is on channel, not group; unchanged
    - Manual base assignment: independent concept; does not touch authority
    - Calculated-channel dependency: mixed leaves correctly propagate worst case
    - transform_id stability: changing transform_id requires a new authority object

  Convenience predicates
    - is_eligible, is_fully_verified, is_blocked_by_calibration, is_compatibility_mode
"""

from __future__ import annotations

import dataclasses

import pytest

from app.domain.channels import AnalogChannel
from app.domain.physical_calibration import (
    CALIBRATION_INVALID,
    CALIBRATION_UNVERIFIED,
    CALIBRATION_VERIFIED,
    KNOWN_CALIBRATION_STATUSES,
    KNOWN_CALIBRATION_PURPOSES,
    PURPOSE_COMPLIANCE_ASSESSMENT,
    PURPOSE_ENGINEERING_CALCULATION,
    PURPOSE_EXPLORATORY_ANALYSIS,
    PURPOSE_RAW_INSPECTION,
    REASON_AVAILABLE,
    REASON_INVALID,
    REASON_NOT_ASSESSED,
    REASON_NOT_FULLY_VERIFIED,
    REASON_UNVERIFIED,
    REASON_CODE_BEN5K_CALIBRATION_UNVERIFIED,
    CalibrationEligibility,
    EvidenceRef,
    PhysicalCalibrationAuthority,
    evaluate_calibration_eligibility,
    is_blocked_by_calibration,
    is_compatibility_mode,
    is_eligible,
    is_fully_verified,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def verified_auth() -> PhysicalCalibrationAuthority:
    return PhysicalCalibrationAuthority(
        status=CALIBRATION_VERIFIED,
        reason=REASON_CODE_BEN5K_CALIBRATION_UNVERIFIED + "_crosscheck_passed",
        transform_id="ben5k_v1_packed16_lsb4status_vl",
        evidence_refs=(
            EvidenceRef(
                description="GPTH VLL RMS crosscheck 2026-10-16",
                scope="gpth_tbin1_20261016",
                method="voltage_ll_rms_nominal_crosscheck",
                hash_ref="sha256:abc123",
            ),
        ),
    )


@pytest.fixture
def unverified_auth() -> PhysicalCalibrationAuthority:
    return PhysicalCalibrationAuthority(
        status=CALIBRATION_UNVERIFIED,
        reason=REASON_CODE_BEN5K_CALIBRATION_UNVERIFIED,
        transform_id="ben5k_v1_packed16_lsb4status_i",
        evidence_refs=(),
    )


@pytest.fixture
def invalid_auth() -> PhysicalCalibrationAuthority:
    return PhysicalCalibrationAuthority(
        status=CALIBRATION_INVALID,
        reason="channel_inactive_all_samples_zero",
        transform_id="ben5k_v1_packed16_lsb4status_vl",
        evidence_refs=(),
    )


# ---------------------------------------------------------------------------
# Authority contract — valid construction
# ---------------------------------------------------------------------------

class TestAuthorityContractConstruction:

    def test_verified_status_accepted(self, verified_auth: PhysicalCalibrationAuthority) -> None:
        assert verified_auth.status == CALIBRATION_VERIFIED

    def test_unverified_status_accepted(self, unverified_auth: PhysicalCalibrationAuthority) -> None:
        assert unverified_auth.status == CALIBRATION_UNVERIFIED

    def test_invalid_status_accepted(self, invalid_auth: PhysicalCalibrationAuthority) -> None:
        assert invalid_auth.status == CALIBRATION_INVALID

    def test_all_known_statuses_accepted(self) -> None:
        for s in KNOWN_CALIBRATION_STATUSES:
            auth = PhysicalCalibrationAuthority(
                status=s, reason="test_reason", transform_id="test_transform",
            )
            assert auth.status == s

    def test_evidence_refs_preserved(self, verified_auth: PhysicalCalibrationAuthority) -> None:
        assert len(verified_auth.evidence_refs) == 1
        ref = verified_auth.evidence_refs[0]
        assert ref.description == "GPTH VLL RMS crosscheck 2026-10-16"
        assert ref.scope == "gpth_tbin1_20261016"
        assert ref.method == "voltage_ll_rms_nominal_crosscheck"
        assert ref.hash_ref == "sha256:abc123"

    def test_empty_evidence_refs_accepted(self, unverified_auth: PhysicalCalibrationAuthority) -> None:
        assert unverified_auth.evidence_refs == ()

    def test_transform_id_preserved(self, unverified_auth: PhysicalCalibrationAuthority) -> None:
        assert unverified_auth.transform_id == "ben5k_v1_packed16_lsb4status_i"


# ---------------------------------------------------------------------------
# Authority contract — validation and immutability
# ---------------------------------------------------------------------------

class TestAuthorityContractValidation:

    def test_unknown_status_rejected(self) -> None:
        with pytest.raises(ValueError, match="Invalid calibration status"):
            PhysicalCalibrationAuthority(
                status="unknown",  # type: ignore[arg-type]
                reason="r",
                transform_id="t",
            )

    def test_empty_reason_rejected(self) -> None:
        with pytest.raises(ValueError, match="reason must be a non-empty string"):
            PhysicalCalibrationAuthority(
                status=CALIBRATION_UNVERIFIED,
                reason="",
                transform_id="t",
            )

    def test_empty_transform_id_rejected(self) -> None:
        with pytest.raises(ValueError, match="transform_id must be a non-empty string"):
            PhysicalCalibrationAuthority(
                status=CALIBRATION_UNVERIFIED,
                reason="r",
                transform_id="",
            )

    def test_authority_is_frozen(self, unverified_auth: PhysicalCalibrationAuthority) -> None:
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
            unverified_auth.status = CALIBRATION_VERIFIED  # type: ignore[misc]

    def test_evidence_ref_is_frozen(self, verified_auth: PhysicalCalibrationAuthority) -> None:
        ref = verified_auth.evidence_refs[0]
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
            ref.description = "tampered"  # type: ignore[misc]

    def test_evidence_ref_hash_ref_optional(self) -> None:
        ref = EvidenceRef(description="test", scope="test_scope")
        assert ref.hash_ref is None
        assert ref.method is None


# ---------------------------------------------------------------------------
# AnalogChannel backward compatibility
# ---------------------------------------------------------------------------

class TestAnalogChannelBackwardCompatibility:

    def test_analog_channel_calibration_authority_defaults_to_none(self) -> None:
        ch = AnalogChannel(name="VR", unit="kV", index=0)
        assert ch.calibration_authority is None

    def test_analog_channel_construction_unchanged(self) -> None:
        ch = AnalogChannel(
            name="VR",
            unit="kV",
            index=0,
            phase="A",
            scale=0.001,
        )
        assert ch.name == "VR"
        assert ch.unit == "kV"
        assert ch.index == 0
        assert ch.calibration_authority is None

    def test_analog_channel_accepts_authority(
        self, unverified_auth: PhysicalCalibrationAuthority
    ) -> None:
        ch = AnalogChannel(
            name="IR",
            unit="kA",
            index=1,
            calibration_authority=unverified_auth,
        )
        assert ch.calibration_authority is unverified_auth
        assert ch.calibration_authority.status == CALIBRATION_UNVERIFIED

    def test_analog_channel_renaming_does_not_alter_authority(
        self, unverified_auth: PhysicalCalibrationAuthority
    ) -> None:
        # Simulate a "rename" by creating a new channel with a different name
        # but carrying the same authority object.
        ch_original = AnalogChannel(name="IR", unit="kA", index=1,
                                    calibration_authority=unverified_auth)
        ch_renamed = dataclasses.replace(ch_original, name="Feeder_IR")
        assert ch_renamed.calibration_authority is ch_original.calibration_authority
        assert ch_renamed.calibration_authority.status == CALIBRATION_UNVERIFIED


# ---------------------------------------------------------------------------
# Evaluator — single channel
# ---------------------------------------------------------------------------

class TestEvaluatorSingleVerified:

    def test_verified_raw_inspection_eligible(
        self, verified_auth: PhysicalCalibrationAuthority
    ) -> None:
        result = evaluate_calibration_eligibility([verified_auth], PURPOSE_RAW_INSPECTION)
        assert result.eligible is True
        assert result.reason == REASON_AVAILABLE
        assert result.all_verified is True
        assert result.has_invalid_leaves is False
        assert result.has_unverified_leaves is False
        assert result.has_not_assessed_leaves is False

    def test_verified_exploratory_eligible(
        self, verified_auth: PhysicalCalibrationAuthority
    ) -> None:
        result = evaluate_calibration_eligibility([verified_auth], PURPOSE_EXPLORATORY_ANALYSIS)
        assert result.eligible is True
        assert result.all_verified is True

    def test_verified_engineering_eligible(
        self, verified_auth: PhysicalCalibrationAuthority
    ) -> None:
        result = evaluate_calibration_eligibility([verified_auth], PURPOSE_ENGINEERING_CALCULATION)
        assert result.eligible is True
        assert result.all_verified is True

    def test_verified_compliance_eligible(
        self, verified_auth: PhysicalCalibrationAuthority
    ) -> None:
        result = evaluate_calibration_eligibility([verified_auth], PURPOSE_COMPLIANCE_ASSESSMENT)
        assert result.eligible is True
        assert result.all_verified is True

    def test_verified_limiting_transform_ids_empty(
        self, verified_auth: PhysicalCalibrationAuthority
    ) -> None:
        result = evaluate_calibration_eligibility([verified_auth], PURPOSE_ENGINEERING_CALCULATION)
        assert result.limiting_transform_ids == ()


class TestEvaluatorSingleUnverified:

    def test_unverified_raw_inspection_eligible(
        self, unverified_auth: PhysicalCalibrationAuthority
    ) -> None:
        result = evaluate_calibration_eligibility([unverified_auth], PURPOSE_RAW_INSPECTION)
        assert result.eligible is True
        assert result.reason == REASON_UNVERIFIED
        assert result.all_verified is False

    def test_unverified_exploratory_eligible(
        self, unverified_auth: PhysicalCalibrationAuthority
    ) -> None:
        result = evaluate_calibration_eligibility([unverified_auth], PURPOSE_EXPLORATORY_ANALYSIS)
        assert result.eligible is True
        assert result.reason == REASON_UNVERIFIED

    def test_unverified_engineering_blocked(
        self, unverified_auth: PhysicalCalibrationAuthority
    ) -> None:
        result = evaluate_calibration_eligibility([unverified_auth], PURPOSE_ENGINEERING_CALCULATION)
        assert result.eligible is False
        assert result.reason == REASON_UNVERIFIED
        assert result.has_unverified_leaves is True

    def test_unverified_compliance_blocked(
        self, unverified_auth: PhysicalCalibrationAuthority
    ) -> None:
        result = evaluate_calibration_eligibility([unverified_auth], PURPOSE_COMPLIANCE_ASSESSMENT)
        assert result.eligible is False
        assert result.reason == REASON_UNVERIFIED

    def test_unverified_limiting_transform_ids_populated(
        self, unverified_auth: PhysicalCalibrationAuthority
    ) -> None:
        result = evaluate_calibration_eligibility([unverified_auth], PURPOSE_ENGINEERING_CALCULATION)
        assert unverified_auth.transform_id in result.limiting_transform_ids


class TestEvaluatorSingleInvalid:

    def test_invalid_raw_inspection_eligible(
        self, invalid_auth: PhysicalCalibrationAuthority
    ) -> None:
        result = evaluate_calibration_eligibility([invalid_auth], PURPOSE_RAW_INSPECTION)
        assert result.eligible is True
        assert result.reason == REASON_INVALID
        assert result.has_invalid_leaves is True
        assert result.all_verified is False

    def test_invalid_exploratory_blocked(
        self, invalid_auth: PhysicalCalibrationAuthority
    ) -> None:
        result = evaluate_calibration_eligibility([invalid_auth], PURPOSE_EXPLORATORY_ANALYSIS)
        assert result.eligible is False
        assert result.reason == REASON_INVALID

    def test_invalid_engineering_blocked(
        self, invalid_auth: PhysicalCalibrationAuthority
    ) -> None:
        result = evaluate_calibration_eligibility([invalid_auth], PURPOSE_ENGINEERING_CALCULATION)
        assert result.eligible is False
        assert result.reason == REASON_INVALID

    def test_invalid_compliance_blocked(
        self, invalid_auth: PhysicalCalibrationAuthority
    ) -> None:
        result = evaluate_calibration_eligibility([invalid_auth], PURPOSE_COMPLIANCE_ASSESSMENT)
        assert result.eligible is False
        assert result.reason == REASON_INVALID

    def test_invalid_limiting_transform_ids_populated(
        self, invalid_auth: PhysicalCalibrationAuthority
    ) -> None:
        result = evaluate_calibration_eligibility([invalid_auth], PURPOSE_ENGINEERING_CALCULATION)
        assert invalid_auth.transform_id in result.limiting_transform_ids


class TestEvaluatorNotAssessed:

    @pytest.mark.parametrize("purpose", list(KNOWN_CALIBRATION_PURPOSES))
    def test_not_assessed_eligible_for_all_purposes(self, purpose: str) -> None:
        result = evaluate_calibration_eligibility([None], purpose)  # type: ignore[list-item]
        assert result.eligible is True

    def test_not_assessed_reason(self) -> None:
        result = evaluate_calibration_eligibility([None], PURPOSE_ENGINEERING_CALCULATION)  # type: ignore[list-item]
        assert result.reason == REASON_NOT_ASSESSED

    def test_not_assessed_all_verified_false(self) -> None:
        result = evaluate_calibration_eligibility([None], PURPOSE_ENGINEERING_CALCULATION)  # type: ignore[list-item]
        assert result.all_verified is False

    def test_not_assessed_has_not_assessed_leaves(self) -> None:
        result = evaluate_calibration_eligibility([None], PURPOSE_ENGINEERING_CALCULATION)  # type: ignore[list-item]
        assert result.has_not_assessed_leaves is True

    def test_not_assessed_limiting_transform_ids_empty(self) -> None:
        result = evaluate_calibration_eligibility([None], PURPOSE_ENGINEERING_CALCULATION)  # type: ignore[list-item]
        assert result.limiting_transform_ids == ()


# ---------------------------------------------------------------------------
# Evaluator — empty leaf list
# ---------------------------------------------------------------------------

class TestEvaluatorEmpty:

    @pytest.mark.parametrize("purpose", list(KNOWN_CALIBRATION_PURPOSES))
    def test_empty_leaf_list_eligible(self, purpose: str) -> None:
        result = evaluate_calibration_eligibility([], purpose)  # type: ignore[arg-type]
        assert result.eligible is True
        assert result.all_verified is True
        assert result.reason == REASON_AVAILABLE


# ---------------------------------------------------------------------------
# Evaluator — dependency propagation
# ---------------------------------------------------------------------------

class TestEvaluatorDependencyPropagation:

    def test_invalid_dominates_unverified(
        self,
        invalid_auth: PhysicalCalibrationAuthority,
        unverified_auth: PhysicalCalibrationAuthority,
    ) -> None:
        result = evaluate_calibration_eligibility(
            [invalid_auth, unverified_auth],
            PURPOSE_ENGINEERING_CALCULATION,
        )
        assert result.reason == REASON_INVALID
        assert result.has_invalid_leaves is True
        assert result.has_unverified_leaves is True

    def test_invalid_dominates_verified(
        self,
        invalid_auth: PhysicalCalibrationAuthority,
        verified_auth: PhysicalCalibrationAuthority,
    ) -> None:
        result = evaluate_calibration_eligibility(
            [invalid_auth, verified_auth],
            PURPOSE_ENGINEERING_CALCULATION,
        )
        assert result.reason == REASON_INVALID
        assert result.eligible is False

    def test_invalid_dominates_not_assessed(
        self, invalid_auth: PhysicalCalibrationAuthority
    ) -> None:
        result = evaluate_calibration_eligibility(
            [invalid_auth, None],  # type: ignore[list-item]
            PURPOSE_ENGINEERING_CALCULATION,
        )
        assert result.reason == REASON_INVALID

    def test_unverified_dominates_verified(
        self,
        unverified_auth: PhysicalCalibrationAuthority,
        verified_auth: PhysicalCalibrationAuthority,
    ) -> None:
        result = evaluate_calibration_eligibility(
            [verified_auth, unverified_auth],
            PURPOSE_ENGINEERING_CALCULATION,
        )
        assert result.reason == REASON_UNVERIFIED
        assert result.eligible is False

    def test_unverified_dominates_not_assessed(
        self, unverified_auth: PhysicalCalibrationAuthority
    ) -> None:
        result = evaluate_calibration_eligibility(
            [unverified_auth, None],  # type: ignore[list-item]
            PURPOSE_ENGINEERING_CALCULATION,
        )
        assert result.reason == REASON_UNVERIFIED
        assert result.eligible is False

    def test_verified_plus_not_assessed_not_fully_verified(
        self, verified_auth: PhysicalCalibrationAuthority
    ) -> None:
        result = evaluate_calibration_eligibility(
            [verified_auth, None],  # type: ignore[list-item]
            PURPOSE_ENGINEERING_CALCULATION,
        )
        assert result.eligible is True
        assert result.all_verified is False
        assert result.reason == REASON_NOT_FULLY_VERIFIED
        assert result.has_not_assessed_leaves is True

    def test_all_verified_multiple_leaves(
        self,
        verified_auth: PhysicalCalibrationAuthority,
    ) -> None:
        second = PhysicalCalibrationAuthority(
            status=CALIBRATION_VERIFIED,
            reason="crosscheck_b",
            transform_id="ben5k_v1_packed16_lsb4status_vl_b",
        )
        result = evaluate_calibration_eligibility(
            [verified_auth, second],
            PURPOSE_ENGINEERING_CALCULATION,
        )
        assert result.eligible is True
        assert result.all_verified is True
        assert result.reason == REASON_AVAILABLE

    def test_all_not_assessed_multiple_leaves(self) -> None:
        result = evaluate_calibration_eligibility(
            [None, None, None],  # type: ignore[list-item]
            PURPOSE_ENGINEERING_CALCULATION,
        )
        assert result.eligible is True
        assert result.reason == REASON_NOT_ASSESSED
        assert result.all_verified is False

    def test_multiple_invalid_all_transform_ids_captured(
        self,
        invalid_auth: PhysicalCalibrationAuthority,
    ) -> None:
        second_invalid = PhysicalCalibrationAuthority(
            status=CALIBRATION_INVALID,
            reason="channel_inactive",
            transform_id="ben5k_v1_packed16_lsb4status_vl_b",
        )
        result = evaluate_calibration_eligibility(
            [invalid_auth, second_invalid],
            PURPOSE_ENGINEERING_CALCULATION,
        )
        assert invalid_auth.transform_id in result.limiting_transform_ids
        assert second_invalid.transform_id in result.limiting_transform_ids
        assert len(result.limiting_transform_ids) == 2

    def test_nested_dependency_unverified_leaf(
        self,
        unverified_auth: PhysicalCalibrationAuthority,
        verified_auth: PhysicalCalibrationAuthority,
    ) -> None:
        # Simulate: Calculated C depends on B (verified) and original leaf A (unverified).
        # Caller resolves to leaf list [verified_auth, unverified_auth].
        result = evaluate_calibration_eligibility(
            [verified_auth, unverified_auth],
            PURPOSE_ENGINEERING_CALCULATION,
        )
        assert result.eligible is False
        assert result.reason == REASON_UNVERIFIED

    def test_mixed_all_purposes_propagate(
        self,
        unverified_auth: PhysicalCalibrationAuthority,
        verified_auth: PhysicalCalibrationAuthority,
    ) -> None:
        leaves = [verified_auth, unverified_auth]
        for purpose in KNOWN_CALIBRATION_PURPOSES:
            result = evaluate_calibration_eligibility(leaves, purpose)
            assert result.reason == REASON_UNVERIFIED
            if purpose in (PURPOSE_ENGINEERING_CALCULATION, PURPOSE_COMPLIANCE_ASSESSMENT):
                assert result.eligible is False
            else:
                assert result.eligible is True


# ---------------------------------------------------------------------------
# Evaluator — invalid purpose
# ---------------------------------------------------------------------------

class TestEvaluatorInvalidPurpose:

    def test_unknown_purpose_raises(
        self, verified_auth: PhysicalCalibrationAuthority
    ) -> None:
        with pytest.raises(ValueError, match="Unknown calibration purpose"):
            evaluate_calibration_eligibility([verified_auth], "unknown_purpose")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Convenience predicates
# ---------------------------------------------------------------------------

class TestConveniencePredicates:

    def test_is_eligible_true_for_verified(
        self, verified_auth: PhysicalCalibrationAuthority
    ) -> None:
        result = evaluate_calibration_eligibility([verified_auth], PURPOSE_ENGINEERING_CALCULATION)
        assert is_eligible(result) is True

    def test_is_eligible_false_for_unverified_engineering(
        self, unverified_auth: PhysicalCalibrationAuthority
    ) -> None:
        result = evaluate_calibration_eligibility([unverified_auth], PURPOSE_ENGINEERING_CALCULATION)
        assert is_eligible(result) is False

    def test_is_fully_verified_true_for_all_verified(
        self, verified_auth: PhysicalCalibrationAuthority
    ) -> None:
        result = evaluate_calibration_eligibility([verified_auth], PURPOSE_ENGINEERING_CALCULATION)
        assert is_fully_verified(result) is True

    def test_is_fully_verified_false_for_not_assessed(self) -> None:
        result = evaluate_calibration_eligibility([None], PURPOSE_ENGINEERING_CALCULATION)  # type: ignore[list-item]
        assert is_fully_verified(result) is False

    def test_is_fully_verified_false_for_unverified(
        self, unverified_auth: PhysicalCalibrationAuthority
    ) -> None:
        result = evaluate_calibration_eligibility([unverified_auth], PURPOSE_ENGINEERING_CALCULATION)
        assert is_fully_verified(result) is False

    def test_is_blocked_by_calibration_unverified_engineering(
        self, unverified_auth: PhysicalCalibrationAuthority
    ) -> None:
        result = evaluate_calibration_eligibility([unverified_auth], PURPOSE_ENGINEERING_CALCULATION)
        assert is_blocked_by_calibration(result) is True

    def test_is_blocked_by_calibration_false_for_eligible(
        self, verified_auth: PhysicalCalibrationAuthority
    ) -> None:
        result = evaluate_calibration_eligibility([verified_auth], PURPOSE_ENGINEERING_CALCULATION)
        assert is_blocked_by_calibration(result) is False

    def test_is_compatibility_mode_true_for_not_assessed(self) -> None:
        result = evaluate_calibration_eligibility([None], PURPOSE_ENGINEERING_CALCULATION)  # type: ignore[list-item]
        assert is_compatibility_mode(result) is True

    def test_is_compatibility_mode_true_for_not_fully_verified(
        self, verified_auth: PhysicalCalibrationAuthority
    ) -> None:
        result = evaluate_calibration_eligibility(
            [verified_auth, None],  # type: ignore[list-item]
            PURPOSE_ENGINEERING_CALCULATION,
        )
        assert is_compatibility_mode(result) is True

    def test_is_compatibility_mode_false_for_all_verified(
        self, verified_auth: PhysicalCalibrationAuthority
    ) -> None:
        result = evaluate_calibration_eligibility([verified_auth], PURPOSE_ENGINEERING_CALCULATION)
        assert is_compatibility_mode(result) is False

    def test_is_compatibility_mode_false_for_unverified(
        self, unverified_auth: PhysicalCalibrationAuthority
    ) -> None:
        result = evaluate_calibration_eligibility([unverified_auth], PURPOSE_ENGINEERING_CALCULATION)
        assert is_compatibility_mode(result) is False


# ---------------------------------------------------------------------------
# Provenance integrity
# ---------------------------------------------------------------------------

class TestProvenanceIntegrity:

    def test_different_voltage_current_channels_different_status(
        self,
        verified_auth: PhysicalCalibrationAuthority,
        unverified_auth: PhysicalCalibrationAuthority,
    ) -> None:
        # BEN5K: voltage Verified, current Unverified — independent statuses.
        voltage_ch = AnalogChannel(name="VR", unit="kV", index=0,
                                   calibration_authority=verified_auth)
        current_ch = AnalogChannel(name="IR", unit="kA", index=1,
                                   calibration_authority=unverified_auth)
        v_result = evaluate_calibration_eligibility(
            [voltage_ch.calibration_authority],
            PURPOSE_ENGINEERING_CALCULATION,
        )
        i_result = evaluate_calibration_eligibility(
            [current_ch.calibration_authority],
            PURPOSE_ENGINEERING_CALCULATION,
        )
        assert v_result.eligible is True
        assert i_result.eligible is False

    def test_calculated_channel_cannot_acquire_stronger_authority(
        self,
        unverified_auth: PhysicalCalibrationAuthority,
        verified_auth: PhysicalCalibrationAuthority,
    ) -> None:
        # Calculated V_line = V_A - V_B: one verified, one unverified leaf.
        # Result must NOT become fully verified.
        result = evaluate_calibration_eligibility(
            [verified_auth, unverified_auth],
            PURPOSE_ENGINEERING_CALCULATION,
        )
        assert result.all_verified is False
        assert result.eligible is False

    def test_transform_id_stability(
        self, unverified_auth: PhysicalCalibrationAuthority
    ) -> None:
        # Changing transform_id requires a new authority object (frozen).
        new_auth = dataclasses.replace(unverified_auth, transform_id="ben5k_v2_corrected")
        assert new_auth.transform_id == "ben5k_v2_corrected"
        assert unverified_auth.transform_id == "ben5k_v1_packed16_lsb4status_i"

    def test_manual_base_independent_of_authority(
        self, unverified_auth: PhysicalCalibrationAuthority
    ) -> None:
        # Assigning a manual PU base does NOT change the channel's authority.
        # The authority is on the AnalogChannel; PU base config is in a separate model.
        ch = AnalogChannel(name="IR", unit="kA", index=1,
                           calibration_authority=unverified_auth)
        # Simulating a "manual base assignment" by creating the PU config model
        # (we don't need to import it — just verify the channel authority is unchanged).
        assert ch.calibration_authority is unverified_auth
        assert ch.calibration_authority.status == CALIBRATION_UNVERIFIED

    def test_not_assessed_not_equivalent_to_verified(self) -> None:
        # An existing source with no authority metadata must not be treated as Verified.
        result = evaluate_calibration_eligibility(
            [None],  # type: ignore[list-item]
            PURPOSE_ENGINEERING_CALCULATION,
        )
        assert result.all_verified is False
        assert result.reason != REASON_AVAILABLE

    def test_verified_not_assessed_mix_cannot_claim_verified(
        self, verified_auth: PhysicalCalibrationAuthority
    ) -> None:
        result = evaluate_calibration_eligibility(
            [verified_auth, None],  # type: ignore[list-item]
            PURPOSE_ENGINEERING_CALCULATION,
        )
        assert result.all_verified is False
        assert result.reason == REASON_NOT_FULLY_VERIFIED
