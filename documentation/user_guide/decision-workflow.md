# Decision Workflow

This guide covers the decision-intelligence framing of the Autonomous Quant
Research OS. Candidates are scored and recorded through
`jarvis.decision_intelligence`. Every decision is an advisory record
(`is_binding=False`) that is never executed. Results persist to the append-only,
hash-chained ledger at `jarvis.config.state_path`.

## What a "decision" is here

A decision is a scored, timestamped, verifiable record that ranks or judges
research candidates. It captures the reasoning and the score, so a human (or a
downstream review) can audit it later. It does not place orders, size
positions, or allocate capital.

```text
candidates -> score/record -> advisory decision record (non-binding)
                                     |
                                     +--> human review (the only gate)
```

## 1. Score candidates

The decision layer compares candidates on recorded evaluation metrics. A
dry-run computes the ranking without persisting; `--commit` writes it.

```bash
# dry-run: see the ranking without recording
python -m jarvis.decision_intelligence score --plan PLAN-4

# persist the advisory decision
python -m jarvis.decision_intelligence score --plan PLAN-4 --commit
```

## 2. The recorded decision is advisory

```python
# conceptual shape of a decision record
decision = {
    "plan": "PLAN-4",
    "winner": "CAND-2",
    "score": 0.71,
    "is_binding": False,   # always advisory
    "executed": False,     # never executed by this system
}
assert decision["is_binding"] is False
```

## 3. Verify the decision trail

Because decisions are appended to the same hash-chained ledger, they can be
verified and replayed for identical results.

```bash
python -m jarvis.research_control verify
python -m jarvis.autonomous_research_os verify
```

## Boundaries

- Scoring is deterministic and reproducible.
- A "winner" is a recommendation, not an instruction.
- The only action taken on a decision is human review; the system itself stops
  at recording.
