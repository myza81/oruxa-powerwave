"""Legacy BEN5K decoder package.

Handles the older Qualitrol BEN recorder family (signature 28 ff / 05 00).
The SubBen decoder (parent package) is not modified; this package lives here
in isolation and shares only BenRecord and BenLayout with the parent.

Entry point: parse_ben5k(data: bytes) -> BenRecord
"""

from app.providers.ben.legacy_ben5k.normalize import parse_ben5k

__all__ = ["parse_ben5k"]
