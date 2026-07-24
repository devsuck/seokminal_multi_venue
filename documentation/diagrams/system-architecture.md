# Diagram — System Architecture

High-level view of the Autonomous Quant Research OS: additive research layers observing an
execution platform they never touch.

```mermaid
flowchart TB
  subgraph EXEC["Execution platform (P1-P8, human-gated, default OFF)"]
    LE["live_execution / execution / permissions"]
  end
  subgraph RESEARCH["Research & Intelligence (P9-P12)"]
    RP["autonomous_research_pipeline"]
    RM["research_manager"]
    RC["research_control"]
    RL["research_learning / experience_memory"]
  end
  subgraph OS["Research OS (P13)"]
    AROS["autonomous_research_os"]
  end
  subgraph HARDEN["Production Hardening (P14)"]
    BENCH["benchmark / cache / concurrency"]
    RES["resilience / profiling / diagnostics"]
  end
  subgraph SEC["Security & Compliance (P15)"]
    S1["security / integrity / sbom"]
    S2["dependency / license / compliance / threat_model"]
  end
  subgraph DOC["Documentation (P16)"]
    D1["documentation (validate + apidoc)"]
  end

  RESEARCH -. READ ONLY .-> AROS
  RESEARCH -. observes, never executes .-> EXEC
  AROS -. READ ONLY .-> HARDEN
  AROS -. READ ONLY .-> SEC
  SEC -. READ ONLY .-> DOC
  HARDEN -. READ ONLY .-> DOC
```

## Reading the diagram

- Solid boxes are additive layer families; dotted arrows are **read-only** observations.
- The research stack observes the execution platform but has no path to execute it.
- Every higher family reads lower families read-only and writes only its own ledgers.

See `documentation/architecture/overview.md` for the narrative.
