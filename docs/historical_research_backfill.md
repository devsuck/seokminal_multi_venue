# Historical Research Backfill Engine (P55)

> Governed by `docs/CONSTITUTION.md`, `docs/AGENTIC_RESEARCH_EVOLUTION.md`, P53
> (`docs/research_data_pipeline.md`), and P54 (`docs/backtest_ingestion_adapter.md`).
> **Integration over expansion** — NO new database, NO parallel research history.
> Reuses `experiment_tracking`, `research_memory_intelligence`, `research_ingestion`,
> and the P54 `backtest_adapter`.
> **No trading. No execution. No broker. No capital allocation.** Jarvis is a research
> memory system, not an autonomous executor.

## Problem it fixes

P54 made *future* backtests flow into memory automatically. But Jarvis had no memory of
**past** research — TSMOM, ORB, VWAP mean-reversion, buyback, liquidity, crypto,
random-baseline and walk-forward studies all lived *outside* the memory system, so
`recall()`, `failure_intelligence()`, and the assistant returned nothing for them.

P55 imports that historical knowledge into the **existing** ledgers so it becomes
searchable — without inventing a new store or a second history.

## Flow

```
Historical file (JSON / JSONL / CSV)
   │  read_records()            ← format detection by extension
   ▼
map_record()                    ← thin mapping layer: field aliases → normalized context
   │  (+ provenance: source_type / source_file / import_timestamp)
   ▼
backtest_adapter.ingest_backtest({}, context, provenance)   ← P54 hook (reused)
   ▼
research_ingestion.ingest()     ← P53 pipeline (reused)
   ├─▶ experiment_tracking   create_experiment / record_run / record_parameter / record_result → expt_*.jsonl
   ├─▶ classify_outcome = SUCCESS | FAILURE | PARTIAL | INCOMPLETE
   ├─▶ FAILURE → auto_classify_failure (9-cat) → record_failure + record_lesson              → rmi_failures/lessons.jsonl
   ├─▶ SUCCESS → record_success (+ lesson)                                                    → rmi_successes/lessons.jsonl
   └─▶ ingestion audit (dedup + hash chain, now w/ source_type/source_file)                   → ring_ingestions.jsonl
                                   │
   research_assistant.recall / failure_intelligence / mistake_check / perspectives  ◀─────────┘  now finds history
```

## 1. Import interface (`jarvis/research_ingestion/history_importer.py`)

`HistoricalResearchImporter(engine=None)`:
- `import_file(path, *, now, commit, field_map)` — reads a file and imports every record.
- `import_records(records, *, source_file, now, commit, field_map)` — imports an in-memory list.

Returns an `ImportSummary`: `record_count`, `imported`, `deduplicated`, `incomplete`,
`failures`, `successes`, `errors` (per-record, isolated), `ingestion_ids`, `is_advisory`.

## 2. Schema detection & mapping (no single old format forced)

`read_records()` detects by extension: **`.jsonl`** (object per line), **`.json`** (array,
or `{"records":[…]}`, or single object), **`.csv`** (row per record via `DictReader`).

`map_record()` is the **mapping layer** — pure key aliasing, no computation:

| Standard field | Accepted aliases |
|---|---|
| `strategy_name` | strategy_name, strategy, name, strategy_id, id |
| `strategy_version` | strategy_version, version, ver |
| `hypothesis` | hypothesis, thesis, description, note, notes |
| `universe` | universe, market, symbols, instrument, instrument_id |
| `features` | features, factors, signals (list or comma/semicolon string) |
| `period` | `period{start,end}`, `date_range[a,b]`, or start/end aliases (start_date, from, …) |
| `outcome` / `lesson` / `root_cause` | outcome/result/verdict · lesson/learning/takeaway · root_cause/failure_reason/reason |

Metrics are collected from nested containers (`metrics`, `validation`, `validation_results`,
`stats`, `results`, `performance`) **and** flat top-level keys, mapped to the standard set
(`return, sharpe, max_drawdown, volatility, walk_forward, out_of_sample, cost_impact,
parameter_stability, random_baseline`) via aliases. A `--field-map` JSON can override any
alias for unusual archives.

## 3. Duplicate protection (content-based)

Dedup reuses P53's identity: `ingestion_id = RING:sha1(strategy_name + backtest_hash)`.
**Provenance is deliberately excluded from `backtest_hash`** — so the *same research
content* re-imported from a different filename, or at a different time, produces the same
hash and creates **no duplicate knowledge** (`deduplicated=True`). Verified by test.

## 4. Provenance (traceability)

Every imported record carries, via a dedicated `provenance` channel that never enters the
dedup hash:
- `source_type = "historical_import"`
- `source_file = <path>`
- `import_timestamp = <now>` (also the audit record's `created_at`)

These are recorded as **experiment parameters** (queryable in `expt_parameters.jsonl`) and
on the `ring_ingestions.jsonl` audit record (`source_type`, `source_file`). `summary()`
now reports `by_source_type` so historical vs. live ingestions are distinguishable.

## 5. Knowledge-quality rule — no fabrication

Missing walk-forward / random-baseline / cost model are **never invented**. When required
validations are absent the outcome is judged **INCOMPLETE** (P53 rule, unchanged) and the
missing set is reported. `_collect_metrics()` only maps values that exist. Verified:
`VWAP_MeanReversion` (only sharpe+return) imports as INCOMPLETE.

## 6. CLI

```
python -m jarvis.research_ingestion import-history --file research_archive.jsonl --commit
python -m jarvis.research_ingestion import-history --file archive.csv --dry-run
python -m jarvis.research_ingestion import-history --file a.json --field-map map.json --commit
```

`--dry-run` always wins over `--commit` (safe default): it maps, detects, and judges
without writing. Prints the full `ImportSummary`.

## 7. Initial validation (known research examples)

A three-record archive (TSMOM success · ORB failure · VWAP incomplete), each in a
*different* shape, is used as the reference. After `--commit`:
- **TSMOM** appears in `recall("TSMOM").tried_before == True`.
- **ORB** appears in `failure_intelligence()` and `mistake_check("ORB").made_this_mistake`;
  classified **REGIME_CHANGE** from its `root_cause`.
- ORB's **lesson** ("regime-dependent; require macro filter") appears in the assistant's
  lesson memory.
- **VWAP** is retained as **INCOMPLETE**, not hidden.

## Tests (`jarvis/research_ingestion/tests/test_history_importer.py`, 26)

Covers all six required cases — (1) file import succeeds, (2) duplicate import → no
duplicate (different filename + time), (3) missing metrics → INCOMPLETE, (4) recall finds
imported research, (5) failure intelligence retrieves old failures, (6) hash chain stays
valid — plus JSON/JSONL/CSV/records-wrapper readers, alias & field-map mapping, date-range
& CSV-string coercion, provenance recorded (params + audit + `by_source_type`), dry-run
writes nothing, per-record error isolation, and forbidden-import / dangerous-def /
model-id-leak scans.

## Files changed

| File | Change |
|---|---|
| `jarvis/research_ingestion/history_importer.py` | **new** — readers, mapping layer, `HistoricalResearchImporter`, `ImportSummary` |
| `jarvis/research_ingestion/backtest_adapter.py` | `ingest_backtest()` gains `provenance` passthrough |
| `jarvis/research_ingestion/engine.py` | `ingest()` gains `provenance` kwarg (params + audit; **excluded from hash**); `summary()` adds `by_source_type` |
| `jarvis/research_ingestion/models.py` | `IngestionRecord` +`source_type`/`source_file`; `IngestionSummary` +`by_source_type` (additive, defaulted) |
| `jarvis/research_ingestion/__main__.py` | + `import-history` subcommand (`--file/--commit/--dry-run/--field-map`) |
| `jarvis/research_ingestion/__init__.py` | export importer API |
| `jarvis/research_ingestion/tests/test_history_importer.py` | **new** — 26 tests |
| `docs/historical_research_backfill.md` | this document |

P1–P54 code, the runners, and existing ledgers on disk: **unchanged** (all additions are
defaulted/optional; existing `ring_` records still verify).

## Remaining gaps

- **Reference archive is synthetic.** The importer is proven against representative shapes,
  but the *actual* historical files (real TSMOM/ORB/buyback/crypto studies) still need to be
  located and pointed at `import-history`. The mapping layer is ready; the data isn't wired.
- **Metric semantics are trusted as-is.** The importer maps whatever the archive reports; it
  does not re-derive walk-forward or random baselines. Records missing them stay INCOMPLETE
  rather than being upgraded — correct, but it means old archives without full validation
  won't become SUCCESS/FAILURE knowledge until re-validated.
- **No UI surface yet.** Import results are visible via CLI/`summary()`; the console has no
  "historical import" panel.

## Next phase recommendation

**P56 — Historical Archive Discovery + Re-validation.** Two tracks: (a) a locator that
scans `research/`, `production_review/`, report folders, and old result JSON/CSV to
auto-build import manifests (so real archives flow through P55 without hand-mapping); and
(b) an optional re-validation pass that runs the existing `research/validation` harness on
INCOMPLETE imports to fill walk-forward / random-baseline / cost gaps — upgrading them from
INCOMPLETE to judged knowledge **without fabricating** anything. A small console panel
(`by_source_type`, INCOMPLETE backlog) would make the backfill visible.
