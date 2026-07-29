# Research Council Evolution (P90)

> Integration only — expands the existing council to **7 perspectives**. Agents produce arguments,
> not decisions. Reuses the existing council; adds no separate agents.

## What it does — `jarvis/research_workflow/council_evolution.py` + `/console/council-expanded`
`deliberate(question)` reuses `ResearchCouncilEngine.deliberate` (P59–60, 6 lenses) and injects the
missing perspectives — **Industry, Behavioral, Contrarian, Portfolio** — derived deterministically
from recall + mistake history, giving the full set: **Quant · Macro · Industry · Behavioral · Risk ·
Contrarian · Portfolio**. Each lens is an argument (stance + rationale); the memo still requires
human judgment.

> Behavioral cautions on past failures (confirmation bias); Contrarian cautions when the idea is
> crowded (many prior records); Portfolio defers to the P92 simulator.

## Reuse & no-duplication
Reuses the existing council's signal-injection mechanism — **no new agent module**. Deterministic,
`is_decision=False`.

## Validation
`test_integration_p86_95.py`: 7 perspectives present including the 4 new lenses.

## Files
`jarvis/research_workflow/council_evolution.py`, `console_api.py`, this doc.
