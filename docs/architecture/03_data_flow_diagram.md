# Data Flow Diagram

```
Upstream research ledgers (P10~P28)
        | READ ONLY (JSONL only)
        v
P21 Production Readiness --> P22 Automation --> P23 Monitoring --> P24 Reliability
        |
        v
P25 Autonomous Research --> P26 Agent Coordination --> P27 Memory --> P28 Insight
        |
        v
P29 Strategy Generation --> P30 Meta --> P31 Orchestration --> P32 Resource
        |
        v
P33 API Gateway (read-only) --> P34 Dashboard Backend (aggregation)
        |
        v
P35 System Integration (static validation of all 14 layers)
```

Each arrow is a READ ONLY reference. No layer mutates another layer's ledgers.
