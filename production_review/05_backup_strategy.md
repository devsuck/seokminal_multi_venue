# Backup Strategy

- Ledgers are append-only JSONL files under `_state/` — copy-on-write friendly.
- SHA256 hash-chaining makes any post-backup tampering detectable on restore.
- Deterministic replay allows verification that a restored backup is intact.
- Recommended: periodic snapshot of `_state/` + verify_chain before and after.
