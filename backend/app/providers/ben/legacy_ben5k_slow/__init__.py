"""Legacy BEN5K Slow decoder package.

Handles the BEN5K Slow recorder family (layout signature 29 ff / gen 05 00,
class flag 0x01 = Slow).

The SubBen and BEN5K Fast decoders (parent package / sibling package) are not
modified; this package lives here in isolation and shares only BenRecord and
BenLayout constants with the parent.

Entry point: parse_ben5k_slow(data: bytes) -> BenRecord
"""

from app.providers.ben.legacy_ben5k_slow.normalize import parse_ben5k_slow

__all__ = ["parse_ben5k_slow"]
