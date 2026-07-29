# Report Generation

This guide covers how the Autonomous Quant Research OS produces non-binding
reports, deterministic system snapshots, P15 supply-chain artifacts, and the API
reference. Every report is advisory (`is_binding=False`); a report never
authorizes deployment. Outputs are recorded to the hash-chained ledger at
`jarvis.config.state_path`.

## 1. Non-binding reports

Reports summarize recorded findings for human review.

```bash
python -m jarvis.research_manager report PLAN-5 --commit
python -m jarvis.research_control report --commit
```

```python
report = {"plan": "PLAN-5", "verdict": "VALIDATED", "is_binding": False}
assert report["is_binding"] is False   # advisory, never a deployment order
```

## 2. Deterministic system snapshots

`jarvis.autonomous_research_os` connects all layers read-only and builds a
deterministic snapshot of the whole system. The same state always yields the
same snapshot and checksum.

```bash
python -m jarvis.autonomous_research_os init --commit
python -m jarvis.autonomous_research_os connect --commit
python -m jarvis.autonomous_research_os snapshot --commit
python -m jarvis.autonomous_research_os report --commit
```

## 3. P15 supply-chain artifacts

The P15 set documents the software supply chain and posture. These artifacts are
generated deterministically and are non-binding records:

- SBOM (software bill of materials),
- dependency inventory,
- license report,
- compliance report,
- threat model.

They give reviewers an auditable picture of what the system is built from.

## 4. API reference

Generate the API reference for the codebase with the documentation tool.

```bash
python -m jarvis.documentation gen
```

## 5. Verify what you generated

```bash
python -m jarvis.autonomous_research_os verify
python -m jarvis.research_manager verify
```

Verification confirms the report and snapshot records are intact in the
hash-chain and that a replay reproduces them identically. Reproducible,
verifiable, and advisory: that is the contract for every artifact this system
emits.
