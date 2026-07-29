# Read-Only Boundaries

The system is a stack in which **higher layers observe lower layers without mutating them**.
This is enforced structurally, not by convention alone.

## The rule

A layer may **read** another layer's ledger files (to aggregate, verify, or report), but it
**never writes** them and never imports another layer's engine to mutate state. Cross-layer
reads go through file access keyed by `jarvis.config.state_path(name)`.

## How it is enforced

1. **Source ledgers are declared, not imported.** For example, `autonomous_research_os` and
   `research_control` keep a `SOURCE_LEDGERS` / `SOURCE_LAYERS` map of `(filename, id_field)`
   tuples and read those files directly. There is no import coupling that could write them.
2. **Append-only accessors.** A layer's own `ledger.py` opens files exclusively in append mode
   (`open(path, "a")`); there is no update/delete/overwrite API.
3. **Read helpers return copies.** Reads parse JSONL into fresh dicts; callers cannot mutate
   stored state.
4. **Tests assert immutability.** Recovery (`resilience`) and OS layers include tests that read
   a source ledger, run the layer, and assert the source bytes are unchanged.

## Example: the Research OS

`autonomous_research_os` connects to 11 lower layers read-only:

```text
decision_intelligence, autonomous_research_pipeline, autonomous_experiment_scheduler,
research_agent_coordinator, adaptive_research_loop, autonomous_research_evaluation,
research_optimization_engine, research_experience_memory, research_learning,
research_manager, research_control
```

For each, it records an **episode** capturing an observed record count, builds a knowledge
view, and emits a deterministic snapshot. It writes only its own `aros_*` ledgers.

## Example: integrity & resilience

- `jarvis.integrity.verify_ledger(records, ...)` verifies hash chain, tamper, duplicate IDs,
  timestamps, lineage, and replay — all read-only over a records list.
- `jarvis.resilience.recover_to_copy(src, dst)` recovers a valid prefix into a **new** file and
  refuses to write the source (and refuses same-path or overwrite).

## Consequence

Because writes are confined to a layer's own ledgers and all cross-layer access is read-only,
you can reason about each layer in isolation. Observation, analysis, and reporting can never
corrupt the data they observe. See `documentation/architecture/data-flow.md` for the
end-to-end flow.
