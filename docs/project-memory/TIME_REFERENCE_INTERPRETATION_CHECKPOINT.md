# Time Reference Interpretation - superseded checkpoint

The 2026-10-23 investigation found that the initial metadata-only / explicit Event
Reconstruction draft could not satisfy automatic Waveform placement under unchanged
Time Groups. Existing group identities also own t0 and cursor coordinates.

The final owner rules resolved the scope: a session-scoped, recording-specific
interpretation must feed every consumer centrally and immediately. The completed
design uses the existing grouping and state machinery with coordinate rebasing,
not a separate synchronization engine. The earlier draft is superseded.

See [TIME_REFERENCE_INTERPRETATION.md](TIME_REFERENCE_INTERPRETATION.md) for the
current design, lifecycle, provenance, transition policy and GPTH/KTBR acceptance
examples; see HANDOFF for final validation and release status.
