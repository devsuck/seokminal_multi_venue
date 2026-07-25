# Research Report Agent (P127)

> Integration only — writes the research report. Summary/explanation only, no recommendation.

## What it does — `jarvis/research_workflow/research_writer.py`
`ResearchWriter.write(question, director, memos, review)` → **Research Report** with seven sections:

1. Research Question · 2. Evidence · 3. Historical Context · 4. Analysis · 5. Risks ·
6. Missing Evidence · 7. Next Research Step

Always includes **confidence** and **limitations**. Evidence/confidence come from `decision_support`,
historical context from `recall`, risks/missing from the reviewer output.

## Reuse & no-duplication
recall + decision_support + explainability. No new engine/memory.

## Governance
`is_advisory=True`, `is_decision=False`, `requires_human_review=True`. No investment recommendation.

## Validation
`test_integration_p121_130.py`: exactly 7 sections, confidence + limitations present.

## Files
`jarvis/research_workflow/research_writer.py`, `console_api.py` (`/console/agent-workspace`), this doc.
