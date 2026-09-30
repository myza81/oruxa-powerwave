"""``BaseProvider`` adapter for BEN files.

Deliberately NOT registered with any ingestion path yet: the upload
workflow (``app.services.import_service``) still accepts COMTRADE only.
Wiring ``.ben`` into upload/normalization is a separate, owner-approved
task.
"""

from __future__ import annotations

from pathlib import Path

from app.domain import DisturbanceRecord
from app.providers.base import BaseProvider
from app.providers.ben.normalize import to_disturbance_record
from app.providers.ben.parser import parse_ben_file

BEN_SUFFIX = ".ben"


class BenProvider(BaseProvider):
    """Loads a BEN32 SubBen record as a ``DisturbanceRecord``.

    ``nominal_frequency_hz`` must be supplied because BEN does not
    declare it in any decoded field.
    """

    provider_name: str = "ben"

    def __init__(self, *, nominal_frequency_hz: float) -> None:
        self._nominal_frequency_hz = nominal_frequency_hz

    def can_load(self, path: Path) -> bool:
        return path.suffix.lower() == BEN_SUFFIX

    def load(self, path: Path) -> DisturbanceRecord:
        record = parse_ben_file(path)
        return to_disturbance_record(
            record,
            source_file=str(path),
            nominal_frequency_hz=self._nominal_frequency_hz,
        )
