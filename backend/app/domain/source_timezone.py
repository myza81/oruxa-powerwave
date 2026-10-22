"""Source timezone interpretation for absolute recording timestamps (DEC-121).

Three separate concerns, never conflated:

- **Stored timestamp** -- a source's ``start_time``/``trigger_time`` as its
  importer produced it, unchanged: timezone-aware UTC for BEN; aware with
  the declared offset for a COMTRADE-2013 CFG that declares ``time_code``
  or a CSV/Excel value that carries an offset; *naive* (the recorder's
  wall-clock digits, no zone) for COMTRADE without ``time_code`` and for
  offset-less CSV/Excel times.
- **Source timezone interpretation** -- the zone a *naive* stored
  timestamp is understood to be in. A declared offset always wins; only
  a naive value uses ``DEFAULT_SOURCE_TIMEZONE``. Applied only where
  instants are compared (``time_grouping.normalize_absolute_datetime``),
  never written back into the stored value.
- **Display timezone** -- how the UI renders a timestamp. Not decided
  here; DEC-122 formats canonical instants in the display timezone. Unknown
  recorder clocks retain their digits without conversion.

``DEFAULT_SOURCE_TIMEZONE`` is the one place to change the interpretation
for this deployment (an IANA name). Malaysian recorders and BEN32 exports
stamp local time (UTC+08:00), so naive engineering timestamps are read
as Asia/Kuala_Lumpur.
"""

from __future__ import annotations

from datetime import datetime, timezone, tzinfo
from enum import StrEnum
from functools import cache
from zoneinfo import ZoneInfo

#: IANA zone a timezone-naive engineering timestamp is interpreted in.
DEFAULT_SOURCE_TIMEZONE = "Asia/Kuala_Lumpur"


class TimeBasis(StrEnum):
    """Authority of recorder clock digits, independent of elapsed-time grouping.

    SOURCE_TIMEZONE retains DEC-121's existing policy for offset-less inputs;
    UNKNOWN explicitly opts out of that policy. Awareness alone is not evidence.
    This describes the time standard, not the accuracy of the recorder clock.
    """

    VERIFIED_UTC = "verified_utc"
    VERIFIED_LOCAL = "verified_local"
    SOURCE_TIMEZONE = "source_timezone"
    UNKNOWN = "unknown"


def resolve_time_basis(value: datetime | None, explicit: TimeBasis | None = None) -> TimeBasis | None:
    """Preserve explicit authority; infer only existing providers' timezone declarations."""
    if explicit is not None:
        return explicit
    if value is None:
        return None
    if value.utcoffset() is None:
        return TimeBasis.SOURCE_TIMEZONE
    return TimeBasis.VERIFIED_UTC if value.utcoffset().total_seconds() == 0 else TimeBasis.VERIFIED_LOCAL


@cache
def _zone(name: str) -> tzinfo:
    return ZoneInfo(name)


def interpret_naive(value: datetime, timezone_name: str = DEFAULT_SOURCE_TIMEZONE) -> datetime:
    """Attach the source timezone to a naive value (digits unchanged);
    an aware value is returned untouched -- its declared offset wins."""
    if value.tzinfo is not None:
        return value
    return value.replace(tzinfo=_zone(timezone_name))


def canonical_utc(
    value: datetime, timezone_name: str = DEFAULT_SOURCE_TIMEZONE, *, time_basis: TimeBasis | None = None,
) -> datetime | None:
    """The canonical instant, or None when clock authority is explicitly unknown.

    Never feed UNKNOWN through the naive-source policy, even if a legacy
    intermediate value happens to carry tzinfo.
    """
    if time_basis == TimeBasis.UNKNOWN:
        return None
    return interpret_naive(value, timezone_name).astimezone(timezone.utc)
