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
  here; today the frontend shows each stored value's own digits.

``DEFAULT_SOURCE_TIMEZONE`` is the one place to change the interpretation
for this deployment (an IANA name). Malaysian recorders and BEN32 exports
stamp local time (UTC+08:00), so naive engineering timestamps are read
as Asia/Kuala_Lumpur.
"""

from __future__ import annotations

from datetime import datetime, timezone, tzinfo
from functools import cache
from zoneinfo import ZoneInfo

#: IANA zone a timezone-naive engineering timestamp is interpreted in.
DEFAULT_SOURCE_TIMEZONE = "Asia/Kuala_Lumpur"


@cache
def _zone(name: str) -> tzinfo:
    return ZoneInfo(name)


def interpret_naive(value: datetime, timezone_name: str = DEFAULT_SOURCE_TIMEZONE) -> datetime:
    """Attach the source timezone to a naive value (digits unchanged);
    an aware value is returned untouched -- its declared offset wins."""
    if value.tzinfo is not None:
        return value
    return value.replace(tzinfo=_zone(timezone_name))


def canonical_utc(value: datetime, timezone_name: str = DEFAULT_SOURCE_TIMEZONE) -> datetime:
    """The value's absolute instant, expressed in UTC."""
    return interpret_naive(value, timezone_name).astimezone(timezone.utc)
