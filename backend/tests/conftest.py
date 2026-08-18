from pathlib import Path

import pytest

from app.config import Settings
from app.storage import LocalStorage

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "comtrade"


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        environment="development",
        storage_type="local",
        storage_path=str(tmp_path),
        cors_origins=("http://localhost:8101",),
        database_url=None,
        max_event_upload_size_mb=100,
        git_sha="local",
        version="local",
    )


@pytest.fixture
def storage(tmp_path) -> LocalStorage:
    return LocalStorage(tmp_path)


@pytest.fixture
def comtrade_fixtures_dir() -> Path:
    return FIXTURES_DIR
