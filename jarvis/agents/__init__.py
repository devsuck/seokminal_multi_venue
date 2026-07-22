"""Jarvis 에이전트 — 표준 principal(레벨 고정). AI는 자기 레벨 못 올린다."""
from jarvis.permissions import Level, Principal

RESEARCH_AGENT = Principal("research_agent", Level.RESEARCH_ONLY)
# Research Planner — 커버리지 격차 '제안'만. 집행/트레이딩 권한 없음.
PLANNER_AGENT = Principal("planner_agent", Level.RESEARCH_ONLY)
DATAGATE_AGENT = Principal("datagate_agent", Level.BACKTEST_ONLY)
BACKTEST_AGENT = Principal("backtest_agent", Level.BACKTEST_ONLY)
CRITIC_AGENT = Principal("critic_agent", Level.BACKTEST_ONLY)
PAPER_AGENT = Principal("paper_agent", Level.PAPER_ONLY)
# Signal Fusion — 합성신호(자문)만 산출/기록. 주문 권한 없음.
FUSION_AGENT = Principal("fusion_agent", Level.PAPER_ONLY)
# Meta Portfolio — 자본배분 '제안'만 산출/기록. 집행 권한 없음(승인은 사람 게이트).
META_PORTFOLIO_AGENT = Principal("meta_portfolio_agent", Level.LIVE_PROPOSAL_ONLY)
LIVE_PROPOSAL_AGENT = Principal("live_proposal_agent", Level.LIVE_PROPOSAL_ONLY)
# 사람만 — live 승인·리스크·레벨 변경
HUMAN_ADMIN = Principal("human_admin", Level.ADMIN_HUMAN_ONLY, is_human=True)
