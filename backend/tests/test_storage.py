from pathlib import Path

import pytest

from app.config import Settings
from app.storage import (
    ImmutableFileError,
    InvalidCategoryError,
    InvalidFilenameError,
    LocalStorage,
    StorageError,
    get_storage,
)

TRAVERSAL_ATTEMPTS = [
    "../escaped.txt",
    "../../escaped.txt",
    "working/../../escaped.txt",
    "..\\escaped.txt",
    "subdir\\..\\..\\escaped.txt",
    "/etc/passwd",
    "\\windows\\system32\\config",
    "C:/Windows/System32/config",
    "./../escaped.txt",
]


class TestRoundTrip:
    def test_write_and_read_text(self, storage):
        storage.write_text("working", "notes.txt", "hello")

        assert storage.read_text("working", "notes.txt") == "hello"

    def test_write_and_read_bytes(self, storage):
        payload = b"\x00\x01\x02binary"
        storage.write_bytes("exports", "report.bin", payload)

        assert storage.read_bytes("exports", "report.bin") == payload

    def test_write_creates_nested_directories(self, storage):
        storage.write_text("working", "nested/deep/file.txt", "x")

        assert storage.read_text("working", "nested/deep/file.txt") == "x"

    def test_write_returns_path_inside_root(self, storage):
        path = storage.write_text("working", "notes.txt", "hello")

        assert path.is_file()
        assert storage.root in path.parents


class TestExists:
    def test_missing_file(self, storage):
        assert storage.exists("working", "absent.txt") is False

    def test_present_file(self, storage):
        storage.write_text("working", "present.txt", "x")

        assert storage.exists("working", "present.txt") is True

    def test_directory_is_not_a_file(self, storage):
        storage.write_text("working", "nested/file.txt", "x")

        assert storage.exists("working", "nested") is False


class TestListing:
    def test_empty_category(self, storage):
        assert storage.list("working") == ()

    def test_lists_nested_files_sorted_with_posix_separators(self, storage):
        storage.write_text("working", "b.txt", "b")
        storage.write_text("working", "a.txt", "a")
        storage.write_text("working", "nested/c.txt", "c")

        assert storage.list("working") == ("a.txt", "b.txt", "nested/c.txt")

    def test_listing_is_scoped_to_one_category(self, storage):
        storage.write_text("working", "w.txt", "w")
        storage.write_text("exports", "e.txt", "e")

        assert storage.list("working") == ("w.txt",)
        assert storage.list("exports") == ("e.txt",)

    def test_invalid_category_is_rejected(self, storage):
        with pytest.raises(InvalidCategoryError):
            storage.list("secrets")


class TestCategoryValidation:
    @pytest.mark.parametrize("category", ["secrets", "", "Original", "../etc"])
    def test_unknown_categories_are_rejected(self, storage, category):
        with pytest.raises(InvalidCategoryError):
            storage.write_text(category, "file.txt", "x")


class TestPathTraversal:
    @pytest.mark.parametrize("filename", TRAVERSAL_ATTEMPTS)
    def test_write_text_rejects_traversal(self, storage, filename):
        with pytest.raises(InvalidFilenameError):
            storage.write_text("working", filename, "owned")

    @pytest.mark.parametrize("filename", TRAVERSAL_ATTEMPTS)
    def test_read_text_rejects_traversal(self, storage, filename):
        with pytest.raises(InvalidFilenameError):
            storage.read_text("working", filename)

    @pytest.mark.parametrize("filename", TRAVERSAL_ATTEMPTS)
    def test_exists_rejects_traversal(self, storage, filename):
        with pytest.raises(InvalidFilenameError):
            storage.exists("working", filename)

    @pytest.mark.parametrize("filename", ["", "   ", "file\x00.txt", "..", "."])
    def test_malformed_filenames_are_rejected(self, storage, filename):
        with pytest.raises(InvalidFilenameError):
            storage.write_text("working", filename, "x")

    def test_traversal_does_not_touch_the_filesystem(self, storage, tmp_path):
        outside = tmp_path.parent / "escaped.txt"

        with pytest.raises(InvalidFilenameError):
            storage.write_text("working", f"../{outside.name}", "owned")

        assert not outside.exists()


class TestWriteOnceOriginals:
    def test_first_write_succeeds(self, storage):
        storage.write_text("original", "drawing.dxf", "v1")

        assert storage.read_text("original", "drawing.dxf") == "v1"

    def test_second_text_write_is_rejected(self, storage):
        storage.write_text("original", "drawing.dxf", "v1")

        with pytest.raises(ImmutableFileError):
            storage.write_text("original", "drawing.dxf", "v2")

        assert storage.read_text("original", "drawing.dxf") == "v1"

    def test_second_bytes_write_is_rejected(self, storage):
        storage.write_bytes("original", "drawing.dxf", b"v1")

        with pytest.raises(ImmutableFileError):
            storage.write_bytes("original", "drawing.dxf", b"v2")

        assert storage.read_bytes("original", "drawing.dxf") == b"v1"

    def test_bytes_write_cannot_replace_a_text_original(self, storage):
        storage.write_text("original", "drawing.dxf", "v1")

        with pytest.raises(ImmutableFileError):
            storage.write_bytes("original", "drawing.dxf", b"v2")

    @pytest.mark.parametrize("category", ["working", "exports", "temporary"])
    def test_other_categories_remain_mutable(self, storage, category):
        storage.write_text(category, "file.txt", "v1")
        storage.write_text(category, "file.txt", "v2")

        assert storage.read_text(category, "file.txt") == "v2"


class TestGetStorage:
    def test_builds_local_storage(self, settings):
        backend = get_storage(settings)

        assert isinstance(backend, LocalStorage)
        assert backend.root == Path(settings.storage_path).resolve()

    def test_unknown_backend_is_rejected(self, settings):
        broken = Settings(
            environment=settings.environment,
            storage_type="s3",
            storage_path=settings.storage_path,
            cors_origins=settings.cors_origins,
            database_url=None,
        )

        with pytest.raises(StorageError):
            get_storage(broken)
