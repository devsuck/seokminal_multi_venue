# Research Archive Discovery (P56)

> Governed by `docs/CONSTITUTION.md` and the P53–P55 pipeline docs.
> **Integration over expansion** — read-only static analysis, NO new database, NO ledger writes.
> **Discovery ≠ import.** This layer only *lists candidates*; a human decides what gets imported.
> No trading / execution / broker / capital allocation.

## Problem it fixes

P55 can import a historical file once you point it at one. But the *actual* archives —
old JSON/CSV results, backtest dumps, Markdown reports scattered under `research/`,
`experiments/`, `results/`, `reports/`, `production_review/` — first have to be **found**
and triaged. P56 is the locator.

## What it does

`jarvis/research_ingestion/archive_discovery.py` walks candidate directories, reads each
supported file **read-only**, lightly detects a strategy + metrics (reusing the P55 mapping
layer), and emits a **Research Import Manifest**. It writes to no ledger.

```
directories → walk (skip .git/__pycache__/_state/data/…)
   ↓  per file (.json/.jsonl/.csv/.md/.py)
detect: strategy (P55 map_record) + metrics (P55 _collect_metrics / regex for md·py)
   ↓
candidate = { file, file_type, record_count, detected_strategy, detected_metrics,
              metric_count, confidence, validation_status, import_candidate }
   ↓
Manifest (ranked HIGH→LOW) — advisory, requires_human_review
```

## Detection & scoring (deterministic)

- **Structured** (`.json/.jsonl/.csv`): parsed via `read_records()`; the most metric-rich
  record represents the file (`map_record` + `_collect_metrics`, alias-aware).
- **Text** (`.md/.py`): regex `alias: number` / `alias = number` for metrics; Markdown
  heading or `strategy:` line for the name. Best-effort, lower confidence.
- **confidence**: `HIGH` (named + ≥6 metrics) · `MEDIUM` (named + ≥1, or ≥3 metrics) ·
  `LOW` (weak) · `NONE`.
- **validation_status**: `COMPLETE` / `INCOMPLETE` (via `validate_backtest`) / `NONE` —
  **missing validations are surfaced, never fabricated**.
- **import_candidate**: `True` only when confidence ≥ MEDIUM with a name and metrics — and
  even then it is a *suggestion*; the actual import runs only after human approval via
  `import-history`.

Per-file errors are isolated (a broken file becomes a `NONE` candidate with a note; the
scan never aborts).

## CLI

```
python -m jarvis.research_ingestion discover                     # default roots that exist
python -m jarvis.research_ingestion discover --root research --root reports
python -m jarvis.research_ingestion discover --all               # include non-detections
```

Prints the manifest JSON. It never imports — the human runs `import-history` on approved files.

## Tests (`tests/test_archive_discovery.py`, 13)

full-JSON→HIGH/COMPLETE · incomplete→MEDIUM/INCOMPLETE · markdown metric scan · unsupported→None ·
`discover` finds candidates & ranks HIGH first · **read-only (no ledger writes, empty `_state`)** ·
missing default roots ok · advisory flags · engine wrapper · broken-file isolation ·
forbidden-import/def/leak scans.

## Files

`archive_discovery.py` (new), `__main__.py` (+`discover`), `__init__.py` (exports),
`tests/test_archive_discovery.py` (new), this doc. Nothing else changed.
