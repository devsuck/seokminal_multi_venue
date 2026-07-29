# Diagram — Automation, Decision & Simulation Pipelines

## Automation flow (autonomous research pipeline)

```mermaid
flowchart LR
  SCHED["experiment_scheduler"] --> COORD["agent_coordinator"]
  COORD --> LOOP["adaptive_research_loop"]
  LOOP --> EVAL["research_evaluation"]
  EVAL --> OPT["optimization_engine"]
  OPT --> MEM["experience_memory"]
  MEM --> LEARN["research_learning<br/>(improvement candidates: recorded, never applied)"]
  LEARN -. record only .-> LOG["append-only ledgers"]
```

## Decision pipeline

```mermaid
flowchart LR
  CAND["candidates"] --> SCORE["decision_intelligence<br/>deterministic scoring"]
  SCORE --> SESS["decision session (recorded)"]
  SESS --> OUT["outcome record<br/>is_binding = false"]
  OUT -. advisory, not executed .-> HUMAN["human / gated decision (out of scope)"]
```

## Simulation pipeline

```mermaid
flowchart LR
  IN["inputs"] --> SIM["deterministic simulation / replay"]
  SIM --> CHK["SHA256 checksum fingerprint"]
  CHK --> ART["artifact record"]
  ART --> VER["integrity.verify_benchmark / artifact checks"]
  VER -. validated = recorded verdict, not deployment .-> ARCH["archived"]
```

## Notes

Every stage only observes, analyzes, and records. No stage places orders or deploys. See
`documentation/adr/0008-automation-pipeline.md`, `documentation/adr/0010-decision-intelligence.md`,
and `documentation/adr/0011-simulation-environment.md`.
