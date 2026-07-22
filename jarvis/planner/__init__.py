"""jarvis.planner — Research Planner Layer (P5). 커버리지 최적화기(아이디어 생성기 아님).

P3 projection + P4 knowledge graph 위. 제안 전용, 집행/트레이딩 없음.
결정적 · 소스 JSONL 무변경.
"""
from jarvis.planner.models import CATEGORIES, PlannerProposal, ResearchGap  # noqa: F401
from jarvis.planner.planner import PlannerReport, run_planner, write_proposals  # noqa: F401
from jarvis.planner.verify import verify  # noqa: F401
