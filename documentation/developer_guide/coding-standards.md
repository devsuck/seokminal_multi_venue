# Coding Standards

These standards keep the Autonomous Quant Research OS safe, deterministic, and
auditable. They are enforced partly by code review and partly by automated AST
scans in each layer's test suite. Read this before writing any code.

## The additive-only rule

Every layer is **additive and read-only**. Code in `jarvis/` must never trade,
place or cancel orders, deploy, allocate capital, promote or demote models, or
mutate permissions. It observes, analyzes, and records. If a change would give a
layer the ability to act on the market or on platform state, it does not belong
here. Tests assert this by scanning for forbidden imports and forbidden execution
primitives (subprocess, network sends, order APIs) at the AST level.

## Frozen dataclasses with `to_dict()`

Model types are immutable value objects:

```python
from dataclasses import dataclass, asdict

@dataclass(frozen=True)
class ExperimentRecord:
    experiment_id: str
    tag: str

    def to_dict(self) -> dict:
        return asdict(self)
```

Immutability makes records safe to hash, replay, and append to ledgers without
accidental mutation.

## Deterministic IDs

Identifiers are a short human-readable tag plus a hash suffix. **No wall-clock
time may enter an ID**, because that would break replay determinism.

```python
import hashlib

def make_id(tag: str, *parts: str) -> str:
    digest = hashlib.sha1("|".join(parts).encode()).hexdigest()[:12]
    return f"{tag}-{digest}"
```

Lifecycle state is event-sourced: an `ALLOWED_TRANSITIONS` dict plus
`can_transition(frm, to)`; the current state is the last event's `to_state`.

## Append-only ledgers

Persistence is append-only, hash-chained JSONL (see
`documentation/developer_guide/ledger-guide.md`). Never rewrite, reorder, or
delete ledger records. Each record carries `previous_hash` and `record_hash`.

## No forbidden imports or execution

Do not import execution-capable modules (order routers, brokers with write access,
deployment tooling) into a research layer. Do not spawn processes or open sockets
for the purpose of acting. The per-layer forbidden-import test will fail the build.

## Docstrings

Every public module, class, and function has a concise docstring stating what it
records or verifies and, where relevant, that it is read-only. Keep docstrings
factual; describe inputs, outputs, and determinism guarantees.

## No model-id leakage

Artifacts, ledgers, and generated docs must not embed live model identifiers,
credentials, or platform secrets. Recorded artifacts describe research outcomes,
not the identity of any production model behind them.
