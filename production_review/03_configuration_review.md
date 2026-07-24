# Configuration Review

- Ledger root resolved via `jarvis.config.state_path` (shared `_state/`).
- No secrets, credentials, tokens, or broker endpoints required or stored.
- All layers deterministic given identical ledger state (no wall-clock in IDs).
- 14 research layers + finalization layers, each self-contained.
