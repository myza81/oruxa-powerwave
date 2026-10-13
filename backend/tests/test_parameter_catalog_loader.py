"""Loading, selecting, rejecting and locking parameter catalogs (the file-based lifecycle)."""

from __future__ import annotations

import copy
import json
import logging
import shutil
from pathlib import Path

import pytest

from app.domain.parameter_catalog.errors import CatalogValidationError, IssueCode
from app.domain.parameter_catalog.loader import (
    CATALOG_ROOT,
    REGISTRY_FILE,
    check_lock,
    load_lock,
    load_store,
    semantics_digest,
    write_lock,
)
from app.domain.parameter_catalog.profile import active_catalog_profiles
from app.relay_profiles.identification_catalogue import build_registry
from tests.parameter_catalog_helpers import catalog_json, mapping


def x_reach(mid="m.x", name="X{zone}"):
    return mapping(mid, "distance.zone.x_reach", zone="*", source={"name": name, "type": "number", "unit": "ohm"})


@pytest.fixture
def root(tmp_path: Path) -> Path:
    """A catalog tree containing only the shipped canonical registry."""
    (tmp_path / "canonical").mkdir()
    shutil.copy(CATALOG_ROOT / REGISTRY_FILE, tmp_path / REGISTRY_FILE)
    return tmp_path


def put(root: Path, rel: str, data) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")
    return path


class TestRejectionIsLoudAndPartial:
    def test_an_invalid_catalog_is_rejected_with_its_issues_and_the_others_still_load(self, root, caplog):
        put(root, "acme/good.json", catalog_json(x_reach(), catalog_id="acme-good"))
        put(root, "acme/bad.json", catalog_json(mapping("m", "no.such.canonical", zone="*", source={"name": "X"}), catalog_id="acme-bad"))
        with caplog.at_level(logging.WARNING):
            store = load_store(root)
        assert [c.catalog_id for c in store.catalogs] == ["acme-good"]
        (rejected,) = store.rejected
        assert rejected.path == "acme/bad.json" and IssueCode.UNKNOWN_CANONICAL in {i.code for i in rejected.issues}
        assert "parameter catalog rejected" in caplog.text and "acme/bad.json" in caplog.text

    def test_a_file_that_is_not_json_is_rejected(self, root):
        put(root, "acme/broken.json", "{ not json")
        (rejected,) = load_store(root).rejected
        assert IssueCode.MALFORMED in {i.code for i in rejected.issues}

    def test_a_rejected_catalog_can_never_be_selected_or_activated(self, root):
        put(root, "acme/bad.json", catalog_json(x_reach(), lifecycle="active", version="nope"))
        store = load_store(root)
        assert store.select("Acme", "X-Series", "X1") is None and store.active() == ()

    def test_the_same_catalog_version_twice_is_a_duplicate(self, root):
        put(root, "acme/a.json", catalog_json(x_reach()))
        put(root, "acme/b.json", catalog_json(x_reach()))
        store = load_store(root)
        assert len(store.catalogs) == 1
        assert IssueCode.DUPLICATE in {i.code for r in store.rejected for i in r.issues}

    def test_only_one_version_of_a_catalog_may_be_active(self, root):
        put(root, "acme/v1.json", catalog_json(x_reach(), lifecycle="active", version="1.0.0"))
        put(root, "acme/v2.json", catalog_json(x_reach(), lifecycle="active", version="2.0.0"))
        store = load_store(root)
        assert [c.version for c in store.active()] == ["1.0.0"]
        assert IssueCode.CONFLICT in {i.code for r in store.rejected for i in r.issues}

    def test_an_invalid_canonical_registry_is_fatal(self, root):
        data = json.loads((root / REGISTRY_FILE).read_text(encoding="utf-8"))
        data["parameters"][0]["unit"] = "furlong"
        put(root, str(REGISTRY_FILE), data)
        with pytest.raises(CatalogValidationError):
            load_store(root)


class TestSelection:
    def build(self, root):
        put(root, "acme/draft.json", catalog_json(x_reach(), version="3.0.0", lifecycle="draft"))
        put(root, "acme/tested.json", catalog_json(x_reach(), version="2.0.0", lifecycle="tested"))
        put(root, "acme/active1.json", catalog_json(x_reach(), version="1.0.0", lifecycle="active",
                                                    applicability={"manufacturer": "Acme", "family": "X-Series", "model": "X1", "versions": ["V1.*", "V2.0"]}))
        return load_store(root)

    def test_only_an_active_catalog_is_selected_by_default(self, root):
        store = self.build(root)
        assert store.select("Acme", "X-Series", "X1").version == "1.0.0"

    def test_other_lifecycle_states_can_be_asked_for_explicitly(self, root):
        store = self.build(root)
        assert store.select("Acme", "X-Series", "X1", lifecycles=("tested",)).version == "2.0.0"
        assert store.select("Acme", "X-Series", "X1", lifecycles=("draft", "tested", "active")).version == "3.0.0"

    def test_manufacturer_family_and_model_must_match_ignoring_case_and_spacing(self, root):
        store = self.build(root)
        assert store.select("ACME", "x-series", " X1 ") is not None
        assert store.select("Acme", "X-Series", "X2") is None
        assert store.select("Other", "X-Series", "X1") is None

    def test_the_firmware_version_must_match_a_declared_pattern(self, root):
        store = self.build(root)
        assert store.select("Acme", "X-Series", "X1", version="V1.4") is not None
        assert store.select("Acme", "X-Series", "X1", version="V2.0") is not None
        assert store.select("Acme", "X-Series", "X1", version="V3.0") is None

    def test_the_highest_version_wins_among_equally_applicable_catalogs(self, root):
        put(root, "acme/a.json", catalog_json(x_reach(), version="1.2.0", lifecycle="tested", catalog_id="acme-a"))
        put(root, "acme/b.json", catalog_json(x_reach(), version="1.10.0", lifecycle="tested", catalog_id="acme-b"))
        store = load_store(root)
        assert store.select("Acme", "X-Series", "X1", lifecycles=("tested",)).catalog_id == "acme-b"       # 1.10 > 1.2, numerically
        assert store.get("acme-a").version == "1.2.0"


class TestLockedVersions:
    def locked_store(self, root, **overrides):
        put(root, "acme/x1.json", catalog_json(x_reach(), lifecycle="tested", **overrides))
        return load_store(root)

    def test_a_locked_catalog_must_be_recorded_in_the_lock(self, root):
        store = self.locked_store(root)
        problems = check_lock(store, {})
        assert len(problems) == 1 and "not in catalog.lock.json" in problems[0]
        write_lock(store, root)
        assert check_lock(store, load_lock(root)) == []

    def test_changing_the_meaning_of_a_locked_version_is_reported(self, root):
        write_lock(self.locked_store(root), root)
        edited = load_store_after(root, x_reach(name="OTHER{zone}"))
        (problem,) = check_lock(edited, load_lock(root))
        assert "changed its meaning without a new version" in problem and "acme-x1@1.0.0" in problem

    def test_a_new_version_may_change_meaning_and_gets_its_own_lock_entry(self, root):
        write_lock(self.locked_store(root), root)
        put(root, "acme/x1_v2.json", catalog_json(x_reach(name="OTHER{zone}"), version="1.1.0", lifecycle="tested"))
        store = load_store(root)
        assert len(check_lock(store, load_lock(root))) == 1                       # only the new, unrecorded version
        write_lock(store, root)
        assert check_lock(store, load_lock(root)) == [] and set(load_lock(root)) == {"acme-x1@1.0.0", "acme-x1@1.1.0"}

    def test_write_lock_never_rewrites_a_recorded_digest(self, root):
        write_lock(self.locked_store(root), root)
        before = load_lock(root)
        edited = load_store_after(root, x_reach(name="OTHER{zone}"))
        write_lock(edited, root)
        assert load_lock(root) == before

    def test_a_draft_is_not_locked_and_may_change_freely(self, root):
        put(root, "acme/x1.json", catalog_json(x_reach(), lifecycle="draft"))
        assert check_lock(load_store(root), {}) == []

    def test_the_digest_covers_meaning_not_description_or_lifecycle(self):
        base = catalog_json(x_reach())
        other = copy.deepcopy(base)
        other["description"], other["lifecycle"] = "reworded", "active"
        assert semantics_digest(base) == semantics_digest(other)
        other["mappings"][0]["source"]["name"] = "Y{zone}"
        assert semantics_digest(base) != semantics_digest(other)


def load_store_after(root: Path, new_mapping: dict):
    put(root, "acme/x1.json", catalog_json(new_mapping, lifecycle="tested"))
    return load_store(root)


class TestActivation:
    def test_an_active_catalog_becomes_an_interpretation_profile_and_nothing_else_does(self, root):
        put(root, "acme/x1.json", catalog_json(x_reach(), lifecycle="active"))
        put(root, "acme/y1.json", catalog_json(x_reach(), lifecycle="tested", catalog_id="acme-y1"))
        profiles = active_catalog_profiles(load_store(root))
        assert [(p.profile_id, p.version) for p in profiles] == [("acme-x1", "acme-x1-v1.0.0")]

    def test_a_catalog_with_a_hand_written_profiles_id_becomes_catalog_first_never_a_second_profile(self, root):
        put(root, "acme/x1.json", catalog_json(x_reach(), lifecycle="active", profile_id="hitachi-red670"))
        registry = build_registry(load_store(root))
        profiles = [p for p in registry._profiles if p.profile_id == "hitachi-red670"]            # noqa: SLF001
        assert len(profiles) == 1                                                  # one definition of one relay
        (profile,) = profiles
        assert profile.catalog_id == "acme-x1" and profile.extension.version == "hitachi-red670-v1"

    def test_two_active_catalogs_may_not_claim_the_same_relay_and_firmware(self, root):
        put(root, "acme/x1.json", catalog_json(x_reach(), lifecycle="active"))
        put(root, "acme/x1_b.json", catalog_json(x_reach(), lifecycle="active", catalog_id="acme-x1-b"))
        store = load_store(root)
        assert [c.catalog_id for c in store.active()] == ["acme-x1"]
        (rejected,) = store.rejected
        assert rejected.path.endswith("x1_b.json") and any(i.code == IssueCode.CONFLICT for i in rejected.issues)

    def test_active_catalogs_for_different_firmware_of_one_relay_may_coexist(self, root):
        for name, cid, versions in (("v1", "acme-x1", ["1.*"]), ("v2", "acme-x1-v2", ["2.*"])):
            data = catalog_json(x_reach(), lifecycle="active", catalog_id=cid)
            data["applicability"]["versions"] = versions
            put(root, f"acme/{name}.json", data)
        store = load_store(root)
        assert not store.rejected and len(store.active()) == 2
        assert store.select("Acme", "X-Series", "X1", "2.4").catalog_id == "acme-x1-v2"

    def test_an_active_catalog_joins_the_shared_registry_and_is_identifiable(self, root):
        put(root, "acme/x1.json", catalog_json(x_reach(), lifecycle="active"))
        registry = build_registry(load_store(root))
        assert "acme-x1" in {p.profile_id for p in registry._profiles}                          # noqa: SLF001
        assert "acme-x1" in {d.profile_id for d in registry.identification_descriptors()}
