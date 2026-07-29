# Research Memory Audit (P131)

> Integration only — audit of the existing memory systems that form the research brain. Read-only.
> Machine-readable form: `jarvis/research_workflow/memory_audit.py::audit_memory()`.

## Memory stores (existing `rmi_` + related)
| Store | Kind | Engine |
|---|---|---|
| rmi_lessons | Lesson | research_memory_intelligence |
| rmi_successes | Success | research_memory_intelligence |
| rmi_failures | Failure | research_memory_intelligence |
| rmi_patterns | Pattern | research_memory_intelligence |
| rmi_memories | Memory (lifecycle) | research_memory_intelligence |
| ring_ingestions | Experiment/Backtest | research_ingestion |
| expt_runs | Experiment run | experiment_tracking |
| ras_notes | Advisory/DecisionMemo | research_assistant |

## Derived layers (read-only, not stores)
`recall`, `memory_graph`, `knowledge_graph` (P79), `timeline` (P78), `failure_intelligence`.

## Mapped entities
`Experiment · Failure · Lesson · Success · Strategy · Company · Market Event`.

## Missing connections (filled by P132–140)
Research-Question/Hypothesis nodes (P132), automatic context recall (P133), similarity (P134), conflict
detection (P135), outcome→lesson conversion (P136), agent↔knowledge link (P137), knowledge quality (P139).

## Governance
Read-only audit; no new DB/ledger/memory.

## Files
`jarvis/research_workflow/memory_audit.py`, `console_api.py` (`/console/memory-audit`), this doc.
