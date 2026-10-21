"""``BaseProvider`` adapter for BEN files.

Registered for upload by ``app.services.import_service`` (DEC-120): a
``.ben`` file is routed here by extension, and the native parser then
validates its signature/layout -- a non-BEN or unsupported-layout file
fails with a BEN error, never falling back to another parser.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.domain import DisturbanceRecord
from app.domain.metadata import DEFAULT_NOMINAL_FREQUENCY_HZ
from app.providers.base import BaseProvider
from app.providers.ben.model import BenRecordClass
from app.providers.ben.normalize import channel_identities, to_disturbance_record
from app.providers.ben.parser import parse_ben_experimental

BEN_SUFFIX = ".ben"
SOURCE_FORMAT = "BEN"
_LAYOUT_FAMILY_SUBBEN = "BEN32 SubBen"
_LAYOUT_FAMILY_BEN5K = "BEN32 BEN5K Legacy"


class BenProvider(BaseProvider):
    """Loads a BEN32 SubBen record as a ``DisturbanceRecord``.

    BEN declares no nominal frequency in any decoded field, so it is an
    import-context input: an explicit value when the caller has one,
    otherwise Powerwave's shared ``DEFAULT_NOMINAL_FREQUENCY_HZ``,
    recorded as assumed in the provenance.
    """

    provider_name: str = "ben"

    def __init__(
        self,
        *,
        nominal_frequency_hz: float | None = None,
        ben5k_experimental_enabled: bool = False,
    ) -> None:
        self._nominal_frequency_assumed = nominal_frequency_hz is None
        self._nominal_frequency_hz = (
            DEFAULT_NOMINAL_FREQUENCY_HZ if nominal_frequency_hz is None else nominal_frequency_hz
        )
        self._ben5k_experimental = ben5k_experimental_enabled

    def can_load(self, path: Path) -> bool:
        return path.suffix.lower() == BEN_SUFFIX

    def load(self, path: Path) -> DisturbanceRecord:
        return self.load_with_provenance(path)[0]

    def load_with_provenance(self, path: Path) -> tuple[DisturbanceRecord, dict[str, Any]]:
        try:
            data = path.read_bytes()
        except OSError as exc:
            from app.providers.ben.errors import BenFormatError
            raise BenFormatError(f"Cannot read BEN file '{path}': {exc}") from exc

        record = parse_ben_experimental(data, allow_legacy_ben5k=self._ben5k_experimental)
        normalized = to_disturbance_record(
            record,
            source_file=str(path),
            nominal_frequency_hz=self._nominal_frequency_hz,
        )
        header = record.header
        is_ben5k = header.record_class == BenRecordClass.BEN5K_LEGACY
        layout_family = _LAYOUT_FAMILY_BEN5K if is_ben5k else _LAYOUT_FAMILY_SUBBEN
        time_basis = "UTC (unverified)" if is_ben5k else "UTC"
        provenance: dict[str, Any] = {
            "source_format": SOURCE_FORMAT,
            "layout_family": layout_family,
            "record_class": header.record_class.value,
            "recorder_unit_id": header.recorder_unit_id,
            "record_number": header.record_number,
            "time_basis": time_basis,
            "pre_trigger_samples": header.pre_trigger_samples,
            "nominal_frequency_hz": self._nominal_frequency_hz,
            "nominal_frequency_assumed": self._nominal_frequency_assumed,
            "diagnostics": [
                {"code": d.code, "severity": d.severity, "message": d.message} for d in record.diagnostics
            ],
            "channels": channel_identities(record),
        }
        return normalized, provenance
