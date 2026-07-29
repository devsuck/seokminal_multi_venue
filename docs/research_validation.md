# Research Re-validation (P57)

> Governed by `docs/CONSTITUTION.md` and the P53–P56 pipeline docs.
> **Integration over expansion** — reuses the P53 `ingest()`; NO new store.
> **Never fabricate.** Missing validation stays INCOMPLETE unless a real harness fills it.
> No trading / execution / broker / capital allocation.

## Problem it fixes

Historical experiments are often *partially* validated — e.g. `Momentum_v1` has Return and
Sharpe but no Walk-Forward, Cost model, or Random Baseline. P55 correctly keeps them
INCOMPLETE (no fabrication). P57 adds the **optional** path to *upgrade* them — but only with
values a real validation harness actually computes.

## Flow

```
Historical experiment (INCOMPLETE)
   ↓  plan(record) → present / missing validations
   ↓  revalidate(record, harness=…)
harness(record) → { only-genuinely-computed validation metrics }
   ↓  merge ONLY missing ∩ numeric (fabrication filtered out)
   ├─ nothing valid produced → stays INCOMPLETE / UNAVAILABLE (no write)
   └─ metrics filled → re-ingest as version "+reval" via P53 ingest()
                       → re-classified SUCCESS / FAILURE / PARTIAL   → Knowledge upgrade
```

## Key guarantees

- **Harness is injected, never assumed.** `harness=None` → status `UNAVAILABLE`, record stays
  INCOMPLETE, **nothing written**. The engine runs no backtest itself.
- **No fabrication.** Only harness outputs that are (a) in the *missing* set and (b) numeric
  are merged. Non-numeric / irrelevant / already-present keys are ignored.
- **Append-only upgrade.** The original INCOMPLETE record is preserved; the re-validated
  version is a *new* judged experiment (`strategy_version` → `…+reval`,
  `source_type=revalidation`, provenance excluded from the dedup hash), linked by identity —
  event-sourced supersede, not mutation.
- **Partial fill stays INCOMPLETE.** Filling some (not all) missing validations upgrades the
  record but keeps status INCOMPLETE — honest about what remains.

## API

`ResearchRevalidationEngine(engine=None)`:
- `plan(record) → RevalidationPlan{present, missing, revalidatable, validation_complete}`
- `revalidate(record, *, harness=None, now, commit) → RevalidationResult{was_incomplete,
  missing_before, filled, missing_after, upgraded, status, new_outcome, new_ingestion_id}`
  where status ∈ `COMPLETE | INCOMPLETE | ALREADY_COMPLETE | UNAVAILABLE`.
- `incomplete_backlog() → RevalidationBacklog` — lists INCOMPLETE ingestions from the `ring_`
  ledger as human-review pointers.

The harness contract: `harness(record) -> dict[str, number]` — return *only* validation
metrics you genuinely computed (e.g. from `research/validation`: `walk_forward`,
`out_of_sample`, `cost_impact`, `parameter_stability`, `random_baseline`). Wiring the real
harness is a programmatic step (kept out of the CLI so the CLI can never fabricate).

## CLI

```
python -m jarvis.research_ingestion revalidate --file record.json   # plan + INCOMPLETE (no harness)
python -m jarvis.research_ingestion revalidate --backlog            # list INCOMPLETE in the ledger
```

## Tests (`tests/test_revalidation.py`, 13)

plan identifies the 5 missing · complete record → no missing · **no-harness → UNAVAILABLE, no
write** · full harness → COMPLETE upgrade (+`reval` run recorded, new outcome) · partial →
INCOMPLETE · **fabricated/irrelevant harness output ignored** · already-complete → ALREADY_COMPLETE ·
backlog lists only INCOMPLETE · advisory · forbidden-import/def/leak scans.

## Files

`revalidation.py` (new), `__main__.py` (+`revalidate`), `__init__.py` (exports),
`tests/test_revalidation.py` (new), this doc. P53 `engine.py` unchanged except the additive
`provenance` channel shared with P55.
