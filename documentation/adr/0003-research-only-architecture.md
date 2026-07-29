# ADR 0003 — Research-Only Architecture

## Status

Accepted.

## Context

The research OS is built on top of an execution-capable trading platform. Combining autonomous
research automation with order-placing capability in the same layers would be dangerous: a bug
or a bad inference could place real trades. We need a hard structural separation.

## Decision

Every research, governance, intelligence, hardening, security, and documentation layer is
**research / analysis / recording only**. These layers must not contain, import, or call any
execution capability: no order, trade, broker, portfolio mutation, capital allocation, model
deployment/promotion, or permission mutation. Reports are non-binding (`is_binding=False`);
anomaly alerts are `is_actionable=False`. *VALIDATED never means deployed.*

## Consequences

- **Safety by construction:** the research stack literally cannot trade; the worst-case failure
  is a wrong record, not a wrong order.
- **Enforcement:** each layer's tests include forbidden-import and forbidden-method AST scans
  (e.g. no `jarvis.execution`, `jarvis.broker`, `jarvis.order`; no `def execute_trade`,
  `place_order`, `deploy_model`, `allocate_capital`).
- **Clear consumer contract:** downstream humans/systems treat research outputs as advisory;
  acting on them is a separate, gated step outside this stack (see ADR 0004).
- **Testability:** `jarvis.compliance` includes a security checklist item asserting no execution
  capability was introduced.
