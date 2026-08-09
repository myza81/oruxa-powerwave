import os
from abc import ABC, abstractmethod
from pathlib import Path


class StorageBackend(ABC):
    @abstractmethod
    def write_text(self, category: str, filename: str, content: str):
        pass

    @abstractmethod
    def read_text(self, category: str, filename: str) -> str:
        pass

    @abstractmethod
    def exists(self, category: str, filename: str) -> bool:
        pass


class LocalStorage(StorageBackend):
    ALLOWED_CATEGORIES = {
        "original",
        "working",
        "exports",
        "temporary",
    }

    def __init__(self, root: str):
        self.root = Path(root)

    def _path(self, category: str, filename: str) -> Path:
        if category not in self.ALLOWED_CATEGORIES:
            raise ValueError("Invalid storage category")

        return self.root / category / filename

    def write_text(self, category: str, filename: str, content: str):
        path = self._path(category, filename)

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

        return path

    def read_text(self, category: str, filename: str) -> str:
        return self._path(category, filename).read_text(encoding="utf-8")

    def exists(self, category: str, filename: str) -> bool:
        return self._path(category, filename).exists()


def get_storage() -> StorageBackend:
    storage_type = os.getenv("STORAGE_TYPE", "local")

    if storage_type == "local":
        storage_path = os.environ["STORAGE_PATH"]
        return LocalStorage(storage_path)

    raise RuntimeError(
        f"Unsupported storage backend: {storage_type}"
    )
