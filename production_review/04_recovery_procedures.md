# Recovery Procedures

1. Detect: run each layer's `verify_chain()` — reports tamper / broken chain / dup.
2. Isolate: append-only ledgers mean the last valid record is always recoverable.
3. Restore: replay from the last intact `record_hash`; no in-place mutation needed.
4. Record: P24 research_reliability captures incidents, recovery plans, postmortems
   (records only — recovery is research-process recovery, never live-system).
