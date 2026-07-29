# Jarvis Research Platform — Test Summary (v1.0.0-rc.1)

- Every layer ships unit + integration tests (isolated `_state/`, deterministic).
- Coverage: lifecycle transitions, hash-chain verify, tamper detection, replay,
  READ ONLY protection, forbidden-import/method scans, CLI, end-to-end.
- Full repository regression is run and required green after every phase.
- Run: `python -m pytest jarvis -q`
