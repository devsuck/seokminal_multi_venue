# ADR 0002 — Hash-Chain Integrity

## Status

Accepted.

## Context

Append-only storage (ADR 0001) prevents in-place edits, but a file on disk can still be
tampered with out of band. We need each record to be self-verifying and each ledger to detect
any modification, reordering, or insertion.

## Decision

Each record is sealed into a **SHA256 hash chain**:

- `record_hash = content_hash(record)`, where `content_hash` serializes the record excluding
  `{previous_hash, record_hash, report_hash}` with
  `json.dumps(core, sort_keys=True, ensure_ascii=False, default=str)` and takes
  `"sha256:" + sha256(...)[:16]`.
- `previous_hash` points at the prior record's `record_hash` (or `GENESIS` for the first).

Verification recomputes each `record_hash` and checks each `previous_hash` link.

## Consequences

- **Tamper-evidence:** any edit to a record changes its `content_hash`, breaking the chain at
  that point; `jarvis.integrity.verify_ledger` reports the exact break index and reason.
- **Determinism:** hashing uses sorted keys and stable serialization, so the same content always
  hashes identically — a prerequisite for replay (ADR 0006).
- **Uniformity:** every layer shares the same convention, so one integrity verifier works across
  all ledgers, and SBOM/artifact checksums reuse the same hashing style.
- **Bounded strength:** the 16-hex truncation is for compact IDs/links, not cryptographic
  non-repudiation; physical file access with full rewrite could forge a self-consistent copy,
  which is why recovery always writes to a new file and off-site verification is recommended.
