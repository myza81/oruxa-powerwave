"""Build a synthetic relay sheet PDF from its spec (the browser tests' fixture source; DEC-199).

    python -m tests.relay_conformance.sheet_cli <sheet-id> ['<overrides JSON>']

Writes the PDF bytes to stdout. Run from ``backend/``. The overrides are those of ``sheet_spec`` (variant, drop, set,
set_range, insert_after, append, notes), so the browser tests never hold relay rows of their own.
"""

from __future__ import annotations

import json
import sys

from tests.relay_conformance.sheet_spec import sheet_pdf


def main(argv: list[str]) -> int:
    if len(argv) not in (1, 2):
        sys.stderr.write(__doc__)
        return 2
    overrides = json.loads(argv[1]) if len(argv) == 2 else None
    sys.stdout.buffer.write(sheet_pdf(argv[0], overrides))
    sys.stdout.buffer.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
