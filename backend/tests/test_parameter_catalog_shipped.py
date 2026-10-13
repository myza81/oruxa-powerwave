"""The catalogs that ship with the application: valid, locked, and not yet the production path."""

from __future__ import annotations

from app.domain.parameter_catalog.loader import CATALOG_ROOT, check_lock, default_store, load_lock
from app.relay_profiles.identification_catalogue import build_registry


class TestShippedCatalogs:
    def test_the_shipped_tree_loads_with_nothing_rejected(self):
        store = default_store()
        assert not store.rejected, [str(r) for r in store.rejected]
        assert {c.catalog_id for c in store.catalogs} >= {"hitachi-red670-catalog", "schneider-micom-p44x-catalog"}

    def test_the_catalogs_live_in_external_json_files(self):
        files = {p.relative_to(CATALOG_ROOT).as_posix() for p in CATALOG_ROOT.rglob("*.json")}
        assert {"canonical/distance_protection.json", "hitachi_energy/red670.json", "schneider/p44x.json"} <= files

    def test_no_7sa511_catalog_exists_yet(self):
        assert not any("7sa511" in p.name.lower() for p in CATALOG_ROOT.rglob("*.json"))
        assert default_store().get("siemens-7sa511-catalog") is None

    def test_no_shipped_catalog_is_active_so_the_hand_written_profiles_stay_the_production_path(self):
        assert default_store().active() == ()
        registry = build_registry()
        assert {p.profile_id for p in registry._profiles} == {"schneider-micom-p441", "siemens-7sa511", "hitachi-red670"}  # noqa: SLF001

    def test_the_lock_matches_the_shipped_locked_catalogs(self):
        assert check_lock(default_store(), load_lock()) == []
