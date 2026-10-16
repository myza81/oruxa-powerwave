"""Generic relay conformance harness (Relay Scalability Phase 0, DEC-199).

Data, not code: ``sheets/<id>.json`` describes one synthetic relay setting sheet (the single source for backend and
browser tests), ``expectations/<name>.json`` the review / readiness / Apply result a sheet -- or an owner's real sheet,
gated on ``RELAY_SAMPLE_PDF_DIR`` -- must produce. ``tests/test_relay_conformance.py`` runs one generic suite over
every shipped catalog, sheet and expectation; nothing here knows a relay family.
"""
