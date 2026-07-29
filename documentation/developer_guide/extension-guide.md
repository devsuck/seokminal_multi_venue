# Extension Guide

This guide explains how to add a **new additive layer** to the Autonomous Quant
Research OS. New layers extend the system's observation and recording capabilities;
they never add execution, trading, or permission-mutating behavior.

## Phase 0: collision check

Before writing any code, prove your new layer does not collide with the 111
existing layers. Check three namespaces:

- **Package name:** `jarvis/<your_layer>/` must not already exist.
- **ID / tag prefix:** the short tag used in deterministic IDs must be unique so
  records from different layers never share an ID space.
- **Ledger file name:** the `state_path(name)` name you pass must be free in `_state/`.

```bash
ls jarvis | grep -i <candidate_name>
grep -rn "state_path(\"<candidate_ledger>\")" jarvis
```

Pick a free namespace before proceeding. A collision here corrupts audit trails.

## Scaffold the layer

Create `jarvis/<your_layer>/` with the standard files:

- `models.py` — frozen dataclasses with `to_dict()`; IDs are `tag + sha1(...)[:12]`.
- `ledger.py` — append-only hash-chained JSONL via `state_path("<your_ledger>")`,
  with `content_hash`, `previous_hash`, and `record_hash` handling.
- `engine.py` — deterministic recording/analysis logic; no wall-clock in IDs.
- `verify.py` — verification plus `replay(engine, now)`.
- `__main__.py` — argparse CLI supporting at least `replay` and `verify`.
- `tests/` — model, ledger, replay, and forbidden-import/execution tests, plus the
  `_iso(tmp_path, monkeypatch)` fixture.

## Keep it research-only

Your layer must remain additive and read-only:

- Do not import order routers, deployment tooling, or write-capable brokers.
- Do not spawn subprocesses or open sockets to act on anything.
- Do not promote models, allocate capital, or change permissions.
- Record model **outcomes**, never live model identifiers or secrets.

Add the forbidden-import and forbidden-execution AST tests from day one — they are
the mechanical proof that the layer is safe.

## Wire in verification and docs

Ensure `python -m jarvis.<your_layer> replay` produces identical output on repeated
runs, and that `python -m jarvis.<your_layer> verify` walks and validates the
ledger. Then regenerate docs:

```bash
python -m jarvis.documentation gen
python -m jarvis.documentation validate
```

## Commit discipline

Land the layer as a self-contained, additive commit. Run the full regression
(`python -m pytest jarvis -q`) plus docs validation before committing. See
`documentation/developer_guide/contribution-guide.md` for branch and message rules.
