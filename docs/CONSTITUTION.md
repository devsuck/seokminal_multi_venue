# Jarvis Project Constitution (v1.0)

> Read this BEFORE implementing anything.
> This document defines the long-term vision, philosophy and architectural direction of Jarvis.
> Every future implementation MUST follow these principles.
> **If any future implementation conflicts with this document, this document takes precedence.**

## What Jarvis Is

Jarvis is NOT an automated trading system.
Jarvis is NOT a hedge fund execution engine.
Jarvis is NOT a broker.
Jarvis is NOT a portfolio manager.

**Jarvis is a Local-First AI Quant Research Operating System.**

Its purpose is to help a human researcher perform institutional-quality quantitative research more efficiently.
Jarvis exists to think, organize, remember, analyze and explain.
**The human always makes the final investment decision.**

## Core Philosophy

Jarvis should behave like a senior quantitative research partner. Not like an autonomous trader.

Jarvis may: collect information · organize knowledge · generate hypotheses · compare research ·
detect anomalies · explain relationships · suggest experiments · record every result ·
build institutional memory · produce reports · summarize findings · detect duplicated work.

Jarvis must NEVER: execute trades · allocate capital · deploy strategies · approve strategies ·
replace human judgment · hide uncertainty · make financial decisions automatically.

**Human approval is always required.**

## Long-Term Vision

The final product should feel like: *"A personal AI research partner that remembers everything."*
A researcher should be able to ask "What have we already learned about momentum?" and Jarvis answers
using years of accumulated knowledge — research history, failed ideas, successful ideas, simulations,
statistical validation, notes, reports, knowledge graph, memory, previous discussions.
**Jarvis should become the researcher's second brain.**

## Desired Research Workflow

Market Data → Observation → Hypothesis → Experiment Proposal → **Human Approval** →
Research Execution → Validation → Report Generation → Knowledge Extraction → Memory Update → Future Research

*Jarvis prepares. Humans decide.*

## Knowledge First

The most valuable asset of Jarvis is NOT code. It is accumulated research knowledge.
Failed research is NOT wasted — it becomes future knowledge.
Jarvis should remember why something failed/worked, under what market conditions, which assumptions
were incorrect, which parameters were unstable, which datasets were unreliable.
Future research should always reuse previous knowledge.

## Simplicity Over Complexity

The architecture should become **simpler** over time.
**Never create a new module if an existing module can be extended.**
Prefer integration · consolidation · reuse — instead of duplication · parallel systems · similar
intelligence layers. Complexity must always be justified.

## Local First

One user · local execution · personal workstation · no cloud dependency · no enterprise architecture ·
no SaaS assumptions. Future cloud support should be optional; never make local usage worse for cloud.

## User Experience Philosophy

The user should not need to understand internal architecture. Internally there may be many modules;
externally Jarvis should feel like **one coherent assistant**. Avoid exposing implementation details.

## Desired Interface

Jarvis should revolve around a small number of workspaces:
**Home · Research · Experiments · Knowledge · Assistant · System.**
Avoid creating dozens of pages. If a new feature is added, first determine whether it belongs inside an
existing workspace. Navigation should become simpler over time.

## The Assistant Is The Primary Interface

The assistant should become the central way of interacting with Jarvis. Examples:
"What changed this week?" · "What did we learn from buyback research?" · "Have we already tested this idea?" ·
"Why did this experiment fail?" · "What should I review next?"
Conversational rather than procedural.

## Memory Is The Competitive Advantage

Jarvis should never forget. Years later: "Didn't we already try something similar?" → immediately retrieve
related experiments · reports · assumptions · datasets · validation · outcomes · lessons learned.
**Knowledge continuity is more valuable than adding new features.**

## Integration Before Expansion

Whenever implementing a new feature, first inspect existing functionality. Ask: Can this be integrated?
Can an existing module perform this task? Can complexity be reduced?
**Only create a new module if integration is clearly impossible.**

## Implementation Principles

Every implementation should preserve: reproducibility · determinism · auditability · lineage ·
explainability · security · modularity. **Never sacrifice transparency for automation.**

## Automation Philosophy

Good automation: report generation · research organization · experiment tracking · memory updates ·
documentation · validation.
Bad automation: autonomous trading · autonomous investment · autonomous deployment · autonomous approval.
Automation should remove repetitive work, NOT human responsibility.

## Future Development Rule

Before implementing any new phase, evaluate:
1. Does this improve research quality?
2. Does this simplify the researcher workflow?
3. Does this reduce duplicated work?
4. Does this strengthen institutional memory?
5. Does this preserve human control?

**If the answer is "No", reconsider the implementation.**

## Final Goal

The final vision is not an AI trader. It is an **AI Quant Research Operating System** — a system that helps
one researcher perform years of institutional-quality quantitative research while remembering everything,
explaining everything and making future research progressively smarter.
**Jarvis should become an extension of the researcher's thinking. Not a replacement for it.**
