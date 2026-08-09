"""Storage abstraction for Powerwave engineering files.

The local backend is the only implementation for now; object storage arrives
later behind the same interface. Two invariants matter here:

* a caller-supplied filename can never escape the storage root, and
* files in the ``original`` category are write-once, because they are the
  as-received engineering inputs that everything else is derived from.
"""

from abc import ABC, abstractmethod
from pathlib import Path

from app.config import Settings

ORIGINAL_CATEGORY = "original"

ALLOWED_CATEGORIES = frozenset(
    {
        ORIGINAL_CATEGORY,
        "working",
        "exports",
        "temporary",
    }
)


class StorageError(RuntimeError):
    """Base class for storage failures."""


class InvalidCategoryError(StorageError, ValueError):
    """Raised for a category outside :data:`ALLOWED_CATEGORIES`."""


class InvalidFilenameError(StorageError, ValueError):
    """Raised for a filename that is unsafe or would escape the storage root."""


class ImmutableFileError(StorageError):
    """Raised on an attempt to overwrite a write-once file."""


def _validate_category(category: str) -> str:
    if category not in ALLOWED_CATEGORIES:
        raise InvalidCategoryError(f"Invalid storage category: {category!r}")
    return category


def _validate_filename(filename: str) -> tuple[str, ...]:
    """Return the filename as validated path segments.

    Relative subdirectories are permitted; anything that could redirect the
    write elsewhere on the filesystem is not.
    """
    if not filename or not filename.strip():
        raise InvalidFilenameError("Filename must not be empty")

    if "\x00" in filename:
        raise InvalidFilenameError("Filename must not contain null bytes")

    # Normalise Windows separators so the same rules apply on every platform.
    normalised = filename.replace("\\", "/")

    if normalised.startswith("/"):
        raise InvalidFilenameError("Filename must be relative, not absolute")

    # A drive prefix ("C:") is absolute on Windows even without a leading slash.
    head = normalised.split("/", 1)[0]
    if len(head) >= 2 and head[1] == ":":
        raise InvalidFilenameError("Filename must not contain a drive letter")

    segments = tuple(part for part in normalised.split("/") if part)
    if not segments:
        raise InvalidFilenameError("Filename must name a file")

    for part in segments:
        if part in (".", ".."):
            raise InvalidFilenameError(
                "Filename must not contain relative path segments"
            )

    return segments


class StorageBackend(ABC):
    @abstractmethod
    def write_text(self, category: str, filename: str, content: str) -> Path: ...

    @abstractmethod
    def write_bytes(self, category: str, filename: str, content: bytes) -> Path: ...

    @abstractmethod
    def read_text(self, category: str, filename: str) -> str: ...

    @abstractmethod
    def read_bytes(self, category: str, filename: str) -> bytes: ...

    @abstractmethod
    def exists(self, category: str, filename: str) -> bool: ...

    @abstractmethod
    def list(self, category: str) -> tuple[str, ...]: ...


class LocalStorage(StorageBackend):
    """Filesystem-backed storage rooted at a single directory."""

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()

    def _path(self, category: str, filename: str) -> Path:
        _validate_category(category)
        segments = _validate_filename(filename)

        base = (self.root / category).resolve()
        candidate = base.joinpath(*segments).resolve()

        # Defence in depth: even if the checks above miss a platform quirk, a
        # resolved path outside the category root is never acceptable. This is
        # what catches symlinks pointing out of the tree.
        if candidate != base and base not in candidate.parents:
            raise InvalidFilenameError("Filename escapes the storage root")

        return candidate

    def _guard_immutable(self, category: str, path: Path) -> None:
        if category == ORIGINAL_CATEGORY and path.exists():
            raise ImmutableFileError(
                f"Files in {ORIGINAL_CATEGORY!r} are write-once and cannot be replaced"
            )

    def write_text(self, category: str, filename: str, content: str) -> Path:
        path = self._path(category, filename)
        self._guard_immutable(category, path)

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

        return path

    def write_bytes(self, category: str, filename: str, content: bytes) -> Path:
        path = self._path(category, filename)
        self._guard_immutable(category, path)

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

        return path

    def read_text(self, category: str, filename: str) -> str:
        return self._path(category, filename).read_text(encoding="utf-8")

    def read_bytes(self, category: str, filename: str) -> bytes:
        return self._path(category, filename).read_bytes()

    def exists(self, category: str, filename: str) -> bool:
        return self._path(category, filename).is_file()

    def list(self, category: str) -> tuple[str, ...]:
        _validate_category(category)

        base = (self.root / category).resolve()
        if not base.is_dir():
            return ()

        return tuple(
            sorted(
                path.relative_to(base).as_posix()
                for path in base.rglob("*")
                if path.is_file()
            )
        )


def get_storage(settings: Settings) -> StorageBackend:
    """Build the storage backend described by ``settings``.

    ``Settings`` has already rejected unknown backends, so reaching the final
    raise means a backend was added to config without an implementation here.
    """
    if settings.storage_type == "local":
        return LocalStorage(settings.storage_path)

    raise StorageError(f"Unsupported storage backend: {settings.storage_type!r}")
