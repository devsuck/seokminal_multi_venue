# Strategy Lifecycle

This guide describes how a research strategy candidate travels from a raw idea
to an archived, evidenced record. The Autonomous Quant Research OS never trades
a strategy: "validated" is a recorded verdict, not a deployment. Every stage is
captured in the append-only, hash-chained ledger at `jarvis.config.state_path`.

## Stages mapped to layers

```text
IDEA        -> jarvis.research_manager            (plan + tasks)
EXPERIMENT  -> jarvis.autonomous_experiment_scheduler
               jarvis.research_agent_coordinator
               jarvis.adaptive_research_loop
EVALUATION  -> jarvis.autonomous_research_evaluation
               jarvis.research_optimization_engine
LEARNING    -> jarvis.research_experience_memory
               jarvis.research_learning
ARCHIVAL    -> jarvis.research_manager archive
               jarvis.autonomous_research_os
```

## 1. Idea

A candidate begins as a research plan. The hypothesis, tasks, and dependencies
are recorded first, so the reasoning is auditable before any experiment runs.

```bash
python -m jarvis.research_manager plan "Momentum + liquidity filter" --commit
python -m jarvis.research_manager task PLAN-7 "Define entry rule" --commit
```

## 2. Experiment

The scheduler and coordinator dispatch research cycles. The adaptive loop
observes intermediate results and proposes the next task, but it only records
suggestions; it never executes an order.

## 3. Evaluation

`jarvis.autonomous_research_evaluation` scores the candidate deterministically,
and `jarvis.research_optimization_engine` records parameter sweeps. The output
is a verdict such as `VALIDATED` or `REJECTED`.

```python
# conceptual: the verdict is a recorded value, not an action
verdict = "VALIDATED"   # advisory only; is_binding is False
assert verdict != "DEPLOYED"  # deployment is never a state in this system
```

## 4. Learning capture

Regardless of verdict, `jarvis.research_experience_memory` and
`jarvis.research_learning` persist what was learned so future cycles can reuse
it. A rejected candidate is as valuable a record as a validated one.

## 5. Archival

```bash
python -m jarvis.research_manager review PLAN-7 --commit
python -m jarvis.research_manager archive PLAN-7 --commit
```

The archived record, including its verdict and lineage, remains permanently
verifiable and reversible only by appending new history.
