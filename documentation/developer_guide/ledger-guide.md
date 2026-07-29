# Ledger Guide

Every layer that records something writes it to an **append-only, SHA256
hash-chained JSONL ledger**. Ledgers are the durable, tamper-evident record of what
the research OS observed. They are never rewritten, reordered, or deleted.

## Where ledgers live

Ledgers are written into the shared `_state/` directory. A layer resolves its file
via `jarvis.config.state_path(name)`, which returns an absolute path inside
`_state/`. One JSON object per line; each line is one immutable record.

## Record fields and the hash chain

Each record carries two chaining fields:

- `previous_hash` — the `record_hash` of the prior record (or a genesis value).
- `record_hash` — this record's hash, binding it to the chain.

The chain means any edit to an old record invalidates every record after it, which
is exactly what makes tampering detectable.

## The `content_hash` convention

`content_hash(record)` hashes the record **excluding** the chaining and report
fields `{previous_hash, record_hash, report_hash}`. The remaining core is
serialized canonically and hashed:

```python
import hashlib, json

def content_hash(record: dict) -> str:
    core = {k: v for k, v in record.items()
            if k not in {"previous_hash", "record_hash", "report_hash"}}
    blob = json.dumps(core, sort_keys=True, ensure_ascii=False, default=str)
    return "sha256:" + hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]
```

Excluding the chaining fields is what lets a verifier recompute the content hash
independently and compare it against the chain.

## Event sourcing and lifecycles

Lifecycles are event-sourced rather than stored as mutable state. A layer defines
an `ALLOWED_TRANSITIONS` dict and a `can_transition(frm, to)` helper; the **current
state is the `to_state` of the last event** in the ledger.

```python
ALLOWED_TRANSITIONS = {"draft": {"active"}, "active": {"closed"}}

def can_transition(frm: str, to: str) -> bool:
    return to in ALLOWED_TRANSITIONS.get(frm, set())
```

Deterministic record and event IDs are a short tag plus `sha1(...)[:12]`.

## Reading and verifying a ledger

To verify, read the JSONL top to bottom and, for each record:

1. recompute `content_hash(record)` and confirm it matches the recorded content,
2. confirm `previous_hash` equals the prior record's `record_hash`,
3. confirm each state change satisfies `can_transition(frm, to)`.

Layers expose this through `verify.py`; run it via the layer CLI where available.

## Never modify or delete

Ledgers are append-only by contract. Do not hand-edit `_state/` files, do not
delete records, and do not reorder lines. Corrections are appended as new events,
never applied in place.
