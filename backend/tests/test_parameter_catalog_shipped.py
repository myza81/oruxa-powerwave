"""The catalogs that ship with the application: valid, locked, and the production path (catalog-first)."""

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

    def test_the_active_catalogs_and_7sa511_is_still_the_hand_written_profile(self):
        assert {c.catalog_id for c in default_store().active()} == {
            "schneider-micom-p44x-catalog", "hitachi-red670-catalog",
            # the remaining relay families: catalog-only (no hand-written profile)
            "hitachi-rel670-catalog", "hitachi-rel511-catalog", "siemens-siprotec5-7sl87-catalog", "siemens-7sa613-catalog",
            "toshiba-grz100-catalog", "toshiba-grl200-catalog", "nr-rcs941-catalog", "lfzp111-catalog", "relz100-catalog",
        }
        registry = build_registry()
        by_id = {p.profile_id: p for p in registry._profiles}                       # noqa: SLF001
        assert set(by_id) == {
            "schneider-micom-p441", "siemens-7sa511", "hitachi-red670",
            "hitachi-rel670", "hitachi-rel511", "siemens-siprotec5-7sl87", "siemens-7sa613",
            "toshiba-grz100", "toshiba-grl200", "nr-rcs941", "lfzp111", "relz100",
        }
        assert not hasattr(by_id["siemens-7sa511"], "catalog_id")                    # paused: no catalog, unchanged
        for profile_id, extension in (("schneider-micom-p441", "micom-p441-v1"), ("hitachi-red670", "hitachi-red670-v1")):
            assert by_id[profile_id].extension.version == extension                  # catalog-first, profile = extension
            assert by_id[profile_id].version == extension                            # the profile id / version are unchanged
        for profile_id in ("hitachi-rel670", "hitachi-rel511", "siemens-siprotec5-7sl87", "siemens-7sa613",
                           "toshiba-grz100", "toshiba-grl200", "nr-rcs941", "lfzp111", "relz100"):
            assert by_id[profile_id].extension is None                               # catalog-only: no Python
            # documented relay behaviour (DEC-198): REL511 1.4.0 (DEC-199 Phase 2C), 7SL87 1.2.0, 7SA613 1.4.0 (DEC-199 Phase
            # 2D/2F), GRZ100 1.2.0 (DEC-199 Phase 2G) shadow boundaries
            version = {"hitachi-rel511": "1.4.0", "siemens-siprotec5-7sl87": "1.2.0", "siemens-7sa613": "1.4.0",
                       "toshiba-grz100": "1.3.0"}.get(profile_id, "1.0.0")
            assert by_id[profile_id].version == f"{by_id[profile_id].catalog_id}-v{version}"

    def test_the_lock_matches_the_shipped_locked_catalogs(self):
        assert check_lock(default_store(), load_lock()) == []
