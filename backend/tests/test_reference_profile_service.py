"""Service-layer tests for Compliance Slice 3
(`app.services.reference_profile_service` + its two sibling registries).
Exercises CRUD/duplicate/delete-cascade/import-export/compatibility/
comparison-chart-assembly directly against real (in-process) registries
-- no HTTP layer (see `test_reference_profile_api.py` for HTTP wiring).

**Every test class in this file constructs its registries fresh and
never touches `WorkspaceRegistry`/`MeasurementGroupRegistry` at all** --
this is itself the direct proof of the mid-conversation product
requirement ("Reference Layers must work without an uploaded recording"):
if these tests can exercise the full profile/layer lifecycle with zero
recording-related registry in sight, the feature genuinely has no
recording dependency.
"""

from __future__ import annotations

import pytest

from app.domain.reference_profile import ReferenceBoundary, ReferenceProfileMetadata
from app.schemas.reference_profile import ReferenceProfileWriteRequest
from app.services.errors import (
    ReferenceLayerNotFoundError,
    ReferenceProfileIsBuiltInError,
    ReferenceProfileNotFoundError,
    ReferenceProfileValidationServiceError,
    UnsupportedReferenceProfileSchemaVersionServiceError,
)
from app.services.reference_layer_registry import ReferenceLayerRegistry
from app.services.reference_profile_registry import ReferenceProfileRegistry
from app.services.reference_profile_service import (
    COMPATIBILITY_COMPATIBLE,
    COMPATIBILITY_INCOMPATIBLE,
    COMPATIBILITY_NOT_YET_APPLICABLE,
    SOURCE_CUSTOM,
    add_layer,
    build_comparison_chart,
    compute_layer_compatibility,
    create_custom_profile,
    delete_custom_profile,
    duplicate_profile,
    export_profile,
    get_profile_entry_or_404,
    import_profile,
    list_layers_for_workspace,
    list_profiles_for_workspace,
    remove_layer,
    set_layer_visibility,
    update_custom_profile,
)

WORKSPACE = "ws-ref-svc-1"


def _write_request(**overrides) -> ReferenceProfileWriteRequest:
    defaults = dict(
        name="Test Profile", category="custom_reference", evaluation_quantity="phase_a_lg_rms", unit="pu",
        display_start_time=-0.5, display_end_time=3.0, evaluation_start_time=0.0, evaluation_end_time=3.0,
        tolerance=0.0,
        lower_boundary={"segments": [
            {"start_time": -0.5, "end_time": 3.0, "start_value": 0.8, "end_value": 0.8, "segment_type": "constant"}
        ]},
        upper_boundary=None,
        metadata={},
    )
    defaults.update(overrides)
    return ReferenceProfileWriteRequest.model_validate(defaults)


@pytest.fixture
def profile_registry() -> ReferenceProfileRegistry:
    return ReferenceProfileRegistry()


@pytest.fixture
def layer_registry() -> ReferenceLayerRegistry:
    return ReferenceLayerRegistry()


class TestCustomProfileCrud:
    def test_create_assigns_a_fresh_id_and_stores_it(self, profile_registry):
        profile = create_custom_profile(WORKSPACE, _write_request().to_domain(profile_id=""), custom_registry=profile_registry)
        assert profile.id
        assert profile_registry.get(WORKSPACE, profile.id) == profile

    def test_create_never_trusts_a_caller_supplied_built_in_flag(self, profile_registry):
        request = _write_request(metadata={"notes": "x"})
        domain = request.to_domain(profile_id="")
        assert domain.metadata.built_in is False  # the schema itself never exposes this field to callers

    def test_invalid_create_raises_validation_service_error_and_stores_nothing(self, profile_registry):
        with pytest.raises(ReferenceProfileValidationServiceError) as exc:
            create_custom_profile(WORKSPACE, _write_request(tolerance=-1.0).to_domain(profile_id=""), custom_registry=profile_registry)
        assert exc.value.reason_code == "negative_tolerance"
        assert profile_registry.list_for_workspace(WORKSPACE) == []

    def test_update_replaces_an_existing_custom_profile(self, profile_registry):
        profile = create_custom_profile(WORKSPACE, _write_request().to_domain(profile_id=""), custom_registry=profile_registry)
        updated = update_custom_profile(
            WORKSPACE, profile.id, _write_request(name="Renamed").to_domain(profile_id=profile.id), custom_registry=profile_registry,
        )
        assert updated.name == "Renamed"
        assert profile_registry.get(WORKSPACE, profile.id).name == "Renamed"

    def test_update_unknown_profile_raises_not_found(self, profile_registry):
        with pytest.raises(ReferenceProfileNotFoundError):
            update_custom_profile(WORKSPACE, "does-not-exist", _write_request().to_domain(profile_id="does-not-exist"), custom_registry=profile_registry)

    def test_duplicate_produces_an_independent_new_custom_profile(self, profile_registry):
        original = create_custom_profile(WORKSPACE, _write_request().to_domain(profile_id=""), custom_registry=profile_registry)
        copy = duplicate_profile(WORKSPACE, original.id, custom_registry=profile_registry)
        assert copy.id != original.id
        assert copy.name != original.name
        # Editing the copy never touches the original.
        update_custom_profile(WORKSPACE, copy.id, _write_request(name="Edited Copy").to_domain(profile_id=copy.id), custom_registry=profile_registry)
        assert profile_registry.get(WORKSPACE, original.id).name == original.name

    def test_delete_removes_a_custom_profile(self, profile_registry):
        profile = create_custom_profile(WORKSPACE, _write_request().to_domain(profile_id=""), custom_registry=profile_registry)
        layer_registry = ReferenceLayerRegistry()
        delete_custom_profile(WORKSPACE, profile.id, custom_registry=profile_registry, layer_registry=layer_registry)
        assert profile_registry.get(WORKSPACE, profile.id) is None

    def test_delete_unknown_profile_raises_not_found(self, profile_registry, layer_registry):
        with pytest.raises(ReferenceProfileNotFoundError):
            delete_custom_profile(WORKSPACE, "does-not-exist", custom_registry=profile_registry, layer_registry=layer_registry)

    def test_delete_cascades_to_remove_referencing_layers(self, profile_registry, layer_registry):
        profile = create_custom_profile(WORKSPACE, _write_request().to_domain(profile_id=""), custom_registry=profile_registry)
        layer = add_layer(WORKSPACE, profile.id, custom_registry=profile_registry, layer_registry=layer_registry)
        removed_count = delete_custom_profile(WORKSPACE, profile.id, custom_registry=profile_registry, layer_registry=layer_registry)
        assert removed_count == 1
        assert layer_registry.get(WORKSPACE, layer.id) is None

    def test_removing_a_layer_never_deletes_its_profile(self, profile_registry, layer_registry):
        profile = create_custom_profile(WORKSPACE, _write_request().to_domain(profile_id=""), custom_registry=profile_registry)
        layer = add_layer(WORKSPACE, profile.id, custom_registry=profile_registry, layer_registry=layer_registry)
        remove_layer(WORKSPACE, layer.id, layer_registry=layer_registry)
        assert profile_registry.get(WORKSPACE, profile.id) is not None
        # And it can be re-added as a fresh layer afterward.
        new_layer = add_layer(WORKSPACE, profile.id, custom_registry=profile_registry, layer_registry=layer_registry)
        assert new_layer.id != layer.id


class TestBuiltInProfilesAreReadOnly:
    """No built-in profile exists in production (see
    `test_reference_profile_builtins.py`), so these tests exercise the
    read-only GUARD itself against a profile id that simply does not
    exist in either registry -- proving `update`/`delete` distinguish
    "genuinely unknown" from "known but built-in" is exercised at the
    API layer instead, where a real built-in fixture directory can be
    injected; see `test_reference_profile_api.py`."""

    def test_update_of_a_genuinely_unknown_id_is_not_found_not_built_in(self, profile_registry):
        with pytest.raises(ReferenceProfileNotFoundError):
            update_custom_profile(WORKSPACE, "totally-unknown", _write_request().to_domain(profile_id="totally-unknown"), custom_registry=profile_registry)


class TestImportExport:
    def test_export_then_import_creates_an_independent_new_custom_profile(self, profile_registry):
        original = create_custom_profile(WORKSPACE, _write_request(name="Exportable").to_domain(profile_id=""), custom_registry=profile_registry)
        envelope = export_profile(WORKSPACE, original.id, custom_registry=profile_registry)
        imported = import_profile(WORKSPACE, envelope, custom_registry=profile_registry)
        assert imported.id != original.id
        assert imported.name == original.name
        assert imported.metadata.built_in is False

    def test_export_unknown_profile_raises_not_found(self, profile_registry):
        with pytest.raises(ReferenceProfileNotFoundError):
            export_profile(WORKSPACE, "does-not-exist", custom_registry=profile_registry)

    def test_import_rejects_unsupported_schema_version(self, profile_registry):
        with pytest.raises(UnsupportedReferenceProfileSchemaVersionServiceError):
            import_profile(WORKSPACE, {"schema_version": 999, "profile": {}}, custom_registry=profile_registry)

    def test_import_rejects_malformed_profile_data(self, profile_registry):
        with pytest.raises(ReferenceProfileValidationServiceError):
            import_profile(WORKSPACE, {"schema_version": 1, "profile": {"name": "incomplete"}}, custom_registry=profile_registry)

    def test_imported_built_in_flag_is_always_forced_false(self, profile_registry):
        envelope = {
            "schema_version": 1,
            "profile": {
                "name": "Claims to be built-in", "category": "custom_reference", "evaluation_quantity": "phase_a_lg_rms",
                "unit": "pu", "display_start_time": 0.0, "display_end_time": 1.0, "evaluation_start_time": 0.0,
                "evaluation_end_time": 1.0, "tolerance": 0.0,
                "lower_boundary": {"segments": [{"start_time": 0.0, "end_time": 1.0, "start_value": 1.0, "end_value": 1.0, "segment_type": "constant"}]},
                "upper_boundary": None,
                "metadata": {"built_in": True},
            },
        }
        imported = import_profile(WORKSPACE, envelope, custom_registry=profile_registry)
        assert imported.metadata.built_in is False


class TestReferenceLayerCrud:
    def test_add_layer_requires_an_existing_profile(self, profile_registry, layer_registry):
        with pytest.raises(ReferenceProfileNotFoundError):
            add_layer(WORKSPACE, "does-not-exist", custom_registry=profile_registry, layer_registry=layer_registry)

    def test_no_maximum_active_layer_count_is_enforced(self, profile_registry, layer_registry):
        profile = create_custom_profile(WORKSPACE, _write_request().to_domain(profile_id=""), custom_registry=profile_registry)
        for _ in range(10):
            add_layer(WORKSPACE, profile.id, custom_registry=profile_registry, layer_registry=layer_registry)
        assert len(list_layers_for_workspace(WORKSPACE, layer_registry=layer_registry)) == 10

    def test_toggle_visibility(self, profile_registry, layer_registry):
        profile = create_custom_profile(WORKSPACE, _write_request().to_domain(profile_id=""), custom_registry=profile_registry)
        layer = add_layer(WORKSPACE, profile.id, custom_registry=profile_registry, layer_registry=layer_registry)
        assert layer.visible is True
        toggled_off = set_layer_visibility(WORKSPACE, layer.id, False, layer_registry=layer_registry)
        assert toggled_off.visible is False
        toggled_on = set_layer_visibility(WORKSPACE, layer.id, True, layer_registry=layer_registry)
        assert toggled_on.visible is True

    def test_remove_unknown_layer_raises_not_found(self, layer_registry):
        with pytest.raises(ReferenceLayerNotFoundError):
            remove_layer(WORKSPACE, "does-not-exist", layer_registry=layer_registry)

    def test_layer_order_is_stable_insertion_order(self, profile_registry, layer_registry):
        profile = create_custom_profile(WORKSPACE, _write_request().to_domain(profile_id=""), custom_registry=profile_registry)
        layer_a = add_layer(WORKSPACE, profile.id, custom_registry=profile_registry, layer_registry=layer_registry)
        layer_b = add_layer(WORKSPACE, profile.id, custom_registry=profile_registry, layer_registry=layer_registry)
        ordered = list_layers_for_workspace(WORKSPACE, layer_registry=layer_registry)
        assert [layer.id for layer in ordered] == [layer_a.id, layer_b.id]


class TestCompatibility:
    def test_no_measurement_selected_is_not_yet_applicable_never_incompatible(self):
        profile = create_custom_profile(
            WORKSPACE, _write_request(evaluation_quantity="phase_a_lg_rms").to_domain(profile_id=""),
            custom_registry=ReferenceProfileRegistry(),
        )
        status, reason = compute_layer_compatibility(profile, selected_quantity_id=None)
        assert status == COMPATIBILITY_NOT_YET_APPLICABLE
        assert reason is not None

    def test_matching_quantity_is_compatible(self):
        profile = create_custom_profile(
            WORKSPACE, _write_request(evaluation_quantity="phase_a_lg_rms").to_domain(profile_id=""),
            custom_registry=ReferenceProfileRegistry(),
        )
        status, reason = compute_layer_compatibility(profile, selected_quantity_id="phase_a_lg_rms")
        assert status == COMPATIBILITY_COMPATIBLE
        assert reason is None

    def test_mismatched_quantity_is_incompatible_with_an_actionable_reason(self):
        profile = create_custom_profile(
            WORKSPACE, _write_request(evaluation_quantity="phase_a_lg_rms").to_domain(profile_id=""),
            custom_registry=ReferenceProfileRegistry(),
        )
        status, reason = compute_layer_compatibility(profile, selected_quantity_id="phase_b_lg_rms")
        assert status == COMPATIBILITY_INCOMPATIBLE
        assert "Phase A Voltage" in reason
        assert "Phase B Voltage" in reason


class TestComparisonChartAssembly:
    def test_empty_workspace_has_no_traces_and_no_axis(self, profile_registry, layer_registry):
        chart = build_comparison_chart(WORKSPACE, custom_registry=profile_registry, layer_registry=layer_registry)
        assert chart.traces == []
        assert chart.axis_unit is None
        assert chart.x_min is None
        assert chart.x_max is None

    def test_single_visible_layer_establishes_the_axis(self, profile_registry, layer_registry):
        profile = create_custom_profile(
            WORKSPACE, _write_request(display_start_time=-1.0, display_end_time=5.0).to_domain(profile_id=""),
            custom_registry=profile_registry,
        )
        add_layer(WORKSPACE, profile.id, custom_registry=profile_registry, layer_registry=layer_registry)
        chart = build_comparison_chart(WORKSPACE, custom_registry=profile_registry, layer_registry=layer_registry)
        assert chart.axis_unit == "pu"
        assert chart.x_min == -1.0
        assert chart.x_max == 5.0
        assert len(chart.traces) == 1
        assert chart.traces[0].on_axis is True
        assert chart.traces[0].points != []

    def test_x_axis_is_the_union_of_visible_profiles_own_display_windows(self, profile_registry, layer_registry):
        profile_a = create_custom_profile(
            WORKSPACE, _write_request(display_start_time=-0.5, display_end_time=3.0).to_domain(profile_id=""),
            custom_registry=profile_registry,
        )
        profile_b = create_custom_profile(
            WORKSPACE, _write_request(display_start_time=-1.0, display_end_time=5.0).to_domain(profile_id=""),
            custom_registry=profile_registry,
        )
        add_layer(WORKSPACE, profile_a.id, custom_registry=profile_registry, layer_registry=layer_registry)
        add_layer(WORKSPACE, profile_b.id, custom_registry=profile_registry, layer_registry=layer_registry)
        chart = build_comparison_chart(WORKSPACE, custom_registry=profile_registry, layer_registry=layer_registry)
        assert chart.x_min == -1.0
        assert chart.x_max == 5.0

    def test_invisible_layer_is_excluded_from_axis_and_has_no_points(self, profile_registry, layer_registry):
        profile = create_custom_profile(WORKSPACE, _write_request().to_domain(profile_id=""), custom_registry=profile_registry)
        layer = add_layer(WORKSPACE, profile.id, visible=False, custom_registry=profile_registry, layer_registry=layer_registry)
        chart = build_comparison_chart(WORKSPACE, custom_registry=profile_registry, layer_registry=layer_registry)
        assert chart.x_min is None and chart.x_max is None
        assert chart.traces[0].on_axis is False
        assert chart.traces[0].points == []

    def test_mismatched_unit_layer_is_reported_but_not_plotted(self, profile_registry, layer_registry):
        pu_profile = create_custom_profile(WORKSPACE, _write_request(unit="pu").to_domain(profile_id=""), custom_registry=profile_registry)
        kv_profile = create_custom_profile(WORKSPACE, _write_request(unit="kV").to_domain(profile_id=""), custom_registry=profile_registry)
        add_layer(WORKSPACE, pu_profile.id, custom_registry=profile_registry, layer_registry=layer_registry)
        add_layer(WORKSPACE, kv_profile.id, custom_registry=profile_registry, layer_registry=layer_registry)
        chart = build_comparison_chart(WORKSPACE, custom_registry=profile_registry, layer_registry=layer_registry)
        assert chart.axis_unit == "pu"
        on_axis_units = {t.unit for t in chart.traces if t.on_axis}
        off_axis_units = {t.unit for t in chart.traces if not t.on_axis}
        assert on_axis_units == {"pu"}
        assert off_axis_units == {"kV"}
        # Never silently hidden from the response entirely -- it still
        # appears in unit_groups, explicitly.
        assert set(chart.unit_groups.keys()) == {"pu", "kV"}

    def test_lower_only_profile_produces_exactly_one_boundary_trace(self, profile_registry, layer_registry):
        profile = create_custom_profile(WORKSPACE, _write_request(upper_boundary=None).to_domain(profile_id=""), custom_registry=profile_registry)
        add_layer(WORKSPACE, profile.id, custom_registry=profile_registry, layer_registry=layer_registry)
        chart = build_comparison_chart(WORKSPACE, custom_registry=profile_registry, layer_registry=layer_registry)
        assert [t.boundary for t in chart.traces] == ["lower"]

    def test_envelope_profile_produces_two_boundary_traces_with_shared_identity(self, profile_registry, layer_registry):
        profile = create_custom_profile(
            WORKSPACE,
            _write_request(upper_boundary={"segments": [
                {"start_time": -0.5, "end_time": 3.0, "start_value": 1.2, "end_value": 1.2, "segment_type": "constant"}
            ]}).to_domain(profile_id=""),
            custom_registry=profile_registry,
        )
        layer = add_layer(WORKSPACE, profile.id, custom_registry=profile_registry, layer_registry=layer_registry)
        chart = build_comparison_chart(WORKSPACE, custom_registry=profile_registry, layer_registry=layer_registry)
        boundaries = sorted(t.boundary for t in chart.traces)
        assert boundaries == ["lower", "upper"]
        for trace in chart.traces:
            assert trace.layer_id == layer.id
            assert trace.profile_id == profile.id
            assert trace.category == profile.category

    def test_chart_reflects_compatibility_against_a_selected_quantity(self, profile_registry, layer_registry):
        profile = create_custom_profile(
            WORKSPACE, _write_request(evaluation_quantity="phase_a_lg_rms").to_domain(profile_id=""), custom_registry=profile_registry,
        )
        add_layer(WORKSPACE, profile.id, custom_registry=profile_registry, layer_registry=layer_registry)
        chart_no_measurement = build_comparison_chart(WORKSPACE, custom_registry=profile_registry, layer_registry=layer_registry, selected_quantity_id=None)
        assert chart_no_measurement.traces[0].compatibility_status == COMPATIBILITY_NOT_YET_APPLICABLE
        chart_compatible = build_comparison_chart(WORKSPACE, custom_registry=profile_registry, layer_registry=layer_registry, selected_quantity_id="phase_a_lg_rms")
        assert chart_compatible.traces[0].compatibility_status == COMPATIBILITY_COMPATIBLE
        chart_incompatible = build_comparison_chart(WORKSPACE, custom_registry=profile_registry, layer_registry=layer_registry, selected_quantity_id="phase_b_lg_rms")
        assert chart_incompatible.traces[0].compatibility_status == COMPATIBILITY_INCOMPATIBLE


class TestWorkspaceIsolation:
    def test_profiles_and_layers_are_isolated_per_workspace(self, profile_registry, layer_registry):
        profile = create_custom_profile("ws-a", _write_request().to_domain(profile_id=""), custom_registry=profile_registry)
        assert profile_registry.get("ws-b", profile.id) is None
        assert list_profiles_for_workspace("ws-b", custom_registry=profile_registry) == []
