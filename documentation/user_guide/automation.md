# Automation

This guide describes how the autonomous layers of the Research OS chain together
to observe, analyze, and record research, without ever executing anything. The
automation is additive and reversible: it only appends to the hash-chained
ledger at `jarvis.config.state_path`, and no step places an order or deploys a
strategy.

## The observe -> analyze -> record loop

```text
autonomous_experiment_scheduler  -> schedules cycles
research_agent_coordinator       -> dispatches research agents
adaptive_research_loop           -> proposes the next task from results
autonomous_research_pipeline     -> runs the cycle end-to-end
research_control                 -> monitors + records (record-only alerts)
autonomous_research_os           -> read-only top-level orchestration
```

Each cycle observes current state, analyzes it, and records findings. Nothing in
the chain has authority to act on the market.

## 1. Run a monitored cycle

```bash
python -m jarvis.autonomous_research_pipeline run --plan PLAN-9 --commit
python -m jarvis.research_control observe --commit
python -m jarvis.research_control health --commit
```

Monitoring emits health, metric, and anomaly alerts, but all of them are
record-only (`is_actionable=False`). An anomaly alert is a note in the ledger,
not a trigger.

```python
alert = {"type": "anomaly", "detail": "eval variance spike", "is_actionable": False}
assert alert["is_actionable"] is False   # never triggers an action
```

## 2. The human/gated boundary

The automation stops at recording. A human review is the only gate that decides
what happens next. The system never crosses from "recorded finding" to "acted
upon."

```text
[automation] observe -> analyze -> record   |  [human] review -> decide
                                            ^
                                     gated boundary
```

## 3. Everything is reversible via history

Because the ledger is append-only, no cycle destroys prior state. To "undo" a
finding you append a correcting record; the original remains verifiable.

```bash
python -m jarvis.autonomous_research_os observe --commit
python -m jarvis.autonomous_research_os verify
```

Dry-runs (omitting `--commit`) let you preview an entire cycle before any record
is written.
